"""
Spec 01 v0.25 §6.5 — the Garmin Pilot "aircraft log", on synthetic files:
header detection, the `timestamp` time base (never localDate/localTime),
the ident from the file name, the mapping, the fingerprint's source
identity, the channel assignment's ignore value, and the SD-card log /
aircraft log of one flight merging into one flight with the aircraft log
analysed (Spec 02 v0.16 §5.7).
"""
import zipfile

import pandas as pd
import pytest

from slingology_eis import workspace as ws
from slingology_eis import workspace_export as wx
from slingology_eis.limits import load_engine_config
from slingology_eis.loader import (
    deduplicate_flights, flight_fingerprint, flight_id, load_log_bytes,
)
from slingology_eis.operations import analyze_flight

from .test_axis_loader import _axis
from .test_server import _flying_log_bytes, _flying_rows

AL_NAME = "aircraft-log-N999XX-2026-10-14T115930.csv"
AL_META = "#hobbsOut=,hobbsIn=,tach1Out=127.3,tach1In=128.3,tach2Out=,tach2In=,\n"
AL_COLUMNS = ["timestamp", "localDate", "localTime", "utcOffset", "systemTime", "flightTime",
              "indicatedBarometricAltitude", "indicatedAirspeed", "verticalSpeed", "trueTrack",
              "engine1FuelFlow", "engine1RevolutionsPerMinute", "e1TachTime", "engine1GeneralPurposeAnalog7",
              "engine1ThrottlePosition", "crewAlertingSystemAlert"]
AL_UNITS = ["YYYY-MM-DDThh:mm:ss.sssZ", "yyyy-mm-dd", "hh:mm:ss", "+/-hh:mm", "millisecond", "hour", "feet",
            "knots", "feet per minute", "degrees", "gallons per hour", "rotations per minute", "hour", "float",
            "percent", "text"]
SD_META = '#airframe_info, log_version="1.04", Product="AXIS", tail_number="N999XX"\n'
SD_COLUMNS = ["localDate", "localTime", "utcOffset", "indicatedBarometricAltitude", "indicatedAirspeed",
              "verticalSpeed", "trueGpsGroundTrack", "engine1FuelFlow", "engine1RevolutionsPerMinute",
              "e1TachTime", "engine1GeneralPurposeAnalog7", "crewAlertingSystemAlert"]
BOOT_S = 40   # the aircraft log opens at avionics boot, 40 s before the SD-card log


def _aircraft_log(rows=None, start="2026-10-14 11:59:30", jitter_ms=(-10, 0, 10, 0), local_lag_s=10,
                  drop=(), analog=lambda i: 3.0, cas=lambda i: "", offset="+00:00") -> bytes:
    """An aircraft log: rows ~1 s apart on `timestamp` with ms jitter; the
    local clock lags by `local_lag_s` (as before a GPS fix). `rows` are
    (rpm, ias, alt, vs); default: 40 s of boot then a synthetic flight."""
    rows = rows if rows is not None else [(0, 0, 100.0, 0)] * BOOT_S + _flying_rows()
    t0 = pd.Timestamp(start)
    lines = []
    for i, (rpm, ias, alt, vs) in enumerate(rows):
        if i in drop:
            continue
        ts = t0 + pd.Timedelta(seconds=i, milliseconds=jitter_ms[i % len(jitter_ms)] + 240)
        local = t0 + pd.Timedelta(seconds=i - local_lag_s)
        lines.append(",".join([
            ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z",
            local.strftime("%Y-%m-%d"), local.strftime("%H:%M:%S"), offset, str(i * 1000), "0.1",
            str(alt), str(ias), str(vs), "270", "6.5", str(rpm), "127.3", str(analog(i)),
            str(14 if rpm == 0 else 96), cas(i),
        ]))
    return (AL_META + "#" + ",".join(AL_UNITS) + "\n" + ",".join(AL_COLUMNS) + "\n"
            + "\n".join(lines) + "\n").encode()


def _sd_card(rows=None, start="2026-10-14 12:00:10", tail="N999XX") -> bytes:
    """The AXIS SD-card log of the same flight: it opens later, at the
    engine start (whole-second local clock, 1 Hz here)."""
    rows = rows if rows is not None else _flying_rows()
    t0 = pd.Timestamp(start)
    lines = []
    for i, (rpm, ias, alt, vs) in enumerate(rows):
        t = t0 + pd.Timedelta(seconds=i)
        lines.append(",".join([t.strftime("%Y-%m-%d"), t.strftime("%H:%M:%S"), "+00:00", str(alt), str(ias),
                               str(vs), "270", "6.5", str(rpm), "127.3", "3.0", ""]))
    units = "#" + ",".join(["x"] * len(SD_COLUMNS)) + "\n"
    return (SD_META.replace("N999XX", tail) + units + ",".join(SD_COLUMNS) + "\n" + "\n".join(lines) + "\n").encode()


