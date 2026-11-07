"""
Renderings of a §8 result that need no UI: plain text (the CLI, and the
acceptance-9 rendering check), the evidence table as CSV, and a static
SVG chart for the `.eisstudy` export and a read-only study.
"""
from __future__ import annotations

import csv
import io
import math
import re
from typing import Optional

# Acceptance 9: words that would turn a description into a judgement.
# None may appear in a finding; anywhere else only on a line that also
# carries its reference.
VERDICT_WORDS = (
    "abnormal", "normal", "fault", "faulty", "defect", "defective", "failure", "failing", "cycling detected",
    "problem", "healthy", "unhealthy", "excessive", "dangerous", "unsafe", "safe", "bad", "good", "ok",
    "anomaly", "anomalous", "warning", "alarm", "concerning", "worrying",
)
# "Normal G" is a channel's name, not a verdict.
_VERDICT_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in VERDICT_WORDS) + r")\b(?! g\b)", re.IGNORECASE)


def verdict_words(text: str) -> list[str]:
    return [m.group(1).lower() for m in _VERDICT_RE.finditer(text or "")]


def _ref_texts(refs: list) -> list[str]:
    return [r.get("text") or f"{r.get('label')}: {r.get('value')}" for r in refs or []]


def render_text(result: dict) -> str:
    """The result as a pilot reads it: question, finding, each magnitude
    beside its references, caveats."""
    lines = [result["question"], "", result["finding"], ""]
    for m in result.get("magnitude") or []:
        refs = _ref_texts(m.get("references"))
        lines.append(f"• {m['label']}: {m.get('text')}" + (f" — beside: {'; '.join(refs)}" if refs else ""))
    lines.append("")
    for c in result.get("caveats") or []:
        lines.append(f"! {c}")
    return "\n".join(lines)


def check_no_verdicts(result: dict) -> list[str]:
    """Acceptance 9: problems with a result's wording (empty when fine)."""
    problems = []
    if verdict_words(result.get("finding", "")):
        problems.append(f"finding uses {verdict_words(result['finding'])}: {result['finding']}")
    for m in result.get("magnitude") or []:
        if not m.get("references"):
            problems.append(f"magnitude without a reference: {m.get('label')}")
        line = f"{m.get('label')} {m.get('text')}"
        if verdict_words(line) and not m.get("references"):
            problems.append(f"verdict word without its reference: {line}")
    return problems


def evidence_csv(result: dict) -> str:
    """The per-slice table, as the evidence package's CSV."""
    table = result["evidence"]["table"]
    cols = [c["key"] for c in table["columns"]]
    keys = ["slice_id"] + [c for c in cols if c != "slice_id"]
    header = ["slice_id"] + [f"{c['label']} ({c['unit']})" if c.get("unit") else c["label"]
                             for c in table["columns"] if c["key"] != "slice_id"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for row in table["rows"]:
        w.writerow(["" if row.get(k) is None else row.get(k) for k in keys])
    return buf.getvalue()


# ── A static chart (no plotting library: the browser has none) ─────────────

def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _chart_values(result: dict) -> tuple[str, list[tuple[str, float, str]]]:
    """(axis label, [(group, value, slice label)]) for the dot chart."""
    tid = result["test_id"]
    rows = result["evidence"]["table"]["rows"]
    cols = {c["key"]: c for c in result["evidence"]["table"]["columns"]}
    if tid == "cycling":
        key, group = "swing", "source"
    elif tid == "coupling":
        key = next((k for k in cols if k.endswith(".corr0")), None)
        group = "source"
    elif tid == "groups":
        key = result["block"]["params"]["descriptor"].split(".", 1)[1]
        group = "group"
    else:
        key, group = "max_abs_z", "source"
    c = cols.get(key, {"label": key})
    axis = f"{c['label']} ({c['unit']})" if c.get("unit") else c["label"]
    out = []
    for r in rows:
        v = r.get(key)
        if isinstance(v, (int, float)) and math.isfinite(v):
            out.append((str(r.get(group) or ""), float(v), str(r.get("start_time") or "")[:16]))
    return axis, out


def chart_svg(result: dict, width: int = 640, height: int = 320) -> str:
    """One dot per slice, grouped (source or split group), with each
    group's median as a bar — the distribution the finding summarises."""
    axis, vals = _chart_values(result)
    groups = list(dict.fromkeys(g for g, _v, _l in vals)) or [""]
    pad_l, pad_r, pad_t, pad_b = 70, 20, 40, 50
    vs = [v for _g, v, _l in vals] or [0.0, 1.0]
    lo, hi = min(vs), max(vs)
    if hi == lo:
        hi, lo = hi + 1, lo - 1
    span = hi - lo
    lo, hi = lo - 0.05 * span, hi + 0.05 * span
    y = lambda v: pad_t + (height - pad_t - pad_b) * (1 - (v - lo) / (hi - lo))
    gw = (width - pad_l - pad_r) / len(groups)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}" font-family="sans-serif" font-size="11">',
             f'<rect width="{width}" height="{height}" fill="white"/>',
             f'<text x="{pad_l}" y="18" font-size="12">{_esc(result["question"])}</text>',
             f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height - pad_b}" stroke="#888"/>']
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        parts.append(f'<text x="{pad_l - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{v:.4g}</text>')
        parts.append(f'<line x1="{pad_l}" y1="{y(v):.1f}" x2="{width - pad_r}" y2="{y(v):.1f}" stroke="#eee"/>')
    parts.append(f'<text x="14" y="{(height - pad_b + pad_t) / 2:.0f}" transform="rotate(-90 14 '
                 f'{(height - pad_b + pad_t) / 2:.0f})" text-anchor="middle">{_esc(axis)}</text>')
    for gi, g in enumerate(groups):
        gv = [v for gg, v, _l in vals if gg == g]
        cx = pad_l + gw * (gi + 0.5)
        for j, v in enumerate(gv):
            jitter = ((j * 37) % 21 - 10) / 10 * gw * 0.3
            parts.append(f'<circle cx="{cx + jitter:.1f}" cy="{y(v):.1f}" r="2.5" fill="#3b6ea8" fill-opacity="0.6"/>')
        if gv:
            med = sorted(gv)[len(gv) // 2] if len(gv) % 2 else sum(sorted(gv)[len(gv) // 2 - 1:len(gv) // 2 + 1]) / 2
            parts.append(f'<line x1="{cx - gw * 0.35:.1f}" y1="{y(med):.1f}" x2="{cx + gw * 0.35:.1f}" '
                         f'y2="{y(med):.1f}" stroke="#c0392b" stroke-width="2"/>')
        parts.append(f'<text x="{cx:.1f}" y="{height - pad_b + 18}" text-anchor="middle">{_esc(g)} ({len(gv)})</text>')
    parts.append("</svg>")
    return "\n".join(parts)
