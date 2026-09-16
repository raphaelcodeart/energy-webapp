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
from app.domains.contracts.models import (
    Contract,
    ContractAttribution,
    ContractRequest,
    ContractStatusHistory,
)
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

#: Where a customer may pay a contract from. Business decision (Session 49):
#: payment is NOT gated on the documents being approved -- a customer can
#: fill in the data, skip the documents, and pay straight away. What stays
#: gated is activation: a contract paid early keeps its status, and only an
#: administrator approving the documents moves it on to PAID -> ACTIVE (see
#: transition_contract), which is the one point commissions are generated.
PREPAYABLE_STATUSES = frozenset(
    {"SUBMITTED", "DOCUMENTS_PENDING", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING"}
)


def is_payable(contract: Contract) -> bool:
    return (
        contract.status in PREPAYABLE_STATUSES
        and bool(contract.gross_amount_cents)
        and contract.paid_at is None
    )


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

    product_version_ids = {c.product_version_id for c in contracts if c.product_version_id is not None}
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
    supply_points: dict[uuid.UUID, SupplyPoint] = {
        sp.id: sp
        for sp in (await db.execute(select(SupplyPoint).where(SupplyPoint.id.in_(supply_point_ids)))).scalars()
    }

    def _agent_name(agent_id: uuid.UUID | None) -> str | None:
        return agent_names.get(agent_id) if agent_id is not None else None

    result = []
    for c in contracts:
        sp = supply_points.get(c.supply_point_id)
        row = {
            "id": c.id,
            "customer_id": c.customer_id,
            "supply_point_id": c.supply_point_id,
            "product_version_id": c.product_version_id,
            "status": c.status,
            "notes": c.notes,
            "iban": c.iban,
            "email": c.email,
            "holder_first_name": c.holder_first_name,
            "holder_last_name": c.holder_last_name,
            "pec": c.pec,
            "created_at": c.created_at,
            "activated_at": c.activated_at,
            "expires_at": c.expires_at,
            "product_name": product_names.get(c.product_version_id) if c.product_version_id else None,
            "supply_point_label": sp.label if sp else None,
            "pod_code": sp.pod_code if sp else None,
            "pdr_code": sp.pdr_code if sp else None,
            "energy_type": sp.energy_type if sp else None,
            "contract_request_id": c.contract_request_id,
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
            "billing_stopped_at": c.billing_stopped_at,
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
    product_version_id: uuid.UUID | None,
    producer_agent_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: str,
    contract_request_id: uuid.UUID | None = None,
    notify_staff: bool = True,
    notes: str | None = None,
    iban: str | None = None,
    email: str | None = None,
    holder_first_name: str | None = None,
    holder_last_name: str | None = None,
    pec: str | None = None,
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
    passed in -- and frozen onto the contract. See catalog/pricing.py.

    Every contract belongs to a pratica (Session 52). A caller building one
    passes `contract_request_id` (and `notify_staff=False`: the pratica
    announces itself once, when it is sent, not once per point); any other
    caller gets a pratica of one created here with the same holder data.
    `product_version_id` may be None only for a point of a pratica still
    being filled in -- the database refuses it anywhere past DRAFT."""
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
    version = await db.get(ProductVersion, product_version_id) if product_version_id is not None else None
    price = await _price_for(db, version=version, customer_kind=customer_kind)

    if contract_request_id is None:
        request = ContractRequest(
            organization_id=organization_id,
            customer_id=customer_id,
            status="DRAFT",
            holder_first_name=holder_first_name,
            holder_last_name=holder_last_name,
            email=email,
            pec=pec,
            iban=iban,
            created_by_user_id=actor_user_id,
            created_by_role=created_by_role,
            activated_by_promoter_id=activated_by_promoter_id,
        )
        db.add(request)
        await db.flush()
        contract_request_id = request.id

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
        contract_request_id=contract_request_id,
        supply_point_id=supply_point_id,
        product_version_id=product_version_id,
        contract_attribution_id=attribution.id,
        status="DRAFT",
        notes=notes,
        iban=iban,
        email=email,
        holder_first_name=holder_first_name,
        holder_last_name=holder_last_name,
        pec=pec,
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
    if notify_staff:
        await notifications_service.notify_roles(
            db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
            type_="CONTRACT_CREATED", entity_type="contract", entity_id=contract.id,
            title="Nuovo contratto creato", body=f"Contratto {contract.id} in stato Bozza.",
            exclude_user_id=actor_user_id,
        )
    await db.commit()
    await db.refresh(contract)
    return contract


async def _price_for(
    db: AsyncSession, *, version: ProductVersion | None, customer_kind: str | None
) -> pricing.PriceBreakdown | None:
    if version is None:
        return None
    product = await db.get(Product, version.product_id)
    return pricing.compute_contract_price(
        version=version, customer_kind=customer_kind,
        product_type=product.product_type if product else None,
    )


async def freeze_price(db: AsyncSession, *, contract: Contract, version: ProductVersion) -> None:
    """Sets the package of a contract that did not have one yet and freezes
    its price, exactly as create_contract would have. Only ever called on a
    DRAFT (see contracts/requests.py::set_point_product): a price is frozen
    once, when the customer commits to it, and never restated. Does not
    commit."""
    from app.domains.customers.models import Customer

    customer = await db.get(Customer, contract.customer_id)
    customer_kind = customer.kind if customer is not None else None
    price = await _price_for(db, version=version, customer_kind=customer_kind)
    contract.product_version_id = version.id
    contract.customer_kind = customer_kind
    contract.net_amount_cents = price.net_amount_cents if price else None
    contract.vat_rate = price.vat_rate if price else None
    contract.vat_amount_cents = price.vat_amount_cents if price else None
    contract.gross_amount_cents = price.gross_amount_cents if price else None
    contract.updated_at = utcnow()


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


async def resolve_self_service_producer(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID | None]:
    """Who earns the commission on a contract the customer activates
    themselves: their own referrer, or -- if that promoter is no longer
    active -- the nearest active sponsor above them. Returns the producer
    and, when a substitution happened, the referrer it replaced.

    A customer must never be stranded by something they had no part in.
    Their referring promoter can be deactivated months after they signed up,
    and create_contract() refuses to attribute a contract to a non-ACTIVE
    agent -- correctly, since a contract that activates and pays nobody is a
    real failure mode (docs/paid-contract-commission-audit.md). Business
    decision: walk UP to the nearest active sponsor rather than block, so the
    branch that built the relationship keeps it and nobody waits for an
    admin to notice. The original referrer is still recorded on the contract
    (first_referrer_agent_id), so the substitution is visible rather than
    silent."""
    referrer_agent_id = await _resolve_referring_agent_id_for_customer(
        db, organization_id=organization_id, customer_id=customer_id
    )
    if referrer_agent_id is None:
        raise SelfServiceContractError(
            "Nessun promoter di riferimento trovato per il tuo account -- contatta l'assistenza."
        )
    producer = await network_service.resolve_nearest_active_agent(
        db, organization_id=organization_id, agent_id=referrer_agent_id
    )
    if producer is None:
        raise SelfServiceContractError(
            "Il promoter che ti ha invitato non è più attivo e non risulta nessun referente attivo "
            "sopra di lui. Contatta l'assistenza: ti verrà assegnato un nuovo referente e potrai "
            "completare l'attivazione."
        )
    return producer.id, (referrer_agent_id if producer.id != referrer_agent_id else None)


async def record_producer_substitution(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, actor_user_id: uuid.UUID,
    substituted_for_agent_id: uuid.UUID,
) -> None:
    """Audited, not silent: somebody other than the customer's own referrer
    is being credited for this contract, and an accountant asking "why is
    this Alessandro's and not Salvatore's?" deserves a row that answers it
    rather than an inference from two statuses. Does not commit."""
    attribution = await db.get(ContractAttribution, contract.contract_attribution_id)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract.producer_substituted", entity_type="contract", entity_id=str(contract.id),
        previous_value={"producer_agent_id": str(substituted_for_agent_id)},
        new_value={"producer_agent_id": str(attribution.producer_agent_id) if attribution else None},
        reason="Il promoter di riferimento non è attivo: attribuito allo sponsor attivo più vicino",
    )


async def resolve_promoter_for_customer(
    db: AsyncSession, *, organization_id: uuid.UUID, promoter_user_id: uuid.UUID, customer_id: uuid.UUID
) -> AgentProfile:
    """The calling promoter's own agent, provided they may act for this
    customer: the customer was attributed to them, or to a deactivated
    promoter whose nearest active sponsor is them. Raises otherwise."""
    promoter_agent = await network_service.get_own_agent_profile(
        db, organization_id=organization_id, user_id=promoter_user_id
    )
    if promoter_agent is None or promoter_agent.status != "ACTIVE":
        raise SelfServiceContractError("Solo un promoter attivo può attivare contratti per i propri clienti.")

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
    return promoter_agent


async def create_contract_self_service(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    product_version_id: uuid.UUID,
    supply_point_payload: "SupplyPointCreate",
    email: str,
    holder_first_name: str | None = None,
    holder_last_name: str | None = None,
    pec: str | None = None,
    iban: str | None = None,
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

    producer_agent_id, substituted_for_agent_id = await resolve_self_service_producer(
        db, organization_id=organization_id, customer_id=customer.id
    )

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
        holder_first_name=holder_first_name, holder_last_name=holder_last_name, pec=pec, iban=iban,
        created_by_role="CUSTOMER",
        # Nobody filled this in on the customer's behalf: they did it
        # themselves, so activated_by_promoter_id stays null and the admin
        # screen says "Cliente ha sottoscritto autonomamente".
        activated_by_promoter_id=None,
    )
    if substituted_for_agent_id is not None:
        await record_producer_substitution(
            db, organization_id=organization_id, contract=contract, actor_user_id=customer_user_id,
            substituted_for_agent_id=substituted_for_agent_id,
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
    holder_first_name: str | None = None,
    holder_last_name: str | None = None,
    pec: str | None = None,
    iban: str | None = None,
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

    customer = await db.get(Customer, customer_id)
    if customer is None or customer.organization_id != organization_id:
        raise SelfServiceContractError("Customer not found")

    promoter_agent = await resolve_promoter_for_customer(
        db, organization_id=organization_id, promoter_user_id=promoter_user_id, customer_id=customer_id
    )

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
        holder_first_name=holder_first_name, holder_last_name=holder_last_name, pec=pec, iban=iban,
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
        # Nobody paid through Stripe: this is staff confirming a bank
        # transfer, which is always the whole amount in one go -- whatever
        # card plan the customer may have opened and abandoned before.
        contract.paid_at = utcnow()
        contract.payment_plan = "FULL"
        contract.payment_method = "BANK_TRANSFER"
    if to_status == "PAID":
        from app.domains.contracts import instalments as instalments_service

        rows = await instalments_service.ensure_schedule(db, contract=contract)
        if not any(r.status == "PAID" for r in rows):
            await instalments_service.record_payment(
                db, contract=contract, source=instalments_service.SOURCE_ADMIN, number=1,
                actor_user_id=actor_user_id,
            )

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

    if from_status == "DRAFT" and to_status == "SUBMITTED":
        # A pratica is sent once none of its points is a draft any more.
        # Sending one normally goes through contracts/requests.py::
        # submit_request, which moves every point together; this covers a
        # pratica of one moved on by staff from the contract list.
        request = await db.get(ContractRequest, contract.contract_request_id)
        if request is not None and request.status == "DRAFT":
            other_drafts = (
                await db.execute(
                    select(Contract.id).where(
                        Contract.contract_request_id == request.id,
                        Contract.id != contract.id,
                        Contract.status == "DRAFT",
                    )
                )
            ).first()
            if other_drafts is None:
                request.status = "SUBMITTED"
                request.submitted_at = utcnow()
                request.updated_at = utcnow()

    if from_status == "ACTIVATION_PENDING" and to_status == "ACTIVE":
        # Every instalment the customer has already paid releases its slice
        # of the commissions now, in this same transaction (Session 50).
        from app.domains.contracts import instalments as instalments_service

        await instalments_service.release_paid_instalments(db, contract=contract)

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
        # Tells whoever brought this customer in (the one-level "Invita un amico"
        # list, a separate thing from the commercial network -- see
        # friend_referrals/models.py) that they have just gone active, and
        # whether that unlocked a gift. Best-effort and after the commit: a
        # notification must never be able to fail an activation.
        from app.domains.friend_referrals import service as friend_referrals_service

        await friend_referrals_service.notify_referrer_of_activation(
            db, organization_id=organization_id, customer_id=contract.customer_id
        )

    if to_status == "REJECTED" and contract.paid_at is not None:
        # Payment is accepted before approval, so rejecting a contract can
        # now mean rejecting one somebody has already paid for -- and, on an
        # instalment plan, one whose card Stripe is still going to charge.
        # Refunding and cancelling are deliberate human decisions, never
        # automatic, but nobody may be left to discover them by accident.
        await notifications_service.notify_roles(
            db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
            type_="CONTRACT_PAID_REJECTED", entity_type="contract", entity_id=contract.id,
            title=f"Respinto un contratto già pagato: {str(contract.id)[:8].upper()}",
            body=(
                "Il cliente aveva già pagato. Valuta il rimborso su Stripe, il cashback LialCash "
                "accreditato e, se a rate, annulla l'abbonamento."
            ),
        )
        await db.commit()

    next_status = AUTO_CASCADE_AFTER.get(contract.status)
    if contract.status == "PAYMENT_PENDING" and contract.paid_at is not None:
        # Paid before the documents were approved: approval was the only
        # thing missing, so the contract goes straight on to PAID and, through
        # the existing cascade, ACTIVE -- commissions fire here, not at
        # payment time.
        next_status = "PAID"
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

    This function credits the WHOLE contract at once, which is right for a
    single payment (card or confirmed bank transfer). An instalment plan is
    skipped here and handled by credit_contract_instalment_cashback, as the
    administrator chose: a slice with every instalment collected (Session
    49, the default -- a customer who stops paying after the first month has
    not been handed the whole year), or the whole amount in advance at the
    first instalment (Session 59).

    Exactly-once is enforced twice over: `contracts.cashback_credited_at` as
    the readable guard, and a deterministic wallet idempotency key against
    the UNIQUE constraint on wallet_transactions for the case the guard is
    raced (a replayed Stripe webhook, say).

    Never raises: by the time this runs the contract is already committed as
    PAID, and a wallet problem must not undo that."""
    from app.domains.contracts import payment_plans

    if contract.cashback_credited_at is not None:
        return
    plan = payment_plans.plan_by_key(contract.payment_plan)
    if plan is not None and plan.instalments > 1:
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
    credited = await _credit_contract_lialcash(
        db, organization_id=organization_id, contract=contract, amount_cents=amount_cents,
        actor_user_id=actor_user_id, idempotency_key=f"contract-cashback:{contract.id}",
        note=f"Cashback contratto {str(contract.id)[:8].upper()}",
    )
    if credited:
        contract.cashback_credited_at = utcnow()
        await db.commit()
        await db.refresh(contract)


async def credit_contract_instalment_cashback(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, instalment_number: int
) -> None:
    """The LialCash one collected instalment earns, on a contract paid in 3
    or 12 instalments -- in the way the administrator chose in Impostazioni
    (organizations/service.py::get_contract_instalment_cashback_mode):

    - PER_INSTALMENT: the cashback percentage applied to that instalment, so
      the credits add up to what a single payment would have earned once
      every instalment is in;
    - UPFRONT: at the first instalment, the whole contract's cashback in one
      credit (the same amount and the same idempotency key as a single
      payment), and nothing for the instalments after it.

    The choice is read when the first instalment is paid and holds for the
    contract's whole life: a contract credited in advance is never credited
    again per instalment, whatever the setting says later -- the ledger row
    of the advance is what decides, not the setting.

    The idempotency key is the instalment NUMBER, not the Stripe invoice: the
    same month confirmed by hand by an administrator and later collected by a
    Stripe retry of the same invoice is still one month. The amount is the
    plan's own instalment, never whatever the invoice said. Never raises."""
    from app.domains.contracts import payment_plans
    from app.domains.organizations import service as organizations_service
    from app.domains.wallets.models import WalletTransaction

    plan = payment_plans.plan_by_key(contract.payment_plan)
    if plan is None or plan.instalments <= 1 or not contract.gross_amount_cents:
        return
    if contract.status in ("REJECTED", "CANCELLED"):
        return
    version = await db.get(ProductVersion, contract.product_version_id)
    if version is None:
        return
    code = str(contract.id)[:8].upper()
    upfront_key = f"contract-cashback:{contract.id}"

    if instalment_number == 1 and (
        await organizations_service.get_contract_instalment_cashback_mode(db, organization_id=organization_id)
        == organizations_service.CASHBACK_UPFRONT
    ):
        amount_cents = pricing.contract_cashback_cents(version=version, gross_amount_cents=contract.gross_amount_cents)
        idempotency_key = upfront_key
        note = f"Cashback contratto {code} (intero, anticipato alla prima rata)"
    else:
        already_in_advance = (
            await db.execute(select(WalletTransaction.id).where(WalletTransaction.idempotency_key == upfront_key))
        ).first()
        if already_in_advance is not None:
            return
        instalment_cents = payment_plans.breakdown_for(plan, contract.gross_amount_cents).instalment_cents
        amount_cents = pricing.contract_cashback_cents(version=version, gross_amount_cents=instalment_cents)
        idempotency_key = f"contract-cashback:{contract.id}:rata-{instalment_number}"
        note = f"Cashback contratto {code} (rata {instalment_number} di {plan.instalments})"

    credited = await _credit_contract_lialcash(
        db, organization_id=organization_id, contract=contract, amount_cents=amount_cents,
        actor_user_id=None, idempotency_key=idempotency_key, note=note,
    )
    if credited and contract.cashback_credited_at is None:
        # Only "a credit has started", on an instalment plan -- never read as
        # "the whole amount is in", which the ledger rows answer instead.
        contract.cashback_credited_at = utcnow()
        await db.commit()
        await db.refresh(contract)


async def _credit_contract_lialcash(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contract: Contract,
    amount_cents: int,
    actor_user_id: uuid.UUID | None,
    idempotency_key: str,
    note: str,
) -> bool:
    from app.domains.customers.models import Customer
    from app.domains.wallets import service as wallets_service

    if amount_cents <= 0:
        return False
    customer = await db.get(Customer, contract.customer_id)
    if customer is None or customer.user_id is None:
        # A customer registered by a promoter who has genuinely never had a
        # login cannot hold a wallet. Not an error -- but it must be visible,
        # because it means somebody is owed credit they cannot yet receive.
        logger.warning("Contract %s customer has no user account; LialCash not credited", contract.id)
        return False

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
            note=note,
            idempotency_key=idempotency_key,
        )
    except Exception:
        logger.exception("Contract %s: LialCash credit failed", contract.id)
        return False
    return True


# --- Pagamento del contratto (Stripe) ---------------------------------------


async def attach_stripe_checkout_session(
    db: AsyncSession, *, contract: Contract, session_id: str, plan_key: str
) -> Contract:
    """Records which Checkout Session is currently live for this contract,
    and which plan it was opened for. Overwrites any previous one, so only
    the customer's latest attempt is ever honoured by the webhook -- same
    rule as orders.

    Deliberately does NOT change the contract's status: it stays
    PAYMENT_PENDING until Stripe confirms, exactly as it would stay
    PAYMENT_PENDING waiting for an admin to confirm a bank transfer."""
    contract.stripe_checkout_session_id = session_id
    contract.payment_plan = plan_key
    contract.payment_method = "CARD"
    contract.updated_at = utcnow()
    await db.commit()
    await db.refresh(contract)
    return contract


async def attach_stripe_subscription(
    db: AsyncSession, *, contract: Contract, subscription_id: str, customer_id: str | None
) -> Contract:
    contract.stripe_subscription_id = subscription_id
    if customer_id:
        contract.stripe_customer_id = customer_id
    contract.updated_at = utcnow()
    await db.commit()
    await db.refresh(contract)
    return contract


async def has_accepted_commission_plan(db: AsyncSession, *, contract_id: uuid.UUID) -> bool:
    from app.domains.contracts.models import ContractCommissionPlan

    return (
        await db.execute(select(ContractCommissionPlan.id).where(ContractCommissionPlan.contract_id == contract_id))
    ).first() is not None


class CommissionPreviewChangedError(Exception):
    pass


async def accept_commission_plan(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, checksum: str, actor_user_id: uuid.UUID
):
    """Stores the preview the administrator accepted -- recomputed here, never
    taken from the browser, and refused if it no longer matches what they
    were shown (somebody's rank changed, the customer paid in the meantime):
    accepting figures that are not the ones on screen would make the log a
    lie. Commits."""
    from app.domains.commissions.services.preview import build_commission_preview
    from app.domains.contracts.models import ContractCommissionPlan

    preview = await build_commission_preview(db, organization_id=organization_id, contract=contract)
    if preview["checksum"] != checksum:
        raise CommissionPreviewChangedError(
            "L'anteprima delle provvigioni è cambiata da quando l'hai aperta (rete, gradi o pagamento aggiornati). "
            "Ricaricala e controllala di nuovo."
        )
    plan = ContractCommissionPlan(
        organization_id=organization_id,
        contract_id=contract.id,
        accepted_by_user_id=actor_user_id,
        accepted_at=utcnow(),
        payment_plan=preview["payment"]["plan_key"],
        total_commission_cents=preview["total_commission_cents"],
        preview=preview,
        checksum=checksum,
    )
    db.add(plan)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract.commission_preview_accepted", entity_type="contract", entity_id=str(contract.id),
        new_value={"total_commission_cents": preview["total_commission_cents"], "checksum": checksum},
    )
    await db.commit()
    return plan


