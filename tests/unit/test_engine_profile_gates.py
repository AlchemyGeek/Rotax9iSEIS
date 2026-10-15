"""
Engine-profile follow-ups to the 912iS OM work (f7554ec, 1073d60, 4a2432e):

- EGT split runs only for an engine whose OM defines one. No egt_spread
  block (912iS: OM-912 i defines none) means no check, no events and no
  EGT split limit anywhere downstream; an incomplete block fails at load.
- 912iS rpm_idle_min carries the idle-established condition (Spec 10
  D16), keyed to its own 1,400 rpm floor.

Synthetic data only; every threshold is read from the profile under test.
"""
import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from slingology_eis.limits import (
    EGT_SPLIT_HIGH_FLOW_ID, EGT_SPLIT_LOW_FLOW_ID, check_exceedances, egt_spread_config,
    limit_catalog, load_engine_config, parse_engine_config, validate_limit_ids,
)
from slingology_eis.operations import FlightAnalysis, FleetAnalysis, evaluate_insights

RULES = json.loads((Path(__file__).resolve().parents[2] / "insight_rules.json").read_text())
SPLIT_IDS = {EGT_SPLIT_HIGH_FLOW_ID, EGT_SPLIT_LOW_FLOW_ID}
T0 = pd.Timestamp("2026-01-01 12:00:00")


def _frame(n, **cols):
    """1 Hz rows from T0."""
    return pd.DataFrame({"datetime": [T0 + pd.Timedelta(seconds=i) for i in range(n)], **cols})


def _offset_s(e):
    return (e.started_at - T0).total_seconds()


def _split_flight(n=120, spread_f=600.0, fuel_flow_lph=20.0):
    """Cruise at high fuel flow with an EGT spread above every profile's
    high-flow split limit (392 °F where one exists)."""
    return _frame(n, phase=["CRUISE"] * n, rpm=[5000.0] * n,
                  egt_spread_f=[spread_f] * n, fuel_flow_lph=[fuel_flow_lph] * n)


def _without_block(engine):
    cfg = copy.deepcopy(load_engine_config(engine))
    cfg.pop("egt_spread", None)
    return cfg


# ── EGT split: no block, no check ────────────────────────────────────────────

def test_915_and_916_check_the_split_from_their_own_block():
    for engine in ("915iS", "916iS"):
        cfg = load_engine_config(engine)
        events = [e for e in check_exceedances(_split_flight(), cfg) if e.limit_id in SPLIT_IDS]
        assert [e.limit_id for e in events] == [EGT_SPLIT_HIGH_FLOW_ID]
        assert events[0].limit_value == cfg["egt_spread"]["high_flow_spread_limit_f"]


@pytest.mark.parametrize("cfg", [load_engine_config("912iS"), _without_block("916iS")], ids=["912iS", "916iS-without-block"])
def test_no_egt_spread_block_means_no_split_check_and_no_split_limit(cfg):
    assert egt_spread_config(cfg) is None
    events = check_exceedances(_split_flight(), cfg)
    assert not [e for e in events if e.limit_id in SPLIT_IDS]
    assert not [e for e in events if e.param == "egt_spread_f"]
    assert not SPLIT_IDS & {lim["id"] for lim in limit_catalog(cfg)}
    validate_limit_ids(cfg)   # loads cleanly


@pytest.mark.parametrize("drop", ["high_flow_threshold_lph", "high_flow_spread_limit_f", "low_flow_spread_limit_f"])
def test_an_incomplete_egt_spread_block_fails_at_load(drop):
    raw = json.loads((Path(__file__).resolve().parents[2] / "engines" / "916iS.json").read_text())
    del raw["egt_spread"][drop]
    with pytest.raises(ValueError, match=f"egt_spread.*incomplete.*{drop}"):
        parse_engine_config(json.dumps(raw), name="test")


@pytest.mark.parametrize("block", [{}, None, {"high_flow_threshold_lph": 3.0, "high_flow_spread_limit_f": "392", "low_flow_spread_limit_f": 932.0}])
def test_an_empty_or_malformed_block_is_an_error_not_an_absence(block):
    raw = json.loads((Path(__file__).resolve().parents[2] / "engines" / "916iS.json").read_text())
    raw["egt_spread"] = block
    with pytest.raises(ValueError, match="egt_spread"):
        parse_engine_config(json.dumps(raw), name="test")


def _fa(cfg, i, spread):
    return FlightAnalysis(
        flight_id=f"f{i:02d}", analysis_key=f"f{i:02d}", source_keys=[f"f{i:02d}"],
        header={"date": f"2026-01-{i + 1:02d}", "start_utc": f"2026-01-{i + 1:02d}T12:00:00",
                "engine_hours_start": 10.0 + i, "engine_hours_end": 10.9 + i},
        phases=[], metrics={"egt_spread_mean_f": {"value": spread}}, exceedances=[], provenance={},
        limits=limit_catalog(cfg),
    )


def _egt_spread_topic(engine):
    cfg = load_engine_config(engine)
    fas = [_fa(cfg, i, 50.0 + i % 3) for i in range(12)]
    points = [{"flight_id": fa.flight_id, "date": fa.header["date"], "x": fa.header["engine_hours_start"],
               "value": fa.metrics["egt_spread_mean_f"]["value"]} for fa in fas]
    fleet = FleetAnalysis(fleet_key="fk", flight_ids=[fa.flight_id for fa in fas],
                          metrics={"egt_spread": {"points": points}}, provenance={"baseline_config": {}})
    iset = evaluate_insights(fas[-1], fleet, RULES)
    return next(t for t in iset.topics if t["topic_id"] == "egt_spread"), iset


def test_egt_spread_topic_takes_its_om_limit_from_the_profile_or_states_none():
    t916, _ = _egt_spread_topic("916iS")
    assert t916["analysis"]["text"].endswith("OM limit: 392°F.")

    t912, iset = _egt_spread_topic("912iS")
    assert "Cruise mean" in t912["analysis"]["text"] and "OM limit" not in t912["analysis"]["text"]
    # No split limit referenced by any topic, insight or limit card.
    assert "egt_split" not in json.dumps(iset.topics) and "392" not in json.dumps(iset.topics)
