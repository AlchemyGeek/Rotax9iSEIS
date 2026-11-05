"""
Spec 01 v0.23 §12 criterion 11 — the Garmin AXIS log source, on the real
2026-10-14 AXIS log, and G3X logs unchanged (no frame gains a filled row).
"""
import pytest

from slingology_eis import exclusions
from slingology_eis.limits import load_engine_config, resolve_min_flight_duration_min
from slingology_eis.loader import load_log_bytes
from slingology_eis.operations import analyze_ecu, analyze_flight
from slingology_eis.phases import detect_phases

from tests.conftest import LOGS_DIR, requires_flight_logs

AXIS = sorted(LOGS_DIR.glob("e5d43072-*.csv")) if LOGS_DIR.is_dir() else []
requires_axis_log = pytest.mark.skipif(not AXIS, reason="the 2026-10-14 AXIS log isn't in data/logs")
AXIS2 = sorted(LOGS_DIR.glob("d87f9dcb-*.csv")) if LOGS_DIR.is_dir() else []
requires_axis_log_2 = pytest.mark.skipif(not AXIS2, reason="the 2026-10-18 AXIS log isn't in data/logs")


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
        if info.source_format in ("axis", "aircraft_log"):
            continue
        g3x += 1
        assert info.source_format in ("g3x_direct", "garmin_pilot") and "_filled" not in df.columns, p.name
    assert g3x >= 115


@requires_axis_log_2
def test_criterion_12_second_axis_log():
    """Spec 01 v0.24 §12 criterion 12: the 117-column log loads with the same
    mapping, its lane check and shutdown classify, and the log opening with
    the engine running raises nothing. Airborne time is the engine's own
    measure (≈ 121 min, matching the AXIS's onGroundState) — the spec's
    "≈ 107" is reported to its author."""
    raw = AXIS2[0].read_bytes()
    df, info = load_log_bytes(raw, AXIS2[0].name)
    assert info.source_format == "axis" and info.engine_hours == 122.2
    assert df["tach_time_h"].dropna().iloc[-1] == pytest.approx(124.4)
    assert df["ias_kt"].max() == pytest.approx(135, abs=0.5) and df["rpm"].max() == 5820
    phased = detect_phases(df.copy(), verbose=False)
    assert exclusions.classify_for_auto_exclusion(phased, resolve_min_flight_duration_min()) == (None, None)

    fa = analyze_flight(raw, AXIS2[0].name, load_engine_config("916iS"), "916iS")
    assert [q["code"] for q in fa.quality] == ["LOG_RESAMPLED_TO_1HZ"]
    assert fa.metrics["airborne_min"]["value"] == pytest.approx(121, abs=2)
    ecu = analyze_ecu([fa]).to_dict()
    assert ecu["counts"] == {"GROUND_START": 0, "LANE_CHECK": 2, "GROUND": 0, "IN_FLIGHT": 0, "GROUND_SHUTDOWN": 1}
    lane = [r for r in ecu["runs"] if r["classification"] == "LANE_CHECK"]
    assert [r["start_utc"][11:] for r in lane] == ["19:57:28", "19:57:39"] and all(r["lane_check_pair"] for r in lane)
    shutdown, = [r for r in ecu["runs"] if r["classification"] == "GROUND_SHUTDOWN"]
    assert shutdown["start_utc"][11:] == "22:07:09"

    tokens = {t.strip() for v in df["cas_alert"].dropna() for t in str(v).split(" / ")}
    assert {"EFIS ON BKUP", "NAV ON BKUP", "ENGINE ECU"} <= tokens
    assert not {"EFIS ON BACKUP", "NAV ON BACKUP", "A", "TER N"} & tokens


@requires_axis_log
@requires_axis_log_2
def test_both_axis_logs_share_one_mapping():
    """102 and 117 columns: the extra 15 (autopilot/flight-director fields
    and terrain/traffic alerts) map to no registry channel, so both logs
    expose the same registry channels."""
    a, _ = load_log_bytes(AXIS[0].read_bytes(), AXIS[0].name)
    b, _ = load_log_bytes(AXIS2[0].read_bytes(), AXIS2[0].name)
    from slingology_eis.channels import CHANNEL_REGISTRY
    registry_cols = lambda df: set(df.columns) & set(CHANNEL_REGISTRY)
    assert registry_cols(a) == registry_cols(b)


# ── Spec 01 v0.25 §12 criterion 13: the Garmin Pilot aircraft log ──────────

AL = sorted(LOGS_DIR.glob("aircraft-log-*-2026-11-04T194056.csv")) if LOGS_DIR.is_dir() else []
requires_aircraft_log = pytest.mark.skipif(not AL, reason="the 2026-11-04 aircraft log isn't in data/logs")
# The SD-card log of the same flight (19:41:07–20:50:31).
SD_1104 = sorted(LOGS_DIR.glob("6df457a1-*.csv")) if LOGS_DIR.is_dir() else []
requires_sd_1104 = pytest.mark.skipif(not SD_1104, reason="the 2026-11-04 SD-card log isn't in data/logs")


