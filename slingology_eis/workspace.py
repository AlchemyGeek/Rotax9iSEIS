"""
workspace.py — the workspace model (Spec 02 v0.5 §5-6).

A workspace is a list of log folders (referenced, never copied — D9)
plus everything derived from what's currently in them. This module is
the host-level layer that sits above the stateless engine (operations.py):
it owns the registry of workspaces, each workspace's manifest, per-flight
provenance (FlightSources), the one real in-app selection (FleetSelection's
`excluded` list), and the app/workspace settings split.

Three things this module is deliberately strict about, because they were
corrected after review and are easy to reintroduce by accident:

1. Membership is never stored. `flights/` on disk (or in this module's
   in-memory view of it) *is* the membership — whatever a scan of
   `manifest.log_folders` currently finds. There is no `included: [...]`
   list anywhere (§5.1, §6.3).
2. `engine_model` is a workspace-level constant, set once at creation,
   applied unconditionally to every log scanned into the workspace. It
   is never read from a log and never checked against one — the log
   data doesn't carry engine-variant information (§5.6; verified against
   limits.py's engine-selection precedence: explicit arg -> env var ->
   config.json -> default, never a log field).
3. A different `aircraft_ident` among a workspace's flights is informational
   only (`FlightSources.different_tail_number`) — it never excludes a
   flight, never blocks a scan, never needs confirmation (§5.6).

Fingerprint = Spec 01's `source_key` (content hash of the file bytes),
reused as-is (§5.7) — there is no second hash. Rescanning re-matches a
moved/renamed file by looking its fingerprint up among a workspace's
already-known imports, not by comparing paths.
"""
from __future__ import annotations

import json
import shutil
import threading
import uuid
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from . import __version__
from . import data_location as _data_location
from . import exclusions as _exclusions
from . import serialize as _json_serialize
from .filters import target_label
from .limits import RETIRED_ENGINES, load_engine_config, resolve_min_flight_duration_min
from .log_sources import DISK, LogEntry, LogRef, LogSource, LogUnavailable, areading, reading, run_now
from .loader import (
    find_duplicate_flights,
    flight_fingerprint,
    flight_id as _compute_flight_id,
    load_log_bytes,
    source_key as _source_key,
)
from .phases import detect_phases
from .operations import (
    DEFAULT_BASELINE_CONFIG, FlightAnalysis, FleetAnalysis, analyze_flight, full_coverage_counterpart, update_fleet,
)

SCHEMA_VERSION = "02-v0.5"

ENGINE_MODELS = ("912iS", "915iS", "916iS")


def check_engine_model(engine_model: str, workspace_name: str = "") -> None:
    """Fail with a clear message for an engine model with no profile —
    never fall through to another engine's limits (§5.6). A retired one
    (914iS) says why it was withdrawn."""
    if engine_model in ENGINE_MODELS:
        return
    who = f"Workspace {workspace_name!r} uses" if workspace_name else "Engine model"
    reason = RETIRED_ENGINES.get(engine_model) or f"expected one of {', '.join(ENGINE_MODELS)}."
    raise ValueError(f"{who} engine model {engine_model!r}, which has no engine profile. {reason}")

_SOURCE_FORMAT_TO_VIA = {
    "g3x_direct": "sd_card",
    "garmin_pilot": "garmin_pilot",
    "axis": "axis",
    "unknown": "unknown",
}


def via_for_source_format(source_format: Optional[str]) -> str:
    """ImportRecord.via for a loader source_format ("unknown" if none)."""
    return _SOURCE_FORMAT_TO_VIA.get(source_format or "", "unknown")


_REPO_ROOT = Path(__file__).resolve().parent.parent


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_serialize.dumps(obj, indent=2))


# ── Path resolution (Spec 02 §5.8) ───────────────────────────────────────────
# Same three-context precedence as Spec 01 §7.1's --logs/--workspace (packaged
# install, else a git checkout, else a usage error) — except workspace
# *creation* always has a sensible default to write into (a first run has
# nothing on disk yet by definition), so this never raises the way
# cli.resolve_logs_dir/resolve_workspace_dir do for data expected to already
# exist. Docker (Spec 02 §5.8's third context) is "whatever is mounted" —
# there is no Docker-specific code anywhere else in this repo either, so this
# doesn't add one; a Docker deployment mounts something at the packaged
# home's path, or sets SLINGOLOGY_EIS_HOME (data_location.py, §5.8.1).

def resolve_registry_path() -> Path:
    """registry.json — alongside workspaces/, never inside any one workspace.
    At the data root (Spec 02 v0.10 §5.8.1): the environment, the pilot's
    chosen location, else the defaults above. Raises
    data_location.DataLocationMissing for a chosen location that can't be
    reached."""
    return _data_location.data_root() / "registry.json"


def resolve_workspaces_root() -> Path:
    return resolve_registry_path().parent / "workspaces"


# ── Document shapes (Spec 02 §5.2, §6) ───────────────────────────────────────

@dataclass
class WorkspaceRegistryEntry:
    id: str
    name: str
    engine_model: str
    primary_tail_number: Optional[str] = None
    created_at: str = ""
    last_opened_at: str = ""
    log_folder_count: int = 0
    flight_count: int = 0

    def to_dict(self) -> dict:
        d = {
            "id": self.id, "name": self.name, "engine_model": self.engine_model,
            "created_at": self.created_at, "last_opened_at": self.last_opened_at,
            "log_folder_count": self.log_folder_count, "flight_count": self.flight_count,
        }
        if self.primary_tail_number is not None:
            d["primary_tail_number"] = self.primary_tail_number
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "WorkspaceRegistryEntry":
        return cls(
            id=d["id"], name=d["name"], engine_model=d["engine_model"],
            primary_tail_number=d.get("primary_tail_number"),
            created_at=d.get("created_at", ""), last_opened_at=d.get("last_opened_at", ""),
            log_folder_count=d.get("log_folder_count", 0), flight_count=d.get("flight_count", 0),
        )


@dataclass
class WorkspaceRegistry:
    workspaces: list[WorkspaceRegistryEntry] = field(default_factory=list)
    version: str = "1"

    def to_dict(self) -> dict:
        return {"version": self.version, "workspaces": [w.to_dict() for w in self.workspaces]}

    @classmethod
    def from_dict(cls, d: dict) -> "WorkspaceRegistry":
        return cls(
            version=d.get("version", "1"),
            workspaces=[WorkspaceRegistryEntry.from_dict(w) for w in d.get("workspaces", [])],
        )


@dataclass
class LogFolder:
    path: str                         # a real path, or (for a page-held folder) its display name
    reachable: bool = True
    last_scanned_at: Optional[str] = None
    # Spec 02 §6.1: the stable key of a folder the host can't reach by path
    # (a browser's directory handle lives outside the manifest, keyed by
    # this). Absent for folders added by path.
    folder_id: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"path": self.path, "reachable": self.reachable}
        if self.last_scanned_at is not None:
            d["last_scanned_at"] = self.last_scanned_at
        if self.folder_id is not None:
            d = {"folder_id": self.folder_id, **d}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "LogFolder":
        return cls(path=d["path"], reachable=d.get("reachable", True), last_scanned_at=d.get("last_scanned_at"),
                   folder_id=d.get("folder_id"))


@dataclass
class WorkspaceManifest:
    id: str
    name: str
    engine_model: str
    primary_tail_number: Optional[str] = None
    log_folders: list[LogFolder] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    created_at: str = ""
    updated_at: str = ""
    engine_version_seen: list[str] = field(default_factory=list)
    flight_count: int = 0
    storage_backend: str = "filesystem"

    def to_dict(self) -> dict:
        d = {
            "id": self.id, "name": self.name, "engine_model": self.engine_model,
            "log_folders": [f.to_dict() for f in self.log_folders],
            "schema_version": self.schema_version,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "engine_version_seen": self.engine_version_seen,
            "flight_count": self.flight_count, "storage_backend": self.storage_backend,
        }
        if self.primary_tail_number is not None:
            d["primary_tail_number"] = self.primary_tail_number
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "WorkspaceManifest":
        return cls(
            id=d["id"], name=d["name"], engine_model=d["engine_model"],
            primary_tail_number=d.get("primary_tail_number"),
            log_folders=[LogFolder.from_dict(f) for f in d.get("log_folders", [])],
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            created_at=d.get("created_at", ""), updated_at=d.get("updated_at", ""),
            engine_version_seen=d.get("engine_version_seen", []),
            flight_count=d.get("flight_count", 0),
            storage_backend=d.get("storage_backend", "filesystem"),
        )


# log_folder_path for a flight imported by dropping/picking files directly
# in the browser (server.py's op_import_files) rather than via a scanned
# manifest.log_folders entry — there's no folder for scan_workspace to find
# it missing from, since its bytes are persisted in the workspace itself.
UPLOADED_SOURCE = "(uploaded)"


@dataclass
class ImportRecord:
    source_key: str
    log_folder_path: str
    relative_path: str
    filename: str
    imported_at: str
    via: str = "unknown"  # "sd_card" | "garmin_pilot" | "unknown"

    def to_dict(self) -> dict:
        return {
            "source_key": self.source_key, "log_folder_path": self.log_folder_path,
            "relative_path": self.relative_path, "filename": self.filename,
            "imported_at": self.imported_at, "via": self.via,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ImportRecord":
        return cls(
            source_key=d["source_key"], log_folder_path=d["log_folder_path"],
            relative_path=d["relative_path"], filename=d["filename"],
            imported_at=d["imported_at"], via=d.get("via", "unknown"),
        )


@dataclass
class FlightSources:
    flight_id: str
    imports: list[ImportRecord] = field(default_factory=list)
    duplicate_of: Optional[str] = None
    different_tail_number: Optional[str] = None
    # Not in Spec 02's §6.2 sketch verbatim, but the spec requires (§5.5)
    # that "missing" persist as durable state until the pilot explicitly
    # clears it — this is the field that state lives in, since sources.json
    # is already per-flight provenance. Cleared automatically if a rescan
    # re-finds one of this flight's fingerprints (that's the whole point of
    # fingerprint-based rematching, §5.7); the "persists until cleared"
    # guarantee in §5.5 is about the not-found case, not about refusing to
    # recognize a file that reappears.
    missing: bool = False

    def to_dict(self) -> dict:
        d = {
            "flight_id": self.flight_id, "imports": [i.to_dict() for i in self.imports],
            "missing": self.missing,
        }
        if self.duplicate_of is not None:
            d["duplicate_of"] = self.duplicate_of
        if self.different_tail_number is not None:
            d["different_tail_number"] = self.different_tail_number
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "FlightSources":
        return cls(
            flight_id=d["flight_id"],
            imports=[ImportRecord.from_dict(i) for i in d.get("imports", [])],
            duplicate_of=d.get("duplicate_of"),
            different_tail_number=d.get("different_tail_number"),
            missing=d.get("missing", False),
        )


@dataclass
class FleetSelection:
    # Membership is NOT a field here — deliberately (§5.1, §6.3). It's
    # whatever flights/ currently contains. The only thing this document
    # stores is the one real in-app selection: which known flights to
    # exclude from baselines, and why.
    excluded: list[dict] = field(default_factory=list)  # [{flight_id, reason}]
    baseline_config: dict = field(default_factory=lambda: dict(DEFAULT_BASELINE_CONFIG))

    def to_dict(self) -> dict:
        return {"excluded": self.excluded, "baseline_config": self.baseline_config}

    @classmethod
    def from_dict(cls, d: dict) -> "FleetSelection":
        # Spec 12 (Session B): a workspace persisted before Spec 12 has a
        # baseline_config with only the pre-Spec-12 keys — merge the new
        # defaults *under* it rather than defaulting the whole dict only
        # when it's empty, so an old workspace's selection.json gets the
        # new fields backfilled (recent_window_*, om_margin_fraction)
        # without silently dropping anything the pilot already set
        # (outlier_z_threshold, band_kind_by_metric, overrides).
        baseline_config = {**DEFAULT_BASELINE_CONFIG, **(d.get("baseline_config") or {})}
        return cls(excluded=d.get("excluded", []), baseline_config=baseline_config)


@dataclass
class AppSettings:
    units: str = "imperial"  # "imperial" | "metric"
    last_active_workspace_id: Optional[str] = None
    # User chart presets (Spec 07 §6.1 Q1) — app-level, not per-workspace:
    # a preset describes a way of looking at data, not a property of a
    # particular aircraft. flight_chart.last_preset_id is the only other
    # key in that dict for v0.1 (§6.5).
    chart_presets: list = field(default_factory=list)
    flight_chart: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "units": self.units, "last_active_workspace_id": self.last_active_workspace_id,
            "chart_presets": self.chart_presets, "flight_chart": self.flight_chart,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AppSettings":
        return cls(
            units=d.get("units", "imperial"), last_active_workspace_id=d.get("last_active_workspace_id"),
            chart_presets=d.get("chart_presets") or [], flight_chart=d.get("flight_chart") or {},
        )


@dataclass
class WorkspaceSettings:
    # anonymize_by_default: retired in Spec 02 v0.11 — anonymisation is a
    # per-export choice (§7.6); an older settings.json's key is ignored.
    active_engine_profile: str = ""
    last_view: Optional[dict] = None
    # Spec 02 v0.8 §5.6/§6.6: groups of aircraft_ident values the pilot
    # has confirmed are one aircraft, e.g. [["N117ZS", "N117Z"]]. Default
    # none — an older workspace's settings.json simply lacks the key.
    aircraft_aliases: list[list[str]] = field(default_factory=list)
    # Spec 12 §8.4/§8.3 (Session F): Trends' per-panel "Show detail
    # strips" state (panel id -> on/off) — plain settings plumbing, not
    # engine computation, but the one existing per-workspace store the
    # web already round-trips through (Session F report: app settings
    # vs. workspace settings).
    trends_detail_strips: dict[str, bool] = field(default_factory=dict)
    # Spec 02 v0.15 §6.6 / Spec 01 §6.5: raw general-purpose analog id →
    # registry channel id, e.g. {"gp_analog_7": "co_ppm"}. Set by the pilot
    # (Settings → Engine → Log channels); never pre-filled.
    channel_assignments: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "active_engine_profile": self.active_engine_profile,
        }
        if self.last_view is not None:
            d["last_view"] = self.last_view
        if self.aircraft_aliases:
            d["aircraft_aliases"] = self.aircraft_aliases
        if self.trends_detail_strips:
            d["trends_detail_strips"] = self.trends_detail_strips
        if self.channel_assignments:
            d["channel_assignments"] = self.channel_assignments
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "WorkspaceSettings":
        return cls(
            active_engine_profile=d.get("active_engine_profile", ""),
            last_view=d.get("last_view"),
            aircraft_aliases=d.get("aircraft_aliases") or [],
            trends_detail_strips=d.get("trends_detail_strips") or {},
            channel_assignments=d.get("channel_assignments") or {},
        )


