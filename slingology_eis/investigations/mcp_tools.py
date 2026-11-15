"""
The MCP tool surface (Spec 16 §4.2): a curated façade over the host.

Every tool is a thin mapping onto one Spec 01 operation (series_get, one
or two): it calls the operation through `call(op, params)` — the host's
own dispatch, the rules every transport shares — and shapes the
operation's JSON with the tool's documented trim. Nothing here computes
an analysis; a tool that needs something no operation answers is a
missing operation, not façade code.

The trims, which the parity test re-applies to the operations' JSON:

  PAGE_ROWS            50 rows per page (flights, fleet rows, slices, rows, table rows)
  SERIES_MAX_POINTS    600 points per channel; ≤ that many seconds come back every row,
                       a longer window as the min/max envelope (Spec 07 §11.2)
  SERIES_MAX_CHANNELS  6
  SAMPLES_MAX_VALUES   6000 values (slices × seconds × channels) per samples_get
  CODE_STREAM_CHARS    8000 characters of stdout/stderr per code cell, head kept
  CODE_FIGURES         4 figures returned as PNG images (all are kept in the study)
  PERIODOGRAM_PEAKS    5 strongest periods per channel; the detrended series, ACF and
                       lag curve are dropped (the UI draws them; the numbers stay)
  STRIP_RUNS           40 lit runs per channel (rolling strips → where it cycles)
  TEXT_CHARS           2000 characters of a stored cell's markdown or stream in study_read

Every result is wrapped as {engine_version, workspace_id, result}. With no
workspace open, every tool answers the same "no workspace yet" text.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

PAGE_ROWS = 50
SERIES_MAX_POINTS = 600
SERIES_MAX_CHANNELS = 6
SAMPLES_MAX_VALUES = 6000
CODE_STREAM_CHARS = 8000
CODE_FIGURES = 4
PERIODOGRAM_PEAKS = 5
STRIP_RUNS = 40
TEXT_CHARS = 2000

NO_WORKSPACE = ("No workspace yet — open the EIS pages at http://127.0.0.1:8420, create a workspace "
                "and import your logs; then ask again.")

Call = Callable[[str, dict], Any]


class ToolRefusal(Exception):
    """A request the tool won't answer as asked (a cap), with why and what to ask instead."""


@dataclass
class Tool:
    name: str
    title: str
    description: str
    properties: dict
    run: Callable[[dict, Call], Any]
    required: tuple = ()
    writes: bool = False
    destructive: bool = False
    images: Optional[Callable[[Any], list]] = None   # extra image blocks (code_run's figures)
    ops: tuple = field(default_factory=tuple)          # the operations it maps onto, for the spec table

    def definition(self) -> dict:
        return {
            "name": self.name, "title": self.title, "description": self.description,
            "inputSchema": {"type": "object", "properties": self.properties, "required": list(self.required),
                            "additionalProperties": False},
            "annotations": {"title": self.title, "readOnlyHint": not self.writes,
                            "destructiveHint": self.destructive, "idempotentHint": not self.writes,
                            "openWorldHint": False},
        }


# ── shared shaping ─────────────────────────────────────────────────────────

def page(items: list, args: dict, key: str = "rows") -> dict:
    """A page of at most PAGE_ROWS items: offset/limit from the arguments."""
    offset = max(0, int(args.get("offset") or 0))
    limit = max(1, min(PAGE_ROWS, int(args.get("limit") or PAGE_ROWS)))
    chunk = items[offset:offset + limit]
    nxt = offset + len(chunk)
    return {"total": len(items), "offset": offset, key: chunk, "next_offset": nxt if nxt < len(items) else None}


def _clip(text: Optional[str], n: int) -> tuple[Optional[str], bool]:
    if text is None or len(text) <= n:
        return text, False
    return text[:n] + f"\n[… {len(text) - n} more characters]", True


def _selection(args: dict) -> dict:
    return {"mode": "flights", "flights": list(args["flights"])} if args.get("flights") else {"mode": "all"}


def _set_params(args: dict) -> dict:
    """The slice-set parameters every Instrument tool shares (Spec 06 §11)."""
    p: dict = {"selection": _selection(args)}
    for a, k in (("slice_rules", "slice_rules"), ("hand_slices", "hand_slices"), ("channels", "channels"),
                 ("reference", "reference"), ("study_id", "study_id")):
        if args.get(a) is not None:
            p[k] = args[a]
    return p


# ── Raw material ───────────────────────────────────────────────────────────

def flight_row(f: dict) -> dict:
    """One flights_list row: local times (§4.7), the route from GPS, the
    counts, the pilot's name — no UTC (F8)."""
    h, s, i = f.get("header") or {}, f.get("summary") or {}, f.get("ident") or {}
    facts = dict(s.get("facts") or {})
    if i.get("max_altitude_ft") is not None:
        facts["max_altitude_ft"] = round(i["max_altitude_ft"])
    return {"flight_id": f["flight_id"], "date": i.get("local_date") or h.get("date"),
            "start_local": i.get("start_local"), "end_local": i.get("end_local"), "tz": i.get("tz_abbrev"),
            "route": "–".join(i.get("route") or []) or None, "dep_airport": i.get("dep_airport"),
            "arr_airport": i.get("arr_airport"), "takeoffs": i.get("takeoffs"), "landings": i.get("landings"),
            "name": f.get("name"), "engine_hours_start": h.get("engine_hours_start"),
            "engine_hours_end": h.get("engine_hours_end"), "source": s.get("source"),
            "source_filename": f.get("source_filename"), **facts, "phase_min": s.get("phase_min"),
            "events": s.get("events"), "quality_notes": len(f.get("quality") or [])}


