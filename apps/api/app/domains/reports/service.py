import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import cast, Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit.models import AuditLog
from app.domains.commissions.models import CommissionMovement
from app.domains.contracts.models import Contract, ContractStatusHistory
from app.domains.customers.models import Customer
from app.domains.network.models import AgentProfile
from app.domains.reports.schemas import (
    AttentionItem,
    CommissionTotals,
    ContractTotals,
    DashboardSummary,
    RecentActivityItem,
    TimeseriesPoint,
)

# Contract statuses that represent "still moving through the pipeline, not yet
# active and not yet terminal" -- see app/domains/contracts/state_machine.py.
PENDING_APPROVAL_STATUSES = {
    "DRAFT",
    "SUBMITTED",
    "DOCUMENTS_PENDING",
    "UNDER_REVIEW",
    "APPROVED",
    "PAYMENT_PENDING",
    "PAID",
    "ACTIVATION_PENDING",
}

# Statuses that have sat in a review queue long enough to flag as "needs attention"
# if older than ATTENTION_THRESHOLD_DAYS.
REVIEW_QUEUE_STATUSES = {"SUBMITTED", "DOCUMENTS_PENDING", "UNDER_REVIEW"}
ATTENTION_THRESHOLD_DAYS = 7


async def get_dashboard_summary(
    db: AsyncSession, organization_id: uuid.UUID, period_from: date, period_to: date
) -> DashboardSummary:
    contract_rows = (
        await db.execute(
            select(Contract.status, func.count())
            .where(Contract.organization_id == organization_id)
            .group_by(Contract.status)
        )
    ).all()
    counts_by_status = {status: count for status, count in contract_rows}
    contracts = ContractTotals(
        total=sum(counts_by_status.values()),
        active=counts_by_status.get("ACTIVE", 0),
        pending_approval=sum(counts_by_status.get(s, 0) for s in PENDING_APPROVAL_STATUSES),
        rejected=counts_by_status.get("REJECTED", 0),
        cancelled=counts_by_status.get("CANCELLED", 0),
        suspended=counts_by_status.get("SUSPENDED", 0),
        expired=counts_by_status.get("EXPIRED", 0),
    )

    commission_rows = (
        await db.execute(
            select(CommissionMovement.status, func.coalesce(func.sum(CommissionMovement.amount_cents), 0))
            .where(CommissionMovement.organization_id == organization_id)
            .group_by(CommissionMovement.status)
        )
    ).all()
    commission_by_status = {status: int(total) for status, total in commission_rows}
    commissions = CommissionTotals(
        accrued_cents=commission_by_status.get("ACCRUED", 0),
        payable_cents=commission_by_status.get("PAYABLE", 0) + commission_by_status.get("SCHEDULED", 0),
        paid_cents=commission_by_status.get("PAID", 0),
        reversed_cents=abs(commission_by_status.get("REVERSED", 0)),
    )

    active_promoters = (
        await db.execute(
            select(func.count())
            .select_from(AgentProfile)
            .where(AgentProfile.organization_id == organization_id, AgentProfile.status == "ACTIVE")
        )
    ).scalar_one()

    active_customers = (
        await db.execute(
            select(func.count(func.distinct(Contract.customer_id)))
            .select_from(Contract)
            .join(Customer, Customer.id == Contract.customer_id)
            .where(Contract.organization_id == organization_id, Contract.status == "ACTIVE")
        )
    ).scalar_one()

    period_new_contracts = (
        await db.execute(
            select(func.count())
            .select_from(Contract)
            .where(
                Contract.organization_id == organization_id,
                cast(Contract.created_at, Date) >= period_from,
                cast(Contract.created_at, Date) <= period_to,
            )
        )
    ).scalar_one()

    period_new_commissions_cents = (
        await db.execute(
            select(func.coalesce(func.sum(CommissionMovement.amount_cents), 0))
            .where(
                CommissionMovement.organization_id == organization_id,
                CommissionMovement.status.notin_(["CANCELLED", "REVERSED"]),
                CommissionMovement.effective_date >= period_from,
                CommissionMovement.effective_date <= period_to,
            )
        )
    ).scalar_one()

    return DashboardSummary(
        contracts=contracts,
        commissions=commissions,
        active_promoters=active_promoters,
        active_customers=active_customers,
        period_new_contracts=period_new_contracts,
        period_new_commissions_cents=int(period_new_commissions_cents),
        generated_at=datetime.now(timezone.utc),
    )


