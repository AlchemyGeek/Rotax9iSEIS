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

MEMORY_EXIT = 87
_MAX_TEXT_CHARS = 20000


def _peak_rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / (1024 * 1024) if sys.platform == "darwin" else r / 1024


def _watchdog(cap_mb: float, stderr) -> None:
    while True:
        if _peak_rss_mb() > cap_mb:
            try:
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


# ── Rendering what a cell returns ──────────────────────────────────────────

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


def render_table(obj, max_rows: int, title=None) -> dict:
    import pandas as pd
    df = obj.to_frame() if isinstance(obj, pd.Series) else obj
    if not isinstance(df.index, pd.RangeIndex) or df.index.name is not None:
        df = df.reset_index()
    n = len(df)
    head = df.head(max_rows)
    out = {"kind": "table", "columns": [str(c) for c in head.columns],
           "rows": [[_cell_value(v) for v in row] for row in head.itertuples(index=False, name=None)],
           "n_rows": int(n), "n_cols": int(df.shape[1]), "truncated": n > max_rows}
    if title:
        out["title"] = str(title)
    return out


def render_figure(fig, title=None) -> dict:
    buf = io.StringIO()
    fig.savefig(buf, format="svg", metadata={"Date": None}, bbox_inches="tight")
    png = io.BytesIO()
    fig.savefig(png, format="png", dpi=72, bbox_inches="tight")
    t = title
    if not t:
        t = fig._suptitle.get_text() if getattr(fig, "_suptitle", None) is not None else ""
        if not t and fig.axes:
            t = fig.axes[0].get_title()
    return {"kind": "figure", "svg": buf.getvalue(), "png_base64": base64.b64encode(png.getvalue()).decode(),
            "title": t or None}


def render(obj, caps: dict, title=None):
    import matplotlib.figure
    import pandas as pd
    if isinstance(obj, (pd.DataFrame, pd.Series)):
        return render_table(obj, int(caps["table_rows"]), title)
    if isinstance(obj, matplotlib.figure.Figure):
        return render_figure(obj, title)
    if hasattr(obj, "figure") and isinstance(getattr(obj, "figure"), matplotlib.figure.Figure):
        return render_figure(obj.figure, title)          # an Axes
    text = repr(obj)
    if len(text) > _MAX_TEXT_CHARS:
        text = text[:_MAX_TEXT_CHARS] + "\n[…truncated]"
    out = {"kind": "text", "text": text}
    if title:
        out["title"] = str(title)
    return out


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
    threading.Thread(target=_watchdog, args=(float(caps["memory_mb"]), sys.stderr), daemon=True).start()

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
    outputs: list[dict] = []

    def show(obj, title=None):
        """Put a table (DataFrame), a figure or any value into the cell's outputs now."""
        outputs.append(render(obj, caps, title))
        if hasattr(obj, "savefig"):
            plt.close(obj)

    namespace = {"__name__": "__eis_cell__", "__builtins__": __builtins__,
                 "np": np, "pd": pd, "plt": plt, "matplotlib": matplotlib, "scipy": scipy,
                 "ws": w, "show": show, "FILES": Path(req["files_dir"]), "profile": w.profile,
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
                outputs.append(render(value, caps))
                if hasattr(value, "savefig"):
                    plt.close(value)
                elif hasattr(value, "figure") and hasattr(value.figure, "savefig"):
                    plt.close(value.figure)
    except SyntaxError as e:
        status, error = "error", {"kind": "error", "ename": "SyntaxError", "evalue": str(e),
                                  "traceback": f"SyntaxError: {e.msg} (line {e.lineno})"}
    except BaseException as e:  # noqa: BLE001 — a cell's error is its output (Spec 16 §4.5)
        status, error = "error", {"kind": "error", "ename": type(e).__name__, "evalue": str(e),
                                  "traceback": _cell_traceback(e, filename)}
    # Figures the cell drew and left open, as a notebook would show them.
    try:
        for num in plt.get_fignums():
            outputs.append(render_figure(plt.figure(num)))
        plt.close("all")
    except Exception as e:  # noqa: BLE001
        outputs.append({"kind": "text", "text": f"[a figure couldn't be drawn: {type(e).__name__}: {e}]"})
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
