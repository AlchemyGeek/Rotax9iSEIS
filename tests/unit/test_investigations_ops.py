"""
Spec 16 §4.3 Investigations operations, run the three ways every host
operation is (Spec 04 §9.6): in process, over HTTP, and under Pyodide in
Node.js — on synthetic flights (no private logs). The bench (code_run)
runs where a worker process can be started; under Pyodide it answers
NOT_SUPPORTED (acceptance 8's Pyodide clause).
"""
import base64
import json

import pytest

from tests.unit.test_research_ops import (  # noqa: F401 — fixtures and helpers
    FULL_POWER, _http_download, _import, _ok, research_ws,
)
from tests.unit.test_server import (  # noqa: F401 — fixtures
    InProcess, NodeHost, _node_host, isolated_packaged_home, registry_server, rpc,
)


def _has_bench(h) -> bool:
    return not isinstance(h, NodeHost)


def _bench_stack():
    pytest.importorskip("matplotlib")
    pytest.importorskip("scipy")


def _download(h, url):
    return h.download(url) if isinstance(h, (InProcess, NodeHost)) else _http_download(h, url)


def _notebook(h, name="Why does rpm cycle?") -> str:
    return _ok(rpc(h, "study_create", {"name": name, "question": "Why does rpm cycle at full power?"}))["study_id"]


def _sm(cell: dict) -> dict:
    return (cell.get("metadata") or {}).get("slingology") or {}


def _rule_literal() -> str:
    return json.dumps(FULL_POWER).replace("false", "False").replace("true", "True").replace("null", "None")


# ── capabilities ──────────────────────────────────────────────────────────

def test_capabilities(registry_server):
    caps = _ok(rpc(registry_server, "get_capabilities", {}))
    assert caps["features"]["investigations"] is True
    assert caps["features"]["bench"] is _has_bench(registry_server)


# ── code_run (§4.5) ───────────────────────────────────────────────────────

def test_code_run_keeps_a_cell(research_ws):
    h, ids = research_ws
    # Every executed cell belongs to a notebook (§5.1).
    no = rpc(h, "code_run", {"source": "1 + 1"})
    assert not no["ok"] and no["error"]["code"] == "BAD_PARAMS" and "study_create" in no["error"]["message"]
    sid = _notebook(h)
    src = ("df = load_slices(FULL_POWER_RULE, channels=['rpm'])\nprint(len(df), 'slices')\n"
           "fig, ax = plt.subplots(); ax.plot(df['rpm.swing']); df[['flight_id', 'rpm.swing']]")
    src = src.replace("FULL_POWER_RULE", _rule_literal())
    d = rpc(h, "code_run", {"study_id": sid, "source": src})
    if not _has_bench(h):
        assert not d["ok"] and d["error"]["code"] == "NOT_SUPPORTED"
        return
    _bench_stack()
    r = _ok(d)
    cell = r["cell"]
    assert cell["cell_type"] == "code" and _sm(cell)["ran"]["status"] == "ok", cell
    kinds = [o["output_type"] for o in cell["outputs"]]
    assert kinds == ["stream", "execute_result", "display_data"], kinds   # figures left open come last
    assert cell["outputs"][0]["text"].strip() == "6 slices"
    assert "<table" in cell["outputs"][1]["data"]["text/html"]
    assert cell["outputs"][1]["metadata"]["slingology"]["table"]["n_rows"] == 6
    assert cell["outputs"][2]["data"]["image/svg+xml"].lstrip().startswith("<?xml")
    assert sorted(_sm(cell)["ran"]["flights"]) == sorted(ids)
    assert list(r["previews"]) == ["o2"]
    # Replacing the cell: same id, new source.
    r2 = _ok(rpc(h, "code_run", {"study_id": sid, "cell_id": cell["id"], "source": "1 + 1"}))
    assert r2["cell"]["id"] == cell["id"]
    assert r2["cell"]["outputs"] == [{"output_type": "execute_result", "execution_count": None, "metadata": {},
                                      "data": {"text/plain": "2"}}]
    view = _ok(rpc(h, "load_study", {"study_id": sid}))
    assert [c["id"] for c in view["notebook"]["cells"]] == ["setup", "c1", cell["id"]]
    assert view["notebook"]["cells"][1]["cell_type"] == "markdown"          # the question, after the setup cell
    # A hand study takes no code.
    hand = _ok(rpc(h, "save_study", {"study": {"name": "Hand", "slice_rules": ["full_power"]}}))
    refused = rpc(h, "code_run", {"study_id": hand["study_id"], "source": "1"})
    assert not refused["ok"] and "hand study" in refused["error"]["message"]