async def mark_paid_via_stripe(
    db: AsyncSession, *, organization_id: uuid.UUID, stripe_checkout_session_id: str,
    stripe_invoice_id: str | None = None,
) -> Contract | None:
    """Called only from the verified Stripe webhook, for a Checkout Session
    opened on one contract by itself (the flow before pratiche, whose open
    sessions must still be honoured). The success URL is never treated as
    proof of anything -- a customer can open it by hand.

    Returns None rather than raising when no contract matches: an event for
    another organization, or for a session superseded by a newer attempt, is
    not this call's problem to solve and must not make Stripe retry forever.
    """
    contract = (
        await db.execute(
            select(Contract).where(
                Contract.organization_id == organization_id,
                Contract.stripe_checkout_session_id == stripe_checkout_session_id,
            )
        )
    ).scalar_one_or_none()
    if contract is None:
        return None
    return await record_card_payment(
        db, organization_id=organization_id, contract=contract, stripe_invoice_id=stripe_invoice_id
    )


async def record_card_payment(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contract: Contract,
    stripe_invoice_id: str | None = None,
    notify_staff: bool = True,
) -> Contract:
    """Stripe confirmed the (first) card payment of this contract.

    For an instalment plan this is the FIRST payment: the contract is in
    force from then on and the remaining instalments are collected
    automatically. `contract.payment_plan` must already say which plan was
    paid -- it decides the instalment schedule and how the LialCash is
    credited.

    `notify_staff=False` lets a pratica paying ten contracts at once say so
    in one notification instead of ten (see contracts/requests.py)."""
    from app.domains.contracts import instalments as instalments_service

    if contract.status == "PAYMENT_PENDING" and await has_accepted_commission_plan(db, contract_id=contract.id):
        await instalments_service.record_payment(
            db, contract=contract, source=instalments_service.SOURCE_STRIPE_CHECKOUT, number=1,
            invoice_id=stripe_invoice_id,
        )
        return await transition_contract(
            db, organization_id=organization_id, contract=contract, to_status="PAID",
            actor_user_id=contract.created_by_user_id or contract.customer_id,
            reason="Pagamento confermato da Stripe", notes=None, correlation_id=str(uuid.uuid4()),
        )
    if contract.paid_at is not None:
        # Already handled (a redelivery that slipped past the event guard,
        # or an admin confirming in parallel). Idempotent by design.
        return contract

    # Paid BEFORE approval -- allowed on purpose (PREPAYABLE_STATUSES). The
    # payment is recorded and the LialCash credited now, because the
    # customer has paid now; the status is left exactly where it is, because
    # nobody has approved the documents yet. Approval later finds paid_at set
    # and carries the contract straight through PAID to ACTIVE.
    #
    # A contract that is no longer activatable at all (rejected while the
    # customer sat on the Stripe page) still gets its payment recorded --
    # the money did move -- but earns no credit, and staff are told to refund.
    #
    # Also the path for a contract already approved (PAYMENT_PENDING) whose
    # commission preview nobody has accepted yet -- one approved before the
    # preview existed. It waits for an administrator to accept it, exactly
    # like a contract whose documents are not approved yet.
    contract.paid_at = utcnow()
    contract.updated_at = utcnow()
    code = str(contract.id)[:8].upper()
    accepted = contract.status in PREPAYABLE_STATUSES
    if accepted:
        await instalments_service.record_payment(
            db, contract=contract, source=instalments_service.SOURCE_STRIPE_CHECKOUT, number=1,
            invoice_id=stripe_invoice_id,
        )
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=None,
        action="contract.paid_before_approval" if accepted else "contract.paid_while_not_activatable",
        entity_type="contract", entity_id=str(contract.id),
        new_value={"status": contract.status, "payment_plan": contract.payment_plan},
        reason="Pagamento confermato da Stripe",
    )
    if notify_staff or not accepted:
        await notifications_service.notify_roles(
            db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
            type_="CONTRACT_PAID_BEFORE_APPROVAL" if accepted else "CONTRACT_PAID_REJECTED",
            entity_type="contract", entity_id=contract.id,
            title=f"Contratto {code} pagato" + ("" if accepted else " dopo essere stato chiuso"),
            body=(
                "Il cliente ha già pagato: il contratto si attiva appena approvi i documenti e accetti l'anteprima provvigioni."
                if accepted
                else "Il contratto non è più attivabile: valuta il rimborso su Stripe e interrompi gli addebiti di questo contratto."
            ),
        )
    await db.commit()
    await db.refresh(contract)
    if accepted:
        await credit_contract_cashback(
            db, organization_id=organization_id, contract=contract, actor_user_id=None
        )
    return contract


