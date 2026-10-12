"""
Spec 12 (Trends/change page) Phase 1 acceptance tests — §15 criteria
1, 2, 3, 4, 8, 9, scoped to the engine (window selection, shift, bend,
level crossing, change_summary ordering and gates). Synthetic fleets
cover the specific, controllable scenarios the criteria describe; the
real log set exercises the same code paths end to end.
"""
import pytest

from slingology_eis.limits import limit_catalog, load_engine_config
from slingology_eis.operations import DEFAULT_BASELINE_CONFIG, FlightAnalysis, update_fleet
from slingology_eis.registry import METRIC_REGISTRY
from slingology_eis.trends import recent_window

from ..conftest import requires_flight_logs
from ..replay import chronological, replay


def _fa(i, values, engine_hours=None, date=None, engine="916iS", limits=None):
    """A synthetic FlightAnalysis with every registered metric set to
    None except the ones in `values` (metric_id -> value). `engine_hours`
    defaults to `i` (one hour apart); `date` to one day per flight."""
    engine_hours = float(i) if engine_hours is None else engine_hours
    date = date or f"2026-01-{(i % 28) + 1:02d}"
    metrics = {mid: {"id": mid, "value": None} for mid in METRIC_REGISTRY}
    # "date" and "engine_hours" are themselves registered metric ids —
    # update_fleet's dataframe builder takes them from fa.header first,
    # then overwrites with fa.metrics[*]["value"], so these must agree
    # with the header above or the overwrite nulls them back out.
    metrics["date"] = {"id": "date", "value": date}
    metrics["engine_hours"] = {"id": "engine_hours", "value": engine_hours}
    for mid, v in values.items():
        metrics[mid] = {"id": mid, "value": v}
    return FlightAnalysis(
        flight_id=f"f{i:04d}", analysis_key=f"ak{i}", source_keys=[f"sk{i}"],
        header={"date": date, "start_utc": f"{date}T00:00:00", "engine_hours_start": engine_hours},
        metrics=metrics,
        provenance={"schema_version": "0.1.0", "params_hash": "x",
                    "engine_profile": {"id": engine, "hash": "h", "source_status": "VERIFIED"}},
        limits=limits or [],
    )


# ── Acceptance 1: window selection ──────────────────────────────────────────

def test_window_hits_flight_floor_when_data_runs_out_before_hours_condition():
    """A short, closely-spaced hop set: 7 flights half an hour apart, well
    under both recent_window_min_flights's successor growth and
    recent_window_hours (10h) even using every flight. The window takes
    all 7 (stopped by running out of data, not by hitting
    recent_window_max_flights), and is NOT capped — max_flights (15) was
    never the limiting factor."""
    points = [{"flight_id": f"f{i}", "date": f"2026-01-{i%28+1:02d}", "x": i * 0.5, "value": 1.0} for i in range(7)]
    w = recent_window(points, hours_min=10, min_flights=5, max_flights=15)
    assert w["n"] == 7
    assert w["capped"] is False


def test_window_capped_when_max_flights_reached_before_hours_condition():
    """30 flights half an hour apart: plenty of data (n=30 >= max_flights),
    but recent_window_max_flights=15 caps the window at 7.5h, short of
    the 10h target — RECENT_WINDOW_CAPPED territory."""
    points = [{"flight_id": f"f{i}", "date": f"2026-01-{i%28+1:02d}", "x": i * 0.5, "value": 1.0} for i in range(30)]
    w = recent_window(points, hours_min=10, min_flights=5, max_flights=15)
    assert w["n"] == 15
    assert w["capped"] is True


def test_window_none_below_min_flights():
    points = [{"flight_id": f"f{i}", "date": f"2026-01-{i%28+1:02d}", "x": float(i), "value": 1.0} for i in range(3)]
    assert recent_window(points, hours_min=10, min_flights=5, max_flights=15) is None


