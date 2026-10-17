"""
Spec 02 v0.10 §5.8.1 — where the data root lives, and moving it.

The data root is one folder holding `registry.json`, the app-level
`settings.json` (§6.6) and `workspaces/`. They always move together: the
registry names workspaces by id and finds each at `workspaces/<id>/`.
Nothing else in the folder belongs to it — in a developer checkout the
root is `data/`, which also holds the logs symlink and legacy CLI output,
and none of that moves.

Resolution, first match wins, in every context:

1. `SLINGOLOGY_EIS_HOME` — fixed by the environment (Docker, scripts).
2. `location.json` in the per-user configuration folder — chosen by the
   pilot. Outside the data root (the root can't record where it is) and
   outside ~/SlingologyEIS (whose existence is a step in the defaults).
3. The §5.8 defaults: ~/SlingologyEIS if it exists, else a git
   checkout's data/, else ~/SlingologyEIS.

A chosen location that can't be reached is reported as missing, never
replaced by the defaults.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

ENV_VAR = "SLINGOLOGY_EIS_HOME"

# What a data root is made of (§5.8.1). Copied, checked and counted as a
# unit; anything else in the folder is not ours.
ROOT_ITEMS = ("registry.json", "settings.json", "workspaces")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGED_HOME = Path.home() / "SlingologyEIS"

# Finder litter that doesn't make a folder "not empty".
_IGNORED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}


class DataLocationMissing(Exception):
    """The chosen data root can't be reached (§5.8.1)."""

    def __init__(self, path: Path):
        super().__init__(f"The data location {path} can't be reached. Reconnect the drive, "
                         f"or choose another location.")
        self.path = path


class DataLocationError(Exception):
    """A change of location that is refused or failed; `code` says which."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ── Where things are ─────────────────────────────────────────────────────────

def config_dir() -> Path:
    """The per-user configuration folder that holds location.json."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SlingologyEIS"
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Roaming") / "SlingologyEIS"
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / "slingology-eis"


def location_file() -> Path:
    return config_dir() / "location.json"


def _is_git_checkout(start: Path) -> bool:
    cur = start
    for _ in range(6):
        if (cur / ".git").exists():
            return True
        if cur.parent == cur:
            return False
        cur = cur.parent
    return False


def default_root() -> Path:
    """The §5.8 defaults, ignoring the environment and the location file."""
    if _PACKAGED_HOME.is_dir():
        return _PACKAGED_HOME
    if _is_git_checkout(_REPO_ROOT):
        return _REPO_ROOT / "data"
    return _PACKAGED_HOME


def _read_location_file() -> Optional[Path]:
    f = location_file()
    if not f.is_file():
        return None
    try:
        raw = json.loads(f.read_text())
        return Path(raw["data_root"]).expanduser()
    except (OSError, ValueError, KeyError, TypeError):
        return None   # unreadable pointer: as if none had been chosen


@dataclass
class Resolved:
    root: Path
    source: str            # "environment" | "chosen" | "default"
    missing: bool = False

    def to_dict(self) -> dict:
        return {"path": str(self.root), "source": self.source, "missing": self.missing}


def resolve() -> Resolved:
    env = os.environ.get(ENV_VAR)
    if env:
        return Resolved(Path(env).expanduser(), "environment")
    chosen = _read_location_file()
    if chosen is not None:
        reachable = chosen.is_dir() and os.access(chosen, os.R_OK | os.W_OK)
        return Resolved(chosen, "chosen", missing=not reachable)
    return Resolved(default_root(), "default")


def data_root() -> Path:
    """The data root in use; raises DataLocationMissing for an unreachable choice."""
    r = resolve()
    if r.missing:
        raise DataLocationMissing(r.root)
    return r.root


# ── Looking at a folder ──────────────────────────────────────────────────────

def _entries(folder: Path) -> list[Path]:
    return [p for p in folder.iterdir() if p.name not in _IGNORED_NAMES]


def _root_files(root: Path) -> list[Path]:
    """Every file of the data root's items, relative to the root."""
    out = []
    for name in ROOT_ITEMS:
        item = root / name
        if item.is_file():
            out.append(Path(name))
        elif item.is_dir():
            out.extend(p.relative_to(root) for p in sorted(item.rglob("*")) if p.is_file())
    return out


def root_size(root: Path) -> int:
    return sum((root / rel).stat().st_size for rel in _root_files(root))


def workspace_count(root: Path) -> int:
    f = root / "registry.json"
    if not f.is_file():
        return 0
    return len(json.loads(f.read_text()).get("workspaces", []))


def _same_or_within(a: Path, b: Path) -> bool:
    """a is b, or inside b."""
    return a == b or b in a.parents


def _nearest_existing(p: Path) -> Path:
    while not p.exists() and p.parent != p:
        p = p.parent
    return p