async def get_attention_items(db: AsyncSession, organization_id: uuid.UUID) -> list[AttentionItem]:
    """A contract "needs attention" once it has sat in a review-queue status longer
    than ATTENTION_THRESHOLD_DAYS. Contracts have no updated_at column (append-only
    history is the source of truth -- see contract_status_history), so "time in
    current status" is derived from that contract's most recent status-history row,
    not from the contract row itself."""
    latest_transition = (
        select(
            ContractStatusHistory.contract_id,
            ContractStatusHistory.created_at,
            func.row_number()
            .over(
                partition_by=ContractStatusHistory.contract_id,
                order_by=ContractStatusHistory.created_at.desc(),
            )
            .label("rn"),
        )
        .subquery()
    )
    threshold = datetime.now(timezone.utc) - timedelta(days=ATTENTION_THRESHOLD_DAYS)
    stmt = (
        select(Contract.id, Contract.customer_id, Contract.status, latest_transition.c.created_at)
        .join(latest_transition, latest_transition.c.contract_id == Contract.id)
        .where(
            Contract.organization_id == organization_id,
            Contract.status.in_(REVIEW_QUEUE_STATUSES),
            latest_transition.c.rn == 1,
            latest_transition.c.created_at <= threshold,
        )
        .order_by(latest_transition.c.created_at.asc())
        .limit(50)
    )
    rows = (await db.execute(stmt)).all()
    now = datetime.now(timezone.utc)
    return [
        AttentionItem(
            contract_id=contract_id,
            customer_id=customer_id,
            status=status,
            days_in_status=(now - since).days,
            reason=f"Fermo in stato {status} da oltre {ATTENTION_THRESHOLD_DAYS} giorni",
        )
        for contract_id, customer_id, status, since in rows
    ]


async def get_recent_activity(
    db: AsyncSession, organization_id: uuid.UUID, limit: int = 20
) -> list[RecentActivityItem]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.organization_id == organization_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        RecentActivityItem(
            id=row.id,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            reason=row.reason,
            created_at=row.created_at,
        )
        for row in rows
    ]


async def get_contracts_timeseries(
    db: AsyncSession, organization_id: uuid.UUID, months: int
) -> list[TimeseriesPoint]:
    period_col = func.date_trunc("month", Contract.created_at).cast(Date).label("period")
    stmt = (
        select(period_col, func.count())
        .where(Contract.organization_id == organization_id)
        .group_by(period_col)
        .order_by(period_col)
    )
    rows = (await db.execute(stmt)).all()
    return _last_n_months(rows, months)


async def get_commissions_timeseries(
    db: AsyncSession, organization_id: uuid.UUID, months: int
) -> list[TimeseriesPoint]:
    period_col = func.date_trunc("month", CommissionMovement.effective_date).cast(Date).label("period")
    stmt = (
        select(period_col, func.coalesce(func.sum(CommissionMovement.amount_cents), 0))
        .where(
            CommissionMovement.organization_id == organization_id,
            CommissionMovement.status.notin_(["CANCELLED", "REVERSED"]),
        )
        .group_by(period_col)
        .order_by(period_col)
    )
    rows = (await db.execute(stmt)).all()
    return _last_n_months(rows, months)


def _last_n_months(rows: list[tuple[date, int]], months: int) -> list[TimeseriesPoint]:
    by_period = {period: int(value) for period, value in rows}
    today = datetime.now(timezone.utc).date().replace(day=1)
    points: list[TimeseriesPoint] = []
    for i in range(months - 1, -1, -1):
        year = today.year + (today.month - 1 - i) // 12
        month = (today.month - 1 - i) % 12 + 1
        period = date(year, month, 1)
        points.append(TimeseriesPoint(period=period, value=by_period.get(period, 0)))
    return points
