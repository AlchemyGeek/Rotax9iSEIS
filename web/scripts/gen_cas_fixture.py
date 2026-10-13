"""
Regenerate the CAS-event web fixtures (Spec 10 D19) from the engine.

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
from tests.unit.test_server import _flying_log_bytes, _ground_and_flight_ecu_log  # noqa: E402

OUT = ROOT / "web" / "src" / "fixtures"
TARGET = {"kind": "cas", "cas_id": "ENGINE ECU"}


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

    for name, obj in [
        ("flight-cas-analysis.json", fa.to_dict()),
        ("flight-cas-insights.json", iset.to_dict()),
        ("cas-trends.json", trends),
        ("cas-filter-proposal.json", proposal),
    ]:
        (OUT / name).write_text(json.dumps(json.loads(dumps(obj)), indent=2) + "\n")
        print("wrote", OUT / name)


if __name__ == "__main__":
    main()
