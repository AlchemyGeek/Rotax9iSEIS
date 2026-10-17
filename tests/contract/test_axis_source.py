"""
Spec 01 v0.23 §12 criterion 11 — the Garmin AXIS log source, on the real
2026-10-14 AXIS log, and G3X logs unchanged (no frame gains a filled row).
"""
import pytest

from slingology_eis import exclusions
from slingology_eis.limits import load_engine_config, resolve_min_flight_duration_min
from slingology_eis.loader import load_log_bytes
from slingology_eis.operations import analyze_flight
from slingology_eis.phases import detect_phases

from tests.conftest import LOGS_DIR, requires_flight_logs

AXIS = sorted(LOGS_DIR.glob("e5d43072-*.csv")) if LOGS_DIR.is_dir() else []
requires_axis_log = pytest.mark.skipif(not AXIS, reason="the 2026-10-14 AXIS log isn't in data/logs")


@requires_axis_log
def test_criterion_11_ingest():
    raw = AXIS[0].read_bytes()
    df, info = load_log_bytes(raw, AXIS[0].name)
    assert info.source_format == "axis" and info.aircraft_ident == "N117ZS"
    assert info.engine_hours == 119.6 and info.airframe_hours is None
    assert len(df) == 2722
    assert str(df["datetime"].iloc[0].time()) == "18:24:47" and str(df["datetime"].iloc[-1].time()) == "19:10:08"
    assert int(df["_filled"].sum()) == 439 and info.filled_share == pytest.approx(0.16, abs=0.01)
    for cid in ("rpm", "map_inhg", "power_pct", "oil_temp_f", "coolant_temp_f", "oil_press_psi", "fuel_press_psi",
                "fuel_flow_gph", "egt1_f", "egt2_f", "egt3_f", "egt4_f", "fuel_qty_l_gal", "fuel_qty_r_gal",
                "ias_kt", "baro_alt_ft", "press_alt_ft", "oat_c", "da_ft"):
        assert df[cid].notna().mean() > 0.99, cid
    assert {"gp_analog_3", "gp_analog_7"} <= set(df.columns) and "co_ppm" not in df.columns

    with_co, _ = load_log_bytes(raw, AXIS[0].name, channel_assignments={"gp_analog_7": "co_ppm"})
    assert with_co["co_ppm"].min() == 0 and with_co["co_ppm"].max() == 22
    alert = with_co["cas_alert"].fillna("").str.contains("CO PPM")
    assert alert.any() and (with_co.loc[alert, "co_ppm"] >= 10).all()


@requires_axis_log
def test_criterion_11_analysis():
    raw = AXIS[0].read_bytes()
    df, _info = load_log_bytes(raw, AXIS[0].name)
    df = detect_phases(df, verbose=False)
    assert exclusions.classify_for_auto_exclusion(df, resolve_min_flight_duration_min()) == (None, None)
    assert df["ias_kt"].max() == pytest.approx(126, abs=0.5)
    assert df["baro_alt_ft"].max() == 6520 and df["rpm"].max() == 5900
    fa = analyze_flight(raw, AXIS[0].name, load_engine_config("916iS"), "916iS")
    assert fa.metrics["airborne_min"]["value"] == pytest.approx(38, abs=1)
    assert [q["code"] for q in fa.quality] == ["LOG_RESAMPLED_TO_1HZ"]
    assert not [e for e in fa.exceedances if e.get("source") == "cas"]          # no ENGINE ECU CAS events
    assert all(r["classification"] != "IN_FLIGHT" for r in fa.ecu_runs)


@requires_flight_logs
def test_no_g3x_frame_is_resampled():
    g3x = 0
    for p in sorted(LOGS_DIR.glob("*.csv")):
        df, info = load_log_bytes(p.read_bytes(), p.name)
        if info.source_format == "axis":
            continue
        g3x += 1
        assert info.source_format in ("g3x_direct", "garmin_pilot") and "_filled" not in df.columns, p.name
    assert g3x >= 115
