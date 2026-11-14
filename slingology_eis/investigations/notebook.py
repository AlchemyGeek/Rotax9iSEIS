"""
The notebook study (Spec 16 §5, D4): the Spec 06 study document with a
`cells` list.

    { "id": "c1", "kind": "markdown", "source": "…" }
    { "id": "c2", "kind": "code", "source": "…", "outputs": [ … ],
      "ran": { "engine", "flights": [flight_id…], "at", "ms", "status", "caps" },
      "pending_outputs": null | [ … ], "pending_ran": null | { … } }
    { "id": "c3", "kind": "question", "test_index": 0 }
    { "id": "c4", "kind": "figure" | "table", "ref": "files/…", "title": "…" }

A **question cell names a question of the study's `tests` list** (Spec 06
§10.1) rather than repeating it: run_study, the Journal's study finding
and the question cards then work on investigator and hand studies alike,
and a hand study — no `cells` — reads as a notebook whose cells are its
questions (`cells_of`). Its document is not rewritten until a cell is
appended.

Code-cell outputs: `{"kind": "text", "stream"?: "stdout"|"stderr", "text"}`,
`{"kind": "table", "columns", "rows", "n_rows", "n_cols", "truncated", "title"?}`,
`{"kind": "figure", "ref": "files/fig-<hash>.svg", "title"}`,
`{"kind": "error", "ename", "evalue", "traceback"}`. A figure's file name
is its content hash, so a re-run that draws the same figure names the same
file.

Flights are named by `flight_id` here as everywhere in Research (Spec 06
§3.2), so `ran.flights` holds flight ids — the hash of each fingerprint.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
from pathlib import Path
from typing import Optional

from ..research.rules import RuleError

CELL_KINDS = ("markdown", "code", "question", "figure", "table")
STUDY_KINDS = ("hand", "investigation", "question-for-type")
AUTHORS = ("user", "claude")
MAX_SOURCE_CHARS = 100_000
_REF = re.compile(r"^files/[A-Za-z0-9][A-Za-z0-9._ -]{0,180}$")
_GENERATED = re.compile(r"^fig-[0-9a-f]{16}\.svg$")


def files_dir(ws_dir: Path, study_id: str) -> Path:
    return ws_dir / "studies" / study_id / "files"


def _cell(c: dict, n_tests: int) -> dict:
    if not isinstance(c, dict) or c.get("kind") not in CELL_KINDS:
        raise RuleError(f"a cell has a kind, one of {', '.join(CELL_KINDS)}; got {c!r}")
    cid = str(c.get("id") or "")
    if not re.match(r"^c[0-9]{1,6}$", cid):
        raise RuleError(f"a cell id is c<number>; got {cid!r}")
    kind = c["kind"]
    out = {"id": cid, "kind": kind}
    if kind in ("markdown", "code"):
        src = c.get("source")
        if not isinstance(src, str):
            raise RuleError(f"cell {cid}: source is text")
        if len(src) > MAX_SOURCE_CHARS:
            raise RuleError(f"cell {cid}: source is longer than {MAX_SOURCE_CHARS} characters")
        out["source"] = src
    if kind == "code":
        out["outputs"] = list(c.get("outputs") or [])
        out["ran"] = dict(c["ran"]) if c.get("ran") else None
        out["pending_outputs"] = list(c["pending_outputs"]) if c.get("pending_outputs") is not None else None
        if c.get("pending_ran"):
            out["pending_ran"] = dict(c["pending_ran"])
        for k in ("ran_elsewhere", "read_only"):
            if c.get(k):
                out[k] = c[k]
    elif kind == "question":
        i = c.get("test_index")
        if not isinstance(i, int) or not 0 <= i < n_tests:
            raise RuleError(f"cell {cid}: test_index names one of the study's {n_tests} questions")
        out["test_index"] = i
        if c.get("read_only"):
            out["read_only"] = True
    elif kind in ("figure", "table"):
        ref = str(c.get("ref") or "")
        if not _REF.match(ref) or ".." in ref:
            raise RuleError(f"cell {cid}: ref is files/<name>, a file the study's code wrote; got {ref!r}")
        out["ref"] = ref
        if c.get("title"):
            out["title"] = str(c["title"])
    if kind == "markdown" and c.get("role"):
        out["role"] = str(c["role"])
    return out


def normalise_cells(cells, n_tests: int) -> Optional[list]:
    if cells is None:
        return None
    if not isinstance(cells, list):
        raise RuleError("cells is a list")
    out = [_cell(c, n_tests) for c in cells]
    ids = [c["id"] for c in out]
    if len(set(ids)) != len(ids):
        raise RuleError("cell ids are unique within a study")
    return out


def normalise_meta(doc: dict) -> dict:
    """The notebook fields of a study (§5): kind, author, question, and
    the investigation's status."""
    out = {}
    kind = doc.get("kind") or "hand"
    if kind not in STUDY_KINDS:
        raise RuleError(f"a study's kind is one of {', '.join(STUDY_KINDS)}")
    out["kind"] = kind
    author = doc.get("author") or "user"
    if author not in AUTHORS:
        raise RuleError(f"a study's author is one of {', '.join(AUTHORS)}")
    out["author"] = author
    if doc.get("question"):
        out["question"] = str(doc["question"])
    for k in ("status", "summary", "finished", "inbox_candidate", "engine_type"):
        if doc.get(k) is not None:
            out[k] = doc[k]
    return out


