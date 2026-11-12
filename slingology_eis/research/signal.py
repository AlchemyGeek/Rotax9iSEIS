"""
Signal view (Spec 06 §9.1, D9–D10): one flight, one or more channels.

**Strips.** Over the whole flight, two rolling strips per channel — swing
and dominant period with its prominence — on a sliding window. The value
at second *i* is the descriptor a slice of that window would carry
(§6, D10): the window is ``[a, a + W)`` with ``a = i − W // 2`` clamped to
the flight, and its swing and period come from the same
``descriptors.swing`` and ``descriptors.dominant_period`` that
``build_slices`` uses. A hand slice over the same seconds therefore
carries the same numbers.

``W`` is sized by §7.0 from the flight's own dominant period: the strips
are computed first at the §7.0 floor, the flight's period is the median
of the periods where the strip is lit (prominent), and the window is
``max(floor, ⌈2.5 P⌉)`` — recomputed at that width when it differs from
the floor. With no lit second the floor stands. (The duration fallback of
§7.0 has no meaning over a whole flight: there is no slice duration.)

**Window.** For a chosen window, the diagnostics behind the numbers: the
detrended trace, the autocorrelation with the detected period marked, the
periodogram with its peak, and for each channel beside the reference the
correlation against lag with the best lag; the window's §6 descriptors
with its resolved §7.0 windows, exactly as a hand slice over the window
would get them; and a **derived rule** (*Make this a rule*): the reference
channel's level band over the window and half its duration, an ordinary
§5.1 rule, so Compare finds the matching window in other flights (D11).

The log is read through the workspace's ``LogSource`` — a resumable
coroutine with one file outstanding (Spec 04 D11).
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .. import workspace as ws
from ..loader import load_log_bytes
from . import descriptors as D
from . import questions as Q
from .rules import RuleError, describe_rule, normalise_rule
from .slices import CONTEXT_CHANNELS, _context, _grid, flight_log_bytes

DERIVED_MERGE_GAP_S = 3          # as the full-power preset: a one-second dip doesn't split the window
DERIVED_MIN_DURATION_FRACTION = 0.5   # half the window: a shorter instance of the same manoeuvre still matches
DEFAULT_CHANNELS = ("rpm", "map_inhg")


def _window_bounds(i: int, w: int, n: int) -> tuple[int, int]:
    a = max(0, min(i - w // 2, n - w))
    return a, min(n, a + w)


def strips(y: np.ndarray, filled: np.ndarray, w: int, prominence_min: float = D.PROMINENCE_MIN) -> dict:
    """The two rolling strips of one channel at window `w`: per second,
    swing, period, prominence and whether the period is prominent. Seconds
    whose window holds fewer than two readings carry None."""
    n = len(y)
    swing, period, prom, lit = [None] * n, [None] * n, [None] * n, [False] * n
    if n == 0:
        return {"swing": swing, "period_s": period, "prominence": prom, "prominent": lit}
    w = min(int(w), n)
    fin = np.isfinite(y)
    cache: dict[int, tuple] = {}          # one computation per distinct window start
    for i in range(n):
        a, b = _window_bounds(i, w, n)
        got = cache.get(a)
        if got is None:
            seg, f = y[a:b], filled[a:b]
            if fin[a:b].sum() < 2:
                got = (None, None, None, False)
            else:
                p = D.dominant_period(seg, f, prominence_min)
                got = (D._r(D.swing(seg, w), 3), p["period_s"], p["period_prominence"], p["period_prominent"])
            cache = {a: got}
        swing[i], period[i], prom[i], lit[i] = got
    return {"swing": swing, "period_s": period, "prominence": prom, "prominent": lit}


def strip_window(lit_periods: list[float]) -> dict:
    """§7.0 for the strips: from the flight's own period where the floor
    strips light up, floors otherwise."""
    if lit_periods:
        p = float(np.median(lit_periods))
        return {"window_s": int(max(D.WINDOW_FLOOR_S, math.ceil(D.WINDOW_PERIODS * p))), "basis": "period",
                "flight_period_s": D._r(p, 3)}
    return {"window_s": D.WINDOW_FLOOR_S, "basis": "floor", "flight_period_s": None}


def _quantum(v: np.ndarray) -> float:
    """The channel's reading step (rpm 10, a temperature 1), for rounding a
    derived band outward; 0.1 when the readings aren't on a coarse grid."""
    u = np.unique(v[np.isfinite(v)])
    if len(u) < 2:
        return 1.0
    d = np.diff(u)
    step = float(d[d > 0].min())
    return step if step >= 1 else 0.1


