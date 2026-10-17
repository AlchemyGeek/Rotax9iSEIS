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


def _cylinder_rank_topics(fas, fleet, rules=_RULES):
    """Spec 10 D4: cylinder_rank emits no TopicResult at all any more —
    evaluating every flight must never produce one."""
    return [
        t["topic_id"]
        for fa in fas
        for t in evaluate_insights(fa, fleet, rules).to_dict()["topics"]
        if t["topic_id"] == "cylinder_rank"
    ]


def _flag(fa, fleet, rules=_RULES):
    """hot_cyl_changed is set as a side effect of evaluate_insights (Spec
    08 v0.3 §6) — it's fleet-dependent, so analyze_flight() alone can't
    compute it."""
    evaluate_insights(fa, fleet, rules)
    return fa.hot_cyl_changed


def test_fleet_learns_cyl2_and_raises_nothing_on_916_profile():
    """Spec 08 v0.3 §10 acceptance 2: an aircraft whose cyl 2 runs hottest
    sets no hottest-cylinder flag for disagreeing with the 916iS prior,
    and cylinder_rank emits no TopicResult."""
    fas = [_fa(i, 2, 30.0) for i in range(15)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    cb = fleet.cylinder_balance
    assert cb["established_hot_cyl"]["cyl"] == 2
    assert cb["established_hot_cyl"]["source"] == "learned"
    assert all(_flag(fa, fleet) is False for fa in fas)
    assert _cylinder_rank_topics(fas, fleet) == []


def test_switch_for_two_consecutive_flights_sets_the_flag_on_the_second():
    """Spec 08 v0.3 §10 acceptance 3 (flag part — Phase A scope; the
    egt_cyl_deviation message naming the change is Phase B): cyl 4 → cyl 2
    by ≥ 20 °F for two consecutive flights sets the flag on the second
    one, and cylinder_rank still emits no TopicResult."""
    fas = [_fa(i, 4, 40.0) for i in range(12)] + [_fa(12, 2, 22.0), _fa(13, 2, 25.0)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    flags = {fa.flight_id: _flag(fa, fleet) for fa in fas}
    assert flags["f12"] is False
    assert flags["f13"] is True
    assert all(f is False for fid, f in flags.items() if fid not in ("f12", "f13"))
    assert _cylinder_rank_topics(fas, fleet) == []


def test_single_flight_switch_sets_no_flag():
    fas = [_fa(i, 4, 40.0) for i in range(12)] + [_fa(12, 2, 30.0), _fa(13, 4, 40.0)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    assert all(_flag(fa, fleet) is False for fa in fas)


def test_switch_below_margin_sets_no_flag():
    fas = [_fa(i, 4, 40.0) for i in range(12)] + [_fa(12, 2, 10.0), _fa(13, 2, 12.0)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    assert all(_flag(fa, fleet) is False for fa in fas)


def test_switch_against_a_prior_also_sets_the_flag():
    """The flag isn't limited to a *learned* usual cylinder — only to
    established_hot_cyl's source being "none" (acceptance 4)."""
    fas = [_fa(i, 2, 30.0) for i in range(3)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    assert fleet.cylinder_balance["established_hot_cyl"]["source"] == "prior"
    assert _flag(fas[-1], fleet) is True


def test_no_pattern_912_sets_no_flag():
    """Spec 08 v0.3 §10 acceptance 4: a 912iS workspace with no learned
    pattern and no prior sets no flag."""
    fas = [_fa(i, 1 + i % 4, 30.0, engine="912iS") for i in range(8)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": None})
    assert fleet.cylinder_balance["established_hot_cyl"]["source"] == "none"
    assert all(_flag(fa, fleet) is False for fa in fas)


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


# ── Phase B: D4 deviation message, D8 egt_spread fold-in ───────────────────

def test_switch_names_the_hottest_cylinder_change_in_its_deviation_insight():
    """Spec 08 v0.3 §10 acceptance 3, full: the cyl 4 -> cyl 2 switch not
    only sets the flag (Phase A) but the fired deviation insight for the
    now-hottest cylinder (2) names the change and the usual cylinder (4);
    other cylinders' insights are untouched."""
    fas = [_fa(i, 4, 40.0) for i in range(12)] + [_fa(12, 2, 22.0), _fa(13, 2, 25.0)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    fa13 = fas[-1]
    # hot_cyl_changed is set as a side effect of evaluate_insights (Phase A) —
    # must call it before reading the flag, not after.
    topic = next(t for t in evaluate_insights(fa13, fleet, _RULES).topics if t["topic_id"] == "egt_cyl_deviation")
    assert fa13.hot_cyl_changed is True
    by_cyl = {}
    for ins in topic["insights"]:
        cyl = next(e["metric_id"] for e in ins["evidence"])
        by_cyl[cyl] = ins["message"]["text"]
    assert "It is now the hottest cylinder (usually cylinder 4)." in by_cyl["egt2_deviation"]
    for cyl, text in by_cyl.items():
        if cyl != "egt2_deviation":
            assert "hottest cylinder" not in text
    # cylinder_rank itself still raises nothing (Phase A/D4).
    assert _cylinder_rank_topics([fa13], fleet) == []


def _fa_with_spread(i, hottest, margin, spread, devs=None):
    fa = _fa(i, hottest, margin, devs)
    fa.metrics["egt_spread_mean_f"] = {"id": "egt_spread_mean_f", "value": spread, "unit": "°F"}
    return fa


def test_cyl_deviation_and_spread_together_fold_into_one_insight():
    """Spec 08 v0.3 §10 acceptance 5, first half: a flight where both an
    egt_cyl_deviation trigger and egt_spread's baseline_deviation trigger
    would fire produces one insight (the cylinder's, noting the spread)."""
    base = {1: -10.0, 2: -12.0, 3: -8.0, 4: 30.0}
    fas = [_fa_with_spread(i, 4, 38.0, 40.0 + (1.0 if i % 2 else -1.0),
                           {n: v + (0.5 if i % 2 else -0.5) for n, v in base.items()})
           for i in range(12)]
    # Outlier flight: cyl 2 deviates (as in test_cyl_deviation_flags_the_drifting_cylinder)
    # *and* spread is far outside the stable 40 ± 1°F baseline.
    fas.append(_fa_with_spread(12, 4, 20.0, 90.0, {1: -10.0, 2: 15.0, 3: -8.0, 4: 30.0}))
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    iset = evaluate_insights(fas[-1], fleet, _RULES)
    cyl_topic = next(t for t in iset.topics if t["topic_id"] == "egt_cyl_deviation")
    spread_topic = next(t for t in iset.topics if t["topic_id"] == "egt_spread")

    spread_bd = [i for i in spread_topic["insights"] if i["trigger"] == "baseline_deviation"]
    assert spread_bd == []  # folded into the cylinder insight, not emitted separately

    cyl_bd = [i for i in cyl_topic["insights"] if i["trigger"] == "baseline_deviation"]
    assert len(cyl_bd) == 1 and cyl_bd[0]["message"]["text"].startswith("Cyl 2:")
    assert "EGT spread is also outside its usual range." in cyl_bd[0]["message"]["text"]


def test_spread_alone_fires_its_own_insight_when_no_cylinder_trigger_fires():
    """Spec 08 v0.3 §10 acceptance 5, second half: a divergence-only flight
    (hottest +6°F, coolest -6°F — no single cylinder trigger) produces the
    spread insight alone."""
    base = {1: -2.0, 2: -1.0, 3: 1.0, 4: 2.0}
    fas = [_fa_with_spread(i, 4, 4.0, 40.0 + (1.0 if i % 2 else -1.0),
                           {n: v + (0.3 if i % 2 else -0.3) for n, v in base.items()})
           for i in range(12)]
    # No single cylinder is a std-dev outlier, but spread is far above baseline.
    fas.append(_fa_with_spread(12, 4, 4.0, 95.0, {1: -2.2, 2: -1.1, 3: 1.1, 4: 2.2}))
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    iset = evaluate_insights(fas[-1], fleet, _RULES)
    cyl_topic = next(t for t in iset.topics if t["topic_id"] == "egt_cyl_deviation")
    spread_topic = next(t for t in iset.topics if t["topic_id"] == "egt_spread")

    assert [i for i in cyl_topic["insights"] if i["trigger"] == "baseline_deviation"] == []
    spread_bd = [i for i in spread_topic["insights"] if i["trigger"] == "baseline_deviation"]
    assert len(spread_bd) == 1
    assert "also outside its usual range" not in spread_bd[0]["message"]["text"]


def test_egt4_elevation_and_cylinder_rank_emit_no_topic():
    """Spec 10 D3 (egt4_elevation, removed completely) and D4
    (cylinder_rank, disabled — context only)."""
    fas = [_fa(i, 4, 40.0) for i in range(3)]
    fleet = update_fleet(fas)
    topic_ids = {t["topic_id"] for t in evaluate_insights(fas[0], fleet, _RULES).topics}
    assert "egt4_elevation" not in topic_ids
    assert "cylinder_rank" not in topic_ids
    assert "egt_cyl_deviation" in topic_ids


def test_results_validate_against_schemas():
    fas = [_fa(i, 4, 40.0) for i in range(12)] + [_fa(12, 2, 22.0), _fa(13, 2, 25.0)]
    fleet = update_fleet(fas, engine_config={"expected_hot_cylinder": 4})
    jsonschema.validate(json.loads(json.dumps(fleet.to_dict())), _schema("fleet_analysis.schema.json"))
    iset = evaluate_insights(fas[-1], fleet, _RULES)
    jsonschema.validate(iset.to_dict(), _schema("insight_set.schema.json"))


def test_old_fleet_without_cylinder_balance_still_evaluates():
    """§10.5: a fleet cache from before Spec 08 — no cylinder_balance to
    look the flag up in, so it stays False rather than erroring."""
    fas = [_fa(i, 4, 40.0) for i in range(3)]
    fleet = update_fleet(fas)
    fleet.cylinder_balance = None
    assert _flag(fas[0], fleet) is False
    assert _cylinder_rank_topics(fas, fleet) == []


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
