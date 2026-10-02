# Spec 10 — Analytics Topic Admission & Register

**Project:** SlingologyEIS
**Status:** Draft v0.3 — for review (no code written). Q1(a) and Q4 decided (§4.1, §4.2); overboost reporting moved to `limit_exceedances` (Spec 09 v0.12); §6's other findings are still proposals, none acted on until decided.
**Suggested repo path:** `docs/specs/10-analytics-topic-admission.md`
**Builds on:** Spec 01 (§8.5 TopicResult/Insight, §9 extension model), Spec 03 (principle 6: the Explore → operational path), Spec 08 (cylinder balance — the first topic spec, §9), Spec 09 (filters on topic threshold insights), research paper Edition 0.3
**Baseline reviewed:** branch `webui` at commit `fee6577` (2026-10-01), engine 0.21.0; `insight_rules.json` v1.3; `engines/916iS.json`
**Audit data:** the project's `fleet_metrics.csv` snapshot — 50 sessions, 23–24 real flights with thermal/EGT data, 12 with cruise data, 2026-04-08 → 2026-06-18, 28.2–66.3 engine hours. Every number in §6 and Appendix A is to be re-run on the full local log set before v0.2 (§11, acceptance 3).

**Revision history**

| Version | Change |
|---|---|
| 0.1 | Initial draft. Admission criteria, register schema, first audit of every current topic, coverage view, lifecycle, topic-spec template. |
| 0.2 | **Q1(a) decided — Option A:** `limit_exceedances` owns every OM-limit event; a topic that references a limit shows it (analysis line, link, mirrored badge) but never emits a second insight for it (new §4.1). **Q4 decided — Option B:** the topic set is for the engine; planning numbers (cruise nm/gal, cruise fuel flow, fuel burned) move to a flight-summary line with no insights, and the power × DA fuel-flow model (BACKLOG A5) becomes a Research item (new §4.2). Register, audit, outcomes, coverage view and acceptance updated to match. The "verify overboost overlap" item is closed: overboost is not checked by `limit_exceedances` (`report_in_exceedances: false`), so `overboost_time` is its only reporter and there is no duplicate. Q1(b) stays open. |
| 0.3 | **Overboost exception removed (Spec 09 v0.12).** Overboost is now the single owner of the OM 5-minute takeoff rule and is reported by `limit_exceedances` as an ordinary event (`report_in_exceedances: true`, blocks built with the 30 s merge gap); `rpm_continuous_max` is retired. The v0.2 reasoning that closed "verify overboost overlap" — overboost is not checked by `limit_exceedances`, so `overboost_time` is its single reporter — no longer holds. Overboost becomes an ordinary §4.1 case: `limit_exceedances` owns the event, and `overboost_time` references it (analysis line, link, mirrored badge) and keeps its close-call insight. §4.1, register, audit, outcome, coverage and acceptance 3 updated. |

---

## 1. Purpose

SlingologyEIS shows a pilot a fixed set of analytics topics on every flight. That set grew bottom-up: modules were built where gaps were found, then collected into "the 14 agreed topics" when the two-layer Analysis/Insight format was designed (BACKLOG A1/A2). No document says why each topic exists, what evidence it rests on, or what a new one has to show to join.

This spec supplies that, for two reasons:

1. **Defensibility.** Every topic a pilot sees should answer, on the record: what engine question does it ask, what physical mechanism or operating practice is behind it, what is it compared against, and why is it worth a card on every flight? A topic that can't answer these shouldn't be shown — it costs the pilot attention and erodes trust in the ones that matter.
2. **Growth.** The set is expected to grow — through research (Spec 03's future Explore mode, experiment workspaces) and eventually through suggestions from other Rotax iS owners. Growth needs one bar that a researcher's finding and a community proposal both have to clear, so the set doesn't drift by accretion.

It does three things the current documents don't: states the **admission criteria** (§4), keeps a **register** of every topic against them (§5, audited in §6), and defines the **lifecycle** from proposal to retirement (§8).

## 2. Scope and boundaries

| This spec owns | Owned elsewhere |
|---|---|
| Whether a topic should exist, and why | **How** a topic plugs in — metrics, compute function, conditions, view hints: Spec 01 §9 |
| The evidence a topic needs at each lifecycle stage | **Findings** — what the data showed, with numbers and narrative: the research paper |
| The register: one entry per topic, current and retired | **Tuned values** — thresholds, `n_min`, `r2_min`, severities: `insight_rules.json` and the engine profiles |
| What a topic spec must contain | **One topic's full design**: its topic spec (§9), e.g. Spec 08 |
| | **Limit filters and change monitoring** on top of topics: Spec 09 |

**Non-goals:** designing Explore mode (Spec 06, reserved); the mechanics of community submission and sharing (deferred — §10 defines only what a proposal must contain); changing any threshold. This spec judges topics; it doesn't tune them.

## 3. Definitions

- **Topic** — one engine-health or engine-operation question asked of every flight, producing the two-layer output of Spec 01 §8.5: an always-present analysis line and zero or more conditional insights. Identified by `topic_id`, which is also its rule id in `insight_rules.json`.
- **Metric** — a per-flight number a topic reads (Spec 01 §6.4 registry). Several topics can share a metric; a topic can read several.
- **Anchor** — what the flight's value is compared against. Four kinds:
  - **OM limit** — a number from the engine's Operators Manual (engine profile `limits`, or computed limits like EGT split and overboost).
  - **Personal baseline** — the aircraft's own history: leave-one-out mean/SD, optionally within a weather band (Spec 01 §8.4, R8), and/or an engine-hours trend.
  - **Empirical model** — a fitted relationship from the aircraft's own data (e.g. takeoff MAP from pressure altitude and OAT).
  - **Classification** — a rule that sorts events into expected vs. not (e.g. ENGINE ECU POWERUP/LANE_CHECK/SHUTDOWN/IN_FLIGHT; learned hottest cylinder).
- **Minimum detectable change (MDC)** — for a baseline anchor, the smallest change in the metric the trigger can separate from flight-to-flight noise: `z × SD` of the metric across comparable flights (default `outlier_z_threshold` = 2.0, so MDC ≈ 2 SD).
- **Topic spec** — the document that justifies and designs one topic (§9).
- **Register** — the table of every topic, past and present, with its standing against the criteria (§5).

## 4. Admission criteria

A topic is admitted when it meets all seven. Each criterion has a test and says what counts as passing.

| # | Criterion | Test | Passing evidence |
|---|---|---|---|
| **A1** | **Observable** | Every input channel is in the standard G3X EIS log, and the phases it needs occur on a typical flight. | Channel list from the registry; **availability** = share of real flights that produce a value. A topic that needs data the G3X doesn't log (throttle position, lane status, injector data, T_plenum — research paper §2.3) can't be admitted, however good the idea. Low availability (e.g. cruise-only metrics) is allowed but must be stated. |
| **A2** | **FADEC-relevant** | The question still means something when the ECU controls mixture, injection and ignition. | A sentence on why. Rules out pilot-mixture analytics (ROP/LOP, peak-EGT finding, FEVA) and anything that assumes CHT where the 9xiS has coolant. |
| **A3** | **Anchored** | At least one anchor (§3) exists, and the analysis line states it. | The anchor named, and its source: OM chapter, baseline config, model definition, or classification rule. |
| **A4** | **Mechanism** | The topic names what it detects — a physical failure or degradation, or an operating practice the pilot controls — and grades the evidence for that link. | Evidence grade, at least one of: **E1** manufacturer (OM, service documents) · **E2** established engineering practice or literature · **E3** observed in this project's data · **E4** hypothesis. **Admission needs E1 or E2 for the mechanism.** E3 alone shows a pattern exists, not what it means; E4 alone keeps a topic in Research. |
| **A5** | **Actionable** | A pilot or mechanic does something different when it fires. | The action named: change a habit (throttle discipline), watch (trend review), inspect (named components), or ground (limit). "Interesting" is not an action. |
| **A6** | **Distinct** | No other topic or limit check fires on the same signal; where two overlap, the register says which one owns which part. | An overlap statement in the register entry. Two cards for one event is a defect, not reinforcement. |
| **A7** | **Discriminating** | For baseline and model anchors: the metric is stable enough across comparable flights that the trigger can catch the change the mechanism implies. | Measured SD and MDC on the aircraft's data, within the comparison scope actually used (all flights, a weather band, a VS bucket…), set against the size of change the mechanism would produce. If MDC is larger than that change, the topic needs conditioning (stratify, bucket, normalize) before admission. Automatically met for OM-limit and classification anchors. |

Two classes of topic go through the same gate:

- **Health topics** detect a change in the engine (A4 names a degradation mechanism).
- **Operational topics** report something the pilot controls that the OM limits or that affects the engine (A4 names the practice: overboost time, oil-temperature condensation). An operational topic must still pass A5 — the pilot must be able to do something about it.

A number that informs flight planning but says nothing about the engine (range, efficiency, fuel burned) is **not a topic** — see §4.2.

### 4.1 Ownership of OM-limit events (Q1(a), decided v0.2)

Every OM-limit exceedance is reported **once**, by `limit_exceedances` — one insight per limit per flight, carrying its events (Spec 09 §10.1). It owns the event's severity, evidence, filter (Spec 09) and annotations.

A topic that references a limit (through a threshold trigger's `limit_ref` — today `oil_temp_peak` and `coolant_temp_peak`) **does not emit an insight for it**. Instead:

- its analysis line states the exceedance and names the limit ("Exceeded OM limit (248 °F) — see Limit exceedances");
- its card links to the `limit_exceedances` insight for that limit;
- its card **displays** that insight's severity badge, so the Analysis grid still shows at a glance which topic the problem belongs to. The badge is mirrored, not a second insight: the insight list, its counts, filters and annotations see exactly one.

The topic keeps everything only it can do — baseline and trend triggers against the aircraft's own history.

**Overboost is not an exception (v0.3).** Until v0.3, overboost was checked only by `overboost_time` (`report_in_exceedances: false`) and this section made it an exception. Spec 09 v0.12 moves it into `limit_exceedances` as an ordinary event, one per block past the 300 s limit, so it follows the same rule as every other limit: `limit_exceedances` owns the event and `overboost_time` references it. The topic keeps the close call — a block near the limit is not an OM exceedance, so only the topic can report it. The 5,800 rpm ceiling (`rpm_takeoff_max`) is an ordinary limit owned by `limit_exceedances`.

**Follow-ups this decision creates** (not made by this spec): for overboost, done in Spec 09 v0.12 (§6.4, §10.3); Spec 09 §10.2 — topic threshold triggers become display-only references; Spec 03 §5.2 — the mirrored badge on topic cards; `insight_rules.json` — the `threshold` triggers on `oil_temp_peak` / `coolant_temp_peak` keep only their `limit_ref` for the reference, or move to a non-trigger field.

### 4.2 Planning numbers are not topics (Q4, decided v0.2)

A topic is about the engine: a health topic detects a change in it, an operational topic reports a pilot-controlled practice the OM limits or that affects it. Numbers whose main drivers are outside the engine — wind, load, the pilot's choice of power — are context, not topics. They appear in a **flight-summary line** (alongside duration and airborne time): fuel burned, cruise nm/gal, mean cruise fuel flow. They raise no insights and no trend alerts, and they don't appear in the Analysis grid.

They can come back as a topic only through the lifecycle (§8), with a definition that isolates an engine signal. The candidate route is BACKLOG A5's fuel-flow model (power % × density altitude), entered as **Research**. Its payoff is uncertain: on a FADEC engine both fuel flow and power % are ECU-computed, so the model may mostly reflect the ECU's map. That makes it more promising as an input to ECO/POWER inference (BACKLOG A4) than as a wear indicator — which the research has to show either way.

## 5. The register

### 5.1 Entry schema

One entry per topic, current or retired. Fields:

| Field | Content |
|---|---|
| `topic_id` | Rule id |
| Question | The plain-language question, as a pilot would ask it |
| Class | health · operational |
| Mechanism (A4) | What it detects, with evidence grade(s) and source |
| Anchors (A3) | Kind(s) and source |
| Inputs (A1) | Metrics, channels, phases; availability |
| Noise (A7) | SD and MDC in the comparison scope used; or "n/a (limit/classification)" |
| Owns / defers (A6) | What signal it owns; what it leaves to another topic or limit |
| Action (A5) | What the pilot/mechanic does |
| Severity defaults | From `insight_rules.json`, for reference only |
| Status | §8.1 |
| Topic spec | Link, or "none — written before this spec" |
| History | Admitted / changed / deprecated, with version and reason |

### 5.2 Register (v0.1)

Status is the **current** state. §6 gives the audit verdict and proposed status change for each.

| `topic_id` | Question | Class | Anchors | Status today |
|---|---|---|---|---|
| `egt_spread` | Are my cylinders burning evenly? | health | OM limit (EGT split, via `limit_exceedances`) · baseline · trend | Admitted |
| `egt_cyl_deviation` | Is any one cylinder drifting from the others? | health | baseline · trend, per cylinder | Admitted (Spec 08) |
| `cylinder_rank` | Has the usually-hottest cylinder changed? | health | classification (learned hottest cylinder) | Admitted (Spec 08) |
| `oil_temp_peak` | Did oil get too hot, or hotter than usual? | health + operational | OM limit (referenced, §4.1) · baseline | Admitted |
| `coolant_temp_peak` | Did coolant get too hot, or hotter than usual? | health | OM limit (referenced, §4.1) · baseline | Admitted |
| `oil_coolant_ratio` | Has the oil-vs-coolant balance shifted? | health | baseline | Admitted |
| `overboost_time` | Did I stay at takeoff power too long? | operational | OM limit (referenced, §4.1: 300 s above 5,500 rpm / 100 %) · close-call margin | Admitted |
| `cruise_efficiency` | How far am I going per gallon in cruise? | planning (§4.2) | baseline · trend, DA band | Admitted — to leave the topic set (Q4) |
| `cruise_fuel_flow` | Is cruise fuel burn normal? | planning (§4.2) | baseline, DA band | Admitted — to leave the topic set (Q4) |
| `map_at_takeoff` | Is the turbo making expected boost at takeoff? | health | empirical model (MAP ~ PA, OAT) | Admitted |
| `engine_ecu_inflight` | Did the FADEC report a fault in flight? | health | classification (cas.py) | Admitted |
| `limit_exceedances` | Did anything go outside an OM limit? | health + operational | OM limits (all, overboost included since v0.3, §4.1) | Admitted — owner of limit events |
| `climb_thermal_rate` | Did the engine heat up faster than usual in climb? | health | baseline | Admitted |
| `egt4_elevation` | (superseded by `egt_cyl_deviation` cylinder 4) | — | — | Deprecated in engine 0.14.0 (Spec 08); rule `enabled: false` |
| `flight_phase_mix` | Was this flight's climb/cruise/descent split unusual? | — | — | Dropped as a topic in toolkit v0.10.0 (replaced by the "no cruise detected" header note) |

## 6. Audit of the current topics (v0.1)

Each topic was checked against A1–A7 using the code at `fee6577`, the research paper, and the data snapshot named in the header. ✓ passes · ◐ passes with a stated condition · ✗ fails.

| `topic_id` | A1 | A2 | A3 | A4 | A5 | A6 | A7 | Verdict |
|---|---|---|---|---|---|---|---|---|
| `egt_spread` | ✓ | ✓ | ✓ | ✓ E1+E2 | ✓ | ◐ | ✓ | Keep; declare overlap |
| `egt_cyl_deviation` | ✓ | ✓ | ✓ | ✓ E2+E3 | ✓ | ◐ | ✓ | Keep |
| `cylinder_rank` | ✓ | ✓ | ✓ | ✓ E2 | ✓ | ✓ | n/a | Keep, provisional |
| `oil_temp_peak` | ✓ | ✓ | ✓ | ✓ E1 | ✓ | ✗ → ✓ by §4.1 | ◐ | Keep; drop its limit insight (§4.1) |
| `coolant_temp_peak` | ✓ | ✓ | ✓ | ✓ E1 | ✓ | ✗ → ✓ by §4.1 | ◐ | Keep; drop its limit insight (§4.1) |
| `oil_coolant_ratio` | ✓ | ✓ | ✓ | ✗ E4 | ◐ | ✓ | ? | Redefine, then re-audit |
| `overboost_time` | ✓ | ✓ | ✓ | ✓ E1 | ✓ | ✓ | n/a | Keep; references the `limit_exceedances` event, keeps the close call (§4.1, v0.3) |
| `cruise_efficiency` | ✓ | ◐ | ✓ | ✗ | ◐ | ◐ | ◐ | Move to flight summary (§4.2) |
| `cruise_fuel_flow` | ✓ | ◐ | ✓ | ✗ | ◐ | ✓ | ◐ | Move to flight summary (§4.2); A5 model to Research |
| `map_at_takeoff` | ✓ | ✓ | ✓ | ✓ E1+E3 | ✓ | ✓ | ◐ | Keep, provisional; fix config |
| `engine_ecu_inflight` | ✓ | ✓ | ✓ | ✓ E1+E3 | ✓ | ✓ | n/a | Keep |
| `limit_exceedances` | ✓ | ✓ | ✓ | ✓ E1 | ✓ | owner | n/a | Keep; owner of limit events |
| `climb_thermal_rate` | ✓ | ✓ | ✓ | ✓ E2 | ◐ | ✓ | ✗ | Move to Research |
| `egt4_elevation` | — | — | — | — | — | ✗ | — | Remove (overdue) |
| `flight_phase_mix` | — | — | — | ✗ | ✗ | — | — | Remove leftover rule |

### 6.1 Findings, topic by topic

**`egt_spread` — keep; declare overlap.** EGT split is an OM limit (392 °F above 3 L/h fuel flow, OM Chapter 2.1), checked as an exceedance by `limit_exceedances`; the topic's own triggers are baseline and trend. Mechanism: a widening spread within limits points to an injector or ignition imbalance (E2; research paper §6.1). Data: cruise mean 56.4 ± 5.1 °F, MDC ≈ 10 °F — discriminating. Trend +0.22 °F/hr, R² 0.30, below the 0.5 gate (E3, not yet confirmed). Overlap: spread (max − min) and `egt_cyl_deviation` respond to the same imbalance. Proposed ownership: `egt_spread` owns *overall balance against the OM split limit and its trend*; `egt_cyl_deviation` owns *attribution to a cylinder*. Whether `egt_spread`'s baseline-deviation trigger is still needed alongside four per-cylinder triggers is Q1(b).

**`egt_cyl_deviation` — keep.** Admitted through Spec 08, which already reads as a topic spec. Cylinder 4 at +44.7 ± 5.3 °F, MDC ≈ 11 °F. Mechanism: lean cylinder runs hot (injector), cooler cylinder points to ignition or plug, erratic reading points to the probe (E2, Spec 08 §1).

**`cylinder_rank` — keep, provisional.** Classification against the learned hottest cylinder, needing a ≥ 15 °F margin on 2 consecutive flights. The mechanism is sound (E2), but the positive case has never been seen: the hottest cylinder was stable on 23/23 flights. Provisional until a true positive, or a deliberate test (§8.1), shows the 15 °F / 2-flight rule fires when it should and not otherwise.

**`oil_temp_peak`, `coolant_temp_peak` — keep; remove the duplicate.** OM limit 248 °F for both (E1). Since Spec 09 §10.2, each topic's threshold trigger fires *exactly when* `limit_exceedances` has an unsuppressed event for `oil_temp_max` / `coolant_temp_max` — so one exceedance produces two `limit`-severity insights. That fails A6. **Decided (§4.1):** `limit_exceedances` owns limit events; the peak topics keep their baseline triggers and *reference* the limit — analysis line, link, mirrored badge — but no longer emit a second limit insight. A7 needs a re-run: the snapshot's peak-temperature SDs (31 °F oil, 26 °F coolant) are much wider than the paper's (12 °F, 7 °F), probably because short or cold-day flights are in the snapshot. Both metrics are OAT-stratifiable; the re-run should report MDC within OAT bands.
*Gap:* the original topic 4 included "% time below the 194 °F/90 °C optimal band". The metric `oil_temp_below_optimal_pct` is computed (snapshot mean 91 %) but no topic surfaces it. It has an E1 basis (OM guidance on reaching operating temperature to drive off condensation) and a clear action. Listed as a candidate in §7.

**`oil_coolant_ratio` — redefine, then re-audit.** Two problems.
1. It is `oil_max_°F / coolant_max_°F` (`fleet.py`). A ratio of temperatures on an interval scale has no physical meaning: the same flight gives a different ratio in °C, and an equal rise in both temperatures moves the ratio. The two peaks can also occur at different moments.
2. The mechanism — "a signature of thermal health" (research paper §6.5) — is unsourced (E4). Its very low CV (0.04) reflects the ratio compressing the data, not a stable signal.

Proposal: redefine as a temperature **difference** (oil − coolant), measured simultaneously in a stable phase (cruise mean, or peak-time-aligned). State the mechanism: oil cooler effectiveness vs. coolant radiator effectiveness — a blocked oil cooler raises the difference, a coolant-side problem lowers it. Grade it E2 or demote to Research.

**`overboost_time` — keep.** OM: 5,500 rpm maximum continuous, 5,800 rpm takeoff limited to 5 minutes (E1). Time above 5,500 rpm or 100 % power is therefore the time-limited regime. Operational class, direct action (throttle back after takeoff). One exceedance in the snapshot (381 s, ATC delay), two flights ≥ 240 s. Since v0.3 (Spec 09 v0.12) a block past the limit is a `limit_exceedances` event; the topic references it (§4.1) and keeps what only it can report — the close call and the time-in-regime context. Overboost also replaced `rpm_continuous_max`, which raised a CAUTION on every takeoff because it had no time allowance.

**`cruise_efficiency` — move to the flight summary (§4.2).** nmpg integrates **ground speed** (`fuel.py`), so a headwind looks like an efficiency loss — the dominant term is wind, not the engine (fails A4 as a health topic). FADEC fuel flow is model-based, ±10 % (OM). A DA band reduces but doesn't remove the confounders: power setting, wind, weight. Its "decreasing — worth watching" trend implies engine degradation that the data can't support. **Decided (§4.2):** cruise nm/gal becomes a flight-summary number with no insights. A true-airspeed, matched-power redefinition is possible later through the lifecycle, but isn't proposed now.

**`cruise_fuel_flow` — move to the flight summary (§4.2).** At a given power and DA the FADEC sets fuel flow from its own map, so the comparison only means something within a power band. Blended across power settings it mostly reports the pilot's choice of power. SD 0.5 gph (CV 0.08) looks discriminating but mixes power settings. **Decided (§4.2):** mean cruise fuel flow becomes a flight-summary number. The comparison within power-% × DA bands (BACKLOG A5's model) is entered as Research, with the caveat in §4.2 that on a FADEC engine it may mainly reflect the ECU's own map.

**`map_at_takeoff` — keep, provisional; fix the config.** Mechanism: under-boost at full power points to turbo, wastegate or intake problems (E1 — OM reference MAP and air-supply guidance per BACKLOG A3; chapter to be cited in the topic spec). Data: empirical model R² 0.71, n 15 (E3). Two problems:
1. `insight_rules.json` says `vs_om_expected` with `tolerance_hpa: 20`, but the code compares against the *personal model* with a hard-coded ±1.5 inHg (≈ 51 hPa). The configured tolerance is never read, and the condition name describes a comparison the code doesn't make.
2. Nearly all departures are near sea level (KPAE), so the model's altitude term is barely constrained (BACKLOG A6).

Provisional until the rule reflects what's computed and the model has altitude diversity.

**`engine_ecu_inflight` — keep.** A classification anchor that separates expected FADEC behaviour (POWERUP, LANE_CHECK, SHUTDOWN) from IN_FLIGHT events (E1 for the alert's meaning, E3 for the classification: 4 genuine in-flight events, CAN-dropout pattern at idle). Clear action: inspect the Display CAN and HIC connectors, pull the B.U.D.S. fault log.

**`limit_exceedances` — keep; owner of limit events.** Every OM limit in the engine profile, with phase-aware suppression and duration thresholds (E1). Under A6 it is the **owner** of limit-exceedance signals; other topics defer to it (§4.1).

**`climb_thermal_rate` — move to Research.** The mechanism is sound (cooling capacity at high power and low airspeed, E2), and an earlier dataset showed the oil rise rate roughly tripling from normal to aggressive climb (E3). But it fails A7. Snapshot oil rise is 1.4 ± 4.1 °F/min (CV 2.9), so MDC ≈ 8 °F/min — larger than the difference it is meant to catch. The original design compared against "your average **for similar vertical speed**" (BACKLOG A2 #14). The code compares against all climbs regardless of VS bucket and of the oil temperature at the start of climb. Coolant rise is computed but unused. Proposal: Research status, conditioned on VS bucket and starting oil temperature; re-admit when MDC within that conditioning is below the effect size.

**`egt4_elevation` — remove.** Deprecated in engine 0.14.0 with a "one minor version" alias window (Spec 08 §4). The engine is now 0.21.0. Remove the rule, registry entry and baseline key.

**`flight_phase_mix` — remove the leftover rule.** Dropped as a topic in v0.10.0. It describes mission profile, not the engine (fails A4/A5). Its rule is still in `insight_rules.json` with `enabled: true`, though nothing evaluates it — anyone reading the rules file, or editing rules in the playground, sees a live rule that can never fire. Remove it, or mark it `enabled: false` with a `_comment` pointing to this register.

### 6.2 Audit outcome

| Outcome | Topics |
|---|---|
| Keep as is | `egt_cyl_deviation`, `engine_ecu_inflight`, `limit_exceedances` |
| Keep; reference the limit event, keep the close call (decided, §4.1, v0.3) | `overboost_time` |
| Keep; drop the duplicate limit insight (decided, §4.1) | `oil_temp_peak`, `coolant_temp_peak` |
| Keep; overlap to declare, trigger review pending Q1(b) | `egt_spread` |
| Keep, provisional (named condition) | `cylinder_rank` (no positive case yet), `map_at_takeoff` (config mismatch, altitude diversity) |
| Redefine before re-audit | `oil_coolant_ratio` |
| Leave the topic set → flight-summary line (decided, §4.2) | `cruise_efficiency`, `cruise_fuel_flow` |
| Move to Research | `climb_thermal_rate`; plus the new A5 fuel-flow model (§4.2) |
| Remove | `egt4_elevation`, `flight_phase_mix` (leftover rule) |

Once decided, each change becomes a BACKLOG item with this register as its reference. No change follows from this spec automatically.

## 7. Coverage view

Logged engine channels against the topics and limit checks that use them. A blank in the Topic column is a gap: it should be either a candidate or a recorded decision not to have a topic.

| Channel | Topics | OM limit checks | Gap / decision |
|---|---|---|---|
| `rpm` | `overboost_time` | idle min, takeoff max (5,800 rpm ceiling), overboost (5-minute rule) | — |
| `power_pct` | `overboost_time` | overboost (5-minute rule) | — |
| `map_inhg` | `map_at_takeoff` | MAP max | — |
| `egt1–4_f` | `egt_spread`, `egt_cyl_deviation`, `cylinder_rank` | EGT max ×4, EGT split ×2 | — |
| `oil_temp_f` | `oil_temp_peak`, `oil_coolant_ratio`, `climb_thermal_rate` | takeoff min, max, optimal-band low | Candidate **C1**: oil-temperature optimal band / condensation (metric exists, not surfaced) |
| `coolant_temp_f` | `coolant_temp_peak`, `oil_coolant_ratio` | max | — |
| `oil_press_psi` | — | min, max, cold max | Candidate **C2**: oil pressure vs. its own baseline at matched RPM and oil temperature — a classic bearing/pump wear observable, currently limits-only |
| `fuel_flow_gph` | — (flight summary only, §4.2) | (conditions the EGT split limit) | A5 fuel-flow model in Research (§4.2) |
| `fuel_press_psi` | — | min, max | Candidate **C3**: fuel pressure stability in flight (pump/regulator health), phase-aware for pump tests and tank switching |
| `main_volts`, `batt_amps` | — | volts min, max | Candidate **C4**: charging-system health (bus voltage and battery current under load). Note: the 9xiS ECU depends on electrical supply, which may make this a health topic rather than airframe-only. |
| `fuel_qty_l/r_gal` | — | — | **Decided: no topic.** Tank senders are attitude-sensitive and used only as a plausibility check (research paper §6.2, toolkit 0.6.0). |
| CAS string | `engine_ecu_inflight` | — | Other engine CAS alerts not yet classified — candidate for a later classification topic |
| Not logged: throttle position, lane A/B status, injector pulse width, ignition advance, wastegate position, T_plenum | — | — | **Out of reach (A1).** ECO/POWER inference (BACKLOG A4) is the only route, and it's blocked on a validation flight. |

C1–C4 enter the lifecycle (§8) as **Proposed**. None is admitted by being listed here.

## 8. Lifecycle

### 8.1 Stages

| Stage | Meaning | To enter it |
|---|---|---|
| **Proposed** | A question worth asking | A written proposal (§10): question, class, mechanism hypothesis, channels (A1, A2, A4 at E4 or better) |
| **Research** | Being measured | An experiment workspace (Spec 02 §5.1) or Explore mode (Spec 06), where the metric is computed but shown to no casual user |
| **Candidate** | Measured and argued | Availability, SD and MDC measured (A1, A7); overlap check done (A6); mechanism at E1/E2 (A4); action named (A5) |
| **Admitted** | Shown on every flight | Topic spec written (§9); rule defaults in `insight_rules.json`; tests against the project logs; register entry complete; maintainer approval |
| **Admitted (provisional)** | Shown, with one named open condition | As Admitted, plus the condition and the evidence that would close it (e.g. "first true positive", "≥ 5 departures above 2,000 ft") |
| **Deprecated** | Superseded or no longer passing | Register records the reason; rule `enabled: false` with a `_comment`; aliases kept for **one minor version** only |
| **Removed** | Gone from code | After the one-minor-version window; register entry stays, as history |

A topic can move back: an Admitted topic that fails a re-audit goes to Deprecated or Research, with the reason recorded.

### 8.2 Re-audit

The whole register is re-audited:

- whenever the number of real flights in the reference dataset has **doubled** since the last audit (A7's noise estimates and E3 evidence change with n), and
- before each research-paper edition, so the paper and the register agree.

A single topic is re-audited whenever its metric definition, anchor or rule shape changes.

### 8.3 Who decides

The project maintainer approves every stage change from Candidate upward. Research and Proposed need no approval — anyone can explore in their own workspace. Experiment workspaces are already the mechanism for keeping research settings away from the casual view (Spec 03 principle 6).

## 9. Topic specs

Every topic admitted from now on has a topic spec. The minimum contents, which map onto the register fields:

1. **Question and class** — the pilot's question; health or operational.
2. **Mechanism** — what it detects, the evidence and its grades, sources cited (OM chapter, literature, data).
3. **Inputs** — metrics (new registry entries), channels, phases, availability.
4. **Anchors** — kinds, sources, comparison scope (stratification, bucketing).
5. **Noise** — SD and MDC within that scope; the effect size the mechanism implies.
6. **Overlap** — what it owns, what it defers.
7. **Insights** — triggers, default severities, message templates, evidence links (Spec 01 §8.5).
8. **Action** — what the pilot or mechanic does.
9. **UI** — where it appears (Flight view card, Trends group).
10. **Acceptance** — tests against the project logs, including a positive and a negative case where the data has them.

**Spec 08 (cylinder balance)** is the first topic spec. It keeps its file and number — about 20 code comments cite "Spec 08 §N" — and is linked from the register for `egt_cyl_deviation` and `cylinder_rank`. It predates this template; items 2 (evidence grades), 5 (MDC) and 6 (overlap with `egt_spread`) would be added at its next revision.

Topics admitted before this spec have no topic spec. They are grandfathered **only** in that sense: the register entry and §6's audit stand in for one until the topic next changes, when it gets a full topic spec.

Where new topic specs live is Q2.

## 10. Proposals, including from the community

A proposal is the same whoever writes it — the maintainer after a research session, or another Rotax iS owner who noticed something in their own logs. It contains:

- the question, in pilot language;
- why it matters on a FADEC engine (A2);
- the suspected mechanism, with whatever evidence exists (A4, any grade);
- which logged channels it would use (A1);
- if possible, example flights showing the pattern — shared as an anonymized results bundle (Spec 02 §7), never raw logs, consistent with no service-side storage.

How a non-technical owner submits one, and how bundles get shared, is deliberately not designed here (Q5). The point of fixing the proposal's contents now is that the bar doesn't change depending on how a proposal arrives.

## 11. Acceptance criteria for this spec

1. Every `topic_id` in `insight_rules.json` and every topic emitted by `evaluate_insights` has a register entry. Nothing is emitted without one, and no rule exists without one.
2. Every Admitted topic has an evidence grade of E1 or E2 for its mechanism, recorded in its entry.
3. No OM-limit exceedance produces more than one insight on a flight (§4.1) — checked by a test against the project logs that includes a real exceedance (the 381 s overboost flight, `log_20260423_135821_KTOA.csv`: one `limit_exceedances` event and no `overboost_time` insight for it; and a synthetic oil/coolant exceedance).
4. No planning number (§4.2) produces an insight.
5. §6's audit numbers are re-run on the full local log set (Claude Code environment, 100+ logs), within the comparison scope each topic actually uses, and the A7 verdicts confirmed or revised. This is v0.2's main job.
6. §6.2's outcomes have a decision recorded — accepted, rejected, or deferred — each with a BACKLOG reference.
7. The research paper's analytics-modules section and this register agree on the topic list at the next paper edition.

## 12. Open questions

| # | Question | Leaning |
|---|---|---|
| Q1 | (a) ~~When a topic threshold mirrors an OM limit, should it still emit its own insight?~~ (b) Does `egt_spread` need a baseline-deviation trigger alongside `egt_cyl_deviation`'s four? | (a) **Resolved v0.2 — Option A:** `limit_exceedances` owns every limit event; topics reference it with a mirrored badge and emit nothing for it. Overboost is the documented exception — single reporter, no duplicate. See §4.1. (b) Open. Keep the spread **trend** (it tracks the OM split limit); review the spread **baseline_deviation** once the re-run shows how often both fire on the same flight. |
| Q2 | Where do new topic specs live: numbered in `docs/specs/` like platform specs, or `docs/specs/topics/<topic_id>.md`? | `docs/specs/topics/<topic_id>.md`, unnumbered. Numbers are for platform features; topics are one-per-question and may be many. Spec 08 keeps its number to avoid churning code references. |
| Q3 | A7's bar compares MDC with "the change the mechanism implies". Who estimates that change, and how precisely? | The topic spec states it, with its source (OM, literature, or an observed fault in the data). The maintainer judges. No universal CV cut-off — a single number would be arbitrary across metrics as different as °F and seconds. |
| Q4 | ~~Do topics that are about fuel planning rather than the engine belong in the per-flight topic set?~~ | **Resolved v0.2 — Option B:** no. Cruise nm/gal, cruise fuel flow and fuel burned move to a flight-summary line with no insights; the power × DA fuel-flow model (BACKLOG A5) enters Research. See §4.2. |
| Q5 | How does a non-technical owner submit a proposal and example bundles? | Deferred to the community-sharing work. Until then, proposals arrive via the project's GitHub (issue template with §10's fields). |
| Q6 | Should the register stay in this markdown spec, or become a machine-readable file (e.g. `topics/register.json`) that the UI and tests can read — for example to enforce acceptance 1 automatically? | Markdown for v0.x, while the schema settles. Revisit when Spec 01 §9's topic interface is frozen; a register check in the test suite (acceptance 1) is worth having either way. |

## Appendix A — Audit measurements (snapshot)

Source: `fleet_metrics.csv` in the project space (header). MDC = 2 × SD (z = 2.0). Comparison scope: all flights, unstratified — **not** the scope every topic uses, which is why acceptance 3 requires a re-run.

| Metric | Topic | n | Mean | SD | CV | MDC |
|---|---|---|---|---|---|---|
| `egt_spread_mean_f` | `egt_spread` | 23 | 56.4 °F | 5.1 | 0.09 | 10.3 °F |
| `egt4_elevation_f` (= `egt4_deviation_f`) | `egt_cyl_deviation` | 23 | +44.7 °F | 5.3 | 0.12 | 10.5 °F |
| `oil_temp_max_f` | `oil_temp_peak` | 24 | 196.9 °F | 31.5 | 0.16 | 63 °F |
| `oil_temp_below_optimal_pct` | (C1 candidate) | 24 | 91.0 % | 12.0 | 0.13 | 24 pts |
| `coolant_temp_max_f` | `coolant_temp_peak` | 24 | 175.8 °F | 25.7 | 0.15 | 51 °F |
| `oil_coolant_ratio` | `oil_coolant_ratio` | 24 | 1.12 | 0.04 | 0.04 | 0.08 (see §6.1) |
| `cruise_nmpg` | `cruise_efficiency` | 12 | 19.5 nm/gal | 2.1 | 0.11 | 4.1 nm/gal |
| `cruise_fuel_flow_gph` | `cruise_fuel_flow` | 12 | 6.33 gph | 0.50 | 0.08 | 1.0 gph |
| `climb_oil_rise_f_per_min` | `climb_thermal_rate` | 15 | 1.41 °F/min | 4.09 | 2.91 | 8.2 °F/min |
| `climb_coolant_rise_f_per_min` | (unused) | 15 | −0.43 °F/min | 1.23 | 2.84 | 2.5 °F/min |
| `egt_rank_stable` | `cylinder_rank` | 23 | stable 23/23 | — | — | — |
| `overboost_max_block_s` | `overboost_time` | 50 sessions | 41 s | 70 | — | n/a (limit: 1 > 300 s, 2 ≥ 240 s) |