# ── Loader ───────────────────────────────────────────────────────────────────

def test_aircraft_log_is_detected_and_its_metadata_read():
    df, info = load_log_bytes(_aircraft_log(), AL_NAME)
    assert info.source_format == "aircraft_log"
    assert info.aircraft_ident == "N999XX" and info.product == "AXIS" and info.system_id == ""
    assert info.engine_hours == 127.3 and info.airframe_hours is None
    assert info.raw["tach1In"] == "128.3" and "_aircraft_log" not in info.raw
    # The SD-card log is still the AXIS format.
    _df, sd = load_log_bytes(_sd_card(), "sd.csv")
    assert sd.source_format == "axis"


def test_time_base_is_timestamp_not_local_time():
    df, info = load_log_bytes(_aircraft_log(), AL_NAME)
    # timestamp starts 11:59:30.230 → rounded to 11:59:30; localTime said 11:59:20.
    assert df["datetime"].iloc[0] == pd.Timestamp("2026-10-14 11:59:30")
    assert df["datetime"].is_monotonic_increasing and df["datetime"].is_unique
    assert (df["datetime"].diff().dropna() == pd.Timedelta(seconds=1)).all()
    assert df["time"].iloc[0] == "11:59:30"                      # the local columns are rewritten from it
    # Jitter alone leaves nothing to fill.
    assert info.filled_share == 0 and not df["_filled"].any()


def test_a_wrong_local_clock_does_not_move_the_frame():
    a, _ = load_log_bytes(_aircraft_log(local_lag_s=0), AL_NAME)
    b, _ = load_log_bytes(_aircraft_log(local_lag_s=37), AL_NAME)
    assert a["datetime"].equals(b["datetime"])


def test_a_dropped_sample_is_filled_and_the_offset_applied():
    df, info = load_log_bytes(_aircraft_log(drop={100}), AL_NAME)
    assert int(df["_filled"].sum()) == 1 and 0 < info.filled_share < 0.01
    shifted, _ = load_log_bytes(_aircraft_log(offset="-07:00"), AL_NAME)
    assert shifted["datetime"].iloc[0] == pd.Timestamp("2026-10-14 04:59:30")


@pytest.mark.parametrize("name, ident", [
    (AL_NAME, "N999XX"),
    ("aircraft-log-C-GABC-2026-10-14T115930.csv", "C-GABC"),
    ("aircraft-log-N999XX-2026-10-14T115930 (1).csv", "N999XX"),
    ("my flight.csv", ""),
])
def test_ident_comes_from_the_file_name(name, ident):
    _df, info = load_log_bytes(_aircraft_log(), name)
    assert info.aircraft_ident == ident


def test_aircraft_log_mapping():
    df, _ = load_log_bytes(_aircraft_log(), AL_NAME)
    for cid in ("rpm", "ias_kt", "baro_alt_ft", "vs_fpm", "fuel_flow_gph", "tach_time_h", "track_deg",
                "throttle_pct", "gp_analog_7", "cas_alert"):
        assert cid in df.columns, cid
    assert df["throttle_pct"].min() == 14 and df["throttle_pct"].max() == 96
    assert df["track_deg"].iloc[0] == 270
    assert "co_ppm" not in df.columns and "timestamp" in df.columns   # raw, unmapped, harmless


def test_fingerprint_source_identity_is_axis_for_both_formats():
    a, ai = load_log_bytes(_aircraft_log(), AL_NAME)
    s, si = load_log_bytes(_sd_card(), "sd.csv")
    assert flight_fingerprint(a, ai)[:2] == flight_fingerprint(s, si)[:2] == ("N999XX", "AXIS")
    assert flight_id(flight_fingerprint(a, ai)) != flight_id(flight_fingerprint(s, si))   # different start minute
    g, gi = load_log_bytes(_flying_log_bytes(), "g.csv")
    assert flight_fingerprint(g, gi)[1] == gi.system_id


def test_unknown_format_names_every_layout():
    with pytest.raises(ValueError) as e:
        load_log_bytes(b"#something=else\n#a,b\nx,y\n1,2\n", "x.csv")
    msg = str(e.value)
    for layout in ("G3X-direct", "Garmin Pilot export", "AXIS SD-card", "aircraft log", "timestamp,localDate"):
        assert layout in msg, layout


