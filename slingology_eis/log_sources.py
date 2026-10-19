"""
log_sources.py — how a workspace's log folders are listed and read
(Spec 04 v0.4 §9.3).

A workspace references folders (Spec 02 §5.1); what differs by host is how
a folder's contents reach Python. A `LogSource` is one folder: it can
**list** the logs in it and **read** one log's bytes by relative path, and
is told when the host has finished with those bytes (`release`), so a
source fed by a web page can stream one file at a time.

- `DiskLogSource` walks a folder on disk — today's rule exactly: every
  file under it, recursively, whose suffix is `.csv` in any case.
- `SuppliedLogSource` is built from a listing the caller provides plus a
  byte provider — what the browser will drive.

The host never constructs a source itself: it asks the factory its
transport installed (`ctx["log_sources"]`) for the source of a
`LogFolder`. `DiskSources` serves folders by path; `SuppliedSources`
serves folders registered by `folder_id`.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator, Optional


@dataclass(frozen=True)
class LogEntry:
    """One log in a folder's listing."""
    relative_path: str        # POSIX separators, relative to the folder
    size: int                 # bytes
    last_modified: float      # seconds since the epoch

    @property
    def name(self) -> str:
        return PurePosixPath(self.relative_path).name

    @classmethod
    def from_dict(cls, d: dict) -> "LogEntry":
        return cls(relative_path=str(d["relative_path"]), size=int(d.get("size", 0)),
                   last_modified=float(d.get("last_modified", 0.0)))


class LogUnavailable(Exception):
    """A log the source can't supply (gone, unreadable, refused by the page)."""


def is_log_name(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() == ".csv"


def listing_order(entry: LogEntry) -> tuple:
    """The order every source lists in: by path components, as sorting the
    disk walk's Paths always did (so `a/b.csv` comes before `a.csv`)."""
    return PurePosixPath(entry.relative_path).parts


class LogSource:
    """One folder's logs. `list()` returns None when the folder can't be
    listed right now (unreachable)."""

    def list(self) -> Optional[list[LogEntry]]:
        raise NotImplementedError

    def read(self, relative_path: str) -> bytes:
        raise NotImplementedError

    def release(self, relative_path: str) -> None:
        """The host is done with this log's bytes."""


class DiskLogSource(LogSource):
    def __init__(self, path: str):
        self.folder = Path(path).expanduser()

    def list(self) -> Optional[list[LogEntry]]:
        if not self.folder.is_dir():
            return None
        out = []
        for p in sorted(p for p in self.folder.rglob("*") if p.is_file() and p.suffix.lower() == ".csv"):
            st = p.stat()
            out.append(LogEntry(relative_path=p.relative_to(self.folder).as_posix(), size=st.st_size,
                                last_modified=st.st_mtime))
        return out

    def read(self, relative_path: str) -> bytes:
        p = self.folder / relative_path
        if not p.is_file():
            raise LogUnavailable(f"{relative_path} isn't in {self.folder}")
        return p.read_bytes()


class SuppliedLogSource(LogSource):
    """A folder whose listing and bytes the caller supplies. `read_bytes`
    is called once per log the host needs, in listing order, and `release`
    (if given) once the host is done with it."""

    def __init__(self, listing: Optional[list], read_bytes: Callable[[str], bytes],
                 release: Optional[Callable[[str], None]] = None):
        self._listing = None if listing is None else sorted(
            (e if isinstance(e, LogEntry) else LogEntry.from_dict(e) for e in listing), key=listing_order)
        self._read = read_bytes
        self._release = release

    def list(self) -> Optional[list[LogEntry]]:
        if self._listing is None:
            return None
        return [e for e in self._listing if is_log_name(e.relative_path)]

    def read(self, relative_path: str) -> bytes:
        try:
            data = self._read(relative_path)
        except LogUnavailable:
            raise
        except Exception as e:  # a page that can't supply the file
            raise LogUnavailable(f"{relative_path}: {e}") from e
        if data is None:
            raise LogUnavailable(f"{relative_path} wasn't supplied")
        return bytes(data)

    def release(self, relative_path: str) -> None:
        if self._release is not None:
            self._release(relative_path)


@contextmanager
def reading(source: LogSource, relative_path: str) -> Iterator[bytes]:
    """A log's bytes for the duration of a block, released afterwards."""
    data = source.read(relative_path)
    try:
        yield data
    finally:
        source.release(relative_path)


@dataclass(frozen=True)
class LogRef:
    """A log found in a folder: where it is, and a way to read it."""
    source: LogSource
    entry: LogEntry

    @property
    def name(self) -> str:
        return self.entry.name

    def read_bytes(self) -> bytes:
        with reading(self.source, self.entry.relative_path) as data:
            return data


# ── Factories: what a transport installs in the host context ───────────────

class DiskSources:
    """Folders by path, walked on disk (the HTTP server and the CLI)."""
    add_folder_by_path = True
    choose_folder = False

    def __call__(self, folder) -> LogSource:
        return DiskLogSource(folder.path)


class SuppliedSources:
    """Folders by `folder_id`, their listing and bytes supplied by the
    transport (the browser's page, in step 4). A folder with no supplied
    source can't be listed — it is unreachable."""
    add_folder_by_path = False
    choose_folder = True

    def __init__(self, sources: Optional[dict[str, LogSource]] = None):
        self.sources: dict[str, LogSource] = dict(sources or {})

    def __call__(self, folder) -> LogSource:
        key = getattr(folder, "folder_id", None) or folder.path
        return self.sources.get(key) or SuppliedLogSource(None, lambda rel: None)


DISK = DiskSources()
