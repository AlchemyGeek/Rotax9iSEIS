"""
Build the engine wheel the browser host loads into Pyodide (Spec 04 v0.7
§9.7; step 4 — CI packaging is step 5), and the static site's
runtime.json.

    python scripts/build_engine_wheel.py --out web/public/engine
    python scripts/build_engine_wheel.py --out web/dist/engine --runtime web/dist/runtime.json

The wheel holds the `slingology_eis` package and, at its top level, the
repo-root files the engine reads at run time (engine profiles, rules,
chart presets, config, the topic register). Installed into Pyodide's
site-packages they sit beside the package exactly as they sit beside it in
a checkout, so the existing repo-root lookups work unchanged. Proper
package data is step 5's packaging work.

Pure stdlib; no network.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Repo-root files the engine reads at run time (see the module docstring).
RUNTIME_FILES = ["config.json", "insight_rules.json", "chart_presets.json", "docs/specs/topics/register.json"]
RUNTIME_DIRS = ["engines"]


def version() -> str:
    text = (ROOT / "slingology_eis" / "__init__.py").read_text()
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def files() -> list[tuple[str, Path]]:
    out = []
    for p in sorted((ROOT / "slingology_eis").rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            out.append((p.relative_to(ROOT).as_posix(), p))
    for rel in RUNTIME_FILES:
        out.append((rel, ROOT / rel))
    for d in RUNTIME_DIRS:
        for p in sorted((ROOT / d).glob("*.json")):
            out.append((p.relative_to(ROOT).as_posix(), p))
    return out


def _record_line(name: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{name},sha256={digest},{len(data)}"


def build(out_dir: Path) -> Path:
    ver = version()
    dist_info = f"slingology_eis-{ver}.dist-info"
    wheel = out_dir / f"slingology_eis-{ver}-py3-none-any.whl"
    out_dir.mkdir(parents=True, exist_ok=True)
    record = []
    with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as z:
        for name, path in files():
            data = path.read_bytes()
            z.writestr(name, data)
            record.append(_record_line(name, data))
        meta = {
            f"{dist_info}/METADATA": f"Metadata-Version: 2.1\nName: slingology-eis\nVersion: {ver}\n"
                                     "Requires-Dist: pandas>=2.0\nRequires-Dist: numpy>=1.24\n",
            f"{dist_info}/WHEEL": "Wheel-Version: 1.0\nGenerator: scripts/build_engine_wheel.py\n"
                                  "Root-Is-Purelib: true\nTag: py3-none-any\n",
            f"{dist_info}/top_level.txt": "slingology_eis\n",
        }
        for name, text in meta.items():
            z.writestr(name, text)
            record.append(_record_line(name, text.encode()))
        record.append(f"{dist_info}/RECORD,,")
        z.writestr(f"{dist_info}/RECORD", "\n".join(record) + "\n")
    return wheel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="folder for the wheel")
    ap.add_argument("--runtime", help="also write the browser runtime.json here")
    args = ap.parse_args()
    wheel = build(Path(args.out))
    if args.runtime:
        runtime = {"host": "browser", "pyodide": (ROOT / "PYODIDE_VERSION").read_text().strip(),
                   "engine_wheel": f"engine/{wheel.name}"}
        Path(args.runtime).write_text(json.dumps(runtime, indent=2) + "\n")
    print(wheel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
