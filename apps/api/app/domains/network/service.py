import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service

if TYPE_CHECKING:
    # Annotation-only -- the real imports stay function-local at their call
    # sites below to avoid module-level coupling with referral/users, same
    # convention as the rest of this file.
    from app.domains.referral.models import PromoterCode
    from app.domains.users.models import User
from app.domains.network.models import (
    AgentProfile,
    NetworkAssignmentHistory,
    NetworkClosure,
    NetworkEdge,
    NetworkNode,
    NetworkSnapshot,
    NetworkSnapshotNode,
)


class NetworkError(Exception):
    pass


class CycleError(NetworkError):
    pass


class DuplicateApplicationError(NetworkError):
    pass


class RootPromoterConflictError(NetworkError):
    pass


async def _get_active_ancestors(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID
) -> list[tuple[uuid.UUID, int]]:
    """Ancestors of agent_id (including itself, depth 0), currently active."""
    stmt = select(NetworkClosure.ancestor_agent_id, NetworkClosure.depth).where(
        NetworkClosure.organization_id == organization_id,
        NetworkClosure.descendant_agent_id == agent_id,
        NetworkClosure.effective_to.is_(None),
    )
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]


async def _get_active_descendants(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID
) -> list[tuple[uuid.UUID, int]]:
    """Descendants of agent_id (including itself, depth 0), currently active."""
    stmt = select(NetworkClosure.descendant_agent_id, NetworkClosure.depth).where(
        NetworkClosure.organization_id == organization_id,
        NetworkClosure.ancestor_agent_id == agent_id,
        NetworkClosure.effective_to.is_(None),
    )
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]


async def create_agent(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    first_name: str,
    last_name: str,
    promoter_code: str,
    parent_agent_id: uuid.UUID | None,
    joined_at: datetime | None = None,
    actor_user_id: uuid.UUID | None = None,
    current_rank_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    status: str = "ACTIVE",
) -> AgentProfile:
    """Register a brand-new agent (no pre-existing subtree) under an optional parent.
    Use move_agent() to relocate an agent that already has descendants. status
    defaults to ACTIVE for internal/test callers; the two user-facing creation
    routes (POST /agents, POST /agents/recruit) explicitly pass
    PENDING_APPROVAL -- see AgentProfile.status docstring.

    first_name/last_name are stored as their own columns (not just baked into
    display_name) so admin screens, exports, and reports can sort/filter by
    either independently -- display_name stays a derived, denormalized
    "first last" for the many existing read paths (contracts, notifications,
    branch views, ...) that only ever needed one string to show."""
    joined_at = joined_at or utcnow()
    display_name = f"{first_name} {last_name}".strip()

    agent = AgentProfile(
        organization_id=organization_id,
        display_name=display_name,
        first_name=first_name,
        last_name=last_name,
        promoter_code=promoter_code,
        status=status,
        joined_at=joined_at,
        current_rank_id=current_rank_id,
        user_id=user_id,
    )
    db.add(agent)
    await db.flush()

    if parent_agent_id is not None:
        parent_node = (
            await db.execute(
                select(NetworkNode).where(
                    NetworkNode.organization_id == organization_id,
                    NetworkNode.agent_id == parent_agent_id,
                    NetworkNode.effective_to.is_(None),
                )
            )
        ).scalar_one_or_none()
        if parent_node is None:
            raise NetworkError("Parent agent has no active network node")

    node = NetworkNode(
        organization_id=organization_id,
        agent_id=agent.id,
        direct_parent_agent_id=parent_agent_id,
        status="ACTIVE",
        effective_from=joined_at,
    )
    db.add(node)

    # Reflexive closure row: every agent is its own ancestor at depth 0.
    db.add(
        NetworkClosure(
            organization_id=organization_id,
            ancestor_agent_id=agent.id,
            descendant_agent_id=agent.id,
            depth=0,
            effective_from=joined_at,
        )
    )

    if parent_agent_id is not None:
        db.add(
            NetworkEdge(
                organization_id=organization_id,
                parent_agent_id=parent_agent_id,
                child_agent_id=agent.id,
                effective_from=joined_at,
            )
        )
        ancestors = await _get_active_ancestors(db, organization_id=organization_id, agent_id=parent_agent_id)
        for ancestor_id, depth in ancestors:
            db.add(
                NetworkClosure(
                    organization_id=organization_id,
                    ancestor_agent_id=ancestor_id,
                    descendant_agent_id=agent.id,
                    depth=depth + 1,
                    effective_from=joined_at,
                )
            )

    await audit_service.record(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="network.agent_created",
        entity_type="agent_profile",
        entity_id=str(agent.id),
        new_value={"parent_agent_id": str(parent_agent_id) if parent_agent_id else None},
    )
    await db.commit()
    await db.refresh(agent)
    return agent