def cells_of(doc: dict) -> list[dict]:
    """The study as a notebook: its cells, or — a hand study, which has
    none — one question cell per question."""
    if doc.get("cells") is not None:
        return doc["cells"]
    return [{"id": f"c{i + 1}", "kind": "question", "test_index": i} for i in range(len(doc.get("tests") or []))]


def materialise(doc: dict) -> dict:
    if doc.get("cells") is None:
        doc["cells"] = cells_of(doc)
    return doc


def next_id(doc: dict) -> str:
    n = max((int(c["id"][1:]) for c in cells_of(doc)), default=0)
    return f"c{n + 1}"


def find(doc: dict, cell_id: str) -> dict:
    for c in cells_of(doc):
        if c["id"] == cell_id:
            return c
    raise RuleError(f"no cell {cell_id} in this study")


# ── Re-run (§5): new outputs beside the stored ones until accepted ─────────

def accept(doc: dict, cell_ids: Optional[list] = None) -> list[str]:
    done = []
    for c in cells_of(doc):
        if c["kind"] == "code" and c.get("pending_outputs") is not None and (not cell_ids or c["id"] in cell_ids):
            c["outputs"], c["ran"] = c["pending_outputs"], c.get("pending_ran") or c.get("ran")
            c["pending_outputs"] = None
            c.pop("pending_ran", None)
            c.pop("ran_elsewhere", None)
            c.pop("read_only", None)
            done.append(c["id"])
    return done


def discard(doc: dict, cell_ids: Optional[list] = None) -> list[str]:
    done = []
    for c in cells_of(doc):
        if c["kind"] == "code" and c.get("pending_outputs") is not None and (not cell_ids or c["id"] in cell_ids):
            c["pending_outputs"] = None
            c.pop("pending_ran", None)
            done.append(c["id"])
    return done


def referenced_files(doc: dict) -> set[str]:
    refs = set()
    for c in cells_of(doc):
        if c["kind"] in ("figure", "table"):
            refs.add(c["ref"])
        for o in (c.get("outputs") or []) + (c.get("pending_outputs") or []):
            if o.get("ref"):
                refs.add(o["ref"])
    return refs


def collect_figures(ws_dir: Path, doc: dict) -> int:
    """Drop the bench's own figure files no cell refers to any more (a
    discarded or replaced re-run). Files a cell wrote itself are kept."""
    d = files_dir(ws_dir, doc["study_id"])
    if not d.is_dir():
        return 0
    keep = {r.split("/", 1)[1] for r in referenced_files(doc)}
    n = 0
    for p in d.iterdir():
        if p.is_file() and _GENERATED.match(p.name) and p.name not in keep:
            p.unlink()
            n += 1
    return n


def remove_files(ws_dir: Path, study_id: str) -> None:
    d = ws_dir / "studies" / study_id
    if d.is_dir():
        shutil.rmtree(d)


def flights_of(doc: dict) -> list[str]:
    out = []
    for c in cells_of(doc):
        if c["kind"] == "code":
            out += list((c.get("ran") or {}).get("flights") or [])
    return list(dict.fromkeys(out))


def mark_imported(doc: dict, present: set) -> None:
    """A notebook that arrives from elsewhere: every code cell's outputs
    are the sender's (*ran elsewhere*, D8); a cell none of whose flights
    are here is read-only — re-running it here has nothing to read."""
    tests = doc.get("tests") or []
    for c in cells_of(doc):
        if c["kind"] == "question":
            # A question's flights are those its stored result read.
            t = tests[c["test_index"]] if 0 <= c.get("test_index", -1) < len(tests) else {}
            read = [r.get("flight") for r in (((t.get("result") or {}).get("block") or {}).get("per_slice") or [])]
            read = [f for f in read if f]
            if read and not any(f in present for f in read):
                c["read_only"] = True
            else:
                c.pop("read_only", None)
            continue
        if c["kind"] != "code":
            continue
        c["pending_outputs"] = None
        c.pop("pending_ran", None)
        if c.get("outputs"):
            c["ran_elsewhere"] = True
        touched = (c.get("ran") or {}).get("flights") or []
        if touched and not any(f in present for f in touched):
            c["read_only"] = True
        else:
            c.pop("read_only", None)


# ── .ipynb (§5): one-way ───────────────────────────────────────────────────

def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _table_html(o: dict) -> str:
    esc = lambda v: "" if v is None else str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    head = "".join(f"<th>{esc(c)}</th>" for c in o["columns"])
    body = "".join("<tr>" + "".join(f"<td>{esc(v)}</td>" for v in r) + "</tr>" for r in o["rows"])
    more = f"<p>{o['n_rows'] - len(o['rows'])} more rows not stored</p>" if o.get("truncated") else ""
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>{more}"


