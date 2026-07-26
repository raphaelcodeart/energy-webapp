import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.storage import UploadValidationError, upload_media
from app.domains.network import service as network_service
from app.domains.network.models import AgentProfile
from app.domains.network.schemas import (
    AgentCreateRequest,
    AgentListItemRead,
    AgentProfileRead,
    AgentUpdateRequest,
    BranchContractRead,
    BranchMemberRead,
    BranchSummaryRead,
    MoveAgentRequest,
    OrganizationNetworkLevelsRead,
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


async def _assert_branch_access(
    db: AsyncSession, *, current_user: CurrentUser, agent_id: uuid.UUID
) -> None:
    """A promoter/team leader may only read a branch rooted at themselves or a
    descendant of themselves -- not a parallel branch. This is an ABAC check layered
    on top of the RBAC permission gate above. SUPER_ADMIN/ORGANIZATION_ADMIN bypass
    the branch-ownership check (org-wide visibility is granted by role, not branch)."""
    if "SUPER_ADMIN" in current_user.roles or "ORGANIZATION_ADMIN" in current_user.roles:
        return
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
    await _assert_branch_access(db, current_user=current_user, agent_id=agent_id)
    branch = await network_service.get_branch(
        db, organization_id=current_user.organization_id, root_agent_id=agent_id
    )
    return [BranchMemberRead(**row) for row in branch]


@router.get("/agents/{agent_id}/branch-summary", response_model=BranchSummaryRead)
async def get_branch_summary(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> BranchSummaryRead:
    """Per-agent contract/commission rollup for a promoter's own downline -- the
    data behind the "azienda" view (contracts per person, per level, problems,
    earnings), same branch-ownership rule as /branch."""
    await _assert_branch_access(db, current_user=current_user, agent_id=agent_id)
    summary = await network_service.get_branch_summary(
        db, organization_id=current_user.organization_id, root_agent_id=agent_id
    )
    return BranchSummaryRead(**summary)


@router.get("/agents/{agent_id}/branch-contracts", response_model=list[BranchContractRead])
async def get_branch_contracts(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> list[BranchContractRead]:
    """Flat contract-level detail (customer, product, status, commission) for a
    promoter's whole downline -- lets a promoter go from "there's a problem" to
    "here's the customer to contact" without leaving the network view."""
    await _assert_branch_access(db, current_user=current_user, agent_id=agent_id)
    rows = await network_service.get_branch_contracts(
        db, organization_id=current_user.organization_id, root_agent_id=agent_id
    )
    return [BranchContractRead(**row) for row in rows]


@router.get("/organization/levels", response_model=OrganizationNetworkLevelsRead)
async def get_organization_network_levels(
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> OrganizationNetworkLevelsRead:
    """Whole-company network depth/headcount -- admin-only (network.manage),
    unlike /agents/{id}/branch-summary which every promoter can call for their
    own restricted downline."""
    result = await network_service.get_organization_network_levels(db, organization_id=current_user.organization_id)
    return OrganizationNetworkLevelsRead(**result)


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


@router.post("/agents/{agent_id}/photo", response_model=AgentProfileRead)
async def upload_agent_photo(
    agent_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    file_bytes = await file.read()
    try:
        photo_url = upload_media(
            file_bytes=file_bytes, content_type=file.content_type or "", key_prefix="photos/promoters"
        )
    except UploadValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    agent = await network_service.set_agent_photo(
        db, organization_id=current_user.organization_id, agent_id=agent_id,
        photo_url=photo_url, actor_user_id=current_user.user_id,
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
