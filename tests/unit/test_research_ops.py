"""
Spec 06 §11 Research operations, run the three ways every host operation
is (Spec 04 §9.6): in process, over HTTP, and under Pyodide in Node.js —
on synthetic flights with an oscillating full-power segment, so they run
without the private logs. The CLI's JSON is checked against the
operation's (acceptance 7).
"""
import base64
import json
import math

import pytest

from slingology_eis import serialize
from tests.unit.test_server import (  # noqa: F401 — fixtures
    CALL_PATHS, InProcess, NodeHost, _FLYING_PREAMBLE_LEN, _flying_log_bytes, _node_host, _serve,
    isolated_packaged_home, registry_server, rpc,
)

FP_START = 120              # rows of full power, oscillating
FP_LEN = 60


def _osc(i: int, period: float = 4.4) -> float:
    return math.sin(2 * math.pi * (i - FP_START) / period)


def _research_log(date: str, swing_rpm: float = 90.0) -> bytes:
    """A flight that climbs, cruises, and holds full power for a minute
    with rpm and MAP cycling together (the acceptance case in miniature)."""
    def rpm(i):
        if FP_START <= i < FP_START + FP_LEN:
            return int(round((5700 + swing_rpm * _osc(i)) / 10) * 10)
        return None

    def extra(i):
        mp = 48 + 2.5 * _osc(i) * (swing_rpm / 90) if FP_START <= i < FP_START + FP_LEN else 40.0
        return f",{mp:.1f},180"
    return _flying_log_bytes(date=date, extra_header=",Manifold Press (inch Hg),Oil Temp (deg F)",
                             row_extra_fn=extra, rpm_override=rpm)


def _import(handle, date: str, swing_rpm: float = 90.0) -> str:
    b64 = base64.b64encode(_research_log(date, swing_rpm)).decode()
    name = f"log_{date.replace('-', '')}_120000_TEST.csv"
    imp = rpc(handle, "import_files", {"files": [{"content_base64": b64, "filename": name}]})
    assert imp["ok"], imp
    return imp["result"]["results"][0]["flight_id"]


FULL_POWER = {"rule_id": "full_power", "conditions": [{"channel": "rpm", "op": ">=", "value": 5550}],
              "min_duration_s": 15, "merge_gap_s": 3}


@pytest.fixture
def research_ws(registry_server):
    rpc(registry_server, "create_workspace", {"name": "Research", "engine_model": "916iS"})
    ids = [_import(registry_server, f"2026-01-0{n}") for n in range(1, 6)]
    ids.append(_import(registry_server, "2026-01-06", swing_rpm=30))
    return registry_server, ids


def _ok(d):
    assert d["ok"], d
    return d["result"]


def test_research_is_a_capability(registry_server):
    caps = _ok(rpc(registry_server, "get_capabilities", {}))
    assert caps["features"]["research"] is True


def test_list_slice_presets(registry_server):
    p = _ok(rpc(registry_server, "list_slice_presets", {"engine": "916iS"}))
    assert p["status"] == "measured" and p["presets"][0]["rule_id"] == "full_power"
    assert _ok(rpc(registry_server, "list_slice_presets", {"engine": "915iS"}))["status"] == "unverified"


def test_build_slices_and_samples(research_ws):
    h, ids = research_ws
    ss = _ok(rpc(h, "build_slices", {"slice_rules": ["full_power"], "channels": ["rpm", "map_inhg"]}))
    assert ss["count"] == 6 and ss["flights_with_slices"] == 6 and ss["by_source"] == {"G3X": 6}
    s = ss["slices"][0]
    assert s["end_s"] - s["start_s"] == FP_LEN and s["anchor_s"] == s["start_s"]
    assert s["context"]["source"] == "G3X" and s["context"]["flight_id"] in ids
    assert s["descriptors"]["rpm"]["period_prominent"] is True
    assert ss["windows"]["rpm"] == {**ss["windows"]["rpm"], "window_s": 12, "lag_s": 10, "basis": "period"}
    # A hand slice on one flight, beside the rule's set (§5.4).
    hand = _ok(rpc(h, "build_slices", {"slice_rules": [], "hand_slices": [{"flight": ids[0], "start_s": FP_START,
                                                                          "end_s": FP_START + 30, "label": "this one"}],
                                      "channels": ["rpm"]}))
    assert hand["count"] == 1 and hand["slices"][0]["kind"] == "hand" and hand["slices"][0]["offset_s"] == 0
    smp = _ok(rpc(h, "get_slice_samples", {"slice_rules": [FULL_POWER], "channels": ["rpm", "map_inhg"],
                                           "slice_ids": [s["slice_id"]], "anchor": "crossing"}))
    assert len(smp["slices"]) == 1 and smp["slices"][0]["t"][0] == 0.0
    assert len(smp["slices"][0]["channels"]["rpm"]) == FP_LEN


