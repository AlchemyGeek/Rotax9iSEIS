"""
workspace_export.py — workspace export and import (Spec 02 v0.11 §7).

A pilot shares a workspace, usually with its logs, and the recipient sees
what the sender sees. The export carries the workspace's configuration and
decisions plus a manifest of its flights — never analyses, which the
recipient's app recomputes from the logs (§7.1). Import always creates a
new workspace (§7.4); the manifest then drives matching the recipient's
logs to the sender's flights (§7.5). *Anonymise logs* rewrites only the
copies written into the export (§7.6).

Formats (§7.3):
- without logs: `<name>.eisworkspace`, a zip of `workspace.json`
  (provenance, manifest, admission record, summary) and the carried
  documents under their workspace names;
- with logs: `<name>.zip` holding `<name>/<name>.eisworkspace` and
  `<name>/logs/`. The app never extracts an archive: the recipient unzips
  it and imports the folder.
"""
from __future__ import annotations

import copy
import csv
import fnmatch
import io
import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Any, Optional

from . import __version__
from . import exclusions as _exclusions
from . import workspace as ws
from .log_sources import DISK, LogUnavailable, areading, reading, run_now
from .loader import flight_fingerprint, flight_id as _compute_flight_id, load_log_bytes, source_key as _source_key
from .resources import resource

FORMAT = "eisworkspace"
FORMAT_VERSION = 1
EXPORT_SUFFIX = ".eisworkspace"
IMPORT_RECORD = "import.json"

# ── §7.1: every workspace document, carried or not ───────────────────────────
# First match wins; a file no pattern covers stops the export, so a new
# document can't be silently dropped. Classes:
#   carried   written into the export (possibly transformed)
#   manifest  read to build the flight manifest / provenance, not copied
#   log       an uploaded log's own copy; goes in logs/ with Include logs
#   derived   recomputed by the recipient from the logs
#   local     meaningful only on this machine / this workspace
#   retired   no longer read (left on disk)
DOCUMENTS: list[tuple[str, str, str]] = [
    ("settings.json", "carried", "Workspace settings: engine profile, aircraft aliases; device-specific fields dropped"),
    ("fleet/selection.json", "carried", "Reference & Models settings, reference exclusions, pins"),
    ("fleet/shift_history.json", "carried", "Reference history (Spec 12)"),
    ("reference_changes.json", "carried", "Reference-change markers (Spec 14 §7.1)"),
    ("rules/active.json", "carried", "Rules in effect: rule edits, disabled topics"),
    ("filters.json", "carried", "Filters (Spec 09 §9)"),
    ("journal.json", "carried", "Journal entries and their records (Spec 14 §6)"),
    ("annotations.json", "carried", "Annotations, including acknowledged insights"),
    ("exclusions.json", "carried", "Log admission record, re-keyed by source_key (§7.5)"),
    ("manifest.json", "manifest", "Workspace name and engine model go into provenance; log_folders are local"),
    ("flights/*/sources.json", "manifest", "Per-flight sources: the flight manifest"),
    ("flights/*/analysis.json", "derived", "Flight analysis"),
    ("fleet/analysis.json", "derived", "Fleet analysis: baselines, models, trends"),
    ("flights/*/*", "log", "An uploaded log's own copy"),
    ("logs/*", "log", "Logs extracted from an imported export zip (Spec 02 v0.14); linked as a log folder"),
    (IMPORT_RECORD, "local", "An imported workspace's sender manifest (§7.5); no role in another export"),
    ("channel_ranges.json", "derived", "Observed ranges of raw general-purpose channels (Log channels panel); recomputed"),
    ("unreadable.json", "derived", "Logs a scan couldn't read or analyse (Spec 03 §5.1 Unreadable); recomputed by scanning"),
    ("settings_changelog.json", "retired", "Settings changelog, unread since Spec 14 v0.13"),
]

_IGNORED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}

# WorkspaceSettings fields that travel; the rest are device- or view-local.
_CARRIED_SETTINGS = ("active_engine_profile", "aircraft_aliases", "channel_assignments")

# §7.6 (and Spec 02 v0.12): columns blanked in anonymised copies — GPS
# position, and the navigation and radio columns that place the aircraft.
# None feeds the analysis (ground speed does, and is kept).
ANONYMISED_COLUMNS = (
    "Latitude (deg)", "Longitude (deg)",
    "Nav Identifier", "Nav Distance (nm)", "Nav Bearing (deg)", "Nav Course (deg)", "Nav Cross Track Distance (nm)",
    "COM Frequency 1 (MHz)", "COM Frequency 2 (MHz)", "NAV Frequency (MHz)",
    # Garmin AXIS names (Spec 01 v0.23 §6.5); bestGlideAirport names a
    # nearby airport on every row, so it places the aircraft too.
    "latitudePosition", "longitudePosition",
    "navIdentifier", "navDistance", "navBearing", "navCourse", "crossTrackDistance",
    "navigationRadio1Frequency", "bestGlideAirport",
)