@dataclass
class ScanResult:
    """What changed in one scan — not persisted, just returned for a host
    (CLI/server) to report to the pilot."""
    new_flight_ids: list[str] = field(default_factory=list)
    rematched_flight_ids: list[str] = field(default_factory=list)  # moved/renamed, or a new export path found
    now_missing_flight_ids: list[str] = field(default_factory=list)
    recovered_flight_ids: list[str] = field(default_factory=list)  # were missing, found again
    unreachable_folders: list[str] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)  # duplicate exports dropped this scan (Spec 01 §6.2)
    reanalyzed_flight_ids: list[str] = field(default_factory=list)  # stale engine_version, re-run for real
    # Ground session / short flight / corrupt log, newly recorded to
    # exclusions.json this scan (Spec 02 §5.11) — never became a
    # flight_id at all, so
    # keyed by filename, not flight_id like the fields above.
    auto_excluded: list[dict] = field(default_factory=list)
    # Spec 03 v0.17 §5.1 — what's waiting for consent after a scan run with
    # analysis deferred (or restricted): logs found but not analysed, and
    # flights whose stored analysis predates the running engine.
    pending_new_logs: list[dict] = field(default_factory=list)
    pending_reanalysis_flight_ids: list[str] = field(default_factory=list)
    # Spec 03 §5.1 "Unreadable": logs this scan couldn't read or analyse,
    # {filename, reason} — recorded in unreadable.json, never silently skipped.
    unreadable: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "unreadable": self.unreadable,
            "new_flight_ids": self.new_flight_ids,
            "rematched_flight_ids": self.rematched_flight_ids,
            "now_missing_flight_ids": self.now_missing_flight_ids,
            "recovered_flight_ids": self.recovered_flight_ids,
            "unreachable_folders": self.unreachable_folders,
            "excluded": self.excluded,
            "reanalyzed_flight_ids": self.reanalyzed_flight_ids,
            "auto_excluded": self.auto_excluded,
            "pending_new_logs": self.pending_new_logs,
            "pending_reanalysis_flight_ids": self.pending_reanalysis_flight_ids,
        }


# ── Registry (app-level, §5.2, §6.7) ─────────────────────────────────────────

def load_registry(registry_path: Path) -> WorkspaceRegistry:
    if not registry_path.exists():
        return WorkspaceRegistry()
    return WorkspaceRegistry.from_dict(json.loads(registry_path.read_text()))


def save_registry(registry_path: Path, registry: WorkspaceRegistry) -> None:
    _write_json(registry_path, registry.to_dict())


def _touch_registry_entry(registry_path: Path, workspace_id: str, **updates) -> None:
    registry = load_registry(registry_path)
    for w in registry.workspaces:
        if w.id == workspace_id:
            for k, v in updates.items():
                setattr(w, k, v)
            save_registry(registry_path, registry)
            return


def resolve_workspace_ref(ref: str, registry_path: Path, workspaces_root: Path) -> Path:
    """
    Spec 01 v0.6 §7.1 (Q10): a registered name or id (registry lookup)
    or a literal path (existing behavior, unchanged, for a
    developer-checkout invocation that predates the registry). Registry
    lookup is tried first; a literal path that happens to collide with a
    registered workspace's name is not a realistic case worth guarding
    against separately.
    """
    registry = load_registry(registry_path)
    for w in registry.workspaces:
        if ref == w.id or ref == w.name:
            return workspaces_root / w.id
    return Path(ref)


# ── Workspace creation ────────────────────────────────────────────────────────

def create_workspace(
    registry_path: Path,
    workspaces_root: Path,
    name: str,
    engine_model: str,
    primary_tail_number: Optional[str] = None,
) -> WorkspaceManifest:
    """
    Spec 02 §5.2/§5.3/§6.1. `engine_model` is required and locked here —
    there is no operation anywhere in this module that changes it after
    creation. That's by construction (§5.6), not an oversight: a pilot
    with two engine types has two workspaces.

    The per-workspace directory is named by `id`, not `name` (the name is
    pilot-chosen and renamable, per §6.1's "kept in sync" — the spec's
    §5.3 tree diagram uses `<workspace_id>`, and §5.8's own summary table
    loosely writes `<name>`; this follows the former since ids are stable
    and filesystem-safe and names aren't guaranteed to be either).
    """
    check_engine_model(engine_model)
    if not name or not name.strip():
        raise ValueError("Workspace name cannot be empty.")

    registry = load_registry(registry_path)
    if any(w.name == name for w in registry.workspaces):
        raise ValueError(f"A workspace named {name!r} already exists.")

    ws_id = _new_id("ws")
    now = _now()
    entry = WorkspaceRegistryEntry(
        id=ws_id, name=name, engine_model=engine_model, primary_tail_number=primary_tail_number,
        created_at=now, last_opened_at=now, log_folder_count=0, flight_count=0,
    )
    registry.workspaces.append(entry)
    save_registry(registry_path, registry)

    manifest = WorkspaceManifest(
        id=ws_id, name=name, engine_model=engine_model, primary_tail_number=primary_tail_number,
        log_folders=[], created_at=now, updated_at=now, engine_version_seen=[], flight_count=0,
    )
    ws_dir = workspaces_root / ws_id
    (ws_dir / "flights").mkdir(parents=True, exist_ok=True)
    (ws_dir / "fleet").mkdir(parents=True, exist_ok=True)
    (ws_dir / "rules").mkdir(parents=True, exist_ok=True)
    save_manifest(ws_dir, manifest)
    save_selection(ws_dir, FleetSelection())
    save_workspace_settings(ws_dir, WorkspaceSettings(active_engine_profile=engine_model))
    return manifest


def delete_workspace(registry_path: Path, workspaces_root: Path, workspace_id: str) -> None:
    """
    Permanently remove a workspace: its registry entry and its entire
    on-disk directory (flights/, fleet/, rules/, manifest, settings,
    exclusions.json — everything derived from it). There is no undo.

    This function itself doesn't ask for confirmation — that's the
    caller's job (server.py's op_delete_workspace, and ultimately the
    UI's "type DELETE to confirm" control). By the time this runs, the
    decision has already been made.
    """
    registry = load_registry(registry_path)
    if not any(w.id == workspace_id for w in registry.workspaces):
        raise ValueError(f"no workspace {workspace_id!r}")
    registry.workspaces = [w for w in registry.workspaces if w.id != workspace_id]
    save_registry(registry_path, registry)

    app_settings = load_app_settings(registry_path)
    if app_settings.last_active_workspace_id == workspace_id:
        app_settings.last_active_workspace_id = None
        save_app_settings(registry_path, app_settings)

    ws_dir = workspaces_root / workspace_id
    if ws_dir.exists():
        shutil.rmtree(ws_dir)


def list_workspaces(registry_path: Path) -> list[WorkspaceRegistryEntry]:
    return load_registry(registry_path).workspaces


def add_log_folder(ws_dir: Path, folder_path: str, registry_path: Optional[Path] = None,
                   folder_id: Optional[str] = None) -> WorkspaceManifest:
    """Link a folder: by path (the host walks it), or — with `folder_id` —
    by display name only, for a folder whose listing and bytes the
    transport supplies (Spec 04 §9.3). No check is made here that the
    folder can be reached; the next scan sets `reachable`."""
    manifest = load_manifest(ws_dir)
    if folder_id is not None:
        if any(f.folder_id == folder_id for f in manifest.log_folders):
            return manifest
    elif any(f.path == folder_path and f.folder_id is None for f in manifest.log_folders):
        return manifest
    manifest.log_folders.append(LogFolder(path=folder_path, reachable=True, last_scanned_at=None, folder_id=folder_id))
    manifest.updated_at = _now()
    save_manifest(ws_dir, manifest)
    if registry_path is not None:
        _touch_registry_entry(registry_path, manifest.id, log_folder_count=len(manifest.log_folders))
    return manifest


# ── Per-workspace documents (§5.3, §6) ───────────────────────────────────────

def load_manifest(ws_dir: Path) -> WorkspaceManifest:
    manifest = WorkspaceManifest.from_dict(json.loads((ws_dir / "manifest.json").read_text()))
    check_engine_model(manifest.engine_model, manifest.name)
    return manifest


def save_manifest(ws_dir: Path, manifest: WorkspaceManifest) -> None:
    _write_json(ws_dir / "manifest.json", manifest.to_dict())


def load_sources(ws_dir: Path, flight_id: str) -> Optional[FlightSources]:
    f = ws_dir / "flights" / flight_id / "sources.json"
    if not f.exists():
        return None
    return FlightSources.from_dict(json.loads(f.read_text()))


def save_sources(ws_dir: Path, sources: FlightSources) -> None:
    _write_json(ws_dir / "flights" / sources.flight_id / "sources.json", sources.to_dict())


def load_flight_analysis(ws_dir: Path, flight_id: str) -> Optional[FlightAnalysis]:
    f = ws_dir / "flights" / flight_id / "analysis.json"
    if not f.exists():
        return None
    return FlightAnalysis(**json.loads(f.read_text()))


def save_flight_analysis(ws_dir: Path, fa: FlightAnalysis) -> None:
    _write_json(ws_dir / "flights" / fa.flight_id / "analysis.json", fa.to_dict())


def list_flight_ids(ws_dir: Path) -> list[str]:
    flights_dir = ws_dir / "flights"
    if not flights_dir.is_dir():
        return []
    return sorted(p.name for p in flights_dir.iterdir() if p.is_dir())


def load_all_flight_analyses(ws_dir: Path) -> list[FlightAnalysis]:
    out = []
    for fid in list_flight_ids(ws_dir):
        fa = load_flight_analysis(ws_dir, fid)
        if fa is not None:
            out.append(fa)
    return out


def remove_missing_flight(ws_dir: Path, flight_id: str) -> bool:
    """
    The pilot's explicit "Remove missing flights" action (§5.5) — the
    only way a Missing flight ever leaves the workspace. Refuses to
    remove a flight that isn't currently flagged missing, since this
    isn't a general delete operation.
    """
    sources = load_sources(ws_dir, flight_id)
    if sources is None or not sources.missing:
        return False
    shutil.rmtree(ws_dir / "flights" / flight_id)
    return True


def remove_flight(ws_dir: Path, flight_id: str) -> bool:
    """
    General "take this flight out of the workspace" — unlike
    remove_missing_flight, works regardless of current status. Also drops
    any FleetSelection.excluded entry for it so a stale exclusion doesn't
    linger pointing at nothing. Deliberately does NOT touch the source log
    file itself: if it's still sitting in a reachable log_folders entry,
    the rescan the caller runs right after (server.py's op_remove_flight)
    will find it again under the same fingerprint-derived flight_id and
    bring it right back — that's a feature, not a bug, since it means
    "remove" only sticks for flights whose source is actually gone from
    every watched folder (or was never in one, e.g. uploaded).
    """
    d = ws_dir / "flights" / flight_id
    if not d.is_dir():
        return False
    shutil.rmtree(d)
    selection = load_selection(ws_dir)
    before = len(selection.excluded)
    selection.excluded = [e for e in selection.excluded if e["flight_id"] != flight_id]
    if len(selection.excluded) != before:
        save_selection(ws_dir, selection)
    return True


def remove_flights(ws_dir: Path, flight_ids: list[str]) -> list[str]:
    """Bulk form of remove_flight — one FleetSelection load/save instead
    of one per flight, since a multi-select removal is exactly the kind
    of batch where that difference is visible."""
    ids = set(flight_ids)
    removed = []
    for fid in ids:
        d = ws_dir / "flights" / fid
        if not d.is_dir():
            continue
        shutil.rmtree(d)
        removed.append(fid)
    if removed:
        selection = load_selection(ws_dir)
        before = len(selection.excluded)
        selection.excluded = [e for e in selection.excluded if e["flight_id"] not in ids]
        if len(selection.excluded) != before:
            save_selection(ws_dir, selection)
    return removed


def load_selection(ws_dir: Path) -> FleetSelection:
    f = ws_dir / "fleet" / "selection.json"
    if not f.exists():
        return FleetSelection()
    return FleetSelection.from_dict(json.loads(f.read_text()))


def save_selection(ws_dir: Path, selection: FleetSelection) -> None:
    _write_json(ws_dir / "fleet" / "selection.json", selection.to_dict())


def exclude_flight(ws_dir: Path, flight_id: str, reason: str) -> FleetSelection:
    selection = load_selection(ws_dir)
    if not any(e["flight_id"] == flight_id for e in selection.excluded):
        selection.excluded.append({"flight_id": flight_id, "reason": reason})
        save_selection(ws_dir, selection)
    return selection


def include_flight(ws_dir: Path, flight_id: str) -> FleetSelection:
    """Undo exclude_flight — drop flight_id from the exclusion list."""
    selection = load_selection(ws_dir)
    before = len(selection.excluded)
    selection.excluded = [e for e in selection.excluded if e["flight_id"] != flight_id]
    if len(selection.excluded) != before:
        save_selection(ws_dir, selection)
    return selection


