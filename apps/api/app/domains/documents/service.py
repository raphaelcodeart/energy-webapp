import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import generate_presigned_document_url
from app.core.storage import upload_document as storage_upload_document
from app.domains.audit import service as audit_service
from app.domains.contracts.models import Contract, ContractRequest
from app.domains.documents.models import (
    DOCUMENT_TYPE_OTHER,
    DOCUMENT_TYPES,
    MAX_DOCUMENT_DESCRIPTION_LENGTH,
    MIN_DOCUMENT_DESCRIPTION_LENGTH,
    Document,
)

# Every contract needs these three regardless of customer type -- a company
# additionally needs its chamber-of-commerce registration. Kept as a plain
# constant (not read from ProductVersion.required_documents) for this first
# version -- that JSONB column exists for a future per-product override but
# nothing populates it yet, so a hardcoded sane default is more honest than
# pretending it's configurable today.
BASE_REQUIRED_DOCUMENT_TYPES = ["IDENTITY", "FISCAL_CODE", "UTILITY_BILL"]
COMPANY_LIKE_KINDS = {"COMPANY", "CONDOMINIUM"}
# A ditta individuale / libero professionista is a business for VAT
# (catalog/pricing.py) but is NOT always in the Registro Imprese -- a
# professionista with a partita IVA has no visura camerale at all. So the
# slot is OFFERED to them rather than demanded: shown in the list, clearly
# marked optional, and never blocking the contract from moving on. Making it
# mandatory would strand exactly the customers who cannot produce it.
CHAMBER_OF_COMMERCE_OPTIONAL_KINDS = {"SOLE_PROPRIETOR"}


class DocumentValidationError(Exception):
    pass


@dataclass(frozen=True)
class DocumentSlot:
    """One named place to upload, on this contract, for this customer kind."""

    document_type: str
    #: False for a slot that is shown and accepted but does not hold the
    #: contract back -- see CHAMBER_OF_COMMERCE_OPTIONAL_KINDS.
    required: bool


def document_slots_for(customer_kind: str) -> list[DocumentSlot]:
    slots = [DocumentSlot(document_type=t, required=True) for t in BASE_REQUIRED_DOCUMENT_TYPES]
    if customer_kind in COMPANY_LIKE_KINDS:
        slots.append(DocumentSlot(document_type="CHAMBER_OF_COMMERCE", required=True))
    elif customer_kind in CHAMBER_OF_COMMERCE_OPTIONAL_KINDS:
        slots.append(DocumentSlot(document_type="CHAMBER_OF_COMMERCE", required=False))
    return slots


#: Slots that describe the holder, not the supply point: the same for every
#: point of a pratica, so a pratica collects them once (Session 52).
REQUEST_LEVEL_DOCUMENT_TYPES = frozenset({"IDENTITY", "FISCAL_CODE", "CHAMBER_OF_COMMERCE"})


def request_document_slots_for(customer_kind: str) -> list[DocumentSlot]:
    """What a pratica asks for once, for all its points: the holder's slots,
    plus an optional bill -- for the customer whose single bill lists every
    point. Each contract still has its own bill slot; a bill on the pratica
    simply fills it for every contract that has none of its own."""
    slots = [slot for slot in document_slots_for(customer_kind) if slot.document_type in REQUEST_LEVEL_DOCUMENT_TYPES]
    slots.append(DocumentSlot(document_type="UTILITY_BILL", required=False))
    return slots


def required_document_types_for(customer_kind: str) -> list[str]:
    """Only the types that actually block the contract. Everything that is
    merely offered (optional slots, extra attachments) is deliberately not
    here: this is the list `maybe_advance_to_under_review` gates on."""
    return [slot.document_type for slot in document_slots_for(customer_kind) if slot.required]


def normalize_document_description(description: str | None) -> str:
    """The label an uploader gives an extra attachment. Whitespace is
    collapsed so "  Delega    firmata " and "Delega firmata" are the same
    string in the admin's list, and the length is bounded on the way in
    rather than truncated on the way out."""
    cleaned = " ".join((description or "").split())
    if len(cleaned) < MIN_DOCUMENT_DESCRIPTION_LENGTH:
        raise DocumentValidationError(
            "Indica di che documento si tratta (almeno "
            f"{MIN_DOCUMENT_DESCRIPTION_LENGTH} caratteri)."
        )
    if len(cleaned) > MAX_DOCUMENT_DESCRIPTION_LENGTH:
        raise DocumentValidationError(
            f"La descrizione del documento non può superare i {MAX_DOCUMENT_DESCRIPTION_LENGTH} caratteri."
        )
    return cleaned


