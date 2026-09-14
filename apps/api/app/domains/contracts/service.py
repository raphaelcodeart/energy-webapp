import calendar
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.catalog import pricing
from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts.models import Contract, ContractAttribution, ContractStatusHistory
from app.domains.contracts.state_machine import assert_transition_allowed, event_name_for
from app.domains.customers.models import SupplyPoint
from app.domains.network import service as network_service
from app.domains.network.models import AgentProfile
from app.domains.notifications import service as notifications_service
from app.domains.outbox import service as outbox_service
from app.domains.users.models import User

if TYPE_CHECKING:
    # Annotation-only -- the real import stays function-local in
    # create_contract_self_service, matching this module's existing
    # convention (see e.g. the customers/network imports below).
    from app.domains.customers.schemas import SupplyPointCreate

# Statuses that represent "the contract's term is running" -- entering one of
# these (re)starts the clock on activated_at/expires_at. Renewing a lapsed
# (EXPIRED) contract restarts it too, same as the first activation.
TERM_START_STATUSES = {"ACTIVE", "RENEWED"}

logger = logging.getLogger(__name__)

#: wallet_transactions.source for the automatic credit a paid Lial Energy
#: contract generates. A distinct value from ORDER_CASHBACK_BASE and
#: INVOICE_REDEMPTION_BASE precisely so accounting can tell the three apart
#: at a glance -- they are three different business rules, not one.
CONTRACT_CASHBACK_SOURCE = "CONTRACT_CASHBACK"


def _add_months(dt: datetime, months: int) -> datetime:
    """Stdlib month arithmetic (no dateutil dependency): clamps the day to the
    target month's actual length, e.g. Jan 31 + 1 month -> Feb 28/29."""
    total_months = dt.month - 1 + months
    year = dt.year + total_months // 12
    month = total_months % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


async def to_read_dicts(db: AsyncSession, contracts: list[Contract]) -> list[dict]:
    """Bulk-attaches product_name/supply_point_label to a page of contracts --
    the "name prominent, id small below" rule applies to every contract list in
    the app, so this is the single place that does the join instead of each
    caller re-deriving it (or, worse, the UI showing a bare UUID)."""
    if not contracts:
        return []

    product_version_ids = {c.product_version_id for c in contracts}
    supply_point_ids = {c.supply_point_id for c in contracts}
    # Both "who filled it in for the customer" and "who originally brought
    # the customer in" are shown by name, never as a bare UUID -- same
    # "name prominent" rule the product/supply-point joins above follow.
    agent_ids = {c.activated_by_promoter_id for c in contracts if c.activated_by_promoter_id} | {
        c.first_referrer_agent_id for c in contracts if c.first_referrer_agent_id
    }
    # Dict comprehensions rather than dict(rows): a SQLAlchemy Row is not a
    # plain tuple as far as the type checker is concerned, so dict(rows) is
    # untypeable and needs an annotation that then contradicts itself.
    agent_names: dict[uuid.UUID, str] = (
        {
            row.id: row.display_name
            for row in (
                await db.execute(
                    select(AgentProfile.id, AgentProfile.display_name).where(AgentProfile.id.in_(agent_ids))
                )
            ).all()
        }
        if agent_ids
        else {}
    )

    product_names: dict[uuid.UUID, str] = {
        row.id: row.name
        for row in (
            await db.execute(
                select(ProductVersion.id, ProductVersion.name).where(ProductVersion.id.in_(product_version_ids))
            )
        ).all()
    }
    supply_point_labels: dict[uuid.UUID, str | None] = {
        row.id: row.label
        for row in (
            await db.execute(
                select(SupplyPoint.id, SupplyPoint.label).where(SupplyPoint.id.in_(supply_point_ids))
            )
        ).all()
    }

    def _agent_name(agent_id: uuid.UUID | None) -> str | None:
        return agent_names.get(agent_id) if agent_id is not None else None

    result = []
    for c in contracts:
        row = {
            "id": c.id,
            "customer_id": c.customer_id,
            "supply_point_id": c.supply_point_id,
            "product_version_id": c.product_version_id,
            "status": c.status,
            "notes": c.notes,
            "iban": c.iban,
            "email": c.email,
            "created_at": c.created_at,
            "activated_at": c.activated_at,
            "expires_at": c.expires_at,
            "product_name": product_names.get(c.product_version_id),
            "supply_point_label": supply_point_labels.get(c.supply_point_id),
            "created_by_role": c.created_by_role,
            "activated_by_promoter_id": c.activated_by_promoter_id,
            "activated_by_promoter_name": _agent_name(c.activated_by_promoter_id),
            "first_referrer_agent_id": c.first_referrer_agent_id,
            "first_referrer_name": _agent_name(c.first_referrer_agent_id),
            "customer_kind": c.customer_kind,
            "net_amount_cents": c.net_amount_cents,
            # Decimal -> float at the edge: JSON has no decimal type and this
            # is a display value, not an amount anything is computed from
            # (every cent figure is already an integer above).
            "vat_rate": float(c.vat_rate) if c.vat_rate is not None else None,
            "vat_amount_cents": c.vat_amount_cents,
            "gross_amount_cents": c.gross_amount_cents,
            "payment_plan": c.payment_plan,
            "payment_method": c.payment_method,
            "paid_at": c.paid_at,
            "terms_accepted_at": c.terms_accepted_at,
            "terms_version": c.terms_version,
        }
        result.append(row)
    return result


