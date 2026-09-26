"""
Spec 08 — cylinder balance: per-cylinder EGT deviation, hottest cylinder,
the learned "usual hottest" cylinder, and the cylinder_rank /
egt_cyl_deviation insights. Synthetic data only (acceptance §10.2–10.5).
"""
import json
from pathlib import Path

import jsonschema
import numpy as np
import pandas as pd
import pytest

from slingology_eis import topics
from slingology_eis.baselines import established_hot_cylinder
from slingology_eis.egt import egt_health
from slingology_eis.operations import FlightAnalysis, evaluate_insights, update_fleet
from slingology_eis.registry import METRIC_REGISTRY
from slingology_eis.rules import validate_rules

_ROOT = Path(__file__).resolve().parent.parent.parent
_RULES = json.loads((_ROOT / "insight_rules.json").read_text())


def _schema(name):
    return json.loads((_ROOT / "contract" / "schema" / name).read_text())


# ── egt_health ───────────────────────────────────────────────────────────────

def _cruise_df(means, n=200, noise=5.0, seed=0):
    rng = np.random.default_rng(seed)
    d = {f"egt{i + 1}_f": m + rng.normal(0, noise, n) for i, m in enumerate(means)}
    d["phase"] = ["CRUISE"] * n
    d["rpm"] = [5000.0] * n
    return pd.DataFrame(d)


def test_egt_health_deviation_hottest_and_margin():
    h = egt_health(_cruise_df([1400, 1450, 1420, 1380]))
    assert h["hottest_cyl"] == 2
    assert h["hottest_margin_f"] == pytest.approx(30, abs=3)
    # Cyl 2 vs mean of 1, 3, 4 = 1450 - 1400 = +50
    assert h["egt2_deviation_f"] == pytest.approx(50, abs=3)
    assert h["egt4_deviation_f"] == pytest.approx(-43, abs=3)
    assert h["rank_order"][0] == "egt2_f"


def test_egt4_elevation_is_alias_of_egt4_deviation():
    h = egt_health(_cruise_df([1400, 1410, 1405, 1450]))
    assert h["egt4_elevation_f"] == h["egt4_deviation_f"]


def test_rank_stable_true_when_one_cylinder_dominates():
    assert egt_health(_cruise_df([1400, 1400, 1400, 1460]))["rank_stable"] is True


def test_rank_stable_false_when_two_cylinders_trade_places():
    # Cyl 3 and 4 within noise of each other: each hottest ~half the time.
    # (The old mode-uniqueness test called this "stable".)
    assert egt_health(_cruise_df([1300, 1300, 1450, 1450], noise=10))["rank_stable"] is False


# ── established_hot_cylinder ─────────────────────────────────────────────────

def test_established_learned():
    e = established_hot_cylinder([(4, 40.0)] * 9 + [(2, 20.0)] * 3, expected_cyl=None)
    assert e == {"cyl": 4, "share": 0.75, "n": 12, "source": "learned"}


def test_established_ignores_ambiguous_flights():
    # 8 clear cyl-4 flights plus many near-ties: too few usable flights to learn.
    e = established_hot_cylinder([(4, 40.0)] * 8 + [(1, 3.0)] * 10, expected_cyl=4)
    assert e["source"] == "prior" and e["n"] == 8


def test_established_falls_back_to_none_without_prior():
    e = established_hot_cylinder([(4, 40.0)] * 3, expected_cyl=None)
    assert e["source"] == "none" and e["cyl"] is None


def test_established_below_share_uses_prior():
    e = established_hot_cylinder([(4, 40.0)] * 6 + [(2, 40.0)] * 6, expected_cyl=4)
    assert e["source"] == "prior" and e["share"] == 0.5


# ── Synthetic fleets through update_fleet + evaluate_insights ────────────────

