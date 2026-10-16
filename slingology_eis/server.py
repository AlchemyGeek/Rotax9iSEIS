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
import shutil
import sys
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from . import __version__
from . import exclusions as _exclusions
from . import serialize as _json_serialize
from . import data_location
from . import workspace as ws
from .channels import CHANNEL_REGISTRY, MAX_CHART_SLOTS, SLOT_GROUPS
from .cli import _REPO_ROOT, _write_workspace, resolve_logs_dir, resolve_workspace_dir
from .presets import validate_chart_preset
from .contract import content_hash
from .fleet import DA_BANDS, OAT_BANDS
from .limits import _resolve_engine_name, limit_catalog, load_engine_config, resolve_min_flight_duration_min
from .loader import flight_fingerprint, flight_id as _compute_flight_id, load_log_bytes
from .loader import source_key as _source_key
from .operations import (
    NO_CARD_TOPICS,
    EcuAnalysis,
    FlightAnalysis,
    FleetAnalysis,
    InsightSet,
    analyze_ecu,
    analyze_flight,
    build_trends_panels,
    evaluate_insights,
    get_topic_help,
    update_fleet,
)
from .phases import AIRBORNE_PHASES, detect_phases, phase_summary
from .rules import validate_rules
from . import filters as _filters

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
    """
    Classify one uploaded file before it becomes a flight (Spec 01 §7
    import_and_update, browser drag-and-drop path). Ground session /
    short flight / corrupt log auto-exclusions are recorded to
    exclusions.json here too, via the same shared classifier
    scan_workspace() (folder-scan) and load_directory() (CLI) use — this
    used to be a hand-rolled RPM/IAS heuristic that could silently
    disagree with the other two ingestion paths on what counts as a
    flight (Spec 02 §5.11.2).
    """
    df, info = load_log_bytes(content, filename)
    df = detect_phases(df, verbose=False)
    min_flight_duration_min = resolve_min_flight_duration_min()
    category, reason = _exclusions.classify_for_auto_exclusion(df, min_flight_duration_min)
    if category is not None:
        _exclusions.add_auto_exclusion(workspace_dir, filename, category, reason)
        if _exclusions.is_excluded(filename, _exclusions.load_exclusions(workspace_dir)):
            return {"classification": category, "filename": filename, "reason": reason}
        # else: this exact filename was already overridden -> falls through, becomes a flight below.

    fid = _compute_flight_id(flight_fingerprint(df, info))
    if (workspace_dir / "flights" / fid / "analysis.json").exists():
        return {"classification": "duplicate", "filename": filename, "flight_id": fid}
    return {"classification": "new", "filename": filename, "flight_id": fid}


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
    second round trip. card_topic_ids (Spec 14 §5.1 v0.6): the topics that
    have a Flight view card — enabled or not — so Settings can list a
    disabled topic as disabled without also listing the ones the engine
    never surfaces."""
    _require_active(ctx)
    rules = _resolve_rules(ctx)
    return {
        "rules": rules, "shipped_rules": _default_rules(),
        "card_topic_ids": [t for t in rules["rules"] if t not in NO_CARD_TOPICS],
    }


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
    before = ws.load_selection(workspace_dir).baseline_config or {}
    # Pinned references are their own decisions (set_reference /
    # clear_reference, Journal reference_pin), not settings: a settings
    # save keeps them as stored. The page edits the fleet's provenance
    # copy, which doesn't carry them — saving it used to delete every pin.
    after = {k: v for k, v in params["baseline_config"].items() if k != "pinned_references"}
    if before.get("pinned_references"):
        after["pinned_references"] = before["pinned_references"]
    ws.update_baseline_config(workspace_dir, after)
    fleet = ws.rebuild_fleet(workspace_dir)
    _sync_setting_entries(workspace_dir, before, after)
    return fleet.to_dict()


def _sync_setting_entries(workspace_dir: Path, before: dict, after: dict) -> None:
    """Spec 14 v0.13 §6.1: a setting edited away from shipped has its
    Journal entry (updated in place when edited again); one back at
    shipped has none."""
    was = {d["ref_id"]: d for d in ws.setting_decisions(before)}
    now = {d["ref_id"]: d for d in ws.setting_decisions(after)}
    for ref_id, d in now.items():
        if was.get(ref_id, {}).get("current") != d["current"]:
            ws.upsert_journal_entry(workspace_dir, kind="changed_setting", ref_id=ref_id, what=f"Setting: {d['label']}",
                                    where={"setting": ref_id, "tab": "reference"})
    for ref_id in was.keys() - now.keys():
        ws.remove_journal_entry(workspace_dir, kind="changed_setting", ref_id=ref_id)


def _num(v: Any) -> str:
    """A setting's number as Settings shows it: 2.0, 0.25, 15."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, float):
        return f"{v:.1f}" if v.is_integer() else f"{v:g}"
    return str(v)


def _setting_value(d: dict, key: str) -> str:
    """One setting's value as the pilot reads it."""
    v = d[key]
    if v is None:
        return "follows the global value" if d["field"] == "outlier_z_threshold_overrides" else "the profile's own"
    if d["field"]:
        return _num(v[d["field"]][d["metric_id"]])
    if d["ref_id"] == "recent_window":
        return (f"{_num(v['recent_window_hours'])} h, {_num(v['recent_window_min_flights'])}–"
                f"{_num(v['recent_window_max_flights'])} flights")
    (val,) = v.values()
    return _num(val)


def _setting_text(d: dict) -> str:
    return f"{_setting_value(d, 'current')} (shipped: {_setting_value(d, 'shipped')})"


def op_list_changed_settings(params: dict, ctx: dict) -> Any:
    """Spec 14 v0.13 §5: the settings that differ from shipped, each with
    its shipped value and its Journal entry — what Settings marks. No
    effect computed (that is Journal's, on open)."""
    _require_active(ctx)
    workspace_dir = ctx["workspace_dir"]
    ws.reconcile_journal(workspace_dir, active_rules=_resolve_rules(ctx), shipped_rules=_default_rules())
    entries = {e["ref_id"]: e["id"] for e in ws.load_journal(workspace_dir)["entries"] if e["kind"] == "changed_setting"}
    return {"settings": [
        {"ref_id": d["ref_id"], "label": d["label"], "current": _setting_value(d, "current"),
         "shipped": _setting_value(d, "shipped"), "entry_id": entries.get(d["ref_id"])}
        for d in ws.setting_decisions(ws.load_selection(workspace_dir).baseline_config)
    ]}


def op_reset_setting(params: dict, ctx: dict) -> Any:
    """*Reset to shipped* for one setting, from Settings or Journal: the
    setting goes back to shipped, everything else in baseline_config
    (other settings, pinned references) stays; the entry goes."""
    _require_active(ctx)
    workspace_dir = ctx["workspace_dir"]
    before = ws.load_selection(workspace_dir).baseline_config or {}
    try:
        after = ws.baseline_config_with_setting_reset(before, params["ref_id"])
    except ValueError as e:
        raise RpcError("NOT_FOUND", str(e))
    ws.update_baseline_config(workspace_dir, after)
    fleet = ws.rebuild_fleet(workspace_dir)
    _sync_setting_entries(workspace_dir, before, after)
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

    filters = _workspace_filters(ctx)
    out: dict[str, dict] = {}
    for fa in _load_workspace_flights(workspace_dir):
        before = evaluate_insights(fa, current_fleet, current_rules, filters=filters)
        after = evaluate_insights(fa, candidate_fleet, candidate_rules, filters=filters)
        out[fa.flight_id] = {"before": before.to_dict(), "after": after.to_dict()}
    return {"flights": out}


def _topic_insight_signature(iset, topic_id: str) -> frozenset:
    t = next((t for t in iset.to_dict()["topics"] if t["topic_id"] == topic_id), None)
    return frozenset((i["rule_id"], i["severity"]) for i in (t["insights"] if t else []))


def op_apply_card_rule_edit(params: dict, ctx: dict) -> Any:
    """Spec 14 §7.2 — the insight card's own Apply, replacing the retired
    playground's "Apply to workspace". Same mechanics as op_exclude_flight
    (§7.1): evaluate every flight's insights for the one edited topic
    before and after, so the counted effect and any "rule changed"
    markers are real, not estimated. The preview the card shows before
    this (acceptance 5) is the existing what_if_rules RPC — unchanged,
    reused as-is — so the card's preview and this apply can never
    disagree about what the edit does; there's only one evaluation path."""
    _require_active(ctx)
    workspace_dir = ctx["workspace_dir"]
    topic_id = params["topic_id"]
    new_topic = params["topic"]
    rules = _resolve_rules(ctx)
    fleet = _get_or_build_fleet(workspace_dir)
    filters = _workspace_filters(ctx)
    flights = _load_workspace_flights(workspace_dir)

    before = {fa.flight_id: _topic_insight_signature(evaluate_insights(fa, fleet, rules, filters=filters), topic_id) for fa in flights}

    new_rules = {**rules, "rules": {**rules["rules"], topic_id: new_topic}}
    ws.save_workspace_rules(workspace_dir, new_rules)
    resolved = _resolve_rules(ctx)

    changed = [
        fa.flight_id for fa in flights
        if _topic_insight_signature(evaluate_insights(fa, fleet, resolved, filters=filters), topic_id) != before[fa.flight_id]
    ]

    # Spec 14 v0.10 §6: the topic's Journal entries follow the rule now in
    # force — a rule_edit entry while the rule differs from shipped, a
    # disabled_topic entry while the pilot has it off. A further edit
    # updates the entry; Enable, or an edit back to shipped, removes it
    # (and resolves the markers it caused).
    entries = _sync_rule_entries(workspace_dir, topic_id, resolved)
    entry = entries.get("disabled_topic") or entries.get("rule_edit")
    if entry is not None:
        reason = ("the topic was turned off" if entry["kind"] == "disabled_topic"
                  else f"a rule setting changed on {topic_id}")
        for fid in changed:
            ws.add_reference_change_marker(
                workspace_dir, flight_id=fid, cause_journal_entry_id=entry["id"], cause_kind="rule_edit",
                cause_topic_id=topic_id, reason=reason,
            )
    return {"rules": resolved, "journal_entry": entry, "changed_flight_ids": changed}


