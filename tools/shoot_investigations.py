#!/usr/bin/env python3
"""Screenshots for the Investigations docs (Spec 13 §7, Spec 16 Session F).

    .venv/bin/python docs/tools/shoot_investigations.py [--out docs/img] [--headed]

Builds a throwaway data root from synthetic flights only (the test suite's
generator: a climb, cruise and a minute of full power with rpm and manifold
pressure cycling together) — no real log, tail number, airport or time — then:
an aircraft record with notes, an inbox scan, the owner's marks under two
questions (Spec 16 D16), a short notebook written through the MCP tools as
Claude would write it — taking up one of the questions — two smaller ones so
Research home shows its cards (Spec 03 v0.34), and a flight name. It starts
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


def _warm_oil(log: bytes) -> bytes:
    """A short oil-temperature peak just over the OM maximum, late in the flight and away from the
    windows the notebooks chart, so the Journal's filter has something to hide."""
    lines = log.decode().splitlines()
    for i in range(602, 615):
        cells = lines[i].split(",")
        cells[-1] = "268"
        lines[i] = ",".join(cells)
    return ("\n".join(lines) + "\n").encode()


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
            if day in (2, 5, 6, 8):
                log = _warm_oil(log)
            files = [{"content_base64": base64.b64encode(log).decode(), "filename": f"log_202601{day:02d}_120000_DEMO.csv"}]
            ids.append(self.rpc("import_files", {"files": files})["results"][0]["flight_id"])
        self.rpc("aircraft_set", {"aircraft": {"name": "Demo aircraft", "airframe": "Kit, two seats, 2024",
                                               "propeller": "Three blades, in-flight adjustable",
                                               "prop_controller": "Constant-speed controller"}, "notes": NOTES})
        self.rpc("flight_set_name", {"flight_id": ids[6], "name": "After the prop balance"})
        inbox = self.tool("inbox_list", {})
        cand = next((c["id"] for c in inbox["candidates"] if c["kind"] == "recurring"), None)
        # The owner's marks: two full-power windows under one question, one under another.
        m1 = self.rpc("flight_pin", {"flight_id": ids[0], "start_s": 110, "end_s": 190, "channels": ["rpm", "map_inhg"],
                                     "note": "rpm and MAP swing together at full power", "question": {"title": "rpm swing at full power"}})
        qid = m1["question"]["id"]
        self.rpc("flight_pin", {"flight_id": ids[2], "start_s": 110, "end_s": 190, "channels": ["rpm", "map_inhg"],
                                "note": "the same, a little less", "question": qid})
        self.rpc("flight_pin", {"flight_id": ids[7], "start_s": 200, "end_s": 300, "channels": ["oil_temp_f"],
                                "note": "oil looks warm after the climb", "question": {"title": "oil warmer in cruise?"}})
        st = self.tool("study_create", {"name": "Full-power rpm cycle", "question_id": qid,
                                        **({"inbox_candidate": cand} if cand else {})})
        sid = st["study_id"]
        # Written as guide v2 asks (Spec 16 D19): the plan under 5 first, a probe as scratch, each finding a
        # sentence and one captioned evidence cell, the calculation as support, then the structured Answer.
        self.tool("cell_append", {"study_id": sid, "kind": "markdown", "section": 5, "source":
                                  "**Plan.** Start from the two marks, then every full-power slice: is rpm cycling, how "
                                  "fast and how far, and does manifold pressure move with it?"})
        self.tool("code_run", {"study_id": sid, "role": "scratch", "source":
                               "list(eis.slices(\"full_power\", [\"rpm\", \"map_inhg\"]).columns)"})
        self.tool("cell_append", {"study_id": sid, "kind": "markdown", "source":
                                  "**1.** RPM swings 180 rpm at full power on 8 of the 10 flights and 60 rpm on the other "
                                  "two, and manifold pressure swings with it (Table 3)."})
        self.tool("code_run", {"study_id": sid, "role": "evidence", "source":
                               "s = eis.slices(\"full_power\", [\"rpm\", \"map_inhg\"])\n"
                               "t = s.groupby(\"flight_id\")[[\"rpm.swing\", \"map_inhg.swing\"]].median().reset_index()\n"
                               "t = eis.flights()[[\"flight_id\", \"date\"]].merge(t).drop(columns=\"flight_id\")\n"
                               "eis.table(t, caption=\"Full-power swing per flight, the median of its slices\")"})
        self.tool("cell_append", {"study_id": sid, "kind": "markdown", "source":
                                  "**2.** The cycle repeats every 4.4 s on every flight — the cycling test's period, "
                                  "under *show the calculation*."})
        self.tool("code_run", {"study_id": sid, "role": "support", "source":
                               "r = eis.cycling(\"full_power\", \"rpm\")\nprint(r)"})
        self.tool("cell_append", {"study_id": sid, "kind": "markdown", "source":
                                  "A period that steady, on every flight, points to a control loop hunting rather than turbulence — a hypothesis."})
        self.tool("study_finish", {"study_id": sid, "journal": True,
                                   "question_scope": "- 10 flights, 1–10 January 2026\n- Every full-power slice (the "
                                                     "*full power* preset)\n- The logs can't tell: the governor's and "
                                                     "the boost control's settings",
                                   "shows": ["RPM cycles every 4.4 s at full power on all 10 flights, manifold pressure "
                                             "in step (Table 3).",
                                             "The swing is 180 rpm on 8 flights and 60 rpm on 2 (Table 3).",
                                             "Your two marks show the same cycle (Log views 1 and 2)."],
                                   "means": "A hypothesis: the propeller governor and the boost control acting on each "
                                            "other. Confidence is moderate — the cycle is steady and in step on every "
                                            "flight, but neither controller's settings are in the logs. A flight with "
                                            "the governor's gain changed would settle it.",
                                   "actions": [{"what": "Ask the propeller shop for the governor's gain setting",
                                                "who": "propeller shop", "settles": "whether the governor is tuned to hunt",
                                                "recheck_after_flights": 5}],
                                   "tags": ["governor", "full power"],
                                   **({"inbox_candidate": cand, "resolution": "investigating"} if cand else {})})
        # Two smaller notebooks, so Research home shows cards of each kind (Spec 03 v0.34 §5.10).
        oil = self.tool("study_create", {"name": "Oil temperature in cruise"})["study_id"]
        self.tool("cell_append", {"study_id": oil, "kind": "logview", "flight": ids[7], "start_s": 200, "end_s": 300,
                                  "channels": ["oil_temp_f"], "title": "8 January — after the climb",
                                  "caption": "8 January: the warm reading is the climb"})
        self.tool("cell_append", {"study_id": oil, "kind": "code", "source":
                                  "r = eis.unusual(\"stable_cruise\", [\"oil_temp_f\"])\nprint(r.finding)"})
        self.tool("cell_append", {"study_id": oil, "kind": "markdown", "source":
                                  "No cruise slice stands out on oil temperature (the unusual test, under *show the "
                                  "calculation*)."})
        self.tool("study_finish", {"study_id": oil, "resolution": "nothing-here", "tags": ["oil", "cruise"], "summary":
                                   "Cruise oil temperature is steady flight to flight; the warm reading on 8 January is the climb, not cruise."})
        new = self.tool("study_create", {"name": "Manifold pressure at takeoff"})["study_id"]
        self.tool("cell_append", {"study_id": new, "kind": "markdown", "source":
                                  "## The question\n\nDoes manifold pressure reach the same value at every takeoff?"})
        # A few decisions in force, so the Journal (Spec 14 §6.4) shows its sections.
        self.rpc("save_filter", {"filter": {"limit_id": "oil_temp_max", "magnitude": {"mode": "absolute", "value": 4},
                                            "duration": {"max_event_s": 30},
                                            "note": "Oil probe reads a few degrees high after the descent; checked against a second probe at the annual."}})
        self.rpc("exclude_flight", {"flight_id": ids[3], "reason": "Ground run after the oil change, not a flight"})
        self.rpc("save_baseline_config", {"baseline_config": {"membership": "leave_one_out", "band_kind_by_metric": {},
                                                              "outlier_z_threshold": 2.5}})
        self.rpc("save_annotation", {"flight_id": ids[6], "ref": {"kind": "flight"},
                                     "note": "First flight after the prop balance; smoother at 5,000 rpm."})
        return {"ids": ids, "study_id": sid, "question_id": qid}


