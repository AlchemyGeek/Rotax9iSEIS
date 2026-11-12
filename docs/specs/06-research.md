# Spec 06 — Research

**Project:** SlingologyEIS
**Status:** v0.6 — v1 (Sessions A and B) built on branch `research`; **v1.1 adds the per-flight levels — Signal view and Compare (§9, D8–D12) — Session C, to be built.** Decisions D1–D12 in §3 and Q1–Q13 in §16 closed.
**Suggested repo path:** `docs/specs/06-research.md`
**Builds on:** Spec 01 (§7 operations envelope, §8.7 series, §9 extension model, §10 privacy), Spec 02 (§5.3 workspace layout, §7 export/import), Spec 03 (principle 6: the Explore → operational path; §4 navigation shell), Spec 10 (§4 admission criteria, §8 lifecycle, §10 proposals; D2/D7 items parked as "Research"), Spec 12 (§13 deferred change-point detection), Spec 14 (§4, Q3)
**Revises:** Spec 03 §4 and §5 (Research becomes a destination; new view), Spec 02 §5.3 and §7.1 (a `studies/` document set, carried by export), Spec 01 §7 (Research operations), Spec 14 Q3 (closes: Research is designed)
**Acceptance case:** the N117ZS takeoff RPM/MAP oscillation investigation (Oct 29 2026, 121 logs, 98 full-power slices) — Appendix A

**Revision history**

| Version | Change |
|---|---|
| 0.6 | **Per-flight analysis (D8–D12, Nov 12 2026).** Research presented only the set level: one sentence, one chart, per-flight detail in a table. Two levels are added beneath it — **Signal view** (one flight, one or more channels, rolling swing and period strips over the whole flight to find *where* a signal cycles, click to set a window, window diagnostics: detrended trace, autocorrelation, spectrum, correlation-vs-lag) and **Compare** (the same analysis per flight over a selection, one row per slice grouped by flight, a chart of the values against date / engine hours / DA / OAT, a pinnable reference row, diagnostics on demand). The existing questions become summaries over Compare's rows. §9 rewritten; §11 gains `analyze_signal` and `compare_rows`; §12 study page restructured as Signal → Compare → Questions; the Flight view's *Research this window* lands on Signal mode; acceptance 14–18; §17 Session C. |
| 0.5 | **After Session B** (2026-11-07). Research is in the nav, gated by the `research` capability (Spec 03 v0.29 §4, §5.10; Spec 14 v0.19 Q3 closed). Research home, study page, aligned view, read-only studies with *Run this on my flights*, the three *Research this* entry points, inline help, and the Journal's `study_finding` entry (§10.3) are built; §11 gains `note_study_finding` and `forget_study_finding`, and `get_slice_samples` reads only the slices' flights. Acceptance 8 measured in-page (§5.5); 10 and 12 pass. Functional decisions of Session B in §3.3. Docs: concept page and walkthrough (§12). |
| 0.4 | **Q11–Q13 decided by the owner** (Nov 7 2026): acceptance 1 is pinned to flights dated through 2026-10-28; acceptance 2 states the period the app measures, **3.8 s (IQR 3.5–4.1)**, with the write-up's 4.4 s kept in Appendix A as the investigation's own figure from a different count; acceptance 5 asserts the two clean high-DA takeoffs stand out on rpm swing, and §7.4's ranking improvements (count of descriptors standing out, combined robust distance, ranking within the study's channels) are recorded as v2 work the §14.1 scan depends on. The two expected failures become passing tests. `docs/research/` is exempted from the repo's per-flight-detail rule by the owner (CLAUDE.md). Session B scope unchanged. |
| 0.3 | After Session A. Preset values **measured** over the acceptance set and recorded with the measurement (§5.2): full-power and governed-climb unchanged; stable cruise ≥ 300 s (was 120); idle confined to TAXI (was "on ground"); warm-up as a rule (rpm ≥ 1000, oil below the profile's takeoff minimum, within the ground phases, ≥ 60 s). §7.0 multipliers chosen (Q9): window 2.5 *P*, lag ±1.5 *P*, fallback 0.2 / 0.1 of the median slice duration. Q10: the small-group caution reuses `n_min` = 10. Functional decisions made in Session A recorded (§3.2). §11 lists the operations as built (adds `run_study`, `run_study_on_my_flights`, `get_research_progress`). Browser-mode build time measured (§5.5). Acceptance items 2 and 5 do not hold on the data as written; items 1's set needs pinning — proposed revisions Q11–Q13 (§16.1). |
| 0.2 | Q1–Q8 resolved (§16). Preset values are **measured in Session A** and recorded here (§5.2). Studies cache **per-slice descriptors** as derived data keyed by fingerprint and engine version; samples are never cached (§5.5, §10.1). Spec 10's Research-status items become **named v2 studies** once the condition-dependence test exists (§14.6); v1 only points at them. Hand slices are v1 via the Flight view's current zoom (§5.4). A study imports **read-only** when none of its flights are present, with *Run this on my flights* (§10.2). Test windows are **proposed from the data** — two-pass: dominant period first, then window and lag range from it, duration-scaled fallback (§7.0). The investigation write-up moves to `docs/research/` (Appendix A). Branch `research` (§17). |
| 0.1 | Initial draft. Research is the home of the third kind of analysis beside OM limits and trends: within-flight *signal shape* — what the oscillation investigation needed and neither existing lens could provide (§1). Seven decisions recorded (§3). Slice as the unit of analysis, condition rules with presets, four v1 tests, a fixed result contract, saved and shareable studies, API-first, nav placement with contextual entry points. Investigations (AI) and symptom detectors designed as future scope only (§14). |

**Note on numbering:** 06 was reserved for research mode since Spec 03 v0.8. 11 remains the paused "insights under the program principles" draft.

---

## 1. Problem

On 2026-10-24 the pilot of N117ZS felt a fore-aft surge in a calm-air climb after a touch-and-go. An investigation over 121 logs found that engine rpm under the Airmaster controller's Take-Off mode had been cycling ±90 rpm with a period of about 4 s (3.8 s by the app's estimators; 4.4 s in the original write-up), in lockstep with manifold pressure (±2.5 inHg), on **94 of 98 takeoffs since delivery** — 145 engine hours, unnoticed by a test pilot, a CFI and the owner. The mechanism was a limit cycle between the 916iS boost schedule and the electric governor; Airmaster recognised it from one email and a plot, and a firmware update followed. Appendix A summarises the case.

The app could not have found it, by construction:

1. **Limits** ask *did a value cross an OM line?* The cycle is a swing about a setpoint 100 rpm below the limit; whatever brief trace it left at the ceiling, Spec 09 v0.12 / Spec 10 D16–17 had deliberately classified takeoff rpm jitter at the 5,800 ceiling as something for a user magnitude filter. The system was designed to look past exactly this.
2. **Trends** ask *is my engine changing?* The swing was 180 rpm at 28 hours and 180 rpm at 145 hours. A self-referenced baseline would have called the oscillation normal. (A fleet of other 916iS aircraft would have shown it — none is available.)

The oscillation was visible only through physics (a governor holding a setpoint should not cycle) and through the *shape* of signals within a flight — periodicity, cross-channel correlation, lag. That is a third kind of analysis: not level, not drift, but **behaviour within a slice of a flight, compared across many slices**. The investigation did it with scratch scripts outside the app (`~/osc/` — Appendix A). This spec puts it in the app.

Two further facts shaped the design. The analysis took real understanding of control loops and the OM, which a pilot should not need: the sophisticated work belongs in a research workbench, and whatever it produces must be stated so that a smart pilot can check it against common sense. And the finding was useful because it turned into an *evidence package* — a per-takeoff table and a plot — that a manufacturer could act on in a day.

## 2. Goals

