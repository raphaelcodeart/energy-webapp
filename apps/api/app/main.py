import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Import every domain's models module so SQLAlchemy's metadata (and therefore
# Alembic autogenerate) sees all tables, even though nothing else here references
# these imports directly.
from app.domains.audit import models as _audit_models  # noqa: F401
from app.domains.auth import models as _auth_models  # noqa: F401
from app.domains.auth.router import router as auth_router
from app.domains.catalog import models as _catalog_models  # noqa: F401
from app.domains.catalog.router import router as catalog_router
from app.domains.commissions import models as _commissions_models  # noqa: F401
from app.domains.commissions.router import router as commissions_router
from app.domains.contracts import models as _contracts_models  # noqa: F401
from app.domains.contracts.router import router as contracts_router
from app.domains.customers import models as _customers_models  # noqa: F401
from app.domains.customers.router import router as customers_router
from app.domains.documentation import models as _documentation_models  # noqa: F401
from app.domains.documentation.router import router as documentation_router
from app.domains.documents import models as _documents_models  # noqa: F401
from app.domains.documents.router import router as documents_router
from app.domains.invoice_redemptions import models as _invoice_redemptions_models  # noqa: F401
from app.domains.invoice_redemptions.router import router as invoice_redemptions_router
from app.domains.network import models as _network_models  # noqa: F401
from app.domains.network.router import router as network_router
from app.domains.notifications import models as _notifications_models  # noqa: F401
from app.domains.notifications.router import router as notifications_router
from app.domains.organizations import models as _organizations_models  # noqa: F401
from app.domains.outbox import models as _outbox_models  # noqa: F401
from app.domains.partners import models as _partners_models  # noqa: F401
from app.domains.partners.router import router as partners_router
from app.domains.rbac import models as _rbac_models  # noqa: F401
from app.domains.referral import models as _referral_models  # noqa: F401
from app.domains.referral.router import authenticated_router as referral_authenticated_router
from app.domains.referral.router import router as referral_router
from app.domains.reports.router import router as reports_router
from app.domains.support import models as _support_models  # noqa: F401
from app.domains.support.router import router as support_router
from app.domains.users import models as _users_models  # noqa: F401
from app.domains.wallets import models as _wallets_models  # noqa: F401
from app.domains.wallets.router import router as wallets_router

settings = get_settings()

app = FastAPI(
    title="Lial Energy Platform API",
    version="0.1.0",
    description="See /opt/lialenergy/docs for architecture and business rules.",
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
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
app.include_router(referral_authenticated_router, prefix="/api")
app.include_router(contracts_router, prefix="/api")
app.include_router(commissions_router, prefix="/api")
app.include_router(customers_router, prefix="/api")
app.include_router(catalog_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(support_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(documentation_router, prefix="/api")
app.include_router(wallets_router, prefix="/api")
app.include_router(partners_router, prefix="/api")
app.include_router(invoice_redemptions_router, prefix="/api")


@app.on_event("startup")
async def _ensure_media_bucket() -> None:
    from app.core.storage import ensure_documents_bucket, ensure_media_bucket

    try:
        ensure_media_bucket()
        ensure_documents_bucket()
    except Exception:
        # Photo/document upload is a nice-to-have, not core to the app -- a
        # MinIO hiccup at startup must never take down the whole API.
        logger.exception("Could not ensure media/documents buckets exist -- photo/document upload will fail until this is resolved")


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
