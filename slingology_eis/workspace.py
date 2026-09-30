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
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import __version__
from . import exclusions as _exclusions
from . import serialize as _json_serialize
from .limits import load_engine_config, resolve_min_flight_duration_min
from .loader import (
    find_duplicate_flights,
    flight_fingerprint,
    flight_id as _compute_flight_id,
    load_log_bytes,
    source_key as _source_key,
)
from .phases import detect_phases
from .operations import FlightAnalysis, FleetAnalysis, analyze_flight, update_fleet

SCHEMA_VERSION = "02-v0.5"

ENGINE_MODELS = ("912iS", "914iS", "915iS", "916iS")

_SOURCE_FORMAT_TO_VIA = {
    "g3x_direct": "sd_card",
    "garmin_pilot": "garmin_pilot",
    "unknown": "unknown",
}

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGED_HOME = Path.home() / "SlingologyEIS"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _is_git_checkout(start: Path) -> bool:
    cur = start
    for _ in range(6):
        if (cur / ".git").exists():
            return True
        if cur.parent == cur:
            return False
        cur = cur.parent
    return False


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
# doesn't add one; a Docker deployment mounts something at _PACKAGED_HOME's
# path and this resolves the same way as a packaged install.

def resolve_registry_path() -> Path:
    """registry.json — alongside workspaces/, never inside any one workspace."""
    if _PACKAGED_HOME.is_dir():
        return _PACKAGED_HOME / "registry.json"
    if _is_git_checkout(_REPO_ROOT):
        return _REPO_ROOT / "data" / "registry.json"
    return _PACKAGED_HOME / "registry.json"


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
    path: str
    reachable: bool = True
    last_scanned_at: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"path": self.path, "reachable": self.reachable}
        if self.last_scanned_at is not None:
            d["last_scanned_at"] = self.last_scanned_at
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "LogFolder":
        return cls(path=d["path"], reachable=d.get("reachable", True), last_scanned_at=d.get("last_scanned_at"))


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
    baseline_config: dict = field(
        default_factory=lambda: {
            "membership": "leave_one_out", "band_kind_by_metric": {}, "outlier_z_threshold": 2.0,
        }
    )

    def to_dict(self) -> dict:
        return {"excluded": self.excluded, "baseline_config": self.baseline_config}

    @classmethod
    def from_dict(cls, d: dict) -> "FleetSelection":
        return cls(
            excluded=d.get("excluded", []),
            baseline_config=d.get("baseline_config") or {
                "membership": "leave_one_out", "band_kind_by_metric": {}, "outlier_z_threshold": 2.0,
            },
        )


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
    anonymize_by_default: bool = False
    active_engine_profile: str = ""
    last_view: Optional[dict] = None

    def to_dict(self) -> dict:
        d = {
            "anonymize_by_default": self.anonymize_by_default,
            "active_engine_profile": self.active_engine_profile,
        }
        if self.last_view is not None:
            d["last_view"] = self.last_view
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "WorkspaceSettings":
        return cls(
            anonymize_by_default=d.get("anonymize_by_default", False),
            active_engine_profile=d.get("active_engine_profile", ""),
            last_view=d.get("last_view"),
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
    # exclusions.json this scan (Spec: Ground Session Detection +
    # Workspace Flight Exclusions) — never became a flight_id at all, so
    # keyed by filename, not flight_id like the fields above.
    auto_excluded: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "new_flight_ids": self.new_flight_ids,
            "rematched_flight_ids": self.rematched_flight_ids,
            "now_missing_flight_ids": self.now_missing_flight_ids,
            "recovered_flight_ids": self.recovered_flight_ids,
            "unreachable_folders": self.unreachable_folders,
            "excluded": self.excluded,
            "reanalyzed_flight_ids": self.reanalyzed_flight_ids,
            "auto_excluded": self.auto_excluded,
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
    if engine_model not in ENGINE_MODELS:
        raise ValueError(f"Unknown engine_model {engine_model!r}; expected one of {ENGINE_MODELS}")
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


def add_log_folder(ws_dir: Path, folder_path: str, registry_path: Optional[Path] = None) -> WorkspaceManifest:
    manifest = load_manifest(ws_dir)
    if any(f.path == folder_path for f in manifest.log_folders):
        return manifest
    manifest.log_folders.append(LogFolder(path=folder_path, reachable=True, last_scanned_at=None))
    manifest.updated_at = _now()
    save_manifest(ws_dir, manifest)
    if registry_path is not None:
        _touch_registry_entry(registry_path, manifest.id, log_folder_count=len(manifest.log_folders))
    return manifest


# ── Per-workspace documents (§5.3, §6) ───────────────────────────────────────

def load_manifest(ws_dir: Path) -> WorkspaceManifest:
    return WorkspaceManifest.from_dict(json.loads((ws_dir / "manifest.json").read_text()))


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


def load_fleet_analysis(ws_dir: Path) -> Optional[FleetAnalysis]:
    f = ws_dir / "fleet" / "analysis.json"
    if not f.exists():
        return None
    return FleetAnalysis(**json.loads(f.read_text()))


def save_fleet_analysis(ws_dir: Path, fleet: FleetAnalysis) -> None:
    _write_json(ws_dir / "fleet" / "analysis.json", fleet.to_dict())


def rebuild_fleet(ws_dir: Path) -> FleetAnalysis:
    """
    Spec 01 `update_fleet`, scoped to this workspace: every flight in
    flights/ *except* the ones FleetSelection.excluded names — Missing
    flights are NOT excluded from this (§5.5: their baseline contribution
    stays unchanged while missing; only an explicit exclusion removes a
    flight from the fleet).
    """
    selection = load_selection(ws_dir)
    excluded_ids = {e["flight_id"] for e in selection.excluded}
    included = [fa for fa in load_all_flight_analyses(ws_dir) if fa.flight_id not in excluded_ids]
    fleet = update_fleet(
        included, excluded=selection.excluded, baseline_config=selection.baseline_config,
        engine_config=load_engine_config(load_manifest(ws_dir).engine_model),
    )
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
        return upgrade_limit_refs(json.loads(f.read_text()))
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

def _find_csv_files(folder: Path) -> list[Path]:
    """Recursive, case-insensitive *.csv — subfolders are included
    automatically (§5.1), matching how loader.load_directory matches."""
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() == ".csv")


