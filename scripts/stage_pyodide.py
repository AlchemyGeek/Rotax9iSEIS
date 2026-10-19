"""
Stage the pinned, self-hosted Pyodide for a static site (Spec 04 v0.8
§9.7, D7; step 5): the release named in PYODIDE_VERSION — its core runtime
and numpy and pandas with the packages they require, nothing else — into
one folder the worker loads from. A built site never loads from a CDN.

    python scripts/stage_pyodide.py --out DIR

The core files come from the `pyodide` npm package (web/node_modules, the
same version, checked). Package wheels come from the local cache that the
Node conformance run fills (web/node_modules/.pyodide-packages), else are
downloaded once from that release on jsDelivr; every wheel is checked
against the SHA-256 in the release's pyodide-lock.json. MANIFEST.json
lists every staged file with its SHA-256 and size, so a build is
reproducible and auditable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NPM = ROOT / "web" / "node_modules" / "pyodide"
CACHE = ROOT / "web" / "node_modules" / ".pyodide-packages"
CORE = ["pyodide.mjs", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"]
WANTED = ["numpy", "pandas"]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def closure(packages: dict, names: list[str]) -> list[str]:
    out, todo = set(), list(names)
    while todo:
        n = todo.pop()
        if n not in out:
            out.add(n)
            todo.extend(packages[n]["depends"])
    return sorted(out)


def stage(out: Path) -> dict:
    version = (ROOT / "PYODIDE_VERSION").read_text().strip()
    npm_version = json.loads((NPM / "package.json").read_text())["version"]
    if npm_version != version:
        raise SystemExit(f"web/node_modules/pyodide is {npm_version}, PYODIDE_VERSION says {version}: run `npm ci` in web/")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in CORE:
        shutil.copy2(NPM / name, out / name)
    lock = json.loads((out / "pyodide-lock.json").read_text())
    files = []
    for pkg in closure(lock["packages"], WANTED):
        info = lock["packages"][pkg]
        target = out / info["file_name"]
        cached = CACHE / info["file_name"]
        if cached.is_file() and sha256(cached) == info["sha256"]:
            shutil.copy2(cached, target)
        else:
            url = f"https://cdn.jsdelivr.net/pyodide/v{version}/full/{info['file_name']}"
            with urllib.request.urlopen(url, timeout=120) as r, open(target, "wb") as f:
                shutil.copyfileobj(r, f)
            CACHE.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, cached)
        if sha256(target) != info["sha256"]:
            raise SystemExit(f"{info['file_name']}: SHA-256 doesn't match pyodide-lock.json")
        files.append(info["file_name"])
    manifest = {"pyodide": version, "packages": closure(lock["packages"], WANTED),
                "files": [{"name": n, "sha256": sha256(out / n), "size": (out / n).stat().st_size}
                          for n in sorted(CORE + files)]}
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    m = stage(Path(args.out))
    total = sum(f["size"] for f in m["files"])
    print(f"Pyodide {m['pyodide']}: {len(m['files'])} files, {total / 1048576:.1f} MB ({', '.join(m['packages'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
