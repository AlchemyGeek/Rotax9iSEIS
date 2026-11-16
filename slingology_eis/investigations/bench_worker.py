"""
The bench's worker (Spec 16 D3, §4.5): one code cell, in a process the
engine starts for it and stops when the cell ends or a cap is reached.

    python -m slingology_eis.investigations.bench_worker REQUEST.json

The worker prepares the namespace — the scientific stack, the workspace
helpers, the engine profile — and only then installs the envelope, an
audit hook (PEP 578) that refuses, for the rest of the process:

- network: every `socket.*` event (no socket can be created);
- processes: `subprocess.Popen`, `os.system`, `os.exec*`, `os.posix_spawn`,
  `os.spawn*`, `os.fork*`, `os.kill*`, `pty.spawn`, `_posixsubprocess`;
- native calls: every `ctypes.*` event (ctypes could call libc directly);
- new audit hooks;
- writes: any `open` for writing, and `os.remove/rename/mkdir/rmdir/
  chmod/chown/link/symlink/truncate/utime`, `shutil.rmtree`,
  `sqlite3.connect`, anywhere but the study's `files/` folder.

stdout and stderr are the files the engine handed over, written through,
so what a cell printed before it was stopped is kept. A watchdog thread
ends the process when its peak resident memory passes the cap.

The engine (bench.py) reads the result file; the worker never talks to
the host or the network.
"""
from __future__ import annotations

import ast
import base64
import io
import json
import math
import os
import resource
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Optional

MEMORY_EXIT = 87
_MAX_TEXT_CHARS = 20000


def _peak_rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / (1024 * 1024) if sys.platform == "darwin" else r / 1024


def _drain(*streams) -> None:
    """Flush what a cell printed into its streams down to fds 1 and 2, so a
    stop keeps it (§4.5). The streams the cell has now come first: it may
    have wrapped or replaced ours with buffered ones."""
    for s in streams:
        try:
            s.flush()
        except Exception:  # noqa: BLE001 — a stream the cell broke can't stop the stop
            pass


def _watchdog(cap_mb: float, stdout, stderr) -> None:
    while True:
        if _peak_rss_mb() > cap_mb:
            try:
                _drain(sys.stdout, sys.stderr, stdout, stderr)
                stderr.write(f"\n[stopped: memory passed the {cap_mb:.0f} MB cap]\n")
                stderr.flush()
            finally:
                os._exit(MEMORY_EXIT)
        time.sleep(0.05)


# ── The envelope ───────────────────────────────────────────────────────────

_BLOCK_PREFIXES = ("socket.", "ctypes.", "_posixsubprocess.", "http.client.", "urllib.Request", "webbrowser.")
_BLOCK_EVENTS = {
    "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty",
    "os.kill", "os.killpg", "os.startfile", "pty.spawn", "sys.addaudithook", "os.add_dll_directory",
    "_winapi.CreateProcess", "msvcrt.open_osfhandle",
}
_PATH_WRITE_EVENTS = {
    "os.remove", "os.rename", "os.mkdir", "os.rmdir", "os.chmod", "os.chown", "os.link", "os.symlink",
    "os.truncate", "os.utime", "os.chflags", "os.lchflags", "os.setxattr", "os.removexattr", "os.mkfifo",
    "os.mknod", "shutil.rmtree", "shutil.copyfile", "shutil.copymode", "shutil.copystat", "shutil.copytree",
    "shutil.move", "shutil.chown", "sqlite3.connect", "tempfile.mkstemp", "tempfile.mkdtemp",
}
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND


class Refused(PermissionError):
    pass


def _refuse_process(*_a, **_k):
    raise Refused("the EIS bench refuses starting other programs (_posixsubprocess.fork_exec)")


