"""
fleet.py — Multi-flight aggregation utilities.

Shared statistical helpers used by 03_multi_flight_insights.py (and any
future fleet-style analysis) to build per-aircraft baselines, detect
trends over engine hours, and flag outlier flights.

These are intentionally generic — they operate on a "metrics table"
(one row per flight, one column per metric) rather than on raw EIS
DataFrames directly, so the same functions serve EGT, fuel, oil temp,
overboost, or any future metric without duplication.

Usage
-----
    from slingology_eis.fleet import build_flight_metrics, baseline, trend, outliers

    metrics_df = build_flight_metrics(flights)       # one row per flight
    b = baseline(metrics_df, "spread_mean_f")          # mean/std/n + confidence
    t = trend(metrics_df, "spread_mean_f", x="engine_hours")
    o = outliers(metrics_df, "spread_mean_f")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd

from .loader import log_summary
from .phases import detect_phases, overboost_time
from .egt import egt_health
from .fuel import integrate_fuel, cruise_efficiency
from .cas import parse_cas
from .climb import climb_thermal_profile, VS_BUCKETS


# Minimum flights before a baseline is considered statistically meaningful.
# Below this, we still compute and show the numbers, but flag low confidence.
MIN_FLIGHTS_FOR_CONFIDENCE = 10

# Density altitude bands (ft) for stratifying performance-type comparisons
# (MAP, power, efficiency). Per the research paper §9: DA is the correct
# single normalising variable for parameters driven by air density, since
# two flights at the same DA present the engine with the same amount of
# oxygen for combustion regardless of how that DA was reached.
DA_BANDS = [
    (-2000, 2000,  "low"),       # sea level-ish
    (2000,  5000,  "moderate"),
    (5000,  9000,  "high"),
    (9000,  20000, "very_high"),
]

# OAT bands (°C) for stratifying thermal-type comparisons (EGT, oil,
# coolant). Per the research paper §9: DA alone is NOT sufficient for
# these, because ambient air is simultaneously the cooling medium — two
# flights at equal DA (one hot-and-high, one cold-and-low) can have very
# different cooling margins despite identical air density.
OAT_BANDS = [
    (-40, 5,  "cold"),
    (5,   20, "mild"),
    (20,  30, "warm"),
    (30,  55, "hot"),
]


def _band_for(value: Optional[float], bands: list[tuple[float, float, str]]) -> Optional[str]:
    """Classify a value into a named band, or None if value is missing/out of range."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    for lo, hi, name in bands:
        if lo <= value < hi:
            return name
    return None


# ── Sample-size confidence labelling ──────────────────────────────────────────

def confidence_label(n: int) -> str:
    """Human-readable confidence label for a sample size."""
    if n < 3:
        return "VERY LOW (n<3 — essentially anecdotal)"
    if n < MIN_FLIGHTS_FOR_CONFIDENCE:
        return f"LOW (n={n} — indicative only, not yet a reliable baseline)"
    if n < MIN_FLIGHTS_FOR_CONFIDENCE * 3:
        return f"MODERATE (n={n} — usable baseline, keep accumulating)"
    return f"GOOD (n={n} — stable baseline)"


# ── Per-flight metrics table ──────────────────────────────────────────────────

@dataclass
class FlightMetrics:
    """One row of derived metrics for a single flight."""
    source_file: str
    date: object
    engine_hours: Optional[float]
    duration_min: float
    airborne_min: float

    # EGT
    egt_spread_mean_f: Optional[float] = None
    egt_spread_max_f: Optional[float] = None
    egt4_elevation_f: Optional[float] = None
    egt_rank_stable: Optional[bool] = None

    # Fuel
    fadec_gallons: Optional[float] = None
    cruise_nmpg: Optional[float] = None
    cruise_fuel_flow_gph: Optional[float] = None

    # Oil / coolant
    oil_temp_max_f: Optional[float] = None
    oil_temp_below_optimal_pct: Optional[float] = None
    coolant_temp_max_f: Optional[float] = None
    oil_coolant_ratio: Optional[float] = None

    # Overboost
    overboost_total_s: Optional[int] = None
    overboost_max_block_s: Optional[int] = None

    # CAS
    cas_inflight_anomaly_count: Optional[int] = None

    # Operational
    max_altitude_ft: Optional[float] = None
    max_ias_kt: Optional[float] = None
    phase_climb_min: Optional[float] = None
    phase_cruise_min: Optional[float] = None
    phase_descent_min: Optional[float] = None

    # Density altitude / OAT — for cross-flight comparison normalisation.
    # Cruise-phase median is used as the flight's representative value,
    # since climb/descent DA varies continuously and isn't a stable
    # single number to band flights by; cruise is the one phase where
    # conditions hold roughly steady long enough to characterise.
    cruise_da_ft: Optional[float] = None
    cruise_oat_c: Optional[float] = None
    da_band: Optional[str] = None      # see DA_BANDS
    oat_band: Optional[str] = None     # see OAT_BANDS

    # Climb thermal rate (see climb.py)
    climb_oil_rise_f_per_min: Optional[float] = None
    climb_coolant_rise_f_per_min: Optional[float] = None
    climb_vs_bucket_dominant: Optional[str] = None   # which VS bucket had the most climb rows