def _fa(i, hottest, margin, devs=None, engine="916iS"):
    devs = devs or {n: (margin if n == hottest else -margin / 3) for n in range(1, 5)}
    metrics = {mid: {"id": mid, "value": None} for mid in METRIC_REGISTRY}
    metrics |= {
        "date": {"id": "date", "value": f"2026-01-{i + 1:02d}"},
        "engine_hours": {"id": "engine_hours", "value": 100.0 + i, "unit": "hr"},
        "egt_hottest_cyl": {"id": "egt_hottest_cyl", "value": hottest},
        "egt_hottest_margin_f": {"id": "egt_hottest_margin_f", "value": margin, "unit": "°F"},
        "egt_rank_order": {"id": "egt_rank_order", "value": [hottest] + [n for n in range(1, 5) if n != hottest]},
    }
    for n, v in devs.items():
        metrics[f"egt{n}_deviation_f"] = {"id": f"egt{n}_deviation_f", "value": float(v), "unit": "°F"}
    return FlightAnalysis(
        flight_id=f"f{i:02d}", analysis_key=f"ak{i}", source_keys=[f"sk{i}"],
        header={"date": f"2026-01-{i + 1:02d}", "start_utc": f"2026-01-{i + 1:02d}T00:00:00",
                "engine_hours_start": 100.0 + i},
        metrics=metrics,
        provenance={"schema_version": "0.1.0", "params_hash": "x",
                    "engine_profile": {"id": engine, "hash": "h", "source_status": "VERIFIED"}},
    )


def _hot_insights(fa, fleet, rules=_RULES):
    d = evaluate_insights(fa, fleet, rules).to_dict()
    return next(t for t in d["topics"] if t["topic_id"] == "cylinder_rank")


