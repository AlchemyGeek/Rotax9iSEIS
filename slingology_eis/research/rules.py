"""
Slice rules (Spec 06 §5.1, §5.3) and hand slices (§5.4).

A rule is data — the form, the API, the CLI and the study file share it:

    {"rule_id": "full_power", "name": "Full-power segment", "from_preset": "full_power",
     "conditions": [{"channel": "rpm", "op": ">=", "value": 5550}],
     "min_duration_s": 15, "merge_gap_s": 3, "pad_s": 0,
     "phase": null | {"mode": "within" | "overlap", "phases": ["CLIMB", …]}}

Conditions are ANDed. A rule with no conditions and a phase constraint is
a **phase slice** (§5.3): every contiguous stretch of those phases.

Applied to one flight on its 1-second grid (the loader's frame, reindexed
to whole seconds — G3X logs are 1 Hz, AXIS frames are resampled to it,
Spec 01 §6.5), a rule yields windows `(start_s, end_s, anchor_s)` in
seconds from the start of the log: `end_s` is exclusive, so
`end_s - start_s` is the number of seconds covered, and `anchor_s` is the
**crossing** — the first satisfying second, before any pad (D6).
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

import numpy as np

from ..channels import CHANNEL_REGISTRY
from ..phases import Phase

OPS = (">=", ">", "<=", "<", "=", "between")
_OP_ALIASES = {"≥": ">=", "≤": "<=", "==": "=", "ge": ">=", "gt": ">", "le": "<=", "lt": "<", "eq": "="}
PHASES = tuple(p.value for p in Phase if p is not Phase.UNKNOWN)
PHASE_MODES = ("within", "overlap")
_RULE_FIELDS = ("conditions", "min_duration_s", "merge_gap_s", "pad_s", "phase")


class RuleError(ValueError):
    """A rule or hand slice that can't be applied; the message says why."""


def _number(v, what: str) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise RuleError(f"{what} must be a number, got {v!r}")
    if not np.isfinite(x):
        raise RuleError(f"{what} must be a finite number, got {v!r}")
    return int(x) if x.is_integer() else x


def _condition(c: dict) -> dict:
    if not isinstance(c, dict):
        raise RuleError(f"a condition is an object, got {c!r}")
    channel = c.get("channel")
    if channel not in CHANNEL_REGISTRY:
        raise RuleError(f"unknown channel {channel!r} (conditions use the channel registry, Spec 01 §6.4)")
    op = _OP_ALIASES.get(c.get("op"), c.get("op"))
    if op not in OPS:
        raise RuleError(f"unknown operator {c.get('op')!r}; one of {', '.join(OPS)}")
    if op == "between":
        lo, hi = _number(c.get("min"), f"{channel} between: min"), _number(c.get("max"), f"{channel} between: max")
        if hi < lo:
            raise RuleError(f"{channel} between: max {hi} is below min {lo}")
        return {"channel": channel, "op": op, "min": lo, "max": hi}
    return {"channel": channel, "op": op, "value": _number(c.get("value"), f"{channel} {op}: value")}


def _phase(p) -> Optional[dict]:
    if p in (None, {}, []):
        return None
    if isinstance(p, str):
        p = {"mode": "within", "phases": [p]}
    if isinstance(p, list):
        p = {"mode": "within", "phases": p}
    mode = p.get("mode", "within")
    if mode not in PHASE_MODES:
        raise RuleError(f"phase mode {mode!r}; one of {', '.join(PHASE_MODES)}")
    phases = [str(x).upper() for x in (p.get("phases") or [])]
    bad = [x for x in phases if x not in PHASES]
    if bad or not phases:
        raise RuleError(f"phase constraint needs phases from {', '.join(PHASES)}; got {p.get('phases')!r}")
    return {"mode": mode, "phases": phases}


def rule_body(rule: dict) -> dict:
    """The fields that decide which windows a rule makes."""
    return {k: rule.get(k) for k in _RULE_FIELDS}