def _sync_rule_entries(workspace_dir: Path, topic_id: str, resolved: dict) -> dict:
    """Upsert or remove `topic_id`'s rule_edit / disabled_topic entries so
    they match the rule in force. Returns {kind: entry} for those in force."""
    decisions = {kind for _, kind in ws.rule_decisions(
        {"rules": {topic_id: resolved["rules"].get(topic_id, {})}}, _default_rules())}
    out = {}
    for kind in ("rule_edit", "disabled_topic"):
        if kind in decisions:
            out[kind] = ws.upsert_journal_entry(workspace_dir, kind=kind, ref_id=topic_id,
                                                what=f"Rule: {topic_id}", where={"topic_id": topic_id})
        else:
            ws.remove_journal_entry(workspace_dir, kind=kind, ref_id=topic_id)
    return out


def op_revert_rule_edit(params: dict, ctx: dict) -> Any:
    """Removes a rule decision from Journal or a "rule changed" marker
    (Spec 14 v0.10 §6): a rule_edit entry puts the topic's rule back to
    shipped (its enabled flag stays as it is); a disabled_topic entry
    turns the topic back on. The entry goes, with its markers."""
    _require_active(ctx)
    workspace_dir = ctx["workspace_dir"]
    entry = ws.get_journal_entry(workspace_dir, entry_id=params["entry_id"])
    if entry is None or entry["kind"] not in ("rule_edit", "disabled_topic"):
        raise RpcError("NOT_FOUND", f"no rule_edit or disabled_topic journal entry {params['entry_id']}")
    topic_id = entry["ref_id"]
    rules = _resolve_rules(ctx)
    current = rules["rules"].get(topic_id, {})
    if entry["kind"] == "rule_edit":
        shipped = _default_rules()["rules"].get(topic_id, {})
        topic = {**shipped, "enabled": current.get("enabled", True)}
    else:
        topic = {**current, "enabled": True}
    ws.save_workspace_rules(workspace_dir, {**rules, "rules": {**rules["rules"], topic_id: topic}})
    resolved = _resolve_rules(ctx)
    _sync_rule_entries(workspace_dir, topic_id, resolved)
    return {"rules": resolved}


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


def op_get_engine_limits(params: dict, ctx: dict) -> Any:
    """Spec 14 §5 Engine tab — the active workspace's engine profile and
    its OM limit catalog, read-only (phase-aware suppression included
    for display; no engine-overrides support yet, Q1)."""
    engine_cfg, engine_name = _current_engine(ctx)
    meta = engine_cfg.get("_metadata", {})
    return {
        "engine": {
            "id": engine_name,
            "engine": meta.get("engine", engine_name),
            "variant": meta.get("variant"),
            "om_reference": meta.get("om_reference"),
            "source_status": meta.get("source_status", "UNKNOWN"),
        },
        "limits": limit_catalog(engine_cfg),
        # Spec 14 v0.13 §5: the engine version in effect (its What's new
        # page, Spec 13, isn't generated yet).
        "engine_version": __version__,
        # Spec 14 §5.1 Stratification panel — research-paper §9 constants
        # (fleet.py DA_BANDS/OAT_BANDS), read-only; not engine-specific but
        # bundled here so Settings loads them in the same round trip.
        "band_edges": {
            "da_band": [{"min": lo, "max": hi, "name": name} for lo, hi, name in DA_BANDS],
            "oat_band": [{"min": lo, "max": hi, "name": name} for lo, hi, name in OAT_BANDS],
        },
    }


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
    return evaluate_insights(fa, fleet, rules, annotations=params.get("annotations"),
                             filters=params.get("filters")).to_dict()


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
    engine_cfg, _ = _current_engine(ctx)
    return validate_rules(params["rules"], limit_ids={lim["id"] for lim in limit_catalog(engine_cfg)})