def shape_flights(args: dict, flights: list) -> dict:
    rows = [flight_row(f) for f in flights]

    def keep(r: dict) -> bool:
        if args.get("date_from") and (r["date"] or "") < args["date_from"]:
            return False
        if args.get("date_to") and (r["date"] or "") > args["date_to"]:
            return False
        if args.get("source") and r["source"] != args["source"]:
            return False
        if args.get("airport"):
            want = str(args["airport"]).upper()
            if want not in {(r["dep_airport"] or "").upper(), (r["arr_airport"] or "").upper()} \
                    and want not in (r["route"] or "").upper().split("–"):
                return False
        hrs = r["engine_hours_start"]
        if args.get("hours_min") is not None and (hrs is None or hrs < args["hours_min"]):
            return False
        if args.get("hours_max") is not None and (hrs is None or hrs > args["hours_max"]):
            return False
        return True
    rows = sorted((r for r in rows if keep(r)), key=lambda r: (r["start_local"] or r["date"] or "", r["flight_id"]))
    return page(rows, args, "flights")


def run_flights_list(args: dict, call: Call) -> dict:
    p = {"summary": True, "identify": True}
    if args.get("name"):
        p["name"] = args["name"]
    return shape_flights(args, call("list_flights", p))


def run_flights_find(args: dict, call: Call) -> dict:
    p = {"description": args.get("description")}
    if args.get("limit"):
        p["limit"] = args["limit"]
    return call("flights_find", p)


def shape_flight(args: dict, g: dict) -> dict:
    fa = g["flight_analysis"]
    phase_min: dict = {}
    for p in fa.get("phases") or []:
        phase_min[p["phase"]] = round(phase_min.get(p["phase"], 0.0) + (p["end_s"] - p["start_s"]) / 60.0, 1)
    ev_keys = ("event_id", "source", "label", "param", "severity", "limit_type", "limit_value", "observed_value",
               "excess", "unit", "start_utc", "elapsed_s", "duration_s", "note")
    topics = []
    for t in (g.get("insight_set") or {}).get("topics") or []:
        if not t.get("enabled", True):
            continue
        topics.append({"topic_id": t["topic_id"], "analysis": (t.get("analysis") or {}).get("text"),
                       "insights": [{"id": i.get("id"), "severity": i.get("severity"),
                                     "message": (i.get("message") or {}).get("text")} for i in t.get("insights") or []],
                       "triggers": [{"type": s.get("type"), "met": s.get("met"), "detail": s.get("detail")}
                                    for s in t.get("trigger_status") or []]})
    return {"flight_id": fa["flight_id"], "header": fa.get("header"), "source_filename": g.get("source_filename"),
            "phases": fa.get("phases"), "phase_min": phase_min,
            "facts": {k: {"value": (v or {}).get("value"), "unit": (v or {}).get("unit")}
                      for k, v in (fa.get("metrics") or {}).items()},
            "events": [{k: e.get(k) for k in ev_keys if e.get(k) is not None} for e in fa.get("exceedances") or []],
            "available_channels": fa.get("available_channels"), "quality": fa.get("quality"),
            "topics": topics, "reference_state": g.get("reference_state")}


def run_flight_get(args: dict, call: Call) -> dict:
    return shape_flight(args, call("get_flight", {"flight_id": args["flight_id"]}))


def _series_params(args: dict) -> dict:
    chans = list(args.get("channels") or [])
    if not chans:
        raise ToolRefusal("Name the channels (see flight_get's available_channels), at most "
                          f"{SERIES_MAX_CHANNELS}.")
    if len(chans) > SERIES_MAX_CHANNELS:
        raise ToolRefusal(f"At most {SERIES_MAX_CHANNELS} channels per call; ask again in groups.")
    p = {"flight_id": args["flight_id"], "channels": chans, "max_points": SERIES_MAX_POINTS}
    if args.get("start_s") is not None:
        p["start_s"] = float(args["start_s"])
    if args.get("end_s") is not None:
        p["end_s"] = float(args["end_s"])
    return p


def shape_series(args: dict, raw: dict, p: dict) -> dict:
    windowed = "start_s" in p or "end_s" in p
    last = max((pts[-1][0] for pts in raw.values() if pts), default=0.0)
    if not windowed and last > SERIES_MAX_POINTS:
        raise ToolRefusal(
            f"This flight is {last:.0f} s long; without a window that is more than the {SERIES_MAX_POINTS}-point "
            f"cap per channel. Give start_s and end_s (from flight_get's phases or events): a window of up to "
            f"{SERIES_MAX_POINTS} s comes back at every 1-second row; a longer one as a min/max envelope of "
            f"{SERIES_MAX_POINTS} points per channel.")
    span = (p.get("end_s", last) - p.get("start_s", 0.0)) if windowed else last
    return {"flight_id": args["flight_id"], "window": {"start_s": p.get("start_s"), "end_s": p.get("end_s")},
            "decimated": span > SERIES_MAX_POINTS,
            "channels": {ch: {"t_s": [pt[0] for pt in pts], "value": [pt[1] for pt in pts]} for ch, pts in raw.items()},
            "missing_channels": [c for c in p["channels"] if c not in raw]}


