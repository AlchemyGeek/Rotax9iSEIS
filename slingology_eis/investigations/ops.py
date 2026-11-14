"""
Spec 16 §4.3: the host operations Investigations adds, on the Spec 01 §7
envelope. host.py registers each one; this module holds them so the
host's own file doesn't grow by a feature's worth of code.

    code_run                                   (D3 — server host only)
    study_cells_append / _rerun / _accept / _discard, study_finish   (D4)
    aircraft_get / aircraft_set                (§4.4)
    documents_list / document_read / document_add / document_remove
    inbox_scan / inbox_list / inbox_resolve    (D5)

`export_study` (Spec 06 §11) gains `format: "ipynb"`; it stays in host.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import __version__
from .. import host as H
from .. import workspace as ws
from ..research import studies as rs
from ..research.rules import RuleError
from . import aircraft as AC
from . import bench as B
from . import documents as DOC
from . import inbox as IB
from . import notebook as NB


def _err(e) -> H.RpcError:
    return H.RpcError(getattr(e, "code", "BAD_PARAMS"), getattr(e, "message", str(e)))


def _load_editable(ctx: dict, study_id: str) -> dict:
    doc = rs.load(ctx["workspace_dir"], study_id)
    if doc.get("read_only"):
        raise H.RpcError("READ_ONLY", "this study holds the sender's results; use Run this on my flights")
    return doc


def _save(ctx: dict, doc: dict) -> dict:
    return rs.save(ctx["workspace_dir"], doc, engine_model=H._engine_model(ctx))


def _mpl_dir(ctx: dict) -> Path:
    root = Path(ctx.get("registry_path") or ctx["workspace_dir"]).parent
    return root / "cache" / "matplotlib"


# ── The bench (D3) ─────────────────────────────────────────────────────────

def _run_code(ctx: dict, doc: dict, cell_id: str, source: str, timeout_s=None, memory_mb=None) -> dict:
    engine_cfg, engine_name = H._current_engine(ctx)
    study = {k: doc.get(k) for k in ("study_id", "name", "question", "selection", "slice_rules", "hand_slices",
                                      "references")}
    try:
        return B.run_cell(source=source, cell_id=cell_id, ws_dir=ctx["workspace_dir"],
                          files_dir=NB.files_dir(ctx["workspace_dir"], doc["study_id"]),
                          scratch=H._export_dir(ctx), mpl_dir=_mpl_dir(ctx), engine_cfg=engine_cfg,
                          engine_name=engine_name, aircraft=AC.load(ctx["workspace_dir"]),
                          assignments=H._assignments(ctx), study=study, cap=B.caps(timeout_s, memory_mb))
    except B.BenchError as e:
        raise _err(e)


def op_code_run(params: dict, ctx: dict) -> Any:
    """§4.5: run a cell of Python on the bench and keep it in the study —
    appended, or (`cell_id`) replacing that code cell's source and
    outputs. The cell's error, if any, is its output, not an RpcError."""
    H._require_active(ctx)
    doc = NB.materialise(_load_editable(ctx, params.get("study_id")))
    source = params.get("source")
    if not isinstance(source, str) or not source.strip():
        raise H.RpcError("BAD_PARAMS", "code_run needs source")
    cid = params.get("cell_id")
    if cid:
        try:
            cell = NB.find(doc, cid)
        except RuleError as e:
            raise H.RpcError("NOT_FOUND", str(e))
        if cell["kind"] != "code":
            raise H.RpcError("BAD_PARAMS", f"cell {cid} isn't a code cell")
    else:
        cell = {"id": NB.next_id(doc), "kind": "code", "source": source, "outputs": [], "ran": None,
                "pending_outputs": None}
        doc["cells"].append(cell)
    got = _run_code(ctx, doc, cell["id"], source, params.get("timeout_s"), params.get("memory_mb"))
    cell.update({"source": source, "outputs": got["outputs"], "ran": got["ran"], "pending_outputs": None})
    for k in ("pending_ran", "ran_elsewhere", "read_only"):
        cell.pop(k, None)
    saved = _save(ctx, doc)
    NB.collect_figures(ctx["workspace_dir"], saved)
    return {"study_id": saved["study_id"], "cell": NB.find(saved, cell["id"]), "previews": got["previews"]}


# ── Cells (D4) ─────────────────────────────────────────────────────────────

async def _run_question(ctx: dict, doc: dict) -> dict:
    engine_cfg, _ = H._current_engine(ctx)
    H._emit(ctx, "research", {"active": True, "phase": "starting"})
    try:
        return await rs.run(ctx["workspace_dir"], H._sources(ctx), doc, engine_cfg=engine_cfg,
                            assignments=H._assignments(ctx), on_progress=H._research_progress(ctx))
    finally:
        H._emit(ctx, "research", {"active": False})


