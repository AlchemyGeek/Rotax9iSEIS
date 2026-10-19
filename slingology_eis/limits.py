"""
limits.py — Engine operating limits loader and exceedance checker.

Limits are loaded from a JSON engine config file in engines/ rather than
hardcoded — this is what makes the toolkit work across the Rotax iS
engines (912iS, 915iS, 916iS) without code changes.

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
from .resources import resource


# ── Paths ─────────────────────────────────────────────────────────────────────

_TOOLKIT_ROOT  = Path(__file__).resolve().parent.parent
_ENGINES_DIR   = resource("engines")
_TOOLKIT_CONFIG = resource("config.json")
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
    severity: str = "CAUTION"
    note: str = ""
    phases: Optional[list] = None
    min_duration_s: Optional[float] = None
    min_duration_by_phase: Optional[dict] = None
    report_in_exceedances: bool = True
    # Spec 09 §6.1: stable identity — `param` plus side isn't unique (rpm
    # has three limits, oil_press_psi two MAX ones).
    id: Optional[str] = None
    filter_policy: Optional[dict] = None
    stratify_by: Optional[str] = None
    # Per-limit override of the profile's exceedance_merge_gap_s (Spec 09
    # Q3) — None means use the profile value.
    merge_gap_s: Optional[float] = None
    # Check this limit only while the engine turns at least this fast —
    # for limits that mean nothing with the engine stopped (fuel pressure
    # minimum), where phase labels alone can't be trusted at the end of a
    # log. None = no RPM gate.
    min_rpm: Optional[float] = None
    # Spec 10 D16: check this limit only after its own threshold has been
    # reached at least once since the start of the flight — for limits
    # whose minimum describes a state the engine reaches during spool-up,
    # not from the first sample (rpm_idle_min: the OM's 1,800 rpm idle
    # minimum doesn't apply until the engine has actually idled there once).
    requires_reached_since_start: bool = False


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


_DEFAULT_MIN_FLIGHT_DURATION_MIN = 10


def resolve_min_flight_duration_min(override: Optional[int] = None) -> int:
    """
    Resolve min_flight_duration_min: argument -> toolkit config.json ->
    default 10 (Spec 02 §5.11.2). No environment variable, unlike engine
    resolution — this isn't a per-invocation override, it's an
    install-wide auto-exclusion setting (Spec 02 Q14 proposes moving it
    into per-workspace settings).
    """
    if override is not None:
        return override
    if _TOOLKIT_CONFIG.exists():
        try:
            cfg = json.loads(_TOOLKIT_CONFIG.read_text())
            if "min_flight_duration_min" in cfg:
                return int(cfg["min_flight_duration_min"])
        except Exception:
            pass
    return _DEFAULT_MIN_FLIGHT_DURATION_MIN


def parse_engine_config(text: str, name: str = "") -> dict:
    """
    Parse engine config JSON text into a dict. No file I/O — the core
    parser `load_engine_config()` wraps for disk access.

    Parameters
    ----------
    text : str
        Raw JSON text (the contents of an engines/<name>.json file).
    name : str, optional
        Engine name, used only in the placeholder warning message.

    Returns
    -------
    dict — the full parsed engine config.

    Raises
    ------
    ValueError  if the text is not valid JSON.
    """
    try:
        cfg = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid engine config JSON: {e}")
    egt_spread_config(cfg)   # an incomplete egt_spread block fails here, at load

    # Warn if this is a placeholder config
    if cfg.get("_metadata", {}).get("source_status") == "PLACEHOLDER":
        import warnings
        warnings.warn(
            f"Engine config for '{name or cfg.get('_metadata', {}).get('engine', '?')}' "
            f"is a PLACEHOLDER — values have not been verified against the official "
            f"Operators Manual. Do not rely on these limits for operational decisions.",
            UserWarning, stacklevel=2
        )
    return cfg


# Profiles that once shipped and were withdrawn, with the reason given to
# anyone who still names one (config.json, SLINGOLOGY_ENGINE, a workspace).
RETIRED_ENGINES = {
    "914iS": ("Rotax has no 914iS. The 914 is a carburetted turbo engine, not an iS engine, and there is "
              "no Operators Manual to source a profile from; the former placeholder only copied 915iS "
              "values. Use the profile for your engine: 912iS, 915iS or 916iS."),
}


def load_engine_config(engine: Optional[str] = None) -> dict:
    """
    Load an engine config dict from engines/<name>.json.

    Thin wrapper around `parse_engine_config()` — resolves the engine
    name and file path (touching the filesystem and `engines/`, relative
    to this package), reads the text, and delegates parsing.

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
    if name in RETIRED_ENGINES:
        raise ValueError(f"Engine profile {name!r} is not supported: {RETIRED_ENGINES[name]}")
    path = _ENGINES_DIR / f"{name}.json"
    if not path.exists():
        available = [p.stem for p in _ENGINES_DIR.glob("*.json")]
        raise FileNotFoundError(
            f"Engine config not found: {path}\n"
            f"Available engines: {', '.join(sorted(available))}"
        )
    return parse_engine_config(path.read_text(), name=name)


