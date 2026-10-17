"""
Spec 12 Phase 3 — register-driven worsening direction and panel layout
(§15 acceptance 7).
"""
import copy

from slingology_eis import help as _help
from slingology_eis.operations import build_trends_panels, resolve_worsening_direction, update_fleet

from ..contract.test_trends import _fa  # shared synthetic FlightAnalysis builder

_REAL_REGISTER = _help.load_register()


def test_register_worsening_overrides_the_provisional_table():
    assert resolve_worsening_direction("egt_spread", _REAL_REGISTER) == "higher"
    assert resolve_worsening_direction("oil_coolant_ratio", _REAL_REGISTER) == "either"


def test_egt_cyl_deviation_metrics_all_resolve_through_one_topic_entry():
    for n in range(1, 5):
        assert resolve_worsening_direction(f"egt{n}_deviation", _REAL_REGISTER) == "either"


def test_removing_a_topics_trends_field_removes_it_from_the_change_summary_and_panels():
    """Acceptance 7 (engine side): a topic with no `trends` declaration
    gets no shift and no panel — not merely a null worsening direction
    that happens to be ignored downstream."""
    register_without_egt_spread = copy.deepcopy(_REAL_REGISTER)
    entry = next(t for t in register_without_egt_spread["topics"] if t["topic_id"] == "egt_spread")
    entry["trends"] = None

    assert resolve_worsening_direction("egt_spread", register_without_egt_spread) is None
    assert resolve_worsening_direction("egt_spread", _REAL_REGISTER) == "higher"

    fas = [_fa(i, {"egt_spread_mean_f": 50.0 + (i % 3) * 0.1}) for i in range(30)]
    fas += [_fa(30 + i, {"egt_spread_mean_f": 80.0}) for i in range(10)]
    fleet = update_fleet(fas)
    assert "shift" in fleet.metrics["egt_spread"]

    panels_with = build_trends_panels(fleet, _REAL_REGISTER)
    assert any("egt_spread" in [m["metric_id"] for m in p["metrics"]] for p in panels_with)
    panels_without = build_trends_panels(fleet, register_without_egt_spread)
    assert not any("egt_spread" in [m["metric_id"] for m in p["metrics"]] for p in panels_without)


def test_limit_panel_appears_only_for_filtered_or_exceeded_limits():
    from slingology_eis.limits import limit_catalog, load_engine_config

    engine_cfg = load_engine_config("916iS")
    lim = next(l for l in limit_catalog(engine_cfg) if l["id"] == "oil_temp_max")
    fas = [_fa(i, {"lim_oil_temp_max_peak_excess": None}, limits=[lim]) for i in range(5)]
    fleet = update_fleet(fas)

    panels_unfiltered = build_trends_panels(fleet, _REAL_REGISTER)
    assert not any(p.get("limit_id") == "oil_temp_max" for p in panels_unfiltered)

    panels_filtered = build_trends_panels(fleet, _REAL_REGISTER, filtered_limit_ids={"oil_temp_max"})
    assert any(p.get("limit_id") == "oil_temp_max" and p["filtered"] for p in panels_filtered)
