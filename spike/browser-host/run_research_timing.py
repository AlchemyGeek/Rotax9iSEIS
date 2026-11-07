"""
Spec 06 §15 acceptance 8 — the in-page slice build on the full log set.

    python spike/browser-host/run_research_timing.py [--logs DIR] [--through YYYY-MM-DD]

web/dist (built with `npm run build:browser`) is served as a static folder
and opened in headless Chromium (Playwright). A workspace is created, the
logs registered through <input webkitdirectory>, Sync run, then the
full-power preset is built over every flight twice — cold, then from the
study's descriptor cache — and a one-question study is run. Timings go to
spike/browser-host/results/research-timing.json. Only CSVs are copied to a
temporary folder; nothing is written to the repo's data/.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import shutil
import socketserver
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))


def serve(directory: Path):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


READY = """async () => { const { client } = await window.__eis.getRuntime(); await client.getCapabilities(); return client.status; }"""

RUN = """async () => {
  const { client } = await window.__eis.getRuntime();
  const out = {};
  const ws = await client.createWorkspace('Research timing', '916iS');
  const input = document.getElementById('timing-folder');
  out.files_given = input.files.length;
  await client.addFolderFiles([...input.files]);
  let t0 = performance.now();
  const scan = await client.scanWorkspace();
  out.scan_ms = performance.now() - t0;
  out.flights = scan.new_flight_ids.length;
  // Acceptance 8: a full-workspace slice build, cold.
  t0 = performance.now();
  const cold = await client.buildSlices({ selection: { mode: 'all' }, slice_rules: ['full_power'], channels: ['rpm', 'map_inhg'] });
  out.build_cold_ms = performance.now() - t0;
  out.slices = cold.count; out.by_source = cold.by_source; out.flights_with_slices = cold.flights_with_slices;
  // A one-question study: save, run (its own build, then the test), run again from the cache.
  const saved = await client.saveStudy({ name: 'Timing', selection: { mode: 'all' }, slice_rules: ['full_power'],
                                         tests: [{ test_id: 'cycling', channels: ['rpm'], params: {} }] });
  t0 = performance.now();
  const ran = await client.runStudy(saved.study_id);
  out.run_study_ms = performance.now() - t0;
  out.finding = ran.tests[0].result ? ran.tests[0].result.finding : ran.tests[0].error;
  t0 = performance.now();
  await client.runStudy(saved.study_id);
  out.run_study_cached_ms = performance.now() - t0;
  t0 = performance.now();
  const samples = await client.getSliceSamples({ study_id: saved.study_id, selection: { mode: 'all' }, slice_rules: ['full_power'],
                                                 slice_ids: cold.slices.slice(0, 12).map(s => s.slice_id), channels: ['rpm', 'map_inhg'], anchor: 'crossing' });
  out.samples_12_slices_ms = performance.now() - t0;
  out.samples_returned = samples.slices.length;
  out.heap_end = await client.engineMemory();
  return out;
}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default=str(ROOT / "data" / "logs"))
    ap.add_argument("--through", default="2026-10-28", help="only logs whose date in the name is on or before this (the acceptance set)")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright
    dist = ROOT / "web" / "dist"
    assert (dist / "runtime.json").is_file(), "build first: (cd web && npm run build:browser)"
    work = Path(tempfile.mkdtemp(prefix="eis-research-timing-"))
    folder = work / "logs"
    folder.mkdir()
    cutoff = args.through.replace("-", "")
    import re
    for p in sorted(Path(args.logs).glob("*.csv")):
        m = re.search(r"(\d{8})", p.name) or re.search(r"(\d{4})-(\d{2})-(\d{2})", p.name)
        d = m.group(1) if m and len(m.groups()) == 1 else ("".join(m.groups()) if m else None)
        if d is None or d <= cutoff:
            shutil.copy2(p, folder / p.name)
    httpd = serve(dist)
    url = f"http://localhost:{httpd.server_address[1]}/"
    profile = tempfile.mkdtemp(prefix="eis-research-timing-profile-")
    result: dict = {"logs_copied": len(list(folder.glob("*.csv"))), "through": args.through}
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(profile, headless=True)
            page = ctx.pages[0]
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            t0 = time.time(); page.goto(url); page.evaluate(READY); result["cold_ready_s"] = round(time.time() - t0, 1)
            page.evaluate("""() => { const i = document.createElement('input'); i.type = 'file'; i.id = 'timing-folder';
                                     i.webkitdirectory = true; i.multiple = true; i.style.display = 'none'; document.body.append(i); }""")
            page.set_input_files("#timing-folder", str(folder))
            run = page.evaluate(RUN)
            result.update(run)
            result["browser_version"] = ctx.browser.version if ctx.browser else None
            result["page_errors"] = errors
            ctx.close()
    finally:
        httpd.shutdown()
        shutil.rmtree(profile, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)
    result["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = HERE / "results" / "research-timing.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "finding"}, indent=2))
    print("finding:", result.get("finding"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
