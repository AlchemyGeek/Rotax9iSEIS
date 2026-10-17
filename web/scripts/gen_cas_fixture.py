"""
Regenerate the CAS-event web fixtures (Spec 10 D19) and the Events-table
fixture flight (Spec 03 v0.16 §5.2) from the engine.

The flights are the synthetic logs the server unit tests use
(tests/unit/test_server.py `_ground_and_flight_ecu_log`): eight flights
with a CAS Alert column, ENGINE ECU on the last two — one GROUND run in
TAXI at 2,550 rpm and one IN_FLIGHT run in cruise. No real flight data,
so the output is scrubbed by construction.

    python web/scripts/gen_cas_fixture.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from slingology_eis import filters as _filters  # noqa: E402
from slingology_eis.limits import load_engine_config  # noqa: E402
from slingology_eis.operations import (  # noqa: E402
    analyze_flight, build_trends_panels, evaluate_insights, update_fleet,
)
from slingology_eis.server import _default_rules  # noqa: E402
from slingology_eis.serialize import dumps  # noqa: E402
from tests.unit.test_server import _FLYING_PREAMBLE_LEN, _flying_log_bytes, _ground_and_flight_ecu_log  # noqa: E402

OUT = ROOT / "web" / "src" / "fixtures"
TARGET = {"kind": "cas", "cas_id": "ENGINE ECU"}

# Events fixture: fuel pressure spikes past fuel_press_max (46 psi) — three
# small (+0.8 psi) and one large (+3.5 psi) — one oil temperature spike past
# oil_temp_max (248 °F), and one ENGINE ECU run in TAXI. A fuel-pressure
# filter (+1.5 psi) tolerates the small ones, so the large one is a breach.
_C = _FLYING_PREAMBLE_LEN
# (fuel_press_max needs 30 s in CRUISE.)
_FUEL_SPIKES = {range(_C + 60, _C + 100): 46.8, range(_C + 160, _C + 200): 46.8,
                range(_C + 260, _C + 300): 46.8, range(_C + 400, _C + 445): 49.5}
_OIL_SPIKE = range(_C + 500, _C + 520)
_ECU = range(16, 23)
EVENTS_FILTER = {
    "id": "flt_fuel_press", "target": {"kind": "limit", "limit_id": "fuel_press_max"},
    "magnitude": {"mode": "absolute", "value": 1.5}, "note": "sender reads high",
    "reference": {"flight_ids": [], "set_at": "2026-01-01T00:00:00Z"},
    "created_at": "2026-01-01T00:00:00Z", "history": [],
}


def _events_row(i: int) -> str:
    fuel = next((v for r, v in _FUEL_SPIKES.items() if i in r), 44.0)
    oil = 255.0 if i in _OIL_SPIKE else 210.0
    return f",{fuel},{oil},{'ENGINE ECU' if i in _ECU else ''}"


def _events_log(date: str) -> bytes:
    return _flying_log_bytes(
        date=date, extra_header=",Fuel Press (PSI),Oil Temp (deg F),CAS Alert",
        row_extra_fn=_events_row, rpm_override=lambda i: 2550 if i in _ECU else None,
    )


def main() -> None:
    cfg = load_engine_config("916iS")
    fas = []
    for day in range(1, 9):
        date = f"2026-01-{day:02d}"
        log = _ground_and_flight_ecu_log(date) if day in (7, 8) else _flying_log_bytes(
            date=date, extra_header=",CAS Alert", row_extra_fn=lambda i: ",")
        fas.append(analyze_flight(log, f"log_202601{day:02d}_120000_TEST.csv", cfg, "916iS"))
    fleet = update_fleet(fas, engine_config=cfg)
    fa = fas[-1]
    iset = evaluate_insights(fa, fleet, _default_rules())

    panels = [p for p in build_trends_panels(fleet, {"topics": []}, set()) if p.get("cas_id")]
    metric_id = panels[0]["metrics"][0]["metric_id"]
    fleet_d = fleet.to_dict()
    trends = {
        "panel": panels[0],
        "metric": fleet_d["metrics"][metric_id],
        "flight_ids": fleet_d["flight_ids"],
    }
    proposal = _filters.propose_limit_filter(fas, fleet, TARGET, cfg)
    # A limit target's proposal, for the "this limit" caption test.
    limit_proposal = _filters.propose_limit_filter(fas, fleet, {"kind": "limit", "limit_id": "oil_temp_max"}, cfg)

    # The Events fixture: same eight-flight fleet shape, this log last.
    efas = [analyze_flight(_flying_log_bytes(date=f"2026-02-{d:02d}"), f"log_202602{d:02d}_120000_TEST.csv", cfg, "916iS")
            for d in range(1, 8)]
    efas.append(analyze_flight(_events_log("2026-02-08"), "log_20260208_120000_TEST.csv", cfg, "916iS"))
    efleet = update_fleet(efas, engine_config=cfg, filters=[EVENTS_FILTER])
    eiset = evaluate_insights(efas[-1], efleet, _default_rules(), filters=[EVENTS_FILTER])

    for name, obj in [
        ("flight-cas-analysis.json", fa.to_dict()),
        ("flight-cas-insights.json", iset.to_dict()),
        ("cas-trends.json", trends),
        ("cas-filter-proposal.json", proposal),
        ("limit-filter-proposal.json", limit_proposal),
        ("flight-events-analysis.json", efas[-1].to_dict()),
        ("flight-events-insights.json", eiset.to_dict()),
    ]:
        (OUT / name).write_text(json.dumps(json.loads(dumps(obj)), indent=2) + "\n")
        print("wrote", OUT / name)


if __name__ == "__main__":
    main()