async def get_status_history(db: AsyncSession, *, contract_id: uuid.UUID) -> list[dict]:
    """Full audit trail of every status change for one contract (who, when,
    from/to, why) -- backs the "click the status badge" history popup. Actor
    display name prefers the agent's display_name (how they're known
    everywhere else in the app) and falls back to their login email for a
    pure back-office user with no AgentProfile row."""
    stmt = (
        select(ContractStatusHistory)
        .where(ContractStatusHistory.contract_id == contract_id)
        .order_by(ContractStatusHistory.created_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return []

    user_ids = {r.actor_user_id for r in rows}
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars()}
    agents_by_user = {
        a.user_id: a
        for a in (
            await db.execute(select(AgentProfile).where(AgentProfile.user_id.in_(user_ids)))
        ).scalars()
    }

    result = []
    for r in rows:
        agent = agents_by_user.get(r.actor_user_id)
        user = users.get(r.actor_user_id)
        actor_name = agent.display_name if agent else (user.email if user else "—")
        result.append({
            "id": r.id,
            "from_status": r.from_status,
            "to_status": r.to_status,
            "actor_user_id": r.actor_user_id,
            "actor_name": actor_name,
            "reason": r.reason,
            "notes": r.notes,
            "created_at": r.created_at,
        })
    return result


class InvalidProducerAgentError(Exception):
    """Raised when a contract is created with a producer_agent_id that does not
    resolve to a real, active agent in this organization. Left unchecked, this
    silently breaks commission calculation later: create_snapshot_for_contract()
    would freeze an empty ancestor chain for a nonexistent agent, and
    run_calculation_for_contract() would then find an empty chain and skip
    calculation entirely -- see docs/paid-contract-commission-audit.md, Problem #1.
    Failing fast here, at creation time, is far cheaper than discovering it after
    activation with no commissions paid and nothing to point to why."""


async def create_contract(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    supply_point_id: uuid.UUID,
    product_version_id: uuid.UUID,
    producer_agent_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: str,
    notes: str | None = None,
    iban: str | None = None,
    email: str | None = None,
    created_by_role: str | None = None,
    activated_by_promoter_id: uuid.UUID | None = None,
) -> Contract:
    """Creates a DRAFT contract. Deliberately does NOT touch commissions -- creating
    or submitting a contract never generates a commission (business-rules.md).

    `created_by_role` is the role the creator was acting as (CUSTOMER /
    PROMOTER / ADMIN), snapshotted rather than looked up later because a
    person's roles change. `activated_by_promoter_id` is set ONLY when a
    promoter filled the contract in on the customer's behalf -- it is what
    makes "Contratto attivato dal promoter X" true exactly when it is true,
    instead of being inferred from who happens to earn the commission
    (which is also the promoter in the ordinary self-service case).

    The price breakdown is computed here, server-side, from the product
    version row and the customer's own kind -- never from anything a caller
    passed in -- and frozen onto the contract. See catalog/pricing.py."""
    producer = await db.get(AgentProfile, producer_agent_id)
    if producer is None or producer.organization_id != organization_id:
        raise InvalidProducerAgentError(
            f"producer_agent_id {producer_agent_id} is not a known agent in this organization"
        )
    if producer.status != "ACTIVE":
        raise InvalidProducerAgentError(
            f"producer_agent_id {producer_agent_id} is {producer.status}, not ACTIVE -- "
            "cannot attribute a new contract to a non-active agent"
        )

    from app.domains.customers.models import Customer

    attribution = ContractAttribution(
        organization_id=organization_id,
        producer_agent_id=producer_agent_id,
        attributed_promoter_id=producer_agent_id,
    )
    db.add(attribution)
    await db.flush()

    # The customer's kind is what decides whether VAT applies at all, so it is
    # read once here and frozen alongside the amounts it produced.
    customer = await db.get(Customer, customer_id)
    customer_kind = customer.kind if customer is not None else None
    version = await db.get(ProductVersion, product_version_id)
    price = (
        pricing.compute_contract_price(version=version, customer_kind=customer_kind)
        if version is not None
        else None
    )

    # Who originally brought this customer in. Resolved now and frozen,
    # deliberately NOT re-read at activation: an admin reassigning the
    # customer to another promoter afterwards changes who earns future
    # business, not who is owed the bonus on a contract already opened.
    first_referrer_agent_id = await _resolve_referring_agent_id_for_customer(
        db, organization_id=organization_id, customer_id=customer_id
    )

    contract = Contract(
        organization_id=organization_id,
        customer_id=customer_id,
        supply_point_id=supply_point_id,
        product_version_id=product_version_id,
        contract_attribution_id=attribution.id,
        status="DRAFT",
        notes=notes,
        iban=iban,
        email=email,
        created_by_user_id=actor_user_id,
        created_by_role=created_by_role,
        activated_by_promoter_id=activated_by_promoter_id,
        first_referrer_agent_id=first_referrer_agent_id,
        customer_kind=customer_kind,
        net_amount_cents=price.net_amount_cents if price else None,
        vat_rate=price.vat_rate if price else None,
        vat_amount_cents=price.vat_amount_cents if price else None,
        gross_amount_cents=price.gross_amount_cents if price else None,
    )
    db.add(contract)
    await db.flush()

    db.add(
        ContractStatusHistory(
            contract_id=contract.id,
            from_status=None,
            to_status="DRAFT",
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
    )
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract.created", entity_type="contract", entity_id=str(contract.id),
        new_value={"status": "DRAFT"},
    )
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CONTRACT_CREATED", entity_type="contract", entity_id=contract.id,
        title="Nuovo contratto creato", body=f"Contratto {contract.id} in stato Bozza.",
        exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(contract)
    return contract


class SelfServiceContractError(Exception):
    pass


async def _resolve_referring_agent_id_for_customer(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> uuid.UUID | None:
    """Same lookup network/service.py::_resolve_referring_agent_id does (by
    user_id) but keyed directly by customer_id, which
    create_contract_self_service already has on hand -- duplicated rather
    than imported across domains, matching this codebase's convention for
    small, domain-local batch/lookup helpers (see e.g. orders/service.py's
    own copy of _resolve_display_name)."""
    from app.domains.referral.models import CustomerAttribution, PromoterCode

    stmt = (
        select(PromoterCode.agent_id)
        .select_from(CustomerAttribution)
        .join(PromoterCode, PromoterCode.id == CustomerAttribution.promoter_code_id)
        .where(CustomerAttribution.organization_id == organization_id, CustomerAttribution.customer_id == customer_id)
        .order_by(CustomerAttribution.attributed_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_contract_self_service(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    product_version_id: uuid.UUID,
    supply_point_payload: "SupplyPointCreate",
    email: str,
) -> Contract:
    """'Attiva Contratto': a customer activates a Lial Energy (INTERNAL)
    product themselves, no promoter/admin action needed to get it started.
    Resolves the commission producer from the customer's own referral
    attribution (same sponsor "lavora con noi" auto-activation uses) --
    there is no self-service way to pick a different one, registration is
    invite-only precisely so this attribution always exists (see
    auth/service.py::register_with_referral). Immediately submits and marks
    DOCUMENTS_PENDING -- unlike a promoter/admin building up a DRAFT by
    hand, self-service has no "save for later, not ready to send yet" step;
    the customer's next action is exactly what DOCUMENTS_PENDING says:
    upload the required documents (business-rules.md#contract-self-service)."""
    from app.domains.customers import service as customers_service
    from app.domains.customers.models import Customer

    customer = (
        await db.execute(
            select(Customer).where(Customer.organization_id == organization_id, Customer.user_id == customer_user_id)
        )
    ).scalar_one_or_none()
    if customer is None:
        raise SelfServiceContractError("No customer record linked to this account")

    version = await db.get(ProductVersion, product_version_id)
    if version is None:
        raise SelfServiceContractError("Product version not found")
    product = await db.get(Product, version.product_id)
    if product is None or product.organization_id != organization_id:
        raise SelfServiceContractError("Product version not found")
    if product.category != "INTERNAL":
        raise SelfServiceContractError(
            "Solo i prodotti Lial Energy si attivano come contratto -- gli altri prodotti si acquistano come ordine."
        )
    # The catalog the customer sees is already filtered by this same rule --
    # this is the enforcement, because hiding a card is never enforcement.
    if not pricing.product_allows_customer_kind(product.customer_type, customer.kind):
        raise SelfServiceContractError(
            "Questo contratto non è disponibile per la tua tipologia di cliente."
        )

    producer_agent_id = await _resolve_referring_agent_id_for_customer(
        db, organization_id=organization_id, customer_id=customer.id
    )
    if producer_agent_id is None:
        raise SelfServiceContractError(
            "Nessun promoter di riferimento trovato per il tuo account -- contatta l'assistenza."
        )
    # A customer must never be stranded by something they had no part in.
    # Their referring promoter can be deactivated months after they signed
    # up, and create_contract() refuses to attribute a contract to a
    # non-ACTIVE agent -- correctly, since a contract that activates and pays
    # nobody is a real failure mode (docs/paid-contract-commission-audit.md).
    # Business decision: walk UP to the nearest active sponsor rather than
    # block, so the branch that built the relationship keeps it and nobody
    # waits for an admin to notice. The original referrer is still recorded
    # on the contract (first_referrer_agent_id), so the substitution is
    # visible rather than silent.
    producer = await network_service.resolve_nearest_active_agent(
        db, organization_id=organization_id, agent_id=producer_agent_id
    )
    if producer is None:
        raise SelfServiceContractError(
            "Il promoter che ti ha invitato non è più attivo e non risulta nessun referente attivo "
            "sopra di lui. Contatta l'assistenza: ti verrà assegnato un nuovo referente e potrai "
            "completare l'attivazione."
        )
    substituted_for_agent_id = producer_agent_id if producer.id != producer_agent_id else None
    producer_agent_id = producer.id

    supply_point = await customers_service.add_supply_point(
        db, organization_id=organization_id, customer_id=customer.id,
        payload=supply_point_payload, actor_user_id=customer_user_id,
    )
    if supply_point is None:
        raise SelfServiceContractError("Unable to create supply point")

    contract = await create_contract(
        db, organization_id=organization_id, customer_id=customer.id,
        supply_point_id=supply_point.id, product_version_id=product_version_id,
        producer_agent_id=producer_agent_id, actor_user_id=customer_user_id,
        correlation_id=str(uuid.uuid4()), email=email,
        created_by_role="CUSTOMER",
        # Nobody filled this in on the customer's behalf: they did it
        # themselves, so activated_by_promoter_id stays null and the admin
        # screen says "Cliente ha sottoscritto autonomamente".
        activated_by_promoter_id=None,
    )
    if substituted_for_agent_id is not None:
        # Audited, not silent: somebody other than the customer's own
        # referrer is being credited for this contract, and an accountant
        # asking "why is this Alessandro's and not Salvatore's?" deserves a
        # row that answers it rather than an inference from two statuses.
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=customer_user_id,
            action="contract.producer_substituted", entity_type="contract", entity_id=str(contract.id),
            previous_value={"producer_agent_id": str(substituted_for_agent_id)},
            new_value={"producer_agent_id": str(producer_agent_id)},
            reason="Il promoter di riferimento non è attivo: attribuito allo sponsor attivo più vicino",
        )
        await db.commit()
    contract = await transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="SUBMITTED",
        actor_user_id=customer_user_id, reason="Attivazione self-service", notes=None,
        correlation_id=str(uuid.uuid4()),
    )
    contract = await transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="DOCUMENTS_PENDING",
        actor_user_id=customer_user_id, reason=None, notes=None,
        correlation_id=str(uuid.uuid4()),
    )
    return contract


async def create_contract_for_recruited_customer(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    promoter_user_id: uuid.UUID,
    customer_id: uuid.UUID,
    product_version_id: uuid.UUID,
    supply_point_payload: "SupplyPointCreate",
    email: str,
) -> Contract:
    """The CRM-style counterpart to create_contract_self_service: a promoter
    activates a contract on behalf of one of THEIR OWN customers (who may
    have never logged in -- there is no customer_user_id requirement at
    all here, unlike the self-service path). producer_agent_id is always
    the calling promoter's own agent (promoter_user_id, never client-
    supplied -- see the router), and customer_id must actually be
    attributed to that same promoter (checked via
    _resolve_referring_agent_id_for_customer, the exact same lookup the
    self-service path uses to find ITS OWN producer) -- a promoter can
    never activate a contract for someone else's customer this way, even
    though POST /contracts (contracts.create-gated, staff-only in
    practice) technically lets an admin attribute to any agent."""
    from app.domains.customers import service as customers_service
    from app.domains.customers.models import Customer

    promoter_agent = await network_service.get_own_agent_profile(
        db, organization_id=organization_id, user_id=promoter_user_id
    )
    if promoter_agent is None or promoter_agent.status != "ACTIVE":
        raise SelfServiceContractError("Solo un promoter attivo può attivare contratti per i propri clienti.")

    customer = await db.get(Customer, customer_id)
    if customer is None or customer.organization_id != organization_id:
        raise SelfServiceContractError("Customer not found")

    resolved_agent_id = await _resolve_referring_agent_id_for_customer(
        db, organization_id=organization_id, customer_id=customer_id
    )
    if resolved_agent_id != promoter_agent.id:
        # Same walk-up as the self-service path: if the customer's own
        # referrer has been deactivated, the nearest ACTIVE sponsor above
        # them inherits the relationship -- and is therefore allowed to
        # activate a contract for them. Without this, a customer whose
        # promoter left would be unreachable from BOTH sides: they cannot
        # self-activate, and nobody can do it for them either.
        inheritor = (
            await network_service.resolve_nearest_active_agent(
                db, organization_id=organization_id, agent_id=resolved_agent_id
            )
            if resolved_agent_id is not None
            else None
        )
        if inheritor is None or inheritor.id != promoter_agent.id:
            raise SelfServiceContractError("Questo cliente non è nella tua rete.")

    version = await db.get(ProductVersion, product_version_id)
    if version is None:
        raise SelfServiceContractError("Product version not found")
    product = await db.get(Product, version.product_id)
    if product is None or product.organization_id != organization_id:
        raise SelfServiceContractError("Product version not found")
    if product.category != "INTERNAL":
        raise SelfServiceContractError(
            "Solo i prodotti Lial Energy si attivano come contratto -- gli altri prodotti si acquistano come ordine."
        )
    if not pricing.product_allows_customer_kind(product.customer_type, customer.kind):
        raise SelfServiceContractError(
            "Questo contratto non è disponibile per la tipologia di questo cliente."
        )

    supply_point = await customers_service.add_supply_point(
        db, organization_id=organization_id, customer_id=customer.id,
        payload=supply_point_payload, actor_user_id=promoter_user_id,
    )
    if supply_point is None:
        raise SelfServiceContractError("Unable to create supply point")

    contract = await create_contract(
        db, organization_id=organization_id, customer_id=customer.id,
        supply_point_id=supply_point.id, product_version_id=product_version_id,
        producer_agent_id=promoter_agent.id, actor_user_id=promoter_user_id,
        correlation_id=str(uuid.uuid4()), email=email,
        created_by_role="PROMOTER",
        # The whole point of the CRM path: the promoter completed this in
        # place of the customer, which is exactly what the admin screen
        # must be able to say.
        activated_by_promoter_id=promoter_agent.id,
    )
    contract = await transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="SUBMITTED",
        actor_user_id=promoter_user_id, reason="Attivazione da promoter per proprio cliente", notes=None,
        correlation_id=str(uuid.uuid4()),
    )
    contract = await transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="DOCUMENTS_PENDING",
        actor_user_id=promoter_user_id, reason=None, notes=None,
        correlation_id=str(uuid.uuid4()),
    )
    return contract