def shoot(url: str, out: Path, study_id: str, headed: bool, flight: str = "") -> list[str]:
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

        # Spec 16 D15–D16: Signal on a flight, a window's numbers, and Mark for Claude.
        page.set_viewport_size({"width": 1100, "height": 1400})   # the timeline with the read-out is tall
        go(f"/flights/{flight}?window=124-176&channels=rpm,map_inhg", "signal-toggle")   # inside the full-power minute
        time.sleep(10)   # the second channel's series arrives late on a fresh server
        page.get_by_test_id("signal-toggle").click()
        page.get_by_test_id("signal-window").wait_for(timeout=120000)
        time.sleep(2)
        save("flight-signal.png", page.locator("#timeline"))
        page.get_by_test_id("mark-open").click()
        page.get_by_test_id("mark-dialog").wait_for(timeout=30000)
        page.get_by_label("Note").fill("rpm wanders by about 100 at full power, MAP with it")
        page.get_by_label("Open question", exact=True).select_option(label="rpm swing at full power (2 marks)")
        time.sleep(0.5)
        save("mark-for-claude.png", page.get_by_test_id("mark-for-claude"))
        page.set_viewport_size({"width": 1100, "height": 820})

        # Spec 03 v0.34 §5.10: Research home — the notebooks as cards, the inbox as a digest.
        go("/research", "notebook-card")
        page.get_by_test_id("question").first.wait_for(timeout=60000)
        dismiss = page.get_by_test_id("move-dismiss")
        if dismiss.count():
            dismiss.click()
        time.sleep(0.5)
        save("investigations-home.png")
        q = page.get_by_test_id("question").filter(has_text="rpm swing at full power").first
        q.get_by_test_id("inbox-line").first.click()               # a digest line expands in place
        q.get_by_test_id("pin").first.wait_for(timeout=30000)
        time.sleep(0.5)
        save("investigations-inbox.png", page.get_by_test_id("inbox"))
        q.get_by_test_id("inbox-line").first.click()
        c = page.get_by_test_id("inbox-candidate").first
        c.get_by_test_id("inbox-line").first.click()
        c.get_by_test_id("inbox-evidence-toggle").click()
        time.sleep(0.5)
        save("investigations-inbox-evidence.png", page.get_by_test_id("inbox"))

        go(f"/research/{study_id}", "notebook")
        page.get_by_test_id("logview-live").first.wait_for(timeout=60000)
        time.sleep(2)
        save("investigations-notebook.png")
        # D19: the Findings — a sentence, its numbered and captioned evidence, the calculation folded.
        page.get_by_text("RPM swings 180 rpm").first.evaluate("e => e.scrollIntoView({block: 'start'})")
        page.evaluate("window.scrollBy(0, -80)")
        time.sleep(1)
        save("investigations-notebook-findings.png")

        go("/settings?tab=aircraft", "aircraft-settings")
        save("settings-aircraft.png")
        go("/settings?tab=research", "research-settings")
        save("settings-research.png", page.get_by_test_id("research-settings"))

        # Spec 14 §6.4 v0.20: the Journal, one line per decision; and a filter's card under Manage limit filters.
        go("/journal", "journal-section-filters")
        time.sleep(1)
        page.get_by_test_id("journal-section-findings").get_by_test_id("journal-line").first.click()
        time.sleep(0.5)
        save("journal.png")
        go("/journal?filters=1", "filter-card")
        time.sleep(2)
        save("journal-filter-card.png", page.get_by_test_id("filter-card").first)

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
        shots = shoot(f"http://127.0.0.1:{port}/", Path(args.out), made["study_id"], args.headed, made["ids"][0])
        print("\n".join(shots))
    finally:
        server.terminate()
        server.wait(timeout=20)
        shutil.rmtree(home, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
