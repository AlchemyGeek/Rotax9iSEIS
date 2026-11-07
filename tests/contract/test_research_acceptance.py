"""
Spec 06 §15 — the acceptance case, reproduced from the app alone
(Session A: items 1–7, 9, 11–13), against the private log set.

The acceptance set is the investigation's: every admitted flight dated
through 2026-10-28 (Appendix A — the logs the investigation read; flights
the owner adds later don't move these numbers). Nothing per-flight is
asserted beyond what Spec 06 itself states.

Two items disagree with the data and are written as strict expected
failures stating what the data shows (session report, proposed revision):
item 2's 4.4 s period (the 1 Hz logs give ~3.8 s by every estimator) and
item 5's ranking (other slices rank above the two clean high-altitude
takeoffs under §7.4's method as written).
"""
import base64
import json
import os
import shutil
import time
from pathlib import Path

import pytest

from slingology_eis import host, serialize
from slingology_eis.log_sources import DISK
from slingology_eis.research.render import check_no_verdicts, render_text

from ..conftest import LOGS_DIR, requires_flight_logs

pytestmark = requires_flight_logs

INVESTIGATION_THROUGH = "2026-10-28"
FULL_POWER = "full_power"
REFS = [{"label": "Airmaster governing band", "channel": "rpm", "value": 100, "kind": "band",
         "source": "AP3/4/5 Operator's Manual V5-1A"}]
STUDY_TESTS = [
    {"test_id": "cycling", "channels": ["rpm"]},
    {"test_id": "coupling", "channels": ["rpm", "map_inhg", "fuel_flow_gph"]},
    {"test_id": "groups", "params": {"descriptor": "rpm.swing", "split": {"by": "da_band", "edges": [3500, 6000]}}},
    {"test_id": "unusual"},
]


class _Host:
    """An in-process host on its own data root (never the owner's)."""

    def __init__(self, root: Path):
        self.root = root
        self.files: dict = {}
        old = os.environ.get("SLINGOLOGY_EIS_HOME")
        os.environ["SLINGOLOGY_EIS_HOME"] = str(root)
        try:
            self.ctx = host.new_context(log_sources=DISK, host="server", deliver_file=self._deliver,
                                        emit_progress=lambda s, u: None)
        finally:
            if old is None:
                os.environ.pop("SLINGOLOGY_EIS_HOME", None)
            else:
                os.environ["SLINGOLOGY_EIS_HOME"] = old

    def _deliver(self, path, filename):
        self.files[filename] = Path(path).read_bytes()
        return filename

    def call(self, op, **params):
        r = json.loads(serialize.dumps(host.reply({"op": op, "request_id": "t", "params": params}, self.ctx)))
        assert r["ok"], r
        return r["result"]

    def workspace(self, name: str, folder: Path) -> str:
        self.call("create_workspace", name=name, engine_model="916iS")
        self.call("add_log_folder", path=str(folder))
        self.call("scan_workspace")
        return self.ctx["active_workspace_id"]

    def investigation_flights(self) -> list[str]:
        from slingology_eis import workspace as ws
        d = self.ctx["workspace_dir"]
        return sorted(f for f in ws.list_flight_ids(d)
                      if (ws.load_flight_analysis(d, f).header.get("date") or "") <= INVESTIGATION_THROUGH)


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    h = _Host(tmp_path_factory.mktemp("research-home"))
    h.main = h.workspace("Research acceptance", LOGS_DIR.resolve())
    h.flights = h.investigation_flights()
    h.selection = {"mode": "flights", "flights": h.flights}
    return h


@pytest.fixture(scope="module")
def results(app):
    """The four tests on the full-power set, each through run_test."""
    out = {}
    for t in STUDY_TESTS:
        out[t["test_id"]] = app.call("run_test", test_id=t["test_id"], selection=app.selection,
                                     slice_rules=[FULL_POWER], channels=t.get("channels"), params=t.get("params"),
                                     references=REFS)
    return out


@pytest.fixture(scope="module")
def slice_set(app):
    return app.call("build_slices", selection=app.selection, slice_rules=[FULL_POWER], channels=["rpm", "map_inhg"])


# ── 1. The 98-slice set ────────────────────────────────────────────────────