def rule_hash(rule: dict) -> str:
    """Identity of what a rule selects (not its name): the descriptor
    cache is keyed by it, so renaming a rule keeps its cache."""
    canonical = json.dumps(rule_body(rule), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def normalise_rule(rule: dict) -> dict:
    """A validated rule with every field present. Raises RuleError."""
    if not isinstance(rule, dict):
        raise RuleError(f"a slice rule is an object, got {rule!r}")
    conditions = [_condition(c) for c in (rule.get("conditions") or [])]
    phase = _phase(rule.get("phase"))
    if not conditions and phase is None:
        raise RuleError("a slice rule needs at least one condition or a phase constraint")
    if not conditions and phase["mode"] == "overlap":
        raise RuleError("a phase slice (no conditions) takes the phase as 'within'")
    out = {
        "conditions": conditions,
        "min_duration_s": _number(rule.get("min_duration_s", 1), "min_duration_s"),
        "merge_gap_s": _number(rule.get("merge_gap_s", 0), "merge_gap_s"),
        "pad_s": _number(rule.get("pad_s", 0), "pad_s"),
        "phase": phase,
    }
    for k in ("min_duration_s", "merge_gap_s", "pad_s"):
        if out[k] < 0:
            raise RuleError(f"{k} can't be negative")
    out["rule_id"] = str(rule.get("rule_id") or f"r-{rule_hash(out)}")
    out["name"] = str(rule.get("name") or out["rule_id"])
    if rule.get("from_preset"):
        out["from_preset"] = str(rule["from_preset"])
    return {"rule_id": out.pop("rule_id"), "name": out.pop("name"),
            **({"from_preset": out.pop("from_preset")} if "from_preset" in out else {}), **out}


def phase_rule(phase: str) -> dict:
    """§5.3: a phase as a slice rule — every stretch of that phase."""
    p = str(phase).upper()
    return normalise_rule({"rule_id": f"phase:{p}", "name": f"All {p.replace('_', ' ').lower()} phases",
                           "phase": {"mode": "within", "phases": [p]}, "min_duration_s": 1})


def normalise_hand_slice(h: dict) -> dict:
    """§5.4: a flight + start/end offsets, named; `offset_s` reserved for
    the v2 splicer (default 0)."""
    if not isinstance(h, dict) or not h.get("flight"):
        raise RuleError("a hand slice needs a flight")
    start, end = _number(h.get("start_s"), "hand slice start_s"), _number(h.get("end_s"), "hand slice end_s")
    if end <= start:
        raise RuleError(f"hand slice end_s {end} must be after start_s {start}")
    return {"flight": str(h["flight"]), "start_s": start, "end_s": end,
            "label": str(h.get("label") or f"{start:g}–{end:g} s"), "offset_s": _number(h.get("offset_s", 0), "offset_s")}


def describe_rule(rule: dict) -> str:
    """One line a pilot can read: "RPM ≥ 5550 for ≥ 15 s (gaps < 3 s bridged)"."""
    parts = []
    for c in rule["conditions"]:
        cdef = CHANNEL_REGISTRY[c["channel"]]
        unit = f" {cdef.unit}" if cdef.unit and cdef.unit != "rpm" else ""
        if c["op"] == "between":
            parts.append(f"{cdef.label} between {c['min']:g} and {c['max']:g}{unit}")
        else:
            sym = {">=": "≥", "<=": "≤"}.get(c["op"], c["op"])
            parts.append(f"{cdef.label} {sym} {c['value']:g}{unit}")
    if rule.get("phase"):
        ph = ", ".join(p.replace("_", " ").lower() for p in rule["phase"]["phases"])
        parts.append(f"{'within' if rule['phase']['mode'] == 'within' else 'overlapping'} {ph}")
    text = " and ".join(parts)
    text += f", for ≥ {rule['min_duration_s']:g} s"
    if rule["merge_gap_s"]:
        text += f" (dips shorter than {rule['merge_gap_s']:g} s bridged)"
    if rule["pad_s"]:
        text += f", padded {rule['pad_s']:g} s"
    return text


# ── Applying a rule to one flight ─────────────────────────────────────────

def _condition_mask(c: dict, values: dict) -> np.ndarray:
    y = values.get(c["channel"])
    if y is None:
        return None
    with np.errstate(invalid="ignore"):
        if c["op"] == "between":
            m = (y >= c["min"]) & (y <= c["max"])
        else:
            v = c["value"]
            m = {">=": y >= v, ">": y > v, "<=": y <= v, "<": y < v, "=": y == v}[c["op"]]
    return m & np.isfinite(y)


def phase_mask(n: int, phases: list[dict], wanted: list[str]) -> np.ndarray:
    """Rows of the 1-second grid inside any of `wanted` phases (stored
    phase segments, Spec 01 phase model: start_s inclusive, end_s exclusive)."""
    m = np.zeros(n, dtype=bool)
    for seg in phases or []:
        if seg.get("phase") in wanted:
            a = max(0, int(np.floor(float(seg["start_s"]))))
            b = min(n, int(np.ceil(float(seg["end_s"]))))
            m[a:b] = True
    return m


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Inclusive (start, end) index runs of True."""
    if not mask.any():
        return []
    d = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1
    return list(zip(starts.tolist(), ends.tolist()))


def _bridge(runs: list[tuple[int, int]], merge_gap_s: float) -> list[tuple[int, int]]:
    """Join runs separated by a drop shorter than the merge gap (§5.1)."""
    out: list[tuple[int, int]] = []
    for a, b in runs:
        if out and (a - out[-1][1] - 1) < merge_gap_s:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


def apply_rule(rule: dict, values: dict, phases: list[dict], n: int) -> tuple[list[dict], list[str]]:
    """Windows of one flight satisfying `rule`. `values` are channel
    arrays on the 1-second grid (index = seconds from log start), `n` the
    grid length. Returns (windows, missing channels)."""
    missing = [c["channel"] for c in rule["conditions"] if values.get(c["channel"]) is None]
    if missing:
        return [], missing
    mask = np.ones(n, dtype=bool)
    for c in rule["conditions"]:
        mask &= _condition_mask(c, values)
    ph = rule.get("phase")
    pmask = phase_mask(n, phases, ph["phases"]) if ph else None
    if ph and ph["mode"] == "within":
        mask &= pmask
    runs = _bridge(_runs(mask), rule["merge_gap_s"])
    out = []
    for a, b in runs:
        if (b - a + 1) < rule["min_duration_s"]:
            continue
        if ph and ph["mode"] == "overlap" and not pmask[a:b + 1].any():
            continue
        pad = int(round(rule["pad_s"]))
        out.append({"start_s": max(0, a - pad), "end_s": min(n, b + 1 + pad), "anchor_s": a})
    return out, []
