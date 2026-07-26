import calendar
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.catalog.models import ProductVersion
from app.domains.contracts.models import Contract, ContractAttribution, ContractStatusHistory
from app.domains.contracts.state_machine import assert_transition_allowed, event_name_for
from app.domains.customers.models import SupplyPoint
from app.domains.network import service as network_service
from app.domains.network.models import AgentProfile
from app.domains.outbox import service as outbox_service

# Statuses that represent "the contract's term is running" -- entering one of
# these (re)starts the clock on activated_at/expires_at. Renewing a lapsed
# (EXPIRED) contract restarts it too, same as the first activation.
TERM_START_STATUSES = {"ACTIVE", "RENEWED"}


def _add_months(dt: datetime, months: int) -> datetime:
    """Stdlib month arithmetic (no dateutil dependency): clamps the day to the
    target month's actual length, e.g. Jan 31 + 1 month -> Feb 28/29."""
    total_months = dt.month - 1 + months
    year = dt.year + total_months // 12
    month = total_months % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


async def to_read_dicts(db: AsyncSession, contracts: list[Contract]) -> list[dict]:
    """Bulk-attaches product_name/supply_point_label to a page of contracts --
    the "name prominent, id small below" rule applies to every contract list in
    the app, so this is the single place that does the join instead of each
    caller re-deriving it (or, worse, the UI showing a bare UUID)."""
    if not contracts:
        return []

    product_version_ids = {c.product_version_id for c in contracts}
    supply_point_ids = {c.supply_point_id for c in contracts}

    product_names = dict(
        (
            await db.execute(
                select(ProductVersion.id, ProductVersion.name).where(ProductVersion.id.in_(product_version_ids))
            )
        ).all()
    )
    supply_point_labels = dict(
        (
            await db.execute(
                select(SupplyPoint.id, SupplyPoint.label).where(SupplyPoint.id.in_(supply_point_ids))
            )
        ).all()
    )

    result = []
    for c in contracts:
        row = {
            "id": c.id,
            "customer_id": c.customer_id,
            "supply_point_id": c.supply_point_id,
            "product_version_id": c.product_version_id,
            "status": c.status,
            "notes": c.notes,
            "created_at": c.created_at,
            "activated_at": c.activated_at,
            "expires_at": c.expires_at,
            "product_name": product_names.get(c.product_version_id),
            "supply_point_label": supply_point_labels.get(c.supply_point_id),
        }
        result.append(row)
    return result


class InvalidProducerAgentError(Exception):
    """Raised when a contract is created with a producer_agent_id that does not
    resolve to a real, active agent in this organization. Left unchecked, this
    silently breaks commission calculation later: create_snapshot_for_contract()
    would freeze an empty ancestor chain for a nonexistent agent, and
    run_calculation_for_contract() would then find an empty chain and skip
    calculation entirely -- see docs/paid-contract-commission-audit.md, Problem #1.
    Failing fast here, at creation time, is far cheaper than discovering it after
    activation with no commissions paid and nothing to point to why."""


async def create_contract(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    supply_point_id: uuid.UUID,
    product_version_id: uuid.UUID,
    producer_agent_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: str,
    notes: str | None = None,
) -> Contract:
    """Creates a DRAFT contract. Deliberately does NOT touch commissions -- creating
    or submitting a contract never generates a commission (business-rules.md)."""
    producer = await db.get(AgentProfile, producer_agent_id)
    if producer is None or producer.organization_id != organization_id:
        raise InvalidProducerAgentError(
            f"producer_agent_id {producer_agent_id} is not a known agent in this organization"
        )
    if producer.status != "ACTIVE":
        raise InvalidProducerAgentError(
            f"producer_agent_id {producer_agent_id} is {producer.status}, not ACTIVE -- "
            "cannot attribute a new contract to a non-active agent"
        )

    attribution = ContractAttribution(
        organization_id=organization_id,
        producer_agent_id=producer_agent_id,
        attributed_promoter_id=producer_agent_id,
    )
    db.add(attribution)
    await db.flush()

    contract = Contract(
        organization_id=organization_id,
        customer_id=customer_id,
        supply_point_id=supply_point_id,
        product_version_id=product_version_id,
        contract_attribution_id=attribution.id,
        status="DRAFT",
        notes=notes,
    )
    db.add(contract)
    await db.flush()

    db.add(
        ContractStatusHistory(
            contract_id=contract.id,
            from_status=None,
            to_status="DRAFT",
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
    )
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract.created", entity_type="contract", entity_id=str(contract.id),
        new_value={"status": "DRAFT"},
    )
    await db.commit()
    await db.refresh(contract)
    return contract


async def transition_contract(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contract: Contract,
    to_status: str,
    actor_user_id: uuid.UUID,
    reason: str | None,
    notes: str | None,
    correlation_id: str,
) -> Contract:
    """The single entry point for every contract status change. Validates the
    transition against the explicit state machine, records history + audit, and --
    only for ACTIVE -- freezes a network snapshot and enqueues the domain event that
    triggers commission calculation. Never generates a commission for any other
    transition."""
    from_status = contract.status
    assert_transition_allowed(from_status, to_status)

    if to_status == "ACTIVE":
        attribution = await db.get(ContractAttribution, contract.contract_attribution_id)
        snapshot = await network_service.create_snapshot_for_contract(
            db,
            organization_id=organization_id,
            producer_agent_id=attribution.producer_agent_id,
        )
        contract.network_snapshot_id = snapshot.id

    if to_status in TERM_START_STATUSES:
        now = utcnow()
        contract.activated_at = now
        product_version = await db.get(ProductVersion, contract.product_version_id)
        duration = product_version.contract_duration_months if product_version else None
        contract.expires_at = _add_months(now, duration) if duration else None

    contract.status = to_status
    db.add(
        ContractStatusHistory(
            contract_id=contract.id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            reason=reason,
            notes=notes,
            correlation_id=correlation_id,
        )
    )

    event_name = event_name_for(from_status, to_status)
    if event_name is not None:
        db.add(
            outbox_service.enqueue(
                organization_id=organization_id,
                event_type=event_name,
                payload={"contract_id": str(contract.id), "correlation_id": correlation_id},
            )
        )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract.transitioned", entity_type="contract", entity_id=str(contract.id),
        previous_value={"status": from_status}, new_value={"status": to_status},
        reason=reason, correlation_id=correlation_id,
    )
    await db.commit()
    await db.refresh(contract)
    return contract
