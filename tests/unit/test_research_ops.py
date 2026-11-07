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