async def set_contract_iban(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, iban: str, actor_user_id: uuid.UUID
) -> Contract:
    """Lets a customer add/correct their own contract's IBAN after creation
    (e.g. the admin created the contract before receiving it, or the
    customer wants to switch bank accounts) -- same "editable afterwards"
    spirit as supply_points.label."""
    previous = contract.iban
    contract.iban = iban
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract.iban_updated", entity_type="contract", entity_id=str(contract.id),
        previous_value={"iban": previous}, new_value={"iban": iban},
    )
    await db.commit()
    await db.refresh(contract)
    return contract


# Transitions with no separate decision of their own -- entering the key
# status on the left always immediately continues to the value on the
# right, so a human never has to click through it as its own step. Added
# Session 29 per explicit request ("l'amministratore deve recensire il
# contratto solo nel passo finale di renderlo pagato"): APPROVED and
# PAYMENT_PENDING/PAID were real staff clicks before, now only "Approva"
# (UNDER_REVIEW -> APPROVED, which cascades on into PAYMENT_PENDING) and
# "Conferma pagamento" (PAYMENT_PENDING -> PAID, which cascades on through
# ACTIVATION_PENDING into ACTIVE) require a human. See
# business-rules.md#contract-self-service. Every hop here is still a real,
# individually-audited transition_contract() call -- this only removes the
# need for someone to manually click each one.
AUTO_CASCADE_AFTER: dict[str, str] = {
    "APPROVED": "PAYMENT_PENDING",
    "PAID": "ACTIVATION_PENDING",
    "ACTIVATION_PENDING": "ACTIVE",
}


