"""
The aircraft's documents (Spec 16 D11, §4.4): the Operators Manual (the
owner's own copy, never shipped: Spec 06 §1), service bulletins, a
propeller manual, earlier write-ups — read **in place** from the folders
the owner named in the aircraft record (`documents_dirs`), subfolders
walked. Nothing is copied. The investigator reads them a page at a time,
never whole.

The pager (§9 Q1):
- **PDF** — one page per PDF page, text as extracted by pypdf (optional
  dependency; without it a PDF lists but doesn't read). Page numbers are
  the PDF's own, 1-based, so a citation says "p. 47" of the file.
- **Markdown** — one page per heading section (`#`…`######`).
- **Plain text** — pages of about `TEXT_PAGE_CHARS` characters.

The index cache (`<data root>/cache/documents/`): `<file hash>/pages.json`
holds a file's extracted pages, so a manual is parsed once; a changed
file has a new hash and is indexed again; a hash no listed file has any
more is dropped. `index.json` remembers each path's size, mtime and hash
so an unchanged file isn't hashed again. Derived data, local, never
exported (and under the repo's never-commit rule).

`find` is case-insensitive with diacritics folded (F5): "hunt" finds
"Hunting", "regle" finds "règle".
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Optional

TEXT_PAGE_CHARS = 3000
MAX_PAGES_PER_READ = 3
MAX_CHARS_PER_READ = 12000
MAX_FIND_MATCHES = 20
SNIPPET_CHARS = 240
SUFFIXES = {".pdf": "pdf", ".md": "markdown", ".markdown": "markdown", ".txt": "text", ".text": "text"}
NO_FOLDER = "no documents folder set for this aircraft — Settings → Aircraft → Documents folders"
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


class DocumentError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def cache_root(data_root: Path) -> Path:
    return Path(data_root) / "cache" / "documents"


# ── The files ──────────────────────────────────────────────────────────────

def _labels(dirs: list[str]) -> list[str]:
    """A short, unique label per folder: its name (with a number if two share one)."""
    out: list[str] = []
    for d in dirs:
        base = Path(d).name or d
        label, k = base, 2
        while label in out:
            label, k = f"{base} ({k})", k + 1
        out.append(label)
    return out


def _walk(dirs: list[str]) -> tuple[list[dict], list[dict]]:
    """(files, folders): every PDF, Markdown and text file under the
    folders, hidden ones skipped; a file's name is its path within its
    folder, prefixed by the folder's label when there are several."""
    files, folders = [], []
    labels = _labels(dirs)
    for d, label in zip(dirs, labels):
        base = Path(d)
        ok = base.is_dir()
        folders.append({"path": str(base), "label": label, "reachable": ok})
        if not ok:
            continue
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(base)
            if not p.is_file() or any(part.startswith(".") for part in rel.parts):
                continue
            kind = SUFFIXES.get(p.suffix.lower())
            if kind is None:
                continue
            name = rel.as_posix() if len(dirs) == 1 else f"{label}/{rel.as_posix()}"
            files.append({"name": name, "path": p, "folder": str(base), "kind": kind})
    return files, folders


def _hash(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:32]


class _Index:
    """index.json: path → {size, mtime_ns, hash}."""

    def __init__(self, root: Path):
        self.root = root
        self.path = root / "index.json"
        try:
            self.paths = json.loads(self.path.read_text()).get("paths", {}) if self.path.is_file() else {}
        except ValueError:
            self.paths = {}
        self.dirty = False

    def hash_of(self, p: Path) -> str:
        st = p.stat()
        key = str(p)
        got = self.paths.get(key)
        if got and got.get("size") == st.st_size and got.get("mtime_ns") == st.st_mtime_ns:
            return got["hash"]
        h = _hash(p)
        self.paths[key] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "hash": h}
        self.dirty = True
        return h

    def prune(self) -> int:
        """Forget paths that are gone; drop the cache of every hash no
        remaining path has. Returns how many cache entries were dropped."""
        for key in [k for k in self.paths if not Path(k).is_file()]:
            del self.paths[key]
            self.dirty = True
        live = {v["hash"] for v in self.paths.values()}
        dropped = 0
        if self.root.is_dir():
            for d in self.root.iterdir():
                if d.is_dir() and d.name not in live:
                    shutil.rmtree(d, ignore_errors=True)
                    dropped += 1
        return dropped

    def save(self) -> None:
        if self.dirty:
            self.root.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"version": 1, "paths": self.paths}))
            self.dirty = False


# ── Pages ──────────────────────────────────────────────────────────────────

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


def _extract(p: Path, kind: str) -> list[dict]:
    if kind == "pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise DocumentError("NOT_SUPPORTED", "reading PDFs needs the pypdf package "
                                                 "(pip install 'slingology-eis[investigations]')")
        try:
            reader = PdfReader(str(p))
            return [{"page": i + 1, "title": None, "text": (pg.extract_text() or "")}
                    for i, pg in enumerate(reader.pages)]
        except Exception as e:  # noqa: BLE001 — a broken PDF says so, it doesn't crash the host
            raise DocumentError("BAD_PARAMS", f"{p.name} couldn't be read as a PDF ({type(e).__name__}: {e})")
    data = p.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return _markdown_pages(text) if kind == "markdown" else _text_pages(text)


