from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

# Import every domain's models module so SQLAlchemy's metadata (and therefore
# Alembic autogenerate) sees all tables, even though nothing else here references
# these imports directly.
from app.domains.audit import models as _audit_models  # noqa: F401
from app.domains.auth import models as _auth_models  # noqa: F401
from app.domains.auth.router import router as auth_router
from app.domains.catalog import models as _catalog_models  # noqa: F401
from app.domains.commissions import models as _commissions_models  # noqa: F401
from app.domains.commissions.router import router as commissions_router
from app.domains.contracts import models as _contracts_models  # noqa: F401
from app.domains.contracts.router import router as contracts_router
from app.domains.customers import models as _customers_models  # noqa: F401
from app.domains.network import models as _network_models  # noqa: F401
from app.domains.network.router import router as network_router
from app.domains.organizations import models as _organizations_models  # noqa: F401
from app.domains.outbox import models as _outbox_models  # noqa: F401
from app.domains.rbac import models as _rbac_models  # noqa: F401
from app.domains.referral import models as _referral_models  # noqa: F401
from app.domains.referral.router import router as referral_router
from app.domains.users import models as _users_models  # noqa: F401

settings = get_settings()

app = FastAPI(
    title="Lial Energy Platform API",
    version="0.1.0",
    description="See /opt/lialenergy/docs for architecture and business rules.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(network_router, prefix="/api")
app.include_router(referral_router, prefix="/api")
app.include_router(contracts_router, prefix="/api")
app.include_router(commissions_router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readiness")
async def readiness() -> dict[str, str]:
    from sqlalchemy import text

    from app.core.db import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ready"}