def derive_rule(channel: str, y: np.ndarray, filled: np.ndarray, start_s: int, end_s: int, flight_id: str,
                when: Optional[str] = None, quantum: Optional[float] = None) -> dict:
    """*Make this a rule* (§9.1): the channel's level band over the window —
    from its lowest reading to its highest plus half the window's range,
    rounded outward to the reading step — held for at least half the
    window. The lower edge is what separates the manoeuvre from what
    surrounds it; the upper edge leaves room for other flights' peaks."""
    v = y[np.isfinite(y) & ~filled]
    if len(v) < 2:
        raise RuleError(f"the window holds no {Q.label(channel)} readings to derive a rule from")
    q = quantum or _quantum(v)
    lo, hi = float(v.min()), float(v.max())
    lo_r = math.floor(lo / q) * q
    hi_r = math.ceil((hi + (hi - lo) / 2) / q) * q
    nd = 0 if q >= 1 else 1
    duration = int(end_s - start_s)
    rule = normalise_rule({
        "name": f"{Q.label(channel)} {Q.fmt(round(lo_r, nd))}–{Q.fmt(round(hi_r, nd))}" + (f", like {when}" if when else ""),
        "conditions": [{"channel": channel, "op": "between", "min": round(lo_r, nd), "max": round(hi_r, nd)}],
        "min_duration_s": max(1, int(round(DERIVED_MIN_DURATION_FRACTION * duration))),
        "merge_gap_s": DERIVED_MERGE_GAP_S,
    })
    rule = normalise_rule({**rule, "derived_from": {"flight": flight_id, "start_s": int(start_s), "end_s": int(end_s),
                                                    "channel": channel}})
    return {**rule, "description": describe_rule(rule)}


def _diagnostics(y: np.ndarray, filled: np.ndarray, p1: dict) -> dict:
    """The curves behind one channel's period: detrended trace, ACF and
    periodogram over the same lags `dominant_period` searches."""
    yy = np.array(y, dtype=float)
    yy[filled] = np.nan
    n = len(yy)
    yd = D.detrend(yy)
    max_lag = int(n * D.PERIOD_MAX_FRACTION)
    out = {"detrended": [D._r(v, 3) for v in yd], "acf": [], "periodogram": {"period_s": [], "power": []},
           "period_s": p1.get("period_s"), "period_ls_s": p1.get("period_ls_s")}
    if max_lag >= D.PERIOD_SEARCH_MIN_S + 1 and np.isfinite(yd).sum() >= 8:
        out["acf"] = [D._r(v) for v in D._acf(yd, max_lag + 1)]
        periods, power = D.lomb_scargle(yd, float(D.PERIOD_SEARCH_MIN_S), float(max_lag))
        if periods is not None:
            order = np.argsort(periods)
            out["periodogram"] = {"period_s": [D._r(v, 3) for v in periods[order]],
                                  "power": [D._r(v) for v in power[order]]}
    return out


