"""
The v1 tests (Spec 06 §7.1–7.4), each returning the §8 result contract:

    {"test_id", "version", "question",
     "finding":   one sentence, with the recurrence count and the per-source split,
     "evidence":  {"chart": what to draw, "table": {"columns", "rows"}},
     "magnitude": [{label, value, unit, spread, references: [{kind, label, value, unit, source, text}], text}],
     "caveats":   [fixed items …, the test's "what this does not mean"],
     "block":     {test_id, version, params, slice_set, per_slice, summary, references, engine_version}}

Tests are pure functions of a built slice set (its descriptors and
context), parameters and references: no samples, no I/O.

No verdicts (D5): a magnitude is always shown beside a reference — the OM
value from the engine profile where one applies, the set's own spread,
and any reference the user typed into the study. The finding describes;
it never judges (acceptance 9, checked by render.verdict_words).
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from .. import __version__
from ..channels import CHANNEL_REGISTRY
from ..fleet import DA_BANDS, MIN_FLIGHTS_FOR_CONFIDENCE, OAT_BANDS
from .descriptors import PERIOD_FLOOR_S, _r
from .rules import RuleError

# Q10: the small-group caution reuses n_min (Spec 12 A4) — one constant.
N_MIN = MIN_FLIGHTS_FOR_CONFIDENCE
# §7.4: a slice "stands out" at a robust (modified) z of 3.5 or more — the
# Iglewicz–Hoaglin convention for outlier screening, a statistical
# convention stated on the card, not a judgement about the engine.
Z_STAND_OUT = 3.5
UNUSUAL_CAP = 10
UNUSUAL_DESCRIPTORS = ("median", "swing", "sd", "slope_per_min", "max_rate_per_s", "corr0")

QUESTIONS = {
    "cycling": "Is this signal steady, or is it cycling?",
    "coupling": "Do these two move together, and who leads?",
    "groups": "Are these two groups different?",
    "unusual": "Which of these slices is unusual?",
}
VERSIONS = {"cycling": 1, "coupling": 1, "groups": 1, "unusual": 1}

DOES_NOT_MEAN = {
    "cycling": "A repeating period describes the signal's shape; it does not say whether the engine or its "
               "controller is working as designed — compare it with the references shown.",
    "coupling": "A correlation says two channels move together; it does not say which one causes the other.",
    "groups": "A difference between groups goes with the split; it does not show that the split variable causes it.",
    "unusual": "This finds difference, not wrongness: when most slices share a pattern, the one that stands out "
               "may be the clean one. Scanning many descriptors guarantees some chance hits; the list is ranked, "
               "capped and never a defect list.",
}

DESCRIPTOR_LABELS = {
    "mean": "mean", "median": "level (median)", "min": "minimum", "max": "maximum", "at_anchor": "value at anchor",
    "sd": "standard deviation", "mad": "MAD", "iqr": "IQR", "swing": "swing (peak-to-peak)",
    "slope_per_min": "slope per minute", "max_rate_per_s": "max rate per second", "period_s": "period",
    "period_prominence": "period prominence", "corr0": "zero-lag correlation with the reference channel",
    "lag_s": "lag behind the reference channel", "corr_at_lag": "correlation at that lag",
}


# ── Formatting ─────────────────────────────────────────────────────────────

def label(ch: str) -> str:
    cdef = CHANNEL_REGISTRY.get(ch)
    return cdef.label if cdef else ch


def unit(ch: str) -> str:
    cdef = CHANNEL_REGISTRY.get(ch)
    return (cdef.unit or "") if cdef else ""


def fmt(v, ch: Optional[str] = None, nd: Optional[int] = None) -> str:
    """A number for a sentence, in the channel's terms: rpm to 10, others
    to sensible decimals, thousands separated."""
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    v = float(v)
    if nd is None and v.is_integer():
        nd = 0
    if nd is None:
        a = abs(v)
        nd = 0 if a >= 100 else 1 if a >= 10 else 2 if a >= 1 else 2
    s = f"{v:,.{nd}f}"
    return s


def with_unit(v, ch: str, nd: Optional[int] = None) -> str:
    u = unit(ch)
    return f"{fmt(v, ch, nd)} {u}".strip() if u else fmt(v, ch, nd)


def _q(values: list, qs=(25, 50, 75)) -> list:
    v = [x for x in values if x is not None and math.isfinite(x)]
    if not v:
        return [None] * len(qs)
    return [float(x) for x in np.percentile(v, qs)]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


# ── References (D5) ────────────────────────────────────────────────────────

def om_limits(engine_cfg: Optional[dict], channel: str) -> list[dict]:
    """The profile's OM limits on a channel (Spec 09 catalogue)."""
    if not engine_cfg:
        return []
    from ..limits import limit_catalog
    out = []
    for lim in limit_catalog(engine_cfg):
        if lim.get("param") == channel and lim.get("limit_value") is not None:
            out.append({"kind": "om", "id": lim["id"], "label": lim["label"], "value": lim["limit_value"],
                        "limit_type": lim["limit_type"], "unit": lim.get("unit") or unit(channel),
                        "source": (engine_cfg.get("_metadata") or {}).get("om_reference")})
    return out


