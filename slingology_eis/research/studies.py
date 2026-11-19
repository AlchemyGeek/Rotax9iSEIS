"""
What remains of Spec 06 §10's studies after v1.0 (Spec 16 D15): hand
studies, `.eisstudy` and their operations are retired — a study is a
notebook (Spec 16 §5), and one still stored the old way
(`studies/<id>.json`) is converted on first load (investigations/ipynb.py).
Kept: a question's normalised form and the channels it needs, which
`run_test` (research/api.py) uses.
"""
from __future__ import annotations

from typing import Optional

from . import questions as Q
from .descriptors import STANDARD_CHANNELS
from .rules import RuleError, normalise_hand_slice, normalise_rule


def _selection(sel: Optional[dict]) -> dict:
    sel = dict(sel or {"mode": "all"})
    mode = sel.get("mode", "all")
    if mode not in ("all", "flights"):
        raise RuleError(f"selection mode {mode!r}; one of all, flights")
    out = {"mode": mode}
    if mode == "flights":
        out["flights"] = [str(f) for f in (sel.get("flights") or [])]
    out["split"] = sel.get("split")
    return out


def _test_slices(sl) -> Optional[dict]:
    """A question's own slice set (Spec 16 §5): a notebook may ask a
    question of another preset than the study's ("is it absent in
    climb?"). Absent: the study's selection, rules and hand slices."""
    if not sl:
        return None
    if not isinstance(sl, dict):
        raise RuleError("a question's slices are {selection?, slice_rules?, hand_slices?}")
    out = {"selection": _selection(sl.get("selection")),
           "slice_rules": [normalise_rule(r) for r in (sl.get("slice_rules") or [])],
           "hand_slices": [normalise_hand_slice(h) for h in (sl.get("hand_slices") or [])]}
    if not out["slice_rules"] and not out["hand_slices"]:
        raise RuleError("a question's own slices need a slice rule or a hand slice")
    return out


def _test(t: dict) -> dict:
    if not isinstance(t, dict) or t.get("test_id") not in Q.QUESTIONS:
        raise RuleError(f"a test needs a test_id, one of {', '.join(Q.QUESTIONS)}; got {t!r}")
    out = {"test_id": t["test_id"], "version": Q.VERSIONS[t["test_id"]], "params": dict(t.get("params") or {}),
           "channels": list(t.get("channels") or [])}
    sl = _test_slices(t.get("slices"))
    if sl is not None:
        out["slices"] = sl
    if t.get("result") is not None:
        out["result"] = t["result"]
    if t.get("error"):
        out["error"] = str(t["error"])
    return out


def _channels_for(t: dict) -> tuple[list[str], str]:
    """Channels a test needs, and its coupling reference channel."""
    tid, chans = t["test_id"], list(t.get("channels") or [])
    if tid == "cycling":
        return (chans[:1] or ["rpm"]), "rpm"
    if tid == "coupling":
        chans = chans or ["rpm", "map_inhg"]
        return chans, chans[0]
    if tid == "groups":
        desc = t["params"].get("descriptor") or f"{(chans or ['rpm'])[0]}.swing"
        return [desc.split(".", 1)[0]], "rpm"
    return (chans or list(STANDARD_CHANNELS)), "rpm"