def _close_unaudited_paths() -> None:
    """`_posixsubprocess.fork_exec` starts a process without raising any
    audit event (multiprocessing's spawn calls it directly), so it is
    replaced; and so is the loader of extension modules, so a fresh copy
    of `_posixsubprocess` can't be made to get the original back."""
    import _imp
    import _posixsubprocess
    _posixsubprocess.fork_exec = _refuse_process
    original = _imp.create_dynamic

    def create_dynamic(spec, *a):
        if getattr(spec, "name", "") in ("_posixsubprocess", "_ctypes", "_socket", "_ssl"):
            raise Refused(f"the EIS bench refuses loading {spec.name} afresh")
        return original(spec, *a)
    _imp.create_dynamic = create_dynamic


def install_envelope(files_dir: str) -> None:
    allowed = os.path.realpath(files_dir)
    guard = threading.local()
    _close_unaudited_paths()

    def inside(path) -> bool:
        if isinstance(path, int):
            return True                          # an already-open descriptor
        try:
            p = os.path.realpath(os.fsdecode(path))
        except (TypeError, ValueError):
            return False
        return p == allowed or p.startswith(allowed + os.sep) or p == os.devnull

    def hook(event: str, args) -> None:
        if getattr(guard, "busy", False):
            return
        guard.busy = True
        try:
            if event in _BLOCK_EVENTS or event.startswith(_BLOCK_PREFIXES):
                what = "network access" if event.startswith(("socket.", "http.", "urllib.")) else (
                    "native calls (ctypes)" if event.startswith("ctypes.") else "starting other programs")
                raise Refused(f"the EIS bench refuses {what} ({event})")
            if event == "open":
                path, mode, flags = (list(args) + [None, None, None])[:3]
                writes = (isinstance(mode, str) and any(c in mode for c in "wax+")) or \
                         (mode is None and isinstance(flags, int) and bool(flags & _WRITE_FLAGS))
                if writes and not inside(path):
                    raise Refused(f"the EIS bench writes only under the study's files/ folder; "
                                  f"not {os.fsdecode(path) if not isinstance(path, int) else path}")
            elif event in _PATH_WRITE_EVENTS:
                paths = [a for a in args[:2] if isinstance(a, (str, bytes, os.PathLike))]
                bad = [p for p in paths if not inside(p)]
                if bad:
                    raise Refused(f"the EIS bench writes only under the study's files/ folder; not {os.fsdecode(bad[0])}")
        finally:
            guard.busy = False

    sys.addaudithook(hook)


# ── Rendering what a cell returns (Spec 16 §5.1: nbformat 4 outputs) ─────

def _cell_value(v):
    import numpy as np
    import pandas as pd
    if v is None:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return None if not math.isfinite(f) else f
    if isinstance(v, (pd.Timestamp,)):
        return None if pd.isna(v) else v.isoformat()
    if v is pd.NaT:
        return None
    return str(v)


def _esc(v) -> str:
    return "" if v is None else str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_table(obj, max_rows: int, title=None, result: bool = False) -> dict:
    """A frame as `text/html` (the table EIS and Jupyter draw) and
    `text/plain`; at most `max_rows` rows are kept, the count is said."""
    import pandas as pd
    df = obj.to_frame() if isinstance(obj, pd.Series) else obj
    if not isinstance(df.index, pd.RangeIndex) or df.index.name is not None:
        df = df.reset_index()
    n = len(df)
    head = df.head(max_rows)
    cols = [str(c) for c in head.columns]
    rows = [[_cell_value(v) for v in row] for row in head.itertuples(index=False, name=None)]
    more = f"<p>{n - len(rows)} more rows not kept</p>" if n > len(rows) else ""
    cap = f"<caption>{_esc(title)}</caption>" if title else ""
    html = (f'<table class="eis-table">{cap}<thead><tr>' + "".join(f"<th>{_esc(c)}</th>" for c in cols)
            + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{_esc(v)}</td>" for v in r) + "</tr>"
                                                for r in rows) + f"</tbody></table>{more}")
    with pd.option_context("display.max_rows", max_rows, "display.max_columns", 50, "display.width", 200):
        plain = head.to_string(index=False)
    if n > len(rows):
        plain += f"\n[{n - len(rows)} more rows not kept]"
    if title:
        plain = f"{title}\n{plain}"
    meta = {"slingology": {"table": {"n_rows": int(n), "n_cols": int(df.shape[1]), "truncated": n > max_rows}}}
    return _bundle({"text/html": html, "text/plain": plain}, meta, result)


