# SlingologyEIS — Project Backlog

Last updated: June 23, 2026  
Toolkit current version: 0.8.0  
Research paper current edition: 0.2

Items organized by category. Each item notes type: **code**, **design**, or **research**.

---

## A — Analytics: Not Yet Built

### A1. Analysis / Insight two-layer output format
**Type:** Code + design  
Every analytics topic produces two layers:
- **Analysis line** — always present, purely descriptive. States this flight's measurement, personal baseline comparison, and OM limit reference in one plain sentence. Present even when nothing notable. e.g. *"EGT spread this flight: 56°F. Your average: 56°F ± 5°F over 23 flights. OM limit: 392°F."*
- **Insight line** — conditional, only appears when the analysis finds something worth flagging (trend clears R² bar, outlier crosses z-score, hard limit exceeded). e.g. *"Trending wider over your last 25 flights — still within limits, worth watching."*

For topics where no baseline exists yet (small-n), show raw number with "still building your baseline" rather than a comparison.

Likely lives in a new `04_flight_summary.py` (per-flight plain-language report) plus a summary header in script 03. Design questions still open: does the per-flight version (script 01) also get this treatment?

---

### A2. The 14 agreed analytics topics
**Type:** Design (agreed), Code (pending)  
Each needs both an analysis line and a conditional insight, for both per-flight and fleet views:

1. EGT spread — cruise mean vs personal average vs OM 392°F limit
2. EGT4 elevation — vs cylinders 1–3, vs personal average
3. Cylinder rank stability — is the same cylinder consistently hottest?
4. Oil temperature — peak and % time below 194°F/90°C optimal band, vs personal average and OM 248°F limit
5. Coolant temperature — peak vs personal average and OM 248°F limit
6. Oil/coolant ratio — vs personal average
7. Overboost time — this flight's max block and distribution vs 300s OM limit
8. Cruise efficiency — nmpg vs personal average (DA-stratified)
9. Cruise fuel flow — vs personal average
10. Manifold pressure at takeoff — vs OM expected value for conditions
11. ENGINE ECU alerts — plain-language classification (expected vs genuine signal)
12. Flight phase mix — climb/cruise/descent split vs personal typical
13. Operating limit exceedances — any OM hard-limit violation, plainly stated
14. Climb thermal rate — oil/coolant rise rate during climb vs personal average for similar VS

---

### A3. Manifold pressure vs OM expected-power model
**Type:** Code  
OM provides target MAP values at specific RPM/OAT conditions. At each takeoff (RPM ≥ 5,500, stable 10s window): record MAP vs OAT, compute expected MAP from OM reference corrected for OAT, track MAP deviation over engine hours as a turbocharger health proxy. Deviation >+20 mbar from expected = air supply fault; below expected = possible turbocharger degradation.

---

### A4. ECO/POWER mode detection
**Type:** Research → Code  
Throttle position (the actual 97% threshold) is not in the G3X log — it's on the FADEC CAN bus but not surfaced in the column set. Need to infer from correlated parameters: fuel flow step-reduction, EGT drop at constant altitude/RPM. Validation requires a flight with deliberate known-throttle-position manoeuvres as ground truth.

---

## B — Classifier / Logic Fixes

### B1. POWERUP duration threshold
**Type:** Code  
A POWERUP run of 28,678 seconds (nearly 8 hours) is not the same event type as a normal 20–120 second pre-start powerup — it's the avionics left on battery or ground power. Any POWERUP run exceeding ~600 seconds should be classified as `AVIONICS_ON_GROUND` (distinct category) to avoid inflating POWERUP totals meaninglessly. Note: with ground sessions now excluded at the loader level (v0.8.0), this primarily affects any future case where someone passes `skip_ground_sessions=False`.

---

### B2. Mid-log power-cycle handling
**Type:** Code  
A single G3X log can span multiple avionics power cycles (e.g. `log_20260423_135821_KTOA.csv` has a POWERUP at 19:17 inside a log that started at 13:58 — a 5-hour gap). The classifier currently treats this as an independent POWERUP within the same file. Either split multi-power-cycle logs into separate logical sessions, or at minimum label mid-log power cycles distinctly from start-of-log powerups.

---

