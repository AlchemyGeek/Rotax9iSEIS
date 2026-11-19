"""
Spec 16 D14, §5.4: the `eis` library is importable — `eis.open` binds it
outside EIS to a workspace and gives the bench's numbers; the bench binds
the same module, so the setup cell is a no-op there; outputs a kernel
outside EIS saved in the notebook are marked *ran elsewhere* and can be
accepted as they stand (`study_accept` with `source: "external"`).
"""
import json
import sys

import pytest

from slingology_eis import eis
from slingology_eis.investigations import ipynb as NBX
from tests.unit.test_research_ops import _import, _ok
from tests.unit.test_server import InProcess, isolated_packaged_home, rpc  # noqa: F401

pytest.importorskip("matplotlib")


@pytest.fixture
def ws(isolated_packaged_home):
    h = InProcess()
    _ok(rpc(h, "create_workspace", {"name": "D14", "engine_model": "916iS"}))
    ids = [_import(h, f"2026-01-0{n}") for n in range(1, 4)]
    ws_id = _ok(rpc(h, "get_active_workspace", {}))["registry_entry"]["id"]
    yield h, ids, ws_id, isolated_packaged_home
    eis._bind(None, None)          # leave the module unbound for the next test


def _nb_path(home, ws_id, sid):
    return home / "workspaces" / ws_id / "studies" / sid / "notebook.ipynb"


def test_unbound_says_what_to_do():
    eis._bind(None, None)
    with pytest.raises(RuntimeError, match="setup cell"):
        eis.cycling("full_power", "rpm")


def test_open_binds_and_gives_the_tools_numbers(ws):
    h, ids, ws_id, home = ws
    tool = _ok(rpc(h, "run_test", {"test_id": "cycling", "slice_rules": ["full_power"], "channels": ["rpm"]}))
    assert eis.open(data_root=home) is None                 # default: the aircraft's workspace
    assert eis.workspace_id() == ws_id and eis.bound()
    assert eis.cycling("full_power", "rpm").finding == tool["finding"]
    assert set(eis.flights()["flight_id"]) == set(ids)
    assert eis.Result.__name__ == "Result" and eis.LOGVIEW_MIME.startswith("application/vnd.slingology")
    eis.open(ws_id, data_root=home)                         # by id
    assert eis.workspace_id() == ws_id
    with pytest.raises(RuntimeError, match="no workspace"):
        eis.open("ws_000000000000", data_root=home)


def test_study_create_writes_the_setup_cell_first(ws):
    h, _ids, ws_id, _home = ws
    sid = _ok(rpc(h, "study_create", {"name": "Setup", "question": "?"}))["study_id"]
    nb = _ok(rpc(h, "load_study", {"study_id": sid}))["notebook"]
    first = nb["cells"][0]
    assert first["id"] == "setup" and first["cell_type"] == "code" and first["outputs"] == []
    assert f'from slingology_eis import eis\neis.open("{ws_id}")' in first["source"]
    assert nb["metadata"]["slingology"]["workspace_id"] == ws_id
    assert nb["cells"][1]["metadata"]["slingology"]["role"] == "question"


@pytest.mark.skipif(sys.platform == "win32", reason="the bench's caps are POSIX")
def test_the_setup_cell_is_a_no_op_on_the_bench(ws):
    h, _ids, ws_id, _home = ws
    sid = _ok(rpc(h, "study_create", {"name": "Bench", "question": "?"}))["study_id"]
    got = _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {
        "kind": "code", "source": f'from slingology_eis import eis\neis.open("{ws_id}")\n'
                                  'print(eis.workspace_id(), eis.cycling("full_power", "rpm").finding)'}}))["cell"]
    assert got["metadata"]["slingology"]["ran"]["status"] == "ok", got
    assert got["outputs"][0]["text"].startswith(ws_id)
    other = _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {
        "kind": "code", "source": 'from slingology_eis import eis\neis.open("ws_000000000000")'}}))["cell"]
    assert other["outputs"][-1]["output_type"] == "error" and "on the EIS bench" in other["outputs"][-1]["evalue"]
    re = _ok(rpc(h, "study_cells_rerun", {"study_id": sid}))
    assert all(c["identical"] for c in re["cells"]), re      # setup cell included: no output, identical