def test_1_full_power_preset_gives_the_appendix_a_set(app, slice_set):
    assert len(app.flights) == 60          # 121 logs; duplicates and non-flights out
    assert slice_set["count"] == 98
    assert slice_set["by_source"] == {"G3X": 84, "AXIS": 14}
    long_blocks = [s for s in slice_set["slices"] if s["end_s"] - s["start_s"] >= 250]
    assert len(long_blocks) == 2 and all(s["context"]["source"] == "G3X" for s in long_blocks)
    assert len({s["slice_id"] for s in slice_set["slices"]}) == 98


# ── 2. 7.1 on rpm ──────────────────────────────────────────────────────────

def test_2_cycling_swing_and_recurrence(results):
    r = results["cycling"]
    sm = r["block"]["summary"]
    assert sm["slices"] == 98 and sm["prominent"] >= 90
    assert sm["swing"][1] == 180
    assert f"in {sm['prominent']} of 98 slices" in r["finding"]


@pytest.mark.xfail(strict=True, reason="Spec 06 §15 item 2 / Appendix A: 4.4 s (IQR 4.1–4.8). The 1 Hz logs give "
                                       "a median of ~3.8 s (IQR ~3.6–3.9) by autocorrelation and by periodogram, "
                                       "on G3X and AXIS alike — proposed revision in the Session A report.")
def test_2_cycling_period_as_the_spec_states(results):
    p25, p50, p75 = results["cycling"]["block"]["summary"]["period_s"]
    assert round(p50, 1) == 4.4 and 4.1 <= p25 and p75 <= 4.8


def test_2_cycling_period_is_stable(results):
    """What the data gives (the guard until the spec's number is settled)."""
    p25, p50, p75 = results["cycling"]["block"]["summary"]["period_s"]
    assert 3.5 <= p25 <= p50 <= p75 <= 4.1


# ── 3. 7.2 rpm vs MAP, fuel flow ───────────────────────────────────────────

def test_3_coupling_per_source_with_damping_caveat(results):
    r = results["coupling"]
    mp = r["block"]["summary"]["map_inhg"]["per_source"]
    assert mp["AXIS"]["corr0"][1] >= 0.85
    assert mp["G3X"]["corr0"][1] <= 0.35
    assert "on AXIS slices" in r["finding"] and "on G3X slices" in r["finding"]
    assert any("damped" in c and "MAP" in c for c in r["caveats"])
    assert r["block"]["summary"]["fuel_flow_gph"]["lag_mode_s"] == 1


# ── 4. 7.3 by DA band ──────────────────────────────────────────────────────

def test_4_groups_by_density_altitude(results):
    g = results["groups"]["block"]["summary"]["groups"]
    low, mid, high = g["below 3,500 ft DA"], g["at 3,500–6,000 ft DA"], g["at 6,000 ft DA and above"]
    assert low["median"] > mid["median"] > high["median"]
    assert high["n"] == 2 and high["small_group"]
    assert "small group" in results["groups"]["finding"]


# ── 5. 7.4 ─────────────────────────────────────────────────────────────────

def _top(r, n):
    return [row["start_time"][:16] for row in r["block"]["per_slice"][:n]]


@pytest.mark.xfail(strict=True, reason="Spec 06 §15 item 5: under §7.4 as written (standard descriptors, robust z "
                                       "within source, ranked by largest |z|) other slices — an EGT/MAP transient, an "
                                       "rpm step — rank above the two clean high-DA takeoffs; proposed revision in "
                                       "the Session A report.")
def test_5_unusual_ranks_the_clean_takeoffs_first(results):
    assert set(_top(results["unusual"], 2)) == {"2026-07-17 18:19", "2026-07-23 18:12"}


def test_5_unusual_lists_the_clean_takeoffs(results):
    """What holds today: both are listed as standing out, on rpm swing."""
    rows = {row["start_time"][:16]: row for row in results["unusual"]["block"]["per_slice"]}
    for t in ("2026-07-17 18:19", "2026-07-23 18:12"):
        assert rows[t]["stands_out"] and rows[t]["descriptor"] == "rpm.swing" and rows[t]["value"] < rows[t]["set_median"]


# ── 6, 12. Studies: save, export, delete, re-import; partial and read-only ─

