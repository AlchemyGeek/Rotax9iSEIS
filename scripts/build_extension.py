"""
Build the Claude Desktop extension (Spec 16 §7) — one `.mcpb` per macOS
architecture:

    python scripts/build_extension.py --wheel DIST/slingology_eis-*.whl --out DIR [--arch arm64|x86_64]

The bundle (an MCP Bundle: a zip with manifest.json at its root, packed and
validated by the `@anthropic-ai/mcpb` CLI):

    manifest.json   server type "binary": the bundled Python runs
                    `-m slingology_eis.investigations.extension` (MCP stdio +
                    the pages on 127.0.0.1:8420, one process)
    icon.png
    python/         a standalone CPython (astral-sh/python-build-standalone,
                    pinned below, checksum-checked) with the engine wheel and
                    its `investigations` extra installed — the wheel carries
                    the built UI (setup.py), so nothing else is needed

Run it on the architecture it targets (the wheels pip picks for numpy,
scipy… are the running Python's); CI does, on one macOS runner per
architecture. The wheel is the one `scripts/build_site.py` (or
`build_engine_wheel.py` after `npm run build`) made, UI included.
Unsigned (signing is deferred, Spec 16 §7).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PBS_RELEASE = "20261110"
PBS_PYTHON = "3.12.16"
PBS_URL = "https://github.com/astral-sh/python-build-standalone/releases/download/{rel}/{name}"
MCPB_CLI = "@anthropic-ai/mcpb@2.1.2"
ARCH = {"arm64": "aarch64", "x86_64": "x86_64"}
DOCS_URL = "https://alchemygeek.github.io/Rotax9iSEIS/"
# Not needed at run time: the interpreter's own tests, IDLE, Tk, the installer.
PRUNE = ("lib/python3.12/test", "lib/python3.12/idlelib", "lib/python3.12/tkinter", "lib/python3.12/turtledemo",
         "lib/python3.12/ensurepip", "lib/tcl9.0", "lib/tk9.0", "lib/tcl8.6", "lib/tk8.6", "lib/itcl4.3.4",
         "share")


def _download(url: str, target: Path) -> None:
    # curl, not urllib: a python.org install may have no CA certificates.
    print(f"downloading {url}", file=sys.stderr)
    subprocess.run(["curl", "-fsSL", "--retry", "3", "-o", str(target), url], check=True)


def fetch_python(arch: str, cache: Path) -> Path:
    name = f"cpython-{PBS_PYTHON}+{PBS_RELEASE}-{ARCH[arch]}-apple-darwin-install_only.tar.gz"
    cache.mkdir(parents=True, exist_ok=True)
    tarball, sums = cache / name, cache / f"SHA256SUMS-{PBS_RELEASE}"
    if not sums.is_file():
        _download(PBS_URL.format(rel=PBS_RELEASE, name="SHA256SUMS"), sums)
    want = next((ln.split()[0] for ln in sums.read_text().splitlines() if ln.strip().endswith(name)), None)
    if want is None:
        raise SystemExit(f"{name} isn't in the release's SHA256SUMS")
    if not tarball.is_file() or hashlib.sha256(tarball.read_bytes()).hexdigest() != want:
        _download(PBS_URL.format(rel=PBS_RELEASE, name=name), tarball)
    got = hashlib.sha256(tarball.read_bytes()).hexdigest()
    if got != want:
        raise SystemExit(f"{name}: checksum {got} ≠ {want}")
    return tarball


def _resolve_symlinks(tree: Path) -> None:
    """Copies in place of links: a zip keeps files, not links."""
    for p in sorted(tree.rglob("*"), key=lambda q: len(q.parts), reverse=True):
        if p.is_symlink():
            real = p.resolve()
            p.unlink()
            if real.is_dir():
                shutil.copytree(real, p, symlinks=False)
            elif real.is_file():
                shutil.copy2(real, p)


def manifest(version: str) -> dict:
    from slingology_eis.investigations import mcp_tools as T
    py = "${__dirname}/python/bin/python3"
    return {
        "manifest_version": "0.3",
        "name": "slingology-eis",
        "display_name": "SlingologyEIS",
        "version": version,
        "description": "Engine health analytics for Rotax 9-series iS engines: Claude investigates your own "
                       "G3X / AXIS engine logs with the EIS engine, on your computer.",
        "long_description": "Runs SlingologyEIS on this computer: the MCP tools Claude uses to look at your flights, "
                            "measure across them and write an investigation up as a notebook, and the EIS pages at "
                            "http://127.0.0.1:8420/ while Claude Desktop is open. Your logs and workspaces stay on "
                            "this computer.",
        "author": {"name": "SlingologyEIS", "url": "https://github.com/AlchemyGeek/Rotax9iSEIS"},
        "homepage": "https://github.com/AlchemyGeek/Rotax9iSEIS",
        "documentation": f"{DOCS_URL}walkthroughs/install-extension/",
        "support": "https://github.com/AlchemyGeek/Rotax9iSEIS/issues",
        "icon": "icon.png",
        "license": "See LICENSE.md in the repository",
        "keywords": ["aviation", "engine", "rotax", "garmin", "g3x", "flight-logs"],
        "server": {
            "type": "binary",
            "entry_point": "python/bin/python3",
            "mcp_config": {
                "command": py,
                "args": ["-I", "-m", "slingology_eis.investigations.extension",
                         "--data-root", "${user_config.data_root}",
                         "--aircraft", "${user_config.aircraft}",
                         "--log-folders", "${user_config.log_folders}"],
                # Bytecode isn't shipped (+40 MB): the first start writes it
                # into the extension's folder (~9 s), later ones use it (~2 s).
                "env": {"MPLBACKEND": "Agg"},
            },
        },
        "tools": [{"name": t.name, "description": t.description.split(". ")[0].rstrip(".") + "."} for t in T.TOOLS],
        "tools_generated": False,
        "user_config": {
            "data_root": {
                "type": "directory", "title": "EIS data folder",
                "description": "Where EIS keeps its workspaces. Leave empty to use the one the EIS pages use "
                               "(set in the pages under Settings → App).",
                "required": False,
            },
            "aircraft": {
                "type": "string", "title": "Aircraft",
                "description": "The aircraft (name or id) whose workspace Claude opens. Leave empty with one "
                               "aircraft, or to use the most recently opened.",
                "required": False,
            },
            "log_folders": {
                "type": "directory", "title": "Log folders", "multiple": True,
                "description": "Folders of engine logs (G3X SD card copies, AXIS exports) to link to that "
                               "workspace. Added, never removed; the pages manage the list too.",
                "required": False,
            },
        },
        "compatibility": {"platforms": ["darwin"]},
        "privacy_policies": [],
    }


def build(wheel: Path, out: Path, arch: str, cache: Path) -> Path:
    from slingology_eis import __version__
    if arch != {"arm64": "arm64", "x86_64": "x86_64", "aarch64": "arm64"}.get(platform.machine()):
        raise SystemExit(f"build the {arch} bundle on an {arch} Mac (this is {platform.machine()})")
    tarball = fetch_python(arch, cache)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="eis-mcpb-") as tmp:
        stage = Path(tmp) / "bundle"
        stage.mkdir()
        with tarfile.open(tarball) as tf:
            tf.extractall(stage, filter="data")          # → stage/python
        py = stage / "python" / "bin" / "python3"
        subprocess.run([str(py), "-m", "pip", "install", "--no-cache-dir", "--disable-pip-version-check",
                        "--quiet", f"{wheel.resolve()}[investigations]"], check=True)
        for rel in PRUNE:
            shutil.rmtree(stage / "python" / rel, ignore_errors=True)
        for d in (stage / "python").rglob("__pycache__"):
            shutil.rmtree(d, ignore_errors=True)
        _resolve_symlinks(stage / "python")
        # The bundled engine must import and carry the UI.
        subprocess.run([str(py), "-I", "-c", "import slingology_eis.investigations.extension, scipy, matplotlib, pypdf;"
                        "from slingology_eis.resources import web_dist; assert web_dist(), 'no UI in the wheel'"],
                       check=True)
        shutil.copy2(ROOT / "web" / "public" / "favicon-512.png", stage / "icon.png")
        (stage / "manifest.json").write_text(json.dumps(manifest(__version__), indent=2, ensure_ascii=False) + "\n")
        target = out / f"slingology-eis-{__version__}-macos-{arch}.mcpb"
        npx = shutil.which("npx") or "npx"
        subprocess.run([npx, "-y", MCPB_CLI, "validate", str(stage / "manifest.json")], check=True)
        subprocess.run([npx, "-y", MCPB_CLI, "pack", str(stage), str(target)], check=True)
    return target


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--wheel", required=True, help="the engine wheel, UI included")
    ap.add_argument("--out", required=True, help="folder for the .mcpb")
    ap.add_argument("--arch", default={"aarch64": "arm64"}.get(platform.machine(), platform.machine()),
                    choices=sorted(ARCH), help="default: this Mac's")
    ap.add_argument("--cache", default=str(Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "slingology-eis"),
                    help="where the standalone Python download is kept")
    args = ap.parse_args()
    print(build(Path(args.wheel), Path(args.out), args.arch, Path(args.cache)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
