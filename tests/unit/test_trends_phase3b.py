"""
Spec 12 v0.3, Session B Phase 3b — engine gaps from Session A (§15
acceptance 2 [z-mode], 11, 12).
"""
from slingology_eis import help as _help
from slingology_eis.limits import limit_catalog, load_engine_config
from slingology_eis.operations import update_fleet

from ..contract.test_trends import _fa  # shared synthetic FlightAnalysis builder

_REGISTER = _help.load_register()


# ── R3b.1 / acceptance 12: takeoff-MAP residual ─────────────────────────────

def test_residual_is_null_without_model_coverage_and_baselined_for_the_rest():
    covered = [
        _fa(i, {
            "takeoff_pressure_alt_ft": 1000.0 + 50 * i,
            "takeoff_oat_c": 15.0 + (i % 5),
            "takeoff_map_inhg": 28.0 - 0.001 * i,
        })
        for i in range(10)
    ]
    uncovered = [_fa(10 + i, {}) for i in range(3)]  # no takeoff-MAP inputs at all
    fleet = update_fleet(covered + uncovered)

    entry = fleet.metrics["takeoff_map_residual_inhg"]
    assert entry["baseline"]["n"] == 10  # only the covered flights have a value
    point_ids = {p["flight_id"] for p in entry["points"]}
    assert all(fa.flight_id not in point_ids for fa in uncovered)
    model = next(m for m in fleet.models if m["id"] == "takeoff_map")
    assert model["coefficients"]  # the strip's caption needs these


def test_residual_metric_gets_a_shift_like_any_other_fleet_metric():
    fas = [
        _fa(i, {
            "takeoff_pressure_alt_ft": 1000.0, "takeoff_oat_c": 15.0,
            "takeoff_map_inhg": 28.0 + (i % 3) * 0.01,
        })
        for i in range(40)
    ]
    fleet = update_fleet(fas)
    assert "shift" in fleet.metrics["takeoff_map_residual_inhg"]


# ── R3b.2 / acceptance 2 (z-mode): z-mode filter-edge level crossing ────────

def test_z_mode_filter_produces_a_filter_edge_crossing():
    """A z-mode filter on oil_temp_max: its own reference-validity check
    (Spec 09 §7.3) needs actual peak_excess events, so the 30 reference
    flights also carry a small lim_oil_temp_max_peak_excess value (a
    tiny real exceedance) distinct from the much larger raw oil_temp_max_f
    jump the Trends-side z-threshold is resolved against."""
    cfg = load_engine_config("916iS")
    lim = next(l for l in limit_catalog(cfg) if l["id"] == "oil_temp_max")

    reference_fas = [
        _fa(i, {"oil_temp_max_f": 190.0 + (i % 5) * 0.5, "lim_oil_temp_max_peak_excess": 1.0 + (i % 5) * 0.2},
            limits=[lim])
        for i in range(30)
    ]
    recent_fas = [_fa(30 + i, {"oil_temp_max_f": 230.0}, limits=[lim]) for i in range(10)]
    fas = reference_fas + recent_fas

    flt = {
        "id": "f1", "limit_id": "oil_temp_max", "magnitude": {"mode": "z", "value": 2.0},
        "note": "watching for drift", "created_at": "x", "history": [],
        "reference": {"flight_ids": [fa.flight_id for fa in reference_fas]},
    }
    fleet = update_fleet(fas, filters=[flt])
    shift = fleet.metrics["oil_temp_peak"]["shift"]
    assert shift["level"]["filter_edge"] is True
    assert shift["qualifies"] is True


