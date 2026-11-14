"""
Studies (Spec 06 §10): the saved record of a Research session.

    workspaces/<id>/studies/<study_id>.json        (Spec 02 §5.3)

A study references flights by `flight_id` — the hash of the flight
fingerprint (aircraft ident, source identity, start minute; Spec 01
§6.1), so the same flight matches on another machine whichever export of
it the recipient holds — never by path or content. `tests[].result` and
`cache` are derived and may be dropped; everything else is the study.

`.eisstudy` (§10.2) is a zip: `study.json` (the study with its results
and descriptor cache), and per test its evidence table as CSV and a
static SVG chart. Importing always creates a new study; flights are
matched by flight_id; unmatched flights are listed and contribute no
slices. With none matched the study opens **read-only** (Q5): the
sender's cached results under the §10.2 label, and one action, *Run this
on my flights*, which makes a new study with the same rules, references
and tests over the recipient's own flights.
"""
from __future__ import annotations

import copy
import io
import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .. import __version__
from .. import workspace as ws
from . import questions as Q
from .descriptors import STANDARD_CHANNELS
from .render import chart_svg, evidence_csv
from .rules import RuleError, normalise_hand_slice, normalise_rule
from .slices import Cache, build_slice_set

FORMAT = "eisstudy"
FORMAT_VERSION = 1
SUFFIX = ".eisstudy"
READ_ONLY_LABEL = "sender's results; none of these flights are in this workspace"
_ID_RE = re.compile(r"^st-[0-9a-f]{6,32}$")


class StudyError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def studies_dir(ws_dir: Path) -> Path:
    return ws_dir / "studies"


def _path(ws_dir: Path, study_id: str) -> Path:
    if not _ID_RE.match(str(study_id or "")):
        raise StudyError("BAD_PARAMS", f"not a study id: {study_id!r}")
    return studies_dir(ws_dir) / f"{study_id}.json"


def _selection(sel: Optional[dict]) -> dict:
    sel = dict(sel or {"mode": "all"})
    mode = sel.get("mode", "all")
    if mode not in ("all", "flights"):
        raise RuleError(f"selection mode {mode!r}; one of all, flights")
    out = {"mode": mode}
    if mode == "flights":
        out["flights"] = [str(f) for f in (sel.get("flights") or [])]
    out["split"] = sel.get("split")
    return out


def _test_slices(sl) -> Optional[dict]:
    """A question's own slice set (Spec 16 §5): a notebook may ask a
    question of another preset than the study's ("is it absent in
    climb?"). Absent: the study's selection, rules and hand slices."""
    if not sl:
        return None
    if not isinstance(sl, dict):
        raise RuleError("a question's slices are {selection?, slice_rules?, hand_slices?}")
    out = {"selection": _selection(sl.get("selection")),
           "slice_rules": [normalise_rule(r) for r in (sl.get("slice_rules") or [])],
           "hand_slices": [normalise_hand_slice(h) for h in (sl.get("hand_slices") or [])]}
    if not out["slice_rules"] and not out["hand_slices"]:
        raise RuleError("a question's own slices need a slice rule or a hand slice")
    return out


def _test(t: dict) -> dict:
    if not isinstance(t, dict) or t.get("test_id") not in Q.QUESTIONS:
        raise RuleError(f"a test needs a test_id, one of {', '.join(Q.QUESTIONS)}; got {t!r}")
    out = {"test_id": t["test_id"], "version": Q.VERSIONS[t["test_id"]], "params": dict(t.get("params") or {}),
           "channels": list(t.get("channels") or [])}
    sl = _test_slices(t.get("slices"))
    if sl is not None:
        out["slices"] = sl
    if t.get("result") is not None:
        out["result"] = t["result"]
    if t.get("error"):
        out["error"] = str(t["error"])
    return out


def _references(refs) -> list[dict]:
    refs = [dict(r) for r in refs or []]
    Q._normalise_user_refs(refs)          # validates; the study keeps them as typed
    return refs


def _signal(sig) -> Optional[dict]:
    """Signal view's state (§9.1, §10.1): the flight, its channels and
    reference, and the window — what the study reopens on."""
    if not sig:
        return None
    if not isinstance(sig, dict):
        raise RuleError("signal is an object")
    win = sig.get("window")
    if win is not None:
        if not isinstance(win, dict):
            raise RuleError("signal.window is {start_s, end_s}")
        a, b = float(win.get("start_s", 0)), float(win.get("end_s", 0))
        if b <= a:
            raise RuleError(f"signal.window end_s {b:g} must be after start_s {a:g}")
        win = {"start_s": a, "end_s": b}
    return {"flight": str(sig["flight"]) if sig.get("flight") else None,
            "channels": [str(c) for c in (sig.get("channels") or [])],
            "reference": str(sig["reference"]) if sig.get("reference") else None, "window": win}