def update_baseline_config(ws_dir: Path, baseline_config: dict) -> FleetSelection:
    """
    Spec 01 §8.4 v0.8 / Spec 03 §5.5: the rule playground's other document
    — outlier_z_threshold and its per-metric overrides live in
    FleetSelection, not rules/active.json (see load_workspace_rules).
    Caller (server.py's op_save_baseline_config) rebuilds the fleet right
    after, since this value feeds update_fleet's outliers(), not just
    evaluate_insights.
    """
    selection = load_selection(ws_dir)
    selection.baseline_config = baseline_config
    save_selection(ws_dir, selection)
    return selection


def set_reference(
    ws_dir: Path, metric_id: str, flight_ids: list[str], label: Optional[str] = None,
) -> FleetSelection:
    """
    Spec 12 §5.7/§11.3: pin `metric_id`'s shift reference to a frozen
    flight_ids membership — statistics recompute from current analyses
    and honour exclusions on the next update_fleet, they just stop
    rolling. Saved regardless of size; a reference below n_min after
    exclusions is caught at update_fleet time (REFERENCE_LOW_N, reverts
    to rolling) rather than rejected here (R2.1: "still saved").
    """
    selection = load_selection(ws_dir)
    pinned = dict(selection.baseline_config.get("pinned_references") or {})
    entry = {"flight_ids": list(flight_ids), "set_at": datetime.now(timezone.utc).isoformat()}
    if label:
        entry["label"] = label
    pinned[metric_id] = entry
    selection.baseline_config = {**selection.baseline_config, "pinned_references": pinned}
    save_selection(ws_dir, selection)
    return selection


def clear_reference(ws_dir: Path, metric_id: str) -> FleetSelection:
    """
    Unpin `metric_id`'s reference. Unlike `set_reference` (which only
    writes the pin for whenever the *next* update_fleet happens to run),
    this rebuilds the fleet immediately — Spec 12 §5.7.1 item 4 needs an
    event that stops qualifying *as a direct result of this unpin* to
    close with `cleared_by: "unpin"` at the moment it actually happens,
    not retroactively guessed at from some later, unrelated rebuild that
    wouldn't otherwise know why the event closed.
    """
    selection = load_selection(ws_dir)
    pinned = dict(selection.baseline_config.get("pinned_references") or {})
    if pinned.pop(metric_id, None) is not None:
        selection.baseline_config = {**selection.baseline_config, "pinned_references": pinned}
        save_selection(ws_dir, selection)
        rebuild_fleet(ws_dir, cleared_by_unpin=metric_id)
    return selection


def _row_names(fleet: FleetAnalysis, metric_id: str) -> bool:
    return any(metric_id in (row.get("members") or [row["metric_id"]]) for row in fleet.change_summary)


def preview_clear_reference(ws_dir: Path, metric_id: str) -> dict:
    """
    Spec 12 §5.7.1 item 5: whether unpinning `metric_id` would change its
    change_summary membership — computed by rebuilding the fleet with
    the pin hypothetically removed, same inputs `rebuild_fleet` uses,
    without writing anything (no call to `save_selection`/`save_fleet_analysis`).
    `currently_in_summary` reflects the *persisted* pinned state (today's
    fleet, rebuilt fresh rather than read from cache, so a stale cache
    can't make the two sides of the comparison disagree).
    """
    selection = load_selection(ws_dir)
    excluded_ids = {e["flight_id"] for e in selection.excluded}
    included = [fa for fa in load_all_flight_analyses(ws_dir) if fa.flight_id not in excluded_ids]
    engine_config = load_engine_config(load_manifest(ws_dir).engine_model)
    filters = load_filters(ws_dir)["filters"]

    current_fleet = update_fleet(
        included, excluded=selection.excluded, baseline_config=selection.baseline_config,
        engine_config=engine_config, filters=filters,
    )
    pinned = dict(selection.baseline_config.get("pinned_references") or {})
    pinned.pop(metric_id, None)
    hypothetical_config = {**selection.baseline_config, "pinned_references": pinned}
    hypothetical_fleet = update_fleet(
        included, excluded=selection.excluded, baseline_config=hypothetical_config,
        engine_config=engine_config, filters=filters,
    )

    currently = _row_names(current_fleet, metric_id)
    after = _row_names(hypothetical_fleet, metric_id)
    return {"currently_in_summary": currently, "would_be_in_summary": after, "changes": currently != after}


def load_fleet_analysis(ws_dir: Path) -> Optional[FleetAnalysis]:
    f = ws_dir / "fleet" / "analysis.json"
    if not f.exists():
        return None
    return FleetAnalysis(**json.loads(f.read_text()))


def save_fleet_analysis(ws_dir: Path, fleet: FleetAnalysis) -> None:
    _write_json(ws_dir / "fleet" / "analysis.json", fleet.to_dict())


# Spec 12 §6: fleet/shift_history.json, alongside selection.json (Spec 02
# §6.3) — not yet itself documented there (out of this task's scope; only
# Spec 10 §5.2 is the one spec edit requested — see report).

def load_shift_history(ws_dir: Path) -> list[dict]:
    f = ws_dir / "fleet" / "shift_history.json"
    if not f.exists():
        return []
    return json.loads(f.read_text())


def save_shift_history(ws_dir: Path, events: list[dict]) -> None:
    _write_json(ws_dir / "fleet" / "shift_history.json", events)


def _shift_event_kind(fleet: FleetAnalysis, row: dict) -> str:
    """The event kind for a change_summary row — the union of om_margin/
    filter_edge across every member for a coupled row (Session B D4:
    "level crossings still override" applies panel-wide), else the one
    metric's own level, else (Spec 12 §5.8) `frequency` when the row's
    event frequency qualified rather than its shift_z — a limit panel's
    `peak_excess` has no shift at all in the "rare" case (§9.3), so
    `shift` is read defensively here. `row` always qualifies
    (change_summary only contains qualifying rows), so this always
    resolves to a real kind."""
    members = row.get("members") or [row["metric_id"]]
    levels = [((fleet.metrics[m].get("shift") or {}).get("level") or {}) for m in members]
    if any(l.get("om_margin") for l in levels):
        return "om_margin"
    if any(l.get("filter_edge") for l in levels):
        return "filter_edge"
    if any((fleet.metrics[m].get("frequency") or {}).get("qualifies") for m in members):
        return "frequency"
    return "shift"


def update_shift_history(
    ws_dir: Path, fleet: FleetAnalysis, cleared_by_unpin: Optional[str] = None,
) -> list[dict]:
    """
    Spec 12 §6, extended by v0.3 §7.1/D4 (Session B R3b.3): compares
    `fleet.change_summary` (already one row per coupled panel, not per
    member) against the metric's/panel's last recorded state, opening
    or closing an event. An event's identity is its panel for a coupled
    row, else its metric_id — matching change_summary's own grouping,
    so a coupled panel never produces more than one open event between
    its members. A coupled event additionally carries `members` (ids)
    and `member_detail` (each member's own shift_z/direction at open
    time) — a snapshot, since the live members' current shift will have
    moved on by the time this history is read. Append-only except user
    deletion (delete_shift_event); re-running update_fleet with no
    qualify/clear transition appends nothing.

    `cleared_by_unpin` (Spec 12 §5.7.1 item 4): the metric id `clear_reference`
    just unpinned, passed through only on the one rebuild it triggers
    itself — any event that closes *in this same call* for that metric
    (or, for a coupled row, has it among `members`) was closed by the
    unpin, not by the window simply rolling on, and is tagged
    `cleared_by: "unpin"` so the history doesn't read as a recovery.
    """
    history = load_shift_history(ws_dir)
    open_by_key = {(ev.get("panel") or ev["metric_id"]): ev for ev in history if "cleared_at" not in ev}

    now = datetime.now(timezone.utc).isoformat()
    changed = False
    current_keys: set = set()
    for row in fleet.change_summary:
        metric_id = row["metric_id"]
        entry = fleet.metrics[metric_id]
        # Spec 12 §9.3 "rare": a limit's peak_excess can qualify on
        # frequency alone with no shift of its own (too few sparse
        # points for its own window) — fall back to the full-coverage
        # counterpart's window (time_above_pct for peak_excess; every
        # other metric is already its own counterpart) for the window
        # this event opened in.
        shift = entry.get("shift") or fleet.metrics[full_coverage_counterpart(metric_id)]["shift"]
        key = row.get("panel") or metric_id
        current_keys.add(key)
        if key in open_by_key:
            continue
        event = {
            "id": str(uuid.uuid4()), "metric_id": metric_id, "detected_at": now,
            "kind": _shift_event_kind(fleet, row),
            "window": {
                "flight_ids": shift["recent"]["flight_ids"],
                "hours_from": shift["recent"]["hours_from"], "hours_to": shift["recent"]["hours_to"],
            },
            "shift_z": entry["shift"]["shift_z"] if entry.get("shift") else None,
            "direction": shift["direction"], "comparison": shift["comparison"],
            "reference": {
                "kind": shift["reference"]["kind"], "n": shift["reference"]["n"],
                "hours_from": shift["reference"].get("hours_from"), "hours_to": shift["reference"].get("hours_to"),
            },
        }
        if entry.get("frequency") is not None:
            event["frequency"] = entry["frequency"]
        if "panel" in row:
            event["panel"] = row["panel"]
            event["members"] = row["members"]
            event["member_detail"] = {
                m: {"shift_z": fleet.metrics[m]["shift"]["shift_z"], "direction": fleet.metrics[m]["shift"]["direction"]}
                for m in row["members"]
            }
        history.append(event)
        changed = True

    for ev in history:
        key = ev.get("panel") or ev["metric_id"]
        if "cleared_at" not in ev and key not in current_keys:
            ev["cleared_at"] = now
            entry = fleet.metrics.get(ev["metric_id"], {})
            ev["cleared_engine_hours"] = max(
                (p["x"] for p in entry.get("points", []) if p.get("x") is not None), default=None)
            if cleared_by_unpin is not None and cleared_by_unpin in (ev.get("members") or [ev["metric_id"]]):
                ev["cleared_by"] = "unpin"
            changed = True

    if changed:
        save_shift_history(ws_dir, history)
    return history


def delete_shift_event(ws_dir: Path, event_id: str) -> list[dict]:
    """User deletion (Spec 12 §11.3 `delete_shift_event`) — the one
    exception to the log's append-only rule."""
    history = load_shift_history(ws_dir)
    filtered = [ev for ev in history if ev.get("id") != event_id]
    if len(filtered) != len(history):
        save_shift_history(ws_dir, filtered)
    return filtered


def fleet_for_exclusions(ws_dir: Path, excluded: list[dict], baseline_config: Optional[dict] = None) -> FleetAnalysis:
    """The workspace fleet as it would be with exactly `excluded` left out
    — nothing saved, no shift history. rebuild_fleet's own computation,
    and the Spec 14 §7.1 exclude/include preview's (v0.6). A
    `baseline_config` replaces the stored one (a changed setting's live
    effect, Spec 14 v0.13)."""
    selection = load_selection(ws_dir)
    excluded_ids = {e["flight_id"] for e in excluded}
    included = [fa for fa in load_all_flight_analyses(ws_dir) if fa.flight_id not in excluded_ids]
    return update_fleet(
        included, excluded=excluded,
        baseline_config=baseline_config if baseline_config is not None else selection.baseline_config,
        engine_config=load_engine_config(load_manifest(ws_dir).engine_model),
        filters=load_filters(ws_dir)["filters"],
    )


def rebuild_fleet(ws_dir: Path, cleared_by_unpin: Optional[str] = None) -> FleetAnalysis:
    """
    Spec 01 `update_fleet`, scoped to this workspace: every flight in
    flights/ *except* the ones FleetSelection.excluded names — Missing
    flights are NOT excluded from this (§5.5: their baseline contribution
    stays unchanged while missing; only an explicit exclusion removes a
    flight from the fleet).

    `cleared_by_unpin` (Spec 12 §5.7.1 item 4): passed straight through
    to `update_shift_history` — set only by `clear_reference`'s own
    rebuild, never by a plain `rebuild_fleet` call.
    """
    fleet = fleet_for_exclusions(ws_dir, load_selection(ws_dir).excluded)
    fleet.shift_history = update_shift_history(ws_dir, fleet, cleared_by_unpin=cleared_by_unpin)
    save_fleet_analysis(ws_dir, fleet)
    return fleet


# ── Rule playground (Spec 02 §6.4, Spec 03 §5.5) ────────────────────────────
# rules/active.json is one half of the playground's "one editor, two
# documents" — threshold/condition/n_min live here; outlier_z_threshold
# lives in FleetSelection.baseline_config (update_baseline_config, above).
# "Edits there never touch the shipped insight_rules.json" (Spec 03 §5.5
# principle 5) — active.json is a per-workspace working copy, present only
# once a pilot has actually changed something.

def load_workspace_rules(ws_dir: Path, shipped_rules: dict) -> dict:
    f = ws_dir / "rules" / "active.json"
    if f.exists():
        rules = json.loads(f.read_text())
        rules = upgrade_limit_refs(rules)
        rules = upgrade_to_limit_refs(rules)
        rules = upgrade_phase_a_rules(rules)
        rules = upgrade_map_condition(rules)
        rules = upgrade_cas_events(rules)
        return rules
    return shipped_rules


# Spec 09 §10.2 (rules v1.3): threshold triggers name a profile limit
# instead of carrying its number. A workspace copy saved before then
# still says e.g. `"limit": 248` on oil_temp_peak — which was always
# oil_temp_max, and wrong for a 915iS (266°F).
_LEGACY_THRESHOLD_LIMIT_REFS = {
    "oil_temp_peak": "oil_temp_max",
    "coolant_temp_peak": "coolant_temp_max",
    "overboost_time": "overboost",
}


def upgrade_limit_refs(rules: dict) -> dict:
    """Rewrite legacy numeric threshold triggers to `limit_ref`, in memory
    (the file itself is left as the pilot saved it until next saved)."""
    for topic_id, ref in _LEGACY_THRESHOLD_LIMIT_REFS.items():
        topic = (rules.get("rules") or {}).get(topic_id)
        if not isinstance(topic, dict):
            continue
        for trig in topic.get("triggers") or []:
            if isinstance(trig, dict) and trig.get("type") == "threshold" and "limit_ref" not in trig and "limit" in trig:
                trig.pop("limit")
                trig.pop("unit", None)
                trig["limit_ref"] = ref
    return rules


