"""
Spec 12 v0.3 acceptance 10 (Session B R3b.4): a frozen `FleetAnalysis`
fixture for the full log set — none existed before Session A; the
pre-Spec-12 characterization goldens cover `build_flight_metrics` only
(fleet_metrics.csv/baselines.json/models.json), never `update_fleet`'s
own `shift`/`change_summary`/`shift_history`/the takeoff-MAP residual.

Regenerate with `python tests/characterization/regen_fleet_analysis_golden.py`
(same "only when you mean to accept new output" rule as every other
golden/ snapshot — see tests/characterization/README.md). CUTOFF_DATE
here must match the regen script's constant exactly.
"""
import json
import tempfile
from pathlib import Path

import pytest

from slingology_eis.cli import resolve_logs_dir, _load_flight_analyses
from slingology_eis.limits import load_engine_config
from slingology_eis import operations, workspace as ws

from ..conftest import GOLDEN_DIR, LOGS_DIR, requires_flight_logs, requires_golden_fixtures
from ..replay import chronological

CUTOFF_DATE = "2026-09-27"
ENGINE_NAME = "916iS"


@pytest.fixture(scope="module")
def frozen_fleet():
    engine_cfg = load_engine_config(ENGINE_NAME)
    fas, excluded, _ = _load_flight_analyses(resolve_logs_dir(str(LOGS_DIR)), engine_cfg, ENGINE_NAME, True)
    fas = chronological(fas, pinned_to_date=CUTOFF_DATE)
    return operations.update_fleet(fas, excluded=excluded, engine_config=engine_cfg)


@pytest.fixture(scope="module")
def golden_fleet():
    return json.loads((GOLDEN_DIR / "fleet_analysis.json").read_text())


@pytest.fixture(scope="module")
def golden_shift_history():
    return json.loads((GOLDEN_DIR / "shift_history.json").read_text())


@requires_flight_logs
@requires_golden_fixtures
def test_flight_set_unchanged_since_the_golden_was_captured(frozen_fleet, golden_fleet):
    assert frozen_fleet.flight_ids == golden_fleet["flight_ids"], (
        "data/logs/ has flights at or before the cut-off date that weren't there when "
        f"the golden was captured — regenerate deliberately if {CUTOFF_DATE} should move."
    )


@requires_flight_logs
@requires_golden_fixtures
def test_change_summary_matches_golden_by_value(frozen_fleet, golden_fleet):
    assert frozen_fleet.change_summary == golden_fleet["change_summary"]


@requires_flight_logs
@requires_golden_fixtures
def test_coupled_cylinder_row_and_residual_shift_match_golden_by_value(frozen_fleet, golden_fleet):
    for metric_id in ("egt2_deviation", "egt3_deviation", "takeoff_map_residual_inhg"):
        mine = frozen_fleet.metrics[metric_id]["shift"]
        golden = golden_fleet["metrics"][metric_id]["shift"]
        assert mine["shift_z"] == golden["shift_z"], metric_id
        assert mine["direction"] == golden["direction"], metric_id
        assert mine["qualifies"] == golden["qualifies"], metric_id
        assert mine["level"] == golden["level"], metric_id
        assert mine["comparison"] == golden["comparison"], metric_id
        assert mine.get("bend") == golden.get("bend"), metric_id


@requires_flight_logs
@requires_golden_fixtures
def test_residual_points_match_golden_by_value(frozen_fleet, golden_fleet):
    mine = {p["flight_id"]: p["value"] for p in frozen_fleet.metrics["takeoff_map_residual_inhg"]["points"]}
    golden = {p["flight_id"]: p["value"] for p in golden_fleet["metrics"]["takeoff_map_residual_inhg"]["points"]}
    assert mine == golden


@requires_flight_logs
@requires_golden_fixtures
def test_shift_history_matches_golden_by_value(frozen_fleet, golden_shift_history):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        (tmp_dir / "fleet").mkdir()
        history = ws.update_shift_history(tmp_dir, frozen_fleet)

    # id/detected_at (and cleared_at, if ever present) are generated fresh
    # on every run (uuid4 / datetime.now()) — compare everything else.
    _VOLATILE = {"id", "detected_at", "cleared_at"}

    def _stable(events):
        return [{k: v for k, v in ev.items() if k not in _VOLATILE} for ev in events]

    assert _stable(history) == _stable(golden_shift_history)