def test_ignore_value_is_missing_under_the_assigned_name_only():
    data = _aircraft_log(analog=lambda i: 254.0 if i < 20 else float(i % 7))
    df, _ = load_log_bytes(data, AL_NAME, channel_assignments={"gp_analog_7": {"channel": "co_ppm", "ignore_value": 254}})
    assert df["co_ppm"].iloc[:20].isna().all() and df["co_ppm"].max() == 6
    assert (df["gp_analog_7"].iloc[:20] == 254).all()              # the raw channel keeps them
    plain, _ = load_log_bytes(data, AL_NAME, channel_assignments={"gp_analog_7": "co_ppm"})
    assert plain["co_ppm"].max() == 254


def test_analysis_of_an_aircraft_log():
    fa = analyze_flight(_aircraft_log(), AL_NAME, load_engine_config("916iS"), "916iS")
    assert [q["code"] for q in fa.quality if q["code"] == "LOG_RESAMPLED_TO_1HZ"] == ["LOG_RESAMPLED_TO_1HZ"]
    resampled, = [q for q in fa.quality if q["code"] == "LOG_RESAMPLED_TO_1HZ"]
    assert resampled["refs"]["source_format"] == "aircraft_log"
    assert fa.header["engine_hours_start"] == 127.3 and fa.header["aircraft"]["ident"] == "N999XX"
    assert fa.header["engine_hours_end"] == 128.3                  # tach1In, not start + duration
    assert "throttle_pct" not in fa.available_channels             # raw, not charted by default


def test_cli_dedup_prefers_the_aircraft_log():
    a = load_log_bytes(_aircraft_log(), AL_NAME)
    s = load_log_bytes(_sd_card(rows=_flying_rows(n_cruise=900)), "sd.csv")   # more rows, still loses
    kept = deduplicate_flights([s, a], verbose=False)
    assert [info.source_format for _df, info in kept] == ["aircraft_log"]


# ── Workspace: the SD-card log and the aircraft log of one flight ──────────

def _workspace(tmp_path):
    registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
    manifest = ws.create_workspace(registry_path, root, "al", "916iS")
    folder = tmp_path / "logs"
    folder.mkdir()
    ws_dir = root / manifest.id
    ws.add_log_folder(ws_dir, str(folder), registry_path)
    return registry_path, ws_dir, folder


def _vias(ws_dir, fid):
    return sorted(i.via for i in ws.load_sources(ws_dir, fid).imports)


def test_scan_merges_an_overlap_pair_and_analyses_the_aircraft_log(tmp_path):
    registry_path, ws_dir, folder = _workspace(tmp_path)
    (folder / "a-sd.csv").write_bytes(_sd_card())        # listed first
    (folder / AL_NAME).write_bytes(_aircraft_log())
    result = ws.scan_workspace(ws_dir, registry_path)
    assert len(result.new_flight_ids) == 1 and result.excluded == []
    fid, = ws.list_flight_ids(ws_dir)
    assert _vias(ws_dir, fid) == ["aircraft_log", "axis"]
    fa = ws.load_flight_analysis(ws_dir, fid)
    assert fa.header["start_utc"] == "2026-10-14T11:59:30"   # the aircraft log's start
    assert ws.analysed_import(ws.load_sources(ws_dir, fid)).via == "aircraft_log"
    assert ws.source_filename(ws_dir, fid) == AL_NAME
    # A rescan changes nothing.
    again = ws.scan_workspace(ws_dir, registry_path)
    assert again.new_flight_ids == [] and again.rematched_flight_ids == [] and ws.list_flight_ids(ws_dir) == [fid]


def test_same_format_overlap_still_drops_one(tmp_path):
    registry_path, ws_dir, folder = _workspace(tmp_path)
    (folder / "a.csv").write_bytes(_sd_card())
    (folder / "b.csv").write_bytes(_sd_card(rows=_flying_rows()[:-60], start="2026-10-14 12:01:10")[:])
    result = ws.scan_workspace(ws_dir, registry_path)
    assert len(result.new_flight_ids) == 1 and len(result.excluded) == 1


