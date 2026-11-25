"""
Browser-mode walk-through of Spec 16 Session F's pages — an investigation notebook on
the Research page (§5.3, D8; acceptance 8 and 12's page clauses), and with
logs the Flights identification and names, Settings → Aircraft / Research
and the Research inbox (§6) — driven through the
real UI of the static site in the installed Chrome (Playwright, headless).

    .venv/bin/python spike/browser-host/run_notebook_walkthrough.py --notebook NB.zip \
        [--logs DIR] [--with LOG.csv ...] [--out results.json] [--headed]

web/dist must be the browser build. A workspace is created in the browser,
the given logs are added (Choose folder…, the input path) and analysed, the
notebook (a notebook's .zip or an .ipynb, e.g. `export_study format zip`
from a server) is imported from Research. Checked: the page renders it
(markdown, code collapsed, outputs, the header's state line); no Re-run /
Accept / Discard without a bench; each log view mounts the chart when its
flight is in the workspace (with Open flight landing on the flight) and
otherwise shows the stored SVG with *flight not in this workspace*; the
browser host's own HTML export shows what the page shows, cell for cell.

The notebook and the logs are the caller's (private flight data): nothing is
written to the repo unless --out points there; the result holds counts and
pass/fail only.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import re
import shutil
import socketserver
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ANALYZE = re.compile(r"^Analyze \d+$")

COMPARE_JS = """async (html) => {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const norm = s => { const d = document.createElement('div'); d.innerHTML = s; return d.innerHTML; };
  const exMd = [...doc.querySelectorAll('.cell.markdown')].map(e => norm(e.innerHTML));
  const pgMd = [...document.querySelectorAll('[data-testid=nb-cell-markdown]')].map(e => e.innerHTML);
  const exCode = [...doc.querySelectorAll('.cell.code')];
  const pgCode = [...document.querySelectorAll('[data-testid=nb-cell-code]')];
  const code = exCode.map((e, i) => {
    const outs = [...e.children].filter(c => c.tagName !== 'DETAILS' && !c.classList.contains('flag')).map(c => norm(c.outerHTML));
    const p = pgCode[i];
    if (!p) return false;
    if (p.querySelector('[data-testid=logview-live]')) return true;    // the chart in place of the SVG, by design
    return outs.every(o => p.innerHTML.includes(o));
  });
  return {md: [exMd.length, pgMd.length], mdSame: exMd.length === pgMd.length && exMd.every((m, i) => m === pgMd[i]),
          code: [exCode.length, pgCode.length], codeSame: code.filter(Boolean).length,
          // Spec 03 v0.34: the page shows the status as its dot and word; the words are the export's
          meta: doc.querySelector('header .meta:not(.card):not(.outputs)').textContent.replace(/\s+/g, ' ').trim() === document.querySelector('[data-testid=nb-meta]').textContent.replace(/\s+/g, ' ').trim(),
          outputs: doc.querySelector('header .outputs').textContent === document.querySelector('[data-testid=nb-outputs]').textContent};
}"""


def serve(directory: Path):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notebook", required=True, help="a notebook's .zip or an .ipynb")
    ap.add_argument("--logs", default=str(ROOT / "data" / "logs"))
    ap.add_argument("--with", dest="with_logs", action="append", default=[], help="log file names to add (else none: every log view falls back)")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--site", default=str(ROOT / "web" / "dist"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="eis-nb-walk-"))
    folder = work / "My logs"
    folder.mkdir()
    for name in args.with_logs:
        shutil.copy(Path(args.logs).resolve() / name, folder / name)
    httpd = serve(Path(args.site))
    url = f"http://localhost:{httpd.server_address[1]}/"
    steps: list[dict] = []
    errors: list[str] = []

    def step(name, ok, **info):
        steps.append({"step": name, "ok": bool(ok), **info})
        print(("PASS " if ok else "FAIL ") + name + (f"  {info}" if info else ""), flush=True)

    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(str(work / "profile"), channel="chrome", headless=not args.headed,
                                                       accept_downloads=True)
            ctx.add_init_script("delete window.showDirectoryPicker;")
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            page.get_by_text("+ New workspace").first.wait_for(timeout=120000)
            page.get_by_text("+ New workspace").first.click()
            page.get_by_placeholder("Workspace name").fill("Notebook walkthrough")
            page.get_by_role("button", name="Create", exact=True).click()
            page.get_by_role("button", name="Choose folder…").wait_for(timeout=30000)
            if args.with_logs:
                with page.expect_file_chooser() as fc:
                    page.get_by_role("button", name="Choose folder…").click()
                fc.value.set_files(str(folder))
                analyze = page.get_by_role("button", name=ANALYZE)
                analyze.wait_for(timeout=60000)
                analyze.click()
                t0 = time.time()
                while time.time() - t0 < 600 and page.get_by_role("button", name=ANALYZE).count():
                    time.sleep(0.5)
                page.locator("tr").filter(has_text="20").first.wait_for(timeout=600000)
                time.sleep(2)
                step("logs analysed in the browser", True, logs=len(args.with_logs))

            if args.with_logs:
                cells = page.get_by_test_id("flight-route-cell")
                cells.first.wait_for(timeout=60000)
                texts = cells.all_inner_texts()
                step("Flights rows show local time with zone and takeoffs/landings",
                     all(re.search(r"\d\d:\d\d [A-Z]{2,4}", t) and "takeoff" in t for t in texts),
                     rows=len(texts), with_route=sum(" – " in t for t in texts))
                cells.first.get_by_test_id("flight-name").click()
                page.get_by_test_id("flight-name-input").fill("Walkthrough name")
                page.get_by_test_id("flight-name-input").press("Enter")
                page.get_by_text("Walkthrough name").first.wait_for(timeout=30000)
                page.get_by_label("Find a flight").fill("walkthrough")
                page.get_by_test_id("flight-find").get_by_role("button", name="Find").click()
                page.get_by_test_id("flight-find-summary").wait_for(timeout=60000)
                step("a name is set in place and Find a flight finds it (flights_find in the browser)",
                     page.get_by_test_id("flight-route-cell").count() == 1
                     and "Walkthrough name" in page.get_by_test_id("flight-route-cell").first.inner_text())

                page.goto(url + "#/settings?tab=aircraft")
                page.get_by_test_id("documents-extension-only").wait_for(timeout=30000)
                page.get_by_label("Propeller", exact=True).fill("Test propeller")
                page.get_by_test_id("aircraft-save").click()
                page.get_by_test_id("aircraft-saved").wait_for(timeout=30000)
                step("Settings → Aircraft saves; documents folders greyed 'extension only'",
                     page.get_by_label("Add a documents folder").count() == 0)
                page.goto(url + "#/settings?tab=research")
                page.get_by_test_id("sensitivity-curious").click()
                page.get_by_test_id("sensitivity-saved").wait_for(timeout=30000)
                page.get_by_test_id("sensitivity-normal").click()
                step("Settings → Research saves the sensitivity", True)

                page.goto(url + "#/research")
                page.get_by_test_id("inbox").wait_for(timeout=60000)
                page.get_by_test_id("inbox-install").wait_for(timeout=300000)
                n = page.get_by_test_id("inbox-candidate").count()
                step("the inbox is on Research home in the browser, with the install invitation", True, candidates=n,
                     scan=page.get_by_test_id("inbox-scan").inner_text() if page.get_by_test_id("inbox-scan").count() else None)
                if n:
                    page.get_by_test_id("inbox-candidate").first.get_by_test_id("inbox-item-menu").click()   # the ⋯ menu
                    page.get_by_test_id("inbox-mark-watch").click()
                    page.get_by_label("Note").fill("walkthrough")
                    page.get_by_test_id("inbox-resolve-confirm").click()
                    page.wait_for_function("() => document.querySelector('[data-testid=inbox-candidate]')?.dataset.status === 'watch'", timeout=30000)
                    step("a candidate is marked (watch, with a note)", True)

            page.goto(url + "#/research")
            page.get_by_test_id("import-study-input").set_input_files(args.notebook)
            page.get_by_test_id("notebook").wait_for(timeout=120000)
            step("Research imports the notebook and opens it", True)
            time.sleep(3)
            info = page.evaluate("""() => ({
              md: document.querySelectorAll('[data-testid=nb-cell-markdown]').length,
              code: document.querySelectorAll('[data-testid=nb-cell-code]').length,
              open: [...document.querySelectorAll('.nb details.code')].filter(d => d.open).length,
              live: document.querySelectorAll('[data-testid=logview-live]').length,
              absent: document.querySelectorAll('[data-testid=logview-absent]').length,
              tables: document.querySelectorAll('.nb table.eis-table').length,
              figures: document.querySelectorAll('.nb img.figure').length,
              outputs: document.querySelector('[data-testid=nb-outputs]')?.textContent,
              runActions: ['nb-rerun', 'nb-accept-all', 'nb-discard-all', 'nb-keep-external'].filter(t => document.querySelector(`[data-testid=${t}]`)).length,
              noBenchNote: document.body.innerText.includes('re-running a notebook needs EIS on your computer'),
            })""")
            step("the page renders the notebook, code collapsed", info["md"] > 0 and info["code"] > 0 and info["open"] == 0,
                 **{k: info[k] for k in ("md", "code", "tables", "figures")})
            step("no Re-run / Accept / Discard without a bench; the page says why", info["runActions"] == 0 and info["noBenchNote"],
                 outputs_line=info["outputs"])
            if args.with_logs:
                step("a log view whose flight is here mounts the chart", info["live"] >= 1, live=info["live"], absent=info["absent"])
            else:
                step("log views whose flight is absent fall back to the SVG", info["absent"] >= 1 and info["live"] == 0, absent=info["absent"])

            with page.expect_download(timeout=120000) as dl:
                page.get_by_test_id("nb-actions").click()            # Spec 03 v0.34: the Actions menu
                page.get_by_test_id("nb-export-html").click()
            saved = work / dl.value.suggested_filename
            dl.value.save_as(saved)
            cmp = page.evaluate(COMPARE_JS, saved.read_text())
            step("the browser host's HTML export shows what the page shows",
                 cmp["mdSame"] and cmp["meta"] and cmp["outputs"] and cmp["codeSame"] == cmp["code"][0] == cmp["code"][1], **cmp)

            if info["live"]:
                page.get_by_test_id("open-flight").first.click()
                page.wait_for_url("**/#/flights/*", timeout=30000)
                page.get_by_text("Timeline").first.wait_for(timeout=60000)
                time.sleep(2)
                rng = page.locator("#timeline .mono").first.inner_text()
                step("Open flight lands on the flight, zoomed to the window", "min)" in rng and "(0 min)" not in rng, range_minutes=rng.split("(")[-1])
            ctx.close()
    finally:
        httpd.shutdown()
        shutil.rmtree(work, ignore_errors=True)

    step("no page errors", not errors, errors=errors[:3])
    result = {"at": datetime.now(timezone.utc).isoformat(), "steps": steps}
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1) + "\n")
    return 0 if all(s["ok"] for s in steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
