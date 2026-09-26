"""
server.py — the local-server adapter (Spec 04 §9.2, Spec 01 §5 path 2).

A small HTTP server exposing the Spec 01 §7 operation envelope over
`POST /rpc`, so the browser UI can call the real engine without Pyodide.
Stdlib only — the spec has "a strong preference for minimal dependencies
to keep installation easy for non-experts," and the endpoint surface here
(one JSON route, op-dispatched) doesn't need more than that.

The server is a thin host: it resolves paths/bytes and persists the
workspace. Registry/multi-workspace awareness (Spec 02 v0.5) lives here
now too — `ctx["workspace_dir"]` is the *active* workspace and can change
at runtime via `switch_workspace`/`create_workspace`, not a path bound
once at startup. A server started with no workspace ever created via the
registry falls back to the pre-registry single-workspace layout exactly
as before (`ctx["active_workspace_id"] is None`) — every data op already
just reads/writes `ctx["workspace_dir"]`, so that fallback needed no
changes to the ops themselves, only to how that path gets resolved at
startup and how much workspace-management surface is available while in
it (add_log_folder/scan_workspace need a real manifest to write into, so
those specifically require an active registry workspace).

All analysis logic stays in operations.py. Binds to loopback (127.0.0.1)
only; the "any other interface needs an access token" case (Spec 04
§9.2, Docker/NAS) isn't implemented yet.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import sys
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from . import serialize as _json_serialize
from . import workspace as ws
from .channels import CHANNEL_REGISTRY, MAX_CHART_SLOTS, SLOT_GROUPS
from .cli import _REPO_ROOT, _write_workspace, resolve_logs_dir, resolve_workspace_dir
from .presets import validate_chart_preset
from .contract import content_hash
from .limits import _resolve_engine_name, load_engine_config
from .loader import flight_fingerprint, flight_id as _compute_flight_id, load_log_bytes
from .loader import source_key as _source_key
from .operations import (
    EcuAnalysis,
    FlightAnalysis,
    FleetAnalysis,
    InsightSet,
    analyze_ecu,
    analyze_flight,
    evaluate_insights,
    update_fleet,
)
from .rules import validate_rules

# Mirrors loader.load_directory's default ground-session threshold — kept
# here rather than imported since it's a single-file check, not a batch
# scan; drift risk is worth the duplication until this is worth factoring
# into loader.py itself.
_GROUND_SESSION_MIN_AIRBORNE_MIN = 3.0

_DEFAULT_RULES_PATH = _REPO_ROOT / "insight_rules.json"
_CHART_PRESETS_PATH = _REPO_ROOT / "chart_presets.json"

_SEVERITY_RANK = {"limit": 0, "warning": 1, "watch": 2, "info": 3}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RpcError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _decode_log(params: dict) -> tuple[bytes, str]:
    if "content_base64" not in params or "filename" not in params:
        raise RpcError("BAD_PARAMS", "expected content_base64 and filename")
    return base64.b64decode(params["content_base64"]), params["filename"]


def _dataclass_from_dict(cls, d: dict):
    # Every contract result dataclass's fields are already flat
    # dicts/lists/strings (see their .to_dict() — an identity mapping), so
    # this is a safe, generic inverse as long as the dict came from the
    # matching .to_dict() in the first place.
    return cls(**d)


def _default_rules() -> dict:
    return json.loads(_DEFAULT_RULES_PATH.read_text())


def _resolve_rules(ctx: dict) -> dict:
    """The rules actually governing insight evaluation right now — the
    workspace's rules/active.json if a pilot has edited one, else the
    shipped defaults. Distinct from _default_rules()/get_default_rules,
    which is always "what's shipped" (needed as the rule playground's
    comparison baseline for "reset to shipped defaults")."""
    if ctx.get("active_workspace_id"):
        return ws.load_workspace_rules(ctx["workspace_dir"], _default_rules())
    return _default_rules()


def _current_engine(ctx: dict) -> tuple[dict, str]:
    """
    The active workspace's locked engine_model (Spec 02 §5.6) — applied
    unconditionally, never per-log. In legacy (no active registry
    workspace) mode there's no lock to read, so this falls back to the
    same --engine/env/config.json/default precedence every other
    standalone operation already uses.
    """
    if ctx.get("active_workspace_id"):
        manifest = ws.load_manifest(ctx["workspace_dir"])
        return load_engine_config(manifest.engine_model), manifest.engine_model
    engine_name = _resolve_engine_name(None)
    return load_engine_config(engine_name), engine_name


def _require_active(ctx: dict) -> None:
    if not ctx.get("active_workspace_id"):
        raise RpcError(
            "NO_ACTIVE_WORKSPACE",
            "no active workspace — create one first (workspace.create_workspace / the + New workspace action)",
        )


def _classify_ingest(content: bytes, filename: str, workspace_dir: Path) -> dict:
    df, info = load_log_bytes(content, filename)
    rpm = df["rpm"].fillna(0) if "rpm" in df.columns else pd.Series(0, index=df.index)
    ias = df["ias_kt"].fillna(0) if "ias_kt" in df.columns else pd.Series(0, index=df.index)
    airborne_rows = int(((rpm > 3000) & (ias > 30)).sum())
    airborne_min = round(airborne_rows / 60.0, 1)
    if airborne_min < _GROUND_SESSION_MIN_AIRBORNE_MIN:
        return {"classification": "ground_session", "filename": filename, "airborne_min": airborne_min}
    fid = _compute_flight_id(flight_fingerprint(df, info))
    if (workspace_dir / "flights" / fid / "analysis.json").exists():
        return {"classification": "duplicate", "filename": filename, "airborne_min": airborne_min, "flight_id": fid}
    return {"classification": "new", "filename": filename, "airborne_min": airborne_min, "flight_id": fid}


def _load_workspace_flights(workspace_dir: Path) -> list[FlightAnalysis]:
    flights_dir = workspace_dir / "flights"
    if not flights_dir.is_dir():
        return []
    out = []
    for d in sorted(flights_dir.iterdir()):
        f = d / "analysis.json"
        if f.exists():
            out.append(_dataclass_from_dict(FlightAnalysis, json.loads(f.read_text())))
    return out


def _downsample_series(content: bytes, filename: str, channels: list[str], n_buckets: int = 400) -> dict:
    """
    Each channel is downsampled independently, with its own min/max
    envelope per bucket (Spec 07 §11.2) — not all channels sampled at one
    reference channel's row indices, which silently dropped other
    channels' real extremes (finding 6: a CO spike and an overboost MAP
    peak both vanished behind RPM's envelope). Bucket edges depend only
    on row count, never on any channel's values, so channels fetched at
    different times under lazy fetch (§11.1) still land on identical
    bucket boundaries as if fetched together (§13.5). NaN rows are
    excluded from a bucket's argmin/argmax so a channel with scattered
    gaps doesn't have its true peak edged out by comparing against NaN.

    The synced-cursor readout no longer assumes every active channel has
    a point at the exact cursor x — the frontend does its own
    nearest-point lookup per series instead (§11.2).
    """
    df, _info = load_log_bytes(content, filename)
    t = df["elapsed_s"].to_numpy()
    present = [c for c in channels if c in df.columns]
    if not present:
        return {}

    edges = [int(round(i * len(df) / n_buckets)) for i in range(n_buckets + 1)]

    out: dict[str, list[list[Optional[float]]]] = {}
    for col in present:
        vals = df[col].to_numpy(dtype=float)
        indices: set[int] = set()
        for i in range(n_buckets):
            lo, hi = edges[i], edges[i + 1]
            if hi <= lo:
                continue
            seg = vals[lo:hi]
            finite = np.flatnonzero(~np.isnan(seg))
            if len(finite) == 0:
                continue
            indices.add(lo + int(finite[np.argmin(seg[finite])]))
            indices.add(lo + int(finite[np.argmax(seg[finite])]))

        points = []
        for idx in sorted(indices):
            v = vals[idx]
            points.append([round(float(t[idx]), 1), None if v != v else round(float(v), 1)])
        out[col] = points
    return out


# ── op handlers ───────────────────────────────────────────────────────────
# Each handler: (params: dict, ctx: dict) -> JSON-serializable result.
# ctx carries the resolved logs_dir/workspace_dir for this server instance,
# plus registry_path/workspaces_root/active_workspace_id (Spec 02 v0.5).

def op_get_default_rules(params: dict, ctx: dict) -> Any:
    return _default_rules()


def op_get_workspace_rules(params: dict, ctx: dict) -> Any:
    """The rule playground's opening state — resolved rules (active.json
    if edited, else shipped) plus the shipped defaults alongside, so the
    UI can show "shipped default: X" next to an edited value without a
    second round trip."""
    _require_active(ctx)
    return {"rules": _resolve_rules(ctx), "shipped_rules": _default_rules()}


def op_save_workspace_rules(params: dict, ctx: dict) -> Any:
    _require_active(ctx)
    ws.save_workspace_rules(ctx["workspace_dir"], params["rules"])
    return {"rules": params["rules"]}


def op_reset_workspace_rules(params: dict, ctx: dict) -> Any:
    _require_active(ctx)
    ws.reset_workspace_rules(ctx["workspace_dir"])
    return {"rules": _resolve_rules(ctx)}


def op_save_baseline_config(params: dict, ctx: dict) -> Any:
    """The rule playground's other document (Spec 01 §8.4 v0.8): unlike
    rules/active.json, outlier_z_threshold feeds update_fleet's
    outliers() too, not just evaluate_insights — so this rebuilds the
    fleet rather than just persisting, same as save_workspace_rules would
    if rules affected FleetMetric (they don't)."""
    _require_active(ctx)
    workspace_dir = ctx["workspace_dir"]
    ws.update_baseline_config(workspace_dir, params["baseline_config"])
    fleet = ws.rebuild_fleet(workspace_dir)
    return fleet.to_dict()


def op_what_if_rules(params: dict, ctx: dict) -> Any:
    """
    Spec 01 §7 `what_if_rules` / Spec 03 §5.5's live diff: for every
    flight currently in the fleet, evaluate_insights under both the
    *currently active* rules/baseline_config and a candidate (either or
    both supplied) — pure and fast, per spec, since neither input changes
    what update_fleet already computed for baselines/points. A candidate
    baseline_config only changes which side of outlier_z_threshold a
    z-score falls on, not the mean/std/points themselves, so this swaps
    fleet_analysis.provenance on an in-memory copy rather than actually
    rebuilding the fleet — the same shortcut resolve_outlier_z_threshold's
    per-metric resolution already makes real for evaluate_insights.
    Nothing here is persisted; that's save_workspace_rules/
    save_baseline_config's job once the pilot commits.
    """
    from dataclasses import replace as _dc_replace

    _require_active(ctx)
    workspace_dir = ctx["workspace_dir"]
    current_rules = _resolve_rules(ctx)
    current_fleet = _get_or_build_fleet(workspace_dir)

    candidate_rules = params.get("rules") or current_rules
    candidate_baseline_config = params.get("baseline_config")
    candidate_fleet = (
        _dc_replace(current_fleet, provenance={**current_fleet.provenance, "baseline_config": candidate_baseline_config})
        if candidate_baseline_config is not None else current_fleet
    )

    out: dict[str, dict] = {}
    for fa in _load_workspace_flights(workspace_dir):
        before = evaluate_insights(fa, current_fleet, current_rules)
        after = evaluate_insights(fa, candidate_fleet, candidate_rules)
        out[fa.flight_id] = {"before": before.to_dict(), "after": after.to_dict()}
    return {"flights": out}


def op_list_engines(params: dict, ctx: dict) -> Any:
    engines_dir = _REPO_ROOT / "engines"
    results = []
    for p in sorted(engines_dir.glob("*.json")):
        cfg = json.loads(p.read_text())
        meta = cfg.get("_metadata", {})
        results.append({
            "id": p.stem, "engine": meta.get("engine", p.stem),
            "source_status": meta.get("source_status", "UNKNOWN"), "hash": content_hash(cfg),
        })
    return results


def op_get_channel_registry(params: dict, ctx: dict) -> Any:
    """Spec 07 v0.2 §4/§12: the chartable set, grouped, with each
    channel's insight-evidence companions, plus slot-group membership
    and the hard slot cap — the single source of truth the UI keeps no
    parallel list of (D4)."""
    channels = [
        {
            "id": c.id, "unit": c.unit, "description": c.description, "label": c.label,
            "group": c.group, "slot_group": c.slot_group, "companions": list(c.companions),
            "unit_variant_of": c.unit_variant_of,
        }
        for c in CHANNEL_REGISTRY.values() if c.chartable
    ]
    slot_groups = [{"id": sg.id, "label": sg.label, "members": list(sg.members)} for sg in SLOT_GROUPS.values()]
    return {"channels": channels, "slot_groups": slot_groups, "max_chart_slots": MAX_CHART_SLOTS}


def op_ingest_log(params: dict, ctx: dict) -> Any:
    content, filename = _decode_log(params)
    return _classify_ingest(content, filename, ctx["workspace_dir"])


def op_analyze_flight(params: dict, ctx: dict) -> Any:
    content, filename = _decode_log(params)
    engine_name = _resolve_engine_name(params.get("engine"))
    engine_cfg = load_engine_config(engine_name)
    fa = analyze_flight(content, filename, engine_cfg, engine_name)
    return fa.to_dict()


def _expand_channels(channels: list[str]) -> list[str]:
    """Spec 07 §11.1: a slot-group id expands to its members here, so a
    caller can pass e.g. "egt_cyl" directly instead of pre-expanding it
    client-side."""
    out: list[str] = []
    for cid in channels:
        sg = SLOT_GROUPS.get(cid)
        out.extend(sg.members if sg else [cid])
    return out


def op_get_series(params: dict, ctx: dict) -> Any:
    content, filename = _decode_log(params)
    channels = params.get("channels")
    if not channels:
        raise RpcError("BAD_PARAMS", "channels is required")
    return _downsample_series(content, filename, _expand_channels(channels))


def op_update_fleet(params: dict, ctx: dict) -> Any:
    fas = [_dataclass_from_dict(FlightAnalysis, d) for d in params["flight_analyses"]]
    engine_cfg = load_engine_config(_resolve_engine_name(params.get("engine")))
    fleet = update_fleet(fas, excluded=params.get("excluded"), baseline_config=params.get("baseline_config"),
                         engine_config=engine_cfg)
    return fleet.to_dict()


def op_evaluate_insights(params: dict, ctx: dict) -> Any:
    fa = _dataclass_from_dict(FlightAnalysis, params["flight_analysis"])
    fleet = _dataclass_from_dict(FleetAnalysis, params["fleet_analysis"])
    rules = params.get("rules") or _default_rules()
    return evaluate_insights(fa, fleet, rules).to_dict()


def op_analyze_ecu(params: dict, ctx: dict) -> Any:
    fas = [_dataclass_from_dict(FlightAnalysis, d) for d in params["flight_analyses"]]
    return analyze_ecu(fas).to_dict()


def op_analyze_ecu_workspace(params: dict, ctx: dict) -> Any:
    """The ECU view's live data (Spec 03 §5.4): every flight already in
    the active workspace, aggregated server-side — unlike op_analyze_ecu,
    the caller doesn't round-trip each flight's full FlightAnalysis over
    the wire just to hand it straight back."""
    return analyze_ecu(_load_workspace_flights(ctx["workspace_dir"])).to_dict()


def op_validate_rules(params: dict, ctx: dict) -> Any:
    return validate_rules(params["rules"])


def _source_filename(workspace_dir: Path, flight_id: str) -> Optional[str]:
    """The real log filename to show in the UI — not the flight_id hash,
    which op_get_flight/op_list_flights fell back to displaying whenever
    this returned None for a folder-scanned flight (same root cause as
    op_get_flight_series before: only the workspace's own persisted copy
    was ever checked, and only import_files writes one of those). A
    folder-scanned flight still has its real filename recorded in
    FlightSources.imports regardless — that's the actual source of truth
    for "what was this log called," not the workspace copy's presence."""
    d = workspace_dir / "flights" / flight_id
    if d.is_dir():
        others = [p.name for p in d.iterdir() if p.name not in ("analysis.json", "sources.json")]
        if others:
            return others[0]
    src = ws.load_sources(workspace_dir, flight_id)
    return src.imports[-1].filename if src and src.imports else None


def op_list_flights(params: dict, ctx: dict) -> Any:
    return [
        {
            "flight_id": fa.flight_id, "header": fa.header, "quality": fa.quality,
            "source_filename": _source_filename(ctx["workspace_dir"], fa.flight_id),
        }
        for fa in _load_workspace_flights(ctx["workspace_dir"])
    ]


def op_get_flight(params: dict, ctx: dict) -> Any:
    flight_id = params["flight_id"]
    f = ctx["workspace_dir"] / "flights" / flight_id / "analysis.json"
    if not f.exists():
        raise RpcError("NOT_FOUND", f"no flight {flight_id} in this workspace")
    fa = _dataclass_from_dict(FlightAnalysis, json.loads(f.read_text()))
    fleet = _get_or_build_fleet(ctx["workspace_dir"])
    annotations = ws.annotations_for_flight(ctx["workspace_dir"], flight_id)
    iset = evaluate_insights(fa, fleet, _resolve_rules(ctx), annotations=annotations)
    return {
        "flight_analysis": fa.to_dict(), "insight_set": iset.to_dict(),
        "source_filename": _source_filename(ctx["workspace_dir"], flight_id),
    }


def _engine_config_for(workspace_dir: Path) -> dict:
    """The workspace's locked engine profile when it has a manifest, else
    the standalone precedence (see _current_engine) — update_fleet needs
    it only for the expected-hottest-cylinder prior (Spec 08 §3)."""
    if (workspace_dir / "manifest.json").exists():
        return load_engine_config(ws.load_manifest(workspace_dir).engine_model)
    return load_engine_config(_resolve_engine_name(None))


def _get_or_build_fleet(workspace_dir: Path) -> FleetAnalysis:
    cache = workspace_dir / "fleet" / "analysis.json"
    if cache.exists():
        return _dataclass_from_dict(FleetAnalysis, json.loads(cache.read_text()))
    fas = _load_workspace_flights(workspace_dir)
    return update_fleet(fas, engine_config=_engine_config_for(workspace_dir))


def op_get_fleet(params: dict, ctx: dict) -> Any:
    return _get_or_build_fleet(ctx["workspace_dir"]).to_dict()


def op_get_flight_series(params: dict, ctx: dict) -> Any:
    """The Flight view's timeline. Checks the workspace's own persisted
    copy first (fast path — every upload-imported flight has one), then
    falls back to re-reading from wherever ws.read_source_bytes can
    actually find it (a scanned flight's registered log folder) — a
    folder-scanned flight never gets a copy written into the workspace
    itself (only import_files does that), so without this fallback its
    timeline had nowhere to read from at all, regardless of whether the
    source file was still perfectly reachable on disk."""
    flight_id = params["flight_id"]
    channels = params.get("channels")
    if not channels:
        raise RpcError("BAD_PARAMS", "channels is required")
    workspace_dir = ctx["workspace_dir"]
    flight_dir = workspace_dir / "flights" / flight_id
    source_files = [p for p in flight_dir.iterdir() if p.name not in ("analysis.json", "sources.json")] if flight_dir.is_dir() else []
    if source_files:
        content, filename = source_files[0].read_bytes(), source_files[0].name
    else:
        src = ws.load_sources(workspace_dir, flight_id)
        found = ws.read_source_bytes(workspace_dir, src) if src else None
        if found is None:
            raise RpcError("NOT_FOUND", f"no source log reachable for flight {flight_id} "
                                         f"(not retained in the workspace, and its log folder isn't reachable right now)")
        content, filename = found
    return _downsample_series(content, filename, _expand_channels(channels))


def op_rebuild_fleet(params: dict, ctx: dict) -> Any:
    if ctx.get("active_workspace_id"):
        return ws.rebuild_fleet(ctx["workspace_dir"]).to_dict()
    fas = _load_workspace_flights(ctx["workspace_dir"])
    fleet = update_fleet(fas, engine_config=_engine_config_for(ctx["workspace_dir"]))
    _write_workspace(ctx["workspace_dir"], fas, fleet)
    return fleet.to_dict()


def op_import_files(params: dict, ctx: dict) -> Any:
    """
    Workflow (Spec 01 §7 import_and_update, scoped to explicitly-uploaded
    bytes rather than a directory scan): classify each file, analyze the
    new ones, persist source bytes alongside the analysis so `get_series`
    can re-parse them later, record provenance (Spec 02 §6.2 FlightSources)
    so the flight shows up correctly in the Flights table regardless of
    whether it arrived via this upload path or a folder scan, merge with
    whatever's already in the workspace, and rebuild the fleet once at
    the end.

    Always uses the active workspace's locked engine (Spec 02 §5.6) — a
    per-call `engine` override doesn't apply here the way it does for the
    standalone analyze_flight op; a workspace-scoped import can't put a
    flight in the workspace under a different engine than the one every
    other flight there uses.
    """
    engine_cfg, engine_name = _current_engine(ctx)
    workspace_dir = ctx["workspace_dir"]

    results = []
    new_fas = []
    for item in params["files"]:
        content, filename = _decode_log({"content_base64": item["content_base64"], "filename": item["filename"]})
        classification = _classify_ingest(content, filename, workspace_dir)
        if classification["classification"] != "new":
            results.append(classification)
            continue
        fa = analyze_flight(content, filename, engine_cfg, engine_name)
        d = workspace_dir / "flights" / fa.flight_id
        d.mkdir(parents=True, exist_ok=True)
        (d / filename).write_bytes(content)
        new_fas.append(fa)

        # A browser upload has no real folder reference (unlike a scanned
        # log_folders entry) — log_folder_path says so plainly rather
        # than fabricating one.
        imp = ws.ImportRecord(
            source_key=_source_key(content), log_folder_path=ws.UPLOADED_SOURCE,
            relative_path=filename, filename=filename, imported_at=_now_iso(), via="unknown",
        )
        existing = ws.load_sources(workspace_dir, fa.flight_id)
        if existing:
            existing.imports.append(imp)
            ws.save_sources(workspace_dir, existing)
        else:
            ws.save_sources(workspace_dir, ws.FlightSources(flight_id=fa.flight_id, imports=[imp]))

        results.append({**classification, "flight_id": fa.flight_id})

    all_fas = _load_workspace_flights(workspace_dir) + new_fas
    # de-dupe in case a file was re-imported in the same batch as an existing one
    by_id = {fa.flight_id: fa for fa in all_fas}
    fleet = update_fleet(list(by_id.values()), engine_config=_engine_config_for(workspace_dir))
    _write_workspace(workspace_dir, list(by_id.values()), fleet)

    if ctx.get("active_workspace_id"):
        manifest = ws.load_manifest(workspace_dir)
        manifest.flight_count = len(by_id)
        manifest.updated_at = _now_iso()
        ws.save_manifest(workspace_dir, manifest)

    return {"results": results, "flight_count": len(by_id), "fleet_key": fleet.fleet_key}


def op_list_flights_with_status(params: dict, ctx: dict) -> Any:
    """
    The Spec 03 §5.1 Flights-table row shape — a host-side join of
    FlightAnalysis + FlightSources (Spec 02 §6.2) + FleetSelection (§6.3)
    that no single stored document has on its own.
    """
    workspace_dir = ctx["workspace_dir"]
    selection = ws.load_selection(workspace_dir)
    excluded = {e["flight_id"]: e["reason"] for e in selection.excluded}
    fleet = _get_or_build_fleet(workspace_dir)
    rules = _resolve_rules(ctx)

    unreachable_folders: set[str] = set()
    if ctx.get("active_workspace_id"):
        manifest = ws.load_manifest(workspace_dir)
        unreachable_folders = {f.path for f in manifest.log_folders if not f.reachable}

    rows = []
    for fid in ws.list_flight_ids(workspace_dir):
        fa = ws.load_flight_analysis(workspace_dir, fid)
        if fa is None:
            continue
        src = ws.load_sources(workspace_dir, fid)
        iset = evaluate_insights(fa, fleet, rules)
        insights = [i for t in iset.topics for i in t.get("insights", [])]
        worst = None
        for ins in insights:
            if worst is None or _SEVERITY_RANK[ins["severity"]] < _SEVERITY_RANK[worst]:
                worst = ins["severity"]

        status = "analyzed"
        if src and src.missing:
            status = "missing"
        elif src and src.imports and all(imp.log_folder_path in unreachable_folders for imp in src.imports):
            status = "folder_unreachable"

        h = fa.header
        last_import = src.imports[-1] if src and src.imports else None
        rows.append({
            "flight_id": fid,
            "date": h.get("date"),
            "airport": h.get("airport_hint") or "—",
            "duration_min": fa.metrics.get("duration_min", {}).get("value"),
            "engine_hours": h.get("engine_hours_end"),
            "insight_count": len(insights),
            "worst_severity": worst,
            "in_baselines": fid not in excluded,
            "excluded_reason": excluded.get(fid),
            "status": status,
            "different_tail_number": src.different_tail_number if src else None,
            "filename": last_import.filename if last_import else (_source_filename(workspace_dir, fid) or ""),
            "log_folder": last_import.log_folder_path if last_import else "",
        })
    return {"rows": rows}


def op_exclude_flight(params: dict, ctx: dict) -> Any:
    return ws.exclude_flight(ctx["workspace_dir"], params["flight_id"], params.get("reason", "")).to_dict()


def op_include_flight(params: dict, ctx: dict) -> Any:
    return ws.include_flight(ctx["workspace_dir"], params["flight_id"]).to_dict()


def op_list_annotations(params: dict, ctx: dict) -> Any:
    """All annotations in the active workspace, or just one flight's
    (Spec 03 §5.6 browse view vs. a single Flight view/ECU card's own
    lookup)."""
    flight_id = params.get("flight_id")
    if flight_id:
        return {"annotations": ws.annotations_for_flight(ctx["workspace_dir"], flight_id)}
    return ws.load_annotations(ctx["workspace_dir"])


def op_save_annotation(params: dict, ctx: dict) -> Any:
    return ws.save_annotation(
        ctx["workspace_dir"], params["flight_id"], params["ref"], params["note"],
        annotation_id=params.get("id"),
    )


def op_delete_annotation(params: dict, ctx: dict) -> Any:
    return {"deleted": ws.delete_annotation(ctx["workspace_dir"], params["id"])}


def op_remove_missing_flight(params: dict, ctx: dict) -> Any:
    return {"removed": ws.remove_missing_flight(ctx["workspace_dir"], params["flight_id"])}


def op_remove_flight(params: dict, ctx: dict) -> Any:
    """
    General remove (any status, not just Missing) — followed by the same
    scan_workspace a manual Rescan runs, so the workspace's flights/
    directory and the removed one's log_folders/fingerprint bookkeeping
    settle back into a consistent state in one round trip, and by a fleet
    rebuild since removal (unlike exclude/include) changes what's on disk,
    not just what's selected.
    """
    _require_active(ctx)
    workspace_dir = ctx["workspace_dir"]
    removed = ws.remove_flight(workspace_dir, params["flight_id"])
    scan_result = ws.scan_workspace(workspace_dir, ctx["registry_path"]) if removed else None
    if removed:
        ws.rebuild_fleet(workspace_dir)
    return {"removed": removed, "scan_result": scan_result.to_dict() if scan_result else None}


def op_remove_flights(params: dict, ctx: dict) -> Any:
    """Multi-select form of op_remove_flight — removes every requested
    flight first, then runs exactly one scan_workspace and one fleet
    rebuild for the whole batch rather than one pair per flight."""
    _require_active(ctx)
    workspace_dir = ctx["workspace_dir"]
    removed_ids = ws.remove_flights(workspace_dir, params["flight_ids"])
    scan_result = ws.scan_workspace(workspace_dir, ctx["registry_path"]) if removed_ids else None
    if removed_ids:
        ws.rebuild_fleet(workspace_dir)
    return {"removed_flight_ids": removed_ids, "scan_result": scan_result.to_dict() if scan_result else None}


# ── workspace management (Spec 02 v0.5) ──────────────────────────────────

def op_list_workspaces(params: dict, ctx: dict) -> Any:
    return [e.to_dict() for e in ws.list_workspaces(ctx["registry_path"])]


def _activate_workspace(ctx: dict, workspace_id: str) -> None:
    ctx["active_workspace_id"] = workspace_id
    ctx["workspace_dir"] = ctx["workspaces_root"] / workspace_id
    (ctx["workspace_dir"] / "flights").mkdir(parents=True, exist_ok=True)

    app_settings = ws.load_app_settings(ctx["registry_path"])
    app_settings.last_active_workspace_id = workspace_id
    ws.save_app_settings(ctx["registry_path"], app_settings)

    registry = ws.load_registry(ctx["registry_path"])
    for e in registry.workspaces:
        if e.id == workspace_id:
            e.last_opened_at = _now_iso()
    ws.save_registry(ctx["registry_path"], registry)


def op_create_workspace(params: dict, ctx: dict) -> Any:
    try:
        manifest = ws.create_workspace(
            ctx["registry_path"], ctx["workspaces_root"],
            params["name"], params["engine_model"],
            primary_tail_number=params.get("tail_number"),
        )
    except ValueError as e:
        raise RpcError("BAD_PARAMS", str(e))
    _activate_workspace(ctx, manifest.id)
    return manifest.to_dict()


def op_switch_workspace(params: dict, ctx: dict) -> Any:
    workspace_id = params["workspace_id"]
    registry = ws.load_registry(ctx["registry_path"])
    if not any(e.id == workspace_id for e in registry.workspaces):
        raise RpcError("NOT_FOUND", f"no workspace {workspace_id}")
    _activate_workspace(ctx, workspace_id)
    return op_get_active_workspace(params, ctx)


def op_get_active_workspace(params: dict, ctx: dict) -> Any:
    if not ctx.get("active_workspace_id"):
        return {"active": False, "workspace_dir": str(ctx["workspace_dir"])}
    manifest = ws.load_manifest(ctx["workspace_dir"])
    registry = ws.load_registry(ctx["registry_path"])
    entry = next((e for e in registry.workspaces if e.id == ctx["active_workspace_id"]), None)
    settings = ws.load_workspace_settings(ctx["workspace_dir"])
    return {
        "active": True,
        "manifest": manifest.to_dict(),
        "registry_entry": entry.to_dict() if entry else None,
        "settings": settings.to_dict(),
        "diagnostic": ws.engine_version_diagnostic(manifest),
    }


def op_add_log_folder(params: dict, ctx: dict) -> Any:
    _require_active(ctx)
    manifest = ws.add_log_folder(ctx["workspace_dir"], params["path"], ctx["registry_path"])
    return manifest.to_dict()


def op_scan_workspace(params: dict, ctx: dict) -> Any:
    """Finds new/missing/moved files AND re-analyzes any already-known
    flight whose stored analysis predates the running engine — one
    action covers both jobs (Spec 03 §5.1's Rescan), so the fleet only
    needs rebuilding here, once, when reanalysis actually changed a
    flight's metrics."""
    _require_active(ctx)
    workspace_dir = ctx["workspace_dir"]
    result = ws.scan_workspace(workspace_dir, ctx["registry_path"])
    if result.reanalyzed_flight_ids:
        ws.rebuild_fleet(workspace_dir)
    return result.to_dict()


def op_get_app_settings(params: dict, ctx: dict) -> Any:
    return ws.load_app_settings(ctx["registry_path"]).to_dict()


def op_save_app_settings(params: dict, ctx: dict) -> Any:
    settings = ws.AppSettings.from_dict(params["settings"])
    ws.save_app_settings(ctx["registry_path"], settings)
    return settings.to_dict()


def op_get_chart_presets(params: dict, ctx: dict) -> Any:
    """Shipped + user chart presets (Spec 07 §6.1/§12), each run through
    validate_chart_preset — an invalid preset is skipped with a
    PRESET_INVALID diagnostic rather than breaking the whole list."""
    shipped = json.loads(_CHART_PRESETS_PATH.read_text())["presets"]
    user = ws.load_app_settings(ctx["registry_path"]).chart_presets

    presets: list[dict] = []
    diagnostics: list[dict] = []
    seen_ids: set[str] = set()
    for preset in [*shipped, *user]:
        issues = validate_chart_preset(preset, existing_ids=frozenset(seen_ids))
        if issues:
            diagnostics.extend(issues)
            continue
        seen_ids.add(preset["id"])
        presets.append(preset)

    return {"presets": presets, "diagnostics": diagnostics, "max_chart_slots": MAX_CHART_SLOTS}


def op_save_user_preset(params: dict, ctx: dict) -> Any:
    """"Save as preset…" (Spec 07 §6.5) for creation — the id gets a
    user. prefix here so it can never collide with a shipped id (§6.2) —
    or an edit-in-place when params["id"] names an existing user preset
    (§6.6's rename; also how "duplicate a shipped preset" works, since
    that's just a creation call seeded with the shipped preset's
    channels). Rejects (doesn't just diagnostic-skip) an invalid preset,
    since this is the save path validate_chart_preset exists to gate."""
    label = params["label"]
    channels = params["channels"]
    settings = ws.load_app_settings(ctx["registry_path"])

    edit_id = params.get("id")
    existing = next(
        (p for p in settings.chart_presets if isinstance(p, dict) and p.get("id") == edit_id), None
    ) if edit_id else None
    preset_id = existing["id"] if existing else f"user.{uuid.uuid4().hex[:12]}"
    preset = {"id": preset_id, "label": label, "description": params.get("description", ""), "channels": channels}

    # Excludes the preset's own id — editing it in place must not trip
    # the duplicate-id check against itself.
    existing_ids = frozenset(
        p["id"] for p in settings.chart_presets
        if isinstance(p, dict) and p.get("id") and p["id"] != preset_id
    )
    issues = validate_chart_preset(preset, existing_ids=existing_ids)
    if issues:
        raise RpcError("BAD_PARAMS", "; ".join(d["message"] for d in issues))

    if existing:
        settings.chart_presets = [preset if p is existing else p for p in settings.chart_presets]
    else:
        settings.chart_presets = [*settings.chart_presets, preset]
    ws.save_app_settings(ctx["registry_path"], settings)
    return preset


def op_delete_user_preset(params: dict, ctx: dict) -> Any:
    """Spec 07 §6.6. Deleting a preset that happens to be someone's
    flight_chart.last_preset_id is fine — the Flight view's own
    last-preset resolution already falls back to "overview" whenever
    the stored id no longer names a real preset."""
    preset_id = params["id"]
    settings = ws.load_app_settings(ctx["registry_path"])
    before = len(settings.chart_presets)
    settings.chart_presets = [p for p in settings.chart_presets if not (isinstance(p, dict) and p.get("id") == preset_id)]
    deleted = len(settings.chart_presets) != before
    if deleted:
        ws.save_app_settings(ctx["registry_path"], settings)
    return {"deleted": deleted}


def op_reorder_user_presets(params: dict, ctx: dict) -> Any:
    """Spec 07 §6.6. `order` must be exactly the current user preset ids,
    just permuted — this isn't where an add/remove/rename also happens."""
    order = params["order"]
    settings = ws.load_app_settings(ctx["registry_path"])
    by_id = {p["id"]: p for p in settings.chart_presets if isinstance(p, dict) and p.get("id")}
    if set(order) != set(by_id.keys()):
        raise RpcError("BAD_PARAMS", "order must contain exactly the current user preset ids, permuted")
    settings.chart_presets = [by_id[pid] for pid in order]
    ws.save_app_settings(ctx["registry_path"], settings)
    return {"presets": settings.chart_presets}


def op_get_workspace_settings(params: dict, ctx: dict) -> Any:
    return ws.load_workspace_settings(ctx["workspace_dir"]).to_dict()


def op_save_workspace_settings(params: dict, ctx: dict) -> Any:
    settings = ws.WorkspaceSettings.from_dict(params["settings"])
    ws.save_workspace_settings(ctx["workspace_dir"], settings)
    return settings.to_dict()


_OPS: dict[str, Callable[[dict, dict], Any]] = {
    "get_default_rules": op_get_default_rules,
    "get_workspace_rules": op_get_workspace_rules,
    "save_workspace_rules": op_save_workspace_rules,
    "reset_workspace_rules": op_reset_workspace_rules,
    "save_baseline_config": op_save_baseline_config,
    "what_if_rules": op_what_if_rules,
    "list_engines": op_list_engines,
    "get_channel_registry": op_get_channel_registry,
    "ingest_log": op_ingest_log,
    "analyze_flight": op_analyze_flight,
    "get_series": op_get_series,
    "update_fleet": op_update_fleet,
    "evaluate_insights": op_evaluate_insights,
    "analyze_ecu": op_analyze_ecu,
    "analyze_ecu_workspace": op_analyze_ecu_workspace,
    "validate_rules": op_validate_rules,
    "list_flights": op_list_flights,
    "get_flight": op_get_flight,
    "get_fleet": op_get_fleet,
    "get_flight_series": op_get_flight_series,
    "rebuild_fleet": op_rebuild_fleet,
    "import_files": op_import_files,
    "list_flights_with_status": op_list_flights_with_status,
    "exclude_flight": op_exclude_flight,
    "include_flight": op_include_flight,
    "list_annotations": op_list_annotations,
    "save_annotation": op_save_annotation,
    "delete_annotation": op_delete_annotation,
    "remove_missing_flight": op_remove_missing_flight,
    "remove_flight": op_remove_flight,
    "remove_flights": op_remove_flights,
    "list_workspaces": op_list_workspaces,
    "create_workspace": op_create_workspace,
    "switch_workspace": op_switch_workspace,
    "get_active_workspace": op_get_active_workspace,
    "add_log_folder": op_add_log_folder,
    "scan_workspace": op_scan_workspace,
    "get_app_settings": op_get_app_settings,
    "save_app_settings": op_save_app_settings,
    "get_chart_presets": op_get_chart_presets,
    "save_user_preset": op_save_user_preset,
    "delete_user_preset": op_delete_user_preset,
    "reorder_user_presets": op_reorder_user_presets,
    "get_workspace_settings": op_get_workspace_settings,
    "save_workspace_settings": op_save_workspace_settings,
}


# ── HTTP layer ────────────────────────────────────────────────────────────

def _make_handler(ctx: dict, ui_dist: Optional[Path]):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            if not ctx["quiet"]:
                sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def do_OPTIONS(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler's naming)
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/rpc":
                self.send_response(404)
                self._cors()
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                envelope = json.loads(self.rfile.read(length))
                op, request_id, op_params = envelope["op"], envelope.get("request_id"), envelope.get("params", {})
                if op not in _OPS:
                    raise RpcError("UNKNOWN_OP", f"unknown operation: {op}")
                result = _OPS[op](op_params, ctx)
                body = {"request_id": request_id, "ok": True, "result": result}
            except RpcError as e:
                body = {"request_id": envelope.get("request_id") if "envelope" in dir() else None,
                        "ok": False, "error": {"code": e.code, "message": e.message}}
            except Exception as e:  # noqa: BLE001 — envelope must always respond, never crash the connection
                body = {"request_id": locals().get("envelope", {}).get("request_id"),
                        "ok": False, "error": {"code": "INTERNAL_ERROR", "message": f"{type(e).__name__}: {e}"}}
            payload = _json_serialize.dumps(body).encode("utf-8")
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            if ui_dist is None:
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(
                    b"SlingologyEIS local server is running. POST /rpc for the API.\n"
                    b"No built UI found - run `npm run build` in web/, or use `npm run dev` and point it at this server.\n"
                )
                return
            rel = self.path.lstrip("/") or "index.html"
            f = (ui_dist / rel)
            if not f.is_file():
                f = ui_dist / "index.html"  # SPA fallback for client-side routes
            self.send_response(200)
            self._cors()
            # Without this, every asset (including the built JS entry
            # point, loaded as <script type="module">) came back with no
            # Content-Type at all — Chrome's strict MIME-type enforcement
            # for module scripts silently refuses to execute an untyped
            # response, so the app never mounted past a blank #root, with
            # no console error to point at why.
            content_type, _ = mimetypes.guess_type(str(f))
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.end_headers()
            self.wfile.write(f.read_bytes())

    return Handler


def _resolve_active_workspace(workspace_arg: Optional[str], registry_path: Path, workspaces_root: Path) -> tuple[Path, Optional[str]]:
    """
    Spec 02 v0.5's registry, with the pre-registry single-workspace layout
    as an explicit, permanent fallback — never a special case that needs
    separate maintenance, just the "no workspace was ever created here"
    branch. Returns (workspace_dir, active_workspace_id | None).
    """
    if workspace_arg:
        registry = ws.load_registry(registry_path)
        match = next((e for e in registry.workspaces if workspace_arg in (e.id, e.name)), None)
        if match:
            return workspaces_root / match.id, match.id
        return Path(workspace_arg), None  # literal path, legacy behavior unchanged

    registry = ws.load_registry(registry_path)
    if registry.workspaces:
        app_settings = ws.load_app_settings(registry_path)
        match = next((e for e in registry.workspaces if e.id == app_settings.last_active_workspace_id), None)
        match = match or registry.workspaces[0]
        return workspaces_root / match.id, match.id

    return resolve_workspace_dir(None), None


def build_server(logs_dir: Optional[str], workspace_dir: Optional[str], port: int, quiet: bool) -> ThreadingHTTPServer:
    """
    Construct (but don't run) the server — split out from run_server() so
    tests can start it in a background thread and call .shutdown()
    cleanly, instead of blocking forever on serve_forever() in-process.
    """
    resolved_logs = resolve_logs_dir(logs_dir)
    registry_path = ws.resolve_registry_path()
    workspaces_root = ws.resolve_workspaces_root()
    resolved_workspace, active_workspace_id = _resolve_active_workspace(workspace_dir, registry_path, workspaces_root)
    (resolved_workspace / "flights").mkdir(parents=True, exist_ok=True)

    ctx = {
        "logs_dir": resolved_logs, "workspace_dir": resolved_workspace, "quiet": quiet,
        "registry_path": registry_path, "workspaces_root": workspaces_root,
        "active_workspace_id": active_workspace_id,
    }

    ui_dist = _REPO_ROOT / "web" / "dist"
    ui_dist = ui_dist if ui_dist.is_dir() else None

    handler = _make_handler(ctx, ui_dist)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.slingology_workspace_dir = resolved_workspace  # type: ignore[attr-defined]
    return httpd


def run_server(logs_dir: Optional[str], workspace_dir: Optional[str], port: int, quiet: bool) -> None:
    httpd = build_server(logs_dir, workspace_dir, port, quiet)
    if not quiet:
        print(f"SlingologyEIS local server: http://127.0.0.1:{httpd.server_port}/  "
              f"(workspace: {httpd.slingology_workspace_dir})", file=sys.stderr)  # type: ignore[attr-defined]
        print("POST /rpc for the API. Ctrl-C to stop.", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
