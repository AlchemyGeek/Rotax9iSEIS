"""
operations.py — the Spec 01 §7 operations, starting with analyze_flight.

An operation is the seam a CLI, browser worker, or local server calls
through the same envelope (Spec 01 §7): given bytes and configuration,
it returns a typed, JSON-serializable result. The core here never
touches a filesystem, environment variable, or the clock — callers
(adapters) supply the log bytes, the engine profile, and parameters.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import numpy as np

from collections import Counter

import pandas as pd

from . import __version__
from .cas import analyze_inflight_pattern, extract_engine_ecu_runs, parse_cas
from .contract import CONTRACT_VERSION, Diagnostic, Provenance, content_hash, engine_profile_ref
from .fleet import MIN_FLIGHTS_FOR_CONFIDENCE, compute_flight_metrics
from .limits import check_exceedances
from .loader import flight_fingerprint, flight_id as _flight_id, load_log_bytes, source_key as _source_key
from .phases import detect_phases, phase_segments
from .registry import METRIC_REGISTRY, missing_reason
from . import topics

# Airborne time (RPM > 3000 & IAS > 30kt — the same proxy loader.py's
# ground-session filter uses) beyond which a flight with no TAKEOFF_ROLL/
# CLIMB phase is flagged, rather than assumed to be a ground session.
_TAKEOFF_NOT_DETECTED_THRESHOLD_ROWS = 180  # 3 minutes at 1 Hz


def _engine_major_minor(version: str) -> str:
    parts = version.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else version


def _elapsed_s(t, t0) -> Optional[float]:
    return (t - t0).total_seconds() if t is not None else None


def _serialize_exceedance(e, t0) -> dict:
    return {
        "param": e.param, "label": e.label, "unit": e.unit,
        "severity": e.severity, "limit_type": e.limit_type,
        "limit_value": e.limit_value, "observed_value": e.observed_value,
        "start_utc": e.started_at.isoformat(),
        "elapsed_s": _elapsed_s(e.started_at, t0),
        "duration_s": e.duration_s, "time_limit_s": e.time_limit_s,
        "note": e.note,
    }


def _serialize_cas_event(e, t0) -> dict:
    return {
        "alert": e.alert, "severity": e.severity,
        "start_utc": e.started_at.isoformat(),
        "elapsed_s": _elapsed_s(e.started_at, t0),
        "duration_s": e.duration_s, "rows": e.rows,
        "started_before_engine": e.started_before_engine,
    }


def _serialize_ecu_run(r, t0) -> dict:
    return {
        "classification": r["classification"],
        "start_utc": r["start_time"].isoformat() if r["start_time"] is not None else None,
        "elapsed_s": _elapsed_s(r["start_time"], t0),
        "duration_s": r["duration_s"],
        "co_alerts": list(r.get("co_alerts") or []),
        "oil_nan_frac": r.get("oil_nan_frac"),
        "lane_check_pair": bool(r.get("lane_check_pair", False)),
        "lane_check_note": r.get("lane_check_note", ""),
        "mean_rpm": r.get("mean_rpm"),
        "mean_ias_kt": r.get("mean_ias_kt"),
    }


def _to_plain(value):
    """
    numpy scalar / date / datetime -> JSON-primitive, for MetricValue.value.

    Also normalizes NaN/Infinity to None: some upstream computations
    (e.g. FlightMetrics.oil_temp_max_f when there's no airborne data)
    can produce a bare NaN rather than None, because Python's NaN is
    truthy — `if x:` doesn't catch it. Treating it as missing here means
    missing_reason() still runs and the contract never emits invalid
    JSON, without having to chase down and fix every such call site.
    """
    if isinstance(value, (float, np.floating)):
        f = float(value)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


@dataclass
class FlightAnalysis:
    flight_id: str
    analysis_key: str
    source_keys: list[str]
    header: dict
    phases: list[dict] = field(default_factory=list)
    metrics: dict[str, dict] = field(default_factory=dict)
    exceedances: list[dict] = field(default_factory=list)
    cas_events: list[dict] = field(default_factory=list)
    ecu_runs: list[dict] = field(default_factory=list)
    quality: list[dict] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "flight_id": self.flight_id,
            "analysis_key": self.analysis_key,
            "source_keys": self.source_keys,
            "header": self.header,
            "phases": self.phases,
            "metrics": self.metrics,
            "exceedances": self.exceedances,
            "cas_events": self.cas_events,
            "ecu_runs": self.ecu_runs,
            "quality": self.quality,
            "provenance": self.provenance,
        }


def analyze_flight(
    log_bytes: bytes,
    filename: str,
    engine_config: dict,
    engine_name: str,
    params: Optional[dict] = None,
) -> FlightAnalysis:
    """
    Full per-flight pipeline (Spec 01 §7 `analyze_flight`): parse, detect
    phases, compute every registry metric with an explicit missing
    reason where null, exceedances, CAS events, ECU runs, and quality
    diagnostics. Pure — the raw DataFrame is discarded on return.
    """
    params = dict(params or {})
    field_elev_ft = params.get("field_elev_ft")

    df, info = load_log_bytes(log_bytes, filename)
    df = detect_phases(df, field_elev_ft=field_elev_ft, verbose=False)

    fid = _flight_id(flight_fingerprint(df, info))
    skey = _source_key(log_bytes)
    t0 = df["datetime"].iloc[0]
    phases_present = set(df["phase"].unique()) if "phase" in df.columns else set()
    channels_present = set(df.columns)

    fm = compute_flight_metrics(df, info, engine_config)

    metrics: dict[str, dict] = {}
    for metric_id, metric_def in METRIC_REGISTRY.items():
        value = _to_plain(getattr(fm, metric_id, None))
        reason = missing_reason(metric_id, value, phases_present, channels_present)
        mv = {"id": metric_id, "value": value}
        if metric_def.unit:
            mv["unit"] = metric_def.unit
        if reason:
            mv["missing"] = reason
        metrics[metric_id] = mv

    exceedances = [_serialize_exceedance(e, t0) for e in check_exceedances(df, engine_config)]
    cas_events = [_serialize_cas_event(e, t0) for e in parse_cas(df)]
    ecu_runs = [_serialize_ecu_run(r, t0) for r in extract_engine_ecu_runs(df, engine_config=engine_config)]

    quality: list[Diagnostic] = []
    if "rpm" in df.columns and "ias_kt" in df.columns:
        airborne_rows = int(((df["rpm"].fillna(0) > 3000) & (df["ias_kt"].fillna(0) > 30)).sum())
    else:
        airborne_rows = 0
    if (airborne_rows > _TAKEOFF_NOT_DETECTED_THRESHOLD_ROWS
            and "TAKEOFF_ROLL" not in phases_present and "CLIMB" not in phases_present):
        quality.append(Diagnostic(
            code="PHASE_TAKEOFF_NOT_DETECTED", severity="warn", scope="flight",
            message="Airborne time was detected but no TAKEOFF_ROLL/CLIMB phase was labelled.",
            refs={"airborne_rows": airborne_rows},
        ))
    if "CRUISE" not in phases_present:
        quality.append(Diagnostic(
            code="PHASE_NO_CRUISE", severity="info", scope="flight",
            message="No CRUISE phase detected this flight.",
        ))
    if engine_config.get("_metadata", {}).get("source_status") == "PLACEHOLDER":
        quality.append(Diagnostic(
            code="ENGINE_PLACEHOLDER_CONFIG", severity="warn", scope="flight",
            message=f"Engine config '{engine_name}' is a PLACEHOLDER — not verified against the official OM.",
        ))

    header = {
        "date": t0.date().isoformat(),
        "start_utc": t0.isoformat(),
        "engine_hours_start": info.engine_hours,
        "engine_hours_end": (
            round(info.engine_hours + fm.duration_min / 60, 2)
            if info.engine_hours is not None else None
        ),
        "airport_hint": filename.rsplit(".", 1)[0].split("_")[-1] if "_" in filename else None,
        "aircraft": {"ident": info.aircraft_ident or None, "system_id": info.system_id or None},
    }

    params_hash = content_hash(params)
    profile_ref = engine_profile_ref(engine_config, engine_name)
    analysis_key = content_hash({
        "flight_id": fid,
        "profile_hash": profile_ref.hash,
        "params_hash": params_hash,
        "engine_major_minor": _engine_major_minor(__version__),
    })

    provenance = Provenance(
        engine_version=__version__,
        engine_profile=profile_ref,
        params_hash=params_hash,
        source_keys=[skey],
    )

    return FlightAnalysis(
        flight_id=fid,
        analysis_key=analysis_key,
        source_keys=[skey],
        header=header,
        phases=phase_segments(df),
        metrics=metrics,
        exceedances=exceedances,
        cas_events=cas_events,
        ecu_runs=ecu_runs,
        quality=[d.to_dict() for d in quality],
        provenance=provenance.to_dict(),
    )


@dataclass
class EcuAnalysis:
    """
    Spec 01 §7 `analyze_ecu` / §8.6. A fleet-level aggregation over
    already-computed FlightAnalysis.ecu_runs — no raw data, no engine
    config: classification already happened per-flight in analyze_flight.
    """
    flight_ids: list[str]
    runs: list[dict]
    counts: dict[str, int]
    inflight_pattern: dict
    provenance: dict

    def to_dict(self) -> dict:
        return {
            "flight_ids": self.flight_ids,
            "runs": self.runs,
            "counts": self.counts,
            "inflight_pattern": self.inflight_pattern,
            "provenance": self.provenance,
        }


def analyze_ecu(flight_analyses: list[FlightAnalysis]) -> EcuAnalysis:
    """
    Aggregate ECU runs across flights: per-classification counts and,
    per BACKLOG B3, per-event co-active-alert analysis for IN_FLIGHT runs
    (cas.analyze_inflight_pattern) rather than a pooled table.
    """
    all_runs: list[dict] = []
    for fa in flight_analyses:
        for run in fa.ecu_runs:
            r = dict(run)
            r["flight_id"] = fa.flight_id
            all_runs.append(r)

    counts = dict(Counter(r["classification"] for r in all_runs))

    inflight_for_pattern = [
        {
            "source_file": r["flight_id"],
            "start_time": r["start_utc"],
            "duration_s": r["duration_s"],
            "oil_nan_frac": r["oil_nan_frac"],
            "co_alerts": r["co_alerts"],
        }
        for r in all_runs if r["classification"] == "IN_FLIGHT"
    ]
    inflight_pattern = analyze_inflight_pattern(inflight_for_pattern)
    # analyze_inflight_pattern's events reuse the key "source_file" for
    # whatever identity string was passed in; here that's a flight_id,
    # not a filename — rename for honesty in this aggregate's output.
    for event in inflight_pattern["events"]:
        event["flight_id"] = event.pop("source_file")

    flight_ids = [fa.flight_id for fa in flight_analyses]
    source_keys = sorted({sk for fa in flight_analyses for sk in fa.source_keys})
    provenance = {
        "engine_version": __version__,
        "schema_version": flight_analyses[0].provenance.get("schema_version") if flight_analyses else None,
        "source_keys": source_keys,
        "flight_analysis_keys": [fa.analysis_key for fa in flight_analyses],
    }

    return EcuAnalysis(
        flight_ids=flight_ids,
        runs=all_runs,
        counts=counts,
        inflight_pattern=inflight_pattern,
        provenance=provenance,
    )


def _confidence(n: int) -> dict:
    if n < 3:
        level = "VERY_LOW"
    elif n < MIN_FLIGHTS_FOR_CONFIDENCE:
        level = "LOW"
    elif n < MIN_FLIGHTS_FOR_CONFIDENCE * 3:
        level = "MODERATE"
    else:
        level = "GOOD"
    return {"level": level, "n": n}


def _fleet_baseline_dict(b) -> dict:
    return {"n": b.n, "mean": b.mean, "std": b.std, "min": b.min, "max": b.max, "confidence": _confidence(b.n)}


def _normalize_trend_direction(direction: str) -> str:
    if direction in ("increasing", "decreasing"):
        return direction
    if direction.startswith("flat"):
        return "flat"
    return "insufficient_data"


def _fleet_trend_dict(t) -> dict:
    return {
        "n": t.n, "slope": t.slope, "r_squared": t.r_squared,
        "direction": _normalize_trend_direction(t.direction),
        "x": "engine_hours", "confidence": _confidence(t.n),
    }


def _metric_points(df: pd.DataFrame, col: str, band_col: Optional[str]) -> list[dict]:
    cols = ["source_file", "date", "engine_hours", col]
    if band_col and band_col in df.columns:
        cols.append(band_col)
    sub = df[[c for c in cols if c in df.columns]].dropna(subset=[col])
    points = []
    for _, row in sub.iterrows():
        point = {
            "flight_id": row["source_file"],
            "date": str(row["date"]),
            "x": float(row["engine_hours"]) if pd.notna(row.get("engine_hours")) else None,
            "value": _to_plain(row[col]),
        }
        if band_col and band_col in row.index and pd.notna(row[band_col]):
            point["band"] = row[band_col]
        points.append(point)
    return points


def _metrics_dataframe_from_flight_analyses(flight_analyses: list[FlightAnalysis]) -> pd.DataFrame:
    """
    Reconstruct a fleet.py-compatible metrics table from FlightAnalysis[]
    — the shared baseline()/trend()/outliers() functions were written
    against a raw DataFrame; this rebuilds one from already-typed
    results rather than duplicating their logic. `flight_id` fills the
    `source_file` slot those functions use only as an opaque per-flight
    label, never as an actual path.
    """
    rows = []
    for fa in flight_analyses:
        row = {
            "source_file": fa.flight_id,
            "date": fa.header.get("date"),
            "engine_hours": fa.header.get("engine_hours_start"),
        }
        for metric_id, mv in fa.metrics.items():
            row[metric_id] = mv["value"]
        rows.append(row)
    return pd.DataFrame(rows)


@dataclass
class FleetAnalysis:
    fleet_key: str
    flight_ids: list[str]
    excluded: list[dict] = field(default_factory=list)
    metrics: dict[str, dict] = field(default_factory=dict)
    models: list[dict] = field(default_factory=list)
    quality: list[dict] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "fleet_key": self.fleet_key,
            "flight_ids": self.flight_ids,
            "excluded": self.excluded,
            "metrics": self.metrics,
            "models": self.models,
            "quality": self.quality,
            "provenance": self.provenance,
        }


def update_fleet(
    flight_analyses: list[FlightAnalysis],
    excluded: Optional[list[dict]] = None,
    baseline_config: Optional[dict] = None,
) -> FleetAnalysis:
    """
    Spec 01 §7 `update_fleet` / §8.4. Computes the all-flights baseline,
    trend, stratified breakdown, points, and outliers for every tracked
    metric, plus the takeoff-MAP model — reusing fleet.py/baselines.py's
    pure functions on a table reconstructed from FlightAnalysis[], so
    this and build_flight_metrics()'s old CSV path report identical
    numbers. Membership here is always all-flights (for display, trend
    charts); evaluate_insights derives its own leave-one-out comparison
    per flight from the `points` this returns (R2, §8.4).
    """
    from .baselines import BASELINE_METRIC_DEFS, build_takeoff_map_model
    from .fleet import baseline, baseline_stratified, outliers, trend

    excluded = excluded or []
    baseline_config = baseline_config or {"membership": "leave_one_out", "band_kind_by_metric": {}}

    if not flight_analyses:
        return FleetAnalysis(
            fleet_key=content_hash({"analysis_keys": [], "baseline_config": baseline_config}),
            flight_ids=[], excluded=excluded, metrics={}, models=[], quality=[],
            provenance={
                "engine_version": __version__, "schema_version": CONTRACT_VERSION,
                "source_keys": [], "flight_analysis_keys": [], "baseline_config": baseline_config,
            },
        )

    df = _metrics_dataframe_from_flight_analyses(flight_analyses)

    metrics_out: dict[str, dict] = {}
    quality: list[Diagnostic] = []
    for key, col, band_col in BASELINE_METRIC_DEFS:
        if col not in df.columns:
            continue
        b = baseline(df, col)
        t = trend(df, col, x="engine_hours")

        entry = {
            "metric_id": key,
            "baseline": _fleet_baseline_dict(b),
            "trend": _fleet_trend_dict(t),
            "points": _metric_points(df, col, band_col),
            "outliers": [{"flight_id": o.source_file, "z_score": o.z_score} for o in outliers(df, col)],
        }
        if band_col and band_col in df.columns:
            stratified = baseline_stratified(df, col, band_column=band_col)
            if stratified:
                entry["by_band"] = {
                    "band_kind": band_col,
                    "bands": {name: _fleet_baseline_dict(sb) for name, sb in stratified.items()},
                }
        metrics_out[key] = entry

        if 0 < b.n < MIN_FLIGHTS_FOR_CONFIDENCE:
            quality.append(Diagnostic(
                code="BASELINE_LOW_N", severity="info", scope="fleet",
                message=f"{key}: baseline n={b.n}, below {MIN_FLIGHTS_FOR_CONFIDENCE} for a stable baseline.",
                refs={"metric_id": key, "n": b.n},
            ))

    models: list[dict] = []
    map_model = build_takeoff_map_model(df)
    if map_model.get("type") == "linear_regression":
        models.append({
            "id": "takeoff_map",
            "kind": "linear_regression",
            "features": map_model["features"],
            "coefficients": map_model["coefficients"],
            "n": map_model["n"],
            "r_squared": map_model["r_squared"],
            "confidence": _confidence(map_model["n"]),
            "capture": "RPM>=5500 during TAKEOFF_ROLL",
        })
    else:
        quality.append(Diagnostic(
            code="MODEL_INSUFFICIENT_DATA", severity="info", scope="fleet",
            message=f"takeoff_map: {map_model.get('note', 'insufficient data for a model fit')}",
            refs={"model_id": "takeoff_map", "n": map_model.get("n", 0)},
        ))

    flight_ids = [fa.flight_id for fa in flight_analyses]
    analysis_keys = sorted(fa.analysis_key for fa in flight_analyses)
    fleet_key = content_hash({"analysis_keys": analysis_keys, "baseline_config": baseline_config})

    provenance = {
        "engine_version": __version__,
        "schema_version": CONTRACT_VERSION,
        "source_keys": sorted({sk for fa in flight_analyses for sk in fa.source_keys}),
        "flight_analysis_keys": analysis_keys,
        "baseline_config": baseline_config,
    }

    return FleetAnalysis(
        fleet_key=fleet_key,
        flight_ids=flight_ids,
        excluded=excluded,
        metrics=metrics_out,
        models=models,
        quality=[d.to_dict() for d in quality],
        provenance=provenance,
    )


# topic_id -> (flight metric id, fleet MetricFleet key). Both sides use
# different naming conventions (registry.py ids vs. baselines.py's
# topic-shaped keys) — this is the one place that reconciles them.
_TOPIC_METRIC_MAP = {
    "egt_spread": ("egt_spread_mean_f", "egt_spread"),
    "egt4_elevation": ("egt4_elevation_f", "egt4_elevation"),
    "oil_temp_peak": ("oil_temp_max_f", "oil_temp_peak"),
    "coolant_temp_peak": ("coolant_temp_max_f", "coolant_temp_peak"),
    "oil_coolant_ratio": ("oil_coolant_ratio", "oil_coolant_ratio"),
    "cruise_efficiency": ("cruise_nmpg", "cruise_efficiency"),
    "cruise_fuel_flow": ("cruise_fuel_flow_gph", "cruise_fuel_flow"),
    "climb_thermal_rate": ("climb_oil_rise_f_per_min", "climb_thermal_rate"),
}


def _leave_one_out_baseline(points: list[dict], flight_id: str) -> dict:
    """Mean/std/n over a FleetAnalysis metric's points, excluding this
    flight's own point (Spec 01 R2)."""
    values = [p["value"] for p in points if p["flight_id"] != flight_id and p["value"] is not None]
    n = len(values)
    if n == 0:
        return {"mean": None, "std": None, "n": 0}
    mean = sum(values) / n
    std = (sum((v - mean) ** 2 for v in values) / (n - 1)) ** 0.5 if n > 1 else 0.0
    return {"mean": round(mean, 4), "std": round(std, 4), "n": n}


def _topic_baseline(fleet_metric: Optional[dict], flight_id: str) -> dict:
    """
    The {mean, std, n, trend} shape topics.py's baseline_triggered/
    trend_triggered expect: leave-one-out for the baseline (R2), but the
    all-flights trend unchanged — a trend over engine hours naturally
    includes the flight being evaluated as its newest point.
    """
    if not fleet_metric:
        return {}
    loo = _leave_one_out_baseline(fleet_metric.get("points", []), flight_id)
    trend = fleet_metric.get("trend", {})
    return {
        "mean": loo["mean"], "std": loo["std"], "n": loo["n"],
        "trend": {
            "direction": trend.get("direction"),
            "r_squared": trend.get("r_squared"),
            "n": trend.get("n", 0),
            "slope": trend.get("slope"),
        },
    }


def _severity_for(rules: dict, topic_id: str, trigger_type: str) -> str:
    """Severity for a trigger (R1): from insight_rules.json if set, else
    the type-based default (limit for threshold, watch otherwise)."""
    for rule in rules.get("rules", {}).get(topic_id, {}).get("triggers", []):
        if rule.get("type") == trigger_type:
            return rule.get("severity") or ("limit" if trigger_type == "threshold" else "watch")
    return "limit" if trigger_type == "threshold" else "watch"


def evaluate_insights(flight_analysis: FlightAnalysis, fleet_analysis: FleetAnalysis, rules: dict) -> "InsightSet":
    """
    Spec 01 §7 `evaluate_insights` / §8.5. Wraps topics.py's 13 topic
    functions, attributing each triggered insight to a rule and severity
    and comparing against a leave-one-out baseline (R2) derived from
    `fleet_analysis`'s points, with a BASELINE_LOW_N note (rather than a
    firing insight) below n_min.

    Deviates from Spec 01 §8.5's illustrative sketch in one place:
    `insight` is a list (`insights: Insight[]`), not a single nullable
    `Insight | null` — real topics (e.g. egt_spread) can trigger both a
    baseline_deviation and a trend insight simultaneously, matching
    what the current text report actually prints. Per §8's own note,
    "type sketches are illustrative."

    Known gap: `cylinder_rank` isn't wired here — its analysis needs
    per-cylinder rank order (egt_health()'s rank_order), which isn't a
    registered metric on FlightAnalysis today, only the boolean
    `egt_rank_stable` is. Extending the registry to carry it is a
    reasonable follow-up, not done in this pass.
    """
    r_data = rules.get("rules", {})
    rules_hash = content_hash(rules)
    fm = flight_analysis.metrics
    flight_id = flight_analysis.flight_id

    topics_out: list[dict] = []

    def _emit(topic_id: str, raw: dict, metric_ids: list[str], fleet_n: int):
        confidence = _confidence(fleet_n)
        insights = []
        for ins in raw["insights"]:
            severity = _severity_for(rules, topic_id, ins["trigger"])
            insights.append({
                "id": content_hash({"flight_id": flight_id, "topic_id": topic_id,
                                     "trigger": ins["trigger"], "text": ins["text"]})[:16],
                "topic_id": topic_id,
                "rule_id": f"{topic_id}.{ins['trigger']}",
                "trigger": ins["trigger"],
                "severity": severity,
                "message": {"text": ins["text"]},
                "evidence": [{"kind": "metric", "metric_id": mid} for mid in metric_ids],
                "confidence": confidence,
            })
        topics_out.append({
            "topic_id": topic_id,
            "analysis": {"text": raw["analysis"]},
            "insights": insights,
            "metric_ids": metric_ids,
        })

    # ── The 8 topics driven by a single flight metric + fleet baseline ──────
    for topic_id, (flight_metric_id, fleet_key) in _TOPIC_METRIC_MAP.items():
        value = fm.get(flight_metric_id, {}).get("value")
        fleet_metric = fleet_analysis.metrics.get(fleet_key)
        b = _topic_baseline(fleet_metric, flight_id)
        all_triggers = r_data.get(topic_id, {}).get("triggers", [])
        fleet_n = b.get("n", 0)

        # BASELINE_LOW_N (R2): below n_min, no baseline_deviation insight
        # may fire — drop those triggers before calling the topic function
        # (not after: the insight would already exist in its output).
        bd_n_min = next((t.get("n_min", 10) for t in all_triggers if t.get("type") == "baseline_deviation"), 10)
        low_n = 0 < fleet_n < bd_n_min
        triggers = [t for t in all_triggers if not (low_n and t.get("type") == "baseline_deviation")]

        if topic_id == "egt_spread":
            enabled = r_data.get(topic_id, {}).get("enabled", True)
            raw = topics.egt_spread(value, 392, b, triggers, enabled)
        elif topic_id == "egt4_elevation":
            raw = topics.egt4_elevation(value, b, triggers)
        elif topic_id == "oil_temp_peak":
            raw = topics.oil_temp_peak(value, b, triggers)
        elif topic_id == "coolant_temp_peak":
            raw = topics.coolant_temp_peak(value, b, triggers)
        elif topic_id == "oil_coolant_ratio":
            raw = topics.oil_coolant_ratio(value, b, triggers)
        elif topic_id == "cruise_efficiency":
            raw = topics.cruise_efficiency(value, b, triggers)
        elif topic_id == "cruise_fuel_flow":
            da_fleet = fleet_analysis.metrics.get("cruise_da_ft", {}).get("baseline", {})
            raw = topics.cruise_fuel_flow(
                value, b, triggers,
                this_da=fm.get("cruise_da_ft", {}).get("value"),
                fleet_da_avg=da_fleet.get("mean"), fleet_da_std=da_fleet.get("std"),
            )
        elif topic_id == "climb_thermal_rate":
            raw = topics.climb_thermal_rate(value, b, triggers)
        else:  # pragma: no cover — exhaustive per _TOPIC_METRIC_MAP
            continue

        _emit(topic_id, raw, [flight_metric_id], fleet_n)
        if low_n:
            topics_out[-1]["_low_n"] = True

    # ── Topics with their own data source (no shared baseline pattern) ──────
    ob_triggers = r_data.get("overboost_time", {}).get("triggers", [])
    ob_limit = next((t.get("limit", 300) for t in ob_triggers if t.get("type") == "threshold"), 300)
    ob_total = fm.get("overboost_total_s", {}).get("value")
    ob_max = fm.get("overboost_max_block_s", {}).get("value")
    ob_exceeded = (ob_max is not None and ob_max > ob_limit)
    raw = topics.overboost(ob_total, ob_max, ob_limit, ob_exceeded)
    _emit("overboost_time", raw, ["overboost_total_s", "overboost_max_block_s"], 0)

    map_model = next((m for m in fleet_analysis.models if m["id"] == "takeoff_map"), None)
    map_model_dict = {
        "n": map_model["n"], "confidence": map_model["confidence"].get("level", ""),
        "r_squared": map_model["r_squared"], "coefficients": map_model["coefficients"],
    } if map_model else {"n": 0, "confidence": "", "coefficients": {}}
    raw = topics.takeoff_map(
        fm.get("takeoff_map_inhg", {}).get("value"),
        fm.get("takeoff_pressure_alt_ft", {}).get("value"),
        fm.get("takeoff_oat_c", {}).get("value"),
        map_model_dict,
    )
    _emit("map_at_takeoff", raw, ["takeoff_map_inhg", "takeoff_pressure_alt_ft", "takeoff_oat_c"], 0)

    # FlightAnalysis.ecu_runs is keyed start_utc/duration_s/... (Spec 01
    # §8.3 shape); topics.engine_ecu_inflight -> cas.analyze_inflight_pattern
    # expects source_file/start_time (§8.6-adjacent, cas.py's own shape).
    # Adapt rather than let the mismatch silently produce a None timestamp.
    adapted_runs = [
        {**r, "source_file": flight_id, "start_time": r.get("start_utc")}
        for r in flight_analysis.ecu_runs
    ]
    raw = topics.engine_ecu_inflight(adapted_runs)
    ecu_topic = {
        "topic_id": "engine_ecu_inflight",
        "analysis": {"text": raw["analysis"]},
        "insights": [{
            "id": content_hash({"flight_id": flight_id, "topic_id": "engine_ecu_inflight", "event": e})[:16],
            "topic_id": "engine_ecu_inflight", "rule_id": "engine_ecu_inflight.threshold",
            "trigger": "threshold", "severity": _severity_for(rules, "engine_ecu_inflight", "threshold"),
            "message": {"text": f"⚠ IN-FLIGHT ENGINE ECU event at {e['start_time']}"},
            "evidence": [{"kind": "ecu_run", "ref": str(e["start_time"])}],
            "confidence": _confidence(0),
        } for e in raw["events"]],
        "metric_ids": ["inflight_ecu_count"],
    }
    topics_out.append(ecu_topic)

    raw = topics.limit_exceedances(flight_analysis.exceedances)
    _emit("limit_exceedances", raw, [], 0)

    # header_warnings carries the flight's own quality diagnostics (e.g.
    # PHASE_NO_CRUISE — the "no stable cruise phase" banner the old text
    # report printed at the top) forward from FlightAnalysis, plus...
    header_warnings_dicts: list[dict] = list(flight_analysis.quality)

    # ...BASELINE_LOW_N: swap in a note instead of a fired insight.
    for t in topics_out:
        if t.pop("_low_n", False):
            header_warnings_dicts.append(Diagnostic(
                code="BASELINE_LOW_N", severity="info", scope="topic",
                message=f"{t['topic_id']}: baseline sample size is below the minimum for a reliable comparison.",
                refs={"topic_id": t["topic_id"]},
            ).to_dict())

    provenance = {
        "engine_version": __version__,
        "schema_version": flight_analysis.provenance.get("schema_version"),
        "engine_profile": flight_analysis.provenance.get("engine_profile"),
        "params_hash": flight_analysis.provenance.get("params_hash"),
        "rules_hash": rules_hash,
        "source_keys": flight_analysis.source_keys,
    }

    return InsightSet(
        flight_id=flight_id,
        analysis_key=flight_analysis.analysis_key,
        fleet_key=fleet_analysis.fleet_key,
        rules_hash=rules_hash,
        topics=topics_out,
        header_warnings=header_warnings_dicts,
        provenance=provenance,
    )


@dataclass
class InsightSet:
    flight_id: str
    analysis_key: str
    fleet_key: str
    rules_hash: str
    topics: list[dict] = field(default_factory=list)
    header_warnings: list[dict] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "flight_id": self.flight_id,
            "analysis_key": self.analysis_key,
            "fleet_key": self.fleet_key,
            "rules_hash": self.rules_hash,
            "topics": self.topics,
            "header_warnings": self.header_warnings,
            "provenance": self.provenance,
        }
