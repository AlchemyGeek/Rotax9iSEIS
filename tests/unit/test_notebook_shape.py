"""
Spec 16 D19 §5.6 (v1.7) — the notebook's shape and cell roles, run the
three ways every host operation is (in process, over HTTP, under Pyodide in
Node.js; the bench parts where a bench exists). Synthetic flights only.

- study_create writes the seven sections; cells land in their section;
  study_followup opens a dated follow-up; cell_edit re-roles and moves.
- study_finish takes the structured top, writes sections 1–3 as generated
  markdown (JupyterLab shows the same text), keeps the previous top in
  history, and makes shows[0] the Journal's line; the card counts actions.
- Acceptance 26: plain text in an evidence cell is refused, a support cell
  with nothing after it is named, scratch cells move under *Working*.
- eis.table / eis.figure / eis.logview(caption=) emit evidence outputs.
- An older notebook gets roles on first load, nothing moved; its sections
  come with the first structured finish.
"""
import json

import pytest

from slingology_eis.investigations import evidence as EV
from tests.unit.test_investigations_ops import _bench_stack, _has_bench, _notebook, _rule_literal, _sm
from tests.unit.test_research_ops import _ok, research_ws  # noqa: F401 — fixture
from tests.unit.test_server import (  # noqa: F401 — fixtures
    NodeHost, _node_host, isolated_packaged_home, registry_server, rpc,
)


def _cells(h, sid):
    return _ok(rpc(h, "load_study", {"study_id": sid}))["notebook"]["cells"]


def _layout(h, sid):
    """[(id, role, section)] in notebook order; sections by their headings."""
    out, cur = [], None
    for c in _cells(h, sid):
        sm = _sm(c)
        if sm.get("role") == "section":
            cur = sm["section"]
        out.append((c["id"], sm.get("role"), cur))
    return out


def _append(h, sid, **cell):
    return _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": cell}))["cell"]


TOP = {"question_scope": "- 6 flights, Jan 2026\n- OM limits as the profile gives them",
       "shows": ["RPM swings 90 rpm at full power on 5 of 6 flights (Table 1).", "The sixth swings 30 rpm."],
       "means": "The governor is the hypothesis; moderate confidence.",
       "actions": [{"what": "Ask the shop to check the governor", "who": "A&P",
                    "settles": "whether the governor hunts", "recheck_after_flights": 10}]}


def test_study_create_writes_the_seven_sections(research_ws):
    h, _ids = research_ws
    sid = _notebook(h)
    cells = _cells(h, sid)
    heads = [(c["id"], _sm(c).get("section"), bool(_sm(c).get("generated"))) for c in cells if _sm(c).get("role") == "section"]
    assert heads == [("s1", 1, True), ("s2", 2, True), ("s3", 3, True), ("s4", 4, False), ("s5", 5, False),
                     ("s6", 6, False), ("s7", 7, False)]
    s1 = "".join(cells[1]["source"])
    assert s1.startswith("# Why does rpm cycle?\n\n## 1 The question\n\nWhy does rpm cycle at full power?")
    assert "*Written when the notebook is finished.*" in "".join(cells[2]["source"])
    assert [ "".join(c["source"]).strip() for c in cells[4:]] == [
        "## 4 Findings", "## 5 How this was done", "## 6 Follow-ups", "## 7 Working"]


def test_cells_land_in_their_section_and_cell_edit_moves_them(research_ws):
    h, _ids = research_ws
    sid = _notebook(h)
    plan = _append(h, sid, kind="markdown", source="Plan: one flight first.", section=5)
    finding = _append(h, sid, kind="markdown", source="RPM swings.")
    note = _append(h, sid, kind="markdown", source="Columns?", role="scratch")
    assert [_sm(c)["role"] for c in (plan, finding, note)] == ["narrative", "narrative", "scratch"]
    lay = {cid: sec for cid, _r, sec in _layout(h, sid)}
    assert (lay[plan["id"]], lay[finding["id"]], lay[note["id"]]) == (5, 4, 7)
    bad = rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "markdown", "source": "x", "role": "evidence"}})
    assert not bad["ok"] and "evidence is a code cell" in bad["error"]["message"]
    bad = rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "markdown", "source": "x", "section": 2}})
    assert not bad["ok"] and "study_finish" in bad["error"]["message"]
    # cell_edit: a role, a section, a markdown cell's text; EIS's own cells refused.
    moved = _ok(rpc(h, "study_cell_edit", {"study_id": sid, "cell_id": note["id"], "role": "narrative", "section": 5}))
    assert moved["section"] == 5 and _sm(moved["cell"])["role"] == "narrative"
    _ok(rpc(h, "study_cell_edit", {"study_id": sid, "cell_id": finding["id"], "source": "RPM swings 90 rpm."}))
    assert "".join(next(c for c in _cells(h, sid) if c["id"] == finding["id"])["source"]) == "RPM swings 90 rpm."
    for cid in ("setup", "s1", "s4"):
        assert not rpc(h, "study_cell_edit", {"study_id": sid, "cell_id": cid, "role": "scratch"})["ok"]
    assert not rpc(h, "study_cell_edit", {"study_id": sid, "cell_id": finding["id"]})["ok"]       # nothing to change


