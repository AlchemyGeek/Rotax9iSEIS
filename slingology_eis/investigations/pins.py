"""
The owner's questions and pins (Spec 16 D16, §6): *Mark for Claude*.

    workspaces/<id>/pins.json     questions and pins (carried by export)

A **pin** is where to look and one sentence — flight, window, the
channels shown, a note, when — and nothing else: no analysis is stored
with it. A **question** is the owner's title over pins across flights,
with the inbox's statuses (*new / investigating / nothing-here / watch /
acted*), the notebook that took it up and a note. A pin with no question
is *unassigned*.

    {"version": 1,
     "questions": [{"id": "q-…", "title", "status", "study_id", "note",
                    "created", "updated", "resolved_at"}],
     "pins": [{"id": "p-…", "question_id": "q-…" | null, "flight",
               "start_s", "end_s", "channels": [...], "note", "created",
               "status"?, "study_id"?}]}

A pin takes its question's resolution when the question is resolved
(`status`, `study_id`); an open question's pins carry none.

Flights are named by flight_id inside the workspace. An export names
them by content fingerprint (S5, `src:<source_key>`) and the recipient's
first read maps each back to the flight here with that source, as a
notebook's import does; one with no such flight yet keeps its
fingerprint until a Sync brings it.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .inbox import OPEN, STATUSES

FILENAME = "pins.json"
MAX_NOTE = 2000
MAX_TITLE = 200
MAX_CHANNELS = 8


class PinsError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _empty() -> dict:
    return {"version": 1, "questions": [], "pins": []}


def _read(ws_dir: Path) -> dict:
    p = ws_dir / FILENAME
    if not p.is_file():
        return _empty()
    try:
        doc = json.loads(p.read_text())
    except ValueError:
        return _empty()
    if not isinstance(doc, dict):
        return _empty()
    doc.setdefault("version", 1)
    doc.setdefault("questions", [])
    doc.setdefault("pins", [])
    return doc


def save(ws_dir: Path, doc: dict) -> None:
    (ws_dir / FILENAME).write_text(json.dumps(doc, indent=2))


def load(ws_dir: Path) -> dict:
    """The document, with imported fingerprints mapped to flights here."""
    doc = _read(ws_dir)
    if any(str(p.get("flight") or "").startswith("src:") for p in doc["pins"]):
        from .notebook import fingerprints
        _, back = fingerprints(ws_dir)
        changed = False
        for p in doc["pins"]:
            fid = back.get(p.get("flight"))
            if fid:
                p["flight"], changed = fid, True
        if changed:
            save(ws_dir, doc)
    return doc


def for_export(doc: dict, ws_dir: Path) -> dict:
    """The document as it leaves the workspace: flights by fingerprint."""
    from .notebook import fingerprints
    out, _ = fingerprints(ws_dir)
    doc = json.loads(json.dumps(doc))
    for p in doc.get("pins") or []:
        p["flight"] = out.get(p.get("flight"), p.get("flight"))
    return doc


# ── reading ────────────────────────────────────────────────────────────────

def question(doc: dict, qid) -> dict:
    q = next((x for x in doc["questions"] if x["id"] == qid), None)
    if q is None:
        raise PinsError("NOT_FOUND", f"no question {qid}")
    return q


def _pin(doc: dict, pid) -> dict:
    p = next((x for x in doc["pins"] if x["id"] == pid), None)
    if p is None:
        raise PinsError("NOT_FOUND", f"no pin {pid}")
    return p


def pins_of(doc: dict, qid: Optional[str]) -> list[dict]:
    """A question's pins (None: the unassigned ones) in the order they were marked."""
    return [p for _i, p in sorted(((i, p) for i, p in enumerate(doc["pins"]) if p.get("question_id") == qid),
                                  key=lambda t: (t[1].get("created") or "", t[0]))]


