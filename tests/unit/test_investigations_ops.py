from pathlib import Path
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
    # D19: the setup cell, the seven sections (the question under 1), the cell under Findings.
    assert [c["id"] for c in view["notebook"]["cells"]] == ["setup", "s1", "s2", "s3", "s4", cell["id"], "s5", "s6", "s7"]
    assert view["notebook"]["cells"][1]["cell_type"] == "markdown"          # the question, after the setup cell
    assert "Why does rpm cycle at full power?" in "".join(view["notebook"]["cells"][1]["source"])


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


def test_spec16_v1_5_a_failed_cell_is_named_and_fixed_in_place(research_ws):
    """v1.5: each cell starts afresh (S3); a cell failing on a name an earlier
    cell set is told so; study_finish refuses while a code cell ends in an
    error, naming it, and finishes once that cell is replaced."""
    h, _ids = research_ws
    if not _has_bench(h):
        pytest.skip("no bench under Pyodide")
    _bench_stack()
    sid = _notebook(h)
    first = _ok(rpc(h, "code_run", {"study_id": sid, "source": "high = [1, 2, 3]\nprint(len(high))"}))["cell"]
    bad = _ok(rpc(h, "code_run", {"study_id": sid, "source": "print(high[0])"}))["cell"]
    err = bad["outputs"][-1]
    assert err["ename"] == "NameError" and err["evalue"] == "name 'high' is not defined"
    hint = err["traceback"][-1]
    assert f"`high` was set in cell {first['id']}" in hint and f"cell_id {bad['id']}" in hint
    # A name no earlier cell set gets no hint; nor does any other error.
    other = _ok(rpc(h, "code_run", {"study_id": sid, "source": "print(nowhere)"}))["cell"]
    assert "starts afresh" not in "\n".join(other["outputs"][-1]["traceback"])
    _ok(rpc(h, "code_run", {"study_id": sid, "cell_id": other["id"], "source": "print('dropped: no such channel')"}))
    fl = rpc(h, "study_finish", {"study_id": sid, "summary": "x"})
    assert not fl["ok"] and fl["error"]["code"] == "FLOOR_RULE"
    assert f"cell {bad['id']} ends in an error" in fl["error"]["message"] and other["id"] not in fl["error"]["message"]
    # The re-run gives the same hinted error, so it stays identical rather than pending.
    re = _ok(rpc(h, "study_cells_rerun", {"study_id": sid}))
    assert all(c["identical"] for c in re["cells"]), re["cells"]
    _ok(rpc(h, "code_run", {"study_id": sid, "cell_id": bad["id"], "source": "high = [1, 2, 3]\nprint(high[0])"}))
    _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "markdown", "source": "The first is 1."}}))
    done = _ok(rpc(h, "study_finish", {"study_id": sid, "summary": "x"}))
    assert done["study"]["status"] == "finished"


# ── cells (§5.1) ──────────────────────────────────────────────────────────

def test_cells_append_rerun_accept_finish(research_ws):
    h, ids = research_ws
    sid = _notebook(h)
    md = _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "markdown", "source": "# Plan"}}))
    assert md["cell"]["cell_type"] == "markdown" and md["cell"]["id"] == "c1"
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
            "marks": [[20, "takeoff power"]]}}))           # no title or caption: nothing says what it shows
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
        rnd = _ok(rpc(h, "code_run", {"study_id": sid, "source": "import random\nprint(random.random())",
                                      "role": "scratch"}))["cell"]
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
    assert row["format"] == "ipynb" and row["cells"] == (13 if bench else 9)   # the setup cell (D14) first and row["status"] == "finished"
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
        assert ("show code" in page or "show the calculation" in page) and "data:image/svg+xml;base64," in page
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


