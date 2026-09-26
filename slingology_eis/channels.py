"""
channels.py — the channel registry (Spec 01 §6.4, extended by Spec 07 v0.2 §4).

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
    label: str
    group: str  # picker section: engine | egt | fuel | electrical | flight | conditions | cabin
    chartable: bool = True
    slot_group: Optional[str] = None  # membership of a slot group (Spec 07 D3)
    companions: tuple = ()  # context channels for an insight whose subject is this channel (§10)
    unit_variant_of: Optional[str] = None  # metric/imperial twin of this id, if any


@dataclass(frozen=True)
class SlotGroup:
    id: str
    label: str
    members: tuple


CHANNEL_REGISTRY: dict[str, ChannelDef] = {}

# Channels sharing one chart slot together (Spec 07 D3, §7) — a slot group
# counts once against MAX_CHART_SLOTS regardless of how many channels it
# actually plots. v0.2 has only the four cylinder EGTs, and — per §7.1 —
# is mutually exclusive on the chart with its own members: picking an
# individual cylinder replaces the group and vice versa.
SLOT_GROUPS: dict[str, SlotGroup] = {
    "egt_cyl": SlotGroup(id="egt_cyl", label="Cylinder EGTs (1–4)", members=("egt1_f", "egt2_f", "egt3_f", "egt4_f")),
}

# A single chart holds at most this many slots (Spec 07 D2) — a hard cap,
# never silently relaxed to make room. Set once here, exposed to the UI
# via get_channel_registry rather than duplicated as a frontend constant.
MAX_CHART_SLOTS = 6


def _c(
    id: str, unit: Optional[str], description: str, source: str, label: str, group: str,
    chartable: bool = True, slot_group: Optional[str] = None,
    companions: tuple = (), unit_variant_of: Optional[str] = None,
) -> None:
    CHANNEL_REGISTRY[id] = ChannelDef(
        id=id, unit=unit, description=description, source=source, label=label, group=group,
        chartable=chartable, slot_group=slot_group, companions=companions, unit_variant_of=unit_variant_of,
    )


# ── Engine — the headline set most reports/charts lead with ─────────────────
_c("rpm", "rpm", "Engine RPM", "raw", "RPM", "engine", companions=("map_inhg", "power_pct"))
_c("power_pct", "%", "Engine power", "raw", "Power", "engine")
_c("map_inhg", "inHg", "Manifold pressure", "raw", "MAP", "engine", companions=("rpm", "power_pct"))
_c("oil_press_psi", "psi", "Oil pressure", "raw", "Oil Press", "engine", companions=("oil_temp_f", "rpm"))
_c("oil_temp_f", "°F", "Oil temperature", "raw", "Oil Temp", "engine", companions=("coolant_temp_f", "oat_c"))
_c("coolant_temp_f", "°F", "Coolant temperature", "raw", "Coolant Temp", "engine", companions=("oil_temp_f", "oat_c"))
_c("fuel_flow_gph", "gal/hr", "Fuel flow", "raw", "Fuel Flow", "fuel")
_c("fuel_press_psi", "psi", "Fuel pressure", "raw", "Fuel Press", "fuel", companions=("fuel_flow_gph", "rpm"))
_c("fuel_qty_l_gal", "gal", "Left tank fuel quantity", "raw", "Fuel Qty L", "fuel")
_c("fuel_qty_r_gal", "gal", "Right tank fuel quantity", "raw", "Fuel Qty R", "fuel")
_c("egt1_f", "°F", "Cylinder 1 EGT", "raw", "EGT 1", "egt", slot_group="egt_cyl", companions=("egt_spread_f", "power_pct"))
_c("egt2_f", "°F", "Cylinder 2 EGT", "raw", "EGT 2", "egt", slot_group="egt_cyl", companions=("egt_spread_f", "power_pct"))
_c("egt3_f", "°F", "Cylinder 3 EGT", "raw", "EGT 3", "egt", slot_group="egt_cyl", companions=("egt_spread_f", "power_pct"))
_c("egt4_f", "°F", "Cylinder 4 EGT", "raw", "EGT 4", "egt", slot_group="egt_cyl", companions=("egt_spread_f", "power_pct"))
_c("main_volts", "V", "Main bus voltage", "raw", "Main Volts", "electrical", companions=("batt_amps", "rpm"))
_c("batt_amps", "A", "Battery current", "raw", "Batt Amps", "electrical")
_c("co_ppm", "ppm", "Cabin carbon monoxide", "raw", "CO", "cabin")

# ── Flight ────────────────────────────────────────────────────────────────
_c("press_alt_ft", "ft", "Pressure altitude", "raw", "Press Alt", "flight")
_c("baro_alt_ft", "ft", "Baro-corrected altitude", "raw", "Baro Alt", "flight")
_c("gps_alt_ft", "ft", "GPS altitude", "raw", "GPS Alt", "flight")
_c("vs_fpm", "ft/min", "Vertical speed", "raw", "Vertical Speed", "flight")
_c("ias_kt", "kt", "Indicated airspeed", "raw", "IAS", "flight")
_c("tas_kt", "kt", "True airspeed", "raw", "TAS", "flight")
_c("gnd_spd_kt", "kt", "GPS ground speed", "raw", "Ground Speed", "flight")
# Wraps at 360° — breaks the 0-100% index every overlaid chart relies on
# (Spec 07 §4), so it's excluded from charting, not just unlisted.
_c("track_deg", "deg", "GPS ground track", "raw", "Track", "flight", chartable=False)
_c("pitch_deg", "deg", "Pitch attitude", "raw", "Pitch", "flight")
_c("roll_deg", "deg", "Roll attitude", "raw", "Roll", "flight")
_c("lat_g", "G", "Lateral acceleration", "raw", "Lateral G", "flight")
_c("norm_g", "G", "Normal acceleration", "raw", "Normal G", "flight")
# Map/GPS-track channels — a future map view's data, not a line-chart
# channel (Spec 07 §14 out of scope).
_c("lat", "deg", "GPS latitude", "raw", "Latitude", "flight", chartable=False)
_c("lon", "deg", "GPS longitude", "raw", "Longitude", "flight", chartable=False)

# ── Conditions ────────────────────────────────────────────────────────────
_c("oat_c", "°C", "Outside air temperature", "raw", "OAT", "conditions")
_c("da_ft", "ft", "Density altitude", "raw", "Density Alt", "conditions")
_c("baro_inhg", "inHg", "Barometric setting", "raw", "Baro Setting", "conditions")
_c("wind_spd_kt", "kt", "Wind speed", "raw", "Wind Speed", "conditions")
_c("wind_dir_deg", "deg", "Wind direction", "raw", "Wind Dir", "conditions", chartable=False)

# ── Derived (loader.py) ───────────────────────────────────────────────────
_c("egt_max_f", "°F", "Maximum cylinder EGT", "derived", "EGT Max", "egt")
_c("egt_min_f", "°F", "Minimum cylinder EGT", "derived", "EGT Min", "egt")
_c("egt_mean_f", "°F", "Mean cylinder EGT", "derived", "EGT Mean", "egt")
_c("egt_spread_f", "°F", "EGT spread (max - min cylinder)", "derived", "EGT Spread", "egt")
_c("fuel_flow_lph", "L/hr", "Fuel flow (litres/hour, for OM EGT-split comparisons)", "derived",
   "Fuel Flow (L/hr)", "fuel", chartable=False, unit_variant_of="fuel_flow_gph")
_c("oat_f", "°F", "Outside air temperature (Fahrenheit)", "derived",
   "OAT (°F)", "conditions", chartable=False, unit_variant_of="oat_c")
_c("map_hpa", "hPa", "Manifold pressure (hPa, for OM limit comparisons)", "derived",
   "MAP (hPa)", "engine", chartable=False, unit_variant_of="map_inhg")
_c("oil_temp_c", "°C", "Oil temperature (Celsius)", "derived",
   "Oil Temp (°C)", "engine", chartable=False, unit_variant_of="oil_temp_f")
_c("coolant_temp_c", "°C", "Coolant temperature (Celsius)", "derived",
   "Coolant Temp (°C)", "engine", chartable=False, unit_variant_of="coolant_temp_f")

# ── Phase (charted as a background band, not a line) ────────────────────────
_c("phase", None, "Detected flight phase", "derived", "Phase", "flight", chartable=False)
