"""
baselines.py — fleet-level baseline/trend/model construction.

Pure functions: take a metrics DataFrame (slingology_eis.fleet.
build_flight_metrics output), return plain dicts ready for JSON
serialization (slingology_eis.serialize). No file I/O and no clock reads
— callers (notebook 03, future adapters) add `generated_at` and write the
result wherever they need.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .fleet import baseline, baseline_stratified, trend, confidence_label

# Fleet baseline metric definitions: (key, source column, stratification band column)
BASELINE_METRIC_DEFS = [
    ("egt_spread", "egt_spread_mean_f", "oat_band"),
    ("egt4_elevation", "egt4_elevation_f", "oat_band"),
    ("oil_temp_peak", "oil_temp_max_f", "oat_band"),
    ("coolant_temp_peak", "coolant_temp_max_f", "oat_band"),
    ("oil_coolant_ratio", "oil_coolant_ratio", "oat_band"),
    ("overboost_time", "overboost_total_s", None),
    ("cruise_efficiency", "cruise_nmpg", "da_band"),
    ("cruise_fuel_flow", "cruise_fuel_flow_gph", "da_band"),
    ("climb_thermal_rate", "climb_oil_rise_f_per_min", None),
    ("cruise_da_ft", "cruise_da_ft", None),
    ("takeoff_map_inhg", "takeoff_map_inhg", None),
]


def _baseline_dict(b) -> dict:
    if b.mean is None:
        return {"n": b.n, "confidence": b.confidence}
    return {
        "mean": b.mean, "std": b.std,
        "min": b.min, "max": b.max,
        "n": b.n, "confidence": b.confidence,
    }


def _trend_dict(t) -> dict:
    if t.slope is None:
        return {"n": t.n, "direction": t.direction, "confidence": t.confidence}
    return {
        "n": t.n, "slope": t.slope,
        "direction": t.direction,
        "r_squared": t.r_squared,
        "confidence": t.confidence,
    }


def _raw_points(metrics: pd.DataFrame, col: str, band_col: Optional[str] = None) -> list[dict]:
    cols = ["date", "engine_hours", col]
    if band_col and band_col in metrics.columns:
        cols += [band_col]
    if "da_band" in metrics.columns and "da_band" not in cols:
        cols += ["da_band"]
    if "oat_band" in metrics.columns and "oat_band" not in cols:
        cols += ["oat_band"]
    sub = metrics[[c for c in cols if c in metrics.columns]].dropna(subset=[col])
    renamed = sub.rename(columns={col: "value"})
    return renamed.where(pd.notna(renamed), other=None).to_dict(orient="records")


def build_baselines(metrics: pd.DataFrame, engine_name: str) -> dict:
    """
    Compute fleet baselines, trends, and stratified breakdowns for every
    tracked metric. Returns a dict in the reports/baselines.json shape
    (minus `generated_at`, since this function doesn't read the clock —
    the caller adds it).
    """
    baselines_out = {}
    for key, col, band_col in BASELINE_METRIC_DEFS:
        if col not in metrics.columns:
            continue
        b = baseline(metrics, col)
        t = trend(metrics, col, x="engine_hours")
        by_band = {}
        if band_col:
            stratified = baseline_stratified(metrics, col, band_column=band_col)
            for band_name, sb in stratified.items():
                by_band[band_name] = _baseline_dict(sb)

        baselines_out[key] = {
            **_baseline_dict(b),
            "trend": _trend_dict(t),
            **({"by_band": by_band} if by_band else {}),
            "raw": _raw_points(metrics, col, band_col),
        }

    return {
        "version": "1.0",
        "engine": engine_name,
        "engine_hours_range": [
            float(metrics["engine_hours"].min()),
            float(metrics["engine_hours"].max()),
        ] if metrics["engine_hours"].notna().any() else None,
        "flight_count": len(metrics),
        "baselines": baselines_out,
    }


def build_takeoff_map_model(metrics: pd.DataFrame) -> dict:
    """
    Fit (or describe insufficient data for) the takeoff MAP linear
    regression model: MAP = f(pressure_alt_ft, oat_c). Returns a dict in
    the models.json "takeoff_map" entry shape.
    """
    map_df = metrics[["takeoff_map_inhg", "takeoff_pressure_alt_ft", "takeoff_oat_c",
                      "engine_hours", "date"]].dropna()
    map_model = {"n": len(map_df), "confidence": confidence_label(len(map_df))}

    if len(map_df) >= 5:
        from numpy.linalg import lstsq as _lstsq
        X = np.column_stack([
            np.ones(len(map_df)),
            map_df["takeoff_pressure_alt_ft"].values,
            map_df["takeoff_oat_c"].values,
        ])
        y = map_df["takeoff_map_inhg"].values
        coeffs, _, _, _ = _lstsq(X, y, rcond=None)
        y_pred = X @ coeffs
        ss_res = float(np.sum((y - y_pred) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        map_model.update({
            "type": "linear_regression",
            "features": ["pressure_alt_ft", "oat_c"],
            "target": "map_inhg",
            "coefficients": {
                "intercept": round(float(coeffs[0]), 4),
                "pressure_alt_ft": round(float(coeffs[1]), 6),
                "oat_c": round(float(coeffs[2]), 4),
            },
            "r_squared": round(r2, 4),
        })
    else:
        map_model["note"] = (
            f"Still collecting data — need 5 minimum for first model fit "
            f"(have {len(map_df)})"
        )

    map_model["raw"] = [
        {
            "date": str(row["date"]),
            "engine_hours": row["engine_hours"],
            "map_inhg": row["takeoff_map_inhg"],
            "pressure_alt_ft": row["takeoff_pressure_alt_ft"],
            "oat_c": row["takeoff_oat_c"],
        }
        for _, row in map_df.iterrows()
    ]
    return map_model


def build_models(metrics: pd.DataFrame) -> dict:
    """Returns a dict in the models.json shape (minus `generated_at`)."""
    return {
        "version": "1.0",
        "flight_count": len(metrics),
        "models": {
            "takeoff_map": build_takeoff_map_model(metrics),
        },
    }