def test_code_run_errors_are_outputs(research_ws):
    h, _ids = research_ws
    if not _has_bench(h):
        pytest.skip("no bench under Pyodide")
    _bench_stack()
    sid = _notebook(h)
    cell = _ok(rpc(h, "code_run", {"study_id": sid, "source": "x = 1\n1 / 0"}))["cell"]
    assert _sm(cell)["ran"]["status"] == "error"
    err = cell["outputs"][-1]
    assert err["output_type"] == "error" and err["ename"] == "ZeroDivisionError"
    tb = "\n".join(err["traceback"])
    assert "1 / 0" in tb and "cell" in tb
    bad = rpc(h, "code_run", {"study_id": sid, "source": "1", "timeout_s": 9999})
    assert not bad["ok"] and bad["error"]["code"] == "BAD_PARAMS"


# ── cells (§5.1) ──────────────────────────────────────────────────────────

def test_cells_append_rerun_accept_finish(research_ws):
    h, ids = research_ws
    sid = _notebook(h)
    md = _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "markdown", "source": "# Plan"}}))
    assert md["cell"]["cell_type"] == "markdown" and md["cell"]["id"] == "c2"
    old = rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "question", "test_id": "cycling"}})
    assert not old["ok"] and "markdown, code or logview" in old["error"]["message"]
    bench = _has_bench(h)
    if bench:
        _bench_stack()
        # Acceptance 12: eis.cycling is question_run's own code.
        tool = _ok(rpc(h, "run_test", {"test_id": "cycling", "slice_rules": [FULL_POWER], "channels": ["rpm"]}))
        c = _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {
            "kind": "code", "source": f"r = eis.cycling({_rule_literal()}, 'rpm')\nprint(r.finding)\nr"}}))["cell"]
        assert c["outputs"][0]["text"].strip() == tool["finding"]
        assert c["outputs"][1]["data"]["text/plain"].startswith(tool["question"])      # the §8 text
        assert sorted(_sm(c)["ran"]["flights"]) == sorted(ids)
        # A log view (§5.2): the SVG and the reference, never samples.
        lv = _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {
            "kind": "logview", "flight": ids[0], "start_s": 10, "end_s": 70, "channels": ["rpm", "map_inhg"],
            "marks": [[20, "takeoff power"]], "title": "Full power"}}))
        out = lv["cell"]["outputs"][-1]["data"]
        ref = out["application/vnd.slingology.logview+json"]
        assert ref["flight"] == ids[0] and ref["start_s"] == 10 and ref["end_s"] == 70
        assert ref["marks"] == [{"t_s": 20.0, "label": "takeoff power"}] and "rpm" not in json.dumps(ref).split('"channels"')[0]
        assert "image/svg+xml" in out and not any(isinstance(v, list) and len(v) > 50 for v in ref.values())
        assert lv["cell"]["source"].startswith("eis.logview(")
        # The floor rule: the log view has a code cell before it and nothing after.
        fl = rpc(h, "study_finish", {"study_id": sid, "summary": "x"})
        assert not fl["ok"] and fl["error"]["code"] == "FLOOR_RULE" and lv["cell"]["id"] in fl["error"]["message"]
        _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "markdown",
                                                                     "source": "The window shows the swing."}}))
        # A cell whose output changes on re-run waits in pending.
        rnd = _ok(rpc(h, "code_run", {"study_id": sid, "source": "import random\nprint(random.random())"}))["cell"]
    re = _ok(rpc(h, "study_cells_rerun", {"study_id": sid}))
    if bench:
        by = {c["cell_id"]: c for c in re["cells"]}
        assert by[rnd["id"]]["identical"] is False
        assert all(c["identical"] for k, c in by.items() if k != rnd["id"]), re["cells"]
        assert re["study"]["pending"] == 1
        view = _ok(rpc(h, "load_study", {"study_id": sid}))["notebook"]
        pend = next(c for c in view["cells"] if c["id"] == rnd["id"])
        assert _sm(pend)["pending"]["outputs"] != pend["outputs"]
        acc = _ok(rpc(h, "study_cells_accept", {"study_id": sid}))
        assert acc["cells"] == [rnd["id"]] and acc["study"]["pending"] == 0
        assert _ok(rpc(h, "study_cells_discard", {"study_id": sid}))["cells"] == []
    else:       # no bench: nothing runs; the setup cell (D14) is the only code cell
        assert re["cells"] == [{"cell_id": "setup", "ran": False, "ran_elsewhere": False}]
    fin = _ok(rpc(h, "study_finish", {"study_id": sid, "summary": "RPM cycles at full power.\nIt is the governor.",
                                      "journal": True}))
    assert fin["study"]["status"] == "finished" and fin["journal_entry"]["kind"] == "study_finding"
    assert fin["journal_entry"]["what"] == "RPM cycles at full power."
    assert fin["flights"] == (len(ids) if bench else 0) and "open" in fin["inbox"]       # F7, F6
    j = _ok(rpc(h, "get_journal", {}))
    assert [e["kind"] for e in j["entries"]].count("study_finding") == 1
    listed = _ok(rpc(h, "list_studies", {}))["studies"]
    row = next(s for s in listed if s["study_id"] == sid)
    assert row["format"] == "ipynb" and row["cells"] == (7 if bench else 3)   # the setup cell (D14) first and row["status"] == "finished"
    assert not rpc(h, "study_finish", {"study_id": sid, "summary": " "})["ok"]


