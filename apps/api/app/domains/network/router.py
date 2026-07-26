import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.domains.network import service as network_service
from app.domains.network.models import AgentProfile
from app.domains.network.schemas import (
    AgentCreateRequest,
    AgentListItemRead,
    AgentProfileRead,
    AgentUpdateRequest,
    BranchMemberRead,
    MoveAgentRequest,
    RecruitRequest,
)

router = APIRouter(prefix="/network", tags=["network"])


async def _resolve_own_agent_id(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID | None:
    stmt = select(AgentProfile.id).where(
        AgentProfile.organization_id == organization_id, AgentProfile.user_id == user_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


@router.get("/mine", response_model=AgentProfileRead | None)
async def get_my_agent_profile(
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead | None:
    """Lets a promoter's own login discover its agent_id without needing to know it
    in advance -- the dashboard calls this first, then /agents/{id}/branch."""
    stmt = select(AgentProfile).where(
        AgentProfile.organization_id == current_user.organization_id,
        AgentProfile.user_id == current_user.user_id,
    )
    agent = (await db.execute(stmt)).scalar_one_or_none()
    return AgentProfileRead.model_validate(agent) if agent else None


@router.get("/agents/{agent_id}/branch", response_model=list[BranchMemberRead])
async def get_branch(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> list[BranchMemberRead]:
    """A promoter/team leader may only read a branch rooted at themselves or a
    descendant of themselves -- not a parallel branch. This is an ABAC check layered
    on top of the RBAC permission gate above. SUPER_ADMIN/ORGANIZATION_ADMIN bypass
    the branch-ownership check (org-wide visibility is granted by role, not branch)."""
    if "SUPER_ADMIN" not in current_user.roles and "ORGANIZATION_ADMIN" not in current_user.roles:
        requesting_agent_id = await _resolve_own_agent_id(
            db, organization_id=current_user.organization_id, user_id=current_user.user_id
        )
        if requesting_agent_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No agent profile for this user")
        if requesting_agent_id != agent_id:
            authorized = await network_service.is_ancestor(
                db,
                organization_id=current_user.organization_id,
                ancestor_agent_id=requesting_agent_id,
                agent_id=agent_id,
            )
            if not authorized:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this branch")

    branch = await network_service.get_branch(
        db, organization_id=current_user.organization_id, root_agent_id=agent_id
    )
    return [BranchMemberRead(**row) for row in branch]


@router.get("/agents", response_model=list[AgentListItemRead])
async def list_agents(
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[AgentListItemRead]:
    """Org-wide agent registry -- the admin 'Promoter' management screen. Gated by
    network.manage (org-wide visibility), unlike /agents/{id}/branch which is
    branch-scoped for everyone else."""
    rows = await network_service.list_agents(db, organization_id=current_user.organization_id)
    return [AgentListItemRead(**row) for row in rows]


@router.post("/agents", response_model=AgentProfileRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AgentCreateRequest,
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    try:
        agent = await network_service.create_agent(
            db,
            organization_id=current_user.organization_id,
            display_name=payload.display_name,
            promoter_code=payload.promoter_code,
            parent_agent_id=payload.parent_agent_id,
            current_rank_id=payload.current_rank_id,
            actor_user_id=current_user.user_id,
        )
    except network_service.NetworkError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return AgentProfileRead.model_validate(agent)


@router.patch("/agents/{agent_id}", response_model=AgentProfileRead)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    agent = await network_service.update_agent(
        db,
        organization_id=current_user.organization_id,
        agent_id=agent_id,
        display_name=payload.display_name,
        status_value=payload.status,
        current_rank_id=payload.current_rank_id,
        actor_user_id=current_user.user_id,
    )
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    return AgentProfileRead.model_validate(agent)


@router.post("/agents/recruit", response_model=AgentProfileRead, status_code=status.HTTP_201_CREATED)
async def recruit_agent(
    payload: RecruitRequest,
    current_user: CurrentUser = Depends(require_permission("network.recruit")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    """A promoter enrolling a new direct collaborator under themselves. Unlike
    POST /agents (org-wide, network.manage-gated), this is scoped: the caller can
    only recruit as their OWN direct child, never place a new agent anywhere else
    in the tree -- that still requires network.manage (or a move request)."""
    own_agent_id = await _resolve_own_agent_id(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    if own_agent_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No agent profile for this user")

    try:
        agent = await network_service.create_agent(
            db,
            organization_id=current_user.organization_id,
            display_name=payload.display_name,
            promoter_code=payload.promoter_code,
            parent_agent_id=own_agent_id,
            current_rank_id=payload.current_rank_id,
            actor_user_id=current_user.user_id,
        )
    except network_service.NetworkError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return AgentProfileRead.model_validate(agent)


@router.post("/agents/{agent_id}/move", status_code=status.HTTP_204_NO_CONTENT)
async def move_agent(
    agent_id: uuid.UUID,
    payload: MoveAgentRequest,
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await network_service.move_agent(
            db,
            organization_id=current_user.organization_id,
            agent_id=agent_id,
            new_parent_agent_id=payload.new_parent_agent_id,
            requested_by=current_user.user_id,
            approved_by=current_user.user_id,  # placeholder self-approval, see open-questions.md #2
            reason=payload.reason,
            effective_at=payload.effective_at,
        )
    except network_service.CycleError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except network_service.NetworkError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
