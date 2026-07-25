"""Celery application. Runs as `apps/worker` in the docker-compose topology, but is
defined inside the api package on purpose: the worker must reuse the exact same
domain code (models, services, the commission engine) as the API, never a copy of
it. `docker-compose.dev.yml`'s celery-worker/celery-beat services build from this
same image (apps/api/Dockerfile) and simply run a different command."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("lial_energy", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "process-domain-outbox": {
            "task": "app.celery_app.process_outbox_task",
            "schedule": crontab(minute="*/1"),
        },
    },
)


@celery_app.task(name="app.celery_app.process_outbox_task")
def process_outbox_task() -> int:
    """Polls domain_outbox for unprocessed events (ContractActivated, etc.) and
    dispatches them -- primarily this is what triggers commission calculation
    after a contract activation commits (see ADR 0005, the transactional outbox)."""
    import asyncio

    from app.core.db import AsyncSessionLocal
    from app.domains.commissions.tasks.dispatch import process_pending_outbox_events

    async def _run() -> int:
        async with AsyncSessionLocal() as db:
            return await process_pending_outbox_events(db)

    return asyncio.run(_run())
