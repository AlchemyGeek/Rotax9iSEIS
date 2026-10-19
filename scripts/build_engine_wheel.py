"""
Build the engine wheel (Spec 04 v0.8 §9.7, D7) — the one wheel both hosts
use: `pip install` gives the server user the engine and the built UI;
the browser host installs the same file into Pyodide.

    python scripts/build_engine_wheel.py --out DIR [--runtime PATH]

A standard setuptools build (`pip wheel .`): the runtime files and, when
web/dist has been built, the UI are added as package data by setup.py.
--runtime also writes a browser runtime.json naming the wheel (the static
site's; scripts/build_site.py uses it).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, "-m", "pip", "wheel", str(ROOT), "--no-deps", "--no-build-isolation",
                        "--quiet", "--wheel-dir", tmp], check=True)
        built = next(Path(tmp).glob("slingology_eis-*.whl"))
        for old in out_dir.glob("slingology_eis-*.whl"):
            old.unlink()
        target = out_dir / built.name
        shutil.copy2(built, target)
    shutil.rmtree(ROOT / "build", ignore_errors=True)   # setuptools' scratch folder
    return target


def runtime_json(wheel: Path, pyodide_url: str = "pyodide/") -> dict:
    return {"host": "browser", "pyodide": (ROOT / "PYODIDE_VERSION").read_text().strip(),
            "pyodide_url": pyodide_url, "engine_wheel": f"engine/{wheel.name}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="folder for the wheel")
    ap.add_argument("--runtime", help="also write the browser runtime.json here")
    args = ap.parse_args()
    wheel = build(Path(args.out))
    if args.runtime:
        Path(args.runtime).write_text(json.dumps(runtime_json(wheel), indent=2) + "\n")
    print(wheel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
