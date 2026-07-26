import uuid

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin


class Customer(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "customers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    # Optional link to a login -- customers acquired before self-service signup (or
    # imported) may have no user account yet. Ownership checks (a customer must only
    # ever see their own contracts) key off this column, never off email matching.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, unique=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # PRIVATE / SOLE_PROPRIETOR / COMPANY / CONDOMINIUM
    fiscal_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vat_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pec: Mapped[str | None] = mapped_column(String(255), nullable=True)


class CustomerProfile(Base):
    __tablename__ = "customer_profiles"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), primary_key=True
    )
    first_name: Mapped[str] = mapped_column(String(128))
    last_name: Mapped[str] = mapped_column(String(128))


class Company(Base):
    __tablename__ = "companies"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), primary_key=True
    )
    company_name: Mapped[str] = mapped_column(String(255))
    legal_form: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sdi_code: Mapped[str | None] = mapped_column(String(16), nullable=True)


class Address(UUIDPKMixin, Base):
    __tablename__ = "addresses"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="SUPPLY")
    street: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(128))
    province: Mapped[str] = mapped_column(String(8))
    postal_code: Mapped[str] = mapped_column(String(16))
    country: Mapped[str] = mapped_column(String(2), default="IT")


class SupplyPoint(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "supply_points"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)
    # Human-readable identifier (e.g. "Abitazione principale - Via Roma 12,
    # Milano") -- POD/PDR codes are correct but meaningless to a person
    # scanning a list. Auto-computed from energy_type + address at creation if
    # not given explicitly (see service.py); always editable afterwards.
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    energy_type: Mapped[str] = mapped_column(String(16))
    pod_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pdr_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    meter_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supply_address_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("addresses.id"))
    estimated_consumption: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actual_consumption: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
