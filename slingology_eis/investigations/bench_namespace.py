"""
The bench's prepared namespace (Spec 16 §4.5, §9 Q2): what a code cell
finds already defined.

    np, pd, plt, scipy, matplotlib      the scientific stack (plt on Agg)
    ws                                  the workspace handle (below)
    flights()                           one row per flight: id, date, hours, duration, airport…
    flight_info(flight_id)              header, phases, events and per-flight metrics
    load_flight(flight_id, channels=None, start_s=None, end_s=None)
                                        the flight on its 1-second grid (index t_s, one column
                                        per registry channel, `filled` where AXIS was resampled)
    load_slices(rule, channels=None, flights=None)
                                        one row per slice: ids, context, every descriptor as
                                        "<channel>.<descriptor>" — the Spec 06 slice set
    load_slice_samples(rule, channels=None, flights=None, anchor="crossing")
                                        the slices' samples, long form: slice_id, flight, t_s
                                        (seconds from the anchor), one column per channel
    profile                             the engine profile (limits with their OM references)
    aircraft                            the aircraft document (§4.4)
    study                               the study's definition (rules, selection, references)
    FILES                               the study's files/ folder — the one place a cell may write
    show(obj, title=None)               put a table, figure or value into the outputs now

`rule` is a preset id ("full_power"), "phase:CLIMB", or a rule object as
Spec 06 §5.1 defines it; `flights` a list of flight ids (default: all).
Every flight a helper reads is recorded as one the cell touched.

The helpers read logs and analyses the way the host does (the same
LogSource and loader), so a number a cell computes from `load_flight`
agrees with Signal view and the slice descriptors.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .. import workspace as _ws
from ..log_sources import DISK, run_now
from ..loader import load_log_bytes
from ..research import presets as _presets
from ..research.rules import RuleError, phase_rule
from ..research.slices import CONTEXT_CHANNELS, _grid, build_slice_set, flight_log_bytes

_FLIGHT_METRICS = ("duration_min", "airborne_min", "max_altitude_ft", "max_ias_kt", "phase_climb_min",
                   "phase_cruise_min")


class Workspace:
    """The workspace as a cell sees it — read-only, except FILES."""

    def __init__(self, req: dict):
        self.dir = Path(req["ws_dir"])
        self.files = Path(req["files_dir"])
        self.profile = req.get("engine_cfg") or {}
        self.engine = req.get("engine_name") or ""
        self.aircraft = req.get("aircraft") or {}
        self.study = req.get("study") or {}
        self._assignments = req.get("assignments") or {}
        self.touched: set[str] = set()
        # Spec 16 §5.5: the channels the tests and log views used, and the tests run — the card's facts.
        self.channels_used: list[str] = []
        self.tests_used: list[str] = []

    def used(self, channels=(), test: Optional[str] = None) -> None:
        self.channels_used += [str(c) for c in channels or [] if c and str(c) not in self.channels_used]
        if test and test not in self.tests_used:
            self.tests_used.append(test)

    def __repr__(self) -> str:
        return f"<EIS workspace {self.dir.name}: {len(_ws.list_flight_ids(self.dir))} flights, engine {self.engine}>"

    # ── flights ──
    def flights(self) -> pd.DataFrame:
        """One row per flight in the workspace, oldest first."""
        rows = []
        for fid in _ws.list_flight_ids(self.dir):
            fa = _ws.load_flight_analysis(self.dir, fid)
            if fa is None:
                continue
            h = fa.header or {}
            row = {"flight_id": fid, "date": h.get("date"), "start_utc": h.get("start_utc"),
                   "engine_hours_start": h.get("engine_hours_start"), "engine_hours_end": h.get("engine_hours_end"),
                   "airport_hint": h.get("airport_hint"), "events": len(fa.exceedances or [])}
            for m in _FLIGHT_METRICS:
                row[m] = (fa.metrics.get(m) or {}).get("value")
            rows.append(row)
        df = pd.DataFrame(rows)
        return df.sort_values(["start_utc", "flight_id"]).reset_index(drop=True) if len(df) else df

    def flight_info(self, flight_id: str) -> dict:
        fa = _ws.load_flight_analysis(self.dir, flight_id)
        if fa is None:
            raise KeyError(f"no flight {flight_id} in this workspace")
        self.touched.add(flight_id)
        return {"flight_id": flight_id, "header": fa.header, "phases": fa.phases, "events": fa.exceedances,
                "metrics": {k: (v or {}).get("value") for k, v in (fa.metrics or {}).items()}}

    def load_flight(self, flight_id: str, channels: Optional[list] = None, start_s: Optional[float] = None,
                    end_s: Optional[float] = None) -> pd.DataFrame:
        """The flight on its 1-second grid — the grid Research slices from."""
        fa = _ws.load_flight_analysis(self.dir, flight_id)
        if fa is None:
            raise KeyError(f"no flight {flight_id} in this workspace")
        found = run_now(flight_log_bytes(self.dir, flight_id, DISK))
        if found is None:
            raise FileNotFoundError(f"the log of flight {flight_id} can't be read right now")
        content, filename = found
        df, _info = load_log_bytes(content, filename, channel_assignments=self._assignments)
        want = set(channels) if channels else {c for c in df.columns if c not in ("datetime", "elapsed_s", "_filled")
                                                and pd.api.types.is_numeric_dtype(df[c])}
        n, values, filled, _row_of = _grid(df, want)
        out = pd.DataFrame({ch: values[ch] for ch in sorted(values)}, index=pd.RangeIndex(n, name="t_s"))
        out["filled"] = filled
        a = 0 if start_s is None else max(0, int(np.floor(start_s)))
        b = n if end_s is None else min(n, int(np.ceil(end_s)))
        self.touched.add(flight_id)
        return out.iloc[a:b]

    # ── slices ──
    def _cache(self):
        """The inbox scan's descriptor cache, read (never written: it is
        outside FILES), so a preset over the workspace needn't re-read
        every log. Anything that doesn't match is recomputed."""
        import json as _json
        from ..research.slices import Cache
        p = self.dir / "inbox_cache.json"
        try:
            return Cache(_json.loads(p.read_text())) if p.is_file() else Cache()
        except ValueError:
            return Cache()

    def _rule(self, rule) -> dict:
        if isinstance(rule, dict):
            return rule
        if isinstance(rule, str) and rule.startswith("phase:"):
            return phase_rule(rule.split(":", 1)[1])
        p = _presets.preset(str(rule), self.engine, self.profile)
        if p is None:
            raise RuleError(f"no preset {rule!r}; one of "
                            + ", ".join(x["rule_id"] for x in _presets.list_presets(self.engine, self.profile)["presets"]))
        return p

    def _build(self, rule, channels, flights, keep_samples: bool):
        sel = {"mode": "flights", "flights": list(flights)} if flights else {"mode": "all"}
        rules = rule if isinstance(rule, list) else [rule]
        ss = run_now(build_slice_set(self.dir, DISK, selection=sel, rules=[self._rule(r) for r in rules],
                                     channels=list(channels) if channels else None,
                                     assignments=self._assignments, keep_samples=keep_samples,
                                     cache=self._cache()))
        self.touched.update(s.flight for s in ss.slices)
        return ss

    def load_slices(self, rule="full_power", channels: Optional[list] = None, flights: Optional[list] = None) -> pd.DataFrame:
        """One row per slice with its context and descriptors."""
        ss = self._build(rule, channels or ["rpm", "map_inhg", "fuel_flow_gph"], flights, keep_samples=False)
        rows = []
        for s in ss.slices:
            row = {"slice_id": s.slice_id, "flight_id": s.flight, "rule_id": s.rule_id, "start_s": s.start_s,
                   "end_s": s.end_s, "duration_s": s.end_s - s.start_s}
            row.update({k: v for k, v in s.context.items() if k not in ("flight_id",)})
            for ch, d in s.descriptors.items():
                for k, v in d.items():
                    row[f"{ch}.{k}"] = v
            rows.append(row)
        return pd.DataFrame(rows)

    def load_slice_samples(self, rule="full_power", channels: Optional[list] = None, flights: Optional[list] = None,
                           anchor: str = "crossing") -> pd.DataFrame:
        """The slices' 1 Hz samples, long form, t_s from the anchor
        ("crossing" — the rule's first second — or "start")."""
        chans = list(channels or ["rpm", "map_inhg"])
        ss = self._build(rule, chans, flights, keep_samples=True)
        frames = []
        for s in ss.slices:
            n = s.end_s - s.start_s
            a = (s.anchor_s - s.start_s) if anchor in (None, "", "crossing") else 0
            d = {"slice_id": [s.slice_id] * n, "flight_id": [s.flight] * n, "t_s": np.arange(n) - a,
                 "source": [s.context.get("source")] * n}
            for ch in chans:
                if ch in (s.samples or {}):
                    d[ch] = s.samples[ch]
            frames.append(pd.DataFrame(d))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["slice_id", "flight_id", "t_s"])


HELPERS = ("ws", "flights", "flight_info", "load_flight", "load_slices", "load_slice_samples", "profile", "aircraft",
           "study", "FILES", "show", "np", "pd", "plt", "scipy", "matplotlib")
__all__ = ["Workspace", "HELPERS", "CONTEXT_CHANNELS"]
