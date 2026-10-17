"""
Spec 01 §8.8: topics.md parser and placeholder resolution.
"""
import pytest

from slingology_eis.help import parse_help_file, resolve_template


def _entry(body: str) -> str:
    return f"## some_topic\n{body}\n"


def test_missing_key_is_a_validation_error():
    text = _entry("title: Foo\napplies_to: all\n\nOne paragraph.")
    with pytest.raises(ValueError, match="missing"):
        parse_help_file(text)


def test_two_paragraphs_is_a_validation_error():
    text = _entry("title: Foo\napplies_to: all\nlast_reviewed: 2026-10-05\n\nFirst paragraph.\n\nSecond paragraph.")
    with pytest.raises(ValueError, match="paragraphs"):
        parse_help_file(text)


def test_duplicate_heading_is_a_validation_error():
    one = "title: Foo\napplies_to: all\nlast_reviewed: 2026-10-05\n\nText one."
    text = f"## some_topic\n{one}\n\n## some_topic\n{one}\n"
    with pytest.raises(ValueError, match="duplicate"):
        parse_help_file(text)


def test_intro_text_before_first_heading_is_ignored():
    text = "# Topic help\n\nSome intro prose, no heading yet.\n\n" + _entry(
        "title: Foo\napplies_to: all\nlast_reviewed: 2026-10-05\n\nOne paragraph."
    )
    entries = parse_help_file(text)
    assert list(entries.keys()) == ["some_topic"]


def test_applies_to_all():
    text = _entry("title: Foo\napplies_to: all\nlast_reviewed: 2026-10-05\n\nOne paragraph.")
    entries = parse_help_file(text)
    assert entries["some_topic"].applies_to == "all"


def test_applies_to_list():
    text = _entry("title: Foo\napplies_to: [915iS, 916iS]\nlast_reviewed: 2026-10-05\n\nOne paragraph.")
    entries = parse_help_file(text)
    assert entries["some_topic"].applies_to == ["915iS", "916iS"]


def test_multiline_paragraph_joins_into_one():
    text = _entry("title: Foo\napplies_to: all\nlast_reviewed: 2026-10-05\n\nLine one\nline two\nline three.")
    entries = parse_help_file(text)
    assert entries["some_topic"].template == "Line one line two line three."


# ── Placeholder resolution ──────────────────────────────────────────────────

_CFG = {"limits": [{"id": "oil_temp_max", "param": "oil_temp_f", "label": "Oil temp max",
                     "unit": "°F", "max_val": 248.0, "severity": "WARNING"}],
        "overboost": {"rpm_threshold": 5500, "power_pct_threshold": 100, "limit_s": 300}}
_RULES = {"rules": {"egt_cyl_deviation": {"triggers": [{"type": "baseline_deviation", "n_min": 10}]}}}
_BASELINE_CFG = {"outlier_z_threshold": 2.0}


def test_limit_placeholder_resolves_value_and_unit():
    values, text, unresolved = resolve_template(
        "Limit: {limit:oil_temp_max}.", engine_config=_CFG, rules=_RULES, baseline_config=_BASELINE_CFG,
    )
    assert unresolved == []
    assert values["{limit:oil_temp_max}"] == {"value": 248.0, "unit": "°F"}
    assert text == "Limit: 248.0°F."


def test_profile_placeholder_resolves_dotted_path():
    values, text, unresolved = resolve_template(
        "Threshold: {profile:overboost.rpm_threshold}.", engine_config=_CFG, rules=_RULES, baseline_config=_BASELINE_CFG,
    )
    assert unresolved == []
    assert values["{profile:overboost.rpm_threshold}"] == {"value": 5500, "unit": "rpm"}
    assert text == "Threshold: 5500 rpm."


def test_profile_placeholder_percent_token_not_at_the_end():
    values, text, unresolved = resolve_template(
        "At {profile:overboost.power_pct_threshold}.", engine_config=_CFG, rules=_RULES, baseline_config=_BASELINE_CFG,
    )
    assert unresolved == []
    assert values["{profile:overboost.power_pct_threshold}"]["unit"] == "%"
    assert text == "At 100%."


def test_profile_placeholder_unrecognized_suffix_is_a_validation_error():
    cfg = {**_CFG, "overboost": {**_CFG["overboost"], "widget_count": 3}}
    with pytest.raises(ValueError, match="unit"):
        resolve_template(
            "{profile:overboost.widget_count}", engine_config=cfg, rules=_RULES, baseline_config=_BASELINE_CFG,
        )


def test_rule_placeholder_resolves_trigger_param():
    values, text, unresolved = resolve_template(
        "n_min: {rule:egt_cyl_deviation.baseline_deviation.n_min}.",
        engine_config=_CFG, rules=_RULES, baseline_config=_BASELINE_CFG,
    )
    assert unresolved == []
    assert values["{rule:egt_cyl_deviation.baseline_deviation.n_min}"] == {"value": 10, "unit": None}
    assert text == "n_min: 10."


def test_config_placeholder_resolves():
    values, text, unresolved = resolve_template(
        "z: {config:outlier_z_threshold}.", engine_config=_CFG, rules=_RULES, baseline_config=_BASELINE_CFG,
    )
    assert unresolved == []
    assert values["{config:outlier_z_threshold}"] == {"value": 2.0, "unit": None}
    assert text == "z: 2.0."


def test_unknown_limit_id_is_unresolved_not_an_error():
    values, text, unresolved = resolve_template(
        "{limit:no_such_limit}", engine_config=_CFG, rules=_RULES, baseline_config=_BASELINE_CFG,
    )
    assert unresolved == ["{limit:no_such_limit}"]
    assert text == "{limit:no_such_limit}"