async def get_own_agent_profile(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> AgentProfile | None:
    """Any authenticated user's own AgentProfile, regardless of RBAC
    permissions -- used by the self-service 'lavora con noi' flow, which a
    plain CUSTOMER (no network.* permission) must be able to call to see
    their own application status. Distinct from GET /network/mine, which is
    gated by network.read_branch."""
    stmt = select(AgentProfile).where(
        AgentProfile.organization_id == organization_id, AgentProfile.user_id == user_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def _generate_promoter_code(display_name: str) -> str:
    """Best-effort human-readable code (initials + random suffix) for
    self-service applications, where -- unlike POST /agents and
    /agents/recruit -- there is no admin/promoter typing one in by hand.
    Uniqueness within the org is enforced by the DB's own uq_agent_promoter_code
    constraint, not guessed here."""
    import re
    import secrets

    slug = re.sub(r"[^A-Z0-9]", "", display_name.upper())[:6] or "PROMO"
    return f"{slug}-{secrets.token_hex(3).upper()}"


AUTO_ACTIVATION_RANK_CODE = "S1"


async def _get_current_rank_id(db: AsyncSession, *, organization_id: uuid.UUID, code: str) -> uuid.UUID | None:
    """The currently-in-effect (valid_to IS NULL) version of a rank code --
    same "current version" convention used by rank_evaluation.py."""
    from app.domains.commissions.models import Rank

    stmt = select(Rank.id).where(
        Rank.organization_id == organization_id, Rank.code == code, Rank.valid_to.is_(None)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _resolve_referring_agent_id(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID | None:
    """Which promoter's referral link this user originally signed up through
    (if any) -- registration is invite-only everywhere (auth/service.py
    register_with_referral), so a customer_attributions row should always
    exist, but this stays defensive (None) for e.g. a customer created
    outside that flow. Used so a self-service promoter application lands
    under the sponsor who actually invited them, not as a stray root."""
    from app.domains.customers.models import Customer
    from app.domains.referral.models import CustomerAttribution, PromoterCode

    stmt = (
        select(PromoterCode.agent_id)
        .select_from(CustomerAttribution)
        .join(Customer, Customer.id == CustomerAttribution.customer_id)
        .join(PromoterCode, PromoterCode.id == CustomerAttribution.promoter_code_id)
        .where(CustomerAttribution.organization_id == organization_id, Customer.user_id == user_id)
        .order_by(CustomerAttribution.attributed_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def apply_as_promoter(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, first_name: str, last_name: str
) -> AgentProfile:
    """Self-service 'Lavora con noi': an existing CUSTOMER becomes a PROMOTER.

    Auto-activates immediately at rank S1, under whichever promoter originally
    referred them (see _resolve_referring_agent_id) -- no admin approval
    needed, PROMOTER role granted right away. The exceptions, both routed
    through the original manual PENDING_APPROVAL/approve workflow instead:
    a previously blacklisted agent (AgentProfile.is_blacklisted, set by an
    admin via PATCH /agents/{id} -- worse than a plain deactivation), and an
    agent an admin explicitly set to SUSPENDED (the agent edit form's "Stato"
    dropdown -- update_agent() treats SUSPENDED as a real deactivation,
    revoking the PROMOTER role same as TERMINATED, so it must not silently
    self-heal here). TERMINATED (the dedicated "Disattiva" button) is the one
    status that IS meant to auto-reactivate on reapply, unchanged from before
    this auto-activation behavior existed.

    get_own_agent_profile() assumes at most one AgentProfile per user_id, so a
    reapply after a TERMINATED (deactivated/rejected) application resets that
    same row in place rather than calling create_agent() again -- a second row
    would make get_own_agent_profile()'s scalar_one_or_none() raise, and would
    orphan a second, disconnected network_nodes row for the same person."""
    from app.domains.rbac import service as rbac_service

    existing = await get_own_agent_profile(db, organization_id=organization_id, user_id=user_id)
    referring_agent_id = await _resolve_referring_agent_id(db, organization_id=organization_id, user_id=user_id)
    rank_id = await _get_current_rank_id(db, organization_id=organization_id, code=AUTO_ACTIVATION_RANK_CODE)

    if existing is not None:
        if existing.status in ("PENDING_APPROVAL", "ACTIVE"):
            raise DuplicateApplicationError(f"Existing application/profile is {existing.status}")

        # Blacklisted always needs manual review. SUSPENDED does too -- it's a
        # real, admin-selectable status (the agent edit form's "Stato" dropdown,
        # distinct from the dedicated "Disattiva"/"Blacklist" buttons which both
        # use TERMINATED) and update_agent() treats SUSPENDED as a genuine
        # deactivation (revokes the PROMOTER role, same as TERMINATED) -- letting
        # it silently auto-reactivate here would let the agent undo an admin's
        # explicit suspension with zero admin involvement, unlike TERMINATED
        # (the "Disattiva" case), which is intentionally self-service-reactivable.
        previous_status = existing.status
        if existing.is_blacklisted or existing.status == "SUSPENDED":
            existing.status = "PENDING_APPROVAL"
            existing.first_name = first_name
            existing.last_name = last_name
            existing.display_name = f"{first_name} {last_name}".strip()
            existing.approved_by_user_id = None
            existing.approved_at = None
            existing.rejection_reason = None
            await audit_service.record(
                db, organization_id=organization_id, actor_user_id=user_id,
                action="network.agent_reapplied", entity_type="agent_profile", entity_id=str(existing.id),
                previous_value={"status": previous_status}, new_value={"status": "PENDING_APPROVAL"},
            )
            await db.commit()
            await db.refresh(existing)
            return existing

        existing.status = "ACTIVE"
        existing.first_name = first_name
        existing.last_name = last_name
        existing.display_name = f"{first_name} {last_name}".strip()
        existing.current_rank_id = rank_id
        existing.approved_by_user_id = None
        existing.approved_at = utcnow()
        existing.rejection_reason = None

        current_parent_id = (
            await db.execute(
                select(NetworkNode.direct_parent_agent_id).where(
                    NetworkNode.organization_id == organization_id,
                    NetworkNode.agent_id == existing.id,
                    NetworkNode.effective_to.is_(None),
                )
            )
        ).scalar_one_or_none()
        if referring_agent_id is not None and referring_agent_id != current_parent_id:
            await move_agent(
                db, organization_id=organization_id, agent_id=existing.id,
                new_parent_agent_id=referring_agent_id, requested_by=user_id, approved_by=user_id,
                reason="Riattivazione automatica 'lavora con noi': sponsor dal link di invito originale",
            )

        await rbac_service.assign_role(db, user_id=user_id, organization_id=organization_id, role_code="PROMOTER")
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=user_id,
            action="network.agent_auto_activated", entity_type="agent_profile", entity_id=str(existing.id),
            previous_value={"status": "TERMINATED"}, new_value={"status": "ACTIVE"},
        )
        await db.commit()
        await db.refresh(existing)
        return existing

    agent = await create_agent(
        db,
        organization_id=organization_id,
        first_name=first_name,
        last_name=last_name,
        promoter_code=_generate_promoter_code(f"{first_name} {last_name}"),
        parent_agent_id=referring_agent_id,
        actor_user_id=user_id,
        user_id=user_id,
        current_rank_id=rank_id,
        status="ACTIVE",
    )
    await rbac_service.assign_role(db, user_id=user_id, organization_id=organization_id, role_code="PROMOTER")
    await db.commit()
    await db.refresh(agent)
    return agent


async def create_root_promoter_with_login(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    first_name: str,
    last_name: str,
    email: str,
    promoter_code: str | None,
    actor_user_id: uuid.UUID,
) -> tuple[AgentProfile, "User", "PromoterCode", str]:
    """SUPER_ADMIN/ORGANIZATION_ADMIN-only bootstrap for a brand-new, parentless
    network root. Registration everywhere else in the app is invite-only,
    gated on an existing promoter's referral code (see auth/service.py
    register_with_referral) -- there is deliberately no self-service way for
    anyone to become a root promoter, since a referral code always implies a
    parent. This is the one escape hatch: equivalent to what app/seed/data.py
    does for the demo network's a0, but for a real person, done in a single
    step (login + ACTIVE root agent + a usable referral link), not the
    suggest-then-approve dance create_agent()'s other callers go through."""
    from app.core.config import get_settings
    from app.core.security import hash_password
    from app.domains.rbac import service as rbac_service
    from app.domains.referral.models import PromoterCode
    from app.domains.users.models import User

    existing_user = (
        await db.execute(select(User).where(User.organization_id == organization_id, User.email == email))
    ).scalar_one_or_none()
    if existing_user is not None:
        raise RootPromoterConflictError(f"An account with email '{email}' already exists")

    code = promoter_code or _generate_promoter_code(f"{first_name} {last_name}")
    existing_code = (
        await db.execute(
            select(AgentProfile).where(
                AgentProfile.organization_id == organization_id, AgentProfile.promoter_code == code
            )
        )
    ).scalar_one_or_none()
    if existing_code is not None:
        raise RootPromoterConflictError(f"Promoter code '{code}' is already in use")

    temporary_password = _generate_temp_password()
    user = User(
        organization_id=organization_id,
        email=email,
        password_hash=hash_password(temporary_password),
        status="ACTIVE",
    )
    db.add(user)
    await db.flush()
    await rbac_service.assign_role(db, user_id=user.id, organization_id=organization_id, role_code="PROMOTER")

    agent = await create_agent(
        db,
        organization_id=organization_id,
        first_name=first_name,
        last_name=last_name,
        promoter_code=code,
        parent_agent_id=None,
        actor_user_id=actor_user_id,
        user_id=user.id,
        status="ACTIVE",
    )

    settings = get_settings()
    promoter_code_row = PromoterCode(
        organization_id=organization_id,
        agent_id=agent.id,
        code=code,
        personal_link=f"{settings.public_app_base_url}/r/{code}?org={organization_id}",
        status="ACTIVE",
        valid_from=utcnow(),
    )
    db.add(promoter_code_row)
    await audit_service.record(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="network.root_promoter_created",
        entity_type="agent_profile",
        entity_id=str(agent.id),
        new_value={"display_name": agent.display_name, "promoter_code": code, "email": email},
    )
    await db.commit()
    await db.refresh(agent)
    await db.refresh(promoter_code_row)
    return agent, user, promoter_code_row, temporary_password


def _generate_temp_password() -> str:
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16)) + "!Aa1"


async def move_agent(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    new_parent_agent_id: uuid.UUID | None,
    requested_by: uuid.UUID,
    approved_by: uuid.UUID | None,
    reason: str,
    effective_at: datetime | None = None,
) -> None:
    """Reparents agent_id (and its whole subtree) under new_parent_agent_id.

    Single transaction: closes the old node/edge/closure rows, opens new ones for
    the entire moving subtree, writes assignment history + audit. Never touches
    network_snapshots of already-activated contracts -- those keep pointing at the
    frozen chain that existed at activation time (see database-model.md).
    """
    effective_at = effective_at or utcnow()

    if new_parent_agent_id == agent_id:
        raise CycleError("An agent cannot be its own parent")

    node = (
        await db.execute(
            select(NetworkNode).where(
                NetworkNode.organization_id == organization_id,
                NetworkNode.agent_id == agent_id,
                NetworkNode.effective_to.is_(None),
            )
        )
    ).scalar_one_or_none()
    if node is None:
        raise NetworkError("Agent has no active network node")

    old_parent_agent_id = node.direct_parent_agent_id

    if new_parent_agent_id is not None:
        new_parent_ancestors = await _get_active_ancestors(
            db, organization_id=organization_id, agent_id=new_parent_agent_id
        )
        if any(ancestor_id == agent_id for ancestor_id, _ in new_parent_ancestors):
            raise CycleError("Move would create a cycle: new parent is a descendant of the agent")

    # The whole moving subtree (agent_id included, depth 0 = itself).
    subtree = await _get_active_descendants(db, organization_id=organization_id, agent_id=agent_id)
    subtree_ids = {a for a, _ in subtree}

    # Internal closure of the subtree (paths that stay valid regardless of the move).
    internal_rows = [
        row
        for row in (
            await db.execute(
                select(
                    NetworkClosure.ancestor_agent_id,
                    NetworkClosure.descendant_agent_id,
                    NetworkClosure.depth,
                ).where(
                    NetworkClosure.organization_id == organization_id,
                    NetworkClosure.ancestor_agent_id.in_(subtree_ids),
                    NetworkClosure.descendant_agent_id.in_(subtree_ids),
                    NetworkClosure.effective_to.is_(None),
                )
            )
        ).all()
    ]

    # Close every closure row that connects an old (non-subtree) ancestor to anything
    # inside the moving subtree.
    old_external_rows = (
        await db.execute(
            select(NetworkClosure).where(
                NetworkClosure.organization_id == organization_id,
                NetworkClosure.descendant_agent_id.in_(subtree_ids),
                NetworkClosure.ancestor_agent_id.not_in(subtree_ids),
                NetworkClosure.effective_to.is_(None),
            )
        )
    ).scalars().all()
    for row in old_external_rows:
        row.effective_to = effective_at

    # Close the old direct edge and node.
    if old_parent_agent_id is not None:
        old_edge = (
            await db.execute(
                select(NetworkEdge).where(
                    NetworkEdge.organization_id == organization_id,
                    NetworkEdge.parent_agent_id == old_parent_agent_id,
                    NetworkEdge.child_agent_id == agent_id,
                    NetworkEdge.effective_to.is_(None),
                )
            )
        ).scalar_one_or_none()
        if old_edge is not None:
            old_edge.effective_to = effective_at

    node.effective_to = effective_at
    new_node = NetworkNode(
        organization_id=organization_id,
        agent_id=agent_id,
        direct_parent_agent_id=new_parent_agent_id,
        status=node.status,
        effective_from=effective_at,
    )
    db.add(new_node)

    if new_parent_agent_id is not None:
        db.add(
            NetworkEdge(
                organization_id=organization_id,
                parent_agent_id=new_parent_agent_id,
                child_agent_id=agent_id,
                effective_from=effective_at,
            )
        )
        new_ancestors = await _get_active_ancestors(
            db, organization_id=organization_id, agent_id=new_parent_agent_id
        )
        # New paths: every (new ancestor) -> every (subtree member), depth composed.
        for ancestor_id, ancestor_depth in new_ancestors:
            for sub_ancestor, sub_descendant, sub_depth in internal_rows:
                if sub_ancestor != agent_id:
                    continue  # only need paths rooted at the moving agent itself
                db.add(
                    NetworkClosure(
                        organization_id=organization_id,
                        ancestor_agent_id=ancestor_id,
                        descendant_agent_id=sub_descendant,
                        depth=ancestor_depth + 1 + sub_depth,
                        effective_from=effective_at,
                    )
                )

    db.add(
        NetworkAssignmentHistory(
            organization_id=organization_id,
            agent_id=agent_id,
            old_parent_agent_id=old_parent_agent_id,
            new_parent_agent_id=new_parent_agent_id,
            requested_by=requested_by,
            approved_by=approved_by,
            reason=reason,
            effective_at=effective_at,
        )
    )

    await audit_service.record(
        db,
        organization_id=organization_id,
        actor_user_id=requested_by,
        action="network.agent_moved",
        entity_type="agent_profile",
        entity_id=str(agent_id),
        previous_value={"parent_agent_id": str(old_parent_agent_id) if old_parent_agent_id else None},
        new_value={"parent_agent_id": str(new_parent_agent_id) if new_parent_agent_id else None},
        reason=reason,
    )
    await db.commit()


async def list_agents(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    from app.domains.commissions.models import Rank
    from app.domains.users.models import User

    stmt = (
        select(
            AgentProfile.id,
            AgentProfile.display_name,
            AgentProfile.promoter_code,
            AgentProfile.status,
            AgentProfile.current_rank_id,
            AgentProfile.joined_at,
            Rank.code,
            NetworkNode.direct_parent_agent_id,
            AgentProfile.photo_url,
            AgentProfile.rejection_reason,
            User.email,
            AgentProfile.is_blacklisted,
            AgentProfile.first_name,
            AgentProfile.last_name,
            AgentProfile.user_id,
        )
        .join(Rank, Rank.id == AgentProfile.current_rank_id, isouter=True)
        .join(
            NetworkNode,
            (NetworkNode.agent_id == AgentProfile.id) & (NetworkNode.effective_to.is_(None)),
            isouter=True,
        )
        # isouter: an admin-suggested agent may have no user_id (no login of its
        # own) -- it must still show up in the list, just with email=None.
        .join(User, User.id == AgentProfile.user_id, isouter=True)
        .where(AgentProfile.organization_id == organization_id)
        .order_by(AgentProfile.joined_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": r[0],
            "display_name": r[1],
            "promoter_code": r[2],
            "status": r[3],
            "current_rank_id": r[4],
            "joined_at": r[5],
            "rank_code": r[6],
            "direct_parent_agent_id": r[7],
            "photo_url": r[8],
            "rejection_reason": r[9],
            "email": r[10],
            "is_blacklisted": r[11],
            "first_name": r[12],
            "last_name": r[13],
            "user_id": r[14],
        }
        for r in rows
    ]


async def update_agent(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    first_name: str | None,
    last_name: str | None,
    status_value: str | None,
    current_rank_id: uuid.UUID | None,
    actor_user_id: uuid.UUID,
    is_blacklisted: bool | None = None,
) -> AgentProfile | None:
    from app.domains.commissions.models import AgentRankHistory
    from app.domains.rbac import service as rbac_service

    agent = await db.get(AgentProfile, agent_id)
    if agent is None or agent.organization_id != organization_id:
        return None

    # PENDING_APPROVAL -> ACTIVE is an approval, not a plain edit -- must go
    # through approve_agent() (network.approve-gated) exclusively. Without this
    # guard, this function's network.manage-gated caller (PATCH /agents/{id})
    # would let a plain ADMIN confirm their own suggested agent, defeating the
    # entire point of network.approve being withheld from that role. Other
    # transitions into ACTIVE (e.g. "Riattiva" on a SUSPENDED/TERMINATED
    # agent) are unaffected -- only the PENDING_APPROVAL source status is special.
    if status_value == "ACTIVE" and agent.status == "PENDING_APPROVAL":
        raise AgentApprovalError("Use the dedicated approve endpoint (network.approve) to activate a suggested agent")

    previous = {
        "status": agent.status,
        "current_rank_id": str(agent.current_rank_id) if agent.current_rank_id else None,
        "is_blacklisted": agent.is_blacklisted,
    }
    if first_name is not None or last_name is not None:
        agent.first_name = first_name if first_name is not None else agent.first_name
        agent.last_name = last_name if last_name is not None else agent.last_name
        agent.display_name = f"{agent.first_name or ''} {agent.last_name or ''}".strip()
    if status_value is not None:
        agent.status = status_value
        # Deactivating (SUSPENDED/TERMINATED, e.g. the admin's "Disattiva
        # promoter"/"Blacklist" buttons) must actually take the PROMOTER
        # capability away, not just hide the row -- re-activating (back to
        # ACTIVE) restores it. A login-less admin-suggested agent has no
        # user_id and nothing to sync.
        if agent.user_id is not None:
            if status_value == "ACTIVE":
                await rbac_service.assign_role(
                    db, user_id=agent.user_id, organization_id=organization_id, role_code="PROMOTER"
                )
            elif status_value in ("SUSPENDED", "TERMINATED"):
                await rbac_service.revoke_role(
                    db, user_id=agent.user_id, organization_id=organization_id, role_code="PROMOTER"
                )
    if is_blacklisted is not None:
        agent.is_blacklisted = is_blacklisted
    if current_rank_id is not None:
        agent.current_rank_id = current_rank_id
        db.add(
            AgentRankHistory(
                organization_id=organization_id,
                agent_id=agent_id,
                rank_id=current_rank_id,
                effective_from=utcnow(),
                calculation_source="MANUAL",
                rule_version_id="manual-admin-update",
                approved_by=actor_user_id,
                reason="Aggiornamento qualifica da pannello amministrativo",
            )
        )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="network.agent_updated", entity_type="agent_profile", entity_id=str(agent_id),
        previous_value=previous,
        new_value={
            "status": agent.status,
            "current_rank_id": str(agent.current_rank_id) if agent.current_rank_id else None,
            "is_blacklisted": agent.is_blacklisted,
        },
    )
    await db.commit()
    await db.refresh(agent)
    return agent


class AgentApprovalError(Exception):
    pass


async def approve_agent(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID, actor_user_id: uuid.UUID
) -> AgentProfile | None:
    """Turns a suggested collaborator (PENDING_APPROVAL, created via POST
    /agents or /agents/recruit) into a real, usable ACTIVE agent -- gated on
    network.approve (SUPER_ADMIN/ORGANIZATION_ADMIN only, i.e. the
    "amministratore principale"), never the plain network.manage a regular
    ADMIN already holds."""
    agent = await db.get(AgentProfile, agent_id)
    if agent is None or agent.organization_id != organization_id:
        return None
    if agent.status != "PENDING_APPROVAL":
        raise AgentApprovalError(f"Agent is {agent.status}, not PENDING_APPROVAL")

    agent.status = "ACTIVE"
    agent.approved_by_user_id = actor_user_id
    agent.approved_at = utcnow()

    # An approved agent tied to a real user account also becomes a PROMOTER,
    # in addition to whatever roles (e.g. CUSTOMER) it already holds --
    # assign_role() is idempotent and a no-op for admin-created agents that
    # have no user_id.
    if agent.user_id is not None:
        from app.domains.rbac import service as rbac_service

        await rbac_service.assign_role(
            db, user_id=agent.user_id, organization_id=organization_id, role_code="PROMOTER"
        )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="network.agent_approved", entity_type="agent_profile", entity_id=str(agent_id),
        previous_value={"status": "PENDING_APPROVAL"}, new_value={"status": "ACTIVE"},
    )
    await db.commit()
    await db.refresh(agent)
    return agent


async def reject_agent(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID, actor_user_id: uuid.UUID, reason: str | None
) -> AgentProfile | None:
    """Rejects a suggested collaborator -- soft (TERMINATED + a reason kept on
    the row), never a hard delete, consistent with this project's
    append-only-history discipline elsewhere (documents, contracts)."""
    agent = await db.get(AgentProfile, agent_id)
    if agent is None or agent.organization_id != organization_id:
        return None
    if agent.status != "PENDING_APPROVAL":
        raise AgentApprovalError(f"Agent is {agent.status}, not PENDING_APPROVAL")

    agent.status = "TERMINATED"
    agent.approved_by_user_id = actor_user_id
    agent.approved_at = utcnow()
    agent.rejection_reason = reason

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="network.agent_rejected", entity_type="agent_profile", entity_id=str(agent_id),
        previous_value={"status": "PENDING_APPROVAL"}, new_value={"status": "TERMINATED", "reason": reason},
    )
    await db.commit()
    await db.refresh(agent)
    return agent


async def set_agent_photo(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID, photo_url: str, actor_user_id: uuid.UUID
) -> AgentProfile | None:
    agent = await db.get(AgentProfile, agent_id)
    if agent is None or agent.organization_id != organization_id:
        return None

    agent.photo_url = photo_url
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="network.agent_photo_updated", entity_type="agent_profile", entity_id=str(agent_id),
    )
    await db.commit()
    await db.refresh(agent)
    return agent


