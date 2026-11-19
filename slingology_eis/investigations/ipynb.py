"""
The investigation notebook (Spec 16 §5, D12): `studies/<id>/notebook.ipynb`
(nbformat 4) with `files/` beside it — the stored form *is* the Jupyter
form, so the folder zips as a notebook JupyterLab opens unchanged.

Notebook metadata `slingology` (§5.1): id, name, kind (investigation |
question-for-type), author (claude | user), question, status (open |
finished), summary, inbox_candidate, engine, created, updated — and, when
they apply, engine_type (D9), imported, converted_from.

Cells are markdown and code. A code cell's `metadata.slingology` holds
`ran` {engine, flights, at, ms, status, digest, caps?} and, after a re-run
whose outputs differ, `pending` {outputs, ran} until accepted or discarded
(D4); an imported cell may carry `ran_elsewhere` and `read_only`.

D14: every investigation begins with the setup cell (id `setup`,
`from slingology_eis import eis; eis.open("<workspace id>")`), and the
metadata names the workspace (`workspace_id`). `ran.digest` is a digest of
the outputs EIS stored; a cell whose outputs no longer match it was run by
a kernel outside EIS and saved in place — it is marked `ran_elsewhere:
"external"` until a bench re-run or `accept_external`. Outputs are
standard: `stream`, `execute_result`/`display_data` with `text/plain`,
`text/html` (tables), `image/svg+xml` (figures), the log view's
`application/vnd.slingology.logview+json` (§5.2), and `error`.

A study still stored the old way (`studies/st-*.json`) is converted here
on first load (`convert`): a Session D investigation (that document with a
`cells` list), the original kept beside the notebook as `.session-d.json`;
and a hand study (Spec 06 v1.0 retired them, Spec 16 D15) — a markdown
cell per question with its §8 result text and the eis code that
reproduces it, the stored output being the stored result — the original
kept as `.hand-study.json`.
"""
from __future__ import annotations

import copy
import io
import json
import pprint
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .. import __version__
from .eis_lib import LOGVIEW_MIME

NOTEBOOK = "notebook.ipynb"
BACKUP = ".session-d.json"
BACKUP_HAND = ".hand-study.json"
KINDS = ("investigation", "question-for-type")
AUTHORS = ("claude", "user")
META_KEYS = ("id", "name", "kind", "author", "question", "status", "summary", "inbox_candidate", "engine",
             "created", "updated")
MAX_SOURCE_CHARS = 100_000
FIGURE_MIMES = ("image/svg+xml", "image/png", LOGVIEW_MIME)
_ID = re.compile(r"^st-[0-9a-f]{12}$")
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
SETUP_ID = "setup"
_SETUP_OPEN = re.compile(r'eis\.open\(\s*(["\'])([^"\']*)\1')


class NotebookError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def folder(ws_dir: Path, study_id: str) -> Path:
    return Path(ws_dir) / "studies" / study_id


def path(ws_dir: Path, study_id: str) -> Path:
    return folder(ws_dir, study_id) / NOTEBOOK


def files_dir(ws_dir: Path, study_id: str) -> Path:
    return folder(ws_dir, study_id) / "files"


def exists(ws_dir: Path, study_id: Optional[str]) -> bool:
    return bool(study_id) and _ID.match(str(study_id)) is not None and path(ws_dir, study_id).is_file()


def meta(nb: dict) -> dict:
    return nb.setdefault("metadata", {}).setdefault("slingology", {})


def slmeta(cell: dict) -> dict:
    return cell.setdefault("metadata", {}).setdefault("slingology", {})


def text(src) -> str:
    return "".join(src) if isinstance(src, list) else str(src or "")


# ── Creating, reading, writing ─────────────────────────────────────────────

