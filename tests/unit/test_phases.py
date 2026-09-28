"""
Tests for phases.py — regression coverage for three real bugs found
while chasing one user report ("phase detection is consistently failing
to recognize phases", log_20260927_212613_4S2.csv). All three left a
genuine flight classified as one continuous TAXI phase for its entire
duration, each for a different reason:

1. Departure/arrival elevation mismatch (4S2). A short departure taxi
   (few "on the ground" rows) let the field-elevation estimate's
   `.iloc[:60]` window reach straight past it into the landing/taxi-in
   segment — a different field, at a very different elevation. AGL
   (baro_alt - field_elev_ft) was then wrong for the whole flight, and
   TAXI -> TAKEOFF_ROLL's `AGL < 50 ft` gate never opened again once
   airborne.
2. A too-tight simultaneous-sample gate (KACV fixture flight,
   log_20260408_141810_KTOA.csv). TAXI -> TAKEOFF_ROLL required
   `RPM > 4500 AND IAS < 35` on the *same* 1 Hz row. A turbocharged
   Rotax iS can spool from idle to full power within one sample, so IAS
   was already past 35 kt by the very first row where RPM cleared
   4500 — the gate never opened, with no recovery path once missed.
3. A sensor warm-up transient dominating the elevation estimate
   (log_20260613_193731_KAWO.csv). The barometric altimeter read a
   physically-impossible ~-330 ft for about 170 seconds right after
   power-on before settling on the real ~131 ft field elevation. The
   glitch alone was longer than the `.iloc[:60]` cap, so the estimate
   never reached the ~150 stable rows that followed it in the same
   departure window.

A fourth bug, found from a separate report ("flight
log_20260927_181026_KAWO.csv fails to detect phases"), was more severe
than any of the above: ENGINE_START -> WARMUP required `IAS < 10` kt,
but several real aircraft in this fleet have a genuine ground/idle IAS
baseline of 10-25 kt while parked (wind over the pitot, or just this
static system's noise floor) that never dips under 10 kt even once.
Unlike every other phase transition, ENGINE_START has no fallback path
if this gate is missed — every flight passes through it, so a fleet
sweep found 7 real flights (one over 5 hours long) stuck classified as
ENGINE_START for nearly their entire duration.
"""
import numpy as np
import pandas as pd
import pytest

from slingology_eis.loader import load_log_bytes
from slingology_eis.phases import _estimate_field_elevation, detect_phases

from ..conftest import LOGS_DIR, requires_flight_logs


def _synthetic_flight(departure_ground_rows: int, arrival_ground_rows: int,
                       departure_elev: float, arrival_elev: float) -> pd.DataFrame:
    """A minimal flight: a short ground segment at departure_elev, a long
    airborne stretch, then a longer ground segment at arrival_elev — the
    shape behind bug 1 (few departure rows, many arrival rows at a
    different field)."""
    rows = []
    for i in range(departure_ground_rows):
        rows.append({"rpm": 2000.0, "ias_kt": 10.0, "baro_alt_ft": departure_elev})
    for i in range(400):
        rows.append({"rpm": 5000.0, "ias_kt": 110.0, "baro_alt_ft": departure_elev + 5000})
    for i in range(arrival_ground_rows):
        rows.append({"rpm": 1800.0, "ias_kt": 12.0, "baro_alt_ft": arrival_elev})
    df = pd.DataFrame(rows)
    df["vs_fpm"] = 0.0
    df["press_alt_ft"] = df["baro_alt_ft"]
    df["oil_temp_f"] = 180.0
    df["power_pct"] = np.where(df["rpm"] > 4000, 80.0, 20.0)
    return df


def test_field_elevation_uses_departure_not_arrival_when_departure_segment_is_short():
    df = _synthetic_flight(departure_ground_rows=14, arrival_ground_rows=46,
                            departure_elev=646.0, arrival_elev=137.0)
    assert _estimate_field_elevation(df) == 646.0


def test_field_elevation_still_uses_departure_when_it_has_plenty_of_rows():
    df = _synthetic_flight(departure_ground_rows=80, arrival_ground_rows=80,
                            departure_elev=646.0, arrival_elev=137.0)
    assert _estimate_field_elevation(df) == 646.0


