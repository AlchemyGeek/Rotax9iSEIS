"""
Offline and update check for the static site (Spec 04 §9.7, §10 step 6),
driven through the UI in the installed Chrome (Playwright, headless).

    .venv/bin/python spike/browser-host/run_offline.py --site DIR [--logs DIR]

1. First visit online: the engine downloads, the service worker caches the
   whole release.
2. The network off (Playwright offline): the site opens from this device,
   a workspace is created, a log is dropped and analysed, a flight opens.
3. A new build of the site (same files plus a marker, so a new release):
   back online, the next visit switches to it, says "Updated to version …"
   once, and runs it; the visit after says nothing.

The site is served from a temporary copy, which step 3 replaces.
Writes spike/browser-host/results/offline-*.json.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import re
import shutil
import socketserver
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import build_site  # noqa: E402

ANALYZE = re.compile(r"^Analyze \d+$")
CACHED_RELEASE = """async () => {
  const keys = await caches.keys();
  for (const k of keys) {
    const c = await caches.open(k);
    for (const r of await c.keys()) if (r.url.endsWith('__eis_manifest__')) return (await (await c.match(r)).json()).release;
  }
  return null;
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
    ap.add_argument("--site", required=True, help="a site built by scripts/build_site.py")
    ap.add_argument("--logs", default=str(ROOT / "data" / "logs"))
    args = ap.parse_args()
    site = Path(args.site).resolve()
    work = Path(tempfile.mkdtemp(prefix="eis-offline-"))
    live = work / "site"
    shutil.copytree(site, live)
    log = sorted(p for p in Path(args.logs).resolve().iterdir() if p.suffix.lower() == ".csv")[-1]
    httpd = serve(live)
    url = f"http://localhost:{httpd.server_address[1]}/"
    steps: list[dict] = []
    errors: list[str] = []

    def step(name, ok, **info):
        steps.append({"step": name, "ok": bool(ok), **info})
        print(("PASS " if ok else "FAIL ") + name + (f"  {info}" if info else ""), flush=True)

    def launch(p, offline=False):
        ctx = p.chromium.launch_persistent_context(str(work / "profile"), channel="chrome", headless=True, offline=offline)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        return ctx, page

    def loading_text(page):
        try:
            page.get_by_test_id("engine-loading").wait_for(timeout=4000)
            return page.get_by_test_id("engine-loading").inner_text()
        except Exception:
            return None

    with sync_playwright() as p:
        # 1. First visit, online.
        ctx, page = launch(p)
        page.goto(url)
        first = loading_text(page)
        page.get_by_text("+ New workspace").first.wait_for(timeout=90000)
        t0 = time.time()
        release = None
        while time.time() - t0 < 120 and not release:
            release = page.evaluate(CACHED_RELEASE)
            time.sleep(0.5)
        cache_bytes = page.evaluate("async () => (await navigator.storage.estimate()).usageDetails?.caches ?? null")
        step("first visit: downloads, then the whole release is cached", first and "Downloading" in first and release,
             release=release, cache_seconds=round(time.time() - t0, 1), cache_bytes=cache_bytes)
        ctx.close()

        # 2. Network off.
        ctx, page = launch(p, offline=True)
        failed: list[str] = []
        page.on("requestfailed", lambda r: failed.append(r.url))
        t0 = time.time()
        page.goto(url)
        again = loading_text(page)
        page.get_by_text("+ New workspace").first.wait_for(timeout=90000)
        step("offline: the site opens from this device", again is None or "Loading from this device" in again,
             loading=again and again.splitlines()[0], seconds=round(time.time() - t0, 1))
        page.get_by_text("+ New workspace").first.click()
        page.get_by_placeholder("Workspace name").fill("Offline")
        with page.expect_navigation(timeout=60000):            # creating a workspace reloads the page
            page.get_by_role("button", name="Create", exact=True).click()
        page.get_by_test_id("onboarding-drop").wait_for(timeout=90000)
        page.get_by_test_id("file-input").set_input_files(str(log))
        t0 = time.time()
        while time.time() - t0 < 90:
            if page.get_by_role("button", name=ANALYZE).count():
                page.get_by_role("button", name=ANALYZE).click()
            if page.locator("tr").filter(has_text="2026-").locator("td.mono").count():
                break
            time.sleep(0.5)
        page.wait_for_timeout(2000)
        rows = page.locator("tr").filter(has_text="2026-").count()
        step("offline: a dropped log is analysed", rows > 0, rows=rows, seconds=round(time.time() - t0, 1))
        if not rows:
            page.screenshot(path=str(ROOT / "spike" / "browser-host" / "results" / "offline-drop-failed.png"), full_page=True)
            raise SystemExit(1)
        page.locator("tr").filter(has_text="2026-").first.locator("td.mono").first.click()
        page.wait_for_url("**/#/flights/*", timeout=30000)
        page.get_by_text("Timeline").first.wait_for(timeout=60000)
        page.wait_for_timeout(1500)
        step("offline: a flight opens with its chart", page.locator("canvas").count() > 0)
        step("offline: nothing needed the network", not failed, failed=sorted(set(failed))[:5])
        ctx.close()

        # 3. A new release on the server, back online.
        (live / "index.html").write_text((live / "index.html").read_text() + "\n<!-- offline-check rebuild -->\n")
        wheel = next((live / "engine").glob("*.whl"))
        new = build_site.write_service_worker(live, wheel)["release"]
        ctx, page = launch(p)
        page.goto(url)
        notice = page.get_by_test_id("update-notice")
        try:
            notice.wait_for(timeout=120000)
            text = notice.inner_text()
        except Exception:
            text = None
        now = page.evaluate(CACHED_RELEASE)
        step("next online visit switches to the new release and says so", text and "Updated to version" in text and now == new,
             notice=text and text.splitlines()[0], release=now, expected=new)
        page.reload()
        page.get_by_text("Flights").first.wait_for(timeout=60000)
        page.wait_for_timeout(3000)
        step("the notice is said once", page.get_by_test_id("update-notice").count() == 0)
        step("the workspace made offline is still there", page.get_by_text("Offline").count() > 0)
        ctx.close()

    step("no page errors", not errors, errors=errors[:3])
    httpd.shutdown()
    out = ROOT / "spike" / "browser-host" / "results" / f"offline-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    out.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "steps": steps}, indent=2) + "\n")
    print(f"{sum(s['ok'] for s in steps)}/{len(steps)} passed → {out.relative_to(ROOT)}")
    shutil.rmtree(work, ignore_errors=True)
    return 0 if all(s["ok"] for s in steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
