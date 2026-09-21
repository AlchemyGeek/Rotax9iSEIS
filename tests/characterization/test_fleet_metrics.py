"""
Stage 0 characterization test (Spec 01 §11, §12 criterion 1/4).

Locks down build_flight_metrics() output against a frozen golden snapshot
of data/reports/fleet_metrics.csv, so later migration stages can prove
they haven't changed current behavior.
"""
import pandas as pd

from slingology_eis.loader import deduplicate_flights, find_duplicate_flights, load_directory
from slingology_eis.fleet import build_flight_metrics

from ..conftest import GOLDEN_DIR, LOGS_DIR, requires_flight_logs, requires_golden_fixtures


@requires_flight_logs
@requires_golden_fixtures
def test_fleet_metrics_matches_golden():
    flights = load_directory(str(LOGS_DIR), verbose=False)
    if find_duplicate_flights(flights):
        flights = deduplicate_flights(flights, prefer="most_rows", verbose=False)

    actual = build_flight_metrics(flights, field_elev_ft=None, verbose=False)
    golden = pd.read_csv(GOLDEN_DIR / "fleet_metrics.csv")

    assert list(actual.columns) == list(golden.columns), (
        "Column set/order changed vs golden fleet_metrics.csv"
    )
    assert len(actual) == len(golden), (
        f"Row count changed: {len(actual)} vs golden {len(golden)} — "
        "has data/logs/ changed since the golden snapshot was captured?"
    )

    # Round-trip `actual` through the same CSV serialization path the golden
    # file was written with, so this compares the artifact as it's actually
    # produced (notebook 03's `metrics.to_csv(...)`) rather than in-memory
    # dtypes that don't survive a CSV round trip anyway (e.g. bool -> str,
    # datetime.date -> str).
    actual_csv = actual.sort_values("source_file").reset_index(drop=True).to_csv(index=False)
    golden_csv = golden.sort_values("source_file").reset_index(drop=True).to_csv(index=False)
    assert actual_csv == golden_csv
