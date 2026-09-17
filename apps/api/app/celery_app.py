"""Celery application. Runs as `apps/worker` in the docker-compose topology, but is
defined inside the api package on purpose: the worker must reuse the exact same
domain code (models, services, the commission engine) as the API, never a copy of
it. `docker-compose.dev.yml`'s celery-worker/celery-beat services build from this
same image (apps/api/Dockerfile) and simply run a different command."""

import logging

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

# Every domain's models, so SQLAlchemy's declarative metadata is fully
# populated before any task ever flushes a session -- without this, a task
# whose own import chain never happens to touch e.g. organizations.models
# (nothing here did, before this was added) hits NoReferencedTableError the
# first time it tries to flush a row with an FK to a table SQLAlchemy has
# literally never heard of yet. Same reasoning, and the same list, as
# main.py's own noqa import block for the API process -- discovered when
# process_outbox_task (which runs every minute) turned out to have always
# crashed on its first flush for exactly this reason.
from app.domains.audit import models as _audit_models  # noqa: F401
from app.domains.auth import models as _auth_models  # noqa: F401
from app.domains.catalog import models as _catalog_models  # noqa: F401
from app.domains.cj_dropshipping import models as _cj_models  # noqa: F401
from app.domains.commissions import models as _commissions_models  # noqa: F401
from app.domains.contracts import models as _contracts_models  # noqa: F401
from app.domains.customers import models as _customers_models  # noqa: F401
from app.domains.documentation import models as _documentation_models  # noqa: F401
from app.domains.documents import models as _documents_models  # noqa: F401
from app.domains.friend_referrals import models as _friend_referrals_models  # noqa: F401
from app.domains.imported_products import models as _imported_products_models  # noqa: F401
from app.domains.invoice_redemptions import models as _invoice_redemptions_models  # noqa: F401
from app.domains.network import models as _network_models  # noqa: F401
from app.domains.notifications import models as _notifications_models  # noqa: F401
from app.domains.orders import models as _orders_models  # noqa: F401
from app.domains.organizations import models as _organizations_models  # noqa: F401
from app.domains.outbox import models as _outbox_models  # noqa: F401
from app.domains.partners import models as _partners_models  # noqa: F401
from app.domains.payments import models as _payments_models  # noqa: F401
from app.domains.rbac import models as _rbac_models  # noqa: F401
from app.domains.referral import models as _referral_models  # noqa: F401
from app.domains.support import models as _support_models  # noqa: F401
from app.domains.users import models as _users_models  # noqa: F401
from app.domains.wallets import models as _wallets_models  # noqa: F401

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
        "cj-sync-orders": {
            # Shop Lial Partner: status and tracking of the orders on CJ.
            "task": "app.celery_app.cj_sync_orders_task",
            "schedule": crontab(minute="*/30"),
        },
        "cj-retry-orders": {
            # Shop Lial Partner: orders not sent, temporary failures, orders
            # waiting for CJ balance (paid as soon as the balance covers them).
            "task": "app.celery_app.cj_retry_orders_task",
            "schedule": crontab(minute="*/10"),
        },
        "cj-sync-products": {
            # Cost, stock and availability of the imported CJ products.
            "task": "app.celery_app.cj_sync_products_task",
            "schedule": crontab(hour=3, minute=30),
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


def _cj_run(job):
    """Runs a CJ job for every organization that has a CJ key."""
    import asyncio

    from sqlalchemy import select

    from app.core.db import AsyncSessionLocal
    from app.domains.cj_dropshipping import client as cj_client
    from app.domains.cj_dropshipping.models import CjSettings

    async def _run() -> int:
        cj_client.reset_redis()
        total = 0
        async with AsyncSessionLocal() as db:
            org_ids = list(
                (await db.execute(select(CjSettings.organization_id).where(CjSettings.api_key.is_not(None)))).scalars()
            )
            for org_id in org_ids:
                try:
                    total += await job(db, org_id)
                except Exception:
                    logging.getLogger(__name__).exception("CJ job failed for organization %s", org_id)
                    await db.rollback()
        return total

    return asyncio.run(_run())


@celery_app.task(name="app.celery_app.cj_sync_orders_task")
def cj_sync_orders_task() -> int:
    from app.domains.cj_dropshipping import service as cj_service

    return _cj_run(lambda db, org_id: cj_service.sync_orders(db, organization_id=org_id))


@celery_app.task(name="app.celery_app.cj_retry_orders_task")
def cj_retry_orders_task() -> int:
    from app.domains.cj_dropshipping import service as cj_service

    return _cj_run(lambda db, org_id: cj_service.retry_due_orders(db, organization_id=org_id))


@celery_app.task(name="app.celery_app.cj_sync_products_task")
def cj_sync_products_task() -> int:
    from app.domains.cj_dropshipping import service as cj_service

    return _cj_run(lambda db, org_id: cj_service.sync_all_products(db, organization_id=org_id))


@celery_app.task(name="app.celery_app.cj_forward_order_task")
def cj_forward_order_task(order_id: str) -> str:
    """Automatic "Invia a CJ" right after payment, when enabled."""
    import asyncio
    import uuid

    from app.core.db import AsyncSessionLocal
    from app.domains.cj_dropshipping import client as cj_client
    from app.domains.cj_dropshipping import service as cj_service
    from app.domains.cj_dropshipping.models import CjOrder

    async def _run() -> str:
        cj_client.reset_redis()
        async with AsyncSessionLocal() as db:
            order = await db.get(CjOrder, uuid.UUID(order_id))
            if order is None:
                return "missing"
            try:
                order = await cj_service.forward_order(
                    db, organization_id=order.organization_id, order_id=order.id, actor_user_id=None
                )
            except cj_service.CjError as exc:
                return f"skipped: {exc}"
            return order.fulfillment_status

    return asyncio.run(_run())
