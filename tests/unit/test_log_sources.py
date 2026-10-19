"""
Log sources (Spec 04 v0.4 §9.3, step 2): the host lists and reads a
workspace's folders only through the source its transport installs.

- parity: a folder scanned through the disk source and through a supplied
  source (an in-memory listing plus bytes) gives the same workspace;
- streaming: a scan reads each log once, one at a time;
- registration by name and folder_id, reachable or not;
- the data root honours a configured location with no workspace in it;
- capabilities follow the installed factory.
"""
import json
import os
import shutil
from pathlib import Path

import pytest

from slingology_eis import host
from slingology_eis import workspace_export as wx
from slingology_eis.cli import _REPO_ROOT
from slingology_eis.log_sources import (DISK, DiskLogSource, LogEntry, SuppliedLogSource, SuppliedSources,
                                        listing_order)

from ..conftest import LOGS_DIR, requires_flight_logs
from .test_server import _flying_log_bytes, isolated_packaged_home  # noqa: F401


def _ctx(log_sources):
    return host.new_context(log_sources=log_sources, emit_progress=lambda s, u: None,
                            deliver_file=lambda p, n: str(p))


def _flight(day: int, start_minute: int = 0) -> bytes:
    """A synthetic flight on 2026-01-<day>, distinct per day."""
    log = _flying_log_bytes(date=f"2026-01-{day:02d}")
    if start_minute:
        log = log.replace(b",12:", f",{12 + start_minute // 60:02d}:".encode())
    return log


def _in_memory(folder: Path):
    """A supplied source built from a disk folder's listing and bytes."""
    listing = [e.__dict__ for e in DiskLogSource(str(folder)).list()]
    data = {e["relative_path"]: (folder / e["relative_path"]).read_bytes() for e in listing}
    return SuppliedLogSource(listing, lambda rel: data[rel])


# ── Interface ───────────────────────────────────────────────────────────────

def test_disk_listing_is_todays_rule(tmp_path):
    (tmp_path / "a").mkdir()
    for rel in ("a/b.csv", "a.CSV", "c.txt", "z.csv"):
        (tmp_path / rel).write_text("x")
    entries = DiskLogSource(str(tmp_path)).list()
    assert [e.relative_path for e in entries] == ["a/b.csv", "a.CSV", "z.csv"]   # recursive, any-case .csv, path order
    assert all(e.size == 1 and e.last_modified > 0 for e in entries)
    assert DiskLogSource(str(tmp_path / "gone")).list() is None


def test_supplied_listing_orders_and_filters_like_the_disk():
    s = SuppliedLogSource([{"relative_path": "z.csv", "size": 1, "last_modified": 0},
                           {"relative_path": "a.CSV", "size": 1, "last_modified": 0},
                           {"relative_path": "notes.txt", "size": 1, "last_modified": 0},
                           {"relative_path": "a/b.csv", "size": 1, "last_modified": 0}], lambda rel: b"")
    assert [e.relative_path for e in s.list()] == ["a/b.csv", "a.CSV", "z.csv"]
    assert sorted([LogEntry("a.csv", 0, 0), LogEntry("a/b.csv", 0, 0)], key=listing_order)[0].relative_path == "a/b.csv"


# ── Streaming ───────────────────────────────────────────────────────────────

def test_a_scan_reads_each_log_once_one_at_a_time(isolated_packaged_home):  # noqa: F811
    logs = {f"log_202601{d:02d}_120000_TEST.csv": _flight(d) for d in range(1, 7)}
    stats = {"reads": 0, "outstanding": 0, "peak": 0}

    def read(rel):
        stats["reads"] += 1
        stats["outstanding"] += 1
        stats["peak"] = max(stats["peak"], stats["outstanding"])
        return logs[rel]

    def release(rel):
        stats["outstanding"] -= 1

    listing = [{"relative_path": n, "size": len(b), "last_modified": 0} for n, b in logs.items()]
    ctx = _ctx(SuppliedSources({"f1": SuppliedLogSource(listing, read, release)}))
    host.dispatch("create_workspace", {"name": "S", "engine_model": "916iS"}, ctx)
    host.dispatch("register_log_folder", {"name": "Logs", "folder_id": "f1"}, ctx)
    result = host.dispatch("scan_workspace", {}, ctx)
    assert len(result["new_flight_ids"]) == 6
    assert stats == {"reads": 6, "outstanding": 0, "peak": 1}


