"""
filters.py — limit filters (Spec 09 §6.3, §7, §8.1).

A filter is the pilot's statement about one OM limit: "on my aircraft,
this limit is exceeded in a way I understand and accept." It tolerates
events by magnitude (how far past the limit) and/or by duration (how long
each event lasted); an event needs only one reason to be tolerated
(§4, either-filter). Tolerated events are suppressed, not deleted.

Pure, like operations.py: filters arrive as plain dicts (the
workspace's filters.json entries, §9), limits as catalogue entries
(limits.limit_catalog / FlightAnalysis.limits), baselines as a
FleetAnalysis. The host owns storage.
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from .contract import Diagnostic

# §13 constants — initial placeholders, to be tuned on the full log set.
N_MIN = 10                    # z reference and band comparison (shared with baseline_deviation)
REFERENCE_N = 20              # reference flights chosen at creation / re-baseline
REFERENCE_MIN_N = 5           # below this the filter is Collecting
Z_STD_FLOOR_FRACTION = 0.05   # z std floor: 5% of the limit value...
Z_STD_FLOOR_MIN = 0.1         # ...but at least 0.1 engine units
DEFAULT_REVIEW_INTERVAL_H = {"CAUTION": 50, "WARNING": 25}

MAGNITUDE_MODES = ("absolute", "percent", "z")
OVERBOOST_PARAM = "overboost_max_block_s"


def is_overboost(limit: dict) -> bool:
    return limit.get("param") == OVERBOOST_PARAM


# ── Policy (§6.3) ───────────────────────────────────────────────────────────


def resolve_filter_policy(limit: dict) -> dict:
    """
    The effective filter policy for a catalogue entry (§6.3). A WARNING
    limit — an OM red line, overboost included (§6.4) — is filterable like
    any other, but always requires a note: a consistent exceedance can be a
    real mechanical issue, or it can be an artifact of a miscalibrated
    sensor or other systemic quirk that isn't itself a WARNING-worthy
    condition — the note is the pilot's record of which, and why, since the
    engine can't tell the two apart on its own. A limit is only ever
    non-filterable when its profile says so explicitly (`filter_policy`
    `filterable: false`, with a pilot-facing `reason`) — e.g. oil_press_min,
    where any reading is a direct lubrication signal to check at the
    source, never one to annotate away. A limit may also declare optional
    caps (`max_band_abs`, `max_duration_s`).

    Returns {filterable, reason, severity, magnitude_modes,
    duration_allowed, max_band_abs, max_duration_s, note_required,
    review_interval_h}; `reason` explains a non-filterable limit.
    """
    raw = limit.get("filter_policy") or {}
    severity = limit.get("severity", "CAUTION")
    duration_allowed = not is_overboost(limit)

    filterable, reason = True, None
    if raw.get("filterable") is False:
        # The profile says why, in words for the pilot (`reason`).
        filterable = False
        reason = raw.get("reason") or "The engine profile marks this limit as one that can't be filtered."
    return {
        "filterable": filterable,
        "reason": reason,
        "severity": severity,
        "magnitude_modes": list(MAGNITUDE_MODES),
        "duration_allowed": duration_allowed,
        "max_band_abs": raw.get("max_band_abs"),
        "max_duration_s": raw.get("max_duration_s") if duration_allowed else None,
        "note_required": bool(raw.get("note_required", severity == "WARNING")),
        "review_interval_h": raw.get("review_interval_h", DEFAULT_REVIEW_INTERVAL_H.get(severity, 50)),
    }


# ── Frozen baseline (§4, §8.1) ──────────────────────────────────────────────

def limit_metric_key(limit: dict, kind: str) -> str:
    """Fleet metric key of a limit's §5 metric: kind is "peak_excess",
    "time_above_pct" or (overboost) "block_s"."""
    return f"limit_{limit['id']}_{kind}"


def _magnitude_metric(limit: dict) -> str:
    return limit_metric_key(limit, "block_s" if is_overboost(limit) else "peak_excess")


def _stats(values: list[float]) -> dict:
    """mean/std/n with the same sample std fleet.baseline() uses."""
    from .fleet import baseline

    if not values:
        return {"n": 0, "mean": None, "std": None, "min": None, "max": None}
    b = baseline(pd.DataFrame({"v": values}), "v")
    return {"n": b.n, "mean": b.mean, "std": b.std, "min": b.min, "max": b.max}


def frozen_baseline(fleet, metric_key: str, reference_ids: list[str]) -> dict:
    """
    §4: the baseline of `metric_key` over a fixed set of flights, from the
    fleet's current points — so it follows re-analysis, and a reference
    flight later excluded from baselines (absent from the fleet's points)
    drops out. Returns {n, mean, std, min, max, by_band: {band: stats}}.
    """
    ref = set(reference_ids)
    points = [p for p in (fleet.metrics.get(metric_key) or {}).get("points", [])
              if p["flight_id"] in ref and p.get("value") is not None]
    out = _stats([p["value"] for p in points])
    bands: dict[str, list[float]] = {}
    for p in points:
        if p.get("band") is not None:
            bands.setdefault(p["band"], []).append(p["value"])
    out["by_band"] = {b: _stats(v) for b, v in sorted(bands.items())}
    return out


def comparison_set(frozen: dict, band: Optional[str], n_min: int = N_MIN) -> tuple[dict, dict]:
    """
    Spec 01 R8, shared with baseline_deviation: the flight's own band if
    the reference has at least n_min points in it, else the unstratified
    frozen baseline. Returns (stats, {"scope", "band", "n"}).
    """
    if band is not None:
        b = frozen.get("by_band", {}).get(band)
        if b and b["n"] >= n_min:
            return b, {"scope": "band", "band": band, "n": b["n"]}
    return frozen, {"scope": "all", "band": None, "n": frozen["n"]}


def z_std_floor(limit: dict) -> float:
    return max(abs(limit["limit_value"]) * Z_STD_FLOOR_FRACTION, Z_STD_FLOOR_MIN)


def flight_band(fa, limit: dict) -> Optional[str]:
    kind = limit.get("stratify_by")
    return fa.metrics.get(kind, {}).get("value") if kind else None


def select_reference(fleet, limit: dict, reference_n: int = REFERENCE_N) -> list[str]:
    """
    §8.1: the reference_n most recent included flights, chronologically —
    taken from the limit's time-above metric (every flight with the
    limit's channel has a point) or, for overboost, its block metric.
    """
    from .operations import _chronological

    key = limit_metric_key(limit, "block_s" if is_overboost(limit) else "time_above_pct")
    points = (fleet.metrics.get(key) or {}).get("points", [])
    seq = _chronological([p for p in points if p.get("value") is not None])
    return [p["flight_id"] for p in seq[-reference_n:]]


# ── Validation (§7.3) ───────────────────────────────────────────────────────

def resolved_band(filter_: dict, limit: dict, frozen: Optional[dict] = None) -> Optional[float]:
    """
    The magnitude condition's band in engine units: absolute as stored,
    percent of |limit|, and for z the excess at `value` std devs above the
    frozen reference mean (unstratified; per-flight z uses the band rule).
    None without a magnitude condition, or for z without a reference.
    """
    m = filter_.get("magnitude")
    if not m:
        return None
    if m["mode"] == "absolute":
        return float(m["value"])
    if m["mode"] == "percent":
        return abs(limit["limit_value"]) * float(m["value"]) / 100.0
    if m["mode"] == "z" and frozen and frozen.get("mean") is not None:
        return frozen["mean"] + float(m["value"]) * max(frozen["std"] or 0.0, z_std_floor(limit))
    return None


def _diag(code: str, message: str, filter_: dict, **refs) -> dict:
    return Diagnostic(code=code, severity="warn", scope="fleet", message=message,
                      refs={"filter_id": filter_.get("id"), "limit_id": filter_.get("limit_id"), **refs}).to_dict()


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def validate_filter(filter_: dict, limits_by_id: dict, fleet=None) -> list[dict]:
    """
    §7.3, enforced in the engine, not only the UI: returns diagnostics;
    empty means the filter is valid and applies. `limits_by_id` is the
    catalogue by id; `fleet` is needed only to check a z reference's n.
    """
    lid = filter_.get("limit_id")
    limit = limits_by_id.get(lid)
    if limit is None:
        return [_diag("FILTER_UNKNOWN_LIMIT", f"Filter for {lid!r}: no such limit in this engine profile.", filter_)]
    policy = resolve_filter_policy(limit)
    label = limit["label"]
    if not policy["filterable"]:
        return [_diag("FILTER_NOT_ALLOWED", f"{label}: {policy['reason']}", filter_)]

    diags = []
    magnitude, duration = filter_.get("magnitude"), filter_.get("duration")
    if not magnitude and not duration:
        diags.append(_diag("FILTER_NOT_ALLOWED", f"{label}: a filter needs a magnitude or a duration condition.", filter_))
    if magnitude:
        mode, value = magnitude.get("mode"), magnitude.get("value")
        if mode not in policy["magnitude_modes"]:
            diags.append(_diag("FILTER_NOT_ALLOWED", f"{label}: magnitude mode {mode!r} is not allowed for this limit.", filter_))
        elif not _number(value) or value <= 0:
            diags.append(_diag("FILTER_NOT_ALLOWED", f"{label}: the magnitude value must be a positive number.", filter_))
        elif policy["max_band_abs"] is not None and mode in ("absolute", "percent"):
            band = resolved_band(filter_, limit)
            if band > policy["max_band_abs"] + 1e-9:
                diags.append(_diag("FILTER_NOT_ALLOWED",
                                   f"{label}: band {band:g} {limit['unit']} exceeds the cap of "
                                   f"{policy['max_band_abs']:g} {limit['unit']}.", filter_))
        if mode == "z" and not diags:
            if fleet is None:
                diags.append(_diag("FILTER_REFERENCE_LOW_N", f"{label}: z mode needs the fleet baselines to check its reference.", filter_))
            else:
                ref_ids = (filter_.get("reference") or {}).get("flight_ids", [])
                n = frozen_baseline(fleet, _magnitude_metric(limit), ref_ids)["n"]
                if n < N_MIN:
                    diags.append(_diag("FILTER_REFERENCE_LOW_N",
                                       f"{label}: z reference has {n} flights with events, below {N_MIN}.", filter_, n=n))
    if duration:
        max_event_s = duration.get("max_event_s")
        if not policy["duration_allowed"]:
            diags.append(_diag("FILTER_NOT_ALLOWED", f"{label}: this limit has no duration condition.", filter_))
        elif not _number(max_event_s) or max_event_s <= 0:
            diags.append(_diag("FILTER_NOT_ALLOWED", f"{label}: max event duration must be a positive number.", filter_))
        elif policy["max_duration_s"] is not None and max_event_s > policy["max_duration_s"]:
            diags.append(_diag("FILTER_NOT_ALLOWED",
                               f"{label}: max event duration {max_event_s:g} s exceeds the cap of "
                               f"{policy['max_duration_s']:g} s.", filter_))
    if policy["note_required"] and not (filter_.get("note") or "").strip():
        diags.append(_diag("FILTER_NOTE_REQUIRED", f"{label}: a note is required to filter this limit.", filter_))
    return diags


def active_filters(filters: list[dict], limits_by_id: dict, fleet=None) -> tuple[dict[str, dict], list[dict]]:
    """
    ({limit_id: valid filter}, diagnostics). With several filters on one
    limit only the newest counts (FILTER_MULTIPLE_FOR_LIMIT); an invalid
    filter is ignored — the limit reports unfiltered — with its
    diagnostics.
    """
    diags: list[dict] = []
    by_limit: dict[str, list[dict]] = {}
    for f in filters or []:
        by_limit.setdefault(f.get("limit_id"), []).append(f)
    out: dict[str, dict] = {}
    for lid, fs in by_limit.items():
        fs = sorted(fs, key=lambda f: f.get("updated_at") or f.get("created_at") or "")
        for older in fs[:-1]:
            diags.append(_diag("FILTER_MULTIPLE_FOR_LIMIT",
                               f"More than one filter for {lid!r}; only the newest applies.", older))
        newest = fs[-1]
        problems = validate_filter(newest, limits_by_id, fleet)
        if problems:
            diags.extend(problems)
        else:
            out[lid] = newest
    return out, diags


# ── Suppression (§4, §7) ────────────────────────────────────────────────────

def classify_event(event: dict, filter_: dict, limit: dict, z_ref: Optional[dict] = None) -> Optional[str]:
    """
    "magnitude" or "duration" if the filter tolerates this event (magnitude
    checked first), None if it's a breach. `z_ref` is the comparison-set
    stats (comparison_set) for a z filter.
    """
    excess = event.get("excess")
    m = filter_.get("magnitude")
    if m and excess is not None:
        if m["mode"] == "z":
            if z_ref and z_ref.get("mean") is not None:
                std = max(z_ref.get("std") or 0.0, z_std_floor(limit))
                if (excess - z_ref["mean"]) / std <= m["value"]:
                    return "magnitude"
        elif excess <= resolved_band(filter_, limit) + 1e-9:
            return "magnitude"
    d = filter_.get("duration")
    if d and event["duration_s"] <= d["max_event_s"]:
        return "duration"
    return None


def band_text(filter_: dict, limit: dict, frozen: Optional[dict] = None) -> str:
    """Short human summary of a filter's conditions, in engine units:
    "up to +2.5 psi", "events up to 10 s", or both joined by "or"."""
    parts = []
    m = filter_.get("magnitude")
    if m:
        band = resolved_band(filter_, limit, frozen)
        unit = limit.get("unit", "")
        side = "-" if limit.get("limit_type") == "MIN" else "+"
        if m["mode"] == "z":
            parts.append(f"up to z {m['value']:g}" + (f" (≈ {side}{band:.1f} {unit})" if band is not None else ""))
        elif m["mode"] == "percent":
            parts.append(f"up to {side}{band:.1f} {unit} ({m['value']:g}%)")
        else:
            parts.append(f"up to {side}{band:g} {unit}")
    d = filter_.get("duration")
    if d:
        parts.append(f"events up to {d['max_event_s']:g} s")
    return " or ".join(parts)


# ── Operations (§11.2) ──────────────────────────────────────────────────────

def _catalog_by_id(engine_config: dict) -> dict:
    from .limits import limit_catalog
    return {lim["id"]: lim for lim in limit_catalog(engine_config)}


def validate_limit_filter(filter_: dict, engine_config: dict, fleet=None) -> list[dict]:
    """§11.2 `validate_limit_filter`: diagnostics for one filter; empty =
    valid. The host calls it before saving; evaluate_insights applies the
    same checks to every filter it's given."""
    return validate_filter(filter_, _catalog_by_id(engine_config), fleet)


def _round_up(x: float) -> float:
    """A readable band just above x: 1 decimal below 10, whole units below
    100, else the next multiple of 5."""
    if x <= 0:
        return 0.0
    if x < 10:
        return math.ceil(x * 10 - 1e-9) / 10
    if x < 100:
        return float(math.ceil(x - 1e-9))
    return float(math.ceil(x / 5 - 1e-9) * 5)


def propose_limit_filter(flight_analyses: list, fleet, limit_id: str, engine_config: dict) -> dict:
    """
    §11.2 `propose_limit_filter`: a pre-filled draft for the filter
    editor — the limit and its policy (allowed modes, caps, whether a note
    is required), the live baseline of this limit's metrics, a suggested
    absolute band (the aircraft's worst excess so far, rounded up, within
    any cap), the proposed reference flights and whether z is available.
    """
    limits = _catalog_by_id(engine_config)
    limit = limits.get(limit_id)
    if limit is None:
        raise ValueError(f"unknown limit {limit_id!r}")
    policy = resolve_filter_policy(limit)
    mag_key = _magnitude_metric(limit)
    live_mag = (fleet.metrics.get(mag_key) or {}).get("baseline") or {"n": 0}
    live = {"magnitude_metric": mag_key, "magnitude": live_mag}
    if not is_overboost(limit):
        pct = fleet.metrics.get(limit_metric_key(limit, "time_above_pct")) or {}
        pct_points = [p for p in pct.get("points", []) if p.get("value") is not None]
        live["time_above_pct"] = pct.get("baseline") or {"n": 0}
        live["share_with_events"] = (sum(1 for p in pct_points if p["value"] > 0) / len(pct_points)
                                     if pct_points else None)

    worst = live_mag.get("max")
    if is_overboost(limit) and worst is not None:
        worst = worst - limit["limit_value"]
    suggested_band = _round_up(worst) if worst is not None and worst > 0 else None
    if suggested_band is not None and policy["max_band_abs"] is not None:
        suggested_band = min(suggested_band, policy["max_band_abs"])

    reference_ids = select_reference(fleet, limit)
    frozen = frozen_baseline(fleet, mag_key, reference_ids)
    return {
        "limit": limit,
        "policy": policy,
        "live": live,
        "suggested": {"magnitude": {"mode": "absolute", "value": suggested_band}} if suggested_band else {},
        "reference": {"flight_ids": reference_ids, "n_with_events": frozen["n"],
                      "collecting": len(reference_ids) < REFERENCE_MIN_N},
        "z_available": "z" in policy["magnitude_modes"] and frozen["n"] >= N_MIN,
        "z_n_min": N_MIN,
    }


def preview_limit_filter(flight_analyses: list, fleet, rules: dict, filters: list[dict], draft: dict) -> dict:
    """
    §11.2 `preview_limit_filter`: re-run evaluate_insights over every
    included flight with the current filters and with the draft in place
    of any existing filter on the same limit, and diff — events newly
    hidden, breaches left, topic threshold insights removed. Same
    before/after idea as the rule playground (Spec 03 §5.5).
    """
    from .operations import evaluate_insights

    included_ids = set(fleet.flight_ids)
    included = [fa for fa in flight_analyses if fa.flight_id in included_ids]
    limit_id = draft.get("limit_id")
    candidate = [f for f in filters if f.get("limit_id") != limit_id and f.get("id") != draft.get("id")]
    draft = {**draft, "id": draft.get("id") or "draft"}
    candidate.append(draft)
    limits = {lim["id"]: lim for fa in included[:1] for lim in fa.limits}
    diagnostics = validate_filter(draft, limits, fleet) if limits else []

    def _limit_counts(iset) -> tuple[int, int, int]:
        """(events, suppressed, breaches) for limit_id on one flight."""
        topic = next((t for t in iset.topics if t["topic_id"] == "limit_exceedances"), {"insights": []})
        evs = [e for i in topic["insights"] if i.get("limit_id") == limit_id for e in i.get("events", [])]
        suppressed = sum(1 for e in evs if e["suppressed_by"])
        breaches = sum(len(i.get("events", [])) for i in topic["insights"]
                       if i.get("limit_id") == limit_id and (i.get("filter") or {}).get("outcome") == "breach")
        return len(evs), suppressed, breaches

    def _topic_ids(iset) -> dict:
        return {i["id"]: i for t in iset.topics if t["topic_id"] != "limit_exceedances" for i in t["insights"]}

    flights, hidden, total_events = [], 0, 0
    for fa in included:
        before = evaluate_insights(fa, fleet, rules, filters=filters)
        after = evaluate_insights(fa, fleet, rules, filters=candidate)
        n, sup_before, _ = _limit_counts(before)
        _, sup_after, breaches = _limit_counts(after)
        if n == 0 and not _topic_ids(before).keys() - _topic_ids(after).keys():
            continue
        b_ids, a_ids = _topic_ids(before), _topic_ids(after)
        removed = [{"id": i, "topic_id": b_ids[i]["topic_id"], "text": b_ids[i]["message"]["text"]}
                   for i in b_ids.keys() - a_ids.keys()]
        total_events += n
        hidden += max(0, sup_after - sup_before)
        flights.append({
            "flight_id": fa.flight_id, "date": fa.header.get("date"),
            "events": n, "suppressed": sup_after, "newly_suppressed": max(0, sup_after - sup_before),
            "breaches": breaches, "topic_insights_removed": removed,
        })
    flights.sort(key=lambda f: f["date"] or "")
    return {
        "limit_id": limit_id,
        "valid": not diagnostics,
        "diagnostics": diagnostics,
        "flights_considered": len(included),
        "events_total": total_events,
        "events_hidden": hidden,
        "flights_affected": sum(1 for f in flights if f["newly_suppressed"] or f["topic_insights_removed"]),
        "flights_with_breach": sum(1 for f in flights if f["breaches"]),
        "flights": flights,
    }


# ── Change monitor (§8) ─────────────────────────────────────────────────────

FREQUENCY_WINDOW = 10         # monitored flights for the event-frequency test
FREQUENCY_DELTA = 0.30        # rise in share of flights with events that counts as drift
QUIET_WINDOW = 10             # monitored flights without events -> Quiet
DRIFT_PERSISTENCE = 2         # consecutive monitored flights (Spec 08 cylinder_rank pattern)
# Not in §13: a floor for time_above_pct's reference std. A limit rarely
# exceeded in its reference has a near-zero std there, and any event at
# all would otherwise read as drift. In percentage points.
TIME_ABOVE_STD_FLOOR = 1.0

STATUS_ORDER = ("breached", "drifting", "review_due", "quiet", "collecting", "stable")


def _point_index(fleet, key: str) -> dict[str, dict]:
    return {p["flight_id"]: p for p in (fleet.metrics.get(key) or {}).get("points", [])}


def effective_reference(filter_: dict, chronology: list[dict], min_n: int = REFERENCE_MIN_N) -> tuple[list[str], bool]:
    """
    §8.1: the stored reference flights still included, extended forward
    over the next included flights until it reaches min_n. Returns
    (flight ids, collecting) — collecting while even that falls short.
    `chronology` is every included flight with the limit's channel,
    oldest first ({"flight_id", ...}).
    """
    stored = set((filter_.get("reference") or {}).get("flight_ids", []))
    order = [p["flight_id"] for p in chronology]
    ref = [fid for fid in order if fid in stored]
    if len(ref) < min_n:
        last = max((order.index(fid) for fid in ref), default=-1)
        for fid in order[last + 1:]:
            if len(ref) >= min_n:
                break
            ref.append(fid)
    return ref, len(ref) < min_n


# Pilot wording for weather bands (fleet.py's OAT_BANDS / DA_BANDS names).
_OAT_BAND_WORDS = {"cold": "cold days", "mild": "mild days", "warm": "warm days", "hot": "hot days"}
_DA_BAND_WORDS = {"low": "low density altitude", "moderate": "moderate density altitude",
                  "high": "high density altitude", "very_high": "very high density altitude"}


def comparison_phrase(comparison: dict, kind: Optional[str]) -> str:
    """What a flight was compared with, for a pilot: "your reference flights
    on cold days (12 flights)" when it compared within its weather band, else
    "all your reference flights (20 flights)"."""
    n = comparison.get("n", 0)
    if comparison.get("scope") == "band" and comparison.get("band"):
        band = comparison["band"]
        words = (_OAT_BAND_WORDS if kind == "oat_band" else _DA_BAND_WORDS).get(band, band.replace("_", " "))
        where = f"on {words}" if kind == "oat_band" else f"at {words}"
        return f"your reference flights {where} ({n} flights)"
    return f"all your reference flights ({n} flights)"


def _fmt_value(v: float, digits: int = 1) -> str:
    return f"{v:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{v:.0f}"


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _z(value: Optional[float], stats: dict, floor: float) -> Optional[float]:
    if value is None or stats.get("mean") is None:
        return None
    return (value - stats["mean"]) / max(stats.get("std") or 0.0, floor)


def evaluate_filter_health(flight_analyses: list, fleet, filters: list[dict], engine_config: Optional[dict] = None) -> list[dict]:
    """
    §11.2 `evaluate_filter_health`: one FilterHealth (§11.3) per filter.
    Stateless: frozen and live baselines come from `fleet` (its points
    already omit excluded flights, and its provenance carries the
    baseline_config, so the drift threshold is the metric's own
    outlier_z_threshold — §8.2's "one threshold"); breaches come from the
    flights' events. `engine_config` resolves limits; without it, the
    flights' own limit catalogue is used.
    """
    from .operations import _chronological, resolve_outlier_z_threshold

    if engine_config is not None:
        limits = _catalog_by_id(engine_config)
    else:
        limits = {lim["id"]: lim for fa in flight_analyses[:1] for lim in fa.limits}
    baseline_config = fleet.provenance.get("baseline_config") or {}
    included = set(fleet.flight_ids)
    fas = {fa.flight_id: fa for fa in flight_analyses if fa.flight_id in included}
    latest_hours = max((h for fa in fas.values()
                        for h in [fa.header.get("engine_hours_end") or fa.header.get("engine_hours_start")]
                        if h is not None), default=None)
    valid, _ = active_filters(filters, limits, fleet)

    out = []
    for f in filters:
        lid = f.get("limit_id")
        limit = limits.get(lid)
        diags = validate_filter(f, limits, fleet) if limit else validate_filter(f, limits)
        is_valid = limit is not None and valid.get(lid) is f
        health = {"filter_id": f.get("id"), "limit_id": lid, "valid": is_valid, "status": "stable",
                  "reasons": [], "diagnostics": diags, "series": [], "hours_since_review": None}
        if limit is None:
            health["reasons"].append("The limit no longer exists in this engine profile.")
            out.append(health)
            continue

        ob = is_overboost(limit)
        mag_key = _magnitude_metric(limit)
        pct_key = None if ob else limit_metric_key(limit, "time_above_pct")
        mag_pts = _point_index(fleet, mag_key)
        pct_pts = _point_index(fleet, pct_key) if pct_key else {}
        # Every included flight with the limit's channel, oldest first.
        chronology = _chronological(list((pct_pts or mag_pts).values()))
        ref_ids, collecting = effective_reference(f, chronology)
        ref_set = set(ref_ids)

        frozen_mag = frozen_baseline(fleet, mag_key, ref_ids)
        frozen_pct = frozen_baseline(fleet, pct_key, ref_ids) if pct_key else None
        ref_pct_values = [pct_pts[fid]["value"] for fid in ref_ids if fid in pct_pts]
        if ob:
            ref_block = [mag_pts[fid]["value"] for fid in ref_ids if fid in mag_pts]
            share_ref = (sum(1 for v in ref_block if v > limit["limit_value"]) / len(ref_block)) if ref_block else None
        else:
            share_ref = (sum(1 for v in ref_pct_values if v > 0) / len(ref_pct_values)) if ref_pct_values else None
        health["frozen_baseline"] = {
            ("block_s" if ob else "peak_excess"): {k: v for k, v in frozen_mag.items()},
            **({"time_above_pct": frozen_pct} if frozen_pct else {}),
            "share_with_events": share_ref,
        }
        health["reference"] = {"flight_ids": ref_ids, "collecting": collecting}
        health["resolved_band"] = ({"value": resolved_band(f, limit, frozen_mag), "unit": limit["unit"]}
                                   if f.get("magnitude") else None)
        health["summary"] = band_text(f, limit, frozen_mag)

        # Per-flight series, with this filter's classification of each event.
        last_ref_pos = max((i for i, p in enumerate(chronology) if p["flight_id"] in ref_set), default=-1)
        series = []
        for i, p in enumerate(chronology):
            fid = p["flight_id"]
            fa = fas.get(fid)
            band = flight_band(fa, limit) if fa else p.get("band")
            events = suppressed = breaches = 0
            if fa is not None:
                evs = [e for e in fa.exceedances if e.get("limit_id") == lid]
                if ob:
                    block = fa.metrics.get("overboost_max_block_s", {}).get("value")
                    if block is not None and block > limit["limit_value"]:
                        events = 1
                        band_s = resolved_band(f, limit, frozen_mag) or 0.0
                        if is_valid and block <= limit["limit_value"] + band_s:
                            suppressed = 1
                        else:
                            breaches = 1
                else:
                    z_ref = comparison_set(frozen_mag, band)[0] if (f.get("magnitude") or {}).get("mode") == "z" else None
                    for e in evs:
                        events += 1
                        if is_valid and classify_event(e, f, limit, z_ref):
                            suppressed += 1
                        else:
                            breaches += 1
            series.append({
                "flight_id": fid, "date": p.get("date"), "engine_hours": p.get("x"), "band": band,
                "in_reference": fid in ref_set, "monitored": i > last_ref_pos,
                ("block_s" if ob else "peak_excess"): (mag_pts.get(fid) or {}).get("value"),
                **({"time_above_pct": (pct_pts.get(fid) or {}).get("value")} if pct_key else {}),
                "events": events, "suppressed": suppressed, "breaches": breaches,
            })
        health["series"] = series
        monitored = [s for s in series if s["monitored"]]

        # Hours since review (or creation).
        since = f.get("reviewed_engine_hours") or f.get("created_engine_hours")
        if since is None and ref_ids:
            since = next((s["engine_hours"] for s in reversed(series) if s["in_reference"]), None)
        health["hours_since_review"] = (round(latest_hours - since, 1)
                                        if latest_hours is not None and since is not None else None)

        reasons: dict[str, list[str]] = {k: [] for k in STATUS_ORDER}
        # Breached: a breach on a monitored flight since the last review.
        reviewed_h = f.get("reviewed_engine_hours")
        # An invalid filter hides nothing, so its "breaches" are just events.
        breach_flights = [s for s in monitored if is_valid and s["breaches"] and
                          (reviewed_h is None or (s["engine_hours"] or 0) > reviewed_h)]
        if breach_flights:
            last = breach_flights[-1]
            reasons["breached"].append(
                f"{_count(sum(s['breaches'] for s in breach_flights), 'event')} went beyond your filter, on "
                f"{_count(len(breach_flights), 'flight')} since you {'last reviewed it' if reviewed_h is not None else 'set it'}.")
            fa = fas.get(last["flight_id"])
            ev = next((e for e in (fa.exceedances if fa else []) if e.get("limit_id") == lid), None)
            health["last_breach"] = {"flight_id": last["flight_id"],
                                     "event_id": ev.get("event_id") if ev else None}

        # Drifting: persistent excursions above the frozen baseline, or events getting more frequent.
        if not collecting and len(monitored) >= DRIFT_PERSISTENCE:
            recent = monitored[-DRIFT_PERSISTENCE:]
            unit = limit.get("unit", "")
            past = "under" if limit.get("limit_type") == "MIN" else "over"
            # (field, frozen stats, std floor, z threshold, pilot wording, value format, suffix after the values)
            checks = [("block_s" if ob else "peak_excess", frozen_mag, z_std_floor(limit) if not ob else 1.0,
                       resolve_outlier_z_threshold(baseline_config, mag_key),
                       "the longest overboost block was longer than usual" if ob
                       else "went further past the limit than usual",
                       (lambda v: f"{v:.0f} s") if ob else (lambda v: f"{_fmt_value(v)} {unit}"),
                       "" if ob else f" {past} the limit")]
            if frozen_pct:
                checks.append(("time_above_pct", frozen_pct, TIME_ABOVE_STD_FLOOR,
                               resolve_outlier_z_threshold(baseline_config, pct_key),
                               "spent more of the flight past the limit than usual",
                               lambda v: f"{v:.0f}%", " of engine time"))
            for field, frozen, floor, z_thr, wording, fmt, suffix in checks:
                comps = [comparison_set(frozen, s["band"]) for s in recent]
                zs = [_z(s.get(field), stats, floor) for s, (stats, _) in zip(recent, comps)]
                if all(z is not None and z > z_thr for z in zs):
                    stats, cmp = comps[-1]
                    values = " and ".join(fmt(s[field]) for s in recent)
                    reasons["drifting"].append(
                        f"{limit['label']} {wording} on your last {DRIFT_PERSISTENCE} flights: {values}{suffix}, "
                        f"against a typical {fmt(stats['mean'])} for "
                        f"{comparison_phrase(cmp, limit.get('stratify_by'))}.")
                    health.setdefault("drift_details", []).append({
                        "metric": field, "values": [s[field] for s in recent],
                        "typical": stats["mean"], "std": stats.get("std"), "std_floor": floor,
                        "z": [round(z, 2) for z in zs], "z_threshold": z_thr, "comparison": cmp,
                    })
            if share_ref is not None and len(monitored) >= FREQUENCY_WINDOW:
                window = monitored[-FREQUENCY_WINDOW:]
                with_events = sum(1 for s in window if s["events"])
                share_now = with_events / len(window)
                if share_now - share_ref >= FREQUENCY_DELTA:
                    n_ref = len(ref_pct_values) if not ob else len([fid for fid in ref_ids if fid in mag_pts])
                    reasons["drifting"].append(
                        f"{limit['label']} is exceeded more often: on {with_events} of your last "
                        f"{FREQUENCY_WINDOW} flights, against {round(share_ref * n_ref)} of {n_ref} "
                        f"reference flights ({share_ref:.0%}).")
                    health.setdefault("drift_details", []).append({
                        "metric": "share_with_events", "values": [share_now], "typical": share_ref,
                        "threshold_delta": FREQUENCY_DELTA, "window": FREQUENCY_WINDOW,
                    })

        policy = resolve_filter_policy(limit)
        if health["hours_since_review"] is not None and health["hours_since_review"] > policy["review_interval_h"]:
            reasons["review_due"].append(
                f"Time to review this filter: {health['hours_since_review']:g} engine hours since you "
                f"{'last reviewed it' if reviewed_h is not None else 'set it'} (review every "
                f"{policy['review_interval_h']:g} h for a {limit.get('severity', 'CAUTION')} limit).")
        if len(monitored) >= QUIET_WINDOW and not any(s["events"] for s in monitored[-QUIET_WINDOW:]):
            reasons["quiet"].append(f"No exceedances on your last {QUIET_WINDOW} flights — you may no longer need this filter.")
        if collecting:
            reasons["collecting"].append(
                f"Still learning what's normal: {len(ref_ids)} of the {REFERENCE_MIN_N} flights it needs so far.")

        status = next((k for k in STATUS_ORDER if reasons[k]), "stable")
        health["status"] = status
        health["reasons"] = [r for k in STATUS_ORDER for r in reasons[k]]
        if not is_valid:
            health["reasons"].insert(0, "Not applied: " + " ".join(d["message"] for d in diags))
        out.append(health)
    return out
