"""
Unit tests for the Stage 1 pure engine-config parser (Spec 01 §11 Stage 1).
"""
import warnings
from pathlib import Path

import pytest

from slingology_eis.limits import load_engine_config, parse_engine_config

_ENGINES_DIR = Path(__file__).resolve().parent.parent.parent / "engines"


def test_parse_engine_config_matches_load_engine_config():
    text = (_ENGINES_DIR / "916iS.json").read_text()
    parsed = parse_engine_config(text, name="916iS")
    loaded = load_engine_config("916iS")
    assert parsed == loaded


def test_parse_engine_config_invalid_json():
    with pytest.raises(ValueError):
        parse_engine_config("{not valid json")


def test_parse_engine_config_warns_on_placeholder():
    text = '{"_metadata": {"engine": "test", "source_status": "PLACEHOLDER"}}'
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cfg = parse_engine_config(text, name="test")
    assert cfg["_metadata"]["source_status"] == "PLACEHOLDER"
    assert any(issubclass(w.category, UserWarning) for w in caught)


def test_parse_engine_config_no_warning_when_verified():
    text = '{"_metadata": {"engine": "test", "source_status": "VERIFIED"}}'
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        parse_engine_config(text, name="test")
    assert not any(issubclass(w.category, UserWarning) for w in caught)
