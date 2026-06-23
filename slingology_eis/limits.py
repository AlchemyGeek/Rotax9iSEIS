"""
limits.py — Engine operating limits loader and exceedance checker.

Limits are loaded from a JSON engine config file in engines/ rather than
hardcoded — this is what makes the toolkit work across all four Rotax iS
engines (912iS, 914iS, 915iS, 916iS) without code changes.

Engine selection (in priority order):
  1. Explicit argument to load_engine_config(engine="916iS")
  2. SLINGOLOGY_ENGINE environment variable
  3. engine field in toolkit root config.json
  4. Fallback default: 916iS

Usage
-----
    from slingology_eis.limits import check_exceedances, limits_report, load_engine_config

    # Uses engine from config.json (or default 916iS):
    events = check_exceedances(df)

    # Explicit engine override:
    cfg = load_engine_config("915iS")
    events = check_exceedances(df, engine_config=cfg)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# ── Paths ─────────────────────────────────────────────────────────────────────

_TOOLKIT_ROOT  = Path(__file__).resolve().parent.parent
_ENGINES_DIR   = _TOOLKIT_ROOT / "engines"
_TOOLKIT_CONFIG = _TOOLKIT_ROOT / "config.json"
_DEFAULT_ENGINE = "916iS"


# ── Limit dataclass ───────────────────────────────────────────────────────────

@dataclass
class Limit:
    """A single operating parameter limit."""
    param: str
    label: str
    unit: str
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    time_limit_s: Optional[float] = None
    severity: str = "CAUTION"
    note: str = ""


# ── Engine config loader ──────────────────────────────────────────────────────

def _resolve_engine_name(engine: Optional[str] = None) -> str:
    """Resolve engine name from argument → env var → config.json → default."""
    if engine:
        return engine
    env = os.environ.get("SLINGOLOGY_ENGINE")
    if env:
        return env
    if _TOOLKIT_CONFIG.exists():
        try:
            cfg = json.loads(_TOOLKIT_CONFIG.read_text())
            if "engine" in cfg:
                return cfg["engine"]
        except Exception:
            pass
    return _DEFAULT_ENGINE


def load_engine_config(engine: Optional[str] = None) -> dict:
    """
    Load an engine config dict from engines/<name>.json.

    Parameters
    ----------
    engine : str, optional
        Engine name (e.g. "916iS"). If None, resolved via
        _resolve_engine_name() — environment variable, then
        config.json, then the 916iS default.

    Returns
    -------
    dict — the full parsed engine config.

    Raises
    ------
    FileNotFoundError  if the engine JSON file doesn't exist.
    ValueError         if the file is not valid JSON.
    """
    name = _resolve_engine_name(engine)
    path = _ENGINES_DIR / f"{name}.json"
    if not path.exists():
        available = [p.stem for p in _ENGINES_DIR.glob("*.json")]
        raise FileNotFoundError(
            f"Engine config not found: {path}\n"
            f"Available engines: {', '.join(sorted(available))}"
        )
    try:
        cfg = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {path}: {e}")

    # Warn if this is a placeholder config
    if cfg.get("_metadata", {}).get("source_status") == "PLACEHOLDER":
        import warnings
        warnings.warn(
            f"Engine config for '{name}' is a PLACEHOLDER — values have not been "
            f"verified against the official Operators Manual. Do not rely on these "
            f"limits for operational decisions.",
            UserWarning, stacklevel=2
        )
    return cfg


def engine_limits_from_config(engine_config: dict) -> list[Limit]:
    """Convert an engine config dict to a list of Limit objects."""
    limits = []
    for entry in engine_config.get("limits", []):
        limits.append(Limit(
            param=entry["param"],
            label=entry["label"],
            unit=entry["unit"],
            min_val=entry.get("min_val"),
            max_val=entry.get("max_val"),
            time_limit_s=entry.get("time_limit_s"),
            severity=entry.get("severity", "CAUTION"),
            note=entry.get("note", ""),
        ))
    return limits


# ── Module-level defaults (loaded once at import, can be overridden per call) ──
# Loading at import time means existing callers (e.g. notebook 01 which calls
# limits_report(df) with no arguments) continue to work with zero changes.

_default_engine_config: Optional[dict] = None
_default_limits: Optional[list[Limit]] = None


def _get_defaults() -> tuple[dict, list[Limit]]:
    """Lazy-load the default engine config once."""
    global _default_engine_config, _default_limits
    if _default_engine_config is None:
        _default_engine_config = load_engine_config()
        _default_limits = engine_limits_from_config(_default_engine_config)
    return _default_engine_config, _default_limits


# Keep LIMITS as a module-level attribute for any code that imports it directly
# — populated lazily on first access.
class _LimitsProxy(list):
    """Proxy list that populates itself from the default engine config on first use."""
    def __init__(self):
        super().__init__()
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            _, lims = _get_defaults()
            self.extend(lims)
            self._loaded = True

    def __iter__(self):
        self._ensure_loaded()
        return super().__iter__()

    def __len__(self):
        self._ensure_loaded()
        return super().__len__()

    def __getitem__(self, idx):
        self._ensure_loaded()
        return super().__getitem__(idx)


LIMITS = _LimitsProxy()


# ── Convenience lookup ────────────────────────────────────────────────────────

def limits_for(param: str, engine_config: Optional[dict] = None) -> list[Limit]:
    """Return all Limit objects for a given column name."""
    lims = engine_limits_from_config(engine_config) if engine_config else list(LIMITS)
    return [l for l in lims if l.param == param]


def normal_range(param: str, engine_config: Optional[dict] = None) -> tuple[Optional[float], Optional[float]]:
    """Return the tightest (min, max) normal range for a parameter."""
    lims = limits_for(param, engine_config)
    mins = [l.min_val for l in lims if l.min_val is not None]
    maxs = [l.max_val for l in lims if l.max_val is not None]
    return (min(mins) if mins else None, max(maxs) if maxs else None)


# ── Exceedance checker ────────────────────────────────────────────────────────

@dataclass
class ExceedanceEvent:
    """A detected exceedance of an operating limit."""
    param: str
    label: str
    unit: str
    severity: str
    limit_type: str
    limit_value: float
    observed_value: float
    started_at: pd.Timestamp
    ended_at: pd.Timestamp
    duration_s: float
    time_limit_s: Optional[float]
    note: str

    def __str__(self):
        direction = "below min" if self.limit_type == "MIN" else "above max"
        return (
            f"[{self.severity}] {self.label}: "
            f"{self.observed_value:.1f} {self.unit} {direction} "
            f"{self.limit_value:.1f} {self.unit} "
            f"at {self.started_at:%H:%M:%S} for {self.duration_s:.0f}s"
        )


def check_exceedances(
    df: pd.DataFrame,
    engine_config: Optional[dict] = None,
) -> list[ExceedanceEvent]:
    """
    Check a flight DataFrame against operating limits.

    Parameters
    ----------
    engine_config : dict, optional
        Engine config from load_engine_config(). If None, uses the
        default engine resolved from config.json / environment variable.

    Returns a list of ExceedanceEvent objects, sorted by start time.
    """
    if engine_config is None:
        engine_config, lims = _get_defaults()
    else:
        lims = engine_limits_from_config(engine_config)

    events: list[ExceedanceEvent] = []

    for lim in lims:
        if lim.param not in df.columns:
            continue
        series = df[lim.param].copy()
        if series.isna().all():
            continue
        if lim.min_val is not None:
            mask = series < lim.min_val
            _accumulate_events(df, series, mask, lim, "MIN", lim.min_val, events)
        if lim.max_val is not None:
            mask = series > lim.max_val
            _accumulate_events(df, series, mask, lim, "MAX", lim.max_val, events)

    # ── EGT spread: conditional on fuel flow ─────────────────────────────────
    # Thresholds come from the engine config rather than being hardcoded.
    egt_spread_cfg = engine_config.get("egt_spread", {})
    hi_flow_threshold = egt_spread_cfg.get("high_flow_threshold_lph", 3.0)
    hi_spread_f       = egt_spread_cfg.get("high_flow_spread_limit_f", 392.0)
    lo_spread_f       = egt_spread_cfg.get("low_flow_spread_limit_f", 932.0)
    hi_note = egt_spread_cfg.get("high_flow_note", f"EGT split limit at fuel flow > {hi_flow_threshold} L/hr")
    lo_note = egt_spread_cfg.get("low_flow_note",  f"EGT split limit at fuel flow < {hi_flow_threshold} L/hr")

    if "egt_spread_f" in df.columns and "fuel_flow_lph" in df.columns:
        hi_flow = df["fuel_flow_lph"] >= hi_flow_threshold
        lo_flow = df["fuel_flow_lph"] <  hi_flow_threshold

        for mask_cond, spread_limit_f, note_text in [
            (hi_flow, hi_spread_f, hi_note),
            (lo_flow, lo_spread_f, lo_note),
        ]:
            mask = (df["egt_spread_f"] > spread_limit_f) & mask_cond
            lim_obj = Limit(
                "egt_spread_f", "EGT Split", "°F",
                max_val=spread_limit_f, severity="WARNING", note=note_text
            )
            _accumulate_events(df, df["egt_spread_f"], mask, lim_obj, "MAX",
                               spread_limit_f, events)

    events.sort(key=lambda e: e.started_at)
    return events


def _accumulate_events(df, series, mask, lim, limit_type, limit_value, events):
    mask = mask.fillna(False)
    if not mask.any():
        return
    in_event = False
    start_idx = None
    for idx in range(len(mask)):
        if mask.iloc[idx] and not in_event:
            in_event = True
            start_idx = idx
        elif not mask.iloc[idx] and in_event:
            in_event = False
            _add_event(df, series, lim, limit_type, limit_value,
                       start_idx, idx - 1, events)
    if in_event and start_idx is not None:
        _add_event(df, series, lim, limit_type, limit_value,
                   start_idx, len(mask) - 1, events)


def _add_event(df, series, lim, limit_type, limit_value, start_idx, end_idx, events):
    t_start = df["datetime"].iloc[start_idx]
    t_end   = df["datetime"].iloc[end_idx]
    dur_s   = (t_end - t_start).total_seconds() + 1
    if lim.time_limit_s is not None and dur_s <= lim.time_limit_s:
        return
    obs = series.iloc[start_idx:end_idx + 1].max() \
        if limit_type == "MAX" else series.iloc[start_idx:end_idx + 1].min()
    events.append(ExceedanceEvent(
        param=lim.param, label=lim.label, unit=lim.unit,
        severity=lim.severity, limit_type=limit_type,
        limit_value=limit_value, observed_value=float(obs),
        started_at=t_start, ended_at=t_end, duration_s=dur_s,
        time_limit_s=lim.time_limit_s, note=lim.note,
    ))


# ── Quick report ─────────────────────────────────────────────────────────────

def limits_report(
    df: pd.DataFrame,
    engine_config: Optional[dict] = None,
) -> str:
    """Return a formatted text summary of all limit checks for a flight."""
    cfg, _ = _get_defaults() if engine_config is None else (engine_config, None)
    engine_name = cfg.get("_metadata", {}).get("engine", "unknown engine")
    source_status = cfg.get("_metadata", {}).get("source_status", "")
    placeholder_warn = " [PLACEHOLDER LIMITS — not verified against OM]" if source_status == "PLACEHOLDER" else ""

    events = check_exceedances(df, engine_config=cfg)
    lines = [f"── Operating Limits ({engine_name}){placeholder_warn} ─────────────────"]
    if not events:
        lines.append("✓ No operating limit exceedances detected.")
    else:
        lines.append(f"⚠  {len(events)} exceedance event(s) detected:")
        for e in events:
            lines.append(f"   {e}")
    return "\n".join(lines)
