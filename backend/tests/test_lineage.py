"""Data lineage integration tests for CSV and REST API paths."""
import io
import os
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = "sqlite:///./databridge-test.db"
from app.main import app
from app.database import Base, engine, SessionLocal
from app.models import ImportRun, SupplierOffer
from app.connectors import dummyjson


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


def upload(client, rows: str):
    return client.post('/api/imports/upload', data={
        'source_name': 'Lieferant A',
        'mapping_json': '{"external_id":"ArtikelNr","name":"Artikelname","price_eur":"Preis","stock":"Menge"}',
    }, files={'file': ('products.csv', io.BytesIO(rows.encode('utf-8')), 'text/csv')})


def test_lineage_exposes_original_normalized_and_before_after():
    header = 'ArtikelNr;Artikelname;Preis;Menge\n'
    with TestClient(app) as client:
        first = upload(client, header + 'A-1;USB Hub;39,90 €;18\n').json()
        second = upload(client, header + 'A-1;USB Hub;39,90 €;18\n').json()
        third = upload(client, header + 'A-1;USB Hub;42,50 €;13\n').json()
        assert [first['inserted'], second['unchanged'], third['updated']] == [1, 1, 1]
        offers = client.get('/api/offers').json()
        assert len(offers) == 1
        info = client.get(f"/api/offers/{offers[0]['id']}/lineage")
        assert info.status_code == 200, info.text
        doc = info.json()
        assert doc['offer']['last_changed_import_id'] == third['id']
        assert [e['action'] for e in doc['events']] == ['updated', 'unchanged', 'inserted']
        update = doc['events'][0]
        assert update['raw']['Preis'] == '42,50 €'
        assert update['before']['price_amount'] == '39.90'
        assert update['after']['price_amount'] == '42.50'
        assert set(update['changed_fields']) == {'price_amount', 'stock'}
        assert doc['events'][1]['changed_fields'] == []
        assert doc['events'][2]['before'] is None
        assert doc['events'][2]['after']['price_amount'] == '39.90'


def test_inspector_shows_rejections_and_preserves_raw_data():
    content = ('ArtikelNr;Artikelname;Preis;Menge\n'
               'A-1;USB Hub;39,90;18\n'
               'A-2;Wrong stock;9,99;-1\n')
    with TestClient(app) as client:
        run = upload(client, content).json()
        response = client.get(f"/api/imports/{run['id']}/rows?offset=0&limit=50")
        assert response.status_code == 200
        rows = response.json()['rows']
        assert [r['action'] for r in rows] == ['inserted', 'rejected']
        assert rows[0]['normalized']['stock'] == 18
        assert rows[1]['raw']['Menge'] == '-1'
        assert rows[1]['normalized'] is None
        assert rows[1]['issues'][0]['field'] == 'stock'
        assert rows[1]['offer_id'] is None
        assert client.get(f"/api/imports/{run['id']}/rows?limit=101").status_code == 422
        assert client.get('/api/imports/9999/rows').status_code == 404
        assert client.get('/api/offers/9999/lineage').status_code == 404


def test_api_connector_uses_same_audit_history(monkeypatch):
    monkeypatch.setattr(dummyjson, 'fetch_products', lambda: [
        {'id': 7, 'title': 'Demo test', 'price': 4.25, 'stock': 1}
    ])
    with TestClient(app) as client:
        run = client.post('/api/imports/dummyjson').json()
        response = client.get(f"/api/imports/{run['id']}/rows")
        assert response.status_code == 200
        row = response.json()['rows'][0]
        assert row['raw']['price'] == 4.25
        assert row['normalized']['price_amount'] == '4.25'
        assert row['normalized']['currency'] == 'XXX'
        offer = client.get('/api/offers').json()[0]
        assert client.get(f"/api/offers/{offer['id']}/lineage").json()['events'][0]['raw']['id'] == 7


def test_offer_created_before_v03_is_not_given_fake_history():
    # Emulates a stateful v0.2 PostgreSQL volume: offer exists, no audit events.
    with SessionLocal() as db:
        run = ImportRun(source_name='Legacy', filename='legacy.csv', total_rows=1)
        db.add(run)
        db.flush()
        offer = SupplierOffer(source_name='Legacy', external_id='OLD', name='Old offer',
                              price_amount=19.9, currency='EUR', stock=2, last_import_id=run.id)
        db.add(offer)
        db.commit()
        offer_id = offer.id
    with TestClient(app) as client:
        doc = client.get(f'/api/offers/{offer_id}/lineage').json()
        assert doc['events'] == []
        assert doc['history_available_since'] == 'v0.3'


def test_schema_addition_keeps_preexisting_v02_records(tmp_path):
    """A v0.2 layout can gain the v0.3 event table without dropping offers."""
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import Session
    from app.models import OfferEvent

    temp_engine = create_engine(f"sqlite:///{tmp_path / 'upgrade.db'}")
    old_tables = [table for table in Base.metadata.sorted_tables if table.name != 'offer_events']
    Base.metadata.create_all(temp_engine, tables=old_tables)
    with Session(temp_engine) as db:
        run = ImportRun(source_name='A', filename='old.csv', total_rows=1)
        db.add(run)
        db.flush()
        db.add(SupplierOffer(source_name='A', external_id='123', name='Historical',
                             price_amount=12.34, currency='EUR', stock=3,
                             last_import_id=run.id))
        db.commit()
    Base.metadata.create_all(temp_engine)  # same behavior as app startup
    assert 'offer_events' in inspect(temp_engine).get_table_names()
    with Session(temp_engine) as db:
        data = db.scalars(select(SupplierOffer)).all()
        assert len(data) == 1
        assert data[0].name == 'Historical'
        assert db.scalars(select(OfferEvent)).all() == []
