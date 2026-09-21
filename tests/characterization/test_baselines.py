"""
Stage 0 characterization test (Spec 01 §11, §12 criterion 4).

Locks down write_baselines() (notebooks/03) against frozen golden
snapshots of baselines.json and models.json. The `generated_at` field is
excluded from comparison since it's a wall-clock read (Principle 2 flags
this as something Stage 1 removes from the core) — everything else must
match exactly.
"""
import json

from slingology_eis.loader import deduplicate_flights, find_duplicate_flights, load_directory
from slingology_eis.fleet import build_flight_metrics
from slingology_eis.limits import load_engine_config

from ..conftest import GOLDEN_DIR, LOGS_DIR, import_notebook, requires_flight_logs, requires_golden_fixtures


def _without_generated_at(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "generated_at"}


@requires_flight_logs
@requires_golden_fixtures
def test_baselines_and_models_match_golden(tmp_path):
    notebook_03 = import_notebook("03_multi_flight_insights")

    flights = load_directory(str(LOGS_DIR), verbose=False)
    if find_duplicate_flights(flights):
        flights = deduplicate_flights(flights, prefer="most_rows", verbose=False)
    metrics = build_flight_metrics(flights, field_elev_ft=None, verbose=False)

    engine_name = load_engine_config().get("_metadata", {}).get("engine", "unknown engine")
    out_baselines = tmp_path / "baselines.json"
    notebook_03.write_baselines(metrics, out_baselines, engine_name=engine_name)
    out_models = out_baselines.parent / "models.json"

    actual_baselines = _without_generated_at(json.loads(out_baselines.read_text()))
    golden_baselines = _without_generated_at(json.loads((GOLDEN_DIR / "baselines.json").read_text()))
    assert actual_baselines == golden_baselines

    actual_models = _without_generated_at(json.loads(out_models.read_text()))
    golden_models = _without_generated_at(json.loads((GOLDEN_DIR / "models.json").read_text()))
    assert actual_models == golden_models
