"""Regression test for deploy/render.yaml: previously it listed GEMINI_API_KEY
and OPENROUTER_API_KEY as prompted secrets but omitted DEMO_API_KEY and
ENCRYPTION_KEY entirely — a real Render deployment following this exact
blueprint would never be prompted to set either, leaving the deployed backend
either fully locked out (no DEMO_API_KEY -> every request 401) or silently
storing PII in plaintext (no ENCRYPTION_KEY, see test_db.py's
EncryptionNotConfiguredError tests for the app-level half of that fix)."""
from pathlib import Path

import yaml

RENDER_YAML = Path(__file__).parent.parent.parent / "deploy" / "render.yaml"

# Every env var the app reads at runtime that has no safe hardcoded default —
# i.e. secrets a real deployer must actually provide, not tunable knobs like
# GEMINI_MODEL that already ship with a working default in app/config.py.
REQUIRED_SECRET_KEYS = {"GEMINI_API_KEY", "OPENROUTER_API_KEY", "DEMO_API_KEY", "ENCRYPTION_KEY"}


def _service_env_vars() -> dict[str, dict]:
    data = yaml.safe_load(RENDER_YAML.read_text())
    service = data["services"][0]
    return {v["key"]: v for v in service["envVars"]}


def test_render_yaml_exists_and_parses():
    assert RENDER_YAML.exists()
    env_vars = _service_env_vars()
    assert len(env_vars) > 0


def test_render_yaml_declares_every_secret_the_app_actually_needs():
    env_vars = _service_env_vars()
    missing = REQUIRED_SECRET_KEYS - env_vars.keys()
    assert not missing, f"deploy/render.yaml is missing required secret(s): {sorted(missing)}"


def test_render_yaml_marks_every_required_secret_as_a_prompted_value_not_hardcoded():
    """sync: false is Render's "prompt the deployer for this, don't put a real
    value in the file" flag. A required secret with a hardcoded value (or
    missing the flag) would mean the placeholder gets deployed as-is."""
    env_vars = _service_env_vars()
    for key in REQUIRED_SECRET_KEYS:
        assert env_vars[key].get("sync") is False, (
            f"{key} must be declared with `sync: false` so Render prompts for a real "
            f"value instead of deploying whatever's in the file."
        )
