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
