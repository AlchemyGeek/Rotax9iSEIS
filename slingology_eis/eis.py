"""
The `eis` library, importable (Spec 16 D14, §5.4):

    from slingology_eis import eis
    eis.open("ws_…")                   # bind to a workspace (default: the aircraft's, as the MCP server picks it)
    r = eis.cycling("full_power", "rpm")
    print(r)

The same functions a notebook cell has on the EIS bench — `flights`, `find`,
`load`, `slices`, `samples`, `cycling`, `coupling`, `groups`, `unusual`,
`compare`, `signal`, `logview`, `document`, `aircraft`, `profile`, `notes`
(see `slingology_eis.investigations.eis_lib`) — and the same code: on the
bench this module is bound before the cell runs, so a notebook's setup
cell (`eis.open("<workspace id>")`) is a no-op there and the binding in
any other kernel.

Outside EIS nothing is sandboxed: it is your kernel on your machine, as
with any notebook. Needs `slingology-eis[investigations]` in the kernel's
environment (pandas, matplotlib, scipy).
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

__all__ = ["open", "bound", "workspace_id", "Result", "LogView", "LOGVIEW_MIME"]

_bound = None             # the EIS instance the module answers through
_workspace_id: Optional[str] = None
_on_bench = False         # bound by the bench worker: another workspace can't be opened from a cell


def __getattr__(name: str):
    # Result, LogView and LOGVIEW_MIME without importing pandas at `import eis`.
    if name in ("Result", "LogView", "LOGVIEW_MIME", "EIS"):
        from .investigations import eis_lib
        return getattr(eis_lib, name)
    if name.startswith("__"):
        raise AttributeError(name)
    if _bound is None:
        raise RuntimeError(f"eis.{name}: no workspace yet — run the notebook's setup cell first "
                           "(from slingology_eis import eis; eis.open(\"<workspace id>\"))")
    return getattr(_bound, name)


def __dir__():
    names = list(__all__)
    if _bound is not None:
        names += [n for n in dir(_bound) if not n.startswith("_")]
    return sorted(set(names))


def bound() -> bool:
    return _bound is not None


def workspace_id() -> Optional[str]:
    return _workspace_id


def _bind(instance, ws_id: Optional[str], *, bench: bool = False) -> None:
    """The bench worker's binding, before a cell runs (and open's)."""
    global _bound, _workspace_id, _on_bench
    _bound, _workspace_id, _on_bench = instance, ws_id, bench


@contextmanager
def _root(data_root):
    """The data root for this open: `data_root=`, else the one the pages
    and the MCP server use (SLINGOLOGY_EIS_HOME, location.json, default)."""
    if data_root is None:
        yield
        return
    old = os.environ.get("SLINGOLOGY_EIS_HOME")
    os.environ["SLINGOLOGY_EIS_HOME"] = str(Path(data_root).expanduser())
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("SLINGOLOGY_EIS_HOME", None)
        else:
            os.environ["SLINGOLOGY_EIS_HOME"] = old


def open(workspace_id: Optional[str] = None, data_root=None) -> None:  # noqa: A001 — the spec's name
    """Bind `eis` to a workspace (the module is then the handle: eis.cycling(...)).

    `workspace_id` (an id or a name; default: the aircraft's workspace, as
    the MCP server chooses it); `data_root` (default: the registry the EIS
    pages use). On the EIS bench the workspace is already bound and this
    does nothing; naming another workspace there is refused. Returns None,
    so the setup cell shows no output.
    """
    global _bound, _workspace_id
    if _on_bench:
        if workspace_id is not None and workspace_id != _workspace_id or data_root is not None:
            raise RuntimeError(f"on the EIS bench this notebook runs against workspace {_workspace_id}; "
                               "open another workspace from a kernel outside EIS")
        return None
    from . import host as H
    from .investigations import ops
    from .investigations.bench_namespace import Workspace
    from .investigations.eis_lib import EIS
    from .investigations.mcp_server import Server
    with _root(data_root):
        server = Server(workspace_arg=workspace_id)
        chosen = server.choose_workspace()
        if chosen is None:
            raise RuntimeError("no workspace to open: this data root has none for an aircraft "
                               + (f"({server.aircraft_error})" if server.aircraft_error else "")
                               + " — pass eis.open(\"<workspace id>\") or data_root=")
        H._open_data_root(server.ctx, chosen)
        ctx = server.ctx
        if not ctx.get("active_workspace_id"):
            raise RuntimeError(f"no workspace {chosen!r} in {Path(ctx['registry_path']).parent}")
        req = ops.eis_request(ctx)
    # FILES outside EIS: the notebook's own files/ when the kernel runs in its folder (JupyterLab does).
    here = Path.cwd()
    req["files_dir"] = str(here / "files" if (here / "notebook.ipynb").is_file() else here)
    instance = EIS(Workspace(req), req)
    _bind(instance, ctx["active_workspace_id"])      # silent: the setup cell has no output anywhere