def _compare(cmp) -> Optional[dict]:
    """Compare's state (§9.2, §10.1): the pinned row (a slice id, or a
    flight id when collapsed), collapse, the chart's axes and colouring,
    and the channels. Pinning survives save (D12)."""
    if not cmp:
        return None
    if not isinstance(cmp, dict):
        raise RuleError("compare is an object")
    chart = dict(cmp.get("chart") or {})
    return {"pinned": str(cmp["pinned"]) if cmp.get("pinned") else None, "collapse": bool(cmp.get("collapse")),
            "channels": [str(c) for c in (cmp.get("channels") or [])],
            "reference": str(cmp["reference"]) if cmp.get("reference") else None,
            "chart": {k: chart[k] for k in ("x", "y", "colour") if chart.get(k)}}


def normalise(doc: dict) -> dict:
    """A study document with every field validated (RuleError otherwise)."""
    if not isinstance(doc, dict):
        raise RuleError("a study is an object")
    out = {
        "study_id": doc.get("study_id"), "name": str(doc.get("name") or "Untitled study"),
        "created": doc.get("created"), "updated": doc.get("updated"),
        "selection": _selection(doc.get("selection")),
        "slice_rules": [normalise_rule(r) for r in (doc.get("slice_rules") or [])],
        "hand_slices": [normalise_hand_slice(h) for h in (doc.get("hand_slices") or [])],
        "references": _references(doc.get("references")),
        "tests": [_test(t) for t in (doc.get("tests") or [])],
        "windows": dict(doc.get("windows") or {}),
        "view": dict(doc.get("view") or {"anchor": "crossing", "channels": ["rpm", "map_inhg", "fuel_flow_gph"]}),
        "notes": str(doc.get("notes") or ""),
        "provenance": dict(doc.get("provenance") or {}),
    }
    for k, fn in (("signal", _signal), ("compare", _compare)):
        v = fn(doc.get(k))
        if v is not None:
            out[k] = v
    # Spec 16 §5: the notebook. A study without `cells` is a hand study
    # whose cells are its questions; its document stays as it was.
    from ..investigations import notebook as NB
    meta = NB.normalise_meta(doc)
    if doc.get("cells") is not None or meta["kind"] != "hand" or meta["author"] != "user" or len(meta) > 2:
        out.update(meta)
    cells = NB.normalise_cells(doc.get("cells"), len(out["tests"]))
    if cells is not None:
        out["cells"] = cells
    for k in ("cache", "read_only", "imported", "flights", "last_run"):
        if doc.get(k) is not None:
            out[k] = doc[k]
    return out


def summary(doc: dict) -> dict:
    first = next((t for t in doc.get("tests") or [] if t.get("result")), None)
    return {"study_id": doc["study_id"], "name": doc["name"], "updated": doc.get("updated"),
            "created": doc.get("created"), "finding": first["result"]["finding"] if first else None,
            "tests": len(doc.get("tests") or []), "read_only": bool(doc.get("read_only")),
            "flights": len(doc.get("flights") or []),
            # Spec 16 §5: who wrote it and what it asks.
            "kind": doc.get("kind") or "hand", "author": doc.get("author") or "user",
            "question": doc.get("question"), "status": doc.get("status"), "summary": doc.get("summary"),
            "cells": len(doc["cells"]) if doc.get("cells") is not None else len(doc.get("tests") or [])}


# ── Storage ────────────────────────────────────────────────────────────────

def save(ws_dir: Path, doc: dict, *, engine_model: str = "") -> dict:
    existing = None
    if doc.get("study_id"):
        p = _path(ws_dir, doc["study_id"])
        existing = json.loads(p.read_text()) if p.is_file() else None
        if existing and existing.get("read_only"):
            raise StudyError("READ_ONLY", "this study holds the sender's results and can't be edited; "
                                          "use Run this on my flights")
    out = normalise(doc)
    out["study_id"] = out["study_id"] or f"st-{uuid.uuid4().hex[:12]}"
    out["created"] = (existing or {}).get("created") or out["created"] or _now()
    out["updated"] = _now()
    out["provenance"] = {**out["provenance"], "app": "SlingologyEIS",
                         "engine": out["provenance"].get("engine") or __version__,
                         "engine_model": out["provenance"].get("engine_model") or engine_model}
    if existing and not out.get("cache") and existing.get("cache"):
        out["cache"] = existing["cache"]     # derived data survives an edit that didn't send it
    studies_dir(ws_dir).mkdir(parents=True, exist_ok=True)
    _path(ws_dir, out["study_id"]).write_text(json.dumps(out, indent=2, sort_keys=False))
    return out


