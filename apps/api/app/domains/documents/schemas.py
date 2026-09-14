import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.domains.documents.models import DOCUMENT_STATUSES, DOCUMENT_TYPES


class DocumentRead(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    document_type: str
    #: Only ever set for an OTHER attachment -- the label its uploader gave
    #: it. None for every slot document, which is named by its type.
    description: str | None = None
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
    """One row per document slot on a contract -- whether it's been uploaded
    yet and, if so, its current review status. Not a Document row itself: a
    slot can be "expected but not uploaded" (document is None)."""

    document_type: str
    #: False for a slot that is offered but does not hold the contract back
    #: (the visura of a ditta individuale). Defaulted to True so an older
    #: client that ignores the field keeps reading every row as required,
    #: which is the safe direction to be wrong in.
    required: bool = True
    document: DocumentRead | None = None


class ContractDocumentsRead(BaseModel):
    contract_id: uuid.UUID
    required: list[RequiredDocumentStatus]
    #: Free-form attachments, oldest first -- each one labelled by whoever
    #: uploaded it. Never gates the contract.
    extra: list[DocumentRead] = []


class DocumentTypeInfo(BaseModel):
    code: str
    label: str


DOCUMENT_TYPE_LABELS = {
    "IDENTITY": "Documento d'identità",
    "FISCAL_CODE": "Codice fiscale",
    "UTILITY_BILL": "Fattura luce/gas",
    "CHAMBER_OF_COMMERCE": "Visura camerale",
    "OTHER": "Documento aggiuntivo",
}

assert set(DOCUMENT_TYPE_LABELS) == DOCUMENT_TYPES
