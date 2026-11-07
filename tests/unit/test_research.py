"""
Spec 06 Research — the engine pieces on synthetic data: slice rules
(§5.1, §5.3, §5.4), descriptors and the §7.0 window rule (§6), the four
tests and the §8 contract (§7.1–7.4), presets (§5.2) and studies (§10).
The real-data acceptance case is tests/contract/test_research_acceptance.py.
"""
import json
import math

import numpy as np
import pytest

from slingology_eis.limits import load_engine_config
from slingology_eis.research import descriptors as D
from slingology_eis.research import presets as P
from slingology_eis.research import questions as Q
from slingology_eis.research import studies as S
from slingology_eis.research.render import check_no_verdicts, evidence_csv, chart_svg, render_text, verdict_words
from slingology_eis.research.rules import (
    RuleError, apply_rule, describe_rule, normalise_hand_slice, normalise_rule, phase_rule, rule_hash,
)


# ── Rules (§5.1, §5.3, §5.4) ───────────────────────────────────────────────

def _rule(**kw):
    base = {"conditions": [{"channel": "rpm", "op": ">=", "value": 5550}], "min_duration_s": 15, "merge_gap_s": 3}
    return normalise_rule({**base, **kw})


def test_rule_validation():
    with pytest.raises(RuleError):
        normalise_rule({"conditions": [{"channel": "nope", "op": ">=", "value": 1}]})
    with pytest.raises(RuleError):
        normalise_rule({"conditions": [{"channel": "rpm", "op": "~", "value": 1}]})
    with pytest.raises(RuleError):
        normalise_rule({"conditions": [{"channel": "rpm", "op": "between", "min": 5, "max": 1}]})
    with pytest.raises(RuleError):
        normalise_rule({"conditions": []})
    r = normalise_rule({"conditions": [{"channel": "rpm", "op": "≥", "value": "5550"}]})
    assert r["conditions"][0] == {"channel": "rpm", "op": ">=", "value": 5550}
    assert r["rule_id"].startswith("r-") and r["pad_s"] == 0


def test_rule_hash_ignores_name():
    a = _rule(rule_id="a", name="A")
    b = _rule(rule_id="b", name="B")
    assert rule_hash(a) == rule_hash(b)
    assert rule_hash(a) != rule_hash(_rule(min_duration_s=20))


def test_apply_rule_merge_gap_min_duration_and_crossing():
    n = 200
    rpm = np.full(n, 5000.0)
    rpm[20:40] = 5600          # 20 s
    rpm[40:42] = 5400          # 2 s dip: bridged (shorter than 3 s)
    rpm[42:50] = 5600
    rpm[100:110] = 5600        # 10 s: too short
    rpm[150:170] = 5600
    rpm[170:173] = 5400        # 3 s dip: not bridged
    rpm[173:190] = 5600
    wins, missing = apply_rule(_rule(), {"rpm": rpm}, [], n)
    assert missing == []
    assert [(w["start_s"], w["end_s"], w["anchor_s"]) for w in wins] == [(20, 50, 20), (150, 170, 150), (173, 190, 173)]


def test_apply_rule_pad_and_missing_channel():
    rpm = np.full(100, 5000.0)
    rpm[30:60] = 5600
    wins, _ = apply_rule(_rule(pad_s=5), {"rpm": rpm}, [], 100)
    assert wins == [{"start_s": 25, "end_s": 65, "anchor_s": 30}]
    wins, missing = apply_rule(_rule(), {}, [], 100)
    assert wins == [] and missing == ["rpm"]