def _subset_folder(tmp_path: Path, names: list[str]) -> Path:
    d = tmp_path / "logs"
    d.mkdir(parents=True)
    for n in names:
        os.symlink((LOGS_DIR / n).resolve(), d / n)
    return d


def test_6_and_12_study_round_trip(app, results, tmp_path):
    study = {"name": "Takeoff rpm oscillation", "selection": app.selection, "slice_rules": [FULL_POWER],
             "references": REFS, "tests": STUDY_TESTS}
    sid = app.call("save_study", study=study)["study_id"]
    ran = app.call("run_study", study_id=sid)
    for t in ran["tests"]:
        assert t["result"]["finding"] == results[t["test_id"]]["finding"]
    exp = app.call("export_study", study_id=sid)
    data = app.files[exp["filename"]]
    app.call("delete_study", study_id=sid)
    imp = json.loads(serialize.dumps(host.reply({"op": "import_study", "request_id": "t",
                                                  "params": {"content": data}}, app.ctx)))["result"]
    assert not imp["read_only"] and imp["missing"] == []
    again = app.call("run_study", study_id=imp["study"]["study_id"])
    assert [t["result"]["finding"] for t in again["tests"]] == [t["result"]["finding"] for t in ran["tests"]]
    assert ([t["result"]["block"]["summary"] for t in again["tests"]]
            == [t["result"]["block"]["summary"] for t in ran["tests"]])

    # A workspace holding some of the logs: G3X only.
    g3x = sorted(p.name for p in LOGS_DIR.glob("log_*.csv"))
    other = _Host(tmp_path / "home2")
    other.workspace("G3X only", _subset_folder(tmp_path / "a", g3x))
    part = json.loads(serialize.dumps(host.reply({"op": "import_study", "request_id": "t",
                                                   "params": {"content": data}}, other.ctx)))["result"]
    assert part["matched"] and part["missing"] and not part["read_only"]
    pr = other.call("run_study", study_id=part["study"]["study_id"])
    assert pr["last_run"]["slices"] == 84 and pr["last_run"]["by_source"] == {"G3X": 84}

    # 12: a study about flights this workspace has none of opens read-only.
    axis_only = {"mode": "flights", "flights": sorted({s["flight"] for s in app.call(
        "build_slices", selection=app.selection, slice_rules=[FULL_POWER], channels=["rpm"])["slices"]
        if s["context"]["source"] == "AXIS"})}
    sid2 = app.call("save_study", study={**study, "name": "AXIS takeoffs", "selection": axis_only,
                                          "tests": [STUDY_TESTS[0]]})["study_id"]
    sent = app.call("run_study", study_id=sid2)
    data2 = app.files[app.call("export_study", study_id=sid2)["filename"]]
    ro = json.loads(serialize.dumps(host.reply({"op": "import_study", "request_id": "t",
                                                 "params": {"content": data2}}, other.ctx)))["result"]
    assert ro["read_only"] and ro["matched"] == []
    assert ro["study"]["read_only"]["label"] == "sender's results; none of these flights are in this workspace"
    assert ro["study"]["tests"][0]["result"]["finding"] == sent["tests"][0]["result"]["finding"]
    mine = other.call("run_study_on_my_flights", study_id=ro["study"]["study_id"])
    assert not mine.get("read_only") and mine["last_run"]["by_source"] == {"G3X": 84}


# ── 7. CLI and browser give the operation's JSON ──────────────────────────

def test_7_cli_json_is_the_operation_json(app, capsys, monkeypatch):
    from slingology_eis import cli
    monkeypatch.setenv("SLINGOLOGY_EIS_HOME", str(app.root))
    expected = app.call("run_test", test_id="cycling", slice_rules=[FULL_POWER], channels=["rpm"])
    assert cli.main(["research", "test", "cycling", "--rule", FULL_POWER, "--channel", "rpm", "--json", "--quiet"]) == 0
    assert capsys.readouterr().out.strip() == serialize.dumps(expected)


