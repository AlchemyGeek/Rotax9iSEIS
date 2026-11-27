"""
Spec 16 §4.3: the host operations Investigations adds, on the Spec 01 §7
envelope. host.py registers each one; this module holds them so the
host's own file doesn't grow by a feature's worth of code.

    guide                                      (D13: method, tool map, aircraft, documents, workspace)
    study_create                               (D12: a notebook, studies/<id>/notebook.ipynb)
    code_run                                   (D3 — server host only; refused without a notebook)
    study_cells_append / _rerun / _accept / _discard, study_finish   (§5.1)
    aircraft_get / aircraft_set / list_aircraft (§4.4 — the registry's record, D10)
    documents_list / document_read             (D11: the aircraft's documents_dirs, read in place)
    inbox_scan / inbox_list / inbox_resolve    (D5)

`export_study` / `import_study` (Spec 06 §11) handle notebooks (zip of the
folder, HTML render) in host.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import __version__
from .. import host as H
from .. import workspace as ws
from ..research.rules import RuleError
from .. import aircraft as AC
from . import bench as B
from . import documents as DOC
from . import inbox as IB
from . import pins as PN
from . import ipynb as NBX


def _err(e) -> H.RpcError:
    return H.RpcError(getattr(e, "code", "BAD_PARAMS"), getattr(e, "message", str(e)))


def _mpl_dir(ctx: dict) -> Path:
    """matplotlib's config and font cache: about this machine's fonts, not
    the user's data, so one per user (the first figure ever builds it,
    ~10 s), not one per data root."""
    import os
    import sys
    if os.environ.get("XDG_CACHE_HOME"):
        base = Path(os.environ["XDG_CACHE_HOME"])
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"])
    else:
        base = Path.home() / ".cache"
    return base / "SlingologyEIS" / "matplotlib"


# ── The notebook (D12, §5.1) ───────────────────────────────────────────────

def presets_of(ctx: dict):
    """rule_id → the engine's preset rule (None if no such preset): how a
    converted question cell names a preset by id."""
    from ..research import presets as rp
    engine_cfg, engine_name = H._current_engine(ctx)
    return lambda rid: rp.preset(rid, engine_name, engine_cfg)


def notebook(ctx: dict, study_id) -> dict:
    """The investigation notebook `study_id` (a Session D or hand study is
    converted on this first load); an unknown id is refused."""
    if not study_id:
        raise H.RpcError("BAD_PARAMS", "every executed cell belongs to a notebook: start one with study_create "
                                       "and pass its study_id")
    try:
        return NBX.load(ctx["workspace_dir"], study_id, presets=presets_of(ctx))
    except NBX.NotebookError as e:
        raise _err(e)


def _save_nb(ctx: dict, nb: dict) -> dict:
    try:
        return NBX.save(ctx["workspace_dir"], nb)
    except NBX.NotebookError as e:
        raise _err(e)


def _reopen(nb: dict) -> None:
    """Spec 16 F17: the notebook is the record. New analysis in a finished
    notebook — a cell appended, or a code cell rewritten — opens it again;
    it needs a fresh study_finish, which keeps the earlier summary as dated
    history. Re-running the cells as they are does not reopen it."""
    m = NBX.meta(nb)
    if m.get("status") == "finished":
        m["status"] = "open"
        m["reopened"] = H._now_iso()


def op_study_create(params: dict, ctx: dict) -> Any:
    """§5.1: a new investigation notebook, its first cell the question."""
    H._require_active(ctx)
    try:
        nb = NBX.new(name=params.get("name"), question=params.get("question"),
                     kind=params.get("kind") or "investigation", author=params.get("author") or "claude",
                     inbox_candidate=params.get("inbox_candidate"), engine_type=params.get("engine_type"),
                     workspace_id=ctx["active_workspace_id"])
    except NBX.NotebookError as e:
        raise _err(e)
    if params.get("inbox_candidate"):
        try:
            IB.resolve(ctx["workspace_dir"], params["inbox_candidate"], "investigating",
                       study_id=NBX.meta(nb)["id"], note=None)
        except IB.InboxError as e:
            raise _err(e)
    qid = params.get("question_id")
    if qid:
        # D16: the owner's question — linked, taken up (investigating), and a
        # log view per pin, each after a markdown cell holding the owner's note.
        try:
            doc = PN.load(ctx["workspace_dir"])
            q = PN.question(doc, qid)
            pins = PN.pins_of(doc, qid)
        except PN.PinsError as e:
            raise _err(e)
        m = NBX.meta(nb)
        m["question_id"] = qid
        if not params.get("question"):
            m["question"] = q["title"]
        nb = _save_nb(ctx, nb)
        for p in pins:
            note = p.get("note") or "*(no note)*"
            when = _pin_when(ctx, p)
            nb["cells"].append(NBX.markdown_cell(NBX.next_id(nb), f"**The owner's mark** — {when}\n\n> {note}",
                                                 role="pin"))
            src = logview_source({"flight": p["flight"], "start_s": p["start_s"], "end_s": p["end_s"],
                                  "channels": p.get("channels") or ["rpm", "map_inhg"], "title": note[:80]})
            if H._FEATURES[ctx.get("host", "server")].get("bench", False) and B.available():
                _append_code(ctx, nb, src)
            else:   # the website: the cell waits for a bench to run it
                nb["cells"].append(NBX.code_cell(NBX.next_id(nb), src))
                _save_nb(ctx, nb)
        try:
            PN.resolve(ctx["workspace_dir"], qid, "investigating", study_id=m["id"])
        except PN.PinsError as e:
            raise _err(e)
        nb = notebook(ctx, m["id"])
    return NBX.read_view(_save_nb(ctx, nb))


# ── guide (D13, §4.6) ──────────────────────────────────────────────────────

GUIDE_FILE = Path(__file__).with_name("guide.md")
PROMPTS_DIR = Path(__file__).with_name("prompts")


def _guide_aircraft(ctx: dict) -> tuple[str, dict]:
    try:
        ac = _aircraft(ctx)
    except H.RpcError:
        return "No aircraft record for this workspace.\n", {"empty": True}
    notes = AC.read_notes(_root(ctx), ac["id"]).strip()
    filled = [(f["label"], ac.get(f["key"])) for f in AC.field_list() if (ac.get(f["key"]) or "").strip()]
    label = AC.engine_label(ac.get("engine_model") or "")
    lines = [f"**{ac.get('name')}**" + (f" — {label}" if label and label != ac.get("name") else ""), ""]
    lines += [f"- {label}: {value}" for label, value in filled]
    # v0.6 (E1): the migration put every workspace under one aircraft; say when this workspace's
    # engine profile isn't the aircraft record's, so no one reads one engine's limits as the other's.
    ws_model = H._current_engine(ctx)[1]
    mismatch = bool(ac.get("engine_model")) and ws_model != ac.get("engine_model")
    if mismatch:
        lines.append(f"- *This workspace's profile is {AC.engine_label(ws_model)}; the aircraft record says "
                     f"{AC.engine_label(ac['engine_model'])}. Use the workspace's profile for limits; the owner can "
                     "move the workspace to its own aircraft (Settings → Aircraft).*")
    empty = not filled
    if empty:
        lines.append("- *The record is empty: no propeller, controller, firmware or avionics. Ask the owner what is "
                     "fitted (Settings → Aircraft) before naming a component as a cause.*")
    lines += ["", "**The owner's notes (notes.md):**", "", notes or "*No notes yet.*"]
    return "\n".join(lines) + "\n", {"empty": empty, "notes": bool(notes), "aircraft_id": ac["id"],
                                     "engine_mismatch": mismatch}


def _guide_documents(ctx: dict) -> tuple[str, dict]:
    if ctx.get("host") == "browser":
        return "Documents are read by the EIS engine on the owner's computer; not in the browser.\n", {"count": 0}
    try:
        got = DOC.list_documents(_documents_dirs(ctx), _root(ctx))
    except (DOC.DocumentError, H.RpcError) as e:
        return f"{getattr(e, 'message', str(e))}\n", {"count": 0}
    if got.get("message") and not got["documents"]:
        return f"*{got['message']}*\n", {"count": 0}
    lines = ["Folders: " + ", ".join(f"{f['label']} ({f['path']}{'' if f['reachable'] else ', not reachable'})"
                                     for f in got["folders"]), ""]
    lines += [f"- `{d['name']}` — {d['kind']}, {d['pages'] if d.get('pages') is not None else '?'} pages"
              + (f": {d['first_line']}" if d.get("first_line") else "") for d in got["documents"]]
    return "\n".join(lines) + "\n", {"count": len(got["documents"])}


def _guide_workspace(ctx: dict) -> tuple[str, dict]:
    from .. import flight_ident as fi
    wid = ctx.get("active_workspace_id")
    entry = next((e for e in ws.load_registry(ctx["registry_path"]).workspaces if e.id == wid), None)
    dates = []
    n = 0
    for fid in ws.list_flight_ids(ctx["workspace_dir"]):
        fa = ws.load_flight_analysis(ctx["workspace_dir"], fid)
        if fa is None:
            continue
        n += 1
        i = fi.load(ctx["workspace_dir"], fid) or {}
        d = i.get("local_date") or (fa.header or {}).get("date")
        if d:
            dates.append(d)
    inbox = IB.load(ctx["workspace_dir"])["candidates"]
    open_ = [c for c in inbox if c.get("status") in IB.OPEN]
    span = f"{min(dates)} to {max(dates)}" if dates else "no dates"
    text = (f"**{entry.name if entry else wid}** (`{wid}`), engine {entry.engine_model if entry else ''}: "
            f"{n} flights, {span} (local dates). Inbox: {len(open_)} open candidate"
            f"{'' if len(open_) == 1 else 's'} ({sum(1 for c in open_ if c['status'] == 'new')} new).\n")
    q_text, qs = _guide_questions(ctx)
    return text + q_text, {"workspace_id": wid, "flights": n, "first": min(dates) if dates else None,
                           "last": max(dates) if dates else None, "inbox_open": len(open_),
                           "questions_open": len(qs["open"]), "pins_unassigned": qs["unassigned"]}


def _guide_questions(ctx: dict) -> tuple[str, dict]:
    """D16: the owner's open questions, each with its pin count and the
    newest pin's note, and how many marks are loose — what *Investigate*
    with no text takes up (the first listed is the newest)."""
    doc = PN.load(ctx["workspace_dir"])
    open_ = [q for q in PN.listing(doc, list(IB.OPEN))["questions"]]
    newest = PN.newest_open(doc)
    if newest:
        open_.sort(key=lambda q: q["id"] != newest["id"])
    loose = len(PN.pins_of(doc, None))
    if not open_ and not loose:
        return "\nThe owner's questions: none open, no marks.\n", {"open": [], "unassigned": 0}
    lines = ["", "The owner's open questions (marked on the Flight view; `pins_list` gives the windows; "
                 "`study_create question_id` opens a notebook with a log view per mark):", ""]
    for q in open_:
        lines.append(f"- `{q['id']}` **{q['title']}** — {q['status']}, {q['pin_count']} mark"
                     f"{'' if q['pin_count'] == 1 else 's'}"
                     + (f"; newest note: \"{q['newest_note']}\"" if q.get("newest_note") else "")
                     + (" *(newest)*" if newest and q["id"] == newest["id"] else ""))
    if loose:
        lines.append(f"- {loose} unassigned mark{'' if loose == 1 else 's'} (no question)")
    return "\n".join(lines) + "\n", {"open": [q["id"] for q in open_], "unassigned": loose}


def op_guide(params: dict, ctx: dict) -> Any:
    """§4.6: one document — the method, the tool map and the notebook rules
    (guide.md, the owner's to edit), then this aircraft's record and notes,
    its documents, and the workspace in use with its flight count, date
    span and open inbox candidates. `flags` say what is missing (F6: an
    empty aircraft record)."""
    H._require_active(ctx)
    base = GUIDE_FILE.read_text(encoding="utf-8").rstrip() + "\n"
    ac_text, ac = _guide_aircraft(ctx)
    doc_text, docs = _guide_documents(ctx)
    ws_text, wsi = _guide_workspace(ctx)
    flags = []
    if ac.get("empty"):
        flags.append("aircraft_record_empty")
    if not ac.get("notes"):
        flags.append("no_owner_notes")
    if not docs["count"]:
        flags.append("no_documents")
    if ac.get("engine_mismatch"):
        flags.append("engine_model_mismatch")
    document = (base + "\n## 4. The aircraft\n\n" + ac_text + "\n## 5. The documents\n\n" + doc_text
                + "\n## 6. The workspace in use\n\n" + ws_text)
    return {"document": document, "flags": flags, "workspace": wsi, "documents": docs["count"],
            "aircraft_id": ac.get("aircraft_id")}


def list_prompts() -> list[dict]:
    """The MCP prompts (§4.6): prompts/*.md, front matter + text."""
    out = []
    for p in sorted(PROMPTS_DIR.glob("*.md")):
        head, body = _front_matter(p.read_text(encoding="utf-8"))
        out.append({**head, "text": body})
    order = {"investigate": 0, "inbox-item": 1, "before-after": 2, "review-new-flights": 3}
    return sorted(out, key=lambda x: order.get(x.get("name"), 9))


def _front_matter(text: str) -> tuple[dict, str]:
    """The small YAML subset the prompt files use: name, title,
    description, and `arguments` as a list of {name, description, required}."""
    if not text.startswith("---\n"):
        return {}, text
    head, body = text[4:].split("\n---\n", 1)
    out: dict = {"arguments": []}
    cur = None
    for line in head.splitlines():
        if line.startswith("  - name:"):
            cur = {"name": line.split(":", 1)[1].strip()}
            out["arguments"].append(cur)
        elif line.startswith("    ") and cur is not None and ":" in line:
            k, v = line.strip().split(":", 1)
            v = v.strip()
            cur[k] = v.lower() == "true" if k == "required" else v
        elif ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            if k != "arguments":
                out[k.strip()] = v.strip()
    return out, body.lstrip("\n")


# ── The bench (D3) ─────────────────────────────────────────────────────────

def eis_request(ctx: dict) -> dict:
    """What the eis library binds to (D14): the workspace, its engine
    profile, aircraft, notes, documents folders and channel assignments —
    the same on the bench (each cell's request) and in a kernel outside EIS
    (`eis.open`)."""
    engine_cfg, engine_name = H._current_engine(ctx)
    ac = _aircraft(ctx)
    return {"ws_dir": str(ctx["workspace_dir"]), "engine_cfg": engine_cfg, "engine_name": engine_name,
            "aircraft": _aircraft_for_bench(ctx), "assignments": H._assignments(ctx),
            "documents_dirs": list(ac.get("documents_dirs") or []), "data_root": str(_root(ctx)),
            "notes": AC.read_notes(_root(ctx), ac["id"]) if ac.get("id") else ""}


def _run_code(ctx: dict, nb: dict, cell_id: str, source: str, timeout_s=None, memory_mb=None) -> dict:
    m = NBX.meta(nb)
    study = {"study_id": m["id"], "name": m.get("name"), "question": m.get("question")}
    r = eis_request(ctx)
    try:
        got = B.run_cell(source=source, cell_id=cell_id, ws_dir=Path(r.pop("ws_dir")),
                         files_dir=NBX.files_dir(ctx["workspace_dir"], m["id"]),
                         scratch=H._export_dir(ctx), mpl_dir=_mpl_dir(ctx), study=study,
                         cap=B.caps(timeout_s, memory_mb), **r)
    except B.BenchError as e:
        raise _err(e)
    return {**got, "outputs": NBX.fresh_namespace_hint(nb, cell_id, got["outputs"])}


def _append_code(ctx: dict, nb: dict, source: str, timeout_s=None, memory_mb=None, cell_id=None) -> dict:
    if not isinstance(source, str) or not source.strip():
        raise H.RpcError("BAD_PARAMS", "a code cell needs source")
    if cell_id:
        try:
            cell = NBX.find(nb, cell_id)
        except NBX.NotebookError as e:
            raise _err(e)
        if cell["cell_type"] != "code":
            raise H.RpcError("BAD_PARAMS", f"cell {cell_id} isn't a code cell")
    else:
        cell = NBX.code_cell(NBX.next_id(nb), source)
        nb["cells"].append(cell)
    got = _run_code(ctx, nb, cell["id"], source, timeout_s, memory_mb)
    cell["source"] = source
    NBX.set_run(cell, got["outputs"], got["ran"])
    _reopen(nb)
    _save_nb(ctx, nb)
    return {"study_id": NBX.meta(nb)["id"], "cell": cell, "previews": got["previews"]}


def op_code_run(params: dict, ctx: dict) -> Any:
    """§4.5: run a cell of Python on the bench and keep it in the notebook —
    appended, or (`cell_id`) replacing that code cell's source and
    outputs. Refused without a study: every executed cell belongs to a
    notebook. The cell's error, if any, is its output, not an RpcError."""
    H._require_active(ctx)
    nb = notebook(ctx, params.get("study_id"))
    return _append_code(ctx, nb, params.get("source"), params.get("timeout_s"), params.get("memory_mb"),
                        params.get("cell_id"))


def logview_source(cell: dict) -> str:
    """`cell_append kind=logview` is the eis.logview call (§5.2), run on the bench."""
    if not cell.get("flight"):
        raise H.RpcError("BAD_PARAMS", "a log view needs flight, start_s, end_s and channels")
    try:
        a, b = float(cell.get("start_s")), float(cell.get("end_s"))
    except (TypeError, ValueError):
        raise H.RpcError("BAD_PARAMS", "a log view needs start_s and end_s (seconds into the flight)")
    if b <= a:
        raise H.RpcError("BAD_PARAMS", "a log view's end_s is after its start_s")
    marks = [list(m) if isinstance(m, (list, tuple)) else [m.get("t_s"), m.get("label", "")]
             for m in cell.get("marks") or []]
    args = [repr(str(cell["flight"])), f"{a:g}", f"{b:g}", f"channels={list(cell.get('channels') or ['rpm', 'map_inhg'])!r}"]
    if marks:
        args.append(f"marks={[(float(t), str(label)) for t, label in marks]!r}")
    if cell.get("title"):
        args.append(f"title={str(cell['title'])!r}")
    if cell.get("rule"):
        args.append(f"rule={str(cell['rule'])!r}")
    return "eis.logview(" + ", ".join(args) + ")\n"


# ── Cells (D4 on the standard format) ──────────────────────────────────────

def op_study_cells_append(params: dict, ctx: dict) -> Any:
    """Append one cell (§5.1): markdown (`source`); code (`source`, run at
    once on the bench); logview (`flight`, `start_s`, `end_s`, `channels`,
    `marks`, `title` — the eis.logview call, run at once)."""
    H._require_active(ctx)
    nb = notebook(ctx, params.get("study_id"))
    cell = dict(params.get("cell") or {})
    kind = cell.get("kind")
    if kind == "markdown":
        src = cell.get("source")
        if not isinstance(src, str) or not src.strip():
            raise H.RpcError("BAD_PARAMS", "a markdown cell needs source")
        new = NBX.markdown_cell(NBX.next_id(nb), src, role=cell.get("role"))
        nb["cells"].append(new)
        _reopen(nb)
        _save_nb(ctx, nb)
        return {"study_id": NBX.meta(nb)["id"], "cell": new, "previews": {}}
    if kind == "code":
        return _append_code(ctx, nb, cell.get("source"), cell.get("timeout_s"), cell.get("memory_mb"))
    if kind == "logview":
        return _append_code(ctx, nb, logview_source(cell))
    raise H.RpcError("BAD_PARAMS", f"a cell's kind is markdown, code or logview; got {kind!r}")


def op_study_cells_rerun(params: dict, ctx: dict) -> Any:
    """§5.1 re-run: the code cells in order against this workspace. New
    outputs identical to the stored ones stand; others wait in `pending`
    until accepted or discarded. Without a bench (the website) nothing
    runs; cells keep their outputs, marked *ran elsewhere* if they came
    from another machine."""
    H._require_active(ctx)
    nb = notebook(ctx, params.get("study_id"))
    bench = H._FEATURES[ctx.get("host", "server")].get("bench", False) and B.available()
    report, previews = [], {}
    for c in nb["cells"]:
        if c["cell_type"] != "code":
            continue
        sm = NBX.slmeta(c)
        if not bench:
            report.append({"cell_id": c["id"], "ran": False, "ran_elsewhere": bool(sm.get("ran_elsewhere") or c.get("outputs"))})
            continue
        got = _run_code(ctx, nb, c["id"], NBX.text(c["source"]))
        previews.update({f"{c['id']}:{k}": v for k, v in got["previews"].items()})
        # Compared as the digest compares (D14): a JupyterLab save's lists of lines say the same thing.
        same = NBX.digest(got["outputs"]) == NBX.digest(c.get("outputs"))
        if same:
            NBX.set_run(c, c.get("outputs") or [], got["ran"])
        else:
            sm["pending"] = {"outputs": got["outputs"], "ran": got["ran"]}
        report.append({"cell_id": c["id"], "ran": True, "identical": same, "status": got["ran"]["status"]})
    _save_nb(ctx, nb)
    return {"study": NBX.summary(nb), "cells": report, "previews": previews}


def _pending(params: dict, ctx: dict, fn) -> Any:
    H._require_active(ctx)
    nb = notebook(ctx, params.get("study_id"))
    ids = params.get("cell_ids")
    done = fn(nb, list(ids) if ids else None)
    _save_nb(ctx, nb)
    return {"study": NBX.summary(nb), "cells": done}


def op_study_cells_accept(params: dict, ctx: dict) -> Any:
    """Accept re-run outputs (all pending, or `cell_ids`): they become the
    cells' outputs. With `source: "external"` (D14), accept instead the
    outputs a kernel outside EIS wrote and saved in place, as they stand."""
    source = params.get("source") or "rerun"
    if source not in ("rerun", "external"):
        raise H.RpcError("BAD_PARAMS", "source is \"rerun\" (the bench's pending outputs) or \"external\" "
                                       "(outputs a kernel outside EIS saved in the notebook)")
    return _pending(params, ctx, NBX.accept_external if source == "external" else NBX.accept)


def op_study_cells_discard(params: dict, ctx: dict) -> Any:
    """Discard re-run outputs; the stored outputs stand."""
    return _pending(params, ctx, NBX.discard)


def op_study_finish(params: dict, ctx: dict) -> Any:
    """An investigation ends (§5.1): the floor rule first — a summary, and a
    markdown cell next to every figure and log view (refused, naming the
    cells, otherwise); then status, summary, the inbox candidate resolved,
    and optionally the Journal study finding (the one Journal entry an
    investigation may write, D7). Reports the inbox's open candidates (F6)
    and the flights the cells read, one count (F7)."""
    H._require_active(ctx)
    nb = notebook(ctx, params.get("study_id"))
    summary = params.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise H.RpcError("BAD_PARAMS", "study_finish needs a summary: what was found, what it means, what to do")
    lacking = NBX.floor_lacking(nb)
    if lacking:
        raise H.RpcError("FLOOR_RULE", "a figure or log view needs a markdown cell right before or after it, "
                                       "saying what it shows; add one beside cell " + ", ".join(lacking))
    failed = NBX.failed_cells(nb)
    if failed:
        raise H.RpcError("FLOOR_RULE", "cell " + ", ".join(failed) + (" ends" if len(failed) == 1 else " end")
                         + " in an error; replace each (code_run with its cell_id) with code that runs — "
                           "the same step done right, or a cell that prints why that path was dropped")
    try:
        tags = NBX.clean_tags(params.get("tags")) if params.get("tags") is not None else None
        finding = NBX.clean_finding(params.get("finding"))
    except NBX.NotebookError as e:
        raise _err(e)
    m = NBX.meta(nb)
    # F17: a follow-up's summary replaces the earlier one; the earlier one
    # stays, with the date it was written, as the notebook's history.
    prev = (m.get("summary") or "").strip()
    if prev and prev != summary.strip():
        m["summaries"] = [*(m.get("summaries") or []), {"summary": prev, "finished": m.get("finished")}]
    m.pop("reopened", None)
    m.update({"summary": summary.strip(), "status": "finished", "finished": H._now_iso()})
    if tags is not None:            # §5.5: Claude's topic words; a follow-up may leave them as they were
        m["tags"] = tags
    # v1.2: the one-line finding (the Journal's line); a finish without one drops an earlier one,
    # which belonged to the earlier summary.
    if finding:
        m["finding"] = finding
    else:
        m.pop("finding", None)
    # §5.5: the resolution this finish gave, for the card (a question's defaults to watch, as below).
    m["resolution"] = params.get("resolution") or ("watch" if (params.get("question") or m.get("question_id")) else None)
    resolved = None
    cand = params.get("inbox_candidate") or m.get("inbox_candidate")
    if cand:
        m["inbox_candidate"] = cand
        status = params.get("resolution")
        if status:
            try:
                resolved = IB.resolve(ctx["workspace_dir"], cand, status, study_id=m["id"], note=params.get("note"))
            except IB.InboxError as e:
                raise _err(e)
    question = None
    qid = params.get("question") or m.get("question_id")
    if qid:
        # D16: the question answered takes the study's resolution, and so
        # do its pins; with none given it is *watch* (the owner decides more).
        m["question_id"] = qid
        try:
            question = PN.resolve(ctx["workspace_dir"], qid, params.get("resolution") or "watch",
                                  study_id=m["id"], note=params.get("note"))
        except PN.PinsError as e:
            raise _err(e)
    _save_nb(ctx, nb)
    entry = None
    if params.get("journal"):
        entry = ws.upsert_journal_entry(
            ctx["workspace_dir"], kind="study_finding", ref_id=f"{m['id']}:summary", what=NBX.journal_line(m, params.get("note")),
            where={"study_id": m["id"], "test_index": None, "study_name": m.get("name")}, note=params.get("note"))
    open_ = [c for c in IB.load(ctx["workspace_dir"])["candidates"] if c.get("status") in IB.OPEN]
    flights = NBX.flights_of(nb)
    return {"study": NBX.summary(nb), "inbox_candidate": resolved, "question": question, "journal_entry": entry,
            "flights": len(flights), "flight_ids": flights,
            "inbox": {"open": len(open_), "new": sum(1 for c in open_ if c.get("status") == "new"),
                      "unresolved_here": bool(cand) and not params.get("resolution")}}


# ── Aircraft and documents (§4.4, §2.4 layer 4) ────────────────────────────

def _root(ctx: dict) -> Path:
    return Path(ctx["registry_path"]).parent


def _aircraft(ctx: dict, aircraft_id=None) -> dict:
    try:
        if aircraft_id:
            return AC.load(_root(ctx), aircraft_id)
        H._require_active(ctx)
        ac = AC.of_workspace(_root(ctx), ctx["active_workspace_id"])
    except AC.AircraftError as e:
        raise _err(e)
    if ac is None:
        raise H.RpcError("NOT_FOUND", "this workspace belongs to no aircraft")
    return ac


def _aircraft_for_bench(ctx: dict) -> dict:
    ac = AC.of_workspace(_root(ctx), ctx.get("active_workspace_id")) or {}
    out = {k: ac.get(k, "") for k in ("name", "engine_model") + AC.KEYS}
    out["notes"] = AC.read_notes(_root(ctx), ac["id"]) if ac.get("id") else ""
    return out


def _with_workspaces(ctx: dict, ac: dict) -> list[dict]:
    reg = {e.id: e for e in ws.load_registry(ctx["registry_path"]).workspaces}
    return [{"id": w, "name": reg[w].name, "engine_model": reg[w].engine_model,
             "flight_count": reg[w].flight_count, "last_opened_at": reg[w].last_opened_at}
            for w in ac["workspaces"] if w in reg]


def op_aircraft_get(params: dict, ctx: dict) -> Any:
    """The aircraft record (§4.4): the active workspace's aircraft, or
    `aircraft_id`'s; with its notes.md whole, its workspaces, the field
    list, and — for the active workspace — what Settings → Log channels
    holds (the channel assignments)."""
    ac = _aircraft(ctx, params.get("aircraft_id"))
    out = {"aircraft": ac, "notes": AC.read_notes(_root(ctx), ac["id"]), "fields": AC.field_list(),
           "workspaces": _with_workspaces(ctx, ac), "engine_model": ac["engine_model"]}
    if ctx.get("active_workspace_id") and ctx["active_workspace_id"] in ac["workspaces"]:
        settings = ws.load_workspace_settings(ctx["workspace_dir"])
        out["channel_assignments"] = settings.channel_assignments
    return out


def op_aircraft_set(params: dict, ctx: dict) -> Any:
    """Set fields of the record (the S14 fields, `name`, `documents_dirs`)
    and/or its notes (`notes`, the whole notes.md)."""
    ac = _aircraft(ctx, params.get("aircraft_id"))
    try:
        if params.get("aircraft"):
            ac = AC.update(_root(ctx), ac["id"], params["aircraft"])
        if params.get("notes") is not None:
            if not isinstance(params["notes"], str):
                raise H.RpcError("BAD_PARAMS", "notes is the whole notes.md as text")
            AC.write_notes(_root(ctx), ac["id"], params["notes"])
    except AC.AircraftError as e:
        raise _err(e)
    return op_aircraft_get({"aircraft_id": ac["id"]}, ctx)


def op_aircraft_assign(params: dict, ctx: dict) -> Any:
    """Settings → Aircraft (Spec 16 §4.4, Session F): move `workspace_id`
    (default: the active one) to `aircraft_id`, or to a new aircraft
    (`new_aircraft: {"name": …}`, the workspace's engine model). Answers
    with the target's record (aircraft_get)."""
    root = _root(ctx)
    wid = params.get("workspace_id") or ctx.get("active_workspace_id")
    reg = {e.id: e for e in ws.load_registry(ctx["registry_path"]).workspaces}
    if not wid or wid not in reg:
        raise H.RpcError("NOT_FOUND", f"no workspace {wid!r} in this registry")
    new = params.get("new_aircraft")
    if bool(new) == bool(params.get("aircraft_id")):
        raise H.RpcError("BAD_PARAMS", "give aircraft_id (an aircraft in this registry) or new_aircraft {\"name\": …}")
    try:
        if new:
            if not isinstance(new, dict):
                raise H.RpcError("BAD_PARAMS", "new_aircraft is {\"name\": …}")
            target = AC.create(root, str(new.get("name") or ""), reg[wid].engine_model)
        else:
            target = AC.load(root, params["aircraft_id"])
        AC.assign(root, wid, target["id"])
    except AC.AircraftError as e:
        raise _err(e)
    return op_aircraft_get({"aircraft_id": target["id"]}, ctx)


def op_list_aircraft(params: dict, ctx: dict) -> Any:
    """Every aircraft in the registry with its workspaces (D10)."""
    return [{**ac, "workspaces": _with_workspaces(ctx, ac)} for ac in AC.list_aircraft(_root(ctx))]


def _documents_dirs(ctx: dict) -> list[str]:
    return list(_aircraft(ctx).get("documents_dirs") or [])


def op_documents_list(params: dict, ctx: dict) -> Any:
    """D11: the documents in the aircraft's documents_dirs, read in place
    (PDF, Markdown, text; subfolders), with page counts from the index
    cache. No folder set: an empty list and the setting to use."""
    H._require_active(ctx)
    try:
        out = DOC.list_documents(_documents_dirs(ctx), _root(ctx))
    except DOC.DocumentError as e:
        raise _err(e)
    legacy = ctx["workspace_dir"] / "documents"
    if legacy.is_dir() and any(p.is_file() and not p.name.startswith(".") for p in legacy.iterdir()):
        out["legacy_note"] = (f"{legacy} (Session D's copy inside the workspace) is no longer read; add the folder "
                              "where the originals live to Settings → Aircraft → Documents folders.")
    return out


def op_document_read(params: dict, ctx: dict) -> Any:
    """A document a page at a time (≤ 3 pages, 12 000 characters), or the
    pages where a phrase occurs (`find`: case-insensitive, diacritics
    folded): never whole."""
    H._require_active(ctx)
    try:
        return DOC.read_document(_documents_dirs(ctx), _root(ctx), params.get("name"), page=params.get("page", 1),
                                 pages=params.get("pages", 1), find=params.get("find"))
    except DOC.DocumentError as e:
        raise _err(e)


# ── The inbox (D5) ─────────────────────────────────────────────────────────

async def _scan(ctx: dict, as_of=None) -> dict:
    engine_cfg, engine_name = H._current_engine(ctx)
    settings = ws.load_workspace_settings(ctx["workspace_dir"])
    bc = ws.load_selection(ctx["workspace_dir"]).baseline_config

    def progress(u):
        H._emit(ctx, "research", {"active": True, "phase": "inbox", **u})
    H._emit(ctx, "research", {"active": True, "phase": "inbox"})
    try:
        return await IB.scan(ctx["workspace_dir"], H._sources(ctx), engine_name=engine_name, engine_cfg=engine_cfg,
                             baseline_config=bc, sensitivity=settings.research_sensitivity,
                             assignments=H._assignments(ctx), as_of=as_of, on_progress=progress)
    finally:
        H._emit(ctx, "research", {"active": False})


def _stale(ctx: dict, doc: dict) -> bool:
    last = doc.get("last_scan")
    if not last:
        return True
    sens = ws.load_workspace_settings(ctx["workspace_dir"]).research_sensitivity
    # The live inbox follows every flight; a scan pinned to a date (as_of)
    # is a reproduction, which the next automatic scan replaces.
    return last.get("fingerprint") != IB.fingerprint(ctx["workspace_dir"], None, sens) \
        or last.get("engine") != __version__


async def op_inbox_scan(params: dict, ctx: dict) -> Any:
    """§6: scan now. `as_of` (a date) pins the scan to the flights up to
    that day — for reproducing a past inbox; the default is every flight."""
    H._require_active(ctx)
    try:
        doc = await _scan(ctx, params.get("as_of"))
        out = IB.listing(doc)
    except IB.InboxError as e:
        raise _err(e)
    return out


async def op_inbox_list(params: dict, ctx: dict) -> Any:
    """§6: the candidates (optionally of some statuses). The scan runs
    first when the workspace changed since the last one — new flights, a
    new engine version, another sensitivity: "after each import" without
    making an import wait for it. `scan: "never"` reads what is stored."""
    H._require_active(ctx)
    doc = IB.load(ctx["workspace_dir"])
    if params.get("scan", "auto") != "never" and (_stale(ctx, doc) or params.get("scan") == "always"):
        doc = await _scan(ctx, None)
    st = params.get("status")
    try:
        return IB.listing(doc, [st] if isinstance(st, str) else st)
    except IB.InboxError as e:
        raise _err(e)


def op_inbox_resolve(params: dict, ctx: dict) -> Any:
    """Set a candidate's status (new, investigating, nothing-here, watch,
    acted), its study and a note. A resolved candidate comes back only
    once the recent window has moved on by half its flights."""
    H._require_active(ctx)
    try:
        return {"candidate": IB.resolve(ctx["workspace_dir"], params.get("candidate_id"), params.get("status"),
                                        study_id=params.get("study_id"), note=params.get("note"))}
    except IB.InboxError as e:
        raise _err(e)


# ── The owner's questions and pins (D16, §6) ───────────────────────────────

def _pin_when(ctx: dict, p: dict) -> str:
    """'“First flight” 2026-10-24 22:26:07–22:26:53 PDT (+10:16–+11:02 into the flight) · `rpm`, `map_inhg`' —
    the date once (the window label carries it), the channels as the ids code uses."""
    d = _describe_pin(ctx)(p)
    from .. import flight_ident as fi
    name = f"\u201c{d['flight_name']}\u201d " if d["flight_name"] else ""
    when = d["when"] or f"{d['date'] or p.get('flight')}, {fi.window_label(None, p['start_s'], p['end_s'])}"
    chans = ", ".join(f"`{c}`" for c in p.get("channels") or [])
    return f"{name}{when}" + (f" \u00b7 {chans}" if chans else "")


def _describe_pin(ctx: dict):
    from .. import flight_ident as fi
    names = fi.load_names(ctx["workspace_dir"])
    present = set(ws.list_flight_ids(ctx["workspace_dir"]))

    def describe(p: dict) -> dict:
        fid = p.get("flight")
        here = fid in present
        ident = fi.load(ctx["workspace_dir"], fid) if here else None
        fa = ws.load_flight_analysis(ctx["workspace_dir"], fid) if here else None
        return {"flight_here": here,
                "date": (ident or {}).get("local_date") or ((fa.header or {}).get("date") if fa else None),
                "flight_name": (names.get(fid) or {}).get("name") if here else None,
                "when": fi.window_label(ident, p["start_s"], p["end_s"]) if here else None,
                "route": "–".join((ident or {}).get("route") or []) or None}
    return describe


def _pins_call(fn):
    try:
        return fn()
    except PN.PinsError as e:
        raise _err(e)


def op_flight_pin(params: dict, ctx: dict) -> Any:
    """D16 *Mark for Claude*: a pin — flight, window, the channels shown, a
    note — under a question (`question`: an id, {"title": …} for a new one,
    or null for unassigned). Stores where to look and a sentence, never
    analysis. Returns the pin, its question and where it went."""
    H._require_active(ctx)
    fid = params.get("flight_id")
    if not fid or fid not in set(ws.list_flight_ids(ctx["workspace_dir"])):
        raise H.RpcError("NOT_FOUND", f"no flight {fid} in this workspace")
    question = params.get("question")
    if question is None and params.get("question_id"):
        question = params["question_id"]
    if question is None and params.get("question_title"):
        question = {"title": params["question_title"]}
    pin, q = _pins_call(lambda: PN.pin(ctx["workspace_dir"], fid, params.get("start_s"), params.get("end_s"),
                                       channels=params.get("channels"), note=params.get("note"), question=question))
    pin = {**pin, **_describe_pin(ctx)(pin)}
    n = len(PN.pins_of(PN.load(ctx["workspace_dir"]), q["id"])) if q else None
    where = (f"under \u201c{q['title']}\u201d ({n} mark{'' if n == 1 else 's'}) in Research \u2192 Inbox"
             if q else "in Research \u2192 Inbox, under Unassigned")
    return {"pin": pin, "question": q, "where": where}


def op_pins_list(params: dict, ctx: dict) -> Any:
    """D16: the owner's questions (optionally of some statuses), each with
    its pins (flight, window, channels, note, and the flight's date, name
    and local window), and the unassigned pins. `newest_open` names the
    question *Investigate* takes when asked with no text."""
    H._require_active(ctx)
    doc = PN.load(ctx["workspace_dir"])
    st = params.get("status")
    out = _pins_call(lambda: PN.listing(doc, [st] if isinstance(st, str) else st, describe=_describe_pin(ctx)))
    newest = PN.newest_open(doc)
    out["newest_open"] = newest["id"] if newest else None
    return out


def op_question_resolve(params: dict, ctx: dict) -> Any:
    """D16: a question's status (new, investigating, nothing-here, watch,
    acted), its notebook and a note; its pins take the resolution."""
    H._require_active(ctx)
    return {"question": _pins_call(lambda: PN.resolve(ctx["workspace_dir"], params.get("question_id"),
                                                      params.get("status"), study_id=params.get("study_id"),
                                                      note=params.get("note")))}


def op_pin_edit(params: dict, ctx: dict) -> Any:
    """A pin's note, channels, window, or question (`question`: an id,
    {"title": …} for a new one, or null to leave it unassigned); only the
    keys given change."""
    H._require_active(ctx)
    changes = {k: params[k] for k in ("note", "channels", "start_s", "end_s", "question") if k in params}
    pin, q = _pins_call(lambda: PN.edit_pin(ctx["workspace_dir"], params.get("pin_id"), **changes))
    return {"pin": pin, "question": q}


def op_pin_delete(params: dict, ctx: dict) -> Any:
    H._require_active(ctx)
    return {"deleted": _pins_call(lambda: PN.delete_pin(ctx["workspace_dir"], params.get("pin_id")))["id"]}


def op_question_edit(params: dict, ctx: dict) -> Any:
    H._require_active(ctx)
    return {"question": _pins_call(lambda: PN.edit_question(ctx["workspace_dir"], params.get("question_id"),
                                                            title=params.get("title"), note=params.get("note")))}


def op_question_delete(params: dict, ctx: dict) -> Any:
    """The question goes; its pins stay, unassigned."""
    H._require_active(ctx)
    q, n = _pins_call(lambda: PN.delete_question(ctx["workspace_dir"], params.get("question_id")))
    return {"deleted": q["id"], "pins_unassigned": n}


def op_study_set_tags(params: dict, ctx: dict) -> Any:
    """Spec 03 v0.37 / Spec 16 §5.5: the owner adds or removes a notebook's
    tags from the page (`+` on a card or the notebook header). One list,
    shared with Claude's study_finish tags. Page-only: no MCP tool. The
    notebook's date is kept — a tag is filing, not an edit."""
    H._require_active(ctx)
    nb = notebook(ctx, params.get("study_id"))
    try:
        tags = NBX.clean_tags(params.get("tags") or [])
        NBX.meta(nb)["tags"] = tags
        NBX.save(ctx["workspace_dir"], nb, touch=False)
    except NBX.NotebookError as e:
        raise _err(e)
    return {"study": NBX.summary(nb)}


OPS = ("guide", "study_create", "code_run", "study_cells_append", "study_cells_rerun", "study_cells_accept", "study_cells_discard",
       "study_finish", "aircraft_get", "aircraft_set", "aircraft_assign", "list_aircraft", "documents_list", "document_read", "inbox_scan", "inbox_list", "inbox_resolve",
       "flight_pin", "pins_list", "question_resolve", "pin_edit", "pin_delete", "question_edit", "question_delete", "study_set_tags")

