"""Write web/src/fixtures/research-notebook.json (run from the repo root:
.venv/bin/python web/scripts/gen_notebook_fixture.py web/src/fixtures/research-notebook.json): a synthetic notebook (no
real flight, tail, airport or time) with every output type the renderer
handles, as load_study returns it."""
import json, sys
from pathlib import Path
from slingology_eis.investigations import ipynb as NBX
from slingology_eis.investigations.eis_lib import LOGVIEW_MIME

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="40" viewBox="0 0 120 40">'
       '<polyline points="0,30 20,10 40,30 60,10 80,30 100,10 120,30" fill="none" stroke="#333"/></svg>')
PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
FLIGHT = "5ynthet1c0f11e01"
TABLE = ('<table class="eis-table"><caption>Slices</caption><thead><tr><th>slice</th><th>rpm swing</th></tr></thead>'
         '<tbody><tr><td>s1</td><td>180</td></tr><tr><td>s2</td><td>176 &lt; 180</td></tr></tbody></table>'
         '<p>3 more rows not kept</p>')

def code(cid, src, outputs, **sm):
    return {"id": cid, "cell_type": "code", "execution_count": None, "source": src, "outputs": outputs,
            "metadata": {"slingology": {"ran": {"engine": "1.0.2", "flights": [FLIGHT], "at": "2026-01-02T10:00:00Z",
                                                "ms": 120, "status": "ok"}, **sm}}}

def md(cid, src):
    return {"id": cid, "cell_type": "markdown", "source": src, "metadata": {}}

cells = [
    {"id": "setup", "cell_type": "code", "execution_count": None, "outputs": [],
     "source": NBX.setup_source("ws_000000000000"), "metadata": {"slingology": {"role": "setup"}}},
    {"id": "c1", "cell_type": "markdown", "source": "## Question\n\nIs there a cycle in **rpm** at full power?",
     "metadata": {"slingology": {"role": "question"}}},
    md("c2", "# Plan\n\n1. Look at *one* flight first.\n2. Then every `full_power` slice.\n\n"
             "- swing about the setpoint\n- period\n\n| measure | value |\n|---|---|\n| swing | 180 rpm |\n\n"
             "> A hypothesis, not a conclusion.\n\n```\nr = eis.cycling(\"full_power\", \"rpm\")\n```\n\n"
             "See [the docs](https://example.org/docs?a=1&b=2) and [this](javascript:alert(1)); "
             "<script>alert('x')</script> stays text.\n\n![chart](files/chart.svg)"),
    code("c3", "print(r)", [{"output_type": "stream", "name": "stdout", "text": ["RPM cycles every 3.8 s\n", "in 9 of 10 slices <ok>\n"]},
                            {"output_type": "stream", "name": "stderr", "text": "a warning & more\n"}]),
    code("c4", "r.rows", [{"output_type": "execute_result", "execution_count": 1, "data": {"text/html": TABLE, "text/plain": "slice rpm swing\n s1 180"},
                           "metadata": {"slingology": {"table": {"n_rows": 5, "n_cols": 2, "truncated": True}}}}]),
    code("c5", "html_without_mark", [{"output_type": "display_data", "data": {"text/html": "<b onclick='x()'>bold</b>",
                                                                           "text/plain": "<b>plain fallback</b>"}, "metadata": {}}]),
    code("c6", "r.figure()", [{"output_type": "display_data", "data": {"image/svg+xml": SVG, "text/plain": "<Figure rpm swing>"}, "metadata": {}}]),
    md("c7", "The figure above shows the swing per slice."),
    code("c8", "plt.show()", [{"output_type": "display_data", "data": {"image/png": PNG, "text/plain": "<Figure>"}, "metadata": {}}],
         ran_elsewhere="external"),
    md("c9", "The log view below is the first takeoff."),
    code("c10", f'eis.logview("{FLIGHT}", 360, 420, ["rpm", "map_inhg"], marks=[(367, "takeoff power")])',
         [{"output_type": "display_data", "metadata": {},
           "data": {"image/svg+xml": SVG, "text/plain": "<LogView>",
                    LOGVIEW_MIME: {"flight": FLIGHT, "flight_date_local": "2026-01-02", "start_s": 360, "end_s": 420,
                                   "channels": ["rpm", "map_inhg"], "marks": [{"t_s": 367.0, "label": "takeoff power"}],
                                   "title": "First takeoff", "window_label": "06:00–07:00 into the flight"}}}]),
    code("c11", "1/0", [{"output_type": "error", "ename": "ZeroDivisionError", "evalue": "division by zero",
                         "traceback": ["\x1b[0;31mZeroDivisionError\x1b[0m", "division by zero"]}],
         pending={"outputs": [{"output_type": "stream", "name": "stdout", "text": "now fine\n"}]}),
    code("c12", "eis.cycling('full_power', 'rpm', flights=['gone'])", [{"output_type": "stream", "name": "stdout", "text": "sender's result\n"}],
         read_only=True),
]
nb = {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
      "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                   "slingology": {"id": "st-000000fixture", "name": "Synthetic rpm cycle", "kind": "investigation",
                                  "author": "claude", "question": "Is there a cycle in rpm at full power?",
                                  "status": "finished", "summary": "RPM swings **180 rpm** about the setpoint.\n\nWatch it.",
                                  "inbox_candidate": None, "engine": "1.0.2", "engine_type": "916iS",
                                  "created": "2026-01-02T09:00:00Z", "updated": "2026-01-02T10:00:00Z",
                                  "workspace_id": "ws_000000000000"}}}
view = {**NBX.read_view(nb), "files": {"files/chart.svg": "data:image/svg+xml;base64,PHN2Zy8+"}}
out = Path(sys.argv[1])
out.write_text(json.dumps(view, indent=1, ensure_ascii=False) + "\n")
print("wrote", out)