async def op_study_cells_append(params: dict, ctx: dict) -> Any:
    """Append one cell: markdown (`source`), question (`test_id`,
    `channels`, `params`, optional own `slices`; run at once), or a figure
    or table a code cell wrote under files/ (`ref`, `title`). Code cells
    are appended by code_run."""
    H._require_active(ctx)
    doc = NB.materialise(_load_editable(ctx, params.get("study_id")))
    cell = dict(params.get("cell") or {})
    kind = cell.get("kind")
    new = {"id": NB.next_id(doc), "kind": kind}
    if kind == "markdown":
        new["source"] = cell.get("source")
        if cell.get("role"):
            new["role"] = cell["role"]
    elif kind == "question":
        test = {k: cell[k] for k in ("test_id", "params", "channels", "slices") if cell.get(k) is not None}
        if isinstance(test.get("slices"), dict):
            # A preset named by id stands for its rule, as in save_study.
            test["slices"] = {**test["slices"], "slice_rules": H._research_rules(ctx, test["slices"].get("slice_rules"))}
        doc["tests"] = list(doc.get("tests") or []) + [test]
        new["test_index"] = len(doc["tests"]) - 1
    elif kind in ("figure", "table"):
        new["ref"] = cell.get("ref")
        if cell.get("title"):
            new["title"] = cell["title"]
        f = NB.files_dir(ctx["workspace_dir"], doc["study_id"]) / str(cell.get("ref") or "").split("/", 1)[-1]
        if not str(cell.get("ref") or "").startswith("files/") or not f.is_file():
            raise H.RpcError("BAD_PARAMS", f"no file {cell.get('ref')!r} in the study's files/ (a code cell writes it under FILES)")
    elif kind == "code":
        raise H.RpcError("BAD_PARAMS", "code cells are run and appended by code_run")
    else:
        raise H.RpcError("BAD_PARAMS", f"a cell's kind is one of markdown, question, figure, table; got {kind!r}")
    doc["cells"].append(new)
    doc = rs.normalise(doc)                       # validates the new cell (RuleError → BAD_PARAMS)
    if kind == "question":
        doc = await _run_question(ctx, doc)
    saved = _save(ctx, doc)
    out = {"study_id": saved["study_id"], "cell": NB.find(saved, new["id"])}
    if kind == "question":
        t = saved["tests"][new["test_index"]]
        out["result"] = t.get("result")
        if t.get("error"):
            out["error"] = t["error"]
    return out


async def op_study_cells_rerun(params: dict, ctx: dict) -> Any:
    """§5 re-run: every cell in order against this workspace. Question
    cells recompute (their results replace the stored ones, as run_study
    does); code cells run on the bench where there is one and their new
    outputs wait in `pending_outputs` until accepted or discarded — unless
    they are identical to the stored outputs, which then stand. Without a
    bench (the website) code cells are left as they are, marked *ran
    elsewhere* if their outputs came from another machine."""
    H._require_active(ctx)
    doc = NB.materialise(_load_editable(ctx, params.get("study_id")))
    report = []
    if doc.get("tests"):
        doc = await _run_question(ctx, doc)
    bench = H._FEATURES[ctx.get("host", "server")].get("bench", False)
    previews: dict = {}
    for c in doc["cells"]:
        if c["kind"] == "question":
            t = doc["tests"][c["test_index"]]
            report.append({"cell_id": c["id"], "kind": "question", "ran": t.get("result") is not None,
                           "error": t.get("error")})
        elif c["kind"] == "code":
            if not bench:
                report.append({"cell_id": c["id"], "kind": "code", "ran": False,
                               "ran_elsewhere": bool(c.get("ran_elsewhere") or c.get("outputs"))})
                continue
            got = _run_code(ctx, doc, c["id"], c["source"])
            previews.update(got["previews"])
            same = B.outputs_equal(got["outputs"], c.get("outputs"))
            if same:
                c["ran"] = got["ran"]
                c["pending_outputs"] = None
                c.pop("pending_ran", None)
                c.pop("ran_elsewhere", None)
                c.pop("read_only", None)
            else:
                c["pending_outputs"], c["pending_ran"] = got["outputs"], got["ran"]
            report.append({"cell_id": c["id"], "kind": "code", "ran": True, "identical": same,
                           "status": got["ran"]["status"]})
    saved = _save(ctx, doc)
    NB.collect_figures(ctx["workspace_dir"], saved)
    return {"study": saved, "cells": report, "previews": previews}


def _pending(params: dict, ctx: dict, fn) -> Any:
    H._require_active(ctx)
    doc = NB.materialise(_load_editable(ctx, params.get("study_id")))
    ids = params.get("cell_ids")
    done = fn(doc, list(ids) if ids else None)
    saved = _save(ctx, doc)
    NB.collect_figures(ctx["workspace_dir"], saved)
    return {"study": saved, "cells": done}