async def is_ancestor(
    db: AsyncSession, *, organization_id: uuid.UUID, ancestor_agent_id: uuid.UUID, agent_id: uuid.UUID
) -> bool:
    """ABAC helper: is ancestor_agent_id an active ancestor of agent_id (or the same
    agent)? Used to authorize branch-scoped access (e.g. network.read_branch)."""
    stmt = select(NetworkClosure.depth).where(
        NetworkClosure.organization_id == organization_id,
        NetworkClosure.ancestor_agent_id == ancestor_agent_id,
        NetworkClosure.descendant_agent_id == agent_id,
        NetworkClosure.effective_to.is_(None),
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def get_branch(
    db: AsyncSession, *, organization_id: uuid.UUID, root_agent_id: uuid.UUID
) -> list[dict]:
    """Descendants of root_agent_id (including itself, depth 0) with the display
    fields the network tree UI needs -- joined here so the router doesn't do a
    second round-trip per node."""
    from app.domains.commissions.models import Rank

    descendants = await _get_active_descendants(
        db, organization_id=organization_id, agent_id=root_agent_id
    )
    if not descendants:
        return []
    depth_by_agent = {agent_id: depth for agent_id, depth in descendants}

    stmt = (
        select(
            AgentProfile.id,
            AgentProfile.display_name,
            AgentProfile.promoter_code,
            AgentProfile.status,
            Rank.code,
            NetworkNode.direct_parent_agent_id,
        )
        .join(Rank, Rank.id == AgentProfile.current_rank_id, isouter=True)
        .join(
            NetworkNode,
            (NetworkNode.agent_id == AgentProfile.id) & (NetworkNode.effective_to.is_(None)),
            isouter=True,
        )
        .where(AgentProfile.id.in_(depth_by_agent.keys()))
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "agent_id": row[0],
            "depth": depth_by_agent[row[0]],
            "display_name": row[1],
            "promoter_code": row[2],
            "status": row[3],
            "rank_code": row[4],
            # The root's own parent (if any) sits outside this branch -- the UI
            # must not try to attach the root to a node it never fetched, so
            # this is null for the root agent specifically even though it has
            # a real parent in the full org tree.
            "parent_agent_id": row[5] if row[0] != root_agent_id else None,
        }
        for row in rows
    ]


