"""/contract-requests -- la pratica di attivazione (Session 52).

Who may do what, enforced here and nowhere else:

- the customer: their own pratiche, everything including paying;
- a promoter: the pratiche of customers they may act for (their own, or
  inherited from a deactivated promoter below them) -- filling in, documents,
  sending; never paying, which the customer does from their own account;
- staff (contracts.review): read every pratica and its payments. Reviewing,
  approving and rejecting stay per contract, on /contracts.

A user can be customer and promoter at once, so both relationships are
checked rather than trusting the first role in the token.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rate_limit import rate_limit
from app.core.storage import UploadValidationError
from app.domains.contracts import payment_plans
from app.domains.contracts import requests as requests_service
from app.domains.contracts import service as contract_service
from app.domains.contracts.models import ContractRequest
from app.domains.contracts.requests_schemas import (
    ContractRequestAddress,
    ContractRequestCheckoutRequest,
    ContractRequestCreate,
    ContractRequestDetailRead,
    ContractRequestHolder,
    ContractRequestPaymentLineRead,
    ContractRequestPaymentOptionRead,
    ContractRequestPaymentOptionsRead,
    ContractRequestPointsCount,
    ContractRequestProductSet,
    ContractRequestSummaryRead,
)
from app.domains.customers.models import Customer
from app.domains.documents import service as documents_service
from app.domains.documents.schemas import (
    ContractDocumentsRead,
    DocumentRead,
    RequiredDocumentStatus,
)
from app.domains.organizations import service as organizations_service
from app.domains.rbac.service import get_permission_codes_for_user
from app.domains.support.service import actor_role_for

router = APIRouter(prefix="/contract-requests", tags=["contract-requests"])


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


async def _own_customer(db: AsyncSession, current_user: CurrentUser) -> Customer | None:
    return (
        await db.execute(
            select(Customer).where(
                Customer.organization_id == current_user.organization_id, Customer.user_id == current_user.user_id
            )
        )
    ).scalar_one_or_none()


async def _is_staff(db: AsyncSession, current_user: CurrentUser) -> bool:
    codes = await get_permission_codes_for_user(
        db, user_id=current_user.user_id, organization_id=current_user.organization_id
    )
    return "contracts.review" in codes


async def _promoter_may_act_for(db: AsyncSession, current_user: CurrentUser, customer_id: uuid.UUID):
    try:
        return await contract_service.resolve_promoter_for_customer(
            db, organization_id=current_user.organization_id, promoter_user_id=current_user.user_id,
            customer_id=customer_id,
        )
    except contract_service.SelfServiceContractError:
        return None


class _Access:
    def __init__(self, *, is_owner: bool, is_promoter: bool, is_staff: bool) -> None:
        self.is_owner = is_owner
        self.is_promoter = is_promoter
        self.is_staff = is_staff

    @property
    def can_edit(self) -> bool:
        return self.is_owner or self.is_promoter


async def _load(
    db: AsyncSession, current_user: CurrentUser, request_id: uuid.UUID, *, edit: bool = False
) -> tuple[ContractRequest, _Access]:
    request = await db.get(ContractRequest, request_id)
    if request is None or request.organization_id != current_user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pratica non trovata.")
    own = await _own_customer(db, current_user)
    is_owner = own is not None and own.id == request.customer_id
    is_promoter = not is_owner and "PROMOTER" in current_user.roles and (
        await _promoter_may_act_for(db, current_user, request.customer_id) is not None
    )
    is_staff = not (is_owner or is_promoter) and await _is_staff(db, current_user)
    access = _Access(is_owner=is_owner, is_promoter=is_promoter, is_staff=is_staff)
    if not (is_owner or is_promoter or is_staff):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pratica non trovata.")
    if edit and not access.can_edit:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Questa pratica la compila il cliente o il suo promoter.")
    return request, access


async def _detail(db: AsyncSession, request: ContractRequest, access: _Access) -> ContractRequestDetailRead:
    data = await requests_service.detail(db, request=request, include_checkouts=access.is_staff)
    return ContractRequestDetailRead(**data)


def _address(payload: ContractRequestAddress) -> requests_service.AddressData:
    return requests_service.AddressData(
        street=payload.street, city=payload.city, province=payload.province, postal_code=payload.postal_code
    )


def _holder(payload: ContractRequestHolder) -> requests_service.HolderData:
    return requests_service.HolderData(
        first_name=payload.holder_first_name, last_name=payload.holder_last_name,
        email=payload.email, pec=payload.pec, iban=payload.iban, address=_address(payload),
    )


# --- Elenchi -----------------------------------------------------------------


@router.get("/mine", response_model=list[ContractRequestSummaryRead])
async def list_my_requests(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ContractRequestSummaryRead]:
    """The customer's own pratiche, newest first. Abandoned drafts are not
    listed: they are nothing the customer needs to see again."""
    own = await _own_customer(db, current_user)
    if own is None:
        return []
    rows = (
        await db.execute(
            select(ContractRequest)
            .where(ContractRequest.customer_id == own.id, ContractRequest.status != "CANCELLED")
            .order_by(ContractRequest.created_at.desc())
        )
    ).scalars()
    return [ContractRequestSummaryRead(**s) for s in await requests_service.summaries(db, list(rows))]


@router.get("/for-customer/{customer_id}", response_model=list[ContractRequestSummaryRead])
async def list_requests_for_my_customer(
    customer_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ContractRequestSummaryRead]:
    """A promoter's view of one of their customers' pratiche -- including the
    ones the customer filled in alone."""
    if await _promoter_may_act_for(db, current_user, customer_id) is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Questo cliente non è nella tua rete.")
    rows = (
        await db.execute(
            select(ContractRequest)
            .where(
                ContractRequest.organization_id == current_user.organization_id,
                ContractRequest.customer_id == customer_id,
                ContractRequest.status != "CANCELLED",
            )
            .order_by(ContractRequest.created_at.desc())
        )
    ).scalars()
    return [ContractRequestSummaryRead(**s) for s in await requests_service.summaries(db, list(rows))]


@router.get("", response_model=list[ContractRequestSummaryRead])
async def list_requests(
    current_user: CurrentUser = Depends(require_permission("contracts.review")),
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = None,
    customer_id: uuid.UUID | None = None,
    limit: int = 500,
) -> list[ContractRequestSummaryRead]:
    stmt = select(ContractRequest).where(ContractRequest.organization_id == current_user.organization_id)
    if status_filter:
        stmt = stmt.where(ContractRequest.status == status_filter)
    if customer_id:
        stmt = stmt.where(ContractRequest.customer_id == customer_id)
    rows = (await db.execute(stmt.order_by(ContractRequest.created_at.desc()).limit(min(limit, 2000)))).scalars()
    return [ContractRequestSummaryRead(**s) for s in await requests_service.summaries(db, list(rows))]


# --- Pratica -----------------------------------------------------------------


@router.post("", response_model=ContractRequestDetailRead, status_code=status.HTTP_201_CREATED)
async def create_request(
    payload: ContractRequestCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRequestDetailRead:
    if payload.customer_id is None:
        own = await _own_customer(db, current_user)
        if own is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nessuna anagrafica cliente collegata a questo account.")
        customer_id, promoter_agent_id, role = own.id, None, "CUSTOMER"
    else:
        try:
            promoter = await contract_service.resolve_promoter_for_customer(
                db, organization_id=current_user.organization_id, promoter_user_id=current_user.user_id,
                customer_id=payload.customer_id,
            )
        except contract_service.SelfServiceContractError as exc:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
        customer_id, promoter_agent_id, role = payload.customer_id, promoter.id, "PROMOTER"
    try:
        request = await requests_service.create_request(
            db, organization_id=current_user.organization_id, customer_id=customer_id,
            holder=_holder(payload), actor_user_id=current_user.user_id, actor_role=role,
            promoter_agent_id=promoter_agent_id, points_count=payload.points_count,
            product_version_id=payload.product_version_id,
        )
    except requests_service.ContractRequestError as exc:
        raise _bad_request(exc) from exc
    return await _detail(db, request, _Access(is_owner=role == "CUSTOMER", is_promoter=role == "PROMOTER", is_staff=False))


@router.get("/{request_id}", response_model=ContractRequestDetailRead)
async def get_request(
    request_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRequestDetailRead:
    request, access = await _load(db, current_user, request_id)
    return await _detail(db, request, access)


@router.patch("/{request_id}", response_model=ContractRequestDetailRead)
async def update_request_holder(
    request_id: uuid.UUID,
    payload: ContractRequestHolder,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRequestDetailRead:
    request, access = await _load(db, current_user, request_id, edit=True)
    try:
        request = await requests_service.update_holder(
            db, request=request, holder=_holder(payload), actor_user_id=current_user.user_id
        )
    except requests_service.ContractRequestError as exc:
        raise _bad_request(exc) from exc
    return await _detail(db, request, access)


@router.put("/{request_id}/points-count", response_model=ContractRequestDetailRead)
async def set_points_count(
    request_id: uuid.UUID,
    payload: ContractRequestPointsCount,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRequestDetailRead:
    """"Quanti POD hai?" changed while the pratica is a draft."""
    request, access = await _load(db, current_user, request_id, edit=True)
    try:
        await requests_service.set_points_count(
            db, request=request, count=payload.count, actor_user_id=current_user.user_id
        )
    except requests_service.ContractRequestError as exc:
        raise _bad_request(exc) from exc
    await db.refresh(request)
    return await _detail(db, request, access)


@router.patch("/{request_id}/points/{contract_id}/address", response_model=ContractRequestDetailRead)
async def update_point_address(
    request_id: uuid.UUID,
    contract_id: uuid.UUID,
    payload: ContractRequestAddress,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRequestDetailRead:
    request, access = await _load(db, current_user, request_id, edit=True)
    try:
        contract = await requests_service.get_point(db, request=request, contract_id=contract_id)
        await requests_service.update_point_address(
            db, request=request, contract=contract, address_data=_address(payload), actor_user_id=current_user.user_id
        )
    except requests_service.ContractRequestError as exc:
        raise _bad_request(exc) from exc
    await db.refresh(request)
    return await _detail(db, request, access)


@router.delete("/{request_id}/points/{contract_id}", response_model=ContractRequestDetailRead)
async def remove_point(
    request_id: uuid.UUID,
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRequestDetailRead:
    request, access = await _load(db, current_user, request_id, edit=True)
    try:
        contract = await requests_service.get_point(db, request=request, contract_id=contract_id)
        await requests_service.remove_point(db, request=request, contract=contract, actor_user_id=current_user.user_id)
    except requests_service.ContractRequestError as exc:
        raise _bad_request(exc) from exc
    await db.refresh(request)
    return await _detail(db, request, access)


@router.put("/{request_id}/points/{contract_id}/product", response_model=ContractRequestDetailRead)
async def set_point_product(
    request_id: uuid.UUID,
    contract_id: uuid.UUID,
    payload: ContractRequestProductSet,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRequestDetailRead:
    request, access = await _load(db, current_user, request_id, edit=True)
    try:
        contract = await requests_service.get_point(db, request=request, contract_id=contract_id)
        await requests_service.set_point_product(
            db, request=request, contract=contract, product_version_id=payload.product_version_id,
            actor_user_id=current_user.user_id,
        )
    except requests_service.ContractRequestError as exc:
        raise _bad_request(exc) from exc
    await db.refresh(request)
    return await _detail(db, request, access)


@router.put("/{request_id}/product", response_model=ContractRequestDetailRead)
async def set_product_for_all_points(
    request_id: uuid.UUID,
    payload: ContractRequestProductSet,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRequestDetailRead:
    request, access = await _load(db, current_user, request_id, edit=True)
    try:
        await requests_service.set_product_for_all(
            db, request=request, product_version_id=payload.product_version_id, actor_user_id=current_user.user_id
        )
    except requests_service.ContractRequestError as exc:
        raise _bad_request(exc) from exc
    await db.refresh(request)
    return await _detail(db, request, access)


@router.post("/{request_id}/submit", response_model=ContractRequestDetailRead)
async def submit_request(
    request_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRequestDetailRead:
    request, access = await _load(db, current_user, request_id, edit=True)
    try:
        request = await requests_service.submit_request(db, request=request, actor_user_id=current_user.user_id)
    except requests_service.ContractRequestError as exc:
        raise _bad_request(exc) from exc
    return await _detail(db, request, access)


@router.post("/{request_id}/cancel", response_model=ContractRequestDetailRead)
async def cancel_request(
    request_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRequestDetailRead:
    request, access = await _load(db, current_user, request_id, edit=True)
    try:
        request = await requests_service.cancel_request(db, request=request, actor_user_id=current_user.user_id)
    except requests_service.ContractRequestError as exc:
        raise _bad_request(exc) from exc
    return await _detail(db, request, access)


# --- Pagamento ---------------------------------------------------------------


@router.get("/{request_id}/payment-options", response_model=ContractRequestPaymentOptionsRead)
async def get_payment_options(
    request_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRequestPaymentOptionsRead:
    """Every figure computed here from the prices frozen on the contracts --
    the browser only ever sends back a plan key."""
    from app.domains.payments.service import _point_labels

    request, _ = await _load(db, current_user, request_id)
    points = await requests_service.list_points(db, request=request)
    payable = requests_service.payable_points(points)
    labels = await _point_labels(db, payable)
    discount_percentage = await organizations_service.get_contract_full_payment_discount_percentage(
        db, organization_id=current_user.organization_id
    )
    cashback_total = await requests_service.cashback_total_cents(db, points=payable)
    full_payment_cashback = await requests_service.cashback_total_cents(
        db, points=payable, discount_percentage=discount_percentage
    )
    bank_available = await organizations_service.is_bank_transfer_configured(
        db, organization_id=current_user.organization_id
    )
    bank = await organizations_service.get_settings(db, organization_id=current_user.organization_id)
    return ContractRequestPaymentOptionsRead(
        contract_request_id=request.id,
        card_available=await organizations_service.is_stripe_configured(
            db, organization_id=current_user.organization_id
        ),
        lines=[
            ContractRequestPaymentLineRead(contract_id=c.id, label=labels[c.id], gross_cents=int(c.gross_amount_cents or 0))
            for c in payable
        ],
        total_gross_cents=sum(int(c.gross_amount_cents or 0) for c in payable),
        options=[
            ContractRequestPaymentOptionRead(
                key=o.plan.key, label=o.plan.label, description=o.plan.description, instalments=o.plan.instalments,
                instalment_cents=o.instalment_cents, total_cents=o.total_cents,
                rounding_difference_cents=o.rounding_difference_cents, available=o.available,
                unavailable_reason=o.unavailable_reason, list_total_cents=o.list_total_cents,
                discount_percentage=o.discount_percentage, discount_cents=o.discount_cents,
                cashback_cents=(
                    full_payment_cashback if o.discount_cents else cashback_total
                ),
            )
            for o in requests_service.plan_options(payable, discount_percentage=discount_percentage)
        ],
        points_paid=sum(1 for c in points if c.paid_at is not None),
        cashback_total_cents=cashback_total,
        cashback_mode=await organizations_service.get_contract_instalment_cashback_mode(
            db, organization_id=current_user.organization_id
        ),
        bank_transfer_available=bank_available,
        bank_transfer_pending=requests_service.bank_transfer_pending(request, points),
        bank_transfer_total_cents=request.bank_transfer_total_cents,
        bank_transfer_requested_at=request.bank_transfer_requested_at,
        payment_proof_uploaded_at=request.payment_proof_uploaded_at,
        bank_iban=bank.get("bank_iban") if bank_available else None,
        bank_account_holder=(bank.get("bank_account_holder") or "Lial Energy") if bank_available else None,
        bank_transfer_instructions=bank.get("bank_transfer_instructions") if bank_available else None,
        bank_transfer_reference=f"Pratica {str(request.id)[:8].upper()}",
    )


@router.post("/{request_id}/checkout-session")
async def create_checkout_session(
    request_id: uuid.UUID,
    payload: ContractRequestCheckoutRequest,
    success_url: str,
    cancel_url: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Opens Stripe Checkout for the whole pratica. Only the customer pays:
    the card is theirs, and so is the decision to charge it. Never marks
    anything paid -- only the verified webhook does."""
    from app.domains.payments import service as payments_service

    request, access = await _load(db, current_user, request_id)
    if not access.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Il pagamento lo effettua il cliente dal proprio account.")
    if payment_plans.plan_by_key(payload.payment_plan) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Modalità di pagamento non valida.")
    try:
        url = await payments_service.create_checkout_session_for_request(
            db, organization_id=current_user.organization_id, request=request, plan_key=payload.payment_plan,
            actor_user_id=current_user.user_id, success_url=success_url, cancel_url=cancel_url,
        )
    except payments_service.StripeNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except payments_service.PaymentsError as exc:
        raise _bad_request(exc) from exc
    return {"checkout_url": url}


