# Changelog — Slingology EIS Toolkit

All notable changes to the `slingology_eis` toolkit are recorded here.
Check your installed version with:

```bash
python -c "import slingology_eis; print(slingology_eis.__version__)"
```

---

## 0.10.0 — July 7, 2026

**New script: `04_flight_report.py`** — per-flight pilot report with two-layer Analysis/Insight format. Accepts a log filename alone (resolved against `data/logs/`) or a full path, matching script 01 behaviour. Report header shows flight date, time, airport (from filename where available), engine hours start→end, airborne duration, max altitude, max IAS, and FADEC fuel used. Saves report to `data/reports/report_<logname>.txt`.

**Two-layer Analysis/Insight format (A1 complete).** Every analytics topic produces an Analysis line (always present, descriptive) and a conditional Insight line (only when something is worth flagging). Trigger rules defined in `insight_rules.json` at the toolkit root — three trigger types: `threshold`, `baseline_deviation`, `trend`. Adding or adjusting triggers requires only editing the JSON file, no code changes.

**`insight_rules.json`** — new file at toolkit root. Defines trigger rules for all 14 analytics topics. Three trigger types: `threshold` (hard limit check), `baseline_deviation` (z-score vs personal average), `trend` (R²-gated directional trend). Same z-score threshold across all stratification bands.

**`reports/baselines.json`** — written by script 03 after every run. Contains per-metric mean, std, n, confidence label, stratified sub-baselines by DA/OAT band, trend coefficients (R²-gated), and raw per-flight data points for future visualisation. Read by script 04 for all baseline comparisons without reloading all logs.

**`reports/models.json`** — written by script 03 alongside baselines. Contains empirical regression models. Currently holds the `takeoff_map` model: linear regression MAP = f(pressure_alt_ft, oat_c), RPM ≥ 5,500 capture threshold during TAKEOFF_ROLL phase. Confidence thresholds: n<5 = "still collecting data", n 5–14 = LOW, n≥15 = MODERATE. Current model: n=15, MODERATE, R²=0.71. Extensible for future models (A5 fuel flow, etc.).

**All 14 A2 analytics topics implemented in script 04:**
- EGT spread — baseline deviation + trend triggers; cruise mean vs personal average vs OM 392°F limit
- EGT4 elevation — baseline deviation; EGT4 vs cylinders 1–3 vs personal average
- Cylinder rank stability — which cylinder is consistently hottest; fleet stable count context; insight if rank unstable during cruise
- Oil temperature — threshold (OM 248°F) + baseline deviation; personal average comparison
- Coolant temperature — threshold (OM 248°F) + baseline deviation; personal average comparison
- Oil/coolant ratio — baseline deviation; personal average comparison
- Overboost time — threshold trigger (300s OM limit) with close-call flag at 240–300s
- Cruise efficiency — DA-stratified baseline deviation; DA context note added
- Cruise fuel flow — baseline deviation; cruise DA vs fleet average DA context; note if this flight significantly above average DA
- MAP at takeoff — empirical linear regression model; shows "still collecting data (n=X)" until n≥5; 1.5 inHg deviation threshold for insight
- ENGINE ECU — uses `extract_engine_ecu_runs()` classifier from `cas.py`; per-event detail for IN_FLIGHT events including co-active alerts; OIL PRESS specifically flagged
- Operating limit exceedances — phase-filtered, duration-thresholded; `report_in_exceedances` flag suppresses guidance bands
- Climb thermal rate — baseline deviation; oil temp rise rate °F/min during climb
- Flight phase mix — DROPPED as standalone; replaced with "no cruise detected" header warning when cruise data is missing

**Fleet Insights section added to script 03.** Appears at end of output and saved as `reports/fleet_insights.txt`. Tight summary of major findings only — no noise. `⚠` lines for: hard OM limit exceedances, IN-FLIGHT ENGINE ECU events, confirmed trends (R²≥0.5, n≥10), outliers (z≥2.5). `✓` lines only for safety-critical clean checks (no limit exceedances, no IN-FLIGHT ENGINE ECU events).