def test_bad_rule_is_bad_params(research_ws):
    h, _ids = research_ws
    d = rpc(h, "build_slices", {"slice_rules": [{"conditions": [{"channel": "nope", "op": ">=", "value": 1}]}]})
    assert not d["ok"] and d["error"]["code"] == "BAD_PARAMS"
    d = rpc(h, "build_slices", {"slice_rules": ["no_such_preset"]})
    assert not d["ok"] and d["error"]["code"] == "BAD_PARAMS"


def test_run_test_returns_the_contract(research_ws):
    h, _ids = research_ws
    r = _ok(rpc(h, "run_test", {"test_id": "cycling", "slice_rules": ["full_power"], "channels": ["rpm"]}))
    assert set(r) == {"test_id", "version", "question", "finding", "evidence", "magnitude", "caveats", "block"}
    assert "in 6 of 6 slices" in r["finding"]
    assert r["block"]["engine_version"] and r["block"]["params"]["windows"]["rpm"]["window_s"] == 12
    c = _ok(rpc(h, "run_test", {"test_id": "coupling", "slice_rules": ["full_power"], "channels": ["rpm", "map_inhg"]}))
    assert c["block"]["summary"]["map_inhg"]["lag_mode_s"] == 0


def test_study_lifecycle_export_import(research_ws, tmp_path):
    h, ids = research_ws
    study = {"name": "Takeoff rpm oscillation", "slice_rules": [FULL_POWER],
             "tests": [{"test_id": "cycling", "channels": ["rpm"]},
                       {"test_id": "unusual", "channels": ["rpm", "map_inhg"]}]}
    saved = _ok(rpc(h, "save_study", {"study": study}))
    sid = saved["study_id"]
    ran = _ok(rpc(h, "run_study", {"study_id": sid}))
    assert ran["tests"][0]["result"]["finding"].endswith("in 6 of 6 slices.")
    assert ran["last_run"]["slices"] == 6 and sorted(ran["flights"]) == sorted(ids)
    assert len(ran["cache"]["descriptors"]) == 6
    assert ran["tests"][1]["result"]["block"]["summary"]["listed"][0].startswith(ids[-1])
    listed = _ok(rpc(h, "list_studies", {}))["studies"]
    assert [s["study_id"] for s in listed] == [sid] and listed[0]["finding"]
    # Re-running from the descriptor cache gives the same results.
    again = _ok(rpc(h, "run_study", {"study_id": sid}))
    assert [t["result"]["block"]["summary"] for t in again["tests"]] == [t["result"]["block"]["summary"] for t in ran["tests"]]
    exp = _ok(rpc(h, "export_study", {"study_id": sid}))
    assert exp["filename"] == "Takeoff-rpm-oscillation.eisstudy" and exp["size"] > 0
    data = h.download(exp["download_url"]) if isinstance(h, (InProcess, NodeHost)) else _http_download(h, exp["download_url"])
    assert _ok(rpc(h, "delete_study", {"study_id": sid}))["deleted"] == sid
    assert rpc(h, "load_study", {"study_id": sid})["error"]["code"] == "NOT_FOUND"
    imported = _ok(rpc(h, "import_study", {"content_base64": base64.b64encode(data).decode(), "filename": exp["filename"]}))
    assert not imported["read_only"] and sorted(imported["matched"]) == sorted(ids) and imported["missing"] == []
    rerun = _ok(rpc(h, "run_study", {"study_id": imported["study"]["study_id"]}))
    assert [t["result"]["block"]["summary"] for t in rerun["tests"]] == [t["result"]["block"]["summary"] for t in ran["tests"]]
    assert [t["result"]["finding"] for t in rerun["tests"]] == [t["result"]["finding"] for t in ran["tests"]]