def _set_reference(lo, hi, ch, what: str) -> dict:
    return {"kind": "set", "label": f"spread of {what} across the set (IQR)", "value": [_r(lo, 3), _r(hi, 3)],
            "unit": unit(ch), "text": f"set IQR {fmt(lo)}–{fmt(hi)}"}


def _user_ref_text(ref: dict, measure: Optional[float], ch: str) -> str:
    v = ref.get("value")
    src = f" ({ref['source']})" if ref.get("source") else ""
    if ref.get("ref_kind") == "band":
        width = 2 * float(v)
        return f"{ref['label']}: ±{fmt(v)} {unit(ch)} ({fmt(width)} {unit(ch)} wide){src}"
    return f"{ref['label']}: {fmt(v)} {unit(ch)}{src}".replace("  ", " ")


def _normalise_user_refs(references: list) -> list[dict]:
    out = []
    for r in references or []:
        if not isinstance(r, dict) or "label" not in r or "value" not in r:
            raise RuleError(f"a reference needs a label and a value, got {r!r}")
        rr = {"label": str(r["label"]), "value": r["value"], "channel": r.get("channel"),
              "ref_kind": r.get("kind", "value"), "source": r.get("source")}
        if r.get("test"):
            rr["test"] = r["test"]
        out.append(rr)
    return out


def _user_refs_for(references: list, channel: str, test_id: str, measure) -> list[dict]:
    out = []
    for r in references:
        if r.get("channel") not in (channel, None, ""):
            continue
        if r.get("test") not in (None, "", test_id):
            continue
        out.append({"kind": "user", "label": r["label"], "value": r["value"], "ref_kind": r["ref_kind"],
                    "unit": unit(channel), "source": r.get("source"), "text": _user_ref_text(r, measure, channel)})
    return out


# ── Common parts ───────────────────────────────────────────────────────────

def _sources(slices: list[dict]) -> list[str]:
    return sorted({s["context"].get("source") for s in slices if s["context"].get("source")})


def _context_columns() -> list[dict]:
    return [{"key": "start_time", "label": "Start (local)"}, {"key": "source", "label": "Source"},
            {"key": "duration_s", "label": "Duration", "unit": "s"}, {"key": "da_ft", "label": "DA", "unit": "ft"},
            {"key": "oat_c", "label": "OAT", "unit": "°C"}, {"key": "engine_hours", "label": "Engine hours", "unit": "h"},
            {"key": "phases", "label": "Phases"}]


def _row(s: dict) -> dict:
    c = s["context"]
    return {"slice_id": s["slice_id"], "flight": s["flight"], "label": s["label"], "start_time": c.get("start_time"),
            "source": c.get("source"), "duration_s": s["quality"].get("duration_s"), "da_ft": c.get("da_ft"),
            "oat_c": c.get("oat_c"), "engine_hours": c.get("engine_hours"), "phases": " → ".join(c.get("phases") or []),
            "filled_share": s["quality"].get("filled_share")}


def _fixed_caveats(test_id: str, slices: list[dict], channels: list[str], windows: dict) -> list[str]:
    out = []
    if test_id in ("cycling", "coupling", "unusual"):
        out.append(f"Logs are 1 Hz: periods below about {PERIOD_FLOOR_S:g} s are unreliable and faster "
                   "oscillations alias, so they are never counted as a prominent period.")
    srcs = _sources(slices)
    if len(srcs) > 1:
        out.append("The set mixes G3X and AXIS slices. The G3X records some channels damped (manifold pressure "
                   "ripple is smaller on G3X than on AXIS for the same oscillation), so results are given per "
                   "source and a damped channel is not pooled across sources without saying so.")
    axis = [s for s in slices if s["context"].get("source") == "AXIS"]
    filled = [s["quality"].get("filled_share") or 0 for s in axis]
    if filled and max(filled) > 0:
        out.append(f"AXIS frames are put on a 1-second grid; {fmt(100 * float(np.mean(filled)), nd=1)} % of AXIS "
                   "seconds were filled in and are excluded from period, rate and lag descriptors.")
    for ch in channels:
        w = windows.get(ch)
        if not w:
            continue
        basis = {"period": f"from the set's median period {fmt(w.get('median_period_s'), nd=1)} s",
                 "duration": f"from the median slice duration {fmt(w.get('median_duration_s'), nd=0)} s (no prominent period)",
                 "override": "set in the study"}[w["basis"]]
        floors = " (at the floors)" if w["window_s"] == 12 and w["lag_s"] == 10 else ""
        out.append(f"{label(ch)}: swing window {w['window_s']} s, lag range ±{w['lag_s']} s — {basis}{floors}.")
    return out