class ExportError(Exception):
    """An export that can't be written as asked; the message says why."""


class ImportRefused(Exception):
    """An export that can't be imported here (format, engine version)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify(rel: str) -> Optional[tuple[str, str]]:
    for pattern, cls, note in DOCUMENTS:
        if fnmatch.fnmatchcase(rel, pattern):
            return cls, note
    return None


def classify_workspace(ws_dir: Path) -> list[dict]:
    """Every file in the workspace with its class; raises ExportError
    for one the table doesn't cover."""
    out, unknown = [], []
    for p in sorted(ws_dir.rglob("*")):
        if not p.is_file() or p.name in _IGNORED_NAMES:
            continue
        rel = p.relative_to(ws_dir).as_posix()
        hit = classify(rel)
        if hit is None:
            unknown.append(rel)
        else:
            out.append({"path": rel, "class": hit[0], "note": hit[1]})
    if unknown:
        raise ExportError("The workspace holds documents the export doesn't know how to treat: "
                          + ", ".join(unknown) + ". This is a defect; nothing was exported.")
    return out


def _safe_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._ -]+", "-", name).strip(" .-")
    return s or "workspace"


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text())


def _version_tuple(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.+-]", v)[:3])


# ── Remapping (anonymisation) ────────────────────────────────────────────────

_HEX16 = re.compile(r"\b[0-9a-f]{16}\b")


def _remap(obj: Any, ids: dict[str, str], names: dict[str, str]) -> Any:
    """Every 16-hex token that is an old flight_id / source_key / insight
    id, and every old file name, replaced throughout a JSON value."""
    if isinstance(obj, dict):
        return {_remap(k, ids, names): _remap(v, ids, names) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_remap(v, ids, names) for v in obj]
    if isinstance(obj, str):
        s = _HEX16.sub(lambda m: ids.get(m.group(0), m.group(0)), obj) if ids else obj
        for old, new in names.items():
            if old in s:
                s = s.replace(old, new)
        return s
    return obj


def _meta_fields(meta_row: str) -> dict[str, str]:
    return dict(re.findall(r'(\w+)="([^"]*)"', meta_row))


def anonymise_log(data: bytes, pseudonyms: dict[tuple[str, str], tuple[str, str]]) -> bytes:
    """The copy of one log with its identity fields rewritten (§7.6):
    aircraft_ident and system_id (and Garmin Pilot's flightstream_header,
    which embeds the system ID) to the aircraft's pseudonym; the columns
    in ANONYMISED_COLUMNS blanked. Everything else is byte-for-byte the
    same rows, so the analysis is unchanged."""
    text = data.decode("utf-8-sig", errors="replace")
    bom = data.startswith(b"\xef\xbb\xbf")
    newline = "\r\n" if "\r\n" in text[:4096] else "\n"
    lines = text.split(newline)
    meta = _meta_fields(lines[0])
    axis = (meta.get("Product") or meta.get("product") or "").upper() == "AXIS"
    tail_key = "tail_number" if axis else "aircraft_ident"
    tail, system = meta.get(tail_key, ""), meta.get("system_id", "")
    p_tail, p_system = pseudonyms[(tail, system)]

    def sub(field_name: str, value: str, row: str) -> str:
        return re.sub(rf'({field_name}=")[^"]*(")', lambda m: m.group(1) + value + m.group(2), row)

    first = sub(tail_key, p_tail, lines[0])
    if "system_id" in meta:
        first = sub("system_id", p_system, first)
    if "flightstream_header" in meta:
        fs = meta["flightstream_header"]
        first = sub("flightstream_header", fs.replace(system, p_system) if system else p_system, first)
    lines[0] = first

    # AXIS: metadata · units · column names; G3X: metadata · column names.
    header_at = 2 if axis else 1
    header = next(csv.reader([lines[header_at]]))
    names = [h.lstrip("#").strip() for h in header]
    blank = {i for i, h in enumerate(names) if h in ANONYMISED_COLUMNS}
    if blank:
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="")
        for i in range(header_at + 1, len(lines)):
            if not lines[i]:
                continue
            row = next(csv.reader([lines[i]]))
            for j in blank:
                if j < len(row):
                    row[j] = ""
            out.seek(0)
            out.truncate()
            writer.writerow(row)
            lines[i] = out.getvalue()
    body = newline.join(lines).encode("utf-8")
    return (b"\xef\xbb\xbf" + body) if bom else body


