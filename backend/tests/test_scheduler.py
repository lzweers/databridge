"""Scheduling tests exercise the same FastAPI and persistent DB used by the worker."""
import os
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE_URL'] = 'sqlite:///./databridge-test.db'

from app.main import app
from app.database import Base, engine, SessionLocal
from app.models import ImportRun, SupplierOffer, PipelineSchedule, PipelineExecution
from app.scheduling import tick, claim_one, complete_attempt, utcnow
from app.connectors import dummyjson
from app import scheduling


@pytest.fixture(autouse=True)
def clean_db():
    if engine.dialect.name != "sqlite":
        raise RuntimeError("BLOCKED: destructive test fixture requires SQLite")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    if engine.dialect.name != "sqlite":
        raise RuntimeError("BLOCKED: destructive test fixture requires SQLite")
    Base.metadata.drop_all(bind=engine)


def setup_pipeline(client):
    response = client.put('/api/pipelines/dummyjson', json={"enabled": True, "interval_minutes": 5})
    assert response.status_code == 200, response.text
    return response.json()


def fake_rows():
    return [{"id": 123, "title": "USB Hub", "price": 39.5, "stock": 10}]


def test_scheduler_opt_in_input_validation_and_disable():
    with TestClient(app) as client:
        initial = client.get('/api/pipelines/dummyjson').json()
        assert initial['configured'] is False and initial['enabled'] is False
        assert client.get('/api/pipelines/dummyjson/executions').json() == []
        assert client.post('/api/pipelines/dummyjson/run-now').status_code == 409
        assert client.put('/api/pipelines/dummyjson', json={"enabled": True, "interval_minutes": 1}).status_code == 422
        assert client.put('/api/pipelines/dummyjson', json={"enabled": True, "interval_minutes": 1441}).status_code == 422
        enabled = setup_pipeline(client)
        assert enabled['next_run_at'] is not None
        assert enabled['last_attempt_at'] is None
        assert not tick()  # first automatic run is in the future
        disabled = client.put('/api/pipelines/dummyjson', json={"enabled": False, "interval_minutes": 5}).json()
        assert disabled['enabled'] is False and disabled['next_run_at'] is None
        assert not tick()


def test_scheduled_api_ingestion_reuses_data_lineage(monkeypatch):
    monkeypatch.setattr(dummyjson, 'fetch_products', fake_rows)
    with TestClient(app) as client:
        setup_pipeline(client)
        assert client.post('/api/pipelines/dummyjson/run-now').status_code == 200
        assert tick() is True
        assert tick() is False
        assert client.get('/api/summary').json()['offers'] == 1
        executions = client.get('/api/pipelines/dummyjson/executions').json()
        assert len(executions) == 1
        assert executions[0]['status'] == 'completed'
        assert executions[0]['import_id'] is not None
        rows = client.get(f"/api/imports/{executions[0]['import_id']}/rows").json()['rows']
        assert rows[0]['action'] == 'inserted'
        assert rows[0]['raw']['price'] == 39.5
        assert rows[0]['normalized']['currency'] == 'XXX'
        assert client.post('/api/pipelines/dummyjson/run-now').status_code == 200
        assert tick()
        assert client.get('/api/summary').json()['offers'] == 1
        later = client.get('/api/pipelines/dummyjson/executions').json()
        assert later[0]['status'] == 'completed'
        assert client.get(f"/api/imports/{later[0]['import_id']}/rows").json()['rows'][0]['action'] == 'unchanged'


def test_fetch_failure_is_logged_and_retried_without_partial_import(monkeypatch):
    class Down:
        count = 0
    calls = Down()

    def flaky():
        calls.count += 1
        if calls.count == 1:
            raise dummyjson.ConnectorError('Upstream antwortet nicht')
        return fake_rows()

    monkeypatch.setattr(dummyjson, 'fetch_products', flaky)
    with TestClient(app) as client:
        setup_pipeline(client)
        client.post('/api/pipelines/dummyjson/run-now')
        assert tick()
        failed = client.get('/api/pipelines/dummyjson').json()
        assert failed['status'] == 'failed'
        assert failed['consecutive_failures'] == 1
        assert 'Upstream' in failed['last_error']
        assert client.get('/api/summary').json()['imports'] == 0
        assert client.get('/api/pipelines/dummyjson/executions').json()[0]['status'] == 'failed'
        assert not tick()  # backoff prevents a tight retry loop
        due = datetime.fromisoformat(failed['next_run_at'])
        monkeypatch.setattr(scheduling, 'utcnow', lambda: due + timedelta(seconds=1))
        assert tick(due + timedelta(seconds=1))
        after = client.get('/api/pipelines/dummyjson').json()
        assert after['status'] == 'completed'
        assert after['consecutive_failures'] == 0
        assert after['last_error'] is None
        assert client.get('/api/summary').json()['offers'] == 1
        assert [x['status'] for x in client.get('/api/pipelines/dummyjson/executions').json()] == ['completed', 'failed']


def test_expired_lease_is_recorded_and_recovered():
    with TestClient(app) as client:
        setup_pipeline(client)
        client.post('/api/pipelines/dummyjson/run-now')
        start = utcnow()
        with SessionLocal() as db:
            claim = claim_one(db, start)
            assert claim is not None
            assert claim_one(db, start) is None
            assert claim_one(db, start + timedelta(seconds=121)) is None
        schedule = client.get('/api/pipelines/dummyjson').json()
        assert schedule['status'] == 'failed'
        assert schedule['consecutive_failures'] == 1
        assert client.get('/api/pipelines/dummyjson/executions').json()[0]['status'] == 'failed'


def test_old_schema_can_gain_scheduler_tables_without_deleting_offers(tmp_path):
    old_engine = create_engine(f"sqlite:///{tmp_path / 'old-v03.db'}")
    old_tables = [t for t in Base.metadata.sorted_tables if t.name not in {'pipeline_schedules', 'pipeline_executions'}]
    Base.metadata.create_all(old_engine, tables=old_tables)
    with Session(old_engine) as db:
        run = ImportRun(source_name='Old', filename='old.csv', total_rows=1)
        db.add(run); db.flush()
        db.add(SupplierOffer(source_name='Old', external_id='123', name='Unchanged',
                             price_amount=9.99, currency='EUR', stock=2, last_import_id=run.id))
        db.commit()
    Base.metadata.create_all(old_engine)
    assert {'pipeline_schedules', 'pipeline_executions'}.issubset(set(inspect(old_engine).get_table_names()))
    with Session(old_engine) as db:
        assert db.scalar(select(SupplierOffer)).name == 'Unchanged'
        assert db.scalars(select(PipelineSchedule)).all() == []
