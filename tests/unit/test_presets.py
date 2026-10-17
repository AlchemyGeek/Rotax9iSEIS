"""
Tests for presets.py — Spec 07 v0.2 §6.3 chart preset validation, and
§13.2/§13.3's explicit test list (every shipped preset validates; unknown
id, non-chartable id, 7 slots, group-plus-member, empty and duplicate
cases are each rejected; egt_cyl plus 5 other slots is accepted, as are
4 individual cylinders plus 2 others).
"""
import json
from pathlib import Path

from slingology_eis.presets import validate_chart_preset

_CHART_PRESETS_PATH = Path(__file__).resolve().parents[2] / "chart_presets.json"


def test_every_shipped_preset_validates():
    shipped = json.loads(_CHART_PRESETS_PATH.read_text())["presets"]
    assert len(shipped) == 6
    seen: set[str] = set()
    for preset in shipped:
        issues = validate_chart_preset(preset, existing_ids=frozenset(seen))
        assert issues == [], f"{preset.get('id')}: {issues}"
        assert len(preset["channels"]) <= 6
        seen.add(preset["id"])


def test_rejects_unknown_channel_id():
    issues = validate_chart_preset({"id": "x", "label": "X", "channels": ["not_a_real_channel"]})
    assert issues and issues[0]["code"] == "PRESET_INVALID"


def test_rejects_non_chartable_channel():
    # phase is a real registry id, just not chartable (drawn as a background band).
    issues = validate_chart_preset({"id": "x", "label": "X", "channels": ["phase"]})
    assert issues and issues[0]["code"] == "PRESET_INVALID"


def test_rejects_seven_slots():
    issues = validate_chart_preset({
        "id": "x", "label": "X",
        "channels": ["rpm", "map_inhg", "oil_temp_f", "coolant_temp_f", "fuel_flow_gph", "main_volts", "ias_kt"],
    })
    assert issues and "7" in issues[0]["message"]


def test_rejects_empty_channels():
    issues = validate_chart_preset({"id": "x", "label": "X", "channels": []})
    assert issues and issues[0]["code"] == "PRESET_INVALID"


def test_rejects_duplicate_channel_within_one_preset():
    issues = validate_chart_preset({"id": "x", "label": "X", "channels": ["rpm", "rpm"]})
    assert issues and issues[0]["code"] == "PRESET_INVALID"


def test_rejects_duplicate_preset_id():
    issues = validate_chart_preset({"id": "dup", "label": "X", "channels": ["rpm"]}, existing_ids=frozenset({"dup"}))
    assert issues and "duplicate" in issues[0]["message"]


def test_accepts_egt_cyl_plus_five_other_slots():
    issues = validate_chart_preset({
        "id": "x", "label": "X",
        "channels": ["egt_cyl", "rpm", "map_inhg", "oil_temp_f", "coolant_temp_f", "main_volts"],
    })
    assert issues == []


def test_accepts_four_individual_cylinders_plus_two_others():
    issues = validate_chart_preset({
        "id": "x", "label": "X",
        "channels": ["egt1_f", "egt2_f", "egt3_f", "egt4_f", "rpm", "map_inhg"],
    })
    assert issues == []


def test_rejects_group_plus_one_of_its_own_members():
    issues = validate_chart_preset({"id": "x", "label": "X", "channels": ["egt_cyl", "egt2_f"]})
    assert issues and issues[0]["code"] == "PRESET_INVALID"
    assert "egt_cyl" in issues[0]["message"] and "egt2_f" in issues[0]["message"]