@requires_aircraft_log
def test_criterion_13_ingest():
    import pandas as pd
    raw = AL[0].read_bytes()
    df, info = load_log_bytes(raw, AL[0].name)
    assert info.source_format == "aircraft_log" and info.aircraft_ident == "N117ZS"
    assert info.engine_hours == 127.3 and info.airframe_hours is None
    # timestamp 19:40:56.99 → 20:50:30.74, rounded to the second.
    assert df["datetime"].iloc[0] == pd.Timestamp("2026-11-04 19:40:57")
    assert df["datetime"].iloc[-1] == pd.Timestamp("2026-11-04 20:50:31")
    assert df["datetime"].is_monotonic_increasing and df["datetime"].is_unique
    assert info.filled_share < 0.01
    stamps = pd.to_datetime(df.loc[~df["_filled"], "timestamp"], utc=True).dt.tz_localize(None).dt.round("1s")
    assert (stamps.to_numpy() == df.loc[~df["_filled"], "datetime"].to_numpy()).all()   # never from localTime
    assert df["throttle_pct"].min() == 14 and df["throttle_pct"].max() == 100
    assert df["track_deg"].notna().mean() > 0.99


@requires_aircraft_log
def test_criterion_13_analysis():
    raw = AL[0].read_bytes()
    fa = analyze_flight(raw, AL[0].name, load_engine_config("916iS"), "916iS")
    assert [q["code"] for q in fa.quality] == ["LOG_RESAMPLED_TO_1HZ"]
    assert fa.metrics["airborne_min"]["value"] == pytest.approx(51.5, abs=1)   # spec: ≈ 50
    assert fa.header["engine_hours_start"] == 127.3 and fa.header["engine_hours_end"] == 128.3   # tach1In
    assert fa.metrics["max_ias_kt"]["value"] == pytest.approx(133, abs=0.5)
    df, _ = load_log_bytes(raw, AL[0].name)
    assert df["rpm"].max() == 5820
    ecu = analyze_ecu([fa]).to_dict()
    assert ecu["counts"] == {"GROUND_START": 2, "LANE_CHECK": 2, "GROUND": 0, "IN_FLIGHT": 0, "GROUND_SHUTDOWN": 1}
    starts = [r["start_utc"][11:] for r in ecu["runs"] if r["classification"] == "GROUND_START"]
    assert starts == ["19:40:57", "19:42:06"]                     # boot run (RPM empty), cranking run
    lane = [r for r in ecu["runs"] if r["classification"] == "LANE_CHECK"]
    assert [r["start_utc"][11:] for r in lane] == ["19:48:21", "19:48:33"] and all(r["lane_check_pair"] for r in lane)
    assert [r["mean_rpm"] for r in fa.ecu_runs if r["classification"] == "LANE_CHECK"] == [4106, 3960]
    shutdown, = [r for r in ecu["runs"] if r["classification"] == "GROUND_SHUTDOWN"]
    assert shutdown["start_utc"][11:] == "20:45:54" and shutdown["end_utc"][11:] == "20:50:31"
    assert fa.ecu_lane_check == "both"


@requires_aircraft_log
def test_criterion_13_co_assignment_with_ignore_value():
    raw = AL[0].read_bytes()
    plain, _ = load_log_bytes(raw, AL[0].name, channel_assignments={"gp_analog_7": "co_ppm"})
    assert plain["co_ppm"].max() == 254                            # the boot sentinel, read as CO
    df, _ = load_log_bytes(raw, AL[0].name,
                           channel_assignments={"gp_analog_7": {"channel": "co_ppm", "ignore_value": 254}})
    assert df["co_ppm"].max() < 254 and (df["gp_analog_7"] == 254).any()


@requires_aircraft_log
@requires_sd_1104
def test_criterion_13_sd_card_and_aircraft_log_are_one_flight(tmp_path):
    import shutil
    from slingology_eis import workspace as ws
    registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
    manifest = ws.create_workspace(registry_path, root, "n117zs", "916iS")
    ws_dir = root / manifest.id
    folder = tmp_path / "logs"
    folder.mkdir()
    shutil.copy(SD_1104[0], folder / SD_1104[0].name)
    shutil.copy(AL[0], folder / AL[0].name)
    ws.add_log_folder(ws_dir, str(folder), registry_path)
    result = ws.scan_workspace(ws_dir, registry_path)
    assert len(result.new_flight_ids) == 1 and result.excluded == []
    fid, = ws.list_flight_ids(ws_dir)
    src = ws.load_sources(ws_dir, fid)
    assert sorted(i.via for i in src.imports) == ["aircraft_log", "axis"]
    assert ws.analysed_import(src).filename == AL[0].name
    assert ws.load_flight_analysis(ws_dir, fid).header["start_utc"] == "2026-11-04T19:40:57"


@requires_aircraft_log
def test_criterion_13_renamed_file_has_no_ident(tmp_path):
    _df, info = load_log_bytes(AL[0].read_bytes(), "renamed.csv")
    assert info.aircraft_ident == ""