async def transition_contract(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contract: Contract,
    to_status: str,
    actor_user_id: uuid.UUID,
    reason: str | None,
    notes: str | None,
    correlation_id: str,
) -> Contract:
    """The single entry point for every contract status change. Validates the
    transition against the explicit state machine, records history + audit, and --
    only for ACTIVE -- freezes a network snapshot and enqueues the domain event that
    triggers commission calculation. Never generates a commission for any other
    transition. Auto-cascades through AUTO_CASCADE_AFTER once the requested
    transition lands -- e.g. a single UNDER_REVIEW->APPROVED call returns a
    contract already in PAYMENT_PENDING."""
    from_status = contract.status
    assert_transition_allowed(from_status, to_status)

    if to_status == "ACTIVE":
        attribution = await db.get(ContractAttribution, contract.contract_attribution_id)
        snapshot = await network_service.create_snapshot_for_contract(
            db,
            organization_id=organization_id,
            producer_agent_id=attribution.producer_agent_id,
        )
        contract.network_snapshot_id = snapshot.id

    if to_status == "PAID" and contract.paid_at is None:
        contract.paid_at = utcnow()

    if to_status in TERM_START_STATUSES:
        now = utcnow()
        contract.activated_at = now
        product_version = await db.get(ProductVersion, contract.product_version_id)
        duration = product_version.contract_duration_months if product_version else None
        contract.expires_at = _add_months(now, duration) if duration else None

    contract.status = to_status
    db.add(
        ContractStatusHistory(
            contract_id=contract.id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            reason=reason,
            notes=notes,
            correlation_id=correlation_id,
        )
    )

    event_name = event_name_for(from_status, to_status)
    if event_name is not None:
        db.add(
            outbox_service.enqueue(
                organization_id=organization_id,
                event_type=event_name,
                payload={"contract_id": str(contract.id), "correlation_id": correlation_id},
            )
        )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract.transitioned", entity_type="contract", entity_id=str(contract.id),
        previous_value={"status": from_status}, new_value={"status": to_status},
        reason=reason, correlation_id=correlation_id,
    )
    contract.updated_at = utcnow()
    await db.commit()
    await db.refresh(contract)

    # After the commit, never before: the LialCash credit is its own
    # committed ledger entry with its own idempotency key, and it must not be
    # able to roll the status change back if anything about it fails.
    if to_status == "PAID":
        await credit_contract_cashback(
            db, organization_id=organization_id, contract=contract, actor_user_id=actor_user_id
        )

    if to_status == "ACTIVE":
        # Tells whoever brought this customer in (the one-level "segnalatori"
        # list, a separate thing from the commercial network -- see
        # friend_referrals/models.py) that they have just gone active, and
        # whether that unlocked a gift. Best-effort and after the commit: a
        # notification must never be able to fail an activation.
        from app.domains.friend_referrals import service as friend_referrals_service

        await friend_referrals_service.notify_referrer_of_activation(
            db, organization_id=organization_id, customer_id=contract.customer_id
        )

    next_status = AUTO_CASCADE_AFTER.get(contract.status)
    if next_status is not None:
        contract = await transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=next_status,
            actor_user_id=actor_user_id, reason="Automatico -- nessuna decisione separata richiesta",
            notes=None, correlation_id=correlation_id,
        )
    return contract


