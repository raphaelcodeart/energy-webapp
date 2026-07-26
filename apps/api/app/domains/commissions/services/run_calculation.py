import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit import service as audit_service
from app.domains.commissions.calculators.entrepreneurial_difference import (
    ChainMember,
    calculate_chain,
)
from app.domains.commissions.models import (
    CommissionCalculation,
    CommissionCalculationStep,
    CommissionMovement,
    Rank,
)
from app.domains.contracts.models import Contract
from app.domains.network.models import NetworkSnapshotNode

RULE_VERSION = "2026.1-placeholder"  # see docs/open-questions.md #1


def _idempotency_key(contract_id: uuid.UUID, trigger_event_id: uuid.UUID, agent_id: str, movement_type: str) -> str:
    raw = f"{contract_id}:{trigger_event_id}:{agent_id}:{movement_type}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def _build_chain(
    db: AsyncSession, *, network_snapshot_id: uuid.UUID
) -> list[ChainMember]:
    stmt = (
        select(
            NetworkSnapshotNode.ancestor_agent_id,
            NetworkSnapshotNode.depth,
            Rank.code,
            Rank.personal_token_cents,
        )
        .join(Rank, Rank.id == NetworkSnapshotNode.rank_id_at_snapshot, isouter=True)
        .where(NetworkSnapshotNode.snapshot_id == network_snapshot_id)
        .order_by(NetworkSnapshotNode.depth.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        ChainMember(
            agent_id=str(agent_id),
            rank_code=rank_code or "UNRANKED",
            personal_token_cents=personal_token_cents or 0,
            depth=depth,
        )
        for agent_id, depth, rank_code, personal_token_cents in rows
    ]


async def _get_existing(
    db: AsyncSession, *, contract_id: uuid.UUID, trigger_event_id: uuid.UUID
) -> CommissionCalculation | None:
    return (
        await db.execute(
            select(CommissionCalculation).where(
                CommissionCalculation.contract_id == contract_id,
                CommissionCalculation.trigger_event_id == trigger_event_id,
            )
        )
    ).scalar_one_or_none()


async def run_calculation_for_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_id: uuid.UUID, trigger_event_id: uuid.UUID
) -> CommissionCalculation | None:
    """Idempotent: re-invoking with the same (contract_id, trigger_event_id) is a
    no-op if a calculation already exists for that pair. Single transaction: either
    everything (calculation + steps + movements) is persisted, or nothing is.

    The (contract_id, trigger_event_id) check below is the fast path, but it is
    only an application-level SELECT-then-INSERT -- see
    uq_commission_calculations_contract_trigger on the model for the DB-level
    backstop this function falls back to if two dispatches race (docs/
    paid-contract-commission-audit.md, Problem #3)."""
    existing = await _get_existing(db, contract_id=contract_id, trigger_event_id=trigger_event_id)
    if existing is not None:
        return existing

    contract = await db.get(Contract, contract_id)
    if contract is None or contract.network_snapshot_id is None:
        raise ValueError("Contract has no network snapshot; cannot calculate commissions")

    chain = await _build_chain(db, network_snapshot_id=contract.network_snapshot_id)
    if not chain:
        # Producer (or its whole ancestor chain) resolved to nothing -- most
        # likely an agent that no longer exists or was removed from the
        # network between contract creation and activation. Recording this as
        # a FAILED calculation (instead of silently returning None) is what
        # makes this visible to accounting/ops instead of the contract just
        # quietly paying nobody forever. See docs/paid-contract-commission-audit.md,
        # Problem #1.
        calculation = CommissionCalculation(
            organization_id=organization_id,
            contract_id=contract_id,
            network_snapshot_id=contract.network_snapshot_id,
            trigger_event_id=trigger_event_id,
            input_snapshot={"contract_id": str(contract_id), "network_snapshot_id": str(contract.network_snapshot_id), "chain": []},
            output_snapshot={"steps": [], "error": "empty_ancestor_chain"},
            checksum=hashlib.sha256(b"empty_ancestor_chain").hexdigest(),
            status="FAILED",
        )
        db.add(calculation)
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=None,
            action="commission.calculation_failed", entity_type="contract", entity_id=str(contract_id),
            new_value={"reason": "empty_ancestor_chain", "network_snapshot_id": str(contract.network_snapshot_id)},
            reason="Network snapshot has no ancestor nodes -- producer agent could not be resolved",
        )
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await _get_existing(db, contract_id=contract_id, trigger_event_id=trigger_event_id)
            if existing is not None:
                return existing
            raise
        await db.refresh(calculation)
        return calculation

    steps = calculate_chain(chain)

    input_snapshot = {
        "contract_id": str(contract_id),
        "network_snapshot_id": str(contract.network_snapshot_id),
        "chain": [
            {"agent_id": m.agent_id, "rank_code": m.rank_code, "depth": m.depth}
            for m in chain
        ],
    }
    output_snapshot = {
        "steps": [
            {
                "beneficiary_agent_id": s.beneficiary_agent_id,
                "movement_type": s.movement_type,
                "gross_amount_cents": s.gross_amount_cents,
                "explanation": s.explanation,
            }
            for s in steps
        ]
    }
    checksum = hashlib.sha256(
        json.dumps({"input": input_snapshot, "output": output_snapshot}, sort_keys=True).encode()
    ).hexdigest()

    calculation = CommissionCalculation(
        organization_id=organization_id,
        contract_id=contract_id,
        network_snapshot_id=contract.network_snapshot_id,
        trigger_event_id=trigger_event_id,
        input_snapshot=input_snapshot,
        output_snapshot=output_snapshot,
        checksum=checksum,
        status="COMPLETED",
    )
    db.add(calculation)
    try:
        # The INSERT (and therefore the earliest point a concurrent dispatch of
        # the same trigger event can be caught by
        # uq_commission_calculations_contract_trigger) happens here, at flush --
        # not at the later db.commit(). calculation.id is needed immediately
        # below for the steps/movements, so this flush cannot be deferred.
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing = await _get_existing(db, contract_id=contract_id, trigger_event_id=trigger_event_id)
        if existing is not None:
            return existing
        raise

    today = datetime.now(UTC).date()
    for order, step in enumerate(steps):
        db.add(
            CommissionCalculationStep(
                calculation_id=calculation.id,
                step_order=order,
                beneficiary_agent_id=uuid.UUID(step.beneficiary_agent_id),
                rank_at_calculation=step.rank_code,
                base_amount_cents=step.base_amount_cents,
                already_distributed_cents=step.already_distributed_cents,
                entrepreneurial_difference_cents=step.entrepreneurial_difference_cents,
                personal_bonus_cents=0,
                gross_amount_cents=step.gross_amount_cents,
                movement_type=step.movement_type,
                explanation=step.explanation,
            )
        )
        if step.gross_amount_cents > 0:
            db.add(
                CommissionMovement(
                    organization_id=organization_id,
                    agent_id=uuid.UUID(step.beneficiary_agent_id),
                    contract_id=contract_id,
                    origin_event_id=trigger_event_id,
                    calculation_id=calculation.id,
                    movement_type=step.movement_type,
                    amount_cents=step.gross_amount_cents,
                    currency="EUR",
                    status="ACCRUED",
                    effective_date=today,
                    rule_version_id=RULE_VERSION,
                    network_snapshot_id=contract.network_snapshot_id,
                    idempotency_key=_idempotency_key(
                        contract_id, trigger_event_id, step.beneficiary_agent_id, step.movement_type
                    ),
                )
            )

    try:
        await db.commit()
    except IntegrityError:
        # Lost a race against a concurrent dispatch of the same trigger event
        # (see uq_commission_calculations_contract_trigger). The other side
        # already committed the real calculation + movements -- return that one
        # instead of raising, so the caller sees a normal idempotent result
        # rather than an error for what is, from the caller's perspective, a
        # successfully-processed event.
        await db.rollback()
        existing = await _get_existing(db, contract_id=contract_id, trigger_event_id=trigger_event_id)
        if existing is not None:
            return existing
        raise
    await db.refresh(calculation)
    return calculation