# Spec 10 §4.1 (Spec 09 §10.2, v0.13): oil_temp_peak, coolant_temp_peak and
# overboost_time used to reference their limit via a `threshold` trigger's
# `limit_ref`; now it's a rule-level `limit_refs` list and none of the
# three has a threshold trigger any more.
_LIMIT_REFS_TOPICS = ("oil_temp_peak", "coolant_temp_peak", "overboost_time")


def upgrade_to_limit_refs(rules: dict) -> dict:
    """
    Move a `threshold` + `limit_ref` trigger on oil_temp_peak /
    coolant_temp_peak / overboost_time to the rule-level `limit_refs`
    field, in memory (the file itself is left as the pilot saved it until
    next saved) — the same pattern as `upgrade_limit_refs`, one level up.
    A rule set that already has `limit_refs` is left alone.
    """
    for topic_id in _LIMIT_REFS_TOPICS:
        topic = (rules.get("rules") or {}).get(topic_id)
        if not isinstance(topic, dict) or topic.get("limit_refs"):
            continue
        triggers = topic.get("triggers") or []
        trig = next(
            (t for t in triggers if isinstance(t, dict) and t.get("type") == "threshold" and t.get("limit_ref")),
            None,
        )
        if trig is None:
            continue
        topic["limit_refs"] = [trig["limit_ref"]]
        topic["triggers"] = [t for t in triggers if t is not trig]
        warnings.warn(
            f"Workspace rules/active.json had a 'threshold'+'limit_ref' trigger on '{topic_id}' — "
            f"moved to the rule-level 'limit_refs' field (Spec 10 §4.1).",
        )
    return rules


# Spec 10 Phase A: these topics no longer exist (D1, D3, Q4 — their
# metrics/baselines may still exist, but the rule and the topic function
# are gone, so a rule block for them is meaningless, not just inert).
_PHASE_A_REMOVED_TOPICS = ("oil_coolant_ratio", "egt4_elevation", "flight_phase_mix", "cruise_efficiency", "cruise_fuel_flow")


def upgrade_phase_a_rules(rules: dict) -> dict:
    """
    A workspace's rules/active.json saved before Spec 10 Phase A may still
    carry rule blocks for removed topics, or the old insight-raising shape
    for cylinder_rank/climb_thermal_rate. Upgraded in memory (the file
    itself is left as the pilot saved it until next saved) — each change
    is reported with warnings.warn, never applied silently.
    """
    topics = rules.get("rules")
    if not isinstance(topics, dict):
        return rules

    for topic_id in _PHASE_A_REMOVED_TOPICS:
        if topic_id in topics:
            topics.pop(topic_id)
            warnings.warn(
                f"Workspace rules/active.json had a '{topic_id}' rule block — that topic "
                f"was removed (Spec 10 Phase A). Dropped on load.",
            )

    cylinder_rank = topics.get("cylinder_rank")
    if isinstance(cylinder_rank, dict) and (cylinder_rank.get("enabled") is not False or "triggers" in cylinder_rank):
        old_trigger = next(
            (t for t in cylinder_rank.get("triggers", []) if isinstance(t, dict) and t.get("type") == "threshold"),
            {},
        )
        topics["cylinder_rank"] = {
            "enabled": False,
            "_comment": "Retired as an insight (Spec 10 D4): egt_cyl_deviation fires first "
                        "on the same event. Rank stays as context — see Spec 08 §6.",
            "margin_min_f": old_trigger.get("margin_min_f", cylinder_rank.get("margin_min_f", 15)),
            "consecutive_flights": old_trigger.get("consecutive_flights", cylinder_rank.get("consecutive_flights", 2)),
        }
        warnings.warn(
            "Workspace rules/active.json had cylinder_rank enabled as an insight — "
            "forced to the new context-only shape (Spec 10 D4).",
        )

    climb = topics.get("climb_thermal_rate")
    if isinstance(climb, dict) and climb.get("enabled") is not False:
        climb["enabled"] = False
        climb.setdefault(
            "_comment",
            "Research (Spec 10 D2): fails A7; metrics still computed for research. Not shown to casual users.",
        )
        warnings.warn(
            "Workspace rules/active.json had climb_thermal_rate enabled — "
            "forced to disabled (Research status, Spec 10 D2).",
        )

    return rules


def upgrade_map_condition(rules: dict) -> dict:
    """
    Spec 10 §6.1/D5 (rules v1.7): map_at_takeoff's threshold trigger used
    to be `condition: "vs_om_expected"` with a fixed `tolerance_hpa`; now
    it's `condition: "vs_personal_model"` with a `z` multiplier on the
    leave-one-out fit's residual standard error. Upgraded in memory (the
    file itself is left as the pilot saved it until next saved) — the
    same pattern as upgrade_limit_refs, one trigger field over.
    """
    topic = (rules.get("rules") or {}).get("map_at_takeoff")
    if not isinstance(topic, dict):
        return rules
    for trig in topic.get("triggers") or []:
        if isinstance(trig, dict) and trig.get("condition") == "vs_om_expected":
            trig.pop("tolerance_hpa", None)
            trig["condition"] = "vs_personal_model"
            trig.setdefault("z", 2.0)
            warnings.warn(
                "Workspace rules/active.json had map_at_takeoff's 'vs_om_expected'+'tolerance_hpa' "
                "trigger — upgraded to 'vs_personal_model'+'z' (Spec 10 §6.1/D5).",
            )
    return rules


def upgrade_cas_events(rules: dict) -> dict:
    """
    Spec 01 v0.21 / Spec 10 D19 (rules v1.8): engine_ecu_inflight no longer
    fires (its GROUND/IN_FLIGHT runs are CAS events owned by
    limit_exceedances), so its trigger goes; limit_exceedances gains the
    `cas` display-label entry. Upgraded in memory, like the others.
    """
    r = rules.get("rules") or {}
    ecu = r.get("engine_ecu_inflight")
    if isinstance(ecu, dict) and ecu.get("triggers"):
        ecu["triggers"] = []
    lim = r.get("limit_exceedances")
    if isinstance(lim, dict):
        lim.setdefault("cas", {"severity": "watch"})
    return rules


def save_workspace_rules(ws_dir: Path, rules: dict) -> None:
    _write_json(ws_dir / "rules" / "active.json", rules)


def reset_workspace_rules(ws_dir: Path) -> None:
    """"Reset to shipped defaults" (Spec 03 §5.5) — deletes the working
    copy rather than writing the shipped rules back verbatim, so
    load_workspace_rules's fallback is the one place "what's shipped"
    is ever read from."""
    f = ws_dir / "rules" / "active.json"
    if f.exists():
        f.unlink()


def load_app_settings(registry_path: Path) -> AppSettings:
    f = registry_path.parent / "settings.json"
    if not f.exists():
        return AppSettings()
    return AppSettings.from_dict(json.loads(f.read_text()))


def save_app_settings(registry_path: Path, settings: AppSettings) -> None:
    _write_json(registry_path.parent / "settings.json", settings.to_dict())


def load_workspace_settings(ws_dir: Path) -> WorkspaceSettings:
    f = ws_dir / "settings.json"
    if not f.exists():
        return WorkspaceSettings()
    return WorkspaceSettings.from_dict(json.loads(f.read_text()))


def save_workspace_settings(ws_dir: Path, settings: WorkspaceSettings) -> None:
    _write_json(ws_dir / "settings.json", settings.to_dict())


# ── Scanning (§5.1, §5.4, §5.5, §5.6, §5.7) ─────────────────────────────────

async def find_log_file_by_name_async(manifest: WorkspaceManifest, filename: str, sources: Callable = DISK) -> Optional[LogRef]:
    """
    Best-effort: search every reachable log_folders entry for a file
    with this exact name. exclusions.json only ever records a filename
    (Spec 02 §6.8), never a path, so this is how a
    skipped log's own data (date, duration, etc.) gets found again for
    display — e.g. the Flights tab's Skipped list. None if the file
    isn't in any currently-reachable watched folder (including the
    always-true case of a browser-uploaded exclusion, which was never
    in a folder at all — its bytes were never saved anywhere).
    """
    target = filename.lower()
    for lf in manifest.log_folders:
        source = sources(lf)
        for entry in (await source.alist()) or []:
            if entry.name.lower() == target:
                return LogRef(source, entry)
    return None


def find_log_file_by_name(*args, **kwargs):
    """`find_log_file_by_name_async` driven to the end at once — for disk sources
    (the server, the CLI); see log_sources.run_now."""
    return run_now(find_log_file_by_name_async(*args, **kwargs))


async def read_source_bytes_async(ws_dir: Path, src: "FlightSources", sources: Callable = DISK) -> Optional[tuple[bytes, str]]:
    """Best-effort re-read of a known flight's own source bytes — the
    workspace's own persisted copy for an uploaded flight, or the
    log_folders path for a scanned one. Shared by scan_workspace's
    engine-version staleness check (below) and server.py's
    op_get_flight_series, which otherwise only ever checked the
    workspace's own copy — a folder-scanned flight never has one (only
    import_files persists raw bytes into the workspace itself), so its
    timeline silently had nowhere to read from. None if nothing's
    reachable right now (src.missing already covers the common scan-time
    case; this also covers a folder that's since gone offline)."""
    manifest = None
    for imp in reversed(src.imports):
        if imp.log_folder_path == UPLOADED_SOURCE:
            p = ws_dir / "flights" / src.flight_id / imp.filename
            if p.is_file():
                return p.read_bytes(), imp.filename
            continue
        if manifest is None:
            try:
                manifest = load_manifest(ws_dir)
            except (FileNotFoundError, OSError, ValueError):
                manifest = WorkspaceManifest(id="", name="", engine_model="")
        try:
            async with areading(sources(_folder_by_path(manifest, imp.log_folder_path)), imp.relative_path) as data:
                return data, imp.filename
        except LogUnavailable:
            continue
    return None


def read_source_bytes(*args, **kwargs):
    """`read_source_bytes_async` driven to the end at once — for disk sources
    (the server, the CLI); see log_sources.run_now."""
    return run_now(read_source_bytes_async(*args, **kwargs))


# ── Unreadable logs (Spec 02 §5.11.2, Spec 03 §5.1 "Unreadable") ─────────────
# A log the scan couldn't read or analyse is recorded here, keyed by its
# source_key, with the reason — never an exclusions.json entry (it isn't a
# decision about a flight), and never left looking like it is waiting for
# analysis. An entry recorded by an older engine is retried (a newer engine
# may read the format); a changed file has a new source_key and is retried.

_UNREADABLE_FILE = "unreadable.json"


def load_unreadable(ws_dir: Path) -> dict[str, dict]:
    p = ws_dir / _UNREADABLE_FILE
    if not p.is_file():
        return {}
    return json.loads(p.read_text()).get("logs", {})


def current_unreadable(ws_dir: Path) -> dict[str, dict]:
    """Entries recorded by the running engine — the ones not to retry."""
    return {k: v for k, v in load_unreadable(ws_dir).items() if v.get("engine_version") == __version__}


def _record_unreadable(ws_dir: Path, skey: str, filename: str, folder_path: str, rel: str, reason: str, detail: str) -> dict:
    logs = load_unreadable(ws_dir)
    entry = {"filename": filename, "log_folder": folder_path, "relative_path": rel, "reason": reason,
             "detail": detail[:500], "engine_version": __version__, "at": _now()}
    logs[skey] = entry
    _write_json(ws_dir / _UNREADABLE_FILE, {"version": "1", "logs": logs})
    return entry


def unreadable_reason(exc: Exception, stage: str) -> str:
    """The pilot-facing reason: a format the app doesn't recognise, or a
    log it recognised but couldn't analyse."""
    text = str(exc)
    if stage == "read" and ("unrecognised header format" in text or "Date (yyyy-mm-dd)" in text):
        return "Format not recognised — not a Garmin G3X engine log this app can read."
    if stage == "read":
        return "Couldn't be read — the file looks damaged or isn't a G3X engine log in a supported format."
    return "Couldn't be analysed — the log's contents aren't in a form this app supports."


def date_from_log_filename(filename: str) -> Optional[str]:
    """G3X names logs log_YYYYMMDD_HHMMSS_<airport>.csv — the only date a
    log that hasn't been analysed yet has (Spec 03 v0.17 §5.1)."""
    import re
    m = re.match(r"log_(\d{4})(\d{2})(\d{2})_", filename)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _pending_log(skey: str, folder_path: str, rel: str, filename: str) -> dict:
    return {"source_key": skey, "log_folder": folder_path, "relative_path": rel,
            "filename": filename, "date": date_from_log_filename(filename)}


async def pending_work_async(ws_dir: Path, sources: Callable = DISK) -> tuple[list[dict], list[str]]:
    """Read-only (Spec 03 v0.17 §5.1): logs in the workspace's folders not
    yet analysed (no known fingerprint, not recorded as a non-flight), and
    flights whose stored analysis predates the running engine and whose
    source can still be read. Hashing a folder is cheap; nothing is parsed."""
    manifest = load_manifest(ws_dir)
    exclusions_data = _exclusions.load_exclusions(ws_dir)
    assignments = load_workspace_settings(ws_dir).channel_assignments
    known: set[str] = set()
    stale: list[str] = []
    for fid in list_flight_ids(ws_dir):
        src = load_sources(ws_dir, fid)
        if src is None:
            continue
        known.update(imp.source_key for imp in src.imports)
        if src.missing:
            continue
        fa = load_flight_analysis(ws_dir, fid)
        if fa is not None and analysis_is_stale(fa, assignments) and (await read_source_bytes_async(ws_dir, src, sources)) is not None:
            stale.append(fid)
    new_logs: dict[str, dict] = {}
    unreadable = current_unreadable(ws_dir)   # shown as Unreadable, not offered again
    for lf in manifest.log_folders:
        source = sources(lf)
        for entry in (await source.alist()) or []:
            if _exclusions.is_excluded(entry.name, exclusions_data):
                continue
            try:
                async with areading(source, entry.relative_path) as data:
                    skey = _source_key(data)
            except LogUnavailable:
                continue
            if skey in unreadable:
                continue
            if skey not in known and skey not in new_logs:
                new_logs[skey] = _pending_log(skey, lf.path, entry.relative_path, entry.name)
    return list(new_logs.values()), stale