def engine_limits_from_config(engine_config: dict) -> list[Limit]:
    """Convert an engine config dict to a list of Limit objects.

    Fails loudly (ValueError) on a limit without an `id` or on a duplicate
    id — across `limits` and the computed EGT split / overboost limits —
    since filters, annotations and per-limit metrics key on it (Spec 09
    §6.1)."""
    validate_limit_ids(engine_config)
    limits = []
    for entry in engine_config.get("limits", []):
        limits.append(Limit(
            param=entry["param"],
            label=entry["label"],
            unit=entry.get("unit", ""),
            min_val=entry.get("min_val"),
            max_val=entry.get("max_val"),
            severity=entry.get("severity", "CAUTION"),
            note=entry.get("note", ""),
            phases=entry.get("phases"),
            min_duration_s=entry.get("min_duration_s"),
            min_duration_by_phase=entry.get("min_duration_by_phase"),
            report_in_exceedances=entry.get("report_in_exceedances", True),
            id=entry["id"],
            filter_policy=entry.get("filter_policy"),
            stratify_by=resolve_stratify_by(entry),
            merge_gap_s=entry.get("exceedance_merge_gap_s"),
            min_rpm=entry.get("min_rpm"),
            requires_reached_since_start=entry.get("requires_reached_since_start", False),
        ))
    return limits


EGT_SPLIT_HIGH_FLOW_ID = "egt_split_high_flow"
EGT_SPLIT_LOW_FLOW_ID = "egt_split_low_flow"

# The OM values an egt_spread block must state. There are no defaults: an
# engine whose OM defines no EGT split (the 912iS) has no block and no
# check, and a block missing one of these is a profile error, not a cue
# to borrow another engine's numbers.
_EGT_SPREAD_REQUIRED = ("high_flow_threshold_lph", "high_flow_spread_limit_f", "low_flow_spread_limit_f")


def egt_spread_config(engine_config: dict) -> Optional[dict]:
    """
    The profile's EGT split block, or None when it has none — then there
    is no EGT split check and no EGT split limit anywhere. Raises
    ValueError when the block is present but doesn't state every OM value
    the check needs (`_EGT_SPREAD_REQUIRED`).
    """
    if "egt_spread" not in engine_config:
        return None
    spread = engine_config["egt_spread"]
    if not isinstance(spread, dict):
        raise ValueError("Engine profile 'egt_spread' must be an object; omit it when the OM defines no EGT split.")
    missing = [k for k in _EGT_SPREAD_REQUIRED
               if isinstance(spread.get(k), bool) or not isinstance(spread.get(k), (int, float))]
    if missing:
        raise ValueError(
            f"Engine profile 'egt_spread' block is incomplete: missing or non-numeric {', '.join(missing)}. "
            f"State every value from the Operators Manual, or omit the block when the OM defines no EGT split."
        )
    return spread