# A contract in one of these statuses needs a human to unblock it (usually
# missing/rejected documents) -- surfaced to promoters as "problemi" so they
# know which of their own customers to chase, not just a raw status code.
PROBLEM_CONTRACT_STATUSES = {"DOCUMENTS_PENDING", "REJECTED", "SUSPENDED"}
# Still moving through the pipeline, nothing wrong yet.
IN_PROGRESS_CONTRACT_STATUSES = {"DRAFT", "SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING", "ACTIVATION_PENDING"}
# Reached a state where the deal is done (paying or has paid).
PROCESSED_CONTRACT_STATUSES = {"PAID", "ACTIVE", "RENEWED"}


async def get_branch_summary(
    db: AsyncSession, *, organization_id: uuid.UUID, root_agent_id: uuid.UUID
) -> dict:
    """Per-agent and per-level rollup for a promoter's own "azienda" view: how many
    contracts (by status bucket) each person in the branch has produced, and how
    much commission each has earned -- the data a promoter needs to run their
    downline like a real sales network, not just see names in a tree."""
    from app.domains.commissions.models import CommissionMovement
    from app.domains.contracts.models import Contract, ContractAttribution

    branch = await get_branch(db, organization_id=organization_id, root_agent_id=root_agent_id)
    if not branch:
        return {
            "agents": [],
            "totals": {
                "contracts": 0, "commission_cents": 0, "contracts_by_status": {},
                "contracts_closed": 0, "contracts_rejected": 0, "contracts_pending": 0,
                "contracts_in_progress": 0, "levels_below": 0, "people_total": 0,
            },
        }
    agent_ids = [row["agent_id"] for row in branch]

    contract_stmt = (
        select(ContractAttribution.producer_agent_id, Contract.status, func.count())
        .select_from(Contract)
        .join(ContractAttribution, ContractAttribution.id == Contract.contract_attribution_id)
        .where(ContractAttribution.producer_agent_id.in_(agent_ids))
        .group_by(ContractAttribution.producer_agent_id, Contract.status)
    )
    contract_rows = (await db.execute(contract_stmt)).all()
    contracts_by_agent: dict[uuid.UUID, dict[str, int]] = {}
    for producer_agent_id, status, count in contract_rows:
        contracts_by_agent.setdefault(producer_agent_id, {})[status] = count

    commission_stmt = (
        select(CommissionMovement.agent_id, func.coalesce(func.sum(CommissionMovement.amount_cents), 0))
        .where(
            CommissionMovement.agent_id.in_(agent_ids),
            CommissionMovement.status.notin_(["CANCELLED", "REVERSED"]),
        )
        .group_by(CommissionMovement.agent_id)
    )
    commission_rows = (await db.execute(commission_stmt)).all()
    commission_by_agent = {agent_id: int(total) for agent_id, total in commission_rows}

    agents = []
    total_contracts = 0
    total_commission_cents = 0
    total_by_status: dict[str, int] = {}
    max_depth = 0
    for row in branch:
        by_status = contracts_by_agent.get(row["agent_id"], {})
        agent_contract_total = sum(by_status.values())
        problem_count = sum(by_status.get(s, 0) for s in PROBLEM_CONTRACT_STATUSES)
        in_progress_count = sum(by_status.get(s, 0) for s in IN_PROGRESS_CONTRACT_STATUSES)
        processed_count = sum(by_status.get(s, 0) for s in PROCESSED_CONTRACT_STATUSES)
        agent_commission = commission_by_agent.get(row["agent_id"], 0)

        agents.append({
            **row,
            "contracts_total": agent_contract_total,
            "contracts_by_status": by_status,
            "contracts_problem": problem_count,
            "contracts_in_progress": in_progress_count,
            "contracts_processed": processed_count,
            "commission_cents": agent_commission,
        })
        total_contracts += agent_contract_total
        total_commission_cents += agent_commission
        max_depth = max(max_depth, row["depth"])
        for status, count in by_status.items():
            total_by_status[status] = total_by_status.get(status, 0) + count

    # "Chiusi/rifiutati/pending/in lavorazione" -- the four buckets a promoter
    # or admin needs at a glance (docs/business-rules.md#contract-state-machine
    # has the full status list; these are the coarse groupings people think in).
    total_closed = sum(total_by_status.get(s, 0) for s in PROCESSED_CONTRACT_STATUSES)
    total_rejected = total_by_status.get("REJECTED", 0)
    total_pending = sum(total_by_status.get(s, 0) for s in PROBLEM_CONTRACT_STATUSES) - total_rejected
    total_in_progress = sum(total_by_status.get(s, 0) for s in IN_PROGRESS_CONTRACT_STATUSES)

    return {
        "agents": agents,
        "totals": {
            "contracts": total_contracts,
            "commission_cents": total_commission_cents,
            "contracts_by_status": total_by_status,
            "contracts_closed": total_closed,
            "contracts_rejected": total_rejected,
            "contracts_pending": total_pending,
            "contracts_in_progress": total_in_progress,
            "levels_below": max_depth,
            "people_total": len(branch) - 1,  # exclude self (depth 0)
        },
    }


