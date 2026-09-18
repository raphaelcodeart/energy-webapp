"""La pratica di attivazione: più punti di fornitura, un contratto per punto,
un pagamento solo.

Business rule (Session 52), as the business put it: a customer with ten POD
is ten contracts -- ten for the customer, ten for the promoter, each with its
own package, its own approval, its own instalments and its own commissions --
but the customer fills in who they are once, uploads their identity once,
chooses a package for each point, and pays once.

The flow a pratica follows (reshaped in Session 53, as the business asked):

1. Everything once, at the start: holder (nome, cognome, email, PEC, IBAN),
   supply address, and "quanti POD hai?". The pratica is created DRAFT with
   that many points already there -- each a real DRAFT contract with its own
   supply point, so a half-finished pratica survives a closed browser. No
   POD/PDR code is asked.
2. Shared documents (identity, fiscal code...), once, on the pratica.
3. For each POD, the contract to activate. The package decides whether the
   point is luce or gas, and its price is frozen on the contract then.
4. Submit: every point leaves DRAFT together and enters the ordinary review
   flow. From here on each contract lives its own life.
5. Payment (customer only): one Checkout Session for every payable contract
   in the pratica -- one line each, or one subscription with one item each.
   See payments/service.py::create_checkout_session_for_request.

Nothing here computes a commission or activates anything: that stays where
it has always been, in contracts/service.py::transition_contract, one
contract at a time.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.catalog import pricing
from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts import payment_plans
from app.domains.contracts import service as contract_service
from app.domains.contracts.models import (
    Contract,
    ContractInstalment,
    ContractRequest,
    ContractRequestCheckout,
)
from app.domains.customers.models import Address, Company, Customer, CustomerProfile, SupplyPoint
from app.domains.network.models import AgentProfile
from app.domains.notifications import service as notifications_service

#: A condominium can have dozens of meters; beyond this it is a job for the
#: back office, not a web form.
MAX_POINTS_PER_REQUEST = 50

#: Stripe's own ceiling on the items of one subscription. An instalment plan
#: puts one item per contract, so a pratica with more payable contracts than
#: this can only be paid in one go (or split into two pratiche).
MAX_SUBSCRIPTION_LINES = 20


class ContractRequestError(Exception):
    pass


@dataclass(frozen=True)
class AddressData:
    street: str
    city: str
    province: str
    postal_code: str


@dataclass(frozen=True)
class HolderData:
    first_name: str
    last_name: str
    email: str
    pec: str | None
    iban: str | None
    address: AddressData


def _code(request: ContractRequest | Contract) -> str:
    return str(request.id)[:8].upper()


def _request_address(request: ContractRequest) -> AddressData | None:
    if not (request.street and request.city and request.province and request.postal_code):
        return None
    return AddressData(
        street=request.street, city=request.city, province=request.province, postal_code=request.postal_code
    )


def _point_label(energy_type: str | None, address: Address) -> str:
    from app.domains.customers.service import ENERGY_TYPE_LABELS

    kind = ENERGY_TYPE_LABELS.get(energy_type or "", "Punto di fornitura")
    return f"{kind} - {address.street}, {address.city}"


async def _customer_name(db: AsyncSession, customer: Customer | None) -> str:
    if customer is None:
        return "Cliente"
    from app.domains.customers.service import display_name_for

    profile = await db.get(CustomerProfile, customer.id)
    company = await db.get(Company, customer.id)
    return display_name_for(customer.kind, profile, company)


def _assert_draft(request: ContractRequest) -> None:
    if request.status != "DRAFT":
        raise ContractRequestError(
            "La pratica è già stata inviata: i POD e i contratti scelti non si possono più modificare. "
            "Per aggiungere un altro POD apri una nuova pratica."
        )


async def list_points(db: AsyncSession, *, request: ContractRequest, include_cancelled: bool = False) -> list[Contract]:
    stmt = select(Contract).where(Contract.contract_request_id == request.id).order_by(Contract.created_at)
    if not include_cancelled:
        # A point removed from a draft is CANCELLED without ever having been
        # sent -- it is not part of the pratica any more. A contract
        # cancelled after activation still is, so only drafts are hidden.
        stmt = stmt.where(~((Contract.status == "CANCELLED") & (Contract.activated_at.is_(None))))
    return list((await db.execute(stmt)).scalars())


# --- Creazione e dati intestatario --------------------------------------------


async def create_request(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    holder: HolderData,
    actor_user_id: uuid.UUID,
    actor_role: str,
    promoter_agent_id: uuid.UUID | None,
    points_count: int = 1,
    product_version_id: uuid.UUID | None = None,
) -> ContractRequest:
    """Opens a DRAFT pratica with its holder, its address and -- answering
    "quanti POD hai?" -- that many points already created, each a DRAFT
    contract waiting for its package. `product_version_id` (the customer
    started from a package in the catalog) pre-chooses it for every point.

    For a customer acting alone, their referrer is resolved first: a customer
    whose promoter has left with nobody active above must be told before
    filling anything in, not after. Commits."""
    if promoter_agent_id is None:
        try:
            await contract_service.resolve_self_service_producer(
                db, organization_id=organization_id, customer_id=customer_id
            )
        except contract_service.SelfServiceContractError as exc:
            raise ContractRequestError(str(exc)) from exc

    request = ContractRequest(
        organization_id=organization_id,
        customer_id=customer_id,
        status="DRAFT",
        holder_first_name=holder.first_name,
        holder_last_name=holder.last_name,
        email=holder.email,
        pec=holder.pec,
        iban=holder.iban,
        street=holder.address.street,
        city=holder.address.city,
        province=holder.address.province,
        postal_code=holder.address.postal_code,
        created_by_user_id=actor_user_id,
        created_by_role=actor_role,
        activated_by_promoter_id=promoter_agent_id,
        updated_at=utcnow(),
    )
    db.add(request)
    await db.flush()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract_request.created", entity_type="contract_request", entity_id=str(request.id),
        new_value={"customer_id": str(customer_id), "created_by_role": actor_role, "points": points_count},
    )
    await db.commit()
    await db.refresh(request)
    await set_points_count(db, request=request, count=points_count, actor_user_id=actor_user_id)
    if product_version_id is not None:
        await set_product_for_all(
            db, request=request, product_version_id=product_version_id, actor_user_id=actor_user_id
        )
    await db.refresh(request)
    return request


async def update_holder(
    db: AsyncSession, *, request: ContractRequest, holder: HolderData, actor_user_id: uuid.UUID
) -> ContractRequest:
    """Holder data and address can change while the pratica is a draft, and
    every point follows -- except a point that was deliberately moved to an
    address of its own, which keeps it. Commits."""
    _assert_draft(request)
    previous_address = _request_address(request)
    request.holder_first_name = holder.first_name
    request.holder_last_name = holder.last_name
    request.email = holder.email
    request.pec = holder.pec
    request.iban = holder.iban
    request.street = holder.address.street
    request.city = holder.address.city
    request.province = holder.address.province
    request.postal_code = holder.address.postal_code
    request.updated_at = utcnow()
    for contract in await list_points(db, request=request):
        contract.holder_first_name = holder.first_name
        contract.holder_last_name = holder.last_name
        contract.email = holder.email
        contract.pec = holder.pec
        contract.iban = holder.iban
        contract.updated_at = utcnow()
        supply_point = await db.get(SupplyPoint, contract.supply_point_id)
        address = await db.get(Address, supply_point.supply_address_id) if supply_point else None
        if address is not None and (
            previous_address is None
            or (address.street, address.city, address.province, address.postal_code)
            == (previous_address.street, previous_address.city, previous_address.province, previous_address.postal_code)
        ):
            _apply_address(address, holder.address)
            supply_point.label = _point_label(supply_point.energy_type, address)
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.holder_updated", entity_type="contract_request", entity_id=str(request.id),
    )
    await db.commit()
    await db.refresh(request)
    return request


def _apply_address(address: Address, data: AddressData) -> None:
    address.street = data.street.strip()
    address.city = data.city.strip()
    address.province = data.province.strip().upper()
    address.postal_code = data.postal_code.strip()


# --- I POD della pratica ------------------------------------------------------


async def _producer_for_new_point(
    db: AsyncSession, *, request: ContractRequest
) -> tuple[uuid.UUID, uuid.UUID | None]:
    """Resolved per point, at the moment it is added, with the same rules as
    a single contract: the promoter filling it in, or the customer's own
    referrer -- in both cases walking up to the nearest active sponsor if that
    person is no longer active, and saying so in the audit log."""
    from app.domains.network import service as network_service

    if request.activated_by_promoter_id is not None:
        promoter = await db.get(AgentProfile, request.activated_by_promoter_id)
        if promoter is not None and promoter.status == "ACTIVE":
            return promoter.id, None
        nearest = await network_service.resolve_nearest_active_agent(
            db, organization_id=request.organization_id, agent_id=request.activated_by_promoter_id
        )
        if nearest is None:
            raise ContractRequestError(
                "Il promoter che ha aperto questa pratica non è più attivo e non c'è un referente attivo sopra di lui. "
                "Contatta l'assistenza."
            )
        return nearest.id, request.activated_by_promoter_id
    try:
        return await contract_service.resolve_self_service_producer(
            db, organization_id=request.organization_id, customer_id=request.customer_id
        )
    except contract_service.SelfServiceContractError as exc:
        raise ContractRequestError(str(exc)) from exc


async def _load_package(db: AsyncSession, *, request: ContractRequest, product_version_id: uuid.UUID) -> tuple[ProductVersion, Product]:
    version = await db.get(ProductVersion, product_version_id)
    product = await db.get(Product, version.product_id) if version is not None else None
    if version is None or product is None or product.organization_id != request.organization_id:
        raise ContractRequestError("Contratto non trovato nel catalogo.")
    if product.category != "INTERNAL":
        raise ContractRequestError(
            "Solo i contratti Lial Energy si attivano da qui -- gli altri prodotti si acquistano nello Shop."
        )
    if product.status != "ACTIVE" or version.status != "ACTIVE":
        raise ContractRequestError(f"Il contratto “{version.name}” non è più disponibile.")
    customer = await db.get(Customer, request.customer_id)
    if not pricing.product_allows_customer_kind(product.customer_type, customer.kind if customer else None):
        raise ContractRequestError(
            f"Il contratto “{version.name}” non è disponibile per la tipologia di questo cliente."
        )
    return version, product


async def add_point(db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID) -> Contract:
    """One more POD in a draft pratica: a supply point at the pratica's
    address, and a DRAFT contract for it with no package yet. Commits."""
    from app.domains.customers.models import SupplyPoint as SupplyPointModel

    _assert_draft(request)
    address_data = _request_address(request)
    if address_data is None:
        raise ContractRequestError("Inserisci l'indirizzo di fornitura prima di aggiungere i POD.")
    if len(await list_points(db, request=request)) >= MAX_POINTS_PER_REQUEST:
        raise ContractRequestError(
            f"Una pratica può contenere al massimo {MAX_POINTS_PER_REQUEST} POD: per gli altri apri una seconda pratica."
        )
    producer_agent_id, substituted_for = await _producer_for_new_point(db, request=request)

    address = Address(organization_id=request.organization_id, customer_id=request.customer_id, kind="SUPPLY",
                      street="", city="", province="", postal_code="")
    _apply_address(address, address_data)
    db.add(address)
    await db.flush()
    supply_point = SupplyPointModel(
        organization_id=request.organization_id,
        customer_id=request.customer_id,
        energy_type=None,
        supply_address_id=address.id,
        label=_point_label(None, address),
    )
    db.add(supply_point)
    await db.flush()

    try:
        contract = await contract_service.create_contract(
            db, organization_id=request.organization_id, customer_id=request.customer_id,
            supply_point_id=supply_point.id, product_version_id=None,
            producer_agent_id=producer_agent_id, actor_user_id=actor_user_id,
            correlation_id=str(uuid.uuid4()), contract_request_id=request.id, notify_staff=False,
            email=request.email, holder_first_name=request.holder_first_name,
            holder_last_name=request.holder_last_name, pec=request.pec, iban=request.iban,
            created_by_role=request.created_by_role, activated_by_promoter_id=request.activated_by_promoter_id,
        )
    except contract_service.InvalidProducerAgentError as exc:
        raise ContractRequestError(str(exc)) from exc
    if substituted_for is not None:
        await contract_service.record_producer_substitution(
            db, organization_id=request.organization_id, contract=contract, actor_user_id=actor_user_id,
            substituted_for_agent_id=substituted_for,
        )
    request.updated_at = utcnow()
    await db.commit()
    await db.refresh(contract)
    return contract


async def set_points_count(
    db: AsyncSession, *, request: ContractRequest, count: int, actor_user_id: uuid.UUID
) -> list[Contract]:
    """"Quanti POD hai?": adds or removes points until the pratica has
    exactly `count`. Removing takes the most recent points first, and among
    them the ones without a contract chosen -- never the work already done
    when there is an empty point to drop instead. Commits."""
    _assert_draft(request)
    if count < 1:
        raise ContractRequestError("Una pratica deve avere almeno un POD.")
    if count > MAX_POINTS_PER_REQUEST:
        raise ContractRequestError(
            f"Una pratica può contenere al massimo {MAX_POINTS_PER_REQUEST} POD: per gli altri apri una seconda pratica."
        )
    points = await list_points(db, request=request)
    while len(points) < count:
        points.append(await add_point(db, request=request, actor_user_id=actor_user_id))
    if len(points) > count:
        drafts = [p for p in points if p.status == "DRAFT"]
        # Empty ones first, newest first within each group.
        removable = sorted(drafts, key=lambda p: (p.product_version_id is not None, -p.created_at.timestamp()))
        for contract in removable[: len(points) - count]:
            await remove_point(db, request=request, contract=contract, actor_user_id=actor_user_id)
        points = await list_points(db, request=request)
    return points


async def get_point(db: AsyncSession, *, request: ContractRequest, contract_id: uuid.UUID) -> Contract:
    contract = await db.get(Contract, contract_id)
    if contract is None or contract.contract_request_id != request.id:
        raise ContractRequestError("POD non trovato in questa pratica.")
    return contract


async def update_point_address(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, address_data: AddressData,
    actor_user_id: uuid.UUID,
) -> Contract:
    """Moves one POD to an address other than the pratica's -- the second
    home, the shop downstairs. Commits."""
    _assert_draft(request)
    if contract.status != "DRAFT":
        raise ContractRequestError("Questo POD non si può più modificare.")
    supply_point = await db.get(SupplyPoint, contract.supply_point_id)
    address = await db.get(Address, supply_point.supply_address_id) if supply_point else None
    if supply_point is None or address is None:
        raise ContractRequestError("Punto di fornitura non trovato.")
    previous = {"street": address.street, "city": address.city}
    _apply_address(address, address_data)
    supply_point.label = _point_label(supply_point.energy_type, address)
    contract.updated_at = request.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.point_address_updated", entity_type="contract", entity_id=str(contract.id),
        previous_value=previous, new_value={"street": address.street, "city": address.city},
    )
    await db.commit()
    await db.refresh(contract)
    return contract


async def remove_point(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, actor_user_id: uuid.UUID
) -> None:
    """Takes a POD out of a draft pratica. The contract is CANCELLED, not
    deleted: its creation is already in the audit trail and the history
    should say what became of it. The last POD cannot go."""
    _assert_draft(request)
    if contract.status != "DRAFT":
        raise ContractRequestError("Questo POD non si può più togliere dalla pratica.")
    if len(await list_points(db, request=request)) <= 1:
        raise ContractRequestError("Una pratica deve avere almeno un POD.")
    await contract_service.transition_contract(
        db, organization_id=request.organization_id, contract=contract, to_status="CANCELLED",
        actor_user_id=actor_user_id, reason="POD tolto dalla pratica prima dell'invio", notes=None,
        correlation_id=str(uuid.uuid4()),
    )
    request.updated_at = utcnow()
    await db.commit()


async def _assign_package(db: AsyncSession, *, contract: Contract, version: ProductVersion, product: Product) -> None:
    """The package decides what the point is: a luce contract makes it a luce
    point, a gas contract a gas point. Freezes the price. Does not commit."""
    supply_point = await db.get(SupplyPoint, contract.supply_point_id)
    if supply_point is not None:
        supply_point.energy_type = product.energy_type
        address = await db.get(Address, supply_point.supply_address_id)
        if address is not None:
            supply_point.label = _point_label(product.energy_type, address)
    await contract_service.freeze_price(db, contract=contract, version=version)


async def set_point_product(
    db: AsyncSession, *, request: ContractRequest, contract: Contract, product_version_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Contract:
    """Chooses (or changes) the contract to activate on one POD. Commits."""
    _assert_draft(request)
    if contract.status != "DRAFT":
        raise ContractRequestError("Il contratto di questo POD non si può più cambiare.")
    version, product = await _load_package(db, request=request, product_version_id=product_version_id)
    previous = str(contract.product_version_id) if contract.product_version_id else None
    await _assign_package(db, contract=contract, version=version, product=product)
    request.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract.package_selected", entity_type="contract", entity_id=str(contract.id),
        previous_value={"product_version_id": previous},
        new_value={"product_version_id": str(version.id), "gross_amount_cents": contract.gross_amount_cents},
    )
    await db.commit()
    await db.refresh(contract)
    return contract


async def set_product_for_all(
    db: AsyncSession, *, request: ContractRequest, product_version_id: uuid.UUID, actor_user_id: uuid.UUID
) -> int:
    """"Stesso contratto per tutti i POD". Returns how many received it.
    Commits."""
    _assert_draft(request)
    version, product = await _load_package(db, request=request, product_version_id=product_version_id)
    applied = 0
    for contract in await list_points(db, request=request):
        if contract.status != "DRAFT":
            continue
        await _assign_package(db, contract=contract, version=version, product=product)
        applied += 1
    request.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.package_applied_to_all", entity_type="contract_request",
        entity_id=str(request.id), new_value={"product_version_id": str(version.id), "points": applied},
    )
    await db.commit()
    return applied


# --- Invio e annullamento ----------------------------------------------------


async def submit_request(db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID) -> ContractRequest:
    """Sends the pratica: every point leaves DRAFT together, and each one
    goes on through the same flow a single contract always has --
    DOCUMENTS_PENDING, then UNDER_REVIEW by itself as soon as its required
    documents (its own, or the pratica's) are all in.

    Staff hear about it once, as a pratica, not once per point."""
    from app.domains.customers.models import Customer
    from app.domains.documents import service as documents_service

    _assert_draft(request)
    points = await list_points(db, request=request)
    if not points:
        raise ContractRequestError("Aggiungi almeno un punto di fornitura prima di inviare la pratica.")
    missing = [p for p in points if p.product_version_id is None]
    if missing:
        raise ContractRequestError(
            f"Scegli il contratto da attivare per {'il POD' if len(missing) == 1 else f'i {len(missing)} POD'} "
            "ancora senza, poi invia la pratica."
        )
    if not (request.holder_first_name and request.holder_last_name and request.email and _request_address(request)):
        raise ContractRequestError("Completa i dati dell'intestatario e l'indirizzo prima di inviare la pratica.")

    for contract in points:
        if contract.status != "DRAFT":
            continue
        contract = await contract_service.transition_contract(
            db, organization_id=request.organization_id, contract=contract, to_status="SUBMITTED",
            actor_user_id=actor_user_id, reason=f"Pratica {_code(request)} inviata", notes=None,
            correlation_id=str(uuid.uuid4()),
        )
        contract = await contract_service.transition_contract(
            db, organization_id=request.organization_id, contract=contract, to_status="DOCUMENTS_PENDING",
            actor_user_id=actor_user_id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
        )
        await documents_service.maybe_advance_to_under_review(
            db, organization_id=request.organization_id, contract_id=contract.id, actor_user_id=actor_user_id
        )

    await db.refresh(request)
    if request.status == "DRAFT":
        # transition_contract promotes the pratica when its last draft
        # leaves; reaching here means it had no draft left to move.
        request.status = "SUBMITTED"
        request.submitted_at = utcnow()
    customer = await db.get(Customer, request.customer_id)
    name = await _customer_name(db, customer)
    await notifications_service.notify_roles(
        db, organization_id=request.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CONTRACT_CREATED", entity_type="contract_request", entity_id=request.id,
        title=f"Nuova pratica {_code(request)}: {len(points)} POD",
        body=f"{name} ha inviato una pratica di attivazione con {len(points)} contratt{'o' if len(points) == 1 else 'i'}.",
        exclude_user_id=actor_user_id,
    )
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.submitted", entity_type="contract_request", entity_id=str(request.id),
        new_value={"points": len(points)},
    )
    # Filled in FOR the customer -- by their promoter, or by the
    # administration (Session 66): either way the customer is the one who
    # pays, so they are told it is waiting for them.
    filled_in_for_customer = request.created_by_role in ("PROMOTER", "ADMIN") and customer is not None
    promoter_name = None
    if filled_in_for_customer:
        if request.activated_by_promoter_id is not None:
            promoter = await db.get(AgentProfile, request.activated_by_promoter_id)
            promoter_name = promoter.display_name if promoter else None
        who = promoter_name or ("Il tuo promoter" if request.created_by_role == "PROMOTER" else "Lial Energy")
        if customer.user_id is not None:
            await notifications_service.notify_user(
                db, organization_id=request.organization_id, user_id=customer.user_id,
                type_="CONTRACT_CREATED", entity_type="contract_request", entity_id=request.id,
                title="I tuoi contratti sono pronti da pagare",
                body=(
                    f"{who} ha compilato per te la pratica {_code(request)} con "
                    f"{len(points)} POD. Controllala in “I miei Contratti” e procedi con il pagamento."
                ),
            )
    await db.commit()
    await db.refresh(request)
    if filled_in_for_customer:
        _email_customer_about_promoter_pratica(
            request=request, customer=customer,
            promoter_name=promoter_name or (None if request.created_by_role == "PROMOTER" else "Lial Energy"),
            points=points,
        )
    return request


def _email_customer_about_promoter_pratica(
    *, request: ContractRequest, customer: Customer, promoter_name: str | None, points: list[Contract]
) -> None:
    """Somebody filled the pratica in for the customer -- their promoter
    (Session 55) or the administration (Session 66): the customer is the one
    who pays, so they have to find out it is waiting. Best-effort and after
    the commit -- the pratica is sent either way."""
    import html

    from app.core.config import get_settings
    from app.core.email import send_html_email_best_effort
    from app.core.email_templates import render_email

    to = request.email or customer.email
    if not to:
        return
    who = html.escape(promoter_name or "Il tuo promoter")
    heading_who = "Il tuo promoter ha preparato i tuoi contratti" if promoter_name != "Lial Energy" else "Abbiamo preparato i tuoi contratti"
    total = sum(int(p.gross_amount_cents or 0) for p in points)
    body_html = (
        f"<p>{who} ha preparato per te la pratica <strong>{_code(request)}</strong> con "
        f"<strong>{len(points)} POD</strong>, per un totale di <strong>{total / 100:.2f} €</strong>.</p>"
        "<p>Ogni POD è un contratto a sé. Accedi alla tua area, controlla i contratti in "
        "<em>I miei Contratti</em> e completa il pagamento: puoi pagare in un'unica soluzione o a rate. "
        "Se non hai ancora impostato la password, usa il link di invito che ti è arrivato.</p>"
    )
    send_html_email_best_effort(
        context=f"Promoter pratica email (request={request.id})",
        to=to,
        subject="I tuoi contratti Lial Energy sono pronti - Lial Energy",
        html_body=render_email(
            preheader=heading_who,
            heading="I tuoi contratti sono pronti",
            body_html=body_html,
            cta_label="Vai ai miei contratti",
            cta_url=f"{get_settings().public_app_base_url}/customer?tab=contracts",
        ),
        text_body=(
            f"{promoter_name or 'Il tuo promoter'} ha preparato per te la pratica {_code(request)} con "
            f"{len(points)} POD. Accedi a I miei Contratti per controllarla e pagare."
        ),
    )


async def cancel_request(db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID) -> ContractRequest:
    """Abandons a draft pratica and its draft points. A sent pratica is not
    cancelled as a whole: each of its contracts is handled on its own."""
    _assert_draft(request)
    for contract in await list_points(db, request=request):
        if contract.status == "DRAFT":
            await contract_service.transition_contract(
                db, organization_id=request.organization_id, contract=contract, to_status="CANCELLED",
                actor_user_id=actor_user_id, reason="Pratica annullata prima dell'invio", notes=None,
                correlation_id=str(uuid.uuid4()),
            )
    request.status = "CANCELLED"
    request.cancelled_at = request.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.cancelled", entity_type="contract_request", entity_id=str(request.id),
    )
    await db.commit()
    await db.refresh(request)
    return request


# --- Pagamento ---------------------------------------------------------------


def payable_points(points: list[Contract]) -> list[Contract]:
    return [c for c in points if contract_service.is_payable(c)]


@dataclass(frozen=True)
class RequestPlanOption:
    plan: payment_plans.PaymentPlan
    instalment_cents: int
    total_cents: int
    rounding_difference_cents: int
    available: bool
    unavailable_reason: str | None
    #: Session 64: the price before the one-go discount, and the discount.
    list_total_cents: int = 0
    discount_percentage: int = 0
    discount_cents: int = 0


def plan_options(points: list[Contract], *, discount_percentage: int = 0) -> list[RequestPlanOption]:
    """Every plan, priced for these contracts: each contract split on its own
    (exactly the instalment its own schedule will record), then added up. The
    customer sees one monthly figure; each contract still owns its line."""
    options = []
    for plan in payment_plans.PAYMENT_PLANS:
        breakdowns = [
            payment_plans.breakdown_for(plan, int(c.gross_amount_cents or 0), discount_percentage=discount_percentage)
            for c in points
        ]
        reason = None
        if any(b.instalment_cents <= 0 for b in breakdowns):
            reason = "Importo troppo basso per questa modalità."
        elif plan.instalments > 1 and len(points) > MAX_SUBSCRIPTION_LINES:
            reason = (
                f"A rate si possono pagare al massimo {MAX_SUBSCRIPTION_LINES} contratti insieme: "
                "scegli la soluzione unica oppure dividi i punti in due pratiche."
            )
        options.append(
            RequestPlanOption(
                plan=plan,
                instalment_cents=sum(b.instalment_cents for b in breakdowns),
                total_cents=sum(b.total_cents for b in breakdowns),
                rounding_difference_cents=sum(b.rounding_difference_cents for b in breakdowns),
                available=bool(points) and reason is None,
                unavailable_reason=reason,
                list_total_cents=sum(int(c.gross_amount_cents or 0) for c in points),
                discount_percentage=discount_percentage if any(b.discount_cents for b in breakdowns) else 0,
                discount_cents=sum(b.discount_cents for b in breakdowns),
            )
        )
    return options


async def cashback_total_cents(db: AsyncSession, *, points: list[Contract], discount_percentage: int = 0) -> int:
    """LialCash these contracts earn; with `discount_percentage`, when paid in
    one go at that discount (the cashback follows what is paid)."""
    total = 0
    for contract in points:
        if contract.product_version_id is None or not contract.gross_amount_cents:
            continue
        version = await db.get(ProductVersion, contract.product_version_id)
        if version is not None:
            gross = int(contract.gross_amount_cents)
            paid = gross - payment_plans.discount_cents_for(gross, discount_percentage)
            total += pricing.contract_cashback_cents(version=version, gross_amount_cents=paid)
    return total


async def apply_checkout(
    db: AsyncSession,
    *,
    checkout: ContractRequestCheckout,
    stripe_invoice_id: str | None,
    stripe_subscription_id: str | None,
    stripe_customer_id: str | None,
    subscription_items: dict[str, str],
) -> str:
    """A Checkout Session of a pratica completed: every contract it covered
    is paid, each exactly as if it had been paid on its own -- its own first
    instalment, its own LialCash, its own activation if already approved.

    `subscription_items` maps contract id -> Stripe subscription item id, for
    an instalment plan: it is what lets each later monthly invoice line find
    its contract (contracts/service.py::record_subscription_invoice).

    A contract already paid by another session (the customer paid twice, in
    two tabs) is not paid again: staff are told to refund that line. Returns
    what happened, in words. Commits."""
    from app.domains.contracts import service as contracts_service

    if checkout.completed_at is not None:
        return f"pratica {str(checkout.contract_request_id)[:8].upper()}: pagamento già registrato"

    plan = payment_plans.plan_by_key(checkout.payment_plan)
    request = await db.get(ContractRequest, checkout.contract_request_id)
    paid: list[Contract] = []
    duplicates: list[Contract] = []
    for line in checkout.lines:
        contract = await db.get(Contract, uuid.UUID(line["contract_id"]))
        if contract is None or contract.contract_request_id != checkout.contract_request_id:
            continue
        if contract.paid_at is not None:
            duplicates.append(contract)
            continue
        contract.payment_plan = checkout.payment_plan
        contract.payment_method = "CARD"
        contract.payment_discount_cents = (
            int(line.get("discount_cents") or 0) if plan is not None and plan.instalments <= 1 else 0
        )
        if stripe_subscription_id:
            contract.stripe_subscription_id = stripe_subscription_id
            contract.stripe_subscription_item_id = subscription_items.get(str(contract.id))
            contract.stripe_customer_id = stripe_customer_id
        contract.updated_at = utcnow()
        await db.commit()
        contract = await contracts_service.record_card_payment(
            db, organization_id=checkout.organization_id, contract=contract,
            stripe_invoice_id=stripe_invoice_id, notify_staff=False,
        )
        if plan is not None and plan.instalments > 1:
            await contracts_service.credit_contract_instalment_cashback(
                db, organization_id=checkout.organization_id, contract=contract, instalment_number=1
            )
        paid.append(contract)

    code = str(checkout.contract_request_id)[:8].upper()
    checkout.completed_at = utcnow()
    checkout.stripe_subscription_id = stripe_subscription_id
    checkout.stripe_customer_id = stripe_customer_id
    outcome = f"pratica {code}: {len(paid)} contratti pagati"
    if duplicates:
        outcome += f", {len(duplicates)} già pagati in precedenza"
    checkout.outcome = outcome[:255]

    if paid:
        await notifications_service.notify_roles(
            db, organization_id=checkout.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
            type_="CONTRACT_PAID_BEFORE_APPROVAL", entity_type="contract_request", entity_id=checkout.contract_request_id,
            title=f"Pratica {code} pagata: {len(paid)} {'contratto' if len(paid) == 1 else 'contratti'}",
            body=(
                f"Pagamento con carta ({plan.label.lower() if plan else checkout.payment_plan}). "
                "Ogni contratto si attiva appena approvi i suoi documenti e accetti la sua anteprima provvigioni."
            ),
        )
        customer = await db.get(Customer, request.customer_id) if request else None
        if customer is not None and customer.user_id is not None:
            await notifications_service.notify_user(
                db, organization_id=checkout.organization_id, user_id=customer.user_id,
                type_="CONTRACT_PAID_BEFORE_APPROVAL", entity_type="contract_request",
                entity_id=checkout.contract_request_id,
                title="Pagamento ricevuto",
                body=(
                    f"Abbiamo ricevuto il pagamento della pratica {code}. "
                    "Ogni contratto si attiva appena i suoi documenti sono approvati."
                ),
            )
    if duplicates:
        await notifications_service.notify_roles(
            db, organization_id=checkout.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
            type_="CONTRACT_PAID_REJECTED", entity_type="contract_request", entity_id=checkout.contract_request_id,
            title=f"Pagamento doppio sulla pratica {code}",
            body=(
                f"{len(duplicates)} contratti erano già stati pagati: "
                + ", ".join(_code(c) for c in duplicates)
                + ". Rimborsa quelle righe su Stripe" + (" e interrompi i loro addebiti." if stripe_subscription_id else ".")
            ),
        )
    await db.commit()
    return outcome


# --- Pagamento con bonifico (Session 65) ---------------------------------------


class BankTransferError(Exception):
    pass


def bank_transfer_pending(request: ContractRequest, points: list[Contract]) -> bool:
    """Announced by the customer, not yet confirmed, and still something to
    pay by transfer (a card payment afterwards settles it too)."""
    return (
        request.bank_transfer_requested_at is not None
        and request.bank_transfer_confirmed_at is None
        and any(c.payment_method == "BANK_TRANSFER" and contract_service.is_payable(c) for c in points)
    )


async def request_bank_transfer(
    db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID
) -> ContractRequest:
    """The customer pays the whole pratica by transfer: a single payment,
    with the one-go discount frozen now on every contract. Nothing is paid
    until an administrator confirms the money arrived. Commits."""
    from app.domains.organizations import service as organizations_service

    if not await organizations_service.is_bank_transfer_configured(db, organization_id=request.organization_id):
        raise BankTransferError("Il pagamento con bonifico non è disponibile al momento.")
    points = payable_points(await list_points(db, request=request))
    if not points:
        raise BankTransferError("In questa pratica non c'è nessun contratto da pagare.")
    percentage = await organizations_service.get_contract_full_payment_discount_percentage(
        db, organization_id=request.organization_id
    )
    total = 0
    for contract in points:
        gross = int(contract.gross_amount_cents or 0)
        contract.payment_plan = payment_plans.PLAN_FULL
        contract.payment_method = "BANK_TRANSFER"
        contract.payment_discount_cents = payment_plans.discount_cents_for(gross, percentage)
        contract.updated_at = utcnow()
        total += gross - contract.payment_discount_cents
    request.bank_transfer_requested_at = utcnow()
    request.bank_transfer_total_cents = total
    request.bank_transfer_confirmed_at = None
    request.bank_transfer_confirmed_by_user_id = None
    request.updated_at = utcnow()
    code = _code(request)
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.bank_transfer_requested", entity_type="contract_request",
        entity_id=str(request.id), new_value={"total_cents": total, "contracts": len(points), "discount": percentage},
    )
    await notifications_service.notify_roles(
        db, organization_id=request.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CONTRACT_REQUEST_BANK_TRANSFER", entity_type="contract_request", entity_id=request.id,
        title=f"Pratica {code}: il cliente paga con bonifico",
        body=f"{total / 100:.2f} EUR per {len(points)} {'contratto' if len(points) == 1 else 'contratti'}. "
             "Conferma quando lo ricevi, dalla pratica.",
        exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(request)
    return request


async def upload_bank_transfer_proof(
    db: AsyncSession, *, request: ContractRequest, file_bytes: bytes, content_type: str, original_filename: str,
    actor_user_id: uuid.UUID,
) -> ContractRequest:
    from app.core.storage import UploadValidationError
    from app.core.storage import upload_document as storage_upload_document

    if not bank_transfer_pending(request, await list_points(db, request=request)):
        raise BankTransferError("La ricevuta si carica per una pratica in attesa di bonifico.")
    try:
        key = storage_upload_document(
            file_bytes=file_bytes, content_type=content_type,
            key_prefix=f"contract-request-payment-proofs/{request.id}",
        )
    except UploadValidationError as exc:
        raise BankTransferError(str(exc)) from exc
    request.payment_proof_storage_key = key
    request.payment_proof_original_filename = original_filename[:255]
    request.payment_proof_uploaded_at = utcnow()
    await notifications_service.notify_roles(
        db, organization_id=request.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CONTRACT_REQUEST_BANK_TRANSFER", entity_type="contract_request", entity_id=request.id,
        title=f"Pratica {_code(request)}: ricevuta del bonifico caricata", body=None, exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(request)
    return request


def payment_proof_url(request: ContractRequest) -> str | None:
    from app.core.storage import generate_presigned_document_url

    if not request.payment_proof_storage_key:
        return None
    return generate_presigned_document_url(storage_key=request.payment_proof_storage_key, expires_in_seconds=300)


async def confirm_bank_transfer(
    db: AsyncSession, *, request: ContractRequest, actor_user_id: uuid.UUID
) -> list[Contract]:
    """An administrator saw the transfer arrive: every contract announced for
    transfer is paid, each exactly as a card payment would record it (its
    instalment row at the discounted price, its LialCash, its activation if
    already approved). Returns the contracts paid. Commits."""
    from app.domains.contracts import service as contracts_service

    points = await list_points(db, request=request)
    if not bank_transfer_pending(request, points):
        raise BankTransferError("Questa pratica non ha un bonifico in attesa di conferma.")
    paid = []
    for contract in points:
        if contract.payment_method != "BANK_TRANSFER" or not contract_service.is_payable(contract):
            continue
        contract = await contracts_service.record_card_payment(
            db, organization_id=request.organization_id, contract=contract, notify_staff=False,
            bank_transfer_confirmed_by=actor_user_id,
        )
        paid.append(contract)
    request.bank_transfer_confirmed_at = utcnow()
    request.bank_transfer_confirmed_by_user_id = actor_user_id
    request.updated_at = utcnow()
    code = _code(request)
    await audit_service.record(
        db, organization_id=request.organization_id, actor_user_id=actor_user_id,
        action="contract_request.bank_transfer_confirmed", entity_type="contract_request",
        entity_id=str(request.id), new_value={"contracts": [str(c.id) for c in paid]},
    )
    customer = await db.get(Customer, request.customer_id)
    if customer is not None and customer.user_id is not None:
        await notifications_service.notify_user(
            db, organization_id=request.organization_id, user_id=customer.user_id,
            type_="CONTRACT_PAID_BEFORE_APPROVAL", entity_type="contract_request", entity_id=request.id,
            title="Bonifico ricevuto",
            body=f"Abbiamo ricevuto il bonifico della pratica {code}. "
                 "Ogni contratto si attiva appena i suoi documenti sono approvati.",
        )
    await db.commit()
    await db.refresh(request)
    return paid


# --- Letture ------------------------------------------------------------------


async def _instalment_summary(db: AsyncSession, contract_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    if not contract_ids:
        return {}
    rows = list(
        (await db.execute(select(ContractInstalment).where(ContractInstalment.contract_id.in_(contract_ids)))).scalars()
    )
    out: dict[uuid.UUID, dict] = {}
    for row in rows:
        entry = out.setdefault(row.contract_id, {"total": row.instalments_total, "paid": 0, "failed": 0})
        if row.status == "PAID":
            entry["paid"] += 1
        elif row.status == "FAILED":
            entry["failed"] += 1
    return out


async def summaries(db: AsyncSession, requests: list[ContractRequest]) -> list[dict]:
    """The row every list shows -- customer, promoter area and staff alike --
    computed from the contracts, never stored twice: how many points, how
    many active, how many waiting for review, what it costs, what is paid."""
    if not requests:
        return []
    request_ids = [r.id for r in requests]
    contracts = list(
        (
            await db.execute(
                select(Contract).where(Contract.contract_request_id.in_(request_ids)).order_by(Contract.created_at)
            )
        ).scalars()
    )
    by_request: dict[uuid.UUID, list[Contract]] = {}
    for c in contracts:
        if c.status == "CANCELLED" and c.activated_at is None:
            continue
        by_request.setdefault(c.contract_request_id, []).append(c)

    customer_ids = {r.customer_id for r in requests}
    customers = {
        c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars()
    }
    customer_names = {cid: await _customer_name(db, customers.get(cid)) for cid in customer_ids}
    agent_ids = {r.activated_by_promoter_id for r in requests if r.activated_by_promoter_id}
    agent_names = (
        {
            a.id: a.display_name
            for a in (await db.execute(select(AgentProfile).where(AgentProfile.id.in_(agent_ids)))).scalars()
        }
        if agent_ids
        else {}
    )
    instalments = await _instalment_summary(db, [c.id for c in contracts])

    out = []
    for r in requests:
        points = by_request.get(r.id, [])
        live = [c for c in points if c.status not in ("REJECTED", "CANCELLED")]
        statuses: dict[str, int] = {}
        for c in points:
            statuses[c.status] = statuses.get(c.status, 0) + 1
        out.append({
            "id": r.id,
            "code": _code(r),
            "customer_id": r.customer_id,
            "customer_name": customer_names.get(r.customer_id),
            "customer_kind": customers[r.customer_id].kind if r.customer_id in customers else None,
            "status": r.status,
            "created_at": r.created_at,
            "submitted_at": r.submitted_at,
            "updated_at": r.updated_at,
            "created_by_role": r.created_by_role,
            "activated_by_promoter_id": r.activated_by_promoter_id,
            "activated_by_promoter_name": agent_names.get(r.activated_by_promoter_id) if r.activated_by_promoter_id else None,
            "holder_name": " ".join(x for x in (r.holder_first_name, r.holder_last_name) if x) or None,
            "points_total": len(points),
            "points_by_status": statuses,
            "points_active": sum(1 for c in points if c.status in ("ACTIVE", "RENEWED")),
            "points_to_review": statuses.get("UNDER_REVIEW", 0),
            "points_documents_pending": statuses.get("DOCUMENTS_PENDING", 0),
            "points_without_package": sum(1 for c in points if c.product_version_id is None),
            "points_paid": sum(1 for c in live if c.paid_at is not None),
            "points_payable": sum(1 for c in live if contract_service.is_payable(c)),
            "total_gross_cents": sum(int(c.gross_amount_cents or 0) for c in live),
            "payment_plans": sorted({c.payment_plan for c in live if c.paid_at is not None and c.payment_plan}),
            "instalments_failed": sum(instalments.get(c.id, {}).get("failed", 0) for c in live),
            "bank_transfer_pending": bank_transfer_pending(r, points),
            "bank_transfer_total_cents": r.bank_transfer_total_cents,
            "bank_transfer_requested_at": r.bank_transfer_requested_at,
            "payment_proof_uploaded_at": r.payment_proof_uploaded_at,
            "total_paid_cents": sum(
                int(c.gross_amount_cents or 0) - int(c.payment_discount_cents or 0)
                for c in live if c.paid_at is not None
            ),
        })
    return out


async def detail(db: AsyncSession, *, request: ContractRequest, include_checkouts: bool) -> dict:
    """Everything one screen needs about a pratica: the summary, the holder,
    and every point with its supply address, package, price, documents
    completeness and instalments."""
    from app.domains.documents import service as documents_service

    [summary] = await summaries(db, [request])
    points = await list_points(db, request=request)
    rows = await contract_service.to_read_dicts(db, points)
    customer = await db.get(Customer, request.customer_id)
    kind = customer.kind if customer else "PRIVATE"
    instalments = await _instalment_summary(db, [c.id for c in points])

    enriched = []
    for contract, row in zip(points, rows, strict=True):
        supply_point = await db.get(SupplyPoint, contract.supply_point_id)
        address = await db.get(Address, supply_point.supply_address_id) if supply_point else None
        slots = await documents_service.get_contract_documents_status(
            db, organization_id=request.organization_id, contract=contract, customer_kind=kind
        )
        product = None
        if contract.product_version_id is not None:
            version = await db.get(ProductVersion, contract.product_version_id)
            product = await db.get(Product, version.product_id) if version else None
        enriched.append({
            **row,
            "position": len(enriched) + 1,
            "meter_number": supply_point.meter_number if supply_point else None,
            "street": address.street if address else None,
            "city": address.city if address else None,
            "province": address.province if address else None,
            "postal_code": address.postal_code if address else None,
            "product_id": product.id if product else None,
            "documents_missing": sum(1 for s in slots if s["required"] and s["document"] is None),
            "documents_rejected": sum(1 for s in slots if s["document"] is not None and s["document"].status == "REJECTED"),
            "instalments_total": instalments.get(contract.id, {}).get("total"),
            "instalments_paid": instalments.get(contract.id, {}).get("paid", 0),
            "instalments_failed": instalments.get(contract.id, {}).get("failed", 0),
            #: Stripe is still charging this contract every month -- what the
            #: "Interrompi addebiti" action applies to.
            "billing_active": contract.stripe_subscription_id is not None and contract.billing_stopped_at is None,
        })

    out = {
        **summary,
        "street": request.street,
        "city": request.city,
        "province": request.province,
        "postal_code": request.postal_code,
        "holder_first_name": request.holder_first_name,
        "holder_last_name": request.holder_last_name,
        "email": request.email,
        "pec": request.pec,
        "iban": request.iban,
        "points": enriched,
        "checkouts": [],
    }
    if include_checkouts:
        checkouts = list(
            (
                await db.execute(
                    select(ContractRequestCheckout)
                    .where(ContractRequestCheckout.contract_request_id == request.id)
                    .order_by(ContractRequestCheckout.created_at.desc())
                )
            ).scalars()
        )
        out["checkouts"] = [
            {
                "id": c.id,
                "created_at": c.created_at,
                "payment_plan": c.payment_plan,
                "total_cents": c.total_cents,
                "instalment_cents": c.instalment_cents,
                "contracts": len(c.lines),
                "completed_at": c.completed_at,
                "stripe_checkout_session_id": c.stripe_checkout_session_id,
                "stripe_subscription_id": c.stripe_subscription_id,
                "outcome": c.outcome,
            }
            for c in checkouts
        ]
    return out
