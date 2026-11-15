"""
The aircraft record (Spec 16 D10, §4.4): the registry's anchor. Every
workspace belongs to one aircraft; the aircraft holds the facts an
investigation needs on its first line, the folders its documents live in
(D11), and the owner's notes for the investigator (D13).

    <data root>/aircraft/<aircraft id>/aircraft.json
    <data root>/aircraft/<aircraft id>/notes.md

`aircraft.json`: id, name, engine_model, the free-text fields below
(Session D's S14 fields), `documents_dirs` (absolute paths), `workspaces`
(ids), created, updated. The registry entry of each workspace names its
aircraft (`aircraft_id`); the two are kept in step here.

There is no registration field: the tail number lives in the logs, and
export anonymisation (Spec 02 §7.6) can only pseudonymise what it knows
is an identity. Workspace export carries the fields and the name, never
`documents_dirs` or the notes (both the owner's, local).

Migration (`ensure`): a registry with workspaces and no aircraft gets one
aircraft holding all of them, named from the engine profile, with the
fields of Session D's per-workspace `aircraft.json` (read once, then
removed). Idempotent; the browser host runs the same code on OPFS.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DIRNAME = "aircraft"
RECORD = "aircraft.json"
NOTES = "notes.md"
LEGACY_FILENAME = "aircraft.json"      # Session D: workspaces/<id>/aircraft.json
MAX_FIELD_CHARS = 2000
MAX_NAME_CHARS = 80

# (key, label, hint) — the order Settings → Aircraft shows them in.
FIELDS: tuple[tuple[str, str, str], ...] = (
    ("airframe", "Airframe", "Make, model, serial, year"),
    ("engine_serial", "Engine serial number", "As on the engine data plate"),
    ("propeller", "Propeller", "Make, model, blades, hub"),
    ("prop_controller", "Propeller controller", "Governor or controller model"),
    ("firmware", "Firmware versions", "Controller, hub, ECU, avionics — one per line"),
    ("avionics", "Avionics", "Displays and engine monitoring"),
)
KEYS = tuple(k for k, _l, _h in FIELDS)
# What travels in a workspace export (Spec 16 §4.4).
EXPORTED = ("name", "engine_model") + KEYS


class AircraftError(Exception):
    code = "BAD_PARAMS"

    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def engine_label(engine_model: str) -> str:
    """'916iS' → 'Rotax 916 iS'."""
    m = (engine_model or "").strip()
    if m[:3].isdigit():
        return f"Rotax {m[:3]} {m[3:]}".strip()
    return f"Rotax {m}".strip() if m else "Aircraft"


def _root_dir(root: Path) -> Path:
    return Path(root) / DIRNAME


def _dir(root: Path, aircraft_id: str) -> Path:
    if not isinstance(aircraft_id, str) or not aircraft_id.startswith("ac_") or "/" in aircraft_id \
            or "\\" in aircraft_id or ".." in aircraft_id:
        raise AircraftError(f"no aircraft {aircraft_id!r}", "NOT_FOUND")
    return _root_dir(root) / aircraft_id


def _blank(aircraft_id: str, name: str, engine_model: str) -> dict:
    now = _now()
    return {"id": aircraft_id, "name": name, "engine_model": engine_model, **{k: "" for k in KEYS},
            "documents_dirs": [], "workspaces": [], "created": now, "updated": now}


def _normalise(doc: dict) -> dict:
    out = {"id": doc.get("id"), "name": str(doc.get("name") or ""), "engine_model": str(doc.get("engine_model") or "")}
    for k in KEYS:
        out[k] = str(doc.get(k) or "")
    out["documents_dirs"] = [str(p) for p in (doc.get("documents_dirs") or []) if str(p).strip()]
    out["workspaces"] = [str(w) for w in (doc.get("workspaces") or [])]
    out["created"] = doc.get("created") or ""
    out["updated"] = doc.get("updated") or ""
    return out


def _write(root: Path, doc: dict) -> dict:
    d = _dir(root, doc["id"])
    d.mkdir(parents=True, exist_ok=True)
    doc = _normalise(doc)
    (d / RECORD).write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    return doc


def list_ids(root: Path) -> list[str]:
    base = _root_dir(root)
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and (p / RECORD).is_file())


def load(root: Path, aircraft_id: str) -> dict:
    p = _dir(root, aircraft_id) / RECORD
    if not p.is_file():
        raise AircraftError(f"no aircraft {aircraft_id!r}", "NOT_FOUND")
    try:
        return _normalise(json.loads(p.read_text()))
    except ValueError:
        raise AircraftError(f"aircraft {aircraft_id!r} can't be read", "INTERNAL_ERROR")


def list_aircraft(root: Path) -> list[dict]:
    return [load(root, i) for i in list_ids(root)]


def read_notes(root: Path, aircraft_id: str) -> str:
    p = _dir(root, aircraft_id) / NOTES
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def write_notes(root: Path, aircraft_id: str, text: str) -> str:
    load(root, aircraft_id)
    text = "" if text is None else str(text)
    (_dir(root, aircraft_id) / NOTES).write_text(text, encoding="utf-8")
    return text


def create(root: Path, name: str, engine_model: str, fields: Optional[dict] = None) -> dict:
    doc = _blank(f"ac_{uuid.uuid4().hex[:12]}", (name or "").strip() or engine_label(engine_model), engine_model)
    for k in KEYS:
        if fields and fields.get(k):
            doc[k] = str(fields[k])[:MAX_FIELD_CHARS].strip()
    return _write(root, doc)


def update(root: Path, aircraft_id: str, fields: dict) -> dict:
    """Replace the given fields (others kept): the S14 fields, `name`,
    `documents_dirs`. Unknown keys are refused; `workspaces` and
    `engine_model` aren't set here."""
    if not isinstance(fields, dict):
        raise AircraftError("aircraft fields are an object")
    allowed = set(KEYS) | {"name", "documents_dirs"}
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise AircraftError(f"unknown aircraft field(s) {', '.join(unknown)}; one of {', '.join(sorted(allowed))}")
    doc = load(root, aircraft_id)
    for k, v in fields.items():
        if k == "documents_dirs":
            if isinstance(v, str):
                v = [v]
            if not isinstance(v, list) or not all(isinstance(p, str) for p in v):
                raise AircraftError("documents_dirs is a list of folder paths, e.g. [\"/Users/me/Aircraft/Manuals\"]")
            paths = []
            for p in v:
                p = p.strip()
                if not p:
                    continue
                pp = Path(p).expanduser()
                if not pp.is_absolute():
                    raise AircraftError(f"documents_dirs takes absolute paths; {p!r} isn't one")
                if str(pp) not in paths:
                    paths.append(str(pp))
            doc["documents_dirs"] = paths
            continue
        v = "" if v is None else str(v)
        cap = MAX_NAME_CHARS if k == "name" else MAX_FIELD_CHARS
        if len(v) > cap:
            raise AircraftError(f"{k} is longer than {cap} characters")
        if k == "name" and not v.strip():
            raise AircraftError("an aircraft needs a name")
        doc[k] = v.strip()
    doc["updated"] = _now()
    return _write(root, doc)


