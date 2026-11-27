"""
Evidence outputs (Spec 16 D19, §5.6): what `eis.table`, `eis.figure` and
`eis.logview(…, caption=)` put in a notebook — a table, figure or log view
the reader can read without the code: column names in words, units in the
headers, values rounded, and a caption. The output's metadata carries
`slingology.evidence` `{kind, caption, units?}`; the renderer numbers the
evidence cells (*Table 1*, *Figure 2*, *Log view 3*) and prints the caption
under each — `eis` doesn't number them, so moving a cell never leaves a
stale number.

The same object renders on the bench and in JupyterLab: `_repr_mimebundle_`
returns `(data, metadata)`, as IPython takes it.
"""
from __future__ import annotations

import html
import io
import math
from typing import Optional

TABLE_ROWS = 500
KINDS = ("table", "figure", "logview")

_UNIT_SUFFIX = (("_inhg", "inHg"), ("_psi", "psi"), ("_gph", "gph"), ("_gal", "gal"), ("_fpm", "fpm"),
                ("_kt", "kt"), ("_ft", "ft"), ("_pct", "%"), ("_volts", "V"), ("_amps", "A"), ("_rpm", "rpm"),
                ("_f", "°F"), ("_c", "°C"), ("_s", "s"), ("_min", "min"), ("_h", "h"))
_WORDS = {"id": "id", "pct": "%", "n": "count", "max": "max", "min": "min", "mean": "mean", "median": "median",
          "std": "std", "p95": "95th percentile", "p05": "5th percentile", "swing": "swing", "period": "period"}


class EvidenceError(ValueError):
    pass


def _caption(caption) -> str:
    c = " ".join(str(caption or "").split())
    if not c:
        raise EvidenceError("evidence needs a caption: one line saying what it shows "
                            "(eis.table(df, caption=\"…\"), eis.figure(fig, caption=\"…\"))")
    return c


def _registry():
    from ..channels import CHANNEL_REGISTRY
    return CHANNEL_REGISTRY


def humanise(col: str, units: Optional[dict] = None) -> str:
    """'fuel_press_psi.mean' → 'Fuel pressure mean (psi)'; 'duration_s' →
    'Duration (s)'; a `units` entry for the column wins over the suffix."""
    col = str(col)
    units = units or {}
    base, _, stat = col.partition(".")
    reg = _registry()
    unit = units.get(col)
    if base in reg:
        label = reg[base].description
        unit = unit if unit is not None else reg[base].unit
    else:
        label, found = base, None
        for suf, u in _UNIT_SUFFIX:
            if base.endswith(suf) and len(base) > len(suf):
                label, found = base[:-len(suf)], u
                break
        unit = unit if unit is not None else found
        label = " ".join(_WORDS.get(w, w) for w in label.split("_") if w)
        label = label[:1].upper() + label[1:]
    if stat:
        label += " " + " ".join(_WORDS.get(w, w) for w in stat.split("_"))
    if unit and not (base == "rpm" and unit == "rpm"):
        label += f" ({unit})"
    return label


def _digits_for(values) -> int:
    finite = [abs(v) for v in values if isinstance(v, float) and math.isfinite(v)]
    if not finite:
        return 0
    top = max(finite)
    return 0 if top >= 100 else 1 if top >= 10 else 2


def _fmt(v, digits: Optional[int]) -> str:
    import numpy as np
    import pandas as pd
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    if isinstance(v, (bool, np.bool_)):
        return "yes" if v else "no"
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    if isinstance(v, (float, np.floating)):
        return f"{float(v):,.{digits if digits is not None else 2}f}"
    if isinstance(v, pd.Timestamp):
        return "—" if pd.isna(v) else v.isoformat()
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    return str(v)


class Evidence:
    """One evidence output: `data` (its representations), `meta`
    (`slingology.evidence` and, for a table, `slingology.table`), and the
    figure behind it (`fig`, for the bench's preview)."""

    def __init__(self, data: dict, meta: dict, fig=None):
        self.data, self.meta, self.fig = data, meta, fig

    def _repr_mimebundle_(self, include=None, exclude=None):
        return dict(self.data), {"slingology": dict(self.meta)}

    def __repr__(self) -> str:
        return str(self.data.get("text/plain") or "<evidence>")