def new(*, name: str, question: Optional[str] = None, kind: str = "investigation", author: str = "claude",
        inbox_candidate: Optional[str] = None, engine_type: Optional[str] = None,
        study_id: Optional[str] = None, workspace_id: Optional[str] = None) -> dict:
    """A notebook that begins with the setup cell (D14) when the workspace
    is named, then the question (§5.1)."""
    if kind not in KINDS:
        raise NotebookError("BAD_PARAMS", f"a notebook's kind is one of {', '.join(KINDS)}")
    if author not in AUTHORS:
        raise NotebookError("BAD_PARAMS", f"a notebook's author is one of {', '.join(AUTHORS)}")
    name = str(name or "").strip() or "Untitled investigation"
    m = {"id": study_id or f"st-{uuid.uuid4().hex[:12]}", "name": name, "kind": kind, "author": author,
         "question": question or None, "status": "open", "summary": None, "inbox_candidate": inbox_candidate or None,
         "engine": __version__, "created": _now(), "updated": None}
    if engine_type:
        m["engine_type"] = engine_type
    head = f"# {name}\n" + (f"\n**Question:** {question}\n" if question else "")
    if workspace_id:
        m["workspace_id"] = workspace_id
    cells = ([setup_cell(workspace_id)] if workspace_id else []) + [markdown_cell("c1", head, role="question")]
    return {"nbformat": 4, "nbformat_minor": 5,
            "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                         "language_info": {"name": "python"}, "slingology": m},
            "cells": cells}


def markdown_cell(cid: str, source: str, role: Optional[str] = None) -> dict:
    c = {"id": cid, "cell_type": "markdown", "metadata": {}, "source": source}
    if role:
        c["metadata"]["slingology"] = {"role": role}
    return c


def code_cell(cid: str, source: str, outputs: Optional[list] = None, ran: Optional[dict] = None) -> dict:
    c = {"id": cid, "cell_type": "code", "execution_count": None, "metadata": {}, "source": source,
         "outputs": list(outputs or [])}
    if ran:
        c["metadata"]["slingology"] = {"ran": ran}
    return c


# ── D14: the setup cell and outputs written outside EIS ────────────────────

def setup_source(workspace_id: str) -> str:
    """The setup cell: `eis` bound to this workspace, and the names the
    bench predefines for every cell (np, pd, plt, scipy, matplotlib), so a
    notebook written on the bench runs in any kernel. On the bench it
    changes nothing (already bound, already imported)."""
    return ("# Setup: binds `eis` to this workspace and imports what the EIS bench predefines. A no-op on the\n"
            "# bench; in JupyterLab (a kernel with slingology-eis[investigations]) it is the binding (Spec 16 D14).\n"
            "import numpy as np, pandas as pd, scipy, matplotlib\n"
            "import matplotlib.pyplot as plt\n"
            f"from slingology_eis import eis\neis.open({json.dumps(workspace_id)})")


def setup_cell(workspace_id: str) -> dict:
    c = code_cell(SETUP_ID, setup_source(workspace_id))
    c["metadata"]["slingology"] = {"role": "setup"}
    return c


def _is_setup(c: dict) -> bool:
    return c.get("cell_type") == "code" and (c.get("id") == SETUP_ID or slmeta_get(c).get("role") == "setup")


def slmeta_get(cell: dict) -> dict:
    return (cell.get("metadata") or {}).get("slingology") or {}


def ensure_setup(nb: dict, workspace_id: str) -> bool:
    """The setup cell first and `workspace_id` in the metadata (D14) —
    inserted into a notebook that predates them, re-pointed at this
    workspace in one that came from another. True when anything changed."""
    m = meta(nb)
    changed = m.get("workspace_id") != workspace_id
    m["workspace_id"] = workspace_id
    cells = nb["cells"]
    found = next((c for c in cells if _is_setup(c)), None)
    if found is None:
        if any(c.get("id") == SETUP_ID for c in cells):      # an unrelated cell took the id
            raise NotebookError("BAD_PARAMS", f"cell id {SETUP_ID!r} is reserved for the setup cell")
        cells.insert(0, setup_cell(workspace_id))
        return True
    src = text(found.get("source"))
    mm = _SETUP_OPEN.search(src)
    if mm and mm.group(2) != workspace_id:
        found["source"] = src[:mm.start(2)] + workspace_id + src[mm.end(2):]
        changed = True
    return changed


def _norm_output(o: dict) -> dict:
    """An output as EIS and Jupyter both say it: multi-line strings joined,
    execution counts and display metadata ignored (JupyterLab re-saves
    them differently)."""
    t = o.get("output_type")
    if t == "stream":
        return {"t": t, "name": o.get("name"), "text": text(o.get("text"))}
    if t == "error":
        return {"t": t, "ename": o.get("ename"), "evalue": o.get("evalue")}
    data = {k: (v if isinstance(v, (dict, int, float, bool)) or v is None else text(v))
            for k, v in (o.get("data") or {}).items()}
    return {"t": "display", "data": data}      # execute_result and display_data say the same thing