**`cas.py` — ENGINE ECU classifier refactored into library.**
- `classify_engine_ecu_run()` and `extract_engine_ecu_runs()` moved from `02_engine_ecu_correlation.py` into `cas.py` as importable library functions
- Script 02 and script 04 both import from `cas.py` — single source of truth, no code duplication
- Lane check pairing logic included in `extract_engine_ecu_runs()` — LANE_CHECK events within `_LANE_CHECK_PAIR_WINDOW_S` seconds of each other are marked as paired
- Classifier constants (`_RPM_RUNNING`, `_VOLTAGE_DECLINE_THRESHOLD`, `_LANE_CHECK_MAX_IAS_KT`, `_LANE_CHECK_PAIR_WINDOW_S`) are signal-processing heuristics that live in code; engine-specific thresholds (lane check RPM band, max duration) are read from engine config
- Additional SHUTDOWN gate added: low IAS + low-medium RPM + duration >30s → SHUTDOWN, preventing long taxi/shutdown sequences from being misclassified as IN_FLIGHT

**`limits.py` — phase filtering and duration thresholds.**
- `Limit` dataclass extended with four new fields: `phases` (list of flight phases where limit applies), `min_duration_s` (flat minimum duration), `min_duration_by_phase` (per-phase duration dict, `null` = suppress entirely), `report_in_exceedances` (bool, default true)
- `check_exceedances()` honours all new fields — phase filtering applied before checking, duration filtering applied per event
- Eliminates false positives from sensor noise, pre-flight readings, and expected transient events

**`engines/916iS.json` — phase-aware exceedance suppression.**
- Fuel pressure maximum: `min_duration_by_phase` — suppressed entirely during TAXI/TAKEOFF_ROLL/LANDING (pump test and tank switching transients), 10s minimum during CLIMB/DESCENT, 30s minimum during CRUISE (covers full tank switching sequence)
- Fuel pressure minimum: `min_duration_s: 10` — filters brief sensor transients
- Idle RPM minimum: `min_duration_s: 30` — filters normal governor variation (1780–1790 rpm is within normal range)
- Oil temp optimal band: `report_in_exceedances: false` — guidance band reported in oil temp analysis section, not exceedances
- Oil temp min (takeoff): `phases: ["TAKEOFF_ROLL", "CLIMB", "CRUISE"]` — excludes pre-flight readings
- Oil pressure min (>3500 rpm): `phases: ["CLIMB", "CRUISE", "DESCENT"]` — excludes engine start and taxi

**`fleet.py` — new `FlightMetrics` fields.**
- `takeoff_map_inhg` — median MAP during TAKEOFF_ROLL with RPM ≥ 5,500
- `takeoff_pressure_alt_ft` — median pressure altitude during same window
- `takeoff_oat_c` — median OAT during same window
- `inflight_ecu_count` — count of genuine IN_FLIGHT ENGINE ECU events per flight using `cas.py` classifier (replaces unreliable `cas_inflight_anomaly_count` for fleet-level reporting)
- `cruise_da_ft` added to `baselines.json` metric definitions for DA context in cruise fuel flow section

**`loader.py` — datetime parsing fix.** Explicit `format="%Y-%m-%d %H:%M:%S"` added to `pd.to_datetime()` call, eliminating per-element dateutil fallback warning on every log load.

**Aircraft registration corrected** — N5512E → N117ZS throughout research paper and all scripts.

**Fleet count clarified** — 23 real flights (50 total log files, 27 ground sessions filtered at loader level). All analytics, baselines, and insights correctly use 23 flights.

**`__version__` bumped to `0.10.0`** in `slingology_eis/__init__.py`.

---

## 0.9.0 — June 23, 2026

**Multi-engine support via external config files.** All operating limits previously hardcoded in `limits.py` are now loaded from JSON engine config files in the `engines/` directory. Engine selection resolves in priority order: explicit argument → `SLINGOLOGY_ENGINE` environment variable → `config.json` in the toolkit root → default (916iS).

**Engine configs:**
- `engines/916iS.json` — fully sourced from OM-916 i/C24, Edition 0 / Rev. 1. Status: `VERIFIED`.
- `engines/915iS.json`, `engines/914iS.json`, `engines/912iS.json` — placeholder configs with estimated values from published specs. Status: `PLACEHOLDER`. Attempting to use these fires a `UserWarning` reminding you to verify against the official OM before operational use.

**`config.json`** added to toolkit root — set `"engine": "916iS"` (or another engine name) once, and all scripts pick it up automatically. No per-run argument needed.

**All hardcoded engine-specific thresholds replaced:**
- `limits.py` — all `Limit` objects and EGT spread conditional thresholds now read from the engine config
- `phases.py` — `overboost_time()` reads RPM threshold, power threshold, and time limit from the engine config's `overboost` block
- `02_engine_ecu_correlation.py` — LANE_CHECK RPM band and max duration read from the engine config's `phase_detection` block
- `03_multi_flight_insights.py` — overboost section uses config-driven limit values; engine name shown in report header

