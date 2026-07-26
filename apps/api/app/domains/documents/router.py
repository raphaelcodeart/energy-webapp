import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.storage import UploadValidationError
from app.domains.contracts.models import Contract
from app.domains.customers.models import Company, Customer, CustomerProfile
from app.domains.customers.service import display_name_for
from app.domains.documents import service as documents_service
from app.domains.documents.models import Document
from app.domains.documents.schemas import (
    ContractDocumentsRead,
    DocumentRead,
    DocumentReviewRequest,
    DocumentUrlRead,
)
from app.domains.support.service import actor_role_for
from app.domains.users.models import User

router = APIRouter(tags=["documents"])

PRESIGNED_URL_TTL_SECONDS = 300


async def _resolve_own_customer_id(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID | None:
    stmt = select(Customer.id).where(Customer.organization_id == organization_id, Customer.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _get_org_scoped_contract(db: AsyncSession, *, organization_id: uuid.UUID, contract_id: uuid.UUID) -> Contract:
    contract = await db.get(Contract, contract_id)
    if contract is None or contract.organization_id != organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contract not found")
    return contract


async def _assert_contract_document_access(
    db: AsyncSession, *, current_user: CurrentUser, contract: Contract, actor_role: str
) -> None:
    """A customer may only touch documents on THEIR OWN contract; staff
    (anyone whose actor_role resolves to ADMIN -- see support/service.py's
    same classification used for tickets) may touch any contract's documents
    in the organization."""
    if actor_role != "CUSTOMER":
        return
    own_customer_id = await _resolve_own_customer_id(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    if own_customer_id is None or contract.customer_id != own_customer_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this contract's documents")


async def _document_read(db: AsyncSession, document: Document) -> dict:
    name = None
    user = await db.get(User, document.uploaded_by_user_id)
    if document.uploaded_by_role == "CUSTOMER":
        customer = (
            await db.execute(select(Customer).where(Customer.user_id == document.uploaded_by_user_id))
        ).scalar_one_or_none()
        if customer is not None:
            profile = await db.get(CustomerProfile, customer.id)
            company = await db.get(Company, customer.id)
            name = display_name_for(customer.kind, profile, company)
    if name is None and user is not None:
        name = user.email

    reviewed_by_name = None
    if document.reviewed_by_user_id is not None:
        reviewer = await db.get(User, document.reviewed_by_user_id)
        reviewed_by_name = reviewer.email if reviewer else None

    return {
        "id": document.id,
        "contract_id": document.contract_id,
        "document_type": document.document_type,
        "original_filename": document.original_filename,
        "content_type": document.content_type,
        "size_bytes": document.size_bytes,
        "uploaded_by_user_id": document.uploaded_by_user_id,
        "uploaded_by_role": document.uploaded_by_role,
        "uploaded_by_name": name,
        "status": document.status,
        "reviewed_by_user_id": document.reviewed_by_user_id,
        "reviewed_by_name": reviewed_by_name,
        "reviewed_at": document.reviewed_at,
        "review_note": document.review_note,
        "created_at": document.created_at,
    }


@router.post("/contracts/{contract_id}/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_contract_document(
    contract_id: uuid.UUID,
    document_type: str = Form(...),
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission("documents.upload")),
    db: AsyncSession = Depends(get_db),
) -> DocumentRead:
    contract = await _get_org_scoped_contract(db, organization_id=current_user.organization_id, contract_id=contract_id)
    actor_role = actor_role_for(current_user.roles)
    await _assert_contract_document_access(db, current_user=current_user, contract=contract, actor_role=actor_role)

    file_bytes = await file.read()
    try:
        document = await documents_service.upload_document(
            db,
            organization_id=current_user.organization_id,
            contract_id=contract_id,
            document_type=document_type,
            file_bytes=file_bytes,
            content_type=file.content_type or "",
            original_filename=file.filename or "documento",
            actor_user_id=current_user.user_id,
            actor_role=actor_role,
        )
    except (documents_service.DocumentValidationError, UploadValidationError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return DocumentRead(**(await _document_read(db, document)))


@router.get("/contracts/{contract_id}/documents", response_model=ContractDocumentsRead)
async def get_contract_documents(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("documents.download")),
    db: AsyncSession = Depends(get_db),
) -> ContractDocumentsRead:
    contract = await _get_org_scoped_contract(db, organization_id=current_user.organization_id, contract_id=contract_id)
    actor_role = actor_role_for(current_user.roles)
    await _assert_contract_document_access(db, current_user=current_user, contract=contract, actor_role=actor_role)

    customer = await db.get(Customer, contract.customer_id)
    customer_kind = customer.kind if customer else "PRIVATE"

    rows = await documents_service.get_contract_documents_status(
        db, organization_id=current_user.organization_id, contract=contract, customer_kind=customer_kind
    )
    required = []
    for row in rows:
        doc_read = await _document_read(db, row["document"]) if row["document"] is not None else None
        required.append({"document_type": row["document_type"], "document": doc_read})
    return ContractDocumentsRead(contract_id=contract_id, required=required)


@router.get("/documents/{document_id}/url", response_model=DocumentUrlRead)
async def get_document_url(
    document_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("documents.download")),
    db: AsyncSession = Depends(get_db),
) -> DocumentUrlRead:
    document = await documents_service.get_document(db, organization_id=current_user.organization_id, document_id=document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=document.contract_id
    )
    actor_role = actor_role_for(current_user.roles)
    await _assert_contract_document_access(db, current_user=current_user, contract=contract, actor_role=actor_role)

    url = await documents_service.get_presigned_url_for_document(document)
    return DocumentUrlRead(url=url, expires_in_seconds=PRESIGNED_URL_TTL_SECONDS)


@router.patch("/documents/{document_id}/review", response_model=DocumentRead)
async def review_document(
    document_id: uuid.UUID,
    payload: DocumentReviewRequest,
    current_user: CurrentUser = Depends(require_permission("documents.review")),
    db: AsyncSession = Depends(get_db),
) -> DocumentRead:
    document = await documents_service.review_document(
        db,
        organization_id=current_user.organization_id,
        document_id=document_id,
        new_status=payload.status,
        review_note=payload.review_note,
        actor_user_id=current_user.user_id,
    )
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return DocumentRead(**(await _document_read(db, document)))
