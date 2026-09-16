import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

#: "OTHER" is the open slot: anything that has to be attached beyond the
#: fixed list -- the back of an ID, a lease, a delega, a visura a private
#: customer was asked for by hand. It is the only type that carries a
#: `description`, because it is the only one whose label the uploader has to
#: supply: without it an admin would open a review queue full of rows that
#: all read "Altro documento".
DOCUMENT_TYPE_OTHER = "OTHER"
DOCUMENT_TYPES = {"IDENTITY", "FISCAL_CODE", "UTILITY_BILL", "CHAMBER_OF_COMMERCE", DOCUMENT_TYPE_OTHER}
DOCUMENT_STATUSES = {"PENDING_REVIEW", "APPROVED", "REJECTED"}
ALLOWED_DOCUMENT_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_DOCUMENT_BYTES = 15 * 1024 * 1024  # 15 MB -- a phone photo of a bill/ID, not a video
MIN_DOCUMENT_DESCRIPTION_LENGTH = 3
#: Long enough for "Visura camerale aggiornata a settembre 2026", short
#: enough to stay on one line in the admin's review list.
MAX_DOCUMENT_DESCRIPTION_LENGTH = 120


class Document(UUIDPKMixin, TimestampMixin, Base):
    """A sensitive customer document attached to a contract (identity, fiscal
    code, utility bill, for companies the chamber of commerce registration,
    or any extra attachment the uploader labels themselves -- see
    DOCUMENT_TYPE_OTHER). Stored in the PRIVATE "lial-documents" bucket, never the
    public "lial-media" one used for profile/product photos -- see
    core/storage.py and security-model.md §Documents. Access is only ever via
    a short-lived presigned URL issued after an authorization check; nothing
    here is ever a public, guessable, or search-engine-indexable URL."""

    __tablename__ = "documents"
    __table_args__ = (CheckConstraint("num_nonnulls(contract_id, contract_request_id) = 1", name="one_owner"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    #: Exactly one of these two is set. A document of the pratica (Session
    #: 52) -- identity, fiscal code, visura, or one bill listing every point
    #: -- is uploaded once and counts for every contract in it; a document of
    #: a contract belongs to that supply point alone (its own bill, a photo of
    #: its meter). See documents/service.py::get_contract_documents_status.
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id"), index=True, nullable=True
    )
    contract_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contract_requests.id"), index=True, nullable=True
    )
    document_type: Mapped[str] = mapped_column(String(32))
    #: What the uploader said this is. Only ever set for DOCUMENT_TYPE_OTHER
    #: -- every other type already has a fixed label
    #: (schemas.py::DOCUMENT_TYPE_LABELS), and letting an uploader relabel
    #: "Documento d'identità" would make the required-document check lie.
    description: Mapped[str | None] = mapped_column(String(MAX_DOCUMENT_DESCRIPTION_LENGTH), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    # Opaque key inside the private bucket -- never handed to a browser as-is,
    # only ever used server-side to mint a presigned GET URL on demand.
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    # Snapshot, not derived at read time -- same "frozen at the moment it
    # happens" rule as tickets.opened_by_role: a later role change must never
    # rewrite who uploaded what as what.
    uploaded_by_role: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="PENDING_REVIEW", index=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
