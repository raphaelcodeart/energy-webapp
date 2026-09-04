import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

# Who a post is published to -- CUSTOMER (material useful to the end customer,
# e.g. how a contract works), PROMOTER (sales/training material for the
# network), or BOTH. There is no "internal staff" audience: this feed is for
# the two customer-facing roles only, not an admin announcements board.
AUDIENCES = ["CUSTOMER", "PROMOTER", "BOTH"]

# ARCHIVED posts are kept (never hard state loss from a stray click) but drop
# out of both feeds -- same soft-hide pattern as AgentProfile.status elsewhere
# in this codebase, distinct from DELETE which is a real, permanent removal an
# admin can still do separately if a post should never have existed at all.
STATUSES = ["PUBLISHED", "ARCHIVED"]


class DocumentationPost(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "documentation_posts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    # Plain text, not HTML/markdown -- rendered with whitespace preserved
    # (see documentation-feed.tsx), same "simple over flexible" choice as
    # every other free-text field in this codebase (e.g. Ticket.description).
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    audience: Mapped[str] = mapped_column(String(16), default="BOTH")
    status: Mapped[str] = mapped_column(String(16), default="PUBLISHED", index=True)
    # All three attachments are optional and independent -- a post can be
    # text-only, or carry any combination of image/pdf/video link, mirroring
    # the "social post" shape the client asked for.
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