def test_7_browser_host_gives_the_same_json(app, tmp_path_factory, request):
    """The same operation under Pyodide in Node (the browser's engine);
    the slice-build time is the browser-mode measurement (acceptance 8
    is Session B's; measured now)."""
    import subprocess
    import sys
    from tests.unit.test_server import _NODE_HOST, _REPO, _node_available, NodeHost
    if not _node_available():
        pytest.skip("Pyodide-in-Node needs node and web/node_modules/pyodide")
    base = tmp_path_factory.getbasetemp().resolve()

    class _LogsNodeHost(NodeHost):
        """NodeHost with the log folder mounted too: the browser reads the
        logs through the page, here through the same paths."""
        def __init__(self):
            self.basetemp = base
            wheel_dir = base / "node-wheel-research"
            subprocess.run([sys.executable, str(_REPO / "scripts" / "build_engine_wheel.py"), "--out", str(wheel_dir)],
                           check=True, capture_output=True)
            wheel = next(wheel_dir.glob("*.whl"))
            self.proc = subprocess.Popen(["node", str(_NODE_HOST), "--wheel", str(wheel), "--mount", str(base),
                                          "--mount", str(LOGS_DIR.resolve())],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                         text=True)
            self._read()

    node = _LogsNodeHost()
    try:
        node.start(app.root.resolve())
        assert node.call("switch_workspace", {"workspace_id": app.main}, "n")["ok"]
        params = {"test_id": "cycling", "slice_rules": [FULL_POWER], "channels": ["rpm"], "selection": app.selection}
        t0 = time.time()
        reply = node.call("run_test", params, "n")
        elapsed = time.time() - t0
        expected = app.call("run_test", **params)
        assert reply["ok"], reply
        # Values, not bytes: the Node bridge's JSON writes 1674.0 as 1674.
        assert reply["result"] == json.loads(serialize.dumps(expected))
        print(f"\n[browser host] full-power slice build + test over {len(app.flights)} flights: {elapsed:.1f} s")
    finally:
        node.close()


# ── 9. No verdict without its reference ───────────────────────────────────

def test_9_no_verdict_words(results):
    for r in results.values():
        assert check_no_verdicts(r) == [], r["finding"]
        assert "beside:" in render_text(r)


# ── 11. Windows printed and resolved ──────────────────────────────────────

def test_11_windows_resolve_to_floors_and_scale_in_cruise(app, results):
    w = results["cycling"]["block"]["params"]["windows"]["rpm"]
    assert (w["window_s"], w["lag_s"], w["basis"]) == (12, 10, "period")
    assert any("swing window 12 s, lag range ±10 s" in c for c in results["cycling"]["caveats"])
    cruise = app.call("build_slices", selection=app.selection, slice_rules=["stable_cruise"], channels=["rpm"])
    cw = cruise["windows"]["rpm"]
    assert cw["basis"] == "duration" and cw["window_s"] > 12 and cw["lag_s"] > 10
    r = app.call("run_test", test_id="cycling", selection=app.selection, slice_rules=["stable_cruise"], channels=["rpm"])
    assert any(f"swing window {cw['window_s']} s, lag range ±{cw['lag_s']} s" in c for c in r["caveats"])


# ── 13. Preset measurements guarded (Spec 06 §5.2, Q1) ─────────────────────

# Measured in Session A over the acceptance set (60 flights); recorded in
# Spec 06 §5.2. (slices, flights with a slice, max per flight, median duration s)
PRESET_MEASUREMENT = {
    "full_power": (98, 59, 9, 54),
    "governed_climb": (92, 48, 7, 126),
    "stable_cruise": (108, 38, 10, 712),
    "idle": (161, 59, 7, 95),
    "warm_up": (44, 44, 1, 256),
}


@pytest.mark.parametrize("preset", sorted(PRESET_MEASUREMENT))
def test_13_preset_measurement(app, preset):
    ss = app.call("build_slices", selection=app.selection, slice_rules=[preset], channels=["rpm"])
    per = {}
    for s in ss["slices"]:
        per[s["flight"]] = per.get(s["flight"], 0) + 1
    durations = sorted(s["end_s"] - s["start_s"] for s in ss["slices"])
    mid = len(durations) // 2
    median = durations[mid] if len(durations) % 2 else (durations[mid - 1] + durations[mid]) / 2
    got = (ss["count"], len(per), max(per.values()), round(median))
    assert got == PRESET_MEASUREMENT[preset]
