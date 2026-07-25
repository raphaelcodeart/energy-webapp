import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit.models import AuditLog


async def record(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: str,
    previous_value: dict | None = None,
    new_value: dict | None = None,
    reason: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    correlation_id: str | None = None,
) -> AuditLog:
    """Insert an audit row. Caller is responsible for committing within the same
    transaction as the change being audited, so an audit entry never exists for a
    change that didn't happen (and vice versa)."""
    entry = AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        previous_value=previous_value,
        new_value=new_value,
        reason=reason,
        ip_address=ip_address,
        user_agent=user_agent,
        correlation_id=correlation_id,
    )
    db.add(entry)
    await db.flush()
    return entry