# ── export, import, Run this on my flights (§5.1, acceptance 5, 12) ───────

def test_notebook_round_trip(research_ws):
    import io
    import zipfile
    h, ids = research_ws
    sid = _notebook(h)
    _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "markdown", "source": "Plan: **look**."}}))
    code = None
    if _has_bench(h):
        _bench_stack()
        code = _ok(rpc(h, "code_run", {"study_id": sid, "source": (
            "import matplotlib.pyplot as plt\nfig, ax = plt.subplots(); ax.plot([1, 2, 3]); "
            "print(len(flights())); info = flight_info(flights().flight_id[0])")}))["cell"]
        assert _sm(code)["ran"]["flights"], code
    re = _ok(rpc(h, "study_cells_rerun", {"study_id": sid}))
    assert re["study"]["pending"] == 0
    stored = _ok(rpc(h, "load_study", {"study_id": sid}))["notebook"]
    try:
        import nbformat
        nbformat.validate(nbformat.from_dict(stored))
    except ImportError:
        pass

    assert not rpc(h, "export_study", {"study_id": sid, "format": "eisstudy"})["ok"]
    exp = _ok(rpc(h, "export_study", {"study_id": sid}))
    assert exp["filename"].endswith(".zip")
    data = _download(h, exp["download_url"])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.namelist()[0] == "notebook.ipynb"
        sent = json.loads(z.read("notebook.ipynb"))
    assert sent["metadata"]["slingology"]["id"] == sid and len(sent["cells"]) == len(stored["cells"])
    page = _download(h, _ok(rpc(h, "export_study", {"study_id": sid, "format": "html"}))["download_url"]).decode()
    assert page.startswith("<!DOCTYPE html>") and "<strong>look</strong>" in page and "<script" not in page
    assert page == _download(h, _ok(rpc(h, "export_study", {"study_id": sid, "format": "html"}))["download_url"]).decode()
    if code is not None:
        assert "show code" in page and "data:image/svg+xml;base64," in page
        # S5: what leaves names flights by content fingerprint, never flight_id…
        sent_code = next(c for c in sent["cells"] if c["cell_type"] == "code" and c["id"] != "setup")
        fl = _sm(sent_code)["ran"]["flights"]
        assert fl and all(f.startswith("src:") for f in fl) and not set(fl) & set(ids)
        # …and an import where the flights are maps them back.
        back = _ok(rpc(h, "import_study", {"content_base64": base64.b64encode(data).decode(), "filename": "S.zip"}))
        back_code = next(c for c in back["notebook"]["cells"] if c["cell_type"] == "code" and c["id"] != "setup")
        assert _sm(back_code)["ran"]["flights"] == _sm(code)["ran"]["flights"]
        assert _sm(back_code)["ran_elsewhere"] and not _sm(back_code).get("read_only")
        # A bare .ipynb imports too.
        bare = _ok(rpc(h, "import_study", {"content_base64": base64.b64encode(json.dumps(sent).encode()).decode(),
                                           "filename": "S.ipynb"}))
        assert bare["study_id"] != sid and bare["format"] == "ipynb"

    # Another workspace that has none of these flights: read-only per cell.
    _ok(rpc(h, "create_workspace", {"name": "Other", "engine_model": "916iS"}))
    other = _import(h, "2026-02-01")
    got = _ok(rpc(h, "import_study", {"content_base64": base64.b64encode(data).decode(), "filename": "S.zip"}))
    assert got["kind"] == "investigation" and got["format"] == "ipynb"
    if code is not None:
        c = next(c for c in got["notebook"]["cells"] if c["cell_type"] == "code" and c["id"] != "setup")
        assert _sm(c).get("read_only") and c["outputs"] == code["outputs"]
        assert all(f.startswith("src:") for f in _sm(c)["ran"]["flights"])   # not here: kept as fingerprints
    mine = _ok(rpc(h, "run_study_on_my_flights", {"study_id": got["study_id"]}))
    assert mine["study_id"] != got["study_id"] and mine["format"] == "ipynb"
    if code is not None:
        c = next(c for c in mine["notebook"]["cells"] if c["cell_type"] == "code" and c["id"] != "setup")
        assert _sm(c)["ran"]["flights"] == [other] and not _sm(c).get("read_only")
        assert c["outputs"][0]["text"].strip() == "1"
    else:
        c = next((c for c in mine["notebook"]["cells"] if c["cell_type"] == "code" and c["id"] != "setup"), None)
        assert c is None or _sm(c).get("ran_elsewhere")


