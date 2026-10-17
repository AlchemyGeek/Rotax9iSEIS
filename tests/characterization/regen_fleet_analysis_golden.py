"""
Regenerates tests/characterization/golden/fleet_analysis.json and
shift_history.json — the Spec 12 v0.3 acceptance 10 frozen fixture
(Session B R3b.4). Run this only when you intend to accept new output
as the new baseline (same rule as the other golden/ snapshots — see
tests/characterization/README.md).

    python tests/characterization/regen_fleet_analysis_golden.py

Pinned to a cut-off date (the same one Spec 09's replay acceptance test
uses) so flights logged after it don't silently move this fixture —
regenerate deliberately, by moving the cut-off forward, when you want
new flights included.
"""
import json
import tempfile
from pathlib import Path

from slingology_eis.cli import resolve_logs_dir, _load_flight_analyses
from slingology_eis.limits import load_engine_config
from slingology_eis import operations, workspace as ws

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from replay import chronological

CUTOFF_DATE = "2026-09-27"
ENGINE_NAME = "916iS"
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def main():
    logs_dir = resolve_logs_dir("data/logs")
    engine_cfg = load_engine_config(ENGINE_NAME)
    fas, excluded, _source_paths = _load_flight_analyses(logs_dir, engine_cfg, ENGINE_NAME, quiet=True)
    fas = chronological(fas, pinned_to_date=CUTOFF_DATE)
    if not fas:
        raise SystemExit(f"No flights at or before {CUTOFF_DATE} in {logs_dir} — nothing to freeze.")

    fleet = operations.update_fleet(fas, excluded=excluded, engine_config=engine_cfg)

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    (GOLDEN_DIR / "fleet_analysis.json").write_text(json.dumps(fleet.to_dict(), indent=2, sort_keys=True, default=str))

    # shift_history is populated by the workspace layer (update_shift_history),
    # not update_fleet itself (Session A design: history is a workspace
    # artifact, Spec 02 §6) — run it once against a throwaway workspace
    # dir so the fixture captures a real, non-empty history snapshot
    # rather than always-empty bare-update_fleet output.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        (tmp_dir / "fleet").mkdir()
        history = ws.update_shift_history(tmp_dir, fleet)
    (GOLDEN_DIR / "shift_history.json").write_text(json.dumps(history, indent=2, sort_keys=True, default=str))

    print(f"Wrote {GOLDEN_DIR / 'fleet_analysis.json'} ({len(fas)} flights, cutoff {CUTOFF_DATE})")
    print(f"Wrote {GOLDEN_DIR / 'shift_history.json'} ({len(history)} event(s))")


if __name__ == "__main__":
    main()
