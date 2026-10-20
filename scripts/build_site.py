"""
Build the static site (Spec 04 v0.8 §9.7; step 5): one folder for any
static host — GitHub Pages included, no custom headers — that runs the
whole app in the browser.

    python scripts/build_site.py --out DIR [--e2e]

Contents: index.html and assets (relative paths, so it works at a
sub-path), runtime.json (browser variant), pyodide/ (the pinned release,
numpy and pandas only, with MANIFEST.json), engine/ (the engine wheel,
which also carries the UI for `pip install`), and sw.js (the offline
cache: web/sw.js with this release's file list; step 6). --e2e builds the UI with the
end-to-end test hook (VITE_E2E=1) for spike/browser-host's scripts; a
shipped site is built without it.

Needs Node (for the UI build) and `npm ci` in web/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_engine_wheel  # noqa: E402
import stage_pyodide  # noqa: E402


def write_service_worker(site: Path, wheel: Path) -> dict:
    """sw.js (step 6): web/sw.js with this release's manifest prepended —
    every file of the site with its SHA-256, and the release key (a hash
    of all of them) that names its cache."""
    files = {}
    for p in sorted(site.rglob("*")):
        rel = p.relative_to(site).as_posix()
        if p.is_file() and rel != "sw.js":
            files[rel] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    release = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]
    version = wheel.name.split("-")[1]
    try:
        commit = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=ROOT, capture_output=True,
                                text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = ""
    manifest = {"release": release, "version": version, "commit": commit, "files": files}
    (site / "sw.js").write_text(f"self.__EIS_MANIFEST = {json.dumps(manifest, indent=1)};\n\n"
                                + (ROOT / "web" / "sw.js").read_text())
    return manifest


def build(out: Path, e2e: bool = False) -> dict:
    web = ROOT / "web"
    env = {**os.environ, **({"VITE_E2E": "1"} if e2e else {})}
    env.pop("VITE_E2E", None) if not e2e else None
    subprocess.run(["npx", "tsc", "-b"], cwd=web, check=True, env=env)
    subprocess.run(["npx", "vite", "build"], cwd=web, check=True, env=env)
    dist = web / "dist"
    wheel = build_engine_wheel.build(dist / "engine")          # carries the UI just built
    stage_pyodide.stage(dist / "pyodide")
    (dist / "runtime.json").write_text(json.dumps(build_engine_wheel.runtime_json(wheel), indent=2) + "\n")
    write_service_worker(dist, wheel)
    out = out.resolve()
    if out != dist.resolve():
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(dist, out)
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    return {"out": str(out), "wheel": wheel.name, "wheel_bytes": wheel.stat().st_size, "site_bytes": size}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--e2e", action="store_true")
    args = ap.parse_args()
    r = build(Path(args.out), e2e=args.e2e)
    print(f"{r['out']}: {r['site_bytes'] / 1048576:.1f} MB (wheel {r['wheel']}, {r['wheel_bytes'] / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