def test_old_studies_convert_on_first_load(research_ws, isolated_packaged_home):
    """Acceptance 15 (Session D) and Spec 16 D15 / acceptance 17: a study
    stored the old way becomes notebook.ipynb on first load. A Session D
    investigation keeps its markdown, its code with outputs, and each
    question cell as markdown plus the eis code that reproduces it. A hand
    study (Spec 06 v1.0 retired them) becomes a markdown cell per question
    with the eis code, its stored output the stored §8 result and its
    finding the notebook's; it re-runs identically where there is a bench."""
    h, ids = research_ws
    if isinstance(h, NodeHost):
        pytest.skip("writes the old documents straight into the workspace folder")
    ws_dir = next(p.parent for p in (isolated_packaged_home / "workspaces").glob("*/manifest.json"))
    tool = _ok(rpc(h, "run_test", {"test_id": "cycling", "slice_rules": ["full_power"], "channels": ["rpm"]}))
    full = _ok(rpc(h, "list_slice_presets", {"engine": "916iS"}))["presets"][0]
    full_rule = {k: v for k, v in full.items() if k not in ("question", "status", "description", "isolates")}
    (ws_dir / "studies").mkdir(exist_ok=True)
    doc = {"study_id": "st-0123456789ab", "name": "Old", "kind": "investigation", "author": "claude",
           "question": "Why?", "selection": {"mode": "all"}, "slice_rules": [full_rule],
           "hand_slices": [], "references": [], "windows": {}, "provenance": {"engine": "1.0.2"},
           "tests": [{"test_id": "cycling", "channels": ["rpm"], "params": {}, "result": tool}],
           "cells": [{"id": "c1", "kind": "markdown", "source": "First."},
                     {"id": "c2", "kind": "code", "source": "print(1)", "ran": {"engine": "1.0.2", "flights": []},
                      "outputs": [{"kind": "text", "stream": "stdout", "text": "1\n"}], "pending_outputs": None},
                     {"id": "c3", "kind": "question", "test_index": 0}],
           "status": "finished", "summary": "It cycles."}
    (ws_dir / "studies" / "st-0123456789ab.json").write_text(json.dumps(doc))
    groups = _ok(rpc(h, "run_test", {"test_id": "groups", "slice_rules": ["full_power"],
                                     "params": {"descriptor": "rpm.swing", "split": {"by": "date", "date": "2026-01-04"}}}))
    hand = {"study_id": "st-00000000abcd", "name": "Full-power swing by hand", "selection": {"mode": "all", "split": None},
            "slice_rules": [full_rule], "hand_slices": [], "references": [], "windows": {}, "notes": "Looked after the SB.",
            "provenance": {"engine": "1.0.2"}, "created": "2026-11-01T10:00:00+00:00", "updated": "2026-11-02T10:00:00+00:00",
            "signal": {"flight_id": ids[0], "channels": ["rpm", "map_inhg"], "window": {"start_s": 600, "end_s": 660}},
            "tests": [{"test_id": "cycling", "channels": ["rpm"], "params": {}, "result": tool},
                      {"test_id": "groups", "channels": ["rpm"],
                       "params": {"descriptor": "rpm.swing", "split": {"by": "date", "date": "2026-01-04"}},
                       "result": groups}]}
    (ws_dir / "studies" / "st-00000000abcd.json").write_text(json.dumps(hand))
    listed = {s["study_id"]: s for s in _ok(rpc(h, "list_studies", {}))["studies"]}
    assert {listed[k]["format"] for k in ("st-0123456789ab", "st-00000000abcd")} == {"ipynb"}
    assert (ws_dir / "studies" / "st-0123456789ab" / ".session-d.json").is_file()
    assert (ws_dir / "studies" / "st-00000000abcd" / ".hand-study.json").is_file()
    assert not list((ws_dir / "studies").glob("*.json"))
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
    # The hand study: intro, notes, then per question its heading and the eis call with the stored result.
    hv = _ok(rpc(h, "load_study", {"study_id": "st-00000000abcd"}))
    hn = hv["notebook"]
    hm = hn["metadata"]["slingology"]
    assert hm["author"] == "user" and hm["converted_from"] == "hand-study" and hm["status"] == "finished"
    assert hv["finding"] == tool["finding"] == listed["st-00000000abcd"]["finding"]     # the findings, unchanged
    assert hm["summary"] == tool["finding"] + "\n" + groups["finding"]
    kinds = [c["cell_type"] for c in hn["cells"]]
    assert kinds == ["code", "markdown", "markdown", "markdown", "markdown", "code", "markdown", "code"], kinds
    intro = hn["cells"][2]["source"]
    assert "built by hand" in intro and "Signal:" in intro and ids[0] in intro and "every flight" in intro
    assert "Looked after the SB." in hn["cells"][3]["source"]
    from slingology_eis.research.render import render_text
    qs = [c for c in hn["cells"] if c["cell_type"] == "code" and c["id"] != "setup"]
    assert [c["outputs"][0]["text"] for c in qs] == [render_text(tool) + "\n", render_text(groups) + "\n"]
    assert qs[1]["source"].startswith("r = eis.groups('full_power', 'rpm.swing', by={'by': 'date', 'date': '2026-01-04'})"), qs[1]["source"]
    if _has_bench(h):
        _bench_stack()
        for sid, cid in (("st-0123456789ab", q["id"]), ("st-00000000abcd", qs[0]["id"]), ("st-00000000abcd", qs[1]["id"])):
            re = _ok(rpc(h, "study_cells_rerun", {"study_id": sid}))
            assert next(c for c in re["cells"] if c["cell_id"] == cid)["identical"] is True, (sid, re)


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
    # Spec 16 §5.5: the guide and the Investigate prompt ask for two or three topic tags at study_finish.
    from slingology_eis.investigations import ops as O
    inv = (O.PROMPTS_DIR / "investigate.md").read_text()
    assert "`tags`: two or three topic words" in doc and "not what it found" in doc
    assert "`tags`: two or three topic words" in inv
    # Guide v2 (D19): the shape — plan first, scratch, a finding is one sentence and one evidence cell, print is
    # never evidence, context kept out of Findings, the structured Answer, a follow-up rewrites it; none is an answer.
    for rule in ("**Plan before computing.**", "in `scratch` cells", "**one sentence and one evidence cell**",
                 "**Raw `print` output is\n  never evidence**", "labelled as context", "**rewritten Answer**",
                 "**\"None\" is\n    an answer**", "`recheck_after_flights`", "| **7 Working** |"):
        assert rule in doc, rule
    # The prompts: Investigate ends with the structured Answer; every prompt asks for it.
    assert inv.rstrip().endswith("Finish with the structured Answer.")
    for p in O.PROMPTS_DIR.glob("*.md"):
        assert "study_followup" in p.read_text() and ("shows" in p.read_text() or "structured Answer" in p.read_text()), p
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