def load(ws_dir: Path, study_id: str) -> dict:
    p = _path(ws_dir, study_id)
    if not p.is_file():
        raise StudyError("NOT_FOUND", f"no study {study_id}")
    return json.loads(p.read_text())


def list_all(ws_dir: Path) -> list[dict]:
    d = studies_dir(ws_dir)
    out = []
    for p in sorted(d.glob("st-*.json")) if d.is_dir() else []:
        try:
            out.append(summary(json.loads(p.read_text())))
        except (ValueError, KeyError):
            continue
    return sorted(out, key=lambda s: s.get("updated") or "", reverse=True)


def delete(ws_dir: Path, study_id: str) -> bool:
    p = _path(ws_dir, study_id)
    if not p.is_file():
        return False
    p.unlink()
    from ..investigations import notebook as NB
    NB.remove_files(ws_dir, study_id)      # the notebook's files/ (Spec 16 §5)
    return True


# ── Running ────────────────────────────────────────────────────────────────

def _channels_for(t: dict) -> tuple[list[str], str]:
    """Channels a test needs, and its coupling reference channel."""
    tid, chans = t["test_id"], list(t.get("channels") or [])
    if tid == "cycling":
        return (chans[:1] or ["rpm"]), "rpm"
    if tid == "coupling":
        chans = chans or ["rpm", "map_inhg"]
        return chans, chans[0]
    if tid == "groups":
        desc = t["params"].get("descriptor") or f"{(chans or ['rpm'])[0]}.swing"
        return [desc.split(".", 1)[0]], "rpm"
    return (chans or list(STANDARD_CHANNELS)), "rpm"


async def run(ws_dir: Path, sources, doc: dict, *, engine_cfg: Optional[dict], assignments: Optional[dict] = None,
              on_progress: Optional[Callable[[dict], None]] = None) -> dict:
    """Run every test of a study, filling `tests[].result`, `cache` and
    `flights` (the flights whose logs the study read). One slice set is
    built per coupling reference channel, from the descriptor cache where
    it still matches."""
    if doc.get("read_only"):
        raise StudyError("READ_ONLY", "this study holds the sender's results; use Run this on my flights")
    doc = normalise(doc)
    own = {"selection": doc["selection"], "slice_rules": doc["slice_rules"], "hand_slices": doc["hand_slices"]}
    has_own = bool(doc["slice_rules"] or doc["hand_slices"])
    if not has_own and (not doc["tests"] or any(not t.get("slices") for t in doc["tests"])):
        if not doc["tests"] and doc.get("cells") is not None:
            return doc                      # a notebook with no question: nothing for run_study to do
        raise RuleError("the study has no slice rule or hand slice")
    cache = Cache(doc.get("cache"))

    def set_key(t) -> str:
        return json.dumps(t.get("slices"), sort_keys=True) if t.get("slices") else ""

    plans: dict[tuple, set] = {}
    for t in doc["tests"]:
        chans, ref = _channels_for(t)
        plans.setdefault((ref, set_key(t)), set()).update(chans)
    if not plans:
        plans[("rpm", "")] = set(STANDARD_CHANNELS)
    sets = {}
    for (ref, key), chans in plans.items():
        src = json.loads(key) if key else own
        ss = await build_slice_set(ws_dir, sources, selection=src["selection"], rules=src["slice_rules"],
                                   hand_slices=src["hand_slices"], channels=sorted(chans), reference=ref,
                                   windows=doc.get("windows"), assignments=assignments, cache=cache,
                                   on_progress=on_progress)
        d = ss.to_dict()
        d["selection"] = src["selection"]
        sets[(ref, key)] = d
    for t in doc["tests"]:
        chans, ref = _channels_for(t)
        t.pop("error", None)
        try:
            t["result"] = Q.run(t["test_id"], sets[(ref, set_key(t))], channels=t.get("channels") or None,
                                params=t["params"], references=doc["references"], engine_cfg=engine_cfg)
        except RuleError as e:
            # One test that can't run on this set (too few slices, a missing
            # channel) doesn't stop the others; it says why.
            t["result"] = None
            t["error"] = str(e)
    first = sets.get(next((k for k in sets if k[1] == ""), next(iter(sets))))
    doc["flights"] = sorted({s["flight"] for d in sets.values() for s in d["slices"]})
    doc["last_run"] = {"slices": first["count"], "by_source": first["by_source"],
                       "missing_flights": first["missing_flights"], "unreachable_flights": first["unreachable_flights"],
                       "engine": __version__}
    doc["cache"] = cache.to_dict()
    return doc


