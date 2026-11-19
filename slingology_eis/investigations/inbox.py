"""
The Research inbox (Spec 16 §6, D5): a deterministic, recurrence-gated
scan of each preset's slices over Trends' recent window. The scan
decides *when* to look; the user's own Claude decides what it means.

    workspaces/<id>/inbox.json          candidates and their resolutions (carried by export)
    workspaces/<id>/inbox_cache.json    the scan's descriptor cache (derived)

For each shipped preset (Spec 06 §5.2) the scan builds the preset's slice
set exactly as a study would (same windows, same descriptors), takes the
recent window from Spec 12's own `recent_window` over the flights that
produced a slice, and looks for three things:

(a) **recurring pattern** — in a governed-rpm preset, a prominent rpm
    period in at least N of the last M recent slices (the physics flag:
    a governor holding a setpoint should not cycle); or a descriptor
    standing out (robust z ≥ 3.5 against the older slices, within source
    as §7.4 does) in at least N of the last M, the same way;
(b) **shift** — a descriptor's per-flight value in the recent window
    against the rest, by Spec 12's `shift_stat`, beyond the threshold;
(c) **group apart** — two or more descriptors of one preset each past
    `GROUP_FRACTION` of the shift threshold without any reaching it.

One candidate per preset-and-descriptor stays open at a time; a resolved
one (nothing-here, watch, acted) comes back only once the recent window
has moved on by half its flights. Sensitivity *quiet / normal / curious*
(Settings → Research, stored in the workspace settings) sets N of M and
the shift threshold, and every candidate records the values that fired.

Nothing here is a verdict: a candidate says what is recurring or has
moved, beside its reference, and links its evidence.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .. import __version__
from .. import trends as _trends
from .. import workspace as ws
from ..research import presets as _presets
from ..research.questions import label as _label
from ..research.questions import unit as _unit
from ..research.slices import Cache, build_slice_set

FILENAME = "inbox.json"
CACHE_FILENAME = "inbox_cache.json"
STATUSES = ("new", "investigating", "nothing-here", "watch", "acted")
OPEN = ("new", "investigating")
SCAN_CHANNELS = ("rpm", "map_inhg", "fuel_flow_gph")
DESCRIPTORS = ("swing", "median")
GOVERNED_PRESETS = ("full_power", "governed_climb", "stable_cruise")
Z_STAND_OUT = 3.5               # Spec 06 §7.4's threshold
N_MIN = 10                      # Spec 12's minimum reference (Spec 06 Q10)
GROUP_FRACTION = 0.75

# D5: N of M = 6 of 10 at normal. The shift threshold is a multiple of the
# workspace's own Spec 12 threshold (outlier_z_threshold, 2.0 by default).
SENSITIVITY = {
    "quiet": {"n": 8, "m": 10, "shift_factor": 2.0},
    "normal": {"n": 6, "m": 10, "shift_factor": 1.5},
    "curious": {"n": 4, "m": 10, "shift_factor": 1.0},
}


class InboxError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(ws_dir: Path) -> dict:
    p = ws_dir / FILENAME
    if not p.is_file():
        return {"version": 1, "candidates": [], "last_scan": None}
    try:
        doc = json.loads(p.read_text())
    except ValueError:
        return {"version": 1, "candidates": [], "last_scan": None}
    doc.setdefault("candidates", [])
    doc.setdefault("last_scan", None)
    return doc


def save(ws_dir: Path, doc: dict) -> None:
    (ws_dir / FILENAME).write_text(json.dumps(doc, indent=2))


def parameters(sensitivity: str, baseline_config: dict) -> dict:
    if sensitivity not in SENSITIVITY:
        raise InboxError("BAD_PARAMS", f"sensitivity is one of {', '.join(SENSITIVITY)}")
    s = SENSITIVITY[sensitivity]
    base = float(baseline_config.get("outlier_z_threshold", 2.0))
    return {"sensitivity": sensitivity, "n": s["n"], "m": s["m"], "shift_z": round(base * s["shift_factor"], 3),
            "group_z": round(base * s["shift_factor"] * GROUP_FRACTION, 3), "stand_out_z": Z_STAND_OUT,
            "recent_window_hours": baseline_config.get("recent_window_hours", 10),
            "recent_window_min_flights": baseline_config.get("recent_window_min_flights", 5),
            "recent_window_max_flights": baseline_config.get("recent_window_max_flights", 15)}


def _flights_as_of(ws_dir: Path, as_of: Optional[str]) -> list[str]:
    ids = ws.list_flight_ids(ws_dir)
    if not as_of:
        return ids
    out = []
    for fid in ids:
        fa = ws.load_flight_analysis(ws_dir, fid)
        if fa is not None and (fa.header or {}).get("date") and fa.header["date"] <= as_of:
            out.append(fid)
    return out


def fingerprint(ws_dir: Path, as_of: Optional[str], sensitivity: str) -> str:
    """What a scan's result depends on: the flights, the engine version,
    the sensitivity and the date it was pinned to."""
    ids = sorted(_flights_as_of(ws_dir, as_of))
    return hashlib.sha256(json.dumps([ids, __version__, sensitivity, as_of]).encode()).hexdigest()[:16]


# ── Statistics over one preset ─────────────────────────────────────────────

def _value(s: dict, d: str):
    ch, name = d.split(".", 1)
    v = ((s.get("descriptors") or {}).get(ch) or {}).get(name)
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else float(v)


def _robust_z_against(values: list, ref: list) -> list:
    ref = np.array([x for x in ref if x is not None], dtype=float)
    if len(ref) < N_MIN:
        return [None] * len(values)
    med = float(np.median(ref))
    scale = 1.4826 * float(np.median(np.abs(ref - med)))
    if scale == 0:
        scale = 1.253314 * float(np.mean(np.abs(ref - med)))
    if scale == 0:
        return [None] * len(values)
    return [None if v is None else (v - med) / scale for v in values]


def _points(slices: list[dict], d: str) -> list[dict]:
    """Spec 12's points: one per flight, the median of its slices' value,
    x = engine hours."""
    by: dict[str, list] = {}
    meta: dict[str, dict] = {}
    for s in slices:
        v = _value(s, d)
        if v is None:
            continue
        by.setdefault(s["flight"], []).append(v)
        c = s["context"]
        m = meta.setdefault(s["flight"], {"x": c.get("engine_hours"), "date": c.get("date"),
                                         "start": c.get("start_utc") or c.get("start_time"), "source": c.get("source")})
        if m["x"] is None and c.get("engine_hours") is not None:
            m["x"] = c["engine_hours"]
    return [{"flight_id": f, "value": float(np.median(v)), "x": meta[f]["x"], "date": meta[f]["date"],
             "start_utc": meta[f]["start"], "source": meta[f]["source"]} for f, v in by.items()]


def _fmt(v, d: str) -> str:
    ch = d.split(".", 1)[0]
    if v is None:
        return "—"
    nd = 0 if abs(v) >= 100 else (1 if abs(v) >= 10 else 2)
    u = _unit(ch)
    return f"{v:,.{nd}f}" + (f" {u}" if u else "")


_DESC_TEXT = {"swing": "swing", "median": "level", "period": "period"}


def _dlabel(d: str) -> str:
    ch, name = d.split(".", 1)
    return f"{_label(ch)} {_DESC_TEXT.get(name, name)}"


def scan_preset(preset: dict, ss: dict, p: dict) -> tuple[list[dict], dict]:
    """Candidates one preset's slice set raises, and what was looked at."""
    slices = ss["slices"]
    info = {"preset": preset["rule_id"], "slices": len(slices), "flights": len({s["flight"] for s in slices})}
    pts_rpm = _points(slices, "rpm.median")
    window = _trends.recent_window(pts_rpm, p["recent_window_hours"], p["recent_window_min_flights"],
                                   p["recent_window_max_flights"])
    if window is None:
        info["skipped"] = f"fewer than {p['recent_window_min_flights']} flights with a slice"
        return [], info
    wids = set(window["flight_ids"])
    recent = [s for s in slices if s["flight"] in wids]
    older = [s for s in slices if s["flight"] not in wids]
    recent.sort(key=lambda s: (s["context"].get("start_utc") or s["context"].get("start_time") or "", s["start_s"]))
    last = recent[-p["m"]:]
    info.update({"recent_flights": len(wids), "recent_slices": len(recent), "reference_slices": len(older),
                 "window": {"flight_ids": window["flight_ids"], "hours_from": window["hours_from"],
                            "hours_to": window["hours_to"]}})
    out: list[dict] = []
    base = {"preset": preset["rule_id"], "preset_name": preset["name"], "window": info["window"]}

    def evidence(descs: list[str], zs: Optional[dict] = None, extra: Optional[dict] = None) -> dict:
        cols = ["slice_id", "flight", "date", "source"] + descs + ([f"{d} z" for d in descs] if zs else []) + \
            (list(extra) if extra else [])
        rows = []
        for i, s in enumerate(last):
            c = s["context"]
            r = [s["slice_id"], s["flight"], c.get("date"), c.get("source")] + [_value(s, d) for d in descs]
            if zs:
                r += [None if zs[d][i] is None else round(zs[d][i], 2) for d in descs]
            if extra:
                r += [fn(s) for fn in extra.values()]
            rows.append(r)
        return {"columns": cols, "rows": rows}

    # (a) the physics flag: a prominent period in governed rpm.
    if preset["rule_id"] in GOVERNED_PRESETS and len(last) >= p["n"]:
        lit = [s for s in last if ((s.get("descriptors") or {}).get("rpm") or {}).get("period_prominent")]
        if len(lit) >= p["n"]:
            per = [s["descriptors"]["rpm"]["period_s"] for s in lit if s["descriptors"]["rpm"].get("period_s")]
            sw = [s["descriptors"]["rpm"].get("swing") for s in lit if s["descriptors"]["rpm"].get("swing") is not None]
            med_p = float(np.median(per)) if per else None
            out.append({**base, "kind": "recurring", "descriptors": ["rpm.period"],
                        "fired": {"rule": "prominent rpm period in a governed-rpm preset", "hits": len(lit),
                                  "of": len(last), "n": p["n"], "m": p["m"]},
                        "summary": (f"{preset['name']}: RPM repeats with a prominent period in {len(lit)} of the last "
                                    f"{len(last)} slices (median period {med_p:.1f} s, swing "
                                    f"{_fmt(float(np.median(sw)) if sw else None, 'rpm.swing')}), in a preset where the governor "
                                    f"holds rpm."),
                        "evidence": evidence(["rpm.period_s", "rpm.swing"],
                                             extra={"rpm.prominent": lambda s: bool(s["descriptors"]["rpm"].get("period_prominent"))}),
                        "slices": [s["slice_id"] for s in last]})

    descs = [f"{ch}.{d}" for ch in SCAN_CHANNELS for d in DESCRIPTORS]
    # (a) a descriptor standing out. A slice is compared only with older
    # slices of its own log source (Spec 06 §5.6: the G3X damps some
    # channels; a change of source is not a change of engine), and not at
    # all when its source has fewer than N_MIN older slices.
    by_src = True
    zs_all: dict[str, list] = {}
    for d in descs:
        zs: list = []
        for s in last:
            ref = [_value(o, d) for o in older if o["context"].get("source") == s["context"].get("source")]
            zs.append(_robust_z_against([_value(s, d)], ref)[0])
        zs_all[d] = zs
        fin = [z for z in zs if z is not None]
        if len(fin) < p["n"]:
            continue
        for sign in (1, -1):
            hits = sum(1 for z in fin if sign * z >= Z_STAND_OUT)
            if hits >= p["n"]:
                med_recent = float(np.median([_value(s, d) for s in last if _value(s, d) is not None]))
                ref_vals = [_value(o, d) for o in older if _value(o, d) is not None
                            and o["context"].get("source") in {s["context"].get("source") for s in last}]
                out.append({**base, "kind": "recurring", "descriptors": [d],
                            "fired": {"rule": f"robust z ≥ {Z_STAND_OUT} against the older slices of the same source",
                                      "hits": hits, "of": len(last), "n": p["n"], "m": p["m"], "direction":
                                      "higher" if sign > 0 else "lower"},
                            "summary": (f"{preset['name']}: {_dlabel(d)} stands out "
                                        f"{'above' if sign > 0 else 'below'} the older slices in {hits} of the last "
                                        f"{len(last)} (median {_fmt(med_recent, d)} vs {_fmt(float(np.median(ref_vals)), d)} "
                                        f"over {len(ref_vals)} older slices)."),
                            "evidence": evidence([d], {d: zs}), "slices": [s["slice_id"] for s in last]})

    # (b) shift and (c) group apart, by Spec 12's shift statistic — within
    # the recent window's own log source, for the same reason as (a).
    near: list[tuple[str, float, dict]] = []
    rec_src = [s["context"].get("source") for s in recent]
    source = max(set(rec_src), key=rec_src.count) if rec_src else None
    info["shift_source"] = source
    for d in descs:
        pts = [q for q in _points(slices, d) if q["x"] is not None and q["source"] == source]
        ref_ids = [q["flight_id"] for q in pts if q["flight_id"] not in wids]
        if len(ref_ids) < N_MIN:
            info["shift_skipped"] = (f"the recent flights are {source}; fewer than {N_MIN} older {source} flights "
                                     f"to compare them with")
            continue
        w = {**window, "flight_ids": [f for f in window["flight_ids"] if any(q["flight_id"] == f for q in pts)]}
        if len(w["flight_ids"]) < p["recent_window_min_flights"]:
            continue
        st = _trends.shift_stat(pts, w, ref_ids, None, N_MIN)
        z = st.get("shift_z")
        if z is None:
            continue
        if abs(z) >= p["shift_z"]:
            out.append({**base, "kind": "shift", "descriptors": [d],
                        "fired": {"rule": "Spec 12 shift statistic, within source", "source": source, "shift_z": z,
                                  "threshold": p["shift_z"],
                                  "recent_flights": st["recent"]["n"], "reference_flights": st["reference"]["n"]},
                        "summary": (f"{preset['name']}: {_dlabel(d)} over the last {st['recent']['n']} {source} flights is "
                                    f"{st['direction']} than over the {st['reference']['n']} {source} flights before them (mean "
                                    f"{_fmt(st['recent']['mean'], d)} vs {_fmt(st['reference']['mean'], d)}; "
                                    f"shift z {z:+.1f}, threshold {p['shift_z']:g})."),
                        "evidence": evidence([d], {d: zs_all[d]}), "slices": [s["slice_id"] for s in last]})
        elif abs(z) >= p["group_z"]:
            near.append((d, z, st))
    if len(near) >= 2:
        ds = [d for d, _z, _st in near]
        parts = [f"{_dlabel(d)} {st['direction']} (z {z:+.1f})" for d, z, st in near]
        out.append({**base, "kind": "group_apart", "descriptors": ds,
                    "fired": {"rule": f"two or more descriptors past {GROUP_FRACTION:g} of the shift threshold",
                              "shift_z": {d: z for d, z, _st in near}, "threshold": p["group_z"]},
                    "summary": (f"{preset['name']}: the recent slices sit apart from the older ones on "
                                f"{len(near)} measurements together — " + "; ".join(parts) + "."),
                    "evidence": evidence(ds, {d: zs_all[d] for d in ds}), "slices": [s["slice_id"] for s in last]})
    return out, info


