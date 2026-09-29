"""
Unit tests for the Stage 1 bytes-based core loader (Spec 01 §11 Stage 1),
load_directory()'s ground-session detection (Spec: Ground Session
Detection), and its exclusions.json integration (Spec: Workspace Flight
Exclusions).

Most tests here use fabricated, synthetic log content only — not real
flight data — so they run without any private local logs. The
confirmed-real-flight tests are the exception: they're gated on real logs
(`requires_flight_logs`) because they document specific bugs found against
this fleet's actual data, not because synthetic coverage isn't possible.
"""
import shutil

import pandas as pd
import pytest

from slingology_eis import exclusions
from slingology_eis.loader import load_directory, load_log, load_log_bytes
from slingology_eis.phases import AIRBORNE_PHASES

from ..conftest import LOGS_DIR, requires_flight_logs

# A confirmed ground session (RPM peaks at 2290, IAS at 18.2 — taxi and a
# partial run-up, never airborne) and a confirmed real flight, both already
# used elsewhere in the suite (tests/unit/test_phases.py) as known-good
# fixtures.
_GROUND_SESSION_LOG = "log_20260825_194740_KAWO.csv"
_REAL_FLIGHT_LOG = "log_20260408_141810_KTOA.csv"

# A ground run-up that spikes RPM past 4500 (TAXI -> TAKEOFF_ROLL's gate)
# with altitude flat the whole time (158-168 ft) — found while verifying
# this fix against the full fleet. Confirms AIRBORNE_PHASES correctly
# excludes TAKEOFF_ROLL: without that exclusion this file would wrongly
# survive the ground-session filter.
_RUNUP_GROUND_SESSION_LOG = "log_20260706_180003_KAWO.csv"

_META = (
    'aircraft_ident="N999XX", product="GDU 460", system_id="123456789", '
    'unit="1", airframe_hours="10.5", engine_hours="20.1", log_version="7"\n'
)
_HEADER = "Date (yyyy-mm-dd),Time (hh:mm:ss),RPM,Oil Temp (deg F)\n"
_ROWS = (
    "2026-01-01,12:00:00,2000,180\n"
    "2026-01-01,12:00:01,2010,181\n"
    "2026-01-01,12:00:02,2020,182\n"
)


def _g3x_direct_bytes() -> bytes:
    return (_META + _HEADER + _ROWS).encode("utf-8")


_FULL_HEADER = (
    "Date (yyyy-mm-dd),Time (hh:mm:ss),RPM,Oil Temp (deg F),"
    "Indicated Airspeed (kt),Baro Altitude (ft),Vertical Speed (ft/min)\n"
)


def _flight_csv_bytes(rows: list[dict], timestamps: list) -> bytes:
    """Build G3X-direct CSV bytes from row dicts (rpm/ias_kt/baro_alt_ft/
    vs_fpm) and an explicit per-row timestamp list — lets tests control
    real elapsed time (needed for the corrupt_log time-gap rule) rather
    than relying on one-row-per-second."""
    lines = [_FULL_HEADER]
    for ts, row in zip(timestamps, rows):
        lines.append(f"{ts.date()},{ts.time()},{row['rpm']},180,"
                      f"{row['ias_kt']},{row['baro_alt_ft']},{row['vs_fpm']}\n")
    return (_META + "".join(lines)).encode("utf-8")


def _short_hop_rows() -> list[dict]:
    """Ground -> a brief ~1 minute airborne climb -> ground again. Reaches
    CLIMB (so it's not a ground_session) but stays well under the default
    10-minute min_flight_duration_min (so it should be a short_flight)."""
    rows = [{"rpm": 2000.0, "ias_kt": 8.0, "baro_alt_ft": 100.0, "vs_fpm": 0.0} for _ in range(30)]
    rows.append({"rpm": 5000.0, "ias_kt": 40.0, "baro_alt_ft": 105.0, "vs_fpm": 100.0})
    for i in range(60):
        rows.append({"rpm": 5400.0, "ias_kt": 60.0 + i, "baro_alt_ft": 105.0 + i * 30, "vs_fpm": 800.0})
    return rows


def _long_flight_with_gap_rows() -> tuple[list[dict], list]:
    """A genuine ~24-minute flight (climb + sustained cruise, well past
    both the ground_session and short_flight thresholds) with a real
    10-minute gap spliced into its timestamps — the corrupt_log trigger."""
    rows = _short_hop_rows()
    rows += [{"rpm": 5000.0, "ias_kt": 110.0, "baro_alt_ft": 1905.0, "vs_fpm": 0.0} for _ in range(800)]
    timestamps = list(pd.date_range("2026-01-01 12:00:00", periods=300, freq="1s"))
    timestamps += list(pd.date_range(timestamps[-1] + pd.Timedelta(minutes=10),
                                      periods=len(rows) - 300, freq="1s"))
    return rows, timestamps


