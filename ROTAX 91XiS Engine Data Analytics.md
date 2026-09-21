# ROTAX 916iS ENGINE DATA ANALYTICS
## A Research Foundation for FADEC-Native Engine Monitoring

**Slingology EIS Project  |  N117ZS Sling TSi  |  KAWO**

Living Document — Edition 0.3  |  July 2026

---

## Abstract

This paper documents an ongoing research programme to build open-source, FADEC-native engine health analytics for Rotax 916iS-powered experimental aircraft. Current platforms such as Savvy Aviation and FlySto provide general-purpose piston engine visualisation tools built around pilot-controlled mixture management. Neither addresses the fundamentally different operating model of a full-authority digital engine — one where the ECU manages fuel mixture, ignition timing, and power mode autonomously.

We use Garmin G3X EIS logs captured at 1-second resolution from N117ZS (Sling TSi, KPAE) as the primary dataset. The current dataset comprises 23 real flights across 50 total log files (27 ground sessions filtered at loader level), spanning engine hours 28.2 to 66.3. We derive operating limits and normal ranges directly from the Rotax Operators Manual (OM-916 i/C24, Edition 0 Rev. 1, December 2023). The long-term goal is SlingologyEIS — a free, offline-first progressive web app that provides actionable engine health insights and anomaly detection tailored specifically to the 916iS.

---

## 1. Introduction and Motivation

The Rotax 916iS represents a new class of general aviation powerplant: a turbocharged, intercooled, liquid-cooled-head, FADEC-controlled engine. With a TBO of 2,000 hours and rated power of 160 hp (119 kW) at takeoff, it is the highest-performance engine in the Rotax light-aviation line. It differs architecturally from the Lycoming and Continental engines that dominate GA analytics tooling in three fundamental ways:

- **No pilot mixture control.** The dual-redundant ECU (Lane A / Lane B) manages fuel injection mapping, ignition timing, and the ECO/POWER mode transition autonomously.

- **Liquid-cooled cylinder heads, air-cooled cylinders.** The cooling health metrics are therefore coolant temperature and EGT — not CHT in the traditional sense.

- **FADEC-calculated fuel flow.** There is no physical flow sensor. Fuel consumption is a model-based value with a manufacturer-stated ±10% tolerance band, making raw fuel flow numbers unreliable without calibration.

Existing platforms do not account for these differences. Savvy Aviation's FEVA (Failing Exhaust Valve Analytics) and ROP/LOP diagnostics are meaningless for a FADEC engine. FlySto provides flight replay and parameter graphing but no engine-specific health models. The Rotax B.U.D.S. diagnostic software provides the deepest access to ECU fault logs but requires a hardware dongle and is used only at maintenance intervals.

This project aims to fill the gap: automated, insight-oriented engine health monitoring that speaks the language of the 916iS.

---

## 2. Data Architecture

### 2.1 Garmin G3X EIS Log Format

The G3X Touch (GDU 460) with GEA-24 engine interface module logs data to a microSD card in CSV format. Each file covers a single power-on session and is named by date, time, and airport identifier: `log_YYYYMMDD_HHMMSS_ICAO.csv`.

Structure: Row 0 is an airframe metadata header containing aircraft ident, software version, system ID, unit type, airframe hours, and engine hours. Row 1 is the column header. Rows 2 onward are 1-second data records.

Confirmed logging interval: 1 second (verified from N117ZS log, 23 April 2026 — all inter-row deltas = 1.000 s, N = 16,198 rows).

Total columns: 111, spanning GPS/navigation, AHRS, autopilot, weather, avionics status, and engine parameters. Both SD-card-direct and Garmin Pilot export formats are supported and can be mixed freely in the same analysis directory.

### 2.2 Engine Parameters Available from FADEC CAN Bus

The GEA-24 receives the following engine parameters from the 916iS via the Rotax Display CAN Bus (per Garmin G3X Installation Manual, section 24.2.2.3, and confirmed in the Rotax OM communication interfaces section):