def pending_work(*args, **kwargs):
    """`pending_work_async` driven to the end at once — for disk sources
    (the server, the CLI); see log_sources.run_now."""
    return run_now(pending_work_async(*args, **kwargs))


def _unreadable(ws_dir: Path, result: "ScanResult", meta: dict, skey: str, filename: str, e: Exception, stage: str) -> None:
    folder_path, rel, _fn = meta[skey]
    reason = unreadable_reason(e, stage)
    _record_unreadable(ws_dir, skey, filename, folder_path, rel, reason, f"{type(e).__name__}: {e}")
    result.unreadable.append({"filename": filename, "reason": reason})


def analysis_params(ws_dir: Path) -> dict:
    """The per-workspace inputs analyze_flight takes (Spec 01 §6.5): the
    channel assignments, when any are set."""
    assignments = load_workspace_settings(ws_dir).channel_assignments
    return {"channel_assignments": dict(assignments)} if assignments else {}


def applicable_assignments(fa: FlightAnalysis, assignments: dict) -> dict:
    """The assignments that bear on this flight: those whose raw channel
    its log carries."""
    available = set(fa.available_channels or [])
    return {raw: target for raw, target in (assignments or {}).items() if raw in available}


def analysis_is_stale(fa: FlightAnalysis, assignments: dict) -> bool:
    """Spec 02 §8: analysed by another engine version, or with channel
    assignments other than the ones now set for the raw channels its log
    carries (Spec 02 v0.15 §6.6)."""
    if fa.provenance.get("engine_version") != __version__:
        return True
    return (fa.provenance.get("channel_assignments") or {}) != applicable_assignments(fa, assignments)


def _load_import_record(ws_dir: Path) -> Optional[dict]:
    """The sender manifest an imported workspace keeps (Spec 02 v0.11 §7.5;
    written by workspace_export.import_workspace). None otherwise."""
    p = ws_dir / "import.json"
    return json.loads(p.read_text()) if p.is_file() else None


def _would_stay_excluded(filename: str, exclusions_data: dict) -> bool:
    """Whether recording an auto-exclusion for this file now would leave it
    excluded: add_auto_exclusion writes only when no entry exists, and an
    existing entry may carry the user's override."""
    return _exclusions._find_entry(exclusions_data, filename) is None or _exclusions.is_excluded(filename, exclusions_data)


def _take_turn(ws_dir, content, folder_path, rel, filename, progress, found_by_key, known, all_sources,
               stale_selected, fresh_by_fid, admission, unreadable_now, new_keys, sender_fids, planned_fids,
               candidates, result, engine_cfg, engine_model, params_now, min_flight_duration_min) -> None:
    """Everything one log's bytes are needed for, while they're in hand."""
    skey = _source_key(content)
    if skey in found_by_key:
        return   # the same file reached through a second folder: the first folder claims it (§5.7)
    found_by_key[skey] = (folder_path, rel, filename)

    if skey in known:
        fid, imp = known[skey]
        if fid in stale_selected:
            index = all_sources[fid].imports.index(imp)
            best = fresh_by_fid.get(fid)
            if best is None or index > best[0]:
                progress("reanalyzing")
                try:
                    fresh = analyze_flight(content, filename, engine_cfg, engine_model, params=params_now)
                except Exception:
                    fresh = None
                fresh_by_fid[fid] = (index, fresh)
        return

    # Not a known fingerprint. Could still be a new export path of an
    # already-known flight (flight_id is a fingerprint of content, not of
    # bytes) — that's only knowable after parsing.
    if skey in admission:
        if _exclusions.add_imported_entry(ws_dir, filename, admission[skey]):
            pass
    exclusions_data = _exclusions.load_exclusions(ws_dir)
    if _exclusions.is_excluded(filename, exclusions_data):
        return  # already recorded as not a flight (Spec 02 §5.11) — nothing new to do
    if skey in unreadable_now and (new_keys is None or skey not in new_keys):
        return  # this engine already found it unreadable — shown as Unreadable, not offered again
    if new_keys is not None and skey not in new_keys:
        result.pending_new_logs.append(_pending_log(skey, folder_path, rel, filename))
        return

    c: dict = {"skey": skey, "meta": (folder_path, rel, filename)}
    candidates.append(c)
    try:
        df, info = load_log_bytes(content, filename)
    except Exception as e:
        c["read_error"] = e
        return
    # What duplicate detection needs, without the frame: the first and last
    # timestamps, the file name and the airframe identity.
    c["stub"] = (df.iloc[[0, -1]][["datetime", "_source_file"]].reset_index(drop=True) if len(df) else df[["datetime", "_source_file"]],
                 info)
    c["rows"] = len(df)
    c["fid"] = _compute_flight_id(flight_fingerprint(df, info))
    c["source_format"] = info.source_format
    try:
        phased = detect_phases(df, verbose=False)
    except Exception as e:
        c["phase_error"] = e
        return
    c["category"], c["reason"] = _exclusions.classify_for_auto_exclusion(phased, min_flight_duration_min)
    del df, phased

    # Analyse now unless the commit step will certainly not need it.
    if c["fid"] in all_sources or c["fid"] in planned_fids:
        return   # a second export path of a flight: recorded as an import, not analysed
    if c["category"] is not None and _would_stay_excluded(filename, exclusions_data):
        return
    if sender_fids is not None and c["fid"] not in sender_fids and _would_stay_excluded(filename, exclusions_data):
        return
    progress("analyzing")
    _analyse(c, content, filename, engine_cfg, engine_model, params_now)
    if "fa" in c and c["fa"] is not None:
        planned_fids.add(c["fid"])


def _analyse(c: dict, content: bytes, filename: str, engine_cfg, engine_model, params_now) -> None:
    try:
        c["fa"] = analyze_flight(content, filename, engine_cfg, engine_model, params=params_now)
    except Exception as e:
        c["fa"], c["analyse_error"] = None, e


async def _analyse_candidate_async(ws_dir, c: dict, sources, manifest, engine_cfg, params_now) -> None:
    folder_path, rel, filename = c["meta"]
    source = sources(_folder_by_path(manifest, folder_path))
    try:
        async with areading(source, rel) as content:
            _analyse(c, content, filename, engine_cfg, manifest.engine_model, params_now)
    except LogUnavailable as e:
        c["fa"], c["analyse_error"] = None, e


def _analyse_candidate(*args, **kwargs):
    """`_analyse_candidate_async` driven to the end at once — for disk sources
    (the server, the CLI); see log_sources.run_now."""
    return run_now(_analyse_candidate_async(*args, **kwargs))


def _uploaded_reanalysis(ws_dir, src, best, engine_cfg, engine_model, params_now, on_progress) -> Optional[FlightAnalysis]:
    """The fresh analysis read_source_bytes' choice gives: the latest
    import whose bytes are available. A folder import's bytes were read on
    its turn (`best`); an uploaded import's live in the workspace."""
    for index in range(len(src.imports) - 1, -1, -1):
        imp = src.imports[index]
        if best is not None and best[0] == index:
            return best[1]
        if imp.log_folder_path == UPLOADED_SOURCE:
            p = ws_dir / "flights" / src.flight_id / imp.filename
            if p.is_file():
                if on_progress:
                    on_progress({"phase": "reanalyzing", "current": 1, "total": 1, "filename": imp.filename})
                try:
                    return analyze_flight(p.read_bytes(), imp.filename, engine_cfg, engine_model, params=params_now)
                except Exception:
                    return None
    return None


def _folder_by_path(manifest: "WorkspaceManifest", folder_path: str) -> "LogFolder":
    """The manifest's folder for an import's log_folder_path (or a bare one
    for a folder no longer in the manifest)."""
    return next((lf for lf in manifest.log_folders if lf.path == folder_path), None) or LogFolder(path=folder_path)


