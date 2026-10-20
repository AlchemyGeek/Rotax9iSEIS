# ROTAX 91XiS ENGINE DATA ANALYTICS
## A Research Foundation for FADEC-Native Engine Monitoring

**Slingology EIS Project  |  N117ZS Sling TSi  |  KAWO**

Living Document — Edition 0.4 (draft for review)  |  October 2026

---

## Abstract

This paper documents a research programme to build open-source, FADEC-native engine health analytics for Rotax iS-powered aircraft, and records what the first 58 flights of one Rotax 916iS have shown. General-purpose platforms such as Savvy Aviation and FlySto are built around pilot-controlled mixture management; their signature diagnostics (rich-of-peak / lean-of-peak analysis, exhaust-valve detection from leaning behaviour) do not apply to an engine whose dual-lane ECU sets fuel, spark and operating mode itself. SlingologyEIS starts instead from what the iS engine actually controls and what its Garmin engine log actually contains.

Since Edition 0.3 the toolkit has become an application. SlingologyEIS 1.0.1 (October 2026) runs either as a local server or entirely inside the browser, reads Garmin G3X, Garmin Pilot and Garmin AXIS logs, keeps per-aircraft workspaces whose logs never leave the pilot's own folders, and answers two questions about every flight: *did anything go outside the Rotax Operators Manual limits* (events), and *is this flight unusual for this engine* (insights against a reference learned only from the aircraft's own history). A Trends page asks the second question over a longer horizon — *is my engine changing*. The analytics topics shown to pilots now rest on written admission criteria; several of Edition 0.3's modules were removed or demoted under them, and one of its findings — four "in-flight" ENGINE ECU events — was withdrawn as a classifier defect.

The dataset is 120 logs from N117ZS (April–October 2026, engine hours 28.2 → 122.2): 59 ground sessions are skipped automatically and three duplicate exports collapse, leaving 58 flights and 76 airborne hours. Findings as of this edition: cylinder 4 is the hottest cylinder on 58/58 flights, by a median 40 °F; cruise EGT spread averages 60.3 ± 5.5 °F and is rising at 0.12 °F per engine hour (R² 0.42), with the last twelve flights 5 °F wider than the reference, carried by cylinder 4; oil and coolant peaks have never approached their limits (201 ± 12 °F and 181 ± 7 °F against 248 °F) and depend on flight length more than on weather; one time-at-takeoff-power exceedance (389 s against 300 s) and one close call; the takeoff manifold-pressure model now stands at n = 56, R² 0.64, with the recent takeoffs delivering about 0.8 inHg more boost than it predicts; zero in-flight ENGINE ECU events in 117 logs. Three Operators Manual limits fire on most flights for diagnosed aircraft-specific reasons (fuel-pressure sender offset, a low idle setting, propeller-governor overshoot) and are handled by filters with a note rather than by changing the limits.

The long-term goal is unchanged: free, FADEC-native engine monitoring for the Rotax iS community, validated beyond a single aircraft.

---

## 1. Introduction and Motivation

The Rotax 916iS is a turbocharged, intercooled, liquid-cooled-head, FADEC-controlled four-cylinder engine: 160 hp (119 kW) at takeoff, 2,000-hour TBO, the highest-performance engine in the Rotax light-aviation line. The 915iS (139 hp, turbocharged) and 912iS (100 hp, normally aspirated) share its control architecture. All three differ from the Lycoming and Continental engines that dominate general-aviation analytics tooling in three ways that matter for engine monitoring:

- **No pilot mixture control.** A dual-redundant ECU (Lane A / Lane B) reads throttle position, manifold pressure and air temperature and from them sets injection, ignition timing and — above roughly 97 % throttle — the ECO/POWER mode transition. The pilot has one input, the throttle.
- **Liquid-cooled cylinder heads, air-cooled barrels.** The cooling-health observables are coolant temperature and EGT, not cylinder-head temperature in the traditional sense.
- **FADEC-calculated fuel flow.** There is no physical flow sensor. Fuel flow is a model-based value with a manufacturer-stated tolerance of about ±10 %.

Existing platforms do not account for this. Savvy Aviation's FEVA exhaust-valve analytics and ROP/LOP diagnostics depend on the mixture being varied by hand; on a FADEC engine they either cannot run or produce noise. FlySto replays flights and graphs any channel but has no engine-health model for an iS engine. Rotax's own B.U.D.S. software reads the ECU fault log directly but needs a hardware interface and is used at maintenance, not after every flight. A pilot with a Rotax iS engine and a modern glass panel has therefore been collecting a rich engine log on every flight with nothing designed to read it.

The question this programme asks is: with the mixture fixed by the computer, which engine-health questions can a flight log answer, and how should they be answered so that a pilot can trust them? The answers so far are the subject of this paper.

**What changed since Edition 0.3.** Edition 0.3 (July 2026) described a Python toolkit and a 23-flight dataset. Since then: the dataset has grown to 58 flights; the toolkit has become a web application with a local-server and an in-browser mode; the aircraft's avionics changed from Garmin G3X to Garmin AXIS, adding a second log format; the analytics topics were audited against written admission criteria and the set changed; limit detection was reworked after a diagnosis of why some limits fired on every flight; limit filters, a change monitor, a Trends change page and a Journal of decisions were added; and the ENGINE ECU finding of Edition 0.3 was corrected. Each of these is covered below.

---

## 2. Data Architecture

### 2.1 Garmin EIS log sources

The engine reads Garmin engine logs from three export paths. All three normalise, inside the loader, to one channel registry; nothing downstream knows which path produced a frame.

| Source | Identification | Layout | Sampling | Notes |
|---|---|---|---|---|
| **G3X direct** (GDU 460 + GEA-24) | Row 1 `#airframe_info … product="GDU 4xx"` | metadata row · column header · 1 Hz rows | 1 Hz (verified: all inter-row deltas 1.000 s, N = 16,198) | Primary source April–October 2026. File name `log_YYYYMMDD_HHMMSS_ICAO.csv`; 111 columns. |
| **Garmin Pilot export** | As above with row 2 prefixed `#` | same | 1 Hz | Same columns; any file name. A flight exported both ways appears twice and collapses to one (§2.4). |
| **Garmin AXIS** | Row 1 `Product="AXIS"`; row 2 a `#` units row; row 3 camelCase column names | metadata · units · column names · rows | ≈ 0.83 Hz | Since October 2026 on N117ZS. **Variable column set** — 102 columns on one log, 117 on the next; mapping is by name only. |

The G3X metadata row carries aircraft ident, software version, system ID, airframe hours and engine hours. The AXIS carries the ident as `tail_number`, no system ID and no hours fields; engine hours are taken from the first row's `e1TachTime` channel — on N117ZS the same hour meter the G3X wrote (119.6 h on 14 October 2026, continuous with the G3X series), so baselines and trends carry straight across the avionics change with no user input.

**AXIS sampling.** The AXIS writes roughly five samples every six seconds (a repeating pattern of four 1,000 ms steps and one 2,000 ms step), so about one row in six is missing. Several engine paths count rows as seconds. The loader therefore reindexes AXIS frames onto a 1-second grid: numeric channels are linearly interpolated across holes of at most 2 s, text and CAS channels carry the previous value forward, longer holes stay missing, filled rows are flagged, and every AXIS analysis carries an informational diagnostic with the filled share (≈ 17 %). G3X logs are never resampled. G3X and AXIS frames are therefore sample-for-sample comparable, and phase detection, limits and topics produce the same classes on either. A time-based engine (elapsed-second arithmetic throughout) is the honest long-term fix and is on the backlog as hardening.

**AXIS differences handled in the loader.** CAS alert tokens are normalised to the G3X wording through a per-source alias table (*EFIS ON BACKUP* → *EFIS ON BKUP*, *NAV ON BACKUP* → *NAV ON BKUP*), so events, filters and Journal entries use one name per alert; AXIS names the ECU alert `ENGINE ECU` as the G3X does (confirmed on the 18 October log). General-purpose analog inputs (`engine1GeneralPurposeAnalog<n>`) carry whatever the installation wired to them and are **never mapped by assumption**: they enter under a raw id and appear under a registry name (CO ppm on N117ZS) only when the pilot assigns them in the app's settings. AXIS-only channels (`onGroundState`, `flightTime`, `e1TachTime`) are carried raw and are not used by phase detection, so a reference built from G3X flights stays valid for AXIS flights of the same aircraft. The first AXIS logs examined opened with the engine already running, one to two minutes after boot; of the five now in the set, two do record the engine start, three carry a complete two-lane check, and all five name the alert `ENGINE ECU` (§8) — so the ECU classifier works unchanged on AXIS, and a log that opens mid-run is treated as normal for the source rather than as a mid-log power cycle.

### 2.2 Engine parameters available from the FADEC CAN bus

The GEA-24 (and the AXIS engine interface) receives the following from the 916iS over the Rotax display CAN bus (Garmin G3X Installation Manual §24.2.2.3; Rotax OM communication-interfaces section):

