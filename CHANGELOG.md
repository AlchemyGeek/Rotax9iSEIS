# Changelog — Slingology EIS Toolkit

All notable changes to the `slingology_eis` toolkit are recorded here.
Check your installed version with:

```bash
python -c "import slingology_eis; print(slingology_eis.__version__)"
```

---

## 0.9.0 — June 23, 2026

**Multi-engine support via external config files.** All operating limits previously hardcoded in `limits.py` are now loaded from JSON engine config files in the `engines/` directory. Engine selection resolves in priority order: explicit argument → `SLINGOLOGY_ENGINE` environment variable → `config.json` in the toolkit root → default (916iS).

**Engine configs:**
- `engines/916iS.json` — fully sourced from OM-916 i/C24, Edition 0 / Rev. 1. Status: `VERIFIED`.
- `engines/915iS.json`, `engines/914iS.json`, `engines/912iS.json` — placeholder configs with estimated values from published specs. Status: `PLACEHOLDER`. Attempting to use these fires a `UserWarning` reminding you to verify against the official OM before operational use.

**`config.json`** added to toolkit root — set `"engine": "916iS"` (or another engine name) once, and all scripts pick it up automatically. No per-run argument needed.

**All hardcoded engine-specific thresholds replaced:**
- `limits.py` — all `Limit` objects and EGT spread conditional thresholds (flow threshold, spread limits in both °F) now read from the engine config
- `phases.py` — `overboost_time()` reads RPM threshold, power threshold, and time limit from the engine config's `overboost` block
- `02_engine_ecu_correlation.py` — LANE_CHECK RPM band and max duration read from the engine config's `phase_detection` block
- `03_multi_flight_insights.py` — overboost section uses config-driven limit values; engine name shown in report header (`[Rotax 916iS]`)

**`limits_report()` now shows engine name** and flags PLACEHOLDER configs explicitly in the output.

**Backlog item D1 completed.** See `engines/` directory for config format; adding a new engine requires only a new JSON file sourced from its OM — no code changes.

---

## 0.8.0 — June 23, 2026

**Ground-session filtering moved to the loader.** Ground-only sessions (engine run-up, taxi test, avionics check — files where the aircraft never actually flew) are now excluded at `load_directory()` time by default (`skip_ground_sessions=True`). These sessions add no analytical value and were producing misleading results: false temperature outliers, meaningless phase labels, inflated flight counts, and degraded trend quality from x-axis clustering at identical engine-hours values.

Detection: a file is excluded if estimated airborne time (rows with RPM > 3,000 AND IAS > 30kt) is under 3 minutes — a fast check that doesn't require the full phase-detection state machine. Ground sessions print as `·` with an explicit "ground session — skipped" label; the summary line reports "Loaded N flight(s), skipped M ground session(s)."

`real_flights_only()` in `fleet.py` and `MIN_AIRBORNE_MIN_FOR_FLEET_STATS` removed — superseded by the loader-level filter. `metrics_all`/`metrics` split in `03_multi_flight_insights.py` simplified to a single `metrics` variable.

Pass `skip_ground_sessions=False` to `load_directory()` to examine ground sessions directly.

**Community data backlog item removed.** Fleet-level comparisons using logs from other aircraft was removed as out of scope — this toolkit is a personal aircraft analytics tool, not a community database.

---

## 0.7.0 — June 20, 2026

**New module: `climb.py`** — climb-rate-correlated thermal analysis. Bins CLIMB-phase rows by VS (gentle <500fpm, normal 500-1000fpm, aggressive >1000fpm) and computes °F/min rise rate per bucket via linear fit. First real finding: oil temp rise rate roughly tripled (+4.4 → +12.8°F/min) from normal to aggressive climb rate. Wired into `01_first_flight_analysis.py` and `fleet.py`.

**DA/OAT stratification in `fleet.py`.** `FlightMetrics` now carries `cruise_da_ft`, `cruise_oat_c`, `da_band`, `oat_band`. New `baseline_stratified()` and `trend_stratified()` group by band before computing statistics. Cruise efficiency moved to DA-banded trend; EGT spread gained OAT-banded trend in script 03.

**Overboost distribution / throttle-discipline view.** Script 03 now reports exceeded/close-call/comfortable buckets across all flights plus a trend — framed around catching slow TO-to-climb-power transitions, not just hard-limit violations.

**Script 02 text report** now includes the IN-FLIGHT interpretation section that was previously console-only.

**Validated against 50-flight dataset** — found 4 genuine IN_FLIGHT ENGINE ECU events and one real overboost exceedance (confirmed ATC-workload-related).

---

## 0.6.0 — June 20, 2026

**Fuel-flow calibration (K_fuel) deliberately descoped.** For full-to-full refuelling, gallons added at the pump already equals true consumption directly. Removed: `FillEvent`, `save_fills`, `load_fills`, `fadec_gallons_for_window`, `import_fills_csv`, `import_and_save_fills`, `compute_k_fuel`, `scripts/import_fills.py`. See research paper §6.2.

**Script 03 reorganized** from 6 sections to 5 — "Maintenance" section was a mislabel; metrics redistributed to Trends (cylinder balance stability) and Operational (overboost, oil condensation risk).

**Changelog split** from README into this file.

---

## 0.5.0 — June 19, 2026

Fuel CSV import multi-flight gap handling — `fadec_gallons` summed across all flights in the window between consecutive fills. `FillEvent` gained `flights_in_window`/`gap_flagged` fields. *(Superseded by 0.6.0 — entire feature removed.)*

---

## 0.4.0 — June 19, 2026

Fuel fill-up CSV import (`scripts/import_fills.py`). Version tracking added to README and `__version__`. *(Superseded by 0.6.0 — entire feature removed.)*

---

## 0.3.0 — June 19, 2026

Duplicate flight detection (`find_duplicate_flights`, `deduplicate_flights`) wired into scripts 02 and 03. Catches same flight exported twice (SD-card + Garmin Pilot).

---

## 0.2.0 — June 16, 2026

`03_multi_flight_insights.py` and `fleet.py` added: baselines, trends, outliers, operational/data-quality summaries. Phase detection fixes: auto field-elevation estimation per flight (was hardcoded to KAWO, broke cross-country flights); hysteresis added to CRUISE/CLIMB/DESCENT transitions (was flickering on VS noise). `01_first_flight_analysis.py` takes a filename argument.

---

## 0.1.x — June 16, 2026

Initial toolkit: `loader`, `limits`, `phases`, `egt`, `fuel`, `cas` modules. `02_engine_ecu_correlation.py` with POWERUP/LANE_CHECK/SHUTDOWN/IN_FLIGHT classification. Dual-format log loading (G3X-direct + Garmin Pilot; header `#` prefix auto-detected). Case-insensitive directory glob (`*.csv` matches `.CSV`, `.Csv`, etc.).
