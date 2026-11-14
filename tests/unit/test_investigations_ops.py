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
    return _ok(rpc(h, "save_study", {"study": {"name": name, "kind": "investigation", "author": "claude",
                                               "question": "Why does rpm cycle at full power?", "cells": []}}))["study_id"]


# ── capabilities ──────────────────────────────────────────────────────────

def test_capabilities(registry_server):
    caps = _ok(rpc(registry_server, "get_capabilities", {}))
    assert caps["features"]["investigations"] is True
    assert caps["features"]["bench"] is _has_bench(registry_server)


# ── code_run (§4.5) ───────────────────────────────────────────────────────

def test_code_run_keeps_a_cell(research_ws):
    h, ids = research_ws
    sid = _notebook(h)
    src = ("df = load_slices(FULL_POWER_RULE, channels=['rpm'])\nprint(len(df), 'slices')\n"
           "fig, ax = plt.subplots(); ax.plot(df['rpm.swing']); df[['flight_id', 'rpm.swing']]")
    src = src.replace("FULL_POWER_RULE", json.dumps(FULL_POWER).replace("false", "False").replace("true", "True"))
    d = rpc(h, "code_run", {"study_id": sid, "source": src})
    if not _has_bench(h):
        assert not d["ok"] and d["error"]["code"] == "NOT_SUPPORTED"
        return
    _bench_stack()
    r = _ok(d)
    cell = r["cell"]
    assert cell["kind"] == "code" and cell["ran"]["status"] == "ok", cell
    kinds = [o["kind"] for o in cell["outputs"]]
    assert kinds == ["text", "table", "figure"], kinds   # figures left open come last
    assert cell["outputs"][0]["text"].strip() == "6 slices"
    assert sorted(cell["ran"]["flights"]) == sorted(ids)
    fig = cell["outputs"][2]["ref"]
    assert fig.startswith("files/fig-") and fig in r["previews"]
    # Replacing the cell: same id, new source, the old figure collected.
    r2 = _ok(rpc(h, "code_run", {"study_id": sid, "cell_id": cell["id"], "source": "1 + 1"}))
    assert r2["cell"]["id"] == cell["id"] and r2["cell"]["outputs"] == [{"kind": "text", "text": "2"}]
    doc = _ok(rpc(h, "load_study", {"study_id": sid}))
    assert [c["id"] for c in doc["cells"]] == [cell["id"]]


def test_code_run_errors_are_outputs(research_ws):
    h, _ids = research_ws
    if not _has_bench(h):
        pytest.skip("no bench under Pyodide")
    _bench_stack()
    sid = _notebook(h)
    cell = _ok(rpc(h, "code_run", {"study_id": sid, "source": "x = 1\n1 / 0"}))["cell"]
    assert cell["ran"]["status"] == "error"
    err = cell["outputs"][-1]
    assert err["kind"] == "error" and err["ename"] == "ZeroDivisionError"
    assert "1 / 0" in err["traceback"] and "cell" in err["traceback"]
    bad = rpc(h, "code_run", {"study_id": sid, "source": "1", "timeout_s": 9999})
    assert not bad["ok"] and bad["error"]["code"] == "BAD_PARAMS"


# ── cells (§5) ────────────────────────────────────────────────────────────

