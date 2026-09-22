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

from . import __version__
from .cas import extract_engine_ecu_runs, parse_cas
from .contract import Diagnostic, Provenance, content_hash, engine_profile_ref
from .fleet import compute_flight_metrics
from .limits import check_exceedances
from .loader import flight_fingerprint, flight_id as _flight_id, load_log_bytes, source_key as _source_key
from .phases import detect_phases, phase_segments
from .registry import METRIC_REGISTRY, missing_reason

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
