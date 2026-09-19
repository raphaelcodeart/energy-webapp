"""The Shopify Admin GraphQL API, as this app uses it.

Every request goes through `call()` -- the one door tests replace:

- **Authentication.** A custom app's Admin API access token (`shpat_...`),
  sent as X-Shopify-Access-Token. No token exchange, nothing to refresh.
- **Rate limit.** Shopify's leaky-bucket cost limit: a THROTTLED answer is
  retried after a short wait, a few times.
- **Errors.** Transport problems, HTTP errors, top-level `errors` and the
  mutations' `userErrors` are all raised as ShopifyApiError with a message
  the admin screens show as is.

Docs: https://shopify.dev/docs/api/admin-graphql
"""

import asyncio
import logging

import httpx

from app.domains.shopify_dropshipping.models import ShopifySettings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30
THROTTLE_RETRIES = 4


class ShopifyApiError(Exception):
    def __init__(self, message: str, kind: str = "FATAL"):
        super().__init__(message)
        #: TEMPORARY / AUTHENTICATION / VALIDATION / FATAL, see models.ERROR_KINDS
        self.kind = kind


class ShopifyNotConfiguredError(ShopifyApiError):
    def __init__(self, message: str = "Negozio Shopify non configurato: inserisci dominio e token."):
        super().__init__(message, kind="AUTHENTICATION")


def normalize_domain(value: str | None) -> str | None:
    """"https://Mio-Negozio.myshopify.com/admin" -> "mio-negozio.myshopify.com"."""
    if not value:
        return None
    domain = value.strip().lower()
    for prefix in ("https://", "http://"):
        domain = domain.removeprefix(prefix)
    domain = domain.split("/")[0]
    if domain and "." not in domain:
        domain = f"{domain}.myshopify.com"
    return domain or None


async def _raw_call(url: str, token: str, payload: dict) -> httpx.Response:
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
        return await http.post(
            url, json=payload, headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        )


async def call(settings: ShopifySettings, query: str, variables: dict | None = None) -> dict:
    """Runs one GraphQL operation and returns its `data`."""
    if not settings.shop_domain or not settings.access_token:
        raise ShopifyNotConfiguredError()
    url = f"https://{settings.shop_domain}/admin/api/{settings.api_version}/graphql.json"
    payload = {"query": query, "variables": variables or {}}
    for attempt in range(THROTTLE_RETRIES + 1):
        try:
            response = await _raw_call(url, settings.access_token, payload)
        except httpx.HTTPError as exc:
            raise ShopifyApiError(f"Shopify non risponde ({type(exc).__name__}). Riprova tra poco.", "TEMPORARY") from exc
        if response.status_code in (401, 403):
            raise ShopifyApiError(
                "Shopify ha rifiutato il token: controlla il token e i permessi (scope) dell'app.", "AUTHENTICATION"
            )
        if response.status_code == 404:
            raise ShopifyApiError("Negozio Shopify non trovato: controlla il dominio .myshopify.com.", "AUTHENTICATION")
        if response.status_code == 429 or response.status_code >= 500:
            if attempt < THROTTLE_RETRIES:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            raise ShopifyApiError(f"Shopify occupato (HTTP {response.status_code}). Riprova tra poco.", "TEMPORARY")
        if response.status_code != 200:
            raise ShopifyApiError(f"Shopify: HTTP {response.status_code}.", "FATAL")
        body = response.json()
        errors = body.get("errors")
        if errors:
            throttled = any(
                (e.get("extensions") or {}).get("code") == "THROTTLED" for e in errors if isinstance(e, dict)
            )
            if throttled and attempt < THROTTLE_RETRIES:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            message = "; ".join(e.get("message", str(e)) if isinstance(e, dict) else str(e) for e in errors)
            if throttled:
                raise ShopifyApiError(f"Shopify: troppe richieste ({message}).", "TEMPORARY")
            if "access" in message.lower() or "scope" in message.lower():
                raise ShopifyApiError(f"Shopify: permesso mancante -- {message}", "AUTHENTICATION")
            raise ShopifyApiError(f"Shopify: {message}", "VALIDATION")
        return body.get("data") or {}
    raise ShopifyApiError("Shopify occupato. Riprova tra poco.", "TEMPORARY")