def test_z_mode_filter_edge_does_not_fire_below_its_resolved_band():
    cfg = load_engine_config("916iS")
    lim = next(l for l in limit_catalog(cfg) if l["id"] == "oil_temp_max")
    reference_fas = [
        _fa(i, {"oil_temp_max_f": 190.0 + (i % 5) * 0.5, "lim_oil_temp_max_peak_excess": 1.0 + (i % 5) * 0.2},
            limits=[lim])
        for i in range(30)
    ]
    recent_fas = [_fa(30 + i, {"oil_temp_max_f": 191.0}, limits=[lim]) for i in range(10)]
    fas = reference_fas + recent_fas
    flt = {
        "id": "f1", "limit_id": "oil_temp_max", "magnitude": {"mode": "z", "value": 2.0},
        "note": "watching for drift", "created_at": "x", "history": [],
        "reference": {"flight_ids": [fa.flight_id for fa in reference_fas]},
    }
    fleet = update_fleet(fas, filters=[flt])
    shift = fleet.metrics["oil_temp_peak"]["shift"]
    assert shift["level"]["filter_edge"] is False


# ── R3b.3 / D4 / acceptance 11: coupled panels ──────────────────────────────

def test_coupled_cylinder_panel_collapses_to_one_row_naming_the_lead():
    fas = [_fa(i, {"egt2_deviation_f": -2.5 + (i % 3) * 0.1, "egt3_deviation_f": 2.5 + (i % 3) * 0.1}) for i in range(30)]
    fas += [_fa(30 + i, {"egt2_deviation_f": -20.0, "egt3_deviation_f": 25.0}) for i in range(10)]
    fleet = update_fleet(fas)

    rows = fleet.change_summary
    coupled_rows = [r for r in rows if r.get("panel") == "cylinder_balance"]
    assert len(coupled_rows) == 1
    row = coupled_rows[0]
    egt2_z = fleet.metrics["egt2_deviation"]["shift"]["shift_z"]
    egt3_z = fleet.metrics["egt3_deviation"]["shift"]["shift_z"]
    lead = "egt3_deviation" if abs(egt3_z) >= abs(egt2_z) else "egt2_deviation"
    assert row["metric_id"] == lead
    assert set(row["members"]) == {"egt2_deviation", "egt3_deviation"}


def test_coupled_panel_history_records_one_event_with_member_detail(tmp_path):
    from slingology_eis import workspace as ws

    registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
    manifest = ws.create_workspace(registry_path, root, "coupled-hist", "916iS")
    ws_dir = root / manifest.id

    fas = [_fa(i, {"egt2_deviation_f": -2.5 + (i % 3) * 0.1, "egt3_deviation_f": 2.5 + (i % 3) * 0.1}) for i in range(30)]
    fas += [_fa(30 + i, {"egt2_deviation_f": -20.0, "egt3_deviation_f": 25.0}) for i in range(10)]
    fleet = update_fleet(fas)

    history = ws.update_shift_history(ws_dir, fleet)
    assert len(history) == 1
    event = history[0]
    assert event["panel"] == "cylinder_balance"
    assert set(event["members"]) == {"egt2_deviation", "egt3_deviation"}
    assert set(event["member_detail"]) == {"egt2_deviation", "egt3_deviation"}
    assert event["member_detail"]["egt2_deviation"]["shift_z"] == fleet.metrics["egt2_deviation"]["shift"]["shift_z"]

    # Re-running with the same data appends nothing (one open event, not two).
    history_again = ws.update_shift_history(ws_dir, update_fleet(fas))
    assert len(history_again) == 1
    assert history_again[0]["id"] == event["id"]


def test_uncoupled_metric_on_a_coupled_panel_still_ranks_on_its_own():
    """egt_spread shares the cylinder_balance panel but is NOT itself
    coupled (D4: only the four egtN_deviation values sum to zero) — it
    must not be folded into the coupled row."""
    fas = [_fa(i, {"egt_spread_mean_f": 50.0 + (i % 3) * 0.1}) for i in range(30)]
    fas += [_fa(30 + i, {"egt_spread_mean_f": 80.0}) for i in range(10)]
    fleet = update_fleet(fas)
    rows = {r["metric_id"]: r for r in fleet.change_summary}
    assert "egt_spread" in rows
    assert "panel" not in rows["egt_spread"]


