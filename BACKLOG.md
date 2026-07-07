# SlingologyEIS — Project Backlog

Last updated: July 7, 2026
Toolkit current version: 0.10.0
Research paper current edition: 0.2

Items organized by category. Each item notes type: **code**, **design**, or **research**.

---

## A — Analytics

### ~~A1. Analysis / Insight two-layer output format~~ — COMPLETED in v0.10.0
**Type:** Code + design
`insight_rules.json` at toolkit root defines trigger rules (threshold, baseline_deviation, trend).
`reports/baselines.json` written by script 03, read by script 04.
`reports/models.json` written by script 03, read by script 04.
Script 04 (`04_flight_report.py`) is the new per-flight pilot report with two-layer format.
Fleet Insights section added to end of script 03 output and saved as `reports/fleet_insights.txt`.

---

### ~~A2. The 14 agreed analytics topics~~ — COMPLETED in v0.10.0
**Type:** Code
All 14 topics implemented in script 04:
1. EGT spread — ✅
2. EGT4 elevation — ✅
3. Cylinder rank stability — ✅
4. Oil temperature — ✅
5. Coolant temperature — ✅
6. Oil/coolant ratio — ✅
7. Overboost time — ✅ (with close-call flag at 240–300s)
8. Cruise efficiency — ✅ (DA context added)
9. Cruise fuel flow — ✅ (with DA context and altitude note)
10. Manifold pressure at takeoff — ✅ (empirical model, shows "still collecting" until n≥5)
11. ENGINE ECU alerts — ✅ (uses proper classifier from cas.py)
12. Flight phase mix — DROPPED as standalone; replaced with "no cruise detected" header note
13. Operating limit exceedances — ✅ (phase-filtered, duration-thresholded)
14. Climb thermal rate — ✅

---

### A3. Manifold pressure vs OM expected-power model — PARTIALLY COMPLETE
**Type:** Code + research
Empirical MAP model built in v0.10.0: linear regression MAP = f(pressure_alt_ft, oat_c).
RPM capture threshold: ≥ 5,500 rpm during TAKEOFF_ROLL phase.
Model lives in `reports/models.json`, written by script 03, read by script 04.
Confidence thresholds: n<5 = "still collecting", n 5–14 = LOW, n≥15 = MODERATE.
Currently at n=15, MODERATE, R²=0.71.

**Remaining:** Model needs more altitude diversity (most departures from KPAE, near sea level).
Target: 5+ flights from departure elevations above 2,000 ft MSL for reliable altitude range.

---

### A4. ECO/POWER mode detection
**Type:** Code
BLOCKED — requires a ground-truth validation flight with deliberate known throttle positions.
ECO/POWER threshold: ~97% throttle position per engine config.
Do not start until validation flight data is available.

---

### A5. Power/altitude/fuel-flow model
**Type:** Code + research
Build a DA band × power setting → expected gph model from fleet data.
Compare observed cruise fuel flow against model prediction rather than blended personal average.
Requires: sufficient data across DA and power combinations.
Currently cruise fuel flow uses blended personal average with DA context note as interim solution.
Park until fleet data is sufficient for a reliable multi-variable regression.

---

### A6. MAP empirical model — altitude diversity requirement
**Type:** Research → code
Currently blocked on altitude diversity — most departures from KPAE (near sea level).
Revisit when 5+ flights from departure elevations above 2,000 ft MSL are available.
Track departure elevation distribution in fleet_metrics to monitor readiness.

---

## B — Bug Fixes & Signal Quality

### ~~B3. IN-FLIGHT ENGINE ECU — per-event reporting~~ — COMPLETED in v0.10.0
**Type:** Code
ENGINE ECU classifier moved from script 02 into `cas.py` as `classify_engine_ecu_run()`
and `extract_engine_ecu_runs()`. Script 02 and script 04 both import from `cas.py`.
Fleet insights reads `inflight_ecu_count` from `fleet_metrics.csv` (computed via classifier).
KSFF OIL PRESS event correctly identified as the only genuine IN-FLIGHT event with
engine-parameter correlation.