def _bundle(data: dict, metadata: Optional[dict] = None, result: bool = False) -> dict:
    if result:
        return {"output_type": "execute_result", "execution_count": None, "metadata": metadata or {}, "data": data}
    return {"output_type": "display_data", "metadata": metadata or {}, "data": data}


def _figure_title(fig) -> str:
    t = fig._suptitle.get_text() if getattr(fig, "_suptitle", None) is not None else ""
    if not t and fig.axes:
        t = fig.axes[0].get_title()
    return t


def _png(fig) -> str:
    png = io.BytesIO()
    fig.savefig(png, format="png", dpi=72, bbox_inches="tight")
    return base64.b64encode(png.getvalue()).decode()


def render_figure(fig, title=None, result: bool = False) -> dict:
    buf = io.StringIO()
    fig.savefig(buf, format="svg", metadata={"Date": None}, bbox_inches="tight")
    t = title or _figure_title(fig)
    out = _bundle({"image/svg+xml": buf.getvalue(), "text/plain": f"<Figure: {t}>" if t else "<Figure>"}, None, result)
    out["_png"] = _png(fig)          # the investigator's preview; never stored
    return out


def _text(text: str) -> str:
    return text if len(text) <= _MAX_TEXT_CHARS else text[:_MAX_TEXT_CHARS] + "\n[…truncated]"


def render(obj, caps: dict, title=None, result: bool = False):
    import matplotlib.figure
    import pandas as pd
    if isinstance(obj, (pd.DataFrame, pd.Series)):
        return render_table(obj, int(caps["table_rows"]), title, result)
    if isinstance(obj, matplotlib.figure.Figure):
        return render_figure(obj, title, result)
    if hasattr(obj, "figure") and isinstance(getattr(obj, "figure"), matplotlib.figure.Figure):
        return render_figure(obj.figure, title, result)          # an Axes
    if hasattr(obj, "_repr_mimebundle_"):
        data = obj._repr_mimebundle_()
        data = {k: v for k, v in data.items() if v is not None}
        data["text/plain"] = _text(str(data.get("text/plain") or repr(obj)))
        out = _bundle(data, None, result)
        if getattr(obj, "fig", None) is not None:
            out["_png"] = _png(obj.fig)
        return out
    text = _text(repr(obj))
    if title:
        text = f"{title}\n{text}"
    return _bundle({"text/plain": text}, None, result)


def _close(obj) -> None:
    import matplotlib.pyplot as plt
    for f in (obj, getattr(obj, "figure", None), getattr(obj, "fig", None)):
        if hasattr(f, "savefig"):
            plt.close(f)
            return


# ── The run ────────────────────────────────────────────────────────────────

def _split_last_expression(source: str, filename: str):
    import linecache
    linecache.cache[filename] = (len(source), None, source.splitlines(keepends=True), filename)
    tree = ast.parse(source, filename=filename, mode="exec")
    last = None
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = ast.Expression(tree.body.pop().value)
    body = compile(tree, filename, "exec")
    return body, (compile(last, filename, "eval") if last is not None else None)


def _cell_traceback(e: BaseException, filename: str) -> str:
    frames = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == filename] or \
        traceback.extract_tb(e.__traceback__)[-1:]
    lines = ["Traceback (cell):"] + [f"  line {f.lineno}: {f.line}" if f.line else f"  line {f.lineno}" for f in frames]
    lines.append(f"{type(e).__name__}: {e}")
    return "\n".join(lines)


