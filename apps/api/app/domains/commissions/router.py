import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.domains.commissions.models import CommissionMovement, Rank
from app.domains.commissions.schemas import (
    CommissionLevelTotalsRead,
    CommissionMovementDetailRead,
    CommissionMovementRead,
    CommissionPaymentRequest,
    RankRead,
    SimulateRequest,
    SimulationStepRead,
)
from app.domains.commissions.services import admin_ledger
from app.domains.commissions.simulations.simulate import simulate_for_contract
from app.domains.network.models import AgentProfile

router = APIRouter(prefix="/commissions", tags=["commissions"])


@router.get("/mine", response_model=list[CommissionMovementRead])
async def get_my_commissions(
    current_user: CurrentUser = Depends(require_permission("commissions.read_own")),
    db: AsyncSession = Depends(get_db),
) -> list[CommissionMovementRead]:
    agent_stmt = select(AgentProfile.id).where(
        AgentProfile.organization_id == current_user.organization_id,
        AgentProfile.user_id == current_user.user_id,
    )
    agent_id = (await db.execute(agent_stmt)).scalar_one_or_none()
    if agent_id is None:
        return []

    stmt = select(CommissionMovement).where(
        CommissionMovement.organization_id == current_user.organization_id,
        CommissionMovement.agent_id == agent_id,
    )
    movements = (await db.execute(stmt)).scalars().all()
    return [CommissionMovementRead.model_validate(m) for m in movements]


@router.get("/mine/detailed", response_model=list[CommissionMovementDetailRead])
async def get_my_commissions_detailed(
    current_user: CurrentUser = Depends(require_permission("commissions.read_own")),
    db: AsyncSession = Depends(get_db),
) -> list[CommissionMovementDetailRead]:
    """Same full traceability as the admin ledger (GET /commissions/movements)
    -- contract, customer, network level, rank at calculation, breakdown,
    explanation -- but hard-scoped to the caller's OWN agent_id, never
    org-wide. Reuses admin_ledger.get_commission_movements() rather than a
    parallel implementation; the only difference from the admin endpoint is
    this mandatory agent_id filter and the read_own (not approve) gate."""
    agent_stmt = select(AgentProfile.id).where(
        AgentProfile.organization_id == current_user.organization_id,
        AgentProfile.user_id == current_user.user_id,
    )
    agent_id = (await db.execute(agent_stmt)).scalar_one_or_none()
    if agent_id is None:
        return []
    rows = await admin_ledger.get_commission_movements(db, organization_id=current_user.organization_id, agent_id=agent_id)
    return [CommissionMovementDetailRead(**row) for row in rows]


@router.get("/ranks", response_model=list[RankRead])
async def list_ranks(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RankRead]:
    """Reference data (rank ladder) -- any authenticated org member can read it, no
    dedicated permission: it's needed by the admin agent-creation form and the
    promoter's own simulator, and carries no sensitive/economic-decision weight by
    itself (see docs/commission-engine-specification.md)."""
    stmt = (
        select(Rank)
        .where(Rank.organization_id == current_user.organization_id)
        .order_by(Rank.level.asc())
    )
    ranks = (await db.execute(stmt)).scalars().all()
    return [RankRead.model_validate(r) for r in ranks]


@router.post("/contracts/{contract_id}/simulate", response_model=list[SimulationStepRead])
async def simulate(
    contract_id: uuid.UUID,
    payload: SimulateRequest,
    current_user: CurrentUser = Depends(require_permission("commissions.simulate")),
    db: AsyncSession = Depends(get_db),
) -> list[SimulationStepRead]:
    try:
        steps = await simulate_for_contract(
            db, contract_id=contract_id, rank_overrides=payload.rank_overrides
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return [
        SimulationStepRead(
            beneficiary_agent_id=s.beneficiary_agent_id,
            rank_code=s.rank_code,
            gross_amount_cents=s.gross_amount_cents,
            movement_type=s.movement_type,
            explanation=s.explanation,
        )
        for s in steps
    ]


@router.get("/movements", response_model=list[CommissionMovementDetailRead])
async def list_commission_movements(
    agent_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    contract_id: uuid.UUID | None = None,
    current_user: CurrentUser = Depends(require_permission("commissions.approve")),
    db: AsyncSession = Depends(get_db),
) -> list[CommissionMovementDetailRead]:
    """Org-wide commission ledger with full traceability -- which contract,
    which customer, which promoter, from how many network levels below the
    producer, at what rank, and the exact calculation breakdown. Gated on
    commissions.approve (admin-tier only): unlike commissions.read_branch
    (also held by TEAM_LEADER/PROMOTER for their OWN branch), this endpoint
    is org-wide with no branch restriction, so it must not be reachable by a
    promoter-tier role."""
    rows = await admin_ledger.get_commission_movements(
        db, organization_id=current_user.organization_id, agent_id=agent_id, status=status_filter, contract_id=contract_id
    )
    return [CommissionMovementDetailRead(**row) for row in rows]


@router.get("/movements/by-level", response_model=list[CommissionLevelTotalsRead])
async def get_commission_totals_by_level(
    current_user: CurrentUser = Depends(require_permission("commissions.approve")),
    db: AsyncSession = Depends(get_db),
) -> list[CommissionLevelTotalsRead]:
    rows = await admin_ledger.get_commission_totals_by_level(db, organization_id=current_user.organization_id)
    return [CommissionLevelTotalsRead(**row) for row in rows]


@router.patch("/movements/{movement_id}/pay", response_model=CommissionMovementRead)
async def pay_commission_movement(
    movement_id: uuid.UUID,
    payload: CommissionPaymentRequest,
    current_user: CurrentUser = Depends(require_permission("commissions.approve")),
    db: AsyncSession = Depends(get_db),
) -> CommissionMovementRead:
    try:
        movement = await admin_ledger.mark_movement_paid(
            db, organization_id=current_user.organization_id, movement_id=movement_id,
            actor_user_id=current_user.user_id, note=payload.note,
        )
    except admin_ledger.CommissionPaymentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if movement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commission movement not found")
    return CommissionMovementRead.model_validate(movement)
