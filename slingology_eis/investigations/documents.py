"""
The workspace's documents (Spec 16 §2.4 layer 4, §4.2): files the user
placed under

    workspaces/<id>/documents/                     (Spec 02 §5.3)

— the Operators Manual (the user's own copy, never shipped: Spec 06 §1),
service bulletins, a propeller manual, earlier write-ups. The
investigator reads them **a page at a time**, never whole.

The pager (§9 Q1):
- **PDF** — one page per PDF page, text as extracted by pypdf (optional
  dependency; without it a PDF lists but doesn't read). Page numbers are
  the PDF's own, 1-based, so a citation says "p. 47" of the file.
- **Markdown** — one page per heading section (`#`…`######`), titled by
  the heading.
- **Plain text** (and anything else that decodes as text) — pages of about
  `TEXT_PAGE_CHARS` characters, broken at line ends.

A read returns at most `MAX_PAGES_PER_READ` pages and `MAX_CHARS_PER_READ`
characters; `find` returns the pages a phrase occurs on, with snippets,
so a 300-page manual is searched rather than paged through.

Extracted PDF text is kept in `documents/.index/` (keyed by size and
mtime) so a manual is parsed once; the index, like the documents, is
local and never exported.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

DIRNAME = "documents"
INDEX_DIRNAME = ".index"
TEXT_PAGE_CHARS = 3000
MAX_PAGES_PER_READ = 3
MAX_CHARS_PER_READ = 12000
MAX_FIND_MATCHES = 20
SNIPPET_CHARS = 240
MAX_DOCUMENT_BYTES = 200 * 1024 * 1024
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


class DocumentError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def documents_dir(ws_dir: Path) -> Path:
    return ws_dir / DIRNAME


def _kind(p: Path) -> str:
    s = p.suffix.lower()
    if s == ".pdf":
        return "pdf"
    if s in (".md", ".markdown"):
        return "markdown"
    return "text"


def _resolve(ws_dir: Path, name: str) -> Path:
    """A document by its name under documents/ — never a path outside it."""
    if not isinstance(name, str) or not name.strip():
        raise DocumentError("BAD_PARAMS", "name a document (documents_list shows them)")
    base = documents_dir(ws_dir).resolve()
    p = (base / name).resolve()
    if base not in p.parents or any(part.startswith(".") for part in p.relative_to(base).parts):
        raise DocumentError("BAD_PARAMS", f"{name!r} isn't a document in this workspace")
    if not p.is_file():
        raise DocumentError("NOT_FOUND", f"no document {name!r}; documents_list shows what is there")
    return p


def _visible(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    out = []
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base)
        if p.is_file() and not any(part.startswith(".") for part in rel.parts):
            out.append(p)
    return out


# ── Pages ───────────────────────────────────────────────────────────────────

def _text_pages(text: str) -> list[dict]:
    pages, buf, size = [], [], 0
    for line in text.splitlines(keepends=True):
        if size + len(line) > TEXT_PAGE_CHARS and buf:
            pages.append("".join(buf))
            buf, size = [], 0
        buf.append(line)
        size += len(line)
    if buf or not pages:
        pages.append("".join(buf))
    return [{"page": i + 1, "title": None, "text": t} for i, t in enumerate(pages)]


def _markdown_pages(text: str) -> list[dict]:
    sections: list[dict] = []
    path: list[str] = []
    cur = {"title": None, "lines": []}
    for line in text.splitlines(keepends=True):
        m = _HEADING.match(line.rstrip("\n"))
        if m:
            if cur["lines"] and "".join(cur["lines"]).strip():
                sections.append(cur)
            level = len(m.group(1))
            path = path[:level - 1] + [m.group(2)]
            cur = {"title": " › ".join(path), "lines": [line]}
        else:
            cur["lines"].append(line)
    if cur["lines"] and ("".join(cur["lines"]).strip() or not sections):
        sections.append(cur)
    return [{"page": i + 1, "title": s["title"], "text": "".join(s["lines"])} for i, s in enumerate(sections)]


def _pdf_pages(p: Path, index_dir: Path) -> list[dict]:
    st = p.stat()
    key = f"{st.st_size}-{st.st_mtime_ns}"
    cached = index_dir / (p.name + ".json")
    if cached.is_file():
        try:
            doc = json.loads(cached.read_text())
            if doc.get("key") == key:
                return doc["pages"]
        except (ValueError, KeyError):
            pass
    try:
        from pypdf import PdfReader
    except ImportError:
        raise DocumentError("NOT_SUPPORTED", "reading PDFs needs the pypdf package "
                                             "(pip install 'slingology-eis[investigations]')")
    try:
        reader = PdfReader(str(p))
        pages = [{"page": i + 1, "title": None, "text": (pg.extract_text() or "")} for i, pg in enumerate(reader.pages)]
    except Exception as e:  # noqa: BLE001 — a broken PDF says so, it doesn't crash the host
        raise DocumentError("BAD_PARAMS", f"{p.name} couldn't be read as a PDF ({type(e).__name__}: {e})")
    try:
        index_dir.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps({"key": key, "pages": pages}))
    except OSError:
        pass                                   # a read-only folder just means no index
    return pages


def pages_of(ws_dir: Path, p: Path) -> list[dict]:
    kind = _kind(p)
    if kind == "pdf":
        return _pdf_pages(p, documents_dir(ws_dir) / INDEX_DIRNAME)
    data = p.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return _markdown_pages(text) if kind == "markdown" else _text_pages(text)


# ── Operations ──────────────────────────────────────────────────────────────

def list_documents(ws_dir: Path) -> dict:
    base = documents_dir(ws_dir)
    out = []
    for p in _visible(base):
        entry = {"name": p.relative_to(base).as_posix(), "kind": _kind(p), "size": p.stat().st_size}
        try:
            pages = pages_of(ws_dir, p)
            entry["pages"] = len(pages)
            first = next((pg["text"].strip().splitlines()[0] for pg in pages if pg["text"].strip()), "")
            entry["first_line"] = first[:120]
        except DocumentError as e:
            entry["pages"] = None
            entry["note"] = e.message
        out.append(entry)
    return {"documents": out, "folder": str(base), "pager": pager()}


def pager() -> dict:
    return {"pdf": "one page per PDF page", "markdown": "one page per heading section",
            "text": f"pages of about {TEXT_PAGE_CHARS} characters", "max_pages_per_read": MAX_PAGES_PER_READ,
            "max_chars_per_read": MAX_CHARS_PER_READ}


def _snippet(text: str, at: int, n: int) -> str:
    a = max(0, at - SNIPPET_CHARS // 2)
    b = min(len(text), at + n + SNIPPET_CHARS // 2)
    s = re.sub(r"\s+", " ", text[a:b]).strip()
    return ("…" if a > 0 else "") + s + ("…" if b < len(text) else "")


def read_document(ws_dir: Path, name: str, page: int = 1, pages: int = 1, find: Optional[str] = None) -> dict:
    p = _resolve(ws_dir, name)
    all_pages = pages_of(ws_dir, p)
    out = {"name": name, "kind": _kind(p), "page_count": len(all_pages)}
    if find is not None:
        q = str(find).strip()
        if not q:
            raise DocumentError("BAD_PARAMS", "find needs a word or phrase")
        rx = re.compile(re.escape(q).replace(r"\ ", r"\s+"), re.IGNORECASE)
        matches, total = [], 0
        for pg in all_pages:
            hits = list(rx.finditer(pg["text"]))
            if not hits:
                continue
            total += 1
            if len(matches) < MAX_FIND_MATCHES:
                matches.append({"page": pg["page"], "title": pg["title"], "hits": len(hits),
                                "snippet": _snippet(pg["text"], hits[0].start(), len(hits[0].group(0)))})
        out.update({"find": q, "pages_matching": total, "matches": matches,
                    "truncated": total > len(matches)})
        return out
    try:
        page, pages = int(page), int(pages)
    except (TypeError, ValueError):
        raise DocumentError("BAD_PARAMS", "page and pages are whole numbers")
    if not 1 <= page <= len(all_pages):
        raise DocumentError("BAD_PARAMS", f"{name} has pages 1–{len(all_pages)}")
    pages = max(1, min(pages, MAX_PAGES_PER_READ))
    got, used, truncated = [], 0, False
    for pg in all_pages[page - 1: page - 1 + pages]:
        text = pg["text"]
        room = MAX_CHARS_PER_READ - used
        if room <= 0:
            truncated = True
            break
        if len(text) > room:
            text, truncated = text[:room], True
        used += len(text)
        got.append({"page": pg["page"], "title": pg["title"], "text": text})
    last = got[-1]["page"] if got else page
    out.update({"pages": got, "next_page": last + 1 if last < len(all_pages) else None, "truncated": truncated})
    return out


_SAFE_NAME = re.compile(r"^[^/\\:*?\"<>|\x00-\x1f]{1,180}$")


def add_document(ws_dir: Path, filename: str, content: bytes) -> dict:
    """A file the user chose, copied into documents/ (the website tier, and
    Settings → Aircraft, have no folder to drop files into)."""
    name = Path(str(filename or "")).name
    if not name or name.startswith(".") or not _SAFE_NAME.match(name):
        raise DocumentError("BAD_PARAMS", f"{filename!r} isn't a usable file name")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise DocumentError("BAD_PARAMS", f"{name} is larger than {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB")
    base = documents_dir(ws_dir)
    base.mkdir(parents=True, exist_ok=True)
    (base / name).write_bytes(content)
    entry = next(d for d in list_documents(ws_dir)["documents"] if d["name"] == name)
    return entry


def remove_document(ws_dir: Path, name: str) -> dict:
    p = _resolve(ws_dir, name)
    p.unlink()
    idx = documents_dir(ws_dir) / INDEX_DIRNAME / (p.name + ".json")
    if idx.is_file():
        idx.unlink()
    return {"removed": name}
