import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.storage import UploadValidationError, upload_media
from app.domains.network import service as network_service
from app.domains.network.models import AgentProfile
from app.domains.network.schemas import (
    AgentCreateRequest,
    AgentListItemRead,
    AgentProfileRead,
    AgentRejectRequest,
    AgentUpdateRequest,
    BranchContractRead,
    BranchMemberRead,
    BranchSummaryRead,
    MoveAgentRequest,
    OrganizationNetworkLevelsRead,
    PromoterApplicationRequest,
    RankProgressRead,
    RecruitRequest,
    RootPromoterCreateRequest,
    RootPromoterCreateResponse,
)
from app.domains.notifications import service as notifications_service
from app.domains.referral.schemas import PromoterCodeRead

router = APIRouter(prefix="/network", tags=["network"])


async def _resolve_own_agent_id(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID | None:
    stmt = select(AgentProfile.id).where(
        AgentProfile.organization_id == organization_id, AgentProfile.user_id == user_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


# Roles that hold the "network.manage" permission (see rbac/models.py
# DEFAULT_ROLE_PERMISSIONS) -- i.e. org-wide network visibility, not just
# their own downline. Kept as an explicit role list (matching this
# function's existing pattern) rather than a live permission-table query:
# real bug found while building the admin "Apri Rete" promoter drill-down
# (Session 15) -- this used to check only SUPER_ADMIN/ORGANIZATION_ADMIN,
# so a plain ADMIN (the actual seeded admin@lialenergy.demo account used
# throughout this project's own demo/docs) got 403 "No agent profile for
# this user" on every branch-summary/branch-contracts call for anyone but
# themselves, even though the SAME admin can already see the whole
# organization's network via GET /network/agents and /organization/levels.
_BRANCH_ACCESS_BYPASS_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN", "SALES_MANAGER"}


async def _assert_branch_access(
    db: AsyncSession, *, current_user: CurrentUser, agent_id: uuid.UUID
) -> None:
    """A promoter/team leader may only read a branch rooted at themselves or a
    descendant of themselves -- not a parallel branch. This is an ABAC check layered
    on top of the RBAC permission gate above. Roles with org-wide network.manage
    bypass the branch-ownership check entirely (org-wide visibility is granted by
    role, not branch)."""
    if _BRANCH_ACCESS_BYPASS_ROLES & set(current_user.roles):
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
    from app.domains.commissions.models import Rank

    stmt = (
        select(AgentProfile, Rank.code)
        .join(Rank, Rank.id == AgentProfile.current_rank_id, isouter=True)
        .where(
            AgentProfile.organization_id == current_user.organization_id,
            AgentProfile.user_id == current_user.user_id,
        )
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None
    agent, rank_code = row
    return AgentProfileRead(
        id=agent.id,
        organization_id=agent.organization_id,
        user_id=agent.user_id,
        display_name=agent.display_name,
        promoter_code=agent.promoter_code,
        status=agent.status,
        photo_url=agent.photo_url,
        current_rank_id=agent.current_rank_id,
        rank_code=rank_code,
        rejection_reason=agent.rejection_reason,
        is_blacklisted=agent.is_blacklisted,
    )


@router.get("/agents/me", response_model=AgentProfileRead | None)
async def get_my_promoter_application(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead | None:
    """Self-service: lets ANY authenticated user (no network.* permission
    required, unlike GET /mine) check whether they already have a 'lavora con
    noi' application/agent profile and its status. Powers the customer-area
    'Lavora con noi' card's four states (none / pending / rejected / active)."""
    agent = await network_service.get_own_agent_profile(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    if agent is None:
        return None
    return AgentProfileRead.model_validate(agent)


@router.post("/agents/apply", response_model=AgentProfileRead, status_code=status.HTTP_201_CREATED)
async def apply_as_promoter(
    payload: PromoterApplicationRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    """'Lavora con noi': any existing CUSTOMER can request to also become a
    PROMOTER. Deliberately not permission-gated like the other /agents routes
    (a plain CUSTOMER holds no network.* permission) -- this IS the
    self-service entry point. Created PENDING_APPROVAL, same
    suggest-then-approve workflow as POST /agents and /agents/recruit; only
    approve_agent() actually grants the PROMOTER role."""
    if "CUSTOMER" not in current_user.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only customers can apply to become a promoter")

    first_name, last_name = payload.first_name, payload.last_name
    if not first_name and not last_name:
        from app.domains.customers.models import Company, Customer, CustomerProfile
        from app.domains.customers.service import COMPANY_LIKE_KINDS

        customer = (
            await db.execute(
                select(Customer).where(
                    Customer.organization_id == current_user.organization_id,
                    Customer.user_id == current_user.user_id,
                )
            )
        ).scalar_one_or_none()
        if customer is not None:
            if customer.kind in COMPANY_LIKE_KINDS:
                company = await db.get(Company, customer.id)
                first_name, last_name = (company.company_name if company else None), ""
            else:
                profile = await db.get(CustomerProfile, customer.id)
                if profile is not None:
                    first_name, last_name = profile.first_name, profile.last_name
    first_name = first_name or "Promoter"
    last_name = last_name or ""

    try:
        agent = await network_service.apply_as_promoter(
            db, organization_id=current_user.organization_id,
            user_id=current_user.user_id, first_name=first_name, last_name=last_name,
        )
    except network_service.DuplicateApplicationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    await notifications_service.notify_roles(
        db, organization_id=current_user.organization_id, roles=notifications_service.APPROVAL_NOTIFY_ROLES,
        type_="PROMOTER_APPROVAL_REQUESTED", entity_type="agent_profile", entity_id=agent.id,
        title=f"Nuova richiesta 'Lavora con noi': {agent.display_name}",
        body=f"Cliente esistente -- codice {agent.promoter_code} in attesa di approvazione.",
        exclude_user_id=current_user.user_id,
    )
    await db.commit()
    return AgentProfileRead.model_validate(agent)


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


@router.get("/agents/{agent_id}/rank-progress", response_model=RankProgressRead)
async def get_rank_progress(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> RankProgressRead:
    """How close this agent is to their next rank's promotion thresholds --
    placeholder feature, see commissions/services/rank_progress.py docstring.
    Same branch-ownership rule as /branch."""
    from app.domains.commissions.services.rank_progress import (
        get_rank_progress as compute_rank_progress,
    )

    await _assert_branch_access(db, current_user=current_user, agent_id=agent_id)
    progress = await compute_rank_progress(db, organization_id=current_user.organization_id, agent_id=agent_id)
    return RankProgressRead(**progress.__dict__)


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
    viewer_agent_id = await _resolve_own_agent_id(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    rows = await network_service.get_branch_contracts(
        db, organization_id=current_user.organization_id, root_agent_id=agent_id, viewer_agent_id=viewer_agent_id
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


@router.get("/agents/{agent_id}/referral-link", response_model=PromoterCodeRead)
async def get_agent_referral_link(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> PromoterCodeRead:
    """Admin equivalent of GET /referral/mine (which only ever resolves the
    CALLER's own link) -- lets the 'Promoter' management screen open ANY
    agent's personal link, e.g. to hand it to them again if they lost it.
    Same lazy get-or-create as the promoter's own dashboard."""
    from app.domains.referral import service as referral_service

    try:
        promoter_code = await referral_service.get_or_create_promoter_code(
            db, organization_id=current_user.organization_id, agent_id=agent_id
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found") from exc
    return PromoterCodeRead.model_validate(promoter_code)


@router.post("/agents", response_model=AgentProfileRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AgentCreateRequest,
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    """A plain ADMIN can only SUGGEST a new promoter -- created PENDING_APPROVAL,
    not usable (can't be a contract producer) until a network.approve-holder
    (SUPER_ADMIN/ORGANIZATION_ADMIN, the "amministratore principale") approves
    it via PATCH /agents/{id}/approve. See AgentProfile.status docstring.

    payload.customer_email optionally links this to an already-registered
    customer's login (e.g. promoting someone referred by another promoter into
    a promoter under that same sponsor) -- approve_agent() already grants the
    PROMOTER role on top of their existing roles once approved, same as the
    self-service 'lavora con noi' path."""
    from app.domains.users.models import User

    user_id = None
    if payload.customer_email:
        user = (
            await db.execute(
                select(User).where(
                    User.organization_id == current_user.organization_id, User.email == payload.customer_email
                )
            )
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
        existing_agent = await network_service.get_own_agent_profile(
            db, organization_id=current_user.organization_id, user_id=user.id
        )
        if existing_agent is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"This user already has a promoter profile ({existing_agent.status})"
            )
        user_id = user.id

    try:
        agent = await network_service.create_agent(
            db,
            organization_id=current_user.organization_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            promoter_code=payload.promoter_code,
            parent_agent_id=payload.parent_agent_id,
            current_rank_id=payload.current_rank_id,
            actor_user_id=current_user.user_id,
            user_id=user_id,
            status="PENDING_APPROVAL",
        )
    except network_service.NetworkError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await notifications_service.notify_roles(
        db, organization_id=current_user.organization_id, roles=notifications_service.APPROVAL_NOTIFY_ROLES,
        type_="PROMOTER_APPROVAL_REQUESTED", entity_type="agent_profile", entity_id=agent.id,
        title=f"Nuovo promoter suggerito: {agent.display_name}",
        body=f"Codice {agent.promoter_code} in attesa di approvazione.",
        exclude_user_id=current_user.user_id,
    )
    await db.commit()
    return AgentProfileRead.model_validate(agent)


@router.post("/agents/root", response_model=RootPromoterCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_root_promoter(
    payload: RootPromoterCreateRequest,
    current_user: CurrentUser = Depends(require_permission("network.approve")),
    db: AsyncSession = Depends(get_db),
) -> RootPromoterCreateResponse:
    """Bootstraps a brand-new, parentless network root with a ready-to-use
    login and referral link in one step -- gated on network.approve
    (SUPER_ADMIN/ORGANIZATION_ADMIN only) since it bypasses the normal
    suggest-then-approve workflow entirely. See create_root_promoter_with_login
    docstring for why this exists: registration is invite-only everywhere
    else, so there is no other way to start a new independent branch."""
    try:
        agent, user, promoter_code_row, temporary_password = await network_service.create_root_promoter_with_login(
            db,
            organization_id=current_user.organization_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            promoter_code=payload.promoter_code,
            actor_user_id=current_user.user_id,
        )
    except network_service.RootPromoterConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    return RootPromoterCreateResponse(
        agent_id=agent.id,
        display_name=agent.display_name,
        promoter_code=agent.promoter_code,
        personal_link=promoter_code_row.personal_link,
        email=user.email,
        temporary_password=temporary_password,
    )


@router.patch("/agents/{agent_id}", response_model=AgentProfileRead)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    try:
        agent = await network_service.update_agent(
            db,
            organization_id=current_user.organization_id,
            agent_id=agent_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            status_value=payload.status,
            current_rank_id=payload.current_rank_id,
            actor_user_id=current_user.user_id,
            is_blacklisted=payload.is_blacklisted,
        )
    except network_service.AgentApprovalError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
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
    in the tree -- that still requires network.manage (or a move request).
    Same suggest-then-approve workflow as POST /agents: created
    PENDING_APPROVAL, not usable until an "amministratore principale"
    approves it."""
    own_agent_id = await _resolve_own_agent_id(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    if own_agent_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No agent profile for this user")

    try:
        agent = await network_service.create_agent(
            db,
            organization_id=current_user.organization_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            promoter_code=payload.promoter_code,
            parent_agent_id=own_agent_id,
            current_rank_id=payload.current_rank_id,
            actor_user_id=current_user.user_id,
            status="PENDING_APPROVAL",
        )
    except network_service.NetworkError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await notifications_service.notify_roles(
        db, organization_id=current_user.organization_id, roles=notifications_service.APPROVAL_NOTIFY_ROLES,
        type_="PROMOTER_APPROVAL_REQUESTED", entity_type="agent_profile", entity_id=agent.id,
        title=f"Nuovo collaboratore suggerito: {agent.display_name}",
        body=f"Reclutato da un promoter -- codice {agent.promoter_code} in attesa di approvazione.",
    )
    await db.commit()
    return AgentProfileRead.model_validate(agent)


@router.patch("/agents/{agent_id}/approve", response_model=AgentProfileRead)
async def approve_agent(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.approve")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    try:
        agent = await network_service.approve_agent(
            db, organization_id=current_user.organization_id, agent_id=agent_id, actor_user_id=current_user.user_id
        )
    except network_service.AgentApprovalError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")

    if agent.user_id is not None:
        await notifications_service.notify_user(
            db, organization_id=current_user.organization_id, user_id=agent.user_id,
            type_="PROMOTER_APPROVED", entity_type="agent_profile", entity_id=agent.id,
            title="Il tuo profilo promoter è stato approvato",
            body=f"{agent.display_name} ({agent.promoter_code}) è ora attivo.",
        )
        await db.commit()
    return AgentProfileRead.model_validate(agent)


@router.patch("/agents/{agent_id}/reject", response_model=AgentProfileRead)
async def reject_agent(
    agent_id: uuid.UUID,
    payload: AgentRejectRequest,
    current_user: CurrentUser = Depends(require_permission("network.approve")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    try:
        agent = await network_service.reject_agent(
            db, organization_id=current_user.organization_id, agent_id=agent_id,
            actor_user_id=current_user.user_id, reason=payload.reason,
        )
    except network_service.AgentApprovalError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")

    if agent.user_id is not None:
        await notifications_service.notify_user(
            db, organization_id=current_user.organization_id, user_id=agent.user_id,
            type_="PROMOTER_REJECTED", entity_type="agent_profile", entity_id=agent.id,
            title="Il tuo profilo promoter suggerito non è stato approvato",
            body=payload.reason,
        )
        await db.commit()
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
