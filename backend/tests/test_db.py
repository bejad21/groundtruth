"""Tests for encryption at rest and foreign-key enforcement in app/db.py."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

VALID_KEY = "test-key-for-pytest-only"  # matches DEMO_API_KEY in conftest.py


def test_confirmed_record_round_trips_through_encryption():
    record = {
        "material_type": "date_palm_fronds",
        "weight_kg": 500,
        "source_name": "Encryption Test Farm",
        "truck_or_driver_id": "TRK-ENC-1",
        "delivery_date": "2026-01-01",
        "notes": "sensitive note",
    }
    record_id = db.save_record("test-client", None, record)

    # Read the raw row to bypass decryption.
    with sqlite3.connect(db.config.DB_PATH) as conn:
        row = conn.execute(
            "SELECT source_name, truck_or_driver_id, notes FROM records WHERE id = ?", (record_id,)
        ).fetchone()

    assert row[0] != "Encryption Test Farm"
    assert row[1] != "TRK-ENC-1"
    assert row[2] != "sensitive note"

    decrypted = db.list_records("test-client")
    match = next(r for r in decrypted if r["id"] == record_id)
    assert match["source_name"] == "Encryption Test Farm"
    assert match["truck_or_driver_id"] == "TRK-ENC-1"
    assert match["notes"] == "sensitive note"
    assert match["material_type"] == "date_palm_fronds"


def test_save_record_refuses_to_write_when_encryption_is_not_configured(monkeypatch):
    monkeypatch.setattr(db, "_fernet", None)

    record = {
        "material_type": "date_palm_fronds",
        "weight_kg": 500,
        "source_name": "Should Not Be Stored",
        "truck_or_driver_id": "TRK-NOENC-1",
        "delivery_date": "2026-01-01",
        "notes": "must not persist",
    }

    with pytest.raises(db.EncryptionNotConfiguredError):
        db.save_record("test-client", None, record)

    with sqlite3.connect(db.config.DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM records WHERE source_name = ?", ("Should Not Be Stored",)
        ).fetchone()
    assert row is None


def test_save_record_still_works_normally_once_encryption_is_configured(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setattr(db, "_fernet", Fernet(Fernet.generate_key()))

    record = {
        "material_type": "date_palm_fronds",
        "weight_kg": 500,
        "source_name": "Configured Again",
        "truck_or_driver_id": "TRK-OK-1",
        "delivery_date": "2026-01-01",
        "notes": "fine",
    }
    record_id = db.save_record("test-client", None, record)
    assert record_id is not None


def test_confirm_endpoint_returns_a_clean_error_when_encryption_is_not_configured(monkeypatch):
    """/api/confirm returns 503, not 500 or a plaintext save, when ENCRYPTION_KEY is unset."""
    import app.main as main_module

    monkeypatch.setattr(main_module.db, "_fernet", None)

    record = {
        "material_type": "date_palm_fronds", "weight_kg": 100, "source_name": "HTTP Test Farm",
        "truck_or_driver_id": "TRK-HTTP-1", "delivery_date": "2026-01-01", "notes": "",
    }
    with TestClient(app) as client:
        res = client.post(
            "/api/confirm",
            headers={"Authorization": f"Bearer {VALID_KEY}"},
            json={"record": record, "run_id": None},
        )

    assert res.status_code == 503
    assert "ncryption" in res.json()["detail"]

    with sqlite3.connect(db.config.DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM records WHERE source_name = ?", ("HTTP Test Farm",)
        ).fetchone()
    assert row is None


def test_save_record_rejects_a_run_id_that_does_not_exist():
    record = {
        "material_type": "date_palm_fronds", "weight_kg": 100, "source_name": "FK Test Farm",
        "truck_or_driver_id": "TRK-FK-1", "delivery_date": "2026-01-01", "notes": "",
    }
    with pytest.raises(sqlite3.IntegrityError):
        db.save_record("test-client", 999999, record)

    with sqlite3.connect(db.config.DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM records WHERE source_name = ?", ("FK Test Farm",)
        ).fetchone()
    assert row is None


def test_save_record_accepts_a_run_id_that_really_exists():
    run_id = db.log_run(
        "test-client", provider="gemini", model="gemini-flash-latest",
        latency_ms=1200, needs_review=False, status="ok",
    )
    record = {
        "material_type": "date_palm_fronds", "weight_kg": 100, "source_name": "Real Run Farm",
        "truck_or_driver_id": "TRK-REAL-1", "delivery_date": "2026-01-01", "notes": "",
    }
    record_id = db.save_record("test-client", run_id, record)
    assert record_id is not None

    saved = next(r for r in db.list_records("test-client") if r["id"] == record_id)
    assert saved["run_id"] == run_id


def test_save_record_with_no_run_id_still_works():
    """A NULL run_id is not checked against the foreign key."""
    record = {
        "material_type": "date_palm_fronds", "weight_kg": 100, "source_name": "No Run Farm",
        "truck_or_driver_id": "TRK-NORUN-1", "delivery_date": "2026-01-01", "notes": "",
    }
    record_id = db.save_record("test-client", None, record)
    assert record_id is not None


def test_confirm_endpoint_returns_a_clean_error_for_a_nonexistent_run_id():
    """A nonexistent run_id returns 422, not 500."""
    record = {
        "material_type": "date_palm_fronds", "weight_kg": 100, "source_name": "HTTP FK Test Farm",
        "truck_or_driver_id": "TRK-HTTP-FK-1", "delivery_date": "2026-01-01", "notes": "",
    }
    with TestClient(app) as client:
        res = client.post(
            "/api/confirm",
            headers={"Authorization": f"Bearer {VALID_KEY}"},
            json={"record": record, "run_id": 999999},
        )

    assert res.status_code == 422
    assert "run_id" in res.json()["detail"]

    with sqlite3.connect(db.config.DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM records WHERE source_name = ?", ("HTTP FK Test Farm",)
        ).fetchone()
    assert row is None


def test_confirm_endpoint_still_accepts_a_real_run_id():
    run_id = db.log_run(
        "demo-client", provider="gemini", model="gemini-flash-latest",
        latency_ms=900, needs_review=False, status="ok",
    )
    record = {
        "material_type": "date_palm_fronds", "weight_kg": 100, "source_name": "HTTP Real Run Farm",
        "truck_or_driver_id": "TRK-HTTP-REAL-1", "delivery_date": "2026-01-01", "notes": "",
    }
    with TestClient(app) as client:
        res = client.post(
            "/api/confirm",
            headers={"Authorization": f"Bearer {VALID_KEY}"},
            json={"record": record, "run_id": run_id},
        )

    assert res.status_code == 200
    assert res.json()["record_id"] is not None