def field_list() -> list[dict]:
    return [{"key": k, "label": label, "hint": hint} for k, label, hint in FIELDS]


def exported(doc: dict) -> dict:
    """The fields a workspace export carries (no documents_dirs, no notes)."""
    return {k: doc.get(k, "") for k in EXPORTED}


# ── The registry link ──────────────────────────────────────────────────────

def _registry(root: Path):
    from . import workspace as ws
    return ws, Path(root) / "registry.json"


def assign(root: Path, workspace_id: str, aircraft_id: str) -> None:
    """Make `workspace_id` belong to `aircraft_id` (and to no other)."""
    ws, reg_path = _registry(root)
    target = load(root, aircraft_id)
    for other in list_aircraft(root):
        if other["id"] != aircraft_id and workspace_id in other["workspaces"]:
            other["workspaces"] = [w for w in other["workspaces"] if w != workspace_id]
            _write(root, other)
    if workspace_id not in target["workspaces"]:
        target["workspaces"].append(workspace_id)
        _write(root, target)
    reg = ws.load_registry(reg_path)
    for e in reg.workspaces:
        if e.id == workspace_id and e.aircraft_id != aircraft_id:
            e.aircraft_id = aircraft_id
            ws.save_registry(reg_path, reg)
            break


def unassign(root: Path, workspace_id: str) -> None:
    for doc in list_aircraft(root):
        if workspace_id in doc["workspaces"]:
            doc["workspaces"] = [w for w in doc["workspaces"] if w != workspace_id]
            _write(root, doc)


