import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.outbox.models import DomainOutbox


def enqueue(*, organization_id: uuid.UUID, event_type: str, payload: dict) -> DomainOutbox:
    """Adds an outbox row to the session WITHOUT committing -- caller must add this
    to the same transaction/session as the state change and commit once, together."""
    return DomainOutbox(organization_id=organization_id, event_type=event_type, payload=payload)


async def fetch_unprocessed(db: AsyncSession, *, limit: int = 100) -> list[DomainOutbox]:
    stmt = (
        select(DomainOutbox)
        .where(DomainOutbox.processed_at.is_(None))
        .order_by(DomainOutbox.created_at)
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def mark_processed(db: AsyncSession, event: DomainOutbox) -> None:
    event.processed_at = utcnow()
    await db.commit()
