"""
Spec 16 §5.1/§5.3: the HTML export shows what the Research page shows. The
page's renderer (web/src/lib/notebook.ts) is a port of nbhtml, string for
string; both are checked against one golden made from a synthetic notebook
with every output type (web/src/fixtures/research-notebook.json →
research-notebook.render.json; the vitest side is notebook.test.ts).

Regenerate after an intended change: SLINGOLOGY_REGEN_NB_GOLDEN=1 pytest this file.
"""
import base64
import json
import os
from pathlib import Path

from slingology_eis.investigations import nbhtml
from slingology_eis.investigations.ipynb import meta, text

FIX = Path(__file__).resolve().parents[2] / "web" / "src" / "fixtures"


def _view():
    return json.loads((FIX / "research-notebook.json").read_text())


def _read(files):
    def read(ref):
        url = files.get(ref)
        return base64.b64decode(url.split(",", 1)[1]) if url else None
    return read


def golden_of(view) -> dict:
    nb, read = view["notebook"], _read(view.get("files") or {})
    m = meta(nb)
    cells = {}
    for c in nb["cells"]:
        if c["cell_type"] == "markdown":
            cells[c["id"]] = {"markdown": nbhtml.markdown(text(c["source"]), read)}
        else:
            sm = (c.get("metadata") or {}).get("slingology") or {}
            flags = [f for f, on in (("ran elsewhere", sm.get("ran_elsewhere")), ("read-only", sm.get("read_only"))) if on]
            cells[c["id"]] = {"outputs": [nbhtml.output(o) for o in c.get("outputs") or []], "flags": flags}
    return {"meta_line": nbhtml.meta_line(m),
            "outputs_line": nbhtml.outputs_line(nb),
            "summary": nbhtml.markdown(m.get("summary") or ""),
            # Spec 03 v0.34: the card's line, the summary block (earlier summaries inside), short window strings.
            "card_line": nbhtml.card_line(m.get("card")),
            "summary_block": nbhtml.summary_block(m.get("summary") or "",
                                                  [{"summary": "Earlier.", "finished": "2026-01-01T00:00:00Z"}]),
            "short_windows": {lab: nbhtml.short_window(lab) for lab in SHORT_WINDOW_CASES},
            "cells": cells}


SHORT_WINDOW_CASES = [
    "2026-10-24 22:26:07–22:26:53 PDT (+10:16–+11:02 into the flight)",
    "2026-01-01 12:01:05–12:03:10 PST (+01:50–+03:55 into the flight)",
    "2026-01-01 12:01:05 (+01:50 into the flight)",
    "2026-03-09 13:01:05–13:03:10 (+1:01:50–+1:03:55 into the flight)",
    "+06:07–+07:04 into the flight",
    "not a window",
]


def test_the_export_matches_the_golden_the_page_is_checked_against():
    got = golden_of(_view())
    path = FIX / "research-notebook.render.json"
    if os.environ.get("SLINGOLOGY_REGEN_NB_GOLDEN"):
        path.write_text(json.dumps(got, indent=1, ensure_ascii=False) + "\n")
    assert got == json.loads(path.read_text())


def test_the_export_page_carries_every_piece():
    view = _view()
    page = nbhtml.render(view["notebook"], _read(view["files"]))
    g = golden_of(view)
    assert g["meta_line"] in page and g["outputs_line"] in page and g["summary"] in page and g["card_line"] in page
    assert '<details class="summary" open><summary>Summary</summary>' in page
    assert 'id="setup"' not in page and "eis.open(" not in page          # the setup cell isn't shown
    assert "First takeoff · Jan 2 · 09:06–09:07 (+6:00 into the flight)" in page
    assert 'title="2026-01-02 09:06:00–09:07:00 UTC (+06:00–+07:00 into the flight)"' in page
    for cid, cell in g["cells"].items():
        if cid == "setup":
            continue
        for piece in [cell.get("markdown") or ""] + cell.get("outputs", []):
            assert piece in page


def test_nothing_in_a_received_notebook_runs():
    g = golden_of(_view())["cells"]
    md = g["c2"]["markdown"]
    assert "<script>" not in md and "&lt;script&gt;" in md
    assert 'href="#"' in md and "javascript:" not in md.split('href="#"')[0][-40:]
    assert 'src="data:image/svg+xml;base64,PHN2Zy8+"' in md                     # files/ image inlined
    assert g["c5"]["outputs"] == ["<pre>&lt;b&gt;plain fallback&lt;/b&gt;</pre>"]  # unmarked html → text
    evil = nbhtml.sanitize_table('<table onload="x()"><tr><td><script>alert(1)</script><img src=x onerror=y></td></tr></table>')
    assert evil == '<table class="eis-table"><tr><td>alert(1)</td></tr></table>'


