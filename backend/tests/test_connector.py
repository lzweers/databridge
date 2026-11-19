import os
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = "sqlite:///./databridge-test.db"
from app.main import app
from app.database import Base, engine
from app.connectors import dummyjson
from app.migrations import upgrade_legacy_schema


@pytest.fixture(autouse=True)
def reset_database():
    if engine.dialect.name != "sqlite":
        raise RuntimeError("BLOCKED: destructive test fixture requires SQLite")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    if engine.dialect.name != "sqlite":
        raise RuntimeError("BLOCKED: destructive test fixture requires SQLite")
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def api_rows(monkeypatch):
    products = [
        {"id": 1001, "title": "Demo product A", "price": 11.25, "stock": 4},
        {"id": 1002, "title": "Demo product B", "price": 22.5, "stock": 0},
        {"id": 1003, "title": "Bad product", "price": -42.0, "stock": 3},
        {"id": 1004, "title": "Another product", "price": 9.99, "stock": 10},
        {"id": 1001, "title": "Duplicate product", "price": 11.25, "stock": 4},
    ]
    monkeypatch.setattr(dummyjson, "fetch_products", lambda: products)
    return products


def test_api_preview_and_import_with_shared_pipeline(api_rows):
    with TestClient(app) as client:
        preview = client.get("/api/connectors/dummyjson/preview")
        assert preview.status_code == 200
        assert preview.json()["total_rows"] == 5
        result = client.post("/api/imports/dummyjson")
        assert result.status_code == 200, result.text
        assert (result.json()["inserted"], result.json()["rejected"]) == (3, 2)
        offers = client.get("/api/offers").json()
        assert len(offers) == 3
        assert all(offer["currency"] == "XXX" for offer in offers)
        assert all("price_eur" not in offer for offer in offers)
        issues = client.get(f"/api/imports/{result.json()['id']}/issues").json()
        assert {issue["row_number"] for issue in issues} == {3, 5}
        assert client.get("/api/summary").json()["sources"] == 1


def test_repeated_api_import_does_not_duplicate_offers(api_rows):
    with TestClient(app) as client:
        assert client.post("/api/imports/dummyjson").json()["inserted"] == 3
        second = client.post("/api/imports/dummyjson").json()
        assert (second["inserted"], second["unchanged"], second["rejected"]) == (0, 3, 2)
        assert client.get("/api/summary").json()["offers"] == 3


def test_connector_error_is_reported_without_partial_import(monkeypatch):
    def broken():
        raise dummyjson.ConnectorError("API nicht verfügbar")
    monkeypatch.setattr(dummyjson, "fetch_products", broken)
    with TestClient(app) as client:
        response = client.post("/api/imports/dummyjson")
        assert response.status_code == 502
        assert client.get("/api/summary").json()["imports"] == 0


def test_legacy_currency_migration_preserves_existing_offer(tmp_path):
    old_engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old_engine.begin() as conn:
        conn.execute(text("CREATE TABLE supplier_offers (id INTEGER PRIMARY KEY, "
                          "source_name VARCHAR(100), external_id VARCHAR(120), "
                          "name VARCHAR(255), price_eur NUMERIC(12,2), "
                          "stock INTEGER, last_import_id INTEGER)"))
        conn.execute(text("INSERT INTO supplier_offers VALUES "
                          "(1, 'Lieferant A', 'SKU-1', 'USB Hub', 19.90, 3, 1)"))
    upgrade_legacy_schema(old_engine)
    upgrade_legacy_schema(old_engine)  # safe on repeated app starts
    with old_engine.connect() as conn:
        cols = {x["name"] for x in inspect(conn).get_columns("supplier_offers")}
        assert "price_amount" in cols and "currency" in cols and "price_eur" not in cols
        row = conn.execute(text("SELECT price_amount, currency FROM supplier_offers WHERE id=1")).one()
        assert str(row[0]) == "19.9" and row[1] == "EUR"
