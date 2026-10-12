"""Checks deploy/render.yaml declares every required secret as a prompted value."""
from pathlib import Path

import yaml

RENDER_YAML = Path(__file__).parent.parent.parent / "deploy" / "render.yaml"

# Secrets with no default in app/config.py.
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
    """`sync: false` makes Render prompt for the value instead of deploying the file's."""
    env_vars = _service_env_vars()
    for key in REQUIRED_SECRET_KEYS:
        assert env_vars[key].get("sync") is False, (
            f"{key} must be declared with `sync: false` so Render prompts for a real "
            f"value instead of deploying whatever's in the file."
        )