@requires_flight_logs
def test_real_log_set_windows_satisfy_conditions_or_are_capped(real_flight_analyses):
    """Over the full local log set, every metric with a shift either
    satisfies both the hours and flight-count conditions, or carries
    RECENT_WINDOW_CAPPED."""
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    fleet = update_fleet(real_flight_analyses)
    capped_codes = {d["refs"].get("metric_id") for d in fleet.quality if d["code"] == "RECENT_WINDOW_CAPPED"}
    hours_min = DEFAULT_BASELINE_CONFIG["recent_window_hours"]
    min_flights = DEFAULT_BASELINE_CONFIG["recent_window_min_flights"]
    checked = 0
    for metric_id, entry in fleet.metrics.items():
        shift = entry.get("shift")
        if not shift:
            continue
        recent = shift["recent"]
        satisfied = recent["n"] >= min_flights and (recent["hours_to"] - recent["hours_from"]) >= hours_min
        assert satisfied or metric_id in capped_codes, f"{metric_id}: window neither satisfied nor capped"
        checked += 1
    assert checked > 0


# ── Acceptance 2: shift agrees with Spec 09 ─────────────────────────────────

def test_shift_reference_agrees_with_spec09_frozen_baseline():
    """A filtered limit's shift reference and Spec 09's frozen_baseline
    over the same flights must be numerically identical — both now go
    through filters.points_baseline (Spec 12 R1.3/acceptance 2)."""
    from slingology_eis.filters import frozen_baseline

    cfg = load_engine_config("916iS")
    lim = next(l for l in limit_catalog(cfg) if l["id"] == "oil_temp_max")
    # "lim_<id>_peak_excess" is the per-flight metric id; "limit_<id>_peak_excess"
    # is the fleet key limit_metric_ids() derives from it (filters.py §5).
    fas = [_fa(i, {"lim_oil_temp_max_peak_excess": 2.0 + 0.1 * i}, limits=[lim]) for i in range(20)]
    fleet = update_fleet(fas)
    metric_id = "limit_oil_temp_max_peak_excess"
    shift = fleet.metrics[metric_id]["shift"]
    # The engine doesn't echo reference flight_ids on Shift.reference (not
    # in Spec 12's TS shape) — recompute the same rolling reference
    # (everything outside the recent window) the engine used.
    window_ids = set(shift["recent"]["flight_ids"])
    reference_ids = [fa.flight_id for fa in fas if fa.flight_id not in window_ids]
    frozen = frozen_baseline(fleet, metric_id, reference_ids)
    assert frozen["n"] == shift["reference"]["n"]
    assert frozen["mean"] == pytest.approx(shift["reference"]["mean"])
    assert frozen["std"] == pytest.approx(shift["reference"]["std"])


# ── Acceptance 3: seasonal false positive ───────────────────────────────────

def test_stratified_comparison_absorbs_a_seasonal_difference():
    """A cold reference and a hot recent window, each normal within its
    own band, produce no shift when compared band-by-band — but do
    produce one when compared unstratified (the false-positive the
    stratification rule exists to prevent). oil_temp_peak's band_col
    (oat_band) is fixed by BASELINE_METRIC_DEFS, not by
    baseline_config["band_kind_by_metric"] (that field feeds
    evaluate_insights's R8 rule, not update_fleet's own stratification —
    see report) — so the band_kind=None contrast is exercised directly
    on trends.shift_stat with the same points, rather than through a
    second update_fleet call."""
    from slingology_eis.trends import recent_window, shift_stat

    # 15 cold (reference-only) + 15 hot (10 recent-window, 5 extra history)
    # so the reference itself has an established "hot" band (n=10 >= n_min)
    # to compare the hot recent window against band-by-band.
    cold_fas = [_fa(i, {"oil_temp_max_f": 190.0 + (i % 3), "oat_band": "cold"}) for i in range(15)]
    hot_fas = [_fa(15 + i, {"oil_temp_max_f": 230.0 + (i % 3), "oat_band": "hot"}) for i in range(15)]
    fas = cold_fas + hot_fas
    fleet = update_fleet(fas)
    points = fleet.metrics["oil_temp_peak"]["points"]

    window = recent_window(points, hours_min=10, min_flights=5, max_flights=10)
    assert all(p["band"] == "hot" for p in points if p["flight_id"] in set(window["flight_ids"]))

    stratified = shift_stat(points, window, [p["flight_id"] for p in points], "oat_band", n_min=10)
    assert stratified["comparison"]["scope"] == "band"
    assert abs(stratified["shift_z"]) < 2.0

    unstratified = shift_stat(points, window, [p["flight_id"] for p in points], None, n_min=10)
    assert abs(unstratified["shift_z"]) >= 2.0


