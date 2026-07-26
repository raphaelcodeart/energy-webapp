import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.domains.documents.models import DOCUMENT_STATUSES, DOCUMENT_TYPES


class DocumentRead(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    document_type: str
    original_filename: str
    content_type: str
    size_bytes: int
    uploaded_by_user_id: uuid.UUID
    uploaded_by_role: str
    uploaded_by_name: str | None = None
    status: str
    reviewed_by_user_id: uuid.UUID | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime


class DocumentUrlRead(BaseModel):
    url: str
    expires_in_seconds: int


class DocumentReviewRequest(BaseModel):
    status: str
    review_note: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in DOCUMENT_STATUSES - {"PENDING_REVIEW"}:
            raise ValueError("status must be APPROVED or REJECTED")
        return v


class RequiredDocumentStatus(BaseModel):
    """One row per required document type for a contract -- whether it's been
    uploaded yet and, if so, its current review status. Not a Document row
    itself: a type can be "required but not uploaded" (document is None)."""

    document_type: str
    document: DocumentRead | None = None


class ContractDocumentsRead(BaseModel):
    contract_id: uuid.UUID
    required: list[RequiredDocumentStatus]


class DocumentTypeInfo(BaseModel):
    code: str
    label: str


DOCUMENT_TYPE_LABELS = {
    "IDENTITY": "Documento d'identità",
    "FISCAL_CODE": "Codice fiscale",
    "UTILITY_BILL": "Fattura luce/gas",
    "CHAMBER_OF_COMMERCE": "Visura camerale",
}

assert set(DOCUMENT_TYPE_LABELS) == DOCUMENT_TYPES
