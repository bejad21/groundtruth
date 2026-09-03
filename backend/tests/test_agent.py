"""Tests for the provider-chain orchestration in app/agent.py.

Covers the happy path (a real ProviderError causes failover — the behavior the
whole chain exists for) and the bug this file adds coverage for: a provider
that returns HTTP 200 with a *malformed* payload (wrong-typed confidence
score, unparseable weight) used to crash run_intake_agent with a raw,
unhandled exception instead of being treated as a failed attempt and either
failing over to the next provider or surfacing a clean AgentError.
"""
import io

import pytest
from fastapi.testclient import TestClient

from app import config
from app.agent import AgentError, run_intake_agent
from app.main import app
from app.providers import gemini_provider, openrouter_provider
from app.providers.common import CONFIDENCE_FIELDS, ProviderError

VALID_ARGS = {
    "material_type": "date_palm_fronds",
    "weight_kg": 100,
    "source_name": "Test Farm",
    "truck_or_driver_id": "TRK-1",
    "delivery_date": "2026-01-01",
    "notes": "",
    "field_confidences": {f: 0.9 for f in CONFIDENCE_FIELDS},
}


def _args(**overrides) -> dict:
    base = {**VALID_ARGS, "field_confidences": dict(VALID_ARGS["field_confidences"])}
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _all_providers_configured(monkeypatch):
    # So the whole 4-entry chain (gemini, gemini-lite, openrouter, openrouter-vl)
    # has somewhere to fail over to instead of being skipped for "no API key".
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "test-openrouter-key")


def test_response_includes_the_configured_confidence_threshold(monkeypatch):
    """The frontend used to hardcode 0.75 in three places instead of reading
    the backend's actual, configurable CONFIDENCE_REVIEW_THRESHOLD. Using a
    value other than the default (0.75) here proves the response reflects
    whatever's actually configured, not a value baked in somewhere."""
    monkeypatch.setattr(config, "CONFIDENCE_REVIEW_THRESHOLD", 0.42)
    monkeypatch.setattr(gemini_provider, "extract", lambda *a, **k: _args())

    result = run_intake_agent(b"fake-bytes", "image/png")

    assert result.response.confidence_threshold == 0.42


def test_successful_extraction_returns_a_populated_record(monkeypatch):
    monkeypatch.setattr(gemini_provider, "extract", lambda *a, **k: _args())

    result = run_intake_agent(b"fake-bytes", "image/png")

    assert result.provider == "gemini"
    assert result.response.record.material_type == "date_palm_fronds"
    assert result.response.record.weight_kg == 100


def test_provider_error_fails_over_to_the_next_provider(monkeypatch):
    def gemini_fails(image_bytes, mime_type, model, api_key):
        raise ProviderError("503 service unavailable")

    monkeypatch.setattr(gemini_provider, "extract", gemini_fails)
    monkeypatch.setattr(openrouter_provider, "extract", lambda *a, **k: _args())

    result = run_intake_agent(b"fake-bytes", "image/png")

    assert result.provider == "openrouter"
    assert result.response.record.material_type == "date_palm_fronds"


def test_all_providers_failing_raises_agent_error_not_a_crash(monkeypatch):
    def always_fails(image_bytes, mime_type, model, api_key):
        raise ProviderError("no quota left")

    monkeypatch.setattr(gemini_provider, "extract", always_fails)
    monkeypatch.setattr(openrouter_provider, "extract", always_fails)

    with pytest.raises(AgentError):
        run_intake_agent(b"fake-bytes", "image/png")


def test_malformed_confidence_value_fails_over_instead_of_crashing(monkeypatch):
    """A provider that returns 200 with a non-numeric confidence score (a real
    thing an unreliable free-tier model can do) must be treated as a failed
    attempt, not crash the whole request with an unhandled ValueError."""

    def gemini_returns_bad_confidence(image_bytes, mime_type, model, api_key):
        if model == config.GEMINI_MODEL:
            return _args(field_confidences={**VALID_ARGS["field_confidences"], "material_type": "very confident"})
        return _args()  # gemini-lite (the fallback model) returns a clean payload

    monkeypatch.setattr(gemini_provider, "extract", gemini_returns_bad_confidence)

    result = run_intake_agent(b"fake-bytes", "image/png")

    assert result.provider == "gemini-lite"
    assert result.response.record.material_type == "date_palm_fronds"


def test_malformed_weight_value_fails_over_instead_of_crashing(monkeypatch):
    """A provider that returns a weight_kg pydantic can't coerce to a float
    must also be treated as a failed attempt, not crash the request."""

    def gemini_returns_bad_weight(image_bytes, mime_type, model, api_key):
        if model == config.GEMINI_MODEL:
            return _args(weight_kg="illegible")
        return _args()

    monkeypatch.setattr(gemini_provider, "extract", gemini_returns_bad_weight)

    result = run_intake_agent(b"fake-bytes", "image/png")

    assert result.provider == "gemini-lite"
    assert result.response.record.weight_kg == 100


def test_all_providers_returning_malformed_data_raises_agent_error_not_a_crash(monkeypatch):
    def always_malformed(image_bytes, mime_type, model, api_key):
        return _args(weight_kg="illegible")

    monkeypatch.setattr(gemini_provider, "extract", always_malformed)
    monkeypatch.setattr(openrouter_provider, "extract", always_malformed)

    with pytest.raises(AgentError):
        run_intake_agent(b"fake-bytes", "image/png")


VALID_KEY = "test-key-for-pytest-only"  # set in conftest.py's DEMO_API_KEY
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_malformed_provider_response_returns_a_clean_502_over_http(monkeypatch):
    """Same bug, exercised through the real request stack (app/main.py ->
    app/agent.py) instead of calling run_intake_agent directly: a malformed
    response from every provider in the chain must come back as the same
    clean 502 the endpoint already returns for real provider outages, not an
    unhandled-exception 500."""

    def always_malformed(image_bytes, mime_type, model, api_key):
        return _args(weight_kg="illegible")

    monkeypatch.setattr(gemini_provider, "extract", always_malformed)
    monkeypatch.setattr(openrouter_provider, "extract", always_malformed)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "test-openrouter-key")

    with TestClient(app) as client:
        res = client.post(
            "/api/extract",
            headers={"Authorization": f"Bearer {VALID_KEY}"},
            files={"file": ("ticket.png", io.BytesIO(PNG_BYTES), "image/png")},
        )

    assert res.status_code == 502  # clean, expected failure — not an unhandled-exception 500
    assert res.json()["detail"]  # a real, non-empty explanation, not a stack trace dump