def _source_filename(workspace_dir: Path, flight_id: str) -> Optional[str]:
    """The real log filename to show in the UI — not the flight_id hash,
    which op_get_flight/op_list_flights fell back to displaying whenever
    this returned None for a folder-scanned flight (same root cause as
    op_get_flight_series before: only the workspace's own persisted copy
    was ever checked, and only import_files writes one of those). A
    folder-scanned flight still has its real filename recorded in
    FlightSources.imports regardless — that's the actual source of truth
    for "what was this log called," not the workspace copy's presence."""
    return ws.source_filename(workspace_dir, flight_id)


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
    iset = evaluate_insights(fa, fleet, _resolve_rules(ctx), annotations=annotations,
                             filters=_workspace_filters(ctx))
    # Live selection, not fleet.excluded — the fleet is a cache that's
    # only rebuilt explicitly (Spec 03 principle 3), but whether a flight
    # is excluded right now is simple, authoritative state that shouldn't
    # wait on a rebuild to display correctly.
    excluded_entry = next((e for e in ws.load_selection(ctx["workspace_dir"]).excluded if e["flight_id"] == flight_id), None)
    return {
        "flight_analysis": fa.to_dict(), "insight_set": iset.to_dict(),
        "source_filename": _source_filename(ctx["workspace_dir"], flight_id),
        # Spec 14 §7.1 — the Flight view header's "Contributes to
        # reference / Excluded from reference (reason)" state, and any
        # open "reference changed" markers (acceptance 8) for this flight.
        "reference_state": {"excluded": excluded_entry is not None, "reason": excluded_entry["reason"] if excluded_entry else None},
        "reference_changes": ws.open_reference_changes_for_flight(ctx["workspace_dir"], flight_id),
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


def op_get_trends_panels(params: dict, ctx: dict) -> Any:
    """Spec 12 R3.3: panel layout for the Trends page, built from the
    topic register rather than a frontend metric list."""
    from . import help as _help

    fleet = _get_or_build_fleet(ctx["workspace_dir"])
    register = _help.load_register() or {"topics": []}
    filters = ws.load_filters(ctx["workspace_dir"])["filters"]
    filtered_limit_ids = {_filters.target_key(f) for f in filters}
    panels = build_trends_panels(fleet, register, filtered_limit_ids)
    # Spec 12 v0.10 G2: a CAS panel shows its duration filter as a header
    # note, not a band — the web needs the duration to say so.
    durations = {_filters.target_key(f): (f.get("duration") or {}).get("max_event_s") for f in filters}
    for p in panels:
        if p.get("cas_id") and durations.get(p["panel"]) is not None:
            p["filter_max_event_s"] = durations[p["panel"]]
    return {"panels": panels}


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
    filters = _workspace_filters(ctx)

    unreachable_folders: set[str] = set()
    if ctx.get("active_workspace_id"):
        manifest = ws.load_manifest(workspace_dir)
        unreachable_folders = {f.path for f in manifest.log_folders if not f.reachable}

    # Spec 03 v0.17 §5.1: work waiting for the pilot's go-ahead — logs found
    # in the folders but not analysed, and flights analysed by an older engine.
    pending_logs, stale_ids = ws.pending_work(workspace_dir) if ctx.get("active_workspace_id") else ([], [])
    stale = set(stale_ids)

    rows = []
    for fid in ws.list_flight_ids(workspace_dir):
        fa = ws.load_flight_analysis(workspace_dir, fid)
        if fa is None:
            continue
        src = ws.load_sources(workspace_dir, fid)
        iset = evaluate_insights(fa, fleet, rules, filters=filters)
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
        elif fid in stale:
            status = "needs_reanalysis"

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
    for p in pending_logs:
        # No results yet: what the file name and folder say, nothing more.
        rows.append({
            "flight_id": None, "source_key": p["source_key"], "date": p["date"] or "", "airport": "—",
            "duration_min": None, "engine_hours": None, "insight_count": None, "worst_severity": None,
            "in_baselines": None, "excluded_reason": None, "status": "needs_analysis",
            "different_tail_number": None, "filename": p["filename"], "log_folder": p["log_folder"],
        })
    return {"rows": rows}


def _insight_signature(iset) -> frozenset:
    """(topic_id, rule_id, severity) per insight — the same grain
    Baselines.tsx's whatIf diff already uses client-side (added/removed/
    changed), here so exclude can tell which *other* flights' verdicts
    moved (Spec 14 §7.1, acceptance 8)."""
    return frozenset(
        (t["topic_id"], i["rule_id"], i["severity"])
        for t in iset.to_dict()["topics"] for i in t["insights"]
    )


def _other_flights_whose_verdict_changes(workspace_dir, flight_id, before_fleet, after_fleet, rules, filters) -> list[str]:
    """Flights other than `flight_id` whose insight verdict differs between
    the two fleets — what an exclusion (or its reversal) changes elsewhere.
    One computation for the exclude itself and for its preview (§7.1), so
    the preview's count and the Journal's counted effect can't disagree."""
    others = [fa for fa in _load_workspace_flights(workspace_dir) if fa.flight_id != flight_id]
    return [
        fa.flight_id for fa in others
        if _insight_signature(evaluate_insights(fa, before_fleet, rules, filters=filters))
        != _insight_signature(evaluate_insights(fa, after_fleet, rules, filters=filters))
    ]


def op_preview_reference_membership(params: dict, ctx: dict) -> Any:
    """Spec 14 §7.1 (v0.6): read-only — the other flights whose verdict
    would change if `flight_id` were excluded from the reference
    (action "exclude") or included again ("include"). Nothing is saved."""
    workspace_dir = ctx["workspace_dir"]
    flight_id = params["flight_id"]
    excluded = ws.load_selection(workspace_dir).excluded
    without = [e for e in excluded if e["flight_id"] != flight_id]
    with_it = without + [{"flight_id": flight_id, "reason": ""}]
    current = _get_or_build_fleet(workspace_dir)
    proposed = ws.fleet_for_exclusions(workspace_dir, with_it if params["action"] == "exclude" else without)
    changed = _other_flights_whose_verdict_changes(
        workspace_dir, flight_id, current, proposed, _resolve_rules(ctx), _workspace_filters(ctx),
    )
    return {"changed_flight_ids": changed}


def op_exclude_flight(params: dict, ctx: dict) -> Any:
    """Spec 14 §7.1: excluding a flight is also a Journal decision, with
    a reason, a counted effect, and a "reference changed" marker on any
    other flight whose insight verdict moved because the reference did.
    Computing that means evaluating every other flight's insights before
    and after — the one place in the app that sees both the before- and
    after-exclusion fleet, so it has to happen here rather than lazily
    at the next rebuild."""
    workspace_dir = ctx["workspace_dir"]
    flight_id = params["flight_id"]
    reason = params.get("reason", "")
    rules = _resolve_rules(ctx)
    filters = _workspace_filters(ctx)

    before_fleet = _get_or_build_fleet(workspace_dir)
    selection = ws.exclude_flight(workspace_dir, flight_id, reason)
    after_fleet = ws.rebuild_fleet(workspace_dir)
    changed = _other_flights_whose_verdict_changes(workspace_dir, flight_id, before_fleet, after_fleet, rules, filters)

    entry = ws.upsert_journal_entry(
        workspace_dir, kind="exclusion", ref_id=flight_id,
        what=_source_filename(workspace_dir, flight_id) or flight_id, where={"flight_id": flight_id}, reason=reason,
    )
    for fid in changed:
        ws.add_reference_change_marker(
            workspace_dir, flight_id=fid, cause_journal_entry_id=entry["id"], cause_kind="exclusion",
            cause_flight_id=flight_id, reason=reason,
        )
    return selection.to_dict()


def op_include_flight(params: dict, ctx: dict) -> Any:
    workspace_dir = ctx["workspace_dir"]
    flight_id = params["flight_id"]
    selection = ws.include_flight(workspace_dir, flight_id)
    ws.remove_journal_entry(workspace_dir, kind="exclusion", ref_id=flight_id)
    return selection.to_dict()


def op_update_exclusion_reason(params: dict, ctx: dict) -> Any:
    """Spec 14 v0.10 §6.1: editing an exclusion's reason updates its entry;
    the exclusion itself (and so the reference) is unchanged."""
    workspace_dir = ctx["workspace_dir"]
    flight_id = params["flight_id"]
    selection = ws.load_selection(workspace_dir)
    hit = next((e for e in selection.excluded if e["flight_id"] == flight_id), None)
    if hit is None:
        raise RpcError("NOT_FOUND", f"{flight_id} is not excluded")
    hit["reason"] = params.get("reason", "")
    ws.save_selection(workspace_dir, selection)
    ws.upsert_journal_entry(
        workspace_dir, kind="exclusion", ref_id=flight_id,
        what=_source_filename(workspace_dir, flight_id) or flight_id, where={"flight_id": flight_id}, reason=hit["reason"],
    )
    return selection.to_dict()


def op_set_reference(params: dict, ctx: dict) -> Any:
    """Spec 12 §11.3: pin a metric's shift reference. Returns the updated
    BaselineConfig, not a rebuilt fleet — same shape as op_exclude_flight,
    since the pin only changes what the *next* update_fleet call does."""
    _require_active(ctx)
    workspace_dir = ctx["workspace_dir"]
    metric_id = params["metric_id"]
    selection = ws.set_reference(workspace_dir, metric_id, params["flight_ids"], params.get("label"))
    # Re-pinning updates the entry (Spec 14 v0.10 §6.1).
    ws.upsert_journal_entry(
        workspace_dir, kind="reference_pin", ref_id=metric_id, what=metric_id, where={"metric_id": metric_id},
        note=params.get("label"),
    )
    return selection.baseline_config


def op_clear_reference(params: dict, ctx: dict) -> Any:
    _require_active(ctx)
    workspace_dir = ctx["workspace_dir"]
    selection = ws.clear_reference(workspace_dir, params["metric_id"])
    ws.remove_journal_entry(workspace_dir, kind="reference_pin", ref_id=params["metric_id"])
    return selection.baseline_config


def op_preview_clear_reference(params: dict, ctx: dict) -> Any:
    """Spec 12 §5.7.1 item 5: read-only — never calls ws.clear_reference,
    so the unpin confirmation can preview the effect before the pilot
    commits to it."""
    _require_active(ctx)
    return ws.preview_clear_reference(ctx["workspace_dir"], params["metric_id"])


def op_delete_shift_event(params: dict, ctx: dict) -> Any:
    _require_active(ctx)
    return {"shift_history": ws.delete_shift_event(ctx["workspace_dir"], params["event_id"])}


def _enrich_exclusion_entry(entry: dict, manifest: Optional["ws.WorkspaceManifest"]) -> dict:
    """
    Best-effort extra context for one exclusions.json entry, for display
    (date/duration/airborne minutes/aircraft) — none of this is stored
    in exclusions.json itself (just filename/category/reason), so it
    means re-locating and re-parsing the source file. None of the extra
    fields are added if the file can't be found (unreachable folder, or
    a browser-uploaded exclusion, which was never in a folder at all —
    its bytes were never saved anywhere) or fails to parse.
    """
    if manifest is None:
        return entry
    path = ws.find_log_file_by_name(manifest, entry["filename"])
    if path is None:
        return entry
    try:
        df, info = load_log_bytes(path.read_bytes(), entry["filename"])
        df = detect_phases(df, verbose=False)
        start, end = df["datetime"].iloc[0], df["datetime"].iloc[-1]
        airborne_s = sum(
            seg["duration_s"] for seg in phase_summary(df).to_dict("records")
            if seg["phase"] in AIRBORNE_PHASES
        )
        return {
            **entry,
            "date": start.strftime("%Y-%m-%d"),
            "duration_min": round((end - start).total_seconds() / 60),
            "airborne_min": round(airborne_s / 60),
            "aircraft_ident": info.aircraft_ident,
        }
    except Exception:
        return entry


def op_list_exclusions(params: dict, ctx: dict) -> Any:
    """
    The Flights tab's "Skipped" list (Spec 02 §5.11.5, Spec 03 §5.1)
    — every ground_session/short_flight/
    corrupt_log/user_defined entry currently in effect (not overridden),
    for a file that never became a flight_id at all. Distinct from
    op_list_flights_with_status's excluded_reason/in_baselines, which is
    for flights that DID get analyzed and are just held out of baselines
    (FleetSelection, a different mechanism).

    params.enrich (default False): also re-locate and re-parse each
    entry's source file for date/duration/airborne-minutes/aircraft —
    real I/O per file, not something to pay for on every routine
    refresh(), so the caller opts in only when actually showing the
    list (not just its count for a chip badge).
    """
    workspace_dir = ctx["workspace_dir"]
    exclusions = _exclusions.load_exclusions(workspace_dir)
    entries = [e for e in exclusions.get("entries", []) if not e.get("user_override")]

    if params.get("enrich"):
        manifest = None
        if ctx.get("active_workspace_id"):
            try:
                manifest = ws.load_manifest(workspace_dir)
            except (FileNotFoundError, OSError):
                manifest = None
        entries = [_enrich_exclusion_entry(e, manifest) for e in entries]

    # Spec 02 v0.11 §7.5: an imported workspace's flights whose log
    # hasn't been found — no actions; they resolve when the log is added.
    from . import workspace_export as wx
    sender_missing = wx.missing_flights(workspace_dir) if ctx.get("active_workspace_id") else []
    return {"entries": entries, "summary": _exclusions.exclusion_summary(exclusions), "sender_missing": sender_missing}


def op_include_excluded_log(params: dict, ctx: dict) -> Any:
    """
    Bring an auto/user-excluded log back — the exclusions.json
    counterpart to op_include_flight (which un-excludes an already-
    analyzed flight from baselines instead). This flips an exclusion
    that currently prevents the file from ever becoming a flight_id, and
    immediately runs a scan so a folder-scanned file's flight appears in
    the same round trip. A browser-uploaded file that was excluded has
    no bytes saved anywhere to scan for (only import_files persists
    those, and only for files it actually keeps) — for that case the
    override just clears the way for a re-upload of the same file to
    succeed next time.
    """
    _require_active(ctx)
    workspace_dir = ctx["workspace_dir"]
    filename = params["filename"]
    try:
        _exclusions.set_user_override(workspace_dir, filename, True, params.get("reason", ""))
    except ValueError as e:
        raise RpcError("NOT_FOUND", str(e))
    scan_result = ws.scan_workspace(workspace_dir, ctx["registry_path"])
    if scan_result.new_flight_ids:
        ws.rebuild_fleet(workspace_dir)
    return {"filename": filename, "included": True, "scan_result": scan_result.to_dict()}


def _find_excluded_log_path(ctx: dict, filename: str) -> Path:
    _require_active(ctx)
    try:
        manifest = ws.load_manifest(ctx["workspace_dir"])
    except (FileNotFoundError, OSError):
        raise RpcError("NOT_FOUND", f"{filename} not found in any watched folder")
    path = ws.find_log_file_by_name(manifest, filename)
    if path is None:
        raise RpcError("NOT_FOUND", f"{filename} not found in any watched folder")
    return path


def op_preview_excluded_log(params: dict, ctx: dict) -> Any:
    """
    Read-only preview of a skipped log's own data (Spec 02 §5.11.5)
    — runs analyze_flight() on it exactly like a real flight
    would, but persists nothing (no flights/<id> created, no
    exclusions.json change). The Skipped panel's "see the flight data"
    action, so a pilot can check whether a ground_session/short_flight/
    corrupt_log call was actually correct before deciding whether to
    Include it — without first having to bring it into the workspace to
    look.
    """
    path = _find_excluded_log_path(ctx, params["filename"])
    engine_cfg, engine_name = _current_engine(ctx)
    fa = analyze_flight(path.read_bytes(), params["filename"], engine_cfg, engine_name)
    return {"flight_analysis": fa.to_dict(), "source_filename": params["filename"]}


def op_get_excluded_log_series(params: dict, ctx: dict) -> Any:
    channels = params.get("channels")
    if not channels:
        raise RpcError("BAD_PARAMS", "channels is required")
    path = _find_excluded_log_path(ctx, params["filename"])
    return _downsample_series(path.read_bytes(), params["filename"], _expand_channels(channels))


# ── Limit filters (Spec 09 §11.5) ───────────────────────────────────────────

def _workspace_filters(ctx: dict) -> list[dict]:
    return ws.load_filters(ctx["workspace_dir"])["filters"]


def _latest_engine_hours(flight_analyses: list[FlightAnalysis]) -> Optional[float]:
    hours = [fa.header.get("engine_hours_end") or fa.header.get("engine_hours_start") for fa in flight_analyses]
    hours = [h for h in hours if h is not None]
    return max(hours) if hours else None


def _target_limits(engine_cfg: dict) -> dict:
    """The engine profile's limits plus the classified CAS alerts, keyed
    by filter target key (Spec 09 v0.18 §4)."""
    return _filters.with_cas_targets({lim["id"]: lim for lim in limit_catalog(engine_cfg)})


def _target_of(params: dict) -> dict:
    """A request's filter target: {kind, ...}, or a bare limit_id."""
    if params.get("target"):
        return params["target"]
    if params.get("limit_id"):
        return {"kind": "limit", "limit_id": params["limit_id"]}
    raise RpcError("BAD_PARAMS", "a filter target (target or limit_id) is required")


def op_list_filters(params: dict, ctx: dict) -> Any:
    """The workspace's filters, each with its target's catalogue entry
    (a limit, or a CAS alert's pseudo entry), whether it currently applies
    (the engine's own validation) and a summary of its conditions."""
    engine_cfg, _ = _current_engine(ctx)
    limits = _target_limits(engine_cfg)
    fleet = _get_or_build_fleet(ctx["workspace_dir"])
    out = []
    for f in _workspace_filters(ctx):
        diags = _filters.validate_filter(f, limits, fleet)
        lim = limits.get(_filters.target_key(f))
        out.append({
            "filter": f,
            "limit": lim,
            "target_label": _filters.target_label(f["target"], lim["label"] if lim else None),
            "policy": _filters.resolve_filter_policy(lim) if lim else None,
            "valid": not [d for d in diags if d["code"] != "FILTER_CAS_MAGNITUDE"],
            "diagnostics": diags,
            "summary": _filters.band_text(f, lim) if lim else "",
        })
    return {"filters": out}


def op_propose_filter(params: dict, ctx: dict) -> Any:
    engine_cfg, _ = _current_engine(ctx)
    fleet = _get_or_build_fleet(ctx["workspace_dir"])
    target = _target_of(params)
    try:
        draft = _filters.propose_limit_filter(_load_workspace_flights(ctx["workspace_dir"]), fleet,
                                              target, engine_cfg)
    except ValueError as e:
        raise RpcError("NOT_FOUND", str(e))
    key = _filters.target_key({"target": target})
    draft["existing"] = next((f for f in _workspace_filters(ctx) if _filters.target_key(f) == key), None)
    return draft


def op_preview_filter(params: dict, ctx: dict) -> Any:
    fleet = _get_or_build_fleet(ctx["workspace_dir"])
    draft = _filters.migrate_filter(dict(params["filter"]))
    if not draft.get("reference"):
        engine_cfg, _ = _current_engine(ctx)
        lim = _target_limits(engine_cfg).get(_filters.target_key(draft))
        if lim is not None:
            draft["reference"] = {"flight_ids": _filters.select_reference(fleet, lim)}
    return _filters.preview_limit_filter(_load_workspace_flights(ctx["workspace_dir"]), fleet,
                                         _resolve_rules(ctx), _workspace_filters(ctx), draft)


def op_save_filter(params: dict, ctx: dict) -> Any:
    """Validate first (§7.3) — an invalid filter is refused, not stored —
    then save. A new filter, or an edit to its band or duration, takes a
    fresh reference of the most recent flights (§8.1). A CAS filter's
    magnitude condition is not stored (FILTER_CAS_MAGNITUDE: ignored)."""
    workspace_dir = ctx["workspace_dir"]
    engine_cfg, _ = _current_engine(ctx)
    fleet = _get_or_build_fleet(workspace_dir)
    fields = _filters.migrate_filter(dict(params["filter"]))
    if not fields.get("target"):
        raise RpcError("BAD_PARAMS", "a filter target is required")
    limits = _target_limits(engine_cfg)
    key = _filters.target_key(fields)
    lim = limits.get(key)
    if lim is not None and _filters.is_cas(lim):
        fields.pop("magnitude", None)
    existing = ws.get_filter(workspace_dir, fields["id"]) if fields.get("id") else None
    if fields.get("id") and existing is None:
        raise RpcError("NOT_FOUND", f"no filter {fields['id']}")
    if existing is None:
        other = next((f for f in _workspace_filters(ctx) if _filters.target_key(f) == key), None)
        if other is not None:
            raise RpcError("ALREADY_EXISTS", f"{_filters.target_label(fields['target'])} already has a filter; edit it instead")
    elif _filters.target_key(existing) != key:
        raise RpcError("BAD_PARAMS", "a filter's target can't be changed")

    new_reference = None
    if lim is not None and (existing is None or ws.filter_conditions_changed(existing, fields)):
        new_reference = _filters.select_reference(fleet, lim)
    candidate = {**(existing or {}), **fields,
                 "reference": {"flight_ids": new_reference} if new_reference is not None
                 else (existing or {}).get("reference", {"flight_ids": []})}
    for k in ("magnitude", "duration", "phases"):
        if not fields.get(k):
            candidate.pop(k, None)
    diags = _filters.validate_filter(candidate, limits, fleet)
    if diags:
        raise RpcError("INVALID_FILTER", " ".join(d["message"] for d in diags))
    hours = _latest_engine_hours(_load_workspace_flights(workspace_dir)) if existing is None else None
    saved = ws.save_filter(workspace_dir, fields, reference_flight_ids=new_reference, engine_hours=hours)
    # Created or edited: one entry, current values (Spec 14 v0.10 §6.1).
    ws.upsert_journal_entry(
        workspace_dir, kind="limit_filter", ref_id=saved["id"],
        what=f"Filter: {_filters.target_label(saved['target'], lim['label'] if lim else None)}",
        where={"target": saved["target"]}, note=saved.get("note"),
    )
    return saved


def op_delete_filter(params: dict, ctx: dict) -> Any:
    workspace_dir = ctx["workspace_dir"]
    flt = ws.get_filter(workspace_dir, params["id"])
    deleted = ws.delete_filter(workspace_dir, params["id"])
    if deleted and flt is not None:
        ws.remove_journal_entry(workspace_dir, kind="limit_filter", ref_id=params["id"])
    return {"deleted": deleted}


def op_filter_health(params: dict, ctx: dict) -> Any:
    """§8 / §11.2 evaluate_filter_health for every filter in the workspace,
    plus the count the Notes badge and Flights banner show (§10.4)."""
    engine_cfg, _ = _current_engine(ctx)
    fleet = _get_or_build_fleet(ctx["workspace_dir"])
    health = _filters.evaluate_filter_health(_load_workspace_flights(ctx["workspace_dir"]), fleet,
                                             _workspace_filters(ctx), engine_cfg)
    return {"health": health,
            "attention_count": sum(1 for h in health if h["status"] in ("breached", "drifting"))}


def op_review_filter(params: dict, ctx: dict) -> Any:
    hours = _latest_engine_hours(_load_workspace_flights(ctx["workspace_dir"]))
    flt = ws.review_filter(ctx["workspace_dir"], params["id"], hours)
    if flt is None:
        raise RpcError("NOT_FOUND", f"no filter {params['id']}")
    return flt


def op_rebaseline_filter(params: dict, ctx: dict) -> Any:
    workspace_dir = ctx["workspace_dir"]
    flt = ws.get_filter(workspace_dir, params["id"])
    if flt is None:
        raise RpcError("NOT_FOUND", f"no filter {params['id']}")
    engine_cfg, _ = _current_engine(ctx)
    lim = _target_limits(engine_cfg).get(_filters.target_key(flt))
    if lim is None:
        raise RpcError("NOT_FOUND", f"no target {_filters.target_label(flt['target'])} in this engine profile")
    ref = _filters.select_reference(_get_or_build_fleet(workspace_dir), lim)
    return ws.rebaseline_filter(workspace_dir, params["id"], ref)


def op_copy_filters(params: dict, ctx: dict) -> Any:
    """
    §9 "Copy filters from…": copy another workspace's filters into the
    active one — only between workspaces with the same engine model.
    Copies get new ids and a fresh reference from this workspace's own
    flights; a target this workspace already filters is skipped, not
    overwritten. A copy that doesn't validate here (e.g. a z filter
    without enough reference flights with events) is still copied, and
    reported, so the pilot can fix or remove it. Nothing is automatic.
    """
    _require_active(ctx)
    source_id = params["source_workspace_id"]
    registry = ws.load_registry(ctx["registry_path"])
    source = next((e for e in registry.workspaces if e.id == source_id), None)
    if source is None:
        raise RpcError("NOT_FOUND", f"no workspace {source_id}")
    if source_id == ctx["active_workspace_id"]:
        raise RpcError("BAD_PARAMS", "can't copy filters from a workspace into itself")
    workspace_dir = ctx["workspace_dir"]
    target_model = ws.load_manifest(workspace_dir).engine_model
    source_dir = ctx["workspaces_root"] / source_id
    source_model = ws.load_manifest(source_dir).engine_model
    if source_model != target_model:
        raise RpcError("ENGINE_MISMATCH",
                       f"{source.name} is a {source_model} workspace; this one is {target_model} — "
                       f"filters are only copied between workspaces with the same engine model")

    engine_cfg = load_engine_config(target_model)
    limits = _target_limits(engine_cfg)
    fleet = _get_or_build_fleet(workspace_dir)
    hours = _latest_engine_hours(_load_workspace_flights(workspace_dir))
    already = {_filters.target_key(f) for f in _workspace_filters(ctx)}
    copied, skipped = [], []
    for f in ws.load_filters(source_dir)["filters"]:
        key = _filters.target_key(f)
        if key in already:
            skipped.append({"target": f["target"], "reason": "this workspace already filters this target"})
            continue
        lim = limits.get(key)
        if lim is None:
            skipped.append({"target": f["target"], "reason": "no such limit or alert in this engine profile"})
            continue
        fields = {k: f[k] for k in ("target", "magnitude", "duration", "phases", "note") if f.get(k) is not None}
        fields["copied_from"] = {"workspace_id": source_id, "filter_id": f.get("id")}
        saved = ws.save_filter(workspace_dir, fields, reference_flight_ids=_filters.select_reference(fleet, lim),
                               engine_hours=hours)
        already.add(key)
        diags = _filters.validate_filter(saved, limits, fleet)
        copied.append({"filter": saved, "valid": not diags, "diagnostics": diags})
    return {"copied": copied, "skipped": skipped}


def op_list_annotations(params: dict, ctx: dict) -> Any:
    """All annotations in the active workspace, or just one flight's
    (Spec 03 §5.6 browse view vs. a single Flight view/ECU card's own
    lookup)."""
    flight_id = params.get("flight_id")
    if flight_id:
        return {"annotations": ws.annotations_for_flight(ctx["workspace_dir"], flight_id)}
    return ws.load_annotations(ctx["workspace_dir"])


def op_save_annotation(params: dict, ctx: dict) -> Any:
    workspace_dir = ctx["workspace_dir"]
    saved = ws.save_annotation(
        workspace_dir, params["flight_id"], params["ref"], params["note"],
        annotation_id=params.get("id"),
    )
    ws.upsert_journal_entry(
        workspace_dir, kind="annotation", ref_id=saved["id"], what=saved["note"][:80],
        where={"flight_id": saved["flight_id"], "ref": saved["ref"]},
    )
    return saved


def op_delete_annotation(params: dict, ctx: dict) -> Any:
    workspace_dir = ctx["workspace_dir"]
    deleted = ws.delete_annotation(workspace_dir, params["id"])
    if deleted:
        ws.remove_journal_entry(workspace_dir, kind="annotation", ref_id=params["id"])
    return {"deleted": deleted}


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


def op_delete_workspace(params: dict, ctx: dict) -> Any:
    """
    The confirmation itself ("type DELETE") is a UI-only gate — the RPC
    layer has no separate confirm step, matching every other destructive
    op here (remove_flights, etc.). By the time this call arrives, the
    decision has already been made client-side.
    """
    workspace_id = params["workspace_id"]
    registry = ws.load_registry(ctx["registry_path"])
    if not any(e.id == workspace_id for e in registry.workspaces):
        raise RpcError("NOT_FOUND", f"no workspace {workspace_id}")
    ws.delete_workspace(ctx["registry_path"], ctx["workspaces_root"], workspace_id)

    if ctx.get("active_workspace_id") == workspace_id:
        remaining = ws.load_registry(ctx["registry_path"]).workspaces
        if remaining:
            _activate_workspace(ctx, remaining[0].id)
        else:
            ctx["active_workspace_id"] = None
            ctx["workspace_dir"] = resolve_workspace_dir(None)
            (ctx["workspace_dir"] / "flights").mkdir(parents=True, exist_ok=True)

    return {"deleted": True, "workspace_id": workspace_id}


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


# ── Workspace export and import (Spec 02 v0.11 §7) ──────────────────────────

def _export_dir(ctx: dict) -> Path:
    import tempfile
    d = ctx.get("export_dir")
    if d is None:
        d = Path(tempfile.mkdtemp(prefix="eis-export-"))
        ctx["export_dir"] = d
    return d


def op_export_workspace(params: dict, ctx: dict) -> Any:
    """§7.2: the whole active workspace. The file is written to a private
    temporary folder and served once from /download/<token>, so the
    browser saves it like any download."""
    import uuid as _uuid
    from . import workspace_export as wx
    _require_active(ctx)
    token = _uuid.uuid4().hex
    out = _export_dir(ctx) / token
    try:
        result = wx.export_workspace(ctx["workspace_dir"], out, include_logs=bool(params.get("include_logs", True)),
                                     anonymise=bool(params.get("anonymise", False)))
    except wx.ExportError as e:
        raise RpcError("EXPORT_FAILED", str(e))
    ctx.setdefault("downloads", {})[token] = result.path
    d = result.to_dict()
    d.pop("path")
    return {**d, "download_url": f"/download/{token}", "size": result.path.stat().st_size}


def op_preview_workspace_export(params: dict, ctx: dict) -> Any:
    """Before Export (Spec 02 v0.12): where the tail number or system ID
    appears in the sender's own text, which anonymising leaves as written."""
    from . import workspace_export as wx
    _require_active(ctx)
    return {"identity_mentions": wx.identity_mentions(ctx["workspace_dir"])}


def _export_contents(params: dict, ctx: dict):
    """An export chosen in the import flow: a path (a file, or an unzipped
    export folder) or an uploaded .eisworkspace."""
    from . import workspace_export as wx
    if params.get("path"):
        return wx.read_export(Path(str(params["path"])).expanduser())
    if params.get("content_base64"):
        import base64 as _b64
        f = _export_dir(ctx) / f"upload-{uuid.uuid4().hex}{wx.EXPORT_SUFFIX}"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(_b64.b64decode(params["content_base64"]))
        return wx.read_export(f)
    raise RpcError("BAD_PARAMS", "choose an export file or an unzipped export folder")


def op_inspect_workspace_export(params: dict, ctx: dict) -> Any:
    """§7.4 step 1: the summary, and the engine check, before anything is created."""
    from . import workspace_export as wx
    try:
        return wx.summarize(_export_contents(params, ctx))
    except wx.ImportRefused as e:
        raise RpcError("IMPORT_REFUSED", str(e))


def op_import_workspace(params: dict, ctx: dict) -> Any:
    """§7.4 steps 2–3: a new workspace (never a merge), switched to; an
    export folder's logs/ is linked."""
    from . import workspace_export as wx
    try:
        contents = _export_contents(params, ctx)
        manifest = wx.import_workspace(ctx["registry_path"], ctx["workspaces_root"], contents, name=params.get("name"))
    except wx.ImportRefused as e:
        raise RpcError("IMPORT_REFUSED", str(e))
    except ValueError as e:
        raise RpcError("BAD_PARAMS", str(e))
    _activate_workspace(ctx, manifest.id)
    return {"manifest": manifest.to_dict(), "logs_linked": bool(manifest.log_folders)}


def op_match_import(params: dict, ctx: dict) -> Any:
    """§7.4 step 4: the folders against the sender's manifest, without analysing."""
    from . import workspace_export as wx
    _require_active(ctx)
    try:
        return wx.match_import(ctx["workspace_dir"])
    except ValueError as e:
        raise RpcError("NOT_IMPORTED", str(e))


def op_get_import_info(params: dict, ctx: dict) -> Any:
    """For an imported workspace: the sender's provenance and its flight
    list (the empty state, §7.4 step 3). {imported: false} otherwise."""
    from . import workspace_export as wx
    if not ctx.get("active_workspace_id"):
        return {"imported": False}
    record = wx.load_import_record(ctx["workspace_dir"])
    if record is None:
        return {"imported": False}
    present = set(ws.list_flight_ids(ctx["workspace_dir"]))
    return {"imported": True, "provenance": record.get("provenance", {}),
            "flights": [{"flight_id": f["flight_id"], "date": f.get("date"), "airport_hint": f.get("airport_hint"),
                         "duration_min": f.get("duration_min"),
                         "sender_filename": next((x.get("filename") for x in f.get("sources", [])), None),
                         "found": f["flight_id"] in present}
                        for f in record.get("manifest", [])]}


def op_add_log_folder(params: dict, ctx: dict) -> Any:
    _require_active(ctx)
    manifest = ws.add_log_folder(ctx["workspace_dir"], params["path"], ctx["registry_path"])
    return manifest.to_dict()


def op_scan_workspace(params: dict, ctx: dict) -> Any:
    """Finds new/missing/moved files AND re-analyzes any already-known
    flight whose stored analysis predates the running engine — one
    action covers both jobs (Spec 03 §5.1's Rescan), so the fleet only
    needs rebuilding here, once, when reanalysis actually changed a
    flight's metrics.

    Runs synchronously (unchanged contract — the caller still just gets
    the final ScanResult back) but publishes progress into
    ctx["scan_progress"] as it goes, so a client that also polls
    op_get_scan_progress from a second request while this one is still
    in flight can show real "processing log X of N" instead of one
    opaque multi-minute spinner on a large initial sync.
    """
    _require_active(ctx)
    workspace_dir = ctx["workspace_dir"]

    def on_progress(update: dict) -> None:
        ctx["scan_progress"] = {"active": True, **update}

    # Spec 03 v0.17 §5.1: Sync discovers first and asks before analysing.
    # analyze: false — discovery only (moved/missing/recovered bookkeeping,
    # nothing parsed or analysed; what's waiting comes back as pending_*).
    # source_keys / flight_ids — analyse just those new logs / stale
    # flights (a row's "Analyze this flight"). Omitted: everything, as before.
    analyze = params.get("analyze", True)
    new_keys = set() if not analyze else (set(params["source_keys"]) if params.get("source_keys") is not None else None)
    reanalyze_ids = set() if not analyze else (set(params["flight_ids"]) if params.get("flight_ids") is not None else None)

    ctx["scan_progress"] = {"active": True, "phase": "starting"}
    try:
        result = ws.scan_workspace(workspace_dir, ctx["registry_path"], on_progress=on_progress,
                                   new_keys=new_keys, reanalyze_ids=reanalyze_ids)
    finally:
        ctx["scan_progress"] = {"active": False}
    if result.reanalyzed_flight_ids or result.new_flight_ids:
        ws.rebuild_fleet(workspace_dir)
    return result.to_dict()


def op_get_scan_progress(params: dict, ctx: dict) -> Any:
    return ctx.get("scan_progress", {"active": False})


def op_reclassify_flights(params: dict, ctx: dict) -> Any:
    """
    One-time migration action for a workspace scanned before
    scan_workspace() gained ground-session/short-flight/corrupt-log
    filtering (workspace.reclassify_existing_flights's docstring has the
    full rationale) — not part of the regular Sync flow, a separate,
    explicitly-triggered op.
    """
    _require_active(ctx)
    workspace_dir = ctx["workspace_dir"]
    reclassified = ws.reclassify_existing_flights(workspace_dir)
    if reclassified:
        ws.rebuild_fleet(workspace_dir)
    return {"reclassified": reclassified}


# ── Data location (Spec 02 v0.10 §5.8.1, Spec 14 v0.12 §5.2) ─────────────────

def op_get_data_location(params: dict, ctx: dict) -> Any:
    loc = data_location.resolve()
    default = data_location.default_root()
    count = None
    if not loc.missing:
        try:
            count = data_location.workspace_count(loc.root)
        except (OSError, ValueError):
            count = None
    return {**loc.to_dict(), "workspace_count": count, "default_path": str(default),
            "env_var": data_location.ENV_VAR}


def _location_target(params: dict) -> Path:
    if params.get("default"):
        return data_location.default_root()
    return Path(str(params.get("path") or ""))


def op_assess_data_location(params: dict, ctx: dict) -> Any:
    """What choosing a folder would do, without doing it (§5.8.1 table)."""
    return data_location.assess(_location_target(params))


def op_change_data_location(params: dict, ctx: dict) -> Any:
    """Move the data root, or switch to one that already holds data, then
    reopen the app on it. Refused while a scan runs."""
    if ctx.get("scan_progress", {}).get("active"):
        raise RpcError("BUSY", "A sync is running. Change the data location when it has finished.")
    if ctx.get("location_progress", {}).get("active"):
        raise RpcError("BUSY", "The data location is already being changed.")

    def on_progress(update: dict) -> None:
        ctx["location_progress"] = {"active": True, **update}

    ctx["location_progress"] = {"active": True, "phase": "starting"}
    try:
        result = data_location.change(_location_target(params), on_progress=on_progress)
    except data_location.DataLocationError as e:
        raise RpcError(e.code, e.message)
    finally:
        ctx["location_progress"] = {"active": False}
    _open_data_root(ctx)
    return {**result, "location": op_get_data_location({}, ctx)}


def op_get_data_location_progress(params: dict, ctx: dict) -> Any:
    return ctx.get("location_progress", {"active": False})


def op_retry_data_location(params: dict, ctx: dict) -> Any:
    """*Try again* on the missing-location notice."""
    _open_data_root(ctx)
    return op_get_data_location({}, ctx)


# Ops the app may call while the data location is missing or being moved.
_LOCATION_OPS = {"get_data_location", "assess_data_location", "change_data_location",
                 "get_data_location_progress", "retry_data_location"}


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


def op_get_topic_help(params: dict, ctx: dict) -> Any:
    """Spec 01 §8.8. Fetched once per engine profile and rule set and
    cached client-side (Spec 03 §5.2) — not a per-flight call."""
    engine_cfg, engine_name = _current_engine(ctx)
    rules = _resolve_rules(ctx) if ctx.get("active_workspace_id") else _default_rules()
    results, diagnostics = get_topic_help(
        params.get("topic_ids"), engine_name, engine_cfg, rules, params.get("baseline_config"),
    )
    return {"topics": [r.to_dict() for r in results], "diagnostics": diagnostics}


def op_get_aircraft_summary(params: dict, ctx: dict) -> Any:
    """
    Spec 02 v0.8 §5.6/§6.6: the distinct aircraft_ident values across
    admitted flights (Tier 2 — baseline membership, the scope that
    actually gets blended), grouped by the pilot's aircraft_aliases.
    `idents` is the canonical (post-alias) list the notice counts;
    `raw_idents` is pre-alias, for the "ungroup" UI to show what each
    group actually contains.
    """
    _require_active(ctx)
    settings = ws.load_workspace_settings(ctx["workspace_dir"])
    selection = ws.load_selection(ctx["workspace_dir"])
    excluded_ids = {e["flight_id"] for e in selection.excluded}
    all_fas = _load_workspace_flights(ctx["workspace_dir"])
    included = [fa for fa in all_fas if fa.flight_id not in excluded_ids]

    raw_idents = sorted({
        fa.header.get("aircraft", {}).get("ident")
        for fa in included
        if fa.header.get("aircraft", {}).get("ident")
    })
    alias_of: dict[str, str] = {}
    for group in settings.aircraft_aliases:
        canonical = group[0]
        for ident in group:
            alias_of[ident] = canonical
    canonical_idents = sorted({alias_of.get(i, i) for i in raw_idents})

    return {
        "idents": canonical_idents,
        "raw_idents": raw_idents,
        "aliases": settings.aircraft_aliases,
    }


def op_get_workspace_settings(params: dict, ctx: dict) -> Any:
    return ws.load_workspace_settings(ctx["workspace_dir"]).to_dict()


def op_get_journal(params: dict, ctx: dict) -> Any:
    """Spec 14 v0.10 §6: the register of decisions in force, each with its
    live counted effect (recomputed now, from the current analyses, by the
    same code the decision's own preview uses), its current values, and
    any change notice. Reconciles the register with the stores first."""
    _require_active(ctx)
    workspace_dir = ctx["workspace_dir"]
    rules = _resolve_rules(ctx)
    ws.reconcile_journal(workspace_dir, active_rules=rules, shipped_rules=_default_rules())
    live = _JournalEffects(ctx, rules)
    engine_cfg, _ = _current_engine(ctx)
    labels = {k: lim.get("label") for k, lim in _target_limits(engine_cfg).items()}
    entries = [{**e, **live.describe(e)} for e in
               (_journal_display(workspace_dir, e, labels) for e in ws.load_journal(workspace_dir)["entries"])]
    return {"entries": sorted(entries, key=lambda e: e["updated_at"], reverse=True)}


def op_confirm_journal_notice(params: dict, ctx: dict) -> Any:
    """Keep a decision whose change notice says it no longer does anything
    (Spec 14 §6.2); the notice clears until the decision is edited."""
    entry = ws.confirm_journal_notice(ctx["workspace_dir"], params["entry_id"], params["notice"])
    if entry is None:
        raise RpcError("NOT_FOUND", f"no journal entry {params['entry_id']}")
    return entry


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


class _JournalEffects:
    """Live counted effects for Journal entries (Spec 14 v0.10 §6.1), each
    from the computation the decision's own preview already uses:
    filters — filters.preview_limit_filter; exclusions — the reference-
    membership preview (_other_flights_whose_verdict_changes); rule edits
    and disabled topics — the what-if evaluation (evaluate_insights with
    the candidate rules, compared per topic). Evaluations are cached for
    the one request."""

    def __init__(self, ctx: dict, rules: dict):
        self.ctx = ctx
        self.workspace_dir = ctx["workspace_dir"]
        self.rules = rules
        self._flights = None
        self._fleet = None
        self._filters = None
        self._current: dict = {}
        self._health = None

    @property
    def flights(self):
        if self._flights is None:
            self._flights = _load_workspace_flights(self.workspace_dir)
        return self._flights

    @property
    def fleet(self):
        if self._fleet is None:
            self._fleet = _get_or_build_fleet(self.workspace_dir)
        return self._fleet

    @property
    def filters(self):
        if self._filters is None:
            self._filters = _workspace_filters(self.ctx)
        return self._filters

    def _topic_insights(self, fa, rules: dict, topic_id: str, cache: bool) -> list:
        if cache and fa.flight_id in self._current:
            iset = self._current[fa.flight_id]
        else:
            iset = evaluate_insights(fa, self.fleet, rules, filters=self.filters).to_dict()
            if cache:
                self._current[fa.flight_id] = iset
        t = next((t for t in iset["topics"] if t["topic_id"] == topic_id), None)
        return sorted((i["rule_id"], i["severity"]) for i in (t["insights"] if t else []))

    def _health_by_id(self) -> dict:
        if self._health is None:
            engine_cfg, _ = _current_engine(self.ctx)
            self._health = {h["filter_id"]: h for h in
                            _filters.evaluate_filter_health(self.flights, self.fleet, self.filters, engine_cfg)}
        return self._health

    def describe(self, e: dict) -> dict:
        try:
            effect, current, notices = getattr(self, f"_{e['kind']}", self._none)(e)
        except Exception as exc:  # a broken store must not take the page down
            effect, current, notices = {"text": f"couldn't compute the effect ({exc})", "zero": False}, None, []
        if effect and effect["zero"] and "no_effect" not in (e.get("confirmed") or {}):
            notices = notices + [{"kind": "no_effect", "text": _NO_EFFECT_NOTICE.get(e["kind"], "This decision currently has no effect.")}]
        return {"effect": effect, "current": current, "notices": notices}

    def _none(self, e):
        return None, None, []

    def _limit_filter(self, e):
        f = next((f for f in self.filters if f["id"] == e["ref_id"]), None)
        if f is None:
            return None, None, []
        others = [x for x in self.filters if x["id"] != f["id"]]
        p = _filters.preview_limit_filter(self.flights, self.fleet, self.rules, others, f)
        n, m = p["events_hidden"], p["flights_affected"]
        effect = ({"text": f"suppressing {_plural(n, 'event')} on {_plural(m, 'flight')}", "zero": False} if n
                  else {"text": "currently suppresses nothing", "zero": True})
        engine_cfg, _ = _current_engine(self.ctx)
        lim = _target_limits(engine_cfg).get(_filters.target_key(f))
        current = _filters.band_text(f, lim) if lim else None
        h = self._health_by_id().get(f["id"])
        notices = ([{"kind": h["status"], "text": (h.get("reasons") or [""])[0]}]
                   if h and h["status"] in ("breached", "drifting") else [])
        return effect, current, notices

    def _disabled_topic(self, e):
        topic_id = e["ref_id"]
        on = {**self.rules, "rules": {**self.rules["rules"], topic_id: {**self.rules["rules"][topic_id], "enabled": True}}}
        counts = [len(self._topic_insights(fa, on, topic_id, cache=False)) for fa in self.flights]
        n, m = sum(counts), sum(1 for c in counts if c)
        effect = ({"text": f"removing {_plural(n, 'insight')} on {_plural(m, 'flight')}", "zero": False} if n
                  else {"text": "currently removes nothing", "zero": True})
        return effect, "off (shipped: on)", []

    def _rule_edit(self, e):
        topic_id = e["ref_id"]
        current = self.rules["rules"].get(topic_id, {})
        shipped = _default_rules()["rules"].get(topic_id, {})
        if not current.get("enabled", True):
            return {"text": "topic is off — see its disabled entry", "zero": False}, _rule_diff_text(current, shipped), []
        cand = {**self.rules, "rules": {**self.rules["rules"], topic_id: {**shipped, "enabled": True}}}
        added = removed = fa_add = fa_rem = 0
        for fa in self.flights:
            now = self._topic_insights(fa, self.rules, topic_id, cache=True)
            base = self._topic_insights(fa, cand, topic_id, cache=False)
            a = len([x for x in now if x not in base])
            r = len([x for x in base if x not in now])
            added, removed = added + a, removed + r
            fa_add, fa_rem = fa_add + bool(a), fa_rem + bool(r)
        parts = []
        if added:
            parts.append(f"adds {_plural(added, 'insight')} on {_plural(fa_add, 'flight')}")
        if removed:
            parts.append(f"removes {_plural(removed, 'insight')} on {_plural(fa_rem, 'flight')}")
        effect = ({"text": "; ".join(parts) + " compared with shipped", "zero": False} if parts
                  else {"text": "currently changes nothing compared with shipped", "zero": True})
        return effect, _rule_diff_text(current, shipped), []

    def _exclusion(self, e):
        fid = e["ref_id"]
        excluded = ws.load_selection(self.workspace_dir).excluded
        without = [x for x in excluded if x["flight_id"] != fid]
        proposed = ws.fleet_for_exclusions(self.workspace_dir, without)
        changed = _other_flights_whose_verdict_changes(self.workspace_dir, fid, self.fleet, proposed, self.rules, self.filters)
        n = len(changed)
        effect = ({"text": f"changes {_plural(n, 'verdict')} on other flights", "zero": False} if n
                  else {"text": "currently changes no other flight's verdict", "zero": True})
        return effect, None, []

    def _all_insights(self, fa, fleet, cache: bool) -> list:
        """Every insight on the flight, as (topic, rule, severity)."""
        if cache and fa.flight_id in self._current:
            iset = self._current[fa.flight_id]
        else:
            iset = evaluate_insights(fa, fleet, self.rules, filters=self.filters).to_dict()
            if cache:
                self._current[fa.flight_id] = iset
        return sorted((t["topic_id"], i["rule_id"], i["severity"]) for t in iset["topics"] for i in t["insights"])

    def _changed_setting(self, e):
        """Spec 14 v0.13: the setting against shipped — the fleet rebuilt
        with only this setting back at shipped, every flight's insights
        compared, and the Trends change summary compared."""
        selection = ws.load_selection(self.workspace_dir)
        d = next((d for d in ws.setting_decisions(selection.baseline_config) if d["ref_id"] == e["ref_id"]), None)
        if d is None:
            return None, None, []
        shipped_cfg = ws.baseline_config_with_setting_reset(selection.baseline_config, e["ref_id"])
        shipped_fleet = ws.fleet_for_exclusions(self.workspace_dir, selection.excluded, baseline_config=shipped_cfg)
        added = removed = fa_add = fa_rem = 0
        for fa in self.flights:
            now = self._all_insights(fa, self.fleet, cache=True)
            base = self._all_insights(fa, shipped_fleet, cache=False)
            a = len([x for x in now if x not in base])
            r = len([x for x in base if x not in now])
            added, removed = added + a, removed + r
            fa_add, fa_rem = fa_add + bool(a), fa_rem + bool(r)
        listed = {c["metric_id"] for c in self.fleet.change_summary}
        listed_shipped = {c["metric_id"] for c in shipped_fleet.change_summary}
        trends = len(listed ^ listed_shipped)
        parts = []
        if added:
            parts.append(f"adds {_plural(added, 'insight')} on {_plural(fa_add, 'flight')}")
        if removed:
            parts.append(f"removes {_plural(removed, 'insight')} on {_plural(fa_rem, 'flight')}")
        if trends:
            parts.append(f"changes {_plural(trends, 'metric')} in the Trends change list")
        effect = ({"text": "; ".join(parts) + " compared with shipped", "zero": False} if parts
                  else {"text": "currently changes nothing compared with shipped", "zero": True})
        return effect, _setting_text(d), []

    def _reference_pin(self, e):
        pinned = (ws.load_selection(self.workspace_dir).baseline_config or {}).get("pinned_references") or {}
        ref = pinned.get(e["ref_id"])
        if ref is None:
            return None, None, []
        n = len(ref.get("flight_ids", []))
        when = (ref.get("set_at") or "")[:10]
        return ({"text": f"reference of {_plural(n, 'flight')}" + (f", pinned {when}" if when else ""), "zero": False},
                ref.get("label"), [])


_NO_EFFECT_NOTICE = {
    "limit_filter": "This filter currently hides nothing.",
    "exclusion": "This exclusion no longer changes any other flight's verdict.",
    "rule_edit": "This rule edit currently changes nothing compared with shipped.",
    "disabled_topic": "This topic would raise nothing even if it were on.",
    "changed_setting": "This setting currently changes nothing compared with shipped.",
}


def _rule_diff_text(current: dict, shipped: dict) -> Optional[str]:
    """The rule now against the shipped default, field by field:
    "trend.r2_min 0.3 (shipped 0.5)"."""
    parts = []
    current, shipped = ws.strip_rule_comments(current), ws.strip_rule_comments(shipped)
    ct, st = current.get("triggers") or [], shipped.get("triggers") or []
    if len(ct) != len(st):
        parts.append(f"{len(ct)} trigger(s) (shipped {len(st)})")
    for c, b in zip(ct, st):
        for k in sorted(set(c) | set(b)):
            if k != "type" and c.get(k) != b.get(k):
                parts.append(f"{c.get('type')}.{k} {c.get(k)} (shipped {b.get(k)})")
    for k in sorted(set(current) | set(shipped)):
        if k not in ("triggers", "enabled") and not k.startswith("_") and current.get(k) != shipped.get(k):
            parts.append(f"{k} {current.get(k)} (shipped {shipped.get(k)})")
    return ", ".join(parts) or None


def _journal_display(workspace_dir: Path, entry: dict, limit_labels: Optional[dict] = None) -> dict:
    """Titles computed on read, so entries written by older code read the
    same as new ones: an exclusion by its log's current file name (not the
    flight id, and not a name stored when the entry was made — after an
    import or a rename that is another machine's or an old name), a filter
    by its limit's label (not the limit id). A flight not in the workspace
    (a dormant decision) keeps its stored label."""
    if entry.get("kind") == "exclusion":
        name = _source_filename(workspace_dir, entry["ref_id"])
        if name:
            return {**entry, "what": name}
    if entry.get("kind") == "limit_filter" and limit_labels is not None:
        # Entries written before Spec 09 v0.18 say where with a bare limit_id.
        target = _filters.migrate_filter(dict(entry.get("where") or {})).get("target")
        if target:
            label = limit_labels.get(_filters.target_key({"target": target}))
            return {**entry, "what": f"Filter: {_filters.target_label(target, label)}", "where": {"target": target}}
    return entry


def op_save_workspace_settings(params: dict, ctx: dict) -> Any:
    settings = ws.WorkspaceSettings.from_dict(params["settings"])
    ws.save_workspace_settings(ctx["workspace_dir"], settings)
    return settings.to_dict()


_OPS: dict[str, Callable[[dict, dict], Any]] = {
    "get_data_location": op_get_data_location,
    "assess_data_location": op_assess_data_location,
    "change_data_location": op_change_data_location,
    "get_data_location_progress": op_get_data_location_progress,
    "retry_data_location": op_retry_data_location,
    "get_default_rules": op_get_default_rules,
    "get_workspace_rules": op_get_workspace_rules,
    "save_workspace_rules": op_save_workspace_rules,
    "reset_workspace_rules": op_reset_workspace_rules,
    "apply_card_rule_edit": op_apply_card_rule_edit,
    "revert_rule_edit": op_revert_rule_edit,
    "save_baseline_config": op_save_baseline_config,
    "what_if_rules": op_what_if_rules,
    "list_engines": op_list_engines,
    "get_engine_limits": op_get_engine_limits,
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
    "get_trends_panels": op_get_trends_panels,
    "get_flight_series": op_get_flight_series,
    "rebuild_fleet": op_rebuild_fleet,
    "import_files": op_import_files,
    "list_flights_with_status": op_list_flights_with_status,
    "exclude_flight": op_exclude_flight,
    "include_flight": op_include_flight,
    "set_reference": op_set_reference,
    "clear_reference": op_clear_reference,
    "preview_clear_reference": op_preview_clear_reference,
    "delete_shift_event": op_delete_shift_event,
    "list_exclusions": op_list_exclusions,
    "include_excluded_log": op_include_excluded_log,
    "preview_excluded_log": op_preview_excluded_log,
    "preview_reference_membership": op_preview_reference_membership,
    "get_excluded_log_series": op_get_excluded_log_series,
    "list_annotations": op_list_annotations,
    "list_filters": op_list_filters,
    "propose_filter": op_propose_filter,
    "preview_filter": op_preview_filter,
    "save_filter": op_save_filter,
    "delete_filter": op_delete_filter,
    "filter_health": op_filter_health,
    "review_filter": op_review_filter,
    "rebaseline_filter": op_rebaseline_filter,
    "copy_filters": op_copy_filters,
    "save_annotation": op_save_annotation,
    "delete_annotation": op_delete_annotation,
    "remove_missing_flight": op_remove_missing_flight,
    "remove_flight": op_remove_flight,
    "remove_flights": op_remove_flights,
    "list_workspaces": op_list_workspaces,
    "create_workspace": op_create_workspace,
    "switch_workspace": op_switch_workspace,
    "delete_workspace": op_delete_workspace,
    "get_active_workspace": op_get_active_workspace,
    "add_log_folder": op_add_log_folder,
    "scan_workspace": op_scan_workspace,
    "get_scan_progress": op_get_scan_progress,
    "reclassify_flights": op_reclassify_flights,
    "get_app_settings": op_get_app_settings,
    "save_app_settings": op_save_app_settings,
    "get_chart_presets": op_get_chart_presets,
    "save_user_preset": op_save_user_preset,
    "delete_user_preset": op_delete_user_preset,
    "reorder_user_presets": op_reorder_user_presets,
    "get_workspace_settings": op_get_workspace_settings,
    "save_workspace_settings": op_save_workspace_settings,
    "list_changed_settings": op_list_changed_settings,
    "export_workspace": op_export_workspace,
    "preview_workspace_export": op_preview_workspace_export,
    "inspect_workspace_export": op_inspect_workspace_export,
    "import_workspace": op_import_workspace,
    "match_import": op_match_import,
    "get_import_info": op_get_import_info,
    "reset_setting": op_reset_setting,
    "get_journal": op_get_journal,
    "confirm_journal_notice": op_confirm_journal_notice,
    "update_exclusion_reason": op_update_exclusion_reason,
    "get_topic_help": op_get_topic_help,
    "get_aircraft_summary": op_get_aircraft_summary,
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
                if op not in _LOCATION_OPS:
                    if ctx.get("data_location_missing"):
                        raise RpcError("DATA_LOCATION_MISSING",
                                       f"The data location {ctx['data_location_missing']} can't be reached.")
                    if ctx.get("location_progress", {}).get("active"):
                        raise RpcError("BUSY", "Your data is being moved; try again when it has finished.")
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
            if self.path.startswith("/download/"):
                # A workspace export (Spec 02 §7.2), served once.
                token = self.path[len("/download/"):].split("?")[0]
                f = ctx.get("downloads", {}).pop(token, None)
                if f is None or not Path(f).is_file():
                    self.send_response(404)
                    self._cors()
                    self.end_headers()
                    return
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", f'attachment; filename="{Path(f).name}"')
                self.send_header("Content-Length", str(Path(f).stat().st_size))
                self.end_headers()
                with open(f, "rb") as fh:
                    shutil.copyfileobj(fh, self.wfile)
                return
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


def _open_data_root(ctx: dict, workspace_arg: Optional[str] = None) -> None:
    """
    Point ctx at the data root (Spec 02 v0.10 §5.8.1) and its active
    workspace — at startup, after a change of location, and on *Try
    again*. A chosen location that can't be reached leaves ctx marked
    `data_location_missing`; every op but the data-location ones is then
    refused (the UI shows its notice), and nothing is written anywhere.
    """
    loc = data_location.resolve()
    ctx["registry_path"] = loc.root / "registry.json"
    ctx["workspaces_root"] = loc.root / "workspaces"
    if loc.missing:
        ctx["data_location_missing"] = str(loc.root)
        ctx["workspace_dir"], ctx["active_workspace_id"] = loc.root, None
        return
    ctx.pop("data_location_missing", None)
    ctx["workspace_dir"], ctx["active_workspace_id"] = _resolve_active_workspace(
        workspace_arg, ctx["registry_path"], ctx["workspaces_root"])
    (ctx["workspace_dir"] / "flights").mkdir(parents=True, exist_ok=True)


def build_server(logs_dir: Optional[str], workspace_dir: Optional[str], port: int, quiet: bool) -> ThreadingHTTPServer:
    """
    Construct (but don't run) the server — split out from run_server() so
    tests can start it in a background thread and call .shutdown()
    cleanly, instead of blocking forever on serve_forever() in-process.
    """
    resolved_logs = resolve_logs_dir(logs_dir)
    ctx = {
        "logs_dir": resolved_logs, "quiet": quiet,
        # Mutated in place by op_scan_workspace's on_progress callback and
        # read back by op_get_scan_progress — ctx is one shared dict for
        # this server process's lifetime (built once here, closed over by
        # every request handler), so a poll running on another thread
        # sees updates from the scan thread with no extra plumbing.
        "scan_progress": {"active": False},
        # Spec 02 v0.10 §5.8.1: a move of the data root in progress.
        "location_progress": {"active": False},
    }
    _open_data_root(ctx, workspace_dir)
    resolved_workspace = ctx["workspace_dir"]

    ui_dist = _REPO_ROOT / "web" / "dist"
    ui_dist = ui_dist if ui_dist.is_dir() else None

    handler = _make_handler(ctx, ui_dist)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.slingology_workspace_dir = resolved_workspace  # type: ignore[attr-defined]
    httpd.slingology_data_location_missing = ctx.get("data_location_missing")  # type: ignore[attr-defined]
    return httpd


def run_server(logs_dir: Optional[str], workspace_dir: Optional[str], port: int, quiet: bool) -> None:
    httpd = build_server(logs_dir, workspace_dir, port, quiet)
    if not quiet:
        print(f"SlingologyEIS local server: http://127.0.0.1:{httpd.server_port}/  "
              f"(workspace: {httpd.slingology_workspace_dir})", file=sys.stderr)  # type: ignore[attr-defined]
        print("POST /rpc for the API. Ctrl-C to stop.", file=sys.stderr)
        if httpd.slingology_data_location_missing:  # type: ignore[attr-defined]
            print(f"Data location {httpd.slingology_data_location_missing} can't be reached; "  # type: ignore[attr-defined]
                  "the app will ask you to reconnect it or choose another.", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