async def scan_workspace_async(
    ws_dir: Path, registry_path: Optional[Path] = None, quiet: bool = True,
    on_progress: Optional[Callable[[dict], None]] = None,
    new_keys: Optional[set] = None, reanalyze_ids: Optional[set] = None,
    sources: Callable = DISK,
) -> ScanResult:
    """
    Spec 03 v0.17 §5.1 (Sync asks before it analyses): `new_keys` limits
    which newly found logs (by source_key) are parsed and analysed, and
    `reanalyze_ids` which stale flights are re-analysed; None means all
    (the behaviour before v0.17), an empty set means none — discovery
    only. The bookkeeping that costs no analysis (moved/renamed files,
    missing and recovered flights, unreachable folders) always runs. What
    was found but left alone comes back in pending_new_logs /
    pending_reanalysis_flight_ids.

    The core Spec 02 operation: reconcile `flights/` against what
    `manifest.log_folders` currently contains.

    on_progress, if given, is called with {"phase", "current", "total",
    "filename"} at each step of the three costly per-file loops below
    (reading, analyzing, reanalyzing) — an initial sync of a large folder
    can genuinely take minutes (every new file gets parsed AND fully
    analyzed), and the caller (server.py's op_scan_workspace) uses this
    to let a polling client show real "processing log X of N" progress
    instead of one opaque multi-minute spinner.

    Two distinct failure paths, not one generic "can't find it" (§5.5):
    a folder that doesn't exist right now is one `unreachable_folders`
    entry and nothing under it is touched; a flight whose fingerprint
    isn't found in any *reachable* folder is evaluated for Missing.
    Flights with at least one import from a folder that's unreachable
    *this scan* are left alone rather than re-evaluated — we didn't
    actually get to check the one place it might still be, so flagging
    it missing here would be a false positive, not a real finding. This
    is the conservative reading of a case the spec doesn't spell out.

    `registry_path` defaults to `resolve_registry_path()` (the install's
    real registry); pass it explicitly in tests/tools pointed at an
    isolated registry so the flight/folder counts synced back to it land
    in the right file.

    A newly-found file that's a ground session, short flight, or corrupt
    log (Spec 02 §5.11.2)
    never becomes a flight_id at all — it's recorded to exclusions.json
    and left out entirely, the same as loader.py's load_directory()
    (CLI/notebook path) already does. Before this, a workspace built by
    folder-scan (the web UI's path) had no such filtering at all.
    """
    manifest = load_manifest(ws_dir)
    engine_cfg = load_engine_config(manifest.engine_model)  # locked, always this (§5.6) — never per-log
    exclusions_data = _exclusions.load_exclusions(ws_dir)
    min_flight_duration_min = resolve_min_flight_duration_min()
    params_now = analysis_params(ws_dir)
    assignments_now = load_workspace_settings(ws_dir).channel_assignments

    result = ScanResult()

    # Known fingerprints already in the workspace, and the flight/import
    # record each belongs to.
    known: dict[str, tuple[str, ImportRecord]] = {}
    all_sources: dict[str, FlightSources] = {}
    known_idents: set[str] = set()
    for fid in list_flight_ids(ws_dir):
        src = load_sources(ws_dir, fid)
        if src is None:
            continue
        all_sources[fid] = src
        for imp in src.imports:
            known[imp.source_key] = (fid, imp)
        fa = load_flight_analysis(ws_dir, fid)
        if fa is not None:
            ident = (fa.header or {}).get("aircraft", {}).get("ident")
            if ident:
                known_idents.add(ident)

    primary_ident = manifest.primary_tail_number or (sorted(known_idents)[0] if known_idents else None)

    # Spec 02 v0.11 §7.5 — an imported workspace: the sender's admission
    # record (keyed by source_key) applies to these files under their own
    # names, and a log whose flight isn't in the sender's manifest is held
    # out until included.
    import_record = _load_import_record(ws_dir)
    sender_fids: Optional[set] = None
    admission: dict = {}
    if import_record is not None:
        sender_fids = {f["flight_id"] for f in import_record.get("manifest", [])}
        admission = {a["source_key"]: a for a in import_record.get("admission", []) if a.get("source_key")}

    unreadable_now = current_unreadable(ws_dir)

    # Flights whose stored analysis is stale and that this scan may
    # re-analyse: re-run from the bytes read_source_bytes would choose — the
    # latest import whose bytes are available (Spec 02 §8).
    stale_selected: dict[str, FlightAnalysis] = {}
    for fid, src in all_sources.items():
        fa = load_flight_analysis(ws_dir, fid)
        if fa is not None and analysis_is_stale(fa, assignments_now) and (reanalyze_ids is None or fid in reanalyze_ids):
            stale_selected[fid] = fa
    fresh_by_fid: dict[str, tuple[int, Optional[FlightAnalysis]]] = {}  # fid -> (import index, fresh or None)

    # ── 1. List every folder, then 2. take each log in turn ────────────────
    # Spec 04 v0.4 §9.3: list first; read each log's bytes only on its turn
    # and release them after, so a page-supplied source can stream a folder.
    # Everything that needs the bytes happens during the turn; what the
    # rest of the scan needs is kept as a small record.
    unreachable_folder_paths: set[str] = set()
    listings: list[tuple["LogFolder", LogSource, list[LogEntry]]] = []
    for lf in manifest.log_folders:
        source = sources(lf)
        entries = (await source.alist())
        if entries is None:
            lf.reachable = False
            unreachable_folder_paths.add(lf.path)
            result.unreachable_folders.append(lf.path)
            continue
        lf.reachable = True
        lf.last_scanned_at = _now()
        listings.append((lf, source, entries))
    total = sum(len(entries) for _lf, _s, entries in listings)

    found_by_key: dict[str, tuple[str, str, str]] = {}  # source_key -> (folder_path, rel, filename), first folder wins (§5.7)
    candidates: list[dict] = []          # new logs to admit, in listing order
    planned_fids: set[str] = set()       # new flights this scan will analyse
    turn = 0
    for lf, source, entries in listings:
        for entry in entries:
            turn += 1
            rel, filename = entry.relative_path, entry.name

            def progress(phase: str) -> None:
                if on_progress:
                    on_progress({"phase": phase, "current": turn, "total": total, "filename": filename})

            progress("reading")
            try:
                async with areading(source, rel) as content:
                    _take_turn(ws_dir, content, lf.path, rel, filename, progress, found_by_key, known,
                               all_sources, stale_selected, fresh_by_fid, admission, unreadable_now, new_keys,
                               sender_fids, planned_fids, candidates, result, engine_cfg, manifest.engine_model,
                               params_now, min_flight_duration_min)
            except LogUnavailable:
                continue   # listed but not readable now — as a file that vanished mid-walk

    # ── 3. Commit, in the order the scan has always written ────────────────
    for skey, (folder_path, rel, filename) in found_by_key.items():
        if skey not in known:
            continue
        fid, imp = known[skey]
        if imp.log_folder_path != folder_path or imp.relative_path != rel or imp.filename != filename:
            # Rename/move under a known fingerprint — rematch, not a new
            # import (§5.7).
            imp.log_folder_path, imp.relative_path, imp.filename = folder_path, rel, filename
            save_sources(ws_dir, all_sources[fid])
            result.rematched_flight_ids.append(fid)
        if all_sources[fid].missing:
            all_sources[fid].missing = False
            save_sources(ws_dir, all_sources[fid])
            result.recovered_flight_ids.append(fid)

    meta = {c["skey"]: c["meta"] for c in candidates}
    parsed = []
    for c in candidates:
        if c.get("read_error") is not None:
            # Spec 03 §5.1 "Unreadable": recorded with its reason, shown on
            # Flights — never left looking like it waits for analysis.
            _unreadable(ws_dir, result, meta, c["skey"], c["meta"][2], c["read_error"], "read")
            continue
        parsed.append(c)

    # Only an OVERLAP duplicate group (different flight_id — different
    # fingerprint, but the same physical flight per the time-overlap
    # heuristic) is dropped here (Spec 01 R5's INGEST_DUPLICATE_OF case),
    # keeping the export with the most rows. An EXACT group (same
    # flight_id) is deliberately kept: same flight_id means "merge into one
    # flights/<id>", which the loop below does by appending a second
    # `imports[]` entry instead of re-analyzing (§6.2's second export path).
    dup_groups_excluded: set[str] = set()
    if len(parsed) > 1:
        overlap_groups = [g for g in find_duplicate_flights([c["stub"] for c in parsed]) if g.match_kind == "overlap"]
        if overlap_groups:
            by_file = {c["meta"][2]: c for c in parsed}
            for group in overlap_groups:
                group_cands = [by_file[f] for f in group.files if f in by_file]
                if len(group_cands) < 2:
                    continue
                keep_name = max(group_cands, key=lambda c: c["rows"])["meta"][2]
                for c in parsed:
                    if c["meta"][2] in group.files and c["meta"][2] != keep_name:
                        dup_groups_excluded.add(c["skey"])
                        result.excluded.append({"flight_id": c["fid"], "reason": f"duplicate export ({c['meta'][2]})"})

    for c in parsed:
        skey, filename = c["skey"], c["meta"][2]
        if skey in dup_groups_excluded:
            continue
        if sender_fids is not None:
            if c["fid"] not in sender_fids and c["fid"] not in all_sources:
                _exclusions.add_auto_exclusion(ws_dir, filename, "not_in_sender", _exclusions.NOT_IN_SENDER_REASON)
                if _exclusions.is_excluded(filename, _exclusions.load_exclusions(ws_dir)):
                    result.auto_excluded.append({"filename": filename, "category": "not_in_sender",
                                                 "reason": _exclusions.NOT_IN_SENDER_REASON})
                    continue
                # else: the user included it — an ordinary flight from here on.

        if c.get("phase_error") is not None:
            _unreadable(ws_dir, result, meta, skey, filename, c["phase_error"], "analyse")
            continue
        if c["category"] is not None:
            _exclusions.add_auto_exclusion(ws_dir, filename, c["category"], c["reason"])
            # add_auto_exclusion() is a no-op if an entry already exists
            # — including one a user already overrode (user_override:
            # true). Re-check the current on-disk state, so an override
            # takes effect immediately, not just on the *next* scan.
            if _exclusions.is_excluded(filename, _exclusions.load_exclusions(ws_dir)):
                result.auto_excluded.append({"filename": filename, "category": c["category"], "reason": c["reason"]})
                continue
            # else: overridden — falls through and becomes a flight below.

        fid = c["fid"]
        folder_path, rel, filename = c["meta"]
        imp = ImportRecord(
            source_key=skey, log_folder_path=folder_path, relative_path=rel,
            filename=filename, imported_at=_now(), via=via_for_source_format(c["source_format"]),
        )

        if fid in all_sources:
            # A new export path of a flight already in this workspace
            # (Spec 01 §6.2's "same flight, two export paths").
            all_sources[fid].imports.append(imp)
            save_sources(ws_dir, all_sources[fid])
            result.rematched_flight_ids.append(fid)
            continue

        if "fa" not in c:
            # Not analysed on its turn (it looked as if it would stay
            # excluded, or another file seemed to be this flight). Rare:
            # read it once more.
            await _analyse_candidate_async(ws_dir, c, sources, manifest, engine_cfg, params_now)
        if c.get("analyse_error") is not None:
            # One log the engine can't analyse must not abort the whole sync.
            _unreadable(ws_dir, result, meta, skey, filename, c["analyse_error"], "analyse")
            continue
        fa = c["fa"]
        # fa.flight_id is computed the same way as `fid` above (same
        # fingerprint function); use fa's own value as the source of truth.
        ident = (fa.header or {}).get("aircraft", {}).get("ident")
        different_tail = ident if (ident and primary_ident and ident != primary_ident) else None
        if primary_ident is None and ident:
            primary_ident = ident  # first flight this workspace has ever seen sets it

        save_flight_analysis(ws_dir, fa)
        new_sources = FlightSources(flight_id=fa.flight_id, imports=[imp], different_tail_number=different_tail)
        save_sources(ws_dir, new_sources)
        all_sources[fa.flight_id] = new_sources
        result.new_flight_ids.append(fa.flight_id)

    # Missing evaluation: any known flight none of whose fingerprints were
    # found this scan, and all of whose origin folders were reachable this
    # scan (so the absence is real, not just "behind an unreachable folder").
    for fid, src in all_sources.items():
        if fid in result.new_flight_ids:
            continue
        if any(imp.log_folder_path == UPLOADED_SOURCE for imp in src.imports):
            # Uploaded, not scanned — no folder for this scan to have
            # found it missing from; its bytes live in the workspace.
            continue
        any_found = any(imp.source_key in found_by_key for imp in src.imports)
        all_folders_reachable = all(imp.log_folder_path not in unreachable_folder_paths for imp in src.imports)
        if not any_found and all_folders_reachable and not src.missing:
            src.missing = True
            save_sources(ws_dir, src)
            result.now_missing_flight_ids.append(fid)

    # Re-analysis: a known flight whose stored analysis predates the
    # engine actually running (or the channel assignments now set) — re-run
    # from the latest import whose bytes were available, read on that log's
    # turn above, or the workspace's own copy of an uploaded log.
    for fid, src in all_sources.items():
        if fid in result.new_flight_ids or src.missing:
            continue
        fa = load_flight_analysis(ws_dir, fid)
        if fa is None or not analysis_is_stale(fa, assignments_now):
            continue
        if reanalyze_ids is not None and fid not in reanalyze_ids:
            result.pending_reanalysis_flight_ids.append(fid)
            continue
        fresh = _uploaded_reanalysis(ws_dir, src, fresh_by_fid.get(fid), engine_cfg, manifest.engine_model, params_now,
                                     on_progress)
        if fresh is None:
            continue   # nothing readable, or it failed: leave the stale analysis in place rather than lose it
        if fresh.flight_id != fid:
            # Source bytes changed under an unchanged path/filename (a
            # different flight now, by fingerprint) — not safely
            # reanalyzable in place; leave the stored one as-is.
            continue
        save_flight_analysis(ws_dir, fresh)
        migrate_limit_annotations(ws_dir, fa, fresh)
        result.reanalyzed_flight_ids.append(fid)

    # Update manifest + registry.
    if manifest.primary_tail_number is None and primary_ident:
        manifest.primary_tail_number = primary_ident
    if __version__ not in manifest.engine_version_seen:
        manifest.engine_version_seen.append(__version__)
    manifest.flight_count = len(list_flight_ids(ws_dir))
    manifest.updated_at = _now()
    save_manifest(ws_dir, manifest)

    effective_registry_path = registry_path if registry_path is not None else resolve_registry_path()
    if effective_registry_path.exists():
        _touch_registry_entry(
            effective_registry_path, manifest.id,
            flight_count=manifest.flight_count, log_folder_count=len(manifest.log_folders),
            last_opened_at=_now(),
        )

    return result


def scan_workspace(*args, **kwargs):
    """`scan_workspace_async` driven to the end at once — for disk sources
    (the server, the CLI); see log_sources.run_now."""
    return run_now(scan_workspace_async(*args, **kwargs))


async def reclassify_existing_flights_async(ws_dir: Path, sources: Callable = DISK) -> list[dict]:
    """
    One-time migration helper, not run automatically by scan_workspace():
    re-applies classify_for_auto_exclusion() to every flight already in
    the workspace, for a workspace whose flights/ was built before that
    classifier existed in scan_workspace() at all (every folder-scanned
    workspace up to that fix ingested ground sessions, short flights,
    and files with a corrupt internal time gap as real flights, with no
    filtering whatsoever).

    A flight that now classifies as excludable is removed exactly like
    remove_flight() removes any other flight, and a fresh exclusions.json
    entry is written *before* the removal — so a rescan right after
    (whose "known fingerprints" check no longer finds this flight_id,
    since its flights/<id> is gone) re-discovers the same source file,
    re-classifies it the same way, and finds it already excluded rather
    than silently re-ingesting it. Returns one dict per flight removed:
    {"flight_id", "filename", "category", "reason"}.

    Not wired into scan_workspace()'s regular per-scan loop deliberately
    — every future scan only classifies genuinely NEW files, matching
    load_directory()'s "classified once, not re-litigated every run"
    model. Re-checking every already-known flight on every routine Sync
    would be a real, unbounded, unnecessary cost.
    """
    min_flight_duration_min = resolve_min_flight_duration_min()
    reclassified: list[dict] = []

    for fid in list_flight_ids(ws_dir):
        src = load_sources(ws_dir, fid)
        if src is None:
            continue
        found = (await read_source_bytes_async(ws_dir, src, sources))
        if found is None:
            continue  # source unreachable right now — leave it alone, not a false positive
        content, filename = found
        try:
            df, info = load_log_bytes(content, filename)
        except Exception:
            continue
        df = detect_phases(df, verbose=False)
        category, reason = _exclusions.classify_for_auto_exclusion(df, min_flight_duration_min)
        if category is None:
            continue

        _exclusions.add_auto_exclusion(ws_dir, filename, category, reason)
        if not _exclusions.is_excluded(filename, _exclusions.load_exclusions(ws_dir)):
            continue  # this exact filename was already overridden — leave it as a flight

        remove_flight(ws_dir, fid)
        reclassified.append({"flight_id": fid, "filename": filename, "category": category, "reason": reason})

    if reclassified:
        manifest = load_manifest(ws_dir)
        manifest.flight_count = len(list_flight_ids(ws_dir))
        manifest.updated_at = _now()
        save_manifest(ws_dir, manifest)

    return reclassified


def reclassify_existing_flights(*args, **kwargs):
    """`reclassify_existing_flights_async` driven to the end at once — for disk sources
    (the server, the CLI); see log_sources.run_now."""
    return run_now(reclassify_existing_flights_async(*args, **kwargs))


def engine_version_diagnostic(manifest: WorkspaceManifest) -> Optional[dict]:
    """
    Spec 02 §6.1: a workspace opened by an engine *older* than the newest
    version it has already seen is a downgrade — a host-level diagnostic,
    not one of Spec 01's engine diagnostics (this one belongs to the
    workspace, not the core).
    """
    def _tuple(v: str) -> tuple:
        try:
            return tuple(int(p) for p in v.split("."))
        except ValueError:
            return (0,)

    if not manifest.engine_version_seen:
        return None
    newest_seen = max(manifest.engine_version_seen, key=_tuple)
    if _tuple(__version__) < _tuple(newest_seen):
        return {
            "code": "WORKSPACE_NEWER_THAN_ENGINE",
            "severity": "warn",
            "message": f"This workspace was last written by engine {newest_seen}, "
                       f"newer than the running {__version__}.",
        }
    return None


# ── Annotations (Spec 02 §6.5, R3) ──────────────────────────────────────────
# annotations.json's shape was already fully specified — id/flight_id/ref/
# note/created_at/updated_at — just never implemented anywhere. One store
# per workspace, flat list; the host (server.py) does the flight_id/ref
# filtering, matching R3's "the engine only attaches."

_ANNOTATIONS_VERSION = "1"


def load_annotations(ws_dir: Path) -> dict:
    f = ws_dir / "annotations.json"
    if not f.exists():
        return {"version": _ANNOTATIONS_VERSION, "annotations": []}
    return json.loads(f.read_text())


def save_annotation(ws_dir: Path, flight_id: str, ref: dict, note: str, annotation_id: Optional[str] = None) -> dict:
    """Create (annotation_id is None) or update (edits note + sets
    updated_at, leaves created_at/flight_id/ref alone). Returns the
    saved annotation dict."""
    store = load_annotations(ws_dir)
    now = _now()
    if annotation_id:
        for a in store["annotations"]:
            if a["id"] == annotation_id:
                a["note"] = note
                a["updated_at"] = now
                _write_json(ws_dir / "annotations.json", store)
                return a
        # id given but not found — fall through and create fresh rather
        # than silently discarding the pilot's note.
    annotation = {
        "id": _new_id("ann"),
        "flight_id": flight_id,
        "ref": ref,
        "note": note,
        "created_at": now,
    }
    store["annotations"].append(annotation)
    _write_json(ws_dir / "annotations.json", store)
    return annotation


