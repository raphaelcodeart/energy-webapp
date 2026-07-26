import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit import service as audit_service
from app.domains.commissions.services.run_calculation import run_calculation_for_contract
from app.domains.outbox import service as outbox_service
from app.domains.outbox.models import DomainOutbox

logger = logging.getLogger(__name__)

# Only these event types trigger a commission calculation. Every other outbox event
# type is marked processed as a no-op by this dispatcher (other handlers, e.g.
# notifications, are expected to register themselves separately in Phase F).
COMMISSION_TRIGGER_EVENTS = {"ContractActivated", "ContractRenewed"}


async def process_pending_outbox_events(db: AsyncSession, *, limit: int = 100) -> int:
    """Polls the outbox and dispatches unprocessed events. In production this runs
    as a Celery Beat task (apps/worker); it is also called directly by the seed
    script and by tests so the vertical slice works without requiring Celery to be
    up. Idempotent: safe to call repeatedly or concurrently thanks to
    run_calculation_for_contract's (contract_id, trigger_event_id) idempotency check.

    Each event is processed in isolation: a failure calculating commissions for one
    contract must never prevent every other unrelated event in the same batch from
    being dispatched, and must never be silently swallowed either. Previously an
    unhandled exception from run_calculation_for_contract propagated out of this
    whole function, aborting the batch and leaving the failing event stuck
    "unprocessed" forever (retried, and re-blocking the whole batch, every minute
    by Celery beat) -- see docs/paid-contract-commission-audit.md, Problem #2.

    Event data is extracted into plain values up front rather than kept as ORM
    objects referenced across the loop: a rollback after a failure expires every
    object in the session's identity map, and a later bare attribute access on one
    of the OTHER (unrelated, still-pending) events' ORM objects would then trigger
    an implicit lazy-reload outside of a properly awaited context, crashing with
    'MissingGreenlet' instead of the failure staying contained to the one event
    that actually failed."""
    events = await outbox_service.fetch_unprocessed(db, limit=limit)
    event_records = [
        {"id": e.id, "organization_id": e.organization_id, "event_type": e.event_type, "payload": e.payload}
        for e in events
    ]

    processed = 0
    for record in event_records:
        if record["event_type"] in COMMISSION_TRIGGER_EVENTS:
            contract_id = uuid.UUID(record["payload"]["contract_id"])
            try:
                await run_calculation_for_contract(
                    db,
                    organization_id=record["organization_id"],
                    contract_id=contract_id,
                    trigger_event_id=record["id"],
                )
            except Exception:
                logger.exception(
                    "Commission calculation failed for contract %s (event %s, type %s)",
                    contract_id, record["id"], record["event_type"],
                )
                await db.rollback()
                await audit_service.record(
                    db, organization_id=record["organization_id"], actor_user_id=None,
                    action="commission.calculation_error", entity_type="contract", entity_id=str(contract_id),
                    new_value={"event_id": str(record["id"]), "event_type": record["event_type"]},
                    reason="Unhandled exception during commission calculation -- see worker logs",
                )
                await db.commit()
                # Deliberately NOT marked processed: left in the outbox so it is
                # retried once the underlying issue is fixed, instead of the
                # failure being silently discarded.
                continue
        # Re-fetched fresh (never the possibly-expired object from the initial
        # fetch_unprocessed() call) so this is safe even right after another
        # event in this same batch rolled back.
        outbox_event = await db.get(DomainOutbox, record["id"])
        await outbox_service.mark_processed(db, outbox_event)
        processed += 1
    return processed
