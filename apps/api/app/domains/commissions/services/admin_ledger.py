"""Org-wide commission traceability + payment tracking for admin/staff --
answers "why did this promoter get this commission, from which contract,
from which level of the network, based on which qualification" (per
CommissionCalculationStep, already computed at calculation time but never
exposed until now) and "has this actually been paid" (CommissionMovement.status
already had a PAID state in the schema; nothing ever set it -- see
docs/business-rules.md#commission-payment-tracking)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.catalog.models import ProductVersion
from app.domains.commissions.models import CommissionCalculationStep, CommissionMovement, Rank
from app.domains.contracts.models import Contract, ContractAttribution
from app.domains.customers.models import Company, Customer, CustomerProfile
from app.domains.customers.service import display_name_for
from app.domains.network.models import AgentProfile, NetworkSnapshotNode

PAYABLE_STATUSES = {"ACCRUED", "PAYABLE", "SCHEDULED"}


class CommissionPaymentError(Exception):
    pass


async def get_commission_movements(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    agent_id: uuid.UUID | None = None,
    status: str | None = None,
    contract_id: uuid.UUID | None = None,
) -> list[dict]:
    stmt = (
        select(
            CommissionMovement.id,
            CommissionMovement.agent_id,
            CommissionMovement.contract_id,
            CommissionMovement.movement_type,
            CommissionMovement.amount_cents,
            CommissionMovement.status,
            CommissionMovement.effective_date,
            CommissionMovement.paid_date,
            CommissionMovement.network_snapshot_id,
            Contract.customer_id,
            ContractAttribution.producer_agent_id,
            ProductVersion.name,
            ProductVersion.base_price_cents,
        )
        .select_from(CommissionMovement)
        .join(Contract, Contract.id == CommissionMovement.contract_id)
        .join(ContractAttribution, ContractAttribution.id == Contract.contract_attribution_id)
        .join(ProductVersion, ProductVersion.id == Contract.product_version_id)
        .where(CommissionMovement.organization_id == organization_id)
        .order_by(CommissionMovement.created_at.desc())
    )
    if agent_id is not None:
        stmt = stmt.where(CommissionMovement.agent_id == agent_id)
    if status is not None:
        stmt = stmt.where(CommissionMovement.status == status)
    if contract_id is not None:
        stmt = stmt.where(CommissionMovement.contract_id == contract_id)

    rows = (await db.execute(stmt)).all()
    if not rows:
        return []

    movement_ids = [r[0] for r in rows]
    agent_ids = {r[1] for r in rows} | {r[10] for r in rows}
    customer_ids = {r[9] for r in rows}
    snapshot_ids = {r[8] for r in rows}

    agents = {
        a.id: a for a in (await db.execute(select(AgentProfile).where(AgentProfile.id.in_(agent_ids)))).scalars()
    }
    customers = {c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars()}
    profiles = {
        p.customer_id: p
        for p in (await db.execute(select(CustomerProfile).where(CustomerProfile.customer_id.in_(customer_ids)))).scalars()
    }
    companies = {
        c.customer_id: c
        for c in (await db.execute(select(Company).where(Company.customer_id.in_(customer_ids)))).scalars()
    }
    ranks_by_id = {r.id: r for r in (await db.execute(select(Rank).where(Rank.organization_id == organization_id))).scalars()}

    # step explanations, keyed by (calculation happens per contract+trigger, but
    # a beneficiary can only appear once per calculation) -- join via
    # calculation_id + beneficiary_agent_id.
    calc_ids_stmt = select(CommissionMovement.calculation_id).where(CommissionMovement.id.in_(movement_ids))
    calc_ids = {row[0] for row in (await db.execute(calc_ids_stmt)).all()}
    steps = (
        await db.execute(
            select(CommissionCalculationStep).where(CommissionCalculationStep.calculation_id.in_(calc_ids))
        )
    ).scalars().all()
    step_by_calc_and_agent = {(s.calculation_id, s.beneficiary_agent_id): s for s in steps}

    movement_calc = dict(
        (await db.execute(select(CommissionMovement.id, CommissionMovement.calculation_id).where(CommissionMovement.id.in_(movement_ids)))).all()
    )

    # Depth of each beneficiary relative to the contract's producer, frozen at
    # activation time -- depth 0 is the producer themselves.
    snapshot_depths = {}
    if snapshot_ids:
        depth_rows = (
            await db.execute(
                select(NetworkSnapshotNode.snapshot_id, NetworkSnapshotNode.ancestor_agent_id, NetworkSnapshotNode.depth)
                .where(NetworkSnapshotNode.snapshot_id.in_(snapshot_ids))
            )
        ).all()
        for snap_id, ancestor_id, depth in depth_rows:
            snapshot_depths[(snap_id, ancestor_id)] = depth

    result = []
    for (
        mv_id, mv_agent_id, contract_id_, movement_type, amount_cents, mv_status, effective_date, paid_date,
        network_snapshot_id, customer_id, producer_agent_id, product_name, base_price_cents,
    ) in rows:
        agent = agents.get(mv_agent_id)
        producer = agents.get(producer_agent_id)
        customer = customers.get(customer_id)
        step = step_by_calc_and_agent.get((movement_calc.get(mv_id), mv_agent_id))
        depth = snapshot_depths.get((network_snapshot_id, mv_agent_id))
        rank = ranks_by_id.get(agent.current_rank_id) if agent and agent.current_rank_id else None

        result.append({
            "id": mv_id,
            "contract_id": contract_id_,
            "customer_id": customer_id,
            "customer_name": display_name_for(customer.kind, profiles.get(customer_id), companies.get(customer_id)) if customer else "—",
            "product_name": product_name,
            "value_cents": base_price_cents,
            "agent_id": mv_agent_id,
            "agent_name": agent.display_name if agent else "—",
            "agent_promoter_code": agent.promoter_code if agent else "—",
            "agent_current_rank_code": rank.code if rank else None,
            "producer_agent_id": producer_agent_id,
            "producer_name": producer.display_name if producer else "—",
            "depth_from_producer": depth,
            "movement_type": movement_type,
            "rank_at_calculation": step.rank_at_calculation if step else None,
            "base_amount_cents": step.base_amount_cents if step else None,
            "already_distributed_cents": step.already_distributed_cents if step else None,
            "entrepreneurial_difference_cents": step.entrepreneurial_difference_cents if step else None,
            "amount_cents": amount_cents,
            "explanation": step.explanation if step else None,
            "status": mv_status,
            "effective_date": effective_date,
            "paid_date": paid_date,
        })
    return result


async def get_commission_totals_by_level(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    """Per depth-from-producer: how many distinct contracts generated a
    commission for someone at that depth, total contract value, total
    commission paid out at that depth. Answers "per ogni livello, numero di
    contratti attivi fatturato e provvigioni relative"."""
    stmt = (
        select(
            NetworkSnapshotNode.depth,
            func.count(func.distinct(CommissionMovement.contract_id)),
            func.coalesce(func.sum(ProductVersion.base_price_cents), 0),
            func.coalesce(func.sum(CommissionMovement.amount_cents), 0),
        )
        .select_from(CommissionMovement)
        .join(Contract, Contract.id == CommissionMovement.contract_id)
        .join(ProductVersion, ProductVersion.id == Contract.product_version_id)
        .join(
            NetworkSnapshotNode,
            (NetworkSnapshotNode.snapshot_id == CommissionMovement.network_snapshot_id)
            & (NetworkSnapshotNode.ancestor_agent_id == CommissionMovement.agent_id),
        )
        .where(
            CommissionMovement.organization_id == organization_id,
            CommissionMovement.status.notin_(["CANCELLED", "REVERSED"]),
        )
        .group_by(NetworkSnapshotNode.depth)
        .order_by(NetworkSnapshotNode.depth.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {"depth": depth, "contracts": contracts, "value_cents": int(value_cents), "commission_cents": int(commission_cents)}
        for depth, contracts, value_cents, commission_cents in rows
    ]


async def pay_all_for_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_id: uuid.UUID, actor_user_id: uuid.UUID, note: str | None = None
) -> list[CommissionMovement]:
    """Manual "settle now" for every beneficiary of one contract at once --
    marks every PAYABLE movement (across the whole beneficiary chain, not just
    the producer) PAID in a single transaction, instead of admin clicking
    "Segna come pagata" once per row. Does not touch, and is unaffected by, the
    monthly rank-evaluation job: that only realigns an agent's rank going
    forward, it never re-triggers or re-amounts a contract's commission
    calculation (see docs/commission-engine-specification.md#trigger)."""
    stmt = select(CommissionMovement).where(
        CommissionMovement.organization_id == organization_id,
        CommissionMovement.contract_id == contract_id,
        CommissionMovement.status.in_(PAYABLE_STATUSES),
    )
    movements = list((await db.execute(stmt)).scalars().all())
    today = utcnow().date()
    for movement in movements:
        previous_status = movement.status
        movement.status = "PAID"
        movement.paid_date = today
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=actor_user_id,
            action="commission.movement_paid", entity_type="commission_movement", entity_id=str(movement.id),
            previous_value={"status": previous_status}, new_value={"status": "PAID", "paid_date": today.isoformat()},
            reason=note,
        )
    await db.commit()
    return movements


async def mark_movement_paid(
    db: AsyncSession, *, organization_id: uuid.UUID, movement_id: uuid.UUID, actor_user_id: uuid.UUID, note: str | None = None
) -> CommissionMovement | None:
    movement = await db.get(CommissionMovement, movement_id)
    if movement is None or movement.organization_id != organization_id:
        return None
    if movement.status not in PAYABLE_STATUSES:
        raise CommissionPaymentError(f"Movement is {movement.status}, not payable")

    previous_status = movement.status
    movement.status = "PAID"
    movement.paid_date = utcnow().date()

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="commission.movement_paid", entity_type="commission_movement", entity_id=str(movement.id),
        previous_value={"status": previous_status}, new_value={"status": "PAID", "paid_date": movement.paid_date.isoformat()},
        reason=note,
    )
    await db.commit()
    await db.refresh(movement)
    return movement
