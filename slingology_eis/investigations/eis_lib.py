"""
The `eis` library on the bench (Spec 16 §4.5, D12): what a notebook's code
cells call. Every function here is the host operation's own code — the
tests call `research.api.run_question` as `run_test` (`question_run`)
does, `compare` calls `research.api.compare` as `compare_rows` does,
`signal` calls `analyze_signal`, `flights` the `list_flights` operation
shaped as the `flights_list` tool shapes it — so a notebook's number is
the tool's number (acceptance 12).

    eis.flights()                      the flights_list rows as a frame (local times, route, counts)
    eis.find("the Oct 24 flight …")    flights_find: candidates with what matched
    eis.load(flight, channels=None, start_s=None, end_s=None)
                                       the flight on its 1-second grid (index t_s)
    eis.slices(rule, channels=None, flights=None)
    eis.samples(rule, channels=None, flights=None, anchor="crossing")
    eis.cycling(rule, "rpm", **params)       → Result
    eis.coupling(rule, ["rpm", "map_inhg"], **params)
    eis.groups(rule, "rpm.swing", by="source" | "date" (date=…) | "da_band" | …)
    eis.unusual(rule, channels=None, **params)
    eis.signal(flight, start_s=None, end_s=None, channels=None, **kw)   the Signal view's analysis (dict)
    eis.compare(rule, channels=None, pinned=None, collapse=False)       a frame, one row per slice
    eis.logview(flight, start_s, end_s, channels, marks=[(t_s, "label")], title=None, caption=None)
    eis.table(df, caption, units={col: unit}, digits=None)     an evidence table (D19)
    eis.figure(fig, caption)                                    an evidence figure (D19)
    eis.document(name).find(phrase) / .page(n)
    eis.aircraft, eis.profile, eis.notes

A `rule` is a preset id ("full_power"), "phase:CLIMB", a Spec 06 §5.1 rule
object, a list of those, or a slice-set spec `{"selection", "slice_rules",
"hand_slices"}` (what a converted Session D question cell names).
`flights=[…]` narrows the selection; `windows`, `references` and
`prominence_min` pass through as the tools take them.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from ..log_sources import DISK, run_now
from ..research import api as _api
from ..research.render import _chart_values, render_text

LOGVIEW_MIME = "application/vnd.slingology.logview+json"
_SET_KEYS = ("selection", "slice_rules", "hand_slices")


class Result:
    """A Spec 06 §8 result: the question's finding, its magnitude beside
    the OM references, the caveats, the per-slice rows and the figure.
    `print(result)` is the §8 text."""

    def __init__(self, data: dict):
        self.data = data

    test_id = property(lambda self: self.data.get("test_id"))
    question = property(lambda self: self.data.get("question"))
    finding = property(lambda self: self.data.get("finding"))
    magnitude = property(lambda self: self.data.get("magnitude") or [])
    caveats = property(lambda self: self.data.get("caveats") or [])

    @property
    def rows(self) -> pd.DataFrame:
        table = (self.data.get("evidence") or {}).get("table") or {}
        cols = [c["key"] for c in table.get("columns") or []]
        return pd.DataFrame(table.get("rows") or [], columns=cols or None)

    def figure(self):
        """The §8 chart: one dot per slice, grouped, each group's median a bar."""
        import matplotlib.pyplot as plt
        axis, vals = _chart_values(self.data)
        groups = list(dict.fromkeys(g for g, _v, _l in vals)) or [""]
        fig, ax = plt.subplots(figsize=(6.4, 3.2))
        for i, g in enumerate(groups):
            ys = [v for gg, v, _l in vals if gg == g]
            if not ys:
                continue
            xs = [i + (k % 7 - 3) * 0.03 for k in range(len(ys))]
            ax.scatter(xs, ys, s=12, alpha=0.7)
            med = sorted(ys)[len(ys) // 2] if len(ys) % 2 else sum(sorted(ys)[len(ys) // 2 - 1:len(ys) // 2 + 1]) / 2
            ax.hlines(med, i - 0.3, i + 0.3, colors="black", linewidth=2)
        ax.set_xticks(range(len(groups)), groups)
        ax.set_ylabel(axis)
        ax.set_title(self.question or self.test_id or "")
        fig.tight_layout()
        return fig

    def __str__(self) -> str:
        return render_text(self.data)

    __repr__ = __str__


class LogView:
    """A log-view cell's output (§5.2): the strip chart as SVG, and the
    reference (never samples) the EIS pages mount the Flight view from."""

    def __init__(self, ref: dict, fig):
        self.ref, self.fig = ref, fig

    def _repr_mimebundle_(self, include=None, exclude=None) -> dict:
        import io
        import matplotlib
        buf = io.StringIO()
        # The bench's salt everywhere (D14): the same SVG in JupyterLab as on the bench.
        with matplotlib.rc_context({"svg.hashsalt": "slingology-eis"}):
            self.fig.savefig(buf, format="svg", metadata={"Date": None}, bbox_inches="tight")
        title = self.ref.get("title") or f"Flight {self.ref['flight']}"
        data = {"image/svg+xml": buf.getvalue(), LOGVIEW_MIME: dict(self.ref),
                "text/plain": f"<log view: {title}, {self.ref.get('window_label') or ''}>"}
        # D19: every log view is an evidence output; its caption is caption=, else the title.
        cap = " ".join(str(self.ref.get("caption") or self.ref.get("title") or "").split())
        return data, {"slingology": {"evidence": {"kind": "logview", "caption": cap}}}

    def __repr__(self) -> str:
        return self._repr_mimebundle_()[0]["text/plain"]


_TREND_COLUMNS = ["rank", "metric_id", "reference_n", "reference_mean", "reference_std", "reference_min",
                  "reference_max", "trend_slope_per_hour", "trend_r_squared", "trend_direction", "shift", "shift_z",
                  "shift_direction", "recent_n", "recent_mean", "recent_hours", "shift_reference_n",
                  "shift_reference_mean", "om_limit", "outliers", "shifts_recorded", "last_shift_at",
                  "recent_flights", "flights"]


class EIS:
    def __init__(self, ws, req: dict):
        self._ws = ws
        self._req = req
        self.aircraft = ws.aircraft
        self.profile = ws.profile
        self.notes = req.get("notes") or ""

    def __repr__(self) -> str:
        return "<eis: flights, find, metrics, trends, load, slices, samples, cycling, coupling, groups, unusual, " \
               "signal, compare, logview, table, figure, document, aircraft, profile, notes>"

    # ── evidence (D19) ──
    def table(self, df, caption=None, units: Optional[dict] = None, digits=None):
        """An evidence table: headers in words with units, values rounded, the caption."""
        from . import evidence as EV
        return EV.table(df, caption, units=units, digits=digits)

    def figure(self, fig, caption=None):
        """An evidence figure: the matplotlib figure with its caption."""
        from . import evidence as EV
        return EV.figure(fig, caption)

    # ── flights ──
    def _flight_rows(self) -> list[dict]:
        from .. import host as H
        return run_now(H.op_list_flights({"summary": True}, {"workspace_dir": self._ws.dir}))

    def flights(self) -> pd.DataFrame:
        """The flights_list rows (local times with the zone, route, counts, facts), oldest first."""
        from .mcp_tools import flight_row
        rows = sorted((flight_row(f) for f in self._flight_rows()),
                      key=lambda r: (r["start_local"] or r["date"] or "", r["flight_id"]))
        return pd.DataFrame(rows)

    def find(self, description: str, limit: int = 10) -> pd.DataFrame:
        """flights_find: the flights a description in words names, best first."""
        from .. import flight_ident as fi
        rows = self._flight_rows()
        got = fi.find([{"flight_id": r["flight_id"], "ident": r.get("ident"), "date": r["header"].get("date"),
                        "name": r.get("name"), "notes": r.get("notes")} for r in rows], description, limit=limit)
        return pd.DataFrame(got.get("candidates") or [])

    # ── Trends (Spec 16 F18: the fleet_metrics and trends_summary code) ──
    def _fleet(self) -> dict:
        from .. import host as H
        return H.op_get_fleet({}, {"workspace_dir": self._ws.dir})

    def metrics(self, flights: Optional[list] = None, metrics: Optional[list] = None) -> pd.DataFrame:
        """The per-flight metrics Trends is built from — fleet_metrics' rows,
        one per flight in engine-hours order — with the conditions each was
        flown in: date, local start, engine hours, cruise density altitude
        (ft) and OAT (°C), log source, flight id and name. `flights` keeps
        those flights; `metrics` chooses columns (default: all but limit_*).
        Plot a metric against date or OAT before reaching for a test."""
        from .mcp_tools import fleet_metric_rows, flight_row
        rows, want, unknown = fleet_metric_rows(self._fleet(), metrics, flights)
        if unknown:
            raise ValueError(f"unknown metrics {unknown}; see eis.metrics().columns")
        cond = {r["flight_id"]: r for r in (flight_row(f) for f in self._flight_rows())}
        lead = ["flight_id", "name", "date", "start_local", "engine_hours", "cruise_da_ft", "cruise_oat_c", "source"]
        want = [k for k in want if k not in lead]        # cruise_da_ft is a metric and a condition: one column
        out = []
        for r in rows:
            c = cond.get(r["flight_id"], {})
            out.append({"flight_id": r["flight_id"], "name": c.get("name"), "date": c.get("date") or r["date"],
                        "start_local": c.get("start_local"), "engine_hours": r["engine_hours"],
                        "cruise_da_ft": r["cruise_da_ft"] if "cruise_da_ft" in r else c.get("cruise_da_ft"),
                        "cruise_oat_c": c.get("cruise_oat_c"), "source": c.get("source"),
                        **{k: r.get(k) for k in want}})
        return pd.DataFrame(out, columns=[*lead, *want])

    def trends(self) -> pd.DataFrame:
        """The Trends cards, ranked — trends_summary's change summary — one
        row per metric: its reference (the baseline: n, mean, std, min, max),
        trend over engine hours, the shift if one stands (recent window
        against its reference, z, direction, the OM limit beside it), the
        shifts recorded for it, and the flights it rests on."""
        from .mcp_tools import trend_cards
        fleet = self._fleet()
        history = fleet.get("shift_history") or []
        rows = []
        for c in trend_cards(fleet):
            b, t, sh = c.get("baseline") or {}, c.get("trend") or {}, c.get("shift") or {}
            rec, ref = sh.get("recent") or {}, sh.get("reference") or {}
            mine = [h for h in history if h.get("metric_id") == c["metric_id"]]
            rows.append({
                "rank": c.get("rank"), "metric_id": c["metric_id"],
                "reference_n": b.get("n"), "reference_mean": b.get("mean"), "reference_std": b.get("std"),
                "reference_min": b.get("min"), "reference_max": b.get("max"),
                "trend_slope_per_hour": t.get("slope"), "trend_r_squared": t.get("r_squared"),
                "trend_direction": t.get("direction"),
                "shift": bool(sh), "shift_z": sh.get("shift_z"), "shift_direction": sh.get("direction"),
                "recent_n": rec.get("n"), "recent_mean": rec.get("mean"), "recent_hours": (rec.get("hours_from"), rec.get("hours_to")) if rec else None,
                "shift_reference_n": ref.get("n"), "shift_reference_mean": ref.get("mean"),
                "om_limit": (sh.get("level") or {}).get("limit"),
                "outliers": [o["flight_id"] for o in c.get("outliers") or []],
                "shifts_recorded": len(mine), "last_shift_at": max((h.get("detected_at") or "" for h in mine), default=None) or None,
                "recent_flights": rec.get("flight_ids") or [], "flights": c.get("flights") or [],
            })
        return pd.DataFrame(rows, columns=_TREND_COLUMNS)

    def load(self, flight: str, channels: Optional[list] = None, start_s=None, end_s=None) -> pd.DataFrame:
        return self._ws.load_flight(flight, channels, start_s, end_s)

    def slices(self, rule="full_power", channels: Optional[list] = None, flights: Optional[list] = None) -> pd.DataFrame:
        return self._ws.load_slices(rule, channels, flights)

    def samples(self, rule="full_power", channels: Optional[list] = None, flights: Optional[list] = None,
                anchor: str = "crossing") -> pd.DataFrame:
        return self._ws.load_slice_samples(rule, channels, flights, anchor)

    # ── the questions (one code path with question_run) ──
    def _set(self, rule, flights) -> dict:
        if isinstance(rule, dict) and any(k in rule for k in _SET_KEYS):
            spec = dict(rule)
        else:
            spec = {"slice_rules": rule if isinstance(rule, list) else [rule]}
        if flights:
            spec["selection"] = {"mode": "flights", "flights": list(flights)}
        return {"selection": spec.get("selection") or {"mode": "all"},
                "slice_rules": [self._ws._rule(r) for r in spec.get("slice_rules") or []],
                "hand_slices": spec.get("hand_slices") or []}

    def _question(self, test_id: str, rule, channels, params: dict) -> Result:
        flights = params.pop("flights", None)
        references = params.pop("references", None)
        windows = params.pop("windows", None)
        prominence_min = float(params.pop("prominence_min", 0.2))
        s = self._set(rule, flights)
        out = run_now(_api.run_question(
            self._ws.dir, DISK, test_id=test_id, selection=s["selection"], slice_rules=s["slice_rules"],
            hand_slices=s["hand_slices"], channels=list(channels or []), params=params, references=references,
            windows=windows, prominence_min=prominence_min, engine_cfg=self._ws.profile or None,
            assignments=self._ws._assignments, cache=self._ws._cache()))
        self._ws.touched.update(r.get("flight") for r in (out.get("block") or {}).get("per_slice") or []
                                if r.get("flight"))
        if hasattr(self._ws, "used"):
            self._ws.used(channels, test_id)
        return Result(out)

    def cycling(self, rule="full_power", channel: str = "rpm", **params) -> Result:
        return self._question("cycling", rule, [channel], params)

    def coupling(self, rule="full_power", channels=("rpm", "map_inhg"), **params) -> Result:
        return self._question("coupling", rule, list(channels), params)

    def groups(self, rule="full_power", descriptor: str = "rpm.swing", by: Any = "source", **params) -> Result:
        split = dict(by) if isinstance(by, dict) else {"by": by}
        for k in ("date", "edges", "groups"):
            if k in params:
                split[k] = params.pop(k)
        params = {**params, "descriptor": descriptor, "split": split}
        return self._question("groups", rule, [descriptor.split(".", 1)[0]], params)

    def unusual(self, rule="full_power", channels: Optional[list] = None, **params) -> Result:
        return self._question("unusual", rule, list(channels or []), params)

    def compare(self, rule="full_power", channels: Optional[list] = None, flights: Optional[list] = None,
                pinned: Optional[str] = None, collapse: bool = False, windows: Optional[dict] = None) -> pd.DataFrame:
        s = self._set(rule, flights)
        out = run_now(_api.compare(self._ws.dir, DISK, selection=s["selection"], slice_rules=s["slice_rules"],
                                   hand_slices=s["hand_slices"], channels=list(channels or ["rpm", "map_inhg"]),
                                   windows=windows, pinned=pinned, collapse=collapse,
                                   engine_cfg=self._ws.profile or None, assignments=self._ws._assignments,
                                   cache=self._ws._cache()))
        df = pd.DataFrame(out.get("rows") or [])
        df.attrs.update({k: out.get(k) for k in ("row_count", "flight_count", "flights_without", "deltas")})
        self._ws.touched.update(r.get("flight") for r in out.get("rows") or [] if r.get("flight"))
        return df

    def signal(self, flight: str, start_s=None, end_s=None, channels: Optional[list] = None, **kw) -> dict:
        """The Signal view's analysis of one flight (and a window): its
        descriptors, numbers with OM references and diagnostics."""
        from ..research.signal import analyze_signal
        window = None if start_s is None and end_s is None else {"start_s": start_s or 0, "end_s": end_s}
        self._ws.touched.add(flight)
        return run_now(analyze_signal(self._ws.dir, DISK, flight, channels=channels, window=window,
                                      engine_cfg=self._ws.profile or None, assignments=self._ws._assignments,
                                      include_values=False, **kw))

    # ── the log view (§5.2) ──
    def logview(self, flight: str, start_s: float, end_s: float, channels=("rpm", "map_inhg"),
                marks: Optional[list] = None, title: Optional[str] = None, rule: Optional[str] = None,
                caption: Optional[str] = None) -> LogView:
        import matplotlib.pyplot as plt
        from .. import flight_ident as fi
        from .. import workspace as ws
        channels = list(channels or ["rpm"])
        df = self._ws.load_flight(flight, channels, start_s, end_s)
        if hasattr(self._ws, "used"):
            self._ws.used(channels)
        fa = ws.load_flight_analysis(self._ws.dir, flight)
        ident = fi.load(self._ws.dir, flight) or {}
        marks = [(float(m[0]), str(m[1])) if isinstance(m, (list, tuple)) else (float(m["t_s"]), str(m.get("label", "")))
                 for m in marks or []]
        fig, axes = plt.subplots(len(channels), 1, sharex=True, figsize=(8, 1.6 * len(channels) + 0.6), squeeze=False)
        for ax, ch in zip(axes[:, 0], channels):
            if ch in df.columns:
                ax.plot(df.index, df[ch], linewidth=0.9)
            else:
                ax.text(0.5, 0.5, f"{ch}: not in this log", transform=ax.transAxes, ha="center")
            ax.set_ylabel(ch, fontsize=8)
            ax.grid(alpha=0.3)
            for t, label in marks:
                ax.axvline(t, color="black", linewidth=0.8, linestyle="--")
        for t, label in marks:
            axes[0, 0].annotate(label, (t, 1.0), xycoords=("data", "axes fraction"), fontsize=7, rotation=0,
                                ha="left", va="bottom")
        when = fi.window_label(ident or None, start_s, end_s)
        axes[-1, 0].set_xlabel("seconds into the flight")
        fig.suptitle(title or f"{flight} · {when}", fontsize=9)
        fig.tight_layout()
        ref = {"flight": flight, "flight_date_local": ident.get("local_date") or (fa.header.get("date") if fa else None),
               "start_s": start_s, "end_s": end_s, "channels": channels,
               "marks": [{"t_s": t, "label": label} for t, label in marks], "title": title,
               "window_label": when}
        if rule:
            ref["rule"] = rule
        if caption and str(caption).strip():
            ref["caption"] = " ".join(str(caption).split())
        plt.close(fig)
        return LogView(ref, fig)

    # ── documents (D11) ──
    def document(self, name: str):
        from pathlib import Path
        from . import documents as D
        D.READ_ONLY = True
        return D.Document(list(self._req.get("documents_dirs") or []), Path(self._req.get("data_root") or "."), name)