async def upload_document(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contract_id: uuid.UUID | None = None,
    contract_request_id: uuid.UUID | None = None,
    document_type: str,
    file_bytes: bytes,
    content_type: str,
    original_filename: str,
    actor_user_id: uuid.UUID,
    actor_role: str,
    description: str | None = None,
) -> Document:
    """Attaches a document to one contract, or -- with `contract_request_id`
    -- to a whole pratica, where it counts for every contract in it."""
    if (contract_id is None) == (contract_request_id is None):
        raise DocumentValidationError("Un documento appartiene a un contratto oppure a una pratica.")
    if document_type not in DOCUMENT_TYPES:
        raise DocumentValidationError(f"document_type must be one of {sorted(DOCUMENT_TYPES)}")

    # Only an extra attachment carries a label, and it must carry one:
    # a slot document is already named by its type, and accepting a
    # caller-supplied label there would let "Documento d'identità" arrive
    # calling itself something else.
    description = normalize_document_description(description) if document_type == DOCUMENT_TYPE_OTHER else None

    storage_key = storage_upload_document(
        file_bytes=file_bytes, content_type=content_type,
        key_prefix=f"documents/{contract_id}" if contract_id else f"documents/requests/{contract_request_id}",
    )

    document = Document(
        organization_id=organization_id,
        contract_id=contract_id,
        contract_request_id=contract_request_id,
        document_type=document_type,
        description=description,
        original_filename=original_filename,
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=len(file_bytes),
        uploaded_by_user_id=actor_user_id,
        uploaded_by_role=actor_role,
        status="PENDING_REVIEW",
    )
    db.add(document)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="document.uploaded", entity_type="document", entity_id=str(contract_id or contract_request_id),
        new_value={
            "document_type": document_type,
            "uploaded_by_role": actor_role,
            **({"description": description} if description else {}),
        },
    )
    await db.commit()
    await db.refresh(document)

    if contract_id is not None:
        contract_ids = [contract_id]
    else:
        contract_ids = list(
            (await db.execute(select(Contract.id).where(Contract.contract_request_id == contract_request_id))).scalars()
        )
    for target_id in contract_ids:
        await maybe_advance_to_under_review(
            db, organization_id=organization_id, contract_id=target_id, actor_user_id=actor_user_id
        )
    return document


async def maybe_advance_to_under_review(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_id: uuid.UUID, actor_user_id: uuid.UUID
) -> None:
    """Once every required document type has at least one uploaded document
    (any status -- staff still reviews/approves/rejects each one, this just
    signals "the customer is done, ready for a human to look"), the contract
    advances itself from SUBMITTED/DOCUMENTS_PENDING to UNDER_REVIEW. Part of
    the Session 29 self-service contract flow -- see
    business-rules.md#contract-self-service. A staff-created contract that
    happens to have its documents uploaded via this same endpoint gets the
    exact same courtesy advance; there's nothing self-service-specific about
    the check itself."""
    from app.domains.contracts import service as contracts_service
    from app.domains.customers.models import Customer

    contract = await db.get(Contract, contract_id)
    if contract is None or contract.status not in ("SUBMITTED", "DOCUMENTS_PENDING"):
        return

    customer = await db.get(Customer, contract.customer_id)
    customer_kind = customer.kind if customer else "PRIVATE"
    rows = await get_contract_documents_status(
        db, organization_id=organization_id, contract=contract, customer_kind=customer_kind
    )
    # Only the required slots gate the advance -- an offered-but-optional
    # one (and any extra attachment) must never be the reason a contract
    # sits waiting for a document nobody actually needs.
    if not all(row["document"] is not None for row in rows if row["required"]):
        return

    if contract.status == "SUBMITTED":
        contract = await contracts_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status="DOCUMENTS_PENDING",
            actor_user_id=actor_user_id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
        )
    await contracts_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="UNDER_REVIEW",
        actor_user_id=actor_user_id, reason="Tutti i documenti richiesti sono stati caricati", notes=None,
        correlation_id=str(uuid.uuid4()),
    )