1. A pilot can reproduce the oscillation investigation inside the app, end to end, from "this takeoff felt odd" to a per-slice table and a one-sentence finding, without writing code.
2. The **slice** — a window of a flight selected by rule, phase or hand — is the unit of analysis; every test runs on a *set* of slices drawn from any selection of the workspace's flights.
3. Statistical tests are phrased as questions a pilot asks, and answer in one fixed shape: a sentence, a chart, a magnitude against a visible reference, caveats, and a machine-readable block (§8).
4. Research ships **no rules and no verdicts**. The only built-in references are OM values already in the engine profile; everything else is derived from the user's own slices or typed in by the user (program principle 1).
5. A Research session is a **study**, saved in the workspace and shareable as a file; a recipient re-runs it on their own copies of the logs.
6. Every Research capability is an **operation first** (Spec 01 §7 envelope), callable from the page, the CLI and — later — a client-side agent. The UI adds nothing the API cannot do.
7. Research has a defined path *out*: a finding becomes a Journal entry carrying provenance, evidence for a Spec 10 topic proposal, or (future) a shared symptom detector. Research is upstream of the operational views, never woven into them (Spec 03 principle 6).

**Non-goals for v1** (designed here, built later — §14): the splicer with free drag alignment, expression-language slice rules, the remaining tests of the catalogue (§7.5), a scheduled automatic scan with recurrence thresholds, Investigations (AI-driven research), symptom detectors. Not in scope at all: any change to limit checking, insights or Trends ranking; any server-side storage or service.

## 3. Decisions

| # | Decision | Rationale |
|---|---|---|
| **D1** | **The slice is the unit of analysis.** A slice is a time window of one flight, made by a condition rule, a phase, or by hand; all three produce the same object. Tests take a *set of slices*. | The investigation was "every segment with rpm ≥ 5550 for ≥ 15 s across 121 logs → 98 slices". The pilot thinks in pieces of flights, not in sampling windows; one abstraction makes every test accessible and makes slice sets reusable across questions. |
| **D2** | **v1 scope: slices and tests first.** Condition slices, the descriptor set, four tests (§7.1–7.4), and the aligned overlay / small-multiples view as the minimum visual. The splicer waits (v2). | Reproducing the investigation is the acceptance test, which needs slices and tests, not the splicer. Visual-first would add no analytical capability and give Code nothing to validate against. |
| **D3** | **Studies are saved in the workspace and shareable.** A study references logs by fingerprint, never by path or content; a recipient re-runs it on the logs they hold and sees fewer slices for logs they lack. | Same model as workspace export (Spec 02 §7): configuration and decisions travel, analyses are recomputed. A study is small, so it can go to a manufacturer or another owner alongside the evidence package. |
| **D4** | **Slice rules are structured, with shipped presets.** One or more channel conditions ANDed, a minimum duration, a merge gap, an optional phase constraint (§5.1). Presets (full-power segment, governed climb, stable cruise, idle, warm-up) are ordinary saved rules the user may edit (§5.2). A slice carries **all channels** for its window plus context; channels are chosen at test time, not slice time. | A form maps directly to a declarative study file and to a future agent's tool call. Presets make the first five minutes work for a pilot and double as the standard slice types for an automatic scan. An expression language is the thing a non-statistician won't write; it can be added later as an advanced field without changing the format, since a rule is data either way. |
| **D5** | **One result contract: evidence against a visible reference, no verdict.** Finding (one sentence with recurrence), Evidence (chart + per-slice table), Magnitude (effect size beside its reference), Caveats, machine-readable block (§8). References are the OM value from the engine profile where one applies, otherwise the spread of the same measure across the other slices in the set, plus any reference the user types in for the study. | A shipped threshold ("cycling / steady") would be a non-OM rule — what the Oct 4 2026 program reset removed. Evidence alone leaves "is that a lot?" unanswered; a visible comparison answers it without us judging. The same contract is what a future Investigator consumes, so it is designed once. |
| **D6** | **Overlay alignment is rule-based: the slice condition's crossing is t = 0 by default**, with selectable anchors (slice start, slice end, peak of a channel, phase boundary); shared x in elapsed seconds, shared y per channel. Free drag alignment is the v2 splicer; the study format reserves a per-slice offset field from v1 so v2 adds no format change. | The crossing is the physically meaningful instant (the oscillation starts when rpm passes ~5600; a touch-and-go reaches it in 2 s, a normal takeoff after 20 s of roll) and every anchor is a rule, so a study reproduces the view. |
| **D7** | **Research is a top-level destination with contextual entry points.** A nav item "Research" lists the workspace's studies and the presets; "Research this" actions on Flight view, Trends cards and events open a study pre-seeded with that flight, metric or event. | Spec 03 principle 6 and Spec 14 Q3 require a distinct destination. Most pilots will first arrive from context — "this takeoff felt odd" → Research this → full-power slices across every flight — which is the KBLI moment made into a button; a hypothesis-first researcher needs a door of their own. |
| **D8** | **Research has three levels: Signal (one flight), Compare (rows per flight), Questions (summary over rows).** The set-level questions remain; the two levels beneath them are added, built on the same per-slice descriptors. | The hunting problem is first *looked at* on one flight, then compared across flights, then summarised. v1 skipped the first two; the per-slice table was the only trace of them. |
| **D9** | **Signal view starts from the whole flight with rolling strips; clicking a strip sets the window.** | Answers "where in this flight does it hunt?" without the user knowing beforehand; the window diagnostics then follow. Window-only would assume the answer. |
| **D10** | **Two rolling strips — swing and dominant period (with prominence) — computed as the slice descriptors are, on a sliding window sized by §7.0.** A rolling-correlation strip for a pair is v2. | Swing says how big, period says whether it repeats; a throttle change has swing but no period, a hunt has both. Same computation as the descriptors, so a strip value and a slice value agree. |
| **D11** | **Compare rows are per slice, grouped by flight, collapsible to one row per flight (median, count shown).** The window chosen in Signal view becomes a rule so the matching window is found in every selected flight; hand windows compare as single slices. | A touch-and-go session has several takeoffs and the before/after needs every one; the pilot still reads it per flight. Rows are the descriptors the questions already use, so the questions stay a summary over level 2. |
| **D12** | **A Compare row shows the analysis values and conditions; the chart plots any value against date, engine hours, DA or OAT; one row can be pinned as the reference and the rest shown as differences from it; diagnostics open as an expandable panel for selected rows.** Signal and Compare are sections of the study page; the Flight view's existing *Research this window* opens a study in Signal mode on that flight with the window set. | Table and chart are the comparison; pinning makes before/after a one-click reading; diagnostics on demand keep the page readable above ~20 rows. One saved study records look → compare → summarise; the Flight view gains nothing new. |

### 3.1 Positions recorded during the discussion (not decisions of this spec, but constraints on it)

| Topic | Position |
|---|---|
| What the third analysis is | It was first framed as a new operational lens ("Behaviour", then "Symptoms") with shipped signature detectors. Reframed: the sophistication belongs in Research; detectors, if any, are *products* of research, built and shared by people who understand the mechanism — never shipped by the app. §14.3. |
| Privacy | The owner's concern is not data locality as such but **never operating a service that stores data on behalf of others**. A future Investigator therefore connects to the user's own AI provider with the user's own key; nothing is relayed through or stored by us. §14.2. |
| Trust | Any automatic finding must be stated in simple language that a smart user can validate from common sense and their own knowledge. This is why D5 fixes the result contract now. |
| Noise | Automatic output surfaces only when a pattern is **established across multiple flights** — N of M slices, both visible and tunable. One-off events are the limits/events layer's job, not Research's. §14.1. |
| Naming | "Insights" is taken by the deterministic layer. The AI capability is **Investigations**, future. The present work is **Research**. |

### 3.2 Functional decisions made in Session A

