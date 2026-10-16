"""
Spec 02 v0.11 §7 — workspace export and import, on synthetic logs.
(The real-data round trip is run per session and reported; its outputs are
derived from the private logs and are never committed.)
"""
import base64
import io
import json
import zipfile
from pathlib import Path

import pytest

from slingology_eis import __version__
from slingology_eis import workspace as ws
from slingology_eis import workspace_export as wx
from slingology_eis.cli import main
from slingology_eis.loader import flight_fingerprint, flight_id, load_log_bytes

from .test_server import _FLYING_PREAMBLE_LEN, _flying_log_bytes, isolated_packaged_home, registry_server, rpc  # noqa: F401

TAIL, SYSTEM = "N999XX", "60002D19C364F"
META = (f'#airframe_info,log_version="1.00",product="GDU 460",aircraft_ident="{TAIL}",system_id="{SYSTEM}",'
        f'unit="PFD1",airframe_hours="10.5",engine_hours="20.1",flightstream_header="{SYSTEM}_20260101_120000"\n')
EXTRA = ",Latitude (deg),Longitude (deg),Nav Identifier,Oil Temp (deg F)"


def _log(day: int, oil: int = 180, tail=TAIL, system=SYSTEM) -> bytes:
    meta = META.replace(TAIL, tail).replace(SYSTEM, system)
    return _flying_log_bytes(date=f"2026-01-{day:02d}", extra_header=EXTRA, meta=meta,
                             row_extra_fn=lambda i: f",47.{9000 + i},-122.{2800 + i},KAWO,{oil}")


def _logs_folder(tmp_path, days=range(1, 13)) -> Path:
    folder = tmp_path / "logs"
    folder.mkdir()
    for d in days:
        (folder / f"log_202601{d:02d}_120000_KAWO.csv").write_bytes(_log(d, 180 + (d % 3)))
    return folder


def _sender(url, tmp_path):
    """A workspace with logs and decisions of every carried kind."""
    rpc(url, "create_workspace", {"name": "Sender", "engine_model": "916iS"})
    folder = _logs_folder(tmp_path)
    rpc(url, "add_log_folder", {"path": str(folder)})
    rpc(url, "scan_workspace", {})
    fids = sorted(r["flight_id"] for r in rpc(url, "list_flights", {})["result"])
    assert len(fids) == 12
    rpc(url, "save_filter", {"filter": {"limit_id": "rpm_idle_min", "phases": ["TAXI"], "note": "taxi idle"}})
    rpc(url, "exclude_flight", {"flight_id": fids[2], "reason": "odd run"})
    fleet = rpc(url, "get_fleet", {})["result"]
    rpc(url, "save_baseline_config", {"baseline_config": {**fleet["provenance"]["baseline_config"], "outlier_z_threshold": 1.5}})
    rpc(url, "set_reference", {"metric_id": "oil_temp_peak", "flight_ids": fids[:6], "label": "first six"})
    rpc(url, "save_annotation", {"flight_id": fids[4], "ref": {"kind": "flight"}, "note": "checked"})
    return folder, fids


def _active_dir():
    reg = ws.load_registry(ws.resolve_registry_path())
    last = ws.load_app_settings(ws.resolve_registry_path()).last_active_workspace_id
    return ws.resolve_workspaces_root() / next(e.id for e in reg.workspaces if e.id == last)


def _snapshot(url):
    out = {}
    for r in rpc(url, "list_flights", {})["result"]:
        f = rpc(url, "get_flight", {"flight_id": r["flight_id"]})["result"]
        out[f["flight_analysis"]["header"]["start_utc"]] = {
            "insights": sorted((t["topic_id"], i["rule_id"], i["severity"], i["message"]["text"], i.get("note") or "")
                               for t in f["insight_set"]["topics"] for i in t["insights"]),
            "excluded": f["reference_state"]["excluded"],
        }
    kinds = sorted(e["kind"] for e in rpc(url, "get_journal", {})["result"]["entries"])
    return out, kinds


def _export(url, include_logs, anonymise=False):
    res = rpc(url, "export_workspace", {"include_logs": include_logs, "anonymise": anonymise})
    assert res["ok"], res
    with urllib_open(url + res["result"]["download_url"]) as r:
        return res["result"], r.read()


def urllib_open(u):
    import urllib.request
    return urllib.request.urlopen(u, timeout=30)


# ── §7.1 classification ──────────────────────────────────────────────────────

