import uuid
from datetime import date, datetime

from pydantic import BaseModel


class ContractTotals(BaseModel):
    total: int
    active: int
    pending_approval: int  # SUBMITTED/DOCUMENTS_PENDING/UNDER_REVIEW/APPROVED/PAYMENT_PENDING/PAID/ACTIVATION_PENDING
    rejected: int
    cancelled: int
    suspended: int
    expired: int


class CommissionTotals(BaseModel):
    accrued_cents: int  # maturate (ACCRUED, non ancora liquidate -- vedi Fase 7 del piano)
    payable_cents: int  # liquidabili (PAYABLE/SCHEDULED)
    paid_cents: int  # già pagate (PAID)
    reversed_cents: int  # storni (REVERSED, valore assoluto)


class DashboardSummary(BaseModel):
    contracts: ContractTotals
    commissions: CommissionTotals
    active_promoters: int
    active_customers: int
    period_new_contracts: int
    period_new_commissions_cents: int
    generated_at: datetime


class AttentionItem(BaseModel):
    contract_id: uuid.UUID
    customer_id: uuid.UUID
    status: str
    days_in_status: int
    reason: str


class RecentActivityItem(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: str
    reason: str | None
    created_at: datetime


class TimeseriesPoint(BaseModel):
    period: date
    value: int