def test_phase_constraint_and_phase_rule():
    n = 100
    rpm = np.full(n, 5600.0)
    phases = [{"phase": "TAKEOFF_ROLL", "start_s": 0, "end_s": 30}, {"phase": "CLIMB", "start_s": 30, "end_s": 70},
              {"phase": "CRUISE", "start_s": 70, "end_s": 100}]
    within = _rule(phase={"mode": "within", "phases": ["CLIMB"]})
    assert apply_rule(within, {"rpm": rpm}, phases, n)[0] == [{"start_s": 30, "end_s": 70, "anchor_s": 30}]
    overlap = _rule(phase={"mode": "overlap", "phases": ["CLIMB"]})
    assert apply_rule(overlap, {"rpm": rpm}, phases, n)[0] == [{"start_s": 0, "end_s": 100, "anchor_s": 0}]
    pr = phase_rule("cruise")
    assert pr["rule_id"] == "phase:CRUISE" and pr["conditions"] == []
    assert apply_rule(pr, {}, phases, n)[0] == [{"start_s": 70, "end_s": 100, "anchor_s": 70}]


def test_hand_slice_carries_offset():
    h = normalise_hand_slice({"flight": "abc", "start_s": 10, "end_s": 40})
    assert h["offset_s"] == 0 and h["label"] == "10–40 s"
    with pytest.raises(RuleError):
        normalise_hand_slice({"flight": "abc", "start_s": 40, "end_s": 10})


def test_describe_rule_reads_like_a_sentence():
    assert describe_rule(_rule()) == "RPM ≥ 5550, for ≥ 15 s (dips shorter than 3 s bridged)"


# ── Descriptors (§6) and windows (§7.0) ────────────────────────────────────

def _oscillation(n=60, period=4.4, amp=90.0, level=5700.0, phase=0.0):
    t = np.arange(n)
    return level + amp * np.sin(2 * np.pi * t / period + phase)


def test_dominant_period_finds_a_sampled_oscillation():
    d = D.dominant_period(_oscillation(period=4.4))
    assert d["period_prominent"] and abs(d["period_s"] - 4.4) < 0.35 and abs(d["period_ls_s"] - 4.4) < 0.2


def test_noise_and_trend_have_no_prominent_period():
    rng = np.random.default_rng(1)
    assert not D.dominant_period(5700 + rng.normal(0, 30, 80))["period_prominent"]
    assert not D.dominant_period(np.linspace(5600, 5800, 80))["period_prominent"]


def test_period_below_the_sampling_floor_is_never_prominent():
    d = D.dominant_period(_oscillation(period=2.5, n=80))
    assert not d["period_prominent"]


def test_filled_rows_are_excluded_from_period_and_rate():
    y = _oscillation()
    filled = np.zeros(len(y), dtype=bool)
    y2 = y.copy()
    y2[10] = 9000          # a filled-in sample far off: ignored by rate
    filled[10] = True
    d = D.describe_channel(y2, filled, 0, 12)
    assert d["max_rate_per_s"] < 200
    assert d["max"] == 9000      # level descriptors keep it


def test_swing_is_peak_to_peak_over_the_window():
    s = D.swing(_oscillation(amp=90, period=4.0), 12)
    assert 170 <= s <= 180.1


def test_coupling_finds_lag():
    ref = _oscillation(n=80)
    follower = np.roll(ref, 1)          # one second behind
    c = D.coupling(ref, follower, 10)
    assert c["lag_s"] == 1 and c["corr_at_lag"] > 0.95
    assert D.coupling(ref, ref, 10)["lag_s"] == 0


def test_window_rule_floors_period_and_duration():
    prom = [{"period_s": 4.4, "period_prominent": True}] * 10
    w = D.resolve_window(prom, [60] * 10)
    assert (w["window_s"], w["lag_s"], w["basis"]) == (12, 10, "period")       # 2.5 × 4.4 = 11 → floor 12; 1.5 × 4.4 → floor 10
    long = [{"period_s": 10.0, "period_prominent": True}] * 10
    w = D.resolve_window(long, [120] * 10)
    assert (w["window_s"], w["lag_s"]) == (25, 15)
    flat = [{"period_s": None, "period_prominent": False}] * 10
    w = D.resolve_window(flat, [700] * 10)
    assert (w["window_s"], w["lag_s"], w["basis"]) == (140, 70, "duration")
    w = D.resolve_window(flat, [700] * 10, {"window_s": 30})
    assert w["window_s"] == 30 and w["basis"] == "override"


# ── Tests and the §8 contract (§7.1–7.4) ───────────────────────────────────