| G3X Column | Source | Notes |
|---|---|---|
| RPM | FADEC CAN | Propeller shaft RPM after gearbox reduction |
| Engine Power (%) | FADEC CAN | Computed % of rated power; can exceed 100% in overboost |
| Manifold Press (inch Hg) | FADEC CAN | Plenum pressure; key turbocharger health indicator |
| Oil Press (PSI) | FADEC CAN | Oil system pressure |
| Oil Temp (deg F) | FADEC CAN | Engine oil temperature |
| Coolant Temp (deg F) | FADEC CAN | Liquid coolant temperature (cylinder heads) |
| Fuel Flow (gal/hour) | FADEC calculated | Model-based; ±10% tolerance; no physical sensor |
| Fuel Press (PSI) | Separate sensor | Rail pressure; monitoring method varies by installation |
| EGT1–4 (deg F) | FADEC CAN | Per-cylinder exhaust gas temperature |
| Main Volts | GEA-24 | Primary bus voltage |
| Batt Amps | GEA-24 | Battery current |
| CAS Alert | G3X synthesised | Composite annunciation string from all active alerts |

### 2.3 Parameters NOT Available in G3X Logs

The following parameters are present in the FADEC ECU but are not exposed through the Display CAN Bus to the G3X and therefore do not appear in log files. They are accessible only via B.U.D.S. at maintenance intervals:

- Throttle position (ECU_throttle_lin) — the actual physical throttle %, which determines ECO vs. POWER mode; the G3X does not log this directly
- Lane A / Lane B individual fault codes and status registers
- Injector pulse width per cylinder
- Ignition advance angle
- Boost pressure control valve position
- Internal ECU diagnostic logs and error code history
- Manifold Air Temperature (T_plenum) — available on CAN but not surfaced in standard G3X column set

> **NOTE:** This is a meaningful gap. The ECO/POWER mode boundary is a throttle-position threshold, not a power-percentage threshold, and throttle position is not in the standard log. We can infer mode from correlated parameters (see Section 4).

---

## 3. Operating Limits and Normal Ranges

All limits below are sourced directly from the Rotax Operators Manual, OM-916 i/C24, Chapter 2.1 (Operating Limits), Edition 0 / Rev. 1, December 2023. These form the authoritative reference for all threshold alerting in SlingologyEIS.

### 3.1 Engine Speed

| Condition | Minimum | Maximum | Notes |
|---|---|---|---|
| Idle | 1,800 rpm | — | |
| Normal continuous | — | 5,500 rpm | 101 kW / 135 hp |
| Takeoff (max 5 min) | — | 5,800 rpm | 117 kW / 157 hp; time-limited |
| Boost pressure peak | — | 6,500 rpm | Max 1,990 hPa for 3 sec only |

### 3.2 Temperatures

| Parameter | Min | Max | Notes |
|---|---|---|---|
| Oil temp — takeoff min | 50°C / 122°F | — | Must reach before takeoff |
| Oil temp — normal | 50°C / 122°F | 120°C / 248°F | |
| Oil temp — optimal | 90–110°C / 194–230°F | — | Below this risks condensation in sump |
| Coolant temp — normal | — | 120°C / 248°F | |
| EGT — max | — | 950°C / 1,742°F | Per cylinder |
| EGT Split (fuel flow > 3 L/hr) | — | 200°C / 392°F | Key health indicator |
| EGT Split (fuel flow < 3 L/hr) | — | 500°C / 932°F | Low power / idle only |
| Manifold Air Temp — normal | — | 50°C / 122°F | Rated power maintained |
| Manifold Air Temp — extended | — | 80°C / 176°F | Power reduced |
| Ambient temp — ground | — | 50°C / 122°F | |
| Ambient temp — flight | −40°C / −40°F | 50°C / 122°F | |

### 3.3 Pressures