def test_cells_append_rerun_accept_finish(research_ws):
    h, ids = research_ws
    sid = _notebook(h)
    md = _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "markdown", "source": "# Plan"}}))
    assert md["cell"]["kind"] == "markdown"
    q = _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {
        "kind": "question", "test_id": "cycling", "channels": ["rpm"], "slices": {"slice_rules": [FULL_POWER]}}}))
    assert q["cell"]["kind"] == "question" and q["cell"]["test_index"] == 0
    assert q["result"]["finding"].startswith("RPM cycles")
    bad = rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "figure", "ref": "files/none.svg"}})
    assert not bad["ok"]
    re = _ok(rpc(h, "study_cells_rerun", {"study_id": sid}))
    assert re["study"]["tests"][0]["result"]["finding"] == q["result"]["finding"]
    acc = _ok(rpc(h, "study_cells_accept", {"study_id": sid}))
    assert acc["cells"] == []          # nothing was pending: re-run outputs were identical
    fin = _ok(rpc(h, "study_finish", {"study_id": sid, "summary": "RPM cycles at full power.\nIt is the governor.",
                                      "journal": True}))
    assert fin["study"]["status"] == "finished" and fin["journal_entry"]["kind"] == "study_finding"
    assert fin["journal_entry"]["what"] == "RPM cycles at full power."
    j = _ok(rpc(h, "get_journal", {}))
    assert [e["kind"] for e in j["entries"]].count("study_finding") == 1
    listed = _ok(rpc(h, "list_studies", {}))["studies"]
    assert next(s for s in listed if s["study_id"] == sid)["cells"] == 2
    assert not rpc(h, "study_finish", {"study_id": sid, "summary": " "})["ok"]


# ── .eisstudy, read-only import, Run this on my flights, .ipynb (acceptance 5) ──

def test_notebook_round_trip(research_ws):
    h, ids = research_ws
    sid = _notebook(h)
    _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "markdown", "source": "Plan."}}))
    _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {
        "kind": "question", "test_id": "cycling", "channels": ["rpm"], "slices": {"slice_rules": [FULL_POWER]}}}))
    code = None
    if _has_bench(h):
        _bench_stack()
        code = _ok(rpc(h, "code_run", {"study_id": sid, "source": (
            "import matplotlib.pyplot as plt\nfig, ax = plt.subplots(); ax.plot([1, 2, 3]); "
            "print(len(flights())); info = flight_info(flights().flight_id[0])")}))["cell"]
        assert code["ran"]["flights"], code
    # Re-run on the same workspace: identical outputs, nothing pending.
    re = _ok(rpc(h, "study_cells_rerun", {"study_id": sid}))
    assert not any(c.get("pending_outputs") for c in re["study"]["cells"])
    sent = _ok(rpc(h, "load_study", {"study_id": sid}))

    exp = _ok(rpc(h, "export_study", {"study_id": sid}))
    data = _download(h, exp["download_url"])
    nb = _ok(rpc(h, "export_study", {"study_id": sid, "format": "ipynb"}))
    ipynb = json.loads(_download(h, nb["download_url"]))
    # A title cell (name, question), then one per notebook cell; a question becomes markdown.
    assert ipynb["nbformat"] == 4 and len(ipynb["cells"]) == len(sent["cells"]) + 1
    assert [c["cell_type"] for c in ipynb["cells"]][:3] == ["markdown", "markdown", "markdown"]
    if code is not None:
        assert ipynb["cells"][3]["cell_type"] == "code" and ipynb["cells"][3]["outputs"]

    if code is not None:
        # S5: what leaves the workspace names flights by content fingerprint, never flight_id…
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            sent_doc = json.loads(z.read("study.json"))["study"]
        sent_code = next(c for c in sent_doc["cells"] if c["kind"] == "code")
        assert sent_code["ran"]["flights"] and all(f.startswith("src:") for f in sent_code["ran"]["flights"])
        assert not set(sent_code["ran"]["flights"]) & set(ids)
        nb_code = next(c for c in ipynb["cells"] if c["cell_type"] == "code")
        assert all(f.startswith("src:") for f in nb_code["metadata"]["eis"]["ran"]["flights"])
        # …and an import where the flights are maps them back to ids.
        back = _ok(rpc(h, "import_study", {"content_base64": base64.b64encode(data).decode(), "filename": "S.eisstudy"}))
        back_code = next(c for c in back["study"]["cells"] if c["kind"] == "code")
        assert back_code["ran"]["flights"] == code["ran"]["flights"] and not back_code.get("read_only")
        # The stored study still names them by id.
        assert next(c for c in _ok(rpc(h, "load_study", {"study_id": sid}))["cells"]
                    if c["kind"] == "code")["ran"]["flights"] == code["ran"]["flights"]

    # Another workspace that has none of these flights: read-only per cell.
    _ok(rpc(h, "create_workspace", {"name": "Other", "engine_model": "916iS"}))
    other = _import(h, "2026-02-01")
    got = _ok(rpc(h, "import_study", {"content_base64": base64.b64encode(data).decode(), "filename": "S.eisstudy"}))
    st = got["study"]
    assert got["read_only"] and st["kind"] == "investigation"
    q = next(c for c in st["cells"] if c["kind"] == "question")
    assert q.get("read_only")
    if code is not None:
        c = next(c for c in st["cells"] if c["kind"] == "code")
        assert c.get("read_only") and c["outputs"] == code["outputs"]
        assert all(f.startswith("src:") for f in c["ran"]["flights"])   # not here: kept as fingerprints
        assert c["outputs"][-1]["ref"].startswith("files/")
        # The figure travelled in the .eisstudy's files/: the imported notebook's .ipynb embeds it.
        nb2 = _ok(rpc(h, "export_study", {"study_id": st["study_id"], "format": "ipynb"}))
        code2 = next(x for x in json.loads(_download(h, nb2["download_url"]))["cells"] if x["cell_type"] == "code")
        assert any("image/svg+xml" in (o.get("data") or {}) or "image/png" in (o.get("data") or {})
                   for o in code2["outputs"]), code2["outputs"]
    mine = _ok(rpc(h, "run_study_on_my_flights", {"study_id": st["study_id"]}))
    assert mine["flights"] == [other] and not mine.get("read_only")
    assert mine["tests"][0]["result"]["finding"].endswith("in 1 of 1 slice.")
    if code is not None:
        c = next(c for c in mine["cells"] if c["kind"] == "code")
        assert c.get("ran_elsewhere"), c   # marked, not re-executed