def _fake_slice(i, source="G3X", swing=180.0, period=4.4, prominent=True, corr=0.9, lag=0, da=1000, ff_lag=1):
    rpm = {"samples": 60, "median": 5700.0, "max": 5790.0, "min": 5610.0, "swing": swing, "sd": 60.0,
           "slope_per_min": 1.0, "max_rate_per_s": 100.0, "period_s": period, "period_prominence": 0.6,
           "period_prominent": prominent}
    mp = {"samples": 60, "median": 48.0, "max": 50.0, "min": 46.0, "swing": 5.0 if source == "AXIS" else 1.7,
          "sd": 1.0, "slope_per_min": 0.1, "max_rate_per_s": 1.0, "corr0": corr, "lag_s": lag, "corr_at_lag": corr,
          "period_prominent": False}
    ff = dict(mp, corr0=0.1, lag_s=ff_lag, corr_at_lag=0.5, swing=1.0)
    return {"slice_id": f"f{i}:r:0-60", "flight": f"f{i:03d}", "label": "Full-power", "kind": "rule", "rule_id": "fp",
            "start_s": 0, "end_s": 60, "anchor_s": 0,
            "context": {"source": source, "da_ft": da, "oat_c": 15.0, "engine_hours": 50.0 + i, "phases": ["CLIMB"],
                        "start_time": f"2026-07-{1 + i % 28:02d} 12:{i % 60:02d}:00"},
            "quality": {"duration_s": 60, "filled_share": 0.0},
            "descriptors": {"rpm": rpm, "map_inhg": mp, "fuel_flow_gph": ff}}


def _fake_set(slices):
    w = {"window_s": 12, "lag_s": 10, "basis": "period", "median_period_s": 4.4, "median_duration_s": 60.0}
    return {"slices": slices, "count": len(slices), "by_source": {}, "reference": "rpm",
            "windows": {"rpm": w, "map_inhg": dict(w, basis="duration"), "fuel_flow_gph": dict(w, basis="duration")},
            "selection": {"mode": "all"}, "rules": [], "hand_slices": [], "flights_selected": len(slices),
            "missing_flights": [], "unreachable_flights": []}


CFG = load_engine_config("916iS")


def test_cycling_finding_carries_recurrence_and_source_split():
    slices = [_fake_slice(i) for i in range(20)] + [_fake_slice(20 + i, source="AXIS") for i in range(5)]
    slices += [_fake_slice(40, swing=70, prominent=False)]
    r = Q.run("cycling", _fake_set(slices), channels=["rpm"], engine_cfg=CFG,
              references=[{"label": "Governing band", "channel": "rpm", "value": 100, "kind": "band", "source": "manual"}])
    assert r["finding"].startswith("RPM cycles every 4.4 s")
    assert "in 25 of 26 slices (AXIS 5 of 5, G3X 20 of 21)" in r["finding"]
    kinds = [ref["kind"] for ref in r["magnitude"][0]["references"]]
    assert kinds == ["om", "set", "user"]
    assert "±100 rpm (200 rpm wide)" in r["magnitude"][0]["references"][2]["text"]
    assert any("swing window 12 s, lag range ±10 s" in c for c in r["caveats"])
    assert r["caveats"][-1] == Q.DOES_NOT_MEAN["cycling"]
    assert r["block"]["params"]["windows"]["rpm"]["window_s"] == 12
    assert check_no_verdicts(r) == []


def test_coupling_reports_per_source_with_damping_caveat():
    slices = [_fake_slice(i, corr=0.1, lag=1) for i in range(20)] + [_fake_slice(30 + i, source="AXIS") for i in range(10)]
    r = Q.run("coupling", _fake_set(slices), channels=["rpm", "map_inhg", "fuel_flow_gph"], engine_cfg=CFG)
    assert "MAP follows RPM with no delay on AXIS slices" in r["finding"]
    assert "1 s behind on G3X slices" in r["finding"]
    assert "Fuel Flow follows RPM 1 s behind" in r["finding"]
    assert [m["source"] for m in r["magnitude"][:2]] == ["AXIS", "G3X"]
    assert any("damped" in c and "MAP" in c for c in r["caveats"])
    assert r["caveats"][-1] == Q.DOES_NOT_MEAN["coupling"]
    assert check_no_verdicts(r) == []


