import logging
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit import service as audit_service
from app.domains.contracts.models import Contract
from app.domains.customers.models import Company, Customer, CustomerProfile
from app.domains.customers.service import display_name_for
from app.domains.friend_referrals.models import (
    ACTIVE_CONTRACT_STATUSES,
    REWARD_DESCRIPTION,
    REWARD_EVERY,
    FriendReferral,
    FriendReferralCode,
    FriendReferralRewardClaim,
)
from app.domains.notifications import service as notifications_service
from app.domains.users.models import User

logger = logging.getLogger(__name__)

#: Prefix so an invite link is recognisably not a promoter code when it turns
#: up in a support conversation or a log line. Codes issued before this was
#: renamed (prefix "SEG") keep working: resolution is an exact match on the
#: whole code, never on the prefix.
CODE_PREFIX = "INV"


class FriendReferralError(Exception):
    pass


def _generate_code() -> str:
    return f"{CODE_PREFIX}-{secrets.token_hex(4).upper()}"


async def get_or_create_code(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> FriendReferralCode:
    """Created lazily on first use rather than for every account at signup --
    most people never share their link, and a row per account would be noise.
    Race-safe on uq_friend_referral_codes_user_id, same
    IntegrityError-then-reread pattern as wallets/service.py::
    get_or_create_wallet."""
    existing = (
        await db.execute(
            select(FriendReferralCode).where(
                FriendReferralCode.organization_id == organization_id,
                FriendReferralCode.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    row = FriendReferralCode(organization_id=organization_id, user_id=user_id, code=_generate_code())
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(FriendReferralCode).where(
                    FriendReferralCode.organization_id == organization_id,
                    FriendReferralCode.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        return existing
    await db.refresh(row)
    return row


async def get_active_code(
    db: AsyncSession, *, organization_id: uuid.UUID, code: str
) -> FriendReferralCode | None:
    return (
        await db.execute(
            select(FriendReferralCode).where(
                FriendReferralCode.organization_id == organization_id,
                FriendReferralCode.code == code,
                FriendReferralCode.status == "ACTIVE",
            )
        )
    ).scalar_one_or_none()


async def promoter_code_for_referrer(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID):
    """Which promoter the person invited through THIS user's friend link must
    be attributed to, for commissions.

    The business rule, verbatim: "se chi invita non è anche un promoter
    automaticamente il cliente va sotto il promoter di quella persona; se
    invece è un promoter va nel suo albero personale".

    So:
      - referrer is an ACTIVE promoter -> their own promoter code
      - otherwise                      -> the promoter code of whoever
                                          introduced the referrer

    Either way the answer is a real, ACTIVE agent: if the resolved promoter
    has since been deactivated we climb to the nearest active sponsor, the
    same rule contracts use (network/service.py::resolve_nearest_active_agent,
    see business-rules.md#terminated-promoter-fallback). Returns None only if
    there is genuinely nobody active to attribute to, which the caller must
    treat as "this link cannot be used right now" rather than attributing to
    nobody.
    """
    from app.domains.network import service as network_service
    from app.domains.referral import service as referral_service

    own_agent = await network_service.get_own_agent_profile(
        db, organization_id=organization_id, user_id=user_id
    )
    agent_id = None
    if own_agent is not None and own_agent.status == "ACTIVE":
        agent_id = own_agent.id
    else:
        # Not a promoter (or no longer one): inherit whoever brought THEM in.
        customer = (
            await db.execute(
                select(Customer).where(
                    Customer.organization_id == organization_id, Customer.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if customer is not None:
            attribution = await referral_service.get_current_attribution(
                db, organization_id=organization_id, customer_id=customer.id
            )
            if attribution is not None:
                code = await db.get(referral_service.PromoterCode, attribution.promoter_code_id)
                agent_id = code.agent_id if code is not None else None

    if agent_id is None:
        return None

    active_agent = await network_service.resolve_nearest_active_agent(
        db, organization_id=organization_id, agent_id=agent_id
    )
    if active_agent is None:
        return None
    return await referral_service.get_or_create_promoter_code(
        db, organization_id=organization_id, agent_id=active_agent.id
    )


async def record_referral(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    referrer_user_id: uuid.UUID,
    referred_customer_id: uuid.UUID,
    code_used: str,
    source: str,
) -> FriendReferral | None:
    """Idempotent on the referred customer. Never raises into the caller: this
    is a nice-to-have list, and a problem recording it must not be able to
    fail a registration that has otherwise completely succeeded."""
    try:
        existing = (
            await db.execute(
                select(FriendReferral).where(FriendReferral.referred_customer_id == referred_customer_id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        row = FriendReferral(
            organization_id=organization_id,
            referrer_user_id=referrer_user_id,
            referred_customer_id=referred_customer_id,
            code_used=code_used,
            source=source,
        )
        db.add(row)
        await db.flush()
        return row
    except Exception:
        logger.exception(
            "Could not record friend referral (referrer=%s, customer=%s)", referrer_user_id, referred_customer_id
        )
        return None


async def _referred_customer_rows(
    db: AsyncSession, *, organization_id: uuid.UUID, referrer_user_id: uuid.UUID
) -> list[tuple[FriendReferral, Customer]]:
    stmt = (
        select(FriendReferral, Customer)
        .join(Customer, Customer.id == FriendReferral.referred_customer_id)
        .where(
            FriendReferral.organization_id == organization_id,
            FriendReferral.referrer_user_id == referrer_user_id,
        )
        .order_by(FriendReferral.created_at.desc())
    )
    # (row.FriendReferral, row.Customer) rather than list(rows): a SQLAlchemy
    # Row is not a plain tuple to the type checker, so list(rows) is
    # untypeable here.
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]


async def list_my_referrals(
    db: AsyncSession, *, organization_id: uuid.UUID, referrer_user_id: uuid.UUID
) -> list[dict]:
    """The flat list, each entry with the state the referrer actually cares
    about. Three states, because "invitato ma non ha ancora fatto nulla" and
    "pratica in corso" are genuinely different news:

      INVITED      -- registered, no contract yet
      IN_PROGRESS  -- has a contract, not in force yet
      ACTIVE       -- has a contract genuinely in force; counts towards the gift

    Names only, deliberately: whoever sent the invite is not entitled to the email,
    phone or address of somebody just because they shared a link with them.
    """
    rows = await _referred_customer_rows(
        db, organization_id=organization_id, referrer_user_id=referrer_user_id
    )
    if not rows:
        return []

    customer_ids = [customer.id for _referral, customer in rows]
    profiles = {
        p.customer_id: p
        for p in (
            await db.execute(select(CustomerProfile).where(CustomerProfile.customer_id.in_(customer_ids)))
        ).scalars()
    }
    companies = {
        c.customer_id: c
        for c in (await db.execute(select(Company).where(Company.customer_id.in_(customer_ids)))).scalars()
    }
    contracts = list(
        (
            await db.execute(
                select(Contract.customer_id, Contract.status).where(Contract.customer_id.in_(customer_ids))
            )
        ).all()
    )
    statuses_by_customer: dict[uuid.UUID, set[str]] = {}
    for customer_id, status in contracts:
        statuses_by_customer.setdefault(customer_id, set()).add(status)

    result = []
    for referral, customer in rows:
        statuses = statuses_by_customer.get(customer.id, set())
        if statuses & set(ACTIVE_CONTRACT_STATUSES):
            state = "ACTIVE"
        elif statuses - {"CANCELLED", "REJECTED"}:
            state = "IN_PROGRESS"
        else:
            state = "INVITED"
        result.append({
            "id": referral.id,
            "display_name": display_name_for(
                customer.kind, profiles.get(customer.id), companies.get(customer.id)
            ),
            "state": state,
            "source": referral.source,
            "invited_at": referral.created_at,
        })
    return result


def _claimable_milestone(active_count: int, claimed_milestones: set[int]) -> int | None:
    """The next gift this person may ask for, or None.

    Milestones are absolute (5, 10, 15 ...) rather than a running counter, so
    "already claimed" is a fact about a number and not about a total that can
    move. The lowest unclaimed milestone at or below the current count wins,
    which means somebody who never claimed at 5 and is now at 12 is offered 5
    first, then 10 -- they are not silently skipped past the gifts they
    earned.
    """
    reached = [m for m in range(REWARD_EVERY, active_count + 1, REWARD_EVERY) if m not in claimed_milestones]
    return reached[0] if reached else None


async def get_my_summary(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> dict:
    code = await get_or_create_code(db, organization_id=organization_id, user_id=user_id)
    referrals = await list_my_referrals(
        db, organization_id=organization_id, referrer_user_id=user_id
    )
    active_count = sum(1 for r in referrals if r["state"] == "ACTIVE")
    claims = await list_my_claims(db, organization_id=organization_id, user_id=user_id)
    claimed = {c["milestone"] for c in claims}
    claimable = _claimable_milestone(active_count, claimed)
    return {
        "code": code.code,
        "invited_total": len(referrals),
        "active_total": active_count,
        "reward_every": REWARD_EVERY,
        "reward_description": REWARD_DESCRIPTION,
        # How many more activations until the NEXT gift -- 0 when one is
        # already claimable.
        "missing_for_next_reward": 0 if claimable else (REWARD_EVERY - (active_count % REWARD_EVERY)),
        "claimable_milestone": claimable,
        "referrals": referrals,
        "claims": claims,
    }


async def list_my_claims(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> list[dict]:
    rows = list(
        (
            await db.execute(
                select(FriendReferralRewardClaim)
                .where(
                    FriendReferralRewardClaim.organization_id == organization_id,
                    FriendReferralRewardClaim.referrer_user_id == user_id,
                )
                .order_by(FriendReferralRewardClaim.milestone.asc())
            )
        ).scalars()
    )
    return [
        {
            "id": r.id,
            "milestone": r.milestone,
            "status": r.status,
            "note": r.note,
            "requested_at": r.created_at,
            "handled_at": r.handled_at,
        }
        for r in rows
    ]


async def request_reward(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> FriendReferralRewardClaim:
    """Asks the administration for the gift earned at the next milestone.

    Recomputed server-side from the referrals actually in the database -- the
    client never says which milestone it thinks it has earned. A double-click
    or a replayed request lands on the same (user, milestone) unique
    constraint and returns the existing request rather than a second one.
    """
    summary = await get_my_summary(db, organization_id=organization_id, user_id=user_id)
    milestone = summary["claimable_milestone"]
    if milestone is None:
        raise FriendReferralError(
            f"Non hai ancora raggiunto {REWARD_EVERY} amici invitati con un contratto attivo."
        )

    claim = FriendReferralRewardClaim(
        organization_id=organization_id,
        referrer_user_id=user_id,
        milestone=milestone,
        status="REQUESTED",
    )
    db.add(claim)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(FriendReferralRewardClaim).where(
                    FriendReferralRewardClaim.referrer_user_id == user_id,
                    FriendReferralRewardClaim.milestone == milestone,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        return existing

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=user_id,
        action="friend_referral.reward_requested", entity_type="friend_referral_reward_claim",
        entity_id=str(claim.id), new_value={"milestone": milestone},
    )
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="FRIEND_REFERRAL_REWARD_REQUESTED", entity_type="friend_referral_reward_claim",
        entity_id=claim.id,
        title="Richiesta omaggio Invita un amico",
        body=(
            f"Un utente ha raggiunto {milestone} amici invitati con un contratto attivo "
            f"e chiede {REWARD_DESCRIPTION}."
        ),
        exclude_user_id=user_id,
    )
    await db.commit()
    await db.refresh(claim)
    return claim


async def notify_referrer_of_activation(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> None:
    """Best-effort: tells whoever brought this customer in that they have just
    gone active, and whether that unlocked a gift. Called from
    contracts/service.py when a contract enters ACTIVE -- after the commit, and
    swallowing everything, because a notification must never be able to fail
    an activation."""
    try:
        referral = (
            await db.execute(
                select(FriendReferral).where(
                    FriendReferral.organization_id == organization_id,
                    FriendReferral.referred_customer_id == customer_id,
                )
            )
        ).scalar_one_or_none()
        if referral is None:
            return
        summary = await get_my_summary(
            db, organization_id=organization_id, user_id=referral.referrer_user_id
        )
        if summary["claimable_milestone"] is not None:
            title = f"Hai raggiunto {summary['claimable_milestone']} amici invitati attivi!"
            body = (
                f"Puoi richiedere {REWARD_DESCRIPTION} dalla sezione «Invita un amico»."
            )
        else:
            title = "Un amico che hai invitato ha attivato un contratto"
            body = (
                f"Amici invitati con contratto attivo: {summary['active_total']}. "
                f"Ne mancano {summary['missing_for_next_reward']} al prossimo omaggio."
            )
        await notifications_service.notify_user(
            db, organization_id=organization_id, user_id=referral.referrer_user_id,
            type_="FRIEND_REFERRAL_ACTIVATED", entity_type="customer", entity_id=customer_id,
            title=title, body=body,
        )
        await db.commit()
    except Exception:
        logger.exception("Could not notify referrer for activated customer %s", customer_id)


# --- Admin -----------------------------------------------------------------


async def list_claims(db: AsyncSession, *, organization_id: uuid.UUID, status: str | None = None) -> list[dict]:
    stmt = (
        select(FriendReferralRewardClaim)
        .where(FriendReferralRewardClaim.organization_id == organization_id)
        .order_by(FriendReferralRewardClaim.created_at.desc())
    )
    if status and status != "ALL":
        stmt = stmt.where(FriendReferralRewardClaim.status == status)
    rows = list((await db.execute(stmt)).scalars())
    if not rows:
        return []

    user_ids = {r.referrer_user_id for r in rows}
    users = {
        u.id: u for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars()
    }
    customers = {
        c.user_id: c
        for c in (
            await db.execute(select(Customer).where(Customer.user_id.in_(user_ids)))
        ).scalars()
    }
    customer_ids = [c.id for c in customers.values()]
    profiles = {
        p.customer_id: p
        for p in (
            await db.execute(select(CustomerProfile).where(CustomerProfile.customer_id.in_(customer_ids)))
        ).scalars()
    } if customer_ids else {}
    companies = {
        c.customer_id: c
        for c in (await db.execute(select(Company).where(Company.customer_id.in_(customer_ids)))).scalars()
    } if customer_ids else {}

    result = []
    for r in rows:
        user = users.get(r.referrer_user_id)
        customer = customers.get(r.referrer_user_id)
        name = (
            display_name_for(customer.kind, profiles.get(customer.id), companies.get(customer.id))
            if customer is not None
            else None
        )
        result.append({
            "id": r.id,
            "referrer_user_id": r.referrer_user_id,
            "referrer_name": name if name and name != "—" else (user.email if user else "—"),
            "referrer_email": user.email if user else None,
            "milestone": r.milestone,
            "status": r.status,
            "note": r.note,
            "requested_at": r.created_at,
            "handled_at": r.handled_at,
        })
    return result


async def handle_claim(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    claim_id: uuid.UUID,
    status: str,
    note: str | None,
    actor_user_id: uuid.UUID,
) -> FriendReferralRewardClaim | None:
    claim = await db.get(FriendReferralRewardClaim, claim_id)
    if claim is None or claim.organization_id != organization_id:
        return None
    previous = claim.status
    claim.status = status
    claim.note = note
    claim.handled_by_user_id = actor_user_id
    claim.handled_at = datetime.now(UTC)

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="friend_referral.reward_handled", entity_type="friend_referral_reward_claim",
        entity_id=str(claim.id),
        previous_value={"status": previous}, new_value={"status": status, "note": note},
    )
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=claim.referrer_user_id,
        type_="FRIEND_REFERRAL_REWARD_HANDLED", entity_type="friend_referral_reward_claim",
        entity_id=claim.id,
        title=(
            f"Omaggio Invita un amico ({claim.milestone} attivi): "
            + ("consegnato" if status == "FULFILLED" else "richiesta non accolta")
        ),
        body=note,
    )
    await db.commit()
    await db.refresh(claim)
    return claim


async def count_active_referrals(
    db: AsyncSession, *, organization_id: uuid.UUID, referrer_user_id: uuid.UUID
) -> int:
    """Same definition as list_my_referrals' ACTIVE state, as a single count
    for callers that don't need the list."""
    stmt = (
        select(func.count(func.distinct(FriendReferral.referred_customer_id)))
        .select_from(FriendReferral)
        .join(Contract, Contract.customer_id == FriendReferral.referred_customer_id)
        .where(
            FriendReferral.organization_id == organization_id,
            FriendReferral.referrer_user_id == referrer_user_id,
            Contract.status.in_(ACTIVE_CONTRACT_STATUSES),
        )
    )
    return int((await db.execute(stmt)).scalar_one() or 0)