def _numbers(ch: str, d: dict, references: list, engine_cfg: Optional[dict]) -> list[dict]:
    """§8 Magnitude for one flight's window: each number beside the OM
    limit nearest its level and the user's references (no threshold)."""
    out = []
    level = d.get("median")
    om = []
    for lim in Q.om_limits(engine_cfg, ch):
        if lim["limit_type"] not in ("MAX", "MIN"):
            continue
        edge = d.get("max") if lim["limit_type"] == "MAX" else d.get("min")
        if edge is None:
            continue
        gap = edge - lim["value"]
        where = "at" if gap == 0 else ("above" if gap > 0 else "below")
        what = "top reaches" if lim["limit_type"] == "MAX" else "bottom is"
        om.append(dict(lim, text=f"OM {lim['label']} {Q.with_unit(lim['value'], ch)}: the window's {what} "
                                 f"{Q.with_unit(edge, ch)}" + ("" if gap == 0 else f", {Q.with_unit(abs(gap), ch)}")
                                 + f" {where} it"))
    if om and level is not None:
        om = [min(om, key=lambda l: abs(l["value"] - level))]
    users = Q._user_refs_for(Q._normalise_user_refs(references), ch, "cycling", d.get("swing"))
    out.append({"label": f"{Q.label(ch)} swing", "value": d.get("swing"), "unit": Q.unit(ch),
                "references": om + users, "text": f"{Q.with_unit(d.get('swing'), ch)} peak-to-peak"})
    prom = d.get("period_prominent")
    out.append({"label": f"{Q.label(ch)} period", "value": d.get("period_s"), "unit": "s",
                "references": [{"kind": "threshold", "label": "prominence", "value": d.get("period_prominence"),
                                "text": f"prominence {Q.fmt(d.get('period_prominence'), nd=2)} "
                                        f"({'at or above' if prom else 'below'} the {D.PROMINENCE_MIN:g} the questions use)"}],
                "text": f"{Q.fmt(d.get('period_s'), nd=1)} s" if d.get("period_s") is not None else "no period found"})
    out.append({"label": f"{Q.label(ch)} level", "value": level, "unit": Q.unit(ch), "references": om,
                "text": f"median {Q.with_unit(level, ch)}"})
    if d.get("corr0") is not None:
        out.append({"label": f"{Q.label(ch)} with the reference", "value": d.get("corr0"), "unit": "",
                    "references": [], "text": f"correlation {Q.fmt(d['corr0'], nd=2)} at zero lag; best match at "
                                              f"{d.get('lag_s'):+d} s ({Q.fmt(d.get('corr_at_lag'), nd=2)})"
                    if d.get("lag_s") is not None else f"correlation {Q.fmt(d['corr0'], nd=2)} at zero lag"})
    return out


