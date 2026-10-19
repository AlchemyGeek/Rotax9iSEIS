"""
Browser-host walk-through (Spec 04 v0.7 §10 step 4, acceptance 1), driven
through the real UI in the installed Chrome (Playwright, headless).

    .venv/bin/python spike/browser-host/run_walkthrough.py [--logs DIR] [--limit N] [--headed]

web/dist must be the browser build (`cd web && npm run build:browser`); it
is served as a plain static folder — no Python server. Chrome's folder
picker (showDirectoryPicker) can't be operated by Playwright, so this run
hides it and Choose folder… takes the same <input webkitdirectory> path as
Safari; the picker and its Allow-access re-grant are checked by hand.
Writes spike/browser-host/results/walkthrough-*.json.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import shutil
import socketserver
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import re

from playwright.sync_api import sync_playwright

ANALYZE = re.compile(r"^Analyze \d+$")
COUNT = """async () => { const { client } = await window.__eis.getRuntime();
  const rows = (await client.listFlightsWithStatus()).rows;
  return { analyzed: rows.filter(r => r.status === 'analyzed').length, total: rows.length }; }"""

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def serve(directory: Path):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default=str(ROOT / "data" / "logs"))
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="eis-walk-"))
    folder = work / "My logs"
    folder.mkdir()
    for p in sorted(p for p in Path(args.logs).resolve().iterdir() if p.suffix.lower() == ".csv")[: args.limit]:
        shutil.copy(p, folder / p.name)
    httpd = serve(ROOT / "web" / "dist")
    url = f"http://localhost:{httpd.server_address[1]}/"
    profile = work / "profile"
    steps: list[dict] = []
    errors: list[str] = []

    def step(name, ok, **info):
        steps.append({"step": name, "ok": bool(ok), **info})
        print(("PASS " if ok else "FAIL ") + name + (f"  {info}" if info else ""), flush=True)

    def launch(p):
        ctx = p.chromium.launch_persistent_context(str(profile), channel="chrome", headless=not args.headed,
                                                   accept_downloads=True)
        # The Safari path in Chrome: no showDirectoryPicker (see the docstring).
        ctx.add_init_script("delete window.showDirectoryPicker;")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        return ctx, page

    try:
        with sync_playwright() as p:
            ctx, page = launch(p)
            t0 = time.time()
            page.goto(url)
            try:
                page.get_by_test_id("engine-loading").wait_for(timeout=5000)
                loading = page.get_by_test_id("engine-loading").inner_text()
            except Exception:
                loading = None
            step("first visit shows the engine-loading state", loading and "About 30 MB, once" in loading)
            page.get_by_text("+ New workspace").first.wait_for(timeout=60000)
            step("engine ready (cold)", True, seconds=round(time.time() - t0, 1))

            page.get_by_text("+ New workspace").first.click()
            page.get_by_placeholder("Workspace name").fill("Walkthrough")
            page.get_by_role("button", name="Create", exact=True).click()
            page.get_by_role("button", name="Choose folder…").wait_for(timeout=30000)
            step("workspace created; Flights offers Choose folder…", True)

            with page.expect_file_chooser() as fc:
                page.get_by_role("button", name="Choose folder…").click()
            fc.value.set_files(str(folder))
            page.get_by_test_id("folder-row").first.wait_for(timeout=30000)
            step("folder chosen (input path)", "My logs" in page.get_by_test_id("folder-row").first.inner_text())

            analyze = page.get_by_role("button", name=ANALYZE)
            analyze.wait_for(timeout=60000)
            label = analyze.inner_text()
            t0 = time.time()
            analyze.click()
            progress = set()
            while time.time() - t0 < 900:
                banner = page.get_by_test_id("flights-banner")
                text = banner.inner_text() if banner.count() else ""
                if text.startswith(("Analyzing", "Reading", "Re-analyzing", "Starting")):
                    progress.add(text.split(" —")[0])
                if page.get_by_role("button", name=ANALYZE).count() == 0 and text and not text.startswith(("Analyzing", "Reading", "Starting", "Re-analyzing", "Syncing")):
                    break
                time.sleep(0.5)
            rows = page.evaluate(COUNT)["analyzed"]
            step("Sync analysed the logs with a live progress line", len(progress) > 1 and rows > 0,
                 button=label, progress_samples=sorted(progress)[:6], seconds=round(time.time() - t0, 1), flight_rows=rows)

            page.locator("tr").filter(has_text="2026-").first.locator("td").nth(1).click()
            page.wait_for_url("**/#/flights/*", timeout=30000)
            page.get_by_text("Timeline").first.wait_for(timeout=60000)
            chart = page.locator("canvas, svg").count()
            step("a flight opens and its chart renders", chart > 0, canvases_or_svgs=chart)

            edit = page.get_by_role("button", name="Edit rules…").first
            edit.click()
            page.locator("select").filter(has_text="limit").first.select_option("warning")
            page.get_by_role("button", name="Apply to all flights").click()
            page.get_by_text("Rule changed").first.wait_for(timeout=60000)
            step("a rule edited on a card", True)

            page.goto(url + "#/journal")
            page.get_by_text("Rule: limit_exceedances").first.wait_for(timeout=30000)
            step("Journal lists the rule edit", True)
            page.goto(url + "#/trends")
            page.get_by_text("cylinder balance").first.wait_for(timeout=60000)
            step("Trends renders", True)
            page.goto(url + "#/settings?tab=app")
            page.get_by_test_id("storage-panel").wait_for(timeout=30000)
            storage = page.get_by_test_id("storage-panel").inner_text()
            step("Settings → App shows Storage", "Space used" in storage, text=storage.splitlines()[1:3])
            with page.expect_download(timeout=120000) as dl:
                page.get_by_role("button", name="Export workspace…").click()
            saved = work / dl.value.suggested_filename
            dl.value.save_as(saved)
            step("export downloads", saved.stat().st_size > 1000, file=saved.name, bytes=saved.stat().st_size)
            page.goto(url + "#/settings?tab=engine")
            step("About line names the host", "in this browser" in page.get_by_test_id("engine-host").inner_text())

            page.goto(url + "#/flights")
            page.reload()
            page.locator("tr").filter(has_text="2026-").first.wait_for(timeout=60000)
            after_reload = page.evaluate(COUNT)["analyzed"]
            step("after reload everything is still there", after_reload == rows, flight_rows=after_reload)
            ctx.close()

            ctx, page = launch(p)          # a browser restart on the same profile
            t0 = time.time()
            page.goto(url + "#/flights")
            page.locator("tr").filter(has_text="2026-").first.wait_for(timeout=60000)
            step("engine ready (warm, after restart)", True, seconds=round(time.time() - t0, 1))
            after_restart = page.evaluate(COUNT)["analyzed"]
            reconnect = page.get_by_role("button", name="Not connected — reconnect").count()
            step("after restart: flights there; the session folder says Not connected — reconnect",
                 after_restart == rows and reconnect == 1, flight_rows=after_restart)

            page.goto(url + "#/settings?tab=app")
            page.get_by_role("button", name="Delete all data on this device").click()
            dialog = page.get_by_role("dialog", name="Delete all data")
            step("delete asks, naming the workspace count", "Delete 1 workspace" in dialog.inner_text())
            dialog.get_by_role("button", name="Delete", exact=True).click()
            page.get_by_text("+ New workspace").first.wait_for(timeout=60000)
            gone = page.get_by_test_id("data-gone").count()
            step("delete all data → the first-run state", gone == 0)
            ctx.close()
    finally:
        httpd.shutdown()
        shutil.rmtree(work, ignore_errors=True)

    result = {"at": datetime.now(timezone.utc).isoformat(), "logs": args.limit, "steps": steps, "page_errors": errors}
    (HERE / "results").mkdir(exist_ok=True)
    out = HERE / "results" / f"walkthrough-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"page errors: {errors}" if errors else "no page errors")
    return 0 if all(s["ok"] for s in steps) and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
