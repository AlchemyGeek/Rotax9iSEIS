"""
Unit tests for the Stage 1 bytes-based core loader (Spec 01 §11 Stage 1),
plus load_directory()'s ground-session detection (Spec: Ground Session
Detection).

Most tests here use fabricated, synthetic log content only — not real
flight data — so they run without any private local logs. The
ground-session tests are the exception: they're gated on real logs
(`requires_flight_logs`) because building a synthetic file that survives
`detect_phases()`'s full state machine end to end would just re-implement
tests/unit/test_phases.py's synthetic fixtures for no added coverage —
what actually needs verifying here is load_directory()'s wiring to
detect_phases()/AIRBORNE_PHASES, not the state machine itself.
"""
import shutil

import pytest

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
