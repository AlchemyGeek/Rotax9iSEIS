"""
Spec 16 Session F, part 3: what the Flights view and Settings → Aircraft
need from the host — the Flights-table rows carry the route, local start
and zone, takeoffs and landings and the pilot's name (Spec 03 §5.1, Spec 16
§4.4); `aircraft_assign` moves a workspace to another aircraft or a new one;
the `documents` capability says where documents folders are read.
"""
import pytest

from tests.unit.test_research_ops import _import, _ok
from tests.unit.test_server import InProcess, isolated_packaged_home, rpc  # noqa: F401


@pytest.fixture
def h(isolated_packaged_home):
    h = InProcess()
    _ok(rpc(h, "create_workspace", {"name": "Main", "engine_model": "916iS"}))
    return h


def test_flights_rows_carry_identification_and_name(h):
    fid = _import(h, "2026-01-05")
    _ok(rpc(h, "flight_set_name", {"flight_id": fid, "name": "First solo"}))
    rows = _ok(rpc(h, "list_flights_with_status", {}))["rows"]
    row = next(r for r in rows if r["flight_id"] == fid)
    assert row["identified"] is True                      # Sync (here, the import) computed it
    for k in ("route", "start_local", "tz_abbrev", "takeoffs", "landings", "name"):
        assert k in row, k
    assert row["name"] == "First solo" and isinstance(row["route"], list)
    ident = next(r for r in _ok(rpc(h, "list_flights", {})) if r["flight_id"] == fid).get("ident") or {}
    assert row["start_local"] == ident.get("start_local") and row["takeoffs"] == ident.get("takeoffs")


def test_aircraft_assign_moves_a_workspace(h):
    first = _ok(rpc(h, "aircraft_get", {}))
    ws_main = first["workspaces"][0]["id"]
    _ok(rpc(h, "create_workspace", {"name": "915 iS", "engine_model": "915iS", "aircraft_id": first["aircraft"]["id"]}))
    second = next(w for w in _ok(rpc(h, "aircraft_get", {"aircraft_id": first["aircraft"]["id"]}))["workspaces"] if w["id"] != ws_main)
    # The 915 iS workspace to an aircraft of its own.
    moved = _ok(rpc(h, "aircraft_assign", {"workspace_id": second["id"], "new_aircraft": {"name": "Test 915"}}))
    assert moved["aircraft"]["name"] == "Test 915" and moved["aircraft"]["engine_model"] == "915iS"
    assert [w["id"] for w in moved["workspaces"]] == [second["id"]]
    left = _ok(rpc(h, "aircraft_get", {"aircraft_id": first["aircraft"]["id"]}))
    assert [w["id"] for w in left["workspaces"]] == [ws_main]
    # ...and back.
    back = _ok(rpc(h, "aircraft_assign", {"workspace_id": second["id"], "aircraft_id": first["aircraft"]["id"]}))
    assert {w["id"] for w in back["workspaces"]} == {ws_main, second["id"]}
    assert len(_ok(rpc(h, "list_aircraft", {}))) == 2
    for bad in ({"workspace_id": second["id"]}, {"workspace_id": second["id"], "aircraft_id": "x", "new_aircraft": {"name": "y"}}):
        assert rpc(h, "aircraft_assign", bad)["error"]["code"] == "BAD_PARAMS"
    assert rpc(h, "aircraft_assign", {"workspace_id": "ws_nope", "aircraft_id": "x"})["error"]["code"] == "NOT_FOUND"


def test_documents_capability(h):
    assert _ok(rpc(h, "get_capabilities", {}))["features"]["documents"] is True