def test_session_d_study_converts_on_first_load(research_ws, isolated_packaged_home):
    """Acceptance 15: a Session D investigation (the Spec 06 document with
    cells) becomes notebook.ipynb on first load — markdown kept, code kept
    with its outputs, a question cell as markdown plus the eis code that
    reproduces it; a hand study is untouched."""
    h, ids = research_ws
    if isinstance(h, NodeHost):
        pytest.skip("writes the Session D document straight into the workspace folder")
    ws_dir = next(p.parent for p in (isolated_packaged_home / "workspaces").glob("*/manifest.json"))
    tool = _ok(rpc(h, "run_test", {"test_id": "cycling", "slice_rules": ["full_power"], "channels": ["rpm"]}))
    full = _ok(rpc(h, "list_slice_presets", {"engine": "916iS"}))["presets"][0]
    full = {k: v for k, v in full.items() if k not in ("question", "status", "description")}
    hand = _ok(rpc(h, "save_study", {"study": {"name": "Hand", "slice_rules": ["full_power"],
                                                "tests": [{"test_id": "cycling", "channels": ["rpm"]}]}}))
    doc = {"study_id": "st-0123456789ab", "name": "Old", "kind": "investigation", "author": "claude",
           "question": "Why?", "selection": {"mode": "all"}, "slice_rules": [hand["slice_rules"][0]],
           "hand_slices": [], "references": [], "windows": {}, "provenance": {"engine": "1.0.2"},
           "tests": [{"test_id": "cycling", "channels": ["rpm"], "params": {}, "result": tool}],
           "cells": [{"id": "c1", "kind": "markdown", "source": "First."},
                     {"id": "c2", "kind": "code", "source": "print(1)", "ran": {"engine": "1.0.2", "flights": []},
                      "outputs": [{"kind": "text", "stream": "stdout", "text": "1\n"}], "pending_outputs": None},
                     {"id": "c3", "kind": "question", "test_index": 0}],
           "status": "finished", "summary": "It cycles."}
    (ws_dir / "studies" / "st-0123456789ab.json").write_text(json.dumps(doc))
    listed = {s["study_id"]: s for s in _ok(rpc(h, "list_studies", {}))["studies"]}
    assert listed["st-0123456789ab"]["format"] == "ipynb" and listed[hand["study_id"]].get("format") is None
    assert (ws_dir / "studies" / "st-0123456789ab" / "notebook.ipynb").is_file()
    assert (ws_dir / "studies" / "st-0123456789ab" / ".session-d.json").is_file()
    assert not (ws_dir / "studies" / "st-0123456789ab.json").exists()
    nb = _ok(rpc(h, "load_study", {"study_id": "st-0123456789ab"}))["notebook"]
    # D14: the setup cell first, bound to this workspace; the workspace in the metadata.
    assert [c["cell_type"] for c in nb["cells"]] == ["code", "markdown", "markdown", "code", "markdown", "code"]
    assert nb["cells"][0]["id"] == "setup" and f'eis.open("{ws_dir.name}")' in nb["cells"][0]["source"]
    assert nb["metadata"]["slingology"]["workspace_id"] == ws_dir.name
    assert nb["metadata"]["slingology"]["status"] == "finished"
    assert nb["cells"][3]["outputs"] == [{"output_type": "stream", "name": "stdout", "text": "1\n"}]
    q = nb["cells"][5]
    assert q["source"].startswith("r = eis.cycling('full_power', 'rpm')") and "print(r)" in q["source"]
    stored_text = q["outputs"][0]["text"]
    assert stored_text.startswith(tool["question"]) and tool["finding"] in stored_text
    if _has_bench(h):
        _bench_stack()
        re = _ok(rpc(h, "study_cells_rerun", {"study_id": "st-0123456789ab"}))
        assert next(c for c in re["cells"] if c["cell_id"] == q["id"])["identical"] is True, re
    # The hand study is a hand study.
    assert _ok(rpc(h, "load_study", {"study_id": hand["study_id"]}))["tests"][0]["test_id"] == "cycling"