def test_spec16_20_the_tests_are_instruments_not_steps():
    """Acceptance 20 (F16), the clause CI can hold: what Claude is told. The
    guide's method names each test with the question it fits and says none
    is a step; an oil-temperature question is worked with load/slice/plot
    and groups, no cycling or coupling unless the notebook says why; and no
    prompt lists the four tests as steps to take whatever the question.
    (That a notebook from *Investigate* follows it is the owner's check in
    Claude Desktop — the session report's checklist.)"""
    import re
    from slingology_eis.investigations import ops as O
    guide = (Path(O.__file__).parent / "guide.md").read_text(encoding="utf-8")
    method = guide[guide.index("## 1. The method"):guide.index("## 2. The tool map")]
    for test, about in (("eis.cycling", "steady"), ("eis.coupling", "two channels moving together"),
                        ("eis.groups", "a difference"), ("eis.unusual", "standing out")):
        row = next(line for line in method.splitlines() if f"`{test}`" in line)
        assert about in row, (test, row)
    assert "None of these is a step every notebook takes" in method
    assert "the cell beside it says\n   why" in method or "the cell beside it says why" in " ".join(method.split())
    oil = " ".join(method[method.index("An oil-temperature question"):].split())
    assert "no cycling or coupling unless the notebook says why" in oil and "eis.groups" in oil and "oil_temp_f" in oil
    four = re.compile(r"eis\.cycling.{0,40}eis\.coupling.{0,40}eis\.groups.{0,40}eis\.unusual", re.S)
    for pr in O.list_prompts():
        assert not four.search(pr["text"]), f"{pr['name']} lists the four tests as steps"
    inv = next(pr for pr in O.list_prompts() if pr["name"] == "investigate")["text"]
    assert "a test only\n   when the question is about" in inv or "a test only when the question is about" in " ".join(inv.split())


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