def _relative_path(abspath: Path, folder: Path) -> str:
    return str(abspath.relative_to(folder))


def find_log_file_by_name(manifest: WorkspaceManifest, filename: str) -> Optional[Path]:
    """
    Best-effort: search every reachable log_folders entry for a file
    with this exact name. exclusions.json only ever records a filename
    (Spec: Workspace Flight Exclusions), never a path, so this is how a
    skipped log's own data (date, duration, etc.) gets found again for
    display — e.g. the Flights tab's Skipped list. None if the file
    isn't in any currently-reachable watched folder (including the
    always-true case of a browser-uploaded exclusion, which was never
    in a folder at all — its bytes were never saved anywhere).
    """
    target = filename.lower()
    for lf in manifest.log_folders:
        folder = Path(lf.path).expanduser()
        if not folder.is_dir():
            continue
        for abspath in _find_csv_files(folder):
            if abspath.name.lower() == target:
                return abspath
    return None


def read_source_bytes(ws_dir: Path, src: "FlightSources") -> Optional[tuple[bytes, str]]:
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
    for imp in reversed(src.imports):
        if imp.log_folder_path == UPLOADED_SOURCE:
            p = ws_dir / "flights" / src.flight_id / imp.filename
        else:
            p = Path(imp.log_folder_path).expanduser() / imp.relative_path
        if p.is_file():
            return p.read_bytes(), imp.filename
    return None


