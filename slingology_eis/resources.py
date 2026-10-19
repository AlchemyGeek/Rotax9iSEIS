"""
resources.py — where the engine's runtime files live (Spec 04 v0.8 §9.7,
D7; step 5).

One lookup rule. In a developer checkout (this package beside the repo's
`pyproject.toml`) the repo-root files are the source of truth: engine
profiles in `engines/`, `insight_rules.json`, `chart_presets.json`,
`config.json`, the topic register under `docs/specs/topics/`. Anywhere else
— an installed wheel, Pyodide — the copies the wheel build put in the
package's `_data/` folder are used. Topic help (`help/topics.md`) is
ordinary package data in both.

The built web UI follows the same rule: a checkout's `web/dist`, else the
copy the wheel carries in `_web/`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

PACKAGE_DIR = Path(__file__).resolve().parent
CHECKOUT_ROOT = PACKAGE_DIR.parent
DATA_DIR = PACKAGE_DIR / "_data"
WEB_DIR = PACKAGE_DIR / "_web"

# Repo-root files the engine reads at run time (what the wheel build copies).
RUNTIME_FILES = ["config.json", "insight_rules.json", "chart_presets.json", "docs/specs/topics/register.json"]
RUNTIME_GLOBS = ["engines/*.json"]


def is_checkout(root: Path = CHECKOUT_ROOT) -> bool:
    """This package is running from a developer checkout."""
    return (root / "pyproject.toml").is_file() and (root / "slingology_eis").is_dir()


def resource(rel: str, root: Optional[Path] = None, data: Optional[Path] = None) -> Path:
    """A runtime file by its repo-relative path (e.g. "engines",
    "insight_rules.json"): the checkout's when running from one, else the
    packaged copy."""
    root = CHECKOUT_ROOT if root is None else root
    data = DATA_DIR if data is None else data
    return (root / rel) if is_checkout(root) else (data / rel)


def web_dist(root: Optional[Path] = None, web: Optional[Path] = None) -> Optional[Path]:
    """The built UI to serve: a checkout's web/dist (developers), else the
    copy in the wheel; None when neither exists."""
    root = CHECKOUT_ROOT if root is None else root
    web = WEB_DIR if web is None else web
    if is_checkout(root) and (root / "web" / "dist" / "index.html").is_file():
        return root / "web" / "dist"
    return web if (web / "index.html").is_file() else None
