"""
server.py — the HTTP transport (Spec 04 v0.4 §9.1, Spec 01 §5 path 2).

A small HTTP server exposing the Spec 01 §7 operation envelope over
`POST /rpc`, so the browser UI can call the real engine without Pyodide.
Stdlib only — the spec has "a strong preference for minimal dependencies
to keep installation easy for non-experts."

This module only speaks HTTP: it accepts a request, decodes the envelope
(including base64 log content, an HTTP-only encoding), calls the
transport-neutral host (`host.py`), encodes the reply, and serves the
built UI, uploads and one-shot downloads. Every operation, and every rule
operations share, lives in the host.

Binds to loopback (127.0.0.1) only; the "any other interface needs an
access token" case (Spec 04 §9.2, Docker/NAS) isn't implemented yet.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import shutil
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

from . import host as _host
from . import serialize as _json_serialize
from .cli import resolve_logs_dir
from .resources import web_dist
from .log_sources import DISK

# Kept importable from here for callers that predate the host split.
RpcError = _host.RpcError


def _decode_content(params: Any) -> Any:
    """Base64 is how HTTP carries bytes in JSON; the host takes bytes.
    `content_base64` (an operation's log or export) and each
    `files[].content_base64` (import_files) become `content`."""
    if not isinstance(params, dict):
        return params
    out = dict(params)
    if "content_base64" in out:
        out["content"] = base64.b64decode(out.pop("content_base64"))
    if isinstance(out.get("files"), list):
        out["files"] = [_decode_content(f) for f in out["files"]]
    return out


def _http_context(logs_dir: Optional[Path], workspace_arg: Optional[str]) -> dict:
    """The host context with this transport's progress store and download
    registry. ctx is one shared dict for the server's lifetime, so a poll
    on another thread sees a scan thread's updates with no extra plumbing."""
    ctx: dict = {"scan_progress": {"active": False}, "data_location_progress": {"active": False}, "downloads": {}}

    def emit_progress(stream: str, update: dict) -> None:
        # Where get_scan_progress / get_data_location_progress read it.
        ctx[f"{stream}_progress"] = update

    def deliver_file(path: Path, filename: str) -> str:
        token = uuid.uuid4().hex
        ctx["downloads"][token] = Path(path)
        return f"/download/{token}"

    # A server's folders are on its own disk, added by path.
    ctx.update(_host.new_context(log_sources=DISK, host="server", logs_dir=logs_dir, workspace_arg=workspace_arg,
                                 emit_progress=emit_progress, deliver_file=deliver_file))
    return ctx


def _make_handler(ctx: dict, ui_dist: Optional[Path], quiet: bool):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            if not quiet:
                sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _send_json(self, body: dict) -> None:
            payload = _json_serialize.dumps(body).encode("utf-8")
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_OPTIONS(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler's naming)
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            if self.path.startswith("/upload"):
                # Spec 02 v0.14: a file chosen in the browser (an export
                # zip can be hundreds of MB), streamed to a private temp
                # file; the RPC ops then refer to it by upload_id.
                from urllib.parse import parse_qs, urlparse
                filename = (parse_qs(urlparse(self.path).query).get("filename") or ["upload"])[0]
                length = int(self.headers.get("Content-Length", 0))
                upload_id = uuid.uuid4().hex
                folder = _host.scratch_dir(ctx) / "uploads" / upload_id
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / (Path(filename).name or "upload")
                remaining = length
                with open(target, "wb") as out:
                    while remaining > 0:
                        chunk = self.rfile.read(min(1 << 20, remaining))
                        if not chunk:
                            break
                        out.write(chunk)
                        remaining -= len(chunk)
                ctx["uploads"][upload_id] = {"path": target, "filename": target.name}
                self._send_json({"ok": True, "result": {"upload_id": upload_id, "filename": target.name,
                                                        "size": length - remaining}})
                return
            if self.path != "/rpc":
                self.send_response(404)
                self._cors()
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                envelope = json.loads(self.rfile.read(length))
                if isinstance(envelope, dict) and "params" in envelope:
                    envelope = {**envelope, "params": _decode_content(envelope["params"])}
            except Exception as e:  # noqa: BLE001 — envelope must always respond, never crash the connection
                self._send_json({"request_id": None, "ok": False,
                                 "error": {"code": "INTERNAL_ERROR", "message": f"{type(e).__name__}: {e}"}})
                return
            self._send_json(_host.reply(envelope, ctx))

        def do_GET(self) -> None:  # noqa: N802
            if self.path.split("?")[0] == "/runtime.json":
                # Spec 04 §9.5: the page asks first which host it runs on.
                # This server answers for itself, whatever a static build
                # left in web/dist.
                payload = b'{"host": "server"}\n'
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if self.path.startswith("/download/"):
                # A workspace export (Spec 02 §7.2), served once.
                token = self.path[len("/download/"):].split("?")[0]
                f = ctx["downloads"].pop(token, None)
                if f is None or not Path(f).is_file():
                    self.send_response(404)
                    self._cors()
                    self.end_headers()
                    return
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", f'attachment; filename="{Path(f).name}"')
                self.send_header("Content-Length", str(Path(f).stat().st_size))
                self.end_headers()
                with open(f, "rb") as fh:
                    shutil.copyfileobj(fh, self.wfile)
                return
            if ui_dist is None:
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(
                    b"SlingologyEIS local server is running. POST /rpc for the API.\n"
                    b"No built UI found - run `npm run build` in web/, or use `npm run dev` and point it at this server.\n"
                )
                return
            rel = self.path.lstrip("/") or "index.html"
            f = (ui_dist / rel)
            if not f.is_file():
                f = ui_dist / "index.html"  # SPA fallback for client-side routes
            self.send_response(200)
            self._cors()
            # Without this, every asset (including the built JS entry
            # point, loaded as <script type="module">) came back with no
            # Content-Type at all — Chrome's strict MIME-type enforcement
            # for module scripts silently refuses to execute an untyped
            # response, so the app never mounted past a blank #root, with
            # no console error to point at why.
            content_type, _ = mimetypes.guess_type(str(f))
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.end_headers()
            self.wfile.write(f.read_bytes())

    return Handler


def _logs_dir_or_none(logs_dir: Optional[str]) -> Optional[Path]:
    """The server's folders come from the workspace; a default --logs only
    exists in a checkout or a legacy install. Without one (a fresh
    `pip install`), the server starts all the same (BACKLOG P3)."""
    from .cli import CliUsageError
    try:
        return resolve_logs_dir(logs_dir)
    except CliUsageError:
        if logs_dir:
            raise
        return None


def build_server(logs_dir: Optional[str], workspace_dir: Optional[str], port: int, quiet: bool) -> ThreadingHTTPServer:
    """
    Construct (but don't run) the server — split out from run_server() so
    tests can start it in a background thread and call .shutdown()
    cleanly, instead of blocking forever on serve_forever() in-process.
    """
    ctx = _http_context(_logs_dir_or_none(logs_dir), workspace_dir)

    # A checkout's web/dist (developers), else the UI the wheel carries.
    ui_dist = web_dist()

    httpd = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(ctx, ui_dist, quiet))
    httpd.slingology_workspace_dir = ctx["workspace_dir"]  # type: ignore[attr-defined]
    httpd.slingology_data_location_missing = ctx.get("data_location_missing")  # type: ignore[attr-defined]
    return httpd


def run_server(logs_dir: Optional[str], workspace_dir: Optional[str], port: int, quiet: bool) -> None:
    httpd = build_server(logs_dir, workspace_dir, port, quiet)
    if not quiet:
        print(f"SlingologyEIS local server: http://127.0.0.1:{httpd.server_port}/  "
              f"(workspace: {httpd.slingology_workspace_dir})", file=sys.stderr)  # type: ignore[attr-defined]
        print("POST /rpc for the API. Ctrl-C to stop.", file=sys.stderr)
        if httpd.slingology_data_location_missing:  # type: ignore[attr-defined]
            print(f"Data location {httpd.slingology_data_location_missing} can't be reached; "  # type: ignore[attr-defined]
                  "the app will ask you to reconnect it or choose another.", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
