"""
exclusions.py — log admission and flight exclusions
(docs/specs/02-results-bundle-and-workspace.md §5.11, §6.8).

Replaces silently dropping ground sessions and other unwanted flights at
load time with an explicit, visible record: every exclusion — automatic
(ground session, short flight, corrupt log) or user-chosen — is written
to exclusions.json, one file per workspace, and can be overridden.

This module is Tier 1 of Spec 02 §5.11 — admission: whether a log in a
workspace's folders becomes a flight_id at all. An excluded log never
does (no flights/<id>, no analysis); it is listed only in the Flights
tab's Skipped panel. Tier 2 — whether an already-analyzed flight feeds
baselines — is a separate mechanism, FleetSelection.excluded in
fleet/selection.json (workspace.py), keyed by flight_id, not filename.

Usage
-----
    from slingology_eis.exclusions import load_exclusions, is_excluded, add_auto_exclusion

    exclusions = load_exclusions(workspace_dir)
    if not is_excluded(filename, exclusions):
        ...
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from .phases import AIRBORNE_PHASES, phase_summary

_EXCLUSIONS_FILENAME = "exclusions.json"
_SCHEMA_VERSION = 1

# Every category exclusion_summary() reports, even at zero — callers can
# index the result without a .get(..., 0) guard.
_KNOWN_CATEGORIES = ("ground_session", "short_flight", "corrupt_log", "user_defined")


def _exclusions_path(workspace_dir: Path) -> Path:
    return Path(workspace_dir) / _EXCLUSIONS_FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_entry(exclusions: dict, filename: str) -> Optional[dict]:
    for entry in exclusions.get("entries", []):
        if entry["filename"] == filename:
            return entry
    return None


def load_exclusions(workspace_dir: Path) -> dict:
    """Load exclusions.json; return an empty structure if it doesn't exist."""
    path = _exclusions_path(workspace_dir)
    if not path.exists():
        return {"version": _SCHEMA_VERSION, "entries": []}
    return json.loads(path.read_text())


def save_exclusions(workspace_dir: Path, exclusions: dict) -> None:
    """Write exclusions.json atomically."""
    path = _exclusions_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(exclusions, indent=2))
    tmp.replace(path)


def is_excluded(filename: str, exclusions: dict) -> bool:
    """
    Return True if this filename should be excluded from analysis.
    Respects user_override: an overridden entry returns False.
    """
    entry = _find_entry(exclusions, filename)
    if entry is None:
        return False
    return not entry.get("user_override", False)


def add_auto_exclusion(workspace_dir: Path, filename: str, category: str, reason: str) -> None:
    """
    Write an auto-exclusion entry if one doesn't already exist for this
    filename. Idempotent — re-running detection on the same file doesn't
    create duplicate entries (and doesn't clobber a user's override of an
    earlier auto-exclusion for the same file).
    """
    exclusions = load_exclusions(workspace_dir)
    if _find_entry(exclusions, filename) is not None:
        return
    exclusions.setdefault("entries", []).append({
        "filename": filename,
        "source": "auto",
        "reason": reason,
        "category": category,
        "excluded_at": _now_iso(),
        "user_override": False,
    })
    save_exclusions(workspace_dir, exclusions)


def add_user_exclusion(workspace_dir: Path, filename: str, reason: str) -> None:
    """
    Add a user-defined exclusion entry. If an entry (auto or user) already
    exists for this filename, it's replaced with a fresh user_defined one
    — an explicit user exclusion always wins over a prior auto-exclusion
    for the same file.
    """
    exclusions = load_exclusions(workspace_dir)
    entries = exclusions.setdefault("entries", [])
    existing = _find_entry(exclusions, filename)
    new_entry = {
        "filename": filename,
        "source": "user",
        "reason": reason,
        "category": "user_defined",
        "excluded_at": _now_iso(),
        "user_override": False,
    }
    if existing is not None:
        entries[entries.index(existing)] = new_entry
    else:
        entries.append(new_entry)
    save_exclusions(workspace_dir, exclusions)


def set_user_override(
    workspace_dir: Path, filename: str, override: bool, override_reason: str = "",
) -> None:
    """
    Set or clear the user_override flag on an existing entry. This is the
    only way to bring a flight back into baselines — the entry itself is
    never deleted, so the auto-rule (or the user's own past exclusion)
    that created it stays on record.
    """
    exclusions = load_exclusions(workspace_dir)
    entry = _find_entry(exclusions, filename)
    if entry is None:
        raise ValueError(f"no exclusion entry for {filename!r} to override")
    entry["user_override"] = override
    if override and override_reason:
        entry["override_reason"] = override_reason
    elif not override:
        entry.pop("override_reason", None)
    save_exclusions(workspace_dir, exclusions)


def exclusion_summary(exclusions: dict) -> dict:
    """
    Return counts by category and override status, for the Flights tab
    header line and the CLI output, e.g. {"ground_session": 14,
    "short_flight": 3, "corrupt_log": 0, "user_defined": 2, "overridden": 1}.

    Category counts are of every entry ever recorded in that category,
    regardless of override status — "overridden" is a separate, additive
    tally of how many of those entries are currently back in baselines.
    """
    counts = {cat: 0 for cat in _KNOWN_CATEGORIES}
    overridden = 0
    for entry in exclusions.get("entries", []):
        counts[entry["category"]] = counts.get(entry["category"], 0) + 1
        if entry.get("user_override"):
            overridden += 1
    counts["overridden"] = overridden
    return counts


def classify_for_auto_exclusion(
    df: pd.DataFrame, min_flight_duration_min: int, check_short_flight_and_gap: bool = True,
) -> tuple[Optional[str], Optional[str]]:
    """
    Apply the three auto-exclusion rules, in priority order (ground_session
    > short_flight > corrupt_log), to an already phase-annotated DataFrame
    (`detect_phases()` must already have run — this doesn't run it itself,
    so a caller that already has phases from an earlier step doesn't pay
    for it twice). Returns (category, reason), or (None, None) if the
    flight should be kept.

    check_short_flight_and_gap=False skips straight to the ground_session
    check only — for a caller with no config.json / no persistence to
    resolve min_flight_duration_min against (load_directory()'s
    workspace_dir=None case).

    The single source of truth for what counts as "not really a flight",
    shared by loader.py's load_directory() (CLI/notebook path) and
    workspace.py's scan_workspace() (web UI folder-scan path) — the two
    ingestion paths silently disagreeing on this (scan_workspace had no
    such check at all until this was added) is exactly the kind of bug a
    second hand-written copy of this logic invites.
    """
    if not any(p in AIRBORNE_PHASES for p in df["phase"].unique()):
        return "ground_session", "no airborne phase detected"

    if not check_short_flight_and_gap:
        return None, None

    if min_flight_duration_min > 0:
        airborne_min = sum(
            seg["duration_s"] for seg in phase_summary(df).to_dict("records")
            if seg["phase"] in AIRBORNE_PHASES
        ) / 60.0
        if airborne_min < min_flight_duration_min:
            return "short_flight", (f"below minimum flight duration "
                                     f"({airborne_min:.0f} min < {min_flight_duration_min} min)")

    gap = df["datetime"].diff().max()
    if pd.notna(gap) and gap > pd.Timedelta(minutes=5):
        return "corrupt_log", (f"time gap of {gap.total_seconds() / 60:.0f} min within "
                                f"a single session — possible avionics restart or SD card error")

    return None, None