def test_every_workspace_document_is_classified_and_an_unknown_one_stops_the_export(registry_server, tmp_path):
    _sender(registry_server, tmp_path)
    ws_dir = _active_dir()
    classes = {d["path"].split("/")[0] if d["path"].startswith("flights/") else d["path"]: d["class"]
               for d in wx.classify_workspace(ws_dir)}
    assert classes["filters.json"] == "carried" and classes["fleet/analysis.json"] == "derived"
    assert classes["manifest.json"] == "manifest" and classes["flights"] in ("manifest", "derived")
    (ws_dir / "new_document.json").write_text("{}")
    with pytest.raises(wx.ExportError, match="new_document.json"):
        wx.export_workspace(ws_dir, tmp_path / "out")


# ── §7.2–7.3 export ──────────────────────────────────────────────────────────

def test_export_without_logs_carries_decisions_and_a_manifest_never_analyses(registry_server, tmp_path):
    folder, fids = _sender(registry_server, tmp_path)
    res, data = _export(registry_server, include_logs=False)
    assert res["filename"] == "Sender.eisworkspace" and res["logs_included"] == 0
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    assert {"workspace.json", "filters.json", "fleet/selection.json", "journal.json", "annotations.json",
            "settings.json"} <= names
    assert not any("analysis" in n for n in names) and "manifest.json" not in names
    w = json.loads(z.read("workspace.json"))
    assert w["provenance"]["engine_version"] == __version__ and w["provenance"]["logs_included"] is False
    assert sorted(f["flight_id"] for f in w["manifest"]) == fids
    assert all(f["sources"][0]["source_key"] and f["airport_hint"] == "KAWO" for f in w["manifest"])
    assert w["summary"]["filters"] == 1 and w["summary"]["phase_filters"] == 1 and w["summary"]["pins"] == 1
    assert set(json.loads(z.read("settings.json"))) <= {"active_engine_profile", "aircraft_aliases"}


def test_export_with_logs_is_a_folder_in_a_zip(registry_server, tmp_path):
    _sender(registry_server, tmp_path)
    res, data = _export(registry_server, include_logs=True)
    z = zipfile.ZipFile(io.BytesIO(data))
    assert res["filename"] == "Sender.zip"
    assert "Sender/Sender.eisworkspace" in z.namelist()
    assert sorted(n for n in z.namelist() if n.startswith("Sender/logs/")) == \
        sorted(f"Sender/logs/log_202601{d:02d}_120000_KAWO.csv" for d in range(1, 13))


# ── §7.4–7.5 import and matching ─────────────────────────────────────────────

def _unzip(data, where: Path) -> Path:
    zipfile.ZipFile(io.BytesIO(data)).extractall(where)
    return where / "Sender"


def test_round_trip_with_logs_matches_the_sender(registry_server, tmp_path):
    url = registry_server
    _sender(url, tmp_path)
    before = _snapshot(url)
    _res, data = _export(url, include_logs=True)
    folder = _unzip(data, tmp_path / "inbox")
    summary = rpc(url, "inspect_workspace_export", {"path": str(folder)})["result"]
    assert summary["flight_count"] == 12 and summary["engine_check"] == {"status": "same", "ok": True, "message": None}
    imported = rpc(url, "import_workspace", {"path": str(folder)})["result"]
    assert imported["manifest"]["name"] == "Sender (imported)" and imported["logs_linked"] is True
    match = rpc(url, "match_import", {})["result"]
    assert (len(match["found"]), len(match["missing"]), len(match["extra"])) == (12, 0, 0)
    rpc(url, "scan_workspace", {})
    rpc(url, "rebuild_fleet", {})
    assert _snapshot(url) == before
    # The sender's workspace is untouched by the import.
    assert [w["name"] for w in rpc(url, "list_workspaces", {})["result"]] == ["Sender", "Sender (imported)"]