| Parameter | Min | Max | Notes |
|---|---|---|---|
| Oil pressure > 3,500 rpm | 2.0 bar / 29 psi | 5.0 bar / 72.5 psi | Normal operating band |
| Oil pressure < 3,500 rpm | 0.8 bar / 11.6 psi | — | |
| Oil pressure — cold start | — | 7.0 bar / 101.5 psi | During warmup only |
| Manifold pressure | 60 hPa / 1.77 inHg | 1,800 hPa / 53.15 inHg | |
| Boost pressure | Ambient | 1,800 hPa / 53.15 inHg | |
| Boost pressure peak | — | 1,990 hPa / 58.76 inHg | Max 3 seconds at 6,500 rpm |
| Fuel pressure (at rail vs MAP) | 2.9 bar / 42 psi | 3.2 bar / 46 psi | Normal operating |
| Fuel pressure (exceedance) | 2.5 bar / 36 psi | 3.5 bar / 51 psi | Max 3 sec after power change |

### 3.4 Other Limits

| Parameter | Limit | Notes |
|---|---|---|
| Oil consumption | Max 0.06 L/hr | |
| Negative G | Max −0.5 G for 5 sec | Dry sump system limitation |
| Static roll angle | Max 40° | |
| Critical altitude | 15,000 ft | Max continuous power maintained below this |
| Max operating altitude | 23,000 ft | Warning lamp may flash 20,000–23,000 ft (normal) |
| ECO/POWER threshold | ~97% throttle position | Below = ECO (lean / efficient); above = POWER (enriched) |
| Single-lane operation | Always POWER mode | ECO requires dual Lane operation |

---

## 4. ECO / POWER Mode — Architecture and Analytics Implications

The ECO/POWER mode boundary is one of the most important features of the 916iS and has no analogue in traditional piston GA. Understanding it is prerequisite to interpreting every engine parameter.

### 4.1 Mechanism

The 916iS FADEC operates in two distinct fuel/ignition maps:

- **POWER mode (≥97% throttle position):** fuel enrichment active, maximum performance, used for takeoff and climb. Higher EGTs, higher fuel flow, optimised for power output.

- **ECO mode (<97% throttle position):** lean injection mapping, best fuel economy, used for cruise and descent. Lower EGTs, lower fuel flow. ECO mode is only available with both Lanes operational — in single-Lane operation the engine always runs POWER mode for maximum safety margin.

Important: the 97% threshold is a throttle position percentage, not engine power output percentage. A 97% throttle with a coarse-pitch fixed-pitch propeller at altitude may produce only 55% of rated power. The G3X logs Engine Power (%) as a computed output value, not throttle position. These are different axes.

### 4.2 Inferring ECO/POWER State from Available Data

Since throttle position is not directly logged by the G3X, we must infer the ECO/POWER mode from correlated observable parameters. Candidate inference signals:

- **Fuel Flow** — ECO mode produces a step-reduction in fuel flow at a given RPM/altitude.
- **EGT behaviour** — EGTs typically drop when transitioning from POWER to ECO at constant RPM.
- **RPM + Manifold Pressure** — A power reduction large enough to cross the throttle threshold while maintaining altitude will appear as a manifold pressure drop with modest RPM change.
- **Engine Power (%)** — Values sustained at or near 100%+ indicate POWER mode. Values in the 40–75% band at cruise RPM are consistent with ECO mode.

> **NOTE:** Hypothesis: ECO mode transitions are detectable as correlated simultaneous drops in both Fuel Flow and EGT at constant altitude and RPM. Validation requires labelled ground-truth data from a flight with deliberate known-throttle-position manoeuvres. This remains an open research question (see §12.1).

---

## 5. Automatic Flight Phase Detection

Manual phase labelling is explicitly excluded from the design — users will not be asked to annotate their log files. All phase detection is fully automatic from the data.