# ── .eisstudy ──────────────────────────────────────────────────────────────

def safe_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._ -]+", "", name or "").strip().replace(" ", "-")
    return s or "study"


def export_bytes(doc: dict, files: Optional[Path] = None) -> bytes:
    """The study as a `.eisstudy` zip; a notebook's `files/` travel with it
    (Spec 16 §5)."""
    body = {"format": FORMAT, "format_version": FORMAT_VERSION, "exported": _now(),
            "provenance": {**(doc.get("provenance") or {}), "exported_by_engine": __version__},
            "study": doc}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("study.json", json.dumps(body, indent=2))
        for i, t in enumerate(doc.get("tests") or [], start=1):
            if t.get("result"):
                z.writestr(f"evidence/{i:02d}-{t['test_id']}.csv", evidence_csv(t["result"]))
                z.writestr(f"charts/{i:02d}-{t['test_id']}.svg", chart_svg(t["result"]))
        if files is not None and files.is_dir():
            for p in sorted(files.rglob("*")):
                if p.is_file() and not any(part.startswith(".") for part in p.relative_to(files).parts):
                    z.writestr(f"files/{p.relative_to(files).as_posix()}", p.read_bytes())
    return buf.getvalue()


_MAX_FILES_BYTES = 200 * 1024 * 1024


def parse_export(data: bytes) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            body = json.loads(z.read("study.json"))
            files, total = {}, 0
            for info in z.infolist():
                n = info.filename
                rel = n[len("files/"):] if n.startswith("files/") else None
                if info.is_dir() or not rel or rel.startswith(("/", ".")) or ".." in rel.split("/") or "\\" in rel:
                    continue
                total += info.file_size
                if total > _MAX_FILES_BYTES:
                    raise StudyError("BAD_PARAMS", "this .eisstudy's files are larger than any study's should be")
                files[rel] = z.read(n)
            body["_files"] = files
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise StudyError("BAD_PARAMS", f"not a .eisstudy file ({e})")
    if body.get("format") != FORMAT:
        raise StudyError("BAD_PARAMS", "not a .eisstudy file")
    if int(body.get("format_version") or 0) > FORMAT_VERSION:
        raise StudyError("BAD_PARAMS", "this study was written by a newer app; update to import it")
    return body


def referenced_flights(doc: dict) -> list[str]:
    """The sender's flights the study is about: its selection's, its hand
    slices', and those its last run read."""
    out = list((doc.get("selection") or {}).get("flights") or [])
    out += [h["flight"] for h in doc.get("hand_slices") or []]
    if (doc.get("signal") or {}).get("flight"):
        out.append(doc["signal"]["flight"])
    out += list(doc.get("flights") or [])
    from ..investigations import notebook as NB
    out += NB.flights_of(doc)           # the flights a notebook's code cells read
    return list(dict.fromkeys(out))


