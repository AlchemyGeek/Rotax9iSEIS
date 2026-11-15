"""
Spec 16 D10 / §4.4: flight identification — airports from GPS against the
bundled table, takeoffs and landings (a touch-and-go included), local time
(the log's zone, or the longitude's with daylight saving by region),
flights_find, flight names; the operations three ways.
"""
import base64
from datetime import date

import numpy as np
import pandas as pd
import pytest

from slingology_eis import flight_ident as FI
from tests.unit.test_research_ops import _ok
from tests.unit.test_server import (  # noqa: F401 — fixtures
    _flying_log_bytes, _node_host, isolated_packaged_home, registry_server, rpc,
)

KTOA = (33.8034, -118.3400, 103)
KSMO = (34.0158, -118.4510, 170)


def _flight(offset=None, day="2026-07-04", start="15:00:00"):
    """KTOA → touch-and-go at KSMO → full stop at KTOA, 1 Hz, phases as the
    phase detector would leave them (no ground phase at the touch-and-go)."""
    rows, phases = [], []

    def seg(n, lat0, lon0, lat1, lon1, alt0, alt1, phase):
        s = len(rows)
        for k in range(n):
            f = k / max(1, n - 1)
            rows.append((lat0 + (lat1 - lat0) * f, lon0 + (lon1 - lon0) * f, alt0 + (alt1 - alt0) * f))
        phases.append({"phase": phase, "start_s": float(s), "end_s": float(len(rows))})
    seg(120, *KTOA[:2], *KTOA[:2], KTOA[2], KTOA[2], "TAXI")
    seg(10, *KTOA[:2], *KTOA[:2], KTOA[2], KTOA[2], "TAKEOFF_ROLL")
    seg(400, *KTOA[:2], *KSMO[:2], KTOA[2] + 20, 1500, "CLIMB")
    seg(300, *KSMO[:2], *KSMO[:2], 1500, KSMO[2] + 60, "APPROACH")
    seg(8, *KSMO[:2], *KSMO[:2], KSMO[2] + 5, KSMO[2] + 5, "APPROACH")      # the touch: 5 ft above the field
    seg(400, *KSMO[:2], *KTOA[:2], KSMO[2] + 60, 1500, "CLIMB")
    seg(300, *KTOA[:2], *KTOA[:2], 1500, KTOA[2] + 40, "APPROACH")
    seg(40, *KTOA[:2], *KTOA[:2], KTOA[2], KTOA[2], "LANDING_ROLL")
    seg(120, *KTOA[:2], *KTOA[:2], KTOA[2], KTOA[2], "TAXI")
    df = pd.DataFrame(rows, columns=["lat", "lon", "baro_alt_ft"])
    df["elapsed_s"] = np.arange(len(df), dtype=float)
    df["datetime"] = pd.Timestamp(f"{day} {start}") + pd.to_timedelta(df["elapsed_s"], unit="s")
    if offset is not None:
        df["utc_offset"] = offset
    return df, phases


def test_route_counts_and_the_logs_zone():
    df, phases = _flight(offset="-07:00")
    f = FI.compute(df, phases)
    assert (f["dep_airport"], f["arr_airport"]) == ("KTOA", "KTOA")
    assert f["route"] == ["KTOA", "KSMO", "KTOA"]
    assert (f["takeoffs"], f["landings"]) == (2, 2)
    assert [s["airport"] for s in f["stops"]] == ["KTOA", "KSMO", "KTOA"] and f["stops"][1]["touch_and_go"]
    assert f["start_local"] == "2026-07-04T15:00:00-07:00" and f["tz_source"] == "log" and f["tz_abbrev"] == "PDT"
    assert f["max_altitude_ft"] == 1500


def test_no_zone_uses_the_longitude_and_daylight_saving():
    # A clock without a zone (the AXIS's +00:00): times are UTC; local from the longitude, DST by region.
    summer, phases = _flight(offset="+00:00", day="2026-07-04", start="22:00:00")
    f = FI.compute(summer, phases)
    assert f["tz_source"] == "longitude" and f["utc_offset"] == "-07:00" and f["tz_abbrev"] == "PDT"
    assert f["start_local"] == "2026-07-04T15:00:00-07:00" and f["utc_start"] == "2026-07-04T22:00:00Z"
    winter, phases = _flight(day="2026-12-04", start="22:00:00")
    w = FI.compute(winter, phases)
    assert w["utc_offset"] == "-08:00" and w["tz_abbrev"] == "PST" and w["local_date"] == "2026-12-04"


def test_codes_pilots_use():
    assert FI.code(FI.search("KMAN")[0]) == "KMAN"            # OurAirports' ident is KS67
    assert FI.code(FI.search("0S9")[0]) == "0S9"              # no K before a digit identifier
    assert "KBLI" in {FI.code(i) for i in FI.search("Bellingham")}
    assert FI.nearest(KTOA[0] + 0.05, KTOA[1]) is None        # 5.6 km: none


def test_labels():
    ident = {"start_local": "2026-11-11T12:49:15-08:00", "tz_abbrev": "PST"}
    assert FI.window_label(ident, 367) == "2026-11-11 12:55:22 PST (+06:07 into the flight)"
    assert FI.window_label(ident, 367, 424) == "2026-11-11 12:55:22–12:56:19 PST (+06:07–+07:04 into the flight)"