def test_a_follow_up_is_dated_and_ends_with_what_changed(research_ws):
    h, _ids = research_ws
    sid = _notebook(h)
    _append(h, sid, kind="markdown", source="RPM swings.")
    _ok(rpc(h, "study_finish", {"study_id": sid, **TOP}))
    fu = _ok(rpc(h, "study_followup", {"study_id": sid, "date": "2026-11-27", "title": "Is phase a factor?"}))
    assert fu["status"] == "open" and "".join(fu["cell"]["source"]).strip() == "### Follow-up — 2026-11-27: Is phase a factor?"
    assert not rpc(h, "study_followup", {"study_id": sid})["ok"]                   # one open at a time
    later = _append(h, sid, kind="markdown", source="Climb is 13% of the time above.")
    lay = _layout(h, sid)
    assert [cid for cid, _r, sec in lay if sec == 6][1:] == [fu["cell"]["id"], later["id"]]
    no = rpc(h, "study_finish", {"study_id": sid, **TOP})
    assert not no["ok"] and "changed" in no["error"]["message"]
    again = {**TOP, "shows": ["Climb is 13% of its time above 46 psi."] + TOP["shows"][1:]}
    _ok(rpc(h, "study_finish", {"study_id": sid, **again, "changed": "Answer: the first bullet."}))
    six = [c for c in _cells(h, sid) if c["id"] in {cid for cid, _r, sec in _layout(h, sid) if sec == 6}]
    assert "".join(six[-1]["source"]).strip() == "**What changed above:** Answer: the first bullet."
    m = _ok(rpc(h, "load_study", {"study_id": sid}))["notebook"]["metadata"]["slingology"]
    assert m["top"]["shows"][0] == "Climb is 13% of its time above 46 psi." and "followup" not in m
    assert [e["shows"][0] for e in m["history"]] == [TOP["shows"][0]] and m["history"][0]["finished"][:2] == "20"
    assert m["finding"] == "Climb is 13% of its time above 46 psi."
    # New text in a finished notebook opens a follow-up itself, dated today.
    _append(h, sid, kind="markdown", source="One more look.")
    assert _ok(rpc(h, "load_study", {"study_id": sid}))["notebook"]["metadata"]["slingology"].get("followup")


def test_the_structured_top_is_sections_1_to_3(research_ws):
    h, _ids = research_ws
    sid = _notebook(h)
    _append(h, sid, kind="markdown", source="RPM swings.")
    bad = rpc(h, "study_finish", {"study_id": sid, "shows": ["a", "b", "c", "d", "e", "f"]})
    assert not bad["ok"] and "3–5" in bad["error"]["message"]
    bad = rpc(h, "study_finish", {"study_id": sid, "shows": ["a"], "actions": [{"who": "A&P"}]})
    assert not bad["ok"] and "what" in bad["error"]["message"]
    assert not rpc(h, "study_finish", {"study_id": sid})["ok"]                       # no Answer, no summary
    fin = _ok(rpc(h, "study_finish", {"study_id": sid, **TOP, "journal": True, "finding": "ignored"}))
    assert fin["journal_entry"]["what"] == TOP["shows"][0]                          # finding = shows[0]
    assert fin["study"]["card"]["actions"] == 1 and fin["study"]["summary"] == TOP["means"]
    cells = _cells(h, sid)
    s1, s2, s3 = ("".join(c["source"]) for c in cells[1:4])
    assert "**Scope and qualifications**\n\n- 6 flights, Jan 2026" in s1
    assert "**What the data shows**\n\n- RPM swings 90 rpm at full power on 5 of 6 flights (Table 1).\n- The sixth" in s2
    assert "**What it means**\n\nThe governor is the hypothesis; moderate confidence." in s2
    assert s3.strip() == ("## 3 Proposed actions\n\n1. **Ask the shop to check the governor** · A&P · settles: whether "
                          "the governor hunts · re-check after the next 10 flights")
    assert all(_sm(c).get("generated") for c in cells[1:4])
    # None is an answer to actions.
    sid2 = _notebook(h, "Nothing to do")
    _append(h, sid2, kind="markdown", source="Normal.")
    fin = _ok(rpc(h, "study_finish", {"study_id": sid2, "shows": ["Normal on every flight."], "means": "Normal.",
                                      "actions": [], "actions_none": "Nothing here departs from the OM."}))
    assert fin["study"]["card"]["actions"] == 0
    assert "None. Nothing here departs from the OM." in "".join(_cells(h, sid2)[3]["source"])