def _aircraft_pseudonyms(identities: list[tuple[str, str]], aliases: list[list[str]]) -> dict:
    """One pseudonym per aircraft (Spec 02 v0.12): tails the sender
    grouped as one aircraft share it. Within an aircraft, each distinct
    system ID keeps its own token so different G3X systems stay distinct."""
    group_of = {}
    for i, grp in enumerate(aliases or []):
        for t in grp:
            group_of[t] = f"alias{i}"
    aircraft: dict[str, str] = {}
    systems: dict[str, list[str]] = {}
    for tail, system in sorted(set(identities)):
        key = group_of.get(tail, f"tail:{tail}")
        if key not in aircraft:
            aircraft[key] = f"ANON-{len(aircraft) + 1}"
        systems.setdefault(key, [])
        if system not in systems[key]:
            systems[key].append(system)
    out = {}
    for tail, system in set(identities):
        key = group_of.get(tail, f"tail:{tail}")
        p = aircraft[key]
        sys_list = systems[key]
        out[(tail, system)] = (p, p if len(sys_list) == 1 else f"{p}.{sys_list.index(system) + 1}")
    return out


# ── Identity in the sender's own text (Spec 02 v0.12) ────────────────────────

def identity_mentions(ws_dir: Path) -> list[dict]:
    """Where the workspace's tail numbers or system IDs appear in text that
    goes as written (§7.6): the workspace name, notes, filter notes,
    exclusion reasons, pin labels, Journal notes and reasons. Anonymising
    doesn't rewrite the sender's own words; the export dialog says where
    they are so the sender can change them first. [{where, value}]"""
    idents: set[str] = set()
    for fid in ws.list_flight_ids(ws_dir):
        fa = ws.load_flight_analysis(ws_dir, fid)
        ac = ((fa.header if fa else {}) or {}).get("aircraft") or {}
        idents |= {v for v in (ac.get("ident"), ac.get("system_id")) if v}
    idents |= {t for grp in ws.load_workspace_settings(ws_dir).aircraft_aliases for t in grp if t}
    if not idents:
        return []
    texts: list[tuple[str, str]] = [("workspace name", ws.load_manifest(ws_dir).name)]
    for a in ws.load_annotations(ws_dir).get("annotations", []):
        texts.append((f"note on flight {a.get('flight_id', '')[:8]}", a.get("note") or ""))
    for f in ws.load_filters(ws_dir).get("filters", []):
        texts.append(("filter note", f.get("note") or ""))
    sel = ws.load_selection(ws_dir)
    for e in sel.excluded:
        texts.append(("reason for excluding a flight", e.get("reason") or ""))
    for metric, ref in ((sel.baseline_config or {}).get("pinned_references") or {}).items():
        texts.append((f"pin label ({metric})", (ref or {}).get("label") or ""))
    for e in ws.load_journal(ws_dir).get("entries", []):
        texts.append(("Journal note", e.get("note") or ""))
        texts.append(("Journal reason", e.get("reason") or ""))
    out, seen = [], set()
    for where, text in texts:
        for ident in sorted(idents):
            if ident and ident.lower() in str(text).lower() and (where, ident) not in seen:
                seen.add((where, ident))
                out.append({"where": where, "value": ident})
    return out


# ── Export ───────────────────────────────────────────────────────────────────

@dataclass
class ExportResult:
    path: Path
    filename: str
    flights: int
    logs_included: int
    anonymised: bool
    documents: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"path": str(self.path), "filename": self.filename, "flights": self.flights,
                "logs_included": self.logs_included, "anonymised": self.anonymised,
                "documents": self.documents, "notes": self.notes}


async def _flight_log_async(ws_dir: Path, src: ws.FlightSources, wanted_key: Optional[str], manifest: ws.WorkspaceManifest,
                sources: Callable = DISK) -> Optional[tuple[bytes, ws.ImportRecord]]:
    """The bytes of the source the flight was analysed from (else any
    readable source), and its import record."""
    imports = sorted(src.imports, key=lambda i: i.source_key != wanted_key)
    for imp in imports:
        if imp.log_folder_path == ws.UPLOADED_SOURCE:
            p = ws_dir / "flights" / src.flight_id / imp.filename
            if p.is_file():
                return p.read_bytes(), imp
            continue
        try:
            async with areading(sources(ws._folder_by_path(manifest, imp.log_folder_path)), imp.relative_path) as data:
                return data, imp
        except LogUnavailable:
            continue
    return None