def op_study_cells_accept(params: dict, ctx: dict) -> Any:
    """Accept re-run outputs (all pending, or `cell_ids`): they become the
    cells' outputs."""
    return _pending(params, ctx, NB.accept)


def op_study_cells_discard(params: dict, ctx: dict) -> Any:
    """Discard re-run outputs; the stored outputs stand."""
    return _pending(params, ctx, NB.discard)


def op_study_finish(params: dict, ctx: dict) -> Any:
    """An investigation ends: its summary (what it found, what it means,
    what to do) is kept on the study; optionally the inbox candidate it
    answered is resolved, and the summary noted in the Journal as a study
    finding — the one Journal entry an investigation may write (D7)."""
    H._require_active(ctx)
    doc = _load_editable(ctx, params.get("study_id"))
    summary = params.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise H.RpcError("BAD_PARAMS", "study_finish needs a summary: what was found, what it means, what to do")
    doc["summary"] = summary.strip()
    doc["status"] = "finished"
    doc["finished"] = H._now_iso()
    if doc.get("kind", "hand") == "hand":
        doc["kind"] = "investigation"
    resolved = None
    cand = params.get("inbox_candidate") or doc.get("inbox_candidate")
    if cand:
        doc["inbox_candidate"] = cand
        status = params.get("resolution")
        if status:
            try:
                resolved = IB.resolve(ctx["workspace_dir"], cand, status, study_id=doc["study_id"],
                                      note=params.get("note"))
            except IB.InboxError as e:
                raise _err(e)
    saved = _save(ctx, doc)
    entry = None
    if params.get("journal"):
        finding = params.get("finding") or summary.strip().split("\n", 1)[0]
        entry = ws.upsert_journal_entry(
            ctx["workspace_dir"], kind="study_finding", ref_id=f"{saved['study_id']}:summary", what=finding,
            where={"study_id": saved["study_id"], "test_index": None, "study_name": saved["name"]},
            note=params.get("note"))
    return {"study": rs.summary(saved), "inbox_candidate": resolved, "journal_entry": entry}


# ── Aircraft and documents (§4.4, §2.4 layer 4) ────────────────────────────

def op_aircraft_get(params: dict, ctx: dict) -> Any:
    """The aircraft document, its field list, and what Settings → Log
    channels holds (the channel assignments)."""
    H._require_active(ctx)
    settings = ws.load_workspace_settings(ctx["workspace_dir"])
    _cfg, engine_name = H._current_engine(ctx)
    return {"aircraft": AC.load(ctx["workspace_dir"]), "fields": AC.field_list(), "engine_model": engine_name,
            "channel_assignments": settings.channel_assignments}


def op_aircraft_set(params: dict, ctx: dict) -> Any:
    H._require_active(ctx)
    try:
        return {"aircraft": AC.save(ctx["workspace_dir"], params.get("aircraft") or {}), "fields": AC.field_list()}
    except AC.AircraftError as e:
        raise H.RpcError("BAD_PARAMS", str(e))


def op_documents_list(params: dict, ctx: dict) -> Any:
    H._require_active(ctx)
    try:
        return DOC.list_documents(ctx["workspace_dir"])
    except DOC.DocumentError as e:
        raise _err(e)


def op_document_read(params: dict, ctx: dict) -> Any:
    """A document a page at a time (or `find` a phrase): never whole."""
    H._require_active(ctx)
    try:
        return DOC.read_document(ctx["workspace_dir"], params.get("name"), page=params.get("page", 1),
                                 pages=params.get("pages", 1), find=params.get("find"))
    except DOC.DocumentError as e:
        raise _err(e)


def op_document_add(params: dict, ctx: dict) -> Any:
    H._require_active(ctx)
    content, filename = H._log_content(params, ctx)
    try:
        return {"document": DOC.add_document(ctx["workspace_dir"], filename, content)}
    except DOC.DocumentError as e:
        raise _err(e)


def op_document_remove(params: dict, ctx: dict) -> Any:
    H._require_active(ctx)
    try:
        return DOC.remove_document(ctx["workspace_dir"], params.get("name"))
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


# export_study's ipynb (host.py calls this)
def ipynb_export(ctx: dict, doc: dict) -> bytes:
    files = NB.files_dir(ctx["workspace_dir"], doc["study_id"])

    def read(ref: str):
        p = files / ref.split("/", 1)[-1]
        return p.read_bytes() if p.is_file() else None
    return NB.ipynb_bytes(doc, read)


OPS = ("code_run", "study_cells_append", "study_cells_rerun", "study_cells_accept", "study_cells_discard",
       "study_finish", "aircraft_get", "aircraft_set", "documents_list", "document_read", "document_add",
       "document_remove", "inbox_scan", "inbox_list", "inbox_resolve")