# ── Registration by name ───────────────────────────────────────────────────

def test_a_folder_registered_by_name_scans_through_its_supplied_source(isolated_packaged_home):  # noqa: F811
    logs = {"log_20260101_120000_TEST.csv": _flight(1)}
    listing = [{"relative_path": n, "size": len(b), "last_modified": 0} for n, b in logs.items()]
    sources = SuppliedSources({"f1": SuppliedLogSource(listing, lambda rel: logs[rel])})
    ctx = _ctx(sources)
    host.dispatch("create_workspace", {"name": "S", "engine_model": "916iS"}, ctx)
    manifest = host.dispatch("register_log_folder", {"name": "My logs", "folder_id": "f1"}, ctx)
    assert manifest["log_folders"] == [{"folder_id": "f1", "path": "My logs", "reachable": True}]
    result = host.dispatch("scan_workspace", {}, ctx)
    assert len(result["new_flight_ids"]) == 1 and result["unreachable_folders"] == []
    folder, = host.dispatch("get_active_workspace", {}, ctx)["manifest"]["log_folders"]
    assert folder["reachable"] is True and folder["folder_id"] == "f1"

    # The page no longer has the folder: unreachable, and nothing under it
    # is touched (the flight isn't marked missing).
    del sources.sources["f1"]
    result = host.dispatch("scan_workspace", {}, ctx)
    assert result["unreachable_folders"] == ["My logs"] and result["now_missing_flight_ids"] == []
    folder, = host.dispatch("get_active_workspace", {}, ctx)["manifest"]["log_folders"]
    assert folder["reachable"] is False


def test_capabilities_follow_the_installed_sources(isolated_packaged_home):  # noqa: F811
    features = host.dispatch("get_capabilities", {}, _ctx(SuppliedSources()))["features"]
    assert features["add_folder_by_path"] is False and features["choose_folder"] is True
    features = host.dispatch("get_capabilities", {}, _ctx(DISK))["features"]
    assert features["add_folder_by_path"] is True and features["choose_folder"] is False


def test_add_folder_by_path_is_refused_where_the_host_cant_walk_paths(isolated_packaged_home, tmp_path):  # noqa: F811
    ctx = _ctx(SuppliedSources())
    host.dispatch("create_workspace", {"name": "S", "engine_model": "916iS"}, ctx)
    reply = host.reply({"op": "add_log_folder", "params": {"path": str(tmp_path)}}, ctx)
    assert reply["error"]["code"] == "UNSUPPORTED_IN_HOST"


# ── Parity: disk walk vs supplied listing ──────────────────────────────────

_TIMESTAMP_KEYS = {"at", "exported_at", "imported_at", "created_at", "updated_at", "last_scanned_at",
                   "last_opened_at", "excluded_at", "set_at", "made_at"}


def _normalised(obj, names):
    if isinstance(obj, dict):
        return {k: _normalised(v, names) for k, v in obj.items() if k not in _TIMESTAMP_KEYS}
    if isinstance(obj, list):
        return [_normalised(v, names) for v in obj]
    if isinstance(obj, str):
        for old, new in names.items():
            obj = obj.replace(old, new)
    return obj


def _scan_and_export(log_sources, folder: Path, name: str, out: Path) -> dict:
    ctx = _ctx(log_sources)
    ws_id = host.dispatch("create_workspace", {"name": name, "engine_model": "916iS"}, ctx)["id"]
    host.dispatch("add_log_folder" if log_sources is DISK else "register_log_folder",
                  {"path": str(folder)} if log_sources is DISK else {"name": str(folder), "folder_id": "f"}, ctx)
    host.dispatch("scan_workspace", {}, ctx)
    res = wx.export_workspace(ctx["workspace_dir"], out, include_logs=False, sources=log_sources)
    contents = wx.read_export(res.path)
    docs = _normalised({"(workspace)": contents.workspace, **contents.documents}, {ws_id: "WS", name: "NAME"})
    docs["(flight count)"] = len(host.dispatch("list_flights_with_status", {}, ctx)["rows"])
    return docs


