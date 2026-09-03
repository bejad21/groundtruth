"""Tests for the provider modules — previously zero direct coverage despite
being the most architecturally central code in the project (see the audit
report). Covers the happy path for each provider, the missing-key guard,
malformed-JSON handling, and two specific fixes: OpenRouter's silent
max_tokens truncation and its hardcoded placeholder HTTP-Referer header.
"""
import json
from types import SimpleNamespace

import httpx
import pytest

from app import config
from app.providers import gemini_provider, openrouter_provider
from app.providers.common import CONFIDENCE_FIELDS, ProviderError

VALID_RESULT = {
    "material_type": "date_palm_fronds",
    "weight_kg": 100,
    "source_name": "Test Farm",
    "truck_or_driver_id": "TRK-1",
    "delivery_date": "2026-01-01",
    "notes": "",
    "field_confidences": {f: 0.9 for f in CONFIDENCE_FIELDS},
}


# ---------------------------------------------------------------------------
# gemini_provider
# ---------------------------------------------------------------------------


class _FakeGeminiModel:
    def __init__(self, response_text, **kwargs):
        self._response_text = response_text

    def generate_content(self, *args, **kwargs):
        return SimpleNamespace(text=self._response_text)


def test_gemini_extract_returns_parsed_args_on_success(monkeypatch):
    import google.generativeai as genai

    monkeypatch.setattr(genai, "configure", lambda **kwargs: None)
    monkeypatch.setattr(genai, "GenerativeModel", lambda **kwargs: _FakeGeminiModel(json.dumps(VALID_RESULT)))

    result = gemini_provider.extract(b"fake-bytes", "image/png", "gemini-flash-latest", "fake-key")

    assert result["material_type"] == "date_palm_fronds"
    assert result["field_confidences"]["weight_kg"] == 0.9


def test_gemini_extract_without_api_key_raises_provider_error():
    with pytest.raises(ProviderError, match="not configured"):
        gemini_provider.extract(b"fake-bytes", "image/png", "gemini-flash-latest", "")


def test_gemini_extract_with_malformed_json_raises_provider_error(monkeypatch):
    import google.generativeai as genai

    monkeypatch.setattr(genai, "configure", lambda **kwargs: None)
    monkeypatch.setattr(genai, "GenerativeModel", lambda **kwargs: _FakeGeminiModel("not valid json"))

    with pytest.raises(ProviderError, match="malformed JSON"):
        gemini_provider.extract(b"fake-bytes", "image/png", "gemini-flash-latest", "fake-key")


def test_gemini_extract_missing_field_confidences_raises_provider_error(monkeypatch):
    import google.generativeai as genai

    incomplete = {**VALID_RESULT, "field_confidences": {"material_type": 0.9}}  # missing 4 of 5 fields
    monkeypatch.setattr(genai, "configure", lambda **kwargs: None)
    monkeypatch.setattr(genai, "GenerativeModel", lambda **kwargs: _FakeGeminiModel(json.dumps(incomplete)))

    with pytest.raises(ProviderError, match="field confidences"):
        gemini_provider.extract(b"fake-bytes", "image/png", "gemini-flash-latest", "fake-key")


# ---------------------------------------------------------------------------
# openrouter_provider
# ---------------------------------------------------------------------------


def _openrouter_response(content: str, finish_reason: str = "stop", status_code: int = 200) -> httpx.Response:
    body = {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}
    return httpx.Response(status_code, json=body, request=httpx.Request("POST", openrouter_provider.API_URL))


def test_openrouter_extract_returns_parsed_args_on_success(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _openrouter_response(json.dumps(VALID_RESULT)))

    result = openrouter_provider.extract(b"fake-bytes", "image/png", "some-model", "fake-key")

    assert result["material_type"] == "date_palm_fronds"


def test_openrouter_extract_without_api_key_raises_provider_error():
    with pytest.raises(ProviderError, match="not configured"):
        openrouter_provider.extract(b"fake-bytes", "image/png", "some-model", "")


def test_openrouter_extract_with_malformed_json_raises_provider_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _openrouter_response("not valid json at all"))

    with pytest.raises(ProviderError):
        openrouter_provider.extract(b"fake-bytes", "image/png", "some-model", "fake-key")


def test_openrouter_extract_reports_truncation_distinctly_from_generic_malformed_json(monkeypatch):
    """A response cut off by hitting max_tokens (finish_reason="length") is a
    different, more actionable failure than genuinely malformed JSON — the
    error message should say so instead of a generic parse-failure message."""
    truncated_json = json.dumps(VALID_RESULT)[:40]  # a valid object cut off mid-way
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _openrouter_response(truncated_json, finish_reason="length"))

    with pytest.raises(ProviderError, match="truncated"):
        openrouter_provider.extract(b"fake-bytes", "image/png", "some-model", "fake-key")


def test_openrouter_extract_missing_field_confidences_raises_provider_error(monkeypatch):
    incomplete = {**VALID_RESULT, "field_confidences": {"material_type": 0.9}}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _openrouter_response(json.dumps(incomplete)))

    with pytest.raises(ProviderError, match="field confidences"):
        openrouter_provider.extract(b"fake-bytes", "image/png", "some-model", "fake-key")


def test_openrouter_referer_header_is_not_a_placeholder_github_url(monkeypatch):
    """app/providers/openrouter_provider.py used to hardcode
    "HTTP-Referer": "https://github.com/" — a non-functional placeholder, not
    a real, dereferenceable URL for this project."""
    captured = {}

    response_body = json.dumps(VALID_RESULT)

    def fake_post(url, headers, timeout, **kwargs):
        captured["headers"] = headers
        return _openrouter_response(response_body)

    monkeypatch.setattr(httpx, "post", fake_post)

    openrouter_provider.extract(b"fake-bytes", "image/png", "some-model", "fake-key")

    assert captured["headers"].get("HTTP-Referer") != "https://github.com/"


def test_openrouter_referer_header_is_configurable(monkeypatch):
    captured = {}

    response_body = json.dumps(VALID_RESULT)

    def fake_post(url, headers, timeout, **kwargs):
        captured["headers"] = headers
        return _openrouter_response(response_body)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(config, "OPENROUTER_HTTP_REFERER", "https://example.com/groundtruth", raising=False)

    openrouter_provider.extract(b"fake-bytes", "image/png", "some-model", "fake-key")

    assert captured["headers"]["HTTP-Referer"] == "https://example.com/groundtruth"