# ── F17: the notebook is the record (acceptance 23's engine clauses) ───────

def test_spec16_23_a_follow_up_reopens_the_notebook_and_keeps_the_earlier_summary(research_ws):
    h, ids = research_ws
    sid = _notebook(h, "Oil temperature in cruise")
    _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "markdown", "source": "Oil runs warmer."}}))
    first = _ok(rpc(h, "study_finish", {"study_id": sid, "summary": "Oil runs 6 °F warmer this month."}))["study"]
    assert first["status"] == "finished" and first["summaries"] == []
    cells = first["cells"]

    def row():
        return next(s for s in _ok(rpc(h, "list_studies", {}))["studies"] if s["study_id"] == sid)

    # A probe-only follow-up adds nothing: the notebook is as it was.
    _ok(rpc(h, "list_flights", {}))
    assert row()["status"] == "finished" and row()["cells"] == cells

    # New analysis appended to a finished notebook opens it again.
    _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {
        "kind": "markdown", "source": "## Follow-up — 2026-11-18\n\nAgainst OAT, the rise follows the warmer days."}}))
    assert row()["status"] == "reopened" and row()["summary"] == "Oil runs 6 °F warmer this month."
    view = _ok(rpc(h, "load_study", {"study_id": sid}))
    assert view["status"] == "reopened" and view["notebook"]["metadata"]["slingology"]["status"] == "open"
    if _has_bench(h):
        _bench_stack()
        _ok(rpc(h, "code_run", {"study_id": sid, "source": "print(1 + 1)", "role": "scratch"}))
        assert row()["status"] == "reopened"

    # Finishing again: the new summary, the earlier one kept with its date. D19: the follow-up the
    # reopening opened ends with what changed.
    no = rpc(h, "study_finish", {"study_id": sid, "summary": "Oil runs warmer with OAT, not on its own."})
    assert not no["ok"] and "changed" in no["error"]["message"]
    again = _ok(rpc(h, "study_finish", {"study_id": sid, "summary": "Oil runs warmer with OAT, not on its own.",
                                        "changed": "The answer: OAT, not the engine."}))["study"]
    assert again["status"] == "finished" and again["summary"] == "Oil runs warmer with OAT, not on its own."
    assert [e["summary"] for e in again["summaries"]] == ["Oil runs 6 °F warmer this month."]
    assert again["summaries"][0]["finished"][:2] == "20"
    meta = _ok(rpc(h, "load_study", {"study_id": sid}))["notebook"]["metadata"]["slingology"]
    assert "reopened" not in meta and meta["summaries"] == again["summaries"]

    # Re-running the cells as they are doesn't reopen it.
    _ok(rpc(h, "study_cells_rerun", {"study_id": sid}))
    assert row()["status"] == "finished"

    # The export shows the history under the summary.
    exp = _ok(rpc(h, "export_study", {"study_id": sid, "format": "html"}))
    page = _download(h, exp["download_url"]).decode()
    assert "Earlier summaries (1)" in page and "Oil runs 6 °F warmer this month." in page


# ── Spec 16 §5.5: what a notebook says about itself (v1.1) ─────────────────