def test_acceptance_26_roles_enforced(research_ws):
    h, _ids = research_ws
    if not _has_bench(h):
        pytest.skip("no bench under Pyodide")
    _bench_stack()
    sid = _notebook(h)
    look = _ok(rpc(h, "code_run", {"study_id": sid, "source": "print(eis.slices('full_power').columns.tolist())",
                                   "role": "scratch"}))["cell"]
    calc = _ok(rpc(h, "code_run", {"study_id": sid, "source": f"s = eis.slices({_rule_literal()}, ['rpm'])\nlen(s)"}))["cell"]
    assert _sm(calc)["role"] == "support"
    ev = _ok(rpc(h, "code_run", {"study_id": sid, "role": "evidence",
                                 "source": f"s = eis.slices({_rule_literal()}, ['rpm'])\nprint(len(s))"}))["cell"]
    fl = rpc(h, "study_finish", {"study_id": sid, **TOP})
    assert not fl["ok"] and f"evidence cell {ev['id']} shows plain text" in fl["error"]["message"]
    tbl = (f"s = eis.slices({_rule_literal()}, ['rpm'])\n"
           "eis.table(s[['flight_id', 'duration_s', 'rpm.swing']], caption='Full-power slices', units={'rpm.swing': 'rpm'})")
    ev = _ok(rpc(h, "code_run", {"study_id": sid, "cell_id": ev["id"], "source": tbl}))["cell"]
    out = ev["outputs"][-1]
    assert out["metadata"]["slingology"]["evidence"] == {"kind": "table", "caption": "Full-power slices",
                                                          "units": {"rpm.swing": "rpm"}}
    assert "<th>Duration (s)</th>" in out["data"]["text/html"] and "<th>Engine RPM swing</th>" in out["data"]["text/html"]
    assert out["data"]["text/html"].startswith('<table class="eis-table"><caption>Full-power slices</caption>')
    # The calc cell before the evidence is fine; a support cell with nothing after it is named.
    tail = _ok(rpc(h, "code_run", {"study_id": sid, "source": "1 + 1"}))["cell"]
    fl = rpc(h, "study_finish", {"study_id": sid, **TOP})
    assert not fl["ok"] and f"support cell {tail['id']} has nothing after it" in fl["error"]["message"]
    assert calc["id"] not in fl["error"]["message"]
    _ok(rpc(h, "study_cell_edit", {"study_id": sid, "cell_id": tail["id"], "role": "scratch"}))
    # A figure and a log view with captions are evidence; scratch moves under Working at finish.
    _ok(rpc(h, "code_run", {"study_id": sid, "role": "evidence", "source":
            "fig, ax = plt.subplots(); ax.plot([1, 2]); eis.figure(fig, caption='A line')"}))
    _ok(rpc(h, "study_cells_append", {"study_id": sid, "cell": {"kind": "logview", "flight": _ids[0], "start_s": 10,
                                                                "end_s": 70, "channels": ["rpm"], "caption": "The window"}}))
    nocap = _ok(rpc(h, "code_run", {"study_id": sid, "role": "evidence", "source": "eis.table(eis.flights())"}))["cell"]
    assert nocap["outputs"][-1]["ename"] == "EvidenceError"
    _ok(rpc(h, "study_cell_edit", {"study_id": sid, "cell_id": nocap["id"], "role": "scratch"}))
    _ok(rpc(h, "code_run", {"study_id": sid, "cell_id": nocap["id"],
                            "source": "eis.table(eis.flights(), caption='Flights')"}))
    fin = _ok(rpc(h, "study_finish", {"study_id": sid, **TOP}))
    assert fin["moved_to_working"] == [tail["id"], nocap["id"]]          # look was appended there already
    lay = _layout(h, sid)
    assert [cid for cid, _r, sec in lay if sec == 7] == ["s7", look["id"], tail["id"], nocap["id"]]
    lv = next(c for c in _cells(h, sid) if "eis.logview(" in "".join(c["source"]))
    assert _sm(lv)["role"] == "evidence" and lv["outputs"][-1]["metadata"]["slingology"]["evidence"] == {
        "kind": "logview", "caption": "The window"}
    assert fin["study"]["card"]["evidence"]["figures"] == 1


