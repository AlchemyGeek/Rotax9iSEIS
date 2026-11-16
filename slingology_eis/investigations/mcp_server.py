"""
`slingology-eis mcp` (Spec 16 §4.1): the MCP server over stdio — the
host's third front door, in the engine's own process.

The transport is newline-delimited JSON-RPC 2.0 on stdin/stdout, written
by hand (no SDK dependency): `initialize`, `ping`, `tools/list`,
`tools/call`, `prompts/list`, `prompts/get` (§4.6's four prompts, from
investigations/prompts/*.md) and the `notifications/*` a client sends. Anything else is
-32601, which is also how a client that tries a newer handshake first
learns to fall back to `initialize`.

stdout is the protocol channel and nothing else may write to it: at start
the real stdout is duplicated for the protocol and fd 1 is pointed at
stderr, so a stray print in the engine (or a library) lands on stderr.

The data root is re-opened before every call, so a workspace the user
switches to or creates in the EIS pages is the one the next tool sees.
With `--serve`, the web server runs on a thread of the same process
(Spec 16 §7's extension shape); if its port is taken (another EIS already
serves the pages) the MCP server carries on without it. `--log-folder`
(repeatable; the extension's configuration) links folders to the workspace
the tools open, once it exists. With `--log-file` the server's stderr is
also written to `cache/mcp.log` under the data root.
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
    "computer. Call `guide` first, in every conversation: it gives the method, every tool's parameters with "
    "examples, the notebook rules, the aircraft record with the owner's notes, the documents and the workspace in "
    "use. Numbers come from the engine's tools; quote them with the OM references they carry, and never use a "
    "verdict word (normal, excessive, fault…) without its reference. Times are the flight's local time. Put "
    "findings in a notebook (study_create, cell_append, code_run, study_finish) — the owner reads and re-runs "
    "the notebook, not this conversation. Tools never change logs, limits, filters or settings."
)


class Server:
    """One MCP connection's server. Which workspace the tools see (D10):
    `workspace_use` for this conversation, else `--workspace`, else the
    aircraft's (`--aircraft`, else the registry's only aircraft, else the
    one most recently opened) most recently opened workspace."""

    def __init__(self, *, workspace_arg: Optional[str] = None, aircraft_arg: Optional[str] = None,
                 ctx: Optional[dict] = None):
        from .. import host as H
        from ..log_sources import DISK
        self.H = H
        self.workspace_arg = workspace_arg
        self.aircraft_arg = aircraft_arg
        self.use_workspace: Optional[str] = None
        self.aircraft_error: Optional[str] = None
        self.ctx = ctx if ctx is not None else H.new_context(log_sources=DISK, host="server",
                                                             workspace_arg=workspace_arg)
        self.lock = threading.Lock()
        self.pending_folders: list[str] = []
        self._linked: set[str] = set()

    # ── the façade's view of the host ──
    def call_op(self, op: str, params: dict) -> Any:
        try:
            return self.H.dispatch(op, params, self.ctx)
        except self.H.RpcError as e:
            raise T.ToolOpError(e.code, e.message)

    def _registry(self):
        from .. import workspace as ws
        from .. import data_location
        loc = data_location.resolve()
        if loc.missing:
            return None, None, []
        return loc.root, ws, ws.load_registry(loc.root / "registry.json").workspaces

    def aircraft(self) -> Optional[dict]:
        """The aircraft this server opens (D10), or None."""
        from .. import aircraft as AC
        root, _ws, entries = self._registry()
        if root is None:
            return None
        AC.ensure(root)
        self.aircraft_error = None
        if self.aircraft_arg:
            try:
                return AC.resolve(root, self.aircraft_arg)
            except AC.AircraftError as e:
                self.aircraft_error = e.message
                return None
        every = AC.list_aircraft(root)
        if len(every) <= 1:
            return every[0] if every else None
        recent = sorted(entries, key=lambda e: e.last_opened_at or "", reverse=True)
        for e in recent:
            a = AC.of_workspace(root, e.id)
            if a is not None:
                return a
        return every[0]

    def choose_workspace(self) -> Optional[str]:
        root, _ws, entries = self._registry()
        if root is None:
            return None
        ids = {e.id for e in entries}
        if self.use_workspace in ids:
            return self.use_workspace
        if self.workspace_arg:
            return self.workspace_arg
        ac = self.aircraft()
        if ac is None:
            return None
        mine = sorted((e for e in entries if e.id in ac["workspaces"]), key=lambda e: e.last_opened_at or "",
                      reverse=True)
        return mine[0].id if mine else None

    def _refresh(self) -> Optional[str]:
        chosen = self.choose_workspace()
        self.H._open_data_root(self.ctx, chosen)
        if self.ctx.get("data_location_missing"):
            return None
        if chosen is None and (self.aircraft_arg or self.aircraft_error):
            return None
        ws_id = self.ctx.get("active_workspace_id")
        if ws_id and self.pending_folders and ws_id not in self._linked:
            self._link_folders(ws_id)
        return ws_id

    def _link_folders(self, ws_id: str) -> None:
        """The extension's configured log folders (§7), linked to the workspace
        the tools open — added, never removed (the pages own removal)."""
        from pathlib import Path
        from .. import workspace as ws
        self._linked.add(ws_id)
        for raw in self.pending_folders:
            folder = Path(raw).expanduser()
            if not folder.is_dir():
                print(f"slingology-eis mcp: log folder {folder} isn't there; not linked", file=sys.stderr)
                continue
            ws.add_log_folder(self.ctx["workspace_dir"], str(folder), self.ctx["registry_path"])

    def call_tool(self, name: str, args: dict) -> dict:
        with self.lock:
            ws_id = self._refresh()
            if name in T.SESSION_TOOLS:
                return T.call_session_tool(name, args or {}, self, engine_version=__version__, workspace_id=ws_id)
            if ws_id is None and self.aircraft_error:
                return T._error(self.aircraft_error)
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
                    "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
                    "serverInfo": {"name": "slingology-eis", "title": "SlingologyEIS", "version": __version__},
                    "instructions": INSTRUCTIONS}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [t.definition() for t in T.TOOLS]}
        if method == "prompts/list":
            from .ops import list_prompts
            return {"prompts": [{k: p[k] for k in ("name", "title", "description", "arguments") if k in p}
                                for p in list_prompts()]}
        if method == "prompts/get":
            from .ops import list_prompts
            p = next((x for x in list_prompts() if x.get("name") == params.get("name")), None)
            if p is None:
                raise _RpcFail(-32602, f"Unknown prompt: {params.get('name')}")
            args = params.get("arguments") or {}
            missing = [a["name"] for a in p.get("arguments") or [] if a.get("required") and not args.get(a["name"])]
            if missing:
                raise _RpcFail(-32602, f"Prompt {p['name']} needs {', '.join(missing)}")
            text = p["text"]
            for a in p.get("arguments") or []:
                text = text.replace("{{" + a["name"] + "}}", str(args.get(a["name"]) or ""))
            return {"description": p.get("description"),
                    "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}
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


class _Tee:
    """stderr to Claude Desktop's MCP log and to the data root's file."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, text: str) -> int:
        for st in self.streams:
            try:
                st.write(text)
                st.flush()
            except (OSError, ValueError):
                pass
        return len(text)

    def flush(self) -> None:
        for st in self.streams:
            try:
                st.flush()
            except (OSError, ValueError):
                pass