def test_spec16_5_5_the_card_is_derived_and_listed(research_ws):
    """list_studies carries each notebook's card — origin, channels, flights
    and dates, evidence, tests, outputs, resolution, tags — computed by the
    engine when the notebook is saved; study_finish takes tags."""
    h, ids = research_ws
    sid = _notebook(h, "Cycling at full power")

    def card():
        return next(s for s in _ok(rpc(h, "list_studies", {}))["studies"] if s["study_id"] == sid)["card"]

    c0 = card()
    assert c0 == {"v": 2, "origin": "asked", "channels": [], "flights": 0, "date_span": None,
                  "evidence": {"log_views": 0, "figures": 0, "tables": 0}, "tests": [], "outputs": "current",
                  "resolution": None, "tags": [], "actions": None}
    if _has_bench(h):
        _bench_stack()
        _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {
            "kind": "code", "source": f"r = eis.cycling({_rule_literal()}, 'rpm')\nr.rows"}}))
        _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {
            "kind": "logview", "flight": ids[0], "start_s": 10, "end_s": 70, "channels": ["rpm", "fuel_flow_gph"]}}))
        _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "markdown", "source": "The window."}}))
        c1 = card()
        # Facts the eis library recorded as the cells ran: the test and the channels it and the log view used.
        assert c1["tests"] == ["cycling"] and c1["channels"] == ["rpm", "fuel_flow_gph"]
        assert c1["flights"] == len(ids) and c1["date_span"] == ["2026-01-01", "2026-01-06"]
        assert c1["evidence"]["log_views"] == 1 and c1["evidence"]["tables"] >= 1
        nb = _ok(rpc(h, "load_study", {"study_id": sid}))["notebook"]
        ran = _sm(next(c for c in nb["cells"] if "eis.cycling" in "".join(c["source"])))["ran"]
        assert ran["tests"] == ["cycling"] and ran["channels"] == ["rpm"]
        _ok(rpc(h, "code_run", {"study_id": sid, "source": "import random\nprint(random.random())",
                                "role": "scratch"}))
        _ok(rpc(h, "study_cells_rerun", {"study_id": sid}))
        assert card()["outputs"] == "pending"
        _ok(rpc(h, "study_cells_discard", {"study_id": sid}))
        assert card()["outputs"] == "current"
    bad = rpc(h, "study_finish", {"study_id": sid, "summary": "x", "tags": ["a", "b", "c", "d", "e", "f"]})
    assert not bad["ok"] and bad["error"]["code"] == "BAD_PARAMS" and "at most 5" in bad["error"]["message"]
    fin = _ok(rpc(h, "study_finish", {"study_id": sid, "summary": "RPM cycles.",
                                      "tags": [" governor ", "full  power", "Governor"]}))
    assert fin["study"]["card"]["tags"] == ["governor", "full power"]
    assert card()["resolution"] is None                         # no item: no resolution

    # An owner's question: origin marks, and the resolution study_finish gave it (watch by default).
    _ok(rpc(h, "flight_pin", {"flight_id": ids[1], "start_s": 20, "end_s": 40, "channels": ["map_inhg"],
                              "note": "a dip", "question": {"title": "MAP dips"}}))
    qid = _ok(rpc(h, "pins_list", {}))["questions"][0]["id"]
    q_sid = _ok(rpc(h, "study_create", {"name": "MAP dips", "question_id": qid}))["study_id"]
    row = next(s for s in _ok(rpc(h, "list_studies", {}))["studies"] if s["study_id"] == q_sid)
    assert row["card"]["origin"] == "marks"
    if _has_bench(h):
        assert row["card"]["channels"] == ["map_inhg"] and row["card"]["evidence"]["log_views"] == 1
        assert row["card"]["date_span"] == ["2026-01-02", "2026-01-02"]
    fin = _ok(rpc(h, "study_finish", {"study_id": q_sid, "summary": "A dip.", "question": qid}))
    assert fin["study"]["card"]["resolution"] == "watch"
    # A follow-up reopens it: no resolution shown until it is finished again.
    _ok(rpc(h, "study_cells_append", {"study_id": q_sid, "cell": {"kind": "markdown", "source": "## Follow-up"}}))
    assert next(s for s in _ok(rpc(h, "list_studies", {}))["studies"] if s["study_id"] == q_sid)["card"]["resolution"] is None
    fin = _ok(rpc(h, "study_finish", {"study_id": q_sid, "summary": "Acted.", "resolution": "acted",
                                      "changed": "Resolved as acted."}))
    assert fin["study"]["card"]["resolution"] == "acted" and fin["study"]["card"]["tags"] == []