async def record_subscription_invoice(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    subscription_id: str,
    paid: bool,
    amount_cents: int,
    invoice_id: str | None = None,
    billing_reason: str | None = None,
    lines: list[tuple[str, int]] | None = None,
) -> str:
    """One monthly invoice of a subscription succeeded or failed.

    A subscription belongs either to one contract (paid on its own) or to a
    pratica, where it carries one line per contract (Session 52): then each
    `(subscription_item_id, amount_cents)` in `lines` is that contract's
    instalment, and each contract records its own month -- its own cashback,
    its own slice of commissions -- exactly as if it had been paid alone.

    Nothing about any contract's status changes: a single failed monthly
    charge is not grounds for automatically suspending somebody's energy
    contract -- that is a decision for a human with the context. What this
    does is make sure a human finds out, on both sides.
    """
    contracts = list(
        (
            await db.execute(
                select(Contract).where(
                    Contract.organization_id == organization_id,
                    Contract.stripe_subscription_id == subscription_id,
                )
            )
        ).scalars()
    )
    if not contracts:
        return "nessun contratto per questo abbonamento"

    if len(contracts) == 1 and contracts[0].stripe_subscription_item_id is None:
        targets = [(contracts[0], amount_cents)]
    else:
        by_item = {c.stripe_subscription_item_id: c for c in contracts if c.stripe_subscription_item_id}
        targets = [(by_item[item_id], cents) for item_id, cents in (lines or []) if item_id in by_item]
        if not targets:
            return "nessuna riga della fattura corrisponde a un contratto"

    from app.domains.contracts import instalments as instalments_service

    codes = ", ".join(str(c.id)[:8].upper() for c, _ in targets)
    # The first instalment is recorded by the checkout handler, which is
    # guaranteed to run for it; its invoice.paid (billing_reason
    # "subscription_create") may or may not find the contracts yet, so it
    # must not be the one that records. Every later month is recorded here,
    # keyed by the invoice.
    is_later_month = bool(invoice_id) and billing_reason != "subscription_create"

    if paid:
        for contract, cents in targets:
            if is_later_month and contract.status not in ("REJECTED", "CANCELLED"):
                # The same month's slice of the commissions: released at once
                # on an active contract, held until activation otherwise.
                row = await instalments_service.record_payment(
                    db, contract=contract, source=instalments_service.SOURCE_STRIPE_INVOICE, invoice_id=invoice_id,
                )
                if row is not None:
                    await db.commit()
                    await credit_contract_instalment_cashback(
                        db, organization_id=organization_id, contract=contract, instalment_number=row.number
                    )
            await audit_service.record(
                db, organization_id=organization_id, actor_user_id=None,
                action="contract.instalment_paid", entity_type="contract", entity_id=str(contract.id),
                new_value={"amount_cents": cents, "subscription_id": subscription_id, "invoice_id": invoice_id},
            )
        await db.commit()
        return f"rata incassata per {'il contratto' if len(targets) == 1 else 'i contratti'} {codes}"

    for contract, cents in targets:
        if is_later_month:
            await instalments_service.record_failure(db, contract=contract, invoice_id=invoice_id)
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=None,
            action="contract.instalment_failed", entity_type="contract", entity_id=str(contract.id),
            new_value={"amount_cents": cents, "subscription_id": subscription_id, "invoice_id": invoice_id},
            reason="Addebito della rata non riuscito",
        )
    first = targets[0][0]
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CONTRACT_INSTALMENT_FAILED", entity_type="contract", entity_id=first.id,
        title=(
            f"Rata non riscossa: contratto {codes}"
            if len(targets) == 1
            else f"Rata non riscossa: {len(targets)} contratti della pratica {str(first.contract_request_id)[:8].upper()}"
        ),
        body=(
            "L'addebito mensile non è andato a buon fine: le provvigioni di questa rata restano ferme. "
            "Se il cliente paga in altro modo, confermala a mano dal registro provvigioni del contratto."
        ),
    )
    customer_user_id = await _customer_user_id_for(db, contract=first)
    if customer_user_id is not None:
        await notifications_service.notify_user(
            db, organization_id=organization_id, user_id=customer_user_id,
            type_="CONTRACT_INSTALMENT_FAILED", entity_type="contract", entity_id=first.id,
            title="Rata del contratto non addebitata",
            body="Non siamo riusciti ad addebitare la rata mensile. Controlla la tua carta: riproveremo a breve.",
        )
    await db.commit()
    return f"rata NON riscossa per {'il contratto' if len(targets) == 1 else 'i contratti'} {codes}"


async def _customer_user_id_for(db: AsyncSession, *, contract: Contract) -> uuid.UUID | None:
    from app.domains.customers.models import Customer

    customer = await db.get(Customer, contract.customer_id)
    return customer.user_id if customer is not None else None
