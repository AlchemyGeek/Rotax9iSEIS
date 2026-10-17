"""
Spec 10 v0.7 acceptance 8 (D6, causes 1-2): a flight that stays inside
its engine profile's own OM limits throughout must raise zero limit
events, for every engine profile. Synthetic — runs everywhere, no log
data needed. Every value is read from the profile under test; nothing
from 916iS is ever assumed for another engine.
"""
import pandas as pd
import pytest

from slingology_eis.limits import check_exceedances, load_engine_config

ENGINES = ("912iS", "915iS", "916iS")


def _limit(cfg, limit_id):
    return next((l for l in cfg["limits"] if l["id"] == limit_id), None)


def _segment(n, phase, rpm, oil_press, oil_temp, coolant_temp, egt, map_inhg,
             fuel_press, volts):
    return {
        "phase": [phase] * n,
        "rpm": [rpm] * n,
        "oil_press_psi": [oil_press] * n,
        "oil_temp_f": [oil_temp] * n,
        "coolant_temp_f": [coolant_temp] * n,
        "egt1_f": [egt] * n, "egt2_f": [egt] * n, "egt3_f": [egt] * n, "egt4_f": [egt] * n,
        "map_inhg": [map_inhg] * n,
        "fuel_press_psi": [fuel_press] * n,
        "main_volts": [volts] * n,
    }