# ── guide (§4.6) ──────────────────────────────────────────────────────────

def test_guide(research_ws):
    """D13: one document — the method and tool map (guide.md), the notebook
    rules, the aircraft record and notes, documents, the workspace — and
    F6: an empty aircraft record is flagged."""
    h, ids = research_ws
    g = _ok(rpc(h, "guide", {}))
    doc = g["document"]
    for part in ("## 1. The method", "## 2. The tool map", "## 3. The notebook", "## 4. The aircraft",
                 "## 5. The documents", "## 6. The workspace in use"):
        assert part in doc, part
    for form in ('"split": "source"', '{"by": "date", "date": "2026-10-01"}', '"hand_slices"', '"windows"',
                 "skip_onset_s", '"phase:CLIMB"'):
        assert form in doc, form
    assert "aircraft_record_empty" in g["flags"] and "The record is empty" in doc
    assert g["workspace"]["flights"] == len(ids) and "6 flights" in doc and "Inbox: 0 open" in doc
    _ok(rpc(h, "aircraft_set", {"aircraft": {"propeller": "Test prop"}, "notes": "Governor adjusted 2026-01-03."}))
    g2 = _ok(rpc(h, "guide", {}))
    assert "aircraft_record_empty" not in g2["flags"] and "Governor adjusted 2026-01-03." in g2["document"]
    assert "- Propeller: Test prop" in g2["document"]
    assert "engine_model_mismatch" not in g2["flags"]
    # v0.6 (E1): a 915 iS workspace under the 916 iS aircraft (as the migration does) is flagged.
    _ok(rpc(h, "create_workspace", {"name": "Other engine", "engine_model": "915iS"}))
    g3 = _ok(rpc(h, "guide", {}))
    assert "engine_model_mismatch" in g3["flags"]
    assert "This workspace's profile is Rotax 915 iS; the aircraft record says Rotax 916 iS" in g3["document"]


