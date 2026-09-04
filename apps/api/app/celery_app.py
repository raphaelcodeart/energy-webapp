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
        "monthly-rank-evaluation": {
            "task": "app.celery_app.run_monthly_rank_evaluation_task",
            # Day 1 of each month, not the last instant of the last day -- more
            # robust than trying to catch an exact month-end moment, and still
            # evaluates the month that just closed (see previous_calendar_month()).
            "schedule": crontab(day_of_month=1, hour=2, minute=0),
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


@celery_app.task(name="app.celery_app.run_monthly_rank_evaluation_task")
def run_monthly_rank_evaluation_task() -> int:
    """Evaluates the calendar month that just closed for every organization,
    promoting/demoting each ACTIVE agent's rank to match their production
    (see commissions/services/rank_evaluation.py). Same admin-triggerable logic
    also runs on demand via POST /commissions/rank-evaluation/run."""
    import asyncio

    from sqlalchemy import select

    from app.core.db import AsyncSessionLocal, utcnow
    from app.domains.commissions.services.rank_evaluation import (
        previous_calendar_month,
        run_monthly_rank_evaluation,
    )
    from app.domains.organizations.models import Organization

    async def _run() -> int:
        window_start, window_end = previous_calendar_month(utcnow())
        total_changes = 0
        async with AsyncSessionLocal() as db:
            org_ids = (await db.execute(select(Organization.id))).scalars().all()
            for organization_id in org_ids:
                changes = await run_monthly_rank_evaluation(
                    db, organization_id=organization_id, window_start=window_start, window_end=window_end,
                )
                total_changes += len(changes)
        return total_changes

    return asyncio.run(_run())
