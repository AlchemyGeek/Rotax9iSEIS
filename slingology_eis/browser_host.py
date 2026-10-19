"""
browser_host.py — the host's Python entry inside a Web Worker (Spec 04
v0.7 §9.2; step 4), and under Pyodide in Node.js for the conformance run
(§9.6 mode 3).

The worker's JavaScript loads Pyodide, mounts the data root, imports this
module and calls `start(bridge, config)` once. `bridge` is a JS object the
worker supplies:

- `request_listing(folder_id)` → Promise of `[ {relative_path, size,
  last_modified} ]`, or null when the page has no access to that folder;
- `request_file(folder_id, relative_path)` → Promise of the bytes, or null
  when the page can't supply them (an "unavailable" answer);
- `release_file(folder_id, relative_path)` — the host is done with them;
- `emit_progress(stream, update_json)` — progress of the operation running;
- `deliver_file(path, filename)` → the token the page will save the file
  under (the worker reads the file from the virtual filesystem and
  transfers its bytes to the page).

Every request then goes through `handle(envelope_json)`, which awaits the
host's `reply_async` — a resumable operation pauses at each file request
until the page answers (D11). The worker syncs the filesystem after each
reply, before posting it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from . import serialize as _json_serialize
from .log_sources import DISK, LogSource, SuppliedLogSource, SuppliedSources

_ctx: Optional[dict] = None
_bridge: Any = None


class PageSources(SuppliedSources):
    """Folders the page holds (Spec 04 §9.3): registered by folder_id; the
    listing and each log's bytes are requested from the page as they're
    needed, one at a time."""

    def __init__(self, bridge, data_root: Optional[Path] = None):
        super().__init__()
        self._bridge = bridge
        self._data_root = None if data_root is None else Path(data_root).resolve()

    def __call__(self, folder) -> LogSource:
        folder_id = getattr(folder, "folder_id", None)
        if not folder_id:
            # A folder by path. Inside the data root (an imported export's
            # own logs/, on OPFS) Python reads it directly; anywhere else
            # (a server's path in an imported workspace) the browser can't
            # reach it — unreachable until a folder is chosen.
            if self._data_root is not None and Path(folder.path).resolve().is_relative_to(self._data_root):
                return DISK(folder)
            return SuppliedLogSource(None, lambda rel: None)
        bridge = self._bridge
        return SuppliedLogSource(
            None,
            lambda rel: bridge.request_file(folder_id, rel),
            release=lambda rel: bridge.release_file(folder_id, rel),
            list_provider=lambda: bridge.request_listing(folder_id),
        )


def start(bridge, config: Optional[dict] = None) -> str:
    """Open the host on the data root. `config`: `data_root` (default
    /data), `host` ("browser", or "server" for the Node conformance run),
    `sources` ("page" or "disk"), `workspace_arg`."""
    global _ctx, _bridge
    from . import host
    cfg = dict(config.to_py() if hasattr(config, "to_py") else (config or {}))
    data_root = cfg.get("data_root", "/data")
    os.environ["SLINGOLOGY_EIS_HOME"] = data_root      # the configured data location (Spec 02 §5.8.1)
    Path(data_root).mkdir(parents=True, exist_ok=True)
    _bridge = bridge
    sources = DISK if cfg.get("sources") == "disk" else PageSources(bridge, Path(data_root))

    def emit_progress(stream: str, update: dict) -> None:
        _ctx[f"{stream}_progress"] = update
        if bridge is not None:
            bridge.emit_progress(stream, json.dumps(update))

    def deliver_file(path: Path, filename: str) -> str:
        return str(bridge.deliver_file(str(path), filename))

    _ctx = {"scan_progress": {"active": False}, "data_location_progress": {"active": False}}
    _ctx.update(host.new_context(log_sources=sources, host=cfg.get("host", "browser"),
                                 workspace_arg=cfg.get("workspace_arg"),
                                 emit_progress=emit_progress, deliver_file=deliver_file))
    return json.dumps(status())


def status() -> dict:
    """What `ready` reports: versions, and whether the data root holds a
    registry (the eviction check, Spec 04 §9.4)."""
    from . import __version__
    from . import workspace as ws
    registry = _ctx["registry_path"]
    return {"engine_version": __version__,
            "registry_present": registry.is_file() and bool(ws.load_registry(registry).workspaces),
            "data_root": str(registry.parent)}


def register_upload(upload_id: str, path: str, filename: str) -> None:
    """A file the page transferred (a dropped log, an export zip), written
    by the worker to a scratch path — the uploads registry, as /upload does
    on the server (Spec 04 v0.5 §9.1)."""
    _ctx["uploads"][str(upload_id)] = {"path": Path(path), "filename": str(filename)}


def scratch_dir() -> str:
    from . import host
    return str(host.scratch_dir(_ctx))


async def handle(envelope_json: str) -> str:
    """One envelope in, one reply out (JSON). Bytes for a log or an export
    come as an `upload_id` the worker registered beforehand — never base64."""
    from . import host
    envelope = json.loads(envelope_json)
    return _json_serialize.dumps(await host.reply_async(envelope, _ctx))


def handle_sync(envelope_json: str) -> str:
    """`handle` for the Node conformance run, whose sources are on disk."""
    from . import host
    return _json_serialize.dumps(host.reply(json.loads(envelope_json), _ctx))
