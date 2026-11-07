"""
Building a slice set over a workspace's logs (Spec 06 §5.5).

Slicing needs raw channel data, which the analysis discards, so the logs
are re-read on demand through the workspace's `LogSource`s — a resumable
coroutine with one file outstanding (Spec 04 D11): in the browser the page
supplies each log's bytes in turn. Each flight is parsed, cut into the
windows its rules select, and dropped; only the slices' samples are kept,
for the channels asked for, until their descriptors are computed.

Descriptors come in two passes (§7.0): period first, on every slice of the
set; then the swing window and lag range are resolved per channel from
the set's median period, and the windowed descriptors computed.

**Descriptor cache (Q2, §10.1).** Given a study's cache, a flight whose
analysed log (`source_key`) and engine version match a cached entry for
the same rule is not parsed: its slices and pass-1 descriptors come from
the cache, and its windowed descriptors too when the cache holds them for
the resolved window. Anything that doesn't match is discarded and
recomputed, never trusted. Samples are never cached.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .. import __version__
from .. import workspace as ws
from ..loader import AXIS_FORMATS, load_log_bytes
from . import descriptors as D
from .rules import RuleError, apply_rule, normalise_hand_slice, normalise_rule, rule_hash

CONTEXT_CHANNELS = ("press_alt_ft", "da_ft", "oat_c", "tach_time_h")


def source_label(source_format: Optional[str]) -> str:
    """The §5.6 source facet: AXIS (SD card or aircraft log) or G3X."""
    return "AXIS" if source_format in AXIS_FORMATS else "G3X"


@dataclass
class Slice:
    slice_id: str
    flight: str
    source_key: str
    kind: str                 # "rule" | "hand"
    rule_id: Optional[str]
    label: str
    start_s: int
    end_s: int
    anchor_s: int
    offset_s: float = 0.0
    context: dict = field(default_factory=dict)
    quality: dict = field(default_factory=dict)
    descriptors: dict = field(default_factory=dict)          # channel -> descriptor dict
    samples: Optional[dict] = None                           # channel -> array (in memory only)
    filled: Optional[np.ndarray] = None
    _pass1: dict = field(default_factory=dict)               # channel -> period dict

    def to_dict(self) -> dict:
        d = {"slice_id": self.slice_id, "flight": self.flight, "source_key": self.source_key, "kind": self.kind,
             "rule_id": self.rule_id, "label": self.label, "start_s": self.start_s, "end_s": self.end_s,
             "anchor_s": self.anchor_s, "context": self.context, "quality": self.quality,
             "descriptors": self.descriptors}
        if self.kind == "hand":
            d["offset_s"] = self.offset_s
        return d


@dataclass
class SliceSet:
    slices: list[Slice]
    rules: list[dict]
    hand_slices: list[dict]
    channels: list[str]
    reference: str
    windows: dict                       # channel -> resolved §7.0 window
    flights_selected: int
    missing_flights: list[str]          # in the selection, not in this workspace
    unreachable_flights: list[str]      # in the workspace, log not readable now
    parsed_flights: int = 0
    cached_flights: int = 0
    missing_channels: dict = field(default_factory=dict)  # rule_id -> flights lacking a condition channel
    engine_version: str = __version__

    def to_dict(self) -> dict:
        by_source: dict[str, int] = {}
        for s in self.slices:
            by_source[s.context.get("source", "?")] = by_source.get(s.context.get("source", "?"), 0) + 1
        return {
            "slices": [s.to_dict() for s in self.slices], "count": len(self.slices), "by_source": by_source,
            "flights_with_slices": len({s.flight for s in self.slices}), "flights_selected": self.flights_selected,
            "rules": self.rules, "hand_slices": self.hand_slices, "channels": self.channels,
            "reference": self.reference, "windows": self.windows,
            "missing_flights": self.missing_flights, "unreachable_flights": self.unreachable_flights,
            "missing_channels": self.missing_channels,
            "parsed_flights": self.parsed_flights, "cached_flights": self.cached_flights,
            "engine_version": self.engine_version,
        }


# ── Reading one flight ─────────────────────────────────────────────────────

async def flight_log_bytes(ws_dir: Path, flight_id: str, sources) -> Optional[tuple[bytes, str]]:
    """The analysed log of a flight: the workspace's own copy when it kept
    one, else read through the flight's log folder (as the Flight view's
    timeline does)."""
    d = ws_dir / "flights" / flight_id
    analysed = ws.source_filename(ws_dir, flight_id)
    if analysed and (d / analysed).is_file():
        return (d / analysed).read_bytes(), analysed
    src = ws.load_sources(ws_dir, flight_id)
    return (await ws.read_source_bytes_async(ws_dir, src, sources)) if src else None


def _grid(df, channels: set) -> tuple[int, dict, np.ndarray, np.ndarray]:
    """The frame on whole seconds from the start of the log: (n, channel
    arrays, filled mask, row index of each second or -1)."""
    t = np.rint(df["elapsed_s"].to_numpy(dtype=float)).astype(int)
    t = t - t.min() if len(t) else t
    n = int(t.max()) + 1 if len(t) else 0
    keep = np.ones(len(t), dtype=bool)
    keep[1:] = t[1:] != t[:-1]              # one row per second
    t, rows = t[keep], np.flatnonzero(keep)
    values = {}
    for ch in channels:
        if ch in df.columns:
            col = df[ch].to_numpy(dtype=float, na_value=np.nan)[rows] if hasattr(df[ch], "to_numpy") else None
            arr = np.full(n, np.nan)
            arr[t] = col
            if np.isfinite(arr).any():
                values[ch] = arr
    filled = np.zeros(n, dtype=bool)
    if "_filled" in df.columns:
        filled[t] = df["_filled"].to_numpy(dtype=bool)[rows]
    row_of = np.full(n, -1)
    row_of[t] = rows
    return n, values, filled, row_of


def _mean(values: dict, ch: str, a: int, b: int, nd: int = 0):
    y = values.get(ch)
    if y is None:
        return None
    seg = y[a:b]
    return D._r(np.nanmean(seg), nd) if np.isfinite(seg).any() else None


def _context(fa, info, df, values, row_of, a: int, b: int, phases: list[dict]) -> dict:
    covered = []
    for seg in phases or []:
        if float(seg["start_s"]) < b and float(seg["end_s"]) > a and seg["phase"] not in covered:
            covered.append(seg["phase"])
    r = row_of[a] if row_of[a] >= 0 else row_of[row_of >= 0][0]
    local = df["datetime"].iloc[int(r)]
    header = fa.header or {}
    start_utc = None
    if header.get("start_utc"):
        try:
            start_utc = (datetime.fromisoformat(header["start_utc"]) + timedelta(seconds=int(a))).isoformat()
        except ValueError:
            start_utc = None
    tach = values.get("tach_time_h")
    if tach is not None and np.isfinite(tach[a:b]).any():
        hours = float(tach[a:b][np.isfinite(tach[a:b])][0])
    elif header.get("engine_hours_start") is not None:
        hours = float(header["engine_hours_start"]) + a / 3600.0
    else:
        hours = None
    return {
        "flight_id": fa.flight_id, "source": source_label(info.source_format), "source_format": info.source_format,
        "phases": covered, "pa_ft": _mean(values, "press_alt_ft", a, b), "da_ft": _mean(values, "da_ft", a, b),
        "oat_c": _mean(values, "oat_c", a, b, 1), "engine_hours": D._r(hours, 2),
        "start_time": local.strftime("%Y-%m-%d %H:%M:%S") if local == local else None,
        "start_utc": start_utc, "date": header.get("date"),
    }


# ── Cache (Q2) ─────────────────────────────────────────────────────────────

def descriptor_key(window: dict, reference: str, prominence_min: float) -> str:
    """What a windowed descriptor depends on beyond the slice itself."""
    return f"w{window['window_s']}:l{window['lag_s']}:r{reference}:p{prominence_min:g}"


class Cache:
    """A study's descriptor cache: per flight, the analysed log's
    source_key and engine version it was computed under, the slices each
    rule made, and per slice its context, quality, pass-1 periods and
    windowed descriptors by descriptor key."""

    def __init__(self, doc: Optional[dict] = None):
        doc = doc or {}
        self.engine = doc.get("engine")
        self.flights: dict = dict(doc.get("flights") or {})
        self.slices: dict = {d["slice"]: d for d in (doc.get("descriptors") or []) if "slice" in d}
        if self.engine != __version__:          # engine changed: every entry is discarded
            self.flights, self.slices = {}, {}
        self.engine = __version__

    def lookup(self, flight_id: str, source_key: str, rkey: str, channels: list[str]) -> Optional[list[dict]]:
        f = self.flights.get(flight_id)
        if not f or f.get("source_key") != source_key or rkey not in (f.get("rules") or {}):
            return None
        if not set(channels) <= set(f.get("channels") or []):
            return None
        ids = f["rules"][rkey]
        if not all(i in self.slices for i in ids):
            return None
        return [self.slices[i] for i in ids]

    def store(self, flight_id: str, source_key: str, rkey: str, slices: list[Slice], channels: list[str]) -> None:
        f = self.flights.get(flight_id)
        if not f or f.get("source_key") != source_key or set(channels) - set(f.get("channels") or []):
            # A new log, or channels this entry never looked at: start the flight afresh.
            for ids in (f or {}).get("rules", {}).values():
                for i in ids:
                    self.slices.pop(i, None)
            f = self.flights[flight_id] = {"source_key": source_key, "channels": sorted(channels), "rules": {}}
        f["rules"][rkey] = [s.slice_id for s in slices]
        for s in slices:
            entry = self.slices.setdefault(s.slice_id, {"flight": flight_id, "slice": s.slice_id})
            entry.update({"source_key": source_key, "kind": s.kind, "rule_id": s.rule_id, "label": s.label,
                          "start_s": s.start_s, "end_s": s.end_s, "anchor_s": s.anchor_s, "offset_s": s.offset_s,
                          "context": s.context, "quality": s.quality})
            entry.setdefault("period", {}).update(s._pass1)
            entry.setdefault("values", {})

    def store_descriptors(self, s: Slice, keys: dict) -> None:
        entry = self.slices.get(s.slice_id)
        if entry is None:
            return
        for ch, d in s.descriptors.items():
            entry["values"].setdefault(ch, {})[keys[ch]] = d

    def to_dict(self) -> dict:
        return {"engine": self.engine, "flights": self.flights,
                "descriptors": sorted(self.slices.values(), key=lambda d: d["slice"])}


def _slice_from_cache(e: dict) -> Slice:
    s = Slice(slice_id=e["slice"], flight=e["flight"], source_key=e["source_key"], kind=e["kind"],
              rule_id=e.get("rule_id"), label=e["label"], start_s=e["start_s"], end_s=e["end_s"],
              anchor_s=e["anchor_s"], offset_s=e.get("offset_s", 0), context=e["context"], quality=e["quality"])
    s._pass1 = dict(e.get("period") or {})
    return s


# ── The builder ────────────────────────────────────────────────────────────

def _selected_flights(ws_dir: Path, selection: dict) -> tuple[list[str], list[str]]:
    present = ws.list_flight_ids(ws_dir)
    mode = (selection or {}).get("mode", "all")
    if mode == "all":
        return present, []
    if mode != "flights":
        raise RuleError(f"selection mode {mode!r}; one of all, flights")
    wanted = list(dict.fromkeys((selection or {}).get("flights") or []))
    have = set(present)
    return [f for f in wanted if f in have], [f for f in wanted if f not in have]


def _slice_id(flight_id: str, rkey: str, start_s: int, end_s: int) -> str:
    return f"{flight_id}:{rkey}:{int(start_s)}-{int(end_s)}"


def _hand_key(h: dict) -> str:
    return f"hand:{h['start_s']:g}-{h['end_s']:g}"


async def build_slice_set(ws_dir: Path, sources, *, selection: Optional[dict] = None, rules: Optional[list] = None,
                          hand_slices: Optional[list] = None, channels: Optional[list] = None,
                          reference: str = "rpm", windows: Optional[dict] = None,
                          prominence_min: float = D.PROMINENCE_MIN, assignments: Optional[dict] = None,
                          cache: Optional[Cache] = None, keep_samples: bool = False,
                          on_progress: Optional[Callable[[dict], None]] = None,
                          only_slices: Optional[set] = None) -> SliceSet:
    """§5.5: the slices `rules` and `hand_slices` make over the `selection`
    of the workspace's flights, with §6 descriptors for `channels` (and
    each channel's coupling with `reference`). `windows` overrides the
    §7.0 window per channel ({channel: {window_s, lag_s}}). With
    `keep_samples` the slices keep their samples (for get_slice_samples);
    `only_slices` limits which slices are kept."""
    rules = [normalise_rule(r) for r in (rules or [])]
    hands = [normalise_hand_slice(h) for h in (hand_slices or [])]
    if not rules and not hands:
        raise RuleError("a slice set needs at least one slice rule or hand slice")
    channels = list(dict.fromkeys(channels or D.STANDARD_CHANNELS))
    if reference and reference not in channels:
        channels.insert(0, reference)
    windows = windows or {}
    cache = cache if cache is not None else Cache()

    flight_ids, missing = _selected_flights(ws_dir, selection or {"mode": "all"})
    hand_by_flight: dict[str, list[dict]] = {}
    for h in hands:
        hand_by_flight.setdefault(h["flight"], []).append(h)
    present = set(ws.list_flight_ids(ws_dir))
    selected = set(flight_ids)
    for fid in hand_by_flight:
        if fid not in present:
            missing.append(fid)
        elif fid not in flight_ids:
            flight_ids.append(fid)
    rkeys = {r["rule_id"]: rule_hash(r) for r in rules}
    needed = set(channels) | set(CONTEXT_CHANNELS) | {c["channel"] for r in rules for c in r["conditions"]}

    slices: list[Slice] = []
    unreachable: list[str] = []
    missing_channels: dict[str, list[str]] = {}
    parsed = cached = 0
    pending_parse: dict[str, list[Slice]] = {}   # flights whose cached slices still need samples for pass 2

    async def parse(fid: str, fa):
        found = await flight_log_bytes(ws_dir, fid, sources)
        if found is None:
            return None
        content, filename = found
        df, info = load_log_bytes(content, filename, channel_assignments=assignments or {})
        return (df, info) + _grid(df, needed)

    total = len(flight_ids)
    for i, fid in enumerate(flight_ids):
        if on_progress:
            on_progress({"phase": "slicing", "done": i, "total": total})
        fa = ws.load_flight_analysis(ws_dir, fid)
        if fa is None:
            unreachable.append(fid)
            continue
        skey = (fa.source_keys or [""])[0]
        jobs = [("rule", r, rkeys[r["rule_id"]]) for r in rules] if fid in selected else []
        jobs += [("hand", h, _hand_key(h)) for h in hand_by_flight.get(fid, [])]
        hits = {k: cache.lookup(fid, skey, k, channels) for _kind, _x, k in jobs}
        if all(h is not None for h in hits.values()):
            cached += 1
            for _kind, _x, k in jobs:
                slices.extend(_slice_from_cache(e) for e in hits[k])
            continue
        got = await parse(fid, fa)
        if got is None:
            unreachable.append(fid)
            continue
        parsed += 1
        df, info, n, values, filled, row_of = got
        for kind, x, k in jobs:
            if kind == "rule":
                wins, lacking = apply_rule(x, values, fa.phases, n)
                if lacking:
                    missing_channels.setdefault(x["rule_id"], []).append(fid)
                made = []
                for w in wins:
                    made.append(Slice(slice_id=_slice_id(fid, k, w["start_s"], w["end_s"]), flight=fid, source_key=skey,
                                      kind="rule", rule_id=x["rule_id"], label=x["name"], start_s=w["start_s"],
                                      end_s=w["end_s"], anchor_s=w["anchor_s"]))
            else:
                a, b = max(0, int(np.floor(x["start_s"]))), min(n, int(np.ceil(x["end_s"])))
                made = [] if b - a < 2 else [Slice(slice_id=_slice_id(fid, k, a, b), flight=fid, source_key=skey,
                                                   kind="hand", rule_id=None, label=x["label"], start_s=a, end_s=b,
                                                   anchor_s=a, offset_s=x["offset_s"])]
            for s in made:
                a, b = s.start_s, s.end_s
                s.context = _context(fa, info, df, values, row_of, a, b, fa.phases)
                s.quality = {"samples": int((row_of[a:b] >= 0).sum()), "duration_s": int(b - a),
                             "filled_share": D._r(filled[a:b].mean() if b > a else 0.0, 3)}
                s.samples = {ch: values[ch][a:b] for ch in channels if ch in values}
                s.filled = filled[a:b]
                s._pass1 = {ch: D.dominant_period(y, s.filled, prominence_min) for ch, y in s.samples.items()}
            cache.store(fid, skey, k, made, channels)
            slices.extend(made)
        del df, values
    if on_progress:
        on_progress({"phase": "slicing", "done": total, "total": total})

    if only_slices is not None:
        slices = [s for s in slices if s.slice_id in only_slices]

    # §7.0 pass 2: resolve each channel's window from the whole set.
    durations = [s.end_s - s.start_s for s in slices]
    resolved = {ch: D.resolve_window([s._pass1.get(ch, {}) for s in slices if ch in s._pass1], durations, windows.get(ch))
                for ch in channels}
    keys = {ch: descriptor_key(resolved[ch], reference, prominence_min) for ch in channels}

    def from_cache(s: Slice) -> bool:
        entry = cache.slices.get(s.slice_id) or {}
        vals = entry.get("values") or {}
        have = {ch for ch in s._pass1}
        if not all(keys[ch] in (vals.get(ch) or {}) for ch in have):
            return False
        s.descriptors = {ch: vals[ch][keys[ch]] for ch in have}
        return True

    need_samples: dict[str, list[Slice]] = {}
    for s in slices:
        if s.samples is None and (keep_samples or not from_cache(s)):
            need_samples.setdefault(s.flight, []).append(s)
    for fid, group in need_samples.items():
        fa = ws.load_flight_analysis(ws_dir, fid)
        got = await parse(fid, fa)
        if got is None:
            unreachable.append(fid)
            slices = [s for s in slices if s.flight != fid]
            continue
        parsed += 1
        _df, _info, n, values, filled, _row_of = got
        for s in group:
            s.samples = {ch: values[ch][s.start_s:s.end_s] for ch in channels if ch in values}
            s.filled = filled[s.start_s:s.end_s]

    for s in slices:
        if s.samples is None:
            continue
        ref = s.samples.get(reference)
        s.descriptors = {}
        for ch, y in s.samples.items():
            w = resolved[ch]
            d = D.describe_channel(y, s.filled, s.anchor_s - s.start_s, w["window_s"],
                                   ref=ref if ch != reference else None, lag_s=w["lag_s"],
                                   prominence_min=prominence_min)
            s.descriptors[ch] = d
        cache.store_descriptors(s, keys)
        if not keep_samples:
            s.samples, s.filled = None, None

    slices.sort(key=lambda s: (s.context.get("start_utc") or s.context.get("start_time") or "", s.flight, s.start_s))
    return SliceSet(slices=slices, rules=rules, hand_slices=hands, channels=channels, reference=reference,
                    windows=resolved, flights_selected=len(flight_ids), missing_flights=sorted(set(missing)),
                    unreachable_flights=sorted(set(unreachable)), parsed_flights=parsed, cached_flights=cached,
                    missing_channels=missing_channels)
