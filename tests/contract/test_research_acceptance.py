"""
Spec 06 §15 — the acceptance case, reproduced from the app alone
(Session A: items 1–7, 9, 11–13; Session C: 14–18), against the private
log set.

The acceptance set is the investigation's: every admitted flight dated
through 2026-10-28 (Appendix A — the logs the investigation read; flights
the owner adds later don't move these numbers). Nothing per-flight is
asserted beyond what Spec 06 itself states.

Items 1, 2 and 5 were revised in Spec 06 v0.4 (Q11–Q13) to what the
data shows: the set is pinned to the investigation's date, the period is
3.8 s (the 1 Hz logs give that by every estimator; the write-up's 4.4 s
came from a different count), and the two clean high-altitude takeoffs
are asserted to stand out on rpm swing rather than to rank first.
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


def test_2_cycling_period_as_the_spec_states(results):
    """Spec 06 §15 item 2 (v0.4, Q11): median 3.8 s, IQR within 3.5–4.1."""
    p25, p50, p75 = results["cycling"]["block"]["summary"]["period_s"]
    assert round(p50, 1) == 3.8 and 3.5 <= p25 <= p50 <= p75 <= 4.1


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

def test_5_unusual_lists_the_clean_takeoffs(results):
    """Spec 06 §15 item 5 (v0.4, Q12): both are listed among the slices standing out, on rpm swing."""
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
        # v1.1: one flight's strips in the browser's engine, against server mode.
        sig = {"flight_id": _oct24(app), "channels": ["rpm", "map_inhg"]}
        t0 = time.time()
        reply = node.call("analyze_signal", sig, "n")
        in_page = time.time() - t0
        t0 = time.time()
        expected = app.call("analyze_signal", **sig)
        server = time.time() - t0
        assert reply["ok"], reply
        assert reply["result"] == json.loads(serialize.dumps(expected))
        print(f"[signal strips] one flight, rpm + MAP: server {server:.1f} s, browser engine {in_page:.1f} s")
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


# ── v1.1 (Session C): Signal view and Compare, items 14–18 ────────────────

OCT24 = "2026-10-24"          # the KAWO–KPAE–KBLI–KAWO flight: three full-power segments
STRIP_LIT_MIN = 0.5           # a segment is "lit" when its period strip is prominent over half its seconds
STRIP_DARK_MAX = 0.2          # cruise and taxi are "dark": lit over at most a fifth of their seconds …
DARK_RUN_MAX_S = 15           # … and never for as long as the full-power preset's minimum duration


def _oct24(app) -> str:
    from slingology_eis import workspace as ws
    d = app.ctx["workspace_dir"]
    got = [f for f in app.flights if ws.load_flight_analysis(d, f).header.get("date") == OCT24]
    assert len(got) == 1
    return got[0]


@pytest.fixture(scope="module")
def oct24(app):
    fid = _oct24(app)
    segs = [s for s in app.call("build_slices", selection={"mode": "flights", "flights": [fid]},
                                slice_rules=[FULL_POWER], channels=["rpm"])["slices"]]
    return fid, segs


def _mask(n, phases, names):
    m = [False] * n
    for p in phases:
        if p["phase"] in names:
            for i in range(int(p["start_s"]), min(n, int(p["end_s"]))):
                m[i] = True
    return m


def _longest(flags):
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


def test_14_period_strip_lit_over_full_power_dark_elsewhere(app, oct24):
    fid, segs = oct24
    assert len(segs) == 3
    r = app.call("analyze_signal", flight_id=fid, channels=["rpm", "map_inhg"])
    n = r["duration_s"]
    for ch in ("rpm", "map_inhg"):
        st = r["strips"][ch]
        lit, per, sw = st["prominent"], st["period_s"], st["swing"]
        seg_swings = []
        for s in segs:
            a, b = s["start_s"], s["end_s"]
            assert sum(lit[a:b]) >= STRIP_LIT_MIN * (b - a), (ch, a, b)
            lit_periods = sorted(p for p, x in zip(per[a:b], lit[a:b]) if x)
            assert 3 <= lit_periods[len(lit_periods) // 2] <= 5
            seg_swings += [x for x in sw[a:b] if x is not None]
        for names in (["CRUISE"], ["TAXI"]):
            m = _mask(n, r["phases"], names)
            in_phase = [x for x, k in zip(lit, m) if k]
            assert sum(in_phase) <= STRIP_DARK_MAX * len(in_phase), (ch, names)
            assert _longest([x and k for x, k in zip(lit, m)]) < DARK_RUN_MAX_S, (ch, names)
            quiet = sorted(x for x, k in zip(sw, m) if k and x is not None)
            assert sorted(seg_swings)[len(seg_swings) // 2] >= 3 * quiet[len(quiet) // 2], (ch, names)


def _first_window(app, oct24):
    fid, segs = oct24
    a, b = segs[0]["start_s"], segs[0]["end_s"]
    return app.call("analyze_signal", flight_id=fid, channels=["rpm", "map_inhg", "fuel_flow_gph"],
                    window={"start_s": a, "end_s": b})["window"]


def test_15_window_on_the_first_full_power_segment(app, oct24):
    w = _first_window(app, oct24)
    rpm, mp, ff = (w["descriptors"][c] for c in ("rpm", "map_inhg", "fuel_flow_gph"))
    assert 150 <= rpm["swing"] <= 210
    assert mp["corr0"] >= 0.85 and mp["lag_s"] == 0
    assert ff["lag_s"] == 1 and w["diagnostics"]["fuel_flow_gph"]["best_lag_s"] == 1
    assert rpm["period_prominent"]
    # Same code path as the slice set: the window's numbers are the slice's.
    fid, segs = oct24
    assert {k: rpm[k] for k in ("swing", "period_s", "period_prominence")} == \
        {k: segs[0]["descriptors"]["rpm"][k] for k in ("swing", "period_s", "period_prominence")}


@pytest.mark.xfail(strict=True, reason="Spec 06 §15 item 15: period 3.5–4.1 s is the set's IQR (item 2); this "
                                       "segment's own period is 3.4 s by the same estimator that gives the set "
                                       "3.8 s — proposed revision in the Session C report.")
def test_15_window_period_as_the_spec_states(app, oct24):
    assert 3.5 <= _first_window(app, oct24)["descriptors"]["rpm"]["period_s"] <= 4.1


def test_15_derived_rule_recovers_the_segment(app, oct24):
    fid, segs = oct24
    rule = _first_window(app, oct24)["derived_rule"]
    got = app.call("build_slices", selection={"mode": "flights", "flights": [fid]}, slice_rules=[rule],
                   channels=["rpm"])["slices"]
    a, b = segs[0]["start_s"], segs[0]["end_s"]
    match = [s for s in got if s["start_s"] < b and s["end_s"] > a]
    assert len(match) == 1 and abs(match[0]["start_s"] - a) <= 3 and abs(match[0]["end_s"] - b) <= 3


@pytest.fixture(scope="module")
def compare(app):
    return app.call("compare_rows", selection=app.selection, slice_rules=[FULL_POWER], channels=["rpm", "map_inhg"])


def test_16_compare_rows_are_the_slice_descriptors(app, compare, slice_set):
    assert compare["row_count"] == 98 and compare["flight_count"] == 59
    assert len(compare["flights_without"]) == len(app.flights) - 59
    assert [r["slice_id"] for r in compare["rows"]] == [s["slice_id"] for s in slice_set["slices"]]
    for r, s in zip(compare["rows"], slice_set["slices"]):
        for ch in ("rpm", "map_inhg"):
            assert r["values"][ch] == {k: s["descriptors"][ch][k] for k in r["values"][ch]}
    col = app.call("compare_rows", selection=app.selection, slice_rules=[FULL_POWER], channels=["rpm", "map_inhg"],
                   collapse=True)
    assert col["row_count"] == 59 and sum(r["count"] for r in col["rows"]) == 98


def test_17_pinned_kawo_row_and_swing_against_da(app, compare, oct24, results):
    fid, segs = oct24
    p = app.call("compare_rows", selection=app.selection, slice_rules=[FULL_POWER], channels=["rpm", "map_inhg"],
                 pinned=segs[0]["slice_id"])
    rows = p["rows"]
    assert sum(1 for r in rows if r["pinned"]) == 1
    assert all("swing" in r["delta"]["rpm"] and "period_s" in r["delta"]["rpm"] for r in rows)
    high = [r for r in rows if (r["da_ft"] or 0) >= 6000]
    assert len(high) == 2 and all(r["delta"]["rpm"]["swing"] <= -90 for r in high)
    # The chart's data, swing against DA, banded as acceptance 4 bands it.
    def med(xs):
        xs = sorted(xs)
        k = len(xs) // 2
        return xs[k] if len(xs) % 2 else (xs[k - 1] + xs[k]) / 2
    bands = {"below 3,500 ft DA": [], "at 3,500–6,000 ft DA": [], "at 6,000 ft DA and above": []}
    for r in rows:
        da = r["da_ft"]
        key = ("below 3,500 ft DA" if da < 3500 else "at 3,500–6,000 ft DA" if da < 6000 else "at 6,000 ft DA and above")
        bands[key].append(r["values"]["rpm"]["swing"])
    g = results["groups"]["block"]["summary"]["groups"]
    for k, xs in bands.items():
        assert len(xs) == g[k]["n"] and med(xs) == g[k]["median"]


def test_18_study_with_signal_rule_pin_and_question_round_trips(app, oct24):
    fid, segs = oct24
    w = _first_window(app, oct24)
    study = {"name": "Oct 24 takeoff", "selection": app.selection, "slice_rules": [w["derived_rule"]],
             "signal": {"flight": fid, "channels": ["rpm", "map_inhg", "fuel_flow_gph"], "reference": "rpm",
                        "window": {"start_s": segs[0]["start_s"], "end_s": segs[0]["end_s"]}},
             "compare": {"pinned": segs[0]["slice_id"], "channels": ["rpm", "map_inhg"],
                         "chart": {"x": "da_ft", "y": "rpm.swing", "colour": "source"}},
             "tests": [{"test_id": "cycling", "channels": ["rpm"]}]}
    sid = app.call("save_study", study=study)["study_id"]
    ran = app.call("run_study", study_id=sid)
    for doc in (app.call("load_study", study_id=sid), ran):
        assert doc["signal"]["flight"] == fid and doc["signal"]["window"]["start_s"] == segs[0]["start_s"]
        assert doc["slice_rules"][0]["derived_from"]["flight"] == fid
        assert doc["compare"]["pinned"] == segs[0]["slice_id"] and len(doc["tests"]) == 1
    data = app.files[app.call("export_study", study_id=sid)["filename"]]
    imp = json.loads(serialize.dumps(host.reply({"op": "import_study", "request_id": "t",
                                                  "params": {"content": data}}, app.ctx)))["result"]
    st = imp["study"]
    assert st["signal"] == ran["signal"] and st["compare"] == ran["compare"]
    assert st["slice_rules"] == ran["slice_rules"] and [t["test_id"] for t in st["tests"]] == ["cycling"]
    again = app.call("run_study", study_id=st["study_id"])
    assert again["tests"][0]["result"]["finding"] == ran["tests"][0]["result"]["finding"]