def _result(test_id: str, finding: str, chart: dict, columns: list[dict], rows: list[dict], magnitude: list[dict],
            caveats: list[str], params: dict, slice_set: dict, summary: dict, references: list[dict]) -> dict:
    return {
        "test_id": test_id, "version": VERSIONS[test_id], "question": QUESTIONS[test_id],
        "finding": finding,
        "evidence": {"chart": chart, "table": {"columns": columns, "rows": rows}},
        "magnitude": magnitude,
        "caveats": caveats + [DOES_NOT_MEAN[test_id]],
        "block": {
            "test_id": test_id, "version": VERSIONS[test_id], "params": params,
            "slice_set": {k: slice_set.get(k) for k in ("selection", "rules", "hand_slices", "count", "by_source",
                                                        "flights_selected", "missing_flights", "unreachable_flights")},
            "per_slice": rows, "summary": summary, "references": references, "engine_version": __version__,
        },
    }


def _need(slices: list[dict], ch: str) -> list[dict]:
    return [s for s in slices if ch in (s.get("descriptors") or {}) and s["descriptors"][ch].get("samples")]


# ── 7.1 Is this signal steady, or is it cycling? ──────────────────────────

def cycling(slice_set: dict, channel: str, params: dict, references: list, engine_cfg: Optional[dict]) -> dict:
    slices = _need(slice_set["slices"], channel)
    if not slices:
        raise RuleError(f"no slice in the set carries {label(channel)}")
    w = slice_set["windows"][channel]
    d = [s["descriptors"][channel] for s in slices]
    prom = [x for x in d if x.get("period_prominent")]
    p25, p50, p75 = _q([x["period_s"] for x in prom])
    s25, s50, s75 = _q([x.get("swing") for x in d])
    n, k = len(slices), len(prom)
    per_source = {}
    for src in _sources(slices):
        ss = [s["descriptors"][channel] for s in slices if s["context"].get("source") == src]
        pp = [x for x in ss if x.get("period_prominent")]
        per_source[src] = {"slices": len(ss), "prominent": len(pp), "median_period_s": _r(_q([x["period_s"] for x in pp])[1], 3),
                           "median_swing": _r(_q([x.get("swing") for x in ss])[1], 3)}
    split = (" (" + ", ".join(f"{src} {v['prominent']} of {v['slices']}" for src, v in per_source.items()) + ")"
             if len(per_source) > 1 else "")
    sw = f"swing {with_unit(s50, channel)} ({fmt(s25)}–{fmt(s75)})"
    if k:
        finding = (f"{label(channel)} cycles every {fmt(p50, nd=1)} s (IQR {fmt(p25, nd=1)}–{fmt(p75, nd=1)}), {sw}, "
                   f"in {k} of {_plural(n, 'slice')}{split}.")
    else:
        finding = (f"No repeating period stands out in {label(channel)}: 0 of {_plural(n, 'slice')} have a prominent "
                   f"period{split}; {sw}.")
    # References: OM limit (headroom from the swing's top), the set's spread, user references.
    tops = _q([x.get("max") for x in d])[1]
    bottoms = _q([x.get("min") for x in d])[1]
    om = []
    for lim in om_limits(engine_cfg, channel):
        edge = tops if lim["limit_type"] == "MAX" else bottoms
        if edge is None or lim["limit_type"] not in ("MAX", "MIN"):
            continue
        gap = edge - lim["value"]
        where = "at" if gap == 0 else ("above" if gap > 0 else "below")
        what = "top reaches" if lim["limit_type"] == "MAX" else "bottom is"
        lim = dict(lim, text=f"OM {lim['label']} {with_unit(lim['value'], channel)}: the median slice's {what} "
                             f"{with_unit(edge, channel)}" + ("" if gap == 0 else f", {with_unit(abs(gap), channel)}")
                             + f" {where} it")
        om.append(lim)
    # Only the limit nearest the slices' level is beside the swing.
    level = _q([x.get("median") for x in d])[1]
    if om and level is not None:
        om = [min(om, key=lambda l: abs(l["value"] - level))]
    users = _user_refs_for(references, channel, "cycling", s50)
    refs = om + [_set_reference(s25, s75, channel, "swing")] + users
    magnitude = [
        {"label": f"{label(channel)} swing (median of slices)", "value": _r(s50, 3), "unit": unit(channel),
         "spread": [_r(s25, 3), _r(s75, 3)], "references": refs,
         "text": f"{with_unit(s50, channel)} peak-to-peak over {w['window_s']} s windows"},
        {"label": f"{label(channel)} period (median of slices with a prominent period)", "value": _r(p50, 3), "unit": "s",
         "spread": [_r(p25, 3), _r(p75, 3)],
         "references": [{"kind": "set", "label": "recurrence", "value": [k, n],
                         "text": f"prominent in {k} of {n} slices (prominence ≥ {params['prominence_min']:g})"}],
         "text": (f"{fmt(p50, nd=1)} s" if k else "none prominent")},
    ]
    columns = _context_columns() + [
        {"key": "swing", "label": "Swing", "unit": unit(channel)}, {"key": "period_s", "label": "Period", "unit": "s"},
        {"key": "period_prominence", "label": "Prominence"}, {"key": "period_prominent", "label": "Prominent"},
        {"key": "median", "label": "Level", "unit": unit(channel)}, {"key": "max", "label": "Max", "unit": unit(channel)}]
    rows = [dict(_row(s), **{k2: s["descriptors"][channel].get(k2) for k2 in
                             ("swing", "period_s", "period_prominence", "period_prominent", "median", "max")})
            for s in slices]
    chart = {"kind": "aligned_slices", "channels": [channel], "anchor": params.get("anchor", "crossing"),
             "distribution": {"descriptor": "swing", "channel": channel}}
    summary = {"slices": n, "prominent": k, "period_s": [_r(p25, 3), _r(p50, 3), _r(p75, 3)],
               "swing": [_r(s25, 3), _r(s50, 3), _r(s75, 3)], "per_source": per_source}
    return _result("cycling", finding, chart, columns, rows, magnitude,
                   _fixed_caveats("cycling", slices, [channel], slice_set["windows"]),
                   {**params, "channel": channel, "windows": {channel: w}}, slice_set, summary, refs)


