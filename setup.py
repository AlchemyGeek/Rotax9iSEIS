"""
Build hook (Spec 04 v0.8 §9.7, D7; step 5). Everything else is in
pyproject.toml.

When a wheel is built, the engine's runtime files — engine profiles,
insight_rules.json, chart_presets.json, config.json, the topic register —
are copied from the repo root into the package as `slingology_eis/_data/`,
and the built web UI (`web/dist`, if present) as `slingology_eis/_web/`.
The repo root stays the source of truth; a developer checkout reads it
directly (slingology_eis/resources.py). Static-site extras in web/dist
(the engine wheel, the Pyodide files, runtime.json) aren't carried.
"""
import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent
RUNTIME_FILES = ["config.json", "insight_rules.json", "chart_presets.json", "docs/specs/topics/register.json"]
RUNTIME_GLOBS = ["engines/*.json"]
SITE_ONLY = {"engine", "pyodide", "runtime.json"}


class BuildWithRuntimeData(build_py):
    def run(self):
        super().run()
        pkg = Path(self.build_lib) / "slingology_eis"
        data = pkg / "_data"
        for rel in RUNTIME_FILES:
            (data / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, data / rel)
        for pattern in RUNTIME_GLOBS:
            for p in sorted(ROOT.glob(pattern)):
                target = data / p.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target)
        dist = ROOT / "web" / "dist"
        web = pkg / "_web"
        if (dist / "index.html").is_file():
            if web.exists():
                shutil.rmtree(web)
            shutil.copytree(dist, web, ignore=lambda d, names: [n for n in names if Path(d) == dist and n in SITE_ONLY])


setup(cmdclass={"build_py": BuildWithRuntimeData})
