import uuid
from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import generate_presigned_document_url, upload_document as storage_upload_document
from app.domains.audit import service as audit_service
from app.domains.contracts.models import Contract
from app.domains.documents.models import DOCUMENT_TYPES, Document

# Every contract needs these three regardless of customer type -- a company
# additionally needs its chamber-of-commerce registration. Kept as a plain
# constant (not read from ProductVersion.required_documents) for this first
# version -- that JSONB column exists for a future per-product override but
# nothing populates it yet, so a hardcoded sane default is more honest than
# pretending it's configurable today.
BASE_REQUIRED_DOCUMENT_TYPES = ["IDENTITY", "FISCAL_CODE", "UTILITY_BILL"]
COMPANY_LIKE_KINDS = {"COMPANY", "CONDOMINIUM"}


class DocumentValidationError(Exception):
    pass


def required_document_types_for(customer_kind: str) -> list[str]:
    types = list(BASE_REQUIRED_DOCUMENT_TYPES)
    if customer_kind in COMPANY_LIKE_KINDS:
        types.append("CHAMBER_OF_COMMERCE")
    return types


async def upload_document(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contract_id: uuid.UUID,
    document_type: str,
    file_bytes: bytes,
    content_type: str,
    original_filename: str,
    actor_user_id: uuid.UUID,
    actor_role: str,
) -> Document:
    if document_type not in DOCUMENT_TYPES:
        raise DocumentValidationError(f"document_type must be one of {sorted(DOCUMENT_TYPES)}")

    storage_key = storage_upload_document(
        file_bytes=file_bytes, content_type=content_type, key_prefix=f"documents/{contract_id}"
    )

    document = Document(
        organization_id=organization_id,
        contract_id=contract_id,
        document_type=document_type,
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
        action="document.uploaded", entity_type="document", entity_id=str(contract_id),
        new_value={"document_type": document_type, "uploaded_by_role": actor_role},
    )
    await db.commit()
    await db.refresh(document)
    return document


async def list_documents_for_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_id: uuid.UUID
) -> list[Document]:
    stmt = (
        select(Document)
        .where(Document.organization_id == organization_id, Document.contract_id == contract_id)
        .order_by(Document.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_contract_documents_status(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, customer_kind: str
) -> list[dict]:
    """One row per required document type -- the latest (by created_at)
    document of that type, or None if it hasn't been uploaded yet. A
    rejected document doesn't disappear -- if a newer one of the same type
    was uploaded after it, that newer one is what's shown; the rejected one
    stays in the full list (list_documents_for_contract) as history."""
    docs = await list_documents_for_contract(db, organization_id=organization_id, contract_id=contract.id)
    latest_by_type: dict[str, Document] = {}
    for doc in docs:  # already newest-first
        if doc.document_type not in latest_by_type:
            latest_by_type[doc.document_type] = doc

    required_types = required_document_types_for(customer_kind)
    return [{"document_type": t, "document": latest_by_type.get(t)} for t in required_types]


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