| Channel | Source | Notes |
|---|---|---|
| RPM | FADEC CAN | Propeller-shaft rpm after gearbox reduction |
| Engine power (%) | FADEC CAN | ECU-computed share of rated power; can exceed 100 % at takeoff |
| Manifold pressure (inHg) | FADEC CAN | Plenum pressure; the turbocharger health observable |
| Oil pressure (psi), oil temperature (°F) | FADEC CAN | |
| Coolant temperature (°F) | FADEC CAN | Cylinder-head liquid cooling |
| Fuel flow (gal/h) | FADEC calculated | Model-based; no physical sensor; ±10 % |
| Fuel pressure (psi) | Separate sensor | Rail pressure relative to manifold pressure |
| EGT1–4 (°F) | FADEC CAN | Per-cylinder exhaust gas temperature |
| Main volts, battery amps | GEA-24 / AXIS | Bus voltage and battery current |
| CAS alert string | Avionics | Composite annunciation of all active alerts (`ENGINE ECU`, `FUEL PRESS`, `OIL PRESS`, …) |

Plus the flight data the analytics need to know what the aircraft was doing: indicated and true airspeed, ground speed, barometric and GPS altitude, vertical speed, outside air temperature, density altitude, position.

### 2.3 Parameters not available in the log

The following exist in the ECU but are not exposed over the display CAN bus and do not appear in any of the three log formats. They are accessible only through B.U.D.S. at maintenance:

- Throttle position — the quantity that determines ECO vs POWER mode
- Lane A / Lane B individual fault codes and status
- Injector pulse width per cylinder; ignition advance angle
- Wastegate (boost-control valve) position
- Manifold air temperature (on the CAN bus, not in the standard column set)
- The ECU's internal fault history

This gap is a design constraint, not a footnote. The topic-admission criteria (§7.1) exclude any topic that needs one of these channels, and the app never infers them. ECO/POWER mode detection remains an open research item (§4).

### 2.4 The dataset

| | |
|---|---|
| Aircraft | N117ZS, Sling TSi, Rotax 916iS, constant-speed propeller with governor |
| Avionics | Garmin G3X Touch (GDU 460, GEA-24) to 5 October 2026; Garmin AXIS from 14 October 2026 |
| Logs | 120 files: 112 G3X direct, 3 Garmin Pilot exports, 5 AXIS |
| Admission | 59 ground sessions skipped (no airborne phase); 3 duplicate exports collapsed; 0 short flights; 0 corrupt logs → **58 flights** (52 G3X, 1 Garmin Pilot, 5 AXIS) |
| Period | 8 April – 18 October 2026; engine hours 28.2 → 122.2 |
| Time | 93.9 h recorded, **76.0 h airborne**; median flight 45 min airborne, longest 293 min; 17 flights under 20 min airborne, 26 over an hour |
| Departures | 18 airports; home field KAWO (27 departures); a July cross-country to Oshkosh (KBIL, KFCM, KOSH, KMML, KRAP, KHLN); 5 departures above 2,000 ft pressure altitude (max 3,685 ft, KHLN) |
| Conditions | cruise OAT 1.6–24.1 °C (OAT bands: 48 mild, 6 cold, 1 warm, 0 hot; 3 flights with no cruise); cruise density altitude 775–15,506 ft (DA bands: 12 low, 28 moderate, 7 high, 8 very high); maximum altitude 15,066 ft |
| Fuel | 508 gal FADEC-integrated, 6.7 gal per airborne hour overall |

The same 120 logs are the test set for the application: the characterization and contract tests assert on this set's counts, and every analysis in this paper was produced by the released engine (1.0.1) with its shipped defaults and **no filters applied** — the topics' natural signal, not what the pilot sees after setting filters.

**Single-aircraft caveat.** Every empirical number in this paper comes from one 916iS in one airframe. The topic register records every such finding as *E3 (916iS, 1 aircraft)*, and every topic is *Unverified* on the 912iS and 915iS until data from such an aircraft exists (§7.1).

---

## 3. Operating Limits and How They Become Events

### 3.1 Engine profiles

Limits come from each engine's Rotax Operators Manual and live in an engine profile (`engines/<model>.json`) with the edition cited. The OM text is never stored in the repository.

| Profile | Source | Status |
|---|---|---|
| 916iS | OM-916 i/C24, Edition 0 / Rev. 1, December 2023 | VERIFIED |
| 915iS | OM-915 i A/C24, Edition 0 / Rev. 4, September 2022 | VERIFIED |
| 912iS | OM-912 i Series, Edition 2 / Rev. 2, September 2025 | VERIFIED — no manifold-pressure or EGT-split limit, as the OM defines none |

A "914iS" placeholder that existed earlier was removed: the Rotax 914 is a carburetted turbo engine, not an iS engine, and no such OM exists.

### 3.2 The 916iS limits (OM Chapter 2.1)

**Engine speed**

| Condition | Minimum | Maximum | Notes |
|---|---|---|---|
| Idle | 1,800 rpm | — | |
| Normal continuous | — | 5,500 rpm | |
| Takeoff (max 5 min) | — | 5,800 rpm | Time-limited |
| Boost pressure peak | — | 6,500 rpm | Max 1,990 hPa for 3 s only |

**Temperatures**

| Parameter | Min | Max | Notes |
|---|---|---|---|
| Oil temp — takeoff minimum | 50 °C / 122 °F | — | Must be reached before takeoff |
| Oil temp — normal | 50 °C / 122 °F | 120 °C / 248 °F | |
| Oil temp — optimal | 90–110 °C / 194–230 °F | | Below this risks condensation in the sump |
| Coolant temp | — | 120 °C / 248 °F | |
| EGT, per cylinder | — | 950 °C / 1,742 °F | |
| EGT split, fuel flow > 3 L/h | — | 200 °C / 392 °F | The cylinder-balance limit |
| EGT split, fuel flow < 3 L/h | — | 500 °C / 932 °F | Idle only |
| Manifold air temp | — | 50 °C normal, 80 °C extended | Not logged |

**Pressures**

| Parameter | Min | Max | Notes |
|---|---|---|---|
| Oil pressure, > 3,500 rpm | 2.0 bar / 29 psi | 5.0 bar / 72.5 psi | |
| Oil pressure, cold start | — | 7.0 bar / 101.5 psi | |
| Manifold / boost pressure | — | 1,800 hPa / 53.15 inHg | Peak 1,990 hPa for 3 s |
| Fuel pressure (rail, relative to MAP) | 2.9 bar / 42 psi | 3.2 bar / 46 psi | Exceedance band 2.5–3.5 bar for max 3 s after a power change |

**Other:** negative G −0.5 G for 5 s; critical altitude 15,000 ft; max operating altitude 23,000 ft; ECO/POWER threshold ≈ 97 % throttle position; single-lane operation always POWER mode.

The 915iS and 912iS profiles differ in a few values (912iS idle minimum 1,400 rpm; 915iS/912iS oil maximum 266 °F; 912iS oil-pressure minimum 12 psi below 3,500 rpm; MAP maximum 51.09 inHg on the 915iS, none on the 912iS). The app also checks bus voltage (11.5–14.5 V), which is not an OM limit: it is a 12 V installation check included because a charging fault shows there first.

### 3.3 From a reading to an event

A reading past a limit for one second is not an event. The 916iS profile checks 21 limits (including per-cylinder EGT maximums, the two EGT-split limits and the five-minute takeoff-power rule) under three rules that were found necessary on real data:

1. **Some excursions must last.** Idle minimum must persist 30 s (a brief dip as the governor settles is normal); fuel-pressure minimum 10 s; fuel-pressure maximum 10 s in climb and descent but 30 s in cruise, where switching tanks causes a longer, harmless spike.
2. **Some limits are checked only when they make sense.** Low oil pressure, low fuel pressure and low voltage are not checked with the engine stopped (an engine-running gate at 1,000 rpm). Oil-pressure minimum is checked only once airborne; the oil-temperature-before-takeoff minimum from the takeoff roll on; fuel-pressure maximum not during taxi at all, because that is when the fuel-pump test is run. Idle minimum is checked only after idle rpm has been reached once since engine start.
3. **Nearby excursions are one event.** An event ends only after the reading has stayed inside the limit for 30 s (the *merge gap*). A value that bounces across the line for two minutes is one two-minute event, not forty.

