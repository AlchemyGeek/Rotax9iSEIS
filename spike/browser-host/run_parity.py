"""
Browser-host parity, memory and timings (Spec 04 v0.7 §10 step 4, §7).

    .venv/bin/python spike/browser-host/run_parity.py [--logs DIR] [--limit N]

1. Server mode: the logs scanned by the host in-process (disk source) and
   exported without logs.
2. Browser mode: web/dist (built with `npm run build:browser`) served as a
   static folder, opened in the installed Chrome (Playwright, headless,
   fresh profile). Cold and warm start to ready are timed; a workspace is
   created, the folder registered through <input webkitdirectory> (the
   Safari path; Chrome's folder picker can't be driven), Sync run while
   the worker's heap is sampled, a rule what-if timed, then exported.
3. The two exports' documents are compared, timestamps and the folder's
   identity aside. Results go to spike/browser-host/results/.

Only the CSVs are copied to a temporary folder; nothing is written to the
repo's data/.
"""
from __future__ import annotations

import argparse
import base64
import functools
import http.server
import json
import os
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

TS = {"at", "exported_at", "imported_at", "created_at", "updated_at", "last_scanned_at", "last_opened_at",
      "excluded_at", "set_at", "made_at", "detected_at"}
UUID = __import__("re").compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def normalise(obj, names: dict[str, str]):
    if isinstance(obj, dict):
        # Random ids (shift-history entries) and timestamps vary run to run.
        return {k: normalise(v, names) for k, v in obj.items()
                if k not in TS and k not in ("folder_id", "storage_backend")
                and not (k == "id" and isinstance(v, str) and UUID.match(v))}
    if isinstance(obj, list):
        return [normalise(v, names) for v in obj]
    if isinstance(obj, str):
        for old, new in names.items():
            obj = obj.replace(old, new)
    return obj


def export_documents(zip_path: Path) -> dict:
    from slingology_eis import workspace_export as wx
    c = wx.read_export(zip_path)
    return {"(workspace)": c.workspace, **c.documents}


def server_side(folder: Path, out: Path) -> tuple[dict, str, float]:
    os.environ["SLINGOLOGY_EIS_HOME"] = str(out / "server-home")
    from slingology_eis import host
    from slingology_eis.log_sources import DISK
    from slingology_eis import workspace_export as wx
    ctx = host.new_context(log_sources=DISK, emit_progress=lambda s, u: None, deliver_file=lambda p, n: str(p))
    ws_id = host.dispatch("create_workspace", {"name": "Parity", "engine_model": "916iS"}, ctx)["id"]
    host.dispatch("add_log_folder", {"path": str(folder)}, ctx)
    t0 = time.time()
    host.dispatch("scan_workspace", {}, ctx)
    scan_s = time.time() - t0
    res = wx.export_workspace(ctx["workspace_dir"], out / "server-export", include_logs=False)
    docs = export_documents(res.path)
    rows = host.dispatch("list_flights_with_status", {}, ctx)["rows"]
    docs["(analyses)"] = {r["flight_id"]: json.loads(json.dumps(host.dispatch("get_flight", {"flight_id": r["flight_id"]}, ctx)["flight_analysis"], default=str))
                          for r in rows if r["flight_id"]}
    return docs, ws_id, scan_s


def serve(directory: Path):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


READY = """async () => {
  const { client } = await window.__eis.getRuntime();
  await client.getCapabilities();
  return client.status;
}"""

RUN = """async ({ samplesEveryMs }) => {
  const { client } = await window.__eis.getRuntime();
  const out = {};
  out.heap_ready = await client.engineMemory();
  const ws = await client.createWorkspace('Parity', '916iS');
  out.workspace_id = ws.id;
  const input = document.getElementById('parity-folder');
  out.files_given = input.files.length;
  const manifest = await client.addFolderFiles([...input.files]);
  out.folder = manifest.log_folders[0];
  const samples = [];
  let scanning = true;
  const sampler = (async () => { while (scanning) { samples.push(await client.engineMemory()); await new Promise(r => setTimeout(r, samplesEveryMs)); } })();
  const t0 = performance.now();
  const scan = await client.scanWorkspace();
  out.scan_ms = performance.now() - t0;
  scanning = false; await sampler;
  out.new_flights = scan.new_flight_ids.length;
  out.auto_excluded = scan.auto_excluded.length;
  out.unreadable = scan.unreadable.length;
  out.heap_after_scan = await client.engineMemory();
  out.heap_samples = samples;
  // A rule what-if round trip (Spec 14 Q4 / Spec 04 Q8): the editor's preview.
  const rules = (await client.getWorkspaceRules()).rules;
  const candidate = JSON.parse(JSON.stringify(rules));
  candidate.rules.limit_exceedances.triggers[0].severity = 'warning';
  const tw = performance.now();
  await client.whatIfRules({ rules: candidate });
  out.what_if_ms = performance.now() - tw;
  const tw2 = performance.now();
  await client.whatIfRules({ rules: candidate });
  out.what_if_again_ms = performance.now() - tw2;
  const te = performance.now();
  const ex = await client.exportWorkspace({ include_logs: false, anonymise: false });
  out.export_ms = performance.now() - te;
  const blob = await (await fetch(client.downloadUrl(ex.download_url))).arrayBuffer();
  let s = ''; const b = new Uint8Array(blob);
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
  out.export_b64 = btoa(s);
  out.heap_end = await client.engineMemory();
  out.heap_trace = client.heapTrace;
  out.analyses = {};
  for (const row of (await client.listFlightsWithStatus()).rows) {
    if (row.flight_id) out.analyses[row.flight_id] = (await client.getFlight(row.flight_id)).flight_analysis;
  }
  return out;
}"""