# ── 7.2 Do these two move together, and who leads? ───────────────────────

def coupling(slice_set: dict, channels: list[str], params: dict, references: list, engine_cfg: Optional[dict]) -> dict:
    if len(channels) < 2:
        raise RuleError("coupling needs a reference channel and at least one other")
    ref_ch, others = channels[0], channels[1:]
    if slice_set.get("reference") != ref_ch:
        raise RuleError(f"this slice set's coupling reference is {slice_set.get('reference')}; build it with "
                        f"reference {ref_ch}")
    slices = _need(slice_set["slices"], ref_ch)
    sentences, magnitude, summary, refs_all = [], [], {}, []
    rows = [_row(s) for s in slices]
    columns = _context_columns()
    srcs = _sources(slices)
    damping = []
    for ch in others:
        have = [s for s in slices if ch in s["descriptors"] and s["descriptors"][ch].get("corr0") is not None]
        if not have:
            sentences.append(f"{label(ch)} is not in these slices")
            continue
        per_source = {}
        for src in srcs or [None]:
            ss = [s["descriptors"][ch] for s in have if src is None or s["context"].get("source") == src]
            if not ss:
                continue
            c25, c50, c75 = _q([x["corr0"] for x in ss])
            lags = [x["lag_s"] for x in ss if x.get("lag_s") is not None]
            mode = max(set(lags), key=lambda v: (lags.count(v), -abs(v))) if lags else None
            per_source[src or "all"] = {"slices": len(ss), "corr0": [_r(c25), _r(c50), _r(c75)], "lag_mode_s": mode,
                                        "lag_mode_count": lags.count(mode) if lags else 0,
                                        "corr_at_lag": _r(_q([x["corr_at_lag"] for x in ss if x.get("lag_s") == mode])[1]),
                                        "swing": _r(_q([x.get("swing") for x in ss])[1], 3)}
        lags_all = [s["descriptors"][ch]["lag_s"] for s in have if s["descriptors"][ch].get("lag_s") is not None]
        mode = max(set(lags_all), key=lambda v: (lags_all.count(v), -abs(v))) if lags_all else None
        k = lags_all.count(mode) if lags_all else 0
        c_all = _q([s["descriptors"][ch]["corr0"] for s in have])[1]

        def when(m):
            return "with no delay" if m == 0 else (f"{m} s behind" if m and m > 0 else f"{-m} s ahead")

        if len(per_source) > 1:
            parts = [f"{when(v['lag_mode_s'])} on {src} slices (lag {v['lag_mode_s']} s in {v['lag_mode_count']} of "
                     f"{v['slices']}; median zero-lag correlation {v['corr0'][1]:.2f})" for src, v in per_source.items()]
            sentences.append(f"{label(ch)} follows {label(ref_ch)} " + " and ".join(parts))
        else:
            sentences.append(f"{label(ch)} follows {label(ref_ch)} {when(mode)} (lag {mode} s in {k} of {len(have)} "
                             f"slices; median zero-lag correlation {c_all:.2f})")
        # Damping: the same channel's swing differs by source.
        if len(per_source) > 1:
            sw = {src: v["swing"] for src, v in per_source.items() if v["swing"]}
            if len(sw) == 2 and max(sw.values()) > 1.5 * min(sw.values()):
                lo, hi = min(sw, key=sw.get), max(sw, key=sw.get)
                damping.append(f"{label(ch)} swings {with_unit(sw[lo], ch)} on {lo} slices against "
                               f"{with_unit(sw[hi], ch)} on {hi} slices: the {lo} record of this channel is damped, "
                               f"so its correlation with {label(ref_ch)} reads lower there — compare per source, not pooled.")
        for src, v in per_source.items():
            refs = [{"kind": "set", "label": f"spread of zero-lag correlation across the {src} slices (IQR)",
                     "value": [v["corr0"][0], v["corr0"][2]],
                     "text": f"{src} slices: IQR {v['corr0'][0]:.2f}–{v['corr0'][2]:.2f}"}]
            refs += _user_refs_for(references, ch, "coupling", v["corr0"][1])
            refs_all += refs
            on = f" — {src} slices" if len(per_source) > 1 else ""
            magnitude.append({"label": f"{label(ch)} vs {label(ref_ch)}: zero-lag correlation (median){on}",
                              "value": v["corr0"][1], "source": src, "slices": v["slices"],
                              "lag_mode_s": v["lag_mode_s"], "references": refs,
                              "text": f"median {v['corr0'][1]:.2f} over {v['slices']} slices; most common lag "
                                      f"{v['lag_mode_s']} s ({v['lag_mode_count']} slices)"})
        summary[ch] = {"per_source": per_source, "lag_mode_s": mode, "lag_mode_count": k, "slices": len(have),
                       "corr0_median": _r(c_all)}
        for row, s in zip(rows, slices):
            dd = s["descriptors"].get(ch) or {}
            row.update({f"{ch}.corr0": dd.get("corr0"), f"{ch}.lag_s": dd.get("lag_s"), f"{ch}.corr_at_lag": dd.get("corr_at_lag")})
        columns += [{"key": f"{ch}.corr0", "label": f"{label(ch)} corr (lag 0)"},
                    {"key": f"{ch}.lag_s", "label": f"{label(ch)} lag", "unit": "s"},
                    {"key": f"{ch}.corr_at_lag", "label": f"{label(ch)} corr at lag"}]
    finding = "; ".join(sentences) + f" — over {_plural(len(slices), 'slice')}."
    caveats = _fixed_caveats("coupling", slices, [ref_ch], slice_set["windows"]) + damping
    chart = {"kind": "multi_channel_stack", "channels": [ref_ch] + others, "anchor": params.get("anchor", "crossing"),
             "scatter": {"x": f"{others[0]}.corr0", "group_by": "source"}}
    return _result("coupling", finding, chart, columns, rows, magnitude, caveats,
                   {**params, "channels": channels, "windows": {ref_ch: slice_set["windows"][ref_ch]}},
                   slice_set, summary, refs_all)


