"""
Session H walkthrough (Spec 16 v0.15): the pages, in headless Chrome, on
synthetic logs (no private data; nothing here names a real flight).

  move     D17 — a browser workspace (the static site in web/dist) with two
           flights and a question with two marks, moved by the button to a
           throwaway `slingology-eis serve`; the local pages open with the
           note, the log folder is linked and synced, the marks open their
           flights; the website's copy is marked as the copy.

Usage:
    .venv/bin/python spike/browser-host/run_session_h_walkthrough.py move [--shots DIR]

`web/dist` must be the browser build (npm run build && npm run build:browser).
The website's real origin can't be reproduced here (it is served from
localhost, a loopback origin); the cross-origin rule for the website's
origin is tested in tests/unit/test_move_workspace.py.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import re
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from slingology_eis.loader import flight_fingerprint, flight_id, load_log_bytes  # noqa: E402
from tests.unit.test_workspace_export import _log  # noqa: E402  (synthetic flying logs)

ANALYZE = re.compile(r"^Analyze \d+$")


def fid_of(path: Path) -> str:
    return flight_id(flight_fingerprint(*load_log_bytes(path.read_bytes(), path.name)))


def serve_site(site: Path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    handler.log_message = lambda *a, **k: None
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def rpc(base: str, op: str, params: dict) -> dict:
    req = urllib.request.Request(f"{base}/rpc", data=json.dumps({"op": op, "params": params}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def start_eis(home: Path) -> tuple[subprocess.Popen, str]:
    port = free_port()
    env = {**os.environ, "SLINGOLOGY_EIS_HOME": str(home)}
    proc = subprocess.Popen([sys.executable, "-m", "slingology_eis.cli", "serve", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            urllib.request.urlopen(base + "/eis/probe", timeout=1).read()
            return proc, base
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("the throwaway EIS didn't start")


def synthetic_folder(work: Path, days=(1, 2)) -> Path:
    folder = work / "My logs"
    folder.mkdir()
    for d in days:
        (folder / f"log_202601{d:02d}_120000_KAWO.csv").write_bytes(_log(d))
    return folder


def create_browser_workspace(page, name: str, folder: Path) -> None:
    """The first workspace, from a folder of logs, in the browser."""
    page.get_by_text("+ New workspace").first.wait_for(timeout=120000)
    page.get_by_text("+ New workspace").first.click()
    page.get_by_placeholder("Workspace name").fill(name)
    page.get_by_role("button", name="Create", exact=True).click()
    with page.expect_file_chooser() as fc:
        page.get_by_role("button", name="Choose folder…").click()
    fc.value.set_files(str(folder))


def analyse(page) -> None:
    page.get_by_role("button", name=ANALYZE).click(timeout=120000)
    t0 = time.time()
    while time.time() - t0 < 600 and page.get_by_role("button", name=ANALYZE).count():
        time.sleep(0.5)
    page.get_by_test_id("flight-route-cell").first.wait_for(timeout=600000)


def mark(page, url: str, fid: str, a: int, b: int, note: str, new_title: str | None) -> str:
    page.goto(url + "#/research")
    page.goto(url + f"#/flights/{fid}?window={a}-{b}&channels=rpm")
    page.get_by_test_id("mark-open").wait_for(timeout=120000)
    page.wait_for_function("() => !document.querySelector('[data-testid=mark-open]')?.disabled", timeout=120000)
    page.get_by_test_id("mark-open").click()
    page.get_by_test_id("mark-dialog").wait_for(timeout=30000)
    page.get_by_label("Note").fill(note)
    if new_title:
        page.get_by_label("New question title").fill(new_title)
    page.get_by_test_id("mark-save").click()
    page.get_by_test_id("mark-done").wait_for(timeout=30000)
    return page.get_by_test_id("mark-done").inner_text()


def run_move(args, work: Path, step, shot, errors) -> None:
    folder = synthetic_folder(work)
    f1, f2 = sorted(fid_of(p) for p in folder.iterdir())
    home = work / "local-home"
    home.mkdir()
    proc, local = start_eis(home)
    try:
        rpc(local, "create_workspace", {"name": "Already here", "engine_model": "916iS"})
        site = serve_site(Path(args.site))
        url = f"http://localhost:{site.server_address[1]}/"
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(str(work / "profile"), channel="chrome", headless=not args.headed,
                                                       viewport={"width": 1400, "height": 1000}, color_scheme="dark")
            ctx.add_init_script("delete window.showDirectoryPicker;")
            # The page's local EIS: the throwaway server, not the owner's 8420.
            ctx.add_init_script(f"try {{ localStorage.setItem('slingology-eis.local-eis', '{local}'); }} catch (e) {{}}")
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            create_browser_workspace(page, "My Sling", folder)
            analyse(page)
            step("website: two synthetic flights analysed", page.get_by_test_id("flight-route-cell").count() == 2)
            done1 = mark(page, url, f1, 300, 360, "rpm wanders in the climb", "rough climbs")
            done2 = mark(page, url, f2, 320, 380, "again", None)
            step("website: a question with two marks", "(1 mark)" in done1 and "(2 marks)" in done2, second=done2)

            page.goto(url + "#/research")
            banner = page.get_by_test_id("move-workspace")
            banner.wait_for(timeout=30000)
            step("website: Research home offers Move my workspace (EIS answers here)",
                 "Move my workspace to EIS on this computer" in banner.inner_text())
            shot(page, "h-move-banner.png", banner)
            page.goto(url + "#/settings?tab=app")
            step("website: Settings → App offers it too", page.get_by_test_id("move-workspace").first.wait_for(timeout=30000) is None)

            page.goto(url + "#/research")
            page.get_by_test_id("move-workspace-button").click()
            page.wait_for_url(f"{local}/**", timeout=60000)
            note = page.get_by_test_id("moved-note")
            note.wait_for(timeout=60000)
            step("local: the pages open with the note to link the folder and Sync",
                 "Link your log folder on Flights and Sync" in note.inner_text() and "moved=" not in page.url, url=page.url)
            shot(page, "h-move-local.png")
            names = sorted(w["name"] for w in rpc(local, "list_workspaces", {})["result"])
            active = rpc(local, "get_active_workspace", {})["result"]["manifest"]["name"]
            step("local: an additional workspace, selected", names == ["Already here", "My Sling (imported)"]
                 and active == "My Sling (imported)", workspaces=names)

            # Link the log folder and Sync.
            page.get_by_role("button", name="Add folder").click()
            page.get_by_placeholder("/path/to/logs").fill(str(folder))
            page.get_by_placeholder("/path/to/logs").press("Enter")
            analyse(page)
            step("local: linked and synced, both flights", page.get_by_test_id("flight-route-cell").count() == 2)
            page.get_by_test_id("nav-research").click()
            q = page.get_by_test_id("question").first
            q.wait_for(timeout=60000)
            step("local: the question arrived with its two marks",
                 "rough climbs" in q.inner_text() and q.get_by_test_id("pin").count() == 2)
            q.get_by_test_id("pin").first.get_by_test_id("pin-open").click()
            page.wait_for_url(re.compile(rf"/flights/({f1}|{f2})\?window="), timeout=30000)
            step("local: a mark opens its flight at the window", True, url=page.url.split("#")[1])

            page.goto(url + "#/research")
            copy = page.get_by_test_id("move-copy")
            copy.wait_for(timeout=60000)
            step("website: the workspace left behind is marked as the copy", "This is now the copy." in copy.inner_text())
            shot(page, "h-move-copy.png", copy)
            ctx.close()
        site.shutdown()
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("part", choices=["move"])
    ap.add_argument("--site", default=str(ROOT / "web" / "dist"))
    ap.add_argument("--shots", default=None)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="eis-h-"))
    steps: list[dict] = []
    errors: list[str] = []

    def step(name, ok, **info):
        steps.append({"step": name, "ok": bool(ok), **info})
        print(("PASS " if ok else "FAIL ") + name + (f"  {info}" if info else ""), flush=True)

    def shot(page, name, locator=None):
        if args.shots:
            Path(args.shots).mkdir(parents=True, exist_ok=True)
            (locator or page).screenshot(path=str(Path(args.shots) / name))

    try:
        {"move": run_move}[args.part](args, work, step, shot, errors)
    except Exception as e:  # noqa: BLE001 — report the step that broke, then fail
        step(f"walkthrough stopped: {type(e).__name__}: {str(e).splitlines()[0][:200]}", False)
    step("no page errors", not errors, errors=errors[:3])
    ok = all(s["ok"] for s in steps)
    print(f"{sum(s['ok'] for s in steps)}/{len(steps)} passed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
