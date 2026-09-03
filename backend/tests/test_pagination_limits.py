"""Regression tests for a real bug found live during an audit: SQLite treats a
negative LIMIT as "no limit at all", so `min(limit, 100)` doesn't actually cap
anything when a caller passes a negative value — `?limit=-1` returned every
row in the table instead of the intended max-100 cap (confirmed with `curl`
against the running server before this fix)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

VALID_KEY = "test-key-for-pytest-only"  # set in conftest.py's DEMO_API_KEY


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        # Seed enough records that an "unlimited" bug would be visible against
        # any small clamp value we assert on below.
        for i in range(5):
            record = {
                "material_type": "date_palm_fronds", "weight_kg": 100, "source_name": f"Limit Test Farm {i}",
                "truck_or_driver_id": f"TRK-LIMIT-{i}", "delivery_date": "2026-01-01", "notes": "",
            }
            res = c.post(
                "/api/confirm",
                headers={"Authorization": f"Bearer {VALID_KEY}"},
                json={"record": record, "run_id": None},
            )
            assert res.status_code == 200
        yield c


def test_negative_limit_on_records_is_clamped_not_treated_as_unlimited(client):
    res = client.get("/api/records?limit=-1", headers={"Authorization": f"Bearer {VALID_KEY}"})
    assert res.status_code == 200
    assert len(res.json()) == 1  # clamped to the minimum (1), not "every row"


def test_negative_limit_on_runs_is_clamped_not_treated_as_unlimited(client):
    res = client.get("/api/runs?limit=-1", headers={"Authorization": f"Bearer {VALID_KEY}"})
    assert res.status_code == 200
    assert len(res.json()) <= 1


def test_zero_limit_is_clamped_to_at_least_one_row(client):
    """limit=0 previously returned an empty list (SQLite's literal interpretation
    of LIMIT 0), which isn't useful and isn't what a caller asking for "at least
    give me something" would expect from a capped-results endpoint."""
    res = client.get("/api/records?limit=0", headers={"Authorization": f"Bearer {VALID_KEY}"})
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_a_very_large_limit_still_caps_at_one_hundred(client):
    """Regression guard: the existing upper-bound behavior must still work."""
    res = client.get("/api/records?limit=999999", headers={"Authorization": f"Bearer {VALID_KEY}"})
    assert res.status_code == 200
    assert len(res.json()) <= 100


def test_a_reasonable_limit_within_range_still_returns_exactly_that_many(client):
    res = client.get("/api/records?limit=3", headers={"Authorization": f"Bearer {VALID_KEY}"})
    assert res.status_code == 200
    assert len(res.json()) == 3