def test_groups_small_group_caution_and_effect_size():
    slices = [_fake_slice(i, da=1000) for i in range(30)] + [_fake_slice(50 + i, da=6200, swing=75) for i in range(2)]
    r = Q.run("groups", _fake_set(slices), params={"descriptor": "rpm.swing", "split": {"by": "da_band", "edges": [3500, 6000]}},
              engine_cfg=CFG)
    assert "180 rpm below 3,500 ft DA (30 slices)" in r["finding"]
    assert "75 rpm at 6,000 ft DA and above (2 slices — small group)" in r["finding"]
    g = r["block"]["summary"]["groups"]["at 6,000 ft DA and above"]
    assert g["small_group"] and g["cliffs_delta"] == -1.0 and g["median_difference"] == -105
    assert any("n_min" in c for c in r["caveats"])
    assert r["block"]["params"]["n_min"] == Q.N_MIN == 10
    assert check_no_verdicts(r) == []


def test_unusual_ranks_the_slice_that_differs():
    slices = [_fake_slice(i, swing=175.0 + (i % 5) * 3) for i in range(30)]
    slices.append(_fake_slice(99, swing=70.0))
    r = Q.run("unusual", _fake_set(slices), channels=["rpm"], engine_cfg=CFG)
    assert r["block"]["summary"]["listed"][0] == "f99:r:0-60"
    assert r["block"]["per_slice"][0]["descriptor"] == "rpm.swing"
    assert "difference, not wrongness" in r["caveats"][-1]
    assert check_no_verdicts(r) == []


def test_unknown_test_and_descriptor():
    with pytest.raises(RuleError):
        Q.run("magic", _fake_set([_fake_slice(1)]))
    with pytest.raises(RuleError):
        Q.run("unusual", _fake_set([_fake_slice(i) for i in range(6)]), params={"descriptors": ["nope"]})


def test_rendering_and_verdict_check():
    assert verdict_words("This is abnormal and a fault") == ["abnormal", "fault"]
    assert verdict_words("Normal G cycles every 3 s") == []
    r = Q.run("cycling", _fake_set([_fake_slice(i) for i in range(12)]), channels=["rpm"], engine_cfg=CFG)
    text = render_text(r)
    assert r["finding"] in text and "beside:" in text
    bad = dict(r, finding="RPM is abnormal.")
    assert check_no_verdicts(bad)
    assert evidence_csv(r).splitlines()[0].startswith("slice_id,Start (local),Source")
    assert chart_svg(r).startswith("<svg")


# ── Presets (§5.2) ─────────────────────────────────────────────────────────

def test_presets_916is_measured_and_other_profiles_unverified():
    p = P.list_presets("916iS", CFG)
    assert p["status"] == "measured" and p["note"] is None
    ids = [x["rule_id"] for x in p["presets"]]
    assert ids == ["full_power", "governed_climb", "stable_cruise", "idle", "warm_up"]
    fp = p["presets"][0]
    assert fp["conditions"] == [{"channel": "rpm", "op": ">=", "value": 5550}]
    assert (fp["min_duration_s"], fp["merge_gap_s"]) == (15, 3) and fp["from_preset"] == "full_power"
    warm = p["presets"][-1]
    assert warm["conditions"][1] == {"channel": "oil_temp_f", "op": "<", "value": 122.0}
    assert warm["value_sources"] == {"oil_temp_f": "profile limit oil_temp_takeoff_min"}
    other = P.list_presets("912iS", load_engine_config("912iS"))
    assert other["status"] == "unverified" and all(x["status"] == "unverified" for x in other["presets"])
    assert "phase:CLIMB" in [r["rule_id"] for r in p["phase_rules"]]


# ── Studies (§10) ──────────────────────────────────────────────────────────

