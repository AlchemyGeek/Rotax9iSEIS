"""
`slingology-eis mcp` (Spec 16 §4.1): the MCP server over stdio — the
host's third front door, in the engine's own process.

The transport is newline-delimited JSON-RPC 2.0 on stdin/stdout, written
by hand (no SDK dependency): `initialize`, `ping`, `tools/list`,
`tools/call` and the `notifications/*` a client sends. Anything else is
-32601, which is also how a client that tries a newer handshake first
learns to fall back to `initialize`.

stdout is the protocol channel and nothing else may write to it: at start
the real stdout is duplicated for the protocol and fd 1 is pointed at
stderr, so a stray print in the engine (or a library) lands on stderr.

The data root is re-opened before every call, so a workspace the user
switches to or creates in the EIS pages is the one the next tool sees.
With `--serve`, the web server runs on a thread of the same process
(Spec 16 §7's extension shape).
"""
from __future__ import annotations

import json
import os
import sys
import threading
from typing import Any, Optional

from .. import __version__
from . import mcp_tools as T

SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
LATEST = SUPPORTED_VERSIONS[0]

INSTRUCTIONS = (
    "SlingologyEIS: the owner's engine logs (Rotax 9-series, Garmin G3X/AXIS), analysed by the EIS engine on this "
    "computer. Start with inbox_list (what the detectors raised) or flights_list / trends_summary. Numbers come "
    "from the engine's operations; quote them with the OM references they carry. For an investigation: "
    "study_create, then question_run / signal_analyze / code_run (each kept as a cell), then study_finish with "
    "what was found, what it means and what to do. series_get and samples_get are capped — use a window, or "
    "code_run's load_flight / load_slice_samples for whole flights. Tools never change logs, limits, filters or "
    "settings."
)


class Server:
    def __init__(self, *, workspace_arg: Optional[str] = None, ctx: Optional[dict] = None):
        from .. import host as H
        from ..log_sources import DISK
        self.H = H
        self.workspace_arg = workspace_arg
        self.ctx = ctx if ctx is not None else H.new_context(log_sources=DISK, host="server",
                                                             workspace_arg=workspace_arg)
        self.lock = threading.Lock()

    # ── the façade's view of the host ──
    def call_op(self, op: str, params: dict) -> Any:
        try:
            return self.H.dispatch(op, params, self.ctx)
        except self.H.RpcError as e:
            raise T.ToolOpError(e.code, e.message)

    def _refresh(self) -> Optional[str]:
        self.H._open_data_root(self.ctx, self.workspace_arg)
        if self.ctx.get("data_location_missing"):
            return None
        return self.ctx.get("active_workspace_id")

    def call_tool(self, name: str, args: dict) -> dict:
        with self.lock:
            ws_id = self._refresh()
            return T.call_tool(name, args or {}, self.call_op, engine_version=__version__, workspace_id=ws_id)

    # ── JSON-RPC ──
    def handle(self, msg: dict) -> Optional[dict]:
        mid, method = msg.get("id"), msg.get("method")
        if method is None:
            return None  # a response to something we never send
        if mid is None:
            return None  # a notification: initialized, cancelled, …
        try:
            result = self._method(method, msg.get("params") or {})
        except _RpcFail as e:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": e.code, "message": e.message}}
        except Exception as e:  # noqa: BLE001 — a request always answers
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def _method(self, method: str, params: dict) -> Any:
        if method == "initialize":
            asked = params.get("protocolVersion")
            return {"protocolVersion": asked if asked in SUPPORTED_VERSIONS else LATEST,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "slingology-eis", "title": "SlingologyEIS", "version": __version__},
                    "instructions": INSTRUCTIONS}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [t.definition() for t in T.TOOLS]}
        if method == "tools/call":
            name = params.get("name")
            if name not in T.BY_NAME:
                raise _RpcFail(-32602, f"Unknown tool: {name}")
            return self.call_tool(name, params.get("arguments") or {})
        raise _RpcFail(-32601, f"Method not found: {method}")


class _RpcFail(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def serve_stdio(server: Server, stdin=None, out=None) -> None:
    """Read requests line by line until EOF; one response line per request."""
    stdin = stdin or sys.stdin
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            if isinstance(msg, list):  # a batch (2025-03-26): answer each request
                replies = [r for r in (server.handle(m) for m in msg if isinstance(m, dict)) if r]
                reply = replies or None
            elif isinstance(msg, dict):
                reply = server.handle(msg)
            else:
                reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
        if reply is not None:
            out.write(json.dumps(reply, ensure_ascii=False, allow_nan=False) + "\n")
            out.flush()


def main(*, workspace_arg: Optional[str] = None, serve: bool = False, port: int = 8420) -> int:
    # The protocol owns the real stdout; everything else written to fd 1 goes to stderr.
    proto = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    if serve:
        from ..server import run_server
        threading.Thread(target=run_server, args=(None, workspace_arg, port, True), daemon=True,
                         name="eis-http").start()
    server = Server(workspace_arg=workspace_arg)
    serve_stdio(server, sys.stdin, proto)
    return 0