def newest_open(doc: dict) -> Optional[dict]:
    """The open question most recently marked into (or created)."""
    def last(q):
        ps = pins_of(doc, q["id"])
        return max([q.get("created") or ""] + [p.get("created") or "" for p in ps])
    def pos(q):
        idx = [i for i, p in enumerate(doc["pins"]) if p.get("question_id") == q["id"]]
        return max(idx) if idx else -1
    open_ = [q for q in doc["questions"] if q.get("status") in OPEN]
    return max(open_, key=lambda q: (last(q), pos(q), doc["questions"].index(q))) if open_ else None


def listing(doc: dict, status: Optional[list] = None, describe=None) -> dict:
    """Questions (newest first within status order) each with its pins,
    and the unassigned pins. `describe(pin)` adds the flight's labels."""
    if status:
        bad = [s for s in status if s not in STATUSES]
        if bad:
            raise PinsError("BAD_PARAMS", f"status is one of {', '.join(STATUSES)}")
    dec = (lambda p: {**p, **describe(p)}) if describe else (lambda p: dict(p))
    order = {s: i for i, s in enumerate(STATUSES)}
    qs = [q for q in doc["questions"] if not status or q.get("status") in status]
    pos = {q["id"]: i for i, q in enumerate(doc["questions"])}
    qs.sort(key=lambda q: (q.get("created") or "", pos[q["id"]]), reverse=True)   # newest first …
    qs.sort(key=lambda q: order.get(q.get("status"), len(order)))       # … within status order (stable)
    out = []
    for q in qs:
        ps = [dec(p) for p in pins_of(doc, q["id"])]
        out.append({**q, "pins": ps, "pin_count": len(ps), "newest_note": next((p.get("note") for p in reversed(ps) if p.get("note")), None)})
    counts = {s: sum(1 for q in doc["questions"] if q.get("status") == s) for s in STATUSES}
    return {"questions": out, "unassigned": [dec(p) for p in pins_of(doc, None)], "counts": counts,
            "pins": len(doc["pins"])}


# ── writing ────────────────────────────────────────────────────────────────

def _text(v, limit: int, what: str) -> Optional[str]:
    if v is None:
        return None
    if not isinstance(v, str):
        raise PinsError("BAD_PARAMS", f"{what} is text")
    v = v.strip()
    return v[:limit] or None


def _window(start_s, end_s) -> tuple[float, float]:
    try:
        a, b = float(start_s), float(end_s)
    except (TypeError, ValueError):
        raise PinsError("BAD_PARAMS", "a pin needs start_s and end_s, in seconds from the start of the flight")
    if not (0 <= a < b):
        raise PinsError("BAD_PARAMS", "a pin's window runs forward from start_s ≥ 0 to a later end_s")
    return round(a, 1), round(b, 1)


def _channels(ch) -> list[str]:
    if ch is None:
        return []
    if not isinstance(ch, list) or not all(isinstance(c, str) and c for c in ch):
        raise PinsError("BAD_PARAMS", "channels is a list of channel ids")
    return list(dict.fromkeys(ch))[:MAX_CHANNELS]


def _target_question(doc: dict, target) -> Optional[dict]:
    """`target`: None/"" (unassigned), an id, {"id": …} or {"title": …} (new)."""
    if target in (None, "", {}):
        return None
    if isinstance(target, str):
        return question(doc, target)
    if isinstance(target, dict):
        if target.get("id"):
            return question(doc, target["id"])
        title = _text(target.get("title"), MAX_TITLE, "a question's title")
        if not title:
            raise PinsError("BAD_PARAMS", "a new question needs a title")
        q = {"id": f"q-{uuid.uuid4().hex[:8]}", "title": title, "status": "new", "study_id": None,
             "note": None, "created": _now(), "updated": _now(), "resolved_at": None}
        doc["questions"].append(q)
        return q
    raise PinsError("BAD_PARAMS", "question is an id, {\"id\": …} or {\"title\": …} for a new one, or null")


