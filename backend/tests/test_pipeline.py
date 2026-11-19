import io
import os
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Set before importing app.database / engine.
os.environ["DATABASE_URL"] = "sqlite:///./databridge-test.db"
from app.main import app
from app.database import Base, engine


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


def upload(client, csv_bytes: bytes, name="Lieferant A"):
    return client.post("/api/imports/upload", data={
        "source_name": name,
        "mapping_json": '{"external_id":"ArtikelNr","name":"Artikelname","price_eur":"Preis","stock":"Menge"}'
    }, files={"file": ("input.csv", io.BytesIO(csv_bytes), "text/csv")})


def test_preview_with_semicolon_and_german_price():
    with TestClient(app) as client:
        response = client.post("/api/imports/preview", files={"file": (
            "input.csv", b"ArtikelNr;Artikelname;Preis;Menge\n1042;USB-C Hub;39,90 EUR;18\n", "text/csv")})
    assert response.status_code == 200
    assert response.json()["total_rows"] == 1


def test_import_rejects_invalid_rows_and_preserves_idempotency():
    data = ("ArtikelNr;Artikelname;Preis;Menge\n"
            "A-1;USB-C Hub;39,90;18\n"
            "A-2;HDMI Adapter;12,99;-5\n"
            "A-3;Thunderbolt Dock;49,99;4\n").encode()
    with TestClient(app) as client:
        first = upload(client, data)
        assert first.status_code == 200, first.text
        assert (first.json()["inserted"], first.json()["rejected"]) == (2, 1)
        assert client.get("/api/summary").json()["offers"] == 2
        again = upload(client, data)
        assert again.status_code == 200, again.text
        assert (again.json()["unchanged"], again.json()["rejected"]) == (2, 1)
        assert client.get("/api/summary").json()["offers"] == 2
        issues = client.get(f"/api/imports/{first.json()['id']}/issues").json()
        assert issues[0]["row_number"] == 3


def test_updating_an_offer_does_not_add_a_second_offer():
    one = b"ArtikelNr;Artikelname;Preis;Menge\nA-1;USB-C Hub;39,90;18\n"
    two = b"ArtikelNr;Artikelname;Preis;Menge\nA-1;USB-C Hub;42,50;18\n"
    with TestClient(app) as client:
        assert upload(client, one).json()["inserted"] == 1
        assert upload(client, two).json()["updated"] == 1
        assert client.get("/api/summary").json()["offers"] == 1


def test_invalid_mapping_is_rejected():
    with TestClient(app) as client:
        response = client.post("/api/imports/upload", data={
            "source_name": "A", "mapping_json": '{"external_id":"BAD","name":"Artikelname","price_eur":"Preis"}'
        }, files={"file": ("a.csv", b"ArtikelNr;Artikelname;Preis\nA;Test;1,99\n", "text/csv")})
        assert response.status_code == 422
