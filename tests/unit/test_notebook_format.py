"""
Spec 16 §5.1 / acceptance 12: the stored notebook is a Jupyter notebook —
`nbformat.validate` accepts it and `jupyter nbconvert --to html` renders
it (markdown, a table, a figure, a log view's SVG) — and EIS's own HTML
render is deterministic and runs nothing.
"""
import io
import json
import subprocess
import sys
import zipfile

import pytest

from tests.unit.test_research_ops import _import, _ok
from tests.unit.test_server import InProcess, isolated_packaged_home, rpc  # noqa: F401

pytest.importorskip("matplotlib")
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the bench's caps are POSIX")


@pytest.fixture
def notebook(isolated_packaged_home):
    h = InProcess()
    _ok(rpc(h, "create_workspace", {"name": "NB", "engine_model": "916iS"}))
    fid = _import(h, "2026-01-01")
    sid = _ok(rpc(h, "study_create", {"name": "Format", "question": "Does it open in Jupyter?"}))["study_id"]
    cell = lambda c: _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": c}))  # noqa: E731
    cell({"kind": "markdown", "source": "## A table\n\nThe slices, one row each."})
    cell({"kind": "code", "source": "eis.slices('full_power', ['rpm'])[['flight_id', 'rpm.swing']]"})
    cell({"kind": "markdown", "source": "The cycle, as the result's figure:"})
    cell({"kind": "code", "source": "r = eis.cycling('full_power', 'rpm')\nprint(r)\nr.figure()"})
    cell({"kind": "markdown", "source": "The first full-power window:"})
    cell({"kind": "logview", "flight": fid, "start_s": 0, "end_s": 60, "channels": ["rpm", "map_inhg"],
          "marks": [[10, "mark"]]})
    view = _ok(rpc(h, "load_study", {"study_id": sid}))
    return h, sid, view["notebook"]


def test_validates_and_converts(notebook, tmp_path):
    nbformat = pytest.importorskip("nbformat")
    h, sid, nb = notebook
    nbformat.validate(nbformat.from_dict(nb))
    data = h.download(_ok(rpc(h, "export_study", {"study_id": sid}))["download_url"])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(tmp_path)
    nbformat.validate(nbformat.read(str(tmp_path / "notebook.ipynb"), as_version=4))
    pytest.importorskip("nbconvert")
    p = subprocess.run([sys.executable, "-m", "nbconvert", "--to", "html", str(tmp_path / "notebook.ipynb")],
                       capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, p.stderr
    page = (tmp_path / "notebook.html").read_text()
    assert "A table" in page and page.count("data:image/svg+xml;base64,") >= 2 and "eis-table" in page


def test_own_render_is_deterministic_and_inert(notebook):
    h, sid, nb = notebook
    a = h.download(_ok(rpc(h, "export_study", {"study_id": sid, "format": "html"}))["download_url"])
    b = h.download(_ok(rpc(h, "export_study", {"study_id": sid, "format": "html"}))["download_url"])
    assert a == b
    page = a.decode()
    assert page.count('<details class="code">') == 3 and "<script" not in page      # the setup cell isn't shown (Spec 03 v0.34)
    assert page.count("data:image/svg+xml;base64,") == 2 and 'class="logview"' in page
    assert "<table" in page and json.dumps(nb)  # the notebook is JSON


def test_zip_is_deterministic(notebook):
    h, sid, _nb = notebook
    a = h.download(_ok(rpc(h, "export_study", {"study_id": sid}))["download_url"])
    b = h.download(_ok(rpc(h, "export_study", {"study_id": sid}))["download_url"])
    assert a == b
