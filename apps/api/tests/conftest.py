import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.db import Base

# Every domain's models, so Base.metadata is fully populated before create_all.
from app.domains.audit import models as _audit_models  # noqa: F401
from app.domains.auth import models as _auth_models  # noqa: F401
from app.domains.catalog import models as _catalog_models  # noqa: F401
from app.domains.commissions import models as _commissions_models  # noqa: F401
from app.domains.contracts import models as _contracts_models  # noqa: F401
from app.domains.customers import models as _customers_models  # noqa: F401
from app.domains.documents import models as _documents_models  # noqa: F401
from app.domains.network import models as _network_models  # noqa: F401
from app.domains.notifications import models as _notifications_models  # noqa: F401
from app.domains.organizations import models as _organizations_models  # noqa: F401
from app.domains.organizations.models import Organization
from app.domains.outbox import models as _outbox_models  # noqa: F401
from app.domains.rbac import models as _rbac_models  # noqa: F401
from app.domains.referral import models as _referral_models  # noqa: F401
from app.domains.support import models as _support_models  # noqa: F401
from app.domains.users import models as _users_models  # noqa: F401

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://lial:lial_dev_pw@localhost:5432/lial_energy_test"
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_schema():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _ensure_storage_buckets():
    """Normally done by main.py's FastAPI startup event, which never fires in
    a pytest run (no ASGI lifespan here) -- tests that upload real files
    (test_documents.py, and any future photo-upload test) need the buckets to
    already exist against the real MinIO this stack runs, same as the live app."""
    from app.core.storage import ensure_documents_bucket, ensure_media_bucket

    ensure_media_bucket()
    ensure_documents_bucket()


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """One test = one connection-level transaction, with the ORM session bound to
    it via a savepoint (join_transaction_mode='create_savepoint'). Application code
    is free to call session.commit() (it does, throughout the service layer) --
    that only releases the savepoint. The OUTER transaction is rolled back at
    teardown, so no test's data leaks into the next one despite every service
    function committing internally."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.connect() as connection:
        await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await connection.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def organization_id(db: AsyncSession) -> uuid.UUID:
    org = Organization(name=f"Test Org {uuid.uuid4()}", status="ACTIVE")
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org.id
