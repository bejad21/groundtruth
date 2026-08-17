"""SQLite persistence, deliberately minimal.

Demonstrates a real per-tenant isolation pattern (every table is scoped by
client_id, and every query filters on it) without pretending to be a full
multi-tenant auth system. There's one demo client today; the column and the
WHERE clause are the real part.

Sensitive text fields (source_name, truck_or_driver_id, notes) are encrypted
at rest with Fernet (AES-128-CBC + HMAC) when ENCRYPTION_KEY is configured,
so a copy of the .db file alone doesn't expose them.
"""
import logging
import sqlite3
import time
from contextlib import contextmanager

from . import config

logger = logging.getLogger("intake_agent.db")

ENCRYPTED_FIELDS = ("source_name", "truck_or_driver_id", "notes")

_fernet = None
if config.ENCRYPTION_KEY:
    from cryptography.fernet import Fernet

    _fernet = Fernet(config.ENCRYPTION_KEY.encode())
else:
    logger.warning("ENCRYPTION_KEY not set: records will be stored in plaintext.")


def _encrypt(value: str | None) -> str | None:
    if value is None or _fernet is None:
        return value
    return _fernet.encrypt(value.encode()).decode()


def _decrypt(value: str | None) -> str | None:
    if value is None or _fernet is None:
        return value
    try:
        return _fernet.decrypt(value.encode()).decode()
    except Exception:  # noqa: BLE001 - pre-encryption rows or a rotated key shouldn't crash a read
        return value


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    provider TEXT,
    model TEXT,
    latency_ms INTEGER,
    needs_review INTEGER,
    status TEXT NOT NULL,
    error TEXT
);

CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL,
    run_id INTEGER,
    created_at REAL NOT NULL,
    material_type TEXT,
    weight_kg REAL,
    source_name TEXT,
    truck_or_driver_id TEXT,
    delivery_date TEXT,
    notes TEXT,
    FOREIGN KEY (run_id) REFERENCES runs (id)
);

CREATE INDEX IF NOT EXISTS idx_runs_client ON runs (client_id);
CREATE INDEX IF NOT EXISTS idx_records_client ON records (client_id);
"""


@contextmanager
def _connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)


def log_run(client_id: str, provider: str, model: str, latency_ms: int, needs_review: bool | None, status: str, error: str = "") -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO runs (client_id, created_at, provider, model, latency_ms, needs_review, status, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (client_id, time.time(), provider, model, latency_ms, int(bool(needs_review)) if needs_review is not None else None, status, error),
        )
        return cur.lastrowid


def list_runs(client_id: str, limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM runs WHERE client_id = ? ORDER BY created_at DESC LIMIT ?",
            (client_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def save_record(client_id: str, run_id: int | None, record: dict) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO records (client_id, run_id, created_at, material_type, weight_kg, source_name, "
            "truck_or_driver_id, delivery_date, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                client_id, run_id, time.time(),
                record.get("material_type"), record.get("weight_kg"), _encrypt(record.get("source_name")),
                _encrypt(record.get("truck_or_driver_id")), record.get("delivery_date"), _encrypt(record.get("notes")),
            ),
        )
        return cur.lastrowid


def list_records(client_id: str, limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM records WHERE client_id = ? ORDER BY created_at DESC LIMIT ?",
            (client_id, limit),
        ).fetchall()
        records = [dict(r) for r in rows]
        for r in records:
            for field in ENCRYPTED_FIELDS:
                r[field] = _decrypt(r[field])
        return records
