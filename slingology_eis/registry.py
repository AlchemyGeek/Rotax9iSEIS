"""
registry.py — the metric registry (Spec 01 §8.2).

Declares every metric id the engine can produce: its unit, a short
description, which report group it belongs to, and (for metrics that can
be null) what phase or channel its absence is attributed to. Ids are the
current FlightMetrics field names (slingology_eis.fleet), so existing
baselines/CSVs stay comparable.

This is a pure, static declaration — no computation, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

MissingReason = str  # one of MISSING_REASONS, kept as str for JSON-friendliness

MISSING_REASONS = (
    "NO_PHASE", "CHANNEL_MISSING", "INSUFFICIENT_DATA", "NOT_APPLICABLE", "EXCLUDED",
)


@dataclass(frozen=True)
class MetricDef:
    id: str
    group: str
    unit: Optional[str]
    description: str
    # What a null value is attributed to, checked in this order. Both may
    # be None for metrics that are always populated (e.g. phase durations,
    # which report 0 rather than null when a phase never occurred).
    requires_phase: Optional[str] = None
    requires_channel: Optional[str] = None


METRIC_REGISTRY: dict[str, MetricDef] = {}


def _register(group: str, entries: list[tuple]) -> None:
    for entry in entries:
        id_, unit, description = entry[0], entry[1], entry[2]
        requires_phase = entry[3] if len(entry) > 3 else None
        requires_channel = entry[4] if len(entry) > 4 else None
        METRIC_REGISTRY[id_] = MetricDef(
            id=id_, group=group, unit=unit, description=description,
            requires_phase=requires_phase, requires_channel=requires_channel,
        )


_register("header", [
    ("date", None, "Flight date"),
    ("engine_hours", "hr", "Engine hours at start of flight, from log metadata"),
    ("duration_min", "min", "Total session duration"),
    ("airborne_min", "min", "Time airborne"),
    ("max_altitude_ft", "ft", "Maximum baro altitude", None, "baro_alt_ft"),
    ("max_ias_kt", "kt", "Maximum indicated airspeed", None, "ias_kt"),
    ("fadec_gallons", "gal", "FADEC-integrated fuel consumed", None, "fuel_flow_gph"),
])

_register("phases", [
    ("phase_climb_min", "min", "Time in CLIMB phase"),
    ("phase_cruise_min", "min", "Time in CRUISE phase"),
    ("phase_descent_min", "min", "Time in DESCENT phase"),
])

_register("egt", [
    ("egt_spread_mean_f", "°F", "Mean EGT spread during cruise", "CRUISE"),
    ("egt_spread_max_f", "°F", "Max EGT spread during cruise", "CRUISE"),
    ("egt1_deviation_f", "°F", "Cylinder 1 cruise EGT vs. mean of the other cylinders", "CRUISE", "egt1_f"),
    ("egt2_deviation_f", "°F", "Cylinder 2 cruise EGT vs. mean of the other cylinders", "CRUISE", "egt2_f"),
    ("egt3_deviation_f", "°F", "Cylinder 3 cruise EGT vs. mean of the other cylinders", "CRUISE", "egt3_f"),
    ("egt4_deviation_f", "°F", "Cylinder 4 cruise EGT vs. mean of the other cylinders", "CRUISE", "egt4_f"),
    ("egt_hottest_cyl", None, "Cylinder with the highest cruise-mean EGT (1-4)", "CRUISE"),
    ("egt_hottest_margin_f", "°F", "Cruise-mean EGT of the hottest cylinder minus the next hottest", "CRUISE"),
    ("egt_rank_order", None, "Cylinders ordered hottest to coldest by cruise-mean EGT", "CRUISE"),
    ("egt_rank_stable", None, "Whether the same cylinder was hottest for at least 80% of cruise", "CRUISE"),
    # Deprecated alias of egt4_deviation_f (Spec 08 §4) — kept one minor
    # version so existing bundles, baselines and fixtures still load.
    ("egt4_elevation_f", "°F", "Deprecated: same as egt4_deviation_f", "CRUISE"),
])

_register("fuel", [
    ("cruise_nmpg", "nm/gal", "Cruise efficiency", "CRUISE"),
    ("cruise_fuel_flow_gph", "gal/hr", "Mean cruise fuel flow", "CRUISE"),
])

_register("thermal", [
    ("oil_temp_max_f", "°F", "Peak oil temperature (airborne)", None, "oil_temp_f"),
    ("oil_temp_below_optimal_pct", "%",
     "Percent of airborne time with oil temp below 194°F/90°C", None, "oil_temp_f"),
    ("coolant_temp_max_f", "°F", "Peak coolant temperature (airborne)", None, "coolant_temp_f"),
    ("oil_coolant_ratio", None, "Oil/coolant peak-temperature ratio", None, "oil_temp_f"),
    ("climb_oil_rise_f_per_min", "°F/min", "Oil temperature rise rate during climb", "CLIMB"),
    ("climb_coolant_rise_f_per_min", "°F/min", "Coolant temperature rise rate during climb", "CLIMB"),
    ("climb_vs_bucket_dominant", None, "Most common vertical-speed bucket during climb", "CLIMB"),
])

_register("boost", [
    ("overboost_total_s", "s", "Total seconds above the overboost threshold", None, "rpm"),
    ("overboost_max_block_s", "s", "Longest continuous overboost block", None, "rpm"),
])

_register("conditions", [
    ("cruise_da_ft", "ft", "Cruise-phase median density altitude", "CRUISE", "da_ft"),
    ("cruise_oat_c", "°C", "Cruise-phase median outside air temperature", "CRUISE", "oat_c"),
    ("da_band", None, "Density-altitude stratification band", "CRUISE", "da_ft"),
    ("oat_band", None, "Outside-air-temperature stratification band", "CRUISE", "oat_c"),
])

_register("takeoff_map", [
    ("takeoff_map_inhg", "inHg", "Observed manifold pressure at takeoff", "TAKEOFF_ROLL", "map_inhg"),
    ("takeoff_pressure_alt_ft", "ft", "Pressure altitude at takeoff", "TAKEOFF_ROLL", "press_alt_ft"),
    ("takeoff_oat_c", "°C", "Outside air temperature at takeoff", "TAKEOFF_ROLL", "oat_c"),
])

_register("events", [
    ("cas_inflight_anomaly_count", None,
     "Raw in-flight ENGINE ECU CAS occurrences (heuristic count, not classified)"),
    ("inflight_ecu_count", None, "Count of classified IN_FLIGHT ENGINE ECU runs"),
])


def missing_reason(metric_id: str, value, phases_present: set[str], channels_present: set[str]) -> Optional[MissingReason]:
    """
    Why is this metric's value null? Returns None if `value` isn't null.

    `phases_present`: the set of phase labels that occur anywhere in the
    flight (e.g. {"TAXI", "CLIMB", "CRUISE"}).
    `channels_present`: the set of raw/derived channel ids present as
    columns in the flight's DataFrame.
    """
    if value is not None:
        return None

    metric = METRIC_REGISTRY.get(metric_id)
    if metric is None:
        return "NOT_APPLICABLE"

    if metric.id == "engine_hours":
        return "NOT_APPLICABLE"  # source log metadata, not a derived channel

    if metric.requires_phase and metric.requires_phase not in phases_present:
        return "NO_PHASE"
    if metric.requires_channel and metric.requires_channel not in channels_present:
        return "CHANNEL_MISSING"
    if metric.requires_phase or metric.requires_channel:
        # The declared prerequisite is present but the value is still null
        # (e.g. a CRUISE phase existed but was too short/noisy to compute
        # a stable EGT spread).
        return "INSUFFICIENT_DATA"
    return "INSUFFICIENT_DATA"