async def analyze_signal(ws_dir: Path, sources, flight_id: str, *, channels: Optional[list] = None,
                         window: Optional[dict] = None, reference: Optional[str] = None,
                         rule_channel: Optional[str] = None, windows: Optional[dict] = None,
                         prominence_min: float = D.PROMINENCE_MIN, references: Optional[list] = None,
                         engine_cfg: Optional[dict] = None, assignments: Optional[dict] = None,
                         include_values: bool = True,
                         on_progress: Optional[Callable[[dict], None]] = None) -> dict:
    """§9.1 / §11 `analyze_signal`."""
    fa = ws.load_flight_analysis(ws_dir, flight_id)
    if fa is None:
        raise RuleError(f"no flight {flight_id} in this workspace")
    channels = list(dict.fromkeys(channels or DEFAULT_CHANNELS))
    reference = reference or ("rpm" if "rpm" in channels else channels[0])
    if reference not in channels:
        channels.insert(0, reference)
    if on_progress:
        on_progress({"phase": "reading", "done": 0, "total": 1})
    found = await flight_log_bytes(ws_dir, flight_id, sources)
    if found is None:
        raise RuleError("this flight's log can't be read now (its folder is unreachable)")
    content, filename = found
    df, info = load_log_bytes(content, filename, channel_assignments=assignments or {})
    n, values, filled, row_of = _grid(df, set(channels) | set(CONTEXT_CHANNELS))
    present = [c for c in channels if c in values]
    absent = [c for c in channels if c not in values]
    if not present:
        raise RuleError("none of these channels is in this flight's log: " + ", ".join(Q.label(c) for c in channels))

    out_strips, strip_windows = {}, {}
    for k, ch in enumerate(present):
        if on_progress:
            on_progress({"phase": "strips", "done": k, "total": len(present)})
        st = strips(values[ch], filled, D.WINDOW_FLOOR_S, prominence_min)
        sw = strip_window([p for p, lit in zip(st["period_s"], st["prominent"]) if lit and p])
        if sw["window_s"] != D.WINDOW_FLOOR_S:
            st = strips(values[ch], filled, sw["window_s"], prominence_min)
        lit = sum(1 for x in st["prominent"] if x)
        strip_windows[ch] = {**sw, "lit_seconds": lit, "lit_share": D._r(lit / n if n else 0.0, 3)}
        out_strips[ch] = st

    context = _context(fa, info, df, values, row_of, 0, n, fa.phases)
    result = {
        "flight_id": flight_id, "duration_s": n, "source": context.get("source"),
        "start_time": context.get("start_time"), "date": context.get("date"),
        "channels": present, "missing_channels": absent, "reference": reference if reference in values else None,
        "phases": [{"phase": p["phase"], "start_s": p["start_s"], "end_s": p["end_s"]} for p in fa.phases],
        "filled": [int(i) for i in np.flatnonzero(filled)],
        "strip_windows": strip_windows, "strips": out_strips,
        "prominence_min": prominence_min,
        "om_limits": {ch: Q.om_limits(engine_cfg, ch) for ch in present},
        "window": None,
    }
    if include_values:
        result["values"] = {ch: [D._r(v, 3) for v in values[ch]] for ch in present}

    if window:
        a = max(0, int(math.floor(float(window.get("start_s", 0)))))
        b = min(n, int(math.ceil(float(window.get("end_s", n)))))
        if b - a < 2:
            raise RuleError(f"the window {a}–{b} s holds fewer than two seconds of this flight")
        f = filled[a:b]
        ref_y = values[reference][a:b] if reference in values else None
        per_ch, desc, diag, resolved = {}, {}, {}, {}
        for ch in present:
            y = values[ch][a:b]
            p1 = D.dominant_period(y, f, prominence_min)
            resolved[ch] = D.resolve_window([p1], [b - a], (windows or {}).get(ch))
            w = resolved[ch]
            # As build_slices does for a hand slice over these seconds: anchor at its start,
            # coupling against the reference for every other channel.
            desc[ch] = D.describe_channel(y, f, 0, w["window_s"], ref=ref_y if ch != reference else None,
                                          lag_s=w["lag_s"], prominence_min=prominence_min)
            diag[ch] = _diagnostics(y, f, p1)
            if ref_y is not None and ch != reference:
                diag[ch]["lag_curve"] = D.lag_curve(ref_y, y, w["lag_s"], f)
                diag[ch]["best_lag_s"] = desc[ch].get("lag_s")
            per_ch[ch] = _numbers(ch, desc[ch], references or [], engine_cfg)
        rc = rule_channel or (reference if reference in values else present[0])
        when = f"{context.get('date')} {Q.fmt(a)}–{Q.fmt(b)} s" if context.get("date") else None
        rule = derive_rule(rc, values[rc][a:b], f, a, b, flight_id, when=when)
        result["window"] = {
            "start_s": a, "end_s": b, "duration_s": b - a,
            "context": _context(fa, info, df, values, row_of, a, b, fa.phases),
            "descriptors": desc, "windows": resolved, "diagnostics": diag, "numbers": per_ch,
            "derived_rule": rule,
        }
    if on_progress:
        on_progress({"phase": "done", "done": 1, "total": 1})
    return result