# ── aircraft and documents (§4.4) ─────────────────────────────────────────

def test_aircraft(registry_server):
    h = registry_server
    _ok(rpc(h, "create_workspace", {"name": "A", "engine_model": "916iS"}))
    a = _ok(rpc(h, "aircraft_get", {}))
    assert a["engine_model"] == "916iS" and "propeller" in [f["key"] for f in a["fields"]]
    s = _ok(rpc(h, "aircraft_set", {"aircraft": {"propeller": "Test prop", "prop_controller": "Test ctl"}}))
    assert s["aircraft"]["propeller"] == "Test prop"
    assert _ok(rpc(h, "aircraft_get", {}))["aircraft"]["prop_controller"] == "Test ctl"
    bad = rpc(h, "aircraft_set", {"aircraft": {"registration": "N1"}})
    assert not bad["ok"] and bad["error"]["code"] == "BAD_PARAMS"


def test_documents_paged(registry_server):
    h = registry_server
    _ok(rpc(h, "create_workspace", {"name": "D", "engine_model": "916iS"}))
    md = "# Engine\n\n## Boost\n\n" + "Boost is allowed for five minutes.\n" * 3 + "\n## Idle\n\nIdle rpm.\n"
    add = _ok(rpc(h, "document_add", {"content_base64": base64.b64encode(md.encode()).decode(), "filename": "om.md"}))
    assert add["document"]["name"] == "om.md"
    docs = _ok(rpc(h, "documents_list", {}))["documents"]
    assert [d["name"] for d in docs] == ["om.md"] and docs[0]["pages"] == 3
    p = _ok(rpc(h, "document_read", {"name": "om.md", "page": 2}))
    assert p["pages"][0]["title"] == "Engine › Boost" and "five minutes" in p["pages"][0]["text"]
    f = _ok(rpc(h, "document_read", {"name": "om.md", "find": "idle"}))
    assert [m["page"] for m in f["matches"]] == [3]
    assert not rpc(h, "document_read", {"name": "../registry.json"})["ok"]
    _ok(rpc(h, "document_remove", {"name": "om.md"}))
    assert _ok(rpc(h, "documents_list", {}))["documents"] == []


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