| Phase | Detection Heuristics | Key Parameters |
|---|---|---|
| Pre-start | RPM = 0, IAS < 5 kt | RPM, IAS |
| Engine start | RPM transitions 0 → idle range (1,800 rpm) | RPM delta |
| Warmup | RPM 1,800–2,500, IAS < 10 kt, Oil Temp rising | RPM, Oil Temp, IAS |
| Taxi | RPM 1,800–3,000, IAS < 35 kt, Baro Alt stable | RPM, IAS, Altitude |
| Takeoff roll | RPM > 5,000, IAS accelerating 0→Vr, Power > 90% | RPM, Power, IAS |
| Climb | VS > 300 fpm, IAS 70–90 kt, RPM > 4,500 | VS, IAS, Altitude |
| Cruise | VS ± 200 fpm sustained > 60 sec, IAS stable | VS stability, IAS |
| Descent | VS < −200 fpm sustained, power reducing | VS, Power |
| Approach | Altitude < TPA+500 ft, IAS 60–85 kt, VS variable | Alt, IAS |
| Landing roll | IAS decelerating through Vr toward 0, RPM dropping | IAS, RPM |
| Shutdown | RPM 0, IAS 0, post-landing | RPM, IAS |

Phase detection is implemented as a state machine with hysteresis (minimum dwell time before committing to a new phase) to prevent rapid oscillation at boundary conditions. Altitude reference is barometric altitude corrected for field elevation, estimated automatically per flight — no manual entry required.

---

## 6. Analytics Modules

The following analytics are specific to the 916iS and fill the gap left by general-purpose tools.

### 6.1 EGT Health and Spread Monitor

EGT spread (Split) is the primary cylinder balance indicator available from the FADEC. The OM defines two hard limits: 200°C spread when fuel flow > 3 L/hr (normal operation), 500°C when fuel flow < 3 L/hr (idle). A growing spread over time — even within limits — may indicate a developing injector imbalance or ignition fault on one lane.

**Findings as of Edition 0.3 (n=23 flights):**

- EGT spread cruise mean: **56.4°F ± 5.1°F** [range 46.6–67.3°F]
- Trend: **increasing** at +0.22°F/hr over engine hours (R²=0.30, n=23 — MODERATE confidence). Trend direction is consistent but R² has not yet cleared the 0.5 confirmation threshold.
- EGT4 consistently elevated vs cylinders 1–3: mean **+44.7°F ± 5.3°F** (n=23, consistent direction across all flights). Hypothesis: normal for cylinder 4 position near turbo exhaust collector — consistent with 916iS architecture.
- Cylinder rank stable (EGT4 consistently hottest) in **23/23 flights**.
- One outlier flight: `log_20260613_193731_KAWO.csv` — EGT spread max 145°F (z=+2.56). Under investigation.

### 6.2 Fuel Flow Calibration — Explored and Descoped

The FADEC fuel flow value is a calculated estimate with a ±10% tolerance (OM Section 5.1) — there is no physical flow sensor in the fuel line. An initial design built a calibration factor (K_fuel = pump gallons ÷ FADEC-integrated gallons) from logged fill-up events.