def _flight_log(*args, **kwargs):
    """`_flight_log_async` driven to the end at once (disk sources)."""
    return run_now(_flight_log_async(*args, **kwargs))


async def _admission_by_key_async(ws_dir: Path, sources: Callable = DISK) -> tuple[list[dict], int]:
    """exclusions.json re-keyed from file name to source_key (§7.5): each
    entry's file is found in the workspace's folders and hashed. Entries
    whose file can't be found are dropped (count returned)."""
    entries = _exclusions.load_exclusions(ws_dir).get("entries", [])
    if not entries:
        return [], 0
    by_name: dict[str, list[str]] = {}
    for lf in ws.load_manifest(ws_dir).log_folders:
        source = sources(lf)
        for entry in (await source.alist()) or []:
            try:
                async with areading(source, entry.relative_path) as data:
                    by_name.setdefault(entry.name, []).append(_source_key(data))
            except LogUnavailable:
                continue
    out, dropped = [], 0
    for e in entries:
        keys = by_name.get(e["filename"])
        if not keys:
            dropped += 1
            continue
        for k in keys:
            out.append({**{k2: v for k2, v in e.items() if k2 != "filename"}, "source_key": k, "filename": e["filename"]})
    return out, dropped


def _admission_by_key(*args, **kwargs):
    """`_admission_by_key_async` driven to the end at once (disk sources)."""
    return run_now(_admission_by_key_async(*args, **kwargs))


def _summary(docs: dict[str, Any]) -> dict:
    filters = (docs.get("filters.json") or {}).get("filters", [])
    sel = docs.get("fleet/selection.json") or {}
    bc = sel.get("baseline_config") or {}
    active = docs.get("rules/active.json")
    rule_edits = disabled = 0
    if active is not None:
        shipped = json.loads(resource("insight_rules.json").read_text())
        for _tid, kind in ws.rule_decisions(ws.strip_rule_comments(active), shipped):
            rule_edits += kind == "rule_edit"
            disabled += kind == "disabled_topic"
    return {
        "filters": len(filters),
        "phase_filters": sum(1 for f in filters if f.get("phases")),
        "rule_edits": rule_edits,
        "disabled_topics": disabled,
        "reference_exclusions": len(sel.get("excluded") or []),
        "pins": len(bc.get("pinned_references") or {}),
        "changed_settings": len(ws.setting_decisions(bc)),
        "notes": len((docs.get("annotations.json") or {}).get("annotations", [])),
        "journal_entries": len((docs.get("journal.json") or {}).get("entries", [])),
    }


