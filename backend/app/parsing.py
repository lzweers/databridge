import csv
import io
import re
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, ValidationError

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_ROWS = 20_000
REQUIRED_FIELDS = ("external_id", "name", "price_eur")


class OfferData(BaseModel):
    external_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=2, max_length=255)
    price_amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    stock: int | None = Field(default=None, ge=0)


def read_csv(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Die CSV muss UTF-8-codiert sein.") from exc
    if not text.strip():
        raise ValueError("Die CSV-Datei ist leer.")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if ";" in text.splitlines()[0] else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter, strict=True)
    headers = reader.fieldnames or []
    if not headers or any(not h or not h.strip() for h in headers) or len(set(headers)) != len(headers):
        raise ValueError("CSV-Spaltennamen fehlen oder sind doppelt vorhanden.")
    rows = []
    try:
        for row in reader:
            if len(rows) >= MAX_ROWS:
                raise ValueError(f"Maximal {MAX_ROWS} Datenzeilen pro Import erlaubt.")
            if None in row:
                raise ValueError(f"Datenzeile {len(rows)+2} hat mehr Spalten als die Kopfzeile.")
            rows.append({k: (v or "").strip() for k, v in row.items()})
    except csv.Error as exc:
        raise ValueError(f"Fehlerhaftes CSV-Format: {exc}") from exc
    return headers, rows


def parse_price(value: str) -> Decimal:
    # Accept 39,90 €, €39.90, 1.234,56, 1,234.56, 39.90
    text = value.strip().replace("€", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+[,]\d{2}", text):
        text = text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:,\d{3})+[.]\d{2}", text):
        text = text.replace(",", "")
    elif re.fullmatch(r"\d+(?:[.,]\d{1,2})?", text):
        text = text.replace(",", ".")
    else:
        raise ValueError("Preis muss ein EUR-Betrag sein (z. B. 39,90 €).")
    return Decimal(text)


def normalize(row: dict[str, Any], mapping: dict[str, str]) -> OfferData:
    external_id = str(row.get(mapping["external_id"], "")).strip()
    name = str(row.get(mapping["name"], "")).strip()
    price = parse_price(str(row.get(mapping["price_eur"], "")))
    raw_stock = str(row.get(mapping.get("stock", ""), "")).strip()
    if raw_stock and not re.fullmatch(r"-?\d+", raw_stock):
        raise ValueError("Lagerbestand muss eine ganze Zahl sein.")
    return OfferData(external_id=external_id, name=name, price_amount=price, currency="EUR", stock=int(raw_stock) if raw_stock else None)


def validate_mapping(mapping: dict, headers: list[str]):
    for key in REQUIRED_FIELDS:
        if key not in mapping or mapping[key] not in headers:
            raise ValueError(f"Pflichtfeld '{key}' ist keiner CSV-Spalte zugeordnet.")
    selected = [value for value in mapping.values() if value]
    if len(set(selected)) != len(selected):
        raise ValueError("Eine CSV-Spalte kann nicht gleichzeitig mehreren Zielfeldern zugeordnet werden.")
    if any(value not in headers for value in selected):
        raise ValueError("Eine ausgewählte Quellspalte existiert nicht.")
    if any(key not in (*REQUIRED_FIELDS, "stock") for key in mapping):
        raise ValueError("Unbekanntes Zielfeld im Mapping.")


def issue_for_error(exc: Exception):
    if isinstance(exc, ValidationError):
        errors = exc.errors()
        first = errors[0]
        return str(first["loc"][0]) if first["loc"] else "row", "VALIDATION_ERROR", first["msg"]
    message = str(exc)
    field = "price_eur" if "Preis" in message else "stock" if "Lagerbestand" in message else "row"
    return field, "INVALID_VALUE", message