def _study():
    return {"name": "Takeoff rpm oscillation",
            "slice_rules": [{"rule_id": "full_power", "from_preset": "full_power",
                             "conditions": [{"channel": "rpm", "op": ">=", "value": 5550}],
                             "min_duration_s": 15, "merge_gap_s": 3}],
            "hand_slices": [{"flight": "aaaaaaaaaaaaaaaa", "start_s": 0, "end_s": 30, "label": "KBLI"}],
            "references": [{"label": "Governing band", "channel": "rpm", "value": 100, "kind": "band", "source": "manual"}],
            "tests": [{"test_id": "cycling", "channels": ["rpm"]}],
            "notes": "n"}


def test_study_save_load_list_delete(tmp_path):
    doc = S.save(tmp_path, _study(), engine_model="916iS")
    assert doc["study_id"].startswith("st-") and doc["provenance"]["engine_model"] == "916iS"
    assert doc["hand_slices"][0]["offset_s"] == 0
    assert (tmp_path / "studies" / f"{doc['study_id']}.json").is_file()
    assert S.load(tmp_path, doc["study_id"])["name"] == "Takeoff rpm oscillation"
    assert [s["study_id"] for s in S.list_all(tmp_path)] == [doc["study_id"]]
    assert S.delete(tmp_path, doc["study_id"]) and S.list_all(tmp_path) == []
    with pytest.raises(S.StudyError):
        S.load(tmp_path, "../../etc/passwd")


def test_study_import_read_only_without_flights_and_run_on_my_flights(tmp_path):
    doc = S.normalise(_study())
    doc["study_id"] = "st-0123456789ab"
    doc["flights"] = ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"]
    sent = Q.run("cycling", _fake_set([_fake_slice(i) for i in range(12)]), channels=["rpm"], engine_cfg=CFG)
    doc["tests"][0]["result"] = sent
    data = S.export_bytes(doc)
    got = S.import_bytes(tmp_path, data, engine_model="916iS")
    assert got["read_only"] and got["matched"] == [] and set(got["missing"]) == set(doc["flights"])
    st = got["study"]
    assert st["read_only"]["label"] == S.READ_ONLY_LABEL
    assert st["tests"][0]["result"] == sent       # the sender's cached results, as sent
    with pytest.raises(S.StudyError) as e:
        S.save(tmp_path, st)
    assert e.value.code == "READ_ONLY"
    mine = S.for_my_flights(st)
    assert mine["selection"]["mode"] == "all" and mine["hand_slices"] == [] and "result" not in mine["tests"][0]
    assert mine["slice_rules"] == st["slice_rules"] and mine["references"] == st["references"]


def test_study_import_with_some_flights_pins_them(tmp_path):
    (tmp_path / "flights" / "aaaaaaaaaaaaaaaa").mkdir(parents=True)
    doc = S.normalise(_study())
    doc["flights"] = ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"]
    doc["tests"][0]["result"] = Q.run("cycling", _fake_set([_fake_slice(i) for i in range(12)]), channels=["rpm"], engine_cfg=CFG)
    got = S.import_bytes(tmp_path, S.export_bytes(doc))
    assert not got["read_only"] and got["matched"] == ["aaaaaaaaaaaaaaaa"] and got["missing"] == ["bbbbbbbbbbbbbbbb"]
    st = got["study"]
    assert st["selection"] == {"mode": "flights", "flights": ["aaaaaaaaaaaaaaaa"], "split": None}
    assert "result" not in st["tests"][0]          # recomputed here, never shown as this workspace's


def test_eisstudy_is_a_zip_with_evidence(tmp_path):
    import io, zipfile
    slices = [_fake_slice(i) for i in range(12)]
    r = Q.run("cycling", _fake_set(slices), channels=["rpm"], engine_cfg=CFG)
    doc = S.normalise(_study())
    doc["tests"][0]["result"] = r
    with zipfile.ZipFile(io.BytesIO(S.export_bytes(doc))) as z:
        names = z.namelist()
        assert names == ["study.json", "evidence/01-cycling.csv", "charts/01-cycling.svg"]
        assert json.loads(z.read("study.json"))["format"] == "eisstudy"
    with pytest.raises(S.StudyError):
        S.parse_export(b"not a zip")