# ── 7.3 Are these two groups different? ───────────────────────────────────

def _cliffs_delta(a: list, b: list) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    gt = (a[:, None] > b[None, :]).sum()
    lt = (a[:, None] < b[None, :]).sum()
    return float(gt - lt) / (len(a) * len(b))


def _mann_whitney_p(a: list, b: list) -> Optional[float]:
    """Two-sided Mann–Whitney U, normal approximation with tie correction
    and continuity correction — support for the effect size, never the
    headline."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    n1, n2 = len(a), len(b)
    if n1 == 0 or n2 == 0:
        return None
    allv = np.concatenate([a, b])
    order = allv.argsort(kind="mergesort")
    ranks = np.empty(len(allv))
    sv = allv[order]
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    u1 = ranks[:n1].sum() - n1 * (n1 + 1) / 2
    mu = n1 * n2 / 2
    _, counts = np.unique(allv, return_counts=True)
    n = n1 + n2
    tie = (counts ** 3 - counts).sum() / (n * (n - 1)) if n > 1 else 0
    sigma = math.sqrt(n1 * n2 / 12 * ((n + 1) - tie))
    if sigma == 0:
        return 1.0
    z = (abs(u1 - mu) - 0.5) / sigma
    return float(math.erfc(max(z, 0) / math.sqrt(2)))


def _band_groups(values: list, edges: list, unit_txt: str, what: str) -> list[tuple[str, callable]]:
    edges = sorted(float(e) for e in edges)
    out = []
    lo = None
    for e in edges + [None]:
        if lo is None and e is not None:
            out.append((f"below {fmt(e, nd=0)} {unit_txt} {what}".strip(), (lambda x, e=e: x < e)))
        elif e is None:
            out.append((f"at {fmt(lo, nd=0)} {unit_txt} {what} and above".strip(), (lambda x, lo=lo: x >= lo)))
        else:
            out.append((f"at {fmt(lo, nd=0)}–{fmt(e, nd=0)} {unit_txt} {what}".strip(), (lambda x, lo=lo, e=e: lo <= x < e)))
        lo = e
    return out


def _split(slices: list[dict], split: dict) -> list[tuple[str, list[dict]]]:
    by = (split or {}).get("by")
    if by in ("da_band", "oat_band", "engine_hours"):
        key = {"da_band": "da_ft", "oat_band": "oat_c", "engine_hours": "engine_hours"}[by]
        default = [b[1] for b in (DA_BANDS if by == "da_band" else OAT_BANDS)[:-1]] if by != "engine_hours" else None
        edges = split.get("edges") or default
        if not edges:
            raise RuleError(f"split by {by} needs edges")
        u, what = {"da_band": ("ft", "DA"), "oat_band": ("°C", "OAT"), "engine_hours": ("h", "engine hours")}[by]
        groups = _band_groups([s["context"].get(key) for s in slices], edges, u, what)
        return [(name, [s for s in slices if s["context"].get(key) is not None and f(s["context"][key])])
                for name, f in groups]
    if by == "source":
        return [(src, [s for s in slices if s["context"].get("source") == src]) for src in _sources(slices)]
    if by == "date":
        date = str(split.get("date") or "")
        if not date:
            raise RuleError("split by date needs a date (YYYY-MM-DD)")
        key = lambda s: (s["context"].get("start_time") or "")[:10]
        return [(f"before {date}", [s for s in slices if key(s) < date]),
                (f"on or after {date}", [s for s in slices if key(s) >= date])]
    if by == "rule":
        ids = list(dict.fromkeys(s.get("rule_id") or "hand" for s in slices))
        return [(i, [s for s in slices if (s.get("rule_id") or "hand") == i]) for i in ids]
    if by == "flights":
        groups = split.get("groups") or []
        if len(groups) < 2:
            raise RuleError("split by flights needs two groups of flights")
        return [(str(g.get("label") or f"group {i + 1}"), [s for s in slices if s["flight"] in set(g.get("flights") or [])])
                for i, g in enumerate(groups)]
    raise RuleError("groups needs a split: by da_band, oat_band, engine_hours, source, date, rule or flights")


def groups(slice_set: dict, descriptor: str, params: dict, references: list, engine_cfg: Optional[dict]) -> dict:
    if "." not in descriptor:
        raise RuleError("descriptor is channel.name, e.g. rpm.swing")
    ch, name = descriptor.split(".", 1)
    slices = [s for s in _need(slice_set["slices"], ch) if s["descriptors"][ch].get(name) is not None]
    split = params.get("split") or slice_set.get("selection", {}).get("split")
    parts = [(g, ss) for g, ss in _split(slices, split) if ss]
    if len(parts) < 2:
        raise RuleError("the split leaves fewer than two non-empty groups")
    vals = {g: [float(s["descriptors"][ch][name]) for s in ss] for g, ss in parts}
    ref_group = max(vals, key=lambda g: len(vals[g]))
    what = f"{label(ch)} {DESCRIPTOR_LABELS.get(name, name)}"
    u = "s" if name in ("period_s", "lag_s") else ("" if name in ("corr0", "corr_at_lag", "period_prominence") else unit(ch))
    stats, pieces, magnitude, small = {}, [], [], []
    for g, v in vals.items():
        q = _q(v)
        st = {"n": len(v), "median": _r(q[1], 3), "iqr": [_r(q[0], 3), _r(q[2], 3)], "small_group": len(v) < N_MIN}
        if g != ref_group:
            st.update({"vs": ref_group, "median_difference": _r(q[1] - _q(vals[ref_group])[1], 3),
                       "cliffs_delta": _r(_cliffs_delta(v, vals[ref_group]), 3),
                       "mann_whitney_p": _r(_mann_whitney_p(v, vals[ref_group]), 4)})
        stats[g] = st
        note = " — small group" if st["small_group"] else ""
        if st["small_group"]:
            small.append(g)
        pieces.append(f"{fmt(q[1])} {u} {g} ({_plural(len(v), 'slice')}{note})".replace("  ", " "))
    finding = f"{what[0].upper() + what[1:]} is " + (", ".join(pieces[:-1]) + " and " + pieces[-1] if len(pieces) > 1 else pieces[0]) + "."
    for g, st in stats.items():
        if g == ref_group:
            continue
        refs = [{"kind": "set", "label": f"the {ref_group} group", "value": stats[ref_group]["median"],
                 "text": f"{ref_group}: median {fmt(stats[ref_group]['median'])} {u} (IQR {fmt(stats[ref_group]['iqr'][0])}–{fmt(stats[ref_group]['iqr'][1])}, {stats[ref_group]['n']} slices)"}]
        refs += _user_refs_for(references, ch, "groups", st["median"])
        magnitude.append({"label": f"{g} vs {ref_group}: median difference", "value": st["median_difference"], "unit": u,
                          "cliffs_delta": st["cliffs_delta"], "mann_whitney_p": st["mann_whitney_p"], "references": refs,
                          "text": f"{fmt(st['median_difference'])} {u}; Cliff's delta {st['cliffs_delta']:+.2f} "
                                  f"(rank test p = {st['mann_whitney_p']:.3g}, support only)".replace("  ", " ")})
    caveats = _fixed_caveats("groups", slices, [ch], {})
    if small:
        caveats.append(f"Small group{'s' if len(small) > 1 else ''} ({', '.join(small)}): fewer than {N_MIN} slices "
                       "(n_min) — a median from so few slices moves with each one, so read the difference as a lead, "
                       "not a measurement.")
    rows = []
    group_of = {s["slice_id"]: g for g, ss in parts for s in ss}
    for s in slices:
        if s["slice_id"] in group_of:
            rows.append(dict(_row(s), group=group_of[s["slice_id"]], **{name: s["descriptors"][ch][name]}))
    columns = _context_columns() + [{"key": "group", "label": "Group"}, {"key": name, "label": what, "unit": u}]
    chart = {"kind": "distributions", "descriptor": descriptor, "group_by": "group"}
    return _result("groups", finding, chart, columns, rows, magnitude, caveats,
                   {**params, "descriptor": descriptor, "split": split, "n_min": N_MIN},
                   slice_set, {"groups": stats, "reference_group": ref_group}, [r for m in magnitude for r in m["references"]])


# ── 7.4 Which of these slices is unusual? ─────────────────────────────────

def _robust_z(values: list[Optional[float]]) -> list[Optional[float]]:
    v = np.array([np.nan if x is None else float(x) for x in values])
    fin = np.isfinite(v)
    if fin.sum() < 5:
        return [None] * len(values)
    med = float(np.median(v[fin]))
    scale = 1.4826 * float(np.median(np.abs(v[fin] - med)))
    if scale == 0:
        # Iglewicz–Hoaglin: with MAD 0 (most values equal), the mean
        # absolute deviation stands in.
        scale = 1.253314 * float(np.mean(np.abs(v[fin] - med)))
    if scale == 0:
        return [None] * len(values)
    return [None if not f else float((x - med) / scale) for x, f in zip(v, fin)]


def unusual(slice_set: dict, channels: list[str], params: dict, references: list, engine_cfg: Optional[dict]) -> dict:
    slices = slice_set["slices"]
    channels = [c for c in channels if any(c in (s.get("descriptors") or {}) for s in slices)]
    n = len(slices)
    if n < 5:
        raise RuleError("unusual needs at least 5 slices to compare")
    z_min = float(params.get("z_min", Z_STAND_OUT))
    cap = int(params.get("cap", UNUSUAL_CAP))
    names = list(params.get("descriptors") or UNUSUAL_DESCRIPTORS)
    bad = [x for x in names if x not in DESCRIPTOR_LABELS]
    if bad:
        raise RuleError(f"unknown descriptor(s) {', '.join(bad)}")
    # Robust z within each source when every source has at least n_min
    # slices (a damped channel is never pooled across sources, §5.6).
    srcs = _sources(slices)
    by_source = len(srcs) > 1 and all(sum(1 for s in slices if s["context"].get("source") == src) >= N_MIN for src in srcs)
    groups_ = {src: [i for i, s in enumerate(slices) if s["context"].get("source") == src] for src in srcs} if by_source \
        else {"all": list(range(n))}
    z = [dict() for _ in slices]
    medians: dict = {}
    for gname, idx in groups_.items():
        for ch in channels:
            for name in names:
                if name == "corr0" and ch == slice_set.get("reference"):
                    continue
                vals = [(slices[i].get("descriptors") or {}).get(ch, {}).get(name) for i in idx]
                zs = _robust_z(vals)
                fin = [x for x in vals if x is not None]
                medians[(gname, ch, name)] = float(np.median(fin)) if fin else None
                for i, zz in zip(idx, zs):
                    if zz is not None:
                        z[i][f"{ch}.{name}"] = zz
    ranked = []
    for i, s in enumerate(slices):
        if not z[i]:
            continue
        key = max(z[i], key=lambda k: abs(z[i][k]))
        ranked.append((abs(z[i][key]), i, key))
    ranked.sort(key=lambda t: (-t[0], slices[t[1]]["context"].get("start_time") or ""))
    standing = [t for t in ranked if t[0] >= z_min]
    listed = standing[:cap]
    gname = lambda s: s["context"].get("source") if by_source else "all"

    def describe(t) -> str:
        zabs, i, key = t
        s = slices[i]
        ch, name = key.split(".", 1)
        v = s["descriptors"][ch][name]
        med = medians[(gname(s), ch, name)]
        side = "below" if v < med else "above"
        uu = "" if name in ("corr0",) else unit(ch)
        return (f"{(s['context'].get('start_time') or '')[:16]} — {label(ch)} {DESCRIPTOR_LABELS.get(name, name)} "
                f"{fmt(v)} {uu} {side} the rest ({fmt(med)} {uu})").replace("  ", " ").replace(" )", ")")

    if listed:
        finding = (f"{len(standing)} of {_plural(n, 'slice')} stand out (robust z ≥ {z_min:g})"
                   + (f"; the first {cap} are listed" if len(standing) > cap else "") + ": "
                   + "; ".join(describe(t) for t in listed) + ".")
    else:
        finding = f"None of {_plural(n, 'slice')} stand out: no descriptor reaches a robust z of {z_min:g}."
    rows = []
    for rank, (zabs, i, key) in enumerate(ranked, start=1):
        s = slices[i]
        ch, name = key.split(".", 1)
        rows.append(dict(_row(s), rank=rank, stands_out=zabs >= z_min, max_abs_z=_r(zabs, 2), descriptor=key,
                         value=s["descriptors"][ch][name], set_median=_r(medians[(gname(s), ch, name)], 3)))
    columns = _context_columns() + [{"key": "rank", "label": "Rank"}, {"key": "max_abs_z", "label": "Largest |z|"},
                                    {"key": "descriptor", "label": "Descriptor"}, {"key": "value", "label": "Value"},
                                    {"key": "set_median", "label": "Set median"}]
    magnitude = [{"label": "Largest robust z among listed slices", "value": _r(listed[0][0], 2) if listed else None,
                  "references": [{"kind": "set", "label": "the set's own median and MAD per descriptor",
                                  "text": f"robust z = (value − set median) / (1.4826 × MAD, or 1.2533 × mean "
                                          f"absolute deviation when MAD is 0); listed at |z| ≥ {z_min:g}"
                                          + (", within each source" if by_source else "")}],
                  "text": f"{len(standing)} of {n} slices at |z| ≥ {z_min:g}"}]
    caveats = _fixed_caveats("unusual", slices, [], {})
    caveats.append(f"{len(channels) * len(names)} descriptors scanned per slice "
                   f"({', '.join(label(c) for c in channels)}); |z| ≥ {z_min:g} is the Iglewicz–Hoaglin screening "
                   "convention, not a limit.")
    if len(srcs) > 1 and not by_source:
        caveats.append(f"Sources pooled: a source has fewer than {N_MIN} slices, so slices are compared across "
                       "sources; a channel the G3X damps can make AXIS slices stand out.")
    chart = {"kind": "ranked", "descriptor_column": "descriptor", "highlight": [slices[t[1]]["slice_id"] for t in listed]}
    summary = {"slices": n, "stand_out": len(standing), "listed": [slices[t[1]]["slice_id"] for t in listed],
               "z_min": z_min, "by_source": by_source}
    return _result("unusual", finding, chart, columns, rows, magnitude, caveats,
                   {**params, "channels": channels, "descriptors": names, "z_min": z_min, "cap": cap,
                    "windows": {c: slice_set["windows"][c] for c in channels if c in slice_set["windows"]}},
                   slice_set, summary, magnitude[0]["references"])


def run(test_id: str, slice_set: dict, *, channels: Optional[list] = None, params: Optional[dict] = None,
        references: Optional[list] = None, engine_cfg: Optional[dict] = None) -> dict:
    """Dispatch one test on a built slice set (`SliceSet.to_dict()`)."""
    params = dict(params or {})
    refs = _normalise_user_refs(references)
    params.setdefault("prominence_min", params.get("prominence_min", 0.2))
    if test_id == "cycling":
        ch = (channels or ["rpm"])[0]
        return cycling(slice_set, ch, params, refs, engine_cfg)
    if test_id == "coupling":
        return coupling(slice_set, channels or ["rpm", "map_inhg"], params, refs, engine_cfg)
    if test_id == "groups":
        desc = params.get("descriptor") or (f"{(channels or ['rpm'])[0]}.swing")
        return groups(slice_set, desc, params, refs, engine_cfg)
    if test_id == "unusual":
        from .descriptors import STANDARD_CHANNELS
        return unusual(slice_set, channels or list(STANDARD_CHANNELS), params, refs, engine_cfg)
    raise RuleError(f"unknown test {test_id!r}; one of {', '.join(QUESTIONS)}")
