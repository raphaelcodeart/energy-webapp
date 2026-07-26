import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

DOCUMENT_TYPES = {"IDENTITY", "FISCAL_CODE", "UTILITY_BILL", "CHAMBER_OF_COMMERCE"}
DOCUMENT_STATUSES = {"PENDING_REVIEW", "APPROVED", "REJECTED"}
ALLOWED_DOCUMENT_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_DOCUMENT_BYTES = 15 * 1024 * 1024  # 15 MB -- a phone photo of a bill/ID, not a video


class Document(UUIDPKMixin, TimestampMixin, Base):
    """A sensitive customer document attached to a contract (identity, fiscal
    code, utility bill, or -- for companies -- chamber of commerce
    registration). Stored in the PRIVATE "lial-documents" bucket, never the
    public "lial-media" one used for profile/product photos -- see
    core/storage.py and security-model.md §Documents. Access is only ever via
    a short-lived presigned URL issued after an authorization check; nothing
    here is ever a public, guessable, or search-engine-indexable URL."""

    __tablename__ = "documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(32))
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