# ── Spec 16 D19 §5.6: the shaped notebook (web/src/fixtures/research-notebook-shaped.json) ──

_TINY_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="2"><path d="M0 1h4"/></svg>'


def shaped_notebook() -> dict:
    """A synthetic shaped notebook built with the engine's own functions —
    sections, a finding with its support and evidence (an eis.table, an
    eis.figure, a log view), a plan under 5, a dated follow-up, scratch
    under Working, a structured top with one earlier Answer. No flight data."""
    pytest = __import__("pytest")
    pd = pytest.importorskip("pandas")
    from slingology_eis.investigations import evidence as EV
    from slingology_eis.investigations import ipynb as NBX
    from slingology_eis.investigations import shape as SH
    nb = NBX.new(name="Fuel pressure by phase", question="Is fuel pressure high only when pump 2 is on?",
                 study_id="st-0000000d1900", workspace_id="ws_fixture")
    m = NBX.meta(nb)
    m.update({"created": "2026-11-27T10:00:00+00:00", "updated": "2026-11-27T12:00:00+00:00", "engine": "1.1.0"})

    def put(cell, section=None):
        SH.place(nb, cell, section)
        return cell

    def code(cid, src, outputs, role):
        c = NBX.code_cell(cid, src, outputs, {"engine": "1.1.0", "flights": ["f1", "f2"], "at": "2026-11-27T11:00:00+00:00",
                                              "ms": 10, "status": "ok", "digest": NBX.digest(outputs)})
        NBX.slmeta(c)["role"] = role
        return c

    def bundle(ev):
        data, md = ev._repr_mimebundle_()
        return {"output_type": "display_data", "metadata": md, "data": data}
    put(NBX.markdown_cell("c1", "Plan: one flight first, then every flight by phase.", role="narrative"), 5)
    put(NBX.markdown_cell("c2", "Fuel pressure is at or above **46 psi** for 81% of idle time (Table 1).", role="narrative"))
    put(code("c3", "share = …", [{"output_type": "stream", "name": "stdout", "text": "computed 7 phases\n"}], "support"))
    tbl = EV.table(pd.DataFrame({"phase": ["IDLE", "CLIMB"], "exceed_share_pct": [81.1, 13.0], "n": [1281, 356]}),
                   caption="Share of each phase's time at or above 46 psi")
    put(code("c4", "eis.table(share, caption=…)", [bundle(tbl)], "evidence"))
    put(NBX.markdown_cell("c5", "The climb looks like this on one flight (Log view 3).", role="narrative"))
    put(code("c6", "fig, ax = plt.subplots() …", [{"output_type": "display_data", "data": {
        "image/svg+xml": _TINY_SVG, "text/plain": "<Figure: by phase>"}, "metadata": {"slingology": {"evidence": {
            "kind": "figure", "caption": "Time above 46 psi, by phase"}}}}], "evidence"))
    lv = {"flight": "f1", "flight_date_local": "2026-01-02", "start_s": 360, "end_s": 420, "channels": ["fuel_press_psi", "rpm"],
          "marks": [{"t_s": 367.0, "label": "pump 2 on"}], "title": "First climb", "caption": "First climb: above 46 psi from the start",
          "window_label": "2026-01-02 09:06:00–09:07:00 UTC (+06:00–+07:00 into the flight)"}
    put(code("c7", "eis.logview('f1', 360, 420, …)", [{"output_type": "display_data", "data": {
        "image/svg+xml": _TINY_SVG, NBX.LOGVIEW_MIME: lv, "text/plain": "<log view>"},
        "metadata": {"slingology": {"evidence": {"kind": "logview", "caption": lv["caption"]}}}}], "evidence"))
    put(code("c8", "eis.slices('idle').columns", [{"output_type": "stream", "name": "stdout", "text": "['a', 'b']\n"}], "scratch"))
    m["top"] = {"question_scope": "- 2 flights, Jan 2026\n- The logs can't tell: the pump 2 switch", "shows": [
        "Fuel pressure is at or above 46 psi for 81% of idle time (Table 1).", "Climb is 13% of its time above."],
        "means": "Phase is a factor, the other way round from the hypothesis.", "actions": [
        {"what": "Ask the shop to check the regulator", "who": "A&P", "settles": "whether it is the setting",
         "recheck_after_flights": 10}]}
    m["history"] = [{"shows": ["Fuel pressure runs high on every flight."], "means": "Not momentary.",
                     "actions": [], "finished": "2026-11-26T02:00:00+00:00"}]
    m.update({"status": "finished", "finished": "2026-11-27T12:00:00+00:00", "summary": m["top"]["means"],
              "finding": m["top"]["shows"][0], "tags": ["fuel pressure"]})
    fu = SH.open_followup(nb, "2026-11-27", "Is phase a factor?")
    fu["id"] = "c9"
    m["followup"] = "c9"
    put(NBX.markdown_cell("c10", "By phase, idle is the most affected.", role="narrative"))
    SH.close_followup(nb, "Answer: phase is a factor; action 1 added.")["id"] = "c11"
    SH.refresh_generated(nb)
    m["card"] = NBX.card(nb)
    return {"study_id": m["id"], "name": m["name"], "format": "ipynb", "notebook": nb, "files": {}}