def _garmin_pilot_bytes() -> bytes:
    return (_META + "#" + _HEADER + _ROWS).encode("utf-8")


def test_load_log_bytes_g3x_direct():
    df, info = load_log_bytes(_g3x_direct_bytes(), "log_20260101_120000_TEST.csv")
    assert info.source_format == "g3x_direct"
    assert info.aircraft_ident == "N999XX"
    assert info.engine_hours == 20.1
    assert len(df) == 3
    assert list(df["rpm"]) == [2000, 2010, 2020]
    assert df["_source_file"].iloc[0] == "log_20260101_120000_TEST.csv"


def test_load_log_bytes_garmin_pilot():
    df, info = load_log_bytes(_garmin_pilot_bytes(), "abc123.csv")
    assert info.source_format == "garmin_pilot"
    assert len(df) == 3


def test_load_log_bytes_unrecognized_format():
    bad = b'aircraft_ident="X"\nnot,a,g3x,header\n1,2,3\n'
    try:
        load_log_bytes(bad, "bad.csv")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "unrecognised header format" in str(e)


def test_load_log_is_a_thin_wrapper_over_load_log_bytes(tmp_path):
    path = tmp_path / "log_20260101_120000_TEST.csv"
    path.write_bytes(_g3x_direct_bytes())

    df_path, info_path = load_log(path)
    df_bytes, info_bytes = load_log_bytes(_g3x_direct_bytes(), path.name)

    assert df_path.equals(df_bytes)
    assert info_path == info_bytes


@requires_flight_logs
def test_load_directory_skips_confirmed_ground_session(tmp_path):
    ground_path = LOGS_DIR / _GROUND_SESSION_LOG
    flight_path = LOGS_DIR / _REAL_FLIGHT_LOG
    if not ground_path.exists() or not flight_path.exists():
        pytest.skip("fixture log(s) not present locally")
    shutil.copy(ground_path, tmp_path)
    shutil.copy(flight_path, tmp_path)

    flights = load_directory(str(tmp_path), verbose=False)

    kept_names = {df["_source_file"].iloc[0] for df, _info in flights}
    assert _REAL_FLIGHT_LOG in kept_names
    assert _GROUND_SESSION_LOG not in kept_names
    # Every kept DataFrame carries a populated phase column.
    for df, _info in flights:
        assert "phase" in df.columns
        assert df["phase"].notna().all()


@requires_flight_logs
def test_load_directory_keeps_ground_session_when_skip_disabled(tmp_path):
    ground_path = LOGS_DIR / _GROUND_SESSION_LOG
    if not ground_path.exists():
        pytest.skip("fixture log not present locally")
    shutil.copy(ground_path, tmp_path)

    flights = load_directory(str(tmp_path), skip_ground_sessions=False, verbose=False)

    assert len(flights) == 1
    df, _info = flights[0]
    assert "phase" in df.columns
    # A ground session — no airborne phase anywhere in it.
    assert not any(p in AIRBORNE_PHASES for p in df["phase"].unique())


@requires_flight_logs
def test_load_directory_skips_ground_runup_that_briefly_enters_takeoff_roll(tmp_path):
    path = LOGS_DIR / _RUNUP_GROUND_SESSION_LOG
    if not path.exists():
        pytest.skip("fixture log not present locally")
    shutil.copy(path, tmp_path)

    flights = load_directory(str(tmp_path), verbose=False)

    assert flights == []


# ── Spec: Workspace Flight Exclusions ─────────────────────────────────────

def test_load_directory_persists_ground_session_exclusion(tmp_path):
    logs_dir, ws_dir = tmp_path / "logs", tmp_path / "ws"
    logs_dir.mkdir()
    ws_dir.mkdir()
    rows = [{"rpm": 2000.0, "ias_kt": 8.0, "baro_alt_ft": 100.0, "vs_fpm": 0.0} for _ in range(60)]
    timestamps = list(pd.date_range("2026-01-01 12:00:00", periods=len(rows), freq="1s"))
    (logs_dir / "log_20260101_120000_TEST.csv").write_bytes(_flight_csv_bytes(rows, timestamps))

    flights = load_directory(str(logs_dir), workspace_dir=ws_dir, verbose=False)

    assert flights == []
    recorded = exclusions.load_exclusions(ws_dir)
    assert len(recorded["entries"]) == 1
    assert recorded["entries"][0]["category"] == "ground_session"
    assert recorded["entries"][0]["filename"] == "log_20260101_120000_TEST.csv"


