#!/usr/bin/env python3
"""Screenshots for the Investigations docs (Spec 13 §7, Spec 16 Session F).

    .venv/bin/python docs/tools/shoot_investigations.py [--out docs/img] [--headed]

Builds a throwaway data root from synthetic flights only (the test suite's
generator: a climb, cruise and a minute of full power with rpm and manifold
pressure cycling together) — no real log, tail number, airport or time — then:
an aircraft record with notes, an inbox scan, a short notebook written
through the MCP tools as Claude would write it, and a flight name. It starts
`slingology-eis serve` on a free port against that root and shoots the pages
in the installed Chrome (Playwright). The data root is deleted afterwards.

web/dist must hold a built UI (`npm run build` then `npm run build:browser`).
Re-run after a UI change and review the image diff like code.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.unit.test_research_ops import _research_log  # noqa: E402 — synthetic flights only

PY = ROOT / ".venv" / "bin" / "python"
NOTES = """2026-01-03 — Propeller governor checked at annual; no change.
2026-01-08 — Controller firmware unchanged since delivery.
"""


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Demo:
    def __init__(self, home: Path, port: int):
        self.home, self.port = home, port
        self.env = {**os.environ, "SLINGOLOGY_EIS_HOME": str(home)}

    def rpc(self, op: str, params: dict):
        body = json.dumps({"op": op, "request_id": "doc", "params": params}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/rpc", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.loads(r.read())
        if not d.get("ok"):
            raise SystemExit(f"{op}: {d}")
        return d["result"]

    def tool(self, name: str, args: dict):
        out = subprocess.run([str(PY), "-m", "slingology_eis.cli", "mcp", "call", name, json.dumps(args)],
                             capture_output=True, text=True, env=self.env, cwd=ROOT, timeout=600)
        if out.returncode:
            raise SystemExit(f"{name}: {out.stderr}")
        return json.loads(out.stdout)["result"]

    def build(self) -> dict:
        self.rpc("create_workspace", {"name": "Demo aircraft", "engine_model": "916iS"})
        ids = []
        for day in range(1, 11):
            log = _research_log(f"2026-01-{day:02d}", swing_rpm=30 if day in (4, 9) else 90)
            files = [{"content_base64": base64.b64encode(log).decode(), "filename": f"log_202601{day:02d}_120000_DEMO.csv"}]
            ids.append(self.rpc("import_files", {"files": files})["results"][0]["flight_id"])
        self.rpc("aircraft_set", {"aircraft": {"name": "Demo aircraft", "airframe": "Kit, two seats, 2024",
                                               "propeller": "Three blades, in-flight adjustable",
                                               "prop_controller": "Constant-speed controller"}, "notes": NOTES})
        self.rpc("flight_set_name", {"flight_id": ids[6], "name": "After the prop balance"})
        inbox = self.tool("inbox_list", {})
        cand = next((c["id"] for c in inbox["candidates"] if c["kind"] == "recurring"), None)
        st = self.tool("study_create", {"name": "Full-power rpm cycle", "question":
                                        "Does rpm cycle at full power, on every flight, and does manifold pressure move with it?",
                                        **({"inbox_candidate": cand} if cand else {})})
        sid = st["study_id"]
        self.tool("cell_append", {"study_id": sid, "kind": "markdown", "source":
                                  "## One flight first\n\nThe minute of full power on 1 January, rpm and manifold pressure together."})
        self.tool("cell_append", {"study_id": sid, "kind": "logview", "flight": ids[0], "start_s": 110, "end_s": 190,
                                  "channels": ["rpm", "map_inhg"], "marks": [[120, "full power"]],
                                  "title": "1 January — full power"})
        self.tool("cell_append", {"study_id": sid, "kind": "markdown", "source":
                                  "## Across the flights\n\nEvery full-power slice: is rpm cycling, how fast and how far?"})
        self.tool("cell_append", {"study_id": sid, "kind": "code", "source":
                                  "r = eis.cycling(\"full_power\", \"rpm\")\nprint(r.finding)\nr.rows.head(10)"})
        self.tool("study_finish", {"study_id": sid, "summary":
                                   "RPM cycles every 4.4 s at full power on all 10 flights, manifold pressure in step; the swing is 180 rpm on 8 and 60 rpm on 2. "
                                   "A hypothesis to test next: the governor and the boost control acting on each other.",
                                   **({"inbox_candidate": cand, "resolution": "investigating"} if cand else {})})
        return {"ids": ids, "study_id": sid}


def shoot(url: str, out: Path, study_id: str, headed: bool) -> list[str]:
    from playwright.sync_api import sync_playwright
    shots = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=not headed)
        page = browser.new_page(viewport={"width": 1100, "height": 820}, device_scale_factor=1, color_scheme="dark")

        def go(route: str, ready: str):
            page.goto(f"{url}#{route}")
            page.get_by_test_id(ready).first.wait_for(timeout=120000)
            time.sleep(1.5)

        def save(name: str, locator=None):
            target = out / name
            (locator or page).screenshot(path=str(target))
            shots.append(name)

        go("/research", "inbox")
        save("investigations-inbox.png", page.get_by_test_id("inbox"))
        page.get_by_test_id("inbox-candidate").first.get_by_test_id("inbox-evidence-toggle").click()
        time.sleep(0.5)
        save("investigations-inbox-evidence.png", page.get_by_test_id("inbox"))

        go(f"/research/{study_id}", "notebook")
        page.get_by_test_id("logview-live").first.wait_for(timeout=60000)
        time.sleep(2)
        save("investigations-notebook.png")

        go("/settings?tab=aircraft", "aircraft-settings")
        save("settings-aircraft.png")
        go("/settings?tab=research", "research-settings")
        save("settings-research.png", page.get_by_test_id("research-settings"))

        go("/flights", "flight-route-cell")
        page.get_by_label("Find a flight").fill("balance")
        page.get_by_test_id("flight-find").get_by_role("button", name="Find").click()
        page.get_by_test_id("flight-find-summary").wait_for(timeout=60000)
        time.sleep(1)
        save("flights-find.png")
        browser.close()
    return shots


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "img"))
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    if not (ROOT / "web" / "dist" / "index.html").is_file():
        raise SystemExit("build the UI first (web/: npm run build && npm run build:browser)")
    home = Path(tempfile.mkdtemp(prefix="eis-docs-demo-"))
    port = free_port()
    demo = Demo(home, port)
    server = subprocess.Popen([str(PY), "-m", "slingology_eis.cli", "serve", "--port", str(port)], env=demo.env, cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        made = demo.build()
        shots = shoot(f"http://127.0.0.1:{port}/", Path(args.out), made["study_id"], args.headed)
        print("\n".join(shots))
    finally:
        server.terminate()
        server.wait(timeout=20)
        shutil.rmtree(home, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