def _assert_parity(folder: Path, tmp_path: Path):
    disk = _scan_and_export(DISK, folder, "Disk", tmp_path / "out-disk")
    supplied = _scan_and_export(SuppliedSources({"f": _in_memory(folder)}), folder, "Supplied", tmp_path / "out-supplied")
    # The supplied folder is registered by name with a folder_id; the disk
    # one by path. Everything else is the same document for document.
    assert sorted(disk) == sorted(supplied)
    for doc in disk:
        assert disk[doc] == supplied[doc], doc
    return disk


def test_parity_synthetic(isolated_packaged_home, tmp_path):  # noqa: F811
    folder = tmp_path / "logs"
    (folder / "sub").mkdir(parents=True)
    for d in range(1, 4):
        (folder / f"log_202601{d:02d}_120000_TEST.csv").write_bytes(_flight(d))
    (folder / "sub" / "log_20260104_120000_TEST.csv").write_bytes(_flight(4))
    (folder / "log_20260105_120000_KAWO.csv").write_bytes(b"not a log\n")       # unreadable
    shutil.copy(folder / "log_20260101_120000_TEST.csv", folder / "sub" / "copy.csv")  # same bytes twice
    docs = _assert_parity(folder, tmp_path)
    assert docs["(flight count)"] == 4 + 1     # four flights, plus the unreadable log's row


@requires_flight_logs
def test_parity_real_logs(isolated_packaged_home, tmp_path):  # noqa: F811
    """A slice of the real set with SD/Garmin Pilot duplicates of one
    flight, ground sessions and an AXIS log."""
    folder = tmp_path / "logs"
    folder.mkdir()
    picks = sorted(LOGS_DIR.glob("log_202604*.csv"))[:12] + sorted(LOGS_DIR.glob("c6df2e24-*.csv")) \
        + sorted(LOGS_DIR.glob("e5d43072-*.csv"))
    for p in picks:
        os.symlink(p.resolve(), folder / p.name)
    docs = _assert_parity(folder, tmp_path)
    assert docs["(flight count)"] >= 5


# ── The data root honours a configured location (Spec 02 §5.8.1) ───────────

def test_a_configured_root_with_no_workspace_is_used_not_the_checkouts_data(tmp_path, monkeypatch):
    root = tmp_path / "fresh-root"
    monkeypatch.setenv("SLINGOLOGY_EIS_HOME", str(root))
    repo_data = _REPO_ROOT / "data"

    def snapshot():
        if not repo_data.is_dir():
            return None
        return sorted((str(p.relative_to(repo_data)), p.stat().st_mtime_ns)
                      for p in repo_data.iterdir() if p.name != "logs")

    before = snapshot()
    ctx = _ctx(DISK)
    assert ctx["workspace_dir"] == root and ctx["active_workspace_id"] is None
    assert not (root / "flights").exists()                 # nothing written before the first workspace
    created = host.dispatch("create_workspace", {"name": "First", "engine_model": "916iS"}, ctx)
    assert (root / "registry.json").is_file()
    assert (root / "workspaces" / created["id"] / "manifest.json").is_file()
    assert json.loads((root / "registry.json").read_text())["workspaces"][0]["id"] == created["id"]
    assert snapshot() == before


# ── Inbound files: the uploads registry (Spec 04 v0.5 §9.1) ────────────────