@pytest.mark.skipif(sys.platform == "win32", reason="the bench's caps are POSIX")
def test_outputs_saved_outside_eis_are_ran_elsewhere_until_accepted(ws):
    h, _ids, ws_id, home = ws
    sid = _ok(rpc(h, "study_create", {"name": "External", "question": "?"}))["study_id"]
    cell = _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "code", "source": "print(6 * 7)"}}))["cell"]
    p = _nb_path(home, ws_id, sid)

    # JupyterLab re-saves the same outputs its own way (lists of lines, execution counts): not a change.
    nb = json.loads(p.read_text())
    for c in nb["cells"]:
        if c["cell_type"] == "code":
            c["source"] = NBX.text(c["source"]).splitlines(keepends=True)
            c["execution_count"] = 3
            for o in c["outputs"]:
                o["text"] = NBX.text(o["text"]).splitlines(keepends=True)
    p.write_text(json.dumps(nb, indent=1))
    nb = _ok(rpc(h, "load_study", {"study_id": sid}))["notebook"]
    assert not any((c["metadata"].get("slingology") or {}).get("ran_elsewhere") for c in nb["cells"])

    # A kernel outside EIS ran the cell and saved different outputs in place.
    nb = json.loads(p.read_text())
    mine = next(c for c in nb["cells"] if c["id"] == cell["id"])
    mine["source"] = "print(6 * 7 + 1)"
    mine["outputs"] = [{"output_type": "stream", "name": "stdout", "text": ["43\n"]}]
    p.write_text(json.dumps(nb, indent=1))
    view = _ok(rpc(h, "load_study", {"study_id": sid}))
    mine = next(c for c in view["notebook"]["cells"] if c["id"] == cell["id"])
    assert mine["metadata"]["slingology"]["ran_elsewhere"] == "external"

    bad = rpc(h, "study_cells_accept", {"study_id": sid, "source": "kernel"})
    assert bad["error"]["code"] == "BAD_PARAMS"
    done = _ok(rpc(h, "study_cells_accept", {"study_id": sid, "source": "external"}))
    assert done["cells"] == [cell["id"]]
    nb = _ok(rpc(h, "load_study", {"study_id": sid}))["notebook"]
    mine = next(c for c in nb["cells"] if c["id"] == cell["id"])
    sm = mine["metadata"]["slingology"]
    assert "ran_elsewhere" not in sm and sm["ran"]["source"] == "external"
    assert NBX.text(mine["outputs"][0]["text"]) == "43\n"

    # A bench re-run replaces them in the usual way (pending until accepted).
    re = _ok(rpc(h, "study_cells_rerun", {"study_id": sid}))
    assert next(c for c in re["cells"] if c["cell_id"] == cell["id"])["identical"] is True


def test_a_notebook_without_the_setup_cell_gets_it(ws):
    """Notebooks written before D14 (Session E's) gain the setup cell on first load."""
    h, _ids, ws_id, home = ws
    sid = _ok(rpc(h, "study_create", {"name": "Old", "question": "?"}))["study_id"]
    p = _nb_path(home, ws_id, sid)
    nb = json.loads(p.read_text())
    nb["cells"] = [c for c in nb["cells"] if c["id"] != "setup"]
    nb["metadata"]["slingology"].pop("workspace_id")
    p.write_text(json.dumps(nb))
    nb = _ok(rpc(h, "load_study", {"study_id": sid}))["notebook"]
    assert [c["id"] for c in nb["cells"]][:2] == ["setup", "c1"]
    assert json.loads(p.read_text())["cells"][0]["id"] == "setup"          # saved


# ── F18: Trends in a cell — the same rows as fleet_metrics and trends_summary ──

def test_spec16_24_eis_metrics_and_trends_are_the_tools_rows(ws):
    from slingology_eis.investigations.mcp_tools import run_fleet_metrics, run_trends_summary
    h, ids, ws_id, home = ws
    call = lambda op, p: _ok(rpc(h, op, p))  # noqa: E731
    eis.open(ws_id, data_root=home)

    tool = run_fleet_metrics({"limit": 1000}, call)
    m = eis.metrics()
    assert list(m["flight_id"]) == [r["flight_id"] for r in tool["rows"]] and set(m["flight_id"]) == set(ids)
    assert list(m.columns[:8]) == ["flight_id", "name", "date", "start_local", "engine_hours", "cruise_da_ft",
                                   "cruise_oat_c", "source"]
    want = [b["metric_id"] for b in tool["metrics"]]
    assert list(m.columns[8:]) == [k for k in want if k != "cruise_da_ft"] and m.columns.is_unique
    for row, r in zip(m.to_dict("records"), tool["rows"]):
        assert row["engine_hours"] == r["engine_hours"]
        for k in want:                                   # row for row, NaN for a missing value
            assert (row[k] == r[k]) or (r[k] is None and row[k] != row[k]) or (r[k] is None and row[k] is None), (k, row[k], r[k])
    # The conditions come from the flights' own facts.
    facts = {f["flight_id"]: f["summary"]["facts"] for f in _ok(rpc(h, "list_flights", {"summary": True}))}
    for row in m.to_dict("records"):
        assert row["source"] in ("G3X", "AXIS")
        oat = facts[row["flight_id"]].get("cruise_oat_c")
        assert row["cruise_oat_c"] == oat or (oat is None and row["cruise_oat_c"] != row["cruise_oat_c"])

    # Choosing flights and metrics, as the tool's arguments do.
    some = run_fleet_metrics({"metrics": want[:2], "flights": ids[:2], "limit": 1000}, call)
    sub = eis.metrics(flights=ids[:2], metrics=want[:2])
    assert list(sub["flight_id"]) == [r["flight_id"] for r in some["rows"]] and list(sub.columns[8:]) == want[:2]
    with pytest.raises(ValueError, match="unknown metrics"):
        eis.metrics(metrics=["no_such_metric"])

    summary = run_trends_summary({}, call)
    t = eis.trends()
    assert list(t["metric_id"]) == [c["metric_id"] for c in summary["change_summary"]]
    for row, c in zip(t.to_dict("records"), summary["change_summary"]):
        assert row["rank"] == c["rank"] and row["reference_n"] == c["baseline"]["n"]
        assert row["reference_mean"] == c["baseline"]["mean"] and row["trend_slope_per_hour"] == c["trend"]["slope"]
        assert row["shift"] == bool(c["shift"])
        assert set(row["flights"]) <= set(ids)