async def export_workspace_async(ws_dir: Path, out_dir: Path, include_logs: bool = True, anonymise: bool = False,
                     sources: Callable = DISK) -> ExportResult:
    """Spec 02 §7.2–7.3: the whole workspace as an export in `out_dir`."""
    if anonymise and not include_logs:
        raise ExportError("Anonymise logs needs Include logs (§7.6): without logs there is nothing to anonymise.")
    documents = classify_workspace(ws_dir)
    manifest = ws.load_manifest(ws_dir)
    settings = ws.load_workspace_settings(ws_dir)
    notes: list[str] = []

    # Flights and their logs.
    flights = []
    for fid in ws.list_flight_ids(ws_dir):
        src = ws.load_sources(ws_dir, fid)
        fa = ws.load_flight_analysis(ws_dir, fid)
        if src is None or fa is None:
            continue
        log = (await _flight_log_async(ws_dir, src, (fa.source_keys or [None])[0], manifest, sources)) if include_logs else None
        flights.append((fid, src, fa, log))
    if include_logs:
        unreadable = [fid for fid, _s, _f, log in flights if log is None]
        if unreadable and anonymise:
            raise ExportError(f"{len(unreadable)} flights' logs can't be read (missing or offline). An anonymised "
                              "export needs every log, to recompute its flight_id; reconnect them, or remove "
                              "those flights, and export again.")
        if unreadable:
            notes.append(f"{len(unreadable)} flights' logs couldn't be read and aren't included; "
                         "they are listed in the manifest, so the recipient sees them as missing.")
    flights.sort(key=lambda t: (t[2].header.get("start_utc") or "", t[0]))

    # Carried documents, as stored.
    docs: dict[str, Any] = {}
    for d in documents:
        if d["class"] == "carried" and d["path"] not in ("settings.json", "exclusions.json"):
            docs[d["path"]] = _read_json(ws_dir / d["path"])
    sdict = settings.to_dict()
    docs["settings.json"] = {k: sdict[k] for k in _CARRIED_SETTINGS if k in sdict}
    admission, dropped = await _admission_by_key_async(ws_dir, sources)
    if dropped:
        notes.append(f"{dropped} log admission entries left out: their files aren't in the workspace's folders.")

    # Manifest, logs, and (anonymised) the id/name remap.
    logs: list[tuple[str, bytes]] = []
    fid_map: dict[str, str] = {}
    key_map: dict[str, str] = {}
    name_map: dict[str, str] = {}
    if anonymise:
        heads = [_meta_fields(log[0].decode("utf-8-sig", errors="replace").split("\n", 1)[0]) for *_x, log in flights]
        identities = [(h.get("aircraft_ident", "") or h.get("tail_number", ""), h.get("system_id", "")) for h in heads]
        pseudonyms = _aircraft_pseudonyms(identities, settings.aircraft_aliases)
    entries = []
    used_names: set[str] = set()
    for n, (fid, src, fa, log) in enumerate(flights, start=1):
        sources = [{"source_key": i.source_key, "filename": i.filename} for i in src.imports]
        entry = {"flight_id": fid, "sources": sources, "date": fa.header.get("date"),
                 "start_utc": fa.header.get("start_utc"),
                 "duration_min": (fa.metrics.get("duration_min") or {}).get("value"),
                 "airport_hint": fa.header.get("airport_hint")}
        if log is not None:
            data, imp = log
            name = imp.filename
            if anonymise:
                data = anonymise_log(data, pseudonyms)
                name = f"flight_{n:03d}.csv"
                df, info = load_log_bytes(data, name)
                new_fid = _compute_flight_id(flight_fingerprint(df, info))
                new_key = _source_key(data)
                fid_map[fid] = new_fid
                key_map[imp.source_key] = new_key
                for i in src.imports:
                    name_map[i.filename] = name
                entry = {**entry, "flight_id": new_fid, "sources": [{"source_key": new_key, "filename": name}],
                         "airport_hint": None}
            else:
                base, k = name, 2
                while name in used_names:
                    stem, dot, ext = base.rpartition(".")
                    name = f"{stem}-{k}.{ext}" if dot else f"{base}-{k}"
                    k += 1
            used_names.add(name)
            entry["log_file"] = name
            logs.append((name, data))
        entries.append(entry)

    if anonymise:
        ids = {**fid_map, **key_map, **_insight_ids(ws_dir, docs, fid_map)}
        # Only entries for included logs travel, under their new keys and
        # neutral names; the rest would carry original keys and names.
        admission = [{**a, "source_key": key_map[a["source_key"]], "filename": name_map.get(a["filename"], "")}
                     for a in admission if a["source_key"] in key_map]
        docs = {k: _remap(v, ids, name_map) for k, v in docs.items()}
        docs["settings.json"]["aircraft_aliases"] = []
        notes.append("Anonymised: tail number and system ID → pseudonym; GPS position, nav and radio columns "
                     "blanked; file names neutral; flight ids recomputed. Dates, times, engine hours and your "
                     "own text are unchanged.")

    workspace_json = {
        "format": FORMAT, "format_version": FORMAT_VERSION,
        "provenance": {
            "app": "SlingologyEIS", "app_version": __version__, "engine_version": __version__,
            "exported_at": _now(), "workspace_name": manifest.name, "engine_model": manifest.engine_model,
            "logs_included": include_logs, "anonymised": anonymise,
        },
        "manifest": entries,
        "admission": admission,
        "summary": _summary(docs),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    safe = _safe_name(manifest.name)
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("workspace.json", json.dumps(workspace_json, indent=2))
        for rel, obj in sorted(docs.items()):
            z.writestr(rel, json.dumps(obj, indent=2))
    if include_logs:
        path = out_dir / f"{safe}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"{safe}/{safe}{EXPORT_SUFFIX}", inner.getvalue())
            for name, data in logs:
                z.writestr(f"{safe}/logs/{name}", data)
    else:
        path = out_dir / f"{safe}{EXPORT_SUFFIX}"
        path.write_bytes(inner.getvalue())
    return ExportResult(path=path, filename=path.name, flights=len(entries), logs_included=len(logs),
                        anonymised=anonymise, documents=documents, notes=notes)


def export_workspace(*args, **kwargs):
    """`export_workspace_async` driven to the end at once (disk sources)."""
    return run_now(export_workspace_async(*args, **kwargs))


def _insight_ids(ws_dir: Path, docs: dict[str, Any], fid_map: dict[str, str]) -> dict[str, str]:
    """Old → new ids of the insights that annotations refer to. Insight
    ids hash the flight_id (operations.py): a limit insight's from
    (limit_id, kind), any other from (topic, trigger, text). Each old id
    is reproduced from candidate inputs before it is remapped."""
    from .contract import content_hash
    from .limits import limit_catalog, load_engine_config
    from .operations import evaluate_insights

    wanted: dict[str, set[str]] = {}
    for a in (docs.get("annotations.json") or {}).get("annotations", []):
        ref = a.get("ref") or {}
        if ref.get("insight_id") and a.get("flight_id") in fid_map:
            wanted.setdefault(a["flight_id"], set()).add(ref["insight_id"])
    if not wanted:
        return {}
    engine_cfg = load_engine_config(ws.load_manifest(ws_dir).engine_model)
    limit_ids = [lim["id"] for lim in limit_catalog(engine_cfg)]
    fleet = ws.load_fleet_analysis(ws_dir)
    shipped = json.loads(resource("insight_rules.json").read_text())
    rules = ws.load_workspace_rules(ws_dir, shipped)
    filters = ws.load_filters(ws_dir)["filters"]
    out: dict[str, str] = {}
    for fid, ids in wanted.items():
        new = fid_map[fid]
        for lid in limit_ids:
            for kind in ("exceedance", "breach", "filtered"):
                old_id = content_hash({"flight_id": fid, "topic_id": "limit_exceedances", "limit_id": lid, "kind": kind})[:16]
                if old_id in ids:
                    out[old_id] = content_hash({"flight_id": new, "topic_id": "limit_exceedances", "limit_id": lid, "kind": kind})[:16]
        rest = ids - out.keys()
        if rest and fleet is not None:
            fa = ws.load_flight_analysis(ws_dir, fid)
            iset = evaluate_insights(fa, fleet, rules, filters=filters).to_dict()
            for t in iset["topics"]:
                for i in t["insights"]:
                    text = (i.get("message") or {}).get("text", "")
                    old_id = content_hash({"flight_id": fid, "topic_id": t["topic_id"], "trigger": i["trigger"], "text": text})[:16]
                    if old_id in rest:
                        out[old_id] = content_hash({"flight_id": new, "topic_id": t["topic_id"], "trigger": i["trigger"], "text": text})[:16]
    return out


# ── Reading an export ────────────────────────────────────────────────────────

@dataclass
class ExportContents:
    workspace: dict
    documents: dict[str, Any]
    logs_dir: Optional[Path] = None
    # Spec 02 v0.14: an export zip chosen as is — its logs are extracted
    # into the new workspace's own logs/ at import.
    zip_path: Optional[Path] = None
    log_members: list[str] = field(default_factory=list)


# Bounds on what an export zip may unpack to (Spec 02 v0.14): a real
# export is one .eisworkspace and its logs; anything else is refused.
_MAX_LOG_FILES = 20000
_MAX_UNPACKED_BYTES = 20 * 1024 ** 3


def _parse_eisworkspace(data: bytes, label: str) -> tuple[dict, dict]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            workspace = json.loads(z.read("workspace.json"))
            documents = {n: json.loads(z.read(n)) for n in names if n != "workspace.json" and n.endswith(".json")}
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise ImportRefused(f"{label} isn't a workspace export ({e}).") from e
    if workspace.get("format") != FORMAT:
        raise ImportRefused(f"{label} isn't a workspace export.")
    if int(workspace.get("format_version", 0)) > FORMAT_VERSION:
        raise ImportRefused("This export was written by a newer app. Update the app to import it.")
    return workspace, documents


def read_export(path: Path, label: Optional[str] = None) -> ExportContents:
    """What the user chose to import (Spec 02 v0.14 §7.4 step 1):
    - the export **zip** (with logs): one `.eisworkspace` and `logs/*.csv`
      inside it; the logs are extracted at import;
    - an `.eisworkspace` on its own (exported without logs): an empty
      workspace;
    - (CLI) an already-unzipped export folder, whose logs/ is linked.
    Recognised by content, not by file name."""
    path = Path(path).expanduser()
    label = label or path.name
    if path.is_dir():
        found = sorted(path.glob(f"*{EXPORT_SUFFIX}"))
        if not found:
            raise ImportRefused(f"No {EXPORT_SUFFIX} file in {path}.")
        workspace, documents = _parse_eisworkspace(found[0].read_bytes(), found[0].name)
        logs = path / "logs"
        return ExportContents(workspace, documents, logs_dir=logs if logs.is_dir() else None)
    if not path.is_file():
        raise ImportRefused(f"{path} doesn't exist.")
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if "workspace.json" in names:                       # an .eisworkspace itself
                logs = path.parent / "logs"
                workspace, documents = _parse_eisworkspace(path.read_bytes(), label)
                return ExportContents(workspace, documents,
                                      logs_dir=logs if path.suffix.lower() == EXPORT_SUFFIX and logs.is_dir() else None)
            inner = [n for n in names if n.endswith(EXPORT_SUFFIX) and n.count("/") <= 1]
            if len(inner) != 1:
                raise ImportRefused(f"{label} isn't a workspace export: it should hold one {EXPORT_SUFFIX} file.")
            prefix = inner[0].rsplit("/", 1)[0] + "/" if "/" in inner[0] else ""
            workspace, documents = _parse_eisworkspace(z.read(inner[0]), label)
            logs = []
            total = 0
            for info in z.infolist():
                n = info.filename
                if info.is_dir() or not n.startswith(prefix + "logs/") or not n.lower().endswith(".csv"):
                    continue
                rel = n[len(prefix + "logs/"):]
                if not rel or "/" in rel or rel.startswith(".") or "\\" in rel:
                    continue   # only logs/<file>.csv, nothing nested or hidden
                total += info.file_size
                logs.append(n)
            if len(logs) > _MAX_LOG_FILES or total > _MAX_UNPACKED_BYTES:
                raise ImportRefused(f"{label} is larger than any workspace export should be; nothing was imported.")
    except zipfile.BadZipFile as e:
        raise ImportRefused(f"{label} isn't a workspace export ({e}).") from e
    return ExportContents(workspace, documents, zip_path=path, log_members=sorted(logs))


def _extract_logs(contents: ExportContents, dest: Path) -> int:
    """The export zip's logs/*.csv into `dest` (the new workspace's own
    logs/), by base name only — nothing outside `dest` can be written."""
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(contents.zip_path) as z:
        for member in contents.log_members:
            name = Path(member).name
            target = dest / name
            if target.resolve().parent != dest.resolve():
                continue
            with z.open(member) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            n += 1
    return n


def engine_check(sender_version: str) -> dict:
    """§7.7: refuse older, warn newer, silent same."""
    mine, theirs = _version_tuple(__version__), _version_tuple(sender_version)
    if mine < theirs:
        return {"status": "older", "ok": False,
                "message": f"This workspace needs engine {sender_version} or later. Update the app to import it."}
    if mine > theirs:
        return {"status": "newer", "ok": True,
                "message": f"Exported with engine {sender_version}; you have {__version__}. Results reflect your "
                           f"newer engine and may differ."}
    return {"status": "same", "ok": True, "message": None}


def summarize(contents: ExportContents) -> dict:
    """§7.4 step 1: what the export is, before anything is created."""
    w = contents.workspace
    prov = w.get("provenance", {})
    dates = sorted(d for d in (f.get("date") for f in w.get("manifest", [])) if d)
    return {
        "workspace_name": prov.get("workspace_name"),
        "engine_model": prov.get("engine_model"),
        "engine_version": prov.get("engine_version"),
        "exported_at": prov.get("exported_at"),
        "flight_count": len(w.get("manifest", [])),
        "date_range": [dates[0], dates[-1]] if dates else None,
        "carries": w.get("summary") or _summary(contents.documents),
        "logs_included": bool(prov.get("logs_included")),
        "anonymised": bool(prov.get("anonymised")),
        "logs_folder": str(contents.logs_dir) if contents.logs_dir else None,
        # Spec 02 v0.14: how many logs the chosen zip carries (0: the
        # workspace starts empty).
        "logs_in_file": len(contents.log_members),
        "engine_check": engine_check(prov.get("engine_version") or "0"),
    }


# ── Import ───────────────────────────────────────────────────────────────────

def import_workspace(registry_path: Path, workspaces_root: Path, contents: ExportContents,
                     name: Optional[str] = None) -> ws.WorkspaceManifest:
    """§7.4 steps 2–3: a new workspace holding the export's documents and
    its sender manifest; an export folder's logs/ is linked. Never
    touches an existing workspace."""
    prov = contents.workspace.get("provenance", {})
    check = engine_check(prov.get("engine_version") or "0")
    if not check["ok"]:
        raise ImportRefused(check["message"])
    engine_model = prov.get("engine_model") or ""
    ws.check_engine_model(engine_model, prov.get("workspace_name") or "")
    name = (name or f"{prov.get('workspace_name') or 'Workspace'} (imported)").strip()
    manifest = ws.create_workspace(registry_path, workspaces_root, name, engine_model)
    ws_dir = workspaces_root / manifest.id
    docs = copy.deepcopy(contents.documents)

    carried_settings = docs.pop("settings.json", {}) or {}
    settings = ws.load_workspace_settings(ws_dir)
    settings.active_engine_profile = carried_settings.get("active_engine_profile") or settings.active_engine_profile
    settings.aircraft_aliases = carried_settings.get("aircraft_aliases") or []
    settings.channel_assignments = carried_settings.get("channel_assignments") or {}   # Spec 02 v0.15 §7.1
    ws.save_workspace_settings(ws_dir, settings)
    carried = {p for p, c, _n in DOCUMENTS if c == "carried"} - {"settings.json", "exclusions.json"}
    for rel, obj in docs.items():
        if rel not in carried:
            continue   # only documents the export format carries
        target = ws_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(obj, indent=2))
    record = {
        "imported_at": _now(), "provenance": prov,
        "manifest": contents.workspace.get("manifest", []),
        "admission": contents.workspace.get("admission", []),
    }
    (ws_dir / IMPORT_RECORD).write_text(json.dumps(record, indent=2))
    if contents.zip_path is not None and contents.log_members:
        # Spec 02 v0.14: the logs travel inside the zip; they become this
        # workspace's own logs/ folder, linked like any other.
        _extract_logs(contents, ws_dir / "logs")
        ws.add_log_folder(ws_dir, str(ws_dir / "logs"), registry_path)
    elif contents.logs_dir is not None:
        ws.add_log_folder(ws_dir, str(contents.logs_dir), registry_path)
    return ws.load_manifest(ws_dir)