# ── aircraft and documents (§4.4) ─────────────────────────────────────────

def test_aircraft(registry_server):
    """D10: the record is the registry's; every workspace belongs to one."""
    h = registry_server
    _ok(rpc(h, "create_workspace", {"name": "A", "engine_model": "916iS"}))
    a = _ok(rpc(h, "aircraft_get", {}))
    assert a["engine_model"] == "916iS" and "propeller" in [f["key"] for f in a["fields"]]
    assert a["aircraft"]["name"] == "Rotax 916 iS" and a["notes"] == ""
    assert [w["name"] for w in a["workspaces"]] == ["A"]
    s = _ok(rpc(h, "aircraft_set", {"aircraft": {"propeller": "Test prop", "prop_controller": "Test ctl",
                                                 "name": "My Sling"}, "notes": "# Notes\n\nGovernor replaced.\n"}))
    assert s["aircraft"]["propeller"] == "Test prop" and s["notes"].startswith("# Notes")
    got = _ok(rpc(h, "aircraft_get", {}))
    assert got["aircraft"]["prop_controller"] == "Test ctl" and got["aircraft"]["name"] == "My Sling"
    bad = rpc(h, "aircraft_set", {"aircraft": {"registration": "N1"}})
    assert not bad["ok"] and bad["error"]["code"] == "BAD_PARAMS"
    rel = rpc(h, "aircraft_set", {"aircraft": {"documents_dirs": ["relative/path"]}})
    assert not rel["ok"] and "absolute" in rel["error"]["message"]
    # A second workspace joins the only aircraft.
    _ok(rpc(h, "create_workspace", {"name": "B", "engine_model": "916iS"}))
    every = _ok(rpc(h, "list_aircraft", {}))
    assert len(every) == 1 and sorted(w["name"] for w in every[0]["workspaces"]) == ["A", "B"]


