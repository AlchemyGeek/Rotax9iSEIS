"""
What remains of Session D's notebook study document (Spec 16 v0.4 §5): a
study stored that way is converted to a Jupyter notebook on first load
(`ipynb.convert`), which uses the table renderers below for its old table
outputs; and the S5 fingerprints every export and import uses.

Flights are named by `flight_id` inside a workspace (Spec 06 §3.2). What
leaves it — a notebook zip or `.ipynb` — names them by content fingerprint
instead (Spec 16 §3.1 S5): `src:<source_key>`, the hash of the analysed
log's bytes, which a reader can't derive from a tail number and a date as
they can a flight_id. An import maps each fingerprint back to the flight
here that has that source; one with no such flight keeps it.
"""
from __future__ import annotations

from pathlib import Path


def _table_html(o: dict) -> str:
    esc = lambda v: "" if v is None else str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    head = "".join(f"<th>{esc(c)}</th>" for c in o["columns"])
    body = "".join("<tr>" + "".join(f"<td>{esc(v)}</td>" for v in r) + "</tr>" for r in o["rows"])
    more = f"<p>{o['n_rows'] - len(o['rows'])} more rows not stored</p>" if o.get("truncated") else ""
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>{more}"


def _table_text(o: dict) -> str:
    rows = [o["columns"]] + [["" if v is None else str(v) for v in r] for r in o["rows"]]
    return "\n".join("\t".join(map(str, r)) for r in rows)


# ── ran.flights across the workspace boundary (S5) ─────────────────────────

FP_PREFIX = "src:"


def fingerprints(ws_dir: Path) -> tuple[dict, dict]:
    """(flight_id → its fingerprint, fingerprint → flight_id) for this
    workspace: the analysed source's key, and every source key a flight
    has (an AXIS SD-card log and its aircraft log are one flight)."""
    from .. import workspace as ws
    out, back = {}, {}
    for fid in ws.list_flight_ids(ws_dir):
        src = ws.load_sources(ws_dir, fid)
        imports = list(src.imports) if src else []
        analysed = ws.source_filename(ws_dir, fid)
        keys = [i.source_key for i in imports if i.filename == analysed] + [i.source_key for i in imports]
        fa = ws.load_flight_analysis(ws_dir, fid)
        keys += list((fa.source_keys if fa else None) or [])
        keys = [k for k in dict.fromkeys(keys) if k]
        if keys:
            out[fid] = FP_PREFIX + keys[0]
            for k in keys:
                back.setdefault(FP_PREFIX + k, fid)
    return out, back
