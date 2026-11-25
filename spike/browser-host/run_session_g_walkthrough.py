"""
Session G walk-through (Spec 16 D15, D16; acceptance 17 and 19's page
clauses), through the real UI in the installed Chrome (Playwright).

    # server mode: a running `slingology-eis serve` on a copy of a data root
    .venv/bin/python spike/browser-host/run_session_g_walkthrough.py --url http://127.0.0.1:8432/ --flight-log F1.csv --second-log F2.csv [--shots DIR]
    # browser mode: web/dist (the browser build) served statically, the two logs added by folder
    .venv/bin/python spike/browser-host/run_session_g_walkthrough.py --browser --flight-log F1.csv --second-log F2.csv [--shots DIR]

Steps: Research home is notebooks + inbox (no hand-study, question-form,
Signal or Compare screen is reachable); the Flight view's Signal toggle
lays the strips and, on the first takeoff window of --flight-log, reads
swing 170 rpm / period 3.4 s / MAP correlation 0.92 beside the OM line;
*Mark for Claude* marks that window under a new question "rough climbs",
and a window of --second-log under the same question; the inbox shows one
question with two marks, and a mark opens its flight at the window with
its channels. In browser mode the question waits with the hand-off line.
Flights are found by their content-derived flight_id, the same on both
hosts. Log names are arguments (they carry airports; see the session
report). Writes nothing to the logs folder.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import re
import shutil
import socketserver
import sys
import tempfile
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from slingology_eis.loader import flight_fingerprint, flight_id, load_log_bytes  # noqa: E402

ANALYZE = re.compile(r"^Analyze \d+$")


def fid_of(path: Path) -> str:
    return flight_id(flight_fingerprint(*load_log_bytes(path.read_bytes(), path.name)))


def serve(site: Path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    handler.log_message = lambda *a, **k: None
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="server mode: a running serve on a throwaway copy")
    ap.add_argument("--browser", action="store_true", help="browser mode: serve --site statically")
    ap.add_argument("--site", default=str(ROOT / "web" / "dist"))
    ap.add_argument("--logs", default=str(ROOT / "data" / "logs"))
    ap.add_argument("--flight-log", required=True, help="the log of acceptance 17's flight (file name in --logs)")
    ap.add_argument("--window", default="616-662", help="the first takeoff of --flight-log (the full-power preset's first slice)")
    ap.add_argument("--second-log", required=True, help="another flight of the same aircraft, in the workspace")
    ap.add_argument("--second-window", default="300-360")
    ap.add_argument("--shots", default=None)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    if bool(args.url) == bool(args.browser):
        ap.error("give --url (server mode) or --browser")
    logs = Path(args.logs).resolve()
    first, second = logs / args.flight_log, logs / args.second_log
    f1, f2 = fid_of(first), fid_of(second)
    a, b = args.window.split("-")
    shots = Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="eis-g-walk-"))
    httpd = None
    if args.browser:
        httpd = serve(Path(args.site))
        url = f"http://localhost:{httpd.server_address[1]}/"
    else:
        url = args.url.rstrip("/") + "/"
    steps, errors = [], []

    def step(name, ok, **info):
        steps.append({"step": name, "ok": bool(ok), **info})
        print(("PASS " if ok else "FAIL ") + name + (f"  {info}" if info else ""), flush=True)

    def shot(page, name, locator=None):
        if shots:
            (locator or page).screenshot(path=str(shots / name))

    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(str(work / "profile"), channel="chrome", headless=not args.headed,
                                                       viewport={"width": 1400, "height": 1000}, color_scheme="dark")
            ctx.add_init_script("delete window.showDirectoryPicker;")
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            if args.browser:
                folder = work / "My logs"
                folder.mkdir()
                for src in (first, second):
                    shutil.copy(src, folder / src.name)
                page.get_by_text("+ New workspace").first.wait_for(timeout=120000)
                page.get_by_text("+ New workspace").first.click()
                page.get_by_placeholder("Workspace name").fill("Session G walkthrough")
                page.get_by_role("button", name="Create", exact=True).click()
                with page.expect_file_chooser() as fc:
                    page.get_by_role("button", name="Choose folder…").click()
                fc.value.set_files(str(folder))
                page.get_by_role("button", name=ANALYZE).click(timeout=60000)
                t0 = time.time()
                while time.time() - t0 < 600 and page.get_by_role("button", name=ANALYZE).count():
                    time.sleep(0.5)
                page.get_by_test_id("flight-route-cell").first.wait_for(timeout=600000)
                step("two logs analysed in the browser", page.get_by_test_id("flight-route-cell").count() == 2)

            # D15 — Research home is notebooks + inbox; nothing of the hand-study UI is reachable.
            page.get_by_test_id("nav-research").wait_for(timeout=120000)
            page.get_by_test_id("nav-research").click()
            page.get_by_test_id("inbox").wait_for(timeout=120000)
            page.get_by_test_id("research-help").click()          # Spec 03 v0.34: the model sentence is in the page's help
            page.get_by_test_id("research-model").wait_for(timeout=120000)
            page.keyboard.press("Escape")
            body = page.inner_text("body")
            step("Research home: the notebooks and the inbox, no hand study, preset, question form, Signal or Compare",
                 page.get_by_test_id("new-study").count() == 0 and not re.search(r"Start from a preset|Is this signal steady|Compare|Research this", body))
            page.goto(url + "#/research/new")
            page.get_by_text("There is no such notebook in this workspace.").wait_for(timeout=60000)
            step("/research/new is not a page", page.get_by_test_id("mark-open").count() == 0 and page.get_by_test_id("new-study").count() == 0)

            # D15 — the seeing aid; acceptance 17's numbers.
            page.goto(url + f"#/flights/{f1}")
            page.get_by_test_id("signal-toggle").wait_for(timeout=120000)
            step("the Flight view has no Research this", page.get_by_test_id("research-this").count() == 0)
            page.get_by_test_id("signal-toggle").click()
            page.get_by_test_id("signal-strips").wait_for(timeout=300000)
            labels = page.get_by_test_id("signal-channel-label").all_inner_texts()
            step("Signal lays a swing and a lit-repeat strip per channel over the whole flight",
                 len(labels) >= 2 and labels[0].startswith("RPM"), rpm=labels[0] if labels else None)
            shot(page, "g-signal-strips.png", page.locator("#timeline"))
            page.goto(url + f"#/flights/{f1}?window={a}-{b}&channels=rpm,map_inhg")
            page.get_by_test_id("signal-toggle").wait_for(timeout=120000)
            time.sleep(1)
            if page.get_by_test_id("signal-toggle").get_attribute("aria-pressed") != "true":
                page.get_by_test_id("signal-toggle").click()
            page.get_by_test_id("signal-window").wait_for(timeout=300000)
            rows = {r.locator("td").nth(0).inner_text(): [td.inner_text() for td in r.locator("td").all()]
                    for r in page.get_by_test_id("signal-number").all()}
            sw, pe, co = rows.get("RPM swing", []), rows.get("RPM period", []), rows.get("MAP with the reference", [])
            step("acceptance 17: swing 170 rpm beside the OM line, period 3.4 s, MAP correlation 0.92",
                 sw[1:2] == ["170 rpm peak-to-peak"] and "OM" in (sw[2] if len(sw) > 2 else "")
                 and pe[1:2] == ["3.4 s"] and (co[1] if len(co) > 1 else "").startswith("correlation 0.92"),
                 swing=sw[1:], period=pe[1:2], corr=co[1:2])
            shot(page, "g-signal-window.png", page.locator("#timeline"))

            # D16 — Mark for Claude: two windows on two flights under one question.
            page.wait_for_function("() => !document.querySelector('[data-testid=mark-open]')?.disabled", timeout=120000)
            page.get_by_test_id("mark-open").click()
            page.get_by_test_id("mark-dialog").wait_for(timeout=30000)
            page.get_by_label("Note").fill("rpm wanders at takeoff power")
            page.get_by_label("New question title").fill("rough climbs")
            shot(page, "g-mark-dialog.png", page.get_by_test_id("mark-for-claude"))
            page.get_by_test_id("mark-save").click()
            done = page.get_by_test_id("mark-done")
            done.wait_for(timeout=30000)
            step("Mark for Claude: a new question, and the confirmation says where it went",
                 "under “rough climbs” (1 mark) in Research → Inbox" in done.inner_text(), said=done.inner_text())
            sa, sb = args.second_window.split("-")
            page.goto(url + "#/research")     # to the next flight as a user goes, not hash to hash
            page.get_by_test_id("inbox").wait_for(timeout=120000)
            page.goto(url + f"#/flights/{f2}?window={sa}-{sb}&channels=rpm")
            page.get_by_test_id("mark-open").wait_for(timeout=120000)
            page.wait_for_function("() => !document.querySelector('[data-testid=mark-open]')?.disabled", timeout=120000)
            page.get_by_test_id("mark-open").click()
            page.get_by_label("Open question", exact=True).wait_for(timeout=30000)
            page.get_by_label("Note").fill("again, less")
            page.get_by_test_id("mark-save").click()
            page.get_by_test_id("mark-done").wait_for(timeout=30000)
            step("a second flight's window under the same question (the open one offered first)",
                 "(2 marks)" in page.get_by_test_id("mark-done").inner_text())

            page.goto(url + "#/research")
            q = page.get_by_test_id("question").filter(has_text="rough climbs").first
            q.wait_for(timeout=120000)
            q.get_by_test_id("inbox-line").first.click()          # Spec 03 v0.34: a digest line expands in place
            pins = q.get_by_test_id("pin")
            pins.first.wait_for(timeout=30000)
            step("acceptance 19: the inbox shows one question with two marks",
                 page.get_by_test_id("question").filter(has_text="rough climbs").count() == 1 and pins.count() == 2,
                 notes=[n for n in q.get_by_test_id("pin-note").all_inner_texts()])
            if args.browser:
                h = page.get_by_test_id("inbox-install")
                step("on the website the question waits, with the install link",
                     h.count() == 1 and "“rough climbs” is waiting for Claude" in h.inner_text())
            else:
                step("with a bench there is no hand-off line", page.get_by_test_id("inbox-install").count() == 0)
            shot(page, "g-inbox-question.png", page.get_by_test_id("inbox"))
            pins.first.get_by_test_id("pin-open").click()
            page.wait_for_url(re.compile(r".*/flights/.*"), timeout=30000)
            want = f"/flights/{f1}?window={a}-{b}&channels=rpm,map_inhg"
            step("a mark opens its flight at the window, with its channels", page.url.endswith(want), url=page.url.split("#")[-1])
            page.get_by_test_id("signal-toggle").wait_for(timeout=120000)

            # Clean up the marks (server mode runs on a copy; leave it as it was found).
            page.goto(url + "#/research")
            q = page.get_by_test_id("question").filter(has_text="rough climbs").first
            q.wait_for(timeout=60000)
            q.get_by_test_id("inbox-item-menu").first.click()     # the item's ⋯ menu
            page.get_by_test_id("question-delete").click()
            q.get_by_test_id("question-delete-confirm").click()
            un = page.get_by_test_id("questions-unassigned")
            un.wait_for(timeout=30000)
            un.get_by_test_id("inbox-line").first.click()
            un.get_by_test_id("pin").first.wait_for(timeout=30000)
            while un.get_by_test_id("pin").count():
                n = un.get_by_test_id("pin").count()
                un.get_by_test_id("pin").first.get_by_test_id("pin-menu").click()     # the mark's ⋯ menu
                page.get_by_test_id("pin-delete").click()
                t0 = time.time()
                while time.time() - t0 < 20 and page.get_by_test_id("questions-unassigned").get_by_test_id("pin").count() == n:
                    time.sleep(0.2)
                if not page.get_by_test_id("questions-unassigned").count():
                    break
            step("the question deleted leaves its marks unassigned; the marks delete", True)
            ctx.close()
    finally:
        if httpd:
            httpd.shutdown()
        shutil.rmtree(work, ignore_errors=True)
    step("no page errors", not errors, errors=errors[:3])
    failed = [s for s in steps if not s["ok"]]
    print(f"{len(steps) - len(failed)} of {len(steps)} steps")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
