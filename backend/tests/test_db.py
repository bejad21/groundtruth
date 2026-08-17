"""Regression test for encryption at rest: confirms sensitive fields are genuinely
ciphertext in the database file, not just decrypted correctly through the app layer
(which would pass even if encryption silently no-op'd)."""
import sqlite3

from app import db


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