async def get_organization_network_levels(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    """Whole-organization view of the network tree: how many people sit at each
    depth from their own top-level sponsor, and how many levels deep the
    network goes in total. Unlike get_branch_summary (rooted at one promoter,
    for that promoter's own restricted view -- "un promoter puo solo vedere
    sotto di lui"), this has no root and is admin-only: it's the whole
    company's org chart, not one branch of it."""
    # An agent's own depth is the largest depth at which it appears as a
    # descendant -- the closure row from its topmost ancestor (a root, with no
    # parent) down to it. Multiple independent root agents can coexist, so
    # there's no single "root_agent_id" to pass to get_branch()/get_branch_summary().
    stmt = (
        select(NetworkClosure.descendant_agent_id, func.max(NetworkClosure.depth))
        .where(NetworkClosure.organization_id == organization_id)
        .group_by(NetworkClosure.descendant_agent_id)
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return {"people_total": 0, "levels_total": 0, "people_by_level": {}}

    people_by_level: dict[int, int] = {}
    for _agent_id, depth in rows:
        people_by_level[depth] = people_by_level.get(depth, 0) + 1

    return {
        "people_total": len(rows),
        "levels_total": max(people_by_level.keys()) + 1,
        "people_by_level": people_by_level,
    }


async def get_branch_contracts(
    db: AsyncSession, *, organization_id: uuid.UUID, root_agent_id: uuid.UUID, viewer_agent_id: uuid.UUID | None = None
) -> list[dict]:
    """Flat, contract-level detail for a promoter's whole downline: which
    customer, which product, what status, how much commission it has generated
    -- the link the promoter needs to go from "there's a problem" to "here's the
    customer to call". One row per contract, not per agent."""
    from app.domains.catalog.models import ProductVersion
    from app.domains.commissions.models import CommissionMovement
    from app.domains.contracts.models import Contract, ContractAttribution, ContractStatusHistory
    from app.domains.customers.models import Company, Customer, CustomerProfile, SupplyPoint
    from app.domains.customers.service import display_name_for

    branch = await get_branch(db, organization_id=organization_id, root_agent_id=root_agent_id)
    agent_ids = [row["agent_id"] for row in branch]
    if not agent_ids:
        return []
    agent_name_by_id = {row["agent_id"]: row["display_name"] for row in branch}

    stmt = (
        select(
            Contract.id,
            Contract.status,
            Contract.customer_id,
            Contract.supply_point_id,
            Contract.expires_at,
            ContractAttribution.producer_agent_id,
            ProductVersion.name,
            ProductVersion.base_price_cents,
        )
        .select_from(Contract)
        .join(ContractAttribution, ContractAttribution.id == Contract.contract_attribution_id)
        .join(ProductVersion, ProductVersion.id == Contract.product_version_id)
        .where(ContractAttribution.producer_agent_id.in_(agent_ids))
        .order_by(Contract.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return []

    contract_ids = [r[0] for r in rows]
    customer_ids = list({r[2] for r in rows})
    supply_point_ids = list({r[3] for r in rows})

    customers = {c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars()}
    profiles = {
        p.customer_id: p
        for p in (await db.execute(select(CustomerProfile).where(CustomerProfile.customer_id.in_(customer_ids)))).scalars()
    }
    companies = {
        c.customer_id: c
        for c in (await db.execute(select(Company).where(Company.customer_id.in_(customer_ids)))).scalars()
    }
    supply_point_labels = dict(
        (
            await db.execute(select(SupplyPoint.id, SupplyPoint.label).where(SupplyPoint.id.in_(supply_point_ids)))
        ).all()
    )

    commission_stmt = (
        select(CommissionMovement.contract_id, func.coalesce(func.sum(CommissionMovement.amount_cents), 0))
        .where(
            CommissionMovement.contract_id.in_(contract_ids),
            CommissionMovement.status.notin_(["CANCELLED", "REVERSED"]),
        )
        .group_by(CommissionMovement.contract_id)
    )
    commission_by_contract = {cid: int(total) for cid, total in (await db.execute(commission_stmt)).all()}

    # "Provvigione presa da me per quel contratto" -- the viewer's OWN cut of
    # each contract, distinct from commission_by_contract above (which sums
    # every beneficiary's share). None (not 0) when the viewer has no agent
    # profile at all (e.g. an org admin browsing someone else's branch) --
    # "not a beneficiary" and "earned zero" are different facts.
    my_commission_by_contract: dict[uuid.UUID, int] | None = None
    if viewer_agent_id is not None:
        my_commission_stmt = (
            select(CommissionMovement.contract_id, func.coalesce(func.sum(CommissionMovement.amount_cents), 0))
            .where(
                CommissionMovement.contract_id.in_(contract_ids),
                CommissionMovement.agent_id == viewer_agent_id,
                CommissionMovement.status.notin_(["CANCELLED", "REVERSED"]),
            )
            .group_by(CommissionMovement.contract_id)
        )
        my_commission_by_contract = {cid: int(total) for cid, total in (await db.execute(my_commission_stmt)).all()}

    # Most recent admin note per contract -- what an admin wrote when moving a
    # contract to e.g. DOCUMENTS_PENDING ("manca il documento X") is exactly
    # what the promoter needs to see to know what to chase with the customer.
    note_history_stmt = (
        select(ContractStatusHistory.contract_id, ContractStatusHistory.notes, ContractStatusHistory.created_at)
        .where(ContractStatusHistory.contract_id.in_(contract_ids), ContractStatusHistory.notes.isnot(None))
        .order_by(ContractStatusHistory.contract_id, ContractStatusHistory.created_at.desc())
    )
    latest_note_by_contract: dict[uuid.UUID, str] = {}
    for cid, notes, _created_at in (await db.execute(note_history_stmt)).all():
        if cid not in latest_note_by_contract:
            latest_note_by_contract[cid] = notes

    result = []
    for (
        contract_id, status, customer_id, supply_point_id, expires_at, producer_agent_id, product_name, base_price_cents,
    ) in rows:
        customer = customers.get(customer_id)
        result.append({
            "contract_id": contract_id,
            "status": status,
            "customer_id": customer_id,
            "customer_name": display_name_for(customer.kind, profiles.get(customer_id), companies.get(customer_id))
            if customer else "—",
            "customer_email": customer.email if customer else None,
            "customer_phone": customer.phone if customer else None,
            "product_name": product_name,
            "value_cents": base_price_cents,
            "supply_point_label": supply_point_labels.get(supply_point_id),
            "expires_at": expires_at,
            "producer_agent_id": producer_agent_id,
            "producer_name": agent_name_by_id.get(producer_agent_id, "—"),
            "commission_cents": commission_by_contract.get(contract_id, 0),
            "my_commission_cents": (
                my_commission_by_contract.get(contract_id, 0) if my_commission_by_contract is not None else None
            ),
            "is_problem": status in PROBLEM_CONTRACT_STATUSES,
            "admin_note": latest_note_by_contract.get(contract_id),
        })
    return result


async def create_snapshot_for_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, producer_agent_id: uuid.UUID, reason: str = "contract_activation"
) -> NetworkSnapshot:
    """Freezes the producer's current ancestor chain (with each ancestor's rank at
    this moment) into an immutable snapshot. Called once, at contract activation.

    Only agents who are ACTIVE at this exact moment are frozen into the chain --
    a SUSPENDED/TERMINATED agent, or one still PENDING_APPROVAL, is not a real,
    confirmed promoter and must not keep collecting entrepreneurial-difference
    commissions from a downline they no longer (or don't yet) actively belong to.
    _get_active_ancestors() only checks that the closure edge is structurally
    current (effective_to IS NULL) -- it says nothing about the agent's own
    status, which never gets touched by a status change (only move_agent()
    rewrites closure rows), so without this filter a terminated ancestor stays
    in every future descendant's chain forever. This only affects snapshots
    created from now on; already-frozen historical snapshots are untouched."""
    from app.domains.network.models import (
        AgentProfile as _AgentProfile,  # local import, avoid cycle at module load
    )

    ancestors = await _get_active_ancestors(db, organization_id=organization_id, agent_id=producer_agent_id)

    snapshot = NetworkSnapshot(organization_id=organization_id, reason=reason)
    db.add(snapshot)
    await db.flush()

    agent_ids = [a for a, _ in ancestors]
    agent_rows = (
        await db.execute(
            select(_AgentProfile.id, _AgentProfile.current_rank_id, _AgentProfile.status).where(
                _AgentProfile.id.in_(agent_ids)
            )
        )
    ).all()
    rank_by_active_agent = {row[0]: row[1] for row in agent_rows if row[2] == "ACTIVE"}

    for ancestor_id, depth in ancestors:
        if ancestor_id not in rank_by_active_agent:
            continue
        db.add(
            NetworkSnapshotNode(
                snapshot_id=snapshot.id,
                ancestor_agent_id=ancestor_id,
                depth=depth,
                rank_id_at_snapshot=rank_by_active_agent[ancestor_id],
            )
        )

    await db.flush()
    return snapshot
