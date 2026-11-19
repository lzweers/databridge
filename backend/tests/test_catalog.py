"""Catalog integration tests: only a fresh in-memory SQLite database is mutated."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import ImportRun, SupplierOffer


@pytest.fixture
def catalog_client():
    isolated_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    assert isolated_engine.dialect.name == "sqlite"
    Base.metadata.create_all(isolated_engine)
    with Session(isolated_engine) as session:
        run = ImportRun(source_name="Fixture", filename="fixture.csv", status="completed", total_rows=6)
        session.add(run)
        session.flush()
        sample = [
            ("Lieferant A", "A-1", "USB-C Hub", 18),
            ("Lieferant A", "A-2", "HDMI Adapter", 35),
            ("Lieferant B", "B-3", "USB-C Kabel", None),
            ("Lieferant B", "B-4", "USB% Sonderangebot", 7),
            ("Lieferant B", "B-USB5", "Anderes Produkt", 0),
            ("Lieferant C", "C-6", "USB-C Hub", 4),
        ]
        for source, external_id, name, stock in sample:
            session.add(SupplierOffer(
                source_name=source, external_id=external_id,
                name=name, price_amount=Decimal("12.99"), currency="EUR",
                stock=stock, last_import_id=run.id,
            ))
        session.commit()

    def test_get_db():
        with Session(isolated_engine) as db:
            yield db

    app.dependency_overrides[get_db] = test_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        isolated_engine.dispose()


def test_search_by_name_and_external_id(catalog_client):
    response = catalog_client.get("/api/catalog/offers", params={"search": "usb-c"})
    assert response.status_code == 200
    assert response.json()["total"] == 3
    response = catalog_client.get("/api/catalog/offers", params={"search": "b-usb5"})
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["name"] == "Anderes Produkt"


def test_source_filter_and_sources_remain_available(catalog_client):
    data = catalog_client.get("/api/catalog/offers", params={"source": "Lieferant A"}).json()
    assert data["total"] == 2
    assert {item["source_name"] for item in data["items"]} == {"Lieferant A"}
    assert data["sources"] == ["Lieferant A", "Lieferant B", "Lieferant C"]


def test_stable_pagination_and_sorting(catalog_client):
    first = catalog_client.get("/api/catalog/offers", params={"sort": "stock_asc", "limit": 2}).json()
    second = catalog_client.get("/api/catalog/offers", params={"sort": "stock_asc", "limit": 2, "offset": 2}).json()
    last = catalog_client.get("/api/catalog/offers", params={"sort": "stock_asc", "limit": 2, "offset": 4}).json()
    assert first["total"] == second["total"] == 6
    assert [x["stock"] for x in first["items"] + second["items"] + last["items"]] == [0, 4, 7, 18, 35, None]
    assert len({x["id"] for x in first["items"] + second["items"] + last["items"]}) == 6


def test_literal_wildcard_search_and_invalid_parameters(catalog_client):
    assert catalog_client.get("/api/catalog/offers", params={"search": "%"}).json()["total"] == 1
    assert catalog_client.get("/api/catalog/offers", params={"search": "_"}).json()["total"] == 0
    assert catalog_client.get("/api/catalog/offers", params={"sort": "DROP TABLE supplier_offers"}).status_code == 422
    assert catalog_client.get("/api/catalog/offers", params={"limit": 101}).status_code == 422
    assert catalog_client.get("/api/catalog/offers", params={"offset": -1}).status_code == 422


def test_csv_export_matches_full_filtered_catalog_not_just_page(catalog_client):
    import csv
    import io

    # Five offers match on the name OR external ID, but a one-item page shows only one.
    params = {"search": "USB", "sort": "stock_asc"}
    page = catalog_client.get("/api/catalog/offers", params={**params, "limit": 1}).json()
    assert page["total"] == 5
    assert len(page["items"]) == 1
    response = catalog_client.get("/api/catalog/export.csv", params=params)
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")  # Excel-friendly UTF-8 BOM
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert rows[0] == ["Produkt", "Externe ID", "Datenquelle", "Preis", "Währung", "Bestand"]
    assert len(rows) == 6
    assert [row[5] for row in rows[1:]] == ["0", "4", "7", "18", ""]


def test_csv_export_filters_source_and_wildcard_search(catalog_client):
    import csv
    import io

    response = catalog_client.get("/api/catalog/export.csv", params={"source": "Lieferant B", "search": "%"})
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert len(rows) == 2
    assert rows[1][0] == "USB% Sonderangebot"
    assert rows[1][2] == "Lieferant B"


def test_csv_export_neutralizes_spreadsheet_formulas(catalog_client):
    import csv
    import io

    # Test through the HTTP endpoint, not only by calling the helper directly.
    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        db.add(SupplierOffer(
            source_name="@Supplier", external_id="+2+2", name=" =1+1",
            price_amount=Decimal("2.50"), currency="XXX", stock=None,
            last_import_id=1,
        ))
        db.commit()
    finally:
        db_generator.close()

    response = catalog_client.get("/api/catalog/export.csv", params={"search": "2+2"})
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert len(rows) == 2
    assert rows[1][:3] == ["' =1+1", "'+2+2", "'@Supplier"]
    assert rows[1][4] == "Unbekannt"  # Unknown currencies are not mislabeled as EUR.
    assert rows[1][5] == ""


def test_csv_export_invalid_query_rejected(catalog_client):
    response = catalog_client.get("/api/catalog/export.csv", params={"sort": "DROP TABLE supplier_offers"})
    assert response.status_code == 422