LOG_LIMIT = 2_000_000


def _open_log_file():
    """`cache/mcp.log` under the data root (started afresh past 2 MB)."""
    from datetime import datetime, timezone
    from .. import data_location
    loc = data_location.resolve()
    if loc.missing:
        return None
    path = loc.root / "cache" / "mcp.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if path.is_file() and path.stat().st_size > LOG_LIMIT else "a"
        f = open(path, mode, encoding="utf-8", buffering=1)
    except OSError:
        return None
    f.write(f"\n── slingology-eis mcp {__version__} started {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
            f"(data root {loc.root}, {loc.source}) ──\n")
    return f


def _serve_pages(workspace_arg: Optional[str], port: int) -> None:
    from ..server import run_server
    try:
        run_server(None, workspace_arg, port, True)
    except OSError as e:
        print(f"slingology-eis mcp: the pages aren't served from this process — port {port} on 127.0.0.1 is in use "
              f"({e.strerror or e}); another EIS may already be serving them there. The tools work regardless.",
              file=sys.stderr)


def main(*, workspace_arg: Optional[str] = None, aircraft_arg: Optional[str] = None, serve: bool = False,
         port: int = 8420, log_folders: Optional[list[str]] = None, log_file: bool = False) -> int:
    # The protocol owns the real stdout; everything else written to fd 1 goes to stderr.
    proto = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    os.dup2(2, 1)
    if log_file:
        f = _open_log_file()
        if f is not None:
            sys.stderr = _Tee(sys.__stderr__, f)  # type: ignore[assignment]
    sys.stdout = sys.stderr
    print(f"slingology-eis mcp {__version__}: stdio" + (f", pages on 127.0.0.1:{port}" if serve else ""), file=sys.stderr)
    if serve:
        threading.Thread(target=_serve_pages, args=(workspace_arg, port), daemon=True, name="eis-http").start()
    server = Server(workspace_arg=workspace_arg, aircraft_arg=aircraft_arg)
    server.pending_folders = [d for d in (log_folders or []) if d and d.strip()]
    serve_stdio(server, sys.stdin, proto)
    return 0
