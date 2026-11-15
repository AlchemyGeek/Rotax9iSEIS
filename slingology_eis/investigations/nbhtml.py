"""
The notebook as one HTML page (Spec 16 §5.1 export, §5.3): EIS's own
renderer, so the export shows what the Research page shows — markdown,
code collapsed under *show code*, outputs (streams, tables, figures, the
log view's SVG), errors. Deterministic: the same notebook gives the same
bytes.

Safety: the page is opened from a file the user may have been sent, so
nothing in it runs — SVG is shown through <img> (a data: URL, where
scripts don't run), markdown and text are escaped, and `text/html` is used
only for the tables EIS wrote (output metadata `slingology.table`);
anything else shows as its text/plain; even an EIS table keeps only
table tags (`sanitize_table`), since a received notebook can claim the mark.

The page's renderer (web/src/lib/notebook.ts) is a port of this module,
string for string; both are checked against one golden
(web/src/fixtures/research-notebook.render.json).
"""
from __future__ import annotations

import base64
import html
import re

from .eis_lib import LOGVIEW_MIME
from .ipynb import meta, text

_CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem;
color:#1d2433;line-height:1.5}
header{border-bottom:1px solid #d6dae3;margin-bottom:1.5rem}
header .meta{color:#5b6475;font-size:.9rem}
.cell{margin:1rem 0}
details.code summary{cursor:pointer;color:#5b6475;font-size:.85rem}
pre{background:#f5f6f8;padding:.6rem .8rem;overflow-x:auto;font-size:.85rem;border-radius:4px}
pre.stderr{background:#fff4e5}
pre.error{background:#fdecec}
table.eis-table{border-collapse:collapse;font-size:.85rem;margin:.5rem 0}
table.eis-table th,table.eis-table td{border:1px solid #d6dae3;padding:.2rem .5rem;text-align:right}
table.eis-table th{background:#f0f2f6}
img.figure{max-width:100%}
.logview figcaption{color:#5b6475;font-size:.85rem}
.flag{font-size:.8rem;color:#8a5a00}
"""


# ── Markdown (the subset notebooks use) ────────────────────────────────────

_MIME = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def _image(alt: str, url: str, read_file) -> str:
    u = html.unescape(url)
    ext = "." + u.rsplit(".", 1)[-1].lower() if "." in u else ""
    if read_file is not None and u.startswith("files/") and ext in _MIME:
        body = read_file(u)
        if body is not None:      # inlined, so the page stands alone
            return f'<img class="figure" alt="{alt}" src="data:{_MIME[ext]};base64,{base64.b64encode(body).decode()}">'
    return f'<img alt="{alt}" src="{_safe_url(url)}">'


def _inline(s: str, read_file=None) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", lambda m: _image(m.group(1), m.group(2), read_file), s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", lambda m: f'<a href="{_safe_url(m.group(2))}">{m.group(1)}</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"<em>\1</em>", s)
    return s


def _safe_url(u: str) -> str:
    u = html.unescape(u)
    if re.match(r"^\s*(javascript|data|vbscript):", u, re.I):
        return "#"
    return html.escape(u, quote=True)


def markdown(src: str, read_file=None) -> str:
    out: list[str] = []
    lines = src.splitlines()
    i = 0
    para: list[str] = []

    def flush() -> None:
        if para:
            out.append("<p>" + _inline(" ".join(para), read_file) + "</p>")
            para.clear()
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            flush()
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(lines[i + 1:j])) + "</code></pre>")
            i = j + 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush()
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
        elif re.match(r"^\s*([-*•]|\d+\.)\s+", line):
            flush()
            tag = "ol" if re.match(r"^\s*\d+\.", line) else "ul"
            items = []
            while i < len(lines) and re.match(r"^\s*([-*•]|\d+\.)\s+", lines[i]):
                items.append("<li>" + _inline(re.sub(r"^\s*([-*•]|\d+\.)\s+", "", lines[i])) + "</li>")
                i += 1
            out.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue
        elif line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-{3,}", lines[i + 1]):
            flush()
            row = lambda s: [c.strip() for c in s.strip().strip("|").split("|")]
            head = row(line)
            body = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                body.append(row(lines[i]))
                i += 1
            out.append('<table class="eis-table"><thead><tr>' + "".join(f"<th>{_inline(c)}</th>" for c in head)
                       + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r)
                                                          + "</tr>" for r in body) + "</tbody></table>")
            continue
        elif line.startswith(">"):
            flush()
            out.append("<blockquote>" + _inline(line.lstrip("> ")) + "</blockquote>")
        elif not line.strip():
            flush()
        else:
            para.append(line.strip())
        i += 1
    flush()
    return "\n".join(out)


# ── Outputs ────────────────────────────────────────────────────────────────

_TABLE_TAGS = {"table", "caption", "thead", "tbody", "tr", "th", "td", "p"}


def sanitize_table(src: str) -> str:
    """EIS's table HTML with every tag but the table's own dropped and every
    attribute dropped (the table keeps class="eis-table"). Identity on what
    the bench writes."""
    out = []
    for tok in re.split(r"(<[^>]*>)", src):
        if tok.startswith("<"):
            m = re.match(r"^<(/?)([a-zA-Z]+)\b", tok)
            if not m or m.group(2).lower() not in _TABLE_TAGS:
                continue
            tag = m.group(2).lower()
            out.append(f"</{tag}>" if m.group(1) else '<table class="eis-table">' if tag == "table" else f"<{tag}>")
        else:
            out.append(tok.replace(">", "&gt;"))
    return "".join(out)


def outputs_line(nb: dict) -> str:
    """"outputs current for this workspace", or what is not (the page's header line)."""
    pending = elsewhere = read_only = 0
    for c in nb.get("cells") or []:
        if c.get("cell_type") != "code":
            continue
        sm = (c.get("metadata") or {}).get("slingology") or {}
        pending += bool(sm.get("pending"))
        elsewhere += bool(sm.get("ran_elsewhere"))
        read_only += bool(sm.get("read_only"))

    def n(k: int, what: str) -> str:
        return f"{k} cell{'' if k == 1 else 's'} {what}"
    parts = ([n(pending, "with new outputs pending")] if pending else []) \
        + ([n(elsewhere, "ran elsewhere")] if elsewhere else []) \
        + ([n(read_only, "read-only (flights not here)")] if read_only else [])
    return "outputs: " + " · ".join(parts) if parts else "outputs current for this workspace"


def _img(svg: str, cls: str = "figure", alt: str = "figure") -> str:
    b64 = base64.b64encode(svg.encode("utf-8")).decode()
    return f'<img class="{cls}" alt="{html.escape(alt)}" src="data:image/svg+xml;base64,{b64}">'


def output(o: dict) -> str:
    t = o.get("output_type")
    if t == "stream":
        cls = "stderr" if o.get("name") == "stderr" else "stdout"
        return f'<pre class="{cls}">' + html.escape(text(o.get("text"))) + "</pre>"
    if t == "error":
        tb = o.get("traceback") or []
        body = "\n".join(tb) if isinstance(tb, list) else str(tb)
        return '<pre class="error">' + html.escape(re.sub(r"\x1b\[[0-9;]*m", "", body)) + "</pre>"
    data = o.get("data") or {}
    if LOGVIEW_MIME in data and "image/svg+xml" in data:
        ref = data[LOGVIEW_MIME] or {}
        cap = html.escape(str(ref.get("title") or ref.get("window_label") or "log view"))
        return f'<figure class="logview">{_img(text(data["image/svg+xml"]), "figure", cap)}<figcaption>{cap}</figcaption></figure>'
    if "image/svg+xml" in data:
        return _img(text(data["image/svg+xml"]), alt=text(data.get("text/plain")) or "figure")
    if "image/png" in data:
        return f'<img class="figure" alt="figure" src="data:image/png;base64,{text(data["image/png"]).strip()}">'
    if "text/html" in data and ((o.get("metadata") or {}).get("slingology") or {}).get("table"):
        return sanitize_table(text(data["text/html"]))
    if "text/plain" in data:
        return "<pre>" + html.escape(text(data["text/plain"])) + "</pre>"
    return ""


def render(nb: dict, read_file=None) -> str:
    """`read_file(ref)` gives a files/ document's bytes (images a markdown
    cell shows are inlined)."""
    m = meta(nb)
    status = m.get("status") or "open"
    head = [f"<h1>{html.escape(m.get('name') or 'Notebook')}</h1>",
            '<p class="meta">' + " · ".join(html.escape(str(x)) for x in (
                f"by {m.get('author') or 'user'}", status, f"engine {m.get('engine') or ''}",
                (m.get("updated") or "")[:10]) if x) + "</p>",
            '<p class="meta outputs">' + html.escape(outputs_line(nb)) + "</p>"]
    if m.get("question"):
        head.append(f"<p><strong>Question:</strong> {_inline(m['question'])}</p>")
    if m.get("summary"):
        head.append("<section class=\"summary\"><h2>Summary</h2>" + markdown(m["summary"]) + "</section>")
    body = []
    for c in nb.get("cells") or []:
        src = text(c.get("source"))
        if c.get("cell_type") == "markdown":
            body.append(f'<div class="cell markdown" id="{html.escape(str(c.get("id")))}">{markdown(src, read_file)}</div>')
        elif c.get("cell_type") == "code":
            sm = (c.get("metadata") or {}).get("slingology") or {}
            flags = [f for f, on in (("ran elsewhere", sm.get("ran_elsewhere")), ("read-only", sm.get("read_only")))
                     if on]
            parts = [f'<div class="cell code" id="{html.escape(str(c.get("id")))}">',
                     '<details class="code"><summary>show code</summary><pre><code>' + html.escape(src)
                     + "</code></pre></details>"]
            if flags:
                parts.append('<p class="flag">' + " · ".join(flags) + "</p>")
            parts += [output(o) for o in c.get("outputs") or []]
            parts.append("</div>")
            body.append("".join(parts))
    return ("<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(m.get('name') or 'Notebook')}</title><style>{_CSS}</style></head><body>"
            "<header>" + "".join(head) + "</header><main>\n" + "\n".join(body) + "\n</main></body></html>\n")
