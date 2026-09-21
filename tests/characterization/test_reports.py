"""
Stage 0 characterization test (Spec 01 §11).

Locks down the plain-language per-flight report (notebooks/04) against
frozen golden report text, for every flight with a golden fixture. Relies
on data/reports/fleet_metrics.csv, baselines.json, and models.json on
disk being current (see test_fleet_metrics.py / test_baselines.py, which
characterize how those are produced).
"""
import re

import pytest

from ..conftest import GOLDEN_DIR, LOGS_DIR, import_notebook, requires_flight_logs, requires_golden_fixtures

# The report embeds baselines.json's `generated_at` (today's date at the time
# baselines were last built) — a wall-clock read Stage 1 removes from the
# core (Principle 2). Normalize it out; everything else must match exactly.
_GENERATED_AT_RE = re.compile(r"(Baselines:\s+\d+ flights\s+\()\d{4}-\d{2}-\d{2}(\))")


def _normalize(text: str) -> str:
    return _GENERATED_AT_RE.sub(r"\1DATE\2", text)

GOLDEN_REPORTS_DIR = GOLDEN_DIR / "reports"

if GOLDEN_REPORTS_DIR.is_dir():
    _CASES = sorted(
        p.name[len("report_"):-len(".txt")]
        for p in GOLDEN_REPORTS_DIR.glob("report_*.txt")
    )
else:
    _CASES = []


@requires_flight_logs
@requires_golden_fixtures
@pytest.mark.skipif(not _CASES, reason="No golden report fixtures found")
@pytest.mark.parametrize("log_stem", _CASES)
def test_flight_report_matches_golden(log_stem, monkeypatch, capsys):
    log_path = LOGS_DIR / f"{log_stem}.csv"
    if not log_path.exists():
        pytest.skip(f"Source log for golden report no longer present: {log_path.name}")

    notebook_04 = import_notebook("04_flight_report")
    monkeypatch.setattr("sys.argv", ["04_flight_report.py", str(log_path)])

    notebook_04._main()
    actual = capsys.readouterr().out

    golden = (GOLDEN_REPORTS_DIR / f"report_{log_stem}.txt").read_text()
    assert _normalize(actual) == _normalize(golden)
