import calendar
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts.models import Contract, ContractAttribution, ContractStatusHistory
from app.domains.contracts.state_machine import assert_transition_allowed, event_name_for
from app.domains.customers.models import SupplyPoint
from app.domains.network import service as network_service
from app.domains.network.models import AgentProfile
from app.domains.notifications import service as notifications_service
from app.domains.outbox import service as outbox_service
from app.domains.users.models import User

if TYPE_CHECKING:
    # Annotation-only -- the real import stays function-local in
    # create_contract_self_service, matching this module's existing
    # convention (see e.g. the customers/network imports below).
    from app.domains.customers.schemas import SupplyPointCreate

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
            "iban": c.iban,
            "created_at": c.created_at,
            "activated_at": c.activated_at,
            "expires_at": c.expires_at,
            "product_name": product_names.get(c.product_version_id),
            "supply_point_label": supply_point_labels.get(c.supply_point_id),
        }
        result.append(row)
    return result


async def get_status_history(db: AsyncSession, *, contract_id: uuid.UUID) -> list[dict]:
    """Full audit trail of every status change for one contract (who, when,
    from/to, why) -- backs the "click the status badge" history popup. Actor
    display name prefers the agent's display_name (how they're known
    everywhere else in the app) and falls back to their login email for a
    pure back-office user with no AgentProfile row."""
    stmt = (
        select(ContractStatusHistory)
        .where(ContractStatusHistory.contract_id == contract_id)
        .order_by(ContractStatusHistory.created_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return []

    user_ids = {r.actor_user_id for r in rows}
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars()}
    agents_by_user = {
        a.user_id: a
        for a in (
            await db.execute(select(AgentProfile).where(AgentProfile.user_id.in_(user_ids)))
        ).scalars()
    }

    result = []
    for r in rows:
        agent = agents_by_user.get(r.actor_user_id)
        user = users.get(r.actor_user_id)
        actor_name = agent.display_name if agent else (user.email if user else "—")
        result.append({
            "id": r.id,
            "from_status": r.from_status,
            "to_status": r.to_status,
            "actor_user_id": r.actor_user_id,
            "actor_name": actor_name,
            "reason": r.reason,
            "notes": r.notes,
            "created_at": r.created_at,
        })
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
    iban: str | None = None,
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
        iban=iban,
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
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CONTRACT_CREATED", entity_type="contract", entity_id=contract.id,
        title="Nuovo contratto creato", body=f"Contratto {contract.id} in stato Bozza.",
        exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(contract)
    return contract


class SelfServiceContractError(Exception):
    pass


async def _resolve_referring_agent_id_for_customer(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> uuid.UUID | None:
    """Same lookup network/service.py::_resolve_referring_agent_id does (by
    user_id) but keyed directly by customer_id, which
    create_contract_self_service already has on hand -- duplicated rather
    than imported across domains, matching this codebase's convention for
    small, domain-local batch/lookup helpers (see e.g. orders/service.py's
    own copy of _resolve_display_name)."""
    from app.domains.referral.models import CustomerAttribution, PromoterCode

    stmt = (
        select(PromoterCode.agent_id)
        .select_from(CustomerAttribution)
        .join(PromoterCode, PromoterCode.id == CustomerAttribution.promoter_code_id)
        .where(CustomerAttribution.organization_id == organization_id, CustomerAttribution.customer_id == customer_id)
        .order_by(CustomerAttribution.attributed_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_contract_self_service(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    product_version_id: uuid.UUID,
    supply_point_payload: "SupplyPointCreate",
) -> Contract:
    """'Attiva Contratto': a customer activates a Lial Energy (INTERNAL)
    product themselves, no promoter/admin action needed to get it started.
    Resolves the commission producer from the customer's own referral
    attribution (same sponsor "lavora con noi" auto-activation uses) --
    there is no self-service way to pick a different one, registration is
    invite-only precisely so this attribution always exists (see
    auth/service.py::register_with_referral). Immediately submits and marks
    DOCUMENTS_PENDING -- unlike a promoter/admin building up a DRAFT by
    hand, self-service has no "save for later, not ready to send yet" step;
    the customer's next action is exactly what DOCUMENTS_PENDING says:
    upload the required documents (business-rules.md#contract-self-service)."""
    from app.domains.customers import service as customers_service
    from app.domains.customers.models import Customer

    customer = (
        await db.execute(
            select(Customer).where(Customer.organization_id == organization_id, Customer.user_id == customer_user_id)
        )
    ).scalar_one_or_none()
    if customer is None:
        raise SelfServiceContractError("No customer record linked to this account")

    version = await db.get(ProductVersion, product_version_id)
    if version is None:
        raise SelfServiceContractError("Product version not found")
    product = await db.get(Product, version.product_id)
    if product is None or product.organization_id != organization_id:
        raise SelfServiceContractError("Product version not found")
    if product.category != "INTERNAL":
        raise SelfServiceContractError(
            "Solo i prodotti Lial Energy si attivano come contratto -- gli altri prodotti si acquistano come ordine."
        )

    producer_agent_id = await _resolve_referring_agent_id_for_customer(
        db, organization_id=organization_id, customer_id=customer.id
    )
    if producer_agent_id is None:
        raise SelfServiceContractError(
            "Nessun promoter di riferimento trovato per il tuo account -- contatta l'assistenza."
        )

    supply_point = await customers_service.add_supply_point(
        db, organization_id=organization_id, customer_id=customer.id,
        payload=supply_point_payload, actor_user_id=customer_user_id,
    )
    if supply_point is None:
        raise SelfServiceContractError("Unable to create supply point")

    contract = await create_contract(
        db, organization_id=organization_id, customer_id=customer.id,
        supply_point_id=supply_point.id, product_version_id=product_version_id,
        producer_agent_id=producer_agent_id, actor_user_id=customer_user_id,
        correlation_id=str(uuid.uuid4()),
    )
    contract = await transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="SUBMITTED",
        actor_user_id=customer_user_id, reason="Attivazione self-service", notes=None,
        correlation_id=str(uuid.uuid4()),
    )
    contract = await transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="DOCUMENTS_PENDING",
        actor_user_id=customer_user_id, reason=None, notes=None,
        correlation_id=str(uuid.uuid4()),
    )
    return contract


async def set_contract_iban(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, iban: str, actor_user_id: uuid.UUID
) -> Contract:
    """Lets a customer add/correct their own contract's IBAN after creation
    (e.g. the admin created the contract before receiving it, or the
    customer wants to switch bank accounts) -- same "editable afterwards"
    spirit as supply_points.label."""
    previous = contract.iban
    contract.iban = iban
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract.iban_updated", entity_type="contract", entity_id=str(contract.id),
        previous_value={"iban": previous}, new_value={"iban": iban},
    )
    await db.commit()
    await db.refresh(contract)
    return contract


# Transitions with no separate decision of their own -- entering the key
# status on the left always immediately continues to the value on the
# right, so a human never has to click through it as its own step. Added
# Session 29 per explicit request ("l'amministratore deve recensire il
# contratto solo nel passo finale di renderlo pagato"): APPROVED and
# PAYMENT_PENDING/PAID were real staff clicks before, now only "Approva"
# (UNDER_REVIEW -> APPROVED, which cascades on into PAYMENT_PENDING) and
# "Conferma pagamento" (PAYMENT_PENDING -> PAID, which cascades on through
# ACTIVATION_PENDING into ACTIVE) require a human. See
# business-rules.md#contract-self-service. Every hop here is still a real,
# individually-audited transition_contract() call -- this only removes the
# need for someone to manually click each one.
AUTO_CASCADE_AFTER: dict[str, str] = {
    "APPROVED": "PAYMENT_PENDING",
    "PAID": "ACTIVATION_PENDING",
    "ACTIVATION_PENDING": "ACTIVE",
}


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
    transition. Auto-cascades through AUTO_CASCADE_AFTER once the requested
    transition lands -- e.g. a single UNDER_REVIEW->APPROVED call returns a
    contract already in PAYMENT_PENDING."""
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

    next_status = AUTO_CASCADE_AFTER.get(contract.status)
    if next_status is not None:
        contract = await transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=next_status,
            actor_user_id=actor_user_id, reason="Automatico -- nessuna decisione separata richiesta",
            notes=None, correlation_id=correlation_id,
        )
    return contract