def run_series_get(args: dict, call: Call) -> dict:
    p = _series_params(args)
    return shape_series(args, call("get_flight_series", p), p)


def _fleet_points(fleet: dict) -> dict:
    """flight_id → {date, engine_hours, metric values} from the fleet's points."""
    rows: dict = {}
    for mid, m in (fleet.get("metrics") or {}).items():
        for pt in m.get("points") or []:
            r = rows.setdefault(pt["flight_id"], {"flight_id": pt["flight_id"], "date": pt.get("date"),
                                                  "engine_hours": pt.get("x")})
            r[mid] = pt.get("value")
    return rows


def _metric_brief(m: dict) -> dict:
    b, t, s = m.get("baseline") or {}, m.get("trend") or {}, m.get("shift")
    return {"metric_id": m["metric_id"],
            "baseline": {k: b.get(k) for k in ("n", "mean", "std", "min", "max")},
            "trend": {k: t.get(k) for k in ("n", "slope", "r_squared", "direction")},
            "outliers": m.get("outliers") or [], "shift": s}


def shape_fleet_metrics(args: dict, fleet: dict) -> dict:
    metrics = fleet.get("metrics") or {}
    want = list(args.get("metrics") or [k for k in sorted(metrics) if not k.startswith("limit_")])
    unknown = [k for k in want if k not in metrics]
    rows = [{k: r.get(k) for k in ("flight_id", "date", "engine_hours", *want)}
            for r in _fleet_points(fleet).values()]
    if args.get("flights"):
        rows = [r for r in rows if r["flight_id"] in set(args["flights"])]
    rows.sort(key=lambda r: (r["engine_hours"] is None, r["engine_hours"] or 0.0, r["flight_id"]))
    out = page(rows, args, "rows")
    out.update({"metrics": [_metric_brief(metrics[k]) for k in want if k in metrics], "unknown_metrics": unknown,
                "available_metrics": sorted(metrics), "excluded": fleet.get("excluded")})
    return out


def run_fleet_metrics(args: dict, call: Call) -> dict:
    return shape_fleet_metrics(args, call("get_fleet", {}))


def shape_trends(args: dict, fleet: dict) -> dict:
    metrics = fleet.get("metrics") or {}
    ranked = []
    for c in fleet.get("change_summary") or []:
        brief = _metric_brief(metrics[c["metric_id"]]) if c["metric_id"] in metrics else {"metric_id": c["metric_id"]}
        ranked.append({**c, **brief})
    return {"change_summary": ranked, "shift_history": fleet.get("shift_history") or [],
            "flights": len(fleet.get("flight_ids") or []), "excluded": fleet.get("excluded")}


def run_trends_summary(args: dict, call: Call) -> dict:
    return shape_trends(args, call("get_fleet", {}))


# ── Instrument (Spec 06 §11) ───────────────────────────────────────────────

def run_presets_list(args: dict, call: Call) -> dict:
    return call("list_slice_presets", {})


def shape_slices(args: dict, ss: dict) -> dict:
    out = {k: ss.get(k) for k in ("count", "flights_selected", "flights_with_slices", "by_source", "windows",
                                  "missing_flights", "unreachable_flights", "selection")}
    out["rules"] = [{"rule_id": r.get("rule_id"), "name": r.get("name")} for r in ss.get("rules") or []]
    out.update(page([{k: s.get(k) for k in ("slice_id", "flight", "rule_id", "kind", "label", "start_s", "end_s",
                                            "context", "descriptors")} for s in ss.get("slices") or []],
                    args, "slices"))
    return out


def run_slices_build(args: dict, call: Call) -> dict:
    return shape_slices(args, call("build_slices", _set_params(args)))


def shape_samples(args: dict, raw: dict) -> dict:
    n = sum(len(s.get("t") or []) * max(1, len(s.get("channels") or {})) for s in raw.get("slices") or [])
    if n > SAMPLES_MAX_VALUES:
        raise ToolRefusal(
            f"These slices hold {n} values; the cap is {SAMPLES_MAX_VALUES}. Name fewer slice_ids (slices_build "
            f"lists them), fewer channels, or use code_run's load_slice_samples, which has no cap.")
    return raw


def run_samples_get(args: dict, call: Call) -> dict:
    p = _set_params(args)
    p.pop("reference", None)
    if args.get("slice_ids"):
        p["slice_ids"] = list(args["slice_ids"])
    p["anchor"] = args.get("anchor") or "crossing"
    return shape_samples(args, call("get_slice_samples", p))


def shape_question(args: dict, r: dict) -> dict:
    block = r.get("block") or {}
    table = (r.get("evidence") or {}).get("table") or {}
    out = {k: r.get(k) for k in ("test_id", "question", "finding", "magnitude", "caveats")}
    out.update({"summary": block.get("summary"), "params": block.get("params"),
                "slice_set": block.get("slice_set"), "references": block.get("references"),
                "columns": [c.get("id", c.get("label")) if isinstance(c, dict) else c for c in table.get("columns") or []]})
    out.update(page(table.get("rows") or [], args, "rows"))
    return out