# ── The scan ───────────────────────────────────────────────────────────────

def _key(c: dict) -> str:
    return f"{c['preset']}:{'+'.join(c['descriptors'])}"


def _moved_on(resolved_window: list, now_window: list) -> bool:
    if not resolved_window:
        return True
    new = len(set(now_window) - set(resolved_window))
    return new >= math.ceil(len(resolved_window) / 2)


async def scan(ws_dir: Path, sources, *, engine_name: str, engine_cfg: dict, baseline_config: dict,
               sensitivity: str, assignments: Optional[dict] = None, as_of: Optional[str] = None,
               on_progress: Optional[Callable[[dict], None]] = None) -> dict:
    p = parameters(sensitivity, baseline_config)
    flights = _flights_as_of(ws_dir, as_of)
    cache_p = ws_dir / CACHE_FILENAME
    try:
        cache = Cache(json.loads(cache_p.read_text()) if cache_p.is_file() else None)
    except ValueError:
        cache = Cache()
    presets = _presets.list_presets(engine_name, engine_cfg)["presets"]
    found: list[dict] = []
    looked: list[dict] = []
    for i, pr in enumerate(presets):
        rule = {k: v for k, v in pr.items() if k not in ("question", "isolates", "description")}
        if not flights:
            break

        def progress(u, i=i):
            if on_progress:
                on_progress({**u, "preset": pr["rule_id"], "preset_index": i, "presets": len(presets)})
        ss = await build_slice_set(ws_dir, sources, selection={"mode": "flights", "flights": flights}, rules=[rule],
                                   channels=list(SCAN_CHANNELS), reference="rpm", assignments=assignments,
                                   cache=cache, on_progress=progress)
        cands, info = scan_preset(pr, ss.to_dict(), p)
        found += cands
        looked.append(info)
    try:
        cache_p.write_text(json.dumps(cache.to_dict()))
    except OSError:
        pass

    doc = load(ws_dir)
    now = _now()
    seen_keys = set()
    new_ids = []
    for c in found:
        key = _key(c)
        seen_keys.add(key)
        mine = [x for x in doc["candidates"] if x["key"] == key]
        open_ = next((x for x in mine if x["status"] in OPEN), None)
        fresh = {k: c[k] for k in ("kind", "descriptors", "fired", "summary", "evidence", "slices", "window",
                                   "preset_name")}
        if open_ is not None:
            open_.update(fresh)
            open_.update({"holds": True, "last_seen": now, "sensitivity": p["sensitivity"]})
            continue
        closed = sorted([x for x in mine if x["status"] not in OPEN], key=lambda x: x.get("resolved_at") or "")
        if closed and not _moved_on(closed[-1].get("resolved_window") or [], c["window"]["flight_ids"]):
            closed[-1].update({"last_seen": now, "holds": True})
            continue
        cid = "ib-" + hashlib.sha256(f"{key}|{now}|{len(doc['candidates'])}".encode()).hexdigest()[:10]
        doc["candidates"].append({"id": cid, "key": key, "preset": c["preset"], **fresh, "status": "new",
                                  "sensitivity": p["sensitivity"], "parameters": {k: p[k] for k in ("n", "m", "shift_z", "group_z")},
                                  "created": now, "last_seen": now, "holds": True, "study_id": None, "note": None,
                                  "resolved_at": None, "resolved_window": None})
        new_ids.append(cid)
    for x in doc["candidates"]:
        if x["status"] in OPEN and x["key"] not in seen_keys:
            x["holds"] = False               # still listed; the pattern isn't there this scan
    doc["last_scan"] = {"at": now, "engine": __version__, "sensitivity": p["sensitivity"], "parameters": p,
                        "as_of": as_of, "flights": len(flights), "fingerprint": fingerprint(ws_dir, as_of, sensitivity),
                        "presets": looked, "new": new_ids, "found": len(found)}
    save(ws_dir, doc)
    return doc