def test_a_dropped_log_can_come_through_the_uploads_registry(isolated_packaged_home, tmp_path):  # noqa: F811
    ctx = _ctx(DISK)
    host.dispatch("create_workspace", {"name": "U", "engine_model": "916iS"}, ctx)
    f = tmp_path / "upload" / "log_20260101_120000_TEST.csv"
    f.parent.mkdir()
    f.write_bytes(_flight(1))
    ctx["uploads"]["u1"] = {"path": f, "filename": f.name}
    by_upload = host.dispatch("import_files", {"files": [{"upload_id": "u1"}]}, ctx)
    assert by_upload["results"][0]["classification"] == "new"
    again = host.dispatch("import_files", {"files": [{"content": _flight(1), "filename": f.name}]}, ctx)
    assert again["results"][0]["classification"] == "duplicate"     # the same log, by either path
    gone = host.reply({"op": "ingest_log", "params": {"upload_id": "nope"}}, ctx)
    assert gone["error"]["code"] == "NOT_FOUND"


# ── Resumable reads (Spec 04 D11) ──────────────────────────────────────────

def test_a_scan_pauses_for_each_file_and_resumes_with_an_async_supplier(isolated_packaged_home):  # noqa: F811
    """The browser's shape: the listing and every log's bytes arrive later
    (here: after an event-loop turn). The scan pauses at each file request,
    resumes with the bytes, one outstanding at a time, in listing order, and
    gives the same flights as a supplier that answers at once."""
    import asyncio

    logs = {f"log_202601{d:02d}_120000_TEST.csv": _flight(d) for d in (3, 1, 2)}
    events: list[str] = []
    stats = {"outstanding": 0, "peak": 0}

    async def list_folder():
        events.append("list")
        await asyncio.sleep(0)                  # the page answers later
        return [{"relative_path": n, "size": len(b), "last_modified": 0} for n, b in logs.items()]

    async def read(rel):
        stats["outstanding"] += 1
        stats["peak"] = max(stats["peak"], stats["outstanding"])
        events.append(f"request {rel}")
        await asyncio.sleep(0)                  # paused until the bytes come back
        events.append(f"bytes {rel}")
        return logs[rel]

    def release(rel):
        stats["outstanding"] -= 1
        events.append(f"release {rel}")

    source = SuppliedLogSource(None, read, release, list_provider=list_folder)
    ctx = _ctx(SuppliedSources({"f1": source}))

    async def run():
        await host.dispatch_async("create_workspace", {"name": "A", "engine_model": "916iS"}, ctx)
        await host.dispatch_async("register_log_folder", {"name": "Logs", "folder_id": "f1"}, ctx)
        return await host.dispatch_async("scan_workspace", {}, ctx)

    result = asyncio.run(run())
    assert len(result["new_flight_ids"]) == 3 and stats == {"outstanding": 0, "peak": 1}
    names = sorted(logs)                                         # listing order
    assert events == ["list"] + [e for n in names for e in (f"request {n}", f"bytes {n}", f"release {n}")]

    # The same logs from a supplier that answers at once: the same flights.
    sync_ctx = _ctx(SuppliedSources({"f1": SuppliedLogSource(
        [{"relative_path": n, "size": len(b), "last_modified": 0} for n, b in logs.items()], lambda rel: logs[rel])}))
    host.dispatch("create_workspace", {"name": "B", "engine_model": "916iS"}, sync_ctx)
    host.dispatch("register_log_folder", {"name": "Logs", "folder_id": "f1"}, sync_ctx)
    assert sorted(host.dispatch("scan_workspace", {}, sync_ctx)["new_flight_ids"]) == sorted(result["new_flight_ids"])


def test_an_async_source_cannot_be_driven_inline(isolated_packaged_home):  # noqa: F811
    """run_now refuses, rather than blocking, when a source would wait."""
    import asyncio

    async def read(rel):
        await asyncio.sleep(0)
        return b""

    listing = [{"relative_path": "log_20260101_120000_TEST.csv", "size": 1, "last_modified": 0}]
    ctx = _ctx(SuppliedSources({"f1": SuppliedLogSource(listing, read)}))
    host.dispatch("create_workspace", {"name": "C", "engine_model": "916iS"}, ctx)
    host.dispatch("register_log_folder", {"name": "Logs", "folder_id": "f1"}, ctx)
    reply = host.reply({"op": "scan_workspace", "params": {}}, ctx)
    assert not reply["ok"] and "WouldWait" in reply["error"]["message"]
