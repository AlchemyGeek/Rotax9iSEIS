"""
Spec 16 acceptance 6: the bench's envelope (§4.5). code_run refuses
network and subprocess access and writes outside the study's files/
folder; a runaway cell is stopped at the cap with its partial output
kept. In process (the envelope is the worker's, the same under HTTP);
under Pyodide there is no bench at all (test_investigations_ops).
"""
import sys

import pytest

from tests.unit.test_research_ops import _import, _ok
from tests.unit.test_server import InProcess, isolated_packaged_home, rpc  # noqa: F401 — fixture

pytest.importorskip("matplotlib")
pytest.importorskip("scipy")
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the envelope's caps are POSIX (killpg, rusage)")


@pytest.fixture
def bench(isolated_packaged_home):
    h = InProcess()
    _ok(rpc(h, "create_workspace", {"name": "Bench", "engine_model": "916iS"}))
    _import(h, "2026-01-01")
    sid = _ok(rpc(h, "study_create", {"name": "Sandbox"}))["study_id"]

    def run(source, **caps):
        cell = _ok(rpc(h, "code_run", {"study_id": sid, "source": source, **caps}))["cell"]
        cell["ran"] = cell["metadata"]["slingology"]["ran"]          # the notebook cell's run record (§5.1)
        return cell
    run.home = isolated_packaged_home
    return run


def _refused(cell) -> str:
    assert cell["ran"]["status"] == "error", cell
    err = cell["outputs"][-1]
    assert err["output_type"] == "error" and err["ename"] == "Refused", err
    return err["evalue"]


@pytest.mark.parametrize("source", [
    "import socket\nsocket.create_connection(('127.0.0.1', 8420), timeout=1)",
    "import socket\nsocket.socket()",
    "import urllib.request\nurllib.request.urlopen('http://example.com', timeout=1)",
    "import http.client\nhttp.client.HTTPConnection('example.com').request('GET', '/')",
])
def test_network_refused(bench, source):
    _refused(bench(source))


@pytest.mark.parametrize("source", [
    "import subprocess\nsubprocess.run(['echo', 'hi'])",
    "import os\nos.system('echo hi')",
    "import os\nos.posix_spawn('/bin/echo', ['echo'], {})",
    "import os\nos.fork()",
    "import multiprocessing as mp\np = mp.Process(target=print)\np.start()",
    "import _posixsubprocess\n_posixsubprocess.fork_exec(*[None] * 23)",
    "import importlib, _posixsubprocess\nimportlib.reload(_posixsubprocess).fork_exec(*[None] * 23)",
    "import ctypes\nctypes.CDLL(None)",
])
def test_subprocesses_refused(bench, source):
    _refused(bench(source))


def test_writes_only_under_files(bench, tmp_path):
    outside = tmp_path / "outside.txt"
    assert "files/" in _refused(bench(f"open({str(outside)!r}, 'w').write('x')"))
    assert not outside.exists()
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    _refused(bench(f"import os\nos.remove({str(victim)!r})"))
    assert victim.read_text() == "keep"
    # The workspace itself (registry, analyses) is outside files/ too.
    registry = bench.home / "registry.json"
    _refused(bench(f"open({str(registry)!r}, 'a').write('x')"))
    _refused(bench(f"import shutil\nshutil.rmtree({str(bench.home / 'workspaces')!r})"))
    assert (bench.home / "workspaces").is_dir()
    # Inside files/ is allowed, and reading anywhere is.
    ok = bench("(FILES / 'note.txt').write_text('hello')\nprint((FILES / 'note.txt').read_text())\n"
               f"len(open({str(registry)!r}).read()) > 0")
    assert ok["ran"]["status"] == "ok", ok
    assert ok["outputs"][0]["text"].strip() == "hello"


def test_runaway_stopped_with_partial_output(bench):
    cell = bench("import time\nfor i in range(10**9):\n    print('line', i, flush=True)\n    time.sleep(0.1)",
                 timeout_s=3)
    assert cell["ran"]["status"] == "timeout"
    text = cell["outputs"][0]["text"]
    assert cell["outputs"][0]["output_type"] == "stream" and "line 0" in text and "line 5" in text
    assert cell["outputs"][-1]["ename"] == "Stopped" and "3 s cap" in cell["outputs"][-1]["evalue"]


def test_memory_cap(bench):
    cell = bench("print('before', flush=True)\nimport numpy as np\nblocks = [np.ones(50_000_000) for _ in range(40)]",
                 memory_mb=400, timeout_s=60)
    assert cell["ran"]["status"] == "memory", cell["ran"]
    assert cell["outputs"][0]["text"].strip() == "before"
    assert cell["outputs"][-1]["ename"] == "Stopped" and "400 MB" in cell["outputs"][-1]["evalue"]


@pytest.mark.skipif(sys.platform != "darwin", reason="the kernel layer is macOS sandbox-exec")
def test_kernel_layer_holds_when_the_hook_is_defeated(bench, tmp_path):
    """The audit hook is not a boundary: a cell can reach its state and
    switch it off. On macOS the worker runs under sandbox-exec, so the
    kernel still refuses the write and the connection."""
    target = tmp_path / "escaped.txt"
    cell = bench(
        "import gc, types, socket\n"
        "hook = next(f for f in gc.get_objects() if type(f) is types.FunctionType and f.__name__ == 'hook'"
        " and 'bench_worker' in f.__code__.co_filename)\n"
        "guard = [c.cell_contents for c in hook.__closure__ if type(c.cell_contents).__name__ == '_local'][0]\n"
        "guard.busy = True\n"
        "for name, f in [('write', lambda: open(" + repr(str(target)) + ", 'w').write('x')),\n"
        "                ('net', lambda: socket.create_connection(('127.0.0.1', 8420), timeout=1))]:\n"
        "    try:\n"
        "        f(); print(name, 'ESCAPED')\n"
        "    except OSError as e:\n"
        "        print(name, 'stopped', e.errno)\n")
    assert cell["ran"]["caps"]["os_sandbox"] == "sandbox-exec"
    assert cell["outputs"][0]["text"].split("\n")[:2] == ["write stopped 1", "net stopped 1"], cell["outputs"]
    assert not target.exists()
