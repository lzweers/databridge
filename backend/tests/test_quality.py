"""Quality metrics and the real-world CORS regression from v0.4."""
import io
import json

from fastapi.testclient import TestClient
from app.main import app
from tests.test_pipeline import upload


def test_quality_reports_only_measured_rows():
    source_a = ("ArtikelNr;Artikelname;Preis;Menge\n"
                "1;USB-C Hub;10,00;5\n"
                "2;HDMI Adapter;wrong;3\n"
                "3;Docking Station;20,00;2\n").encode()
    source_b = ("ArtikelNr;Artikelname;Preis;Menge\n"
                "1;USB-C Hub;10,00;1\n").encode()
    with TestClient(app) as client:
        empty = client.get('/api/analytics/quality').json()
        assert empty['total_runs'] == 0
        assert empty['quality_percent'] is None  # No false 100% for empty data.
        assert upload(client, source_a, 'A').status_code == 200
        assert upload(client, source_b, 'B').status_code == 200
        all_data = client.get('/api/analytics/quality').json()
        assert (all_data['total_runs'], all_data['total_rows'], all_data['accepted'], all_data['rejected']) == (2, 4, 3, 1)
        assert all_data['quality_percent'] == 75.0
        assert all_data['top_issues'][0]['count'] == 1
        assert len(all_data['by_source']) == 2
        a_data = client.get('/api/analytics/quality?source=A').json()
        assert a_data['total_runs'] == 1
        assert (a_data['total_rows'], a_data['rejected'], a_data['quality_percent']) == (3, 1, 66.7)
        assert len(a_data['recent_runs']) == 1
        assert client.get('/api/analytics/quality?source=unknown').json()['total_rows'] == 0


def test_put_cors_preflight_from_frontend_allowed():
    with TestClient(app) as client:
        response = client.options('/api/pipelines/dummyjson', headers={
            'Origin': 'http://localhost:5173',
            'Access-Control-Request-Method': 'PUT',
            'Access-Control-Request-Headers': 'content-type',
        })
    assert response.status_code == 200, response.text
    assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
    assert 'PUT' in response.headers['access-control-allow-methods']


def test_foreign_origin_not_allowed():
    with TestClient(app) as client:
        response = client.options('/api/pipelines/dummyjson', headers={
            'Origin': 'https://other.example',
            'Access-Control-Request-Method': 'PUT',
        })
    assert response.status_code == 400
    assert 'access-control-allow-origin' not in response.headers
