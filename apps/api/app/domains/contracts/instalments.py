"""Le rate di un contratto, e le provvigioni che ciascuna libera.

Business rule (Session 50), stated by the business:

- a contract paid in one go pays its commissions once;
- a contract paid in 3 or 12 instalments pays them 3 or 12 times, one slice
  per instalment, each slice released only when that instalment has really
  been paid -- confirmed by Stripe, or, when Stripe could not collect it, by
  an administrator by hand;
- nothing is released before the contract is ACTIVE, i.e. before an
  administrator has approved the documents and accepted the commission
  preview. Instalments paid before that are released together at activation.

The slice is 1/N of each beneficiary's commission (commissions/services/
run_calculation.py::instalment_share), never the whole commission N times:
the gettoni run from 40 to 160 EUR on a 180 EUR contract.

Every release is one ContractInstalmentPaid outbox event, emitted at most
once per row (commission_event_id is claimed with a conditional UPDATE), so
the commission engine's own idempotency is backed by a row that cannot be
released twice however many webhooks and clicks arrive.
"""

import calendar
import uuid
from datetime import date, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.contracts import payment_plans
from app.domains.contracts.models import Contract, ContractInstalment
from app.domains.outbox import service as outbox_service

INSTALMENT_PAID_EVENT = "ContractInstalmentPaid"

SOURCE_STRIPE_CHECKOUT = "STRIPE_CHECKOUT"
SOURCE_STRIPE_INVOICE = "STRIPE_INVOICE"
SOURCE_ADMIN = "ADMIN"

#: Statuses in which a paid instalment releases its commissions straight away.
RELEASING_CONTRACT_STATUSES = frozenset({"ACTIVE", "RENEWED"})


class InstalmentError(Exception):
    pass


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def instalments_for(contract: Contract) -> int:
    plan = payment_plans.plan_by_key(contract.payment_plan)
    return plan.instalments if plan is not None else 1


async def list_instalments(db: AsyncSession, *, contract_id: uuid.UUID) -> list[ContractInstalment]:
    return list(
        (
            await db.execute(
                select(ContractInstalment)
                .where(ContractInstalment.contract_id == contract_id)
                .order_by(ContractInstalment.number)
            )
        ).scalars()
    )


async def ensure_schedule(db: AsyncSession, *, contract: Contract) -> list[ContractInstalment]:
    """Creates the instalment rows the first time a payment is recorded. The
    count is fixed by the plan the customer actually paid with, so it is
    never guessed ahead of that moment."""
    existing = await list_instalments(db, contract_id=contract.id)
    if existing:
        return existing
    plan = payment_plans.plan_by_key(contract.payment_plan)
    total = instalments_for(contract)
    gross = int(contract.gross_amount_cents or 0)
    amount = payment_plans.breakdown_for(plan, gross).instalment_cents if plan is not None else gross
    start = (contract.paid_at or utcnow()).date()
    rows = [
        ContractInstalment(
            organization_id=contract.organization_id,
            contract_id=contract.id,
            number=n,
            instalments_total=total,
            due_date=_add_months(start, n - 1),
            amount_cents=amount,
            status="SCHEDULED",
        )
        for n in range(1, total + 1)
    ]
    db.add_all(rows)
    await db.flush()
    return rows


async def _find_row(
    db: AsyncSession, *, contract: Contract, number: int | None, invoice_id: str | None
) -> ContractInstalment | None:
    rows = await ensure_schedule(db, contract=contract)
    if invoice_id:
        for row in rows:
            if row.stripe_invoice_id == invoice_id:
                return row
    if number is not None:
        return next((r for r in rows if r.number == number), None)
    # A new invoice: the earliest instalment not yet paid and not already
    # tied to a different Stripe invoice (a FAILED one keeps its own id, so a
    # later retry of that same invoice finds it above).
    return next((r for r in rows if r.status != "PAID" and r.stripe_invoice_id is None), None)