def scan_workspace(ws_dir: Path, registry_path: Optional[Path] = None, quiet: bool = True) -> ScanResult:
    """
    The core Spec 02 operation: reconcile `flights/` against what
    `manifest.log_folders` currently contains.

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
    log (Spec: Ground Session Detection + Workspace Flight Exclusions)
    never becomes a flight_id at all — it's recorded to exclusions.json
    and left out entirely, the same as loader.py's load_directory()
    (CLI/notebook path) already does. Before this, a workspace built by
    folder-scan (the web UI's path) had no such filtering at all.
    """
    manifest = load_manifest(ws_dir)
    engine_cfg = load_engine_config(manifest.engine_model)  # locked, always this (§5.6) — never per-log
    exclusions_data = _exclusions.load_exclusions(ws_dir)
    min_flight_duration_min = resolve_min_flight_duration_min()

    result = ScanResult()
    found_by_key: dict[str, tuple[str, str, str, Path]] = {}  # source_key -> (folder_path, rel, filename, abspath)
    unreachable_folder_paths: set[str] = set()

    for lf in manifest.log_folders:
        folder = Path(lf.path).expanduser()
        if not folder.is_dir():
            lf.reachable = False
            unreachable_folder_paths.add(lf.path)
            result.unreachable_folders.append(lf.path)
            continue
        lf.reachable = True
        lf.last_scanned_at = _now()
        for abspath in _find_csv_files(folder):
            content = abspath.read_bytes()
            skey = _source_key(content)
            # First folder (in manifest order) to claim a given fingerprint
            # wins if the same physical file is reachable via two folder
            # references (§5.7's "same log in two folders" case).
            found_by_key.setdefault(skey, (lf.path, _relative_path(abspath, folder), abspath.name, abspath))

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

    new_batch: list[tuple[bytes, str, str]] = []  # (content, filename, source_key) for genuinely new flight_ids
    new_batch_meta: dict[str, tuple[str, str, str]] = {}  # source_key -> (folder_path, rel, filename)

    for skey, (folder_path, rel, filename, abspath) in found_by_key.items():
        if skey in known:
            fid, imp = known[skey]
            if imp.log_folder_path != folder_path or imp.relative_path != rel or imp.filename != filename:
                # Rename/move under a known fingerprint — rematch, not a
                # new import (§5.7).
                imp.log_folder_path, imp.relative_path, imp.filename = folder_path, rel, filename
                save_sources(ws_dir, all_sources[fid])
                result.rematched_flight_ids.append(fid)
            if all_sources[fid].missing:
                all_sources[fid].missing = False
                save_sources(ws_dir, all_sources[fid])
                result.recovered_flight_ids.append(fid)
            continue
        # Not a known fingerprint. Could still be a new export path of an
        # already-known flight (same physical flight, different file) —
        # that's only knowable after parsing (flight_id is fingerprint-of-
        # content, not of bytes), so defer to the batch below.
        content = abspath.read_bytes()
        new_batch.append((content, filename, skey))
        new_batch_meta[skey] = (folder_path, rel, filename)

    # Resolve the deferred batch: parse each, then split into "new export
    # path of an existing flight" vs "genuinely new flight". Only an
    # OVERLAP duplicate group (different flight_id — different fingerprint,
    # but the same physical flight per the time-overlap heuristic) gets
    # dropped here (Spec 01 R5's INGEST_DUPLICATE_OF case). An EXACT group
    # (same flight_id) is deliberately *not* run through deduplicate_flights'
    # drop-one-keep-one logic the way cli.py's single-workspace `import`
    # does — that would throw away exactly the second export path §6.2
    # wants recorded. Same flight_id already means "merge into one
    # flights/<id>", which the per-file loop below does naturally by
    # appending a second `imports[]` entry instead of re-analyzing.
    parsed = []  # (df, info, content, filename, skey)
    for content, filename, skey in new_batch:
        try:
            df, info = load_log_bytes(content, filename)
        except Exception:
            continue  # unreadable — Spec 03 §5.1's "Unreadable" status; nothing to record yet
        parsed.append((df, info, content, filename, skey))

    dup_groups_excluded: set[str] = set()
    if len(parsed) > 1:
        flights_for_dedup = [(df, info) for df, info, _, _, _ in parsed]
        overlap_groups = [g for g in find_duplicate_flights(flights_for_dedup) if g.match_kind == "overlap"]
        if overlap_groups:
            file_to_row = {df["_source_file"].iloc[0]: (df, info) for df, info, _, _, _ in parsed}
            for group in overlap_groups:
                candidates = [file_to_row[f] for f in group.files if f in file_to_row]
                if len(candidates) < 2:
                    continue
                keep_df, _ = max(candidates, key=lambda pair: len(pair[0]))
                keep_name = keep_df["_source_file"].iloc[0]
                for df, info, content, filename, skey in parsed:
                    if filename in group.files and filename != keep_name:
                        dup_groups_excluded.add(skey)
                        fid = _compute_flight_id(flight_fingerprint(df, info))
                        result.excluded.append({"flight_id": fid, "reason": f"duplicate export ({filename})"})

    for df, info, content, filename, skey in parsed:
        if skey in dup_groups_excluded:
            continue

        df = detect_phases(df, verbose=False)
        category, reason = _exclusions.classify_for_auto_exclusion(df, min_flight_duration_min)
        if category is not None:
            _exclusions.add_auto_exclusion(ws_dir, filename, category, reason)
            # add_auto_exclusion() is a no-op if an entry already exists
            # — including one a user already overrode (user_override:
            # true). Re-check the current on-disk state, not the copy
            # loaded at the top of this scan, so an override takes
            # effect immediately, not just on the *next* scan (same
            # reasoning as load_directory()'s equivalent check).
            if _exclusions.is_excluded(filename, _exclusions.load_exclusions(ws_dir)):
                result.auto_excluded.append({"filename": filename, "category": category, "reason": reason})
                continue
            # else: overridden — falls through and becomes a flight below.

        fid = _compute_flight_id(flight_fingerprint(df, info))
        folder_path, rel, filename = new_batch_meta[skey]
        via = _SOURCE_FORMAT_TO_VIA.get(info.source_format, "unknown")
        imp = ImportRecord(
            source_key=skey, log_folder_path=folder_path, relative_path=rel,
            filename=filename, imported_at=_now(), via=via,
        )

        if fid in all_sources:
            # A new export path of a flight already in this workspace
            # (Spec 01 §6.2's "same flight, two export paths").
            all_sources[fid].imports.append(imp)
            save_sources(ws_dir, all_sources[fid])
            result.rematched_flight_ids.append(fid)
            continue

        fa = analyze_flight(content, filename, engine_cfg, manifest.engine_model)
        # fa.flight_id is computed the same way as `fid` above (same
        # fingerprint function); use fa's own value as the source of truth.
        ident = (fa.header or {}).get("aircraft", {}).get("ident")
        different_tail = ident if (ident and primary_ident and ident != primary_ident) else None
        if primary_ident is None and ident:
            primary_ident = ident  # first flight this workspace has ever seen sets it

        save_flight_analysis(ws_dir, fa)
        sources = FlightSources(flight_id=fa.flight_id, imports=[imp], different_tail_number=different_tail)
        save_sources(ws_dir, sources)
        all_sources[fa.flight_id] = sources
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
    # engine version actually running gets re-run for real, not left
    # stale indefinitely — Spec 03's "needs_reanalysis" status names this
    # case but nothing ever actually triggered it. Scoped to flights this
    # scan can still reach a source for; skips ones just created above
    # (already current) and ones already missing (nothing to re-read).
    for fid, src in all_sources.items():
        if fid in result.new_flight_ids or src.missing:
            continue
        fa = load_flight_analysis(ws_dir, fid)
        if fa is None or fa.provenance.get("engine_version") == __version__:
            continue
        found = read_source_bytes(ws_dir, src)
        if found is None:
            continue
        content, filename = found
        try:
            fresh = analyze_flight(content, filename, engine_cfg, manifest.engine_model)
        except Exception:
            continue  # leave the stale analysis in place rather than losing it
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


