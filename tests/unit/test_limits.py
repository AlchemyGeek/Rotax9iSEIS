"""
Unit tests for the Stage 1 pure engine-config parser (Spec 01 §11 Stage 1).
"""
import warnings
from pathlib import Path

import pytest

from slingology_eis.limits import engine_limits_from_config, load_engine_config, parse_engine_config

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


def test_engine_limits_from_config_returns_one_limit_per_entry():
    # Regression test for a7af9ad: a stray `lims = []` inside the loop
    # shadowed the outer accumulator, so every entry was built and then
    # discarded — engine_limits_from_config always returned []. That
    # silently made check_exceedances() find zero exceedances for every
    # engine, since it iterates this list.
    config = {"limits": [
        {"id": "rpm_max", "param": "rpm", "label": "RPM max", "unit": "rpm", "max_val": 5800},
        {"id": "oil_temp_max", "param": "oil_temp_f", "label": "Oil temp max", "unit": "f", "max_val": 248},
    ]}
    limits = engine_limits_from_config(config)
    assert len(limits) == 2
    assert [l.param for l in limits] == ["rpm", "oil_temp_f"]


def test_engine_limits_from_config_916is_nonempty():
    config = load_engine_config("916iS")
    limits = engine_limits_from_config(config)
    assert len(limits) == len(config["limits"])
    assert len(limits) > 0


# ── Spec 09 v0.12: retired time_limit_s, rpm_continuous_max ──────────────────

@pytest.mark.parametrize("engine", ["912iS", "915iS", "916iS"])
def test_rpm_continuous_max_is_retired(engine):
    config = load_engine_config(engine)
    ids = {e["id"] for e in config["limits"]}
    assert "rpm_continuous_max" not in ids


def test_time_limit_s_on_an_ordinary_limit_fails_to_load():
    config = {"limits": [
        {"id": "rpm_max", "param": "rpm", "label": "RPM max", "unit": "rpm", "max_val": 5800, "time_limit_s": 300},
    ]}
    with pytest.raises(ValueError, match="time_limit_s"):
        engine_limits_from_config(config)


def test_time_limit_s_on_the_overboost_block_fails_to_load():
    config = {
        "limits": [],
        "overboost": {"id": "overboost", "rpm_threshold": 5500, "time_limit_s": 300},
    }
    with pytest.raises(ValueError, match="time_limit_s"):
        engine_limits_from_config(config)


@pytest.mark.parametrize("engine", ["912iS", "915iS", "916iS"])
def test_shipped_profiles_have_no_time_limit_s(engine):
    config = load_engine_config(engine)
    assert all("time_limit_s" not in e for e in config["limits"])
    assert "time_limit_s" not in (config.get("overboost") or {})
    # Loads cleanly, which it wouldn't if any did.
    engine_limits_from_config(config)