| Topic | Decision |
|---|---|
| Flight reference | Studies, hand slices and the cache name flights by `flight_id` — the hash of the fingerprint (Spec 01), which is what every other operation takes. Still never a path or content. |
| Cache key | Per flight: `flight_id`, the analysed log's `source_key` and the engine version; per rule: a hash of the rule body (a renamed rule keeps its cache, an edited one doesn't); per descriptor: the resolved window, lag range, reference channel and prominence floor. Any mismatch recomputes. The cache also records which channels were looked for, so a channel added later is read rather than taken as absent. |
| Slice identity | `<flight_id>:<rule hash>:<start>-<end>`; hand slices `<flight_id>:hand:<start>-<end>`. Stable across runs and machines. |
| Slice end and anchor | `end_s` is exclusive; the anchor (D6 crossing) is the first second the rule's conditions all hold, before padding. |
| Merge gap | Two runs merge when the hole between them is shorter than `merge_gap_s`. |
| "No slice spanning two phases" (§5.2) | Read as no slice spanning two *instances of the manoeuvre* (two takeoff rolls, two taxi segments). A full-power slice necessarily covers TAKEOFF_ROLL → CLIMB. |
| Preset values from the profile | A preset condition may name a profile limit instead of a number (`{"profile_limit": "oil_temp_takeoff_min"}`); the warm-up preset uses it. A profile without that limit doesn't offer the preset. |
| Preset ids in requests | Wherever a rule is accepted, a preset id (`"full_power"`) or `"phase:<PHASE>"` stands for the rule. A saved study stores the full rule, so it travels unchanged to a workspace or engine version whose presets differ. |
| Default DA and OAT edges | §7.3's split by DA or OAT band uses the fleet bands (Spec 12) unless the study gives edges; group labels read "below X", "at X–Y", "at X and above". |
| Unusual (7.4) per source | Robust z is taken within each source when every source has at least `n_min` slices, else across the set (said in the caveats), so G3X's damped channels don't make every AXIS slice stand out. A descriptor with zero MAD falls back to the mean absolute deviation; one with no spread at all is skipped. |
| Per-test errors | In `run_study`, a test that can't run (too few slices, channel absent) records its error and the others still run. |
| Import of an "all" study | An imported study whose selection was "all flights" is pinned to the sender's flights that are present; *Run this on my flights* is the way to widen it. |
| `.eisstudy` | A zip: `study.json`, `evidence/NN-<test>.csv`, `charts/NN-<test>.svg`. The chart is an SVG drawn by the engine (no plotting library in the browser runtime). |
| Workspace export | `studies/*.json` is carried; tests' results, the cache and the last-run summary are derived and stripped, except in a read-only study, where the sender's results are the study. |
| Lag sign | Positive lag: the channel follows the reference by that many seconds. |
| `time to reach a level` (§6) | Not computed in v1: no v1 test uses it and its level is a test parameter. Kept in §6 for §7.5. |
| Periodogram | Lomb–Scargle in numpy (the browser runtime has numpy and pandas only); used as the cross-check of §6, not as the estimate. |

### 3.3 Functional decisions made in Session B

| Topic | Decision |
|---|---|
| Journal path out (§10.3) | Two operations, `note_study_finding(study_id, test_index, note?)` and `forget_study_finding(ref_id)`. The entry (kind `study_finding`, ref `<study_id>:<test_index>`) carries the finding verbatim and links to the study; one entry per study and question, re-noting after a re-run replaces it. Removing the entry never touches the study. Recorded in Spec 14 §6.1. |
| Aligned view reads only its slices' flights | `get_slice_samples` narrows the build to the flights named by the requested slice ids (a slice id starts with its `flight_id`, §3.2) instead of the study's whole selection, so changing anchor or channels costs the slices' flights, not a workspace pass. Samples are still never cached. |
| Evidence package (§10.3) | One Markdown file: per question the finding, magnitude and reference, caveats, and the per-slice table as CSV inside a code block; downloaded from the page. The per-slice CSV alone is also downloadable from each card. The `.eisstudy` zip (§3.2) stays the machine-readable export. |
| "Research this" seeds (§12) | A seed is stashed in session storage and consumed by `/research/new`, never by URL, so a seed carrying flight ids is not shareable or bookmarkable. Flight view: the chart's current zoom as a hand slice with the first visible channel's cycling question; the full-power preset is *suggested*, not added, when the window covers a takeoff. Trends: the metric's recent flights vs the rest as a two-group split (`split.by = "flights"`, the one split kind that names explicit groups) on the metric's channel, in the metric's natural slice rule. Events: the event's window by hand (±10 s) plus a rule `channel ≥/≤ limit` with 10 s pad across every flight. |
| Trends and Events entry points need data | *Research this* on a Trends card appears only on a card with a shift (nothing to compare otherwise) and only when the host offers the research capability; on an Events row always, when the capability exists. |
| Research home pointer (§14.6) | Plain text naming the three open questions with a link to Spec 10 on GitHub; no study is created. |
| Read-only study (§10.2) | The label *Sender's results — none of these flights are in this workspace* sits above the results; every editing control is disabled rather than hidden, so the page reads the same; the one enabled action is *Run this on my flights* (`run_study_on_my_flights`), which navigates to the new study. Export of a read-only study exports the sender's file unchanged. |
| Inline help (Spec 14 §7.4) | Seven Research items join the registry: the four questions, reference, slice rule and selection; one sentence each, aircraft-neutral, verdict-free (acceptance 9 has a UI test over the page's own strings). |
| Small-multiples threshold | Overlay up to 10 slices, small multiples above; the user can toggle either way. The scrubbing cursor is ECharts' linked axisPointer. |

## 4. Concepts

**Slice.** A contiguous time window of one flight: `flight_id`, source fingerprint, start/end offsets, every channel's samples in the window, and context — source (G3X/AXIS), phase(s) covered, pressure and density altitude, OAT, engine hours, start time. Slices are derived data: recomputed from the logs, never stored (only their *definitions* are).

**Slice rule.** The definition that produces slices from a flight: conditions, minimum duration, merge gap, phase constraint (§5.1). A **preset** is a shipped slice rule.

**Slice set.** The slices a rule (or a phase, or hand selection) produces over a **selection** of flights — all flights in the workspace, or a subset chosen by the user. The input to every test.

**Descriptor.** A number computed per slice per channel (§6): level, spread, peak-to-peak, dominant period, correlation with a reference channel, and so on. Descriptors are what tests compare.

**Test.** A question applied to a slice set, returning a result in the §8 contract. Tests are pure functions of slices, descriptors and parameters.

**Reference.** What a magnitude is shown against: an OM value from the engine profile, the spread of the same measure across the other slices, or a user-typed value with a label.

**Study.** The saved record of a Research session: selection, slice rules, tests with their parameters, user references, notes, and cached results (§10).

**Scan.** The automatic form of §7.4: standard descriptors over preset slice types, ranked by unusualness. Present in v1 as a user-initiated test; scheduled and recurrence-gated in v2 (§14.1).

## 5. Slices

### 5.1 Condition rules (D4)

A rule has:

- **Conditions** — one or more, ANDed; each is a registry channel, an operator (`≥ > ≤ < = between`), and a value or range in the channel's display unit. Channels come from the Spec 01 §6.4 registry, so AXIS and G3X logs are handled alike.
- **Minimum duration** — the window must satisfy the conditions for at least this long (seconds).
- **Merge gap** — brief drops below the condition shorter than this are bridged (seconds), so a 1 s dip does not split a slice in two. Same idea as Spec 09 §6.2's exceedance merge gap.
- **Phase constraint** — optional: only windows overlapping chosen phases (Spec 01 phase model), or only within a chosen phase.
- **Pad** — optional seconds added before the first and after the last satisfying sample, so the onset of a condition is visible in the slice (default 0).

A rule is JSON; the form and the API share it. The study stores the rule, not the slices.

### 5.2 Presets

Shipped as editable rules. Only the full-power rule is validated (the acceptance case). The other values were **starting points**; Session A measured each candidate rule over the full log set — slice count, slices per flight, duration distribution, agreement with the phase engine's count for the matching phase — and the chosen values and the measurement are recorded here, the way Spec 10 recorded its audit (Q1). The acceptance rule for a preset: about one slice per flight that contains the manoeuvre, durations in a plausible band, no slice spanning two phases. Presets with rpm bands are per engine profile; profiles other than the 916iS carry the 916iS values marked *unverified*, as Spec 10 §5.1 marks topic status. Preset parameters are documented on the docs site.

| Preset | Rule (measured, v0.3) | What it isolates |
|---|---|---|
| Full-power segment | `rpm ≥ 5550`, ≥ 15 s, merge 3 s | Takeoff and go-around power — the acceptance case |
| Governed climb | `rpm between 5300 and 5500`, `vertical speed ≥ 300 fpm`, ≥ 60 s, merge 5 s | Climb mode under the governor |
| Stable cruise | within CRUISE, `rpm between 4800 and 5300`, ≥ 300 s, merge 5 s | Steady-state cruise |
| Idle | within TAXI, `rpm < 2200`, ≥ 30 s, merge 3 s | Idle quality |
| Warm-up | within ENGINE_START, WARMUP or TAXI, `rpm ≥ 1000`, oil temperature below the profile's takeoff minimum (`oil_temp_takeoff_min`, 122 °F on the 916iS), ≥ 60 s, merge 5 s | Warm-up behaviour |

**Measurement (Q1, Session A, 2026-11-07).** Over the acceptance set — the 60 admitted N117ZS flights dated through 2026-10-28 (§15 item 1). Durations in seconds. "Phase count agrees" is the number of flights whose slice count equals the phase engine's count of the matching phase.

| Preset | Slices | Flights with a slice | Max per flight | Flights with > 1 | Duration min / p10 / median / p90 / max | Matching phase | Phase count agrees | Spanning two instances |
|---|---|---|---|---|---|---|---|---|
| Full-power segment | 98 | 59 | 9 | 21 | 31 / 41 / 54 / 72 / 377 | TAKEOFF_ROLL (69) | 39 | 0 |
| Governed climb | 92 | 48 | 7 | 20 | 63 / 73 / 126 / 301 / 923 | CLIMB (385) | 5 | 0 |
| Stable cruise | 108 | 38 | 10 | 24 | 306 / 340 / 712 / 3286 / 10426 | CRUISE (399) | 6 | 0 |
| Idle | 161 | 59 | 7 | 41 | 30 / 39 / 95 / 235 / 1263 | TAXI (104) | 19 | 1 |
| Warm-up | 44 | 44 | 1 | 0 | 134 / 162 / 256 / 324 / 417 | WARMUP (82) | 32 | — |

What the measurement showed, preset by preset:

- **Full-power segment** — unchanged. The flights with several slices are touch-and-go sessions (up to 9 takeoffs); the phase engine labels one TAKEOFF_ROLL per landing sequence and misses touch-and-go rolls, so the per-flight disagreement is the phase engine's, not the rule's. No slice covers two takeoffs. The two long blocks (Phase-1 extended full-power, 377 and 273 s) are included.
- **Governed climb** — unchanged. The phase engine's CLIMB is fragmented (385 segments, median rpm 5400 inside them), so its count is no yardstick; a climb interrupted by a level-off is two slices, which is the manoeuvre. No slice overlaps a takeoff roll or a descent.
- **Stable cruise** — minimum raised from 120 s to 300 s. At 120 s the rule gave 211 slices with up to 25 per flight (every power change in a cross-country cut cruise into pieces); at 300 s it gives the steady stretches. Flights with more than one remain the long cross-countries with power changes. Durations are long (median 12 min), which is what the duration-scaled windows of §7.0 are for. 22 flights have no cruise of 5 min (pattern work).
- **Idle** — "on ground" made concrete as *within TAXI*: over all ground phases 14 slices ran from before-takeoff taxi through the run-up into the next taxi; within TAXI one does. Several slices per flight are the taxi-out and taxi-in.
- **Warm-up** — the initial "from start until oil reaches the target" written as a rule. The phase engine's WARMUP alone gives no slice of ≥ 60 s (its segments are short and interleaved with TAXI), hence the three ground phases. One slice per flight at most; the 16 flights without one started warm (oil already at the takeoff minimum).

Presets are per engine profile where values depend on the engine (rpm bands); the 916iS values above are the first set. A pilot may duplicate and edit a preset; the copy becomes a workspace rule.

### 5.3 Phase slices

Any phase from the Spec 01 phase model is a slice rule with no conditions: "all climbs", "all takeoff rolls". Available alongside presets.

### 5.4 Hand slices (v1 minimum)

A hand slice is `flight fingerprint + start/end offsets`, named. v1 (Q4): on Flight view, *Research this* takes the chart's **current zoom range** as the slice — no new selector — and adds it to a new or existing study; the engine, CLI and study format accept hand slices from Session A, the UI arrives in Session B. The natural v1 pattern is a hand slice as the highlighted member of a rule-built set ("this takeoff against all takeoffs"). Alignment uses D6's anchors (default: slice start). Free drag alignment, trimming and moving slices between studies are v2 (§14.4); the format carries `offset_s` per hand slice from v1, default 0. If Session B runs long, the UI part slips without a spec change.

### 5.5 Computation

Slicing needs raw channel data, which Spec 01 discards after `analyze_flight`. Research re-parses logs on demand through the `LogSource` abstraction (Spec 04), streaming flight by flight with progress, and keeps only the slices' samples. A rule over the whole workspace is therefore a full pass over the logs; on the 120-log N117ZS set this is the same cost as the Spec 04 parity run and is acceptable with progress shown. Measured in Session A on the 60-flight acceptance set (full-power rule plus test 7.1): about 6 s in server mode and 12 s in the browser's engine (Pyodide under Node.js, the same wheel the page loads); a re-run from a study's descriptor cache, 0.1 s. **Acceptance 8 (Session B, in-page):** headless Chromium against the static build, 122 logs picked as a folder, the acceptance set (60 flights through 2026-10-28): engine ready 5.4 s; first scan 133 s (the Spec 04 import path, once); full-power slice build cold **14.5 s** with progress shown; `run_study` (slices + cycling) 13.7 s; from the descriptor cache 0.16 s; samples for 12 slices 14.1 s (the slices' 12 flights re-read); heap 291 MB; no page errors (`spike/browser-host/run_research_timing.py`, results in `spike/browser-host/results/research-timing.json`, aggregates only).