def test_spec16_5_5_an_older_notebook_gets_its_card_on_first_load_and_on_import(research_ws, isolated_packaged_home):
    import io
    import zipfile
    h, ids = research_ws
    if isinstance(h, NodeHost):
        pytest.skip("rewrites the notebook straight in the workspace folder")
    sid = _notebook(h, "Older")
    ws_dir = next(p.parent for p in (isolated_packaged_home / "workspaces").glob("*/manifest.json"))
    p = ws_dir / "studies" / sid / "notebook.ipynb"
    nb = json.loads(p.read_text())
    del nb["metadata"]["slingology"]["card"]
    nb["cells"].append({"id": "c9", "cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
                        "source": "r = eis.coupling('full_power')\nr"})      # a cell from before ran.tests existed
    nb["cells"][-1]["outputs"] = []
    nb["metadata"]["slingology"]["updated"] = "2026-01-02T03:04:05+00:00"
    p.write_text(json.dumps(nb))
    row = next(s for s in _ok(rpc(h, "list_studies", {}))["studies"] if s["study_id"] == sid)
    assert row["card"]["v"] == 2 and row["card"]["tests"] == ["coupling"] and row["card"]["origin"] == "asked"
    assert row["updated"] == "2026-01-02T03:04:05+00:00"      # filling in the card isn't an edit: newest-first holds
    assert "card" in json.loads(p.read_text())["metadata"]["slingology"]       # stored, not recomputed per listing
    # Import: recomputed (origin imported), whatever card the sender's file carried.
    data = _download(h, _ok(rpc(h, "export_study", {"study_id": sid}))["download_url"])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        sent = json.loads(z.read("notebook.ipynb"))
    sent["metadata"]["slingology"]["card"] = {"v": 1, "origin": "asked", "tags": ["forged"]}
    got = _ok(rpc(h, "import_study", {"content_base64": base64.b64encode(json.dumps(sent).encode()).decode(),
                                      "filename": "S.ipynb"}))
    card = got["notebook"]["metadata"]["slingology"]["card"]
    assert card["origin"] == "imported" and card["tags"] == [] and card["tests"] == ["coupling"]


def test_spec14_6_1_a_research_finding_is_the_title_and_one_line(research_ws):
    """Spec 14 v0.20 §6.1 / Spec 16 v1.2: study_finish's `finding` is the
    Journal line, under the notebook's title; without one, the note, else
    the summary's first sentence. The summary is behind the expand."""
    h, _ = research_ws
    sid = _notebook(h, "Oil temperature in cruise")
    summary = "Oil runs 6 °F warmer in cruise since April. It follows OAT; nothing points at the cooler."

    def finding():
        j = _ok(rpc(h, "get_journal", {}))
        e = next(e for e in j["entries"] if e["kind"] == "study_finding")
        return e, next(s for s in j["sections"] if s["key"] == "findings")

    _ok(rpc(h, "study_finish", {"study_id": sid, "summary": summary, "finding": "Oil runs warmer with OAT, not with age.",
                                "journal": True}))
    e, sec = finding()
    assert (e["title"], e["finding"], e["what"]) == ("Oil temperature in cruise", "Oil runs warmer with OAT, not with age.",
                                                     "Oil runs warmer with OAT, not with age.")
    assert e["summary"] == summary and sec["count"] == 1 and sec["total"] == "1 finding"
    _ok(rpc(h, "study_finish", {"study_id": sid, "summary": summary, "note": "shown to the mechanic", "journal": True}))
    assert finding()[0]["finding"] == "shown to the mechanic"
    _ok(rpc(h, "study_finish", {"study_id": sid, "summary": summary, "journal": True}))
    assert finding()[0]["finding"] == "Oil runs 6 °F warmer in cruise since April."
    assert len([e for e in _ok(rpc(h, "get_journal", {}))["entries"] if e["kind"] == "study_finding"]) == 1
    long = "x" * 300
    assert rpc(h, "study_finish", {"study_id": sid, "summary": summary, "finding": long})["error"]["code"] == "BAD_PARAMS"