def tiny_pdf(pages: list[str]) -> bytes:
    """A minimal PDF, one line of Helvetica per page (enough for pypdf)."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
        objs.append(f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream")
        content = len(objs)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content} 0 R "
                    f"/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(len(objs))
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        body = o if isinstance(o, bytes) else o.encode("latin-1")
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_documents_from_the_aircraft_folders(registry_server, tmp_path):
    """D11 / acceptance 11 (engine clauses) on a temp folder: listed in place
    (nothing copied), paged, found case-insensitively with diacritics
    folded, re-indexed when a file changes, and no folder → the setting."""
    h = registry_server
    _ok(rpc(h, "create_workspace", {"name": "D", "engine_model": "916iS"}))
    empty = _ok(rpc(h, "documents_list", {}))
    assert empty["documents"] == [] and "Settings → Aircraft → Documents folders" in empty["message"]
    folder = tmp_path / "Manuals"
    (folder / "Bulletins").mkdir(parents=True)
    md = "# Engine\n\n## Boost\n\n" + "Boost is allowed for five minutes.\n" * 3 + "\n## Idle\n\nIdle rpm. Régime de ralenti.\n"
    (folder / "om.md").write_text(md)
    (folder / "Bulletins" / "sb-23.pdf").write_bytes(tiny_pdf(["Governor overview", "Governor HUNTING at full power"]))
    (folder / ".hidden.md").write_text("# no")
    _ok(rpc(h, "aircraft_set", {"aircraft": {"documents_dirs": [str(folder)]}}))
    listing = _ok(rpc(h, "documents_list", {}))
    docs = {d["name"]: d for d in listing["documents"]}
    assert sorted(docs) == ["Bulletins/sb-23.pdf", "om.md"] and docs["om.md"]["pages"] == 3
    assert listing["folders"] == [{"path": str(folder), "label": "Manuals", "reachable": True}]
    p = _ok(rpc(h, "document_read", {"name": "om.md", "page": 2}))
    assert p["pages"][0]["title"] == "Engine › Boost" and "five minutes" in p["pages"][0]["text"]
    f = _ok(rpc(h, "document_read", {"name": "om.md", "find": "regime DE RALENTI"}))
    assert [m["page"] for m in f["matches"]] == [3] and "Régime" in f["matches"][0]["snippet"]
    if docs["Bulletins/sb-23.pdf"]["pages"] is not None:          # pypdf present (not under Pyodide)
        hunt = _ok(rpc(h, "document_read", {"name": "Bulletins/sb-23.pdf", "find": "hunt"}))
        assert [m["page"] for m in hunt["matches"]] == [2]
    # Nothing was copied into the workspace or the data root, beyond the cache.
    assert not rpc(h, "document_read", {"name": "../registry.json"})["ok"]
    # A changed file is re-indexed on the next read.
    (folder / "om.md").write_text(md + "\n## Shutdown\n\nCool down two minutes.\n")
    assert _ok(rpc(h, "document_read", {"name": "om.md", "find": "cool down"}))["matches"][0]["page"] == 4
    # The withdrawn copy operations are gone.
    assert rpc(h, "document_add", {"filename": "x.md", "content_base64": ""})["error"]["code"] == "UNKNOWN_OP"


# ── inbox (§6) ────────────────────────────────────────────────────────────

def _flights(h, n, swing, start_day=1):
    return [_import(h, f"2026-03-{d:02d}", swing_rpm=swing) for d in range(start_day, start_day + n)]


def test_inbox_nominal_workspace_raises_nothing(registry_server):
    """Acceptance 7, second clause: a nominal synthetic workspace — full
    power held steady — gives no candidate at any sensitivity."""
    h = registry_server
    _ok(rpc(h, "create_workspace", {"name": "Nominal", "engine_model": "916iS"}))
    _flights(h, 8, swing=0)
    for level in ("quiet", "normal", "curious"):
        _ok(rpc(h, "save_workspace_settings", {"settings": {"research_sensitivity": level}}))
        got = _ok(rpc(h, "inbox_scan", {}))
        assert got["candidates"] == [], (level, got["candidates"])


def test_inbox_recurring_pattern_and_resolution(registry_server):
    h = registry_server
    _ok(rpc(h, "create_workspace", {"name": "Cycling", "engine_model": "916iS"}))
    _flights(h, 8, swing=90)
    got = _ok(rpc(h, "inbox_list", {}))          # scans: the workspace is new to the inbox
    rec = [c for c in got["candidates"] if c["kind"] == "recurring"]
    assert len(rec) == 1, got["candidates"]
    c = rec[0]
    assert c["preset"] == "full_power" and c["descriptors"] == ["rpm.period"] and c["status"] == "new"
    assert c["sensitivity"] == "normal" and c["parameters"]["n"] == 6 and c["parameters"]["m"] == 10
    assert len(c["slices"]) >= 6 and c["evidence"]["rows"]
    # One open candidate per preset and descriptor: a rescan doesn't add another.
    again = _ok(rpc(h, "inbox_scan", {}))
    assert [x["id"] for x in again["candidates"] if x["kind"] == "recurring"] == [c["id"]]
    # nothing-here keeps it out…
    _ok(rpc(h, "inbox_resolve", {"candidate_id": c["id"], "status": "nothing-here", "note": "governor"}))
    _flights(h, 1, swing=90, start_day=20)
    after = _ok(rpc(h, "inbox_list", {}))
    assert [x["status"] for x in after["candidates"] if x["kind"] == "recurring"] == ["nothing-here"]
    # …until the recent window has moved on by half its flights.
    window = after["candidates"][0]["window"]["flight_ids"]
    _flights(h, (len(window) + 1) // 2, swing=90, start_day=21)
    moved = _ok(rpc(h, "inbox_list", {}))
    st = sorted(x["status"] for x in moved["candidates"] if x["kind"] == "recurring")
    assert st == ["new", "nothing-here"], moved["candidates"]
    bad = rpc(h, "inbox_resolve", {"candidate_id": c["id"], "status": "maybe"})
    assert not bad["ok"] and bad["error"]["code"] == "BAD_PARAMS"
