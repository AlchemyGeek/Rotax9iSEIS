"""
Build the static site (Spec 04 v0.8 §9.7; step 5): one folder for any
static host — GitHub Pages included, no custom headers — that runs the
whole app in the browser.

    python scripts/build_site.py --out DIR [--e2e]

Contents: index.html and assets (relative paths, so it works at a
sub-path), runtime.json (browser variant), pyodide/ (the pinned release,
numpy and pandas only, with MANIFEST.json), engine/ (the engine wheel,
which also carries the UI for `pip install`). --e2e builds the UI with the
end-to-end test hook (VITE_E2E=1) for spike/browser-host's scripts; a
shipped site is built without it.

Needs Node (for the UI build) and `npm ci` in web/.
"""
from __future__ import annotations

import argparse
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
