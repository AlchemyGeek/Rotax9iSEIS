"""
Compare (Spec 06 §9.2, D11–D12): the same analysis per flight over a
selection — one row per slice, grouped by flight.

Rows are read straight from a slice set's descriptors (the dict
``build_slices`` returns), never recomputed, so a Compare row and the
per-slice table of a question are the same numbers (acceptance 16).
Grouping collapses a flight's slices to one row: the median of each value
and the slice count. A pinned row (a slice, or a flight when collapsed)
turns every row's values into differences from it as well.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from . import descriptors as D
from . import questions as Q
from .rules import RuleError

# The analysis values of §9.2, per channel. corr0 and lag_s are the
# channel's coupling with the reference channel (absent on the reference).
VALUES = ("period_s", "period_prominence", "period_prominent", "swing", "median", "corr0", "lag_s")
DELTAS = ("period_s", "swing", "median", "corr0")
CONDITIONS = ("source", "da_ft", "oat_c", "pa_ft", "engine_hours", "phases")
CHART_X = ("date", "engine_hours", "da_ft", "oat_c")


def _row(s: dict, channels: list[str]) -> dict:
    c = s.get("context") or {}
    vals = {}
    for ch in channels:
        d = (s.get("descriptors") or {}).get(ch)
        if d is not None:
            vals[ch] = {k: d.get(k) for k in VALUES if k in d}
    return {
        "row_id": s["slice_id"], "slice_id": s["slice_id"], "flight": s["flight"], "kind": s.get("kind"),
        "label": s.get("label"), "start_s": s["start_s"], "end_s": s["end_s"],
        "start_time": c.get("start_time"), "date": c.get("date"), "duration_s": s["end_s"] - s["start_s"],
        **{k: c.get(k) for k in CONDITIONS}, "values": vals,
    }


def _median(xs: list) -> Optional[float]:
    v = [float(x) for x in xs if x is not None and not isinstance(x, bool)]
    return D._r(float(np.median(v)), 4) if v else None


def _collapse(flight: str, rows: list[dict], channels: list[str]) -> dict:
    """A flight's slices as one row: medians of every value, the slice
    count; the prominent flag becomes the count of slices with one."""
    first = rows[0]
    vals = {}
    for ch in channels:
        have = [r["values"][ch] for r in rows if ch in r["values"]]
        if not have:
            continue
        v = {k: _median([h.get(k) for h in have]) for k in VALUES if k not in ("period_prominent", "lag_s")}
        v["period_prominent"] = sum(1 for h in have if h.get("period_prominent"))
        lags = [h.get("lag_s") for h in have if h.get("lag_s") is not None]
        if lags:
            v["lag_s"] = int(round(float(np.median(lags))))
        vals[ch] = {k: x for k, x in v.items() if x is not None}
    return {
        "row_id": flight, "slice_id": None, "flight": flight, "kind": "flight", "label": f"{len(rows)} slices",
        "start_s": first["start_s"], "end_s": rows[-1]["end_s"], "start_time": first["start_time"], "date": first["date"],
        "duration_s": _median([r["duration_s"] for r in rows]), "count": len(rows),
        "source": first["source"], "da_ft": _median([r["da_ft"] for r in rows]), "oat_c": _median([r["oat_c"] for r in rows]),
        "pa_ft": _median([r["pa_ft"] for r in rows]), "engine_hours": first["engine_hours"],
        "phases": first["phases"], "values": vals,
    }


def _deltas(row: dict, pin: dict) -> dict:
    out = {}
    for ch, v in row["values"].items():
        p = pin["values"].get(ch)
        if not p:
            continue
        d = {}
        for k in DELTAS:
            if v.get(k) is not None and p.get(k) is not None:
                d[k] = D._r(float(v[k]) - float(p[k]), 4)
        if v.get("lag_s") is not None and p.get("lag_s") is not None:
            d["lag_s"] = int(v["lag_s"]) - int(p["lag_s"])
        out[ch] = d
    return out


def compare_rows(slice_set: dict, *, channels: Optional[list] = None, pinned: Optional[str] = None,
                 collapse: bool = False, flights: Optional[dict] = None,
                 engine_cfg: Optional[dict] = None) -> dict:
    """§9.2 / §11 `compare_rows` over a built slice set. `flights` maps the
    selection's flight ids to {date, start_time, source} so flights without
    a matching slice can be listed. `pinned` names a row: a slice id, or a
    flight id (the flight's first slice, or its collapsed row)."""
    channels = list(channels or slice_set.get("channels") or [])
    rows = [_row(s, channels) for s in slice_set["slices"]]
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["flight"], []).append(r)
    group_list = [{"flight": f, "date": rs[0]["date"], "start_time": rs[0]["start_time"], "source": rs[0]["source"],
                   "count": len(rs), "row_ids": [r["row_id"] for r in rs], "summary": _collapse(f, rs, channels)}
                  for f, rs in groups.items()]
    shown = [g["summary"] for g in group_list] if collapse else rows

    pin = None
    if pinned:
        pin = next((r for r in shown if r["row_id"] == pinned), None)
        if pin is None and not collapse:
            # A flight id pins that flight's first slice; a slice id while collapsed pins its flight.
            pin = next((r for r in rows if r["flight"] == pinned), None)
        if pin is None and collapse:
            owner = next((r["flight"] for r in rows if r["row_id"] == pinned), None)
            pin = next((g["summary"] for g in group_list if g["flight"] == owner), None)
        if pin is None:
            raise RuleError(f"no row {pinned!r} in this comparison")
    out_rows = []
    for r in shown:
        rr = dict(r)
        if pin is not None:
            rr["pinned"] = r["row_id"] == pin["row_id"]
            rr["delta"] = _deltas(r, pin)
        out_rows.append(rr)

    without = []
    for fid, meta in (flights or {}).items():
        if fid not in groups:
            without.append({"flight": fid, **{k: (meta or {}).get(k) for k in ("date", "start_utc")}})
    without.sort(key=lambda w: (w.get("start_utc") or "", w["flight"]))
    return {
        "rows": out_rows, "groups": group_list, "collapsed": bool(collapse),
        "row_count": len(out_rows), "slice_count": len(rows), "flight_count": len(group_list),
        "flights_without": without, "pinned": pin["row_id"] if pin else None,
        "channels": channels, "reference": slice_set.get("reference"), "windows": slice_set.get("windows"),
        "chart_x": list(CHART_X), "values": list(VALUES), "deltas": list(DELTAS),
        "om_limits": {ch: Q.om_limits(engine_cfg, ch) for ch in channels},
        "rules": slice_set.get("rules"), "hand_slices": slice_set.get("hand_slices"),
        "by_source": slice_set.get("by_source"), "missing_flights": slice_set.get("missing_flights"),
        "unreachable_flights": slice_set.get("unreachable_flights"),
        "engine_version": slice_set.get("engine_version"),
    }


def rows_csv(result: dict) -> str:
    """The rows as CSV (§8 Evidence): conditions, then each channel's values
    and, when a row is pinned, its differences."""
    import csv
    import io
    chans = result["channels"]
    head = ["flight", "start_time", "duration_s", "count"] + list(CONDITIONS)
    for ch in chans:
        head += [f"{ch}.{k}" for k in VALUES]
    if result.get("pinned"):
        head += ["pinned"] + [f"{ch}.delta_{k}" for ch in chans for k in DELTAS + ("lag_s",)]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(head)
    for r in result["rows"]:
        line = [r["flight"], r.get("start_time"), r.get("duration_s"), r.get("count", 1)]
        line += ["; ".join(map(str, r[k])) if isinstance(r.get(k), list) else r.get(k) for k in CONDITIONS]
        for ch in chans:
            v = r["values"].get(ch) or {}
            line += [v.get(k) for k in VALUES]
        if result.get("pinned"):
            line += [bool(r.get("pinned"))]
            for ch in chans:
                d = (r.get("delta") or {}).get(ch) or {}
                line += [d.get(k) for k in DELTAS + ("lag_s",)]
        w.writerow(["" if x is None else x for x in line])
    return buf.getvalue()
