from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.domains.reports import service
from app.domains.reports.schemas import (
    AttentionItem,
    DashboardSummary,
    RecentActivityItem,
    TimeseriesPoint,
)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/dashboard-summary", response_model=DashboardSummary)
async def dashboard_summary(
    period_from: date | None = Query(None),
    period_to: date | None = Query(None),
    current_user: CurrentUser = Depends(require_permission("reports.read")),
    db: AsyncSession = Depends(get_db),
) -> DashboardSummary:
    to_ = period_to or datetime.now(UTC).date()
    from_ = period_from or (to_ - timedelta(days=30))
    return await service.get_dashboard_summary(db, current_user.organization_id, from_, to_)


@router.get("/attention-items", response_model=list[AttentionItem])
async def attention_items(
    current_user: CurrentUser = Depends(require_permission("reports.read")),
    db: AsyncSession = Depends(get_db),
) -> list[AttentionItem]:
    return await service.get_attention_items(db, current_user.organization_id)


@router.get("/recent-activity", response_model=list[RecentActivityItem])
async def recent_activity(
    limit: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_permission("reports.read")),
    db: AsyncSession = Depends(get_db),
) -> list[RecentActivityItem]:
    return await service.get_recent_activity(db, current_user.organization_id, limit)


@router.get("/contracts-timeseries", response_model=list[TimeseriesPoint])
async def contracts_timeseries(
    months: int = Query(12, ge=1, le=36),
    current_user: CurrentUser = Depends(require_permission("reports.read")),
    db: AsyncSession = Depends(get_db),
) -> list[TimeseriesPoint]:
    return await service.get_contracts_timeseries(db, current_user.organization_id, months)


@router.get("/commissions-timeseries", response_model=list[TimeseriesPoint])
async def commissions_timeseries(
    months: int = Query(12, ge=1, le=36),
    current_user: CurrentUser = Depends(require_permission("reports.read")),
    db: AsyncSession = Depends(get_db),
) -> list[TimeseriesPoint]:
    return await service.get_commissions_timeseries(db, current_user.organization_id, months)