def _norm_outputs(outputs: Optional[list]) -> list:
    out: list = []
    for o in outputs or []:
        n = _norm_output(o)
        if n["t"] == "stream" and out and out[-1]["t"] == "stream" and out[-1]["name"] == n["name"]:
            out[-1] = {**out[-1], "text": out[-1]["text"] + n["text"]}   # Jupyter splits a stream in chunks
        else:
            out.append(n)
    return out


def digest(outputs: Optional[list]) -> str:
    import hashlib
    body = json.dumps(_norm_outputs(outputs), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def mark_external(nb: dict) -> list[str]:
    """Cells whose outputs a kernel outside EIS wrote (their digest no
    longer matches what EIS stored): marked ran elsewhere ("external").
    A cell EIS wrote before digests existed gets one now."""
    marked = []
    for c in nb["cells"]:
        if c.get("cell_type") != "code":
            continue
        sm = slmeta_get(c)
        ran = sm.get("ran")
        now = digest(c.get("outputs"))
        if ran is None:
            if c.get("outputs") and not sm.get("ran_elsewhere"):
                slmeta(c)["ran_elsewhere"] = "external"
                marked.append(c["id"])
            continue
        if "digest" not in ran:
            ran["digest"] = now
            continue
        if ran["digest"] != now:
            if sm.get("ran_elsewhere") != "external":
                slmeta(c)["ran_elsewhere"] = "external"
                marked.append(c["id"])
        elif sm.get("ran_elsewhere") == "external":
            slmeta(c).pop("ran_elsewhere")
    return marked


def accept_external(nb: dict, cell_ids: Optional[list] = None) -> list[str]:
    """`study_accept source: external` (D14): the outputs a kernel outside
    EIS wrote become the cells' outputs as they stand. The flights they
    read are not known; `ran.flights` keeps what EIS last recorded."""
    done = []
    for c in nb["cells"]:
        sm = slmeta_get(c)
        if c.get("cell_type") == "code" and sm.get("ran_elsewhere") == "external" \
                and (not cell_ids or c["id"] in cell_ids):
            old = sm.get("ran") or {}
            set_run(c, c.get("outputs") or [], {"engine": old.get("engine") or __version__,
                                                "flights": old.get("flights") or [], "at": _now(), "ms": 0,
                                                "status": "error" if any(o.get("output_type") == "error"
                                                                         for o in c.get("outputs") or []) else "ok",
                                                "source": "external"})
            done.append(c["id"])
    return done


def save(ws_dir: Path, nb: dict) -> dict:
    m = meta(nb)
    if not m.get("id") or not _ID.match(m["id"]):
        raise NotebookError("BAD_PARAMS", "a notebook's id is st-<12 hex>")
    m["updated"] = _now()
    m["created"] = m.get("created") or m["updated"]
    for c in nb["cells"]:
        if len(text(c.get("source"))) > MAX_SOURCE_CHARS:
            raise NotebookError("BAD_PARAMS", f"cell {c['id']}: source is longer than {MAX_SOURCE_CHARS} characters")
    p = path(ws_dir, m["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n")
    tmp.replace(p)
    return nb


def load(ws_dir: Path, study_id: str, *, presets: Optional[Callable] = None) -> dict:
    """The notebook; a Session D investigation study is converted first.
    D14: a notebook without the setup cell gets it (saved), and cells a
    kernel outside EIS ran and saved in place are marked ran elsewhere."""
    if not exists(ws_dir, study_id):
        legacy = Path(ws_dir) / "studies" / f"{study_id}.json"
        if _ID.match(str(study_id or "")) and legacy.is_file() and is_legacy(json.loads(legacy.read_text())):
            nb = convert(ws_dir, study_id, presets=presets)
        else:
            raise NotebookError("NOT_FOUND", f"no notebook {study_id}")
    else:
        try:
            nb = json.loads(path(ws_dir, study_id).read_text())
        except ValueError as e:
            raise NotebookError("BAD_PARAMS", f"{study_id}: the notebook isn't valid JSON ({e})")
        for c in nb.get("cells") or []:       # a Jupyter save may drop the empty metadata
            c.setdefault("metadata", {})
    before = json.dumps(nb, sort_keys=True)
    ensure_setup(nb, Path(ws_dir).name)
    mark_external(nb)
    if json.dumps(nb, sort_keys=True) != before:
        save(ws_dir, nb)
    return nb


def delete(ws_dir: Path, study_id: str) -> bool:
    import shutil
    d = folder(ws_dir, study_id)
    if not (d / NOTEBOOK).is_file():
        return False
    shutil.rmtree(d)
    return True


def list_ids(ws_dir: Path) -> list[str]:
    d = Path(ws_dir) / "studies"
    return sorted(p.parent.name for p in d.glob(f"st-*/{NOTEBOOK}")) if d.is_dir() else []


def convert_all(ws_dir: Path, *, presets: Optional[Callable] = None) -> list[str]:
    """Convert every study still stored the old way: Session D
    investigations and hand studies."""
    d = Path(ws_dir) / "studies"
    done = []
    for p in sorted(d.glob("st-*.json")) if d.is_dir() else []:
        try:
            doc = json.loads(p.read_text())
        except ValueError:
            continue
        if is_legacy(doc) and not exists(ws_dir, p.stem):
            convert(ws_dir, p.stem, presets=presets)
            done.append(p.stem)
    return done


# ── Cells ──────────────────────────────────────────────────────────────────

def next_id(nb: dict) -> str:
    n = max((int(c["id"][1:]) for c in nb["cells"] if re.match(r"^c\d+$", str(c.get("id")))), default=0)
    return f"c{n + 1}"


def find(nb: dict, cell_id: str) -> dict:
    for c in nb["cells"]:
        if c.get("id") == cell_id:
            return c
    raise NotebookError("NOT_FOUND", f"no cell {cell_id} in this notebook")


def set_run(cell: dict, outputs: list, ran: dict) -> None:
    cell["outputs"] = outputs
    m = slmeta(cell)
    m["ran"] = {**(ran or {}), "digest": digest(outputs)}
    for k in ("pending", "ran_elsewhere", "read_only"):
        m.pop(k, None)


def accept(nb: dict, cell_ids: Optional[list] = None) -> list[str]:
    done = []
    for c in nb["cells"]:
        m = (c.get("metadata") or {}).get("slingology") or {}
        if c["cell_type"] == "code" and m.get("pending") and (not cell_ids or c["id"] in cell_ids):
            p = m["pending"]
            set_run(c, p["outputs"], p.get("ran") or m.get("ran"))
            done.append(c["id"])
    return done


def discard(nb: dict, cell_ids: Optional[list] = None) -> list[str]:
    done = []
    for c in nb["cells"]:
        m = (c.get("metadata") or {}).get("slingology") or {}
        if c["cell_type"] == "code" and m.get("pending") and (not cell_ids or c["id"] in cell_ids):
            m.pop("pending")
            done.append(c["id"])
    return done


def has_figure(cell: dict) -> bool:
    return any(k in (o.get("data") or {}) for o in cell.get("outputs") or [] for k in FIGURE_MIMES)


def floor_lacking(nb: dict) -> list[str]:
    """§5.1 floor rule: every cell showing a figure or a log view has a
    markdown cell immediately before or after it. The cells that don't."""
    cells = nb["cells"]
    out = []
    for i, c in enumerate(cells):
        if c["cell_type"] == "code" and has_figure(c):
            near = [cells[j] for j in (i - 1, i + 1) if 0 <= j < len(cells)]
            if not any(n["cell_type"] == "markdown" and text(n.get("source")).strip() for n in near):
                out.append(c["id"])
    return out


def flights_of(nb: dict) -> list[str]:
    """The union of the flights the code cells read (F7: one count)."""
    out: list[str] = []
    for c in nb["cells"]:
        if c["cell_type"] == "code":
            out += list((((c.get("metadata") or {}).get("slingology") or {}).get("ran") or {}).get("flights") or [])
    return list(dict.fromkeys(out))


def summary(nb: dict) -> dict:
    """The list_studies row of a notebook (the hand-study row's shape)."""
    m = meta(nb)
    return {"study_id": m["id"], "name": m.get("name"), "updated": m.get("updated"), "created": m.get("created"),
            "finding": (m.get("summary") or "").split("\n", 1)[0] or None, "tests": 0, "read_only": False,
            "flights": len(flights_of(nb)), "kind": m.get("kind"), "author": m.get("author"),
            # F17: an open notebook that was finished before reads *reopened*.
            "question": m.get("question"),
            "status": "reopened" if m.get("status") == "open" and m.get("reopened") else m.get("status"),
            "summary": m.get("summary"), "summaries": m.get("summaries") or [],
            "cells": len(nb["cells"]), "format": "ipynb",
            "pending": sum(1 for c in nb["cells"] if ((c.get("metadata") or {}).get("slingology") or {}).get("pending"))}


def read_view(nb: dict) -> dict:
    """load_study's answer for a notebook: the list row and the notebook."""
    return {**summary(nb), "inbox_candidate": meta(nb).get("inbox_candidate"), "engine": meta(nb).get("engine"),
            "notebook": nb}


_IMG_MIME = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\((files/[^)\s]+)\)")


def markdown_images(ws_dir, nb: dict, limit: int = 2_000_000) -> dict:
    """The `files/…` images the markdown cells show, as data: URLs — the
    page inlines them as the HTML export does (§5.3). Larger files are left
    out (the page shows the reference)."""
    import base64
    folder = files_dir(ws_dir, meta(nb)["id"])
    out = {}
    for c in nb.get("cells") or []:
        if c.get("cell_type") != "markdown":
            continue
        for ref in _MD_IMAGE.findall(text(c.get("source"))):
            ext = "." + ref.rsplit(".", 1)[-1].lower() if "." in ref else ""
            p = folder / ref.split("/", 1)[-1]
            if ext in _IMG_MIME and ".." not in ref and p.is_file() and p.stat().st_size <= limit:
                out[ref] = f"data:{_IMG_MIME[ext]};base64,{base64.b64encode(p.read_bytes()).decode()}"
    return out


# ── Session D studies (acceptance 15) ──────────────────────────────────────

def is_legacy(doc: dict) -> bool:
    """A study document stored the old way: a Session D investigation or a
    hand study (a Spec 06 document with tests)."""
    return isinstance(doc, dict) and bool(doc.get("study_id")) and (is_session_d(doc) or isinstance(doc.get("tests"), list))


def is_session_d(doc: dict) -> bool:
    """A Session D investigation: the Spec 06 document with notebook cells,
    or a kind/author that isn't a hand study's."""
    return isinstance(doc, dict) and (doc.get("cells") is not None or (doc.get("kind") or "hand") != "hand"
                                      or (doc.get("author") or "user") != "user")


def _lit(v) -> str:
    return pprint.pformat(v, width=100, sort_dicts=False)


def question_code(doc: dict, t: dict, presets: Optional[Callable] = None) -> str:
    """The eis call that reproduces a Session D question cell: the same
    test, channels, parameters and slice set (the question's own, else the
    study's), so its printed result is the stored one."""
    spec = t.get("slices") or {"selection": doc.get("selection"), "slice_rules": doc.get("slice_rules"),
                               "hand_slices": doc.get("hand_slices")}
    sel = {k: v for k, v in (spec.get("selection") or {"mode": "all"}).items() if v is not None}
    rules = list(spec.get("slice_rules") or [])
    hand = list(spec.get("hand_slices") or [])
    from ..research.rules import RuleError, normalise_rule

    def same(a: dict, b: dict) -> bool:
        try:
            return normalise_rule(a) == normalise_rule(b)
        except RuleError:
            return False
    named = []
    for r in rules:
        rid = r.get("rule_id") if isinstance(r, dict) else None
        p = presets(rid) if (presets and rid) else None
        named.append(rid if p is not None and same(p, r) else r)
    if sel == {"mode": "all"} and not hand:
        arg = _lit(named[0]) if len(named) == 1 else _lit(named)
    else:
        arg = _lit({"selection": sel, "slice_rules": named, "hand_slices": hand})
    tid, chans, params = t["test_id"], list(t.get("channels") or []), dict(t.get("params") or {})
    kw = []
    if tid == "cycling":
        call = f"eis.cycling({arg}, {(chans[:1] or ['rpm'])[0]!r}"
    elif tid == "coupling":
        call = f"eis.coupling({arg}, {_lit(chans or ['rpm', 'map_inhg'])}"
    elif tid == "groups":
        desc = params.pop("descriptor", None) or f"{(chans or ['rpm'])[0]}.swing"
        split = params.pop("split", None) or sel.get("split")
        call = f"eis.groups({arg}, {desc!r}, by={_lit(split)}"
    else:
        call = f"eis.unusual({arg}, {_lit(chans) if chans else 'None'}"
    for k, v in params.items():
        kw.append(f"{k}={_lit(v)}")
    for k in ("windows", "references"):
        if doc.get(k):
            kw.append(f"{k}={_lit(doc[k])}")
    return "r = " + call + "".join(", " + k for k in kw) + ")\nprint(r)\n"


def _old_outputs(outputs: list, read_file: Callable) -> list:
    out = []
    for o in outputs or []:
        k = o.get("kind")
        if k == "text" and o.get("stream"):
            out.append({"output_type": "stream", "name": o["stream"], "text": o["text"]})
        elif k == "text":
            out.append({"output_type": "execute_result", "execution_count": None, "metadata": {},
                        "data": {"text/plain": o["text"]}})
        elif k == "table":
            from .notebook import _table_html, _table_text
            out.append({"output_type": "display_data",
                        "metadata": {"slingology": {"table": {"n_rows": o.get("n_rows"), "n_cols": o.get("n_cols"),
                                                              "truncated": bool(o.get("truncated"))}}},
                        "data": {"text/html": _table_html(o), "text/plain": _table_text(o)}})
        elif k == "figure":
            svg = read_file(o["ref"])
            data = {"text/plain": f"<Figure: {o['title']}>" if o.get("title") else "<Figure>"}
            if svg is not None:
                data["image/svg+xml"] = svg.decode("utf-8", errors="replace")
            out.append({"output_type": "display_data", "metadata": {}, "data": data})
        elif k == "error":
            tb = o.get("traceback") or ""
            out.append({"output_type": "error", "ename": o.get("ename", "Error"), "evalue": o.get("evalue", ""),
                        "traceback": tb.splitlines() if isinstance(tb, str) else list(tb)})
    return out


def convert(ws_dir: Path, study_id: str, *, presets: Optional[Callable] = None) -> dict:
    """A Session D study document → notebook.ipynb. Markdown stays
    markdown; code keeps its source, outputs (figures inlined from files/)
    and `ran`; a question cell becomes a markdown heading and the eis code
    that reproduces it, its stored output the stored result's §8 text; a
    figure or table cell becomes markdown showing the file. The old
    document is kept as studies/<id>/.session-d.json."""
    from ..research.render import render_text
    legacy = Path(ws_dir) / "studies" / f"{study_id}.json"
    doc = json.loads(legacy.read_text())
    fdir = files_dir(ws_dir, study_id)

    def read_file(ref: str):
        p = fdir / ref.split("/", 1)[-1]
        return p.read_bytes() if p.is_file() else None
    prov = doc.get("provenance") or {}
    hand = not is_session_d(doc)
    tests = doc.get("tests") or []
    kind = doc.get("kind") if doc.get("kind") in KINDS else "investigation"
    nb = new(name=doc.get("name"), question=doc.get("question"), kind=kind,
             author=doc.get("author") if doc.get("author") in AUTHORS else "user",
             inbox_candidate=doc.get("inbox_candidate"), engine_type=doc.get("engine_type"), study_id=study_id)
    m = meta(nb)
    if hand:
        # A hand study's findings are its questions' findings (the list row showed the first).
        findings = [t["result"]["finding"] for t in tests if (t.get("result") or {}).get("finding")]
        status = "finished" if tests and len(findings) == len(tests) else "open"
        summary = "\n".join(findings) or None
    else:
        status, summary = doc.get("status") or "open", doc.get("summary")
    m.update({"status": status, "summary": summary,
              "engine": prov.get("engine") or __version__, "created": doc.get("created") or m["created"],
              "converted_from": "hand-study" if hand else "session-d"})
    if doc.get("finished"):
        m["finished"] = doc["finished"]
    cells = [nb["cells"][0]]
    n = 1

    def cid() -> str:
        nonlocal n
        n += 1
        return f"c{n}"
    if hand:
        cells.append(markdown_cell(cid(), _hand_intro(doc), role="converted"))
        if (doc.get("notes") or "").strip():
            cells.append(markdown_cell(cid(), "### Notes\n\n" + doc["notes"].strip() + "\n"))
    for c in doc.get("cells") or [{"kind": "question", "test_index": i} for i in range(len(tests))]:
        k = c.get("kind")
        if k == "markdown":
            cells.append(markdown_cell(cid(), c.get("source") or "", role=c.get("role")))
        elif k == "code":
            cell = code_cell(cid(), c.get("source") or "", _old_outputs(c.get("outputs"), read_file), c.get("ran"))
            if c.get("pending_outputs") is not None:
                slmeta(cell)["pending"] = {"outputs": _old_outputs(c["pending_outputs"], read_file),
                                           "ran": c.get("pending_ran")}
            for f in ("ran_elsewhere", "read_only"):
                if c.get(f):
                    slmeta(cell)[f] = True
            cells.append(cell)
        elif k == "question":
            t = tests[c["test_index"]]
            r = t.get("result")
            title = (r or {}).get("question") or f"Question ({t['test_id']})"
            cells.append(markdown_cell(cid(), f"### {title}\n", role="question"))
            outputs = [{"output_type": "stream", "name": "stdout", "text": render_text(r) + "\n"}] if r else []
            if not r and t.get("error"):
                outputs = [{"output_type": "error", "ename": "RuleError", "evalue": t["error"], "traceback": [t["error"]]}]
            flights = list(dict.fromkeys(s.get("flight") for s in ((r or {}).get("block") or {}).get("per_slice") or []
                                         if s.get("flight")))
            ran = {"engine": ((r or {}).get("block") or {}).get("engine_version") or prov.get("engine") or __version__,
                   "flights": flights, "at": doc.get("updated") or m["created"], "ms": 0,
                   "status": "ok" if r else "error", "converted": "question"}
            qcell = code_cell(cid(), question_code(doc, t, presets), outputs, ran)
            if doc.get("read_only"):
                slmeta(qcell)["read_only"] = True      # an imported hand study held the sender's results
            cells.append(qcell)
        elif k in ("figure", "table"):
            ref = c.get("ref") or ""
            label = c.get("title") or ref
            src = f"![{label}]({ref})\n" if k == "figure" else f"*Table:* [{label}]({ref})\n"
            cells.append(markdown_cell(cid(), src))
    nb["cells"] = cells
    save(ws_dir, nb)
    folder(ws_dir, study_id).mkdir(parents=True, exist_ok=True)
    legacy.replace(folder(ws_dir, study_id) / (BACKUP_HAND if hand else BACKUP))
    return nb


def _hand_intro(doc: dict) -> str:
    """The first markdown of a converted hand study: what it was and what it
    looked at (its slice set, and the Signal flight and window if it had
    one) — the record the study page used to show above its questions."""
    from ..research.rules import RuleError, describe_rule, normalise_rule
    lines = ["*A study built by hand on the Research page, converted to a notebook (Spec 16 D15). Each question below "
             "is its stored result and the `eis` call that reproduces it.*", ""]
    rules = []
    for r in doc.get("slice_rules") or []:
        if isinstance(r, str):
            rules.append(r)
            continue
        try:
            rules.append(describe_rule(normalise_rule(r)))
        except RuleError:
            rules.append(str(r.get("name") or r.get("rule_id") or "a rule"))
    sel = doc.get("selection") or {}
    flights = "every flight" if sel.get("mode", "all") == "all" else f"{len(sel.get('flights') or [])} chosen flights"
    if rules:
        lines.append(f"- **Slices:** {'; '.join(rules)} — over {flights}.")
    if doc.get("hand_slices"):
        lines.append(f"- **Hand slices:** {len(doc['hand_slices'])}.")
    if sel.get("split"):
        lines.append(f"- **Split:** {json.dumps(sel['split'])}.")
    sig = doc.get("signal") or {}
    if sig.get("flight_id"):
        w = sig.get("window") or {}
        span = f", window {w.get('start_s')}–{w.get('end_s')} s" if w else ""
        lines.append(f"- **Signal:** flight `{sig['flight_id']}`{span} ({', '.join(sig.get('channels') or [])}).")
    if doc.get("read_only"):
        lines.append("- **Imported:** none of its flights are in this workspace; the results are the sender's.")
    return "\n".join(lines).rstrip() + "\n"


# ── Leaving and arriving (§5.1 export, S5 fingerprints) ────────────────────

def _map_flights(nb: dict, f: Callable[[str], str]) -> dict:
    nb = copy.deepcopy(nb)
    for c in nb["cells"]:
        m = (c.get("metadata") or {}).get("slingology") or {}
        for ran in (m.get("ran"), (m.get("pending") or {}).get("ran")):
            if isinstance(ran, dict) and ran.get("flights"):
                ran["flights"] = [f(x) for x in ran["flights"]]
        for outs in (c.get("outputs") or [], (m.get("pending") or {}).get("outputs") or []):
            for o in outs:
                lv = (o.get("data") or {}).get(LOGVIEW_MIME)
                if isinstance(lv, dict) and lv.get("flight"):
                    lv["flight"] = f(lv["flight"])
    return nb


def for_export(nb: dict, ws_dir: Path) -> dict:
    from .notebook import fingerprints
    out, _ = fingerprints(ws_dir)
    nb = _map_flights(nb, lambda fid: out.get(fid, fid))
    for c in nb["cells"]:
        (c.get("metadata") or {}).get("slingology", {}).pop("pending", None)
    return nb


def export_zip(ws_dir: Path, nb: dict) -> bytes:
    """The notebook folder as a zip: <name>/notebook.ipynb and files/,
    deterministic (fixed dates, sorted)."""
    sid = meta(nb)["id"]
    sent = for_export(nb, ws_dir)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def put(name: str, data: bytes) -> None:
            zi = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, data)
        put(NOTEBOOK, (json.dumps(sent, indent=1, ensure_ascii=False) + "\n").encode())
        fdir = files_dir(ws_dir, sid)
        for p in sorted(fdir.rglob("*")) if fdir.is_dir() else []:
            if p.is_file():
                put("files/" + p.relative_to(fdir).as_posix(), p.read_bytes())
    return buf.getvalue()


