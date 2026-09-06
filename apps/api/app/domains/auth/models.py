import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin


class Session(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column()
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)


class PasswordResetToken(UUIDPKMixin, TimestampMixin, Base):
    """Same pattern as Session/refresh tokens: the opaque random token is only
    ever handed to the client (in the reset link); the DB stores just its
    hash, so a DB leak alone never yields a usable reset token."""

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column()
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)


class EmailVerificationToken(UUIDPKMixin, TimestampMixin, Base):
    """Same opaque-token/hashed-at-rest pattern as PasswordResetToken -- sent
    once at self-registration (auth/service.py::register_with_referral), used
    once by GET /auth/verify-email to set users.email_verified_at."""

    __tablename__ = "email_verification_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column()
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)


class OtpCode(UUIDPKMixin, TimestampMixin, Base):
    """A short numeric code emailed to the user to confirm they, and only
    they, took some sensitive self-service action -- today just the
    'lavora con noi' collaboration-contract acceptance (see
    network/service.py::apply_as_promoter). `purpose` keeps this reusable for
    a future OTP-gated action without a new table."""

    __tablename__ = "otp_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column()
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