def main(request_path: str) -> int:
    req = json.loads(Path(request_path).read_text())
    caps = req["caps"]
    result_fd = os.open(req["result_path"], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    # fds 1 and 2 are the files the engine opened for this cell; write through
    # so what was printed before a stop is on disk.
    sys.stdout = io.TextIOWrapper(os.fdopen(1, "wb", buffering=0), encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(os.fdopen(2, "wb", buffering=0), encoding="utf-8", write_through=True)
    sys.dont_write_bytecode = True
    threading.Thread(target=_watchdog, args=(float(caps["memory_mb"]), sys.stdout, sys.stderr), daemon=True).start()

    import logging
    logging.getLogger("matplotlib").setLevel(logging.ERROR)   # the one-off font-cache notice isn't the cell's output
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["svg.hashsalt"] = "slingology-eis"
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    try:
        import scipy
        import scipy.signal
        import scipy.stats
    except ImportError:      # the bench without scipy still runs; a cell importing it says why
        scipy = None
    from .bench_namespace import Workspace
    import matplotlib.font_manager  # noqa: F401 — builds the font cache now, outside the envelope
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    w = Workspace(req)
    from .eis_lib import EIS
    from .. import eis       # D14: the importable module, bound to this workspace — the setup cell's no-op
    eis._bind(EIS(w, req), Path(req["ws_dir"]).name, bench=True)
    outputs: list[dict] = []

    def show(obj, title=None):
        """Put a table (DataFrame), a figure or any value into the cell's outputs now."""
        outputs.append(render(obj, caps, title))
        _close(obj)

    namespace = {"__name__": "__eis_cell__", "__builtins__": __builtins__,
                 "np": np, "pd": pd, "plt": plt, "matplotlib": matplotlib, "scipy": scipy,
                 "ws": w, "eis": eis, "show": show, "FILES": Path(req["files_dir"]), "profile": w.profile,
                 "aircraft": w.aircraft, "flights": w.flights, "load_flight": w.load_flight,
                 "load_slices": w.load_slices, "load_slice_samples": w.load_slice_samples,
                 "flight_info": w.flight_info, "study": w.study}

    filename = f"<cell {req.get('cell_id') or ''}>"
    status, error = "ok", None
    install_envelope(req["files_dir"])
    t0 = time.monotonic()
    try:
        body, last = _split_last_expression(req["source"], filename)
        exec(body, namespace)
        if last is not None:
            value = eval(last, namespace)
            if value is not None:
                outputs.append(render(value, caps, result=True))
                _close(value)
    except SyntaxError as e:
        status, error = "error", {"output_type": "error", "ename": "SyntaxError", "evalue": str(e),
                                  "traceback": [f"SyntaxError: {e.msg} (line {e.lineno})"]}
    except BaseException as e:  # noqa: BLE001 — a cell's error is its output (Spec 16 §4.5)
        status, error = "error", {"output_type": "error", "ename": type(e).__name__, "evalue": str(e),
                                  "traceback": _cell_traceback(e, filename).splitlines()}
    # Figures the cell drew and left open, as a notebook would show them.
    try:
        for num in plt.get_fignums():
            outputs.append(render_figure(plt.figure(num)))
        plt.close("all")
    except Exception as e:  # noqa: BLE001
        outputs.append({"output_type": "stream", "name": "stderr",
                        "text": f"[a figure couldn't be drawn: {type(e).__name__}: {e}]\n"})
    if error is not None:
        outputs.append(error)
    ms = int((time.monotonic() - t0) * 1000)
    sys.stdout.flush()
    sys.stderr.flush()
    body = json.dumps({"status": status, "outputs": outputs, "flights": sorted(w.touched), "ms": ms,
                       "peak_rss_mb": round(_peak_rss_mb(), 1)}).encode()
    view = memoryview(body)
    while view:
        view = view[os.write(result_fd, view):]
    os.close(result_fd)
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