def delete_annotation(ws_dir: Path, annotation_id: str) -> bool:
    store = load_annotations(ws_dir)
    before = len(store["annotations"])
    store["annotations"] = [a for a in store["annotations"] if a["id"] != annotation_id]
    if len(store["annotations"]) == before:
        return False
    _write_json(ws_dir / "annotations.json", store)
    return True


def annotations_for_flight(ws_dir: Path, flight_id: str) -> list[dict]:
    return [a for a in load_annotations(ws_dir)["annotations"] if a["flight_id"] == flight_id]


def migrate_limit_annotations(ws_dir: Path, old: FlightAnalysis, fresh: FlightAnalysis) -> int:
    """
    Spec 09 Q6: before Spec 09, `limit_exceedances` had one insight per
    event, identified by a hash of its message text; now there is one per
    limit per flight, identified by limit (operations._limit_insight_id).
    On re-analysis, re-attach each note on an old per-event insight to
    the new per-limit insight for the same flight and limit. Several
    notes landing on one insight are joined into one, oldest first.
    Returns the number of notes moved. A no-op for an `old` analysis that
    already has limit ids.
    """
    from .contract import content_hash
    from .operations import _format_exceedance_text, _limit_insight_id

    if not old.exceedances or any(e.get("limit_id") for e in old.exceedances) or not fresh.limits:
        return 0

    def _match_limit_id(e: dict) -> Optional[str]:
        candidates = [lim for lim in fresh.limits
                      if lim["param"] == e["param"] and lim["limit_type"] == e["limit_type"]
                      and abs(lim["limit_value"] - e["limit_value"]) < 1e-9]
        if len(candidates) > 1:
            candidates = [lim for lim in candidates if lim["label"] == e["label"]] or candidates[:1]
        return candidates[0]["id"] if candidates else None

    new_id_by_old_id = {}
    for e in old.exceedances:
        text = f"⚠ {_format_exceedance_text(e)}"
        old_id = content_hash({"flight_id": old.flight_id, "topic_id": "limit_exceedances",
                               "trigger": "threshold", "text": text})[:16]
        lid = _match_limit_id(e)
        if lid:
            new_id_by_old_id[old_id] = _limit_insight_id(fresh.flight_id, lid, "exceedance")

    store = load_annotations(ws_dir)
    moved = 0
    kept: list[dict] = []
    by_new_id: dict[str, dict] = {
        a["ref"]["insight_id"]: a for a in store["annotations"]
        if a["flight_id"] == old.flight_id and a.get("ref", {}).get("kind") == "insight"
    }
    for a in sorted(store["annotations"], key=lambda a: a.get("created_at", "")):
        ref = a.get("ref", {})
        new_id = new_id_by_old_id.get(ref.get("insight_id")) if (
            a["flight_id"] == old.flight_id and ref.get("kind") == "insight") else None
        if new_id is None:
            kept.append(a)
            continue
        moved += 1
        target = by_new_id.get(new_id)
        if target is None:
            a["ref"] = {"kind": "insight", "insight_id": new_id}
            a["updated_at"] = _now()
            by_new_id[new_id] = a
            kept.append(a)
        else:
            target["note"] = f"{target['note']}\n\n{a['note']}"
            target["updated_at"] = _now()
    if moved:
        store["annotations"] = sorted(kept, key=lambda a: a.get("created_at", ""))
        _write_json(ws_dir / "annotations.json", store)
    return moved


# ── Journal (Spec 14 §6, v0.10) ─────────────────────────────────────────────
# journal.json, next to annotations.json: the register of decisions in
# force. One entry per live decision, keyed by its source record
# (JOURNAL_KEY below): reversing the decision removes the entry, editing
# it updates the entry in place. History is not kept here — filters keep
# their own (Spec 09 §9), and since Spec 14 v0.13 there is no Settings
# changelog (an old settings_changelog.json is left on disk, unread). The
# counted effect is computed live by the server when the page opens;
# nothing about it is stored.
#
# Entry keys, by kind:
#   limit_filter    filter id            exclusion       flight id
#   rule_edit       topic id             reference_pin   metric id
#   disabled_topic  topic id             annotation      annotation id
#   changed_setting setting id (v0.13: "outlier_z_threshold", "recent_window",
#                   "outlier_z_threshold_overrides:<metric>", …)
#   acknowledged_insight  insight id (Spec 11; nothing writes it yet)

_JOURNAL_VERSION = "2"

# server.py runs a ThreadingHTTPServer — one thread per request — so two
# clients opening the same workspace at once (Spec 14 §9 acceptance 12)
# can import concurrently in this one process. One process-wide RLock
# around every journal.json read-modify-write keeps that to one entry per
# source record.
_JOURNAL_LOCK = threading.RLock()

_UNSET: Any = object()


def migrate_journal_store(store: dict) -> tuple[dict, dict, dict]:
    """v1 (a log: open/closed entries, one per action) -> v2 (a register).
    Closed entries are dropped; several open entries for the same key
    collapse to the most recent one (created_at: the earliest of them).
    Returns (store, report, id_map) — id_map sends each merged-away id to
    the surviving entry's id, so reference-change markers can follow."""
    entries = store.get("entries", [])
    open_entries = [e for e in entries if e.get("status", "open") != "closed"]
    dropped_closed = len(entries) - len(open_entries)
    groups: dict[tuple, list[dict]] = {}
    for e in open_entries:
        groups.setdefault((e["kind"], e.get("ref_id")), []).append(e)
    out, id_map, merged = [], {}, 0
    for group in groups.values():
        group.sort(key=lambda e: e.get("updated_at") or e.get("at") or "")
        survivor = group[-1]
        merged += len(group) - 1
        for e in group[:-1]:
            id_map[e["id"]] = survivor["id"]
        created = min(e.get("created_at") or e.get("at") or "" for e in group)
        out.append({
            "id": survivor["id"], "kind": survivor["kind"], "ref_id": survivor.get("ref_id"),
            "what": survivor.get("what"), "where": survivor.get("where"),
            "reason": survivor.get("reason"), "note": survivor.get("note"),
            "created_at": created, "updated_at": survivor.get("updated_at") or survivor.get("at") or created,
        })
    report = {"dropped_closed": dropped_closed, "merged": merged, "kept": len(out), "at": _now()}
    return {"version": _JOURNAL_VERSION, "entries": out, "migrated_from_v1": report}, report, id_map


def _remap_reference_change_causes(ws_dir: Path, id_map: dict, dropped_ids: set) -> None:
    """After migration: markers caused by a merged-away entry point at its
    survivor; markers still open for a dropped (closed) entry resolve —
    the decision that caused them is no longer in force."""
    store = load_reference_changes(ws_dir)
    changed = False
    for m in store["markers"]:
        cause = m.get("cause_journal_entry_id")
        if cause in id_map:
            m["cause_journal_entry_id"] = id_map[cause]
            changed = True
        elif cause in dropped_ids and not m.get("resolved"):
            m["resolved"] = True
            changed = True
    if changed:
        _write_json(ws_dir / "reference_changes.json", store)


def load_journal(ws_dir: Path) -> dict:
    f = ws_dir / "journal.json"
    if not f.exists():
        return {"version": _JOURNAL_VERSION, "entries": []}
    store = json.loads(f.read_text())
    if store.get("version") == _JOURNAL_VERSION:
        return store
    with _JOURNAL_LOCK:
        store = json.loads(f.read_text())
        if store.get("version") == _JOURNAL_VERSION:
            return store
        before_ids = {e["id"] for e in store.get("entries", [])}
        migrated, _report, id_map = migrate_journal_store(store)
        kept = {e["id"] for e in migrated["entries"]}
        _remap_reference_change_causes(ws_dir, id_map, before_ids - kept - set(id_map))
        _write_json(f, migrated)
        return migrated


def get_journal_entry(ws_dir: Path, *, kind: Optional[str] = None, ref_id: Optional[str] = None,
                      entry_id: Optional[str] = None) -> Optional[dict]:
    for e in load_journal(ws_dir)["entries"]:
        if entry_id is not None and e["id"] == entry_id:
            return e
        if entry_id is None and e["kind"] == kind and e.get("ref_id") == ref_id:
            return e
    return None


def upsert_journal_entry(
    ws_dir: Path, *, kind: str, ref_id: str, what: str, where: Optional[dict] = None,
    reason: Any = _UNSET, note: Any = _UNSET, at: Optional[str] = None, create_only: bool = False,
) -> dict:
    """The decision `kind`/`ref_id` is in force: create its entry, or
    update the existing one in place (current values, updated_at; a
    confirmed notice is cleared — the decision changed). `create_only`
    leaves an existing entry untouched (the import)."""
    with _JOURNAL_LOCK:
        store = load_journal(ws_dir)
        now = at or _now()
        for e in store["entries"]:
            if e["kind"] == kind and e.get("ref_id") == ref_id:
                if create_only:
                    return e
                e["what"] = what
                if where is not None:
                    e["where"] = where
                if reason is not _UNSET:
                    e["reason"] = reason
                if note is not _UNSET:
                    e["note"] = note
                e["updated_at"] = _now()
                e.pop("confirmed", None)
                _write_json(ws_dir / "journal.json", store)
                return e
        entry = {
            "id": _new_id("jnl"), "kind": kind, "ref_id": ref_id, "what": what, "where": where,
            "reason": None if reason is _UNSET else reason, "note": None if note is _UNSET else note,
            "created_at": now, "updated_at": now,
        }
        store["entries"].append(entry)
        _write_json(ws_dir / "journal.json", store)
        return entry


def remove_journal_entry(ws_dir: Path, *, kind: str, ref_id: str) -> Optional[dict]:
    """The decision is no longer in force: remove its entry, and resolve
    the reference-change markers it caused."""
    with _JOURNAL_LOCK:
        store = load_journal(ws_dir)
        hit = next((e for e in store["entries"] if e["kind"] == kind and e.get("ref_id") == ref_id), None)
        if hit is None:
            return None
        store["entries"] = [e for e in store["entries"] if e is not hit]
        _write_json(ws_dir / "journal.json", store)
    resolve_reference_changes_for_cause(ws_dir, hit["id"])
    return hit


def confirm_journal_notice(ws_dir: Path, entry_id: str, notice: str) -> Optional[dict]:
    """Spec 14 §6.2: the pilot has seen a change notice and keeps the
    decision as it is; the notice stays cleared until the decision is
    edited (upsert clears it)."""
    with _JOURNAL_LOCK:
        store = load_journal(ws_dir)
        for e in store["entries"]:
            if e["id"] == entry_id:
                e.setdefault("confirmed", {})[notice] = _now()
                _write_json(ws_dir / "journal.json", store)
                return e
        return None


def source_filename(ws_dir: Path, flight_id: str) -> Optional[str]:
    """The log's real file name for display: the workspace's own copy if
    it kept one, else the last import recorded in sources.json."""
    d = ws_dir / "flights" / flight_id
    if d.is_dir():
        others = [p.name for p in d.iterdir() if p.name not in ("analysis.json", "sources.json")]
        if others:
            return others[0]
    src = load_sources(ws_dir, flight_id)
    return src.imports[-1].filename if src and src.imports else None


def reconcile_journal(ws_dir: Path, *, active_rules: Optional[dict] = None, shipped_rules: Optional[dict] = None) -> None:
    """
    Make the register match the decisions actually in force (Spec 14 §6,
    v0.10). Imports a decision with no entry — filters, exclusions, pins
    and annotations made before journal.json existed, and rule edits /
    disabled topics found in rules/active.json — as an ordinary entry
    dated to its own record where it has one, else to now; and removes an
    entry whose decision no longer exists (reversed outside Journal, or
    the store edited by hand). Idempotent and keyed on the source record,
    and one critical section, so two clients opening a workspace at once
    produce one entry per decision (acceptance 12).
    """
    with _JOURNAL_LOCK:
        live: dict[tuple, dict] = {}
        for f in load_filters(ws_dir)["filters"]:
            live[("limit_filter", f["id"])] = {
                "what": f"Filter: {target_label(f['target'])}", "where": {"target": f["target"]},
                "note": f.get("note"), "at": f.get("created_at"),
            }
        for a in load_annotations(ws_dir)["annotations"]:
            live[("annotation", a["id"])] = {
                "what": a["note"][:80], "where": {"flight_id": a["flight_id"], "ref": a["ref"]}, "at": a.get("created_at"),
            }
        selection = load_selection(ws_dir)
        for metric_id, ref in ((selection.baseline_config or {}).get("pinned_references") or {}).items():
            live[("reference_pin", metric_id)] = {
                "what": metric_id, "where": {"metric_id": metric_id}, "note": ref.get("label"), "at": ref.get("set_at"),
            }
        # Spec 14 v0.14 §5.3: each channel assignment is a changed setting.
        for raw, target in load_workspace_settings(ws_dir).channel_assignments.items():
            ref = f"channel_assignment:{raw}"
            live[("changed_setting", ref)] = {
                "what": channel_assignment_title(raw, target), "where": {"setting": ref, "tab": "engine"},
            }
        for d in setting_decisions(selection.baseline_config):
            live[("changed_setting", d["ref_id"])] = {
                "what": f"Setting: {d['label']}", "where": {"setting": d["ref_id"], "tab": "reference"},
            }
        for e in selection.excluded:
            fid = e["flight_id"]
            live[("exclusion", fid)] = {
                "what": source_filename(ws_dir, fid) or fid, "where": {"flight_id": fid}, "reason": e.get("reason"),
            }
        if active_rules is not None and shipped_rules is not None:
            for topic_id, kind in rule_decisions(active_rules, shipped_rules):
                live[(kind, topic_id)] = {"what": f"Rule: {topic_id}", "where": {"topic_id": topic_id}}

        store = load_journal(ws_dir)
        stale = [e for e in store["entries"]
                 if e["kind"] in _RECONCILED_KINDS and (e["kind"], e.get("ref_id")) not in live
                 and (e["kind"] not in ("rule_edit", "disabled_topic") or active_rules is not None)]
        for e in stale:
            remove_journal_entry(ws_dir, kind=e["kind"], ref_id=e["ref_id"])
        for (kind, ref_id), d in live.items():
            upsert_journal_entry(
                ws_dir, kind=kind, ref_id=ref_id, what=d["what"], where=d.get("where"),
                reason=d.get("reason"), note=d.get("note"), at=d.get("at"), create_only=True,
            )


