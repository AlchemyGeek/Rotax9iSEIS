"""
Run the persistence probe in Chromium (Spec 04 v0.6 §9.4, step 3).

Serves this folder on localhost, opens the probe in the installed Google
Chrome through Playwright (no browser is downloaded), lets it run its first
visit and its own reload, then closes the browser and relaunches it on the
same persistent profile for the restart check. Saves the probe's JSON under
results/.

    .venv/bin/python spike/persistence/run_chromium.py [--headed] [--idbfs]

Needs the `playwright` Python package and Google Chrome; the page loads
Pyodide 0.28.0 from the jsDelivr CDN, so it needs the network.
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
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
TIMEOUT_MS = 240_000


def serve() -> tuple[socketserver.TCPServer, int]:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    httpd = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(HERE)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def stage_is(page, stage: str) -> None:
    page.wait_for_function(f"() => window.__probe && window.__probe.stage === {json.dumps(stage)}", timeout=TIMEOUT_MS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--idbfs", action="store_true", help="also run the IDBFS fallback even if OPFS passes")
    args = ap.parse_args()

    httpd, port = serve()
    url = f"http://localhost:{port}/index.html" + ("?idbfs=1" if args.idbfs else "")
    profile = Path(tempfile.mkdtemp(prefix="eis-probe-profile-"))
    log: list[str] = []
    try:
        with sync_playwright() as p:
            launch = dict(user_data_dir=str(profile), channel="chrome", headless=not args.headed)

            # Visits 1 and 2: the write checks, then the page's own reload.
            ctx = p.chromium.launch_persistent_context(**launch)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.on("console", lambda m: log.append(f"[{m.type}] {m.text}"))
            page.goto(url)
            stage_is(page, "awaiting_restart")
            ctx.close()                                    # quit the browser

            # Visit 3: a new browser process on the same profile.
            ctx = p.chromium.launch_persistent_context(**launch)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.on("console", lambda m: log.append(f"[{m.type}] {m.text}"))
            page.goto(url)
            stage_is(page, "done")
            result = page.evaluate("() => window.__probe")
            result["runner"] = {"tool": "playwright", "channel": "chrome", "headless": not args.headed,
                                "browser_version": ctx.browser.version if ctx.browser else None,
                                "restart": "browser closed and relaunched on the same persistent profile",
                                "console": log[-50:]}
            ctx.close()
    finally:
        httpd.shutdown()
        shutil.rmtree(profile, ignore_errors=True)

    out = HERE / "results"
    out.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"chromium-{stamp}.json"
    path.write_text(json.dumps(result, indent=2))
    checks = {k: v.get("pass") for k, v in result["results"].items() if isinstance(v, dict) and "pass" in v}
    print(json.dumps(checks, indent=2))
    print(f"saved {path.relative_to(HERE.parent.parent)}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