def test_an_older_notebook_gets_roles_on_load_and_its_sections_at_a_structured_finish(research_ws, isolated_packaged_home):
    h, _ids = research_ws
    if isinstance(h, NodeHost):
        pytest.skip("rewrites the notebook straight in the workspace folder")
    sid = _notebook(h, "Older")
    ws_dir = next(p.parent for p in (isolated_packaged_home / "workspaces").glob("*/manifest.json"))
    p = ws_dir / "studies" / sid / "notebook.ipynb"
    nb = json.loads(p.read_text())
    m = nb["metadata"]["slingology"]
    m.pop("shape")
    m["updated"] = "2026-01-02T03:04:05+00:00"
    nb["cells"] = [nb["cells"][0],
                   {"id": "c1", "cell_type": "markdown", "metadata": {"slingology": {"role": "question"}},
                    "source": "# Older\n\n**Question:** Why does rpm cycle at full power?\n"},
                   {"id": "c2", "cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": "1"},
                   {"id": "c3", "cell_type": "markdown", "metadata": {}, "source": "One is one."}]
    p.write_text(json.dumps(nb))
    lay = _layout(h, sid)
    assert lay == [("setup", "setup", None), ("c1", "question", None), ("c2", "support", None), ("c3", "narrative", None)]
    row = next(s for s in _ok(rpc(h, "list_studies", {}))["studies"] if s["study_id"] == sid)
    assert row["updated"] == "2026-01-02T03:04:05+00:00"           # roles filled in aren't an edit
    # A summary-only finish leaves it as it is.
    _ok(rpc(h, "study_finish", {"study_id": sid, "summary": "It is one."}))
    assert [c for c, _r, _s in _layout(h, sid)] == ["setup", "c1", "c2", "c3"]
    # A structured finish gives it the sections: 1–3 replace the question cell; its cells sit under Findings.
    _ok(rpc(h, "study_finish", {"study_id": sid, **TOP}))
    assert [(c, s) for c, _r, s in _layout(h, sid)] == [
        ("setup", None), ("s1", 1), ("s2", 2), ("s3", 3), ("s4", 4), ("c2", 4), ("c3", 4), ("s5", 5), ("s6", 6), ("s7", 7)]
    assert "Why does rpm cycle at full power?" in "".join(_cells(h, sid)[1]["source"])


def test_evidence_headers_read_as_words():
    assert EV.humanise("fuel_press_psi.mean") == "Fuel pressure mean (psi)"
    assert EV.humanise("duration_s") == "Duration (s)"
    assert EV.humanise("rpm") == "Engine RPM"
    assert EV.humanise("flight_id") == "Flight id"
    assert EV.humanise("exceed_s", {"exceed_s": "min"}) == "Exceed (min)"
    pd = pytest.importorskip("pandas")
    t = EV.table(pd.DataFrame({"phase": ["CLIMB", "TAXI"], "share": [0.1303, 0.355], "n": [356, 1281]}),
                 caption="Share of time above 46 psi", units={"share": "fraction"})
    data, meta = t._repr_mimebundle_()
    assert "<td>0.13</td>" in data["text/html"] and "<td>1,281</td>" in data["text/html"]
    assert meta["slingology"]["evidence"]["caption"] == "Share of time above 46 psi"
    assert meta["slingology"]["table"] == {"n_rows": 2, "n_cols": 3, "truncated": False}
    assert data["text/plain"].splitlines()[0] == "Share of time above 46 psi"
    with pytest.raises(EV.EvidenceError):
        EV.table(pd.DataFrame({"a": [1]}), caption=" ")