def load_import_record(ws_dir: Path) -> Optional[dict]:
    p = ws_dir / IMPORT_RECORD
    return json.loads(p.read_text()) if p.is_file() else None


async def match_import_async(ws_dir: Path, sources: Callable = DISK) -> dict:
    """§7.4 step 4, without analysing: the workspace's folders against
    the sender's manifest, by flight_id (a file whose bytes are a known
    source matches by source_key; any other is parsed for its flight_id).
    found / missing / extra, each a list."""
    record = load_import_record(ws_dir)
    if record is None:
        raise ValueError("not an imported workspace")
    by_fid = {f["flight_id"]: f for f in record["manifest"]}
    fid_by_key = {s["source_key"]: f["flight_id"] for f in record["manifest"] for s in f.get("sources", [])}
    found: dict[str, dict] = {}
    extra: list[dict] = []
    for lf in ws.load_manifest(ws_dir).log_folders:
        source = sources(lf)
        for entry in (await source.alist()) or []:
            try:
                async with areading(source, entry.relative_path) as data:
                    key = _source_key(data)
                    fid = fid_by_key.get(key)
                    if fid is None:
                        try:
                            df, info = load_log_bytes(data, entry.name)
                            fid = _compute_flight_id(flight_fingerprint(df, info))
                        except Exception:
                            fid = None
            except LogUnavailable:
                continue
            if fid in by_fid:
                found.setdefault(fid, {"flight_id": fid, "filename": entry.name, "date": by_fid[fid].get("date")})
            else:
                extra.append({"filename": entry.name, "date": ws.date_from_log_filename(entry.name)})
    # Flights already in the workspace (a later Sync) count as found.
    for fid in ws.list_flight_ids(ws_dir):
        if fid in by_fid and fid not in found:
            found[fid] = {"flight_id": fid, "filename": None, "date": by_fid[fid].get("date")}
    missing = [_missing_row(f) for fid, f in by_fid.items() if fid not in found]
    return {"total": len(by_fid), "found": sorted(found.values(), key=lambda r: r["date"] or ""),
            "missing": missing, "extra": sorted(extra, key=lambda r: r["filename"])}


def match_import(*args, **kwargs):
    """`match_import_async` driven to the end at once (disk sources)."""
    return run_now(match_import_async(*args, **kwargs))


def _missing_row(f: dict) -> dict:
    names = [s.get("filename") for s in f.get("sources", []) if s.get("filename")]
    return {"flight_id": f["flight_id"], "date": f.get("date"), "airport_hint": f.get("airport_hint"),
            "sender_filename": names[0] if names else None,
            "reason": "In the sender's workspace — log not found"}


def missing_flights(ws_dir: Path) -> list[dict]:
    """The Skipped panel's sender rows (§7.5): manifest flights with no
    flight in the workspace yet."""
    record = load_import_record(ws_dir)
    if record is None:
        return []
    present = set(ws.list_flight_ids(ws_dir))
    return [_missing_row(f) for f in record["manifest"] if f["flight_id"] not in present]