def _user_errors(result: dict | None) -> None:
    errors = (result or {}).get("userErrors") or []
    if errors:
        raise ShopifyApiError(
            "Shopify: " + "; ".join(e.get("message", "") for e in errors), "VALIDATION"
        )


# --- Operazioni -------------------------------------------------------------------------------

SHOP_QUERY = "query { shop { name currencyCode myshopifyDomain } }"

_PRODUCT_FIELDS = """
    id title handle vendor status descriptionHtml
    featuredImage { url }
    images(first: 20) { nodes { url } }
    variants(first: 100) {
      nodes {
        id title sku price inventoryQuantity
        image { url }
        inventoryItem { tracked unitCost { amount currencyCode } }
      }
    }
"""

PRODUCTS_QUERY = (
    "query($first: Int!, $after: String, $query: String) {"
    " products(first: $first, after: $after, query: $query, sortKey: UPDATED_AT, reverse: true) {"
    "  pageInfo { hasNextPage endCursor }"
    "  nodes {" + _PRODUCT_FIELDS + "} } }"
)

PRODUCT_QUERY = "query($id: ID!) { product(id: $id) {" + _PRODUCT_FIELDS + "} }"

DRAFT_CREATE = """
mutation($input: DraftOrderInput!) {
  draftOrderCreate(input: $input) { draftOrder { id name } userErrors { field message } }
}
"""

DRAFT_COMPLETE = """
mutation($id: ID!) {
  draftOrderComplete(id: $id, paymentPending: false) {
    draftOrder { id order { id name } } userErrors { field message }
  }
}
"""

DRAFT_QUERY = "query($id: ID!) { draftOrder(id: $id) { id status order { id name } } }"

ORDERS_BY_TAG = """
query($query: String!) {
  orders(first: 5, query: $query) { nodes { id name tags } }
}
"""

ORDER_QUERY = """
query($id: ID!) {
  order(id: $id) {
    id name cancelledAt displayFulfillmentStatus
    fulfillments(first: 10) {
      status displayStatus deliveredAt createdAt
      trackingInfo(first: 5) { number url company }
    }
  }
}
"""


async def shop_info(settings: ShopifySettings) -> dict:
    return (await call(settings, SHOP_QUERY)).get("shop") or {}


async def list_products(settings: ShopifySettings, *, query: str | None, after: str | None, first: int = 24) -> dict:
    data = await call(settings, PRODUCTS_QUERY, {"first": first, "after": after, "query": query})
    return data.get("products") or {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}


async def get_product(settings: ShopifySettings, *, product_id: str) -> dict | None:
    return (await call(settings, PRODUCT_QUERY, {"id": product_id})).get("product")


async def create_draft_order(settings: ShopifySettings, *, draft_input: dict) -> dict:
    result = (await call(settings, DRAFT_CREATE, {"input": draft_input})).get("draftOrderCreate")
    _user_errors(result)
    draft = (result or {}).get("draftOrder")
    if not draft or not draft.get("id"):
        raise ShopifyApiError("Shopify non ha creato la bozza d'ordine.", "VALIDATION")
    return draft


async def complete_draft_order(settings: ShopifySettings, *, draft_id: str) -> dict:
    """Returns the created order {id, name}."""
    result = (await call(settings, DRAFT_COMPLETE, {"id": draft_id})).get("draftOrderComplete")
    _user_errors(result)
    order = ((result or {}).get("draftOrder") or {}).get("order")
    if not order or not order.get("id"):
        raise ShopifyApiError("Shopify non ha completato l'ordine.", "TEMPORARY")
    return order


async def get_draft_order(settings: ShopifySettings, *, draft_id: str) -> dict | None:
    return (await call(settings, DRAFT_QUERY, {"id": draft_id})).get("draftOrder")


async def find_orders_by_tag(settings: ShopifySettings, *, tag: str) -> list[dict]:
    data = await call(settings, ORDERS_BY_TAG, {"query": f"tag:'{tag}'"})
    return ((data.get("orders") or {}).get("nodes")) or []


async def get_order(settings: ShopifySettings, *, order_id: str) -> dict | None:
    return (await call(settings, ORDER_QUERY, {"id": order_id})).get("order")