def _http_download(base_url, path):
    import urllib.request
    with urllib.request.urlopen(f"{base_url}{path}", timeout=10) as resp:
        return resp.read()


def test_read_only_import_and_run_on_my_flights(research_ws):
    h, ids = research_ws
    sid = _ok(rpc(h, "save_study", {"study": {"name": "S", "slice_rules": [FULL_POWER],
                                              "tests": [{"test_id": "cycling", "channels": ["rpm"]}]}}))["study_id"]
    sent = _ok(rpc(h, "run_study", {"study_id": sid}))
    exp = _ok(rpc(h, "export_study", {"study_id": sid}))
    data = h.download(exp["download_url"]) if isinstance(h, (InProcess, NodeHost)) else _http_download(h, exp["download_url"])
    # A second workspace holding none of these flights.
    _ok(rpc(h, "create_workspace", {"name": "Other", "engine_model": "916iS"}))
    other = _import(h, "2026-02-01")
    got = _ok(rpc(h, "import_study", {"content_base64": base64.b64encode(data).decode(), "filename": "S.eisstudy"}))
    assert got["read_only"] and got["matched"] == [] and sorted(got["missing"]) == sorted(ids)
    st = got["study"]
    assert st["read_only"]["label"] == "sender's results; none of these flights are in this workspace"
    assert st["tests"][0]["result"]["finding"] == sent["tests"][0]["result"]["finding"]
    d = rpc(h, "run_study", {"study_id": st["study_id"]})
    assert not d["ok"] and d["error"]["code"] == "READ_ONLY"
    mine = _ok(rpc(h, "run_study_on_my_flights", {"study_id": st["study_id"]}))
    assert not mine.get("read_only") and mine["flights"] == [other]
    assert mine["tests"][0]["result"]["finding"].endswith("in 1 of 1 slice.")


