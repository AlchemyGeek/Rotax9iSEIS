"""
Unit tests for exclusions.py (docs/specs/08-flight-exclusions.md).

All synthetic — pure JSON/dict logic, no private flight data involved.
Loader-level integration (load_directory() actually using this module)
is covered separately in tests/unit/test_loader.py.
"""
import pytest

from slingology_eis.exclusions import (
    add_auto_exclusion,
    add_user_exclusion,
    exclusion_summary,
    is_excluded,
    load_exclusions,
    save_exclusions,
    set_user_override,
)


def test_load_exclusions_returns_empty_structure_when_file_missing(tmp_path):
    exclusions = load_exclusions(tmp_path)
    assert exclusions == {"version": 1, "entries": []}


def test_save_then_load_roundtrip(tmp_path):
    add_auto_exclusion(tmp_path, "a.csv", "ground_session", "no airborne phase detected")
    reloaded = load_exclusions(tmp_path)
    assert len(reloaded["entries"]) == 1
    assert reloaded["entries"][0]["filename"] == "a.csv"
    assert reloaded["entries"][0]["category"] == "ground_session"
    assert reloaded["entries"][0]["source"] == "auto"
    assert reloaded["entries"][0]["user_override"] is False
    assert (tmp_path / "exclusions.json").exists()


def test_save_exclusions_direct_roundtrip(tmp_path):
    payload = {"version": 1, "entries": [{"filename": "z.csv", "source": "user",
                                           "reason": "r", "category": "user_defined",
                                           "excluded_at": "2026-01-01T00:00:00Z",
                                           "user_override": False}]}
    save_exclusions(tmp_path, payload)
    assert load_exclusions(tmp_path) == payload


def test_is_excluded_true_for_recorded_entry(tmp_path):
    add_auto_exclusion(tmp_path, "a.csv", "ground_session", "reason")
    exclusions = load_exclusions(tmp_path)
    assert is_excluded("a.csv", exclusions) is True


def test_is_excluded_false_for_unknown_filename(tmp_path):
    exclusions = load_exclusions(tmp_path)
    assert is_excluded("never-seen.csv", exclusions) is False


def test_is_excluded_false_when_user_override_true(tmp_path):
    add_auto_exclusion(tmp_path, "a.csv", "ground_session", "reason")
    set_user_override(tmp_path, "a.csv", True, "intentional")
    exclusions = load_exclusions(tmp_path)
    assert is_excluded("a.csv", exclusions) is False


def test_add_auto_exclusion_is_idempotent(tmp_path):
    add_auto_exclusion(tmp_path, "a.csv", "ground_session", "first reason")
    add_auto_exclusion(tmp_path, "a.csv", "ground_session", "second reason — should be ignored")
    exclusions = load_exclusions(tmp_path)
    assert len(exclusions["entries"]) == 1
    assert exclusions["entries"][0]["reason"] == "first reason"


def test_add_auto_exclusion_does_not_clobber_an_override(tmp_path):
    add_auto_exclusion(tmp_path, "a.csv", "ground_session", "reason")
    set_user_override(tmp_path, "a.csv", True, "keep it")
    add_auto_exclusion(tmp_path, "a.csv", "ground_session", "reason")  # e.g. a later rescan
    exclusions = load_exclusions(tmp_path)
    assert len(exclusions["entries"]) == 1
    assert exclusions["entries"][0]["user_override"] is True


def test_add_user_exclusion_replaces_prior_auto_entry(tmp_path):
    add_auto_exclusion(tmp_path, "a.csv", "ground_session", "auto reason")
    add_user_exclusion(tmp_path, "a.csv", "actually a ferry flight")
    exclusions = load_exclusions(tmp_path)
    assert len(exclusions["entries"]) == 1
    entry = exclusions["entries"][0]
    assert entry["category"] == "user_defined"
    assert entry["source"] == "user"
    assert entry["reason"] == "actually a ferry flight"
    assert entry["user_override"] is False


def test_set_user_override_sets_and_clears(tmp_path):
    add_auto_exclusion(tmp_path, "a.csv", "short_flight", "reason")
    set_user_override(tmp_path, "a.csv", True, "pattern work, keep it")
    exclusions = load_exclusions(tmp_path)
    assert exclusions["entries"][0]["user_override"] is True
    assert exclusions["entries"][0]["override_reason"] == "pattern work, keep it"

    set_user_override(tmp_path, "a.csv", False)
    exclusions = load_exclusions(tmp_path)
    assert exclusions["entries"][0]["user_override"] is False
    assert "override_reason" not in exclusions["entries"][0]


def test_set_user_override_raises_for_unknown_filename(tmp_path):
    with pytest.raises(ValueError):
        set_user_override(tmp_path, "never-seen.csv", True)


def test_exclusion_summary_counts_by_category_and_overridden(tmp_path):
    add_auto_exclusion(tmp_path, "a.csv", "ground_session", "r1")
    add_auto_exclusion(tmp_path, "b.csv", "ground_session", "r2")
    add_auto_exclusion(tmp_path, "c.csv", "short_flight", "r3")
    add_user_exclusion(tmp_path, "d.csv", "r4")
    set_user_override(tmp_path, "c.csv", True, "keep it")

    summary = exclusion_summary(load_exclusions(tmp_path))
    assert summary == {
        "ground_session": 2, "short_flight": 1, "corrupt_log": 0,
        "user_defined": 1, "overridden": 1,
    }


def test_exclusion_summary_empty_workspace(tmp_path):
    summary = exclusion_summary(load_exclusions(tmp_path))
    assert summary == {
        "ground_session": 0, "short_flight": 0, "corrupt_log": 0,
        "user_defined": 0, "overridden": 0,
    }