def reclassify_existing_flights(ws_dir: Path) -> list[dict]:
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
        found = read_source_bytes(ws_dir, src)
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


# ── Limit filters (Spec 09 §9) ──────────────────────────────────────────────
# filters.json, next to annotations.json: the pilot's filters on OM limits.
# Validation is the engine's (filters.validate_filter); this layer stores
# what it's given and keeps each filter's history.

_FILTERS_VERSION = "1"
_FILTER_CONDITION_KEYS = ("magnitude", "duration")
_FILTER_EDITABLE_KEYS = ("magnitude", "duration", "note")


def load_filters(ws_dir: Path) -> dict:
    f = ws_dir / "filters.json"
    if not f.exists():
        return {"version": _FILTERS_VERSION, "filters": []}
    return json.loads(f.read_text())


def _save_filter_store(ws_dir: Path, store: dict) -> None:
    _write_json(ws_dir / "filters.json", store)


def get_filter(ws_dir: Path, filter_id: str) -> Optional[dict]:
    return next((f for f in load_filters(ws_dir)["filters"] if f["id"] == filter_id), None)


def save_filter(ws_dir: Path, fields: dict, reference_flight_ids: Optional[list[str]] = None,
                engine_hours: Optional[float] = None) -> dict:
    """
    Create (no `id` in `fields`) or edit a filter. `fields` carries
    limit_id, magnitude and/or duration, note and optionally created_from.
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
            "limit_id": fields["limit_id"],
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


def filter_conditions_changed(old: dict, fields: dict) -> bool:
    """Did an edit change the band or the duration (which resets the
    reference, §8.1), as opposed to only the note?"""
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
