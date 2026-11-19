"""Explicitly allowlisted test connector. No user-entered URLs, tokens or redirects."""
from decimal import Decimal, InvalidOperation
import httpx

from ..parsing import OfferData

API_URL = "https://dummyjson.com/products"
SOURCE_NAME = "DummyJSON Demo"
BATCH_SIZE = 20


class ConnectorError(Exception):
    pass


def fetch_products() -> list[dict]:
    try:
        with httpx.Client(timeout=10.0, follow_redirects=False) as client:
            response = client.get(API_URL, params={"limit": BATCH_SIZE, "skip": 0})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ConnectorError("Die Demo-API ist gerade nicht erreichbar oder liefert ungültiges JSON.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
        raise ConnectorError("Die API-Antwort besitzt kein gültiges Produktarray.")
    rows = payload["products"]
    if len(rows) > BATCH_SIZE or any(not isinstance(row, dict) for row in rows):
        raise ConnectorError("Die API hat unerwartete Produktdaten zurückgegeben.")
    return rows


def normalize_product(row: dict) -> OfferData:
    # DummyJSON documents a number for price but not an ISO currency code.
    # XXX means no currency. NEVER silently convert these demo values to EUR.
    id_value = row.get("id")
    if type(id_value) is not int or id_value <= 0:
        raise ValueError("Produkt-ID muss eine positive ganze Zahl sein.")
    raw_price = row.get("price")
    if isinstance(raw_price, bool) or raw_price is None:
        raise ValueError("Preis fehlt oder ist ungültig.")
    try:
        amount = Decimal(str(raw_price))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Preis ist keine gültige Dezimalzahl.") from exc
    return OfferData(
        external_id=str(id_value), name=row.get("title"),
        price_amount=amount, currency="XXX", stock=row.get("stock"),
    )
