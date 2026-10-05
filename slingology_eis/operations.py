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
from .limits import check_exceedances, engine_running_s, limit_catalog, per_limit_metrics
from .loader import flight_fingerprint, flight_id as _flight_id, load_log_bytes, source_key as _source_key
from .phases import detect_phases, phase_segments
from .channels import CHANNEL_REGISTRY
from .registry import METRIC_REGISTRY, missing_reason
from . import topics
from . import filters as _filters

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
    start_utc = e.started_at.isoformat()
    return {
        # Spec 09 §11.1: limit_id identifies the limit (stable across
        # engine versions); event_id identifies this event within the
        # flight, for annotations and drill-down.
        "limit_id": e.limit_id,
        "event_id": f"{e.limit_id}@{start_utc}",
        "excess": e.excess,
        "param": e.param, "label": e.label, "unit": e.unit,
        "severity": e.severity, "limit_type": e.limit_type,
        "limit_value": e.limit_value, "observed_value": e.observed_value,
        "start_utc": start_utc,
        "elapsed_s": _elapsed_s(e.started_at, t0),
        "duration_s": e.duration_s,
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
        "end_utc": r["end_time"].isoformat() if r.get("end_time") is not None else None,
        "elapsed_s": _elapsed_s(r["start_time"], t0),
        "duration_s": r["duration_s"],
        "co_alerts": list(r.get("co_alerts") or []),
        "oil_nan_frac": r.get("oil_nan_frac"),
        "lane_check_pair": bool(r.get("lane_check_pair", False)),
        "lane_check_note": r.get("lane_check_note", ""),
        "mean_rpm": r.get("mean_rpm"),
        "mean_ias_kt": r.get("mean_ias_kt"),
        "mean_power_pct": r.get("mean_power_pct"),
        "mean_oil_press_psi": r.get("mean_oil_press_psi"),
        "mean_oil_temp_f": r.get("mean_oil_temp_f"),
        "mean_coolant_temp_f": r.get("mean_coolant_temp_f"),
        "mean_main_volts": r.get("mean_main_volts"),
        "mean_batt_amps": r.get("mean_batt_amps"),
        "mean_fuel_press_psi": r.get("mean_fuel_press_psi"),
        "mean_baro_alt_ft": r.get("mean_baro_alt_ft"),
    }


def _format_exceedance_text(e: dict) -> str:
    """
    Match limits.ExceedanceEvent.__str__'s exact text, from the
    serialized dict form (FlightAnalysis.exceedances). This was the
    per-event limit_exceedances insight text — and so, hashed, its id —
    before Spec 09; workspace.migrate_limit_annotations rebuilds those
    old ids from it to move pilot notes onto the per-limit insights.
    """
    direction = "below min" if e["limit_type"] == "MIN" else "above max"
    t = e.get("start_utc")
    time_str = datetime.fromisoformat(t).strftime("%H:%M:%S") if t else "?"
    return (
        f"[{e['severity']}] {e['label']}: "
        f"{e['observed_value']:.1f} {e['unit']} {direction} "
        f"{e['limit_value']:.1f} {e['unit']} "
        f"at {time_str} for {e['duration_s']:.0f}s"
    )


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
    available_channels: list[str] = field(default_factory=list)
    # Spec 09: the engine profile's limit catalogue (limits.limit_catalog)
    # this flight was checked against, so insight evaluation can resolve
    # a limit_ref without the profile in hand. Empty for analyses written
    # before Spec 09.
    limits: list[dict] = field(default_factory=list)
    # Spec 08 v0.3 §6 (Spec 10 D4): fleet-dependent, so analyze_flight()
    # (pure, no fleet in hand) always leaves this False — evaluate_insights()
    # sets the real value from FleetAnalysis.cylinder_balance before this
    # object is serialized to a caller.
    hot_cyl_changed: bool = False

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
            "available_channels": self.available_channels,
            "limits": self.limits,
            "hot_cyl_changed": self.hot_cyl_changed,
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
    # Spec 07 §5: which chartable channels this particular log actually has
    # data for — an older or Garmin Pilot export may be missing columns the
    # registry declares, and the picker needs to know before the user taps
    # rather than showing an empty line for the whole flight.
    available_channels = sorted(
        cid for cid, cdef in CHANNEL_REGISTRY.items()
        if cdef.chartable and cid in df.columns and df[cid].notna().any()
    )

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
    limits = limit_catalog(engine_config)
    # Spec 09 §5: per-limit metrics, baselined like any other (update_fleet).
    metrics.update(per_limit_metrics(
        exceedances, limits, engine_running_s(df), channels_present,
        overboost_max_block_s=metrics.get("overboost_max_block_s", {}).get("value"),
    ))
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
        available_channels=available_channels,
        limits=limits,
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


_ECU_CONTEXT_FIELDS = (
    "mean_rpm", "mean_power_pct", "mean_oil_press_psi", "mean_oil_temp_f",
    "mean_coolant_temp_f", "mean_main_volts", "mean_batt_amps",
    "mean_fuel_press_psi", "mean_ias_kt", "mean_baro_alt_ft", "oil_nan_frac",
)


