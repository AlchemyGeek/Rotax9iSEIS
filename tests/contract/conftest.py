import json
from pathlib import Path

import pytest

from slingology_eis.limits import load_engine_config
from slingology_eis.loader import deduplicate_flights, find_duplicate_flights, load_directory
from slingology_eis.operations import analyze_flight, update_fleet

from ..conftest import LOGS_DIR

_CONTRACT_ROOT = Path(__file__).resolve().parent.parent.parent / "contract"


def load_schema(name: str) -> dict:
    return json.loads((_CONTRACT_ROOT / "schema" / name).read_text())


@pytest.fixture(scope="session")
def real_flight_analyses():
    """All real local flights (private data) as FlightAnalysis objects. Empty if unavailable."""
    if not LOGS_DIR.is_dir() or not any(LOGS_DIR.glob("*.csv")):
        return []
    cfg = load_engine_config()
    flights = load_directory(str(LOGS_DIR), verbose=False)
    if find_duplicate_flights(flights):
        flights = deduplicate_flights(flights, prefer="most_rows", verbose=False)
    fas = []
    for df, info in flights:
        fname = df["_source_file"].iloc[0]
        p = LOGS_DIR / fname
        fas.append(analyze_flight(p.read_bytes(), fname, cfg, "916iS"))
    return fas


@pytest.fixture(scope="session")
def real_fleet_analysis(real_flight_analyses):
    if not real_flight_analyses:
        return None
    return update_fleet(real_flight_analyses)


@pytest.fixture(scope="session")
def rules():
    rules_path = Path(__file__).resolve().parent.parent.parent / "insight_rules.json"
    return json.loads(rules_path.read_text())
