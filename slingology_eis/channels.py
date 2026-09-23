"""
channels.py — the channel registry (Spec 01 §6.4).

Declares every normalized channel id the public API exposes for charts
(get_series, §8.7 SeriesData). Raw Garmin column names (loader.COLUMN_MAP's
keys) are never part of the contract — only the normalized ids on the
right-hand side of that map, plus derived columns loader.py computes.

A pure, static declaration — no computation, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChannelDef:
    id: str
    unit: Optional[str]
    description: str
    source: str  # "raw" | "derived"
    charted_by_default: bool = False


CHANNEL_REGISTRY: dict[str, ChannelDef] = {}


def _register(entries: list[tuple]) -> None:
    for id_, unit, description, source, *rest in entries:
        charted = rest[0] if rest else False
        CHANNEL_REGISTRY[id_] = ChannelDef(
            id=id_, unit=unit, description=description, source=source, charted_by_default=charted,
        )


_register([
    # ── Engine — the headline set most reports/charts lead with ──────────────
    ("rpm", "rpm", "Engine RPM", "raw", True),
    ("power_pct", "%", "Engine power", "raw", True),
    ("map_inhg", "inHg", "Manifold pressure", "raw", True),
    ("oil_press_psi", "psi", "Oil pressure", "raw"),
    ("oil_temp_f", "°F", "Oil temperature", "raw", True),
    ("coolant_temp_f", "°F", "Coolant temperature", "raw", True),
    ("fuel_flow_gph", "gal/hr", "Fuel flow", "raw", True),
    ("fuel_press_psi", "psi", "Fuel pressure", "raw"),
    ("fuel_qty_l_gal", "gal", "Left tank fuel quantity", "raw"),
    ("fuel_qty_r_gal", "gal", "Right tank fuel quantity", "raw"),
    ("egt1_f", "°F", "Cylinder 1 EGT", "raw", True),
    ("egt2_f", "°F", "Cylinder 2 EGT", "raw", True),
    ("egt3_f", "°F", "Cylinder 3 EGT", "raw", True),
    ("egt4_f", "°F", "Cylinder 4 EGT", "raw", True),
    ("main_volts", "V", "Main bus voltage", "raw"),
    ("batt_amps", "A", "Battery current", "raw"),
    ("co_ppm", "ppm", "Cabin carbon monoxide", "raw"),

    # ── Flight ─────────────────────────────────────────────────────────────
    ("press_alt_ft", "ft", "Pressure altitude", "raw"),
    ("baro_alt_ft", "ft", "Baro-corrected altitude", "raw", True),
    ("gps_alt_ft", "ft", "GPS altitude", "raw"),
    ("vs_fpm", "ft/min", "Vertical speed", "raw", True),
    ("ias_kt", "kt", "Indicated airspeed", "raw", True),
    ("tas_kt", "kt", "True airspeed", "raw"),
    ("gnd_spd_kt", "kt", "GPS ground speed", "raw"),
    ("track_deg", "deg", "GPS ground track", "raw"),
    ("pitch_deg", "deg", "Pitch attitude", "raw"),
    ("roll_deg", "deg", "Roll attitude", "raw"),
    ("lat_g", "G", "Lateral acceleration", "raw"),
    ("norm_g", "G", "Normal acceleration", "raw"),
    ("lat", "deg", "GPS latitude", "raw"),
    ("lon", "deg", "GPS longitude", "raw"),

    # ── Conditions ─────────────────────────────────────────────────────────
    ("oat_c", "°C", "Outside air temperature", "raw", True),
    ("da_ft", "ft", "Density altitude", "raw", True),
    ("baro_inhg", "inHg", "Barometric setting", "raw"),
    ("wind_spd_kt", "kt", "Wind speed", "raw"),
    ("wind_dir_deg", "deg", "Wind direction", "raw"),

    # ── Derived (loader.py) ────────────────────────────────────────────────
    ("egt_max_f", "°F", "Maximum cylinder EGT", "derived"),
    ("egt_min_f", "°F", "Minimum cylinder EGT", "derived"),
    ("egt_mean_f", "°F", "Mean cylinder EGT", "derived"),
    ("egt_spread_f", "°F", "EGT spread (max - min cylinder)", "derived", True),
    ("fuel_flow_lph", "L/hr", "Fuel flow (litres/hour, for OM EGT-split comparisons)", "derived"),
    ("oat_f", "°F", "Outside air temperature (Fahrenheit)", "derived"),
    ("map_hpa", "hPa", "Manifold pressure (hPa, for OM limit comparisons)", "derived"),
    ("oil_temp_c", "°C", "Oil temperature (Celsius)", "derived"),
    ("coolant_temp_c", "°C", "Coolant temperature (Celsius)", "derived"),

    # ── Phase (charted as a background band, not a line) ─────────────────────
    ("phase", None, "Detected flight phase", "derived"),
])