def test_spec14_6_1_an_older_finding_is_rewritten_from_its_notebook(research_ws, isolated_packaged_home):
    """Entries written before v0.20 carried the whole summary; the next
    Journal read rewrites them from the notebook, without dating them."""
    h, _ = research_ws
    if isinstance(h, NodeHost):
        pytest.skip("rewrites journal.json straight in the workspace folder")
    sid = _notebook(h, "Takeoff oscillation")
    summary = "RPM swings 180 rpm at full power on 94 of 100 slices.\n\nWhat it means: the governor and the boost control."
    _ok(rpc(h, "study_finish", {"study_id": sid, "summary": summary, "journal": True}))
    ws_dir = next(p.parent for p in (isolated_packaged_home / "workspaces").glob("*/manifest.json"))
    store = json.loads((ws_dir / "journal.json").read_text())
    e = next(e for e in store["entries"] if e["kind"] == "study_finding")
    e["what"], e["updated_at"] = summary, "2026-01-02T03:04:05+00:00"           # as 1.1.0 wrote it
    (ws_dir / "journal.json").write_text(json.dumps(store))
    got = next(x for x in _ok(rpc(h, "get_journal", {}))["entries"] if x["kind"] == "study_finding")
    assert got["what"] == got["finding"] == "RPM swings 180 rpm at full power on 94 of 100 slices."
    assert got["title"] == "Takeoff oscillation" and got["updated_at"] == "2026-01-02T03:04:05+00:00"
    assert next(x for x in json.loads((ws_dir / "journal.json").read_text())["entries"]
                if x["kind"] == "study_finding")["what"] == got["what"]                 # rewritten, once


def test_spec03_v037_the_owner_sets_a_notebooks_tags(research_ws):
    """study_set_tags (page-only): the owner's tags and Claude's are one list,
    on the card at once; the notebook's date is kept."""
    h, _ = research_ws
    sid = _notebook(h, "Tags")
    _ok(rpc(h, "study_finish", {"study_id": sid, "summary": "Done.", "tags": ["governor"]}))

    def row():
        return next(s for s in _ok(rpc(h, "list_studies", {}))["studies"] if s["study_id"] == sid)

    before = row()["updated"]
    out = _ok(rpc(h, "study_set_tags", {"study_id": sid, "tags": ["governor", "takeoff"]}))
    assert out["study"]["card"]["tags"] == ["governor", "takeoff"]
    assert row()["card"]["tags"] == ["governor", "takeoff"] and row()["updated"] == before
    assert _ok(rpc(h, "study_set_tags", {"study_id": sid, "tags": []}))["study"]["card"]["tags"] == []
    assert rpc(h, "study_set_tags", {"study_id": sid, "tags": list("abcdef")})["error"]["code"] == "BAD_PARAMS"


def test_spec14_6_1_the_summarys_first_sentence():
    """Without a finding or a note, the Journal line is the summary's first
    sentence — not cut inside a citation's brackets or at an abbreviation."""
    from slingology_eis.investigations.ipynb import first_sentence as f
    assert f("Found: against the OM's values (OM 916 i A/C24 Ed. 0 Rev. 1, p. 30: 29–72.5 psi) the logs stay inside. "
             "What it means: nothing.") == "Found: against the OM's values (OM 916 i A/C24 Ed. 0 Rev. 1, p. 30: 29–72.5 psi) the logs stay inside."
    assert f("RPM swings 180 rpm.\n\nWhat it means.") == "RPM swings 180 rpm."
    assert f("Peaks e.g. at 5,820 rpm stay brief. More.") == "Peaks e.g. at 5,820 rpm stay brief."
    assert f("## Found: yes. Then") == "Found: yes." and f("No full stop") == "No full stop" and f(None) == ""