def pages_of(index: _Index, f: dict) -> list[dict]:
    """A file's pages, from the cache when its hash has been indexed."""
    h = index.hash_of(f["path"])
    cached = index.root / h / "pages.json"
    if cached.is_file():
        try:
            return json.loads(cached.read_text())["pages"]
        except (ValueError, KeyError):
            pass
    pages = _extract(f["path"], f["kind"])
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps({"kind": f["kind"], "pages": pages}))
    except OSError:
        pass
    return pages


# ── Folding (F5) ───────────────────────────────────────────────────────────

def fold(text: str) -> tuple[str, list[int]]:
    """Case-folded text without diacritics, and for each folded character
    the index of the original character it came from."""
    out, where = [], []
    for i, ch in enumerate(text):
        for c in unicodedata.normalize("NFKD", ch):
            if unicodedata.combining(c):
                continue
            for f in c.casefold():
                out.append(f)
                where.append(i)
    return "".join(out), where


# ── Operations ─────────────────────────────────────────────────────────────

def pager() -> dict:
    return {"pdf": "one page per PDF page", "markdown": "one page per heading section",
            "text": f"pages of about {TEXT_PAGE_CHARS} characters", "max_pages_per_read": MAX_PAGES_PER_READ,
            "max_chars_per_read": MAX_CHARS_PER_READ}


def list_documents(dirs: list[str], data_root: Path) -> dict:
    if not dirs:
        return {"documents": [], "folders": [], "message": NO_FOLDER, "pager": pager()}
    files, folders = _walk(dirs)
    index = _Index(cache_root(data_root))
    out = []
    for f in files:
        entry = {"name": f["name"], "folder": f["folder"], "kind": f["kind"], "size": f["path"].stat().st_size}
        try:
            pages = pages_of(index, f)
            entry["pages"] = len(pages)
            first = next((pg["text"].strip().splitlines()[0] for pg in pages if pg["text"].strip()), "")
            entry["first_line"] = first[:120]
        except DocumentError as e:
            entry["pages"] = None
            entry["note"] = e.message
        out.append(entry)
    index.prune()
    index.save()
    res = {"documents": out, "folders": folders, "pager": pager()}
    missing = [f["path"] for f in folders if not f["reachable"]]
    if missing:
        res["message"] = "can't reach " + ", ".join(missing) + " — check Settings → Aircraft → Documents folders"
    return res


def _find_file(dirs: list[str], name: str) -> dict:
    if not isinstance(name, str) or not name.strip():
        raise DocumentError("BAD_PARAMS", "name a document (documents_list shows them)")
    if not dirs:
        raise DocumentError("NOT_FOUND", NO_FOLDER)
    files, _ = _walk(dirs)
    f = next((f for f in files if f["name"] == name), None)
    if f is None:
        f = next((f for f in files if f["name"].lower() == name.strip().lower()), None)
    if f is None:
        raise DocumentError("NOT_FOUND", f"no document {name!r}; documents_list shows what is there")
    return f


def _snippet(text: str, at: int, n: int) -> str:
    a = max(0, at - SNIPPET_CHARS // 2)
    b = min(len(text), at + n + SNIPPET_CHARS // 2)
    s = re.sub(r"\s+", " ", text[a:b]).strip()
    return ("…" if a > 0 else "") + s + ("…" if b < len(text) else "")


def read_document(dirs: list[str], data_root: Path, name: str, page: int = 1, pages: int = 1,
                  find: Optional[str] = None) -> dict:
    f = _find_file(dirs, name)
    index = _Index(cache_root(data_root))
    all_pages = pages_of(index, f)
    index.save()
    out = {"name": f["name"], "folder": f["folder"], "kind": f["kind"], "page_count": len(all_pages)}
    if find is not None:
        q = str(find).strip()
        if not q:
            raise DocumentError("BAD_PARAMS", "find needs a word or phrase")
        fq, _ = fold(q)
        rx = re.compile(r"\s+".join(re.escape(w) for w in fq.split()))
        matches, total = [], 0
        for pg in all_pages:
            ft, where = fold(pg["text"])
            hits = list(rx.finditer(ft))
            if not hits:
                continue
            total += 1
            if len(matches) < MAX_FIND_MATCHES:
                h = hits[0]
                start = where[h.start()] if h.start() < len(where) else 0
                end = where[h.end() - 1] + 1 if h.end() - 1 < len(where) else start
                matches.append({"page": pg["page"], "title": pg["title"], "hits": len(hits),
                                "snippet": _snippet(pg["text"], start, end - start)})
        out.update({"find": q, "pages_matching": total, "matches": matches, "truncated": total > len(matches)})
        return out
    try:
        page, pages = int(page), int(pages)
    except (TypeError, ValueError):
        raise DocumentError("BAD_PARAMS", "page and pages are whole numbers")
    if not 1 <= page <= len(all_pages):
        raise DocumentError("BAD_PARAMS", f"{f['name']} has pages 1–{len(all_pages)}")
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


class Document:
    """`eis.document(name)` on the bench: .find(phrase), .page(n), .pages."""

    def __init__(self, dirs: list[str], data_root: Path, name: str):
        self._dirs, self._root, self.name = dirs, data_root, name
        self.info = read_document(dirs, data_root, name, page=1, pages=1)

    @property
    def page_count(self) -> int:
        return self.info["page_count"]

    def page(self, n: int) -> str:
        got = read_document(self._dirs, self._root, self.name, page=n, pages=1)
        return got["pages"][0]["text"] if got["pages"] else ""

    def find(self, phrase: str) -> list[dict]:
        return read_document(self._dirs, self._root, self.name, find=phrase)["matches"]

    def __repr__(self) -> str:
        return f"<document {self.name!r}, {self.page_count} pages>"