**`limits_report()` now shows engine name** and flags PLACEHOLDER configs explicitly in the output.

**Backlog item D1 completed.** Adding a new engine requires only a new JSON file sourced from its OM — no code changes.

---

## 0.8.0 — June 23, 2026

**Ground-session filtering moved to the loader.** Ground-only sessions are now excluded at `load_directory()` time by default (`skip_ground_sessions=True`). Detection: a file is excluded if estimated airborne time (rows with RPM > 3,000 AND IAS > 30kt) is under 3 minutes. Ground sessions print as `·` with an explicit "ground session — skipped" label; the summary line reports "Loaded N flight(s), skipped M ground session(s)."

`real_flights_only()` in `fleet.py` and `MIN_AIRBORNE_MIN_FOR_FLEET_STATS` removed — superseded by the loader-level filter. Pass `skip_ground_sessions=False` to `load_directory()` to examine ground sessions directly.

**Community data backlog item removed.** Fleet-level comparisons using logs from other aircraft removed as out of scope.

---

## 0.7.0 — June 20, 2026

**New module: `climb.py`** — climb-rate-correlated thermal analysis. Bins CLIMB-phase rows by VS (gentle <500fpm, normal 500–1000fpm, aggressive >1000fpm) and computes °F/min rise rate per bucket via linear fit. First real finding: oil temp rise rate roughly tripled (+4.4 → +12.8°F/min) from normal to aggressive climb rate. Wired into `01_first_flight_analysis.py` and `fleet.py`.

**DA/OAT stratification in `fleet.py`.** `FlightMetrics` now carries `cruise_da_ft`, `cruise_oat_c`, `da_band`, `oat_band`. New `baseline_stratified()` and `trend_stratified()` group by band before computing statistics. Cruise efficiency moved to DA-banded trend; EGT spread gained OAT-banded trend in script 03.

**Overboost distribution / throttle-discipline view.** Script 03 now reports exceeded/close-call/comfortable buckets across all flights plus a trend.

**Script 02 text report** now includes the IN-FLIGHT interpretation section that was previously console-only.

**Validated against 50-flight dataset** — 23 real flights, 27 ground sessions. Found 1 genuine IN_FLIGHT ENGINE ECU event (KSFF, OIL PRESS co-active) and one real overboost exceedance (confirmed ATC-workload-related, 381s).

---

## 0.6.0 — June 20, 2026

**Fuel-flow calibration (K_fuel) deliberately descoped.** For full-to-full refuelling, gallons added at the pump already equals true consumption directly. Removed: `FillEvent`, `save_fills`, `load_fills`, `fadec_gallons_for_window`, `import_fills_csv`, `import_and_save_fills`, `compute_k_fuel`, `scripts/import_fills.py`. See research paper §6.2.

**Script 03 reorganized** from 6 sections to 5 — "Maintenance" section was a mislabel; metrics redistributed to Trends and Operational.

**Changelog split** from README into this file.

---

## 0.5.0 — June 19, 2026

Fuel CSV import multi-flight gap handling — `fadec_gallons` summed across all flights in the window between consecutive fills. *(Superseded by 0.6.0 — entire feature removed.)*

---

## 0.4.0 — June 19, 2026

Fuel fill-up CSV import (`scripts/import_fills.py`). Version tracking added to README and `__version__`. *(Superseded by 0.6.0 — entire feature removed.)*

---

## 0.3.0 — June 19, 2026

Duplicate flight detection (`find_duplicate_flights`, `deduplicate_flights`) wired into scripts 02 and 03. Catches same flight exported twice (SD-card + Garmin Pilot).

---

## 0.2.0 — June 16, 2026

`03_multi_flight_insights.py` and `fleet.py` added: baselines, trends, outliers, operational/data-quality summaries. Phase detection fixes: auto field-elevation estimation per flight; hysteresis added to CRUISE/CLIMB/DESCENT transitions. `01_first_flight_analysis.py` takes a filename argument.

---

## 0.1.x — June 16, 2026

Initial toolkit: `loader`, `limits`, `phases`, `egt`, `fuel`, `cas` modules. `02_engine_ecu_correlation.py` with POWERUP/LANE_CHECK/SHUTDOWN/IN_FLIGHT classification. Dual-format log loading (G3X-direct + Garmin Pilot). Case-insensitive directory glob.