def table(df, caption, units: Optional[dict] = None, digits=None) -> Evidence:
    """A frame as evidence: humanised headers with units, values rounded
    (`digits`: one int for every number column, a {column: int} dict, or
    None — by size: 0 decimals from 100, 1 from 10, else 2), the caption."""
    import pandas as pd
    cap = _caption(caption)
    if isinstance(df, pd.Series):
        df = df.to_frame()
    if not isinstance(df, pd.DataFrame):
        raise EvidenceError("eis.table takes a pandas DataFrame (or Series)")
    if not isinstance(df.index, pd.RangeIndex) or df.index.name is not None:
        df = df.reset_index()
    n = len(df)
    head = df.head(TABLE_ROWS)
    cols = [str(c) for c in head.columns]
    per: dict = {}
    for c, src in zip(cols, head.columns):
        vals = [v for v in head[src].tolist()]
        if isinstance(digits, dict):
            per[c] = digits.get(c, _digits_for(vals))
        elif isinstance(digits, int):
            per[c] = digits
        else:
            per[c] = _digits_for(vals)
    heads = [humanise(c, units) for c in cols]
    rows = [[_fmt(v, per[c]) for c, v in zip(cols, row)] for row in head.itertuples(index=False, name=None)]
    more = f"<p>{n - len(rows)} more rows not shown</p>" if n > len(rows) else ""
    body = (f'<table class="eis-table"><caption>{html.escape(cap, quote=False)}</caption><thead><tr>'
            + "".join(f"<th>{html.escape(h, quote=False)}</th>" for h in heads) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{html.escape(v, quote=False)}</td>" for v in r) + "</tr>" for r in rows)
            + f"</tbody></table>{more}")
    widths = [max([len(h)] + [len(r[i]) for r in rows]) for i, h in enumerate(heads)]
    plain = "\n".join([cap, "  ".join(h.rjust(w) for h, w in zip(heads, widths))]
                      + ["  ".join(v.rjust(w) for v, w in zip(r, widths)) for r in rows])
    if n > len(rows):
        plain += f"\n[{n - len(rows)} more rows not shown]"
    ev = {"kind": "table", "caption": cap}
    if units:
        ev["units"] = {str(k): str(v) for k, v in units.items()}
    return Evidence({"text/html": body, "text/plain": plain},
                    {"evidence": ev, "table": {"n_rows": int(n), "n_cols": int(df.shape[1]), "truncated": n > len(rows)}})


def figure(fig, caption) -> Evidence:
    """A matplotlib figure (or Axes) as evidence: its SVG and the caption."""
    import matplotlib
    import matplotlib.pyplot as plt
    cap = _caption(caption)
    if hasattr(fig, "figure") and not hasattr(fig, "savefig"):
        fig = fig.figure
    if not hasattr(fig, "savefig"):
        raise EvidenceError("eis.figure takes a matplotlib figure (fig, from plt.subplots())")
    buf = io.StringIO()
    with matplotlib.rc_context({"svg.hashsalt": "slingology-eis"}):
        fig.savefig(buf, format="svg", metadata={"Date": None}, bbox_inches="tight")
    plt.close(fig)
    return Evidence({"image/svg+xml": buf.getvalue(), "text/plain": f"<Figure: {cap}>"},
                    {"evidence": {"kind": "figure", "caption": cap}}, fig)


def caption_of(o: dict) -> Optional[dict]:
    """An output's evidence mark — `{kind, caption}` — or, for a log view
    written before captions, its title as the caption."""
    ev = ((o.get("metadata") or {}).get("slingology") or {}).get("evidence")
    if ev:
        return {"kind": ev.get("kind") or "table", "caption": ev.get("caption") or ""}
    from .eis_lib import LOGVIEW_MIME
    ref = (o.get("data") or {}).get(LOGVIEW_MIME)
    if isinstance(ref, dict):
        return {"kind": "logview", "caption": str(ref.get("caption") or ref.get("title") or "").strip()}
    return None
