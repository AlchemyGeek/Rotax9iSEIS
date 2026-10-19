"""
Server-mode walk-through through the UI (Spec 04 §10 step 5 acceptance):
a running `slingology-eis serve` — e.g. from a clean `pip install` of the
wheel — opened in the installed Chrome (Playwright, headless).

    .venv/bin/python spike/browser-host/run_server_walkthrough.py --url http://127.0.0.1:8420/ --logs DIR

Create a workspace, add a folder by path, Sync, open a flight and its
chart, edit a rule on a card, check Journal, export and download, import
the export back, and the About line. Use a server on a throwaway data root.
"""
from __future__ import annotations

import argparse
import re
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ANALYZE = re.compile(r"^Analyze \d+$")
SUMMARY = re.compile(r"(\d+) flights · (\d+) in reference")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--logs", required=True, help="a folder of logs, given to Add folder by path")
    args = ap.parse_args()
    url = args.url.rstrip("/") + "/"
    work = Path(tempfile.mkdtemp(prefix="eis-server-walk-"))
    results = []

    def ok(name, cond, **kw):
        results.append(bool(cond))
        print(("PASS " if cond else "FAIL ") + name + (f"  {kw}" if kw else ""), flush=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(work / "profile"), channel="chrome", headless=True, accept_downloads=True)
        page = ctx.pages[0]
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.get_by_text("+ New workspace").first.wait_for(timeout=60000)
        ok("the UI opens", True)
        page.get_by_text("+ New workspace").first.click()
        page.get_by_placeholder("Workspace name").fill("Server walk")
        page.get_by_role("button", name="Create", exact=True).click()
        page.get_by_role("button", name="Add folder").wait_for(timeout=30000)
        ok("workspace created; Add folder by path offered", True)
        page.get_by_role("button", name="Add folder").click()
        page.get_by_label("Folder path").fill(str(Path(args.logs).resolve()))
        page.keyboard.press("Enter")
        analyze = page.get_by_role("button", name=ANALYZE)
        analyze.wait_for(timeout=60000)
        label = analyze.inner_text()
        analyze.click()
        t0 = time.time()
        while time.time() - t0 < 600 and page.get_by_role("button", name=ANALYZE).count():
            time.sleep(0.5)
        time.sleep(2)
        flights = int(SUMMARY.search(page.get_by_text(SUMMARY).first.inner_text()).group(1))
        ok("folder added by path and synced", flights > 0, button=label, flights=flights, seconds=round(time.time() - t0, 1))
        page.locator("tr").filter(has_text="2026-").first.locator("td").nth(1).click()
        page.wait_for_url("**/#/flights/*", timeout=30000)
        page.get_by_text("Timeline").first.wait_for(timeout=60000)
        ok("a flight opens with its chart", page.locator("canvas, svg").count() > 0)
        page.get_by_role("button", name="Edit rules…").first.click()
        page.locator("select").filter(has_text="limit").first.select_option("warning")
        page.get_by_role("button", name="Apply to all flights").click()
        page.get_by_text("Rule changed").first.wait_for(timeout=60000)
        ok("a rule edited on a card", True)
        page.goto(url + "#/journal")
        page.get_by_text("Rule: limit_exceedances").first.wait_for(timeout=30000)
        ok("Journal lists the rule edit", True)
        page.goto(url + "#/settings?tab=app")
        page.get_by_text("Data location").first.wait_for(timeout=30000)
        with page.expect_download(timeout=120000) as dl:
            page.get_by_role("button", name="Export workspace…").click()
        exported = work / dl.value.suggested_filename
        dl.value.save_as(exported)
        ok("export downloads", exported.stat().st_size > 1000, file=exported.name, bytes=exported.stat().st_size)
        page.get_by_role("button", name=re.compile("Import workspace")).first.click()
        dialog = page.get_by_role("dialog", name="Import workspace")
        dialog.locator('input[type="file"]').set_input_files(str(exported))
        dialog.get_by_role("button", name="Continue").click()                 # the summary
        dialog.get_by_role("button", name="Create workspace").click()         # the name
        dialog.get_by_role("button", name="Continue").wait_for(timeout=120000)  # the match
        matched = dialog.get_by_test_id("match-result").inner_text().splitlines()[0]
        dialog.get_by_role("button", name="Continue").click()
        page.get_by_text(SUMMARY).first.wait_for(timeout=120000)
        ok("the export imports as a new workspace", True, match=matched)
        page.goto(url + "#/settings?tab=engine")
        ok("About line: the local server", "on the local server" in page.get_by_test_id("engine-host").inner_text())
        ok("no page errors", not errors, errors=errors[:3])
        ctx.close()
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
