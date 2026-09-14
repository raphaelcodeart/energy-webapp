"""La "rete segnalatori": una rete a UN livello, staccata da quella commerciale.

Deliberately a parallel structure, not an extension of the commercial network
-- the business was explicit that "non c'entra nulla con l'attuale rete, e'
una cosa staccata e separata che ogni cliente ha".

What it is: every person with a login has a personal invite link and a flat
list of the people who signed up through it. One level deep, no hierarchy, no
closure table, **no commissions** -- it exists purely so somebody who is not a
promoter can still see who they brought in, and so we can count how many of
those went on to activate a real Lial Energy contract.

What it is NOT: it never decides who earns anything. Where the new customer
lands in the *commercial* tree is still decided entirely by the existing
`referral`/`network` domains, by exactly the same rule as before:

  - referrer IS a promoter  -> the customer joins their own tree, as always
  - referrer is NOT         -> the customer joins the tree under the
                               referrer's OWN promoter

so this table can be dropped tomorrow without changing a single euro of
commission.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

#: How many activated referrals earn one gift. "un omaggio ogni 5 attivati" --
#: repeatable: 5, 10, 15 ... each is its own separately claimable milestone.
REWARD_EVERY = 5

#: A referred customer counts as "attivo" only once one of their contracts is
#: genuinely in force. RENEWED is included because a renewed contract is still
#: an active contract (see docs/business-rules.md, contract state machine) --
#: a customer must not stop counting on their renewal date.
ACTIVE_CONTRACT_STATUSES = ("ACTIVE", "RENEWED")

#: Which link the person actually used. Both feed the same list; the
#: distinction is only so an admin can tell a promoter's normal recruiting
#: from a plain customer's word-of-mouth.
REFERRAL_SOURCE_PROMOTER_LINK = "PROMOTER_LINK"
REFERRAL_SOURCE_FRIEND_LINK = "FRIEND_LINK"

CLAIM_STATUSES = ("REQUESTED", "FULFILLED", "REJECTED")


class FriendReferralCode(UUIDPKMixin, TimestampMixin, Base):
    """One personal invite code per login, created lazily the first time
    somebody opens "Segnala un amico".

    Separate from `promoter_codes` on purpose. That table means "this agent
    earns commissions on what comes through here" and is wired into
    attribution, the network tree and the commission engine; this one means
    nothing more than "this person shared a link". Overloading the promoter
    table with codes that pay nobody would have made every existing query
    about promoter codes subtly wrong.
    """

    __tablename__ = "friend_referral_codes"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_friend_referral_codes_user_id"),
        UniqueConstraint("code", name="uq_friend_referral_codes_code"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    code: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")


class FriendReferral(UUIDPKMixin, TimestampMixin, Base):
    """One row per person somebody brought in. The flat, one-level list.

    There is no `activated_at` column, deliberately: whether a referred
    customer counts as "attivo" is derived from their contracts at read time.
    A stored flag would need an event hook on every path that can activate,
    renew or cancel a contract, and the first one anybody forgot would leave
    the count permanently wrong with nothing to reconcile it against.
    """

    __tablename__ = "friend_referrals"
    __table_args__ = (
        # A customer can only ever have been brought in by one person.
        UniqueConstraint("referred_customer_id", name="uq_friend_referrals_referred_customer_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    referrer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    referred_customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    #: The code as typed/clicked, kept for support ("quale link ha usato?").
    code_used: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16))


class FriendReferralRewardClaim(UUIDPKMixin, TimestampMixin, Base):
    """A request for the gift earned at a milestone (5, 10, 15 ... referrals
    activated). Explicitly NOT an automatic wallet credit: the business chose
    to keep a human in the loop, so the gift can be anything -- LialCash, a
    product, a voucher -- decided case by case.

    The UNIQUE on (referrer_user_id, milestone) is what makes "un omaggio ogni
    5" exact: milestone 5 can be requested once, ever, whatever happens to the
    count afterwards.
    """

    __tablename__ = "friend_referral_reward_claims"
    __table_args__ = (
        UniqueConstraint("referrer_user_id", "milestone", name="uq_friend_referral_claim_user_milestone"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    referrer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    #: 5, 10, 15 ... -- the number of activated referrals this gift is for.
    milestone: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="REQUESTED", index=True)
    handled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    handled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