**Descriptor cache (Q2).** A study stores its slices' **descriptors** (§6 — a few KB per slice) as derived data, keyed by each slice's log fingerprint and the engine version. Opening a study shows tests and tables at once; only the aligned view, which needs samples, re-parses — and only the slices' flights, not the workspace. A cached entry whose fingerprint or engine version no longer matches is discarded and recomputed, never trusted. Samples are never cached. The study file is valid without the cache.

### 5.6 Sampling and source caveats (carried into every result)

- Logs are 1 Hz (AXIS resampled from ~0.83 Hz at the loader, Spec 01 §6.5). Periods below about 3 s are unreliable and faster oscillations alias; the cycling test states this bound.
- The G3X damps some channels (manifold pressure ripple 2 inHg vs 5–7 inHg on AXIS for the same oscillation; rpm identical). Source is a **facet** on every slice; tests report per source when both are present and never pool a damped channel across sources without saying so.
- Filled rows from AXIS resampling are flagged in the slice and excluded from rate and period descriptors.

## 6. Descriptors

Computed per slice, per channel the test asks for. All robust variants are available because 1 Hz engine data has outliers and quantisation (rpm in steps of 10).

| Group | Descriptors |
|---|---|
| Level | mean, median, min, max, value at anchor |
| Spread | standard deviation, MAD, **peak-to-peak** (median over a rolling window whose length is proposed from the data, §7.0 — the investigation's 12 s "swing"), interquartile range |
| Shape | linear slope over the slice, max absolute rate of change, time to reach a level from the anchor |
| Periodicity | **dominant period** and its prominence, from the detrended autocorrelation (first peak beyond lag 1) with a periodogram cross-check (Lomb–Scargle, tolerant of gaps) |
| Coupling | **zero-lag correlation** and **lag of maximum correlation** with a reference channel (default: rpm), over a lag range proposed from the data (§7.0) |
| Quality | sample count, duration, filled-row share, dropouts |
| Context (per slice, not per channel) | source, phase(s), pressure altitude, density altitude, OAT, engine hours, start time, flight id |

The per-slice descriptor table *is* the evidence table of §8 — the app's version of Appendix A's table.

## 7. Tests — v1

Each test: the question it answers, inputs, method (functional — Code chooses implementation), what the result says, its reference, and what it would have shown on the acceptance case.

### 7.0 Windows and lag ranges are proposed from the data (Q7)

No test carries a static window. Two passes:

1. **Period first.** The dominant period and its prominence (§6) are estimated on the whole detrended slice — they need no window. The period search is bounded above by a fraction of the slice duration so a trend is never read as half a cycle, and below by the sampling floor (§5.6).
2. **Derive from it.** When the slice set has a prominent median period *P*: peak-to-peak window ≈ 2–3 *P* (whole cycles, so it measures swing rather than noise); lag range ≈ ±1.5 *P*. When no prominent period exists (steady cruise, thermal channels): window = a fraction of the median slice duration, lag range likewise, both bounded below by the floors.

Floors are fixed at the acceptance case's values — 12 s window, ±10 s lag — so that case reproduces exactly (3.8 s × 2.5 ≈ 9.5 s; ±1.5 × 3.8 ≈ ±6 s, both below the floors, so the floors apply). The **resolved values are printed on every result card** as part of the Magnitude/Caveats (§8) and are overridable per study. Code chooses the exact multipliers within these bands and records them in this section.

**Chosen (Q9, Session A).** Window = 2.5 *P*, lag range = ±1.5 *P*, both rounded to whole seconds and floored at 12 s / ±10 s. *P* is the median period over the set's slices with a prominent period, used when at least half the slices have one; otherwise window = 0.2 × and lag range = 0.1 × the median slice duration, with the same floors. The period search runs from 2 s up to a third of the slice; a period below 3 s is never counted prominent (§5.6); prominence is half the ACF's peak-to-trough height, prominent at ≥ 0.2 with the Lomb–Scargle peak within 20 %. On the acceptance case the windows resolve to the floors (12 s / ±10 s); on the stable-cruise set to 142 s / ±71 s. 2.5 *P* is the middle of the band — two whole cycles plus margin for the period's spread across slices; 1.5 *P* lets the lag search see a full half-cycle either side without folding onto the next cycle. The fractions keep the window well inside the shortest slices of a duration-scaled set. The resolved values and their basis (period, duration, or override) are in every result's block and caveats.

### 7.1 Is this signal steady, or is it cycling?

- **Inputs:** slice set, one channel. Parameters: peak-to-peak window (proposed per §7.0), minimum prominence for a period to count.
- **Method:** per slice, detrend; compute peak-to-peak, dominant period and prominence (§6). Summarise over the set: median and IQR of period and swing; the count of slices with a prominent period ("recurrence").
- **Finding:** "RPM cycles every 3.8 s (IQR 3.5–4.1), swing 180 rpm (170–190), in 93 of 98 full-power slices."
- **Reference:** the OM limit for the channel if one exists (rpm 5,800 shown on the chart as headroom from the swing's top); the swing distribution across the set; user reference (e.g. "governing band ±100 rpm", typed in with its source).
- **Caveats:** period floor from sampling (§5.6); per-source split.
- **Acceptance case:** reproduces Appendix A's headline.

### 7.2 Do these two move together, and who leads?

- **Inputs:** slice set, channel A, channel B. Parameter: lag range (proposed per §7.0).
- **Method:** per slice, detrend both, cross-correlation over the lag range; report zero-lag correlation and lag of maximum correlation. Summarise: median correlation, distribution of lag, per source.
- **Finding:** "Manifold pressure follows RPM with no delay (median correlation 0.93 on AXIS slices, 0.2 on G3X slices — see caveat); fuel flow follows 1 s behind."
- **Reference:** none from the OM; the correlation distribution across the set is the comparison; the result says what a correlation does not mean (direction of cause).
- **Acceptance case:** reproduces the rpm–MAP 0.89–0.97 (AXIS) / 0.1–0.3 (G3X) split and the 1 s fuel-flow lag.

### 7.3 Are these two groups different?

- **Inputs:** two slice sets (or one set split by a context variable: source, DA band, OAT band, date range, before/after a chosen date), one descriptor.
- **Method:** robust effect size (median difference and Cliff's delta) with a rank test for support; plotted as two distributions side by side. No p-value as the headline.
- **Finding:** "Swing is 180 rpm below 3,000 ft DA and 75 rpm above 6,000 ft DA (93 vs 2 slices — small group)."
- **Reference:** the two groups are each other's reference; small-n cautions when a group has fewer than `n_min` = 10 slices (Q10 — the Spec 12 A4 constant, reused).
- **Acceptance case:** the DA-band table of Appendix A; this is also the before/after test for the Airmaster firmware update.

### 7.4 Which of these slices is unusual?

- **Inputs:** slice set, channels (default: rpm, MAP, fuel flow, EGT1–4, CHT, oil pressure and temperature, coolant temperature, fuel pressure, volts).
- **Method:** compute the standard descriptor set per slice; robust-z each descriptor against the set; rank slices by their largest |z| and list the descriptor responsible. Cap the list.
- **Finding:** "2 of 98 slices stand out: 2026-07-17 18:19 and 2026-07-23 18:12 — swing far below the rest (70–80 rpm vs 180) and MAP flat at 51.4 inHg."
- **Caveats, stated on the card:** this finds *difference*, not *wrongness* — on the acceptance case the outliers are the two **clean** high-altitude takeoffs, because the oscillation was the norm. Scanning many descriptors guarantees some spurious hits; the list is ranked, capped, and never called a defect.
- **Acceptance case:** lists the KBIL/KHLN slices among those standing out, on rpm swing (Q12). As written they rank 19th and 22nd: with twelve channels, 51 of 98 slices stand out on *something*. **v2 (Q12):** rank by the number of descriptors standing out and their combined robust distance rather than a single largest |z|, and rank within the channels the study's other tests use — on the acceptance case the two clean takeoffs are odd in two dimensions (swing and MAP ceiling) and would then rank first. The §14.1 scan depends on this.

### 7.5 Catalogue for later versions (designed, not built)

| Question | Method | Catches |
|---|---|---|
| Is this response damped or self-sustaining? | Decay of the autocorrelation envelope; step response (overshoot, settling) after throttle changes | Governor/loop health — distinguishes a disturbance that settles from a limit cycle |
| Is this what the OM says it should be? | Residuals against the engine-deck MAP vs rpm by DA and against fitted models (Spec 12 §8.2 `takeoff_map_residual_inhg` is the first) | Boost control at its ceiling, wastegate issues; residual *shape* (oscillating vs stepped) |
| When did it change within the flight? | Change-point detection on mean and variance (CUSUM / binary segmentation; Spec 12 §13 deferred CUSUM) | Lane switch step in EGT, injector drop-out, oil pressure step, onset of an oscillation |
| Is this cylinder behaving like the others? | Common-mode removal across EGT1–4 (first principal component), then per-cylinder transient dips and drift | Misfire, injector, ignition imbalance; complements Spec 08 |
| Does it depend on conditions? | Descriptor vs DA, OAT, wind; Spearman correlation and stratified plot | Cause hunting — the DA dependence of the oscillation |
| Is the sensor or log healthy? | Dropouts, stuck values, quantisation, noise floor by source | Instrument artefacts before they are mistaken for engine behaviour |

Spec 10's items parked as Research — `climb_thermal_rate` (D2), the A5 fuel-flow model (§4.2), peak temperature predicted from airborne time (D7) — become named v2 studies once the condition-dependence test exists (Q3, §14.6). v1 does not seed them: answering them with the two-group test would be the wrong tool, and a half-answer on `climb_thermal_rate` could read as a verdict.

## 8. Result contract (D5)

Every test returns the same five parts; the UI renders them in this order and the study stores the block.

| Part | Content |
|---|---|
| **Finding** | One sentence in pilot language, always containing the recurrence count ("in 94 of 98 slices") and the per-source split when sources differ. |
| **Evidence** | The chart appropriate to the test (aligned slices, distribution, scatter), and the **per-slice table** — every slice's descriptors and context — one click away and exportable (CSV). |
| **Magnitude** | The effect size, shown beside its **reference**: OM value from the engine profile; the set's own spread; a user reference with its label and source. Never a bare statistic. |
| **Caveats** | Fixed items (sampling floor, source differences, group size) plus the test's "what this does not mean" sentence. |
| **Block** | JSON: test id and version, parameters, slice-set definition, per-slice descriptors, summary statistics, references used, engine version. What a study saves and what a future Investigator reads. |

Nothing in the contract is a verdict. The only shipped numbers are OM values already in the profile.

## 9. The three levels: Signal, Compare, Questions (D8)

Research works at three levels on the same per-slice descriptors (§6). v1 built the third; v1.1 adds the first two.

| Level | Unit | Question it answers | Output |
|---|---|---|---|
| **Signal** (§9.1) | one flight, one or more channels | *Where in this flight does the signal cycle, and what does it look like there?* | rolling strips over the flight; window diagnostics; this flight's numbers |
| **Compare** (§9.2) | a selection of flights | *Does every flight do this, and how do they differ?* | one row per slice grouped by flight; chart against conditions; reference row |
| **Questions** (§7) | a slice set | *What is true of the set as a whole?* | the §8 result contract |

### 9.1 Signal view (D9, D10)

**Inputs.** One flight; one or more channels (default: the channels the study's last question used, else rpm and manifold pressure); an optional **window** (start/end seconds); for a pair, the reference channel.

**Over the whole flight:**
- the channels as a stacked multi-channel chart sharing the time axis (Spec 07 charts; phases shaded as in Flight view);
- under each channel, two **rolling strips**: *swing* (rolling peak-to-peak) and *dominant period* with its prominence (rolling detrended autocorrelation with a periodogram cross-check), both on a sliding window sized by §7.0 from the flight's own dominant period where one exists, floors otherwise. Strips are colour-mapped (swing in the channel's units; period in seconds, drawn only where prominence passes the §7 threshold). A strip value equals the descriptor a slice of that window would carry.
- a **rolling correlation** strip for a pair (v2, §14.7).

**Window.** Click-drag on a strip or the chart sets the window; the Flight view's *Research this window* passes its zoom as the initial window. For the window:
- **diagnostics**: the detrended trace; the autocorrelation with the detected period marked; the periodogram with its peak; for a pair, correlation against lag with the best lag marked;
- **this flight's numbers**: period, prominence, swing, level, and for a pair correlation at zero lag and the lag of best match — the same descriptors as §6, with the §7.0 resolved windows printed;
- **Make this a rule**: derives a condition rule from the window (the channel's level band over the window and its duration, editable in the rule form) so Compare can find the same window in other flights (D11).

**No verdict**: the numbers carry the OM reference and the user's references as in §8 Magnitude; no threshold is applied.

### 9.2 Compare (D11, D12)

**Inputs.** A selection of flights (all, picked, or a split — §5) and either a rule (from Signal's *Make this a rule*, a preset, a phase) or hand slices; the channels and, for a pair, the reference channel.

**Rows.** One per slice, grouped by flight; flights with no matching slice are listed as such. Columns: flight, start time, duration, source, DA, OAT, engine hours, phases, and the analysis values — period, prominence, swing, level, correlation at zero lag, best lag. Group rows collapse to one per flight (median of its slices, slice count shown). CSV export as §8 Evidence.

**Chart.** Any value against date, engine hours, DA or OAT; one point per row, colour by flight or source; the OM line where the channel has one.

**Reference row.** Any row can be pinned; the table then shows each row's difference from it (Δperiod, Δswing, Δcorrelation) and the chart marks it. Pinning survives save.

**Diagnostics.** An expandable panel shows the §9.1 window diagnostics for the pinned row and the rows the user selects, as aligned small multiples (D6 anchors apply).

**Relationship to the questions.** Compare's rows *are* the slice set's descriptors; adding a question summarises them (§7, §8). A study records the Signal flight and window, the derived rule, the Compare selection, the pinned row, and the questions.

### 9.3 Aligned view (v1, unchanged)

- **Aligned overlay** of a slice set for chosen channels: t = 0 at the rule's crossing by default (D6); anchors selectable; x in elapsed seconds; y shared per channel; one colour per slice with a legend keyed to the slice table.
- **Small multiples** (one panel per slice, shared axes) becomes the default above ~10 slices; overlay stays a toggle. A **scrubbing cursor** reads every panel at the same aligned time.
- **Multi-channel stack:** rpm, MAP and fuel flow (or any picked channels) as stacked strips sharing the time axis — the view that shows lockstep by eye.
- Clicking a slice opens the flight at that window in Flight view.
- Charts follow Spec 03 §6.1 (ECharts) and Spec 07's channel presets; Research adds no new charting stack.

## 10. Studies (D3)

### 10.1 Object

```jsonc
{
  "study_id": "st-…", "name": "Takeoff rpm oscillation", "created": "…", "updated": "…",
  "selection": { "mode": "all" | "flights", "flights": ["<fingerprint>", …], "split": null | { "by": "da_band" | "source" | "date", … } },
  "slice_rules": [ { "rule_id": "…", "from_preset": "full_power", "conditions": [ … ], "min_duration_s": 15, "merge_gap_s": 3, "phase": null, "pad_s": 0 } ],
  "hand_slices": [ { "flight": "<fingerprint>", "start_s": 0, "end_s": 0, "label": "…", "offset_s": 0 } ],
  "references": [ { "label": "Airmaster governing band", "channel": "rpm", "value": 100, "kind": "band", "source": "AP3/4/5 Operator's Manual V5-1A" } ],
  "tests": [ { "test_id": "cycling", "version": 1, "params": { … }, "channels": ["rpm"], "result": { /* §8 block, derived */ } } ],
  "view": { "anchor": "crossing", "channels": ["rpm", "map", "fuel_flow"] },
  "notes": "…",
  "cache": { "engine": "…", "descriptors": [ { "flight": "<fingerprint>", "slice": "…", "values": { … } } ] },
  "provenance": { "app": "…", "engine": "…" }
}
```

`tests[].result` and `cache` are derived (§5.5) and may be dropped; everything else is the study. Terminology (Q6): the destination is **Research**, the saved object is a **study**; "Research" is never used as a noun for a saved thing.

### 10.2 Storage and export

- `workspaces/<workspace_id>/studies/<study_id>.json` (Spec 02 §5.3 gains a `studies/` folder). Studies are **carried** by workspace export (Spec 02 §7.1 table gains a row).
- A study can also be exported alone as `<name>.eisstudy` (the JSON including the descriptor cache, plus the evidence CSV and a rendered chart image). Importing a study always creates a new study in the active workspace; flights are matched by fingerprint; unmatched flights are listed and simply contribute no slices.
- **Read-only import (Q5).** When *none* of a study's flights are present, the import still succeeds and the study opens **read-only**: the sender's cached finding, per-slice table and a static chart, under an unmistakable label — "sender's results; none of these flights are in this workspace" — so the numbers are never taken for the recipient's engine. One action, **Run this on my flights**, creates a new study with the same rules, references and tests over the recipient's own selection. This is the sharing pattern that needs no shared logs: "here is the rule that found my oscillation, run it on yours." The evidence package (§10.3) remains the route for readers who won't install the app.
- Studies are listed in Journal as records when they produce a Journal entry (§10.3), not otherwise.

### 10.3 Paths out

- **Journal entry** "from study …" with the finding and a link back (Spec 14 §6).
- **Evidence package**: one action exports the per-slice table (CSV), the aligned chart, and the finding text — what a manufacturer or mechanic needs.
- **Topic proposal** (Spec 10 §10): a study is E3 evidence — stated with engine type and aircraft count — for a proposed topic; the proposal form links the study.
- Future: filter or reference change carrying provenance (Spec 14 §4), symptom detector (§14.3).

## 11. Research operations (Spec 01 §7)

API-first (Goal 6): each UI action is one operation on the standard envelope; progress uses the host callback; nothing is computed only in the page.

| Operation | Inputs | Output |
|---|---|---|
| `list_slice_presets` | `EngineProfile` | preset rules |
| `build_slices` | selection, slice rules, hand slices | slice set (definitions + descriptors + context; samples on request) |
| `get_slice_samples` | slice ids, channels, anchor | aligned sample arrays for the views |
| `run_test` | test id, slice set (or two), channels, params, references | §8 result |
| `analyze_signal` | flight id, channels, optional window, optional reference channel | rolling strips (swing, period, prominence per sample), window diagnostics (detrended trace, autocorrelation, periodogram, correlation-vs-lag), the window's descriptors with resolved §7.0 windows, and a derived rule (§9.1) — v1.1 |
| `compare_rows` | selection, rule or hand slices, channels, optional reference channel, optional pinned row | rows per slice grouped by flight with analysis values, conditions and differences from the pinned row; flights without a match — v1.1 |
| `save_study` / `load_study` / `list_studies` / `delete_study` | study document | — |
| `export_study` / `import_study` | study id / file | `.eisstudy` / new study |
| `run_study` | study id | the study with each test's result, the cache and a last-run summary |
| `run_study_on_my_flights` | study id (read-only import) | a new study over the recipient's flights (§10.2) |
| `get_research_progress` | — | progress of a running build (`research` stream) |
| `note_study_finding` / `forget_study_finding` | study id + test index (+ note) / `ref_id` | the Journal entry (§10.3, kind `study_finding`) / `{removed}` — Session B, §3.3 |

All are gated in the UI by the `research` capability (`get_capabilities().features.research`). Errors: a malformed rule or unknown preset is `BAD_PARAMS`; running a read-only study is `READ_ONLY`.

CLI: `slingology-eis research presets | slices | samples | test | signal | compare | study {list,show,save,run,delete,export,import,fork}` — the same operations; with `--json` the CLI prints exactly the operation's JSON, so a study can be reproduced headless and a future agent can drive them.

## 12. UI (Spec 03 §4, §5 — new view)

- **Nav:** `Flights Trends Research Journal ⚙` — Research is the fourth everyday destination (D7; Spec 14 Q3 closed), shown when `get_capabilities().features.research` is true (Spec 03 v0.29 §4). Built: Spec 03 §5.10 describes the views as they are.
- **Research home:** the workspace's studies (name, finding of its first test, updated date), the presets with a one-line question each, *New study*. Empty state: the presets, and a sentence on what Research is for.
- **Study page** (v1.1, D12), top to bottom: **Signal** (one flight, channels, strips, window, diagnostics, *Make this a rule*) → **Compare** (selection, rule or hand slices with the slice count live, rows grouped by flight, chart, pinned reference, diagnostics panel; the aligned view of §9.3 as a tab of Compare) → **Questions** (add a question; each renders the §8 contract) → references and notes → actions (Journal entry, evidence package, export). Each section collapses; a study opened from a preset starts at Compare, one opened from a flight starts at Signal.
- **Entry points** ("Research this"): on Flight view (v1.1: opens a study in **Signal mode** on that flight with the chart's channels and zoom as the window; the full-power preset is suggested for a takeoff window); on a Trends card (study pre-split before/after the card's shift); on an event (study with a slice at the event's window across all flights with the same limit).
- **Help:** inline help on each test's question, the reference, the slice rule and the selection (Spec 14 §7.4 registry); the docs site has a Research concept page (`docs/concepts/research.md`) and one walkthrough (`docs/walkthroughs/research-takeoff.md`) reproducing the acceptance case; screenshots to be taken in the docs' screenshot pass (Spec 13).

## 13. Relationship to other specs

- **Spec 09 / 11 / 12:** Research creates no filters, insights or Trends entries in v1 and changes no ranking. Descriptors that prove useful may later be declared as fleet metrics (Spec 12 §8.1) through the normal Spec 10 route.
- **Spec 10:** Research is the lifecycle's first stage made concrete — a study is the evidence a candidate topic carries. Items parked as Research by Spec 10 become v2 example studies (Q3, §14.6).
- **Spec 02:** `studies/` is a new per-workspace document set, carried by export; nothing else changes.
- **Spec 03 principle 6:** two personas, one computation — Research is a destination, not a mode; a casual pilot's views are unchanged.
- **Program principles (Oct 4 2026):** Research ships no rule beyond the OM (goal 4), the user controls what they investigate and what they conclude, and nothing in Research is policy.

## 14. Deferred, designed here

### 14.1 Scan with recurrence (v2)
§7.4 run automatically on preset slice types after import, surfacing a short list only when a pattern holds in **N of M** slices (both shown and tunable; default to be set from the acceptance data), and including physics flags (a prominent period in a governed-rpm slice; a non-decaying autocorrelation) beside statistical outliers. Output goes to Research home, never to Flight view cards. One-off events stay with limits/events.

### 14.2 Investigations (future)
A client-side agent that takes the scan's list or a user's question, forms hypotheses, calls the §11 operations, reads the OM and service documents, and writes a card in the §8 contract plus candidate causes and what to do. Constraints fixed now: the user connects **their own AI provider with their own key**; the app operates no service and stores nothing; only descriptors and test results leave the device, never raw logs, with explicit consent; every sentence traces to a tool result or a cited document or is labelled hypothesis; on-demand first, never chatty. Named *Investigations*; "insights" stays with the deterministic layer.

### 14.3 Symptom detectors (future)
A finding may be packaged as a **declarative detector**: slice rule + descriptor + threshold + author's text (what was observed, what it may mean, what to do). Detectors are built in Research by people who understand the mechanism, shared as files, and installed by users; **the app ships none**. A detector whose author cannot fill in "what it may mean" and "what to do" is not publishable — the Research analogue of Spec 10's admission bar. A fired detector is an observation, silenceable like any other.

### 14.4 Splicer (v2)
Free drag alignment of slices with stored per-slice `offset_s` (field reserved in v1), slice trimming, and copying slices between studies.

### 14.5 Expression rules (v2+)
An advanced field accepting expressions over channels and derivatives, stored beside the structured rule.

### 14.6 Seeded studies from Spec 10 (v2)
Once the condition-dependence test (§7.5) exists, three studies ship as **examples** — questions and rules, no thresholds: `climb_thermal_rate` conditioned on VS bucket, climb duration, power and OAT (Spec 10 D2); the A5 fuel-flow model, power % × DA (Spec 10 §4.2); peak oil/coolant temperature predicted from airborne time and OAT (Spec 10 D7). Spec 10 §6.3 gains a note that these items resolve into Research studies. In v1 the Research home's empty state names them as "questions this app's own research left open", linking Spec 10 — a pointer, not a study.

### 14.7 Rolling correlation strip (v2)
A third Signal strip for a channel pair — rolling correlation at zero lag — "where do these move together?" Same sliding-window machinery as D10.

## 15. Acceptance criteria (tested against the project log set)

1. The *Full-power segment* preset over the admitted N117ZS flights dated through 2026-10-28 (the investigation's logs; later flights don't move these numbers) produces the Appendix A slice set: 98 slices (duplicates removed by fingerprint), with the two extended Phase-1 blocks included.
2. Test 7.1 on rpm reports median period 3.8 s (IQR within 3.5–4.1) and median swing 180 rpm, with ≥ 90 of 98 slices showing a prominent period; the finding sentence carries the count.
3. Test 7.2 rpm vs MAP reports median zero-lag correlation ≥ 0.85 on AXIS slices and ≤ 0.35 on G3X slices, stated per source with the damping caveat; fuel flow lag 1 s.
4. Test 7.3 split by DA band shows the swing falling above 3,500 ft DA with the small-group caution on the 6,000 ft band.
5. Test 7.4 lists the 2026-07-17 18:19 and 2026-07-23 18:12 slices among those standing out, on rpm swing, below the set's median.
6. A study holding 1–5 is saved, exported as `.eisstudy`, deleted, re-imported, and reproduces the same results on the same logs; imported into a workspace lacking some logs, it reports them and runs on the rest.
7. Every operation in §11 runs from the CLI with byte-identical JSON to the page (Spec 04 parity rule), in server and browser modes.
8. The browser mode completes a full-workspace slice build on the 120-log set with progress shown; the measured time is recorded in the spec.
9. No result contains a verdict word ("abnormal", "fault", "cycling detected") without its reference beside it; this is checked in a rendering test.
10. Research adds nothing to Flight view, Trends or Journal except through the explicit paths out (§10.3).
11. Every result card prints the resolved window and lag range (§7.0); on the acceptance case they resolve to the 12 s / ±10 s floors, and on a stable-cruise slice set they resolve to duration-scaled values.
12. A `.eisstudy` imported into a workspace with none of its flights opens read-only with the sender's cached results and the label of §10.2; *Run this on my flights* produces a new study over the recipient's selection.
13. Each shipped preset's measurement (slice count, slices per flight, duration distribution) is recorded in §5.2 and a test guards the chosen values against the log set.

**v1.1 — Signal and Compare (Session C):**

14. `analyze_signal` on the 2026-10-24 KAWO–KPAE–KBLI–KAWO flight, channels rpm and manifold pressure, no window: the period strip is lit (prominence above threshold, period 3–5 s) over each of the three full-power segments and dark over cruise and taxi; the swing strip peaks in the same segments.
15. With the window set to the first full-power segment (the KAWO takeoff), the diagnostics report period 3.5–4.1 s, swing 150–210 rpm, rpm–MAP correlation ≥ 0.85 at lag 0, fuel flow best lag +1 s; *Make this a rule* yields a rule that, applied to the flight, recovers that segment within ±3 s at each end.
16. `compare_rows` over the flights dated through 2026-10-28 with the full-power preset gives 98 rows in 59 flight groups whose per-row values equal the per-slice descriptors of acceptance 1–2 (same engine code path), and collapsing to flights gives 59 rows with counts summing to 98.
17. Pinning the KAWO row shows every other row's Δperiod and Δswing; the two high-DA rows show Δswing ≤ −90 rpm; a chart of swing against DA reproduces the acceptance-4 picture.
18. The study page opened from Flight view's *Research this window* on that flight lands in Signal mode with the zoom as the window; a study saved with a Signal flight, a derived rule, a pinned row and one question reopens with all four; `.eisstudy` carries them (acceptance 6 extended).

## 16. Questions resolved in v0.2

| # | Question | Resolution |
|---|---|---|
| Q1 | Preset values (§5.2) | **Measured in Session A** against the full log set, with the acceptance rule in §5.2; values and measurement recorded in this spec. Per engine profile; non-916iS profiles marked *unverified*. |
| Q2 | Slice recomputation cost on reopen | **Cache descriptors, never samples** (§5.5, §10.1), keyed by fingerprint and engine version; discarded on mismatch. |
| Q3 | Spec 10's Research-status items in v1? | **No** — named v2 example studies once the condition-dependence test exists (§14.6); v1 points at them from the Research home. |
| Q4 | Hand slices in v1? | **Yes, minimal**: the Flight view's current zoom becomes the slice (§5.4); engine in Session A, UI in Session B, may slip to v2 without a spec change. |
| Q5 | Study import without the logs | **Read-only import** with *Run this on my flights* (§10.2); evidence package kept for non-app readers. |
| Q6 | UI label | **Research** for the destination, **study** for the object (§10.1). |
| Q7 | Static window and lag defaults | **Proposed from the data**, two-pass with duration-scaled fallback and fixed floors (§7.0). |
| Q8 | Where the investigation document lives | `docs/research/2026-10-takeoff-rpm-oscillation.md` (Appendix A), correspondence and scratch-path references removed. |

Resolved in v0.3 (Session A):

| # | Question | Resolution |
|---|---|---|
| Q9 | Multipliers inside §7.0's bands | Window 2.5 *P*, lag ±1.5 *P*; fallback 0.2 / 0.1 × median slice duration; floors 12 s / ±10 s (§7.0). |
| Q10 | Minimum group size for the small-n caution | `n_min` = 10, reused (§7.3). The data didn't argue otherwise: the DA groups are 92, 4 and 2. |

### 16.1 Resolved in v0.4 — revisions to §15

| # | Question | What Session A found | Decided (owner, Nov 7 2026) |
|---|---|---|---|
| Q11 | Acceptance 2: period 4.4 s (IQR 4.1–4.8) | Over the 98 slices the period is median 3.76 s (IQR 3.55–3.94) — by autocorrelation, by Lomb–Scargle, and by counting peaks in the raw 1 Hz rpm, on G3X and AXIS alike. Swing (180 rpm) and recurrence (93 of 98) hold. | **Accepted.** Item 2 reads 3.8 s (IQR within 3.5–4.1); §1 and §7.1 updated; Appendix A keeps 4.4 s as the write-up's figure with a note. The before/after firmware comparison uses the app's estimator on both sides, so the discrepancy doesn't affect it. |
| Q12 | Acceptance 5: 7.4 ranks the two clean high-DA takeoffs first | Under §7.4 as written (twelve standard channels, robust z per descriptor within source, ranked by the largest \|z\|) they rank 19th and 22nd; 51 of 98 slices pass \|z\| ≥ 3.5, spread over coolant temperature, rpm, EGT, volts and fuel flow. With rpm, MAP and fuel flow only they rank 3rd and 4th, behind a slice with one sharp rpm step and one with a large MAP swing. Both are listed as standing out on rpm swing in every configuration. | **Reworded now, method change recorded as v2** (§7.4): count-based and combined-distance ranking, within the study's channels. Not worth reopening Session A; not to be forgotten — the §14.1 scan needs it. |
| Q13 | Acceptance 1: "all admitted logs" | The set grows: with the 2026-11-04 flight admitted, the rule gives 99. | **Accepted.** Items 1–5 run over the flights dated through 2026-10-28; Appendix A's Data line carries the date. |

## 17. Implementation plan

**Status (v0.5):** Sessions A and B done on `research`. Acceptance 1–7, 9, 11–13 pass on the real logs (`tests/contract/test_research_acceptance.py`); 8 measured in-page (§5.5); 10 is a host test (`tests/unit/test_research_ops.py`) plus the UI walkthrough (`spike/browser-host/run_research_walkthrough.py`, 19 checks in server mode); 12's UI side is a vitest (`web/src/views/Research.test.tsx`). Branch ready for the owner's review and merge into `main`.

Two Claude Code sessions on branch **`research`** off `main` (merged back when both are done), prompts delivered separately.

- **Session A — engine and CLI:** slice rules and presets (with the Q1 measurement), slice building over `LogSource`, descriptors and the §7.0 window rule, tests 7.1–7.4 with the §8 contract, hand slices in the model, studies with descriptor cache, `.eisstudy` export/import including read-only state, operations and CLI, acceptance 1–7, 9, 11–13; the investigation write-up placed at `docs/research/`.
- **Session B — web:** nav item, Research home, study page, aligned overlay and small multiples, entry points, help text; acceptance 8, 10 and the UI side of 12; Spec 03 revision rows.
- **Session C — Signal and Compare (v1.1):** engine: rolling strips and window diagnostics (`analyze_signal`), rule derivation from a window, `compare_rows` with grouping, pinning and differences; CLI `signal` and `compare`; study format extended (Signal flight and window, derived rule, pinned row). Web: the study page restructured as Signal → Compare → Questions (§12), strips with click-drag window, diagnostics panels, the Compare table/chart with pinning, Flight view entry in Signal mode. Acceptance 14–18; Spec 03 §5.10 and Spec 02 §5.3 revision rows; docs: Signal and Compare concept pages and a walkthrough (owner's docs plan, Phase 3).

---

## Appendix A — The acceptance case

Source: *N117ZS — Takeoff RPM/MAP Oscillation Investigation*, rev 3, 2026-10-29 — in the repo at `docs/research/2026-10-takeoff-rpm-oscillation.md` (Q8), with the Airmaster correspondence section and the scratch-script path removed; the analysis is reproducible with the full-power preset once Session A lands.

- **Data:** 121 CSV logs, G3X (2026-04-08 → 10-05) and AXIS (2026-10-14 → 10-28) — the admitted flights dated through 2026-10-28 (Q13); 98 distinct segments with rpm ≥ 5550 for ≥ 15 s.
- **Headline:** 94 of 98 takeoffs oscillate; median swing 180 rpm (140–240), period 4.4 s (IQR 4.1–4.8) in the write-up's peak count — the app's estimators (autocorrelation, periodogram and peak counting on the detrended 1 Hz slices) give 3.8 s (IQR 3.5–4.1) and 93 of 98 (Q11); unchanged from 28 to 145 engine hours and across the two log sources.
- **Coupling:** rpm–MAP zero-lag correlation 0.89–0.97 (AXIS), 0.1–0.3 (G3X, damped MAP channel); fuel flow lags 1 s.
- **Conditions:** swing vs density altitude r = −0.50; < 3,000 ft DA 180 rpm (92 slices); 3,500–4,900 ft 125–140 rpm (3); 6,000–6,350 ft 70–80 rpm (2), with MAP flat at the 1,750 mbar boost-control ceiling. No dependence on OAT or turbulence.
- **Mechanism:** limit cycle between the 916iS boost schedule (OM-916 Ch. 5 engine deck: 1484 → 1722 mbar between 5500 and 5800 rpm) and the electric governor's response; absent in Climb mode where the boost target is flat with rpm.
- **Outcome:** Airmaster confirmed a known 916iS behaviour addressed by controller and hub firmware; remote update session arranged. The before/after comparison is test 7.3.
- **Why it matters for this spec:** within OM limits, stable over time, invisible to the limits and trends lenses; found by shape analysis across many slices; made actionable by a per-slice table and a plot.