async def list_documents_for_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_id: uuid.UUID
) -> list[Document]:
    """The contract's own documents only, newest first -- not its pratica's."""
    stmt = (
        select(Document)
        .where(Document.organization_id == organization_id, Document.contract_id == contract_id)
        .order_by(Document.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_documents_for_request(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_request_id: uuid.UUID
) -> list[Document]:
    """The documents uploaded once for a whole pratica, newest first."""
    stmt = (
        select(Document)
        .where(Document.organization_id == organization_id, Document.contract_request_id == contract_request_id)
        .order_by(Document.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


def _latest_by_type(docs: list[Document]) -> dict[str, Document]:
    latest: dict[str, Document] = {}
    for doc in sorted(docs, key=lambda d: d.created_at, reverse=True):
        latest.setdefault(doc.document_type, doc)
    return latest


async def get_contract_documents_status(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, customer_kind: str
) -> list[dict]:
    """One row per document slot -- the latest (by created_at) document of
    that type, or None if it hasn't been uploaded yet, plus whether the slot
    is required or merely offered. A rejected document doesn't disappear --
    if a newer one of the same type was uploaded after it, that newer one is
    what's shown; the rejected one stays in the full list
    (list_documents_for_contract) as history.

    A document uploaded on the contract's pratica fills the same slot here
    (Session 52): identity and fiscal code are uploaded once for ten points,
    and each of the ten contracts sees them. When both exist, the contract's
    own wins -- it is the more specific one (this point's bill over the
    pratica's shared bill)."""
    own = _latest_by_type(
        await list_documents_for_contract(db, organization_id=organization_id, contract_id=contract.id)
    )
    shared = _latest_by_type(
        await list_documents_for_request(
            db, organization_id=organization_id, contract_request_id=contract.contract_request_id
        )
    )

    return [
        {
            "document_type": slot.document_type,
            "required": slot.required,
            "document": own.get(slot.document_type) or shared.get(slot.document_type),
        }
        for slot in document_slots_for(customer_kind)
    ]


async def get_request_documents_status(
    db: AsyncSession, *, organization_id: uuid.UUID, request: ContractRequest, customer_kind: str
) -> list[dict]:
    """Same shape as get_contract_documents_status, for the slots a pratica
    collects once (request_document_slots_for)."""
    shared = _latest_by_type(
        await list_documents_for_request(db, organization_id=organization_id, contract_request_id=request.id)
    )
    return [
        {"document_type": slot.document_type, "required": slot.required, "document": shared.get(slot.document_type)}
        for slot in request_document_slots_for(customer_kind)
    ]


async def get_extra_documents_for_request(
    db: AsyncSession, *, organization_id: uuid.UUID, request: ContractRequest, customer_kind: str
) -> list[Document]:
    slot_types = {slot.document_type for slot in request_document_slots_for(customer_kind)}
    docs = await list_documents_for_request(db, organization_id=organization_id, contract_request_id=request.id)
    return [doc for doc in reversed(docs) if doc.document_type not in slot_types]


async def get_extra_documents_for_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, customer_kind: str
) -> list[Document]:
    """Everything attached to this contract that no slot accounts for.

    That is every OTHER attachment (all of them, oldest first -- unlike a
    slot, a second extra document does not supersede the first), and also
    any document whose type simply has no slot for this customer kind --
    a visura uploaded back when the customer was registered as a company,
    say. Those would otherwise vanish from the screen while still sitting in
    the bucket, which is the one thing a documents list must not do."""
    slot_types = {slot.document_type for slot in document_slots_for(customer_kind)}
    docs = await list_documents_for_contract(db, organization_id=organization_id, contract_id=contract.id)
    return [doc for doc in reversed(docs) if doc.document_type not in slot_types]


async def get_document(db: AsyncSession, *, organization_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
    document = await db.get(Document, document_id)
    if document is None or document.organization_id != organization_id:
        return None
    return document


async def get_presigned_url_for_document(document: Document) -> str:
    return generate_presigned_document_url(storage_key=document.storage_key)


async def review_document(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    new_status: str,
    review_note: str | None,
    actor_user_id: uuid.UUID,
) -> Document | None:
    document = await get_document(db, organization_id=organization_id, document_id=document_id)
    if document is None:
        return None

    previous_status = document.status
    document.status = new_status
    document.review_note = review_note
    document.reviewed_by_user_id = actor_user_id
    document.reviewed_at = datetime.now(UTC)

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="document.reviewed", entity_type="document", entity_id=str(document_id),
        previous_value={"status": previous_status}, new_value={"status": new_status},
        reason=review_note,
    )
    await db.commit()
    await db.refresh(document)
    return document
