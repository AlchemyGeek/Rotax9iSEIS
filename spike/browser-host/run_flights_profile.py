"""
Flights load profile in the browser host (Spec 04 §10 step 6): how long
Flights takes to open with the full test set, and where the time goes.

    .venv/bin/python spike/browser-host/run_flights_profile.py --site DIR [--logs DIR] [--runs N]

DIR must be a site built with `scripts/build_site.py --e2e` (the test hook
exposes the client). The logs are synced once through the UI; then Flights
is opened N times from Trends, timing navigation → rows on screen, and each
engine operation the page made (time in the page, including the worker).
Prints the figures and writes spike/browser-host/results/flights-profile-*.json
(timings and counts only).
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import re
import shutil
import socketserver
import statistics
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
ANALYZE = re.compile(r"^Analyze \d+$")
SUMMARY = re.compile(r"(\d+) flights · (\d+) in reference")

TIMER = """async () => {
  const { client } = await window.__eis.getRuntime();
  if (client.__timed) return;
  client.__timed = true;
  window.__rpcLog = [];
  const orig = client.rpc.bind(client);
  client.rpc = (op, params) => {
    const t = performance.now();
    return orig(op, params).finally(() => window.__rpcLog.push([op, performance.now() - t, t]));
  };
}"""


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
    ap.add_argument("--site", required=True)
    ap.add_argument("--logs", default=str(ROOT / "data" / "logs"))
    ap.add_argument("--runs", type=int, default=8)
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="eis-flights-"))
    folder = work / "My logs"
    folder.mkdir()
    for p in sorted(p for p in Path(args.logs).resolve().iterdir() if p.suffix.lower() == ".csv"):
        shutil.copy(p, folder / p.name)
    httpd = serve(Path(args.site).resolve())
    url = f"http://localhost:{httpd.server_address[1]}/"
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(work / "profile"), channel="chrome", headless=True)
        ctx.add_init_script("delete window.showDirectoryPicker;")
        page = ctx.pages[0]
        page.goto(url)
        page.get_by_text("+ New workspace").first.wait_for(timeout=90000)
        page.get_by_text("+ New workspace").first.click()
        page.get_by_placeholder("Workspace name").fill("Profile")
        with page.expect_navigation(timeout=60000):
            page.get_by_role("button", name="Create", exact=True).click()
        page.get_by_role("button", name="Choose folder…").wait_for(timeout=90000)
        with page.expect_file_chooser() as fc:
            page.get_by_role("button", name="Choose folder…").click()
        fc.value.set_files(str(folder))
        page.get_by_role("button", name=ANALYZE).wait_for(timeout=120000)
        page.get_by_role("button", name=ANALYZE).click()
        t0 = time.time()
        while time.time() - t0 < 1200 and page.get_by_role("button", name=ANALYZE).count():
            time.sleep(1)
        while time.time() - t0 < 1200:
            banner = page.get_by_test_id("flights-banner")
            text = banner.inner_text() if banner.count() else ""
            if not text.startswith(("Analyzing", "Reading", "Starting", "Re-analyzing", "Syncing")):
                break
            time.sleep(1)
        m = SUMMARY.search(page.get_by_text(SUMMARY).first.inner_text())
        flights = int(m.group(1))
        print(f"synced: {flights} flights in {time.time() - t0:.0f} s", flush=True)

        page.evaluate(TIMER)
        runs = []
        for i in range(args.runs):
            page.evaluate("location.hash = '#/trends'")
            page.get_by_text("Trends").first.wait_for()
            page.wait_for_timeout(1500)                       # Trends' own requests settle
            page.evaluate("window.__rpcLog = []")
            t = page.evaluate("""() => new Promise((done) => {
              const t0 = performance.now();
              location.hash = '#/flights';
              const check = () => {
                const rows = [...document.querySelectorAll('td.mono')].length;
                if (rows > 0 && !document.body.innerText.includes('Loading…')) done({ ms: performance.now() - t0, t0 });
                else requestAnimationFrame(check);
              };
              requestAnimationFrame(check);
            })""")
            page.wait_for_timeout(1500)
            log = page.evaluate("window.__rpcLog")
            ops = [{"op": op, "ms": round(ms, 1), "start_ms": round(start - t["t0"], 1)} for op, ms, start in log if start >= t["t0"] - 1]
            runs.append({"open_ms": round(t["ms"], 1), "ops": ops})
            print(f"run {i + 1}: Flights on screen in {t['ms']:.0f} ms; " +
                  ", ".join(f"{o['op']} {o['ms']:.0f}" for o in ops), flush=True)
        ctx.close()
    httpd.shutdown()
    opens = [r["open_ms"] for r in runs[1:]] or [runs[0]["open_ms"]]
    summary = {"flights": flights, "runs": len(runs), "open_ms_median": round(statistics.median(opens), 1),
               "open_ms_max": round(max(opens), 1)}
    print(json.dumps(summary))
    out = ROOT / "spike" / "browser-host" / "results" / f"flights-profile-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    out.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "summary": summary, "runs": runs}, indent=2) + "\n")
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