OVERBOOST_ID = "overboost"


def validate_limit_ids(engine_config: dict) -> None:
    """
    Raise ValueError if any limit lacks an `id`, two limits share one, or
    a limit (or the `overboost` block) still declares the retired
    `time_limit_s` field. `time_limit_s` suppressed an event shorter than
    a minimum duration; its one real use (`rpm_takeoff_max`'s 5-minute
    allowance) was wrong — the OM's 5-minute rule belongs to `overboost`,
    not the 5,800 rpm ceiling — so v0.12 retires the field everywhere
    (Spec 09 §6.7) rather than leave a stale profile free to keep the old,
    incorrect meaning. `overboost`'s own former `time_limit_s` (the 300 s
    block ceiling) is renamed `limit_s` for the same reason.
    """
    seen: set[str] = set()
    ids = [(e.get("id"), e.get("label", "?")) for e in engine_config.get("limits", [])]
    spread = egt_spread_config(engine_config)
    if spread is not None:
        ids.append((spread.get("high_flow_limit_id", EGT_SPLIT_HIGH_FLOW_ID), "EGT split (high flow)"))
        ids.append((spread.get("low_flow_limit_id", EGT_SPLIT_LOW_FLOW_ID), "EGT split (low flow)"))
    if engine_config.get("overboost"):
        ids.append((engine_config["overboost"].get("id", OVERBOOST_ID), "Overboost"))
    for lid, label in ids:
        if not lid or not isinstance(lid, str):
            raise ValueError(f"Engine profile limit {label!r} has no 'id' (Spec 09 §6.1).")
        if lid in seen:
            raise ValueError(f"Engine profile has duplicate limit id {lid!r} (Spec 09 §6.1).")
        seen.add(lid)

    for entry in engine_config.get("limits", []):
        if "time_limit_s" in entry:
            raise ValueError(
                f"Engine profile limit {entry.get('label', entry.get('id', '?'))!r} declares "
                f"'time_limit_s', removed in v0.12 (Spec 09 §6.7) — no limit uses a duration-"
                f"suppression gate any more; the OM 5-minute rule belongs to 'overboost'."
            )
    ob = engine_config.get("overboost")
    if ob and "time_limit_s" in ob:
        raise ValueError(
            "Engine profile's 'overboost' block declares 'time_limit_s' — renamed 'limit_s' "
            "in v0.12 (Spec 09 §6.4/§6.7)."
        )


# Spec 09 §6.5: default stratification band for each limit's per-flight
# metrics, following the BASELINE_METRIC_DEFS convention (temperatures by
# OAT, manifold pressure by density altitude, everything else none).
_OAT_STRATIFIED_PARAMS = {"oil_temp_f", "coolant_temp_f", "egt1_f", "egt2_f", "egt3_f", "egt4_f", "egt_spread_f"}
_DA_STRATIFIED_PARAMS = {"map_inhg"}


def resolve_stratify_by(entry: dict) -> Optional[str]:
    if "stratify_by" in entry:
        return entry["stratify_by"]
    param = entry.get("param")
    if param in _OAT_STRATIFIED_PARAMS:
        return "oat_band"
    if param in _DA_STRATIFIED_PARAMS:
        return "da_band"
    return None


def exceedance_merge_gap_s(engine_config: dict) -> float:
    """Spec 09 §6.2. Absent from a profile means no merging (each dip back
    within the limit ends the event, the pre-Spec-09 behaviour)."""
    return float(engine_config.get("exceedance_merge_gap_s", 0) or 0)