def assess(target: Path, current: Optional[Resolved] = None) -> dict:
    """
    What choosing `target` would do (§5.8.1 table), without doing it:
    {action: "move" | "use_existing" | "start_fresh" | "refused", path,
     workspace_count, bytes, reason, code}. "start_fresh" is an empty
    target while the current location is missing — there is nothing to
    move, so the folder becomes a new, empty data root.
    """
    current = current or resolve()
    if current.source == "environment":
        return _refused(target, "LOCATION_FIXED",
                        f"The data location is set by the environment ({ENV_VAR}) and can't be changed here.")
    if not str(target).strip():
        return _refused(target, "BAD_PATH", "Enter a folder path.")
    target = target.expanduser()
    if not target.is_absolute():
        return _refused(target, "BAD_PATH", "Enter a full path, starting from the top of the disk.")
    target = Path(os.path.realpath(target))
    cur = Path(os.path.realpath(current.root))

    if target == cur:
        return _refused(target, "SAME_LOCATION", "That's where your data already is.")
    if target.exists() and not target.is_dir():
        return _refused(target, "NOT_A_FOLDER", "That path is a file, not a folder.")
    if (target / "registry.json").is_file():
        try:
            n = workspace_count(target)
        except (OSError, ValueError):
            return _refused(target, "UNREADABLE", "That folder holds a registry.json that can't be read.")
        return {"action": "use_existing", "path": str(target), "workspace_count": n,
                "bytes": None, "reason": None, "code": None}
    if not current.missing:
        if _same_or_within(target, cur):
            return _refused(target, "INSIDE_CURRENT", "That folder is inside your current data location.")
        if _same_or_within(cur, target):
            return _refused(target, "CONTAINS_CURRENT", "Your current data location is inside that folder.")
    if target.exists() and _entries(target):
        return _refused(target, "NOT_EMPTY",
                        "That folder isn't empty and doesn't hold SlingologyEIS data. "
                        "Choose a new, empty folder — for example one inside it.")
    if not os.access(_nearest_existing(target), os.W_OK):
        return _refused(target, "NOT_WRITABLE", "That folder can't be written to.")
    if current.missing:
        return {"action": "start_fresh", "path": str(target), "workspace_count": 0,
                "bytes": 0, "reason": None, "code": None}
    return {"action": "move", "path": str(target), "workspace_count": workspace_count(cur),
            "bytes": root_size(cur), "reason": None, "code": None}


def _refused(target: Path, code: str, reason: str) -> dict:
    return {"action": "refused", "path": str(target), "workspace_count": None, "bytes": None,
            "reason": reason, "code": code}


# ── Changing it ──────────────────────────────────────────────────────────────

def _write_location(root: Path) -> None:
    """Point at `root`; pointing at the default removes the file instead."""
    f = location_file()
    if root == Path(os.path.realpath(default_root())):
        f.unlink(missing_ok=True)
        return
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "data_root": str(root),
                               "set_at": datetime.now(timezone.utc).isoformat()}, indent=2))
    tmp.replace(f)


def _check_copy(src: Path, dst: Path, files: list[Path]) -> None:
    from . import workspace as ws   # workspace imports this module
    for rel in files:
        a, b = src / rel, dst / rel
        if not b.is_file() or b.stat().st_size != a.stat().st_size:
            raise DataLocationError("COPY_FAILED", f"{rel} didn't arrive intact.")
    if (dst / "registry.json").is_file():
        registry = ws.load_registry(dst / "registry.json")
        for entry in registry.workspaces:
            if (src / "workspaces" / entry.id).is_dir():
                ws.load_manifest(dst / "workspaces" / entry.id)


def change(target: Path, on_progress: Optional[Callable[[dict], None]] = None) -> dict:
    """
    Carry out what assess(target) said. Move: copy the root's items,
    check them, then write the location file; the old copy is left where
    it is. Use existing / start fresh: just write the location file. A
    failed move removes what it copied and changes nothing else. Returns
    {action, path, previous_path}.
    """
    current = resolve()
    plan = assess(target, current)
    if plan["action"] == "refused":
        raise DataLocationError(plan["code"], plan["reason"])
    dst = Path(plan["path"])
    src = Path(os.path.realpath(current.root))

    if plan["action"] == "move":
        files = _root_files(src)
        existed = dst.exists()
        try:
            dst.mkdir(parents=True, exist_ok=True)
            total = len(files)
            for i, rel in enumerate(files, 1):
                (dst / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src / rel, dst / rel)
                if on_progress and (i == total or i % 25 == 0):
                    on_progress({"phase": "copying", "done": i, "total": total})
            if on_progress:
                on_progress({"phase": "checking", "done": total, "total": total})
            _check_copy(src, dst, files)
            _rebase_paths(src, dst)
        except Exception as e:
            _undo_copy(dst, existed)
            if isinstance(e, DataLocationError):
                raise
            raise DataLocationError("COPY_FAILED", f"Copying your data failed: {e}") from e
    elif plan["action"] == "start_fresh":
        dst.mkdir(parents=True, exist_ok=True)

    _write_location(dst)
    return {"action": plan["action"], "path": str(dst),
            "previous_path": str(src) if plan["action"] == "move" else None}


def _rebase_paths(src: Path, dst: Path) -> None:
    """A workspace can hold its own logs (an imported export's logs/,
    Spec 02 v0.14): its manifest and sources record them by absolute path
    under the data root. In the copy, those paths point into the new root,
    so the logs move with the workspace. Paths outside the root (the
    pilot's own log folders) are left alone."""
    old, new = str(src), str(dst)

    def rebased(p: str) -> str:
        return new + p[len(old):] if p == old or p.startswith(old + "/") else p

    for manifest in (dst / "workspaces").glob("*/manifest.json"):
        m = json.loads(manifest.read_text())
        changed = False
        for lf in m.get("log_folders", []):
            if rebased(lf.get("path", "")) != lf.get("path"):
                lf["path"] = rebased(lf["path"])
                changed = True
        if changed:
            manifest.write_text(json.dumps(m, indent=2))
    for sources in (dst / "workspaces").glob("*/flights/*/sources.json"):
        d = json.loads(sources.read_text())
        changed = False
        for imp in d.get("imports", []):
            if rebased(imp.get("log_folder_path", "")) != imp.get("log_folder_path"):
                imp["log_folder_path"] = rebased(imp["log_folder_path"])
                changed = True
        if changed:
            sources.write_text(json.dumps(d, indent=2))


def _undo_copy(dst: Path, existed: bool) -> None:
    """Remove what a failed move wrote; the target was empty before."""
    if not existed:
        shutil.rmtree(dst, ignore_errors=True)
        return
    for name in ROOT_ITEMS:
        p = dst / name
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()
