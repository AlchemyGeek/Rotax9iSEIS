"""
Stage 0 characterization test (Spec 01 §11, §12 criterion 3).

Locks down extract_engine_ecu_runs() across the whole fleet against a
frozen golden snapshot of data/reports/engine_ecu_runs.csv (as built by
notebooks/02_engine_ecu_correlation.py's main loop).
"""
import pandas as pd

from slingology_eis.cas import extract_engine_ecu_runs
from slingology_eis.limits import load_engine_config
from slingology_eis.loader import deduplicate_flights, find_duplicate_flights, load_directory

from ..conftest import GOLDEN_DIR, LOGS_DIR, requires_flight_logs, requires_golden_fixtures


@requires_flight_logs
@requires_golden_fixtures
def test_ecu_runs_match_golden():
    flights = load_directory(str(LOGS_DIR), verbose=False)
    if find_duplicate_flights(flights):
        flights = deduplicate_flights(flights, prefer="most_rows", verbose=False)

    engine_cfg = load_engine_config()
    all_runs = []
    for df, _info in flights:
        all_runs.extend(extract_engine_ecu_runs(df, engine_config=engine_cfg))

    actual = pd.DataFrame(all_runs)
    golden = pd.read_csv(GOLDEN_DIR / "engine_ecu_runs.csv")

    assert list(actual.columns) == list(golden.columns)
    assert len(actual) == len(golden), (
        f"Run count changed: {len(actual)} vs golden {len(golden)}"
    )

    sort_cols = ["source_file", "start_idx"]
    actual_sorted = actual.sort_values(sort_cols).reset_index(drop=True)
    golden_sorted = golden.sort_values(sort_cols).reset_index(drop=True)

    # Float means (e.g. oil_nan_frac) differ at the ULP level between two
    # independent parses of the same CSV data — reduction order depends on
    # array memory layout, not on the data. Round before comparing; this is
    # far tighter than anything that would matter for the underlying signal.
    numeric_cols = golden_sorted.select_dtypes(include="number").columns
    actual_sorted[numeric_cols] = actual_sorted[numeric_cols].round(9)
    golden_sorted[numeric_cols] = golden_sorted[numeric_cols].round(9)

    # Round-trip through the same CSV serialization path the golden file was
    # written with (notebook 02's `runs_df.to_csv(...)`), avoiding in-memory
    # dtype mismatches (datetime.date/list objects vs CSV strings) that
    # don't reflect real differences.
    actual_csv = actual_sorted.to_csv(index=False)
    golden_csv = golden_sorted.to_csv(index=False)
    assert actual_csv == golden_csv

    classification_counts = actual["classification"].value_counts().to_dict()
    golden_counts = golden["classification"].value_counts().to_dict()
    assert classification_counts == golden_counts