async def record_payment(
    db: AsyncSession,
    *,
    contract: Contract,
    source: str,
    number: int | None = None,
    invoice_id: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> ContractInstalment | None:
    """Marks one instalment paid and, if the contract is already active,
    releases its commissions. Returns None when there was nothing to do (the
    same payment reported twice, or no instalment left). Does not commit."""
    row = await _find_row(db, contract=contract, number=number, invoice_id=invoice_id)
    if row is None or row.status == "PAID":
        return None
    row.status = "PAID"
    row.paid_at = utcnow()
    row.payment_source = source
    row.confirmed_by_user_id = actor_user_id
    if invoice_id and row.stripe_invoice_id is None:
        row.stripe_invoice_id = invoice_id
    await db.flush()
    if contract.status in RELEASING_CONTRACT_STATUSES:
        await release(db, contract=contract, row=row)
    return row


async def record_failure(db: AsyncSession, *, contract: Contract, invoice_id: str | None) -> ContractInstalment | None:
    row = await _find_row(db, contract=contract, number=None, invoice_id=invoice_id)
    if row is None or row.status == "PAID":
        return None
    row.status = "FAILED"
    if invoice_id and row.stripe_invoice_id is None:
        row.stripe_invoice_id = invoice_id
    await db.flush()
    return row


async def release(db: AsyncSession, *, contract: Contract, row: ContractInstalment) -> bool:
    """Emits the outbox event that pays this instalment's slice of the
    commissions -- at most once per row, whoever gets here first."""
    event = outbox_service.enqueue(
        organization_id=contract.organization_id,
        event_type=INSTALMENT_PAID_EVENT,
        payload={
            "contract_id": str(contract.id),
            "instalment_number": row.number,
            "instalments_total": row.instalments_total,
        },
    )
    event.id = uuid.uuid4()
    claimed = await db.execute(
        update(ContractInstalment)
        .where(ContractInstalment.id == row.id, ContractInstalment.commission_event_id.is_(None))
        .values(commission_event_id=event.id)
    )
    if claimed.rowcount != 1:
        return False
    db.add(event)
    row.commission_event_id = event.id
    await db.flush()
    return True


async def release_paid_instalments(db: AsyncSession, *, contract: Contract) -> int:
    """At activation: everything the customer had already paid releases now."""
    released = 0
    for row in await list_instalments(db, contract_id=contract.id):
        if row.status == "PAID" and row.commission_event_id is None and await release(db, contract=contract, row=row):
            released += 1
    return released


async def confirm_manually(
    db: AsyncSession, *, contract: Contract, number: int, actor_user_id: uuid.UUID
) -> ContractInstalment:
    """An administrator confirming an instalment Stripe did not collect (a
    bank transfer, a card fixed by phone...). Commits."""
    rows = await list_instalments(db, contract_id=contract.id)
    if not rows:
        raise InstalmentError("Questo contratto non ha ancora un piano di rate: nessun pagamento registrato.")
    row = next((r for r in rows if r.number == number), None)
    if row is None:
        raise InstalmentError("Rata inesistente.")
    if row.status == "PAID":
        raise InstalmentError("Questa rata risulta già pagata.")
    await record_payment(
        db, contract=contract, source=SOURCE_ADMIN, number=number, actor_user_id=actor_user_id
    )
    await db.commit()
    await db.refresh(row)
    return row


async def mark_commission_released(
    db: AsyncSession, *, contract_id: uuid.UUID, number: int, calculation_id: uuid.UUID | None, at: datetime
) -> None:
    row = (
        await db.execute(
            select(ContractInstalment).where(
                ContractInstalment.contract_id == contract_id, ContractInstalment.number == number
            )
        )
    ).scalar_one_or_none()
    if row is not None and row.commission_released_at is None:
        row.commission_released_at = at
        row.commission_calculation_id = calculation_id
        await db.commit()