What remains is an event: time, phase, limit, duration and excess, at most one insight per limit per flight. Each limit carries the OM's own WARNING or CAUTION label; the labels help read the table and nothing else — the app never hides a caution, escalates a warning or decides on the pilot's behalf which deserves action (a program principle recorded in October 2026: the OM is the only predefined rule; the pilot overrides it through operations such as filters; the system's job is to say when something in those operations changed).

Why this matters: before phase awareness the fuel-pressure maximum "fired" on four flights out of five and the low-voltage limit on half of them — the fastest way to teach a pilot to ignore every alert. The limits are unchanged; what changed is knowing when a reading is *expected* to be out of range.

**Time at takeoff power.** The OM's two rpm rules were encoded wrongly in earlier toolkit versions: 5,500 rpm "continuous" raised a caution on every takeoff because it had no time allowance, while a short run above 5,800 rpm went unreported. Now a single rule — *overboost* — owns the five-minute allowance: the longest continuous block above 5,500 rpm or 100 % power (with the same 30 s merge), an event past 300 s, a *close call* within 60 s of it. The 5,800 rpm ceiling is a separate hard limit with no time allowance (§7.6 on why it fires on most flights of this aircraft).

---

## 4. ECO / POWER Mode — Still Not Detectable

The 916iS FADEC runs two fuel/ignition maps: POWER (≥ 97 % throttle position: enrichment, maximum performance, takeoff and climb) and ECO (< 97 %: lean mapping, best economy, cruise and descent; available only with both lanes operating). The threshold is a *throttle-position* percentage, not an engine-power percentage: 97 % throttle at altitude with a coarse propeller setting may produce 55 % of rated power. The log carries engine power (ECU-computed output), not throttle position.

Edition 0.2 hypothesised that ECO transitions are detectable as correlated simultaneous drops in fuel flow and EGT at constant altitude and rpm. That remains a hypothesis. Validation requires a flight with deliberate, known throttle positions, which has not been flown; the 912iS OM states no throttle-position threshold at all. The app does not attempt the inference and no topic depends on it (backlog A8). The practical consequence is that fuel-flow comparisons across flights mix two ECU maps, which is one of the reasons cruise fuel flow is no longer an analytics topic (§7.8).

---

## 5. Automatic Flight Phase Detection and Log Admission

Manual phase labelling is excluded by design: the pilot never annotates a log. Everything else in the system — which part of a flight feeds which topic, when a limit is checked, whether an ENGINE ECU alert is expected — depends on the phase detector, so it is described here as built.

### 5.1 The detector

A state machine runs over smoothed signals (rpm, IAS, vertical speed, barometric altitude, power; 5–11-sample moving means so that one noisy reading cannot flip a phase), with dwell times before committing to a new phase.

| Phase | Entered when | Notes |
|---|---|---|
| PRE_START | log start | Avionics on, engine not running |
| ENGINE_START | rpm > 500 | |
| WARMUP | rpm 1,500–3,000 and IAS < 30 kt | A generous IAS ceiling: several real flights show a 10–25 kt IAS floor while parked (wind, pitot noise), and ENGINE_START has no other exit |
| TAXI | IAS > 5 kt from WARMUP | A run-up that drops back to idle without leaving the ground stays in TAXI |
| TAKEOFF_ROLL | rpm > 4,500, IAS < 60 kt, height above field < 50 ft | A turbocharged iS can spool from idle to full power within one 1 Hz sample; the gate is wide for that reason. A gusty run-up falls back to TAXI |
| CLIMB | IAS > 50 kt and VS > 200 fpm | The only gate that confirms lift-off |
| CRUISE | \|VS\| < 200 fpm sustained 60 s (45 s from DESCENT) | Exit at ±300 fpm held 3 s (hysteresis) |
| DESCENT | VS < −300 fpm | |
| APPROACH | low (< 500–1,500 ft above field, depending on the phase left) and slowing | Reachable from CLIMB only after climbing 800 ft clear of the pattern |
| LANDING_ROLL | rpm < 2,000, IAS < 30 kt, near the ground | |
| SHUTDOWN | rpm < 500 | Can return to ENGINE_START (a restart) |

**Field elevation** is estimated from barometric altitude while stationary before takeoff — no user entry — and re-anchored wherever the aircraft is next detected on the ground (sustained IAS < 30 kt with rpm < 2,000 for 10 s, which cannot happen in flight). Without that, flights landing at a higher field than they left (eleven in this set, 107–3,422 ft higher) stayed in DESCENT or APPROACH through roll-out, taxi and shutdown, and multi-leg logs could not detect the next takeoff.

Three further fixes came from real flights that had collapsed into one TAXI or ENGINE_START phase; each was made under a regression rule (snapshot every log's phases, metrics and exceedances before the change, compare after, confirm every difference is intended) that is now mandatory for any change to a detection heuristic.

**Known limitations** (backlog S1, S2): after landing, DESCENT/APPROACH can run through the taxi-in because taxi power is above the on-ground test's 2,000 rpm, and LANDING_ROLL leaves only on IAS < 5 kt, which some logs never show at rest — so an in-flight label can outlast the engine cut (the ECU classifier works around this with an engine-state rule, §8); and LANDING_ROLL exits only to TAXI or SHUTDOWN, so a touch-and-go misclassifies every later circuit (stop-and-goes and go-arounds are handled). Both are hardening items, not blockers.

### 5.2 Which phases feed what

- Cylinder balance (spread and per-cylinder deviation): **cruise only**, where the engine is settled and the cylinders can be compared fairly.
- Turbo boost at takeoff: **takeoff roll** at ≥ 5,500 rpm.
- Time at takeoff power: every second above the threshold, any phase.
- Oil and coolant peaks: the whole flight.
- ENGINE ECU runs: sorted by phase into expected (start, lane check, shutdown) and not expected (ground with the engine running, in flight).
- Phase-aware limit checks: §3.3.

A short flight, a pattern session or a flight that never settled may have no cruise; the cruise-based cards then say *unavailable: no cruise detected* rather than reporting a number from a few seconds of level flight (3 of the 58 flights).

### 5.3 Log admission

Every discovered file is classified once, when first seen, by one classifier shared by the CLI loader, the folder scan and drag-and-drop import, so the three cannot disagree:

1. **Ground session** — no row lands in an airborne phase (CLIMB, CRUISE, DESCENT, APPROACH, LANDING_ROLL). TAKEOFF_ROLL deliberately does not count: TAXI → TAKEOFF_ROLL fires on rpm alone, and only CLIMB's altitude-gain gate confirms lift-off. The case that proved it was a ground run-up on 6 July that pushed rpm past 4,500 with the altitude flat. This rule replaced an earlier proxy (rpm > 3,000 and IAS > 30 kt for ≥ 3 min); on the 54 files then available the two agreed exactly.
2. **Short flight** — total airborne time under 10 minutes (configurable). Aimed at three-minute circuits, not at a twelve-minute hop. No log in the current set trips it.
3. **Corrupt log** — a time gap of more than 5 minutes inside one session, evaluated on the 1-second grid so AXIS's routine 2 s holes never count.

Skipped logs are recorded with the reason, listed under *Skipped* in the app with a read-only preview, and can be included by the pilot; the override is permanent and survives rescans. Duplicate exports of the same flight (the same G3X session copied from the SD card and exported from Garmin Pilot) are identified by a content fingerprint and collapse to one. A file the loader cannot read is listed as *Unreadable* with the reason and never stops the other logs. On the current set: 120 files → 59 ground sessions → 61 loaded → 3 duplicates → 58 flights.

A separate, pilot-only tier keeps an admitted flight out of the *reference* (§6) without removing it from the workspace — for a flight after maintenance, a known bad probe, a ferry flight flown very differently from the norm. Exclusion needs a reason and is a Journal decision.

---

## 6. Two Layers: What Rotax Says and What Is Normal for This Aircraft

The analysis is built in two layers, and keeping them apart is the design's central decision.

**Layer 1 — the engine profile: what Rotax says.** One per engine type, from that engine's OM, every limit cited. It answers *did anything go outside the manufacturer's limits* and is the same for every aircraft with that engine (§3).

**Layer 2 — the aircraft model: what is normal for *this* aircraft.** Learned only from that aircraft's own flights: baselines, trends, the takeoff-MAP model, the usual hottest cylinder. It answers *is this flight different from how this engine usually behaves*. No number learned from one aircraft is applied to another. Two 916iS engines in two Sling TSis will not run the same oil temperature on the same day — cowling, baffling, oil cooler, probe placement, the individual engine shift the numbers by more than the changes the system is trying to detect — so a fleet-wide "normal" would hide exactly the changes that matter.

### 6.1 The reference

For each tracked metric the reference is the mean and standard deviation across the aircraft's **other** flights. "Other" is literal: a flight is left out of its own reference (leave-one-out), so one unusual flight cannot make itself look normal. On the 23-flight dataset of Edition 0.3, self-inclusion changed four borderline results (z between 1.8 and 2.1, always damped).

A flight is flagged when a metric sits more than **z = 2.0** standard deviations from its reference (the *outlier z-threshold*, roughly the outer 5 % of the aircraft's own history), once at least **n_min = 10** other comparable flights exist; below that the card shows the number with *still building*. One number, two consumers: the same threshold rings outlier points on Trends charts and fires the baseline-deviation insight, so "unusual" means the same thing everywhere.

**Minimum detectable change.** The practical consequence of a baseline anchor is that the smallest change a trigger can separate from flight-to-flight noise is about 2 SD of the metric. This *MDC* is now an admission criterion (§7.1): a topic whose mechanism implies a change smaller than its MDC needs conditioning before it is shown.

### 6.2 Stratification by conditions

Every cross-flight comparison assumes the flights are comparable. They are not by default: density altitude and outside air temperature both affect engine behaviour independently of anything mechanical, and they affect different things.

- **Density altitude** is the right single normaliser for *performance* quantities — power at a throttle setting, manifold pressure, true airspeed from indicated: two flights at the same DA present the engine with the same oxygen.
- **Outside air temperature** is separately needed for *thermal* quantities — EGT, oil and coolant temperatures — because the ambient air is simultaneously the cooling medium for the intercooler, oil cooler and radiator. A hot-and-high flight and a cold-and-low flight can share a DA and have different cooling margins.
- **Stratification is preferred over invented correction formulas** where no OM reference exists.

Bands as implemented: OAT cold < 5 °C, mild 5–20, warm 20–30, hot > 30; DA low < 2,000 ft, moderate 2,000–5,000, high 5,000–9,000, very high > 9,000. Thermal metrics (spread, per-cylinder deviations, oil and coolant peaks) use the OAT band; cruise fuel figures and the takeoff-MAP limit metric use the DA band; event counts and climb rates are not stratified.

Since engine 0.25.0 stratification is no longer display-only: the baseline-deviation insight compares a flight against the leave-one-out reference of its **own band** when that band has at least n_min other flights, falling back to all flights otherwise, and the message says which (*2.1 std devs above your other mild flights, n = 47* vs *above all your flights, n = 57*). This removed seasonal false positives — a hot-day oil peak standing out against a reference that included winter flights — and made the insights agree with the stratified Trends view. The cost, accepted deliberately, is that per-band samples are smaller: on this dataset 48 of 55 cruise flights are *mild*, so the cold, warm and hot bands fall back to the unstratified reference.

### 6.3 Trends over engine hours

Besides *is this flight unusual*, the reference answers *is this metric drifting*. A straight line is fitted to each metric against engine hours across all flights; a trend is reported — and a trend insight fires — only when the line explains at least half the variation (**R² ≥ 0.5**) and there are at least ten flights. Below that gate no line is drawn and no insight fires; a weak trend is not reported as if it were strong. The gate has not yet been cleared by any metric on N117ZS (§7.2).

---

## 7. Analytics Topics

### 7.1 Admission: why these topics and not others

Edition 0.3 listed fourteen "agreed topics" that had grown bottom-up as modules were built where gaps were found. In October 2026 the set was audited against seven written criteria (Spec 10), and each topic now has a written case for existing, an evidence grade, and a status per engine. The criteria:

| # | Criterion | Test |
|---|---|---|
| A1 | Observable | Every input channel is in the standard log and the phases it needs occur on a typical flight (rules out anything needing throttle position, lane status, injector data) |
| A2 | FADEC-relevant | The question still means something when the ECU controls mixture, injection and ignition (rules out ROP/LOP, peak-EGT, FEVA) |
| A3 | Anchored | At least one anchor — OM limit, personal baseline, empirical model, or classification rule — and the analysis line states it |
| A4 | Mechanism | Names what it detects and grades the evidence: E1 manufacturer, E2 established engineering practice, E3 observed in this project's data (always with engine type and aircraft count), E4 hypothesis. **Admission needs E1 or E2**; E3 alone shows a pattern exists, not what it means |
| A5 | Actionable | A pilot or mechanic does something different when it fires; "interesting" is not an action |
| A6 | Distinct | No other topic or limit fires on the same signal; two cards for one event is a defect |
| A7 | Discriminating | For baseline and model anchors, the measured MDC is below the change the mechanism implies, within the comparison scope actually used |

Two consequences of A6 shape what the pilot sees. **Every event is reported once**, by the *Operators Manual limits* topic, whatever its source (an OM limit or a classified CAS alert); a topic that references a limit — oil peak, coolant peak, time at takeoff power, ENGINE ECU — states it in its analysis line and mirrors the badge but never emits a second insight. And **planning numbers are not topics**: cruise nm/gal, cruise fuel flow and fuel burned are mostly wind, weight and the pilot's choice of power, so they appear as *flight facts* in the flight header (alongside the lane-check result) with no insight and no trend.

The register as of this edition, for the 916iS:

| Topic | Question | Anchor | Status | Trends panel |
|---|---|---|---|---|
| Cylinder balance (EGT spread) | Are my cylinders burning evenly? | OM split limit · baseline · trend | Admitted | Cylinder balance |
| Cylinder EGT deviation | Is any one cylinder drifting from the others? | baseline · trend, per cylinder | Admitted (Spec 08) | Cylinder balance |
| Hottest cylinder (rank) | Has the usually-hottest cylinder changed? | classification | Admitted — insight retired, rank kept as context | — |
| Oil temperature peak | Did oil get hotter than usual? | OM limit (referenced) · baseline | Admitted | Thermal |
| Coolant temperature peak | Did coolant get hotter than usual? | OM limit (referenced) · baseline | Admitted | Thermal |
| Time at takeoff power | Did I stay at takeoff power too long? | OM limit (referenced) · close-call margin | Admitted | Boost / power |
| Turbo boost at takeoff | Is the turbo making expected boost? | empirical model | Admitted (not on the 912iS) | Boost / power |
| Engine computer alerts in flight | Did the FADEC report a fault in flight? | classification | Admitted (provisional) | per-alert event panel |
| Operators Manual limits | Did anything go outside an OM limit? | all OM limits | Admitted — owner of events | per-limit event panels |
| Climb thermal rate | — | baseline | **Research** (fails A7) | context strip |
| Oil/coolant ratio, EGT4 elevation, flight-phase mix, cruise efficiency, cruise fuel flow | — | — | **Removed** | — |

On the 912iS and 915iS every applicable topic is *Unverified*: the same analysis runs, the card says it has not yet been validated on that engine, and it becomes Admitted when data from such an aircraft passes A7. The whole register is re-audited when the flight count doubles, before each edition of this paper, and whenever data from a new aircraft or engine type arrives.

### 7.2 Cylinder balance

On a FADEC engine the four cylinders should behave as a matched set: the ECU gives each the fuel and spark it intends, so a cylinder that drifts from its neighbours is reporting on an injector, plug, coil or probe — not on how the engine was leaned. Two measurements, both in cruise:

- **Spread** — hottest minus coolest cruise EGT — the one-number summary and the OM-limited quantity (392 °F above 3 L/h fuel flow).
- **Deviation** — each cylinder's cruise EGT minus the mean of the other three — the diagnostic version: which cylinder moved, which way. The four deviations sum to zero, so when one moves the others appear to move the other way; the insight names the cylinder whose change is largest. Admission evidence E2 (lean cylinder runs hot → injector; cooler → ignition or plug; erratic → probe), with Spec 08 as the topic spec.

The earlier toolkit assumed cylinder 4 is hottest ("typical for the 916iS — turbo exhaust proximity"). That assumption is not universal (installation, individual engine, probe insertion all shift it), so the app now **learns** the usual hottest cylinder per aircraft — one cylinder winning ≥ 70 % of ten or more flights by a clear margin — with the engine profile's expectation (cylinder 4 on the turbo engines, none on the 912iS) as a prior until then.

**Findings, Edition 0.4 (n = 58):**

| Metric | Mean ± SD | Range | MDC (2 SD) | Mild band (n = 48) |
|---|---|---|---|---|
| EGT spread, cruise mean | **60.3 ± 5.5 °F** | 45.3–70.2 | 11.1 °F | 60.9 ± 5.8 |
| Cyl 1 deviation | −31.6 ± 5.3 °F | −40.8 to −14.0 | 10.5 | −32.2 ± 5.1 |
| Cyl 2 deviation | −9.1 ± 5.9 °F | −25.5 to +10.2 | 11.9 | −9.1 ± 5.9 |
| Cyl 3 deviation | −6.9 ± 4.0 °F | −16.9 to +0.6 | 7.9 | −7.0 ± 4.1 |
| Cyl 4 deviation | **+47.6 ± 5.3 °F** | +28.9 to +58.2 | 10.7 | +48.3 ± 5.5 |

- **Hottest cylinder: cylinder 4 on 58 of 58 flights**, learned at 100 % (n = 57), by a margin over the next cylinder of 14.0–50.4 °F (median 39.8). Rank order 4-3-2-1 on 32 flights, 4-2-3-1 on 25, 4-3-1-2 on one; the hottest-cylinder-changed condition has never fired. Edition 0.3's "EGT4 elevation +44.7 ± 5.3 °F" is the same observation with a slightly different denominator (EGT4 minus the mean of 1–3); that metric was removed as redundant with the cylinder-4 deviation.
- **Spread trend: +0.118 °F per engine hour, R² 0.42** over 58 flights (Edition 0.3: +0.22 °F/h, R² 0.30, n = 23). The direction has been consistent through three editions; R² has not cleared the 0.5 reporting gate, so no trend insight has fired.
- **The recent window is wider.** Trends' change summary (§10) ranks the spread second of six qualifying changes: the last 12 flights (111.9–122.2 h) average **65.1 °F** against the 60.3 °F reference (shift z = +3.7, with a *bend* — the recent slope is 0.66 °F/h against 0.11 °F/h over the whole history). The change is carried by **cylinder 4**, whose deviation averages +51.8 °F in the window (z = +3.3), with cylinder 2 moving the other way (−12.7 °F, z = −2.7). The five AXIS flights are in the window, but the seven G3X flights in it average 64.6 °F spread and +50.4 °F on cylinder 4, so the change is not an artefact of the avionics change or the 1-second resampling. It is the first engine-level change the Trends page has reported on this aircraft and the one to watch.
- **Insights fired (unfiltered):** 9 per-cylinder deviation insights on 8 flights — cylinder 1 twice, cylinder 2 three times, cylinder 3 twice, cylinder 4 twice — all *watch*, none on consecutive flights, and 3 of them noting that the spread was also outside its range. At z = 2 across four cylinders and 58 flights about 12 chance firings are expected, so this rate is consistent with noise; no cylinder shows a persistent pattern. The spread's own baseline trigger never fired alone — it is folded into the cylinder insight whenever both fire (Spec 10 D8), and its niche (a divergence across cylinders that no single cylinder explains) has not occurred.
- No EGT maximum or EGT split limit has ever been approached (highest spread 70 °F against 392 °F).

### 7.3 Oil and coolant temperature peaks

OM limit 248 °F for both (E1). Each topic compares the flight's peak with the aircraft's usual peak in the same OAT band; the limit itself belongs to the limits topic (§7.1).

**Findings, Edition 0.4 (n = 58):**

| Metric | Mean ± SD | Range | MDC | OM limit | Exceedances |
|---|---|---|---|---|---|
| Oil peak | **201.1 ± 12.1 °F** | 180–225 | 24 °F | 248 °F | 0 |
| Coolant peak | **180.8 ± 7.1 °F** | 170–198 | 14 °F | 248 °F | 0 |

- The headroom is large: the hottest oil peak (225 °F, Billings, 17 July, 31 °C departure) sits 23 °F under the limit, the hottest coolant peak (198 °F) 50 °F under it. The *cold* band (n = 6) runs a hotter oil peak (209.5 °F) than *mild* (200.5 °F): the band is set by cruise OAT, and those six are long cross-country flights cruising high enough for the air to be cold — which is the point of the next finding.
- **Flight length drives the peaks more than weather does.** Peak oil temperature correlates with airborne time at **r = 0.66** (coolant r = 0.39): hour-plus flights peak about 18 °F above 10–20-minute ones, and 17 of 58 flights are under 20 minutes airborne, never reaching thermal equilibrium. Edition 0.3's wider SDs (31 and 26 °F on an earlier snapshot) were a duration artefact, not weather. No airborne-time threshold was applied, because the measurement found no duration beyond which the dependence stops (r ≈ 0.6 at every candidate from 10 to 30 minutes); predicting the expected peak from airborne time and OAT is a research item (backlog A6), and the topic help tells the pilot that a lower peak after a short hop is normal.
- **Insights (unfiltered):** 3 oil and 3 coolant *watch* insights, on the same three flights — 8 April (26 °C departure, the aircraft's first flight in the set), 17 July (KBIL, 31 °C) and 23 July (KHLN, 31 °C): the three hottest, highest-elevation departures of the year, each flagged against the mild band it was compared with because the warm band holds a single flight. These are the stratification fallback working as specified, and the kind of case that stays a note rather than a finding.
- **The optimal band is rarely reached.** The OM gives 90–110 °C (194–230 °F) as the optimal oil range, below which condensation can accumulate in the sump. On N117ZS oil temperature is below 194 °F for **90.6 ± 12.6 %** of flight time (Edition 0.3: 91 %). The metric is computed but has no topic yet; it is candidate C1 in the register (E1 basis, clear action), the one coverage gap with a known mechanism and no card.
- **Recent window.** Both peaks rank in the change summary as *lower* (oil 192.7 °F, coolant 176.3 °F; z ≈ −2.9). The twelve recent flights average 46 minutes airborne against 81 for the reference, so this is the duration effect again, not cooling improving. It is also the clearest argument on current data for the planned condition strip under each Trends panel (backlog T3), which would show duration and OAT next to the metric.

**Oil/coolant ratio — removed.** Edition 0.3 reported an oil/coolant peak ratio of 1.10 ± 0.04 as "a signature of thermal health". It was dropped under the audit for two reasons: a ratio of two temperatures on an interval scale has no physical meaning (the same flight gives a different ratio in °C, and an equal rise in both moves it), and the mechanism was unsourced. Its very low CV reflected the ratio compressing the data, not a stable signal. A better form — the cruise-phase mean of the simultaneous oil − coolant difference, 19.9 ± 2.6 °F over 47 flights, MDC 5.1 °F — is discriminating and physically interpretable (oil-cooler effectiveness vs radiator effectiveness), but whether the oil–coolant relationship is an established health indicator in Rotax or engine-monitoring practice is unknown, and admitting it ahead of that answer would repeat the original mistake with a better number. It is candidate C5, Proposed, with the measurements above as its starting data.

### 7.4 Time at takeoff power

Operational class; the OM's five-minute allowance at takeoff power (E1); the action is throttle discipline — reduce to climb power once safely airborne.

**Findings, Edition 0.4 (n = 58):**

- **One exceedance:** 23 April (KTOA → KACV), longest block **389 s** against 300 s (Edition 0.3 reported 381 s on the same flight; the 30 s merge gap now joins a brief dip). Confirmed cause: ATC workload before the throttle was reduced.
- **One close call:** 27 May (KSFF departure), 274 s — 26 s under the limit.
- 56 of 58 flights ≤ 240 s. Mean longest block 70 s, median 58 s; total time at takeoff power 101 ± 84 s per flight.
- Since Spec 09 v0.12 the exceedance is an ordinary event owned by the limits topic; the *Time at takeoff power* card references it and keeps what only it can report — the close call and the time-in-regime context.

### 7.5 Turbo boost at takeoff — the empirical MAP model

Under-boost at full power points to the turbo, wastegate or an intake leak (E1: OM reference MAP and air-supply guidance); over-boost is usually worth a sensor check. Rather than a single OM reference point, the app fits the aircraft's own takeoffs: rows with phase TAKEOFF_ROLL and rpm ≥ 5,500; features pressure altitude and OAT; target manifold pressure; ordinary least squares.

**Findings, Edition 0.4:**

| | Edition 0.3 | Spec 10 audit (Oct 1) | Edition 0.4 |
|---|---|---|---|
| n (takeoffs) | 15 | 48 | **56** |
| R² | 0.71 | 0.75 | **0.64** |
| Residual SE | — | — | **0.84 inHg** |

- Fitted: MAP = 42.87 + 0.000675·PA(ft) + 0.155·OAT(°C) inHg. Over the dataset's ranges (PA −264 to 3,685 ft; OAT 12.7–31.1 °C) each term spans about 2.5 inHg. Observed takeoff MAP: 46.3 ± 1.4 inHg (43.8–49.5). The OM's single reference figure (1,690 mbar ≈ 49.9 inHg at 5,800 rpm, 25–35 °C) stays on the analysis line as context, not as a tolerance.
- **The tolerance comes from the model, not a hard-coded number.** Edition 0.3's ±1.5 inHg was a coded constant, and the rules file said 20 hPa — a mismatch the audit quantified (1 firing at 1.5 inHg vs 23 at 20 hPa on 48 flights). Now: tolerance = 2 × the leave-one-out residual SD, so a flight is never judged by a model it helped fit; on current data ±1.5–1.7 inHg. A **fitted-range guard** suppresses the judgement, with a note, when a takeoff's PA or OAT lies outside anything the model was fitted on — which under leave-one-out means the dataset's extreme flight on each axis is never judged (4 of 48 at the audit). Accepted: "never extrapolate" is the simplest defensible rule, and the range widens as more places are flown.
- **Altitude diversity is still thin:** 5 departures above 2,000 ft. The guard means this limits *where* the topic can judge, not whether its judgements are sound.
- **One insight:** 14 October (the third AXIS flight), observed 47.9 inHg at −212 ft and 17 °C against 45.4 expected — +2.56 inHg, *verify sensor*. It is on an AXIS log, the first with the 1-second resampling; whether the capture window behaves identically on AXIS is a question for the next AXIS flights.
- **The top-ranked change on Trends is this model's residual.** The last 11 takeoffs deliver on average **0.8 inHg more boost than the model predicts** (z = −4.7, with a bend); the September–October G3X takeoffs show it as clearly as the AXIS ones. A model fitted on all 56 takeoffs is pulled by the spring and summer departures; recent takeoffs at the home field in mild conditions sit above its line. This is not a boost deficit, and on one aircraft it cannot be separated from a season or airport effect the two-feature model does not carry. It is logged as what it is: the residual has shifted, in the direction that is *not* the failure mode, and the model will be re-fitted as data accumulates.

### 7.6 Operators Manual limits — events and saturation

The limits topic owns every event. On the 58 flights, with no filters:

| Limit | Events | Flights | Excess (median / max) | Duration (median / max) | Diagnosis |
|---|---|---|---|---|---|
| Takeoff rpm 5,800 max | 101 | **55 / 58** | 20 / 100 rpm | 16 / 57 s | 3a — propeller-governor overshoot on power application |
| Fuel pressure 46 psi max | 175 | **48 / 58** | 0.9 / 4.6 psi | 139 s / 2 h 35 min | 3a — steady sender offset through climb, cruise, descent |
| Idle rpm 1,800 min | 44 | **25 / 58** | 40 / 110 rpm | 51 / 188 s | 3a — idle set 20–30 rpm low |
| Overboost (5-minute rule) | 1 | 1 / 58 | 89 s | 389 s | real (§7.4) |
| Bus voltage 11.5 V min | 2 | 2 / 58 | — | 2 s, 24 s | one 0 V reading in the first minute of an AXIS log (14 October), one 6 V reading for 2 s (9 April) — artefacts to confirm |
| The other 14 limits (temperatures, EGT maxima and split, MAP, oil pressure, fuel-pressure minimum, voltage maximum) | 0 | 0 | | | |

132 limit insights on 58 flights, unfiltered. A limit that fires on nearly every flight tells the pilot nothing about *this* flight, whatever its OM basis — the first audit found five limits firing on 23–50 of 50 flights. The diagnosis that followed (Spec 10 D6) classified each saturating limit by its fingerprint in the data and assigned responsibility:

| Cause | Fingerprint | Whose problem | Fix |
|---|---|---|---|
| 1 — limit encoded wrongly | Fires during a procedure the OM allows (every takeoff), normal values | Ours | Engine profile |
| 2 — phase or artefact gap | Fires at transitions; impossible values (0.0 V running, −0.6 psi) | Ours | Phase rule or gate |
| 3a — persistent, stable (sensor, calibration, installation) | Steady offset through steady operation, plausible values | The aircraft | Filter with a note; the change monitor watches it |
| 3b — anything else | | Unexplained | Research |

Results: fuel-pressure minimum (50/50) was cause 2, fixed by the engine-running gate; bus-voltage minimum (23/50) cause 2, the same gate; the retired 5,500 rpm "continuous" rule (49/50) cause 1; fuel-pressure maximum, idle minimum and takeoff rpm are **cause 3a on N117ZS** — the sender reads 0.9–1.6 psi high, the idle is set 20–30 rpm low (worth checking with a service centre), and the propeller governor overshoots 5,800 rpm by 10–100 rpm on power application (worth mentioning to whoever maintains the governor; the OM allows no transient overspeed and rpm is logged in 10 rpm steps, so no tolerance is applied). Each is recorded in a per-aircraft allowlist with its evidence, and the pilot handles it with a filter (§9).

Two principles came out of this and are now enforced by tests: a nominal synthetic flight following OM procedures must raise **zero** events on every profile, and no limit may fire on more than half the real flights without an allowlist entry giving its cause-3 classification; and **a limit fix must trace to the OM, Rotax documentation or sensor physics — never to clearing a test**. A limit is never removed or demoted for firing often. Both cause-3a classifications rest on one aircraft: a limit that saturates the same way on a second airframe would move to cause 1 and get a profile fix.

### 7.7 Flight facts

Shown in the flight header, never judged: fuel burned (FADEC-integrated), cruise nm/gal, mean cruise fuel flow, lane-check result. On the dataset: 508 gal over 76 airborne hours; cruise efficiency 18.9 ± 1.5 nm/gal (n = 46, 15.5–22.7); cruise fuel flow 6.40 ± 0.53 gal/h (5.5–7.5), rising with density altitude from 5.9 in the low band to 6.9 in the very-high band.

**Why these are not topics** (Spec 10 §4.2): nm/gal integrates ground speed, so a headwind looks like an efficiency loss — the dominant term is wind, not the engine; and at a given power and DA the FADEC sets fuel flow from its own map, so a blended comparison mostly reports the pilot's choice of power, and may mix the ECO and POWER maps (§4). Both were topics in Edition 0.3 (cruise efficiency "decreasing — worth watching" at the time, a trend the data could not support). A power-% × DA fuel-flow model (backlog A7) is the route back, entered as research — with the caveat that on a FADEC engine it may mostly reflect the ECU's map and be more useful for ECO/POWER inference than as a wear indicator.

**Fuel quantity sensors.** The Sling TSi's float-type tank senders are attitude-sensitive; instantaneous quantity readings are not usable for consumption. FADEC flow integration is the consumption signal, used directly and uncalibrated; tank deltas serve only as a plausibility check. Calibrating FADEC flow against pump receipts was built in an early version and deliberately removed: for an aircraft fuelled full-to-full, gallons added at the pump already equal true consumption since the previous fill, and no log-dependent step is needed.

### 7.8 Topics removed or sent to research

- **Climb thermal rate** (Edition 0.3 §6.7) — Research. The mechanism is sound (cooling capacity at high power and low airspeed, E2) and the physical effect is confirmed: oil-temperature rise rate climbs from +0.1 °F/min in gentle climbs (200–500 fpm) through +2.2 (500–1,000 fpm) to +6.2 °F/min in aggressive climbs (≥ 1,000 fpm). But within-bucket noise exceeds the effect (aggressive-climb MDC 14.8 °F/min); start-of-climb oil temperature explains almost nothing (r = −0.18). On the full set the overall rate is 1.3 ± 3.6 °F/min (n = 58, MDC 7.2). The metrics are still computed (CLI, notebooks, a context strip on the Thermal panel), no card is shown, and re-admission needs a predictor this data does not yet have — climb duration, power, OAT, or a rate over a fixed altitude band.
- **Hottest-cylinder-changed insight** — retired (D4): with cylinder 4 leading by a median 40 °F, another cylinder can only overtake it after a relative movement of ~55 °F, by which point the per-cylinder deviation insight (MDC ~10 °F) has long fired. The rank stays as context on Trends and is named in the deviation insight when it changes.
- **EGT4 elevation** — removed as redundant with the cylinder-4 deviation (D3). **Flight-phase mix** — removed; it described the mission, not the engine. **Oil/coolant ratio** — removed (§7.3). **Cruise efficiency and cruise fuel flow** — flight facts (§7.7).

---

## 8. ENGINE ECU — Classification and a Corrected Finding

The string `ENGINE ECU` appears in the CAS column of every log from the first row, before engine start, and recurs through the session. Edition 0.3 reported, after a correlation study across 23 flights, "four genuine in-flight ENGINE ECU events … consistent with intermittent CAN communication", one of them with `OIL PRESS` co-active, and recommended a B.U.D.S. fault-log read and a wiring check. **That finding is withdrawn.** The classifier behind it labelled a run IN_FLIGHT whenever it was not power-up, shutdown or a lane check; it never tested for flight. Reviewed against the raw logs, the four runs were a 1 s blip 2.5 minutes after power-on at 1,720 rpm, a 1 s blip on the ground at 1,770 rpm, a 1 s blip at 510 rpm with 2 psi oil pressure — the engine catching, which is where the `OIL PRESS` co-activity came from — and a 5 s run that was the log ending as the engine was cut. Four single-aircraft maintenance recommendations were built on a classifier defect; the register now grades the topic's E3 evidence as absent, and the help text carries no aircraft-specific wiring guidance.

### 8.1 Classification as built (Spec 01 §8.6)

Contiguous `ENGINE ECU` rows form a run; runs closer than 5 s merge; runs shorter than 3 s after merging are **sub-threshold blips**, counted for data quality but never events — at 1 Hz a single-row token is indistinguishable from a sampling artefact. Classification is by the flight phase the run overlaps, with no private rpm, IAS or voltage heuristics:

| Class | Phases | Meaning |
|---|---|---|
| GROUND_START | PRE_START, ENGINE_START, WARMUP | Avionics boot, RS-232 fallback, the engine catching. Expected. |
| LANE_CHECK | WARMUP or TAXI with the lane-check signature: rpm in the OM run-up band (4,000 ± 500 rpm on the 916iS/912iS, 2,500 on the 915iS), stationary, short, paired within 90 s | The deliberate single-lane run-up. Expected; reported as a flight fact (*both lanes ✓* / *one lane only* / *not detected*). |
| GROUND | TAXI (not a lane check), or LANDING_ROLL after stopping | Engine running on the ground, not starting, not a lane check. **An event**, with the reason it is not a lane check. |
| IN_FLIGHT | TAKEOFF_ROLL to LANDING_ROLL, **and** IAS above the taxi ceiling during the overlap | **The event that matters.** |
| GROUND_SHUTDOWN | SHUTDOWN | Expected. |

Two rules guard the phase detector's known lag at the engine cut: a run during which rpm falls below the running threshold and stays there is GROUND_SHUTDOWN whatever its phase labels say, and a run whose rows all precede the first running rpm is GROUND_START. A run in an UNKNOWN phase takes the nearest preceding phase and is flagged *phase uncertain*; and when takeoff was not detected on a flight, a GROUND run with IAS above the taxi ceiling is reported as IN_FLIGHT, uncertain, rather than silently downgraded.

### 8.2 Findings, Edition 0.4

| | 58 flights | All 117 analysed logs |
|---|---|---|
| ENGINE ECU occurrences in the CAS string | 262 | — |
| GROUND_START runs | 79 | 149 |
| LANE_CHECK runs | 97 | 103 |
| GROUND_SHUTDOWN runs | 56 | 70 |
| GROUND events | **1** | **3** |
| IN_FLIGHT events | **0** | **0** |
| Sub-threshold blips | 24 | — |
| Lane check: both / one lane / not detected | 44 / 9 / 5 | — |

The three GROUND events are all *rpm below band*: a pair on 5 October at KBVS (7 s and 8 s, 15 s apart, ~2,550 rpm, in a stationary ground run) consistent with a lane check performed well below the OM's 4,000 rpm; and 20 May (11 s, TAXI, 3,402 rpm) — the first half of a paired lane check in which rpm fell from ~4,300 to ~2,600–3,160 while the lane was off, pulling the run's mean below the band. None is a fault.

Zero in-flight events across 117 logs means the topic's positive case has never been observed. It is therefore **Admitted (provisional)**: mechanism sound (E1 for the alert's meaning), noise test passed trivially, closed by the first true positive or a deliberate injected-excerpt test. Everything that used to be a pooled "in-flight pattern analysis" with recommended actions left the engine; what remains is per-event context (rpm, IAS, co-active alerts, oil-pressure dropout) on each GROUND or IN_FLIGHT event, which is a CAS event in the same list as the limit exceedances, filterable by duration, with its own event-frequency panel on Trends. The ECU page that existed in the web UI for a while was removed when this became true: the flight header's lane-check fact and the Events table carry everything it showed.

**Lane-check adherence** — whether the pilot performed the two-lane check — is pilot procedure, not an engine signal, and is deliberately not a topic (candidate C6, awaiting a definition of a "procedure" class). **Other CAS alerts** (`FUEL PRESS` 152 occurrences, `OIL PRESS` 46, `CO PPM` 50, the avionics backup and fail annunciations) are recorded per flight but not yet classified; each one admitted through the lifecycle would become a CAS event target in the same way.

---

## 9. Limit Filters and the Change Monitor

Three limits fire on most flights of N117ZS for stable, diagnosed reasons (§7.6). The design problem is to let the pilot silence a known, consistent exceedance without the system slowly accepting a problem that is getting worse — and without the pilot learning to skim the limits card.

**A filter** is the pilot's own statement about one limit: "on my aircraft this limit is exceeded in a way I understand and accept." It is set from a limit insight, requires a note on WARNING-severity limits, and never changes the displayed limit. It carries any combination of three independent conditions, each a distinct pilot intention — an event needs only one reason to be fine:

- **magnitude** — "a little high is fine": an absolute band, a percentage, or z against the filter's frozen reference of peak excess;
- **duration** — "brief spikes are fine": a maximum event length;
- **phase** — "this happens on the ground, and that's fine": an event lying wholly within listed phases is suppressed; one that touches any other phase is judged by the other conditions. Per limit only — a workspace-wide phase exclusion would hide an oil-pressure loss while taxiing.

Filtered events are suppressed, not deleted: they collapse into one informational line per limit, expandable to the events. A breach — an event no condition tolerates — is reported at the limit's normal severity, marked *beyond your filter*. The oil-pressure minimum stays unfilterable. Filters apply retroactively to every flight and travel with a workspace export.

**The change monitor** is what makes a filter safe. Every filter freezes a reference — the membership of the most recent included flights at creation, its statistics recomputed from current analyses — and watches the limit's per-flight metrics (peak excess, time above the limit as a share of engine-running time, share of flights with an event) on every later flight, excluded-phase events included. Statuses in priority order: **Breached**, **Drifting** (two consecutive flights more than z above the frozen mean in the worsening direction, or the share of flights with events up by 30 points over the last ten), **Review due** (engine hours since the last review exceed the limit's interval), **Quiet** (no events on recent flights — the filter may no longer be needed), **Collecting**, **Stable**. The pilot's own baseline keeps learning as the engine ages; the filter's reference does not, because a filter that kept learning would accept a worsening problem.

The baseline and the filter answer different questions and work together: a filter hides known exceedances; it does not switch off the baseline. A pilot who filters fuel-pressure maximum because the sender reads high still gets a *watch* insight on a flight whose pressure is unusual *for this engine*.

---

## 10. Trends — Is My Engine Changing?

The Flight view asks whether one flight was unusual; a single unusual flight can be weather, a long taxi, a short hop. A metric that has *shifted* — whose recent average sits somewhere different from where it used to — is a change in the engine or its installation, and can be small enough that no single flight was ever flagged. Trends was rebuilt in October 2026 from a metric picker into a change page (Spec 12) that finds the second kind.

**The change statistic.** The **recent window** is the newest flights spanning at least 10 engine hours with at least 5 flights, capped at 15 (wear tracks hours; statistical power tracks flight count; 10 h is about a month for an active private pilot). For each metric, **shift** is the recent window's mean against the reference, in standard errors — stratified per band where the metric has one, with the same n_min fallback as the insights — and a metric enters the summary when |shift z| ≥ 2.0, the same number as everywhere else. **Bend** (the recent slope differs from the reference slope by more than two standard errors, in the worsening direction) is a qualifier, never a ranking key. A **level crossing** — the recent mean has used up three quarters of the headroom to an OM limit, or crossed the edge of a filter band — outranks every shift. For limit and CAS panels **event frequency** (share of flights with an event, recent vs reference, qualifying at +30 points) is the primary signal, because peak excess exists only on flights that went over and cannot say "this used to happen once a year and now it is every flight".

**Reference: rolling or pinned.** The reference rolls by default. A pilot can pin a metric's reference to the flights in the current zoom — the twenty flights before an injector change — and every later flight is compared with that set until unpinned; pins are visible on every strip, listed in the Journal, and unpinning never rewrites the shift history.

**The change summary on N117ZS, 20 October 2026** (58 flights; recent window 12 flights, 111.9–122.2 h; rolling reference):

| Rank | Metric | Direction | Shift z | Reading |
|---|---|---|---|---|
| 1 | Takeoff-MAP model residual | more boost than predicted | −4.7, bend | §7.5 — the model lags the recent takeoffs; not the failure direction |
| 2 | EGT spread | wider, 65.1 vs 60.3 °F | +3.7, bend | §7.2 — the one engine-level change to watch |
| 3 | Cylinder balance (cyl 4 leads; cyl 2 member) | cyl 4 hotter relative to the others | +3.3, bend | §7.2 — the cylinder carrying the spread change |
| 4 | Oil temperature peak | lower, 192.7 vs 201.1 °F | −2.9, bend | §7.3 — shorter recent flights |
| 5 | Coolant temperature peak | lower, 176.3 vs 180.8 °F | −2.9 | §7.3 — shorter recent flights |
| 6 | Cruise efficiency (planning panel) | lower | −2.1, bend | wind, weight, short cruises |

Nothing has crossed an OM margin line; no limit's event frequency has qualified; the ENGINE ECU panel reads *rare*. The summary is doing what it was built to do — surfacing the spread change weeks before any single flight would trip the trend gate — and also showing what it cannot yet do: two of the six rows are explained by flight duration rather than the engine, which is the case for the condition strip (T3) and the maintenance annotations (T2) planned for the next version.

---

## 11. The Software — SlingologyEIS 1.0.1

The toolkit of Edition 0.3 (four scripts, a CSV of fleet metrics) became an application between September and October 2026. It is described here only as far as it bears on the research: how the analysis is run, where the data lives, and what is reproducible.

**One engine, three hosts.** The analysis engine (`slingology_eis`, pure Python on pandas and numpy; `operations.py` is the contract: `analyze_flight`, `update_fleet`, `evaluate_insights`, filters, trends) is stateless — bytes in, typed results out, validated against JSON schemas. Around it sit a command-line interface, a local HTTP server with a React web UI (`slingology-eis serve`, listening only on 127.0.0.1), and — since 1.0.1 — a browser host: the same Python engine runs inside the browser under Pyodide in a Web Worker, from a static site, with the workspace in the browser's origin-private file system and the logs read from a folder the pilot points at. Both modes produce byte-identical analyses on the 120-log test set (58 flight analyses and the export documents compared); the in-browser heap peaked at 277 MB and a rule-edit preview takes about 180 ms. Every operation that reads raw logs is a resumable coroutine that pauses on a file request the page fulfils, so the server, the CLI and the browser share one scan.

**Workspaces.** Logs stay in the pilot's own folders and are never copied or uploaded; a workspace holds derived results only (per-flight analyses, the reference, rules, filters, notes, the Journal) and references its log folders, re-matching renamed or moved logs by fingerprint. Any number of workspaces, one active at a time — another aircraft, or an experiment on a subset of logs organised in the pilot's own file system. The engine model is fixed per workspace, which is what guarantees a filter can never apply to the wrong engine. A workspace with more than one tail number is told so; one aircraft per workspace is the recommendation until fleet workspaces (engine-type insights across many aircraft) are designed.

**Decisions are first-class.** Everything a pilot decides — a filter, a rule edit, a disabled topic, a flight excluded from the reference, a pinned reference, a changed setting, a note — is a Journal entry with its scope (*this flight only* / *all flights in this workspace*), its live effect (*changes the verdict on N other flights*), and a notice when its basis has moved. Rule edits are made on the topic card with a preview of the effect across the whole workspace before applying. A workspace export carries the decisions and a flight manifest (never analyses), optionally the logs in a zip, optionally anonymised; the recipient imports it, points at the logs and re-analyses to see the same screens — the route by which another pilot's 916iS data would reach this research.

**Reproducibility.** The private log set (`AlchemyGeek/EIS-Test-Data`, 120 files) is the test oracle: characterization goldens, contract tests that assert on the set's counts, the nominal-flight and saturation tests of §7.6, and the phase-regression snapshot tool. 910 Python tests and 198 web tests at 1.0.1; the operations tests run in-process, over HTTP and under Pyodide in Node.js. Every number in §§7–10 was produced by `slingology-eis import` and `slingology-eis fleet` on that set with the 1.0.1 engine, followed by `evaluate_insights` with the shipped rules and no filters.

**Where things are.** Repository: https://github.com/AlchemyGeek/Rotax9iSEIS (MIT). Hosted in-browser app: https://alchemygeek.github.io/Rotax9iSEIS/app/. Pilot documentation (concept pages, walkthroughs, OM limits by engine): https://alchemygeek.github.io/Rotax9iSEIS/. Design: specifications 01–15 under `docs/specs/`, one per behaviour, each with its revision history; the topic register at `docs/specs/topics/register.json`; engine profiles under `engines/`; shipped trigger rules in `insight_rules.json` (v1.8). `CHANGELOG.md` records every engine version and what a stored analysis's `engine_version` meant.

---

## 12. Competitive Landscape

| Platform | Strengths | Gaps for a Rotax iS |
|---|---|---|
| Savvy Aviation | Largest GA engine dataset, human analysts, FEVA exhaust-valve detection, ML research | Built for pilot-mixture engines; FEVA and ROP/LOP inapplicable to FADEC; no Rotax-specific models; subscription |
| FlySto | Excellent Garmin import, 3D replay, approach scoring, free tier | Raw engine graphs only; no engine-health model, no FADEC analytics, no trend detection |
| B.U.D.S. (Rotax) | Full ECU fault access, both lanes, injector and ignition data | Hardware interface, maintenance-interval use, no flight-log integration, no trends |
| SlingologyEIS 1.0.1 | FADEC-native topics with written admission criteria; OM limits with phase awareness; per-aircraft reference with stratification; filters with a change monitor; a Trends change page; a Journal of decisions; three Garmin log formats; runs in the browser with no upload; free, open source, documented | Validated on one aircraft; no borescope or maintenance-record integration; no human analyst; ECO/POWER mode not detectable |

---

## 13. Open Questions and Research Agenda

### 13.1 Engine and FADEC behaviour

- **EGT spread widening** — the first engine-level change surfaced by Trends (§7.2): +5 °F in the last twelve flights, carried by cylinder 4, visible on G3X and AXIS logs alike. Watch over the next ten flights; if it persists, cylinder 4's injector and probe are where a mechanic would look.
- **Takeoff-MAP residual** — the recent takeoffs make 0.8 inHg more boost than the model predicts (§7.5). Re-fit as data accumulates; a season or airport term is the obvious candidate if it persists. Altitude diversity remains thin (backlog A10).
- **ECO/POWER mode detection** — open, blocked on a known-throttle test flight (A8).
- **Oil below the optimal band 91 % of the time** — a candidate topic with an E1 basis (C1); the action is operational (longer warm-up, cowl-flap or oil-thermostat settings) and installation-specific.
- **Climb thermal rate** — research; needs a predictor beyond VS bucket and starting temperature (A5).
- **Peak temperature vs flight length** — predict the expected peak from airborne time and OAT (A6).
- **Oil–coolant balance (C5)** — is the relationship used as a health indicator anywhere in Rotax or engine-monitoring practice, and what is the sourced mechanism?
- **Fuel-pressure sender offset on N117ZS** — root cause with a mechanic (E2); separating pump cycling from sensor and regulator behaviour would need a pump-state inference from the pressure signature (A9).

### 13.2 CAS and avionics

- **ENGINE ECU in flight** — positive case never seen; a deliberate injected-excerpt test would close the provisional status (A2).
- **AXIS** — the alert naming and lane-check capture are now confirmed on five logs (§2.1); still open: whether `onGroundState` should feed phase detection once the reference is AXIS-dominated, the 0 V bus-voltage reading at the start of the 14 October AXIS log, and whether the takeoff-MAP capture window behaves identically on resampled logs (S4).
- **Other CAS alerts** — `FUEL PRESS`, `OIL PRESS`, `CO PPM` and the avionics annunciations are recorded but unclassified; each is a candidate CAS event target.

### 13.3 Data and analytics

- **Single-aircraft evidence** — every E3 grade and every cause-3a classification rests on N117ZS. The practical path to a second 916iS is other pilots' logs through workspace export/import, and fleet workspaces for engine-type insights (A1, U5).
- **Trends v2** — OM headroom projection, maintenance annotations on the time axis, a condition strip under each panel, change-point detection (CUSUM) as a research-mode first (T1–T4).
- **Research mode** — reviewing a metric outside expected thresholds over many flights and a path from a research finding to the operational side (Spec 06, reserved).
- **Engine hours as the x-axis** — the log header's hours are the Hobbs at log creation; compare with cumulative airborne hours derived from the logs (T5).
- **Band granularity** — 48 of 55 cruise flights fall in one OAT band; whether the bands should be re-cut once data from other climates exists is open.

---

## 14. Revision History

| Version | Date | Changes |
|---|---|---|
| 0.1 | June 2026 | Initial edition. Operating limits from OM. Data architecture documented. Analytics modules defined. First flight log analysed (N117ZS, 18 May 2026). ENGINE ECU investigation initiated. |
| 0.2 | June 2026 | ENGINE ECU classified as expected behaviour (POWERUP/LANE_CHECK/SHUTDOWN). Second log format (Garmin Pilot export). Fuel-flow calibration explored, built, then descoped. Climb-rate-correlated thermal analysis and DA/OAT normalisation approach added. `fleet.py` baselines/trends/outliers. |
| 0.3 | July 2026 | Registration corrected to N117ZS. 23 flights from 50 logs. EGT findings (spread 56.4 ± 5.1 °F, EGT4 +44.7 °F), one overboost exceedance (381 s), empirical MAP model (n = 15, R² 0.71), climb thermal findings, "four in-flight ENGINE ECU events", DA/OAT implementation status, toolkit v0.10.0 (script 04, two-layer format, insight rules). |
| 0.4 | October 2026 | **Dataset:** 58 flights from 120 logs (59 ground sessions skipped at admission, 3 duplicates collapsed), 28.2–122.2 engine hours, 76 airborne hours; Garmin AXIS added as a third log source with 1-second resampling (§2). **Corrections:** §8 — Edition 0.3's four in-flight ENGINE ECU events withdrawn as a classifier defect; the phase-based classifier finds 0 in-flight and 3 ground events in 117 logs. **Topics (§7):** written admission criteria and the register; oil/coolant ratio, EGT4 elevation, flight-phase mix removed; climb thermal rate to research; cruise efficiency and cruise fuel flow to flight facts; hottest-cylinder-changed insight retired; learned hottest cylinder. **Limits (§3, §7.6):** phase-aware event rules, the 30 s merge gap, overboost as single owner of the five-minute rule, the saturation diagnosis and per-aircraft allowlist, the "fixes trace to the OM" principle. **Reference (§6):** leave-one-out, n_min, one z-threshold, stratified insight comparison. **New sections:** limit filters and the change monitor (§9), Trends as a change page with the current change summary (§10), the application and its reproducibility (§11). **Findings updated:** spread 60.3 ± 5.5 °F rising 0.12 °F/h (R² 0.42) with a +5 °F recent shift carried by cylinder 4; cylinder 4 hottest 58/58; oil 201 ± 12 °F and coolant 181 ± 7 °F peaks, duration-driven (r = 0.66), no exceedances; overboost 389 s and one close call; MAP model n = 56, R² 0.64, tolerance from leave-one-out residuals, recent residual shift; three saturating limits diagnosed as aircraft-specific. Open questions rewritten against the 1.0.1 backlog. |

---

*Slingology EIS Research  •  N117ZS  •  KAWO  •  Living document — update with each analytical finding*

*Edition 0.4 — October 2026 — draft for review*
