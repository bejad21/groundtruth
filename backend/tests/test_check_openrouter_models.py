"""Tests for find_missing_models in scripts/check_openrouter_models.py (no network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.check_openrouter_models import find_missing_models


def test_reports_nothing_missing_when_both_models_are_in_the_catalog():
    catalog = {"google/gemma-4-31b-it:free", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "other/model"}
    missing = find_missing_models(
        ["nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "google/gemma-4-31b-it:free"], catalog
    )
    assert missing == []


def test_reports_a_model_that_has_been_removed_from_the_catalog():
    catalog = {"google/gemma-4-31b-it:free", "some/other-model"}
    missing = find_missing_models(
        ["nvidia/nemotron-nano-12b-v2-vl:free", "google/gemma-4-31b-it:free"], catalog
    )
    assert missing == ["nvidia/nemotron-nano-12b-v2-vl:free"]


def test_reports_both_models_missing_if_both_are_gone():
    missing = find_missing_models(["dead/model-a", "dead/model-b"], {"unrelated/model"})
    assert missing == ["dead/model-a", "dead/model-b"]


def test_empty_configured_list_reports_nothing_missing():
    missing = find_missing_models([], {"some/model"})
    assert missing == []


def test_ignores_blank_model_ids_instead_of_flagging_them_as_missing():
    missing = find_missing_models(["", "google/gemma-4-31b-it:free"], {"google/gemma-4-31b-it:free"})
    assert missing == []