def of_workspace(root: Path, workspace_id: Optional[str]) -> Optional[dict]:
    if not workspace_id:
        return None
    ws, reg_path = _registry(root)
    e = next((e for e in ws.load_registry(reg_path).workspaces if e.id == workspace_id), None)
    if e is not None and e.aircraft_id:
        try:
            return load(root, e.aircraft_id)
        except AircraftError:
            pass
    return next((a for a in list_aircraft(root) if workspace_id in a["workspaces"]), None)


def for_new_workspace(root: Path, engine_model: str, aircraft_id: Optional[str] = None,
                      fields: Optional[dict] = None, name: Optional[str] = None) -> dict:
    """The aircraft a new workspace joins: the one named; else, with no
    fields from an export, the registry's only aircraft (or a new one);
    with an export's fields, the aircraft with the same engine serial,
    else a new one carrying them."""
    if aircraft_id:
        return load(root, aircraft_id)
    existing = list_aircraft(root)
    if fields:
        serial = (fields.get("engine_serial") or "").strip()
        same = [a for a in existing if serial and a["engine_serial"].strip() == serial]
        if same:
            return same[0]
        return create(root, name or fields.get("name") or engine_label(engine_model), engine_model, fields)
    if len(existing) == 1:
        return existing[0]
    if existing:
        same_engine = [a for a in existing if a["engine_model"] == engine_model]
        if len(same_engine) == 1:
            return same_engine[0]
    return create(root, name or engine_label(engine_model), engine_model)


def resolve(root: Path, ref: str) -> dict:
    """An aircraft by id or (case-insensitive) name."""
    for a in list_aircraft(root):
        if ref == a["id"] or ref.strip().lower() == a["name"].strip().lower():
            return a
    raise AircraftError(f"no aircraft {ref!r}; aircraft here: "
                        + (", ".join(f"{a['name']} ({a['id']})" for a in list_aircraft(root)) or "none"), "NOT_FOUND")


def ensure(root: Path) -> bool:
    """Spec 16 §4.4 migration, idempotent. Every registered workspace
    ends up belonging to an aircraft; Session D's per-workspace
    aircraft.json is read once (its fields seed the record, its `notes`
    the notes.md) and removed. Returns whether anything was written."""
    ws, reg_path = _registry(root)
    if not reg_path.is_file():
        return False
    reg = ws.load_registry(reg_path)
    if not reg.workspaces:
        return False
    existing = {a["id"]: a for a in list_aircraft(root)}
    orphans = [e for e in reg.workspaces if not e.aircraft_id or e.aircraft_id not in existing
               or e.id not in existing[e.aircraft_id]["workspaces"]]
    legacy = [(e, Path(root) / "workspaces" / e.id / LEGACY_FILENAME) for e in reg.workspaces]
    legacy = [(e, p) for e, p in legacy if p.is_file()]
    if not orphans and not legacy:
        return False

    by_recent = sorted(reg.workspaces, key=lambda e: e.last_opened_at or "", reverse=True)
    if not existing:
        engine = by_recent[0].engine_model
        target = create(root, engine_label(engine), engine)
        existing[target["id"]] = target
    for e in orphans:
        if e.aircraft_id in existing:
            aid = e.aircraft_id
        elif len(existing) == 1:
            aid = next(iter(existing))
        else:
            same = [a for a in existing.values() if a["engine_model"] == e.engine_model]
            aid = (same or list(existing.values()))[0]["id"]
        assign(root, e.id, aid)
        existing[aid] = load(root, aid)

    # Session D's documents: the most recently opened workspace's wins per field.
    rank = {e.id: i for i, e in enumerate(by_recent)}
    for e, p in sorted(legacy, key=lambda t: rank.get(t[0].id, 0), reverse=True):
        try:
            old = json.loads(p.read_text())
        except ValueError:
            old = {}
        aid = ws.load_registry(reg_path)
        aid = next((x.aircraft_id for x in aid.workspaces if x.id == e.id), None)
        if aid and isinstance(old, dict):
            doc = load(root, aid)
            for k in KEYS:
                if str(old.get(k) or "").strip():
                    doc[k] = str(old[k]).strip()
            doc["updated"] = _now()
            _write(root, doc)
            note = str(old.get("notes") or "").strip()
            if note and note not in read_notes(root, aid):
                cur = read_notes(root, aid)
                write_notes(root, aid, (cur.rstrip() + "\n\n" if cur.strip() else "") + note + "\n")
        p.unlink()
    return True