def _table_text(o: dict) -> str:
    rows = [o["columns"]] + [["" if v is None else str(v) for v in r] for r in o["rows"]]
    return "\n".join("\t".join(map(str, r)) for r in rows)


def _ipynb_outputs(outputs: list, read_file) -> list[dict]:
    out = []
    for o in outputs or []:
        k = o.get("kind")
        if k == "text" and o.get("stream"):
            out.append({"output_type": "stream", "name": o["stream"], "text": _lines(o["text"])})
        elif k == "text":
            out.append({"output_type": "execute_result", "execution_count": None, "metadata": {},
                        "data": {"text/plain": _lines(o["text"])}})
        elif k == "table":
            out.append({"output_type": "display_data", "metadata": {},
                        "data": {"text/html": _lines(_table_html(o)), "text/plain": _lines(_table_text(o))}})
        elif k == "figure":
            svg = read_file(o["ref"])
            data = {"text/plain": [o.get("title") or "figure"]}
            if svg is not None:
                data["image/svg+xml"] = _lines(svg.decode("utf-8", errors="replace"))
            out.append({"output_type": "display_data", "metadata": {}, "data": data})
        elif k == "error":
            out.append({"output_type": "error", "ename": o.get("ename", "Error"), "evalue": o.get("evalue", ""),
                        "traceback": (o.get("traceback") or "").splitlines()})
    return out


def _question_markdown(t: dict) -> str:
    r = t.get("result")
    if not r:
        return f"**Question ({t['test_id']})** — not run" + (f": {t['error']}" if t.get("error") else "") + "\n"
    lines = [f"**{r.get('question') or t['test_id']}**", "", r["finding"], ""]
    for m in r.get("magnitude") or []:
        txt = (m.get("text") or f"{m.get('label')}: {m.get('value')} {m.get('unit') or ''}".strip()) \
            if isinstance(m, dict) else str(m)
        if txt:
            lines.append(f"- {txt}")
    if r.get("caveats"):
        lines += ["", "*Caveats:*"] + [f"- {c}" for c in r["caveats"]]
    return "\n".join(lines) + "\n"


def to_ipynb(doc: dict, read_file) -> dict:
    """The notebook as Jupyter nbformat 4: markdown and code cells with
    their stored outputs; a question cell becomes markdown carrying its
    §8 result; figure and table cells become markdown naming their file
    (the file travels in the .eisstudy, not in the .ipynb)."""
    head = [f"# {doc.get('name') or 'Study'}", ""]
    if doc.get("question"):
        head.append(f"**Question:** {doc['question']}")
    prov = doc.get("provenance") or {}
    head.append(f"*Author: {doc.get('author', 'user')} · engine {prov.get('engine', '')} · "
                f"exported from SlingologyEIS; code cells call the EIS bench helpers (load_flight, load_slices, …), "
                f"which exist only inside EIS.*")
    cells = [{"cell_type": "markdown", "metadata": {}, "source": _lines("\n".join(head) + "\n")}]
    tests = doc.get("tests") or []
    for c in cells_of(doc):
        meta = {"eis": {"id": c["id"], "kind": c["kind"]}}
        if c["kind"] == "markdown":
            cells.append({"cell_type": "markdown", "metadata": meta, "source": _lines(c["source"])})
        elif c["kind"] == "code":
            if c.get("ran"):
                meta["eis"]["ran"] = c["ran"]
            cells.append({"cell_type": "code", "execution_count": None, "metadata": meta,
                          "source": _lines(c["source"]), "outputs": _ipynb_outputs(c.get("outputs"), read_file)})
        elif c["kind"] == "question":
            cells.append({"cell_type": "markdown", "metadata": meta,
                          "source": _lines(_question_markdown(tests[c["test_index"]]))})
        else:
            cells.append({"cell_type": "markdown", "metadata": meta,
                          "source": _lines(f"*{c['kind'].capitalize()}: {c.get('title') or c['ref']}* (`{c['ref']}`)\n")})
    if doc.get("summary"):
        cells.append({"cell_type": "markdown", "metadata": {"eis": {"kind": "summary"}},
                      "source": _lines(f"## Summary\n\n{doc['summary']}\n")})
    return {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
            "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                         "language_info": {"name": "python"},
                         "eis": {"study_id": doc.get("study_id"), "kind": doc.get("kind"), "author": doc.get("author")}}}


def ipynb_bytes(doc: dict, read_file) -> bytes:
    nb = to_ipynb(copy.deepcopy(doc), read_file)
    # nbformat 4.5 wants cell ids; use the study's own.
    for i, c in enumerate(nb["cells"]):
        c["id"] = (c["metadata"].get("eis") or {}).get("id") or f"h{i}"
    return json.dumps(nb, indent=1, ensure_ascii=False).encode()