_RECONCILED_KINDS = ("limit_filter", "annotation", "reference_pin", "exclusion", "rule_edit", "disabled_topic",
                     "changed_setting")


def strip_rule_comments(x: Any) -> Any:
    """Drop "_comment"-style keys at every level — they aren't settings."""
    if isinstance(x, dict):
        return {k: strip_rule_comments(v) for k, v in x.items() if not k.startswith("_")}
    if isinstance(x, list):
        return [strip_rule_comments(v) for v in x]
    return x


def _rule_body(topic: Optional[dict]) -> dict:
    """A topic's rule without its enabled flag or comments — what a
    rule_edit entry is about (enabled is the disabled_topic entry's)."""
    return {k: v for k, v in strip_rule_comments(topic or {}).items() if k != "enabled"}


def rule_decisions(active_rules: dict, shipped_rules: dict) -> list[tuple[str, str]]:
    """(topic_id, kind) for every rule decision in force: "rule_edit" when
    a topic's rule differs from shipped, "disabled_topic" when the pilot
    has turned off a topic shipped enabled."""
    out = []
    shipped = shipped_rules.get("rules", {})
    for topic_id, topic in active_rules.get("rules", {}).items():
        base = shipped.get(topic_id)
        if base is None:
            continue
        if _rule_body(topic) != _rule_body(base):
            out.append((topic_id, "rule_edit"))
        if not topic.get("enabled", True) and base.get("enabled", True):
            out.append((topic_id, "disabled_topic"))
    return out


# ── Changed settings (Spec 14 v0.13 §5, §6.1) ───────────────────────────────
# A results-affecting setting that differs from shipped is a decision in
# force, derived like a rule edit: one entry per setting, per-metric
# values one per metric. The settings are FleetSelection.baseline_config's
# fields; pinned_references are not settings (they are reference_pin
# entries). Display-only settings (units, reopen-on-launch, anonymise
# default, chart presets, tail-number aliases) never appear here.

# (setting id, baseline_config keys, label). The recent window is one
# setting made of three numbers.
_SCALAR_SETTINGS = (
    ("outlier_z_threshold", ("outlier_z_threshold",), "Outlier z-threshold"),
    ("recent_window", ("recent_window_hours", "recent_window_min_flights", "recent_window_max_flights"), "Recent window"),
    ("om_margin_fraction", ("om_margin_fraction",), "OM margin fraction"),
    ("membership", ("membership",), "Reference membership"),
    ("frequency_delta", ("frequency_delta",), "Event-frequency drift threshold"),
)
# (baseline_config field, label): a {metric_id: value} map, shipped empty.
_PER_METRIC_SETTINGS = (
    ("outlier_z_threshold_overrides", "Outlier z-threshold"),
    ("band_kind_by_metric", "Weather band"),
)


def channel_assignment_title(raw: str, target: str, sources: Optional[list] = None) -> str:
    """"Log channels — analog 7 is CO ppm (AXIS)" (Spec 14 v0.14 §5.3)."""
    from .channels import CHANNEL_REGISTRY
    cdef = CHANNEL_REGISTRY.get(target)
    name = target if cdef is None else (f"{cdef.label} {cdef.unit}" if cdef.unit and cdef.unit not in cdef.label else cdef.label)
    src = f" ({', '.join(sources)})" if sources else ""
    return f"Log channels — analog {raw.rsplit('_', 1)[-1]} is {name}{src}"


def shipped_baseline_config() -> dict:
    """Every setting at its shipped value."""
    from .filters import FREQUENCY_DELTA
    return {**DEFAULT_BASELINE_CONFIG, "frequency_delta": FREQUENCY_DELTA}


def setting_decisions(baseline_config: Optional[dict]) -> list[dict]:
    """Each setting that differs from shipped: {ref_id, label, field,
    metric_id, current, shipped}. `current`/`shipped` hold the setting's
    keys; a per-metric value's shipped is None (no per-metric value: it
    follows the global setting). An absent key is at shipped."""
    bc = baseline_config or {}
    shipped = shipped_baseline_config()
    out = []
    for ref_id, keys, label in _SCALAR_SETTINGS:
        current = {k: bc.get(k, shipped[k]) for k in keys}
        base = {k: shipped[k] for k in keys}
        if current != base:
            out.append({"ref_id": ref_id, "label": label, "field": None, "metric_id": None,
                        "current": current, "shipped": base})
    for field, label in _PER_METRIC_SETTINGS:
        for metric_id, value in sorted((bc.get(field) or {}).items()):
            if value is None:
                continue
            out.append({"ref_id": f"{field}:{metric_id}", "label": f"{label} — {metric_id}", "field": field,
                        "metric_id": metric_id, "current": {field: {metric_id: value}}, "shipped": None})
    return out


def baseline_config_with_setting_reset(baseline_config: Optional[dict], ref_id: str) -> dict:
    """`baseline_config` with one setting back at shipped and everything
    else — other settings, pinned references — untouched."""
    bc = dict(baseline_config or {})
    shipped = shipped_baseline_config()
    for sid, keys, _label in _SCALAR_SETTINGS:
        if sid == ref_id:
            for k in keys:
                bc[k] = shipped[k]
            return bc
    field, _, metric_id = ref_id.partition(":")
    if field in dict(_PER_METRIC_SETTINGS) and metric_id:
        per = dict(bc.get(field) or {})
        per.pop(metric_id, None)
        bc[field] = per
        return bc
    raise ValueError(f"unknown setting {ref_id!r}")


# ── Reference-change markers (Spec 14 §7.1) ─────────────────────────────────
# reference_changes.json: when excluding a flight changes another
# flight's insight verdict (computed by server.py at exclude time, since
# that's the one place both the before- and after-exclusion fleet are in
# hand), that flight gets a marker here — "reference changed" on its
# card — until the exclusion that caused it is reverted.

_REFERENCE_CHANGES_VERSION = "1"


def load_reference_changes(ws_dir: Path) -> dict:
    f = ws_dir / "reference_changes.json"
    if not f.exists():
        return {"version": _REFERENCE_CHANGES_VERSION, "markers": []}
    return json.loads(f.read_text())


def add_reference_change_marker(
    ws_dir: Path, *, flight_id: str, cause_journal_entry_id: str, cause_kind: str, reason: str,
    cause_flight_id: Optional[str] = None, cause_topic_id: Optional[str] = None,
) -> dict:
    """One marker kind, two causes (Spec 14 §7.1's "reference changed"
    and §7.2's "rule changed" are the same card-level signal — something
    about this flight's verdict moved for a reason that isn't this
    flight's own data): cause_kind "exclusion" (cause_flight_id is what
    Revert re-includes) or "rule_edit" (cause_topic_id + the causing
    Journal entry's own before/after is what Revert restores)."""
    store = load_reference_changes(ws_dir)
    marker = {
        "id": _new_id("rfc"), "flight_id": flight_id, "at": _now(),
        "cause_journal_entry_id": cause_journal_entry_id, "cause_kind": cause_kind,
        "cause_flight_id": cause_flight_id, "cause_topic_id": cause_topic_id,
        "reason": reason, "resolved": False,
    }
    store["markers"].append(marker)
    _write_json(ws_dir / "reference_changes.json", store)
    return marker


def open_reference_changes_for_flight(ws_dir: Path, flight_id: str) -> list[dict]:
    return [m for m in load_reference_changes(ws_dir)["markers"] if m["flight_id"] == flight_id and not m["resolved"]]


def resolve_reference_changes_for_cause(ws_dir: Path, cause_journal_entry_id: str) -> int:
    store = load_reference_changes(ws_dir)
    n = 0
    for m in store["markers"]:
        if m["cause_journal_entry_id"] == cause_journal_entry_id and not m["resolved"]:
            m["resolved"] = True
            n += 1
    if n:
        _write_json(ws_dir / "reference_changes.json", store)
    return n


# ── Limit filters (Spec 09 §9) ──────────────────────────────────────────────
# filters.json, next to annotations.json: the pilot's filters on OM limits.
# Validation is the engine's (filters.validate_filter); this layer stores
# what it's given and keeps each filter's history.

_FILTERS_VERSION = "1"
_FILTER_CONDITION_KEYS = ("magnitude", "duration", "phases")   # phases: Spec 09 v0.20 §7.5
_FILTER_EDITABLE_KEYS = ("magnitude", "duration", "phases", "note")


def load_filters(ws_dir: Path) -> dict:
    """filters.json, every record in the Spec 09 v0.18 shape: a pre-v0.18
    record (top-level limit_id) is migrated to target {kind: "limit"} on
    read; any save writes the new shape."""
    from .filters import migrate_filter
    f = ws_dir / "filters.json"
    if not f.exists():
        return {"version": _FILTERS_VERSION, "filters": []}
    store = json.loads(f.read_text())
    store["filters"] = [migrate_filter(x) for x in store.get("filters", [])]
    return store


def _save_filter_store(ws_dir: Path, store: dict) -> None:
    _write_json(ws_dir / "filters.json", store)


def get_filter(ws_dir: Path, filter_id: str) -> Optional[dict]:
    return next((f for f in load_filters(ws_dir)["filters"] if f["id"] == filter_id), None)


def save_filter(ws_dir: Path, fields: dict, reference_flight_ids: Optional[list[str]] = None,
                engine_hours: Optional[float] = None) -> dict:
    """
    Create (no `id` in `fields`) or edit a filter. `fields` carries
    target ({kind: "limit", limit_id} | {kind: "cas", cas_id}), magnitude
    and/or duration, note and optionally created_from.
    `reference_flight_ids` is the reference the caller chose (§8.1): given
    on create, and on an edit that changes the band or duration, which
    resets the reference. A condition absent from `fields` is removed.
    Returns the saved filter.
    """
    store = load_filters(ws_dir)
    now = _now()
    existing = next((f for f in store["filters"] if f["id"] == fields.get("id")), None) if fields.get("id") else None
    if existing is None:
        flt = {
            "id": _new_id("flt"),
            "target": _filter_target(fields),
            **{k: fields[k] for k in _FILTER_CONDITION_KEYS if fields.get(k)},
            "note": fields.get("note") or "",
            "reference": {"flight_ids": list(reference_flight_ids or []), "set_at": now},
            "created_at": now,
            "history": [],
        }
        if fields.get("created_from"):
            flt["created_from"] = fields["created_from"]
        if fields.get("copied_from"):
            flt["copied_from"] = fields["copied_from"]
        if engine_hours is not None:
            flt["created_engine_hours"] = engine_hours
        flt["history"].append({"at": now, "action": "created",
                               "after": {k: flt[k] for k in _FILTER_EDITABLE_KEYS if k in flt}})
        store["filters"].append(flt)
        _save_filter_store(ws_dir, store)
        return flt

    before = {k: existing[k] for k in _FILTER_EDITABLE_KEYS if k in existing}
    for k in _FILTER_CONDITION_KEYS:
        if fields.get(k):
            existing[k] = fields[k]
        else:
            existing.pop(k, None)
    existing["note"] = fields.get("note") or ""
    after = {k: existing[k] for k in _FILTER_EDITABLE_KEYS if k in existing}
    if before == after:
        return existing
    existing["updated_at"] = now
    if reference_flight_ids is not None:
        existing["reference"] = {"flight_ids": list(reference_flight_ids), "set_at": now}
    existing["history"].append({"at": now, "action": "edited", "before": before, "after": after})
    _save_filter_store(ws_dir, store)
    return existing


def _filter_target(fields: dict) -> dict:
    """A save's target, accepting a bare limit_id from an older caller."""
    if fields.get("target"):
        return fields["target"]
    return {"kind": "limit", "limit_id": fields["limit_id"]}


def filter_conditions_changed(old: dict, fields: dict) -> bool:
    """Did an edit change the band, the duration or (v0.20) the excluded
    phases — which resets the reference, §8.1 — as opposed to only the note?"""
    return any((old.get(k) or None) != (fields.get(k) or None) for k in _FILTER_CONDITION_KEYS)


def delete_filter(ws_dir: Path, filter_id: str) -> bool:
    """Removing a filter deletes the record; its history goes with it (§9)."""
    store = load_filters(ws_dir)
    before = len(store["filters"])
    store["filters"] = [f for f in store["filters"] if f["id"] != filter_id]
    if len(store["filters"]) == before:
        return False
    _save_filter_store(ws_dir, store)
    return True


def review_filter(ws_dir: Path, filter_id: str, engine_hours: Optional[float]) -> Optional[dict]:
    """§8.2 "Mark reviewed": records when (time and engine hours). Clears
    Breached and Review due; Drifting clears only when its condition
    stops holding or the filter is re-baselined."""
    store = load_filters(ws_dir)
    flt = next((f for f in store["filters"] if f["id"] == filter_id), None)
    if flt is None:
        return None
    now = _now()
    flt["reviewed_at"] = now
    flt["reviewed_engine_hours"] = engine_hours
    flt["history"].append({"at": now, "action": "reviewed", "after": {"reviewed_engine_hours": engine_hours}})
    _save_filter_store(ws_dir, store)
    return flt


def rebaseline_filter(ws_dir: Path, filter_id: str, reference_flight_ids: list[str]) -> Optional[dict]:
    """§8.1 re-baseline: a fresh reference of the most recent flights,
    accepting the aircraft's current behaviour as the new normal."""
    store = load_filters(ws_dir)
    flt = next((f for f in store["filters"] if f["id"] == filter_id), None)
    if flt is None:
        return None
    now = _now()
    before = len(flt.get("reference", {}).get("flight_ids", []))
    flt["reference"] = {"flight_ids": list(reference_flight_ids), "set_at": now}
    flt["history"].append({"at": now, "action": "rebaselined",
                           "before": {"reference_flights": before},
                           "after": {"reference_flights": len(reference_flight_ids)}})
    _save_filter_store(ws_dir, store)
    return flt