@router.post("/{request_id}/bank-transfer", response_model=ContractRequestDetailRead)
async def request_bank_transfer(
    request_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRequestDetailRead:
    """"Paga con bonifico": single payment with the one-go discount, paid
    when an administrator confirms the transfer arrived."""
    request, access = await _load(db, current_user, request_id)
    if not access.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Il pagamento lo sceglie il cliente dal proprio account.")
    try:
        request = await requests_service.request_bank_transfer(db, request=request, actor_user_id=current_user.user_id)
    except requests_service.BankTransferError as exc:
        raise _bad_request(exc) from exc
    return await _detail(db, request, access)


@router.post(
    "/{request_id}/bank-transfer/proof",
    response_model=ContractRequestDetailRead,
    dependencies=[Depends(rate_limit("contract-request-payment-proof", max_requests=20, window_seconds=300))],
)
async def upload_bank_transfer_proof(
    request_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRequestDetailRead:
    request, access = await _load(db, current_user, request_id)
    if not access.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "La ricevuta la carica il cliente dal proprio account.")
    try:
        request = await requests_service.upload_bank_transfer_proof(
            db, request=request, file_bytes=await file.read(), content_type=file.content_type or "",
            original_filename=file.filename or "ricevuta-bonifico", actor_user_id=current_user.user_id,
        )
    except requests_service.BankTransferError as exc:
        raise _bad_request(exc) from exc
    return await _detail(db, request, access)


@router.get("/{request_id}/bank-transfer/proof-url")
async def get_bank_transfer_proof_url(
    request_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    request, _access = await _load(db, current_user, request_id)
    url = requests_service.payment_proof_url(request)
    if url is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nessuna ricevuta caricata.")
    return {"url": url}


@router.post("/{request_id}/bank-transfer/confirm", response_model=ContractRequestDetailRead)
async def confirm_bank_transfer(
    request_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("contracts.review")),
    db: AsyncSession = Depends(get_db),
) -> ContractRequestDetailRead:
    """"Conferma bonifico ricevuto": every contract announced for transfer is
    paid at the discounted amount frozen when the customer chose it."""
    request, access = await _load(db, current_user, request_id)
    try:
        await requests_service.confirm_bank_transfer(db, request=request, actor_user_id=current_user.user_id)
    except requests_service.BankTransferError as exc:
        raise _bad_request(exc) from exc
    await db.refresh(request)
    return await _detail(db, request, access)


# --- Documenti della pratica ---------------------------------------------------


@router.get("/{request_id}/documents", response_model=ContractDocumentsRead)
async def get_request_documents(
    request_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractDocumentsRead:
    from app.domains.documents.router import _document_read

    request, _ = await _load(db, current_user, request_id)
    customer = await db.get(Customer, request.customer_id)
    kind = customer.kind if customer else "PRIVATE"
    rows = await documents_service.get_request_documents_status(
        db, organization_id=request.organization_id, request=request, customer_kind=kind
    )
    required = [
        RequiredDocumentStatus(
            document_type=row["document_type"], required=row["required"],
            document=DocumentRead(**(await _document_read(db, row["document"]))) if row["document"] else None,
        )
        for row in rows
    ]
    extra = [
        DocumentRead(**(await _document_read(db, doc)))
        for doc in await documents_service.get_extra_documents_for_request(
            db, organization_id=request.organization_id, request=request, customer_kind=kind
        )
    ]
    return ContractDocumentsRead(contract_request_id=request.id, required=required, extra=extra)


@router.post(
    "/{request_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("document-upload", max_requests=20, window_seconds=300))],
)
async def upload_request_document(
    request_id: uuid.UUID,
    document_type: str = Form(...),
    description: str | None = Form(None),
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentRead:
    """A document for the whole pratica: counts for every point in it."""
    from app.domains.documents.router import _document_read

    request, access = await _load(db, current_user, request_id)
    if not (access.can_edit or access.is_staff):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Non puoi caricare documenti su questa pratica.")
    file_bytes = await file.read()
    try:
        document = await documents_service.upload_document(
            db, organization_id=request.organization_id, contract_request_id=request.id,
            document_type=document_type, description=description, file_bytes=file_bytes,
            content_type=file.content_type or "", original_filename=file.filename or "documento",
            actor_user_id=current_user.user_id,
            actor_role="CUSTOMER" if access.is_owner else "PROMOTER" if access.is_promoter else actor_role_for(current_user.roles),
        )
    except (documents_service.DocumentValidationError, UploadValidationError) as exc:
        raise _bad_request(exc) from exc
    return DocumentRead(**(await _document_read(db, document)))
