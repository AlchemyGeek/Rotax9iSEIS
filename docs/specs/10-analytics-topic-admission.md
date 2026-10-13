# Spec 10 — Analytics Topic Admission & Register

**Project:** SlingologyEIS
**Status:** Draft v0.12 — for review. Decisions D1–D19 in §6.3, all closed (D7 revised in v0.7; D18 added in v0.10; D19 in v0.12). Implemented: Phases A–D; Phase E (topic help) in progress.
**Suggested repo path:** `docs/specs/10-analytics-topic-admission.md`
**Builds on:** Spec 01 (§8.5 TopicResult/Insight, §9 extension model), Spec 03 (principle 6: the Explore → operational path), Spec 08 (cylinder balance — the first topic spec, §9), Spec 09 (filters on topic threshold insights), research paper Edition 0.3
**Baseline reviewed:** branch `webui` at commit `fee6577` (2026-10-01), engine 0.21.0; `insight_rules.json` v1.3; `engines/916iS.json`
**Audit data (v0.4):** full local log set, 2026-10-01 re-run (`reports/spec10_audit_2026-10-01.md`) — 107 logs → **50 admitted flights** (54 ground sessions skipped at admission, 3 merged into multi-file flights), 2026-04-08 → 2026-09-27, 28.2–115.0 engine hours, N117ZS. Computed with the app's own pipeline (`update_fleet`, `evaluate_insights`, leave-one-out baselines, default bands), with **no limit filters applied** — the topics' natural signal, not what the Flight view shows under saved filters. v0.1–v0.3 used an older 24-flight snapshot; Appendix A.2 records what changed.

**Revision history**