def test_cli_json_is_the_operation_json(research_ws, capsys, monkeypatch):
    """Acceptance 7: the CLI prints exactly the operation's JSON."""
    h, _ids = research_ws
    if not isinstance(h, InProcess):
        pytest.skip("the CLI runs in process; compared once")
    from slingology_eis import cli
    expected = _ok(rpc(h, "run_test", {"test_id": "groups", "slice_rules": ["full_power"],
                                       "params": {"descriptor": "rpm.swing", "split": {"by": "date", "date": "2026-01-03"}}}))
    rc = cli.main(["research", "test", "groups", "--rule", "full_power", "--descriptor", "rpm.swing",
                   "--split-by", "date", "--date", "2026-01-03", "--json", "--quiet"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == serialize.dumps(expected)
    sig = _ok(rpc(h, "analyze_signal", {"flight_id": _ids[0], "window": {"start_s": FP_START, "end_s": FP_START + 30}}))
    assert cli.main(["research", "signal", _ids[0], "--window", f"{FP_START}:{FP_START + 30}", "--json", "--quiet"]) == 0
    assert capsys.readouterr().out.strip() == serialize.dumps(sig)
    cmp = _ok(rpc(h, "compare_rows", {"slice_rules": ["full_power"], "collapse": True}))
    assert cli.main(["research", "compare", "--rule", "full_power", "--collapse", "--json", "--quiet"]) == 0
    assert capsys.readouterr().out.strip() == serialize.dumps(cmp)
    presets = _ok(rpc(h, "list_slice_presets", {}))
    assert cli.main(["research", "presets", "--json", "--quiet"]) == 0
    assert capsys.readouterr().out.strip() == serialize.dumps(presets)


def test_research_changes_no_flight_fleet_or_insight_result(research_ws):
    """Spec 06 §15 acceptance 10: Research adds nothing to Flight view,
    Trends or Journal except through its explicit paths out (§10.3). The
    flights' analyses and insights, the fleet analysis and the Journal read
    the same before and after a study is built, run, noted and exported;
    only the study-finding entry the user asked for appears."""
    h, ids = research_ws
    def snapshot():
        flights = {fid: _ok(rpc(h, "get_flight", {"flight_id": fid})) for fid in ids}
        fleet = _ok(rpc(h, "get_fleet", {}))
        journal = [(e["kind"], e["ref_id"]) for e in _ok(rpc(h, "get_journal", {}))["entries"]]
        return json.dumps(flights, sort_keys=True), json.dumps(fleet, sort_keys=True), journal
    before = snapshot()
    saved = _ok(rpc(h, "save_study", {"study": {"name": "Untouched", "slice_rules": [FULL_POWER],
                                                "tests": [{"test_id": "cycling", "channels": ["rpm"]}]}}))
    sid = saved["study_id"]
    _ok(rpc(h, "run_study", {"study_id": sid}))
    _ok(rpc(h, "export_study", {"study_id": sid}))
    after = snapshot()
    assert after[0] == before[0] and after[1] == before[1] and after[2] == before[2]
    # §10.3: the one explicit path into the Journal, and its removal.
    entry = _ok(rpc(h, "note_study_finding", {"study_id": sid, "test_index": 0}))["entry"]
    assert entry["kind"] == "study_finding" and entry["ref_id"] == f"{sid}:0" and entry["what"].startswith("RPM cycles")
    assert entry["where"]["study_id"] == sid
    kinds = [(e["kind"], e["ref_id"]) for e in _ok(rpc(h, "get_journal", {}))["entries"]]
    assert kinds == before[2] + [("study_finding", f"{sid}:0")]
    assert _ok(rpc(h, "forget_study_finding", {"ref_id": f"{sid}:0"}))["removed"] is True
    assert [(e["kind"], e["ref_id"]) for e in _ok(rpc(h, "get_journal", {}))["entries"]] == before[2]
    assert rpc(h, "note_study_finding", {"study_id": sid, "test_index": 5})["error"]["code"] == "BAD_PARAMS"


def test_run_study_after_a_wider_build_reuses_the_cache(research_ws):
    """The study page builds slices for the view's channels, then runs a
    test on fewer: the cache holds more channels than the run asks for."""
    h, _ids = research_ws
    view = ["rpm", "map_inhg", "fuel_flow_gph"]
    sid = _ok(rpc(h, "save_study", {"study": {"name": "S", "selection": {"mode": "all"}, "slice_rules": ["full_power"],
                                              "tests": [{"test_id": "cycling", "params": {}, "channels": ["rpm"]}],
                                              "view": {"anchor": "crossing", "channels": view}}}))["study_id"]
    _ok(rpc(h, "build_slices", {"study_id": sid, "selection": {"mode": "all"}, "slice_rules": ["full_power"],
                                "channels": view}))
    for _ in range(2):
        ran = _ok(rpc(h, "run_study", {"study_id": sid}))
        assert ran["tests"][0]["result"]["finding"].endswith("in 6 of 6 slices.")


# ── v1.1: Signal view and Compare (Spec 06 §9.1–9.2) ───────────────────────

def _signal(h, fid, **params):
    return _ok(rpc(h, "analyze_signal", {"flight_id": fid, "channels": ["rpm", "map_inhg"], **params}))


def test_analyze_signal_strips_light_over_the_oscillation(research_ws):
    h, ids = research_ws
    r = _signal(h, ids[0])
    assert r["channels"] == ["rpm", "map_inhg"] and r["reference"] == "rpm"
    w = r["strip_windows"]["rpm"]
    assert w["window_s"] == 12 and w["basis"] == "period" and abs(w["flight_period_s"] - 4.4) < 0.5
    lit = r["strips"]["rpm"]["prominent"]
    inner = range(FP_START + 6, FP_START + FP_LEN - 6)
    assert sum(lit[i] for i in inner) >= 0.8 * len(inner)
    assert not any(lit[:FP_START - 6]) and not any(lit[FP_START + FP_LEN + 6:])
    assert len(r["values"]["rpm"]) == r["duration_s"] and r["phases"]


def test_a_strip_value_is_the_descriptor_of_that_window(research_ws):
    """D10: the strip at second i is what a slice of the strip's window
    centred there carries."""
    h, ids = research_ws
    r = _signal(h, ids[0])
    i = FP_START + 30
    a = i - 6
    hand = _ok(rpc(h, "build_slices", {"slice_rules": [], "channels": ["rpm"],
                                       "hand_slices": [{"flight": ids[0], "start_s": a, "end_s": a + 12}]}))
    d = hand["slices"][0]["descriptors"]["rpm"]
    st = r["strips"]["rpm"]
    assert (st["swing"][i], st["period_s"][i], st["prominence"][i], st["prominent"][i]) == \
        (d["swing"], d["period_s"], d["period_prominence"], d["period_prominent"])


def test_signal_window_numbers_diagnostics_and_derived_rule(research_ws):
    h, ids = research_ws
    win = {"start_s": FP_START, "end_s": FP_START + FP_LEN}
    r = _signal(h, ids[0], window=win)["window"]
    hand = _ok(rpc(h, "build_slices", {"slice_rules": [], "channels": ["rpm", "map_inhg"],
                                       "hand_slices": [{"flight": ids[0], **win}]}))["slices"][0]
    assert r["descriptors"] == hand["descriptors"]          # the same §6 code path as a hand slice
    assert r["windows"]["rpm"]["window_s"] == 12
    dg = r["diagnostics"]
    assert len(dg["rpm"]["detrended"]) == FP_LEN and dg["rpm"]["acf"] and dg["rpm"]["periodogram"]["period_s"]
    assert dg["map_inhg"]["best_lag_s"] == 0 and any(p["lag_s"] == 0 for p in dg["map_inhg"]["lag_curve"])
    assert all("references" in m for m in r["numbers"]["rpm"])
    rule = r["derived_rule"]
    assert rule["derived_from"] == {"flight": ids[0], "start_s": FP_START, "end_s": FP_START + FP_LEN, "channel": "rpm"}
    got = _ok(rpc(h, "build_slices", {"slice_rules": [rule], "channels": ["rpm"],
                                      "selection": {"mode": "flights", "flights": [ids[0]]}}))["slices"]
    assert len(got) == 1 and abs(got[0]["start_s"] - FP_START) <= 3 and abs(got[0]["end_s"] - FP_START - FP_LEN) <= 3


def test_analyze_signal_errors(research_ws):
    h, _ids = research_ws
    assert rpc(h, "analyze_signal", {"flight_id": "0000000000000000"})["error"]["code"] == "BAD_PARAMS"
    assert rpc(h, "analyze_signal", {})["error"]["code"] == "BAD_PARAMS"


def test_compare_rows_group_collapse_and_pin(research_ws):
    h, ids = research_ws
    base = {"slice_rules": ["full_power"], "channels": ["rpm", "map_inhg"]}
    c = _ok(rpc(h, "compare_rows", base))
    b = _ok(rpc(h, "build_slices", base))
    assert c["row_count"] == 6 and c["flight_count"] == 6 and c["flights_without"] == []
    assert [r["slice_id"] for r in c["rows"]] == [s["slice_id"] for s in b["slices"]]
    for r, s in zip(c["rows"], b["slices"]):
        for ch in ("rpm", "map_inhg"):
            assert r["values"][ch] == {k: s["descriptors"][ch][k] for k in r["values"][ch]}
    col = _ok(rpc(h, "compare_rows", {**base, "collapse": True}))
    assert col["collapsed"] and col["row_count"] == 6 and sum(r["count"] for r in col["rows"]) == 6
    low = next(r for r in c["rows"] if r["flight"] == ids[-1])
    p = _ok(rpc(h, "compare_rows", {**base, "pinned": low["row_id"]}))
    assert p["pinned"] == low["row_id"]
    others = [r for r in p["rows"] if not r["pinned"]]
    assert len(others) == 5 and all(r["delta"]["rpm"]["swing"] > 0 for r in others)
    assert rpc(h, "compare_rows", {**base, "pinned": "nope"})["error"]["code"] == "BAD_PARAMS"
    # A flight the rule finds nothing in is listed.
    _import(h, "2026-01-07", swing_rpm=90)
    hand = _ok(rpc(h, "compare_rows", {"slice_rules": [], "channels": ["rpm"],
                                       "hand_slices": [{"flight": ids[0], "start_s": FP_START, "end_s": FP_START + 20}],
                                       "selection": {"mode": "flights", "flights": [ids[0], ids[1]]}}))
    assert hand["row_count"] == 1 and [w["flight"] for w in hand["flights_without"]] == [ids[1]]


def test_study_keeps_signal_compare_and_derived_rule(research_ws):
    """Acceptance 18, engine side: a study with a Signal flight and window,
    a derived rule, a pinned row and one question reopens with all four,
    and the .eisstudy carries them."""
    h, ids = research_ws
    win = {"start_s": FP_START, "end_s": FP_START + FP_LEN}
    rule = _signal(h, ids[0], window=win)["window"]["derived_rule"]
    rows = _ok(rpc(h, "compare_rows", {"slice_rules": [rule], "channels": ["rpm"]}))["rows"]
    study = {"name": "Signal study", "slice_rules": [rule],
             "signal": {"flight": ids[0], "channels": ["rpm", "map_inhg"], "reference": "rpm", "window": win},
             "compare": {"pinned": rows[0]["row_id"], "collapse": False, "channels": ["rpm"],
                         "chart": {"x": "da_ft", "y": "rpm.swing", "colour": "source"}},
             "tests": [{"test_id": "cycling", "channels": ["rpm"]}]}
    sid = _ok(rpc(h, "save_study", {"study": study}))["study_id"]
    back = _ok(rpc(h, "load_study", {"study_id": sid}))
    assert back["signal"] == {**study["signal"], "window": {"start_s": float(FP_START), "end_s": float(FP_START + FP_LEN)}}
    assert back["compare"] == {**study["compare"], "reference": None}
    assert back["slice_rules"][0]["derived_from"] == rule["derived_from"] and len(back["tests"]) == 1
    exp = _ok(rpc(h, "export_study", {"study_id": sid}))
    data = h.download(exp["download_url"]) if isinstance(h, (InProcess, NodeHost)) else _http_download(h, exp["download_url"])
    imp = _ok(rpc(h, "import_study", {"content_base64": base64.b64encode(data).decode(), "filename": exp["filename"]}))
    st = imp["study"]
    assert st["signal"] == back["signal"] and st["compare"] == back["compare"]
    assert st["slice_rules"][0]["derived_from"] == rule["derived_from"]
    # Into a workspace without the flights: read-only, then Run this on my flights
    # keeps the channels and the derived rule, drops the sender's flight and pin.
    _ok(rpc(h, "create_workspace", {"name": "Other", "engine_model": "916iS"}))
    _import(h, "2026-02-01")
    ro = _ok(rpc(h, "import_study", {"content_base64": base64.b64encode(data).decode(), "filename": exp["filename"]}))
    assert ro["read_only"] and ro["study"]["signal"]["flight"] == ids[0]
    mine = _ok(rpc(h, "run_study_on_my_flights", {"study_id": ro["study"]["study_id"]}))
    assert mine["signal"]["flight"] is None and mine["signal"]["channels"] == ["rpm", "map_inhg"]
    assert mine["compare"]["pinned"] is None and mine["slice_rules"][0]["derived_from"]["flight"] == ids[0]


def test_analyze_signal_window_only(research_ws):
    """Compare's diagnostics panel asks for one row's window without the
    whole flight's strips or values."""
    h, ids = research_ws
    win = {"start_s": FP_START, "end_s": FP_START + FP_LEN}
    full = _signal(h, ids[0], window=win)
    lean = _signal(h, ids[0], window=win, include_strips=False, include_values=False)
    assert lean["strips"] == {} and lean["strip_windows"] == {} and "values" not in lean
    assert lean["window"] == full["window"]