def test_field_elevation_is_robust_to_a_startup_sensor_glitch_longer_than_the_old_cap():
    # 80 glitched rows (comfortably longer than the old 60-row window),
    # then 150 genuine stable rows in the same departure window.
    rows = (
        [{"rpm": np.nan, "ias_kt": 14.0, "baro_alt_ft": -330.0} for _ in range(80)]
        + [{"rpm": 2000.0, "ias_kt": 14.0, "baro_alt_ft": 131.0} for _ in range(150)]
        + [{"rpm": 5000.0, "ias_kt": 110.0, "baro_alt_ft": 5131.0} for _ in range(400)]
    )
    df = pd.DataFrame(rows)
    assert _estimate_field_elevation(df) == 131.0


def test_taxi_to_takeoff_roll_survives_rpm_and_ias_crossing_in_the_same_sample():
    # No row anywhere has RPM > 4500 while IAS is still under the old 35
    # kt ceiling — RPM and IAS both cross their thresholds between one
    # row and the next, the exact shape that left the old gate closed
    # forever on a real flight.
    rows = [{"rpm": 2000.0, "ias_kt": 8.0, "baro_alt_ft": 100.0, "vs_fpm": 0.0} for _ in range(30)]
    rows.append({"rpm": 5000.0, "ias_kt": 40.0, "baro_alt_ft": 105.0, "vs_fpm": 100.0})
    for i in range(60):
        rows.append({"rpm": 5400.0, "ias_kt": 60.0 + i, "baro_alt_ft": 105.0 + i * 30, "vs_fpm": 800.0})
    df = pd.DataFrame(rows)
    df["press_alt_ft"] = df["baro_alt_ft"]
    df["oil_temp_f"] = 180.0
    df["power_pct"] = np.where(df["rpm"] > 4000, 80.0, 20.0)

    result = detect_phases(df, field_elev_ft=100.0, verbose=False)
    assert "TAKEOFF_ROLL" in set(result["phase"])
    assert "CLIMB" in set(result["phase"])


def test_engine_start_to_warmup_survives_a_high_ground_idle_ias_baseline():
    # IAS never drops below 14 kt on the ground — comfortably above the
    # old 10 kt ceiling but well under the new 30 kt one — the exact
    # shape that left several real flights stuck classified as
    # ENGINE_START for their entire duration.
    rows = [{"rpm": 0.0, "ias_kt": 14.0, "baro_alt_ft": 100.0, "vs_fpm": 0.0} for _ in range(20)]
    rows += [{"rpm": 2200.0, "ias_kt": 14.0, "baro_alt_ft": 100.0, "vs_fpm": 0.0} for _ in range(20)]
    rows += [{"rpm": 1800.0, "ias_kt": 18.0, "baro_alt_ft": 100.0, "vs_fpm": 0.0} for _ in range(60)]
    df = pd.DataFrame(rows)
    df["press_alt_ft"] = df["baro_alt_ft"]
    df["oil_temp_f"] = 180.0
    df["power_pct"] = np.where(df["rpm"] > 4000, 80.0, 20.0)

    result = detect_phases(df, field_elev_ft=100.0, verbose=False)
    counts = result["phase"].value_counts()
    assert counts.get("WARMUP", 0) > 0
    assert counts.get("TAXI", 0) > 0
    assert counts.get("ENGINE_START", 0) < len(df) / 2


@requires_flight_logs
@pytest.mark.parametrize("filename", [
    "log_20260927_212613_4S2.csv",       # bug 1: departure/arrival elevation mismatch
    "log_20260408_141810_KTOA.csv",      # bug 2: RPM/IAS crossing in one sample (also the KACV fixture flight's issue)
    "log_20260613_193731_KAWO.csv",      # bug 3: startup sensor glitch
    "log_20260927_181026_KAWO.csv",      # bug 4: high ground-idle IAS baseline
])
def test_real_flights_affected_by_these_bugs_now_reach_cruise(filename):
    path = LOGS_DIR / filename
    if not path.exists():
        pytest.skip("real flight log not available in this environment")
    df, _info = load_log_bytes(path.read_bytes(), path.name)
    result = detect_phases(df, verbose=False)
    counts = result["phase"].value_counts()
    assert counts.get("CRUISE", 0) > 0
    assert counts.get("TAXI", 0) < len(df) / 2