def shaped_golden(view) -> dict:
    nb = view["notebook"]
    m = meta(nb)
    lay = nbhtml.layout(nb)
    by = {c["id"]: c for c in nb["cells"]}
    evidence = {b["id"]: [nbhtml.evidence_output(by[b["id"]]["outputs"][x["output"]])
                          + nbhtml.evidence_caption(x["label"], x["caption"]) for x in b["labels"]]
                for b in lay["blocks"] if b["kind"] == "evidence"}
    return {"layout": lay, "answer_block": nbhtml.answer_block(lay["top"], m.get("history") or [], m.get("summaries") or []),
            "evidence": evidence, "working_summary": [nbhtml.working_summary(k) for k in (1, 2)],
            "card_line": nbhtml.card_line(m.get("card")), "actions_text": [nbhtml.actions_text(k) for k in (0, 1, 3)]}


def test_spec16_d19_the_shaped_export_matches_the_golden_the_page_is_checked_against():
    view = shaped_notebook()
    fix = FIX / "research-notebook-shaped.json"
    gold = FIX / "research-notebook-shaped.render.json"
    if os.environ.get("SLINGOLOGY_REGEN_NB_GOLDEN"):
        fix.write_text(json.dumps(view, indent=1, ensure_ascii=False) + "\n")
        gold.write_text(json.dumps(shaped_golden(view), indent=1, ensure_ascii=False) + "\n")
    assert view == json.loads(fix.read_text()), "the shaped fixture is stale: regenerate it"
    assert shaped_golden(view) == json.loads(gold.read_text())


def test_spec16_d19_the_shaped_page_reads_in_section_order():
    view = shaped_notebook()
    nb = view["notebook"]
    lay = nbhtml.layout(nb)
    kinds = [(b["kind"], b.get("n") or b.get("id")) for b in lay["blocks"]]
    assert kinds == [("section", 4), ("markdown", "c2"), ("support", "c3"), ("evidence", "c4"), ("markdown", "c5"),
                     ("evidence", "c6"), ("evidence", "c7"), ("section", 5), ("markdown", "c1"), ("section", 6),
                     ("markdown", "c9"), ("markdown", "c10"), ("markdown", "c11"), ("section", 7), ("working", None)]
    assert lay["blocks"][-1]["ids"] == ["c8"]
    assert [x["label"] for b in lay["blocks"] if b["kind"] == "evidence" for x in b["labels"]] == [
        "Table 1", "Figure 2", "Log view 3"]
    assert not lay["top"][0].startswith("# ") and lay["top"][0].startswith("## 1 The question")
    page = nbhtml.render(nb)
    order = [page.index(x) for x in ('<section class="answer">', "<h2>2 Answer</h2>", "<h2>3 Proposed actions</h2>",
                                     '<h2 class="section" id="s4">4 Findings</h2>', "<strong>Table 1.</strong>",
                                     '<h2 class="section" id="s5">', "Follow-up — 2026-11-27",
                                     '<details class="working"><summary>Working (1 cell)</summary>')]
    assert order == sorted(order)
    assert "Earlier answers (1)" in page and "Answer of 2026-11-26" in page
    assert '<details class="calc"><summary>show the calculation</summary>' in page
    assert "<caption>" not in page.split('<div class="cell evidence" id="c4">')[1].split("</figure>")[0]
    assert "re-check after the next 10 flights" in page and "1 action" in page
    assert 'id="setup"' not in page and "eis.open(" not in page