def _ecu_run_output(r: dict) -> dict:
    """
    The API-facing per-run shape (Spec 01 §8.6's `runs[]`) — channel means
    grouped under `context`, separate from the run's own identity/timing,
    since a co-active-alert correlation check (B3) is judged against the
    context, not the classification. `all_runs`' flat shape stays as-is
    for analyze_inflight_pattern's own internal use, above/below this.
    """
    return {
        "flight_id": r["flight_id"],
        "classification": r["classification"],
        "start_utc": r.get("start_utc"),
        "end_utc": r.get("end_utc"),
        "duration_s": r["duration_s"],
        "co_alerts": r.get("co_alerts") or [],
        "lane_check_pair": bool(r.get("lane_check_pair", False)),
        "lane_check_note": r.get("lane_check_note", ""),
        "context": {k: r.get(k) for k in _ECU_CONTEXT_FIELDS},
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

    runs_output = [_ecu_run_output(r) for r in all_runs]

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
        runs=runs_output,
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
    # Spec 08 §5. Optional so fleet caches written before it still load.
    cylinder_balance: Optional[dict] = None

    def to_dict(self) -> dict:
        d = {
            "fleet_key": self.fleet_key,
            "flight_ids": self.flight_ids,
            "excluded": self.excluded,
            "metrics": self.metrics,
            "models": self.models,
            "quality": self.quality,
            "provenance": self.provenance,
        }
        if self.cylinder_balance is not None:
            d["cylinder_balance"] = self.cylinder_balance
        return d


_CYL_DEVIATION_KEYS = [f"egt{n}_deviation" for n in range(1, 5)]


def resolve_outlier_z_threshold(baseline_config: dict, metric_id: str) -> float:
    """
    Spec 01 §8.4 v0.8: `outlier_z_threshold` (resolved per metric as
    `overrides[metric_id] ?? outlier_z_threshold`, default 2.0 if neither
    is set) is the ONE value behind both update_fleet's FleetMetric.outliers
    and evaluate_insights's baseline_deviation trigger — a shared resolver
    so the two can't drift apart the way insight_rules.json's own
    per-rule z_score_threshold field used to let them.
    """
    overrides = baseline_config.get("outlier_z_threshold_overrides") or {}
    if metric_id in overrides:
        return overrides[metric_id]
    # The rule playground keys overrides by rule id; one rule block covers
    # all four cylinder-balance metrics (Spec 08 §6 `applies_to`).
    if metric_id in _CYL_DEVIATION_KEYS and "egt_cyl_deviation" in overrides:
        return overrides["egt_cyl_deviation"]
    return baseline_config.get("outlier_z_threshold", 2.0)


def _hot_cyl_points(df: pd.DataFrame) -> list[dict]:
    """Per-flight hottest cylinder, its margin and rank order (Spec 08 §5),
    oldest first. Flights with no hottest cylinder are left out."""
    if "egt_hottest_cyl" not in df.columns:
        return []
    sub = df[df["egt_hottest_cyl"].notna()]
    points = []
    for _, row in sub.iterrows():
        rank = row.get("egt_rank_order")
        points.append({
            "flight_id": row["source_file"],
            "date": str(row["date"]),
            "x": float(row["engine_hours"]) if pd.notna(row.get("engine_hours")) else None,
            "hottest_cyl": int(row["egt_hottest_cyl"]),
            "margin_f": _to_plain(row.get("egt_hottest_margin_f")),
            "rank_order": [int(c) for c in rank] if isinstance(rank, list) else None,
        })
    return _chronological(points)


def _chronological(points: list[dict]) -> list[dict]:
    # Engine hours first (monotonic per engine), date as the tie-break and
    # the fallback when a log carries no engine-hours metadata.
    return sorted(points, key=lambda p: (p["x"] is None, p["x"] or 0.0, p["date"]))


_HOT_CYL_CHANGED_CONSECUTIVE = 2  # matches insight_rules.json's cylinder_rank default


def _hot_cyl_changed_flags(
    points: list[dict], expected_cyl: Optional[int], margin_min_f: float, consecutive: int,
) -> dict[str, bool]:
    """
    Spec 08 v0.3 §6: per-flight context flag — has the hottest cylinder
    differed from the aircraft's usual one, by at least margin_min_f, for
    `consecutive` flights running (this one and the ones immediately
    before it)? Computed once over the whole fleet (points already
    chronological) rather than per flight at request time, since Trends
    needs it for every point on the strip at once, not just one flight —
    the same leave-window-out principle established_hot_cylinder() itself
    uses. No longer an insight (Spec 10 D4): egt_cyl_deviation is what
    actually fires; this only feeds the flag on FlightAnalysis and the
    Trends strip/panel marks (§7 item 4).
    """
    from .baselines import established_hot_cylinder

    flags: dict[str, bool] = {}
    for i, p in enumerate(points):
        window = points[max(0, i - consecutive + 1): i + 1]
        if len(window) < consecutive:
            flags[p["flight_id"]] = False
            continue
        window_ids = {w["flight_id"] for w in window}
        established = established_hot_cylinder(
            [(q["hottest_cyl"], q.get("margin_f")) for q in points if q["flight_id"] not in window_ids],
            expected_cyl, margin_min_f,
        )
        usual = established.get("cyl")
        flags[p["flight_id"]] = established.get("source") != "none" and all(
            w["hottest_cyl"] != usual and w.get("margin_f") is not None and w["margin_f"] >= margin_min_f
            for w in window
        )
    return flags


def _cylinder_balance(df: pd.DataFrame, expected_cyl: Optional[int]) -> dict:
    from .baselines import established_hot_cylinder
    from .egt import MARGIN_MIN_F

    points = _hot_cyl_points(df)
    flags = _hot_cyl_changed_flags(points, expected_cyl, MARGIN_MIN_F, _HOT_CYL_CHANGED_CONSECUTIVE)
    for p in points:
        p["hot_cyl_changed"] = flags.get(p["flight_id"], False)
    return {
        "margin_min_f": MARGIN_MIN_F,
        "expected_hot_cyl": expected_cyl,
        "established_hot_cyl": established_hot_cylinder(
            [(p["hottest_cyl"], p["margin_f"]) for p in points], expected_cyl, MARGIN_MIN_F,
        ),
        "points": points,
    }


def update_fleet(
    flight_analyses: list[FlightAnalysis],
    excluded: Optional[list[dict]] = None,
    baseline_config: Optional[dict] = None,
    engine_config: Optional[dict] = None,
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

    `engine_config` supplies only the profile's `expected_hot_cylinder`
    (Spec 08 §3), the prior used until an aircraft's own hottest cylinder
    is learned; without it there is no prior.
    """
    from .baselines import BASELINE_METRIC_DEFS, build_takeoff_map_model, limit_baseline_metric_defs
    from .fleet import baseline, baseline_stratified, outliers, trend, trend_stratified

    excluded = excluded or []
    expected_cyl = (engine_config or {}).get("expected_hot_cylinder")
    baseline_config = baseline_config or {
        "membership": "leave_one_out", "band_kind_by_metric": {}, "outlier_z_threshold": 2.0,
    }

    if not flight_analyses:
        return FleetAnalysis(
            fleet_key=content_hash({"analysis_keys": [], "baseline_config": baseline_config}),
            flight_ids=[], excluded=excluded, metrics={}, models=[], quality=[],
            provenance={
                "engine_version": __version__, "schema_version": CONTRACT_VERSION,
                "source_keys": [], "flight_analysis_keys": [], "baseline_config": baseline_config,
            },
            cylinder_balance=_cylinder_balance(pd.DataFrame(), expected_cyl),
        )

    df = _metrics_dataframe_from_flight_analyses(flight_analyses)

    metrics_out: dict[str, dict] = {}
    quality: list[Diagnostic] = []
    # Spec 09 §5: the per-limit metrics' defs are generated from the limit
    # catalogue the flights were analysed against, not hand-listed.
    metric_defs = BASELINE_METRIC_DEFS + limit_baseline_metric_defs(
        [lim for fa in flight_analyses for lim in fa.limits])
    for key, col, band_col in metric_defs:
        if col not in df.columns:
            continue
        b = baseline(df, col)
        t = trend(df, col, x="engine_hours")

        z_threshold = resolve_outlier_z_threshold(baseline_config, key)
        entry = {
            "metric_id": key,
            "baseline": _fleet_baseline_dict(b),
            "trend": _fleet_trend_dict(t),
            "points": _metric_points(df, col, band_col),
            "outliers": [
                {"flight_id": o.source_file, "z_score": o.z_score}
                for o in outliers(df, col, z_threshold=z_threshold)
            ],
        }
        if band_col and band_col in df.columns:
            stratified = baseline_stratified(df, col, band_column=band_col)
            # Spec 03 §5.3 v0.10: stratified view redraws one trend line
            # per band too, same n_min gate as the unstratified one — not
            # just a split baseline. trend_stratified existed in fleet.py
            # unused until now; nothing else in the pipeline needed it.
            trend_by_band = trend_stratified(df, col, x="engine_hours", band_column=band_col)
            if stratified:
                entry["by_band"] = {
                    "band_kind": band_col,
                    "bands": {
                        name: {
                            **_fleet_baseline_dict(sb),
                            **({"trend": _fleet_trend_dict(trend_by_band[name])} if name in trend_by_band else {}),
                            # Per-band outliers (R8, Spec 01 §8.4 v0.13) —
                            # against that band's own all-flights baseline,
                            # same threshold as the unstratified outliers
                            # above, so the Trends view's rings agree with
                            # the stratified baseline region when
                            # stratification is on (Spec 03 §5.3 v0.11).
                            "outliers": [
                                {"flight_id": o.source_file, "z_score": o.z_score}
                                for o in outliers(df[df[band_col] == name], col, z_threshold=z_threshold)
                            ],
                        }
                        for name, sb in stratified.items()
                    },
                }
        metrics_out[key] = entry

        # Per-limit metrics have no insight rules (Spec 09 §3); the filter
        # monitor reports its own low-n condition (FILTER_REFERENCE_LOW_N).
        if 0 < b.n < MIN_FLIGHTS_FOR_CONFIDENCE and not key.startswith("limit_"):
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
            # Spec 10 D5: every flight's own (pressure_alt_ft, oat_c,
            # map_inhg), so evaluate_insights can fit its own leave-one-out
            # model per flight rather than judging a flight against a fit
            # that includes itself.
            "points": map_model["raw"],
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
        cylinder_balance=_cylinder_balance(df, expected_cyl),
    )


# topic_id -> (flight metric id, fleet MetricFleet key). Both sides use
# different naming conventions (registry.py ids vs. baselines.py's
# topic-shaped keys) — this is the one place that reconciles them.
_TOPIC_METRIC_MAP = {
    "egt_spread": ("egt_spread_mean_f", "egt_spread"),
    "oil_temp_peak": ("oil_temp_max_f", "oil_temp_peak"),
    "coolant_temp_peak": ("coolant_temp_max_f", "coolant_temp_peak"),
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


def _leave_one_out_map_fit(points: list[dict], flight_id: str) -> dict:
    """The takeoff-MAP regression fit on every other flight's point
    (Spec 10 D5) — same exclusion pattern as _leave_one_out_baseline,
    but for the regression model rather than a mean/std."""
    from .baselines import fit_takeoff_map
    others = [p for p in points if p["flight_id"] != flight_id]
    return fit_takeoff_map(others)


def _topic_baseline(fleet_metric: Optional[dict], flight_id: str, n_min: int = 10) -> dict:
    """
    The {mean, std, n, trend, comparison} shape topics.py's
    baseline_triggered/trend_triggered expect: leave-one-out for the
    baseline (R2), taken within the flight's own weather band when the
    metric is stratified and that band has at least n_min OTHER flights
    (R8, Spec 01 §8.4 v0.13) — falling back to the unstratified
    leave-one-out baseline otherwise. `comparison` records which was
    used: {"scope": "band"|"all", "band": str|None, "n": int}. The trend
    is always unstratified — a trend is over engine hours across all
    flights regardless of weather, never split by band, and naturally
    includes the flight being evaluated as its newest point.
    """
    if not fleet_metric:
        return {}
    points = fleet_metric.get("points", [])
    trend = fleet_metric.get("trend", {})

    own_band = next((p.get("band") for p in points if p["flight_id"] == flight_id), None)
    loo = _leave_one_out_baseline(points, flight_id)
    comparison = {"scope": "all", "band": None, "n": loo["n"]}
    if own_band is not None:
        band_points = [p for p in points if p.get("band") == own_band]
        band_loo = _leave_one_out_baseline(band_points, flight_id)
        if band_loo["n"] >= n_min:
            loo = band_loo
            comparison = {"scope": "band", "band": own_band, "n": band_loo["n"]}

    return {
        "mean": loo["mean"], "std": loo["std"], "n": loo["n"],
        "comparison": comparison,
        "trend": {
            "direction": trend.get("direction"),
            "r_squared": trend.get("r_squared"),
            "n": trend.get("n", 0),
            "slope": trend.get("slope"),
        },
    }


def exceedance_limit_id(e: dict) -> str:
    """An exceedance's limit_id — or, for an analysis written before Spec
    09 (no limit_id), a stand-in built from what it does carry, so its
    events still group per limit until the flight is re-analysed."""
    return e.get("limit_id") or f"legacy:{e['param']}:{e['limit_type']}:{e['label']}"


def _event_id(e: dict) -> str:
    """An exceedance's event_id — or, for an analysis written before Spec
    09 (no event_id), the same stand-in _event_summary below already
    falls back to on the way out. Used as a dict key wherever an event
    needs to be looked up by identity (suppressed_by), so every reader
    has to agree on this, not just the one write site that already
    tolerated a missing key with .get()."""
    return e.get("event_id") or f"{exceedance_limit_id(e)}@{e['start_utc']}"


def _events_by_limit(exceedances: list[dict]) -> dict[str, list[dict]]:
    """Exceedances grouped by limit, groups in order of each limit's first
    event (exceedances are already sorted by start time)."""
    out: dict[str, list[dict]] = {}
    for e in exceedances:
        out.setdefault(exceedance_limit_id(e), []).append(e)
    return out


def _limit_insight_id(flight_id: str, limit_id: str, kind: str) -> str:
    """Spec 09 §10.1: stable across wording changes, so a pilot's note stays
    attached when the message text changes."""
    return content_hash({"flight_id": flight_id, "topic_id": "limit_exceedances",
                         "limit_id": limit_id, "kind": kind})[:16]


def _event_window(exc: dict) -> dict:
    pad = max(exc["duration_s"] * 0.5, 15)
    return {
        "kind": "series_window",
        "channels": [exc["param"]] if exc["param"] in CHANNEL_REGISTRY else [],
        "start_s": max(0, (exc["elapsed_s"] or 0) - pad),
        "end_s": (exc["elapsed_s"] or 0) + exc["duration_s"] + pad,
    }


def _event_summary(exc: dict, suppressed_by: Optional[str] = None) -> dict:
    return {
        "event_id": _event_id(exc),
        "start_utc": exc["start_utc"],
        "elapsed_s": exc["elapsed_s"],
        "duration_s": exc["duration_s"],
        "observed_value": exc["observed_value"],
        "excess": exc.get("excess") if exc.get("excess") is not None else (
            exc["observed_value"] - exc["limit_value"] if exc["limit_type"] == "MAX"
            else exc["limit_value"] - exc["observed_value"]),
        "suppressed_by": suppressed_by,
    }


def _severity_for(rules: dict, topic_id: str, trigger_type: str) -> str:
    """Severity for a trigger (R1): from insight_rules.json if set, else
    the type-based default (limit for threshold, watch otherwise)."""
    for rule in rules.get("rules", {}).get(topic_id, {}).get("triggers", []):
        if rule.get("type") == trigger_type:
            return rule.get("severity") or ("limit" if trigger_type == "threshold" else "watch")
    return "limit" if trigger_type == "threshold" else "watch"


def _emit_cyl_deviation(fa, fleet, r_data, baseline_config, emit, topics_out) -> None:
    """Spec 08 §6 `egt_cyl_deviation`: one rule block applied to each
    cylinder's balance metric (`applies_to`), each against its own
    leave-one-out baseline."""
    rule = r_data.get("egt_cyl_deviation", {})
    enabled = rule.get("enabled", True)
    all_triggers = rule.get("triggers", []) if enabled else []
    applies_to = set(rule.get("applies_to") or _CYL_DEVIATION_KEYS)
    bd_n_min = next((t.get("n_min", 10) for t in all_triggers if t.get("type") == "baseline_deviation"), 10)

    cyls, metric_ids, low_n, fleet_n = [], [], False, 0
    for n, key in enumerate(_CYL_DEVIATION_KEYS, start=1):
        fleet_metric = fleet.metrics.get(key)
        value = fa.metrics.get(f"{key}_f", {}).get("value")
        if fleet_metric is None and value is None:
            continue
        metric_ids.append(key)
        b = _topic_baseline(fleet_metric, fa.flight_id, bd_n_min)
        fleet_n = max(fleet_n, b.get("n", 0))
        cyl_low_n = 0 < b.get("n", 0) < bd_n_min
        low_n = low_n or cyl_low_n
        z = resolve_outlier_z_threshold(baseline_config, key)
        triggers = [] if key not in applies_to else [
            {**t, "z_score_threshold": z} if t.get("type") == "baseline_deviation" else t
            for t in all_triggers
            if not (cyl_low_n and t.get("type") == "baseline_deviation")
        ]
        cyls.append({"cyl": n, "value": value, "b": b, "triggers": triggers})

    if not cyls:
        return
    raw = topics.cyl_deviation(cyls)
    for ins in raw["insights"]:
        ins["evidence"] = [{"kind": "metric", "metric_id": f"egt{ins.pop('cyl')}_deviation"}]
    emit("egt_cyl_deviation", raw, metric_ids, fleet_n)
    if low_n:
        topics_out[-1]["_low_n"] = True


def _hot_cyl_changed_for(fa, fleet) -> bool:
    """Spec 08 v0.3 §6: `hot_cyl_changed` is a flag on FlightAnalysis, not
    a rule condition — `cylinder_rank` emits no TopicResult. The flag
    itself is computed fleet-wide, once per update_fleet() (same
    leave-window-out principle as established_hot_cylinder), not
    recomputed here with rule-playground overrides — Trends needs the
    same flag for every flight on the strip at once, not just the one
    being evaluated, so there is exactly one computation to agree with
    (_hot_cyl_changed_flags)."""
    cb = fleet.cylinder_balance or {}
    point = next((p for p in cb.get("points", []) if p["flight_id"] == fa.flight_id), None)
    return bool(point and point.get("hot_cyl_changed"))


def evaluate_insights(
    flight_analysis: FlightAnalysis, fleet_analysis: FleetAnalysis, rules: dict,
    annotations: Optional[list[dict]] = None,
    filters: Optional[list[dict]] = None,
) -> "InsightSet":
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

    `annotations` (Spec 02 §6.5, R3): pilot notes already filtered to
    this flight_id — "the host is responsible for matching; the engine
    only attaches." Matched here by insight_id, which is itself a
    content_hash of {flight_id, topic_id, trigger, text} (below) — stable
    across re-evaluations only as long as an insight's exact wording
    doesn't change; a Sync reanalysis or a rule-playground edit that
    shifts a z-score enough to change the rendered text would orphan an
    existing note. A real edge, not fixed here, just not silently
    smoothed over either. `limit_exceedances` insights are the exception
    (Spec 09 §10.1): one per limit per flight, id'd by limit, not text.

    `filters` (Spec 09 §7, §10): the workspace's limit filters
    (filters.json entries). Each is validated here, not only by the UI —
    an invalid one is ignored with a diagnostic, the limit reporting
    unfiltered. A filtered limit's events split into a quiet "filtered"
    insight and a "breach" insight at the rule's severity; topic threshold
    insights for that limit fire only on breaching events. baseline_
    deviation and trend insights are never filtered. InsightSet.
    filters_hash identifies the filters applied.

    `cylinder_rank` (Spec 08 §6) compares this flight's hottest cylinder
    with the aircraft's usual one, from FleetAnalysis.cylinder_balance;
    `egt_cyl_deviation` baselines each cylinder's balance separately.
    """
    r_data = rules.get("rules", {})
    rules_hash = content_hash(rules)
    fm = flight_analysis.metrics
    flight_id = flight_analysis.flight_id
    notes_by_insight_id = {
        a["ref"]["insight_id"]: a["note"] for a in (annotations or []) if a.get("ref", {}).get("kind") == "insight"
    }
    # Same BaselineConfig update_fleet resolved fleet_analysis's outliers
    # from (carried in provenance) — not a fresh param, so this can never
    # be called with a config that disagrees with the fleet it's paired
    # with (Spec 01 §8.4 v0.8's "one threshold, two consumers").
    baseline_config = fleet_analysis.provenance.get("baseline_config") or {}

    topics_out: list[dict] = []
    limit_diagnostics: list[dict] = []
    filters_hash = content_hash(sorted(filters or [], key=lambda f: str(f.get("id"))))

    # Spec 09: limits resolve through the catalogue the flight was checked
    # against. Empty for a pre-Spec-09 analysis — topics then fall back to
    # the legacy numeric thresholds until the flight is re-analysed.
    limits_by_id = {lim["id"]: lim for lim in flight_analysis.limits}
    events_by_limit = _events_by_limit(flight_analysis.exceedances)

    # Spec 09 §7: classify each filtered limit's events. `unsuppressed`
    # (breaches, or every event on an unfiltered limit) is what topic
    # thresholds react to (§10.2).
    valid_filters, filter_diagnostics = _filters.active_filters(filters or [], limits_by_id, fleet_analysis)
    limit_diagnostics.extend(filter_diagnostics)
    suppressed_by: dict[str, Optional[str]] = {}   # event_id -> "magnitude" | "duration" | None
    frozen_by_limit: dict[str, dict] = {}
    for lid, flt in valid_filters.items():
        lim = limits_by_id[lid]
        z_ref = None
        if (flt.get("magnitude") or {}).get("mode") == "z":
            frozen = _filters.frozen_baseline(fleet_analysis, _filters._magnitude_metric(lim),
                                              (flt.get("reference") or {}).get("flight_ids", []))
            frozen_by_limit[lid] = frozen
            z_ref, _ = _filters.comparison_set(frozen, _filters.flight_band(flight_analysis, lim))
        for e in events_by_limit.get(lid, []):
            suppressed_by[_event_id(e)] = _filters.classify_event(e, flt, lim, z_ref)
    unsuppressed_by_limit = {
        lid: [e for e in evs if suppressed_by.get(_event_id(e)) is None]
        for lid, evs in events_by_limit.items()
    }

    def _resolve_limit_ref_events(topic_id: str) -> tuple[Optional[dict], Optional[list]]:
        """
        Spec 10 §4.1 (Spec 09 §10.2, §10.3): (om_limit, unsuppressed events)
        for a topic's rule-level `limit_refs` — the one mechanism every
        limit-referencing topic uses now (oil_temp_peak, coolant_temp_peak,
        overboost_time alike; Phase 6's overboost-only fallback is gone).
        `limit_refs` can in principle list more than one limit, but every
        current topic lists exactly one — the one this drives the analysis
        line and TopicResult.limit_refs for. An unresolvable entry reports
        a diagnostic rather than silently comparing against nothing.
        """
        refs = r_data.get(topic_id, {}).get("limit_refs") or []
        if not refs or not limits_by_id:
            return None, None
        ref = refs[0]
        om_limit = limits_by_id.get(ref)
        if om_limit is None:
            limit_diagnostics.append(Diagnostic(
                code="RULES_LIMIT_REF_UNRESOLVED", severity="warn", scope="topic",
                message=f"{topic_id}: limit_refs entry {ref!r} is not a limit in this engine profile.",
                refs={"topic_id": topic_id, "limit_ref": ref},
            ).to_dict())
            return None, None
        return om_limit, unsuppressed_by_limit.get(ref, [])

    def _emit(topic_id: str, raw: dict, metric_ids: list[str], fleet_n: int):
        confidence = _confidence(fleet_n)
        insights = []
        for ins in raw["insights"]:
            severity = ins.get("severity") or _severity_for(rules, topic_id, ins["trigger"])
            insight_id = content_hash({"flight_id": flight_id, "topic_id": topic_id,
                                        "trigger": ins["trigger"], "text": ins["text"]})[:16]
            # comparison (R8, Spec 01 §8.4 v0.13): only baseline_deviation
            # insights carry one — topics.py's baseline_triggered() is the
            # only thing that sets it on the raw insight dict.
            message = {"text": ins["text"]}
            if ins.get("comparison"):
                message["values"] = {"comparison": ins["comparison"]}
            extra = {"filter": ins["filter"]} if ins.get("filter") else {}
            if "filterable" in ins:
                extra["filterable"] = ins["filterable"]
            insight = {
                "id": insight_id,
                "topic_id": topic_id,
                "rule_id": f"{topic_id}.{ins['trigger']}",
                "trigger": ins["trigger"],
                "severity": severity,
                "message": message,
                "evidence": ins.get("evidence") or [{"kind": "metric", "metric_id": mid} for mid in metric_ids],
                "confidence": confidence,
                **extra,
            }
            if insight_id in notes_by_insight_id:
                insight["note"] = notes_by_insight_id[insight_id]
            insights.append(insight)
        topics_out.append({
            "topic_id": topic_id,
            "analysis": {"text": raw["analysis"]},
            "insights": insights,
            "metric_ids": metric_ids,
        })

    # ── The 8 topics driven by a single flight metric + fleet baseline ──────
    for topic_id, (flight_metric_id, fleet_key) in _TOPIC_METRIC_MAP.items():
        # Spec 10 D2: climb_thermal_rate ships disabled (Research status) —
        # a disabled topic emits no TopicResult at all, not just zero
        # insights, so it has no Flight view card. The rise-rate metrics
        # themselves stay computed (fm/fleet_analysis), just not surfaced
        # as a topic here.
        if not r_data.get(topic_id, {}).get("enabled", True):
            continue
        value = fm.get(flight_metric_id, {}).get("value")
        fleet_metric = fleet_analysis.metrics.get(fleet_key)
        all_triggers = r_data.get(topic_id, {}).get("triggers", [])
        # BASELINE_LOW_N (R2): below n_min, no baseline_deviation insight
        # may fire — drop those triggers before calling the topic function
        # (not after: the insight would already exist in its output).
        # Resolved before _topic_baseline() now (R8, Spec 01 §8.4 v0.13):
        # the same n_min also gates whether a stratified metric compares
        # within-band or falls back to all-flights.
        bd_n_min = next((t.get("n_min", 10) for t in all_triggers if t.get("type") == "baseline_deviation"), 10)
        b = _topic_baseline(fleet_metric, flight_id, bd_n_min)
        fleet_n = b.get("n", 0)
        low_n = 0 < fleet_n < bd_n_min
        resolved_z = resolve_outlier_z_threshold(baseline_config, fleet_key)
        triggers = [
            {**t, "z_score_threshold": resolved_z} if t.get("type") == "baseline_deviation" else t
            for t in all_triggers
            if not (low_n and t.get("type") == "baseline_deviation")
        ]

        if topic_id == "egt_spread":
            enabled = r_data.get(topic_id, {}).get("enabled", True)
            raw = topics.egt_spread(value, 392, b, triggers, enabled)
        elif topic_id in ("oil_temp_peak", "coolant_temp_peak"):
            om_limit, limit_events = _resolve_limit_ref_events(topic_id)
            fn = topics.oil_temp_peak if topic_id == "oil_temp_peak" else topics.coolant_temp_peak
            raw = fn(value, b, triggers, om_limit=om_limit, limit_events=limit_events)
        elif topic_id == "climb_thermal_rate":
            raw = topics.climb_thermal_rate(value, b, triggers)
        else:  # pragma: no cover — exhaustive per _TOPIC_METRIC_MAP
            continue

        # Evidence and the topic's own metric_ids must carry the fleet-side
        # key (Trends/get_fleet's naming), not flight_metric_id — "View
        # evidence" navigates with this id as ?metric=, and the two sides
        # of _TOPIC_METRIC_MAP disagree on naming for 7 of 8 topics.
        _emit(topic_id, raw, [fleet_key], fleet_n)
        if low_n:
            topics_out[-1]["_low_n"] = True

    _emit_cyl_deviation(flight_analysis, fleet_analysis, r_data, baseline_config, _emit, topics_out)
    flight_analysis.hot_cyl_changed = _hot_cyl_changed_for(flight_analysis, fleet_analysis)

    cyl_dev_topic = next((t for t in topics_out if t["topic_id"] == "egt_cyl_deviation"), None)

    # Spec 08 §6 (Spec 10 D4): the deviation insight for the cylinder that
    # is now hottest names the change and the usual cylinder — only when
    # that specific cylinder's own insight fired, matched via its evidence
    # (the "cyl" key _emit_cyl_deviation pops is gone by the time a topic
    # reaches topics_out). The flag itself and its margin/consecutive-flight
    # logic are unchanged from Phase A.
    if flight_analysis.hot_cyl_changed and cyl_dev_topic and cyl_dev_topic["insights"]:
        hottest_cyl = fm.get("egt_hottest_cyl", {}).get("value")
        usual_cyl = (fleet_analysis.cylinder_balance or {}).get("established_hot_cyl", {}).get("cyl")
        if hottest_cyl is not None and usual_cyl is not None:
            target_metric = f"egt{int(hottest_cyl)}_deviation"
            for ins in cyl_dev_topic["insights"]:
                if any(e.get("metric_id") == target_metric for e in ins["evidence"]):
                    ins["message"]["text"] += f" It is now the hottest cylinder (usually cylinder {usual_cyl})."

    # Spec 08 §6 (Spec 10 D8): egt_spread's baseline_deviation insight
    # folds into the cylinder insight(s) whenever any egt_cyl_deviation
    # trigger fired — one insight instead of two reporting the same
    # underlying imbalance. The trend trigger is never affected.
    egt_spread_topic = next((t for t in topics_out if t["topic_id"] == "egt_spread"), None)
    if cyl_dev_topic and cyl_dev_topic["insights"] and egt_spread_topic:
        spread_bd = [i for i in egt_spread_topic["insights"] if i["trigger"] == "baseline_deviation"]
        if spread_bd:
            egt_spread_topic["insights"] = [i for i in egt_spread_topic["insights"] if i["trigger"] != "baseline_deviation"]
            for ins in cyl_dev_topic["insights"]:
                ins["message"]["text"] += " EGT spread is also outside its usual range."

    # ── Topics with their own data source (no shared baseline pattern) ──────
    # Spec 09 v0.12 §6.4/§10.3, Spec 10 §4.1: a block past the limit is an
    # ordinary limit_exceedances event (below); this topic only resolves
    # the close call, whose threshold still shifts with any active filter
    # band. `_resolve_limit_ref_events` is the same resolution oil_temp_peak
    # / coolant_temp_peak use — overboost no longer gets its own mechanism.
    ob_om, _ = _resolve_limit_ref_events("overboost_time")
    if ob_om is not None:
        ob_limit = ob_om["limit_value"]
        ob_filter = valid_filters.get(ob_om["id"])
        ob_band = (_filters.resolved_band(ob_filter, ob_om, frozen_by_limit.get(ob_om["id"])) or 0.0
                   if ob_filter is not None else 0.0)
        ob_close_call = (ob_limit + ob_band) - ob_om.get("close_call_margin_s", 60)
    else:
        ob_limit = 300
        ob_close_call = None
    ob_total = fm.get("overboost_total_s", {}).get("value")
    ob_max = fm.get("overboost_max_block_s", {}).get("value")
    raw = topics.overboost(ob_total, ob_max, ob_limit, close_call_s=ob_close_call)
    for ins in raw["insights"]:
        if ob_om is not None:
            ins["filterable"] = _filters.resolve_filter_policy(ob_om)["filterable"]
    _emit("overboost_time", raw, ["overboost_total_s", "overboost_max_block_s"], 0)

    map_model = next((m for m in fleet_analysis.models if m["id"] == "takeoff_map"), None)
    map_points = (map_model or {}).get("points", [])
    map_loo_fit = _leave_one_out_map_fit(map_points, flight_id)
    map_trigger = next(
        (t for t in r_data.get("map_at_takeoff", {}).get("triggers", []) if t.get("type") == "threshold"),
        {},
    )
    map_z = map_trigger.get("z", 2.0)
    raw = topics.takeoff_map(
        fm.get("takeoff_map_inhg", {}).get("value"),
        fm.get("takeoff_pressure_alt_ft", {}).get("value"),
        fm.get("takeoff_oat_c", {}).get("value"),
        map_loo_fit, z=map_z,
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

    # analyze_inflight_pattern() (cas.py) rebuilds its own event dicts and
    # drops elapsed_s along the way (it's also used fleet-wide, where one
    # flight's elapsed time isn't meaningful) — look the run back up by its
    # start_utc, which survives, to recover it for the series_window below.
    _ecu_runs_by_start = {r["start_utc"]: r for r in flight_analysis.ecu_runs}

    def _ecu_insight(e: dict) -> dict:
        iid = content_hash({"flight_id": flight_id, "topic_id": "engine_ecu_inflight", "event": e})[:16]
        run = _ecu_runs_by_start.get(e["start_time"]) or {}
        elapsed_s = run.get("elapsed_s")
        duration_s = run.get("duration_s") or e.get("duration_s") or 0
        # Zoom to the moment on this flight's own chart, like every other
        # insight (RPM + oil pressure — the pair a CAN-dropout/oil-NaN
        # signature actually shows up in). The ecu_run reference stays as a
        # second evidence entry so "See in ECU page" can still jump to and
        # highlight the matching run there (ECU.tsx's runRefKey) — a
        # deliberate second destination, not a replaced one.
        evidence = []
        if elapsed_s is not None:
            pad = max(duration_s * 0.5, 15)
            evidence.append({
                "kind": "series_window",
                "channels": [c for c in ("rpm", "oil_press_psi") if c in CHANNEL_REGISTRY],
                "start_s": max(0, elapsed_s - pad),
                "end_s": elapsed_s + duration_s + pad,
                # The event's own, unpadded bounds — a marker at the exact
                # moment, distinct from the padded window above (padding is
                # for zoom context; a one-row alert would otherwise be
                # invisible inside its own ~30s of surrounding padding).
                "marker_start_s": elapsed_s,
                "marker_end_s": elapsed_s + max(duration_s, 1),
            })
        evidence.append({"kind": "ecu_run", "ref": str(e["start_time"])})
        d = {
            "id": iid,
            "topic_id": "engine_ecu_inflight", "rule_id": "engine_ecu_inflight.threshold",
            "trigger": "threshold", "severity": _severity_for(rules, "engine_ecu_inflight", "threshold"),
            "message": {"text": f"⚠ IN-FLIGHT ENGINE ECU event at {e['start_time']}"},
            "evidence": evidence,
            "confidence": _confidence(0),
        }
        if iid in notes_by_insight_id:
            d["note"] = notes_by_insight_id[iid]
        return d

    ecu_topic = {
        "topic_id": "engine_ecu_inflight",
        "analysis": {"text": raw["analysis"]},
        "insights": [_ecu_insight(e) for e in raw["events"]],
        "metric_ids": ["inflight_ecu_count"],
    }
    topics_out.append(ecu_topic)

    # Bypasses _emit(): limit_exceedances is per-limit (Spec 09 §10.1), not
    # metric-shaped. One insight per limit per flight, carrying its events;
    # its evidence is one series_window per event, in time order, so the
    # card's click zooms to the first and the expanded rows to each.
    groups = []
    for lid, evs in events_by_limit.items():
        first = evs[0]
        lim = limits_by_id.get(lid) or {
            "id": lid, "label": first["label"], "unit": first["unit"], "limit_type": first["limit_type"],
            "limit_value": first["limit_value"], "severity": first["severity"],
        }
        flt = valid_filters.get(lid)
        if flt is None:
            groups.append({"limit_id": lid, "limit": lim, "events": evs, "kind": "exceedance"})
            continue
        text = _filters.band_text(flt, lim, frozen_by_limit.get(lid))
        breaches = [e for e in evs if suppressed_by.get(_event_id(e)) is None]
        tolerated = [e for e in evs if suppressed_by.get(_event_id(e)) is not None]
        if breaches:
            groups.append({"limit_id": lid, "limit": lim, "events": breaches, "kind": "breach",
                           "filter": flt, "filter_text": text})
        if tolerated:
            groups.append({"limit_id": lid, "limit": lim, "events": tolerated, "kind": "filtered",
                           "filter": flt, "filter_text": text})
    raw = topics.limit_exceedance_groups(groups)
    limit_insights = []
    noted_limits: set[str] = set()
    for ins in raw["insights"]:
        g = groups[ins.pop("group")]
        kind = g["kind"]
        iid = _limit_insight_id(flight_id, g["limit_id"], kind)
        if kind == "filtered":
            # Quiet: info for a CAUTION limit, watch for a WARNING one (§10.1).
            severity = "watch" if g["limit"].get("severity") == "WARNING" else "info"
        else:
            severity = _severity_for(rules, "limit_exceedances", ins["trigger"])
        limit_insight = {
            "id": iid,
            "topic_id": "limit_exceedances",
            "rule_id": "limit_exceedances.threshold",
            "trigger": ins["trigger"],
            "severity": severity,
            "message": {"text": ins["text"]},
            "evidence": [_event_window(e) for e in g["events"]],
            "confidence": _confidence(0),
            "limit_id": g["limit_id"],
            "events": [_event_summary(e, suppressed_by.get(_event_id(e))) for e in g["events"]],
            # Whether "Filter this limit…" can succeed (Spec 09 §6.3), so the UI
            # can say up front when it can't.
            "filterable": (_filters.resolve_filter_policy(g["limit"])["filterable"]
                           if g["limit_id"] in limits_by_id else False),
        }
        if kind != "exceedance":
            limit_insight["filter"] = {"filter_id": g["filter"]["id"],
                                       "outcome": "breach" if kind == "breach" else "suppressed"}
        # A note saved on this limit before it was filtered (or while it had
        # no breach) is keyed to another kind's id; show it on the limit's
        # first insight rather than lose it from view.
        note = notes_by_insight_id.get(iid)
        if note is None and g["limit_id"] not in noted_limits:
            note = next((notes_by_insight_id[k] for k in (
                _limit_insight_id(flight_id, g["limit_id"], other)
                for other in ("exceedance", "breach", "filtered") if other != kind)
                if k in notes_by_insight_id), None)
        if note is not None:
            limit_insight["note"] = note
            noted_limits.add(g["limit_id"])
        limit_insights.append(limit_insight)
    topics_out.append({
        "topic_id": "limit_exceedances",
        "analysis": {"text": raw["analysis"]},
        "insights": limit_insights,
        "metric_ids": [],
    })

    # Spec 10 §4.1 (Spec 01 §8.5 TopicResult.limit_refs, Spec 09 §10.2/
    # §10.3): every topic that declares limit_refs at rule level gets each
    # entry resolved to this flight's limit_exceedances insight for that
    # limit, or None if none fired — drives the mirrored badge (Spec 03
    # §5.2/§12.1). A limit can carry two insights on one flight only when a
    # filter splits events into breach + filtered (§10.1); breach (or a
    # plain, unfiltered exceedance) is preferred over a filtered one so the
    # badge mirrors the more actionable state.
    for t in topics_out:
        refs = r_data.get(t["topic_id"], {}).get("limit_refs")
        if not refs:
            continue
        resolved = []
        for lid in refs:
            candidates = [li for li in limit_insights if li["limit_id"] == lid]
            best = max(
                candidates,
                key=lambda li: 0 if (li.get("filter") or {}).get("outcome") == "suppressed" else 1,
            ) if candidates else None
            resolved.append({"limit_id": lid, "insight_id": best["id"] if best else None})
        t["limit_refs"] = resolved

    # header_warnings carries the flight's own quality diagnostics (e.g.
    # PHASE_NO_CRUISE — the "no stable cruise phase" banner the old text
    # report printed at the top) forward from FlightAnalysis, plus...
    header_warnings_dicts: list[dict] = list(flight_analysis.quality) + limit_diagnostics

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
        filters_hash=filters_hash,
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
    # Spec 09 §11.2: identifies the filters applied; a host caching insight
    # sets keys on it alongside analysis_key/fleet_key/rules_hash.
    filters_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "flight_id": self.flight_id,
            "analysis_key": self.analysis_key,
            "fleet_key": self.fleet_key,
            "rules_hash": self.rules_hash,
            "filters_hash": self.filters_hash,
            "topics": self.topics,
            "header_warnings": self.header_warnings,
            "provenance": self.provenance,
        }
