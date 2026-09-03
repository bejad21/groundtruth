"""Regression test for encryption at rest: confirms sensitive fields are genuinely
ciphertext in the database file, not just decrypted correctly through the app layer
(which would pass even if encryption silently no-op'd)."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

VALID_KEY = "test-key-for-pytest-only"  # set in conftest.py's DEMO_API_KEY


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

    # Read the raw row directly, bypassing db.list_records()'s decryption.
    with sqlite3.connect(db.config.DB_PATH) as conn:
        row = conn.execute(
            "SELECT source_name, truck_or_driver_id, notes FROM records WHERE id = ?", (record_id,)
        ).fetchone()

    assert row[0] != "Encryption Test Farm"  # stored value must not be plaintext
    assert row[1] != "TRK-ENC-1"
    assert row[2] != "sensitive note"

    decrypted = db.list_records("test-client")
    match = next(r for r in decrypted if r["id"] == record_id)
    assert match["source_name"] == "Encryption Test Farm"
    assert match["truck_or_driver_id"] == "TRK-ENC-1"
    assert match["notes"] == "sensitive note"
    # Fields not in ENCRYPTED_FIELDS stay in plaintext, unaffected either way.
    assert match["material_type"] == "date_palm_fronds"


def test_save_record_refuses_to_write_when_encryption_is_not_configured(monkeypatch):
    """Fail-open regression test: previously, if ENCRYPTION_KEY wasn't set, the app
    silently stored source_name/truck_or_driver_id/notes in plaintext with only a
    warning log line — the kind of gap that's invisible until someone reads the raw
    .db file. It must now refuse the write outright instead."""
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

    # No partial/plaintext row must have been written.
    with sqlite3.connect(db.config.DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM records WHERE source_name = ?", ("Should Not Be Stored",)
        ).fetchone()
    assert row is None


def test_save_record_still_works_normally_once_encryption_is_configured(monkeypatch):
    """Regression guard: the refusal above must be specific to the unconfigured
    case, not a general break in save_record."""
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
    """Same fix, exercised through the real HTTP endpoint: /api/confirm must not
    500 (or, worse, silently succeed with plaintext) when ENCRYPTION_KEY is unset."""
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
    assert "ncryption" in res.json()["detail"]  # a real explanation, not a stack trace

    # And nothing was persisted.
    with sqlite3.connect(db.config.DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM records WHERE source_name = ?", ("HTTP Test Farm",)
        ).fetchone()
    assert row is None


# ---------------------------------------------------------------------------
# Foreign key enforcement: records.run_id declares
# `FOREIGN KEY (run_id) REFERENCES runs (id)` in the schema, but SQLite never
# actually enforces foreign keys unless `PRAGMA foreign_keys = ON` is set on
# the connection. Previously it wasn't, so the constraint was purely
# decorative — a record could reference a run_id that never existed.
# ---------------------------------------------------------------------------


def test_save_record_rejects_a_run_id_that_does_not_exist():
    record = {
        "material_type": "date_palm_fronds", "weight_kg": 100, "source_name": "FK Test Farm",
        "truck_or_driver_id": "TRK-FK-1", "delivery_date": "2026-01-01", "notes": "",
    }
    with pytest.raises(sqlite3.IntegrityError):
        db.save_record("test-client", 999999, record)

    # And, just as important, nothing was actually written.
    with sqlite3.connect(db.config.DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM records WHERE source_name = ?", ("FK Test Farm",)
        ).fetchone()
    assert row is None


def test_save_record_accepts_a_run_id_that_really_exists():
    """Regression guard: enforcing the constraint must not break the normal,
    legitimate case of confirming a record against a real prior run."""
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
    """A confirm with no prior extraction run (run_id=None) is a legitimate,
    already-tested case — NULL foreign key values are never checked, by the
    SQL standard and by SQLite, so enforcing the constraint must not touch it."""
    record = {
        "material_type": "date_palm_fronds", "weight_kg": 100, "source_name": "No Run Farm",
        "truck_or_driver_id": "TRK-NORUN-1", "delivery_date": "2026-01-01", "notes": "",
    }
    record_id = db.save_record("test-client", None, record)
    assert record_id is not None


def test_confirm_endpoint_returns_a_clean_error_for_a_nonexistent_run_id():
    """Same fix, exercised through the real HTTP endpoint: a bogus run_id must
    come back as a clean 4xx, not an unhandled 500."""
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
