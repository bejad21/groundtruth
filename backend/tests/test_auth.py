"""Integration tests for access control. These are the regression tests for the
real vulnerability caught during development: every data endpoint used to trust a
client-supplied X-Client-Id header, so anyone could read another client's records
by naming a different ID. If these tests ever go red, that gap is back."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

VALID_KEY = "test-key-for-pytest-only"  # set in conftest.py's DEMO_API_KEY


@pytest.fixture(scope="module")
def client():
    # Used as a context manager so the app's lifespan (db.init_db()) actually runs;
    # a bare TestClient(app) never fires startup, and every query would 500.
    with TestClient(app) as c:
        yield c


def test_no_token_is_rejected(client):
    res = client.get("/api/records")
    assert res.status_code == 401


def test_wrong_token_is_rejected(client):
    res = client.get("/api/records", headers={"Authorization": "Bearer wrong-key"})
    assert res.status_code == 401


def test_spoofed_client_id_header_alone_is_rejected(client):
    """The exact attack the old code was vulnerable to: no credential, just a claimed identity."""
    res = client.get("/api/records", headers={"X-Client-Id": "someone-elses-client"})
    assert res.status_code == 401


def test_valid_token_is_accepted(client):
    res = client.get("/api/records", headers={"Authorization": f"Bearer {VALID_KEY}"})
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_valid_token_on_runs_endpoint_is_accepted(client):
    res = client.get("/api/runs", headers={"Authorization": f"Bearer {VALID_KEY}"})
    assert res.status_code == 200


def test_confirm_rejects_blocking_validation_errors(client):
    empty_record = {
        "material_type": "", "weight_kg": None, "source_name": "",
        "truck_or_driver_id": "", "delivery_date": "", "notes": "",
    }
    res = client.post(
        "/api/confirm",
        headers={"Authorization": f"Bearer {VALID_KEY}"},
        json={"record": empty_record, "run_id": None},
    )
    assert res.status_code == 422


def test_confirm_accepts_a_valid_record_and_persists_it(client):
    record = {
        "material_type": "date_palm_fronds", "weight_kg": 100, "source_name": "Test Farm",
        "truck_or_driver_id": "TRK-1", "delivery_date": "2026-01-01", "notes": "",
    }
    res = client.post(
        "/api/confirm",
        headers={"Authorization": f"Bearer {VALID_KEY}"},
        json={"record": record, "run_id": None},
    )
    assert res.status_code == 200
    assert res.json()["record_id"] is not None

    records = client.get("/api/records", headers={"Authorization": f"Bearer {VALID_KEY}"}).json()
    assert any(r["source_name"] == "Test Farm" for r in records)


def test_health_endpoint_needs_no_auth(client):
    # Health should stay publicly checkable without a key, unlike the data endpoints.
    res = client.get("/api/health")
    assert res.status_code == 200
