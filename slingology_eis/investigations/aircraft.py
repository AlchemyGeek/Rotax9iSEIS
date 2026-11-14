"""
The aircraft document (Spec 16 §4.4): a small per-workspace record of
the facts an investigation needs on its first line — airframe, engine
serial, propeller and controller models, firmware versions, avionics.

    workspaces/<id>/aircraft.json                  (Spec 02 §5.3)

Free-text fields, aircraft-neutral labels; carried by workspace export.
The registration is deliberately not a field: the tail number lives in
the logs, and export anonymisation (Spec 02 §7.6) can only pseudonymise
what it knows is an identity.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

FILENAME = "aircraft.json"
MAX_FIELD_CHARS = 2000

# (key, label, hint) — the order Settings → Aircraft shows them in.
FIELDS: tuple[tuple[str, str, str], ...] = (
    ("airframe", "Airframe", "Make, model, serial, year"),
    ("engine_serial", "Engine serial number", "As on the engine data plate"),
    ("propeller", "Propeller", "Make, model, blades, hub"),
    ("prop_controller", "Propeller controller", "Governor or controller model"),
    ("firmware", "Firmware versions", "Controller, hub, ECU, avionics — one per line"),
    ("avionics", "Avionics", "Displays and engine monitoring"),
    ("notes", "Notes", "Anything else an investigation should know"),
)
KEYS = tuple(k for k, _l, _h in FIELDS)


class AircraftError(Exception):
    pass


def _path(ws_dir: Path) -> Path:
    return ws_dir / FILENAME


def load(ws_dir: Path) -> dict:
    p = _path(ws_dir)
    if not p.is_file():
        return {k: "" for k in KEYS}
    try:
        doc = json.loads(p.read_text())
    except ValueError:
        return {k: "" for k in KEYS}
    out = {k: str(doc.get(k) or "") for k in KEYS}
    if doc.get("updated"):
        out["updated"] = doc["updated"]
    return out


def save(ws_dir: Path, fields: dict) -> dict:
    """Replace the given fields (others kept); unknown keys are refused."""
    if not isinstance(fields, dict):
        raise AircraftError("aircraft fields are an object")
    unknown = sorted(set(fields) - set(KEYS))
    if unknown:
        raise AircraftError(f"unknown aircraft field(s) {', '.join(unknown)}; one of {', '.join(KEYS)}")
    doc = load(ws_dir)
    for k, v in fields.items():
        v = "" if v is None else str(v)
        if len(v) > MAX_FIELD_CHARS:
            raise AircraftError(f"{k} is longer than {MAX_FIELD_CHARS} characters")
        doc[k] = v.strip()
    doc["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _path(ws_dir).write_text(json.dumps(doc, indent=2))
    return doc


def field_list() -> list[dict]:
    return [{"key": k, "label": label, "hint": hint} for k, label, hint in FIELDS]
