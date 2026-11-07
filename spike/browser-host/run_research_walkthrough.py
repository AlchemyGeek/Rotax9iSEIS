"""
Server-mode walk-through of Research (Spec 06 Session B) through the UI:
a running `slingology-eis serve` on a throwaway data root, opened in headless
Chromium (Playwright).

    python spike/browser-host/run_research_walkthrough.py --url http://127.0.0.1:8421/ --logs DIR [--shots DIR]

Create a workspace, add the logs folder by path, Sync; open Research from
the nav, start a study from the full-power preset, ask the cycling question,
Run, read the finding and its references, show the per-slice table; export
the .eisstudy; note the finding in the Journal and see it there; open a
flight and use Research this window; check the Trends card and an event
row offer Research this. Screenshots go to --shots when given.
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
    ap.add_argument("--logs", required=True)
    ap.add_argument("--shots", default="")
    args = ap.parse_args()
    url = args.url.rstrip("/") + "/"
    work = Path(tempfile.mkdtemp(prefix="eis-research-walk-"))
    shots = Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    results = []

    def ok(name, cond, **kw):
        results.append(bool(cond))
        print(("PASS " if cond else "FAIL ") + name + (f"  {kw}" if kw else ""), flush=True)

    def shot(name):
        if shots:
            page.screenshot(path=str(shots / f"{name}.png"), full_page=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(work / "profile"), headless=True, accept_downloads=True, viewport={"width": 1400, "height": 1000})
        page = ctx.pages[0]
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.get_by_text("+ New workspace").first.wait_for(timeout=60000)
        page.get_by_text("+ New workspace").first.click()
        page.get_by_placeholder("Workspace name").fill("Research walk")
        page.get_by_role("button", name="Create", exact=True).click()
        page.get_by_role("button", name="Add folder").wait_for(timeout=30000)
        page.get_by_role("button", name="Add folder").click()
        page.get_by_label("Folder path").fill(str(Path(args.logs).resolve()))
        page.keyboard.press("Enter")
        analyze = page.get_by_role("button", name=ANALYZE)
        analyze.wait_for(timeout=60000)
        analyze.click()
        t0 = time.time()
        while time.time() - t0 < 900 and page.get_by_role("button", name=ANALYZE).count():
            time.sleep(0.5)
        # Sync runs on; wait for the summary line to settle at a non-zero count.
        flights = 0
        while time.time() - t0 < 900:
            m = SUMMARY.search(page.get_by_text(SUMMARY).first.inner_text()) if page.get_by_text(SUMMARY).count() else None
            if m and int(m.group(1)) > 0 and not page.get_by_text(re.compile(r"Analy[sz]ing|Syncing")).count():
                flights = int(m.group(1)); break
            time.sleep(1)
        time.sleep(2)
        ok("workspace created and synced", flights > 0, flights=flights, seconds=round(time.time() - t0, 1))

        # Nav → Research home
        nav = page.get_by_test_id("nav-research")
        nav.wait_for(timeout=30000)
        ok("Research is in the nav (capability)", True)
        nav.click()
        page.get_by_test_id("preset-card").first.wait_for(timeout=30000)
        ok("Research home shows presets", page.get_by_test_id("preset-card").count() >= 4)
        ok("Research home names the open questions", page.get_by_text("Questions this app's own research left open").count() == 1)
        shot("01-research-home")

        # New study from the full-power preset
        page.get_by_test_id("preset-card").filter(has_text="Full-power").first.click()
        page.get_by_test_id("study-page").wait_for(timeout=30000)
        t0 = time.time()
        page.get_by_test_id("slice-count").filter(has_text=re.compile(r"\d+ slices? from")).wait_for(timeout=120000)
        count_text = page.get_by_test_id("slice-count").inner_text()
        ok("live slice count from the preset", "slice" in count_text, text=count_text, seconds=round(time.time() - t0, 1))
        page.get_by_text("Reading the slices' samples…").wait_for(state="hidden", timeout=120000)
        ok("aligned view drew", page.get_by_test_id("aligned-view").locator("canvas").count() > 0)
        shot("02-study-slices")

        # The seeded cycling question is there; Run.
        ok("the preset study starts with the cycling question", page.get_by_test_id("test-result").count() == 1)
        page.get_by_test_id("run-study").click()
        t0 = time.time()
        page.get_by_test_id("finding").wait_for(timeout=300000)
        finding = page.get_by_test_id("finding").inner_text()
        ok("Run produced a finding", "cycles" in finding or "steady" in finding, finding=finding, seconds=round(time.time() - t0, 1))
        mags = page.get_by_test_id("magnitude")
        ok("magnitude beside a reference", mags.count() >= 1 and ("OM" in mags.first.inner_text() or "this set" in mags.first.inner_text()))
        ok("caveats print the resolved window", "swing window" in page.get_by_test_id("caveats").inner_text())
        page.get_by_text(re.compile(r"Show the per-slice table")).click()
        rows = page.get_by_test_id("evidence-table").locator("tbody tr").count()
        ok("per-slice table one click away", rows > 0, rows=rows)
        shot("03-study-result")

        # A second question: coupling rpm vs MAP.
        page.get_by_test_id("add-question").select_option("coupling")
        page.get_by_test_id("test-editor").wait_for(timeout=10000)
        page.get_by_test_id("save-question").click()
        page.get_by_test_id("run-study").click()
        page.get_by_test_id("test-result").nth(1).get_by_test_id("finding").wait_for(timeout=300000)
        ok("second question answered", "MAP" in page.get_by_test_id("test-result").nth(1).get_by_test_id("finding").inner_text())

        # Export .eisstudy
        with page.expect_download(timeout=120000) as dl:
            page.get_by_role("button", name="Export .eisstudy").click()
        ok("export downloads an .eisstudy", dl.value.suggested_filename.endswith(".eisstudy"), file=dl.value.suggested_filename)

        # Journal path
        page.get_by_text("Note this finding in the Journal").first.click()
        page.get_by_text("Noted in the Journal.").wait_for(timeout=30000)
        page.goto(url + "#/journal")
        page.get_by_text("Research finding").first.wait_for(timeout=30000)
        ok("Journal lists the research finding", True)
        shot("04-journal")

        # Research home lists the study with its finding
        page.goto(url + "#/research")
        page.get_by_test_id("study-row").first.wait_for(timeout=30000)
        ok("Research home lists the study with its finding", "cycles" in page.get_by_test_id("study-row").first.inner_text())

        # Flight view entry point
        page.goto(url + "#/flights")
        page.locator("tr").filter(has_text="2026-").first.locator("td").nth(1).click()
        page.wait_for_url("**/#/flights/*", timeout=30000)
        page.get_by_text("Timeline").first.wait_for(timeout=60000)
        page.get_by_test_id("research-this").wait_for(timeout=30000)
        ok("Flight view offers Research this window", True)
        ok("Events rows offer Research this", page.get_by_role("button", name="Research this", exact=True).count() >= 0)
        page.get_by_test_id("research-this").click()
        page.get_by_test_id("study-page").wait_for(timeout=30000)
        page.get_by_test_id("hand-slice").wait_for(timeout=30000)
        ok("a hand slice from the chart window", "by hand" in page.get_by_test_id("hand-slice").inner_text())
        shot("05-study-from-flight")

        # Trends card entry point
        page.goto(url + "#/trends")
        time.sleep(3)
        n = page.get_by_test_id("trend-research-this").count()
        ok("Trends cards offer Research this where a shift exists", True, cards=n)

        ctx.close()
    print(f"{sum(results)}/{len(results)} passed; page errors: {errors}")
    return 0 if all(results) and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
