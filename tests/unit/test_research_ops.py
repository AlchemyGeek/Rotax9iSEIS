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

def _http_download(base_url, path):
    import urllib.request
    with urllib.request.urlopen(f"{base_url}{path}", timeout=10) as resp:
        return resp.read()

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
    Trends or Journal except through its explicit paths out. The flights'
    analyses and insights, the fleet analysis and the Journal read the same
    before and after the instrument runs (slices, a test, compare, a flight's
    signal) and a notebook is written and exported; only the study-finding
    entry asked for (`study_finish journal`) appears, and the Journal's
    Remove takes it away."""
    h, ids = research_ws
    def snapshot():
        flights = {fid: _ok(rpc(h, "get_flight", {"flight_id": fid})) for fid in ids}
        fleet = _ok(rpc(h, "get_fleet", {}))
        journal = [(e["kind"], e["ref_id"]) for e in _ok(rpc(h, "get_journal", {}))["entries"]]
        return json.dumps(flights, sort_keys=True), json.dumps(fleet, sort_keys=True), journal
    before = snapshot()
    _ok(rpc(h, "build_slices", {"slice_rules": [FULL_POWER], "channels": ["rpm"]}))
    _ok(rpc(h, "run_test", {"test_id": "cycling", "slice_rules": [FULL_POWER], "channels": ["rpm"]}))
    _ok(rpc(h, "compare_rows", {"slice_rules": [FULL_POWER], "channels": ["rpm"]}))
    _ok(rpc(h, "analyze_signal", {"flight_id": ids[0], "channels": ["rpm"], "include_values": False}))
    sid = _ok(rpc(h, "study_create", {"name": "Untouched", "question": "Does rpm cycle?"}))["study_id"]
    _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "markdown", "source": "A look."}}))
    _ok(rpc(h, "export_study", {"study_id": sid}))
    after = snapshot()
    assert after[0] == before[0] and after[1] == before[1] and after[2] == before[2]
    # The one explicit path into the Journal, and its removal.
    fin = _ok(rpc(h, "study_finish", {"study_id": sid, "summary": "RPM cycles at full power.", "journal": True}))
    entry = fin["journal_entry"]
    assert entry["kind"] == "study_finding" and entry["where"]["study_id"] == sid
    kinds = [(e["kind"], e["ref_id"]) for e in _ok(rpc(h, "get_journal", {}))["entries"]]
    assert kinds == before[2] + [("study_finding", entry["ref_id"])]
    assert _ok(rpc(h, "forget_study_finding", {"ref_id": entry["ref_id"]}))["removed"] is True
    assert [(e["kind"], e["ref_id"]) for e in _ok(rpc(h, "get_journal", {}))["entries"]] == before[2]
    # Spec 06 v1.0: the hand-study operations are gone.
    for op in ("save_study", "run_study", "note_study_finding"):
        assert rpc(h, op, {})["error"]["code"] in ("UNKNOWN_OP", "NOT_FOUND", "BAD_PARAMS"), op


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


def test_signal_window_numbers_and_diagnostics(research_ws):
    h, ids = research_ws
    win = {"start_s": FP_START, "end_s": FP_START + FP_LEN}
    r = _signal(h, ids[0], window=win)["window"]
    hand = _ok(rpc(h, "build_slices", {"slice_rules": [], "channels": ["rpm", "map_inhg"],
                                       "hand_slices": [{"flight": ids[0], **win}]}))["slices"][0]
    # The same §6 code path as a hand slice; the window adds F2's derived below_floor (not cached on slices).
    from slingology_eis.research.descriptors import below_floor
    assert {ch: {k: v for k, v in d.items() if k != "below_floor"} for ch, d in r["descriptors"].items()} \
        == hand["descriptors"]
    assert all(r["descriptors"][ch]["below_floor"] == below_floor(d) for ch, d in hand["descriptors"].items())
    assert r["windows"]["rpm"]["window_s"] == 12
    dg = r["diagnostics"]
    assert len(dg["rpm"]["detrended"]) == FP_LEN and dg["rpm"]["acf"] and dg["rpm"]["periodogram"]["period_s"]
    assert dg["map_inhg"]["best_lag_s"] == 0 and any(p["lag_s"] == 0 for p in dg["map_inhg"]["lag_curve"])
    assert all("references" in m for m in r["numbers"]["rpm"])
    assert "derived_rule" not in r                     # Spec 06 v1.0: the derived rule is retired


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

def test_analyze_signal_window_only(research_ws):
    """Compare's diagnostics panel asks for one row's window without the
    whole flight's strips or values."""
    h, ids = research_ws
    win = {"start_s": FP_START, "end_s": FP_START + FP_LEN}
    full = _signal(h, ids[0], window=win)
    lean = _signal(h, ids[0], window=win, include_strips=False, include_values=False)
    assert lean["strips"] == {} and lean["strip_windows"] == {} and "values" not in lean
    assert lean["window"] == full["window"]


def test_skip_onset_s_leaves_the_ramp_out_and_the_caveat_suggests_it(research_ws):
    """Spec 16 §3.2 F4: a window that opens on the power change carries a
    caveat naming a skip; with it the cycle's period comes back, and the
    window itself is unchanged."""
    h, ids = research_ws
    win = {"start_s": FP_START - 15, "end_s": FP_START + FP_LEN}
    plain = _signal(h, ids[0], window=win, include_strips=False, include_values=False)["window"]
    assert plain["skip_onset_s"] == 0
    cav = [c for c in plain["caveats"] if "Try skip_onset_s=" in c]
    assert cav, plain["caveats"]
    skip = int(cav[0].rsplit("=", 1)[1].rstrip("."))
    assert 14 <= skip <= 22
    got = _signal(h, ids[0], window=win, skip_onset_s=skip, include_strips=False, include_values=False)["window"]
    assert (got["start_s"], got["end_s"], got["skip_onset_s"]) == (win["start_s"], win["end_s"], skip)
    rpm = got["descriptors"]["rpm"]
    assert rpm["period_prominent"] and abs(rpm["period_s"] - 4.4) < 0.5 and rpm["below_floor"] is False
    assert any("left out of the descriptors" in c for c in got["caveats"])
    bad = rpc(h, "analyze_signal", {"flight_id": ids[0], "window": win, "skip_onset_s": FP_LEN + 10})
    assert bad["error"]["code"] == "BAD_PARAMS" and "fewer than 8 seconds" in bad["error"]["message"]


def test_groups_split_shorthand_over_rpc(research_ws):
    h, _ids = research_ws
    # Every synthetic flight is G3X: the shorthand answers exactly as {"by": "source"} does.
    run = lambda split: rpc(h, "run_test", {"test_id": "groups", "slice_rules": [FULL_POWER],  # noqa: E731
                                            "params": {"descriptor": "rpm.swing", "split": split}})
    short, full = run("source"), run({"by": "source"})
    assert short == full and "fewer than two non-empty groups" in short["error"]["message"]
    bad = rpc(h, "run_test", {"test_id": "groups", "slice_rules": [FULL_POWER],
                              "params": {"descriptor": "rpm.swing", "split": "colour"}})
    assert bad["error"]["code"] == "BAD_PARAMS" and "da_band" in bad["error"]["message"]