async def credit_contract_cashback(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, actor_user_id: uuid.UUID | None
) -> None:
    """Credits the automatic LialCash a paid Lial Energy contract earns.

    This is the "servizi Lial Energy e formazione" rule, and it is
    deliberately a DIFFERENT mechanism from the partner-invoice cashback --
    which is exactly what was asked for:

      - Partner esterni (invoice_redemptions): the customer pays Lial 5% of
        the invoice to unlock the credit. Untouched by any of this.
      - Prodotti DROPSHIPPING/PARTNER (orders): opt-in, the customer pays a
        5% surcharge on the order to earn cashback. Also untouched.
      - Servizi nostri (INTERNAL contracts): NO surcharge, nothing extra to
        pay, nothing to opt into. Paying the contract is itself what earns
        the credit, and the percentage of the gross (VAT included) that
        comes back is a per-product setting -- 0 by default, so a product
        only does this once an admin says so.

    Exactly-once is enforced twice over: `contracts.cashback_credited_at` as
    the readable guard, and a deterministic wallet idempotency key against
    the UNIQUE constraint on wallet_transactions for the case the guard is
    raced (a replayed Stripe webhook, say).

    Never raises: by the time this runs the contract is already committed as
    PAID, and a wallet problem must not undo that."""
    from app.domains.customers.models import Customer
    from app.domains.wallets import service as wallets_service

    if contract.cashback_credited_at is not None:
        return

    version = await db.get(ProductVersion, contract.product_version_id)
    if version is None:
        return
    gross = contract.gross_amount_cents
    if gross is None:
        # A contract created before the price snapshot existed. Recomputing it
        # now from today's product version would be exactly the retroactive
        # restatement the snapshot exists to prevent, so: no credit, loudly
        # skipped rather than silently guessed.
        logger.warning("Contract %s has no gross_amount_cents snapshot; skipping cashback", contract.id)
        return
    amount_cents = pricing.contract_cashback_cents(version=version, gross_amount_cents=gross)
    if amount_cents <= 0:
        return

    customer = await db.get(Customer, contract.customer_id)
    if customer is None or customer.user_id is None:
        # A customer registered by a promoter who has genuinely never had a
        # login cannot hold a wallet. Not an error -- but it must be visible,
        # because it means somebody is owed credit they cannot yet receive.
        logger.warning("Contract %s customer has no user account; LialCash not credited", contract.id)
        return

    wallet = await wallets_service.get_or_create_wallet(
        db, organization_id=organization_id, user_id=customer.user_id
    )
    try:
        await wallets_service.credit_wallet(
            db,
            organization_id=organization_id,
            wallet_id=wallet.id,
            amount_cents=amount_cents,
            type_="ADMIN_CREDIT",
            actor_user_id=actor_user_id,
            reference_contract_id=contract.id,
            source=CONTRACT_CASHBACK_SOURCE,
            note=f"Cashback contratto {str(contract.id)[:8].upper()}",
            idempotency_key=f"contract-cashback:{contract.id}",
        )
    except Exception:
        logger.exception("Contract %s: LialCash credit failed", contract.id)
        return

    contract.cashback_credited_at = utcnow()
    await db.commit()
    await db.refresh(contract)