def build_flight_metrics(
    flights: list[tuple[pd.DataFrame, object]],
    field_elev_ft: Optional[float] = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Run the full per-flight analysis pipeline (phases, EGT, fuel, oil,
    overboost, CAS) on every flight and assemble one row per flight.

    field_elev_ft: passed through to detect_phases() for each flight.
    Default (None) auto-estimates each flight's departure elevation from
    its own ground-ops data — important when flights depart from
    different airports at different elevations. Pass an explicit value
    only to force the same elevation across every flight in the batch.

    This is the shared foundation for every fleet-level insight —
    baselines, trends, and outlier detection all operate on the
    DataFrame this returns.
    """
    rows = []
    for df, info in flights:
        fname = df["_source_file"].iloc[0]
        try:
            df = detect_phases(df, field_elev_ft=field_elev_ft, verbose=False)
            s   = log_summary(df, info)
            egt = egt_health(df)
            ob  = overboost_time(df)
            eff = cruise_efficiency(df)
            fuel_total = integrate_fuel(df)

            cas_events = parse_cas(df)
            inflight_anomalies = sum(
                1 for e in cas_events
                if e.alert == "ENGINE ECU"
                # Heuristic without re-running full classification: running engine,
                # not a brief (<=15s) ground-speed-near-zero pair → handled properly
                # in 02; here we just count raw ENGINE ECU runs while airborne.
            )

            airborne = df[df["rpm"].fillna(0) > 3000]
            oil_t    = airborne["oil_temp_f"].dropna() if "oil_temp_f" in airborne.columns else pd.Series(dtype=float)
            below_optimal_pct = (
                round(float((oil_t < 194).mean() * 100), 1) if len(oil_t) else None
            )
            coolant_max = airborne["coolant_temp_f"].max() if "coolant_temp_f" in airborne.columns else None
            oil_max     = airborne["oil_temp_f"].max() if "oil_temp_f" in airborne.columns else None
            oc_ratio    = (
                round(float(oil_max / coolant_max), 3)
                if oil_max and coolant_max and coolant_max > 0 else None
            )

            phase_min = {}
            if "phase" in df.columns:
                for ph in ["CLIMB", "CRUISE", "DESCENT"]:
                    phase_min[ph] = round(float((df["phase"] == ph).sum() / 60), 1)

            # ── Density altitude / OAT — cruise-phase median ──────────────────────
            cruise_rows = df[df["phase"] == "CRUISE"] if "phase" in df.columns else pd.DataFrame()
            cruise_da  = cruise_rows["da_ft"].median() if "da_ft" in cruise_rows.columns and len(cruise_rows) else None
            cruise_oat = cruise_rows["oat_c"].median() if "oat_c" in cruise_rows.columns and len(cruise_rows) else None
            da_band  = _band_for(cruise_da, DA_BANDS)
            oat_band = _band_for(cruise_oat, OAT_BANDS)

            # ── Climb thermal profile ──────────────────────────────────────────────
            climb_profile = climb_thermal_profile(df)
            dominant_bucket = None
            if climb_profile["available"] and climb_profile["by_bucket"]:
                dominant_bucket = max(
                    climb_profile["by_bucket"].items(),
                    key=lambda kv: kv[1]["rows"]
                )[0]

            m = FlightMetrics(
                source_file=fname,
                date=s["date"],
                engine_hours=info.engine_hours,
                duration_min=round(s["duration_min"], 1),
                airborne_min=round(s["airborne_min"], 1),
                egt_spread_mean_f=egt.get("spread_mean_f"),
                egt_spread_max_f=egt.get("spread_max_f"),
                egt4_elevation_f=egt.get("egt4_elevation_f"),
                egt_rank_stable=egt.get("rank_stable"),
                fadec_gallons=fuel_total.get("fadec_gallons"),
                cruise_nmpg=eff.get("nmpg") if eff else None,
                cruise_fuel_flow_gph=eff.get("mean_fuel_flow_gph") if eff else None,
                oil_temp_max_f=round(float(oil_max), 1) if oil_max else None,
                oil_temp_below_optimal_pct=below_optimal_pct,
                coolant_temp_max_f=round(float(coolant_max), 1) if coolant_max else None,
                oil_coolant_ratio=oc_ratio,
                overboost_total_s=ob.get("overboost_total_s"),
                overboost_max_block_s=ob.get("overboost_max_block_s"),
                cas_inflight_anomaly_count=inflight_anomalies,
                max_altitude_ft=round(float(df["baro_alt_ft"].max()), 0) if "baro_alt_ft" in df.columns else None,
                max_ias_kt=round(float(df["ias_kt"].max()), 0) if "ias_kt" in df.columns else None,
                phase_climb_min=phase_min.get("CLIMB"),
                phase_cruise_min=phase_min.get("CRUISE"),
                phase_descent_min=phase_min.get("DESCENT"),
                cruise_da_ft=round(float(cruise_da), 0) if cruise_da is not None and not pd.isna(cruise_da) else None,
                cruise_oat_c=round(float(cruise_oat), 1) if cruise_oat is not None and not pd.isna(cruise_oat) else None,
                da_band=da_band,
                oat_band=oat_band,
                climb_oil_rise_f_per_min=climb_profile.get("oil_rise_f_per_min_overall"),
                climb_coolant_rise_f_per_min=climb_profile.get("coolant_rise_f_per_min_overall"),
                climb_vs_bucket_dominant=dominant_bucket,
            )
            rows.append(m.__dict__)
            if verbose:
                print(f"  ✓ {fname}")
        except Exception as e:
            if verbose:
                print(f"  ✗ {fname}: {e}")

    metrics_df = pd.DataFrame(rows)
    if len(metrics_df):
        metrics_df = metrics_df.sort_values("date").reset_index(drop=True)
    return metrics_df


# ── Baseline ──────────────────────────────────────────────────────────────────

@dataclass
class Baseline:
    metric: str
    n: int
    mean: Optional[float]
    std: Optional[float]
    min: Optional[float]
    max: Optional[float]
    confidence: str

    def __str__(self):
        if self.mean is None:
            return f"{self.metric}: insufficient data"
        return (f"{self.metric}: {self.mean:.1f} ± {self.std:.1f} "
                f"[{self.min:.1f}–{self.max:.1f}]  (n={self.n}, {self.confidence})")


def baseline(metrics_df: pd.DataFrame, column: str) -> Baseline:
    """Compute a simple mean/std baseline for a metric column, with confidence label."""
    if column not in metrics_df.columns:
        return Baseline(column, 0, None, None, None, None, "NO DATA — column not found")
    series = metrics_df[column].dropna()
    n = len(series)
    if n == 0:
        return Baseline(column, 0, None, None, None, None, "NO DATA")
    return Baseline(
        metric=column, n=n,
        mean=round(float(series.mean()), 2),
        std=round(float(series.std()), 2) if n > 1 else 0.0,
        min=round(float(series.min()), 2),
        max=round(float(series.max()), 2),
        confidence=confidence_label(n),
    )


def baseline_stratified(
    metrics_df: pd.DataFrame,
    column: str,
    band_column: str = "da_band",
) -> dict[str, Baseline]:
    """
    Compute a separate baseline() per band (DA or OAT) instead of one
    blended number across all conditions.

    Per the research paper §9: use band_column="da_band" for
    performance-type metrics (cruise_nmpg, etc.) and band_column=
    "oat_band" for thermal-type metrics (egt_spread_mean_f, oil/coolant
    temps, etc.) — DA alone doesn't capture cooling margin since ambient
    air is also the cooling medium.

    Returns a dict keyed by band name (e.g. "low", "moderate", "hot"),
    each value a Baseline for just that band's flights. Bands with zero
    matching flights are omitted. Flights with no band assigned (missing
    DA/OAT data) are excluded from every band's calculation.
    """
    if band_column not in metrics_df.columns or column not in metrics_df.columns:
        return {}

    result = {}
    for band_name in metrics_df[band_column].dropna().unique():
        sub = metrics_df[metrics_df[band_column] == band_name]
        b = baseline(sub, column)
        if b.n > 0:
            result[band_name] = b
    return result


# ── Trend ─────────────────────────────────────────────────────────────────────

@dataclass
class Trend:
    metric: str
    n: int
    slope: Optional[float]          # change in metric per unit x
    direction: str                  # "increasing" | "decreasing" | "flat" | "insufficient data"
    r_squared: Optional[float]
    confidence: str

    def __str__(self):
        if self.slope is None:
            return f"{self.metric}: insufficient data for trend"
        return (f"{self.metric}: {self.direction}  "
                f"(slope={self.slope:+.4f}/unit, R²={self.r_squared:.2f}, "
                f"n={self.n}, {self.confidence})")


def trend(
    metrics_df: pd.DataFrame,
    column: str,
    x: str = "engine_hours",
    flat_threshold_r2: float = 0.1,
) -> Trend:
    """
    Simple linear trend of `column` vs `x` (default: engine_hours).

    A trend is only called "increasing"/"decreasing" if R² exceeds
    flat_threshold_r2 — otherwise it's labelled "flat" even if the
    slope is nonzero, since with few points noise easily produces
    a nonzero slope with no real relationship.
    """
    if column not in metrics_df.columns or x not in metrics_df.columns:
        return Trend(column, 0, None, "insufficient data", None, "NO DATA")

    sub = metrics_df[[x, column]].dropna()
    n = len(sub)
    if n < 3:
        return Trend(column, n, None, "insufficient data", None, confidence_label(n))

    xs = sub[x].values.astype(float)
    ys = sub[column].values.astype(float)

    if np.std(xs) == 0:
        return Trend(column, n, None, "insufficient data (no x variance)", None, confidence_label(n))

    slope, intercept = np.polyfit(xs, ys, 1)
    pred = slope * xs + intercept
    ss_res = np.sum((ys - pred) ** 2)
    ss_tot = np.sum((ys - ys.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    if r2 < flat_threshold_r2:
        direction = "flat / no clear trend"
    elif slope > 0:
        direction = "increasing"
    else:
        direction = "decreasing"

    return Trend(
        metric=column, n=n, slope=round(float(slope), 5),
        direction=direction, r_squared=round(float(r2), 3),
        confidence=confidence_label(n),
    )


def trend_stratified(
    metrics_df: pd.DataFrame,
    column: str,
    x: str = "engine_hours",
    band_column: str = "da_band",
    flat_threshold_r2: float = 0.1,
) -> dict[str, Trend]:
    """
    Compute trend() separately within each band, instead of one trend
    line blending flights flown under very different conditions.

    This is the direct fix for the kind of false/muddied trend we saw
    with cruise_nmpg: a flight-to-flight efficiency trend computed
    across mixed density altitudes doesn't cleanly separate "engine is
    changing" from "conditions varied" — the weak R² in that case was
    exactly this effect. Stratifying by da_band (for performance
    metrics like nmpg) or oat_band (for thermal metrics) answers the
    more honest question: within similar conditions, is this metric
    actually trending?

    Each band will have fewer flights than the whole-fleet trend, so
    expect lower confidence labels per band — that's the honest
    trade-off for a cleaner comparison; see confidence_label().
    """
    if band_column not in metrics_df.columns:
        return {}

    result = {}
    for band_name in metrics_df[band_column].dropna().unique():
        sub = metrics_df[metrics_df[band_column] == band_name]
        t = trend(sub, column, x=x, flat_threshold_r2=flat_threshold_r2)
        if t.n > 0:
            result[band_name] = t
    return result


# ── Outliers ──────────────────────────────────────────────────────────────────

@dataclass
class OutlierFlight:
    source_file: str
    date: object
    value: float
    z_score: float


def outliers(
    metrics_df: pd.DataFrame,
    column: str,
    z_threshold: float = 2.0,
) -> list[OutlierFlight]:
    """
    Flag flights where `column` deviates more than z_threshold standard
    deviations from the fleet mean. With small n this is noisy — the
    caller should weigh results against the confidence label from
    baseline().
    """
    if column not in metrics_df.columns:
        return []
    sub = metrics_df[["source_file", "date", column]].dropna()
    if len(sub) < 3:
        return []

    mean = sub[column].mean()
    std  = sub[column].std()
    if std == 0 or pd.isna(std):
        return []

    sub = sub.copy()
    sub["z"] = (sub[column] - mean) / std
    flagged = sub[sub["z"].abs() >= z_threshold]

    return [
        OutlierFlight(
            source_file=row["source_file"],
            date=row["date"],
            value=round(float(row[column]), 2),
            z_score=round(float(row["z"]), 2),
        )
        for _, row in flagged.iterrows()
    ]