This was deliberately removed after review. For an aircraft consistently fuelled full-to-full, gallons added at the pump already equals true consumption since the previous fill — no flight-log-dependent step is required. FADEC fuel flow (uncalibrated, within the OM's stated ±10%) remains used directly for cruise efficiency (§6.4) and per-flight consumption reporting. Wing tank senders are used only as a rough plausibility check (attitude-sensitive, not trusted as calibration reference — see CHANGELOG 0.6.0).

### 6.3 Overboost Time Tracking

The 916iS has a 5-minute limit on operation at 5,800 rpm (takeoff power). The toolkit tracks cumulative time-at-overboost per flight and flags exceedances.

**Findings as of Edition 0.3 (n=23 flights):**

- 1 overboost exceedance confirmed: `log_20260423_135821_KTOA.csv` — 381s total (limit 300s). Confirmed cause: ATC workload delay before throttle reduction.
- 1 close call: same flight, max block 381s. 1 additional flight at 274s (91% of limit).
- Throttle discipline is generally good: 21/23 flights ≤240s total overboost time.

### 6.4 Cruise Efficiency

Nautical miles per gallon (nmpg) during stable cruise, DA-stratified for valid cross-flight comparison.

**Findings as of Edition 0.3 (n=12 flights with cruise data):**

- Fleet mean: **19.5 ± 2.1 nm/gal** [range 15.5–22.7 nm/gal]
- Cruise fuel flow mean: **6.3 ± 0.5 gph** [range 5.5–7.4 gph]
- DA context is added to all cruise fuel flow comparisons — higher DA flights show different fuel flow than the blended average due to power and altitude effects. A power/altitude/fuel-flow model (A5) is planned for a future release.

### 6.5 Oil and Coolant Temperature Ratio

The ratio between oil and coolant temperature is a signature of the engine's thermal health. A change in this ratio — even if both values remain within limits — may indicate a developing cooling system issue.

**Findings as of Edition 0.3 (n=23 flights):**

- Oil temp peak mean: **202.9°F ± 12.1°F** [range 180–224°F]. OM limit: 248°F. No exceedances.
- Coolant temp peak mean: **180.8°F ± 7.4°F** [range 170–196°F]. OM limit: 248°F. No exceedances.
- Oil/coolant ratio mean: **1.10 ± 0.04** [range 1.0–1.2]. Stable — no concerning trend.
- Oil temp below optimal band (194°F/90°C): average **91% of flight time**. OM recommends reaching 100°C (212°F) at least once daily to drive off sump condensation. Worst flight: 100% below optimal (short local flight).

### 6.6 Manifold Pressure — Empirical Takeoff Model

An empirical model of takeoff MAP has been built from fleet data. Rather than relying on the OM's single reference data point (1,690 mbar at 5,800 rpm, 25–35°C), the model uses actual takeoff data from N117ZS.

**Model design:**

- Capture window: rows where phase = TAKEOFF_ROLL and RPM ≥ 5,500
- Features: pressure altitude (ft) and OAT (°C)
- Target: observed MAP (inHg)
- Method: ordinary least squares linear regression

**Findings as of Edition 0.3:**

- Model: n=15 events, **R²=0.71**, MODERATE confidence
- Example prediction: at −75 ft PA, 16°C → expected 44.9 inHg; observed 44.8 inHg (delta: −0.1 inHg — within noise)
- Insight threshold: ±1.5 inHg deviation from model triggers a flag
- Model notes "still collecting data" until n≥5; requires altitude diversity across departure airports for reliable altitude-range coverage

### 6.7 Climb-Rate-Correlated Thermal Analysis

Built in v0.7.0 (`climb.py`). Bins CLIMB-phase rows by vertical speed (VS) bucket and computes °F/min temperature rise rate per bucket via linear fit.

**Findings as of Edition 0.3 (n=15 flights with climb data):**

- Oil temp rise rate overall: **1.4 ± 4.1°F/min** [range −1.4 to +12.4°F/min]
- Coolant temp rise rate overall: **−0.4 ± 1.2°F/min** [range −2.9 to +2.5°F/min]
- Dominant climb VS bucket across fleet: **normal** (500–1,000 fpm) in 11/15 flights; aggressive (>1,000 fpm) in 2/15; gentle (<500 fpm) in 2/15
- First finding (earlier dataset): oil temp rise rate roughly tripled (+4.4 → +12.8°F/min) from normal to aggressive climb rate. Validation ongoing with larger n.

---

## 7. CAS Alert Investigation — ENGINE ECU

In the first logs analysed, the string 'ENGINE ECU' appeared in the CAS Alert column from the very first data row (pre-engine-start) and persisted throughout the session. Following multi-flight correlation analysis across 23 flights, this has been classified and understood.

### 7.1 Classification — Resolved

The ENGINE ECU CAS alert has been classified into four categories by the toolkit's `cas.py` classifier:

| Classification | Description | Expected? |
|---|---|---|
| POWERUP | Before engine start; alert present at avionics power-on | Yes — suppress in UI |
| LANE_CHECK | Deliberate single-lane run-up test (Lane A off → on, Lane B off → on) | Yes — expected pre-takeoff procedure |
| SHUTDOWN | After engine stops; alert clears post-shutdown | Yes — suppress in UI |
| IN_FLIGHT | Engine running, not a lane check; the real signal | Requires investigation |

**Findings across 23 flights:**

- **4 genuine IN_FLIGHT ENGINE ECU events** identified across the full dataset. All are 1-second duration events, consistent with intermittent CAN communication signals rather than sustained ECU faults.
- **1 flight has a direct engine-parameter correlation:** `log_20260527_200344_KSFF.csv` (2026-05-27, KSFF) — OIL PRESS co-active with ENGINE ECU at 20:06:38 for 1 second. Oil pressure data WAS present (oil_NaN = 0%) — the oil pressure was being read, not dropped out. This is the only IN_FLIGHT event with a direct engine-parameter correlation and warrants continued monitoring.
- **Other IN_FLIGHT events** have no engine-parameter correlation — consistent with intermittent CAN dropout, not ECU hardware fault.

### 7.2 Recommended Actions

- Connect B.U.D.S. at next 25-hour check or oil change — read ECU fault log from both Lane A and Lane B
- Check G3X Config mode (on ground, engine running, fault active) for specific Rotax fault code
- Verify GEA-24 FADEC CAN wiring integrity (pins 17 and 33 on J244 connector)
- Monitor KSFF OIL PRESS co-occurrence on subsequent flights — if it recurs, escalate to Rotax service

---

## 8. Fuel Quantity Sensor Limitations

Standard resistive fuel quantity sensors (float-type) in the Sling TSi are sensitive to aircraft attitude. Instantaneous fuel quantity readings from the G3X are not reliable for fuel consumption calculations.

Design decisions for SlingologyEIS:

- FADEC fuel flow integration is the primary fuel consumption signal — used directly (not calibrated; see §6.2)
- Tank quantity readings are used only for gross sanity checks — a >2 gallon discrepancy between flow-integrated consumption and tank delta triggers a data quality note, not a correction
- Display of per-flight fuel consumed uses integrated FADEC flow, not tank deltas

---

## 9. Density Altitude and OAT Normalisation for Cross-Flight Comparison

Every baseline and trend computed across multiple flights implicitly assumes the flights are comparable. They are not, by default: density altitude (DA) and outside air temperature (OAT) both affect engine behaviour independently of anything mechanical.

### 9.1 Why Density Altitude Alone Is Not Sufficient

DA is the correct single normalising variable for parameters that depend on air density acting on the engine or airframe — power output at a given throttle setting, manifold pressure behaviour, true airspeed for a given indicated airspeed.

This breaks down for thermal parameters. EGT, oil temperature, and coolant temperature are not purely functions of air density — they also depend on the actual temperature of the ambient air, which is simultaneously the cooling medium for the intercooler, oil cooler, and coolant radiator.

### 9.2 Approach

- **Performance-type parameters** (MAP, power output, TAS-from-IAS): normalise using DA directly
- **Thermal-type parameters** (EGT, oil temp, coolant temp): stratify or normalise using OAT, or both DA and OAT together
- **Stratification is preferred over invented correction formulas** where no OM reference exists

### 9.3 Implementation Status (Edition 0.3)

- **Cruise efficiency (nmpg):** DA-stratified baselines and trends — implemented in v0.7.0
- **EGT spread:** OAT-stratified baselines and trends — implemented in v0.7.0
- **Cruise fuel flow:** DA context note added to per-flight report — implemented in v0.10.0
- **Remaining thermal metrics** (oil temp, coolant temp, oil/coolant ratio, climb thermal rate): DA/OAT stratification pending — backlog item C3

---

## 10. Competitive Landscape

| Platform | Strengths | Gaps for 916iS |
|---|---|---|
| Savvy Aviation | Largest GA engine dataset (5M+ flights), expert human analysts, FEVA exhaust valve detection, AI/ML (GADfly project) | Built entirely for pilot-mixture engines (Lycoming/Continental); FEVA and ROP/LOP analysis inapplicable to FADEC; no Rotax-specific models; paid subscription |
| FlySto | Excellent Garmin log import, 3D flight replay, approach scoring, POH performance comparison, free tier | Engine visualisation only (raw graphs), no engine health modelling, no FADEC-specific analytics, no trend detection |
| B.U.D.S. (Rotax) | Full ECU fault access, both Lanes, injector data, ignition timing | Hardware dongle required ($880+), maintenance-interval only, no flight log integration, no trend analytics |
| SlingologyEIS (this project) | FADEC-native models, free, offline-first, 916iS-specific limits, auto phase detection, DA/OAT-aware cross-flight comparison, open source, per-flight plain-language report | Single aircraft dataset (N117ZS), no borescope integration, no human analyst layer |

---

## 11. Research Toolkit — Python (v0.10.0)

A Python toolkit supports data analysis on the full flight log dataset locally. This avoids upload friction and enables batch analysis across all flights. The toolkit is the analytical engine from which SlingologyEIS app algorithms will be derived.

Current version: **0.10.0** — see CHANGELOG.md for full revision history.

GitHub: https://github.com/AlchemyGeek/Rotax9iSEIS

### 11.1 Library Modules

| Module | Purpose |
|---|---|
| `loader.py` | Load and normalise G3X CSV files (both SD-card-direct and Garmin Pilot export formats); ground session filtering; duplicate flight detection |
| `phases.py` | State-machine flight phase detector with auto field-elevation estimation and hysteresis; no manual labelling required |
| `limits.py` | OM-sourced parameter limits; phase filtering; duration thresholds; exceedance detection |
| `egt.py` | EGT spread analysis, cylinder rank tracking, trend detection across flights |
| `fuel.py` | FADEC fuel flow integration, cruise efficiency (nmpg), tank sender plausibility check |
| `cas.py` | CAS alert parser; ENGINE ECU classifier (`classify_engine_ecu_run`, `extract_engine_ecu_runs`) |
| `fleet.py` | Multi-flight aggregation; baseline establishment with sample-size confidence labelling; trend detection (R²-gated); outlier flagging; takeoff MAP capture |
| `climb.py` | Climb-rate-correlated thermal analysis (oil/coolant rise rate vs VS bucket) |

### 11.2 Analysis Scripts

| Script | Purpose |
|---|---|
| `notebooks/01_first_flight_analysis.py` | Single-flight deep-dive diagnostic report |
| `notebooks/02_engine_ecu_correlation.py` | Cross-flight ENGINE ECU pattern correlation and classification |
| `notebooks/03_multi_flight_insights.py` | Fleet-level baselines, trends, outliers, operational summary, Fleet Insights section |
| `notebooks/04_flight_report.py` | Per-flight plain-language pilot report with two-layer Analysis/Insight format |

### 11.3 Configuration and Output Files

| File | Purpose |
|---|---|
| `config.json` | Engine selection (default: 916iS) |
| `engines/916iS.json` | VERIFIED engine limits and phase-aware suppression rules (sourced from OM) |
| `insight_rules.json` | Trigger rules for all 14 analytics topics (threshold, baseline_deviation, trend) |
| `reports/baselines.json` | Fleet baselines written by script 03, read by script 04 |
| `reports/models.json` | Empirical regression models (currently: takeoff MAP model) |
| `reports/fleet_metrics.csv` | Per-flight metrics table (34 columns) |
| `reports/fleet_insights.txt` | Tight summary of major fleet findings |

### 11.4 Two-Layer Analysis/Insight Format

Every analytics topic in scripts 03 and 04 produces two output layers:

- **Analysis line** — always present, purely descriptive. States this flight's measurement, personal baseline comparison, and OM limit reference.
- **Insight line** — conditional, only appears when something is worth flagging (trend clears R² threshold, outlier crosses z-score, hard limit exceeded).

Trigger rules are defined in `insight_rules.json` with three trigger types:
- `threshold` — hard limit check (e.g. overboost >300s)
- `baseline_deviation` — z-score vs personal average (default threshold: z=2.0)
- `trend` — R²-gated directional trend (default minimum R²=0.5, n=10)

---

## 12. Open Questions and Research Agenda

### 12.1 Engine and FADEC Behaviour

→ **EGT4 elevation** — SUBSTANTIALLY ANSWERED. n=23 confirms mean +44.7°F ± 5.3°F, consistent direction across all flights. Hypothesis (turbo exhaust collector proximity) is consistent with findings but not independently confirmed. Continue monitoring — is this pattern consistent across other 916iS installations?

→ **ECO/POWER mode detection** — OPEN. Can ECO/POWER mode transitions be reliably detected from the correlated drop in fuel flow and EGT without direct throttle position data? Validation requires a deliberate known-throttle-position test flight. Backlog item A4.

→ **MAP at takeoff vs OM reference** — PARTIALLY ANSWERED. Empirical model built (v0.10.0): n=15 events, R²=0.71, MODERATE confidence. Observed MAP at N117ZS departures from KPAE (near sea level) is consistent with model predictions. Model needs altitude diversity (5+ flights from >2,000 ft MSL departures) for reliable multi-altitude validation. Backlog item A3.

→ **Cooling margin vs climb rate** — ANSWERED. Built in v0.7.0 (`climb.py`). Oil temp rise rate roughly triples from normal to aggressive climb rate. Validation ongoing with larger dataset.

### 12.2 CAS Alerts

→ **ENGINE ECU in-flight events** — SUBSTANTIALLY ANSWERED. 1 genuine IN_FLIGHT event identified across 23 flights (KSFF, 2026-05-27, OIL PRESS co-active). Remaining events are consistent with intermittent CAN dropout. B.U.D.S. fault log pull still recommended at next maintenance event.

→ **EFIS ON BKUP / NAV ON BKUP** — OPEN. What does this indicate in the CAS string — normal avionics backup mode operation, or a transient powerup condition?

### 12.3 Data and Analytics

→ **Baseline reliability thresholds** — PARTIALLY ANSWERED. Current labelling: n<10 = LOW, n<30 = MODERATE. At n=23 the EGT spread baseline is usable but still building. Target n=30+ for high-confidence baselines on all metrics.

→ **DA/OAT banding granularity** — OPEN. What band granularity gives useful balance between comparability and sample size per band? Current bands (low/moderate/high/very_high for DA; cold/mild/warm/hot for OAT) are working but per-band n is small. Backlog item C3.

→ **Power/altitude/fuel-flow model** — OPEN. Build a DA × power setting → expected gph model to replace blended personal average for cruise fuel flow comparison. Backlog item A5.

→ **Maintenance event tracking** — OPEN. No mechanism exists to record maintenance events and detect metric shifts before/after service. Backlog item D2.

---

## 13. Revision History

| Version | Date | Changes |
|---|---|---|
| 0.1 | June 2026 | Initial edition. Operating limits from OM. Data architecture documented. Analytics modules defined. First flight log analysed (N117ZS, 18 May 2026). ENGINE ECU investigation initiated. |
| 0.2 | June 2026 | ENGINE ECU resolved as expected behaviour (POWERUP/LANE_CHECK/SHUTDOWN) following multi-flight correlation analysis. Second flight log incorporated (Garmin Pilot export format). Fuel-flow calibration (K_fuel) explored, built, then deliberately descoped — see §6.2. Climb-rate-correlated thermal analysis (§6.7) and DA/OAT cross-flight normalisation approach (§9) added as identified gaps. Toolkit `fleet.py` module added for baselines/trends/outliers across engine hours. |
| 0.3 | July 2026 | Aircraft registration corrected throughout: N5512E → N117ZS. Dataset updated: 23 real flights (50 total log files, 27 ground sessions filtered). Added §6.1 EGT findings (n=23: mean spread 56.4°F ± 5.1°F, EGT4 elevation +44.7°F ± 5.3°F confirmed). Added §6.3 overboost findings (1 exceedance, 381s). Added §6.6 empirical MAP model (n=15, R²=0.71). Added §6.7 climb thermal findings (n=15). Updated §7 ENGINE ECU: 1 genuine IN_FLIGHT event identified (KSFF, OIL PRESS co-active). Updated §9.3 DA/OAT implementation status. Added §11.2–11.4 for toolkit v0.10.0 (script 04, two-layer format, insight_rules.json, baselines.json, models.json, Fleet Insights). Updated §12 open questions with current status. |

---

*Slingology EIS Research  •  N117ZS  •  KAWO •  Living document — update with each analytical finding*

*Edition 0.3 — July 2026*
