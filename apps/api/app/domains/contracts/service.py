import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit import service as audit_service
from app.domains.contracts.models import Contract, ContractAttribution, ContractStatusHistory
from app.domains.contracts.state_machine import assert_transition_allowed, event_name_for
from app.domains.network import service as network_service
from app.domains.outbox import service as outbox_service


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
) -> Contract:
    """Creates a DRAFT contract. Deliberately does NOT touch commissions -- creating
    or submitting a contract never generates a commission (business-rules.md)."""
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
