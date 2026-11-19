"""
Spec 16 §7 — the Claude Desktop extension: the entry the bundle's manifest
runs (its user configuration as Desktop substitutes it → `slingology-eis
mcp --serve --log-file …`), the configured log folders linked to the
workspace the tools open, the log file under the data root, the pages
served by the same process (and the tools carrying on when the port is
taken), and the manifest scripts/build_extension.py writes.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from slingology_eis.investigations import extension as E
from slingology_eis.investigations import mcp_server as M
from slingology_eis.investigations import mcp_tools as T
from tests.unit.test_mcp import TOOL_COUNT, ws  # noqa: F401 — fixture
from tests.unit.test_server import isolated_packaged_home  # noqa: F401 — fixture

ROOT = Path(__file__).resolve().parents[2]


def test_translate_empty_settings():
    """Unset settings arrive empty or as the placeholder itself: the pages' data root, D10's aircraft, no folders."""
    for empty in ("", "${user_config.data_root}"):
        root, args = E.translate(["--data-root", empty, "--aircraft", empty.replace("data_root", "aircraft"),
                                  "--log-folders", "${user_config.log_folders}"])
        assert root is None
        assert args == ["mcp", "serve", "--serve", "--port", "8420", "--log-file", "--quiet"]
    assert E.translate(["--data-root", "", "--aircraft", "", "--log-folders"])[1][-1] == "--quiet"


def test_translate_settings():
    root, args = E.translate(["--data-root", "~/EIS", "--aircraft", "N117ZS", "--log-folders", "/logs/a", "/logs/b c", ""])
    assert root == "~/EIS"
    assert args[args.index("--aircraft") + 1] == "N117ZS"
    assert [args[i + 1] for i, a in enumerate(args) if a == "--log-folder"] == ["/logs/a", "/logs/b c"]
    with pytest.raises(SystemExit):
        E.translate(["--bogus", "x"])


def test_log_folders_linked_once_the_workspace_is_open(ws, tmp_path):
    _h, _ids, _sid, ws_id, home = ws
    there, missing = tmp_path / "card", tmp_path / "nowhere"
    there.mkdir()
    server = M.Server()
    server.pending_folders = [str(there), str(missing)]
    server.call_tool("flights_list", {"limit": 1})
    server.call_tool("flights_list", {"limit": 1})    # once per workspace, not per call
    manifest = json.loads((home / "workspaces" / ws_id / "manifest.json").read_text())
    paths = [f["path"] for f in manifest["log_folders"]]
    assert paths.count(str(there)) == 1 and str(missing) not in paths


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _run_entry(home: Path, port: int, extra: list[str]) -> tuple[list[dict], str, str]:
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "flights_list", "arguments": {"limit": 1}}},
            {"jsonrpc": "2.0", "id": 3, "method": "prompts/get", "params": {"name": "investigate"}},
            {"jsonrpc": "2.0", "id": 4, "method": "prompts/get", "params": {"name": "nope"}}]
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    env.pop("SLINGOLOGY_EIS_HOME", None)
    p = subprocess.Popen([sys.executable, "-m", "slingology_eis.investigations.extension", "--data-root", str(home),
                          "--aircraft", "", "--port", str(port), *extra],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    for m in msgs:
        p.stdin.write(json.dumps(m) + "\n")
    p.stdin.flush()
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    p.stdin.flush()
    lines = [json.loads(p.stdout.readline()) for _ in msgs]
    page = ""
    for _ in range(40):
        try:
            page = urllib.request.urlopen(f"http://127.0.0.1:{port}/rpc", data=json.dumps(
                {"op": "get_capabilities", "params": {}}).encode(), timeout=2).read().decode()
            break
        except OSError:
            time.sleep(0.25)
    p.stdin.close()
    assert p.wait(timeout=30) == 0           # stops when Desktop closes the connection
    return lines, page, p.stderr.read()


def test_one_process_mcp_and_pages(ws):
    """§7: one process — MCP on stdio and the pages on the port; messages also in cache/mcp.log."""
    _h, ids, _sid, ws_id, home = ws
    port = _free_port()
    lines, page, err = _run_entry(home, port, ["--log-folders"])
    assert [m["id"] for m in lines] == [1, 2, 3, 4]
    assert lines[1]["result"]["structuredContent"]["workspace_id"] == ws_id
    assert json.loads(page)["result"]["host"] == "server"
    log = (home / "cache" / "mcp.log").read_text()
    assert "slingology-eis mcp" in log and f"pages on 127.0.0.1:{port}" in log and str(home) in log


def test_request_log(ws):
    """F15: one line per client message in cache/mcp.log — method, tool or prompt name, outcome; no payloads."""
    _h, _ids, _sid, _ws_id, home = ws
    _run_entry(home, _free_port(), [])
    log = (home / "cache" / "mcp.log").read_text()
    requests = [ln for ln in log.splitlines() if " → " in ln]
    import re
    pid = re.search(r"started \S+ pid (\d+)", log).group(1)
    assert all(f" pid {pid} " in ln for ln in requests)
    tail = [ln.split(f" pid {pid} ", 1)[1] for ln in requests]
    assert re.fullmatch(r"initialize #1 → ok \(\d+ ms\)", tail[0])
    assert re.fullmatch(r"tools/call flights_list #2 → ok \(\d+ ms\)", tail[1])
    assert re.fullmatch(r"prompts/get investigate #3 → ok \(\d+ ms\)", tail[2])
    assert re.fullmatch(r"prompts/get nope #4 → error -32602 \(\d+ ms\)", tail[3])
    assert tail[4] == "notifications/initialized → notification"
    assert "limit" not in log and "Investigate this question" not in log


def test_port_taken_tools_carry_on(ws):
    _h, _ids, _sid, ws_id, home = ws
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    try:
        lines, _page, err = _run_entry(home, s.getsockname()[1], [])
    finally:
        s.close()
    assert lines[1]["result"]["structuredContent"]["workspace_id"] == ws_id
    assert "is in use" in err and "The tools work regardless" in err


def test_bundle_manifest():
    """The manifest build_extension.py writes: what Desktop runs, the configuration it substitutes, the tools."""
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import build_extension as B
    finally:
        sys.path.remove(str(ROOT / "scripts"))
    from slingology_eis import __version__
    m = B.manifest(__version__)
    assert m["manifest_version"] == "0.3" and m["version"] == __version__
    assert m["server"]["type"] == "binary" and m["server"]["entry_point"] == "python/bin/python3"
    cfg = m["server"]["mcp_config"]
    assert cfg["command"] == "${__dirname}/python/bin/python3"
    assert cfg["args"][:3] == ["-I", "-m", "slingology_eis.investigations.extension"]
    used = {a[len("${user_config."):-1] for a in cfg["args"] if a.startswith("${user_config.")}
    assert used == set(m["user_config"]) == {"data_root", "aircraft", "log_folders"}
    assert cfg["args"][-2:] == ["--log-folders", "${user_config.log_folders}"]   # a multiple setting expands last
    assert m["user_config"]["log_folders"]["multiple"] is True
    assert not any(c.get("required") for c in m["user_config"].values())         # first run needs no settings
    assert [t["name"] for t in m["tools"]] == [t.name for t in T.TOOLS] and len(m["tools"]) == TOOL_COUNT
    assert m["compatibility"]["platforms"] == ["darwin"]


def test_bundle_manifest_prompts(ws):
    """F15: Desktop refuses prompts/get for a prompt the manifest doesn't declare. The manifest declares the
    server's prompts in MCPB 0.3's strict shape, and its text, filled the way Desktop fills it, is what the
    server's prompts/get returns."""
    import re
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import build_extension as B
    finally:
        sys.path.remove(str(ROOT / "scripts"))
    from slingology_eis import __version__
    m = B.manifest(__version__)
    assert m["prompts_generated"] is True
    server = M.Server()
    listed = server.handle({"jsonrpc": "2.0", "id": 1, "method": "prompts/list"})["result"]["prompts"]
    assert [p["name"] for p in m["prompts"]] == [p["name"] for p in listed]
    for decl, lp in zip(m["prompts"], listed):
        assert set(decl) == {"name", "description", "arguments", "text"}            # z.strictObject
        assert decl["description"] == lp["description"]
        assert decl["arguments"] == [a["name"] for a in lp["arguments"]]
        assert "{{" not in decl["text"]
        assert set(re.findall(r"\$\{arguments\.(\w+)\}", decl["text"])) == set(decl["arguments"])
        args = {a: f"<{a} value>" for a in decl["arguments"]}
        filled = re.sub(r"\$\{arguments\.(\w+)\}", lambda g: args[g.group(1)], decl["text"])
        got = server.handle({"jsonrpc": "2.0", "id": 2, "method": "prompts/get",
                             "params": {"name": decl["name"], "arguments": args}})
        assert got["result"]["messages"][0]["content"]["text"] == filled