def browser_side(folder: Path, out: Path) -> dict:
    from playwright.sync_api import sync_playwright
    dist = ROOT / "web" / "dist"
    assert (dist / "runtime.json").is_file(), "build first: (cd web && npm run build:browser)"
    httpd = serve(dist)
    url = f"http://localhost:{httpd.server_address[1]}/"
    profile = tempfile.mkdtemp(prefix="eis-browser-host-")
    result: dict = {}
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(profile, channel="chrome", headless=True)
            page = ctx.pages[0]
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            t0 = time.time(); page.goto(url); page.evaluate(READY); result["cold_ready_s"] = time.time() - t0
            t0 = time.time(); page.reload(); page.evaluate(READY); result["warm_ready_s"] = time.time() - t0
            page.evaluate("""() => { const i = document.createElement('input'); i.type = 'file'; i.id = 'parity-folder';
                                     i.webkitdirectory = true; i.multiple = true; i.style.display = 'none'; document.body.append(i); }""")
            page.set_input_files("#parity-folder", str(folder))
            run = page.evaluate(RUN, {"samplesEveryMs": 1000})
            zip_bytes = base64.b64decode(run.pop("export_b64"))
            (out / "browser-export.zip").write_bytes(zip_bytes)
            result.update(run)
            result["browser_version"] = ctx.browser.version if ctx.browser else None
            result["page_errors"] = errors
            ctx.close()
    finally:
        httpd.shutdown()
        shutil.rmtree(profile, ignore_errors=True)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default=str(ROOT / "data" / "logs"))
    ap.add_argument("--limit", type=int, default=0, help="use only the first N logs (0: all)")
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="eis-parity-"))
    folder = work / "logs"
    folder.mkdir()
    csvs = sorted(p for p in Path(args.logs).resolve().iterdir() if p.suffix.lower() == ".csv")
    if args.limit:
        csvs = csvs[: args.limit]
    for p in csvs:
        shutil.copy(p, folder / p.name)
    try:
        server_docs, server_ws, server_scan_s = server_side(folder, work)
        b = browser_side(folder, work)
        browser_docs = export_documents(work / "browser-export.zip")
        browser_docs["(analyses)"] = b.pop("analyses")
        names_s = {server_ws: "WS", str(folder): "FOLDER"}
        names_b = {b["workspace_id"]: "WS", b["folder"]["path"]: "FOLDER"}
        ns, nb = normalise(server_docs, names_s), normalise(browser_docs, names_b)
        differing = sorted(k for k in set(ns) | set(nb) if ns.get(k) != nb.get(k))
        heap = [b["heap_ready"], *b["heap_samples"], b["heap_after_scan"]]
        trace = b["heap_trace"]
        first = trace[0][1] if trace else b["heap_ready"]
        summary = {
            "at": datetime.now(timezone.utc).isoformat(), "browser": b["browser_version"], "logs": len(csvs),
            "documents_compared": len(ns) - 1, "flight_analyses_compared": len(ns.get("(analyses)", {})),
            "flight_analyses_identical": sum(1 for k, v in ns.get("(analyses)", {}).items() if nb.get("(analyses)", {}).get(k) == v),
            "documents_identical": len(ns) - len(differing), "differing": differing,
            "new_flights": b["new_flights"], "auto_excluded": b["auto_excluded"], "unreadable": b["unreadable"],
            "cold_ready_s": round(b["cold_ready_s"], 2), "warm_ready_s": round(b["warm_ready_s"], 2),
            "browser_scan_s": round(b["scan_ms"] / 1000, 1), "server_scan_s": round(server_scan_s, 1),
            "browser_per_log_ms": round(b["scan_ms"] / len(csvs)),
            "browser_per_flight_ms": round(b["scan_ms"] / max(1, b["new_flights"])),
            "what_if_ms": round(b["what_if_ms"]), "what_if_again_ms": round(b["what_if_again_ms"]),
            "export_ms": round(b["export_ms"]),
            "heap_mb": {"ready": round(b["heap_ready"] / 2**20), "first_sample": round(first / 2**20),
                        "peak": round(max(heap) / 2**20), "after_scan": round(b["heap_after_scan"] / 2**20),
                        "end": round(b["heap_end"] / 2**20)},
            "heap_mb_after_first_flight": round(first / 2**20),
            "heap_growth_over_batch_pct": round(100 * (max(heap) - first) / first, 1) if first else None,
            "heap_trace_mb": [[n, round(h / 2**20)] for n, h in trace],
            "page_errors": b["page_errors"],
        }
        (HERE / "results").mkdir(exist_ok=True)
        path = HERE / "results" / f"parity-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        path.write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2))
        if differing:
            if "(analyses)" in differing:
                a_s, a_b = ns.get("(analyses)", {}), nb.get("(analyses)", {})
                for fid in sorted(set(a_s) | set(a_b)):
                    if a_s.get(fid) != a_b.get(fid):
                        x, y = a_s.get(fid) or {}, a_b.get(fid) or {}
                        keys = sorted(k for k in set(x) | set(y) if x.get(k) != y.get(k))
                        print("ANALYSIS DIFF", fid, keys)
                        for k in keys[:3]:
                            print("   ", k, json.dumps(x.get(k))[:200], "|", json.dumps(y.get(k))[:200])
                        break
            for k in [d for d in differing if d != "(analyses)"][:5]:
                print("DIFF", k, json.dumps(ns.get(k))[:300], "\n     ", json.dumps(nb.get(k))[:300])
        return 0 if not differing else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