### B3. IN_FLIGHT ENGINE ECU — per-event co-active alert reporting
**Type:** Code  
Current report lumps all IN_FLIGHT events' co-active alerts into one frequency table. Each event is different. The KSFF flight (`log_20260527_200344_KSFF.csv`) has `OIL PRESS` as a co-active alert — the only event with a direct engine-parameter correlation alongside the ECU alert. This should be called out explicitly, not buried in a combined count.

---

### B4. Overboost known-cause annotation
**Type:** Code  
Need a lightweight mechanism to attach a note/known-cause to a specific flight's flagged event (e.g. `annotations.json` keyed by source file). Pilot-facing report then shows: *"April 23 — exceeded 300s limit (+81s). Note: ATC delay at LAX."* This is not suppression — the event still shows — but lets the pilot's own context travel with the finding.

---

## C — Fleet Statistics

### C1. Fleet count reporting
**Type:** Code (small)  
With ground-session filtering now in the loader (v0.8.0), the headline count in script 03 should accurately reflect real flights only. Verify this is consistent everywhere after v0.8.0 changes.

---

### C2. Engine hours as trend x-axis — reliability
**Type:** Research → possible code  
Engine hours in log metadata reflect the Hobbs at log creation. For ground sessions (now excluded) this was a big problem; for real flights it's less severe but still worth checking. Consider using cumulative airborne hours derived from the logs themselves as an alternative x-axis. Investigate and compare both approaches.

---

### C3. DA/OAT stratification — remaining thermal metrics
**Type:** Code  
`da_band` and `oat_band` are captured per flight. Cruise efficiency (DA) and EGT spread (OAT) are already stratified in script 03. Remaining thermal metrics — oil temp, coolant temp, oil/coolant ratio, climb thermal rate — should also trend within OAT bands rather than blended across conditions.

---

## D — Engine Coverage

### D1. ~~Multi-engine config file support~~ — COMPLETED in v0.9.0 (912iS, 914iS, 915iS, 916iS)
**Type:** Architecture + Code  
All four Rotax iS engines are turbocharged and FADEC — the analytics architecture generalizes without redesign. Work needed: externalize the `Limit` registry from `limits.py` into per-engine JSON/YAML config files; add user-specifiable engine selection (config file or CLI flag); source limits from each engine's OM. Phase-detection RPM/power thresholds may need per-engine tuning. Depends on obtaining the other three engines' Operators Manuals.

---

## E — Documentation & Registration

### E1. Aircraft registration correction — N5512E → N117ZS
**Type:** Documentation  
Research paper title page, abstract, and several body references still say N5512E. The aircraft is N117ZS. Fix throughout `research/build_paper.js` and rebuild the paper.

---

### E2. Research paper — ongoing updates
**Type:** Documentation (ongoing)  
Edition 0.2. Updates needed as findings accumulate:
- §11 Open Questions — update as answered or refined
- §12 Revision History — add entry per meaningful analytical finding
- §6.1 EGT4 elevation — update with validated statistical finding (n=23, mean +44.7°F ± 5.3°F)
- §6.7 Climb-rate-correlated thermal analysis — update from "identified gap" to "built" (v0.7.0)
- §9 DA/OAT normalization — update from "design gap" to "partially implemented" (v0.7.0 bands, full stratification pending)

---

### E3. GitHub repository preparation
**Type:** Infrastructure  
Eventual goal: publish the toolkit to GitHub as an open-source project. Before doing so:
- Confirm no sensitive data (flight logs, personal info) is in any committed file
- Add a proper `.gitignore` (exclude `data/logs/`, `data/reports/`, `__pycache__/`, `.venv/`)
- Add a `LICENSE` file (recommend MIT or Apache 2.0)
- Review README for public audience (currently written assuming familiarity with the project history)
- Tag v0.8.0 as the first public release candidate

---

## F — Future / Long Horizon

### F1. Maintenance-interval tracking (100-hr / annual cycle)
**Type:** Future capability  
Tying findings to actual maintenance inspection intervals. Requires much longer baseline than currently available. Deferred deliberately.

### F2. SlingologyEIS web app
**Type:** Future product milestone  
Free, offline-first PWA for any Sling / Rotax iS pilot. Lovable (React + Tailwind). Analytics toolkit must be validated and the Analysis/Insight two-layer format (A1) defined first.
