import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.commissions.services.run_calculation import run_calculation_for_contract
from app.domains.outbox import service as outbox_service

# Only these event types trigger a commission calculation. Every other outbox event
# type is marked processed as a no-op by this dispatcher (other handlers, e.g.
# notifications, are expected to register themselves separately in Phase F).
COMMISSION_TRIGGER_EVENTS = {"ContractActivated", "ContractRenewed"}


async def process_pending_outbox_events(db: AsyncSession, *, limit: int = 100) -> int:
    """Polls the outbox and dispatches unprocessed events. In production this runs
    as a Celery Beat task (apps/worker); it is also called directly by the seed
    script and by tests so the vertical slice works without requiring Celery to be
    up. Idempotent: safe to call repeatedly or concurrently thanks to
    run_calculation_for_contract's (contract_id, trigger_event_id) idempotency check."""
    events = await outbox_service.fetch_unprocessed(db, limit=limit)
    processed = 0
    for event in events:
        if event.event_type in COMMISSION_TRIGGER_EVENTS:
            contract_id = uuid.UUID(event.payload["contract_id"])
            await run_calculation_for_contract(
                db,
                organization_id=event.organization_id,
                contract_id=contract_id,
                trigger_event_id=event.id,
            )
        await outbox_service.mark_processed(db, event)
        processed += 1
    return processed
