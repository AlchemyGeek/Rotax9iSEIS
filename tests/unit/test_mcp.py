"""
Spec 16 §4.1–§4.2: the MCP server, a façade over the host.

- Parity: each tool's result equals its operation's JSON — fetched
  independently through the host — after the tool's documented trim
  (investigations/mcp_tools.py), and the tool calls exactly the
  operations it declares.
- Every result carries the engine version and the workspace id; writing
  tools are annotated as such; with no workspace every tool answers
  "no workspace yet".
- The stdio transport (a real subprocess), and acceptance 8: every tool
  runs from the CLI with byte-identical JSON.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from slingology_eis import __version__, serialize
from slingology_eis.investigations import mcp_server as M
from slingology_eis.investigations import mcp_tools as T
from tests.unit.test_research_ops import FULL_POWER, FP_START, _import, _ok
from tests.unit.test_server import InProcess, isolated_packaged_home, rpc  # noqa: F401 — fixture

WRITING = {"code_run", "study_create", "cell_append", "study_rerun", "study_accept", "study_discard", "study_finish",
           "inbox_resolve", "workspace_use"}
TOOL_COUNT = 31


@pytest.fixture
def ws(isolated_packaged_home):
    h = InProcess()
    _ok(rpc(h, "create_workspace", {"name": "MCP", "engine_model": "916iS"}))
    ids = [_import(h, f"2026-01-0{n}") for n in range(1, 8)]
    docs = isolated_packaged_home.parent / "mcp-docs"
    docs.mkdir(exist_ok=True)
    (docs / "om.md").write_text("# Engine\n\n## Boost\n\nFive minutes.\n")
    _ok(rpc(h, "aircraft_set", {"aircraft": {"documents_dirs": [str(docs)]}}))
    sid = _ok(rpc(h, "save_study", {"study": {"name": "S", "slice_rules": [FULL_POWER],
                                              "tests": [{"test_id": "cycling", "channels": ["rpm"]}]}}))["study_id"]
    _ok(rpc(h, "run_study", {"study_id": sid}))
    _ok(rpc(h, "inbox_scan", {}))
    ws_id = _ok(rpc(h, "get_active_workspace", {}))["registry_entry"]["id"]
    return h, ids, sid, ws_id, isolated_packaged_home


def _norm(x):
    return json.loads(serialize.dumps(x))


def _recording(server):
    seen = []

    def call(op, params):
        out = server.call_op(op, params)
        seen.append((op, json.loads(json.dumps(params))))
        return out
    return call, seen


def _tool(server, name, args, error=False):
    """Run a tool with a recording `call`; returns (result, the (op, params) it made)
    — or, with error=True, (the error text, the calls)."""
    call, seen = _recording(server)
    out = T.call_tool(name, args, call, engine_version=__version__, workspace_id=server._refresh())
    if error:
        assert out["isError"], out
        return out["content"][0]["text"], seen
    assert not out["isError"], out["content"][0]["text"]
    body = out["structuredContent"]
    assert body["engine_version"] == __version__ and body["workspace_id"] == server._refresh()
    assert json.loads(out["content"][0]["text"]) == body
    return body["result"], seen


def _read_cases(ids, sid):
    fp = [FULL_POWER]
    return [
        ("guide", {}, None),
        ("flights_list", {"date_from": "2026-01-02", "limit": 3, "offset": 1}, T.shape_flights),
        ("flights_find", {"description": "January 3"}, None),
        ("flight_get", {"flight_id": ids[0]}, T.shape_flight),
        ("series_get", {"flight_id": ids[0], "channels": ["rpm", "map_inhg"], "start_s": FP_START, "end_s": FP_START + 60},
         None),
        ("series_get", {"flight_id": ids[0], "channels": ["rpm"], "start_s": 0, "end_s": 750}, None),
        ("fleet_metrics", {"limit": 4}, T.shape_fleet_metrics),
        ("trends_summary", {}, T.shape_trends),
        ("presets_list", {}, None),
        ("slices_build", {"slice_rules": fp, "channels": ["rpm"], "limit": 3}, T.shape_slices),
        ("samples_get", {"slice_rules": fp, "channels": ["rpm"], "flights": ids[:2]}, T.shape_samples),
        ("question_run", {"test_id": "cycling", "slice_rules": fp, "channels": ["rpm"], "limit": 2}, T.shape_question),
        ("signal_analyze", {"flight_id": ids[0], "start_s": FP_START, "end_s": FP_START + 60}, T.shape_signal),
        ("rows_compare", {"slice_rules": fp, "channels": ["rpm"], "limit": 2}, T.shape_compare),
        ("profile_get", {}, None),
        ("aircraft_get", {}, None),
        ("documents_list", {}, None),
        ("document_read", {"name": "om.md", "page": 2}, None),
        ("journal_list", {}, T.shape_journal),
        ("studies_list", {}, None),
        ("study_read", {"study_id": sid}, T.shape_study),
        ("inbox_list", {}, None),
    ]


def test_every_read_tool_is_its_operation_trimmed(ws):
    h, ids, sid, _ws_id, _home = ws
    server = M.Server()
    cases = _read_cases(ids, sid)
    assert {c[0] for c in cases} | WRITING | set(T.SESSION_TOOLS) == set(T.BY_NAME)
    for name, args, shape in cases:
        got, seen = _tool(server, name, args)
        assert tuple(op for op, _ in seen) == T.BY_NAME[name].ops, name
        (op, params), = seen
        raw = _ok(rpc(h, op, params))            # the operation's JSON, fetched independently
        if name == "series_get":
            expected = T.shape_series(args, raw, params)
        else:
            expected = shape(args, raw) if shape else raw
        assert got == _norm(T.local_only(expected)), name       # §4.7: local times only
        assert "start_utc" not in json.dumps(got), name
    # §4.7: slices and windows carry the local time with the zone and the offset into the flight.
    sl, _ = _tool(server, "slices_build", {"slice_rules": [FULL_POWER], "channels": ["rpm"], "limit": 2})
    assert all(s["when"].endswith("into the flight)") and "start_time" not in s["context"] for s in sl["slices"]), sl
    q, _ = _tool(server, "question_run", {"test_id": "cycling", "slice_rules": [FULL_POWER], "channels": ["rpm"]})
    assert "start_local" in q["columns"] and all("start_local" in r and "when" in r for r in q["rows"])
    sig, _ = _tool(server, "signal_analyze", {"flight_id": ids[0], "start_s": FP_START, "end_s": FP_START + 60})
    assert sig["window"]["when"].endswith("into the flight)")
    # Spec 16 §3.2 F1/F4: the shorthand split and skip_onset_s reach the operation as given.
    sk, seen = _tool(server, "signal_analyze", {"flight_id": ids[0], "start_s": FP_START - 15, "end_s": FP_START + 60,
                                                "skip_onset_s": 16, "strips": False})
    assert seen[0][1]["skip_onset_s"] == 16 and sk["window"]["skip_onset_s"] == 16 and sk["window"]["caveats"]
    err, _ = _tool(server, "question_run", {"test_id": "groups", "slice_rules": [FULL_POWER],
                                            "params": {"descriptor": "rpm.swing", "split": "colour"}}, error=True)
    assert err.startswith("BAD_PARAMS") and all(f in err for f in ("source", "date", "da_band", "flights"))
    # every tool that takes more than an id or a page shows an example of its parameters
    formed = [t for t in T.TOOLS if set(t.properties) - {"study_id", "offset", "limit"}]
    assert [t.name for t in formed if "xample" not in t.description] == []


def test_caps_refuse_and_say_why(ws):
    h, ids, _sid, ws_id, _home = ws
    server = M.Server()
    r = server.call_tool("series_get", {"flight_id": ids[0], "channels": ["rpm"]})
    assert r["isError"] and "start_s and end_s" in r["content"][0]["text"]
    r = server.call_tool("series_get", {"flight_id": ids[0], "channels": [f"c{i}" for i in range(7)], "start_s": 0, "end_s": 9})
    assert r["isError"] and "At most 6 channels" in r["content"][0]["text"]
    wide = server.call_tool("series_get", {"flight_id": ids[0], "channels": ["rpm"], "start_s": 0, "end_s": 750})
    res = wide["structuredContent"]["result"]
    assert res["decimated"] and len(res["channels"]["rpm"]["t_s"]) <= T.SERIES_MAX_POINTS
    r = server.call_tool("samples_get", {"slice_rules": [{"rule_id": "cruise", "min_duration_s": 15, "merge_gap_s": 3,
                                                          "conditions": [{"channel": "rpm", "op": ">=", "value": 4900}]}],
                                         "channels": ["rpm", "map_inhg"]})
    assert r["isError"] and "the cap is 6000" in r["content"][0]["text"]
    page = server.call_tool("flights_list", {"limit": 500})["structuredContent"]["result"]
    assert len(page["flights"]) <= T.PAGE_ROWS
    r = server.call_tool("flight_get", {})
    assert r["isError"] and "needs flight_id" in r["content"][0]["text"]
    r = server.call_tool("flight_get", {"flight_id": "nope"})
    assert r["isError"] and r["content"][0]["text"].startswith("NOT_FOUND")


def test_writing_tools(ws):
    pytest.importorskip("matplotlib")
    h, ids, _sid, _ws_id, _home = ws
    server = M.Server()
    made, seen = _tool(server, "study_create", {"name": "Why", "question": "Why does rpm cycle?"})
    assert [op for op, _ in seen] == ["study_create"]
    st = made["study_id"]
    app, _ = _tool(server, "cell_append", {"study_id": st, "kind": "code",
                                           "source": "r = eis.cycling('full_power', 'rpm')\nprint(r.finding)"})
    tool_finding = _tool(server, "question_run", {"test_id": "cycling", "slice_rules": ["full_power"],
                                                  "channels": ["rpm"]})[0]["finding"]
    assert app["outputs"][0]["text"].strip() == tool_finding        # acceptance 12
    raw_seen = []

    def call(op, params):
        out = server.call_op(op, params)
        raw_seen.append(out)
        return out
    out = T.call_tool("code_run", {"study_id": st, "source": "import matplotlib.pyplot as plt\n"
                                   "fig, ax = plt.subplots(); ax.plot([1, 2]); print('hi' * 5000)"},
                      call, engine_version=__version__, workspace_id=server._refresh())
    res = out["structuredContent"]["result"]
    assert res == _norm(T.shape_code_run({}, raw_seen[0]))
    assert res["status"] == "ok" and res["outputs"][0]["clipped"] and len(res["outputs"][0]["text"]) < 8100
    images = [c for c in out["content"] if c["type"] == "image"]
    assert len(images) == 1 and images[0]["mimeType"] == "image/png"
    stored = _ok(rpc(h, "load_study", {"study_id": st}))["notebook"]["cells"][2]
    assert len(stored["outputs"][0]["text"]) == 10001          # the notebook keeps it whole (with the newline)
    refused, _ = _tool(server, "study_finish", {"study_id": st, "summary": "x"}, error=True)
    assert "FLOOR_RULE" in refused and stored["id"] in refused
    _tool(server, "cell_append", {"study_id": st, "kind": "markdown", "source": "The figure above is a line."})
    rr, _ = _tool(server, "study_rerun", {"study_id": st})
    assert rr["study"]["pending"] == 0 and all(c["identical"] for c in rr["cells"])
    assert _tool(server, "study_accept", {"study_id": st})[0]["cells"] == []
    read, _ = _tool(server, "study_read", {"study_id": st})
    assert [c["kind"] for c in read["cells"]] == ["markdown", "code", "code", "markdown"]
    assert read["cells"][2]["outputs"][-1] == {"text": "<Figure>", "figure": True}
    cand = _ok(rpc(h, "inbox_list", {}))["candidates"]
    fin, _ = _tool(server, "study_finish", {"study_id": st, "summary": "It cycles.", "journal": True,
                                            **({"inbox_candidate": cand[0]["id"], "resolution": "watch"} if cand else {})})
    assert fin["journal_entry"]["kind"] == "study_finding"
    if cand:
        assert fin["inbox_candidate"]["status"] == "watch"
        res, _ = _tool(server, "inbox_resolve", {"candidate_id": cand[0]["id"], "status": "nothing-here"})
        assert res["candidate"]["status"] == "nothing-here"


def test_annotations_mark_writing_tools():
    for t in T.TOOLS:
        a = t.definition()["annotations"]
        assert a["readOnlyHint"] is (t.name not in WRITING), t.name
        assert a["openWorldHint"] is False and a["destructiveHint"] is False
        assert t.definition()["inputSchema"]["type"] == "object"
    assert len(T.TOOLS) == TOOL_COUNT


def test_no_workspace_yet(isolated_packaged_home):
    server = M.Server()
    for t in T.TOOLS:
        r = server.call_tool(t.name, {})
        assert r["isError"] and r["content"][0]["text"] == T.NO_WORKSPACE, t.name
    assert not (isolated_packaged_home / "registry.json").exists()


def test_jsonrpc_methods(ws):
    server = M.Server()
    init = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-06-18", "capabilities": {}}})["result"]
    assert init["protocolVersion"] == "2025-06-18" and init["serverInfo"]["version"] == __version__
    assert init["capabilities"] == {"tools": {"listChanged": False}, "prompts": {"listChanged": False}}
    assert "Call `guide` first" in init["instructions"] and "notebook" in init["instructions"]
    tools = server.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/list"})["result"]["tools"]
    assert tools[0]["name"] == "guide"                                  # D13: listed first
    prompts = server.handle({"jsonrpc": "2.0", "id": 10, "method": "prompts/list"})["result"]["prompts"]
    assert [p["name"] for p in prompts] == ["investigate", "inbox-item", "before-after", "review-new-flights"]
    assert prompts[0]["arguments"] == [{"name": "question", "description": prompts[0]["arguments"][0]["description"],
                                        "required": True}]
    got = server.handle({"jsonrpc": "2.0", "id": 11, "method": "prompts/get",
                         "params": {"name": "investigate", "arguments": {"question": "Does rpm hunt at takeoff?"}}})
    text = got["result"]["messages"][0]["content"]["text"]
    assert "> Does rpm hunt at takeoff?" in text and "Call `guide` first" in text and "{{" not in text
    for p in prompts[1:]:
        args = {a["name"]: "x" for a in p["arguments"]}
        assert server.handle({"jsonrpc": "2.0", "id": 12, "method": "prompts/get",
                              "params": {"name": p["name"], "arguments": args}})["result"]["messages"]
    missing = server.handle({"jsonrpc": "2.0", "id": 13, "method": "prompts/get", "params": {"name": "investigate"}})
    assert missing["error"]["code"] == -32602
    newer = server.handle({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "2099-01-01"}})
    assert newer["result"]["protocolVersion"] == M.LATEST
    assert server.handle({"jsonrpc": "2.0", "id": 3, "method": "server/discover"})["error"]["code"] == -32601
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert server.handle({"jsonrpc": "2.0", "id": 4, "method": "ping"})["result"] == {}
    bad = server.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "rm_rf"}})
    assert bad["error"]["code"] == -32602


def test_stdio_subprocess(ws):
    h, ids, _sid, ws_id, home = ws
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "flight_get",
                                                                           "arguments": {"flight_id": ids[0]}}}]
    env = {**os.environ, "SLINGOLOGY_EIS_HOME": str(home), "PYTHONPATH": str(Path(__file__).resolve().parents[2])}
    p = subprocess.run([sys.executable, "-m", "slingology_eis.cli", "mcp"], input="".join(json.dumps(m) + "\n" for m in msgs),
                       capture_output=True, text=True, env=env, timeout=120)
    lines = [json.loads(x) for x in p.stdout.splitlines()]   # nothing but protocol on stdout
    assert [m["id"] for m in lines] == [1, 2, 3], p.stderr
    assert len(lines[1]["result"]["tools"]) == TOOL_COUNT
    body = lines[2]["result"]["structuredContent"]
    assert body["workspace_id"] == ws_id and body["result"]["flight_id"] == ids[0]


def test_cli_parity_byte_identical(ws, capsys):
    """Acceptance 8: every tool runs from the CLI with byte-identical JSON."""
    from slingology_eis import cli
    h, ids, sid, _ws_id, _home = ws
    server = M.Server()
    for name, args, _shape in _read_cases(ids, sid):
        expected = server.call_tool(name, args)["content"][0]["text"]
        assert cli.main(["mcp", "call", name, json.dumps(args)]) == 0, name
        assert capsys.readouterr().out.rstrip("\n") == expected, name
    # Writing tools run from the CLI too.
    assert cli.main(["mcp", "call", "study_create", json.dumps({"name": "From the CLI"})]) == 0
    made = json.loads(capsys.readouterr().out)["result"]
    assert cli.main(["mcp", "call", "cell_append", json.dumps({"study_id": made["study_id"], "kind": "markdown",
                                                              "source": "x"})]) == 0
    assert cli.main(["mcp", "call", "flight_get", "{}"]) == 1
    assert "needs flight_id" in capsys.readouterr().err
