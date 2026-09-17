"""The CJ Dropshipping Open API 2.0, as this app uses it.

Three things every call has to respect, all handled here so no caller can
forget them:

- **Authentication.** The API key buys an access token (180 days) and a
  refresh token (180 days). Tokens are stored on cj_settings and reused; a
  token CJ rejects is dropped and fetched again once. A new token is asked
  for only when there is none, never on every call -- CJ answers the token
  endpoint once per second at most.
- **Rate limit.** 1 request per second per account at CJ's base level. The
  API process and the Celery workers share one Redis slot per organization,
  so a customer asking for shipping costs and the nightly product sync cannot
  push the account over the limit together.
- **Errors.** CJ answers HTTP 200 with its own `code`; anything but 200 is
  raised as CjApiError with CJ's message, which the admin screens show.

Docs: https://developers.cjdropshipping.com/en/api/api2/
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.domains.cj_dropshipping.models import CjSettings

logger = logging.getLogger(__name__)

BASE_URL = "https://developers.cjdropshipping.com/api2.0/v1"
TIMEOUT_SECONDS = 40
#: Slightly over one second between calls of the same account.
MIN_INTERVAL_MS = 1100
#: CJ codes meaning "this token is not good any more".
TOKEN_ERROR_CODES = {1600001, 1600003}

_redis_client: redis.Redis | None = None


class CjApiError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class CjNotConfiguredError(CjApiError):
    pass


def reset_redis() -> None:
    """Celery tasks run each job in a new event loop (asyncio.run): a client
    made in a previous loop cannot be reused there."""
    global _redis_client
    _redis_client = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis_client


async def _wait_for_slot(organization_id: uuid.UUID) -> None:
    """One call per MIN_INTERVAL_MS per organization, across every process.
    If Redis is unavailable, falls back to simply waiting the interval."""
    key = f"cj:throttle:{organization_id}"
    try:
        client = _get_redis()
        for _ in range(240):  # up to ~60 s of queueing
            if await client.set(key, "1", nx=True, px=MIN_INTERVAL_MS):
                return
            await asyncio.sleep(0.25)
    except (redis.RedisError, RuntimeError):
        await asyncio.sleep(MIN_INTERVAL_MS / 1000)
        return
    raise CjApiError("CJ è molto occupato in questo momento: riprova tra un minuto.")


def _parse_cj_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone(UTC)
    except ValueError:
        return None


async def _raw_call(
    method: str, path: str, *, organization_id: uuid.UUID, token: str | None,
    params: dict | list | None = None, body: dict | None = None,
) -> dict:
    await _wait_for_slot(organization_id)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["CJ-Access-Token"] = token
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
            response = await http.request(method, BASE_URL + path, params=params, json=body, headers=headers)
    except httpx.HTTPError as exc:
        raise CjApiError(f"CJ non risponde ({type(exc).__name__}). Riprova tra poco.") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise CjApiError(f"Risposta non valida da CJ (HTTP {response.status_code}).") from exc
    if response.status_code == 429:
        raise CjApiError("Troppe richieste a CJ: riprova tra qualche secondo.", code=429)
    return payload


async def _fetch_tokens(db: AsyncSession, settings: CjSettings) -> str:
    if not settings.api_key:
        raise CjNotConfiguredError("Inserisci la chiave API di CJ nelle impostazioni di Shop Lial Partner.")
    now = utcnow()
    payload = None
    if settings.refresh_token and settings.refresh_token_expires_at and settings.refresh_token_expires_at > now:
        payload = await _raw_call(
            "POST", "/authentication/refreshAccessToken", organization_id=settings.organization_id, token=None,
            body={"refreshToken": settings.refresh_token},
        )
        if payload.get("code") != 200:
            payload = None
    if payload is None:
        payload = await _raw_call(
            "POST", "/authentication/getAccessToken", organization_id=settings.organization_id, token=None,
            body={"apiKey": settings.api_key},
        )
    if payload.get("code") != 200 or not payload.get("data"):
        settings.access_token = settings.refresh_token = None
        await db.commit()
        raise CjApiError(
            f"CJ ha rifiutato la chiave API: {payload.get('message') or 'errore sconosciuto'}", code=payload.get("code")
        )
    data = payload["data"]
    settings.access_token = data.get("accessToken")
    settings.refresh_token = data.get("refreshToken") or settings.refresh_token
    settings.access_token_expires_at = _parse_cj_date(data.get("accessTokenExpiryDate")) or now + timedelta(days=170)
    settings.refresh_token_expires_at = _parse_cj_date(data.get("refreshTokenExpiryDate")) or now + timedelta(days=170)
    if data.get("openId") is not None:
        settings.open_id = str(data["openId"])
    settings.updated_at = now
    await db.commit()
    return settings.access_token


async def _token(db: AsyncSession, settings: CjSettings) -> str:
    # Renewed a day early, so a token never expires in the middle of a checkout.
    if (
        settings.access_token
        and settings.access_token_expires_at
        and settings.access_token_expires_at > utcnow() + timedelta(days=1)
    ):
        return settings.access_token
    return await _fetch_tokens(db, settings)


async def call(
    db: AsyncSession, settings: CjSettings, method: str, path: str,
    *, params: dict | list | None = None, body: dict | None = None,
):
    """One authenticated CJ call; returns `data`. Raises CjApiError."""
    token = await _token(db, settings)
    payload = await _raw_call(
        method, path, organization_id=settings.organization_id, token=token, params=params, body=body
    )
    if payload.get("code") in TOKEN_ERROR_CODES:
        settings.access_token = None
        await db.commit()
        token = await _fetch_tokens(db, settings)
        payload = await _raw_call(
            method, path, organization_id=settings.organization_id, token=token, params=params, body=body
        )
    if payload.get("code") != 200:
        message = payload.get("message") or "errore sconosciuto"
        logger.warning("CJ %s %s failed: %s %s", method, path, payload.get("code"), message)
        raise CjApiError(f"CJ: {message}", code=payload.get("code"))
    return payload.get("data")


# --- Endpoints ---------------------------------------------------------------------------------


async def get_balance(db: AsyncSession, settings: CjSettings) -> dict:
    return await call(db, settings, "GET", "/shopping/pay/getBalance") or {}


async def get_categories(db: AsyncSession, settings: CjSettings) -> list:
    return await call(db, settings, "GET", "/product/getCategory") or []


async def search_products(
    db: AsyncSession, settings: CjSettings, *, keyword: str | None, page: int, size: int,
    category_id: str | None = None, min_price: float | None = None, max_price: float | None = None,
    free_shipping: bool = False, country_code: str | None = None,
) -> dict:
    params: list[tuple[str, str | int | float]] = [("page", page), ("size", size)]
    if keyword:
        params.append(("keyWord", keyword))
    if category_id:
        params.append(("categoryId", category_id))
    if min_price is not None:
        params.append(("startSellPrice", min_price))
    if max_price is not None:
        params.append(("endSellPrice", max_price))
    if free_shipping:
        params.append(("addMarkStatus", 1))
    if country_code:
        params.append(("countryCode", country_code))
    params.append(("features", "enable_category"))
    return await call(db, settings, "GET", "/product/listV2", params=params) or {}


async def get_product(db: AsyncSession, settings: CjSettings, *, pid: str) -> dict:
    data = await call(db, settings, "GET", "/product/query", params={"pid": pid})
    if not data:
        raise CjApiError("Prodotto non trovato su CJ.")
    return data


async def get_variant_stock(db: AsyncSession, settings: CjSettings, *, vid: str) -> list:
    return await call(db, settings, "GET", "/product/stock/queryByVid", params={"vid": vid}) or []


async def freight(
    db: AsyncSession, settings: CjSettings, *, vid: str, quantity: int, origin: str, destination: str,
    zip_code: str | None = None,
) -> list[dict]:
    body = {
        "startCountryCode": origin,
        "endCountryCode": destination,
        "products": [{"quantity": quantity, "vid": vid}],
    }
    if zip_code:
        body["zip"] = zip_code
    return await call(db, settings, "POST", "/logistic/freightCalculate", body=body) or []


async def create_order(db: AsyncSession, settings: CjSettings, *, body: dict) -> dict:
    return await call(db, settings, "POST", "/shopping/order/createOrderV2", body=body) or {}


async def pay_balance(db: AsyncSession, settings: CjSettings, *, cj_order_id: str) -> None:
    await call(db, settings, "POST", "/shopping/pay/payBalance", body={"orderId": cj_order_id})


async def get_orders(db: AsyncSession, settings: CjSettings, *, cj_order_ids: list[str]) -> list:
    return await call(db, settings, "POST", "/shopping/order/getOrderDetailBatch", body={"orderIds": cj_order_ids}) or []


async def get_order(db: AsyncSession, settings: CjSettings, *, cj_order_id: str) -> dict:
    return await call(db, settings, "GET", "/shopping/order/getOrderDetail", params={"orderId": cj_order_id}) or {}