def pin(ws_dir: Path, flight: str, start_s, end_s, *, channels=None, note=None, question=None) -> tuple[dict, Optional[dict]]:
    target = question
    if not flight or not isinstance(flight, str):
        raise PinsError("BAD_PARAMS", "a pin needs a flight_id")
    a, b = _window(start_s, end_s)
    doc = load(ws_dir)
    q = _target_question(doc, target)
    p = {"id": f"p-{uuid.uuid4().hex[:8]}", "question_id": q["id"] if q else None, "flight": flight,
         "start_s": a, "end_s": b, "channels": _channels(channels), "note": _text(note, MAX_NOTE, "a note"),
         "created": _now()}
    if q is not None:
        q["updated"] = _now()
        _inherit(p, q)
    doc["pins"].append(p)
    save(ws_dir, doc)
    return p, q


def _inherit(p: dict, q: dict) -> None:
    if q.get("status") in OPEN:
        p.pop("status", None)
        p.pop("study_id", None)
    else:
        p["status"], p["study_id"] = q["status"], q.get("study_id")


def edit_pin(ws_dir: Path, pin_id: str, **changes) -> tuple[dict, Optional[dict]]:
    """note, channels, start_s/end_s, and `question` (move: id, {"title"}
    for a new one, or null for unassigned) — only the keys given change."""
    doc = load(ws_dir)
    p = _pin(doc, pin_id)
    q = None
    if "note" in changes:
        p["note"] = _text(changes["note"], MAX_NOTE, "a note")
    if "channels" in changes:
        p["channels"] = _channels(changes["channels"])
    if "start_s" in changes or "end_s" in changes:
        p["start_s"], p["end_s"] = _window(changes.get("start_s", p["start_s"]), changes.get("end_s", p["end_s"]))
    if "question" in changes:
        q = _target_question(doc, changes["question"])
        p["question_id"] = q["id"] if q else None
        if q is None:
            p.pop("status", None)
            p.pop("study_id", None)
        else:
            q["updated"] = _now()
            _inherit(p, q)
    elif p.get("question_id"):
        q = question(doc, p["question_id"])
    save(ws_dir, doc)
    return p, q


def delete_pin(ws_dir: Path, pin_id: str) -> dict:
    doc = load(ws_dir)
    p = _pin(doc, pin_id)
    doc["pins"] = [x for x in doc["pins"] if x["id"] != pin_id]
    save(ws_dir, doc)
    return p


def edit_question(ws_dir: Path, question_id: str, *, title=None, note=None) -> dict:
    doc = load(ws_dir)
    q = question(doc, question_id)
    if title is not None:
        t = _text(title, MAX_TITLE, "a question's title")
        if not t:
            raise PinsError("BAD_PARAMS", "a question needs a title")
        q["title"] = t
    if note is not None:
        q["note"] = _text(note, MAX_NOTE, "a note")
    q["updated"] = _now()
    save(ws_dir, doc)
    return q


def delete_question(ws_dir: Path, question_id: str) -> tuple[dict, int]:
    """The question goes; its pins stay, unassigned (the least destructive
    reading — a pin is deleted on its own)."""
    doc = load(ws_dir)
    q = question(doc, question_id)
    doc["questions"] = [x for x in doc["questions"] if x["id"] != question_id]
    n = 0
    for p in doc["pins"]:
        if p.get("question_id") == question_id:
            p["question_id"] = None
            p.pop("status", None)
            p.pop("study_id", None)
            n += 1
    save(ws_dir, doc)
    return q, n


def resolve(ws_dir: Path, question_id: str, status: str, *, study_id=None, note=None) -> dict:
    """A question's status, notebook and note; its pins take the
    resolution (an open status clears it from them)."""
    if status not in STATUSES:
        raise PinsError("BAD_PARAMS", f"status is one of {', '.join(STATUSES)}")
    doc = load(ws_dir)
    q = question(doc, question_id)
    q["status"] = status
    if study_id is not None:
        q["study_id"] = study_id or None
    if note is not None:
        q["note"] = _text(note, MAX_NOTE, "a note")
    q["resolved_at"] = None if status in OPEN else _now()
    q["updated"] = _now()
    for p in doc["pins"]:
        if p.get("question_id") == question_id:
            _inherit(p, q)
    save(ws_dir, doc)
    return q
