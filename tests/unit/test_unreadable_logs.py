"""
Spec 03 §5.1 "Unreadable" (Spec 02 §5.11.2): a log the scan can't read or
analyse is shown as Unreadable with its reason — never left as "Needs
analysis" for ever, never offered again by Sync, and one such log never
stops the others being analysed.
"""
from slingology_eis import workspace as ws

from .test_server import _flying_log_bytes, isolated_packaged_home, registry_server, rpc  # noqa: F401


def _workspace_with(url, tmp_path, files: dict) -> None:
    rpc(url, "create_workspace", {"name": "W", "engine_model": "916iS"})
    folder = tmp_path / "logs"
    folder.mkdir()
    for name, data in files.items():
        (folder / name).write_bytes(data)
    rpc(url, "add_log_folder", {"path": str(folder)})


def _rows(url):
    return {r["filename"]: r for r in rpc(url, "list_flights_with_status", {})["result"]["rows"]}


def test_an_unrecognised_file_is_unreadable_with_its_reason(registry_server, tmp_path):
    url = registry_server
    _workspace_with(url, tmp_path, {
        "log_20260101_120000_KAWO.csv": _flying_log_bytes(),
        "export_from_other_avionics.csv": b"Time,Altitude,Speed\n1,2,3\n",
    })
    found = rpc(url, "scan_workspace", {"analyze": False})["result"]
    assert len(found["pending_new_logs"]) == 2                  # both found, nothing parsed yet

    result = rpc(url, "scan_workspace", {})["result"]
    assert len(result["new_flight_ids"]) == 1                    # the good one is analysed
    assert result["unreadable"] == [{"filename": "export_from_other_avionics.csv",
                                      "reason": "Format not recognised — not a Garmin G3X engine log this app can read."}]
    row = _rows(url)["export_from_other_avionics.csv"]
    assert row["status"] == "unreadable" and row["unreadable_reason"].startswith("Format not recognised")

    # Sync doesn't offer it again.
    again = rpc(url, "scan_workspace", {"analyze": False})["result"]
    assert again["pending_new_logs"] == []
    assert [r["status"] for r in _rows(url).values()].count("needs_analysis") == 0


def test_a_log_that_fails_analysis_doesnt_stop_the_others(registry_server, tmp_path, monkeypatch):
    url = registry_server
    _workspace_with(url, tmp_path, {
        "log_20260101_120000_KAWO.csv": _flying_log_bytes(date="2026-01-01"),
        "log_20260102_120000_KAWO.csv": _flying_log_bytes(date="2026-01-02"),
    })
    real = ws.analyze_flight

    def flaky(content, filename, *a, **k):
        if "0102" in filename:
            raise KeyError("fuel_flow_gph")
        return real(content, filename, *a, **k)

    monkeypatch.setattr(ws, "analyze_flight", flaky)
    result = rpc(url, "scan_workspace", {})["result"]
    assert len(result["new_flight_ids"]) == 1
    assert result["unreadable"][0]["filename"] == "log_20260102_120000_KAWO.csv"
    assert result["unreadable"][0]["reason"].startswith("Couldn't be analysed")
    assert _rows(url)["log_20260102_120000_KAWO.csv"]["status"] == "unreadable"


def test_a_newer_engine_retries_it(registry_server, tmp_path, monkeypatch):
    url = registry_server
    _workspace_with(url, tmp_path, {"weird.csv": b"not a log at all"})
    rpc(url, "scan_workspace", {})
    assert rpc(url, "scan_workspace", {"analyze": False})["result"]["pending_new_logs"] == []
    monkeypatch.setattr(ws, "__version__", "99.0.0")          # an app update
    assert len(rpc(url, "scan_workspace", {"analyze": False})["result"]["pending_new_logs"]) == 1