def test_exact_match_pair_analyses_the_aircraft_log(tmp_path):
    """Both start in the same minute (one fingerprint): the aircraft log is
    analysed though the SD-card file is listed and read first."""
    registry_path, ws_dir, folder = _workspace(tmp_path)
    (folder / "a-sd.csv").write_bytes(_sd_card(start="2026-10-14 11:59:50"))
    (folder / AL_NAME).write_bytes(_aircraft_log(rows=[(0, 0, 100.0, 0)] * 15 + _flying_rows(),
                                                 start="2026-10-14 11:59:35"))
    ws.scan_workspace(ws_dir, registry_path)
    fid, = ws.list_flight_ids(ws_dir)
    assert _vias(ws_dir, fid) == ["aircraft_log", "axis"]
    assert ws.load_flight_analysis(ws_dir, fid).header["start_utc"] == "2026-10-14T11:59:35"


def test_aircraft_log_arriving_later_reanalyses_the_flight_under_its_id(tmp_path):
    registry_path, ws_dir, folder = _workspace(tmp_path)
    (folder / "a-sd.csv").write_bytes(_sd_card())
    ws.scan_workspace(ws_dir, registry_path)
    fid, = ws.list_flight_ids(ws_dir)
    before = ws.load_flight_analysis(ws_dir, fid)
    assert before.header["start_utc"] == "2026-10-14T12:00:10"

    (folder / AL_NAME).write_bytes(_aircraft_log())
    result = ws.scan_workspace(ws_dir, registry_path)
    assert result.new_flight_ids == [] and fid in result.reanalyzed_flight_ids
    assert ws.list_flight_ids(ws_dir) == [fid] and _vias(ws_dir, fid) == ["aircraft_log", "axis"]
    after = ws.load_flight_analysis(ws_dir, fid)
    assert after.flight_id == fid and after.header["start_utc"] == "2026-10-14T11:59:30"
    assert after.source_keys != before.source_keys     # analysed from the aircraft log now
    # A stale-engine re-analysis keeps reading the aircraft log, under the same id.
    after.provenance["engine_version"] = "0.0.0"
    ws.save_flight_analysis(ws_dir, after)
    again = ws.scan_workspace(ws_dir, registry_path)
    assert again.reanalyzed_flight_ids == [fid]
    assert ws.load_flight_analysis(ws_dir, fid).header["start_utc"] == "2026-10-14T11:59:30"


def test_sd_card_log_arriving_later_is_recorded_not_analysed(tmp_path):
    registry_path, ws_dir, folder = _workspace(tmp_path)
    (folder / AL_NAME).write_bytes(_aircraft_log())
    ws.scan_workspace(ws_dir, registry_path)
    fid, = ws.list_flight_ids(ws_dir)
    key = ws.load_flight_analysis(ws_dir, fid).analysis_key
    (folder / "a-sd.csv").write_bytes(_sd_card())
    result = ws.scan_workspace(ws_dir, registry_path)
    assert result.new_flight_ids == [] and result.reanalyzed_flight_ids == [] and result.rematched_flight_ids == [fid]
    assert _vias(ws_dir, fid) == ["aircraft_log", "axis"]
    assert ws.load_flight_analysis(ws_dir, fid).analysis_key == key


def test_a_renamed_aircraft_log_does_not_merge(tmp_path):
    """No ident → no pairing (the mixed-aircraft notice asks the pilot)."""
    registry_path, ws_dir, folder = _workspace(tmp_path)
    (folder / "a-sd.csv").write_bytes(_sd_card())
    (folder / "renamed.csv").write_bytes(_aircraft_log())
    ws.scan_workspace(ws_dir, registry_path)
    assert len(ws.list_flight_ids(ws_dir)) == 2


def test_anonymised_export_carries_the_pseudonym_in_the_name(tmp_path):
    registry_path, ws_dir, folder = _workspace(tmp_path)
    (folder / AL_NAME).write_bytes(_aircraft_log())
    ws.scan_workspace(ws_dir, registry_path)
    out = tmp_path / "out"
    out.mkdir()
    result = wx.export_workspace(ws_dir, out, include_logs=True, anonymise=True)
    with zipfile.ZipFile(result.path) as z:
        logs = {n.rsplit("/", 1)[-1]: z.read(n) for n in z.namelist() if "/logs/" in "/" + n and n.endswith(".csv")}
    assert list(logs) == ["aircraft-log-ANON-1-2026-10-14T115930.csv"]
    data = logs["aircraft-log-ANON-1-2026-10-14T115930.csv"]
    _df, info = load_log_bytes(data, "aircraft-log-ANON-1-2026-10-14T115930.csv")
    assert info.aircraft_ident == "ANON-1" and b"N999XX" not in data