def test_fleet_learns_cyl2_and_raises_nothing_on_916_profile():
    """§10.2: an aircraft whose cyl 2 runs hottest isn't flagged for
    disagreeing with the 916iS prior."""
    fas = [_fa(i, 2, 30.0) for i in range(15)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    cb = fleet.cylinder_balance
    assert cb["established_hot_cyl"]["cyl"] == 2
    assert cb["established_hot_cyl"]["source"] == "learned"
    for fa in fas:
        assert _hot_insights(fa, fleet)["insights"] == []


def test_switch_for_two_consecutive_flights_raises_exactly_one_warning():
    """§10.3: cyl 4 → cyl 2 by ≥ 20 °F on the last two flights."""
    fas = [_fa(i, 4, 40.0) for i in range(12)] + [_fa(12, 2, 22.0), _fa(13, 2, 25.0)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    fired = [(fa.flight_id, ins) for fa in fas for ins in _hot_insights(fa, fleet)["insights"]]
    assert len(fired) == 1
    fid, ins = fired[0]
    assert fid == "f13"
    assert ins["severity"] == "warning"
    assert "Cyl 2 ran hottest" in ins["message"]["text"] and "usual hottest is Cyl 4" in ins["message"]["text"]
    assert {e["metric_id"] for e in ins["evidence"]} == {"egt2_deviation", "egt4_deviation"}


def test_single_flight_switch_raises_nothing():
    fas = [_fa(i, 4, 40.0) for i in range(12)] + [_fa(12, 2, 30.0), _fa(13, 4, 40.0)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    assert all(_hot_insights(fa, fleet)["insights"] == [] for fa in fas)


def test_switch_below_margin_raises_nothing():
    fas = [_fa(i, 4, 40.0) for i in range(12)] + [_fa(12, 2, 10.0), _fa(13, 2, 12.0)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    assert all(_hot_insights(fa, fleet)["insights"] == [] for fa in fas)


def test_mismatch_against_prior_only_is_info():
    fas = [_fa(i, 2, 30.0) for i in range(3)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    assert fleet.cylinder_balance["established_hot_cyl"]["source"] == "prior"
    ins = _hot_insights(fas[-1], fleet)["insights"]
    assert len(ins) == 1 and ins[0]["severity"] == "info"


def test_no_pattern_912_raises_nothing():
    """§10.4: no prior, nothing learned yet."""
    fas = [_fa(i, 1 + i % 4, 30.0, engine="912iS") for i in range(8)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": None})
    assert fleet.cylinder_balance["established_hot_cyl"]["source"] == "none"
    topic = _hot_insights(fas[-1], fleet)
    assert topic["insights"] == []
    assert "not yet established" in topic["analysis"]["text"]


def test_legacy_rank_changed_condition_still_evaluated():
    rules = json.loads(json.dumps(_RULES))
    rules["rules"]["cylinder_rank"]["triggers"] = [
        {"type": "threshold", "condition": "rank_changed", "severity": "warning"}]
    fas = [_fa(i, 4, 40.0) for i in range(12)] + [_fa(12, 2, 22.0), _fa(13, 2, 25.0)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    assert len(_hot_insights(fas[-1], fleet, rules)["insights"]) == 1


def test_cyl_deviation_flags_the_drifting_cylinder():
    base = {1: -10.0, 2: -12.0, 3: -8.0, 4: 30.0}
    fas = [_fa(i, 4, 38.0, {n: v + (0.5 if i % 2 else -0.5) for n, v in base.items()}) for i in range(12)]
    fas.append(_fa(12, 4, 20.0, {1: -10.0, 2: 15.0, 3: -8.0, 4: 30.0}))
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    d = evaluate_insights(fas[-1], fleet, _RULES).to_dict()
    topic = next(t for t in d["topics"] if t["topic_id"] == "egt_cyl_deviation")
    bd = [i for i in topic["insights"] if i["trigger"] == "baseline_deviation"]
    assert [i["evidence"] for i in bd] == [[{"kind": "metric", "metric_id": "egt2_deviation"}]]
    assert bd[0]["message"]["text"].startswith("Cyl 2:")
    assert set(topic["metric_ids"]) == {f"egt{n}_deviation" for n in range(1, 5)}


def test_shipped_rules_skip_deprecated_egt4_elevation_topic():
    fas = [_fa(i, 4, 40.0) for i in range(3)]
    fleet = update_fleet(fas)
    topic_ids = {t["topic_id"] for t in evaluate_insights(fas[0], fleet, _RULES).topics}
    assert "egt4_elevation" not in topic_ids
    assert {"cylinder_rank", "egt_cyl_deviation"} <= topic_ids


def test_results_validate_against_schemas():
    fas = [_fa(i, 4, 40.0) for i in range(12)] + [_fa(12, 2, 22.0), _fa(13, 2, 25.0)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    jsonschema.validate(json.loads(json.dumps(fleet.to_dict())), _schema("fleet_analysis.schema.json"))
    iset = evaluate_insights(fas[-1], fleet, _RULES)
    jsonschema.validate(iset.to_dict(), _schema("insight_set.schema.json"))


def test_old_fleet_without_cylinder_balance_still_evaluates():
    """§10.5: a fleet cache from before Spec 08."""
    fas = [_fa(i, 4, 40.0) for i in range(3)]
    fleet = update_fleet(fas)
    fleet.cylinder_balance = None
    topic = _hot_insights(fas[0], fleet)
    assert topic["insights"] == []


# ── Rules ────────────────────────────────────────────────────────────────────

def test_trend_either_matches_both_directions():
    rule = {"type": "trend", "direction": "either", "r2_min": 0.5, "n_min": 10}
    for direction in ("increasing", "decreasing"):
        b = {"trend": {"direction": direction, "r_squared": 0.8, "n": 12, "slope": 1.0}}
        assert topics.trend_triggered(b, rule)[0]
    b = {"trend": {"direction": "flat", "r_squared": 0.8, "n": 12, "slope": 0.0}}
    assert not topics.trend_triggered(b, rule)[0]


def test_shipped_rules_validate_clean():
    assert validate_rules(_RULES) == []


def test_validate_rules_rejects_bad_applies_to():
    rules = {"rules": {"x": {"enabled": True, "applies_to": "egt1_deviation", "triggers": []}}}
    assert any(d["severity"] == "error" for d in validate_rules(rules))


def test_rule_level_z_override_applies_to_each_cylinder_metric():
    from slingology_eis.operations import resolve_outlier_z_threshold
    cfg = {"outlier_z_threshold": 2.0, "outlier_z_threshold_overrides": {"egt_cyl_deviation": 3.0}}
    assert resolve_outlier_z_threshold(cfg, "egt2_deviation") == 3.0
    cfg["outlier_z_threshold_overrides"]["egt2_deviation"] = 2.5
    assert resolve_outlier_z_threshold(cfg, "egt2_deviation") == 2.5
    assert resolve_outlier_z_threshold(cfg, "egt_spread") == 2.0