---

### B4. Overboost known-cause annotation
**Type:** Code
Need a lightweight mechanism to attach a note/known-cause to a specific flight's flagged event
(e.g. `annotations.json` keyed by source file). Pilot-facing report then shows:
*"April 23 — exceeded 300s limit (+81s). Note: ATC delay at LAX."*
This is not suppression — the event still shows — but lets the pilot's own context travel
with the finding.

---

### B1, B2 — Ground session edge cases
**Type:** Code
Low urgency post-v0.8.0 loader filtering. Investigate if needed.

---

## C — Fleet Statistics

### ~~C1. Fleet count reporting~~ — RESOLVED in v0.10.0
**Type:** Code
Confirmed: 23 real flights (50 total log files, 27 ground sessions filtered at loader).
All fleet metrics, baselines, and insights correctly use 23 flights.

---

### C2. Engine hours as trend x-axis — reliability
**Type:** Research → possible code
Engine hours in log metadata reflect the Hobbs at log creation.
Consider using cumulative airborne hours derived from logs as alternative x-axis.
Investigate and compare both approaches. Low urgency.

---

### C3. DA/OAT stratification — remaining thermal metrics
**Type:** Code
`da_band` and `oat_band` captured per flight. Cruise efficiency (DA) and EGT spread (OAT)
already stratified. Remaining thermal metrics — oil temp, coolant temp, oil/coolant ratio,
climb thermal rate — should also trend within OAT bands rather than blended.

---

## D — Engine Coverage & Maintenance

### ~~D1. Multi-engine config file support~~ — COMPLETED in v0.9.0
916iS fully verified. 912iS, 914iS, 915iS are verified placeholders.

---

### D2. Maintenance event logging and post-maintenance baseline tracking
**Type:** Code + design
Ability to record maintenance events (oil change, spark plug replacement, intercooler
service, turbo inspection, etc.) with engine hours and date. Analytics then track whether
key metrics (oil temp, EGT spread, MAP at takeoff) shift after a maintenance event —
useful for validating that a service had the expected effect and detecting regressions.
Events stored in a `maintenance_log.json` at the toolkit root.

---

## E — Documentation & Registration

### ~~E1. Aircraft registration correction — N5512E → N117ZS~~ — PENDING
**Type:** Documentation
Research paper still references N5512E in several places. Fix in v0.10.0 release.

---

### E2. Research paper — ongoing updates
**Type:** Documentation (ongoing)
Edition 0.2. Updates needed for v0.10.0:
- Correct registration N5512E → N117ZS throughout
- Update fleet count: 23 real flights (50 total log files)
- Add script 04 per-flight report section
- Add Fleet Insights section
- Add MAP empirical model section
- Add two-layer format design section
- Update §9 DA/OAT normalisation — stratification partially implemented
- Update §11 Open Questions — close answered questions
- Update §12 Revision History

---

### E3. GitHub repository — v0.10.0 release
**Type:** Infrastructure
- `.gitignore` excludes `data/logs/`, `data/reports/`, `__pycache__/`, `.venv/`
- LICENSE file (MIT)
- README updated with user manual
- CHANGELOG updated
- Version bumped to 0.10.0 in `slingology_eis/__init__.py`
- Tag v0.10.0

---

## F — Future / Long Horizon

### F1. Maintenance-interval tracking (100-hr / annual cycle)
**Type:** Future capability
Tying findings to actual maintenance inspection intervals.
Requires much longer baseline than currently available. Deferred deliberately.

### F2. SlingologyEIS web app
**Type:** Future product milestone
Free, offline-first PWA for any Sling / Rotax iS pilot.
Analytics toolkit must be validated first.
Script 04 per-flight report logic becomes the per-flight report page.