def test_load_directory_short_flight_below_min_duration(tmp_path):
    logs_dir, ws_dir = tmp_path / "logs", tmp_path / "ws"
    logs_dir.mkdir()
    ws_dir.mkdir()
    rows = _short_hop_rows()
    timestamps = list(pd.date_range("2026-01-01 12:00:00", periods=len(rows), freq="1s"))
    (logs_dir / "log_20260101_120000_TEST.csv").write_bytes(_flight_csv_bytes(rows, timestamps))

    flights = load_directory(str(logs_dir), workspace_dir=ws_dir, verbose=False)

    assert flights == []
    entry = exclusions.load_exclusions(ws_dir)["entries"][0]
    assert entry["category"] == "short_flight"
    assert "min" in entry["reason"]


def test_load_directory_short_flight_rule_disabled_by_zero_config(tmp_path, monkeypatch):
    logs_dir, ws_dir = tmp_path / "logs", tmp_path / "ws"
    logs_dir.mkdir()
    ws_dir.mkdir()
    rows = _short_hop_rows()
    timestamps = list(pd.date_range("2026-01-01 12:00:00", periods=len(rows), freq="1s"))
    (logs_dir / "log_20260101_120000_TEST.csv").write_bytes(_flight_csv_bytes(rows, timestamps))
    monkeypatch.setattr("slingology_eis.loader.resolve_min_flight_duration_min", lambda *a, **k: 0)

    flights = load_directory(str(logs_dir), workspace_dir=ws_dir, verbose=False)

    assert len(flights) == 1
    assert exclusions.load_exclusions(ws_dir)["entries"] == []


def test_load_directory_corrupt_log_time_gap(tmp_path):
    logs_dir, ws_dir = tmp_path / "logs", tmp_path / "ws"
    logs_dir.mkdir()
    ws_dir.mkdir()
    rows, timestamps = _long_flight_with_gap_rows()
    (logs_dir / "log_20260101_120000_TEST.csv").write_bytes(_flight_csv_bytes(rows, timestamps))

    flights = load_directory(str(logs_dir), workspace_dir=ws_dir, verbose=False)

    assert flights == []
    entry = exclusions.load_exclusions(ws_dir)["entries"][0]
    assert entry["category"] == "corrupt_log"


def test_load_directory_skips_already_excluded_without_reparsing(tmp_path):
    logs_dir, ws_dir = tmp_path / "logs", tmp_path / "ws"
    logs_dir.mkdir()
    ws_dir.mkdir()
    # A file that would fail to parse if load_directory ever tried —
    # proves the existing exclusions.json entry short-circuits before
    # load_log() runs, as the spec requires ("don't re-run detection").
    (logs_dir / "log_20260101_120000_TEST.csv").write_bytes(b"not,a,valid,g3x,file\n1,2,3,4,5\n")
    exclusions.add_auto_exclusion(ws_dir, "log_20260101_120000_TEST.csv", "user_defined", "pre-recorded")

    flights = load_directory(str(logs_dir), workspace_dir=ws_dir, verbose=False)

    assert flights == []


def test_load_directory_respects_user_override(tmp_path):
    logs_dir, ws_dir = tmp_path / "logs", tmp_path / "ws"
    logs_dir.mkdir()
    ws_dir.mkdir()
    rows = [{"rpm": 2000.0, "ias_kt": 8.0, "baro_alt_ft": 100.0, "vs_fpm": 0.0} for _ in range(60)]
    timestamps = list(pd.date_range("2026-01-01 12:00:00", periods=len(rows), freq="1s"))
    filename = "log_20260101_120000_TEST.csv"
    (logs_dir / filename).write_bytes(_flight_csv_bytes(rows, timestamps))

    assert load_directory(str(logs_dir), workspace_dir=ws_dir, verbose=False) == []

    exclusions.set_user_override(ws_dir, filename, True, "intentional ground run-up test")
    flights = load_directory(str(logs_dir), workspace_dir=ws_dir, verbose=False)
    assert len(flights) == 1
    assert flights[0][0]["_source_file"].iloc[0] == filename

    exclusions.set_user_override(ws_dir, filename, False)
    assert load_directory(str(logs_dir), workspace_dir=ws_dir, verbose=False) == []


def test_load_directory_without_workspace_dir_does_not_persist(tmp_path):
    rows = [{"rpm": 2000.0, "ias_kt": 8.0, "baro_alt_ft": 100.0, "vs_fpm": 0.0} for _ in range(60)]
    timestamps = list(pd.date_range("2026-01-01 12:00:00", periods=len(rows), freq="1s"))
    (tmp_path / "log_20260101_120000_TEST.csv").write_bytes(_flight_csv_bytes(rows, timestamps))

    flights = load_directory(str(tmp_path), verbose=False)

    assert flights == []
    assert not (tmp_path / "exclusions.json").exists()