def listing(doc: dict, status: Optional[list] = None) -> dict:
    cands = doc.get("candidates") or []
    if status:
        bad = [s for s in status if s not in STATUSES]
        if bad:
            raise InboxError("BAD_PARAMS", f"status is one of {', '.join(STATUSES)}")
        cands = [c for c in cands if c["status"] in status]
    order = {s: i for i, s in enumerate(STATUSES)}
    cands = sorted(cands, key=lambda c: (order[c["status"]], c.get("created") or ""), reverse=False)
    counts = {s: sum(1 for c in doc.get("candidates") or [] if c["status"] == s) for s in STATUSES}
    return {"candidates": cands, "counts": counts, "last_scan": doc.get("last_scan")}


def resolve(ws_dir: Path, candidate_id: str, status: str, *, study_id: Optional[str] = None,
            note: Optional[str] = None) -> dict:
    if status not in STATUSES:
        raise InboxError("BAD_PARAMS", f"status is one of {', '.join(STATUSES)}")
    doc = load(ws_dir)
    c = next((x for x in doc["candidates"] if x["id"] == candidate_id), None)
    if c is None:
        raise InboxError("NOT_FOUND", f"no inbox candidate {candidate_id}")
    if status in OPEN and c["status"] not in OPEN:
        other = next((x for x in doc["candidates"] if x["key"] == c["key"] and x["status"] in OPEN), None)
        if other is not None:
            raise InboxError("BAD_PARAMS", f"{other['id']} is already open for the same preset and measurement")
    c["status"] = status
    if study_id is not None:
        c["study_id"] = study_id or None
    if note is not None:
        c["note"] = str(note)[:4000] or None
    if status in OPEN:
        c["resolved_at"], c["resolved_window"] = None, None
    else:
        c["resolved_at"] = _now()
        c["resolved_window"] = list((c.get("window") or {}).get("flight_ids") or [])
    save(ws_dir, doc)
    return c
