import hashlib
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.referral.models import (
    AttributionCorrection,
    CustomerAttribution,
    PromoterCode,
    ReferralEvent,
    ReferralSession,
)

settings = get_settings()

# Attribution window: how long a referral session stays valid for attributing a
# later registration/purchase to the promoter who generated the click.
ATTRIBUTION_WINDOW_DAYS = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def get_or_create_promoter_code(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID
) -> PromoterCode:
    """Every agent can share a referral link -- reuses the agent's existing
    promoter_code (already unique per org, see agent_profiles) as the referral
    code rather than generating a separate random one, so a promoter only ever
    has to remember/quote one code. Created lazily on first request instead of
    at agent-creation time, since most agents may never need to share a link."""
    from app.domains.network.models import AgentProfile

    stmt = select(PromoterCode).where(
        PromoterCode.organization_id == organization_id,
        PromoterCode.agent_id == agent_id,
        PromoterCode.status == "ACTIVE",
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    agent = await db.get(AgentProfile, agent_id)
    if agent is None or agent.organization_id != organization_id:
        raise ValueError("Unknown agent")

    now = utcnow()
    promoter_code = PromoterCode(
        organization_id=organization_id,
        agent_id=agent_id,
        code=agent.promoter_code,
        personal_link=f"/r/{agent.promoter_code}",
        status="ACTIVE",
        valid_from=now,
    )
    db.add(promoter_code)
    await db.commit()
    await db.refresh(promoter_code)
    return promoter_code


async def get_active_promoter_code(
    db: AsyncSession, *, organization_id: uuid.UUID, code: str
) -> PromoterCode | None:
    now = utcnow()
    stmt = select(PromoterCode).where(
        PromoterCode.organization_id == organization_id,
        PromoterCode.code == code,
        PromoterCode.status == "ACTIVE",
        PromoterCode.valid_from <= now,
    )
    code_row = (await db.execute(stmt)).scalar_one_or_none()
    if code_row is None:
        return None
    if code_row.valid_to is not None and code_row.valid_to < now:
        return None
    return code_row


async def record_referral_click(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    promoter_code: PromoterCode,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[ReferralSession, str]:
    """Records the click, opens a referral session, and returns the raw (unhashed)
    cookie token to set on the visitor's browser -- only the hash is persisted."""
    now = utcnow()
    db.add(
        ReferralEvent(
            organization_id=organization_id,
            promoter_code_id=promoter_code.id,
            ip_address=ip_address,
            user_agent=user_agent,
            occurred_at=now,
        )
    )
    raw_token = secrets.token_urlsafe(32)
    session = ReferralSession(
        organization_id=organization_id,
        promoter_code_id=promoter_code.id,
        cookie_token_hash=_hash_token(raw_token),
        expires_at=now + timedelta(days=ATTRIBUTION_WINDOW_DAYS),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session, raw_token


async def resolve_referral_session(
    db: AsyncSession, *, organization_id: uuid.UUID, cookie_token: str
) -> ReferralSession | None:
    stmt = select(ReferralSession).where(
        ReferralSession.organization_id == organization_id,
        ReferralSession.cookie_token_hash == _hash_token(cookie_token),
    )
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session is None or session.expires_at < utcnow():
        return None
    return session


async def attribute_customer(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    promoter_code_id: uuid.UUID,
    referral_session_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None = None,
) -> CustomerAttribution:
    attribution = CustomerAttribution(
        organization_id=organization_id,
        customer_id=customer_id,
        promoter_code_id=promoter_code_id,
        referral_session_id=referral_session_id,
        attributed_at=utcnow(),
    )
    db.add(attribution)
    await audit_service.record(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="referral.customer_attributed",
        entity_type="customer",
        entity_id=str(customer_id),
        new_value={"promoter_code_id": str(promoter_code_id)},
    )
    await db.commit()
    await db.refresh(attribution)
    return attribution


class ReassignmentError(Exception):
    pass


async def get_current_attribution(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> CustomerAttribution | None:
    stmt = (
        select(CustomerAttribution)
        .where(CustomerAttribution.organization_id == organization_id, CustomerAttribution.customer_id == customer_id)
        .order_by(CustomerAttribution.attributed_at.desc())
    )
    return (await db.execute(stmt)).scalars().first()


async def reassign_customer_promoter(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    new_agent_id: uuid.UUID,
    requested_by: uuid.UUID,
    reason: str,
) -> CustomerAttribution:
    """Changes which promoter a customer is attributed to -- admin-only
    (see customers/router.py). "nessuno può stare senza promoter che lo
    invita" (business-rules.md) means every customer keeps an attribution,
    it just moves from one promoter to another; a customer is never left
    unattributed. AttributionCorrection is a pre-existing, previously-unused
    schema (referral/models.py) built for exactly this -- the audit trail of
    who moved a customer from which promoter to which, requested by whom,
    and why.

    **Dual-role people move in the network tree too (Session 37).** A person
    can hold both CUSTOMER and PROMOTER roles (see business-rules.md
    #customer-promoter-dual-role). Reassigning such a person used to move
    only this attribution, leaving them hanging under their OLD promoter in
    the commission tree -- "cliente di Carlo, ma downline di Alessandro",
    which is not a state anyone asked for and looked to admins like the
    reassignment had silently failed. Per the explicit business rule: from
    the moment of reassignment the person belongs to the new promoter *in
    their entirety*, as if that promoter had signed them up. So when the
    customer also has an AgentProfile, they (and their whole downline) are
    reparented under the new promoter as well.

    Past commissions are deliberately left untouched: every activated
    contract keeps the network snapshot frozen at its activation
    (contracts/service.py::transition_contract -> create_snapshot_for_contract),
    so a move only ever changes who earns on FUTURE production. That is
    exactly the intended semantics ("del vecchio storico non ci interessa"),
    not an oversight."""
    from app.domains.network import service as network_service

    current = await get_current_attribution(db, organization_id=organization_id, customer_id=customer_id)
    if current is None:
        raise ReassignmentError("This customer has no existing promoter attribution to correct")

    new_promoter_code = await get_or_create_promoter_code(
        db, organization_id=organization_id, agent_id=new_agent_id
    )
    if new_promoter_code.id == current.promoter_code_id:
        raise ReassignmentError("Customer is already attributed to this promoter")

    db.add(
        AttributionCorrection(
            organization_id=organization_id,
            customer_attribution_id=current.id,
            previous_promoter_code_id=current.promoter_code_id,
            new_promoter_code_id=new_promoter_code.id,
            requested_by=requested_by,
            approved_by=requested_by,  # admin-only action -- see router.py permission gate
            reason=reason,
        )
    )
    previous_promoter_code_id = current.promoter_code_id
    current.promoter_code_id = new_promoter_code.id

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=requested_by,
        action="referral.customer_reassigned", entity_type="customer", entity_id=str(customer_id),
        previous_value={"promoter_code_id": str(previous_promoter_code_id)},
        new_value={"promoter_code_id": str(new_promoter_code.id)},
        reason=reason,
    )

    moving_agent_id = await _agent_id_to_move_with_customer(
        db, organization_id=organization_id, customer_id=customer_id, new_agent_id=new_agent_id
    )
    if moving_agent_id is not None:
        # move_agent() commits -- which lands the attribution change above in
        # that same transaction, so the two either both happen or neither
        # does. A CycleError here therefore leaves NOTHING committed, rather
        # than a customer reassigned but stranded in the old tree position.
        try:
            await network_service.move_agent(
                db, organization_id=organization_id, agent_id=moving_agent_id,
                new_parent_agent_id=new_agent_id, requested_by=requested_by,
                approved_by=requested_by,  # same admin-only gate as the reassignment itself
                reason=f"Riassegnazione promoter: {reason}",
            )
        except network_service.CycleError as exc:
            raise ReassignmentError(
                "Impossibile riassegnare: il nuovo promoter fa già parte della rete sotto questa "
                "persona, e spostarla creerebbe un anello nell'albero."
            ) from exc
    else:
        await db.commit()

    await db.refresh(current)
    return current


async def _agent_id_to_move_with_customer(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_id: uuid.UUID, new_agent_id: uuid.UUID
) -> uuid.UUID | None:
    """The AgentProfile that must follow this customer to the new promoter,
    or None when there is nothing to move -- i.e. the customer has no login,
    isn't a promoter at all (the common case: a plain customer, whose
    reassignment behaves exactly as it did before this existed), is already
    sitting under the new promoter, or IS the new promoter."""
    from app.domains.customers.models import Customer
    from app.domains.network import service as network_service

    customer = await db.get(Customer, customer_id)
    if customer is None or customer.user_id is None:
        return None

    agent = await network_service.get_own_agent_profile(
        db, organization_id=organization_id, user_id=customer.user_id
    )
    if agent is None or agent.id == new_agent_id:
        return None

    node = await network_service.get_active_node(db, organization_id=organization_id, agent_id=agent.id)
    if node is None or node.direct_parent_agent_id == new_agent_id:
        # Never placed in the tree, or already in the right place -- moving
        # would only add a no-op row to the assignment history.
        return None
    return agent.id