def test_mismatch_missing_flights_are_dormant_and_extra_logs_held_out(registry_server, tmp_path):
    url = registry_server
    _f, fids = _sender(url, tmp_path)
    _res, data = _export(url, include_logs=False)
    export = tmp_path / "Sender.eisworkspace"
    export.write_bytes(data)
    mine = tmp_path / "mine" / "nested"
    mine.mkdir(parents=True)
    names = {}
    for d in range(1, 13):
        b = _log(d, 180 + (d % 3))
        names[flight_id(flight_fingerprint(*load_log_bytes(b, "x.csv")))] = (d, b)
    excluded_fid = fids[2]
    noted_fid = fids[4]
    for fid, (d, b) in names.items():
        if fid not in (excluded_fid, noted_fid):
            (mine / f"copy_{d}.csv").write_bytes(b)           # renamed, nested
    for k in range(3):                                         # another aircraft's logs
        (mine / f"other_{k}.csv").write_bytes(_log(20 + k, tail="N111AA", system="AAAA"))
    rpc(url, "import_workspace", {"content_base64": base64.b64encode(data).decode(), "filename": export.name})
    rpc(url, "add_log_folder", {"path": str(mine.parent)})
    match = rpc(url, "match_import", {})["result"]
    assert (len(match["found"]), len(match["missing"]), len(match["extra"])) == (10, 2, 3)
    assert {m["flight_id"] for m in match["missing"]} == {excluded_fid, noted_fid}
    rpc(url, "scan_workspace", {})
    rpc(url, "rebuild_fleet", {})
    ex = rpc(url, "list_exclusions", {})["result"]
    held = [e for e in ex["entries"] if e["category"] == "not_in_sender"]
    assert len(held) == 3 and held[0]["reason"] == "Not in the sender's workspace"
    assert [m["reason"] for m in ex["sender_missing"]] == ["In the sender's workspace — log not found"] * 2
    journal = rpc(url, "get_journal", {})["result"]["entries"]
    assert any(e["kind"] == "exclusion" and e["ref_id"] == excluded_fid for e in journal)       # dormant
    # Include one extra; the missing log arrives later and its decision applies.
    rpc(url, "include_excluded_log", {"filename": held[0]["filename"]})
    (mine / "late.csv").write_bytes(names[excluded_fid][1])
    rpc(url, "scan_workspace", {})
    flights = {r["flight_id"] for r in rpc(url, "list_flights", {})["result"]}
    assert excluded_fid in flights and len(flights) == 12
    assert rpc(url, "get_flight", {"flight_id": excluded_fid})["result"]["reference_state"]["excluded"] is True
    assert len(rpc(url, "list_exclusions", {})["result"]["sender_missing"]) == 1


def test_skip_linking_leaves_the_empty_state_with_the_manifest(registry_server, tmp_path):
    url = registry_server
    _sender(url, tmp_path)
    _res, data = _export(url, include_logs=False)
    imported = rpc(url, "import_workspace", {"content_base64": base64.b64encode(data).decode(), "filename": "x.eisworkspace",
                                             "name": "Theirs"})["result"]
    assert imported["logs_linked"] is False and imported["manifest"]["name"] == "Theirs"
    info = rpc(url, "get_import_info", {})["result"]
    assert info["imported"] is True and len(info["flights"]) == 12 and not any(f["found"] for f in info["flights"])


# ── §7.6 anonymisation ───────────────────────────────────────────────────────

def test_anonymise_log_rewrites_identity_and_position_only():
    raw = _log(1)
    anon = wx.anonymise_log(raw, {(TAIL, SYSTEM): ("ANON-1", "ANON-1")})
    text = anon.decode()
    assert TAIL not in text and SYSTEM not in text and "KAWO" not in text and "47.9" not in text
    assert 'aircraft_ident="ANON-1"' in text and 'flightstream_header="ANON-1_20260101_120000"' in text
    a, b = load_log_bytes(raw, "a.csv")[0], load_log_bytes(anon, "b.csv")[0]
    for col in ("rpm", "oil_temp_f", "baro_alt_ft", "datetime"):
        assert a[col].equals(b[col]), col


def test_one_pseudonym_per_aircraft_and_aliases_share_one():
    ids = [("N1", "S1"), ("N1", "S1"), ("N2", "S2"), ("N3", "S3")]
    p = wx._aircraft_pseudonyms(ids, [["N1", "N3"]])
    assert p[("N1", "S1")][0] == p[("N3", "S3")][0] != p[("N2", "S2")][0]
    assert p[("N1", "S1")][1] != p[("N3", "S3")][1]          # distinct G3X systems stay distinct


def test_anonymised_round_trip_same_results_and_no_identity_in_the_zip(registry_server, tmp_path):
    url = registry_server
    _f, fids = _sender(url, tmp_path)
    before = _snapshot(url)
    _res, data = _export(url, include_logs=True, anonymise=True)
    blob = b""
    z = zipfile.ZipFile(io.BytesIO(data))
    for n in z.namelist():
        blob += n.encode() + z.read(n)
        if n.endswith(".eisworkspace"):
            inner = zipfile.ZipFile(io.BytesIO(z.read(n)))
            blob += b"".join(inner.read(m) for m in inner.namelist())
    for leak in (TAIL, SYSTEM, "KAWO", "log_2026", "47.9", "-122.2", *fids):
        assert leak.encode() not in blob, leak
    folder = _unzip(data, tmp_path / "inbox")
    rpc(url, "import_workspace", {"path": str(folder)})
    rpc(url, "scan_workspace", {})
    rpc(url, "rebuild_fleet", {})
    assert _snapshot(url) == before