def test_find_ranks_and_says_what_matched():
    rows = [
        {"flight_id": "a", "ident": {"local_date": "2026-10-24", "start_local": "2026-10-24T08:15:56-07:00",
                                     "route": ["KAWO", "KPAE", "KBLI", "KAWO"], "landings": 3, "takeoffs": 3}},
        {"flight_id": "b", "ident": {"local_date": "2026-10-28", "start_local": "2026-10-28T12:00:00-07:00",
                                     "route": ["KAWO"], "landings": 3, "takeoffs": 3}},
        {"flight_id": "c", "name": "Bellingham fuel run", "ident": {"local_date": "2026-09-01",
                                                                     "start_local": "2026-09-01T09:00:00-07:00",
                                                                     "route": ["KAWO", "KPAE"], "landings": 2}},
    ]
    got = FI.find(rows, "the Oct 24 flight with three landings, Bellingham", today=date(2026, 11, 15))
    assert [c["flight_id"] for c in got["candidates"]][:1] == ["a"]
    assert "airport KBLI (bellingham)" in got["candidates"][0]["matched"] and "3 landings" in got["candidates"][0]["matched"]
    assert FI.find(rows, "fuel run", today=date(2026, 11, 15))["candidates"][0]["flight_id"] == "c"
    last = FI.find(rows, "last Wednesday", today=date(2026, 10, 30))   # 2026-10-28 was a Wednesday
    assert last["candidates"][0]["flight_id"] == "b"


# ── the operations, three ways ─────────────────────────────────────────────

def _gps_log(day: str) -> bytes:
    """A synthetic G3X flight that starts on the ground at KTOA."""
    def extra(i):
        lat = KTOA[0] + (0 if i < 26 else (i - 26) * 0.0004)
        return f",{lat:.6f},{KTOA[1]:.6f},-08:00"
    return _flying_log_bytes(date=day, extra_header=",Latitude (deg),Longitude (deg),UTC Offset (hh:mm)",
                             row_extra_fn=extra)


def test_ops_identify_name_find(registry_server):
    h = registry_server
    _ok(rpc(h, "create_workspace", {"name": "Ident", "engine_model": "916iS"}))
    ids = []
    for day in ("2026-01-05", "2026-01-09"):
        b64 = base64.b64encode(_gps_log(day)).decode()
        imp = _ok(rpc(h, "import_files", {"files": [{"content_base64": b64,
                                                     "filename": f"log_{day.replace('-', '')}_120000_KTOA.csv"}]}))
        ids.append(imp["results"][0]["flight_id"])
    rows = _ok(rpc(h, "list_flights", {"identify": True}))
    by = {r["flight_id"]: r for r in rows}
    i = by[ids[0]]["ident"]
    assert i["dep_airport"] == "KTOA" and i["takeoffs"] == 1 and i["landings"] == 0 and i["route"] == ["KTOA"]
    assert i["start_local"] == "2026-01-05T12:00:00-08:00" and i["tz_abbrev"] == "PST"
    # Stored: a plain list_flights carries it without reading logs.
    assert _ok(rpc(h, "list_flights", {}))[0]["ident"]["dep_airport"] == "KTOA"
    named = _ok(rpc(h, "flight_set_name", {"flight_id": ids[1], "name": "Prop balance check", "notes": "after the shop"}))
    assert named["name"] == "Prop balance check"
    only = _ok(rpc(h, "list_flights", {"name": "balance"}))
    assert [r["flight_id"] for r in only] == [ids[1]] and only[0]["name"] == "Prop balance check"
    bad = rpc(h, "flight_set_name", {"flight_id": "nope", "name": "x"})
    assert not bad["ok"] and bad["error"]["code"] == "NOT_FOUND"
    # A server host (also under Pyodide in Node); the browser host answers UNSUPPORTED_IN_HOST.
    c = _ok(rpc(h, "flights_find", {"description": "the prop balance flight from Torrance"}))["candidates"]
    assert c[0]["flight_id"] == ids[1] and any("KTOA" in m for m in c[0]["matched"])


def test_the_browser_host_refuses_the_server_operations(isolated_packaged_home):  # noqa: F811
    """Spec 04 §9.5: flights_find, the documents and the bench are the server host's."""
    from slingology_eis import host
    from slingology_eis.log_sources import DISK
    ctx = host.new_context(log_sources=DISK, host="browser")
    host.dispatch("create_workspace", {"name": "B", "engine_model": "916iS"}, ctx)
    for op, params in (("flights_find", {"description": "yesterday"}), ("documents_list", {}),
                       ("document_read", {"name": "om.md"}), ("code_run", {"study_id": "x", "source": "1"})):
        assert host.reply({"op": op, "params": params}, ctx)["error"]["code"] == "UNSUPPORTED_IN_HOST", op
    # Naming a flight is everyone's.
    assert host.reply({"op": "flight_set_name", "params": {"flight_id": "x", "name": "y"}}, ctx)["error"]["code"] == "NOT_FOUND"