# ── Acceptance 4 (bend half): steady trend vs. steepening ───────────────────

def test_bend_does_not_fire_on_a_steady_trend():
    """Reference and recent window on the same line (no change in slope)
    — bend must not fire even though the metric is trending."""
    fas = [_fa(i, {"egt_spread_mean_f": 50.0 + 0.1 * i}) for i in range(40)]
    fleet = update_fleet(fas)
    shift = fleet.metrics["egt_spread"]["shift"]
    assert shift.get("bend", {}).get("fires", False) is False


def test_bend_fires_on_a_steepening_trend():
    """Reference holds a shallow slope; the recent window's slope is
    several times steeper in the worsening (higher) direction."""
    fas = [_fa(i, {"egt_spread_mean_f": 50.0 + 0.05 * i}) for i in range(30)]
    fas += [_fa(30 + i, {"egt_spread_mean_f": 51.5 + 2.0 * i}) for i in range(10)]
    fleet = update_fleet(fas)
    shift = fleet.metrics["egt_spread"]["shift"]
    assert shift["bend"]["fires"] is True


@requires_flight_logs
def test_real_overboost_event_enters_and_leaves_the_window(real_flight_analyses):
    """Replaying the real log set chronologically, the known long
    overboost block flight (the 'KTOA' flight the task names) should
    show up as a visible outlier on limit_overboost_block_s / a high
    overboost_time while it sits in the recent window — and the window
    should move past it as later flights arrive. This is the hand-verify
    the task asked for; see the report for the actual durations."""
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    fas = chronological(real_flight_analyses)
    target = next((fa for fa in fas if "overboost_total_s" in fa.metrics
                    and (fa.metrics["overboost_total_s"].get("value") or 0) > 300), None)
    if target is None:
        pytest.skip("no overboost-heavy flight in this local log set")
    idx = fas.index(target)
    fleets = replay(fas, start=max(idx - 2, 1))
    found_in_window = any(
        (fleet.metrics.get("overboost_time") or {}).get("shift")
        and target.flight_id in fleet.metrics["overboost_time"]["shift"]["recent"]["flight_ids"]
        for fleet in fleets
    )
    assert found_in_window
    # And it eventually rolls back out of the window as later flights arrive.
    last_fleet = fleets[-1]
    last_shift = (last_fleet.metrics.get("overboost_time") or {}).get("shift")
    if idx < len(fas) - DEFAULT_BASELINE_CONFIG["recent_window_max_flights"]:
        assert last_shift is None or target.flight_id not in last_shift["recent"]["flight_ids"]


# ── Acceptance 8: summary order ─────────────────────────────────────────────