def limit_catalog(engine_config: dict) -> list[dict]:
    """
    Every limit the profile defines — `limits` entries plus the two
    computed EGT split limits and the overboost limit — as plain dicts:
    {id, param, label, unit, limit_type, limit_value, severity,
    report_in_exceedances, stratify_by, filter_policy?}.
    One entry per side, so a limit with both min_val and max_val (none do
    today) would appear twice under the same id. Carried on
    FlightAnalysis.limits so insight evaluation can resolve a limit
    without the engine profile in hand.
    """
    out = []
    for lim in engine_limits_from_config(engine_config):
        for limit_type, value in (("MIN", lim.min_val), ("MAX", lim.max_val)):
            if value is None:
                continue
            entry = {
                "id": lim.id, "param": lim.param, "label": lim.label, "unit": lim.unit,
                "limit_type": limit_type, "limit_value": value, "severity": lim.severity,
                "report_in_exceedances": lim.report_in_exceedances,
                "stratify_by": lim.stratify_by,
                "min_rpm": lim.min_rpm,
            }
            if lim.filter_policy is not None:
                entry["filter_policy"] = lim.filter_policy
            # Spec 14 §5 Engine tab — phase-aware suppression, read-only
            # display only; these are already-declared profile fields
            # (engine_limits_from_config above), not new computation.
            if lim.phases is not None:
                entry["phases"] = lim.phases
            if lim.min_duration_s is not None:
                entry["min_duration_s"] = lim.min_duration_s
            if lim.min_duration_by_phase is not None:
                entry["min_duration_by_phase"] = lim.min_duration_by_phase
            if lim.requires_reached_since_start:
                entry["requires_reached_since_start"] = True
            if lim.note:
                entry["note"] = lim.note
            out.append(entry)
    spread = egt_spread_config(engine_config)
    if spread is not None:
        for id_key, default_id, limit_key, label in (
            ("high_flow_limit_id", EGT_SPLIT_HIGH_FLOW_ID, "high_flow_spread_limit_f", "EGT Split (high fuel flow)"),
            ("low_flow_limit_id", EGT_SPLIT_LOW_FLOW_ID, "low_flow_spread_limit_f", "EGT Split (low fuel flow)"),
        ):
            entry = {
                "id": spread.get(id_key, default_id), "param": "egt_spread_f", "label": label, "unit": "°F",
                "limit_type": "MAX", "limit_value": spread[limit_key],
                "severity": "WARNING", "report_in_exceedances": True,
                "stratify_by": spread.get("stratify_by", "oat_band"),
            }
            policy = spread.get("high_flow_filter_policy" if "high" in id_key else "low_flow_filter_policy")
            if policy is not None:
                entry["filter_policy"] = policy
            out.append(entry)
    ob = engine_config.get("overboost") or {}
    if ob:
        entry = {
            "id": ob.get("id", OVERBOOST_ID), "param": "overboost",
            "label": "Overboost (max continuous block)", "unit": "s",
            "limit_type": "MAX", "limit_value": ob.get("limit_s", 300),
            # Spec 09 v0.12 §6.4: overboost is the single owner of the OM
            # 5-minute rule (retiring rpm_continuous_max), so it's now an
            # ordinary reported exceedance rather than excluded from
            # limit_exceedances.
            "severity": "WARNING", "report_in_exceedances": True,
            "stratify_by": ob.get("stratify_by", "da_band"),
            "close_call_margin_s": ob.get("close_call_margin_s", 60),
        }
        if ob.get("filter_policy") is not None:
            entry["filter_policy"] = ob["filter_policy"]
        out.append(entry)
    return out


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
    note: str
    limit_id: Optional[str] = None
    # Spec 09 §4: how far past the limit, in engine units — observed − limit
    # for MAX, limit − observed for MIN.
    excess: Optional[float] = None

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

    Readings that dip back within a limit for less than the profile's
    `exceedance_merge_gap_s` don't end an event (Spec 09 §6.2); the
    `min_duration_s` / `min_duration_by_phase` checks then apply to the
    merged event.

    Returns a list of ExceedanceEvent objects, sorted by start time.
    """
    if engine_config is None:
        engine_config, lims = _get_defaults()
    else:
        lims = engine_limits_from_config(engine_config)
    gap_s = exceedance_merge_gap_s(engine_config)

    events: list[ExceedanceEvent] = []

    for lim in lims:
        if not lim.report_in_exceedances:
            continue
        if lim.param not in df.columns:
            continue

        # Phase filtering — restrict rows to allowed phases if specified
        if lim.phases and "phase" in df.columns:
            working_df = df[df["phase"].isin(lim.phases)]
        else:
            working_df = df
        # RPM gate — only rows with the engine turning at least min_rpm
        # (a missing RPM reading counts as not running).
        if lim.min_rpm is not None and "rpm" in working_df.columns:
            working_df = working_df[working_df["rpm"].fillna(0) >= lim.min_rpm]
        # Idle-established gate (Spec 10 D16) — the limit applies only
        # after its own threshold has been reached at least once since
        # the start of the flight (e.g. rpm reaching 1,800 at least once
        # before idle-minimum checking begins), so spool-up before the
        # engine has ever gotten there isn't an exceedance. A phase
        # exclusion can't do this: spool-up mostly falls in WARMUP, and
        # excluding WARMUP would also hide a real low warm-up idle.
        if lim.requires_reached_since_start and lim.param in working_df.columns:
            threshold = lim.min_val if lim.min_val is not None else lim.max_val
            if threshold is not None:
                reached = (working_df[lim.param] >= threshold) if lim.min_val is not None \
                    else (working_df[lim.param] <= threshold)
                reached_idx = working_df.index[reached.fillna(False)]
                working_df = working_df.loc[reached_idx[0]:] if len(reached_idx) else working_df.iloc[0:0]

        series = working_df[lim.param]
        if series.isna().all():
            continue

        lim_gap_s = gap_s if lim.merge_gap_s is None else float(lim.merge_gap_s)
        if lim.min_val is not None:
            mask = series < lim.min_val
            _accumulate_events(working_df, series, mask, lim, "MIN", lim.min_val, events, lim_gap_s)
        if lim.max_val is not None:
            mask = series > lim.max_val
            _accumulate_events(working_df, series, mask, lim, "MAX", lim.max_val, events, lim_gap_s)

    # ── EGT spread: conditional on fuel flow ─────────────────────────────────
    # Only for an engine whose OM defines an EGT split: no egt_spread block,
    # no check (OM-912 i defines none). Thresholds come from the profile,
    # never from another engine's numbers.
    egt_spread_cfg = egt_spread_config(engine_config)
    if egt_spread_cfg is not None and "egt_spread_f" in df.columns and "fuel_flow_lph" in df.columns:
        hi_flow_threshold = egt_spread_cfg["high_flow_threshold_lph"]
        hi_spread_f       = egt_spread_cfg["high_flow_spread_limit_f"]
        lo_spread_f       = egt_spread_cfg["low_flow_spread_limit_f"]
        hi_note = egt_spread_cfg.get("high_flow_note", f"EGT split limit at fuel flow > {hi_flow_threshold} L/hr")
        lo_note = egt_spread_cfg.get("low_flow_note",  f"EGT split limit at fuel flow < {hi_flow_threshold} L/hr")
        hi_id = egt_spread_cfg.get("high_flow_limit_id", EGT_SPLIT_HIGH_FLOW_ID)
        lo_id = egt_spread_cfg.get("low_flow_limit_id", EGT_SPLIT_LOW_FLOW_ID)

        hi_flow = df["fuel_flow_lph"] >= hi_flow_threshold
        lo_flow = df["fuel_flow_lph"] <  hi_flow_threshold

        for mask_cond, spread_limit_f, note_text, lid in [
            (hi_flow, hi_spread_f, hi_note, hi_id),
            (lo_flow, lo_spread_f, lo_note, lo_id),
        ]:
            mask = (df["egt_spread_f"] > spread_limit_f) & mask_cond
            lim_obj = Limit(
                "egt_spread_f", "EGT Split", "°F",
                max_val=spread_limit_f, severity="WARNING", note=note_text, id=lid,
            )
            _accumulate_events(df, df["egt_spread_f"], mask, lim_obj, "MAX",
                               spread_limit_f, events, gap_s)

    # ── Overboost: single owner of the OM 5-minute rule (Spec 09 §6.4, v0.12) ──
    # Not an ordinary column-vs-threshold limit — the "value" being tested
    # is a merged block's own duration, not a channel reading within it —
    # so it doesn't go through _accumulate_events/_add_event; it shares
    # only the run-finding/merging machinery those use.
    ob_cfg = engine_config.get("overboost") or {}
    if ob_cfg and "rpm" in df.columns:
        ob_limit_s = ob_cfg.get("limit_s", 300)
        lid = ob_cfg.get("id", OVERBOOST_ID)
        for block in overboost_blocks(df, ob_cfg, gap_s):
            if block["duration_s"] <= ob_limit_s:
                continue
            events.append(ExceedanceEvent(
                param="overboost", label="Overboost (max continuous block)", unit="s",
                severity="WARNING", limit_type="MAX", limit_value=ob_limit_s,
                observed_value=block["duration_s"],
                started_at=block["start_time"], ended_at=block["end_time"],
                duration_s=block["duration_s"], note=ob_cfg.get("note", ""),
                limit_id=lid, excess=round(block["duration_s"] - ob_limit_s, 4),
            ))

    events.sort(key=lambda e: e.started_at)
    return events


def overboost_blocks(df: pd.DataFrame, ob_cfg: dict, gap_s: float = 0.0) -> list[dict]:
    """
    Spec 09 §6.4 (v0.12): every merged block where the engine was in the
    overboost regime (`rpm > rpm_threshold` OR `power_pct > power_pct_threshold`),
    merged across gaps under `gap_s` seconds the same way check_exceedances()
    merges every other limit's runs (find_runs/split_runs_at_time_gaps/
    merge_runs) — so `overboost_max_block_s` (phases.overboost_time) and the
    limit_exceedances events built from this list share one block
    definition and can never disagree.

    Returns every merged block (including ones that never reach the
    configured limit — phases.overboost_time needs the full set for its
    "longest block" metric), as
    `{"start_idx", "end_idx", "start_time", "end_time", "duration_s"}`,
    in order. Empty without an `rpm` channel or an `overboost` config.
    """
    if "rpm" not in df.columns or not ob_cfg:
        return []
    rpm_threshold = ob_cfg.get("rpm_threshold", 5500)
    pwr_threshold = ob_cfg.get("power_pct_threshold", 100)
    power_pct = df["power_pct"].fillna(0) if "power_pct" in df.columns else 0
    mask = (df["rpm"].fillna(0) > rpm_threshold) | (power_pct > pwr_threshold)
    runs = split_runs_at_time_gaps(df["datetime"], find_runs(mask))
    blocks = []
    for start_idx, end_idx in merge_runs(df["datetime"], runs, gap_s):
        t_start = df["datetime"].iloc[start_idx]
        t_end = df["datetime"].iloc[end_idx]
        dur_s = (t_end - t_start).total_seconds() + 1
        blocks.append({
            "start_idx": start_idx, "end_idx": end_idx,
            "start_time": t_start, "end_time": t_end, "duration_s": dur_s,
        })
    return blocks


def find_runs(mask: pd.Series) -> list[tuple[int, int]]:
    """Positional (start, end) index pairs, inclusive, of each run of True
    rows in `mask` (NaN counts as False)."""
    m = mask.fillna(False).to_numpy(dtype=bool)
    if not m.any():
        return []
    padded = np.concatenate(([False], m, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return [(int(s), int(e) - 1) for s, e in zip(edges[0::2], edges[1::2])]


def merge_runs(times: pd.Series, runs: list[tuple[int, int]], gap_s: float) -> list[tuple[int, int]]:
    """
    Spec 09 §6.2: join consecutive runs when the reading stayed within the
    limit for less than `gap_s` seconds between them. Measured in time,
    not rows — phase filtering makes rows non-contiguous. "Within the limit
    for" = the time between the last exceeding row and the next one, less
    one sample (1 s at the G3X's 1 Hz), matching duration_s's own +1.
    """
    if gap_s <= 0 or len(runs) < 2:
        return list(runs)
    merged = [runs[0]]
    for start, end in runs[1:]:
        prev_start, prev_end = merged[-1]
        within_s = (times.iloc[start] - times.iloc[prev_end]).total_seconds() - 1
        if within_s < gap_s:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))
    return merged


def split_runs_at_time_gaps(times: pd.Series, runs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """
    Break a run wherever consecutive rows aren't consecutive samples in
    time — phase filtering (`lim.phases`) drops rows, so two exceeding
    stretches either side of an excluded phase sit next to each other in
    the filtered frame but are really separate. The sample period is the
    frame's median row spacing; a jump beyond 1.5x that is a break.
    merge_runs() then decides, in time, whether to re-join them.
    """
    if len(times) < 2 or not runs:
        return list(runs)
    secs = (times - times.iloc[0]).dt.total_seconds().to_numpy()
    diffs = np.diff(secs)
    period = float(np.median(diffs)) if len(diffs) else 1.0
    breaks = np.flatnonzero(diffs > 1.5 * max(period, 1e-9))  # break between i and i+1
    out = []
    for start, end in runs:
        cut = breaks[(breaks >= start) & (breaks < end)]
        s = start
        for b in cut:
            out.append((s, int(b)))
            s = int(b) + 1
        out.append((s, end))
    return out


def _accumulate_events(df, series, mask, lim, limit_type, limit_value, events, gap_s: float = 0.0):
    runs = split_runs_at_time_gaps(df["datetime"], find_runs(mask))
    if not runs:
        return
    for start_idx, end_idx in merge_runs(df["datetime"], runs, gap_s):
        _add_event(df, series, lim, limit_type, limit_value, start_idx, end_idx, events)


def _add_event(df, series, lim, limit_type, limit_value, start_idx, end_idx, events):
    t_start = df["datetime"].iloc[start_idx]
    t_end   = df["datetime"].iloc[end_idx]
    dur_s   = (t_end - t_start).total_seconds() + 1

    # min_duration_by_phase — per-phase duration threshold
    if lim.min_duration_by_phase and "phase" in df.columns:
        phase_at_start = df["phase"].iloc[start_idx]
        threshold = lim.min_duration_by_phase.get(phase_at_start)
        if threshold is None:
            return  # null = suppress entirely for this phase
        if dur_s < threshold:
            return

    # min_duration_s — flat duration threshold regardless of phase
    elif lim.min_duration_s is not None:
        if dur_s < lim.min_duration_s:
            return
    obs = series.iloc[start_idx:end_idx + 1].max() \
        if limit_type == "MAX" else series.iloc[start_idx:end_idx + 1].min()
    excess = float(obs) - limit_value if limit_type == "MAX" else limit_value - float(obs)
    events.append(ExceedanceEvent(
        param=lim.param, label=lim.label, unit=lim.unit,
        severity=lim.severity, limit_type=limit_type,
        limit_value=limit_value, observed_value=float(obs),
        started_at=t_start, ended_at=t_end, duration_s=dur_s,
        note=lim.note,
        limit_id=lim.id, excess=round(excess, 4),
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


# ── Per-limit metrics (Spec 09 §5) ───────────────────────────────────────────

def limit_metric_ids(entry: dict) -> list[tuple[str, str, str]]:
    """
    (flight metric id, fleet metric key, unit) for each per-flight metric
    one catalogue entry gets. Overboost's limit is itself a time, so it
    gets the longest continuous block instead of peak excess and no
    time-above share. A limit that is never checked for events
    (`report_in_exceedances: false`) gets none.
    """
    lid = entry["id"]
    if entry.get("param") == "overboost":
        return [(f"lim_{lid}_block_s", f"limit_{lid}_block_s", "s")]
    if not entry.get("report_in_exceedances", True):
        return []
    return [
        (f"lim_{lid}_peak_excess", f"limit_{lid}_peak_excess", entry.get("unit", "")),
        (f"lim_{lid}_time_above_pct", f"limit_{lid}_time_above_pct", "%"),
    ]


def per_limit_metrics(
    exceedances: list[dict],
    catalog: list[dict],
    running_s: Optional[float],
    channels_present: set,
    overboost_max_block_s: Optional[float] = None,
) -> dict[str, dict]:
    """
    Spec 09 §5: two per-flight metrics for every limit, filtered or not —
    `lim_<id>_peak_excess` (largest excess of any merged event; missing
    when the flight had none) and `lim_<id>_time_above_pct` (total event
    duration over engine-running time, %; 0 with no events). Returns
    MetricValue dicts keyed by flight metric id, the same shape as
    FlightAnalysis.metrics. `exceedances` are serialized events (with
    limit_id and excess); `running_s` is engine-running time from phase
    detection, so the share doesn't depend on how long the log ran.
    """
    by_limit: dict[str, list[dict]] = {}
    for e in exceedances:
        if e.get("limit_id"):
            by_limit.setdefault(e["limit_id"], []).append(e)

    out: dict[str, dict] = {}
    for entry in catalog:
        ids = limit_metric_ids(entry)
        if not ids:
            continue
        if entry.get("param") == "overboost":
            mid, _, unit = ids[0]
            mv = {"id": mid, "value": overboost_max_block_s, "unit": unit}
            if overboost_max_block_s is None:
                mv["missing"] = "CHANNEL_MISSING" if "rpm" not in channels_present else "INSUFFICIENT_DATA"
            out[mid] = mv
            continue
        (peak_id, _, peak_unit), (pct_id, _, pct_unit) = ids
        events = by_limit.get(entry["id"], [])
        if entry["param"] not in channels_present:
            out[peak_id] = {"id": peak_id, "value": None, "unit": peak_unit, "missing": "CHANNEL_MISSING"}
            out[pct_id] = {"id": pct_id, "value": None, "unit": pct_unit, "missing": "CHANNEL_MISSING"}
            continue
        excesses = [e["excess"] for e in events if e.get("excess") is not None]
        peak = {"id": peak_id, "value": round(max(excesses), 4) if excesses else None, "unit": peak_unit}
        if not excesses:
            peak["missing"] = "NOT_APPLICABLE"  # no event this flight
        out[peak_id] = peak
        if running_s:
            pct = 100.0 * sum(e["duration_s"] for e in events) / running_s
            out[pct_id] = {"id": pct_id, "value": round(min(pct, 100.0), 4), "unit": pct_unit}
        else:
            out[pct_id] = {"id": pct_id, "value": None, "unit": pct_unit, "missing": "INSUFFICIENT_DATA"}
    return out


_NOT_RUNNING_PHASES = {"PRE_START", "SHUTDOWN"}


def engine_running_s(df: pd.DataFrame) -> Optional[float]:
    """Engine start to shutdown, in seconds, from phase detection: the span
    of rows not labelled PRE_START or SHUTDOWN. Without a phase column,
    the span of rows with RPM above zero. None if neither finds any."""
    if "datetime" not in df.columns or df.empty:
        return None
    if "phase" in df.columns:
        running = df[~df["phase"].isin(_NOT_RUNNING_PHASES)]
    elif "rpm" in df.columns:
        running = df[df["rpm"].fillna(0) > 0]
    else:
        return None
    if running.empty:
        return None
    return (running["datetime"].iloc[-1] - running["datetime"].iloc[0]).total_seconds() + 1