def test_anonymise_needs_logs(registry_server, tmp_path):
    _sender(registry_server, tmp_path)
    res = rpc(registry_server, "export_workspace", {"include_logs": False, "anonymise": True})
    assert res["ok"] is False and "Include logs" in res["error"]["message"]


# ── §7.7 engine versions ─────────────────────────────────────────────────────

def _restamp(data: bytes, version: str) -> bytes:
    src, out = zipfile.ZipFile(io.BytesIO(data)), io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for n in src.namelist():
            b = src.read(n)
            if n == "workspace.json":
                w = json.loads(b)
                w["provenance"]["engine_version"] = version
                b = json.dumps(w).encode()
            z.writestr(n, b)
    return out.getvalue()


def test_engine_versions_refuse_older_warn_newer(registry_server, tmp_path):
    url = registry_server
    _sender(url, tmp_path)
    _res, data = _export(url, include_logs=False)
    newer = base64.b64encode(_restamp(data, "99.0.0")).decode()
    s = rpc(url, "inspect_workspace_export", {"content_base64": newer, "filename": "x.eisworkspace"})["result"]
    assert s["engine_check"]["ok"] is False and "needs engine 99.0.0 or later" in s["engine_check"]["message"]
    refused = rpc(url, "import_workspace", {"content_base64": newer, "filename": "x.eisworkspace"})
    assert refused["ok"] is False and refused["error"]["code"] == "IMPORT_REFUSED"
    older = base64.b64encode(_restamp(data, "0.1.0")).decode()
    s = rpc(url, "inspect_workspace_export", {"content_base64": older, "filename": "x.eisworkspace"})["result"]
    assert s["engine_check"]["status"] == "newer" and "may differ" in s["engine_check"]["message"]
    assert rpc(url, "import_workspace", {"content_base64": older, "filename": "x.eisworkspace"})["ok"]


def test_a_zip_is_refused_with_how_to_unzip(tmp_path):
    p = tmp_path / "Sender.zip"
    p.write_bytes(b"PK")
    with pytest.raises(wx.ImportRefused, match="Unzip it first"):
        wx.read_export(p)


# ── §7.8 CLI, and the retired bundle ─────────────────────────────────────────

def test_cli_export_and_import(registry_server, tmp_path, capsys):
    _sender(registry_server, tmp_path)
    out = tmp_path / "out"
    assert main(["export-workspace", "--workspace", "Sender", "--include-logs", "--out", str(out), "--quiet"]) == 0
    assert (out / "Sender.zip").is_file()
    _unzip((out / "Sender.zip").read_bytes(), tmp_path / "cli-inbox")
    assert main(["import-workspace", str(tmp_path / "cli-inbox" / "Sender"), "--name", "Via CLI", "--yes", "--quiet"]) == 0
    text = capsys.readouterr().out
    assert "12 of 12 flights found · 0 missing · 0 other logs held out" in text and "Analysed 12 flights." in text


def test_export_bundle_is_retired(capsys):
    with pytest.raises(SystemExit) as e:
        main(["export-bundle"])
    assert e.value.code == 2


def test_identity_in_the_senders_own_text_is_pointed_out_not_rewritten(registry_server, tmp_path):
    url = registry_server
    _f, fids = _sender(url, tmp_path)
    rpc(url, "save_annotation", {"flight_id": fids[1], "ref": {"kind": "flight"}, "note": f"{TAIL} oil change"})
    got = rpc(url, "preview_workspace_export", {})["result"]["identity_mentions"]
    assert {(m["where"].split(" (")[0].split(" on flight")[0], m["value"]) for m in got} == {("note", TAIL)}
    _res, data = _export(url, include_logs=True, anonymise=True)
    inner = zipfile.ZipFile(io.BytesIO(zipfile.ZipFile(io.BytesIO(data)).read("Sender/Sender.eisworkspace")))
    assert f"{TAIL} oil change" in inner.read("annotations.json").decode()   # the sender's words, as written


def test_journal_exclusion_shows_the_logs_current_name(registry_server, tmp_path):
    """Spec 02 v0.12: an exclusion entry is labelled with its log's current
    file name — after an import or a rename, not a name stored back then."""
    url = registry_server
    folder, fids = _sender(url, tmp_path)
    excluded = fids[2]
    name = ws.source_filename(_active_dir(), excluded)
    (folder / name).rename(folder / "renamed.csv")
    rpc(url, "scan_workspace", {})
    entry = next(e for e in rpc(url, "get_journal", {})["result"]["entries"]
                 if e["kind"] == "exclusion" and e["ref_id"] == excluded)
    assert entry["what"] == "renamed.csv"