def build_nominal_flight(cfg: dict) -> pd.DataFrame:
    """
    A synthetic flight that stays inside every limit `cfg` declares:
    ordinary spool-up, warm-up, taxi/run-up, a takeoff and brief initial
    climb in the 5,500-5,800 rpm band (OM-permitted for up to 5 minutes,
    held here for well under a minute), the rest of climb/cruise/descent
    at continuous-rated power, landing, and shutdown with rpm and bus
    voltage both going to 0 (D14).

    Every threshold is read from `cfg` itself — idle rpm, takeoff
    ceiling, oil/coolant/EGT/MAP maxima, oil pressure minimum, fuel
    pressure band, bus voltage band — with a safety margin inward from
    each, never a number borrowed from another profile.
    """
    pd_cfg = cfg.get("phase_detection", {})
    idle_min = _limit(cfg, "rpm_idle_min")["min_val"]
    takeoff_ceiling = _limit(cfg, "rpm_takeoff_max")["max_val"]
    oil_press_min = _limit(cfg, "oil_press_min")["min_val"]
    oil_temp_max = _limit(cfg, "oil_temp_max")["max_val"]
    coolant_max = _limit(cfg, "coolant_temp_max")["max_val"]
    egt_max = _limit(cfg, "egt1_max")["max_val"]
    # A naturally aspirated profile (912iS) has no MAP limit — its OM gives
    # none — so MAP can't raise an event; standard sea-level pressure is
    # used rather than a number borrowed from another profile.
    map_lim = _limit(cfg, "map_max")
    volts_min = _limit(cfg, "volts_min")["min_val"]
    volts_max = _limit(cfg, "volts_max")["max_val"]
    fp_lim = _limit(cfg, "fuel_press_min")
    fuel_press_min = fp_lim["min_val"] if fp_lim else None
    fp_max_lim = _limit(cfg, "fuel_press_max")
    fuel_press_max = fp_max_lim["max_val"] if fp_max_lim else None

    idle_rpm = idle_min + 50
    runup_rpm = pd_cfg.get("runup_rpm_max", idle_min + 2000)
    takeoff_rpm = takeoff_ceiling - 100          # in the OM-permitted band, under the ceiling
    overboost_threshold = cfg.get("overboost", {}).get("rpm_threshold", 5500)
    climb_rpm_continuous = min(overboost_threshold, takeoff_rpm) - 200  # back under the continuous limit
    oil_temp_nominal = min(200.0, oil_temp_max - 20)
    coolant_nominal = min(200.0, coolant_max - 20)
    egt_nominal = min(1400.0, egt_max - 100)
    map_nominal = map_lim["max_val"] - 5 if map_lim else 29.92
    volts_nominal = min(13.0, volts_max - 1)
    oil_press_nominal = oil_press_min + 10
    fuel_press_nominal = (
        min(44.0, fuel_press_max - 1) if fuel_press_max is not None
        else (fuel_press_min + 2 if fuel_press_min is not None else 0.0)
    )

    segs = []
    # Before engine start and after shutdown, every engine-driven channel
    # reads 0 — rpm, oil pressure, fuel pressure, bus voltage — exactly
    # as a real log shows (the engine isn't turning, the pumps aren't
    # running, the alternator isn't charging). Oil/coolant/EGT temps stay
    # at their nominal warm values even here: they're thermal mass, not
    # engine-driven readings, so they don't collapse to 0 the instant the
    # engine stops. This is the exact shape acceptance 8 needs to catch a
    # limit with no engine-running gate.
    segs.append(_segment(5, "PRE_START", 0, 0.0, oil_temp_nominal, coolant_nominal,
                          egt_nominal, 0.0, 0.0, 0.0))
    segs.append(_segment(10, "ENGINE_START", idle_rpm, oil_press_nominal, oil_temp_nominal,
                          coolant_nominal, egt_nominal, map_nominal, fuel_press_nominal, volts_nominal))
    segs.append(_segment(60, "WARMUP", idle_rpm, oil_press_nominal, oil_temp_nominal,
                          coolant_nominal, egt_nominal, map_nominal, fuel_press_nominal, volts_nominal))
    # TAXI, with a brief run-up to runup_rpm well inside the ceiling
    segs.append(_segment(20, "TAXI", idle_rpm, oil_press_nominal, oil_temp_nominal,
                          coolant_nominal, egt_nominal, map_nominal, fuel_press_nominal, volts_nominal))
    segs.append(_segment(10, "TAXI", runup_rpm, oil_press_nominal, oil_temp_nominal,
                          coolant_nominal, egt_nominal, map_nominal, fuel_press_nominal, volts_nominal))
    # Takeoff + initial climb in the 5,500-5,800 rpm band: 30 s total, well
    # under the OM's 5-minute allowance.
    segs.append(_segment(20, "TAKEOFF_ROLL", takeoff_rpm, oil_press_nominal, oil_temp_nominal,
                          coolant_nominal, egt_nominal, map_nominal, fuel_press_nominal, volts_nominal))
    segs.append(_segment(10, "CLIMB", takeoff_rpm, oil_press_nominal, oil_temp_nominal,
                          coolant_nominal, egt_nominal, map_nominal, fuel_press_nominal, volts_nominal))
    # Back to continuous-rated power for the rest of climb/cruise/descent.
    segs.append(_segment(100, "CLIMB", climb_rpm_continuous, oil_press_nominal, oil_temp_nominal,
                          coolant_nominal, egt_nominal, map_nominal, fuel_press_nominal, volts_nominal))
    segs.append(_segment(200, "CRUISE", climb_rpm_continuous - 200, oil_press_nominal, oil_temp_nominal,
                          coolant_nominal, egt_nominal, map_nominal, fuel_press_nominal, volts_nominal))
    segs.append(_segment(100, "DESCENT", idle_rpm + 1500, oil_press_nominal, oil_temp_nominal,
                          coolant_nominal, egt_nominal, map_nominal, fuel_press_nominal, volts_nominal))
    segs.append(_segment(60, "APPROACH", idle_rpm + 1000, oil_press_nominal, oil_temp_nominal,
                          coolant_nominal, egt_nominal, map_nominal, fuel_press_nominal, volts_nominal))
    segs.append(_segment(20, "LANDING_ROLL", idle_rpm, oil_press_nominal, oil_temp_nominal,
                          coolant_nominal, egt_nominal, map_nominal, fuel_press_nominal, volts_nominal))
    # Shutdown: rpm, oil pressure, fuel pressure and bus voltage all go to
    # 0, same as PRE_START above.
    segs.append(_segment(10, "SHUTDOWN", 0, 0.0, oil_temp_nominal,
                          coolant_nominal, egt_nominal, 0.0, 0.0, 0.0))

    cols = {k: [] for k in segs[0]}
    for seg in segs:
        for k, v in seg.items():
            cols[k].extend(v)
    n = len(cols["phase"])
    df = pd.DataFrame(cols)
    df["datetime"] = pd.date_range("2026-01-01 12:00:00", periods=n, freq="1s")
    return df


@pytest.mark.parametrize("engine", ENGINES)
def test_nominal_flight_raises_zero_limit_events(engine):
    cfg = load_engine_config(engine)
    required_limits = ["rpm_idle_min", "rpm_takeoff_max", "oil_press_min", "oil_temp_max",
                       "coolant_temp_max", "egt1_max", "volts_min", "volts_max"]
    if cfg.get("turbocharged"):
        required_limits.append("map_max")
    for required in required_limits:
        if _limit(cfg, required) is None:
            pytest.fail(f"{engine} lacks the '{required}' limit this nominal flight needs — "
                        f"reporting rather than inventing a value for it.")
    df = build_nominal_flight(cfg)
    events = check_exceedances(df, cfg)
    assert events == [], f"{engine}: nominal flight raised {len(events)} event(s): " \
        f"{[(e.limit_id, e.observed_value, e.started_at) for e in events]}"