def _safe_member(name: str) -> Optional[str]:
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or ".." in parts or name.startswith("/"):
        return None
    return "/".join(parts)


def parse_bytes(data: bytes) -> tuple[dict, dict]:
    """(notebook, {files/<rel>: bytes}) from a zip of a notebook folder or a bare .ipynb."""
    files: dict[str, bytes] = {}
    if data[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise NotebookError("BAD_PARAMS", "not a notebook zip")
        names = [n for n in z.namelist() if _safe_member(n)]
        nbs = sorted((n for n in names if n.endswith(".ipynb")), key=lambda n: (n.count("/"), n))
        if not nbs:
            raise NotebookError("BAD_PARAMS", "the zip holds no .ipynb")
        top = nbs[0].rsplit("/", 1)[0] + "/" if "/" in nbs[0] else ""
        raw = z.read(nbs[0])
        for n in names:
            rel = _safe_member(n)
            if rel.startswith(top + "files/") and not n.endswith("/"):
                files["files/" + rel[len(top + "files/"):]] = z.read(n)
    else:
        raw = data
    try:
        nb = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise NotebookError("BAD_PARAMS", "not a Jupyter notebook (.ipynb JSON)")
    if not isinstance(nb, dict) or nb.get("nbformat") != 4 or not isinstance(nb.get("cells"), list):
        raise NotebookError("BAD_PARAMS", "only nbformat 4 notebooks can be imported")
    return nb, files


def import_bytes(ws_dir: Path, data: bytes) -> dict:
    """A notebook placed under studies/ as a new investigation: fingerprints
    mapped to this workspace's flights (S5); each code cell's outputs are
    the sender's (*ran elsewhere*); a cell none of whose flights are here
    is read-only."""
    from .. import workspace as ws
    from .notebook import fingerprints
    nb, files = parse_bytes(data)
    _, back = fingerprints(ws_dir)
    nb = _map_flights(nb, lambda x: back.get(x, x))
    present = set(ws.list_flight_ids(ws_dir))
    m = meta(nb)
    sid = f"st-{uuid.uuid4().hex[:12]}"
    m.update({"id": sid, "imported": _now()})
    m.setdefault("name", "Imported notebook")
    m.setdefault("kind", "investigation")
    m.setdefault("author", "user")
    m.setdefault("status", "open")
    m.setdefault("engine", "")
    ids = set()
    for c in nb["cells"]:
        c.setdefault("metadata", {})
        if not c.get("id") or c["id"] in ids:
            c["id"] = f"c{len(ids) + 1}"
        ids.add(c["id"])
        if c.get("cell_type") != "code":
            continue
        s = slmeta(c)
        s.pop("pending", None)
        if c.get("outputs"):
            s["ran_elsewhere"] = True
            s.setdefault("ran", {})["digest"] = digest(c.get("outputs"))
        touched = (s.get("ran") or {}).get("flights") or []
        if touched and not any(f in present for f in touched):
            s["read_only"] = True
        else:
            s.pop("read_only", None)
    ensure_setup(nb, Path(ws_dir).name)
    save(ws_dir, nb)
    fdir = files_dir(ws_dir, sid)
    for rel, body in files.items():
        p = fdir / rel.split("/", 1)[1]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
    return nb
