"""
Shipped slice rules (Spec 06 §5.2), per engine profile.

Only the 916iS values are measured (Q1, Session A, over the N117ZS log
set — the measurement is recorded in Spec 06 §5.2 and guarded by
tests/contract/test_research_acceptance.py). Every other profile carries
the 916iS values marked *unverified*, as Spec 10 §5.1 marks topic status.

A preset is an ordinary rule: a pilot may duplicate and edit it, and the
copy becomes a workspace rule (it keeps `from_preset`). The warm-up
preset's oil temperature is read from the profile's OM takeoff minimum,
so it follows the profile rather than a number shipped here.
"""
from __future__ import annotations

import copy
from typing import Optional

from .rules import describe_rule, normalise_rule, phase_rule, PHASES

MEASURED_PROFILES = ("916iS",)
_WARMUP_LIMIT = "oil_temp_takeoff_min"

# Q1 (Session A, 2026-11-07): chosen values. Each entry: the rule, the
# question it lets a pilot ask, and what it isolates.
_916IS = [
    {"rule_id": "full_power", "name": "Full-power segment",
     "conditions": [{"channel": "rpm", "op": ">=", "value": 5550}], "min_duration_s": 15, "merge_gap_s": 3,
     "question": "How does the engine behave at takeoff and go-around power?",
     "isolates": "Takeoff and go-around power — the acceptance case"},
    {"rule_id": "governed_climb", "name": "Governed climb",
     "conditions": [{"channel": "rpm", "op": "between", "min": 5300, "max": 5500},
                    {"channel": "vs_fpm", "op": ">=", "value": 300}], "min_duration_s": 60, "merge_gap_s": 5,
     "question": "How does the engine behave in a climb under the governor?",
     "isolates": "Climb mode under the governor"},
    {"rule_id": "stable_cruise", "name": "Stable cruise",
     "conditions": [{"channel": "rpm", "op": "between", "min": 4800, "max": 5300}],
     "phase": {"mode": "within", "phases": ["CRUISE"]}, "min_duration_s": 300, "merge_gap_s": 5,
     "question": "How steady is the engine in cruise?",
     "isolates": "Steady-state cruise"},
    {"rule_id": "idle", "name": "Idle",
     "conditions": [{"channel": "rpm", "op": "<", "value": 2200}],
     "phase": {"mode": "within", "phases": ["TAXI"]}, "min_duration_s": 30, "merge_gap_s": 3,
     "question": "How smooth is the idle on the ground?",
     "isolates": "Idle quality"},
    {"rule_id": "warm_up", "name": "Warm-up",
     "conditions": [{"channel": "rpm", "op": ">=", "value": 1000},
                    {"channel": "oil_temp_f", "op": "<", "value": {"profile_limit": _WARMUP_LIMIT}}],
     "phase": {"mode": "within", "phases": ["ENGINE_START", "WARMUP", "TAXI"]}, "min_duration_s": 60, "merge_gap_s": 5,
     "question": "How does the engine warm up after start?",
     "isolates": "Warm-up behaviour: engine running until the oil reaches the profile's takeoff minimum"},
]

_INFO_KEYS = ("question", "isolates")


def _profile_value(engine_cfg: Optional[dict], limit_id: str):
    for lim in (engine_cfg or {}).get("limits") or []:
        if lim.get("id") == limit_id:
            return lim.get("min_val") if lim.get("min_val") is not None else lim.get("max_val")
    return None


def _resolve(entry: dict, engine_cfg: Optional[dict]) -> Optional[dict]:
    e = copy.deepcopy(entry)
    for c in e.get("conditions") or []:
        v = c.get("value")
        if isinstance(v, dict) and "profile_limit" in v:
            got = _profile_value(engine_cfg, v["profile_limit"])
            if got is None:
                return None          # the profile has no such limit: the preset doesn't apply
            c["value"] = got
            c["value_source"] = f"profile limit {v['profile_limit']}"
    return e


def list_presets(engine_name: str, engine_cfg: Optional[dict]) -> dict:
    """The presets for a profile, with their status and a one-line
    description each; and the phase rules (§5.3)."""
    measured = engine_name in MEASURED_PROFILES
    out = []
    for entry in _916IS:
        e = _resolve(entry, engine_cfg)
        if e is None:
            continue
        info = {k: e.pop(k) for k in _INFO_KEYS}
        sources = {c["channel"]: c.pop("value_source") for c in e["conditions"] if "value_source" in c}
        rule = normalise_rule({**e, "from_preset": e["rule_id"]})
        out.append({**rule, **info, "description": describe_rule(rule),
                    "status": "measured" if measured else "unverified",
                    **({"value_sources": sources} if sources else {})})
    phases = [phase_rule(p) for p in PHASES if p not in ("PRE_START",)]
    return {"engine": engine_name, "status": "measured" if measured else "unverified",
            "note": (None if measured else f"{engine_name}: the 916iS values, not yet measured on this engine "
                                           "(Spec 06 §5.2) — treat the slice counts with care."),
            "presets": out, "phase_rules": [{**r, "description": describe_rule(r)} for r in phases]}


def preset(rule_id: str, engine_name: str, engine_cfg: Optional[dict]) -> Optional[dict]:
    for p in list_presets(engine_name, engine_cfg)["presets"]:
        if p["rule_id"] == rule_id:
            return p
    return None
