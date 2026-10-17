# Characterization tests (Spec 01 Stage 0)

These tests lock down the current behavior of the toolkit before the
Spec 01 engine-contract migration touches it (`docs/specs/01-engine-contract.md`
§11). They compare fresh output from `slingology_eis`/`notebooks` against a
frozen snapshot in `golden/`.

`golden/` is gitignored, like `data/logs/` and `data/reports/` — it's
derived from private flight data and must not be committed. Each
contributor (or future you) regenerates it locally from their own
`data/logs/`.

## Regenerating the golden snapshot

```bash
python notebooks/03_multi_flight_insights.py
python notebooks/02_engine_ecu_correlation.py
python notebooks/04_flight_report.py <a log filename>   # for each flight you want a report fixture for

mkdir -p tests/characterization/golden/reports
cp data/reports/fleet_metrics.csv tests/characterization/golden/
cp data/reports/baselines.json tests/characterization/golden/
cp data/reports/models.json tests/characterization/golden/
cp data/reports/engine_ecu_runs.csv tests/characterization/golden/
cp data/reports/engine_ecu_report.txt tests/characterization/golden/
cp data/reports/fleet_insights.txt tests/characterization/golden/
cp data/reports/report_*.txt tests/characterization/golden/reports/
```

Only regenerate the snapshot when you *intend* to accept new output as the
new baseline (e.g. after adding real new flights, or after a Stage 1+
change that intentionally changes behavior — diff it first). Tests will
fail loudly if `data/logs/` has changed since the snapshot was captured
without the snapshot being refreshed to match.

If `data/logs/` or `golden/` is absent, these tests are skipped rather
than failed — they require private local flight data that isn't part of
the repo.

## Spec 12 (Trends) golden: `fleet_analysis.json` / `shift_history.json`

A second, separate pair of golden files locks `update_fleet`'s own
output — `shift`, `change_summary`, `shift_history`, and the
takeoff-MAP residual metric — by value (Spec 12 v0.3 acceptance 10,
Session B R3b.4). Regenerate with:

```bash
python tests/characterization/regen_fleet_analysis_golden.py
```

Unlike the snapshot above, this one is **pinned to a cut-off date**
(`CUTOFF_DATE` in the regen script and in
`tests/characterization/test_fleet_analysis_golden.py` — keep the two in
sync) rather than to "however many logs happen to be in `data/logs/`
today": new flights added after the cut-off don't move it, so the
fixture stays meaningful without needing a regen every time someone
drops a new log in. Move the cut-off forward and regenerate only when
you want the fixture to include newer flights.
