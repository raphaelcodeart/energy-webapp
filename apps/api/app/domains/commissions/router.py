import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.domains.commissions.models import CommissionMovement
from app.domains.commissions.schemas import (
    CommissionMovementRead,
    SimulateRequest,
    SimulationStepRead,
)
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
