"""
The code tool's engine side (Spec 16 D3, §4.5): run one cell in a worker
process (bench_worker.py) under the envelope, and turn what it returned
into a notebook cell.

Caps (§9 Q2), per cell:
- wall clock `DEFAULT_TIMEOUT_S` (a cell may ask for up to `MAX_TIMEOUT_S`),
  counted from the worker's start, imports included;
- memory `DEFAULT_MEMORY_MB` peak resident (up to `MAX_MEMORY_MB`);
- stdout and stderr kept up to `MAX_STREAM_CHARS` each;
- tables up to `TABLE_ROWS` rows, figures as SVG (stored under the
  study's files/) with a small PNG preview for the investigator.

A cell stopped at a cap keeps what it printed before the stop. A cell's
own error is its output, never a host error, so the investigator can read
it and try again.

The worker gets a minimal environment — no inherited variables beyond
PATH, HOME and the locale — so a cell can't read the engine's
environment either.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .. import __version__

DEFAULT_TIMEOUT_S = 60
MAX_TIMEOUT_S = 300
DEFAULT_MEMORY_MB = 2048
MAX_MEMORY_MB = 8192
MAX_STREAM_CHARS = 100_000
TABLE_ROWS = 500
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]


class BenchError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def caps(timeout_s=None, memory_mb=None) -> dict:
    try:
        t = DEFAULT_TIMEOUT_S if timeout_s is None else float(timeout_s)
        m = DEFAULT_MEMORY_MB if memory_mb is None else float(memory_mb)
    except (TypeError, ValueError):
        raise BenchError("BAD_PARAMS", "timeout_s and memory_mb are numbers")
    if not 1 <= t <= MAX_TIMEOUT_S:
        raise BenchError("BAD_PARAMS", f"timeout_s is 1–{MAX_TIMEOUT_S}")
    if not 256 <= m <= MAX_MEMORY_MB:
        raise BenchError("BAD_PARAMS", f"memory_mb is 256–{MAX_MEMORY_MB}")
    return {"timeout_s": t, "memory_mb": m, "table_rows": TABLE_ROWS}


def _read_capped(p: Path) -> tuple[str, bool]:
    if not p.is_file():
        return "", False
    data = p.read_bytes()
    text = data.decode("utf-8", errors="replace")
    if len(text) > MAX_STREAM_CHARS:
        return text[:MAX_STREAM_CHARS] + "\n[…output truncated]", True
    return text, False


def _env(mpl_dir: Path) -> dict:
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT") if k in os.environ}
    env.update({"PYTHONPATH": str(_PACKAGE_ROOT), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
                "PYTHONNOUSERSITE": "1", "MPLCONFIGDIR": str(mpl_dir), "MPLBACKEND": "Agg",
                "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"})
    return env


def run_cell(*, source: str, cell_id: str, ws_dir: Path, files_dir: Path, scratch: Path, mpl_dir: Path,
             engine_cfg: dict, engine_name: str, aircraft: dict, assignments: dict, study: dict,
             cap: dict) -> dict:
    """Run one cell; returns {outputs, ran, previews}. `outputs` are the
    notebook outputs (figures as refs into files/), `previews` maps a
    figure ref to its PNG (base64) for the investigator's eyes."""
    if not isinstance(source, str) or not source.strip():
        raise BenchError("BAD_PARAMS", "a code cell needs source")
    files_dir.mkdir(parents=True, exist_ok=True)
    mpl_dir.mkdir(parents=True, exist_ok=True)
    work = scratch / f"bench-{uuid.uuid4().hex[:12]}"
    work.mkdir(parents=True, exist_ok=True)
    req = {"source": source, "cell_id": cell_id, "ws_dir": str(ws_dir), "files_dir": str(files_dir),
           "engine_cfg": engine_cfg, "engine_name": engine_name, "aircraft": aircraft, "assignments": assignments,
           "study": study, "caps": cap, "result_path": str(work / "result.json")}
    (work / "request.json").write_text(json.dumps(req))
    out_p, err_p = work / "stdout.txt", work / "stderr.txt"
    started = time.monotonic()
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(out_p, "wb") as out_f, open(err_p, "wb") as err_f:
        proc = subprocess.Popen([sys.executable, "-m", "slingology_eis.investigations.bench_worker",
                                 str(work / "request.json")], cwd=str(files_dir), env=_env(mpl_dir),
                                stdin=subprocess.DEVNULL, stdout=out_f, stderr=err_f, start_new_session=True)
        status = None
        try:
            proc.wait(timeout=cap["timeout_s"])
        except subprocess.TimeoutExpired:
            status = "timeout"
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
            proc.wait()
    ms = int((time.monotonic() - started) * 1000)
    from .bench_worker import MEMORY_EXIT
    stdout, _ = _read_capped(out_p)
    stderr, _ = _read_capped(err_p)
    result = None
    if status is None:
        if proc.returncode == MEMORY_EXIT:
            status = "memory"
        else:
            try:
                result = json.loads((work / "result.json").read_text())
                status = result["status"]
            except (OSError, ValueError, KeyError):
                status = "crashed"

    outputs: list[dict] = []
    if stdout:
        outputs.append({"kind": "text", "stream": "stdout", "text": stdout})
    previews: dict[str, str] = {}
    for o in (result or {}).get("outputs") or []:
        if o["kind"] == "figure":
            svg = o["svg"].encode()
            name = f"fig-{hashlib.sha256(svg).hexdigest()[:16]}.svg"
            (files_dir / name).write_bytes(svg)
            ref = f"files/{name}"
            previews[ref] = o["png_base64"]
            outputs.append({"kind": "figure", "ref": ref, "title": o.get("title")})
        else:
            outputs.append(o)
    if stderr.strip():
        outputs.append({"kind": "text", "stream": "stderr", "text": stderr})
    if status == "timeout":
        outputs.append({"kind": "error", "ename": "Stopped", "evalue": f"the cell ran past the {cap['timeout_s']:g} s cap",
                        "traceback": f"Stopped at the {cap['timeout_s']:g} s wall-clock cap; the output above is what "
                                     "it printed before the stop."})
    elif status == "memory":
        outputs.append({"kind": "error", "ename": "Stopped", "evalue": f"the cell passed the {cap['memory_mb']:g} MB memory cap",
                        "traceback": f"Stopped at the {cap['memory_mb']:g} MB memory cap; the output above is what "
                                     "it printed before the stop."})
    elif status == "crashed":
        outputs.append({"kind": "error", "ename": "Crashed",
                        "evalue": f"the bench process ended without a result (exit {proc.returncode})",
                        "traceback": "The bench process ended without a result; stderr above may say why."})
    ran = {"engine": __version__, "flights": (result or {}).get("flights") or [], "at": at, "ms": ms,
           "status": status, "caps": {"timeout_s": cap["timeout_s"], "memory_mb": cap["memory_mb"]}}
    for p in work.iterdir():
        p.unlink()
    work.rmdir()
    return {"outputs": outputs, "ran": ran, "previews": previews}


def outputs_equal(a: Optional[list], b: Optional[list]) -> bool:
    """Two runs' outputs say the same thing (refs are content hashes)."""
    return json.dumps(a or [], sort_keys=True) == json.dumps(b or [], sort_keys=True)
