"""Catches OpenRouter free-tier catalog churn before it silently breaks the
failover chain in production.

This is exactly the bug found during the audit: `OPENROUTER_MODEL` pointed at
`nvidia/nemotron-nano-12b-v2-vl:free`, a model OpenRouter had quietly removed
from its catalog entirely (not rate-limited — gone). Every extract request
that fell through to OpenRouter got a 404 with no earlier warning.

Run manually or on a schedule (cron / CI) against real credentials, from the
`backend/` directory:
    python scripts/check_openrouter_models.py

Exits non-zero and prints which configured model IDs no longer exist in
OpenRouter's live catalog, so this gets caught long before a real user does.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

MODELS_URL = "https://openrouter.ai/api/v1/models"


def find_missing_models(configured_models: list[str], catalog_ids: set[str]) -> list[str]:
    """Pure, testable core: which of the configured model IDs aren't in the catalog."""
    return [m for m in configured_models if m and m not in catalog_ids]


def fetch_catalog_ids(api_key: str, timeout: float = 10.0) -> set[str]:
    response = httpx.get(MODELS_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
    response.raise_for_status()
    return {m["id"] for m in response.json()["data"]}


def main() -> int:
    from app import config  # local import so this module stays importable/testable with no env required

    if not config.OPENROUTER_API_KEY:
        print("OPENROUTER_API_KEY is not set — skipping (nothing to check against).")
        return 0

    try:
        catalog_ids = fetch_catalog_ids(config.OPENROUTER_API_KEY)
    except httpx.HTTPError as exc:
        print(f"Could not reach OpenRouter's catalog: {exc}")
        return 1

    configured = [config.OPENROUTER_MODEL, config.OPENROUTER_MODEL_FALLBACK]
    missing = find_missing_models(configured, catalog_ids)

    if missing:
        print("OpenRouter model(s) configured but no longer in the live catalog:")
        for model_id in missing:
            print(f"  - {model_id}")
        print("Update OPENROUTER_MODEL / OPENROUTER_MODEL_FALLBACK in .env (see .env.example).")
        return 1

    print(f"OK - both configured OpenRouter models are live: {configured}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