def import_bytes(ws_dir: Path, data: bytes, *, engine_model: str = "") -> dict:
    """§10.2: always a new study in this workspace. Returns
    {study, matched, missing, read_only}."""
    body = parse_export(data)
    sent = copy.deepcopy(body["study"])
    flights = referenced_flights(sent)
    present = set(ws.list_flight_ids(ws_dir))
    matched = [f for f in flights if f in present]
    missing = [f for f in flights if f not in present]
    sent.pop("study_id", None)
    sent["created"] = None
    imported = {"at": _now(), "sender": body.get("provenance") or {}, "name": sent.get("name"),
                "matched": matched, "missing": missing}
    read_only = bool(flights) and not matched
    if read_only:
        sent["read_only"] = {"label": READ_ONLY_LABEL, "sender": body.get("provenance") or {}}
    else:
        for t in sent.get("tests") or []:
            t.pop("result", None)    # the sender's numbers are recomputed here, never shown as ours
        sent.pop("read_only", None)
        if (sent.get("selection") or {}).get("mode") == "all" and flights:
            # The study is about the sender's flights: pin them, so this
            # workspace's other flights don't join it (Run this on my
            # flights is the way to apply the rules to those).
            sent["selection"] = {"mode": "flights", "flights": matched, "split": sent["selection"].get("split")}
        elif (sent.get("selection") or {}).get("mode") == "flights":
            sent["selection"]["flights"] = [f for f in sent["selection"]["flights"] if f in present]
        sent["hand_slices"] = [h for h in sent.get("hand_slices") or [] if h["flight"] in present]
        _forget_absent(sent, present)
    sent["imported"] = imported
    sent["flights"] = flights
    from ..investigations import notebook as NB
    if sent.get("cells") is not None:
        NB.mark_imported(sent, present)     # code outputs are the sender's; per-cell read-only (Spec 16 §5)
    studies_dir(ws_dir).mkdir(parents=True, exist_ok=True)
    doc = normalise(sent)
    doc["study_id"] = f"st-{uuid.uuid4().hex[:12]}"
    files_out = NB.files_dir(ws_dir, doc["study_id"])
    for rel, data in (body.get("_files") or {}).items():
        target = files_out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    doc["created"] = doc["updated"] = _now()
    doc["provenance"] = {**(doc.get("provenance") or {}), "engine_model": doc["provenance"].get("engine_model") or engine_model}
    _path(ws_dir, doc["study_id"]).write_text(json.dumps(doc, indent=2))
    return {"study": doc, "matched": matched, "missing": missing, "read_only": read_only}


def _pinned_flight(pinned: Optional[str]) -> Optional[str]:
    """A pinned row names a slice (`<flight_id>:…`) or a flight."""
    return pinned.split(":", 1)[0] if pinned else None


def _forget_absent(doc: dict, present: set) -> None:
    """Signal's flight and Compare's pinned row name the sender's flights;
    where this workspace lacks them they are cleared, the rest kept."""
    sig = doc.get("signal")
    if sig and sig.get("flight") and sig["flight"] not in present:
        doc["signal"] = {**sig, "flight": None, "window": None}
    cmp = doc.get("compare")
    if cmp and cmp.get("pinned") and _pinned_flight(cmp["pinned"]) not in present:
        doc["compare"] = {**cmp, "pinned": None}


def _test_for_my_flights(t: dict) -> dict:
    out = {k: v for k, v in t.items() if k not in ("result", "error")}
    if out.get("slices"):
        # A question's own slice set names the sender's flights the way the
        # study's does: it widens to this workspace's flights.
        sl = out["slices"]
        out["slices"] = {"selection": {"mode": "all", "split": (sl.get("selection") or {}).get("split")},
                         "slice_rules": sl.get("slice_rules") or [], "hand_slices": []}
        if not out["slices"]["slice_rules"]:
            out.pop("slices")
    return out


def for_my_flights(doc: dict) -> dict:
    """*Run this on my flights* (Q5): the same rules, references and tests
    over this workspace's flights — a new, editable study. Hand slices
    name the sender's flights, so they don't carry over."""
    from ..investigations import notebook as NB
    cells = None
    if doc.get("cells") is not None:
        cells = copy.deepcopy(doc["cells"])
        # Question cells re-run here; code cells keep the sender's outputs,
        # marked, until this workspace re-runs them (Spec 16 D8).
        NB.mark_imported({"cells": cells}, set())
        for c in cells:
            c.pop("read_only", None)
    return normalise({
        "name": f"{doc.get('name') or 'Study'} (my flights)",
        "cells": cells, "kind": doc.get("kind"), "author": doc.get("author"), "question": doc.get("question"),
        "selection": {"mode": "all", "split": (doc.get("selection") or {}).get("split")},
        "slice_rules": doc.get("slice_rules"), "hand_slices": [], "references": doc.get("references"),
        "tests": [_test_for_my_flights(t) for t in doc.get("tests") or []],
        "windows": doc.get("windows"), "view": doc.get("view"), "notes": doc.get("notes"),
        # Signal's flight and the pinned row are the sender's; the channels,
        # the chart and the derived rule (in slice_rules) carry over.
        "signal": {**doc["signal"], "flight": None, "window": None} if doc.get("signal") else None,
        "compare": {**doc["compare"], "pinned": None} if doc.get("compare") else None,
        "provenance": {"from_study": (doc.get("imported") or {}).get("name") or doc.get("name")},
    })