| Version | Change |
|---|---|
| 0.1 | Initial draft. Admission criteria, register schema, first audit of every current topic, coverage view, lifecycle, topic-spec template. |
| 0.2 | **Q1(a) decided — Option A:** `limit_exceedances` owns every OM-limit event; a topic that references a limit shows it (analysis line, link, mirrored badge) but never emits a second insight for it (new §4.1). **Q4 decided — Option B:** the topic set is for the engine; planning numbers (cruise nm/gal, cruise fuel flow, fuel burned) move to a flight-summary line with no insights, and the power × DA fuel-flow model (BACKLOG A5) becomes a Research item (new §4.2). Register, audit, outcomes, coverage view and acceptance updated to match. The "verify overboost overlap" item is closed: overboost is not checked by `limit_exceedances` (`report_in_exceedances: false`), so `overboost_time` is its only reporter and there is no duplicate. Q1(b) stays open. |
| 0.3 | **Overboost exception removed (Spec 09 v0.12).** Overboost is now the single owner of the OM 5-minute takeoff rule and is reported by `limit_exceedances` as an ordinary event (`report_in_exceedances: true`, blocks built with the 30 s merge gap); `rpm_continuous_max` is retired. The v0.2 reasoning that closed "verify overboost overlap" — overboost is not checked by `limit_exceedances`, so `overboost_time` is its single reporter — no longer holds. Overboost becomes an ordinary §4.1 case: `limit_exceedances` owns the event, and `overboost_time` references it (analysis line, link, mirrored badge) and keeps its close-call insight. §4.1, register, audit, outcome, coverage and acceptance 3 updated. |
| 0.4 | **Audit re-run on the full log set** (50 flights, from 24): §6 and Appendix A rewritten from it. Findings that changed: oil/coolant peak noise was a sample artefact — SDs now 12.2 / 6.9 °F, matching the research paper, and discriminating unstratified; the old spread came mostly from flight **duration** (peak oil vs airborne time r = 0.65), not weather. `climb_thermal_rate`'s Research verdict confirmed with both proposed conditioners tested and found insufficient. The oil − coolant cruise-mean difference measured and found discriminating (supports the redefinition). `map_at_takeoff`'s config mismatch quantified: 1 firing at the coded 1.5 inHg vs 23 at the configured 20 hPa — new **Q7** (derive the tolerance from the model). `limit_exceedances` saturation found: `fuel_press_min` on 50/50 flights — new **Q8**. Q1(b) co-firing measured (2/2). CV noted as unusable for metrics centred near zero (supports Q3's leaning). Acceptance 5 marked met. **Also §6.2 decisions, round 1** (new §6.3 decision log). D1: `oil_coolant_ratio` **dropped** — topic, metric and baseline removed rather than redefined; the oil − coolant balance idea goes to §7 as candidate **C5**, Proposed, with the research questions it must answer first (is it used in industry, and what sourced mechanism stands behind it). D2: `climb_thermal_rate` **moved to Research** — rule disabled, no Flight view card or Trends chart; rise-rate metrics still computed for research with new predictors. D3: `egt4_elevation` and `flight_phase_mix` **removed completely** from code; kept in the register as history. D4: `cylinder_rank`'s `hot_cyl_changed` insight **retired** (A6 — `egt_cyl_deviation` always fires first); the rank stays as context on Trends and in `egt_cyl_deviation`'s message. D5 (resolves Q7): `map_at_takeoff` tolerance = 2 × the model's leave-one-out residual SD, condition renamed `vs_personal_model`, plus a fitted-range guard; provisional status closed. D6 (resolves Q8): saturating limits — the pilot keeps the existing tools (filter with note, change monitor; research later); encoding and phase/artifact gaps are ours to find and fix, enforced by three new acceptance tests (nominal flight, saturation with allowlist, fingerprint regressions). D7: peak-temperature baselines exclude flights below a measured minimum airborne time. D8 (resolves Q1(b)): `egt_spread`'s baseline trigger kept for its niche (cross-cylinder divergence), folded into `egt_cyl_deviation`'s insight whenever both fire. D9 (resolves Q2): new topic specs live at `docs/specs/topics/<topic_id>.md`, unnumbered; Spec 08 keeps its number. D10 (resolves Q3): A7's effect size is stated in the topic spec with its source and judged by the maintainer; no universal CV cut-off. D11 (resolves Q5): interim GitHub "Topic proposal" issue template with §10's fields; the non-technical route is designed with the community-sharing work, keeping the same proposal contents. D12 (resolves Q6): hybrid register — markdown stays authoritative; `docs/specs/topics/register.json` holds the test-checked fields and the saturation allowlist, with an agreement test. |
| 0.5 | **D13 — topic help.** Every topic shown to pilots has a one-paragraph explanation behind a `?` on its card, kept outside code (Spec 01 §8.8: one file, `slingology_eis/help/topics.md`, a section per topic, placeholders for profile and rule values). Admission now requires it (§8.1), the topic-spec template gains a pilot-explanation item (§9), `register.json` records whether each topic has a help entry (§5), and acceptance 11 checks it. Draft paragraphs written for the eight visible topics and the flight-summary line. |
| 0.6 | **D6 diagnosis results** (`reports/spec10_d6_limit_diagnosis_2026-10-03.md`, D14–D17; fixes specified in Spec 09 v0.14 §6.8). `fuel_press_min`'s 50/50 predated commit 2632d01's engine-running gate — resolved before diagnosis (cause 2). D14 `volts_min`: cause 2, engine-running gate. D15 `fuel_press_max`: cause 3a, allowlist entry plus pilot filter; profile keeps 46 psi. D16 `rpm_idle_min`: cause 1 (plus one artifact), re-encode from the OM's idle wording — pending. D17 `rpm_takeoff_max`: classified 3a (prop-governor overshoot), keep Spec 09 v0.12's filter design, plus a resolution tolerance if quantized — pending the OM transient-overspeed check. New principle recorded: a limit fix must trace to the OM, Rotax documentation or sensor physics, never to clearing acceptance 9. |
| 0.7 | **Two-layer framing** added to §1 (engine profile + aircraft model). **D16 and D17 closed** (OM states idle as a minimum; no OM transient overspeed; 10 rpm resolution justifies no tolerance — details in Spec 09 v0.15 §6.8). **D5:** fitted-range guard kept as min–max, accepting that under leave-one-out each axis's extreme flight is never judged (4/48 on current data). **D7 revised:** the Phase C measurement found no airborne time beyond which peaks stop depending on duration (oil r ≈ 0.6 at every candidate threshold, coolant no pattern, no flights under 10 min), so no threshold is applied; predicting the peak from flight length moves to Research. **Single-aircraft evidence made explicit:** E3 grades state engine type and aircraft count (§4), topic status is recorded per engine profile with an *Unverified* status for engines without validating data (§5.1, §8.1), and a re-audit is triggered by data from a new aircraft or engine type (§8.2). |
| 0.8 | §9 item 11: help text must be **aircraft-neutral** — written for any aircraft with the engine, with no findings from one aircraft's data, no non-OM numbers, causes stated as possibilities. Applied to the drafts (`engine_ecu_inflight`'s single-aircraft sentence removed; the ±10 % fuel-flow figure, not OM-cited, removed). |
| 0.9 | **Spec 12 adds a `trends` field** (§5.1, §5.2) — panel, role, worsening direction and phrasing for the Trends change page (Spec 12 §8.1). Declaration lives at `docs/specs/topics/register.json` (alongside `status`/`topic_spec`/`help`, D12's existing hybrid register — not a new document), one `trends` object per topic entry, `null` where a topic has no scalar fleet metric for a panel to draw (`cylinder_rank`, `engine_ecu_inflight`, `limit_exceedances`) or the metric it would use doesn't exist yet (`map_at_takeoff`, pending the takeoff-MAP residual). `update_fleet` reads it (via `slingology_eis.operations.resolve_worsening_direction`) for the change statistic's worsening direction (Spec 12 R1.6/R3.3); `operations.build_trends_panels` exposes panel layout to callers without a frontend metric list. §5.2's table gains a **Trends panel** column with the same values. |
| 0.10 | **D18 — `engine_ecu_inflight` re-audited after Spec 01 v0.19.** The E3 evidence (v0.1: "4 genuine in-flight events"; v0.4: "5 IN_FLIGHT events in 50 flights, CAN-dropout pattern at idle") was a classifier defect — the runs are ground events, most of them single-row blips at engine start; the corrected result is zero in-flight events and one 5 s ground CAN dropout. Verdict changes from **Keep** to **Admitted (provisional)** (§8.1 stage; same footing `cylinder_rank` had: mechanism sound, positive case never seen; condition: first true positive or a deliberate test). The "clear action" sentence (CAN/HIC inspection, B.U.D.S.) is removed from the audit — it is single-aircraft maintenance guidance (§9 item 11) and the engine no longer emits it. §3 example, register row, audit table, §6.1, §6.2 and Appendix A updated; `register.json` status for 916iS becomes `Admitted (provisional)`. |
| 0.11 | Lane-check RPM band sourced from the OM (4,000 rpm procedure RPM, ±500 rpm our tolerance; 912iS/916iS, 915iS at its OM's 2,500 rpm, 914iS unverified); D18 evidence recorded (full set, Spec 01 v0.20). |
| 0.12 | **D19 — ENGINE ECU events are CAS events** (ECU review, 2026-10-13, four decisions). §4.1 generalised from OM-limit events to *events*: `limit_exceedances` owns every event, `source: limit` or `source: cas`; `engine_ecu_inflight` becomes a referencing topic (analysis line, lane-check summary, mirrored badge; no second insight), its D18 provisional condition unchanged. `GROUND` events are shown by default with the reason they are not a lane check; the user filters (Spec 09 v0.18) or acknowledges. Trends gets a frequency panel per classified CAS alert now, not deferred (Spec 12 v0.10) — the decision is not to be based on one aircraft's data. Lane-check adherence is **not** admitted: it is pilot procedure, not an engine signal; recorded as candidate **C6** (procedure class, undefined) in §7. The Engine ECU view (Spec 03 §5.4) is removed. |

---

## 1. Purpose

**How the analysis is built.** Two layers, plus two pieces on top:

1. **Engine profile — what Rotax says.** One per engine type, built from that engine's Operators Manual, every limit cited (the OM text itself is never stored). It answers *"did anything go outside the manufacturer's limits?"* and is the same for every aircraft with that engine.
2. **Aircraft model — what's normal for *this* aircraft.** Learned only from that aircraft's own flights: baselines, trends, the takeoff-MAP model, the usual hottest cylinder. It answers *"is this flight different from how this engine usually behaves?"* No number learned from one aircraft is applied to another. (A workspace holding several aircraft treats them as one for this layer — Spec 02 §5.6.)

On top: **the topics** — which questions get asked, admitted against this spec's criteria and recorded per engine type — and **the pilot's filters**, for characteristics of their own aircraft they've accepted, with the change monitor watching for anything that shifts. The rules come from Rotax, the expectations come from each aircraft's own history, and the pilot decides what to accept.

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
  - **Classification** — a rule that sorts events into expected vs. not (e.g. ENGINE ECU `GROUND_START`/`LANE_CHECK`/`GROUND`/`IN_FLIGHT`/`GROUND_SHUTDOWN`; learned hottest cylinder).
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
| **A4** | **Mechanism** | The topic names what it detects — a physical failure or degradation, or an operating practice the pilot controls — and grades the evidence for that link. | Evidence grade, at least one of: **E1** manufacturer (OM, service documents) · **E2** established engineering practice or literature · **E3** observed in this project's data — always stated with its engine type and aircraft count, e.g. *E3 (916iS, 1 aircraft)* · **E4** hypothesis. **Admission needs E1 or E2 for the mechanism.** E3 alone shows a pattern exists, not what it means; E4 alone keeps a topic in Research. *Every E3 in this spec so far is (916iS, 1 aircraft — N117ZS)*: findings that may not hold on another airframe or engine (§8.2). |
| **A5** | **Actionable** | A pilot or mechanic does something different when it fires. | The action named: change a habit (throttle discipline), watch (trend review), inspect (named components), or ground (limit). "Interesting" is not an action. |
| **A6** | **Distinct** | No other topic or limit check fires on the same signal; where two overlap, the register says which one owns which part. | An overlap statement in the register entry. Two cards for one event is a defect, not reinforcement. |
| **A7** | **Discriminating** | For baseline and model anchors: the metric is stable enough across comparable flights that the trigger can catch the change the mechanism implies. | Measured SD and MDC on the aircraft's data, within the comparison scope actually used (all flights, a weather band, a VS bucket…), set against the size of change the mechanism would produce. If MDC is larger than that change, the topic needs conditioning (stratify, bucket, normalize) before admission. Automatically met for OM-limit and classification anchors. |

Two classes of topic go through the same gate:

- **Health topics** detect a change in the engine (A4 names a degradation mechanism).
- **Operational topics** report something the pilot controls that the OM limits or that affects the engine (A4 names the practice: overboost time, oil-temperature condensation). An operational topic must still pass A5 — the pilot must be able to do something about it.

A number that informs flight planning but says nothing about the engine (range, efficiency, fuel burned) is **not a topic** — see §4.2.

### 4.1 Ownership of events (Q1(a), decided v0.2; generalised to CAS events in v0.12, D19)

Every **event** — an OM-limit exceedance (`source: limit`) or a classified CAS alert occurrence (`source: cas`, Spec 01 §8.6; today the `GROUND`/`IN_FLIGHT` classes of ENGINE ECU) — is reported **once**, by `limit_exceedances` — one insight per target per flight, carrying its events (Spec 09 §10.1). It owns the event's severity label, evidence, filter (Spec 09) and annotations. The card's display name may say "Limits & alerts"; the topic id does not change.

A topic that references a limit (through a threshold trigger's `limit_ref` — today `oil_temp_peak` and `coolant_temp_peak`) **does not emit an insight for it**. Instead:

- its analysis line states the exceedance and names the limit ("Exceeded OM limit (248 °F) — see Limit exceedances");
- its card links to the `limit_exceedances` insight for that limit;
- its card **displays** that insight's severity badge, so the Analysis grid still shows at a glance which topic the problem belongs to. The badge is mirrored, not a second insight: the insight list, its counts, filters and annotations see exactly one.

The topic keeps everything only it can do — baseline and trend triggers against the aircraft's own history.

**ENGINE ECU follows the same rule (v0.12, D19).** `engine_ecu_inflight` references the CAS event: its analysis line carries the per-class counts and the `lane_check` summary (`both` / `single` / `none`, informational only — never an insight), its card links to the event and mirrors its badge. It emits no insight of its own. Its D18 provisional condition (first `IN_FLIGHT` event) is unchanged — the event will appear as a CAS event when it happens.

**Overboost is not an exception (v0.3).** Until v0.3, overboost was checked only by `overboost_time` (`report_in_exceedances: false`) and this section made it an exception. Spec 09 v0.12 moves it into `limit_exceedances` as an ordinary event, one per block past the 300 s limit, so it follows the same rule as every other limit: `limit_exceedances` owns the event and `overboost_time` references it. The topic keeps the close call — a block near the limit is not an OM exceedance, so only the topic can report it. The 5,800 rpm ceiling (`rpm_takeoff_max`) is an ordinary limit owned by `limit_exceedances`.

**Follow-ups this decision creates** (not made by this spec): for overboost, done in Spec 09 v0.12 (§6.4, §10.3); Spec 09 §10.2 — topic threshold triggers become display-only references; Spec 03 §5.2 — the mirrored badge on topic cards; `insight_rules.json` — the `threshold` triggers on `oil_temp_peak` / `coolant_temp_peak` keep only their `limit_ref` for the reference, or move to a non-trigger field.

### 4.2 Planning numbers are not topics (Q4, decided v0.2)

A topic is about the engine: a health topic detects a change in it, an operational topic reports a pilot-controlled practice the OM limits or that affects it. Numbers whose main drivers are outside the engine — wind, load, the pilot's choice of power — are context, not topics. They appear in a **flight-summary line** (alongside duration and airborne time): fuel burned, cruise nm/gal, mean cruise fuel flow. They raise no insights and no trend alerts, and they don't appear in the Analysis grid.

They can come back as a topic only through the lifecycle (§8), with a definition that isolates an engine signal. The candidate route is BACKLOG A5's fuel-flow model (power % × density altitude), entered as **Research**. Its payoff is uncertain: on a FADEC engine both fuel flow and power % are ECU-computed, so the model may mostly reflect the ECU's map. That makes it more promising as an input to ECO/POWER inference (BACKLOG A4) than as a wear indicator — which the research has to show either way.

## 5. The register

The register has two parts (D12). **This section is authoritative** for rationale, evidence and history. **`docs/specs/topics/register.json`** carries only what tests check — each `topic_id` with its status, topic-spec path and whether it has a help entry (D13), and the limit-saturation allowlist (D6) — and a test keeps the two in agreement on topic ids and statuses.

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
| Status | §8.1 — **per engine profile** (v0.7): e.g. Admitted for 916iS, Unverified for 912iS / 914iS / 915iS |
| Topic spec | Link, or "none — written before this spec" |
| History | Admitted / changed / deprecated, with version and reason |

### 5.2 Register (v0.4)

Status is the **current** state, **for the 916iS**. §6 gives the audit verdict and proposed status change for each. On the 912iS, 914iS and 915iS profiles every topic that applies to that engine is **Unverified** (§8.1): no logs from those engines have been analysed. `map_at_takeoff` doesn't apply to the non-turbo 912iS.

| `topic_id` | Question | Class | Anchors | Status today | Trends panel |
|---|---|---|---|---|---|
| `egt_spread` | Are my cylinders burning evenly? | health | OM limit (EGT split, via `limit_exceedances`) · baseline · trend | Admitted | `cylinder_balance` |
| `egt_cyl_deviation` | Is any one cylinder drifting from the others? | health | baseline · trend, per cylinder | Admitted (Spec 08) | `cylinder_balance` |
| `cylinder_rank` | Has the usually-hottest cylinder changed? | health | classification (learned hottest cylinder) | Admitted (Spec 08) — insight **retired** (decided v0.4, D4); rank kept as context | null — no scalar fleet metric |
| `oil_temp_peak` | Did oil get too hot, or hotter than usual? | health + operational | OM limit (referenced, §4.1) · baseline | Admitted | `thermal` |
| `coolant_temp_peak` | Did coolant get too hot, or hotter than usual? | health | OM limit (referenced, §4.1) · baseline | Admitted | `thermal` |
| `oil_coolant_ratio` | Has the oil-vs-coolant balance shifted? | health | baseline | **Dropped** (decided v0.4, D1) — to be removed; idea kept as candidate C5 (§7) | `thermal` (context) |
| `overboost_time` | Did I stay at takeoff power too long? | operational | OM limit (referenced, §4.1: 300 s above 5,500 rpm / 100 %) · close-call margin | Admitted | `boost_power` |
| `cruise_efficiency` | How far am I going per gallon in cruise? | planning (§4.2) | baseline · trend, DA band | Admitted — to leave the topic set (Q4) | `fuel` |
| `cruise_fuel_flow` | Is cruise fuel burn normal? | planning (§4.2) | baseline, DA band | Admitted — to leave the topic set (Q4) | `fuel` |
| `map_at_takeoff` | Is the turbo making expected boost at takeoff? | health | empirical model (MAP ~ PA, OAT); tolerance from model residuals (D5) | Admitted | null — pending the takeoff-MAP residual fleet metric (Spec 12 §8.2, not yet built) |
| `engine_ecu_inflight` | Did the FADEC report a fault in flight? | health | classification (`cas.py`, phase-based since Spec 01 v0.19) | Admitted (provisional) — D18 | null — not a baselined scalar |
| `limit_exceedances` | Did anything go outside an OM limit? | health + operational | OM limits (all, overboost included since v0.3, §4.1) | Admitted — owner of limit events | null — limit panels are generated per limit, not declared |
| `climb_thermal_rate` | Did the engine heat up faster than usual in climb? | health | baseline | **Research** (decided v0.4, D2) — rule disabled; metrics still computed | `thermal` (context) |
| `egt4_elevation` | (superseded by `egt_cyl_deviation` cylinder 4) | — | — | Deprecated in engine 0.14.0 (Spec 08); **Removed** (decided v0.4, D3) | null |
| `flight_phase_mix` | Was this flight's climb/cruise/descent split unusual? | — | — | Dropped as a topic in toolkit v0.10.0 (replaced by the "no cruise detected" header note); leftover rule **Removed** (decided v0.4, D3) | null |

## 6. Audit of the current topics (v0.4)

Each topic was checked against A1–A7 using the code at `fee6577`, the research paper, and the full-set re-run named in the header (numbers in Appendix A.1). ✓ passes · ◐ passes with a stated condition · ✗ fails.

| `topic_id` | A1 | A2 | A3 | A4 | A5 | A6 | A7 | Verdict |
|---|---|---|---|---|---|---|---|---|
| `egt_spread` | ✓ | ✓ | ✓ | ✓ E1+E2 | ✓ | ✓ by D8 | ✓ | Keep; folds into cylinder insight when both fire (D8) |
| `egt_cyl_deviation` | ✓ | ✓ | ✓ | ✓ E2+E3 | ✓ | ◐ | ✓ | Keep |
| `cylinder_rank` | ✓ | ✓ | ✓ | ✓ E2 | ✓ | ✗ | n/a | **Retire insight**, keep as context (D4) |
| `oil_temp_peak` | ✓ | ✓ | ✓ | ✓ E1 | ✓ | ✗ → ✓ by §4.1 | ✓ | Keep; drop its limit insight (§4.1) |
| `coolant_temp_peak` | ✓ | ✓ | ✓ | ✓ E1 | ✓ | ✗ → ✓ by §4.1 | ✓ | Keep; drop its limit insight (§4.1) |
| `oil_coolant_ratio` | ✓ | ✓ | ✓ | ✗ E4 | ◐ | ✓ | ✗ ratio · ✓ ΔT | **Drop** (D1); idea → C5 |
| `overboost_time` | ✓ | ✓ | ✓ | ✓ E1 | ✓ | ✓ | n/a | Keep; references the `limit_exceedances` event, keeps the close call (§4.1, v0.3) |
| `cruise_efficiency` | ✓ | ◐ | ✓ | ✗ | ◐ | ◐ | ◐ | Move to flight summary (§4.2) |
| `cruise_fuel_flow` | ✓ | ◐ | ✓ | ✗ | ◐ | ✓ | ◐ | Move to flight summary (§4.2); A5 model to Research |
| `map_at_takeoff` | ✓ | ✓ | ✓ | ✓ E1+E3 | ✓ | ✓ | ✓ by D5 | Keep; tolerance from model + range guard (D5) |
| `engine_ecu_inflight` | ✓ | ✓ | ✓ | ✓ E1 (E3 withdrawn, D18) | ✓ | ✓ | n/a | Keep, provisional |
| `limit_exceedances` | ✓ | ✓ | ✓ | ✓ E1 | ◐ | owner | n/a | Keep; owner of limit events; saturation per D6 |
| `climb_thermal_rate` | ✓ | ✓ | ✓ | ✓ E2 | ◐ | ✓ | ✗ | **Research** (D2) |
| `egt4_elevation` | — | — | — | — | — | ✗ | — | **Remove** (D3) |
| `flight_phase_mix` | — | — | — | ✗ | ✗ | — | — | **Remove** leftover rule (D3) |

### 6.1 Findings, topic by topic

**`egt_spread` — keep; declare overlap.** EGT split is an OM limit (392 °F above 3 L/h fuel flow, OM Chapter 2.1), checked as an exceedance by `limit_exceedances`; the topic's own triggers are baseline and trend. Mechanism: a widening spread within limits points to an injector or ignition imbalance (E2; research paper §6.1). Data: cruise mean 59.3 ± 5.2 °F, MDC 10.4 °F — discriminating (mild OAT band: MDC 11.0, n = 40). Trend +0.22 °F/hr, R² 0.30 at the earlier count, below the 0.5 gate (E3, not yet confirmed). Overlap: spread (max − min) and `egt_cyl_deviation` respond to the same imbalance. Proposed ownership: `egt_spread` owns *overall balance against the OM split limit and its trend*; `egt_cyl_deviation` owns *attribution to a cylinder*. Whether `egt_spread`'s baseline-deviation trigger is still needed alongside four per-cylinder triggers is Q1(b). Re-run: it fired on 2/50 flights, and on both a per-cylinder deviation fired too (any per-cylinder: 7/50). No case yet of the spread trigger catching something the cylinder triggers missed — but two cases is too few to retire it.

**Decision (D8, resolves Q1(b)):** keep the baseline trigger; the per-cylinder insight owns shared events. The spread has a niche the per-cylinder triggers can miss — a divergence across cylinders that no single cylinder explains (e.g. hottest +6 °F and coolest −6 °F: each cylinder's deviation moves about 8 °F, under its ~10 °F MDC, while the spread moves 12 °F, over its 10.4 °F MDC) — and it is the OM split-limit quantity. So: on any flight where an `egt_cyl_deviation` trigger fires, the spread's baseline insight is not emitted separately; the cylinder insight notes that the spread is also outside its usual range. The spread fires alone only in its niche. The trend trigger is unchanged. This satisfies A6 — one card per event — by the same rule as D4 and §4.1: the more specific signal owns the event.

**`egt_cyl_deviation` — keep.** Admitted through Spec 08, which already reads as a topic spec. Per-cylinder deviations, MDC 8–12 °F: cyl 1 −31.1 ± 5.4, cyl 2 −8.5 ± 5.8, cyl 3 −6.9 ± 4.1, cyl 4 +46.6 ± 4.9 °F. Fired 9 times across 50 flights. (Cyl 2 and 3 show CVs of 0.6–0.7 only because their means sit near zero — CV is meaningless there; MDC is the measure that matters, see Q3.) Mechanism: lean cylinder runs hot (injector), cooler cylinder points to ignition or plug, erratic reading points to the probe (E2, Spec 08 §1).

**`cylinder_rank` — insight retired, rank kept as context (decided v0.4, D4).** Classification against the learned hottest cylinder, needing a ≥ 15 °F margin on 2 consecutive flights. The mechanism is sound (E2), but the positive case has never been seen: the hottest cylinder was stable on 50/50 flights (cylinder 4, learned at 100 %), and `hot_cyl_changed` has never fired. The hottest-minus-next margin runs 14.0–48.4 °F (median 39.2); the minimum sits just under the 15 °F `margin_min_f`, so the threshold is close to, but has not met, real data.

**A6 — fails: it overlaps `egt_cyl_deviation` and always fires second.** Spec 08's synthetic test shows the code works (a cyl 4 → cyl 2 switch raises exactly one warning), so the open question isn't correctness but contribution. With cylinder 4 leading by a median 39 °F, another cylinder can only lead it by 15 °F after a relative movement of about 55 °F; `egt_cyl_deviation` flags about 10 °F per cylinder against its own history, and its trend trigger catches gradual drift. Any fault that changes the hottest cylinder — a lean injector heating another cylinder, or an ignition fault cooling cylinder 4 — has therefore already raised a deviation insight. On engines whose cylinders run closer together the margin guard alone still demands more movement than the deviation MDC, so the ordering holds there too. What the rank adds is a clearer description, not an earlier signal.

**Decision (D4):** retire the `hot_cyl_changed` insight; keep the rank as context.
- The `cylinder_rank` rule is disabled (`enabled: false`, `_comment` pointing to this register); no Flight view card.
- The learned hottest cylinder stays on the Trends header chip and the hottest-cylinder strip (Spec 08 §7).
- When this flight's hottest cylinder differs from the learned one (by ≥ `margin_min_f`), `egt_cyl_deviation`'s insight says so in its message — e.g. "…cylinder 2 is now the hottest, usually cylinder 4" — so the wording moves to the signal that owns the event.
- **Follow-up:** Spec 08 revision (§6 insights: `hot_cyl_changed` retired, message added to `egt_cyl_deviation`; §10 acceptance 3 rewritten to assert the message rather than a separate warning). Not made by this spec. Provisional until a true positive, or a deliberate test (§8.1), shows the 15 °F / 2-flight rule fires when it should and not otherwise.

**`oil_temp_peak`, `coolant_temp_peak` — keep; remove the duplicate.** OM limit 248 °F for both (E1). Since Spec 09 §10.2, each topic's threshold trigger fires *exactly when* `limit_exceedances` has an unsuppressed event for `oil_temp_max` / `coolant_temp_max` — so one exceedance produces two `limit`-severity insights. That fails A6. **Decided (§4.1):** `limit_exceedances` owns limit events; the peak topics keep their baseline triggers and *reference* the limit — analysis line, link, mirrored badge — but no longer emit a second limit insight. **A7 — passes (v0.4).** On the full set the SDs are 12.2 °F oil and 6.9 °F coolant (MDC 24.4 / 13.8 °F), matching the research paper, without stratification; the mild OAT band barely changes them (11.8 / 6.8, n = 40). The old snapshot's 31 / 26 °F came mostly from **flight duration**, not weather: peak oil correlates with airborne time at r = 0.65 (coolant r = 0.36), and 13/50 flights are under 20 minutes airborne, never reaching thermal equilibrium. OAT bands can't yet do much regardless — the set is 40 mild / 6 cold / 1 warm / 0 hot.
*Proposal (new):* because duration drives the peaks, a short flight's "lower than usual" peak is expected, not a finding. Either leave flights under a minimum airborne time out of the peak baselines, or condition the comparison on airborne duration.

**Decision (D7) — revised v0.7: no threshold.** v0.4 decided a minimum airborne time below which peaks wouldn't be compared, to be measured as the airborne time beyond which the peak stops depending on duration. The Phase C measurement found no such point: oil peak correlates with airborne time at r ≈ 0.6 at every candidate threshold from 10 to 30 minutes (hour-plus flights peak about 18 °F above 10–20-minute ones), coolant shows no consistent pattern, and the log set has no flights under 10 minutes. Any threshold would be a number the data doesn't support, so none is applied: the peak baselines stay as they are (A7 already passes, MDC 24 °F oil / 14 °F coolant). Predicting the expected peak from airborne time (and OAT) moves to **Research**, like D2; whether the current peak insights include short-flight "below usual" cases is checked in Phase C and becomes that Research item's evidence.
*Duplicate check:* zero double-reports on real data — not because the defect is absent, but because neither limit has ever been exceeded (peaks well under 248 °F even at +2 SD). §4.1 still applies; acceptance 3 needs a synthetic exceedance to test it.
*Gap:* the original topic 4 included "% time below the 194 °F/90 °C optimal band". The metric `oil_temp_below_optimal_pct` is computed (snapshot mean 91 %) but no topic surfaces it. It has an E1 basis (OM guidance on reaching operating temperature to drive off condensation) and a clear action. Listed as a candidate in §7.

**`oil_coolant_ratio` — dropped (decided v0.4, D1).** Two problems.
1. It is `oil_max_°F / coolant_max_°F` (`fleet.py`). A ratio of temperatures on an interval scale has no physical meaning: the same flight gives a different ratio in °C, and an equal rise in both temperatures moves the ratio. The two peaks can also occur at different moments.
2. The mechanism — "a signature of thermal health" (research paper §6.5) — is unsourced (E4). Its very low CV (0.04) reflects the ratio compressing the data, not a stable signal.

Proposal: redefine as a temperature **difference** (oil − coolant), measured simultaneously in a stable phase. State the mechanism: oil cooler effectiveness vs. coolant radiator effectiveness — a blocked oil cooler raises the difference, a coolant-side problem lowers it. Grade it E2 or demote to Research.

**Re-run (v0.4)** compared three forms on the same flights:

| Form | n | Mean | SD | MDC | Fires at z = 2 |
|---|---|---|---|---|---|
| Current ratio | 50 | 1.11 | 0.04 | 0.08 | 1 / 50 |
| **Cruise-phase mean of simultaneous (oil − coolant)** | 47 | 19.9 °F | 2.55 | **5.1 °F** | 3 / 47 |
| Difference at the time of the oil peak | 50 | 23.5 °F | 6.59 | 13.2 °F | 1 / 50 |

The cruise-phase mean difference is the one to use: a real, interpretable spread, a 5 °F detectable change, and a fire rate (~6 %) consistent with a 95 % band. The peak-time form is noisier because the two temperatures aren't in equilibrium at that instant. **A7 passes for the cruise-mean ΔT; A4 still needs an E2 source for the cooler-effectiveness mechanism before it can be admitted under the new definition.**

**Decision (D1):** drop rather than redefine. A better measurement doesn't make a topic defensible on its own: whether the oil–coolant balance is an established health indicator — used by Rotax, by maintenance practice, or in engine-monitoring literature — is unknown, and admitting it ahead of that answer would repeat the original mistake with a better number. The topic, the `oil_coolant_ratio` metric and its baseline are removed. The idea, and the measurements above, are kept as candidate **C5** (§7) so the research can start from them.

**`overboost_time` — keep.** OM: 5,500 rpm maximum continuous, 5,800 rpm takeoff limited to 5 minutes (E1). Time above 5,500 rpm or 100 % power is therefore the time-limited regime. Operational class, direct action (throttle back after takeoff). Full set: one exceedance (381 s, ATC delay) and one further close call (≥ 240 s) in 50 flights; mean longest block 71 s. Since v0.3 (Spec 09 v0.12) a block past the limit is a `limit_exceedances` event; the topic references it (§4.1) and keeps what only it can report — the close call and the time-in-regime context. Overboost also replaced `rpm_continuous_max`, which raised a CAUTION on every takeoff because it had no time allowance.

**`cruise_efficiency` — move to the flight summary (§4.2).** nmpg integrates **ground speed** (`fuel.py`), so a headwind looks like an efficiency loss — the dominant term is wind, not the engine (fails A4 as a health topic). FADEC fuel flow is model-based, ±10 % (OM). A DA band reduces but doesn't remove the confounders: power setting, wind, weight. Its "decreasing — worth watching" trend implies engine degradation that the data can't support. **Decided (§4.2):** cruise nm/gal becomes a flight-summary number with no insights. A true-airspeed, matched-power redefinition is possible later through the lifecycle, but isn't proposed now.

**`cruise_fuel_flow` — move to the flight summary (§4.2).** At a given power and DA the FADEC sets fuel flow from its own map, so the comparison only means something within a power band. Blended across power settings it mostly reports the pilot's choice of power. SD 0.5 gph (CV 0.08) looks discriminating but mixes power settings. **Decided (§4.2):** mean cruise fuel flow becomes a flight-summary number. The comparison within power-% × DA bands (BACKLOG A5's model) is entered as Research, with the caveat in §4.2 that on a FADEC engine it may mainly reflect the ECU's own map.

**`map_at_takeoff` — keep, provisional; fix the config.** Mechanism: under-boost at full power points to turbo, wastegate or intake problems (E1 — OM reference MAP and air-supply guidance per BACKLOG A3; chapter to be cited in the topic spec). Data: empirical model R² 0.75, n 48 (E3). Two problems:
1. `insight_rules.json` says `vs_om_expected` with `tolerance_hpa: 20`, but the code compares against the *personal model* with a hard-coded ±1.5 inHg (≈ 51 hPa). The configured tolerance is never read, and the condition name describes a comparison the code doesn't make. Re-run: the coded 1.5 inHg fired on **1** of 48 flights; the configured 20 hPa (≈ 0.59 inHg) would have fired on **23** — nearly half of all flights. Neither number is justified by A7: the tolerance should come from the model's own residual scatter (Q7).
2. Altitude diversity is thin: 5 of 48 departures above 2,000 ft pressure altitude (BACKLOG A6) — no longer zero, but the altitude term still rests on few points.

**Decision (D5, resolves Q7):**
- **Tolerance = z × the model's residual SD**, z = 2 as for every baseline, with residuals computed leave-one-out so a flight is never judged by a model it helped fit. The rule's config holds `z`, not a fixed number; the tolerance tightens as the model improves and adapts to each aircraft. The 20 hPa OM figure is a reference-condition check, not a tolerance for a statistical model, and is not used as one. Rough estimate from the audit counts: residual SD ≈ 0.6–0.9 inHg, so 2 SD ≈ 1.2–1.8 inHg — similar behaviour to today's coded 1.5 inHg, now justified; the exact value is measured at implementation.
- **Condition renamed** from `vs_om_expected` to `vs_personal_model`, describing the comparison actually made. The OM reference MAP stays in the analysis line as context.
- **Fitted-range guard:** if the flight's pressure altitude or OAT lies outside the range the model was fitted on, the analysis line says so and no insight is raised — an explicit statement instead of a silent extrapolation.
- **Leave-one-out side effect (Phase C measurement, accepted v0.7):** a flight judged by a model fitted on all *other* flights is always outside their range if it is the dataset's extreme on either axis, so those flights are never judged — 4 of 48 on current data. Accepted: "never extrapolate" is the simplest rule that can be defended, and the range widens as more places and conditions are flown. A leverage-based guard was considered and not adopted. Measured leave-one-out residual SE: 0.71–0.75 inHg (2 × SE ≈ 1.45 inHg; 3 of 48 flights fire, against 2 at the old 1.5 inHg).
- With the guard in place, thin altitude diversity (5 of 48 departures above 2,000 ft) limits *where* the topic can judge, not whether its judgments are sound. **Provisional status closed.**

**`engine_ecu_inflight` — keep, provisional (D18, v0.10).** A classification anchor separating expected FADEC behaviour (`GROUND_START`, `LANE_CHECK`, `GROUND_SHUTDOWN`) from `IN_FLIGHT` events (E1 for the alert's meaning). E3 is now **absent**: the five runs the v0.4 audit counted as in-flight were a classifier defect (Spec 01 v0.19 — no flight test, no minimum duration); the corrected result on all 115 logs is zero in-flight events and two short `GROUND` runs (Spec 01 v0.20; the 2026-06-04 run first read as a CAN dropout is a shutdown). The topic passes A1–A7 on mechanism (E2) and clears the noise test trivially (nothing fires), but its positive case has never been observed. Provisional until a true positive, or a deliberate test (§8.1 — e.g. an injected `IN_FLIGHT` excerpt), shows the phase-based classifier fires when it should and not otherwise. `GROUND` runs are not this topic's concern; how they surface is Spec 03's.

**`limit_exceedances` — keep; owner of limit events.** Every OM limit in the engine profile, with phase-aware suppression and duration thresholds (E1). Under A6 it is the **owner** of limit-exceedance signals; other topics defer to it (§4.1).
*Saturation (new, v0.4):* with no filters applied it produced 187 flight-level insights across 50 flights, almost all from five limits — `fuel_press_min` on **50/50** flights, `rpm_continuous_max` 49/50, `fuel_press_max` 40/50, `rpm_idle_min` 25/50, `volts_min` 23/50. (`rpm_continuous_max` is the saturation case already fixed at the source: Spec 09 v0.12 retires it because it had no time allowance, so every takeoff breached it. The audit ran on code that still has it; Phase 6 is not yet implemented. Its 2026-10-01 numbers also predate overboost becoming a `limit_exceedances` event.) A limit that fires on every flight tells the pilot nothing about *this* flight (A5 in practice), whatever its OM basis. The remedy belongs to Spec 09 (filters, phase rules, durations) — and saved filters already do this in the Flight view — but the register must record it: see Q8.

**Decision (D6, resolves Q8).** A limit can saturate for three reasons, and they are not the pilot's problem in the same way:

| Cause | Fingerprint in the data | Whose problem | Fix |
|---|---|---|---|
| 1 — limit encoded wrongly | Fires during a normal procedure the OM allows (e.g. every takeoff), with normal values | **Ours** — an EIS solution gap | Engine profile (Spec 09) |
| 2 — phase or artifact gap | Fires at transitions (start, warm-up, shutdown, taxi); brief spikes or impossible values (0.0 V running, −0.6 psi); same position relative to a phase boundary every flight | **Ours** — an EIS solution gap | Phase rule (Spec 09) |
| 3a — persistent, stable (sensor, calibration, installation) | Steady offset through steady operation, plausible values, no link to procedure | Pilot's aircraft | Filter with a note; change monitor watches for drift (Spec 09) |
| 3b — anything else | Doesn't fit the above | Unexplained | Research (trends, correlations; future research module, Spec 06) |

Causes 1 and 2 belong to our rules, so they would show on every aircraft using the same engine profile; cause 3 belongs to one airframe. **The pilot never classifies anything** — what they see is unchanged: limit events, filters with notes, the change monitor, and later the research module. We find and fix causes 1 and 2, and the test suite enforces it (acceptance 8–10): a nominal flight raises nothing, no limit saturates without a documented cause-3 allowlist entry, and fixed gaps stay fixed. A limit is never removed or demoted for firing often; the OM limit stays the OM limit.

**First job — done (v0.6).** The diagnosis (`reports/spec10_d6_limit_diagnosis_2026-10-03.md`, whole log set) classified every saturating limit; the fixes are specified in Spec 09 v0.14 §6.8:

| Limit | Corrected rate | Cause | Decision |
|---|---|---|---|
| `fuel_press_min` | 0/50 | 2 | Resolved before diagnosis: the audit's 50/50 predated commit 2632d01's `min_rpm` gate |
| `volts_min` | 23/50 | 2 (0.0 V at shutdown) | **D14:** engine-running gate |
| `fuel_press_max` | 40/50 | 3a (steady offset) | **D15:** allowlist + pilot filter; OM 46 psi kept |
| `rpm_idle_min` | 25/50 | 3a (steady low idle) + 2 (start spool-up) | **D16:** minimum kept; idle-established condition; allowlist + pilot filter — decided |
| `rpm_takeoff_max` | 47/50 (Phase 6) | 3a (prop-governor overshoot) | **D17:** hard ceiling, pilot filter ≤ +30 rpm, allowlist citing the MML; no OM allowance, no resolution tolerance — decided |

Code's first classification of `rpm_takeoff_max` was cause 1 (engine-type governor tolerance). It became 3a because on a constant-speed propeller installation the propeller governor, not the FADEC, holds rpm at full power, so the overshoot belongs to the installation. It would have reverted to cause 1 only if the OM permitted a transient overspeed; it doesn't (v0.7). Both classifications rest on one aircraft and are re-examined when a second 916iS's data arrives (§8.2).

**Principle (v0.6):** every limit fix must trace to the OM, Rotax documentation or a physical fact about the sensor. Acceptance 9's 50 % bar says *that* something is wrong, never *what's right*; a tolerance chosen because it clears the bar is ruled out.

**`climb_thermal_rate` — moved to Research (decided v0.4, D2).** The mechanism is sound (cooling capacity at high power and low airspeed, E2), and an earlier dataset showed the oil rise rate roughly tripling from normal to aggressive climb (E3). But it fails A7. Full set: oil rise 1.13 ± 3.25 °F/min, MDC 6.5 °F/min — larger than the difference it is meant to catch. The original design compared against "your average **for similar vertical speed**" (BACKLOG A2 #14). The code compares against all climbs regardless of VS bucket and of the oil temperature at the start of climb. Coolant rise is computed but unused. Proposal: Research status, conditioned on VS bucket and starting oil temperature; re-admit when MDC within that conditioning is below the effect size.

**Re-run (v0.4) tested both conditioners — neither is enough:**

| VS bucket | n | Oil rise | SD | MDC |
|---|---|---|---|---|
| gentle (200–500 fpm) | 46 | +0.12 °F/min | 1.59 | 3.2 |
| normal (500–1,000 fpm) | 49 | +2.22 °F/min | 4.39 | 8.8 |
| aggressive (≥ 1,000 fpm) | 47 | +6.17 °F/min | 7.40 | 14.8 |

Bucketing confirms the physical effect (gentle → aggressive +6.1 °F/min) but within-bucket noise still exceeds it: aggressive climbs' own MDC is 14.8 °F/min. Start-of-climb oil temperature explains almost nothing (r = −0.18; residual SD 3.25 → 3.20). **Research verdict confirmed.** The remaining noise needs a predictor this data doesn't yet have — candidates for the Research stage: climb duration (short climbs give unstable rates), power %, OAT, or a rate taken over a fixed altitude band rather than a whole climb.

**Decision (D2):** Research. Unlike D1, the mechanism is established (E2) — only the measurement fails — so the data keeps accumulating rather than being dropped. In practice:
- the `climb_thermal_rate` rule is disabled (`enabled: false`, with a `_comment` pointing to this register), so no Flight view card and no insights;
- the climb-rate chart comes off the Trends tab too, since Research means no casual user sees it (§8.1);
- the rise-rate metrics (oil and coolant, overall and per VS bucket) stay computed and available in the CLI, notebooks and experiment workspaces;
- re-admission goes through Candidate (§8.1): a conditioning that brings MDC below the gentle → aggressive effect (about 6 °F/min on current data), shown on the log set.

**`egt4_elevation` — remove.** Deprecated in engine 0.14.0 with a "one minor version" alias window (Spec 08 §4). The engine is now 0.21.0. Remove the rule, registry entry and baseline key. **Decided (D3):** removed completely — rule, registry metric, baseline key, Trends reference and web fixtures (17 references at `8f7c82c`); workspaces drop the stale key on their next rebuild. The research paper's "EGT4 elevation" finding stays as history and is reconciled at the next edition (acceptance 7).

**`flight_phase_mix` — remove the leftover rule.** Dropped as a topic in v0.10.0. It describes mission profile, not the engine (fails A4/A5). Its rule is still in `insight_rules.json` with `enabled: true`, though nothing evaluates it — anyone reading the rules file, or editing rules in the playground, sees a live rule that can never fire. Remove it, or mark it `enabled: false` with a `_comment` pointing to this register. **Decided (D3):** remove the rule entry (and its web fixture copy). The phase-minutes data behind the "no cruise detected" header note is unaffected.

### 6.2 Audit outcome

| Outcome | Topics |
|---|---|
| Keep as is | `egt_cyl_deviation` |
| Keep, provisional (D18) — no positive case; prior evidence withdrawn | `engine_ecu_inflight` |
| Keep; saturation handled per D6 — our gaps fixed and test-enforced, pilot keeps existing tools | `limit_exceedances` |
| Keep; reference the limit event, keep the close call (decided, §4.1, v0.3) | `overboost_time` |
| Keep; drop the duplicate limit insight (decided, §4.1); no duration threshold (D7 revised) | `oil_temp_peak`, `coolant_temp_peak` |
| Keep; per-cylinder insight owns shared events (decided, D8) | `egt_spread` |
| Keep; tolerance from the model, fitted-range guard (decided, D5) | `map_at_takeoff` |
| Retire insight, keep as context (decided, D4) | `cylinder_rank` |
| Leave the topic set → flight-summary line (decided, §4.2) | `cruise_efficiency`, `cruise_fuel_flow` |
| Research (decided, D2, D7) | `climb_thermal_rate`; the A5 fuel-flow model (§4.2); peak temperature predicted from airborne time (D7) |
| Remove (decided, D1, D3) | `egt4_elevation`, `flight_phase_mix` (leftover rule), `oil_coolant_ratio` |

Once decided, each change becomes a BACKLOG item with this register as its reference. No change follows from this spec automatically.

### 6.3 Decision log

| # | Item | Decision | Date / version |
|---|---|---|---|
| D1 | `oil_coolant_ratio` | **Dropped.** Remove topic, metric and baseline. The oil − coolant balance becomes candidate C5 (Proposed) pending research into industry use and a sourced mechanism. | 2026-10-02, v0.4 |
| D2 | `climb_thermal_rate` | **Research.** Disable the rule; remove the Flight view card and the Trends chart; keep the rise-rate metrics computed. Re-admit via Candidate when a conditioning brings MDC below the effect size. | 2026-10-02, v0.4 |
| D3 | `egt4_elevation`, `flight_phase_mix` | **Removed completely.** `egt4_elevation`: rule, registry metric, baseline key, Trends reference, fixtures. `flight_phase_mix`: rule entry. Both stay in the register as history. | 2026-10-02, v0.4 |
| D4 | `cylinder_rank` | **Insight retired** (fails A6: `egt_cyl_deviation` always fires first on the same event). Rule disabled; rank stays on Trends (chip, strip) and is named in `egt_cyl_deviation`'s message when it changes. Spec 08 revision to follow. | 2026-10-02, v0.4 |
| D5 | `map_at_takeoff` (Q7) | **Tolerance = 2 × leave-one-out model residual SD**; config holds `z`; condition renamed `vs_personal_model`; insight suppressed (with a note) outside the model's fitted PA/OAT range — min–max, accepting that each axis's extreme flight is never judged (v0.7). Provisional status closed. | 2026-10-02, v0.4; guard confirmed 2026-10-05, v0.7 |
| D6 | Limit saturation (Q8) | **Pilot: existing tools only** (filter with note, change monitor; research module later for unexplained cases). **Us: causes 1 and 2 are EIS solution gaps**, found and fixed by us and enforced by acceptance 8–10. First job: make those pass for `fuel_press_min`, `fuel_press_max`, `rpm_idle_min`, `volts_min`. | 2026-10-02, v0.4 |
| D7 | Short flights in peak baselines | **Revised v0.7: no threshold.** Measurement found no airborne time beyond which peaks stop depending on duration; peak baselines unchanged; predicting the peak from airborne time moves to Research. | 2026-10-02, v0.4; revised 2026-10-05, v0.7 |
| D8 | `egt_spread` baseline trigger (Q1(b)) | **Kept** for its cross-cylinder-divergence niche; folded into `egt_cyl_deviation`'s insight on any flight where a per-cylinder trigger fires. Trend trigger unchanged. | 2026-10-02, v0.4 |
| D9 | Topic spec location (Q2) | **`docs/specs/topics/<topic_id>.md`**, unnumbered; numbers reserved for platform specs; Spec 08 stays where it is. | 2026-10-02, v0.4 |
| D10 | A7 effect size (Q3) | **The topic spec states the expected change and its source** (OM, literature, or an observed fault) against the measured MDC; the maintainer judges at Candidate → Admitted. No universal CV cut-off (CV is meaningless for metrics centred near zero). | 2026-10-02, v0.4 |
| D11 | Community proposals (Q5) | **Interim GitHub "Topic proposal" issue template** with §10's fields, bundles attached. Non-technical route deferred to the community-sharing work; same contents required. | 2026-10-02, v0.4 |
| D12 | Register format (Q6) | **Hybrid.** Markdown register authoritative for rationale and history; `docs/specs/topics/register.json` holds topic ids, statuses, topic-spec paths and the saturation allowlist; an agreement test prevents drift. | 2026-10-02, v0.4 |
| D13 | Topic help | **Every visible topic has a one-paragraph explanation behind a `?`**, kept outside code in one package markdown file, `slingology_eis/help/topics.md`, with placeholders (Spec 01 §8.8); required for admission; flight-summary line included. Research and removed topics need none. | 2026-10-02, v0.5 |
| D14 | `volts_min` | **Engine-running gate** (`min_rpm`), cause 2; low-voltage events with the engine running must still fire (Spec 09 acceptance 23). | 2026-10-03, v0.6 |
| D15 | `fuel_press_max` | **Cause 3a: allowlist entry + pilot filter**; profile keeps OM 46 psi; entry prompts a mechanic check (sender vs regulator). | 2026-10-03, v0.6 |
| D16 | `rpm_idle_min` | **Closed.** OM states 1,800 rpm as a minimum (915 i A OM table; OM-916 per the research paper). Keep the minimum and the `min_rpm: 1000` gate; add the idle-established condition (applies only after rpm has reached 1,800 since engine start); N117ZS's steady 20–30 rpm low idle is cause 3a (allowlist entry, pilot filter); profile note states the real rationale for `min_duration_s`. | 2026-10-05, v0.7 |
| D17 | `rpm_takeoff_max` | **Closed.** Cause 3a (prop-governor overshoot, constant-speed propeller confirmed). No OM transient allowance in the 5,800–5,900 rpm band; no resolution tolerance (10 rpm steps). Hard ceiling; pilot filter ≤ +30 rpm; allowlist entry citing the Maintenance Manual Line. | 2026-10-05, v0.7 |
| D19 | ENGINE ECU events | **CAS events, owned by `limit_exceedances`** (§4.1 generalised). `GROUND` events shown by default with `not_lane_check_reason`; user filters (duration) or acknowledges — no severity policy. Trends: frequency panel per classified CAS alert, built now (Spec 12 v0.10). Lane-check adherence not admitted → C6. Spec 03 §5.4 removed. Decided with four options discussed per point; the Trends panel was not deferred because "my aircraft shows nothing" is single-aircraft reasoning. | 2026-10-13, v0.12 |
| D18 | `engine_ecu_inflight` | **Admitted (provisional).** Prior E3 evidence (4, then 5 "in-flight" ENGINE ECU runs) withdrawn — a classifier defect, corrected in Spec 01 v0.19 (phase-based classes, minimum duration). Zero in-flight events on the full set (115 logs); two short `GROUND` runs (Spec 01 v0.20). Condition to close: first true `IN_FLIGHT` positive, or a deliberate injected-excerpt test. Single-aircraft action text removed from the audit and the engine. Full set (115 logs, Spec 01 v0.20): 0 `IN_FLIGHT`; 2 `GROUND` runs, both in one stationary ground run (2026-10-05 KBVS, 7 s and 8 s, 15 s apart, ~2,550 rpm, oil-pressure dropout in the second) — consistent with a lane check performed below the OM's 4,000 rpm; no ground faults. With the lane-check band sourced from the OM (v0.11, 4,000 ± 500 rpm on the 916iS) a third `GROUND` run appears: 2026-05-20 18:09:49 (11 s), the first half of a paired lane check in which rpm fell from ~4,300 to ~2,600–3,160 while the lane was off, pulling the run's mean below the band. | 2026-10-13, v0.10; evidence v0.11 |

## 7. Coverage view

Logged engine channels against the topics and limit checks that use them. A blank in the Topic column is a gap: it should be either a candidate or a recorded decision not to have a topic.

| Channel | Topics | OM limit checks | Gap / decision |
|---|---|---|---|
| `rpm` | `overboost_time` | idle min, takeoff max (5,800 rpm ceiling), overboost (5-minute rule) | — |
| `power_pct` | `overboost_time` | overboost (5-minute rule) | — |
| `map_inhg` | `map_at_takeoff` | MAP max | — |
| `egt1–4_f` | `egt_spread`, `egt_cyl_deviation`; `cylinder_rank` (context only, D4) | EGT max ×4, EGT split ×2 | — |
| `oil_temp_f` | `oil_temp_peak`; `climb_thermal_rate` (Research, D2) | takeoff min, max, optimal-band low | Candidate **C1**: oil-temperature optimal band / condensation (metric exists, not surfaced; 89.7 ± 13.3 % of airborne time below 194 °F across 50 flights) |
| `coolant_temp_f` | `coolant_temp_peak` | max | Candidate **C5** (with `oil_temp_f`): oil–coolant temperature balance — see below |
| `oil_press_psi` | — | min, max, cold max | Candidate **C2**: oil pressure vs. its own baseline at matched RPM and oil temperature — a classic bearing/pump wear observable, currently limits-only |
| `fuel_flow_gph` | — (flight summary only, §4.2) | (conditions the EGT split limit) | A5 fuel-flow model in Research (§4.2) |
| `fuel_press_psi` | — | min, max | Candidate **C3**: fuel pressure stability in flight (pump/regulator health), phase-aware for pump tests and tank switching. Note: both fuel-pressure limits fire on most flights (D6 diagnosis pending) — a topic needs to establish what normal looks like on this installation first |
| `main_volts`, `batt_amps` | — | volts min, max | Candidate **C4**: charging-system health (bus voltage and battery current under load). Note: the 9xiS ECU depends on electrical supply, which may make this a health topic rather than airframe-only. |
| `fuel_qty_l/r_gal` | — | — | **Decided: no topic.** Tank senders are attitude-sensitive and used only as a plausibility check (research paper §6.2, toolkit 0.6.0). |
| CAS string | `engine_ecu_inflight` | — | Other engine CAS alerts not yet classified — candidate for a later classification topic; each one admitted becomes a CAS event target (Spec 01 §8.6, D19) |
| lane-check pairing (`EcuAnalysis.lane_check`) | `engine_ecu_inflight` (summary line only) | — | Candidate **C6**: lane-check adherence over flights. Fails A2 as written — pilot procedure, not an engine signal. Would need a *procedure* class defined first (admission criteria for procedure metrics do not exist). Not admitted (D19). |
| Not logged: throttle position, lane A/B status, injector pulse width, ignition advance, wastegate position, T_plenum | — | — | **Out of reach (A1).** ECO/POWER inference (BACKLOG A4) is the only route, and it's blocked on a validation flight. |

C1–C5 enter the lifecycle (§8) as **Proposed**. None is admitted by being listed here.

**C5 — oil–coolant temperature balance (future exploration).** Successor to the dropped `oil_coolant_ratio` (D1). Hypothesis: on the 916iS the oil carries heat from the cylinder barrels, bearings and turbo to its own cooler, while the heads are liquid-cooled through the radiator, so a shift in the simultaneous oil − coolant difference could isolate a problem on one cooling path (oil-cooler blockage or airflow, turbo heat load, or the coolant side) before either temperature nears a limit. Before it can leave Proposed, research must answer:
1. **Is it used?** Does Rotax (installation, maintenance or service documentation), engine-monitoring practice or the literature use the oil–coolant relationship — on Rotax or comparable liquid-cooled engines — as a health indicator? If not, why not?
2. **What is the sourced mechanism (E2)?** What raises or lowers the difference, and what would a mechanic inspect in each case?
3. **What does a fault look like?** Any documented case giving an effect size to set against A7.

Starting data (v0.4 re-run): the cruise-phase mean of the simultaneous difference measured 19.9 ± 2.6 °F over 47 flights, minimum detectable change 5.1 °F, firing on ~6 % at z = 2. The peak-time difference (23.5 ± 6.6 °F) is too noisy; the old °F ratio is not a valid form.

## 8. Lifecycle

### 8.1 Stages

| Stage | Meaning | To enter it |
|---|---|---|
| **Proposed** | A question worth asking | A written proposal (§10): question, class, mechanism hypothesis, channels (A1, A2, A4 at E4 or better) |
| **Research** | Being measured | An experiment workspace (Spec 02 §5.1) or Explore mode (Spec 06), where the metric is computed but shown to no casual user |
| **Candidate** | Measured and argued | Availability, SD and MDC measured (A1, A7); overlap check done (A6); mechanism at E1/E2 (A4); action named (A5) |
| **Admitted** | Shown on every flight | Topic spec written (§9); **help entry written** (D13, Spec 01 §8.8); rule defaults in `insight_rules.json`; tests against the project logs; register entry complete; maintainer approval |
| **Unverified (on this engine)** | Runs and is shown, but no data from this engine type has validated it | Admitted on another engine type with the same mechanism (A2, A4) and inputs (A1). The pilot sees a short note on the topic's card or help that it hasn't yet been validated on their engine type (Spec 03 §5.2, Phase E). It becomes Admitted for that engine once data from it passes A7 |
| **Admitted (provisional)** | Shown, with one named open condition | As Admitted, plus the condition and the evidence that would close it (e.g. "first true positive", "≥ 5 departures above 2,000 ft") |
| **Deprecated** | Superseded or no longer passing | Register records the reason; rule `enabled: false` with a `_comment`; aliases kept for **one minor version** only |
| **Removed** | Gone from code | After the one-minor-version window; register entry stays, as history |

A topic can move back: an Admitted topic that fails a re-audit goes to Deprecated or Research, with the reason recorded.

### 8.2 Re-audit

The whole register is re-audited:

- whenever the number of real flights in the reference dataset has **doubled** since the last audit (A7's noise estimates and E3 evidence change with n), and
- before each research-paper edition, so the paper and the register agree;
- **whenever data from a new aircraft or a new engine type arrives** (v0.7). Every E3 finding and every cause-3a classification rests on one 916iS (N117ZS); a second aircraft can confirm or overturn them. A limit that saturates the same way on two airframes moves from cause 3a to cause 1 and gets a profile fix; a topic validated on a new engine type moves from Unverified to Admitted for it. Fleet workspaces (Spec 02 Q15) are the intended route for that data.

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
11. **Pilot explanation** — the one-paragraph help text (D13): what it checks, what it compares against, why it matters, what to do if it fires. Plain language, no values hard-coded (placeholders per Spec 01 §8.8), and **aircraft-neutral** (v0.8): every reader is a different owner, so the text states no finding from a particular aircraft's data (patterns seen, typical values, how often something happens), cites no number that isn't the OM's or a placeholder, and gives causes as possibilities, not as what usually turns out to be the case. It is the topic's section in `slingology_eis/help/topics.md`; the topic spec says what it must convey, and the help entry is reviewed with the topic spec.

**Spec 08 (cylinder balance)** is the first topic spec. It keeps its file and number — about 20 code comments cite "Spec 08 §N" — and is linked from the register for `egt_cyl_deviation` and `cylinder_rank`. It predates this template; items 2 (evidence grades), 5 (MDC) and 6 (overlap with `egt_spread`) would be added at its next revision.

Topics admitted before this spec have no topic spec. They are grandfathered **only** in that sense: the register entry and §6's audit stand in for one until the topic next changes, when it gets a full topic spec.

**Where topic specs live (D9, resolves Q2):** `docs/specs/topics/<topic_id>.md`, unnumbered and named after the `topic_id` — the same id as the rule and the register entry. Numbers stay reserved for platform specs. Spec 08 keeps its number and location to avoid churning code references; the register links to it.

## 10. Proposals, including from the community

A proposal is the same whoever writes it — the maintainer after a research session, or another Rotax iS owner who noticed something in their own logs. It contains:

- the question, in pilot language;
- why it matters on a FADEC engine (A2);
- the suspected mechanism, with whatever evidence exists (A4, any grade);
- which logged channels it would use (A1);
- if possible, example flights showing the pattern — shared as an anonymized results bundle (Spec 02 §7), never raw logs, consistent with no service-side storage.

How a non-technical owner submits one, and how bundles get shared, is deliberately not designed here. The point of fixing the proposal's contents now is that the bar doesn't change depending on how a proposal arrives.

**Interim route (D11, resolves Q5):** a "Topic proposal" issue template in the project's GitHub repository, with the fields above; example bundles are attached to the issue. The proper route for non-technical owners is designed with the community-sharing work, under one constraint: it carries exactly these contents, so the bar is the same whichever way a proposal arrives. Consistent with no service-side storage, neither route uploads raw logs anywhere.

## 11. Acceptance criteria for this spec

1. Every `topic_id` in `insight_rules.json` and every topic emitted by `evaluate_insights` has a register entry. Nothing is emitted without one, and no rule exists without one. Checked by a test against `register.json`, which a second test keeps in agreement with §5.2 on topic ids and statuses (D12).
2. Every Admitted topic has an evidence grade of E1 or E2 for its mechanism, recorded in its entry.
3. No OM-limit exceedance produces more than one insight on a flight (§4.1) — checked by a test against the project logs that includes a real exceedance (the 381 s overboost flight, `log_20260423_135821_KTOA.csv`: one `limit_exceedances` event and no `overboost_time` insight for it; and a synthetic oil/coolant exceedance).
4. No planning number (§4.2) produces an insight.
5. ✓ *Met in v0.4.* §6's audit numbers are re-run on the full local log set (Claude Code environment, 100+ logs), within the comparison scope each topic actually uses, and the A7 verdicts confirmed or revised. The re-run script stays outside the package; whether it becomes a committed audit tool for future re-audits (§8.2) is open.
6. §6.2's outcomes have a decision recorded — accepted, rejected, or deferred — each with a BACKLOG reference.
7. The research paper's analytics-modules section and this register agree on the topic list at the next paper edition.
8. **Nominal-flight test (D6, causes 1–2).** A synthetic flight following normal OM procedures — start, warm-up, run-up, takeoff at 5,800 rpm for under 5 minutes, climb, cruise, descent, landing, shutdown, with ordinary start and shutdown transients — raises **zero** limit events on every engine profile it applies to. Needs no log data; runs everywhere.
9. **Saturation test (D6).** On the full log set, every limit fires on at most half of admitted flights, unless it has an allowlist entry giving its cause-3 classification and the evidence (e.g. "`fuel_press_max` — steady +0.1–0.4 psi offset across all phases; sender reads high"). The allowlist lives in `register.json` (D12) — limit id, cause, evidence, register reference — so an exception can't be added without a recorded reason. Skips where the log set isn't present.
10. **Fingerprint regression tests (D6, cause 2).** Each fixed cause-2 gap gets a test that keeps it fixed — at minimum: no limit event lies wholly within ENGINE_START, WARMUP or shutdown, and no event is built from physically impossible values (e.g. 0.0 V bus with the engine running).
11. **Topic help (D13).** Every topic that produces a card on the Flight view — status Admitted in `register.json`, which excludes `cylinder_rank` (context only since D4) — has a help entry, and the flight-summary line has its own; Spec 01 acceptance 10 holds (all placeholders resolve for every applicable bundled profile). A Research, Deprecated or Removed topic needs none, and a help entry for a topic not in the register fails the agreement test.

## 12. Open questions

| # | Question | Leaning |
|---|---|---|
| Q1 | ~~(a) When a topic threshold mirrors an OM limit, should it still emit its own insight? (b) Does `egt_spread` need a baseline-deviation trigger alongside `egt_cyl_deviation`'s four?~~ | (a) **Resolved v0.2 — Option A** (§4.1). (b) **Resolved v0.4 (D8):** kept for its niche, folded into the cylinder insight when both fire. |
| Q2 | ~~Where do new topic specs live?~~ | **Resolved v0.4 (D9):** `docs/specs/topics/<topic_id>.md`, unnumbered; Spec 08 keeps its number. See §9. |
| Q3 | ~~Who estimates the change the mechanism implies, and how precisely?~~ | **Resolved v0.4 (D10):** the topic spec states it with its source; the maintainer judges; MDC is always reported. No universal CV cut-off — CV is meaningless for metrics centred near zero, and one number can't fit °F, psi and seconds. Applied already in D2 and D5. |
| Q4 | ~~Do topics that are about fuel planning rather than the engine belong in the per-flight topic set?~~ | **Resolved v0.2 — Option B:** no. Cruise nm/gal, cruise fuel flow and fuel burned move to a flight-summary line with no insights; the power × DA fuel-flow model (BACKLOG A5) enters Research. See §4.2. |
| Q5 | ~~How does a non-technical owner submit a proposal and example bundles?~~ | **Resolved v0.4 (D11):** interim GitHub issue template; the non-technical route comes with the community-sharing work, with the same contents. See §10. |
| Q6 | ~~Should the register stay in markdown, or become machine-readable?~~ | **Resolved v0.4 (D12):** both — markdown authoritative, `register.json` for what tests check, with an agreement test. See §5. |
| Q7 | ~~What should `map_at_takeoff`'s tolerance be?~~ | **Resolved v0.4 (D5):** 2 × the model's leave-one-out residual SD, with a fitted-range guard; the configured 20 hPa and the coded 1.5 inHg are both retired. See §6.1. |
| Q8 | ~~How does the register treat a limit that fires on (nearly) every flight?~~ | **Resolved v0.4 (D6):** the pilot keeps the existing tools; encoding and phase/artifact gaps are ours, enforced by acceptance 8–10. See §6.1, `limit_exceedances`. |

## Appendix A — Audit measurements

### A.1 Full log set (v0.4)

Source: `reports/spec10_audit_2026-10-01.md` (header). 50 admitted flights. MDC = 2 × SD (z = 2.0); within-band MDC only where n ≥ 10. No limit filters applied.

| Metric | Topic | Scope today | n | Mean | SD | MDC (all) | MDC (mild OAT / moderate DA) |
|---|---|---|---|---|---|---|---|
| `egt_spread_mean_f` | `egt_spread` | oat_band | 50 | 59.3 °F | 5.18 | 10.4 °F | 11.0 (n 40) |
| `egt1_deviation_f` | `egt_cyl_deviation` | oat_band | 50 | −31.1 °F | 5.38 | 10.8 °F | — |
| `egt2_deviation_f` | `egt_cyl_deviation` | oat_band | 50 | −8.5 °F | 5.81 | 11.6 °F | — |
| `egt3_deviation_f` | `egt_cyl_deviation` | oat_band | 50 | −6.9 °F | 4.06 | 8.1 °F | — |
| `egt4_deviation_f` | `egt_cyl_deviation` | oat_band | 50 | +46.6 °F | 4.88 | 9.8 °F | — |
| `oil_temp_max_f` | `oil_temp_peak` | oat_band | 50 | 202.3 °F | 12.18 | 24.4 °F | 23.5 (n 40) |
| `coolant_temp_max_f` | `coolant_temp_peak` | oat_band | 50 | 181.8 °F | 6.91 | 13.8 °F | 13.7 (n 40) |
| `oil_coolant_ratio` | `oil_coolant_ratio` | oat_band | 50 | 1.11 | 0.04 | 0.08 | 0.08 (n 40) |
| cruise-mean (oil − coolant) | (proposed redefinition) | — | 47 | 19.9 °F | 2.55 | 5.1 °F | — |
| `oil_temp_below_optimal_pct` | (C1 candidate) | none | 50 | 89.7 % | 13.26 | 26.5 pts | — |
| `cruise_nmpg` | (flight summary, §4.2) | da_band | 39 | 19.1 nm/gal | 1.49 | 3.0 | 3.0 (n 21) |
| `cruise_fuel_flow_gph` | (flight summary, §4.2) | da_band | 39 | 6.39 gph | 0.53 | 1.1 | 1.0 (n 21) |
| `climb_oil_rise_f_per_min` | `climb_thermal_rate` | none | 50 | 1.13 °F/min | 3.25 | 6.5 | by VS bucket: 3.2 / 8.8 / 14.8 |
| `climb_coolant_rise_f_per_min` | (unused) | none | 50 | −0.64 °F/min | 1.28 | 2.6 | — |
| `overboost_max_block_s` | `overboost_time` | none | 50 | 71.2 s | 57.6 | n/a (limit) | — |

Other counts: hottest cylinder stable 50/50, `hot_cyl_changed` 0; MAP model n 48, R² 0.75, 5 departures above 2,000 ft; IN_FLIGHT ECU events 5 under the pre-v0.19 classifier — **0 after D18**, with 2 `GROUND` runs (Spec 01 v0.20); overboost > 300 s: 1, ≥ 240 s: 2. OAT bands: 40 mild / 6 cold / 1 warm / 0 hot.

Insights fired across 50 flights (unfiltered): `limit_exceedances` 187, `egt_cyl_deviation` 9, `engine_ecu_inflight` 5 (pre-v0.19 classifier; 0 after D18), `climb_thermal_rate` 4, `coolant_temp_peak` 3, `cruise_efficiency` 3, `egt_spread` 2, `cruise_fuel_flow` 2, `overboost_time` 2, `map_at_takeoff` 1, `oil_coolant_ratio` 1, `oil_temp_peak` 1. Every rule id except `egt4_elevation` (disabled) and `flight_phase_mix` (enabled, never evaluated) was emitted; nothing was emitted without a rule.

### A.2 What changed from the v0.1–v0.3 snapshot

The v0.1–v0.3 audit used the project's `fleet_metrics.csv` snapshot: 23–24 flights, 2026-04-08 → 06-18, 28.2–66.3 hours. Against it, the full set:

- doubled the sample (24 → 50 flights; the §8.2 re-audit trigger);
- cut oil/coolant peak SD from 31.5 / 25.7 °F to 12.2 / 6.9 °F — the snapshot's spread was a duration artefact, not weather;
- left every other A7 verdict unchanged in direction (EGT metrics discriminating; climb rate not; ratio uninformative);
- quantified two findings the snapshot could only state: the MAP tolerance mismatch (1 vs 23) and limit saturation (fuel pressure on every flight).