def run_question_run(args: dict, call: Call) -> dict:
    p = _set_params(args)
    p["test_id"] = args["test_id"]
    if args.get("params"):
        p["params"] = args["params"]
    return shape_question(args, call("run_test", p))


def _lit_runs(strip: dict) -> list:
    """The seconds a rolling strip is lit (prominent), as runs."""
    lit, per, sw = strip.get("prominent") or [], strip.get("period_s") or [], strip.get("swing") or []
    runs, i, n = [], 0, len(lit)
    while i < n:
        if not lit[i]:
            i += 1
            continue
        j = i
        while j < n and lit[j]:
            j += 1
        ps = sorted(p for p in per[i:j] if p is not None)
        ss = [s for s in sw[i:j] if s is not None]
        runs.append({"start_s": i, "end_s": j, "period_s": ps[len(ps) // 2] if ps else None,
                     "swing_max": max(ss) if ss else None})
        i = j
    return runs


def _peaks(pg: dict) -> list:
    per, pw = pg.get("period_s") or [], pg.get("power") or []
    idx = [k for k in range(1, len(pw) - 1) if pw[k] is not None and pw[k] >= (pw[k - 1] or 0) and pw[k] >= (pw[k + 1] or 0)]
    idx.sort(key=lambda k: -pw[k])
    return [{"period_s": per[k], "power": pw[k]} for k in idx[:PERIODOGRAM_PEAKS]]


def shape_signal(args: dict, a: dict) -> dict:
    out = {k: a.get(k) for k in ("flight_id", "duration_s", "source", "start_time", "date", "channels",
                                 "missing_channels", "reference", "filled", "prominence_min", "om_limits",
                                 "strip_windows")}
    out["phases"] = a.get("phases")
    out["lit_runs"] = {ch: (lambda rs: {"runs": rs[:STRIP_RUNS], "total": len(rs)})(_lit_runs(st))
                       for ch, st in (a.get("strips") or {}).items()}
    w = a.get("window")
    if w:
        diag = {}
        for ch, d in (w.get("diagnostics") or {}).items():
            diag[ch] = {k: d.get(k) for k in ("period_s", "period_ls_s", "best_lag_s") if k in d}
            if d.get("periodogram"):
                diag[ch]["periodogram_peaks"] = _peaks(d["periodogram"])
            if d.get("lag_curve") and d.get("best_lag_s") is not None:
                diag[ch]["corr_at_best_lag"] = next((c.get("corr") for c in d["lag_curve"]
                                                     if c.get("lag_s") == d["best_lag_s"]), None)
        out["window"] = {k: w.get(k) for k in ("start_s", "end_s", "duration_s", "context", "descriptors", "windows",
                                               "numbers", "derived_rule")}
        out["window"]["diagnostics"] = diag
    return out


def run_signal_analyze(args: dict, call: Call) -> dict:
    p = {"flight_id": args["flight_id"], "include_values": False, "include_strips": bool(args.get("strips", True))}
    for k in ("channels", "reference", "rule_channel", "references"):
        if args.get(k) is not None:
            p[k] = args[k]
    if args.get("start_s") is not None or args.get("end_s") is not None:
        p["window"] = {"start_s": args.get("start_s", 0), "end_s": args.get("end_s")}
    return shape_signal(args, call("analyze_signal", p))


def shape_compare(args: dict, c: dict) -> dict:
    out = {k: c.get(k) for k in ("row_count", "slice_count", "flight_count", "flights_without", "pinned", "collapsed",
                                 "channels", "reference", "windows", "deltas", "om_limits", "by_source",
                                 "missing_flights", "unreachable_flights", "selection")}
    out["groups"] = [{k: g.get(k) for k in ("flight", "date", "source", "count")} for g in c.get("groups") or []]
    out.update(page(c.get("rows") or [], args, "rows"))
    return out


def run_rows_compare(args: dict, call: Call) -> dict:
    p = _set_params(args)
    if args.get("pinned"):
        p["pinned"] = args["pinned"]
    if args.get("collapse"):
        p["collapse"] = True
    return shape_compare(args, call("compare_rows", p))


# ── Bench ──────────────────────────────────────────────────────────────────

def _trim_outputs(outputs: list, stream_chars: int) -> list:
    out = []
    for o in outputs or []:
        o = dict(o)
        if o.get("kind") == "text":
            o["text"], cut = _clip(o.get("text"), stream_chars)
            if cut:
                o["clipped"] = True
        elif o.get("kind") == "table":
            rows = o.get("rows") or []
            if len(rows) > PAGE_ROWS:
                o["rows"], o["truncated"] = rows[:PAGE_ROWS], True
        elif o.get("kind") == "error":
            tb = o.get("traceback") or ""
            lines = tb.splitlines() if isinstance(tb, str) else list(tb)
            if len(lines) > 20:
                o["traceback"] = "\n".join(["[…]"] + lines[-20:]) if isinstance(tb, str) else lines[-20:]
        out.append(o)
    return out


def shape_code_run(args: dict, r: dict) -> dict:
    cell = r["cell"]
    return {"study_id": r["study_id"], "cell_id": cell["id"], "status": (cell.get("ran") or {}).get("status"),
            "ran": cell.get("ran"), "outputs": _trim_outputs(cell.get("outputs"), CODE_STREAM_CHARS),
            "figures_returned": [ref for ref in list(r.get("previews") or {})[:CODE_FIGURES]]}


def code_run_images(r: dict) -> list:
    return [{"type": "image", "data": b64, "mimeType": "image/png"}
            for _ref, b64 in list((r.get("previews") or {}).items())[:CODE_FIGURES]]


def run_code_run(args: dict, call: Call) -> dict:
    p = {"study_id": args["study_id"], "source": args["source"]}
    for k in ("cell_id", "timeout_s", "memory_mb"):
        if args.get(k) is not None:
            p[k] = args[k]
    return call("code_run", p)


# ── Context ────────────────────────────────────────────────────────────────

def run_profile_get(args: dict, call: Call) -> dict:
    return call("get_engine_limits", {})


def run_aircraft_get(args: dict, call: Call) -> dict:
    return call("aircraft_get", {})


def run_documents_list(args: dict, call: Call) -> dict:
    return call("documents_list", {})


def run_document_read(args: dict, call: Call) -> dict:
    p = {"name": args["name"]}
    for k in ("page", "pages", "find"):
        if args.get(k) is not None:
            p[k] = args[k]
    return call("document_read", p)


def shape_journal(args: dict, j: dict) -> dict:
    keep = ("id", "kind", "ref_id", "what", "where", "reason", "note", "created_at", "updated_at", "effect", "current")
    out = {k: v for k, v in j.items() if k != "entries"}
    out.update(page([{k: e.get(k) for k in keep} for e in j.get("entries") or []], args, "entries"))
    return out


def run_journal_list(args: dict, call: Call) -> dict:
    return shape_journal(args, call("get_journal", {}))


def run_studies_list(args: dict, call: Call) -> dict:
    return call("list_studies", {})


def shape_study(args: dict, doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k not in ("cache", "cells", "tests")}
    out["tests"] = [{**{k: v for k, v in t.items() if k != "result"},
                     "result": shape_question({}, t["result"]) if t.get("result") else None}
                    for t in doc.get("tests") or []]
    cells = []
    for c in doc.get("cells") or []:
        c = dict(c)
        if c.get("kind") == "markdown":
            c["source"], _ = _clip(c.get("source"), TEXT_CHARS)
        for k in ("outputs", "pending_outputs"):
            if c.get(k):
                c[k] = _trim_outputs(c[k], TEXT_CHARS)
        cells.append(c)
    if doc.get("cells") is not None:
        out["cells"] = cells
    for t in out["tests"]:
        if t["result"]:
            t["result"]["rows"] = t["result"]["rows"][:10]
    return out


def run_study_read(args: dict, call: Call) -> dict:
    return shape_study(args, call("load_study", {"study_id": args["study_id"]}))


# ── Record ─────────────────────────────────────────────────────────────────

def run_study_create(args: dict, call: Call) -> dict:
    study = {"name": args["name"], "kind": args.get("kind") or "investigation", "author": "claude",
             "question": args.get("question"), "cells": [], "selection": _selection(args)}
    if args.get("inbox_candidate"):
        study["inbox_candidate"] = args["inbox_candidate"]
    if args.get("engine_type"):
        study["engine_type"] = args["engine_type"]
    saved = call("save_study", {"study": study})
    return {"study_id": saved["study_id"], "name": saved["name"], "kind": saved.get("kind"),
            "question": saved.get("question"), "inbox_candidate": saved.get("inbox_candidate")}


def run_cell_append(args: dict, call: Call) -> dict:
    cell = {k: args[k] for k in ("kind", "source", "role", "test_id", "params", "channels", "slices", "ref", "title")
            if args.get(k) is not None}
    r = call("study_cells_append", {"study_id": args["study_id"], "cell": cell})
    return shape_cell_append(args, r)


def shape_cell_append(args: dict, r: dict) -> dict:
    out = dict(r)
    if isinstance(out.get("cell"), dict) and out["cell"].get("outputs"):
        out["cell"] = {**out["cell"], "outputs": _trim_outputs(out["cell"]["outputs"], CODE_STREAM_CHARS)}
    if isinstance(out.get("result"), dict):
        out["result"] = shape_question({}, out["result"])
    out.pop("study", None)
    return out


def run_study_finish(args: dict, call: Call) -> dict:
    p = {k: args[k] for k in ("study_id", "summary", "inbox_candidate", "resolution", "note", "journal", "finding")
         if args.get(k) is not None}
    return call("study_finish", p)


def run_inbox_list(args: dict, call: Call) -> dict:
    p = {}
    if args.get("status"):
        p["status"] = args["status"]
    return call("inbox_list", p)


def run_inbox_resolve(args: dict, call: Call) -> dict:
    return call("inbox_resolve", {k: args[k] for k in ("candidate_id", "status", "study_id", "note")
                                  if args.get(k) is not None})


# ── schemas ────────────────────────────────────────────────────────────────

_S = {"type": "string"}
_N = {"type": "number"}
_I = {"type": "integer", "minimum": 0}
_STRS = {"type": "array", "items": {"type": "string"}}
_PAGE = {"offset": {**_I, "description": "First row (default 0)"},
         "limit": {"type": "integer", "minimum": 1, "maximum": PAGE_ROWS, "description": f"Rows (≤ {PAGE_ROWS})"}}
_RULES = {"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "object"}]},
          "description": "Slice rules: a preset id (presets_list), \"phase:CLIMB\", or a Spec 06 §5.1 rule object"}
_SET = {"slice_rules": _RULES,
        "hand_slices": {"type": "array", "items": {"type": "object"},
                        "description": "Hand slices: {flight, start_s, end_s, label?}"},
        "flights": {**_STRS, "description": "Flight ids (default: every flight)"},
        "channels": {**_STRS, "description": "Channels (default rpm, map_inhg)"},
        "study_id": {**_S, "description": "Use this study's descriptor cache"}}

TOOLS: list[Tool] = [
    Tool("flights_list", "List flights",
         "The workspace's flights, oldest first: local date and start/end time with the zone, route (airports "
         "resolved from GPS), takeoffs and landings, the pilot's name, engine hours, source (G3X or AXIS), flight "
         "facts, minutes per phase and event count. Filters: date_from/date_to (local YYYY-MM-DD), source, "
         "airport (any airport on the route), name (words in the pilot's name or notes), hours_min/hours_max; "
         f"{PAGE_ROWS} per page. Example: {{\"airport\": \"KBLI\", \"date_from\": \"2026-10-01\"}}.",
         {"date_from": {**_S, "description": "Local date YYYY-MM-DD"}, "date_to": {**_S, "description": "Local date YYYY-MM-DD"},
          "source": {"type": "string", "enum": ["G3X", "AXIS"]},
          "airport": {**_S, "description": "An airport code on the route, e.g. KBLI"},
          "name": {**_S, "description": "Words in the flight's name or notes"}, "hours_min": _N, "hours_max": _N,
          **_PAGE}, run_flights_list, ops=("list_flights",)),
    Tool("flights_find", "Find a flight",
         "Flights for a description in words, best first (at most 10), each with what matched: dates (\"Oct 24\", "
         "\"2026-10-24\", \"last Friday\", a month or weekday), airports by code or name (\"KBLI\", \"Bellingham\"), "
         "counts (\"three landings\", \"two stops\", \"touch and go\"), words of the pilot's flight name. "
         "Example: {\"description\": \"the Oct 24 flight with three landings, Bellingham\"}.",
         {"description": _S, "limit": {"type": "integer", "minimum": 1, "maximum": 10}}, run_flights_find,
         required=("description",), ops=("flights_find",)),
    Tool("flight_get", "One flight",
         "One flight: header, phases, flight facts, events (limit exceedances and CAS) and the topic findings the "
         "Flight view shows.", {"flight_id": _S}, run_flight_get, required=("flight_id",), ops=("get_flight",)),
    Tool("series_get", "Channel series",
         f"Channels of one flight over a window (seconds from the log's start). At most {SERIES_MAX_CHANNELS} channels; "
         f"a window of up to {SERIES_MAX_POINTS} s comes back at every row, a longer one as a {SERIES_MAX_POINTS}-point "
         "min/max envelope per channel. Without a window it answers only for a flight that short.",
         {"flight_id": _S, "channels": _STRS, "start_s": _N, "end_s": _N}, run_series_get,
         required=("flight_id", "channels"), ops=("get_flight_series",)),
    Tool("fleet_metrics", "Per-flight metrics",
         f"The Spec 12 per-flight metrics table (one row per flight, ordered by engine hours) with each metric's "
         f"baseline, trend, outliers and shift; {PAGE_ROWS} rows per page. Default metrics: all but the limit_* ones.",
         {"metrics": _STRS, "flights": _STRS, **_PAGE}, run_fleet_metrics, ops=("get_fleet",)),
    Tool("trends_summary", "Trends summary",
         "The Trends change summary (ranked metrics with baseline, trend and shift) and the shift history.",
         {}, run_trends_summary, ops=("get_fleet",)),
    Tool("presets_list", "Slice presets",
         "The engine profile's shipped slice rules (Spec 06): id, name, the question each is for, its conditions.",
         {}, run_presets_list, ops=("list_slice_presets",)),
    Tool("slices_build", "Build slices",
         f"The slices a selection and slice rules make, with each slice's context and descriptors; {PAGE_ROWS} per page.",
         {**_SET, **_PAGE}, run_slices_build, ops=("build_slices",)),
    Tool("samples_get", "Slice samples",
         f"The 1 Hz samples of slices, aligned at an anchor (crossing, start, end, peak:CHANNEL). Refuses more than "
         f"{SAMPLES_MAX_VALUES} values — name slice_ids from slices_build.",
         {**_SET, "slice_ids": _STRS, "anchor": _S}, run_samples_get, ops=("get_slice_samples",)),
    Tool("question_run", "Run a question",
         "A Spec 06 test over a slice set — cycling, coupling, groups or unusual — with its finding, magnitude with "
         f"OM references, caveats and the evidence rows ({PAGE_ROWS} per page).",
         {"test_id": {"type": "string", "enum": ["cycling", "coupling", "groups", "unusual"]},
          "params": {"type": "object", "description": "Test parameters (Spec 06 §7)"}, "reference": _S, **_SET, **_PAGE},
         run_question_run, required=("test_id",), ops=("run_test",)),
    Tool("signal_analyze", "Signal view",
         "One flight's rolling strips, summarised as the runs where each channel cycles (lit), and a window's "
         f"descriptors, numbers with OM references and diagnostics (periods, top {PERIODOGRAM_PEAKS} periodogram peaks, "
         "best lag). Without a window, the window is derived from where the reference channel cycles.",
         {"flight_id": _S, "channels": _STRS, "start_s": _N, "end_s": _N, "reference": _S, "rule_channel": _S,
          "strips": {"type": "boolean", "description": "Compute the rolling strips (default true)"}},
         run_signal_analyze, required=("flight_id",), ops=("analyze_signal",)),
    Tool("rows_compare", "Compare rows",
         f"One row per slice, grouped by flight, with deltas to a pinned row; {PAGE_ROWS} rows per page.",
         {**_SET, "reference": _S, "pinned": _S, "collapse": {"type": "boolean"}, **_PAGE},
         run_rows_compare, ops=("compare_rows",)),
    Tool("code_run", "Run Python",
         "Run Python on the bench (numpy, pandas, scipy, matplotlib; helpers flights(), load_flight(), "
         "load_slices(), load_slice_samples(), flight_info(), profile, aircraft, FILES, show()) and keep it as a "
         "code cell in the study — appended, or replacing cell_id. No network, no subprocesses, writes only under "
         f"FILES, time and memory capped. Returns stdout (≤ {CODE_STREAM_CHARS} characters), tables "
         f"(≤ {PAGE_ROWS} rows) and up to {CODE_FIGURES} figures as images.",
         {"study_id": _S, "source": _S, "cell_id": _S,
          "timeout_s": {"type": "number", "minimum": 1, "maximum": 300, "description": "Default 60"},
          "memory_mb": {"type": "number", "minimum": 256, "maximum": 8192, "description": "Default 2048"}},
         run_code_run, required=("study_id", "source"), writes=True, images=code_run_images, ops=("code_run",)),
    Tool("profile_get", "Engine profile",
         "The engine profile: limits with their Operators Manual references.", {}, run_profile_get,
         ops=("get_engine_limits",)),
    Tool("aircraft_get", "Aircraft",
         "The aircraft record: name, airframe, engine serial, propeller, controller, firmware, avionics, the "
         "documents folders; the owner's notes (notes.md) whole; its workspaces; the engine model and the "
         "Settings → Log channels assignments.", {}, run_aircraft_get, ops=("aircraft_get",)),
    Tool("documents_list", "Documents",
         "The documents the user placed in the workspace's documents folder (manuals, service bulletins, notes).",
         {}, run_documents_list, ops=("documents_list",)),
    Tool("document_read", "Read a document",
         "Pages of one document (at most 3 at a time), or the pages where a phrase occurs (find). Never a whole manual.",
         {"name": _S, "page": {"type": "integer", "minimum": 1}, "pages": {"type": "integer", "minimum": 1, "maximum": 3},
          "find": _S}, run_document_read, required=("name",), ops=("document_read",)),
    Tool("journal_list", "Journal",
         f"The Journal entries as the UI shows them; {PAGE_ROWS} per page.", {**_PAGE}, run_journal_list,
         ops=("get_journal",)),
    Tool("studies_list", "Studies", "The studies in the workspace: kind, author, question, status, finding.",
         {}, run_studies_list, ops=("list_studies",)),
    Tool("study_read", "Read a study",
         "One study: its definition, its tests' findings and its notebook cells with their outputs.",
         {"study_id": _S}, run_study_read, required=("study_id",), ops=("load_study",)),
    Tool("study_create", "Start a study",
         "Start a notebook study (an investigation) for a question; cells are added with code_run and cell_append.",
         {"name": _S, "question": _S, "kind": {"type": "string", "enum": ["investigation", "question-for-type"]},
          "inbox_candidate": {**_S, "description": "The inbox candidate this investigates"},
          "engine_type": _S, "flights": _STRS}, run_study_create, required=("name",), writes=True,
         ops=("save_study",)),
    Tool("cell_append", "Add a cell",
         "Append a cell to a study: markdown (source), a question (test_id, params, channels, own slices; run at "
         "once), or a figure or table a code cell wrote under files/ (ref, title).",
         {"study_id": _S, "kind": {"type": "string", "enum": ["markdown", "question", "figure", "table"]},
          "source": _S, "role": _S, "test_id": _S, "params": {"type": "object"}, "channels": _STRS,
          "slices": {"type": "object", "description": "This question's own {selection, slice_rules, hand_slices}"},
          "ref": _S, "title": _S}, run_cell_append, required=("study_id", "kind"), writes=True,
         ops=("study_cells_append",)),
    Tool("study_finish", "Finish a study",
         "End an investigation with its summary (what was found, what it means, what to do); optionally resolve its "
         "inbox candidate and note the finding in the Journal (the one Journal entry Claude may write).",
         {"study_id": _S, "summary": _S, "inbox_candidate": _S,
          "resolution": {"type": "string", "enum": ["investigating", "nothing-here", "watch", "acted"]},
          "note": _S, "journal": {"type": "boolean"}, "finding": _S}, run_study_finish,
         required=("study_id", "summary"), writes=True, ops=("study_finish",)),
    Tool("inbox_list", "Inbox",
         "The candidates the detectors raised (recurring patterns, stand-out flights, shifts, groups) with evidence "
         "and status; scans first when there are new flights.",
         {"status": {"anyOf": [_S, _STRS]}}, run_inbox_list, ops=("inbox_list",)),
    Tool("inbox_resolve", "Resolve a candidate",
         "Set a candidate's status — investigating, nothing-here, watch, acted (or new) — with its study and a note.",
         {"candidate_id": _S, "status": {"type": "string",
                                         "enum": ["new", "investigating", "nothing-here", "watch", "acted"]},
          "study_id": _S, "note": _S}, run_inbox_resolve, required=("candidate_id", "status"), writes=True,
         ops=("inbox_resolve",)),
]

# ── Session tools (D10): which workspace this conversation's tools see ──
# They act on the server (the conversation), not on a host operation, so
# they aren't in the parity test; nothing they do touches the registry.

def _workspaces_view(server) -> dict:
    from .. import aircraft as AC
    root, _ws, entries = server._registry()
    if root is None:
        return {"aircraft": None, "in_use": None, "workspaces": [], "other_aircraft": []}
    ac = server.aircraft()
    in_use = server.choose_workspace()
    reg = {e.id: e for e in entries}

    def row(wid: str) -> dict:
        e = reg[wid]
        return {"workspace_id": e.id, "name": e.name, "engine_model": e.engine_model,
                "flight_count": e.flight_count, "last_opened_at": e.last_opened_at, "in_use": e.id == in_use}
    others = [{"aircraft_id": a["id"], "name": a["name"], "workspaces": [row(w) for w in a["workspaces"] if w in reg]}
              for a in AC.list_aircraft(root) if not ac or a["id"] != ac["id"]]
    return {"aircraft": {"aircraft_id": ac["id"], "name": ac["name"], "engine_model": ac["engine_model"]} if ac else None,
            "in_use": in_use, "chosen_by": ("workspace_use" if server.use_workspace == in_use and in_use
                                            else "--workspace" if server.workspace_arg else "aircraft"),
            "workspaces": [row(w) for w in (ac["workspaces"] if ac else []) if w in reg],
            "other_aircraft": others}


def call_session_tool(name: str, args: dict, server, *, engine_version: str, workspace_id: Optional[str]) -> dict:
    from .. import serialize
    if workspace_id is None:
        return _error(server.aircraft_error or NO_WORKSPACE)
    if name == "workspaces_list":
        result = _workspaces_view(server)
    else:   # workspace_use
        want = args.get("workspace_id")
        _root, _ws, entries = server._registry()
        match = next((e for e in entries if want in (e.id, e.name)), None) if want else None
        if match is None:
            names = ", ".join(f"{e.name} ({e.id})" for e in entries) or "none"
            return _error(f"workspace_use needs workspace_id, one of: {names}.")
        server.use_workspace = match.id
        workspace_id = server._refresh()
        result = {**_workspaces_view(server),
                  "note": "Only this conversation's following tool calls use it; the EIS pages are unchanged."}
    body = {"engine_version": engine_version, "workspace_id": workspace_id, "result": result}
    text = serialize.dumps(body)
    return {"content": [{"type": "text", "text": text}], "structuredContent": json.loads(text), "isError": False}


def _no_op(args: dict, call: Call) -> Any:
    raise ToolRefusal("a session tool runs in the server")


SESSION_TOOLS = ("workspaces_list", "workspace_use")
TOOLS[:0] = [
    Tool("workspaces_list", "Workspaces",
         "The aircraft's workspaces (and any other aircraft's), with the one these tools use. Usually one: the "
         "server opens the aircraft's workspace without asking.", {}, _no_op, ops=()),
    Tool("workspace_use", "Use a workspace",
         "Use another of the aircraft's workspaces for the rest of this conversation (not the EIS pages). "
         "Example: {\"workspace_id\": \"ws_2b59350ca5ac\"} or the workspace's name.",
         {"workspace_id": _S}, _no_op, required=("workspace_id",), writes=True, ops=()),
]

# code_run's façade result is shaped after the call (the images need the raw result).
_SHAPE_AFTER = {"code_run": shape_code_run}

BY_NAME = {t.name: t for t in TOOLS}


def call_tool(name: str, args: dict, call: Call, *, engine_version: str, workspace_id: Optional[str]) -> dict:
    """One tool call → an MCP CallToolResult: {content, structuredContent, isError}."""
    from .. import serialize
    tool = BY_NAME.get(name)
    if tool is None:
        return _error(f"No tool {name!r}.")
    if workspace_id is None:
        return _error(NO_WORKSPACE)
    missing = [k for k in tool.required if args.get(k) in (None, "", [])]
    if missing:
        return _error(f"{name} needs {', '.join(missing)}.")
    try:
        raw = tool.run(dict(args), call)
        result = _SHAPE_AFTER[name](args, raw) if name in _SHAPE_AFTER else raw
    except ToolRefusal as e:
        return _error(str(e))
    except ToolOpError as e:
        return _error(f"{e.code}: {e.message}")
    body = {"engine_version": engine_version, "workspace_id": workspace_id, "result": result}
    text = serialize.dumps(body)
    content: list = [{"type": "text", "text": text}]
    if tool.images:
        content.extend(tool.images(raw))
    # structuredContent is exactly the text block's JSON (NaN → null, as every transport sends it).
    return {"content": content, "structuredContent": json.loads(text), "isError": False}


class ToolOpError(Exception):
    """An operation's RpcError, as the façade reports it."""
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message


def _error(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": True}