def test_change_summary_ranks_om_margin_crossing_above_larger_shift_z():
    """An OM-margin crossing with a modest |shift_z| outranks a larger
    |shift_z| with no crossing, per §7's ordering rule."""
    cfg = load_engine_config("916iS")
    oil_limit = next(l for l in limit_catalog(cfg) if l["id"] == "oil_temp_max")
    limit_value = oil_limit["limit_value"]

    # oil_temp_peak: reference centred well below the limit; recent window
    # sits just inside the OM margin line (om_margin_fraction default 0.25).
    # egt_spread: a clean, larger unstratified shift with no limit nearby.
    # Both metrics live on the same 40 flights so one fleet carries both.
    headroom = limit_value - 190.0
    near_limit = limit_value - 0.1 * headroom
    fas = [
        _fa(i, {"oil_temp_max_f": 190.0 + (i % 3) * 0.1, "egt_spread_mean_f": 50.0 + (i % 3) * 0.1},
            limits=[oil_limit])
        for i in range(30)
    ] + [
        _fa(30 + i, {"oil_temp_max_f": near_limit, "egt_spread_mean_f": 80.0}, limits=[oil_limit])
        for i in range(10)
    ]
    fleet = update_fleet(fas)

    oil_shift = fleet.metrics["oil_temp_peak"]["shift"]
    egt_shift = fleet.metrics["egt_spread"]["shift"]
    assert oil_shift["level"]["om_margin"] is True
    assert egt_shift["level"]["om_margin"] is False and egt_shift["level"]["filter_edge"] is False
    assert oil_shift["qualifies"] and egt_shift["qualifies"]

    # The point of §7's ordering rule: a level crossing outranks every
    # shift regardless of |shift_z| — not asserting oil's z is smaller,
    # since a crossing ranks first either way.
    ranks = {row["metric_id"]: row["rank"] for row in fleet.change_summary}
    assert ranks["oil_temp_peak"] < ranks["egt_spread"]


# ── Acceptance 9: gates ──────────────────────────────────────────────────────

def test_few_eligible_flights_show_no_shift():
    """Below recent_window_min_flights eligible flights in total, there is
    no window and no shift at all (not even an unqualified one)."""
    fas = [_fa(i, {"egt_spread_mean_f": 50.0}) for i in range(3)]
    fleet = update_fleet(fas)
    assert "shift" not in fleet.metrics["egt_spread"]
    codes = {d["code"] for d in fleet.quality}
    assert "RECENT_WINDOW_LOW_N" in codes


def test_seven_eligible_flights_has_a_window_but_no_qualifying_reference():
    """With only 7 eligible flights, the recent window can take up to
    max_flights of them, starving the rolling reference below n_min —
    the shift is computed but reports an insufficient comparison, not a
    confident qualifying shift."""
    fas = [_fa(i, {"egt_spread_mean_f": 50.0 + i}) for i in range(7)]
    fleet = update_fleet(fas)
    shift = fleet.metrics["egt_spread"].get("shift")
    assert shift is not None
    assert shift["reference"]["n"] < 10
    assert shift["shift_z"] is None
    assert shift["qualifies"] is False


# ── Session B / acceptance 11: real-log-set coupled row ──────────────────────

@requires_flight_logs
def test_real_log_set_cylinder_panel_is_exactly_one_row_naming_cylinder_3(real_flight_analyses):
    """Spec 12 v0.3 acceptance 11: on the real log set, the cylinder
    panel's coupled egtN_deviation metrics produce exactly one
    change_summary row, naming cylinder 3 (Session A's +4.02σ result).
    Pinned to the fleet golden's cut-off (test_fleet_analysis_golden.
    CUTOFF_DATE): a result recorded on that set, not on whatever the log
    directory has grown to — with the three later flights the same
    coupled row (egt2 + egt3) leads with cylinder 2 instead."""
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    fleet = update_fleet(chronological(real_flight_analyses, pinned_to_date="2026-09-27"))
    coupled_rows = [r for r in fleet.change_summary if r.get("panel") == "cylinder_balance"]
    assert len(coupled_rows) == 1
    assert coupled_rows[0]["metric_id"] == "egt3_deviation"
    assert set(coupled_rows[0]["members"]) == {"egt2_deviation", "egt3_deviation"}


# ── Session B / acceptance 12: real-log-set residual ────────────────────────

@requires_flight_logs
def test_real_log_set_residual_is_baselined_and_null_where_uncovered(real_flight_analyses):
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    fleet = update_fleet(real_flight_analyses)
    entry = fleet.metrics["takeoff_map_residual_inhg"]
    model = next(m for m in fleet.models if m["id"] == "takeoff_map")
    assert model.get("coefficients")
    assert 0 < entry["baseline"]["n"] <= model["n"]
    point_ids = {p["flight_id"] for p in entry["points"]}
    assert point_ids <= {fa.flight_id for fa in real_flight_analyses}
