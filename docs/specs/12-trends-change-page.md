# Spec 12 — Trends as a Change Page

**Project:** SlingologyEIS
**Status:** v0.10 — Phases 1–9 implemented (Sessions A–F, Oct 2026); Session G (§17 Phase 10, zoom-based pin) pending
**Suggested repo path:** `docs/specs/12-trends-change-page.md`
**Builds on:** Spec 01 (engine contract §8.4), Spec 03 (UI §5.3), Spec 08 (cylinder balance panel), Spec 09 (frozen baselines, change monitor, per-limit metrics), Spec 10 (topic register)
**Revises:** Spec 01 §8.4 (new change statistic, `BaselineConfig` fields), Spec 03 §5.3 (rewritten), Spec 10 §5.1 (register gains a `trends` field)
**Revision history**

| Version | Change |
|---|---|
| 0.1 | Initial draft from the Oct 6 2026 Trends review. Decisions D1–D3 recorded in §3. |
| 0.9 | After Session F, which ran against the v0.7 prompt and delivered tiers and detail strips but not the zoom-based pin; that work becomes Phase 10 (Session G). Session F decisions recorded (§3.6). The whole-history fit line was found never to have been implemented and now is (§8.3). Tier-3 count on the current log set is 14. |
| 0.10 | **CAS event panels** (Spec 10 D19, Spec 01 v0.21). Event panels are generated for two sources: the profile's limits (as before) and the **classified CAS alerts** (today `ENGINE ECU`), one panel per target. A CAS panel has the event strip and the frequency header (§5.8, §8.4) and no `peak_excess` strip (no excess exists); frequency is its only ranking signal. Built now, not deferred: a panel that reads *no events* on one aircraft is the honest state for that aircraft and the useful state for another. §3.7, §5.8, §8.2, §8.4, §11.7 updated. |
| 0.8 | **Pin is zoom-based** (D2 amended again, §5.7, §5.7.1): the flights visible in the strip's current x-range become the baseline; the recent window is the one-click alternative in the confirmation. This is the explicit historical cut v0.1–v0.7 deferred to v2, delivered now because `set_reference` already takes a flight list and the label *these flights* already implied it. Phase 9 extended. |
| 0.7 | After Session E. Session E decisions recorded (§3.5). **Panel tiers** (§9.1): panels ordered by what they have to say — qualifying first, then trendable, then a single collapsed *Never exceeded (N)* group at the bottom. **Detail strips** (§8.3): the page-level "researcher view" toggle becomes a per-panel *Show detail strips* affordance. Spec 03's stale pin wording noted for correction in the Phase 9 pass. Phase 9 added. |
| 0.6 | After Session D. **Pin semantics corrected** (D2 amended, §5.7, §5.7.1): pinning makes the current window's flights the metric's fixed baseline — what Session D built and validated — not a freeze of the older rolling reference, which v0.1–v0.5 described and which has weak value (a rolling reference grows, it does not slide, so it dilutes drift rather than hiding it) and an arbitrary cut. Wording: **Pin baseline to these flights / Unpin baseline**; badge *baseline pinned*. Visual: muted *not used* region to the left of the pinned baseline replaces the gap region. Small-baseline caution in the confirmation. Session D decisions recorded (§3.4). Phase 8 added. |
| 0.5 | After Session C. Six functional decisions recorded (§3.3). **Pinned-reference UX** specified as requirements (§5.7.1): visible pinned state on every strip and list, explanation and preview before pinning, Unpin everywhere the pin is shown, `cleared_by` on events closed by an unpin. §8.3's whole-history toggle is the page-level researcher toggle Session C built. Test limitation recorded (§15). Phase 7 added (§17). Session C result recorded. |
| 0.4 | After Session B. Seven functional decisions recorded (§3.2). Limit panels reworked (§8.4): a required **event strip**, **event frequency** as the primary change signal for limits (§5.8), `peak_excess` stated as conditional and drawn under the strip, `time_above_pct` out of the default view. **Readiness badge** on every strip and summary surface so a metric that cannot yet be trended says so where its name is (§9.3). Per-limit metrics carry units (§11.7). `Shift.level.filter_edge_value` typed. Pin semantics narrowed to "pin current reference" (§5.7); z-mode Notes/Trends divergence noted (§10). Phase 6 added (§17). |
| 0.3 | After Session A. Coupled panels produce one summary row (§7.1, D4); §8.1 points at the existing `docs/specs/topics/register.json`; takeoff-MAP residual declared as a new fleet metric (§8.2, §11.6); z-mode filter-edge level crossing brought into v1 scope (§5.5); seven Phase 1 functional decisions recorded (§3.1); acceptance 4 corrected to the 389 s KTOA block and acceptance 10 to require a new frozen `FleetAnalysis` fixture; Spec 10 revision is v0.9 not v0.4. |
| 0.2 | Q1–Q5 resolved (§16): pinned-reference shifts merge into the one summary with a prominent qualifier; Fuel panel kept for v1, last, labelled planning; `om_margin_fraction` stays global with the margin line drawn on every chart; no Flights banner — the Trends nav item carries a count of open shift events (§9.5); the replay harness becomes a Phase 1 deliverable (§17) after checking that Spec 09's replay is an inline test loop, not a reusable harness. |

**Note on numbering:** 06 stays reserved for research mode. 11 is the paused "insights under the program principles" draft.

---

## 1. Problem

The Trends view (Spec 03 §5.3) is a metric picker: one metric at a time, points over engine hours, a baseline band, and a linear fit over every flight since the first log. Its menu is a hand-written constant in `web/src/views/Trends.tsx` that mirrors `BASELINE_METRIC_DEFS` in `baselines.py`, which in turn descends from the trend section of the original script 03. The list was never designed as a page; it accreted.

Three consequences for a pilot:

1. **The page asks the wrong question.** A pilot opening Trends wants to know *is my engine changing, and should I care?* The page answers *here is a chart of whichever metric you picked*. The work of scanning eleven metrics for something that moved is left to the user.
2. **The headline statistic can't see change.** A linear fit since hour zero is dominated by history. Once an engine has 200 hours of logs, a shift in the last 20 hours barely moves the slope; and a slope has no reference, so nothing says what "the same as before" would look like. The fit also keeps reporting "increasing" long after a metric has levelled off — exactly the steady, known trend an insight should *not* re-report.
3. **The list is out of step with the rest of the design.** Spec 10 moved `cruise_efficiency` and `cruise_fuel_flow` out of the topic set and `climb_thermal_rate` to Research, yet all three remain top-level Trends entries. Spec 09's per-limit metrics — the OM measured over time, the most defensible content on the page — are baselined but hidden (Spec 09 Q5). `oil_temp_below_optimal_pct` was trended in script 03 and dropped silently. Any metric the engine adds is invisible until someone edits the TSX.

Spec 09 already built the right primitive for the first two problems, for one narrow case: a filter compares live flights against a **frozen baseline** of reference flights, within the flight's weather band, and reports Stable / Drifting / Breached. This spec generalises that comparison from "limits the user has filtered" to every fleet metric, and rebuilds the page around its result.

## 2. Goals

1. The first thing on Trends is a **ranked summary of what has changed** — metrics whose recent flights sit differently from their reference — or a single line saying nothing has.
2. One definition of "changed", shared with Spec 09's filter monitor, so filters and trends never disagree about the same flights.
3. Known, steady trends stay quiet; changes *in* them do not (the program's stated view of what an insight is for).
4. The OM limit is visible on every chart that has one (principle 1).
5. Metrics are grouped into **panels** by shared mechanism, declared in the topic register rather than in frontend code.
6. Spec 09's per-limit metrics appear on the page, with their filter bands.
7. Changes that roll out of the recent window are kept as a **shift history**, not lost.

**Non-goals for v1** (designed here, built later — §13): OM headroom projection, maintenance annotations on the time axis, the operating-condition strip, change-point detection (CUSUM). Not in scope at all: new insight kinds (the change summary is a view of fleet statistics, not an insight), per-cylinder CHT, any change to limit checking.

## 3. Decisions

| # | Decision | Rationale |
|---|---|---|
| **D1** | **Shift** (recent mean vs. frozen reference, in σ) is the single ranking statistic. **Level crossing** (recent mean past an OM margin or a filter band edge) overrides rank when it fires. **Bend** (recent slope differs from reference slope) is a card qualifier only; it never ranks a metric by itself. | One number drives the list, so it is stable and explainable with one threshold. Bend is noisier at small n and would add a second tuning surface; promote it later if real use shows bends being missed — demoting a signal pilots have seen is harder than promoting one. |
| **D2** (amended v0.6) | The reference is **rolling by default** (every eligible flight older than the recent window; it grows as flights arrive). A user may **pin the baseline** per metric: the flights visible in the strip's current zoom become the fixed baseline (or, as the one-click alternative, the recent window's flights); flights outside the pinned set are no longer used for that metric, and new flights are compared against the pinned set until unpinned. Spec 09 filters keep their own frozen reference unchanged. | Rolling needs no management. Pinning answers "treat how the engine runs now as normal and tell me when it departs from that" — after maintenance, a fix, a new prop. The earlier idea of freezing the *older* reference was dropped in v0.6: a rolling reference grows rather than slides, so it dilutes drift but never hides it, and "the first N flights" is an arbitrary cut. v0.8 makes the cut explicit and user-chosen through zoom, which is what the label *these flights* implied all along; v2 maintenance annotations (§13) will add named cut points on top. The fade of a change into a rolling reference is mitigated by the shift history (§6). |
| **D3** | **Panels are declared in the topic register** (Spec 10) via one `trends` field per topic. Per-limit metrics always get a panel, generated from Spec 09 data, with no register entry. The `GROUPS` constant in `Trends.tsx` is removed. | Trends becomes data-driven; a contributed topic appears in the right place by declaring one field. Panel membership is reviewed under Spec 10 A6 so panels stay mechanism-based, not convenience groupings. |

| **D4** | **Coupled panels summarise once.** A panel whose metrics are mathematically coupled (the four `egtN_deviation` values are distances from their own mean and sum to zero) contributes **one** summary row, ranked by its largest member \|shift_z\|, with member detail on the card. Declared with `coupled: true` on the panel (§8.1). | Session A showed EGT3 at +4.0 σ and EGT2 at −2.5 σ in the same window: partly one event seen twice. A change page should say it once. Spec 08's header chip is the precedent; a register flag generalises it rather than special-casing cylinders. |

Decisions settled during the review for the window and the v1/v2 split are recorded in §5 and §13.

### 3.1 Functional decisions made in Session A (recorded, accepted)

| # | Decision |
|---|---|
| A1 | EGT spread's level crossing uses the high-flow OM limit (392 °F), matching the Flight view's attribution. |
| A2 | `limit_*_time_above_pct` metrics get no level crossing: a percentage share is not commensurable with the limit's units or a magnitude filter band. |
| A3 | For `limit_*_peak_excess` the filter-edge value is the filter's resolved band directly (the metric is already excess above limit); for every other metric it is `limit + band`. |
| A4 | One `n_min` (the existing `MIN_FLIGHTS_FOR_CONFIDENCE` = 10) gates shift, bend and reference validity; no second constant. |
| A5 | Topics without a scalar fleet metric (`cylinder_rank`, `engine_ecu_inflight`, `limit_exceedances`) and `egt4_elevation`, `cruise_da_ft` have `trends: null`. |
| A6 | `limit_*_time_above_pct` metrics with a zero-variance reference report `shift_z = null` (no z defined), consistent with Spec 09's treatment of the same skewed metrics. |
| A7 | `change_summary` is the thin `{metric_id, rank}` list; ranking lives once in the engine. |

### 3.2 Functional decisions made in Session B (recorded, accepted)

| # | Decision |
|---|---|
| B1 | A coupled panel's `change_summary` row carries the lead member's `metric_id` plus the panel id and the qualifying members; full membership comes from the panel layout, not the summary. |
| B2 | A coupled panel's shift-history event is keyed by panel and snapshots every member's `shift_z` and direction at open. |
| B3 | A z-mode filter's edge on Trends resolves against the metric's own current reference (rolling or pinned), not the filter's frozen reference; see §10 for the consequence. |
| B4 | `takeoff_map_residual_inhg` uses the all-flights model fit (`FleetAnalysis.models.takeoff_map`), the same fit the Flight view shows. A recent-window residual therefore partly reflects the model being fitted on those same flights; a persistent residual shift is still meaningful, a marginal one less so. Leave-one-out fitting is a v2 candidate. |
| B5 | Panel order: the four register panels in fixed order, then limit panels, filtered first, then by most recent exceedance. |
| B6 | "Set reference here" is **Pin current reference**: it freezes the current rolling reference membership. An arbitrary cut point ("before the oil change") waits for v2 maintenance annotations (§13). |
| B7 | `Shift.level` gains `filter_edge_value: number | null`, the resolved edge, so the web can draw it. |

### 3.3 Functional decisions made in Session C (recorded, accepted)

| # | Decision |
|---|---|
| C1 | Two-proportion z uses the pooled proportion; it is null only when both shares are 0, which never qualifies. |
| C2 | When a limit is both filtered and in another readiness state, *filtered* wins; it is computed from validated active filters, not the panel's `filtered` flag. |
| C3 | The *rare* / *never exceeded* denominator is lifetime events from the limit's full-coverage metric (`time_above_pct` or `block_s`), not `peak_excess`'s own sparse reference, which would badge almost every limit *building*. |
| C4 | Overboost "has event" means block > the 300 s limit, not block > 0; a block is present on nearly every takeoff. |
| C5 | `overboost_time` and `limit_overboost_block_s` share one frequency and readiness. |
| C6 | Rank key is \|frequency.z\| when frequency is the reason a metric qualifies, else \|shift_z\|; the two never add. |

### 3.4 Functional decisions made in Session D (recorded, accepted)

| # | Decision |
|---|---|
| D-1 | ~~The gap region is drawn only when the window has moved past the pinned baseline.~~ Superseded in v0.8: every eligible flight outside the pinned set is *not used*, one region kind, wherever it sits. |
| D-2 | The pin marker's flight count is the live post-exclusion count, not the original pin size; `REFERENCE_LOW_N` is the safety net. |
| D-3 | *filtered* metrics rank (§9.3 as written); Session C had excluded them — corrected. |
| D-4 | Unpin from Baselines & Models uses the same confirmation and engine preview as the strip. |
| D-5 | The pin explanation is one shared text used by the confirmation; no separate help popover. |
| D-6 | What Session D built — the window's flights become the baseline — is the intended behaviour (D2 amended); the spec's earlier description was the error. |

### 3.5 Functional decisions made in Session E (recorded, accepted)

| # | Decision |
|---|---|
| E1 | The small-baseline caution threshold is `n_min` (10), one shared constant; the caution appears only for baselines the rest of the system already calls low-confidence. |
| E2 | Region names live in the strip's existing legend row (conditional entries); the ±1σ entry relabels itself *pinned baseline* when pinned. No separate caption block. |

### 3.6 Functional decisions made in Session F (recorded, accepted)

| # | Decision |
|---|---|
| F1 | Detail-strip state is a workspace setting (`trends_detail_strips`, panel id → on/off), per §8.3's "remembered per workspace". |
| F2 | No visible dividers between tiers 1 and 2; position and tier 1's default-expanded state carry the distinction. The *Never exceeded* group is the only structural marker. |
| F3 | The whole-history fit had never been implemented; it is now a dotted line through `baseline.mean` at the mean plotted x with `trend.slope` (the contract carries no intercept). |
| F4 | A tier-3 row's representative metric is `peak_excess` (or `block_s` for overboost), the same metric the group's tick count and event strip use. |

### 3.7 Functional decisions from the ECU review (recorded, 2026-10-13)

| # | Decision |
|---|---|
| G1 | Panel sources are the profile's limits **and** the register's classified CAS alerts (Spec 10 §8 lifecycle; today `ENGINE ECU`). Not "any CAS id seen in the logs" — an unclassified alert has no defined meaning and gets no panel. |
| G2 | A CAS panel = event strip + frequency header only. No `peak_excess` strip, no OM line, no filter band edge (a duration filter shows as a header note, "events ≤ N s filtered"). |
| G3 | Same generation rule as limits: a panel exists when the target has a filter or at least one event on an eligible flight; otherwise it sits in the *Never exceeded / no events* group in the bottom tier. |
| G4 | `engine_ecu_inflight` keeps `trends: null` in the register — the panel is generated from events, not declared by the topic. |

## 4. Concepts

**Fleet metric.** A per-flight scalar baselined by `update_fleet` (today: `BASELINE_METRIC_DEFS` plus Spec 09's `limit_<id>_peak_excess` / `limit_<id>_time_above_pct`).

**Recent window.** The newest eligible flights of a metric, chosen by §5.1. These are the flights being asked "do you still look like the reference?"

**Reference.** The flights the recent window is compared against. Either *rolling* — every eligible flight not in the recent window — or *pinned* — a frozen membership chosen by the user (same mechanism as Spec 09 §4's frozen baseline: membership frozen, statistics recomputed from current flight analyses). The reference is a Spec 01 `Baseline`, stratified by the metric's `band_kind` where one exists.

**Eligible flight.** A flight in the workspace's baseline membership (not excluded, Spec 02 §5.11 Tier 2) that has a non-null value for the metric.

**Shift.** The standardised difference between the recent window's mean and the reference mean (§5.2).

**Change summary.** The ranked list of metrics whose shift crosses the threshold, or whose recent mean has crossed a level (§7).

**Shift history.** The workspace's record of past threshold crossings, per metric (§6).

**Panel.** A chart that draws several related fleet metrics on one engine-hours axis (§8). Cylinder balance (Spec 08 §7) is the existing example.

## 5. The change statistic

### 5.1 Recent window

Starting from the newest eligible flight and walking back in time, the window is the smallest set of flights such that **both** hold:

- total engine hours spanned ≥ `recent_window_hours` (default **10**)
- flight count ≥ `recent_window_min_flights` (default **5**)

capped at `recent_window_max_flights` (default **15**). If the cap is hit before the hours condition, the window is the capped set and `RECENT_WINDOW_CAPPED` is noted. If fewer than `recent_window_min_flights` eligible flights exist in total, there is no recent window and no shift (§5.5).

Engine hours are the span between the oldest and newest flight in the window, from log metadata (`engine_hours`), the same x-axis the page uses.

Rationale: wear tracks engine hours, so the window is sized in hours; statistical power tracks flight count, so a floor is needed for pilots flying short hops; the cap keeps a long-hop pilot's window from swallowing half the log set. 10 h is about a month for an active private pilot, so the page answers "what is different about the last month". Five flights is where the shift test stops being able to see anything but very large changes (standard error = reference std / √5 ≈ 0.45 σ, so z = 2 needs a ~0.9 σ shift). All three are `BaselineConfig` fields (§11.1), edited in Baselines & Models, never on Trends.

### 5.2 Shift

For a metric with reference statistics (mean *μ*, std *σ*, n *n_ref*) and a recent window of *n_rec* flights with values *x_i*:

- **Unstratified** (`band_kind` is null, or the fallback in §5.3 applies): `shift_z = (mean(x_i) − μ) / (σ / √n_rec)`.
- **Stratified:** each recent flight gets `z_i = (x_i − μ_b) / σ_b` against the reference statistics of its own band *b*; `shift_z = mean(z_i) · √n_rec`. Flights whose band has no usable reference (§5.3) are dropped from the mean and counted in `comparison.unmatched`.

`shift_z` is signed. The card reports direction in the metric's own terms (hotter / cooler, wider / narrower, longer / shorter). Rank is by `|shift_z|`.

`σ` is the reference std with the same std-floor policy as Spec 09 §13 applies to the metric — none for ordinary metrics, the documented floor for `time_above_pct`.

### 5.3 Stratification and fallback

Follows Spec 01 R8 exactly. For a metric with a `band_kind`:

1. A recent flight is compared within its band when the reference has at least `n_min` flights in that band.
2. Otherwise it is compared against the unstratified reference, if that has at least `n_min` flights.
3. Otherwise it is unmatched.

If more than half the recent flights are unmatched, there is no shift for this metric and the card shows `comparison.scope = "insufficient"` ("recent flights were flown in conditions your reference doesn't cover yet"). A run of hot-day flights after a mild-day reference produces this, not a false thermal shift.

`comparison` on the result records `scope` (`band` | `all` | `mixed` | `insufficient`), per-band counts, and `unmatched`, so the card can say exactly what was compared with what.

### 5.4 Bend (qualifier)

Where both the reference and the recent window have at least `n_min` flights with engine-hours x-values, fit a slope over each. Bend fires when the recent slope differs from the reference slope by more than 2 × the standard error of the reference slope, in the worsening direction for the metric. Reported on the card as one line ("and the rate of increase has roughly doubled"); never used for ranking. Below `n_min` on either side, not computed.

### 5.5 Level crossing (override)

Fires when the recent window's mean (unstratified, since limits are not weather-dependent) has crossed:

- the metric's **OM margin line**: `limit − om_margin_fraction × |limit − μ_ref|`, where `om_margin_fraction` defaults to **0.25** — i.e. the recent mean has used up three quarters of the headroom the reference had; or
- the **edge of a filter band** for a Spec 09 filtered limit. Absolute and percent bands use the filter's `magnitude`; z-mode bands resolve against the metric's current reference (§5.7) — rolling or pinned — so a z-mode filter has a filter-edge crossing like any other (Session A shipped absolute/percent only; z-mode is Session B work).

Level crossings rank above every shift in the summary regardless of `|shift_z|`. The OM limit for a metric comes from the engine profile through the same mapping the Flight view topic cards already use (`egt_spread` → EGT spread max, `oil_temp_peak` → oil max, etc.); metrics with no OM limit have no OM crossing.

### 5.6 Threshold and gates

A metric enters the change summary when `|shift_z| ≥ resolve_outlier_z_threshold(metric_id)` — the same resolver and default (2.0) as `FleetMetric.outliers` and `baseline_deviation`, so one number means "unusual" everywhere — or when a level crossing fires.

No shift is computed when the reference has fewer than `n_min` eligible flights (`BASELINE_LOW_N` carries over). The card then shows the building-reference message of §9.3.

### 5.7 Reference pinning

A pinned baseline is a frozen membership (`flight_ids[]`, `set_at`, optional `label`), stored per metric (§6). The pin action is **Pin baseline to these flights**: the eligible flights inside the strip's current zoomed x-range become the baseline. Zoom is the selection tool — a pilot zooms to "after the oil change, before the prop swap" and pins. The confirmation offers **Use the recent window instead** as a one-click alternative (the §5.1 window's flights). Flights outside the pinned set are not used for that metric while pinned. The recent window continues to advance; flights in both the pinned set and the window are counted in both (immediately after a window-based pin the shift is zero by construction). A pin needs at least `n_min` eligible flights in range; below that the control is disabled with the count shown. When the zoom is the full history, the confirmation says so (*"all 50 flights are selected — zoom to the flights you want first, or use the recent window"*). Its statistics are recomputed from current analyses and honour exclusions (Spec 09 §4 semantics). A pinned baseline that falls below `n_min` after exclusions is invalid (`REFERENCE_LOW_N`, warn) and the metric reverts to rolling; the pin is retained. **Unpin baseline** returns the metric to rolling at once.

#### 5.7.1 Pinned-reference UX (requirements)

A pin that cannot be seen, understood or undone is a trap, not a tool. Requirements (wording fixed in v0.6):

1. **Visible state.** A pinned metric looks different from a rolling one on every strip that draws it. The pinned baseline region has fixed, hard edges and a pin marker labelled *"baseline pinned · 21 flights · 12 Oct"* (plus the label if given). Every eligible flight outside the pinned set — older than it, or between it and the current window — is drawn in a muted **not used** region; that region is the visual tell, since under rolling every older flight is in the reference. The pinned region is drawn at its true x-extent regardless of zoom, so zooming out after pinning shows exactly which span was chosen. *baseline pinned* is a readiness badge (§9.3) so the state is visible in every list that names the metric, and the summary row carries the *since <label>* qualifier (§7).
2. **Explanation before pinning.** The control **Pin baseline to these flights** opens a confirmation, not an immediate action. It states: *"The N flights in view (X h, <dates>) become this metric's baseline and stay fixed. Flights outside this span are no longer used for this metric. New flights are compared against these N until you unpin."* Beneath it, **Use the recent window instead** switches the selection to the §5.1 window and restates N and the dates. The full-history notice of §5.7 appears when applicable. When N < `n_min`-equivalent comfort (say, under 10) it adds *"A baseline of N flights makes comparisons noisier than your full history."* When it is useful: after maintenance or a change you want to measure from. Optional label field; Confirm / Cancel. The same text is the help entry, written once.
3. **Revert.** **Unpin baseline** is available wherever the pin marker is shown and in the Baselines & Models pinned-baselines table (§12). It returns the metric to rolling at once, with one line saying so (*"the baseline will again include all earlier flights and grow as you fly"*). Unpinning never deletes shift-history events recorded while pinned; they keep `reference.kind = "pinned"`.
4. **Honest history.** If unpinning causes an open shift event to stop qualifying, the event closes with `cleared_by: "unpin"` (new optional field on `ShiftEvent`, alongside `cleared_at`), so the history does not read as the engine having recovered.
5. **Preview on unpin.** The unpin confirmation shows whether the metric's current qualification would change (*"this metric will no longer appear in the change summary"* / *"no change to the summary"*), computed by the engine, not guessed by the web. Its statistics are recomputed from current analyses, honour exclusions, and are stratified exactly like the rolling reference. Pinning does not change the recent window. A pinned reference that falls below `n_min` after exclusions becomes invalid (`REFERENCE_LOW_N`, warn) and the metric reverts to rolling until the user re-pins or unpins. Spec 09 filters are not affected by pinning; their reference stays the filter's own.

### 5.8 Event frequency (limit panels)

`peak_excess` is **conditional**: it has a value only on flights where the limit was exceeded (Spec 09 §5), so its reference is "how far over, on the flights that went over." A shift in it says exceedances are getting larger; it cannot say they are getting more frequent. `time_above_pct` carries frequency but is mostly zeros, so its reference usually has no variance and no z is defined (A6). Neither strip can detect the change a pilot most wants on a rarely-exceeded limit: *this used to happen once a year and now it is every flight.*

For every limit (and for `overboost_time`), and from v0.10 for every classified CAS alert (Spec 01 §8.6 `source: cas`), the engine therefore computes **event frequency**: the share of flights with at least one event, in the recent window and in the reference. It qualifies when the recent share exceeds the reference share by at least `frequency_delta`, the rule Spec 09 §8.2 already applies to filters, so Notes and Trends use one definition of "more often". A qualifying frequency ranks in the summary like a shift, using the recent share's standardised difference from the reference share (a two-proportion z) as its rank key, and opens a shift-history event of kind `frequency`. Frequency is the **primary** change signal for limit panels; `peak_excess` shift is the secondary ("and when it happens, it goes further over"). `time_above_pct` is context only (§8.4).

Below `n_min` reference flights, or when the reference share is 0 and the recent window has a single event, frequency does not qualify; a single new event on a never-exceeded limit is reported by the Flight view's `limit_exceedances`, not by Trends.

## 6. Shift history

Each time `update_fleet` runs, for every metric with a shift computed, compare against the metric's last recorded state:

- If `|shift_z|` crosses the threshold (or a level crossing fires) and the previous state was below, append a **shift event**: `{ metric_id, detected_at, window: { flight_ids, hours_from, hours_to }, shift_z, direction, kind: "shift" | "om_margin" | "filter_edge", comparison, reference: { kind: "rolling" | "pinned", n, hours_from, hours_to } }`.
- If a shift event is open and the condition no longer holds (the window rolled on, or the metric returned), close it with `cleared_at` and the engine hours at clearing.

The history is append-only except for user deletion. It is what makes a rolling reference safe: a change that has become "the new normal" is still visible as "cylinder 4 shifted +40 °F around 120 h". It is also the natural input to maintenance annotations (§13).

Storage: `fleet/shift_history.json` in the workspace (Spec 02 §6), alongside `selection.json`. Pinned references live in `selection.json`'s `BaselineConfig` (§11.1).

## 7. The change summary

Top of the Trends view. One row per metric meeting §5.6, ordered: level crossings first (OM before filter edge), then by `|shift_z|` descending. Each row:

- **Panel and metric name**, e.g. *Cylinder balance · cylinder 4*.
- **Plain statement**, from the metric's `trends.phrasing` (§8.1): *"Cylinder 4 is running about 28 °F hotter than it used to."*
- **Comparison line**, from `comparison`: *"last 13 flights (10.4 h) vs. 31 earlier flights, compared within OAT band."* `n_rec` and `n_ref` link to Flights filtered to those flights (Spec 03 §5.1's existing cross-link).
- **Qualifiers**, zero or more: bend (§5.4), *"within 25 % of the OM limit"*, *"at the edge of your filter band"*, *"since <label>"* for a pinned reference. The pinned qualifier is rendered at full weight, not as a footnote: that row answers a different question (since the pinned point) from the rows around it (since the recent window), and the reader must see that. Pinned and rolling rows share one list and one ranking (Q1).
- **Severity-free.** No severity token is shown. The summary ranks by evidence, not policy, consistent with the program principles; the OM-margin case is marked by the OM line itself, not a colour.

Clicking a row opens that metric's panel (§8) scrolled into view, with the recent window and reference regions shaded on the chart.

Below the rows: **"N other metrics checked, no change"**, so a short list reads as "nothing more to report". When no row qualifies the summary is one line: *"No change detected across N metrics over the last X hours."*

### 7.1 Coupled panels (D4)

A panel declared `coupled: true` produces at most one summary row. The row qualifies if any member qualifies; it ranks by the largest member |shift_z| (level crossings still override); its plain statement names the member that moved most and its direction relative to the others (*"Cylinder balance has shifted: cylinder 3 is running about 22 °F hotter relative to the other three"*); the card lists every member's shift. Shift history (§6) records one event per coupled panel, carrying member detail, not one per member.

A collapsed **Past changes** section lists closed shift events from §6, newest first, each linking to its panel with the event's window shaded.

A metric below `n_min` is not in either list; it appears in the metric list (§9) with its building-reference message.

## 8. Panels

### 8.1 Register field (Spec 10 §5.1)

The register is the existing machine-readable file `docs/specs/topics/register.json` (the Spec 10 D12 hybrid register), mirrored by the table in Spec 10 §5.2. Every topic entry gains:

```yaml
trends:
  panel: cylinder_balance | thermal | boost_power | fuel | null   # null: never on Trends
  coupled: true | false          # panel-level, D4; true only for cylinder_balance today
  role: primary | context        # context metrics draw muted, never rank in the summary
  phrasing:
    higher: "…running about {delta} hotter than it used to"
    lower:  "…running about {delta} cooler than it used to"
  worsening: higher | lower | either
```

`worsening` drives the level-crossing direction, the bend direction and the summary wording. `phrasing` is per topic because "wider" / "longer" / "hotter" cannot be derived from a unit. A topic with `trends: null` is baselined (if it has a baseline anchor) but never drawn — this is where `cruise_da_ft` goes.

Panel membership is part of the register entry and is reviewed under A6 (distinct): a panel groups metrics that share a *mechanism*, so a shift in one is read against the others. Convenience groupings are rejected.

### 8.2 The v1 panels

| Panel | Metrics (primary unless noted) | Shared axis | OM line |
|---|---|---|---|
| **Cylinder balance** | `egt1..4_deviation` (Spec 08, unchanged), `egt_spread` added as a second strip | °F | EGT spread max (on the spread strip) |
| **Thermal** | `oil_temp_peak`, `coolant_temp_peak`; `oil_coolant_ratio` (context, own small axis); `climb_thermal_rate` (context, own small axis; Research per Spec 10 but drawn as context) | °F | oil max, coolant max |
| **Boost / power** | `overboost_time`; `takeoff_map_residual_inhg` — **new fleet metric** (§11.6), the takeoff-MAP model's predicted-minus-actual per flight, replacing the raw `takeoff_map_inhg` entry; `limit_rpm_takeoff_max_peak_excess` if present | s / inHg / rpm, one strip each | 300 s overboost block; 5,800 rpm |
| **Fuel** (planning) | `cruise_efficiency`, `cruise_fuel_flow` | nm/gal, gal/hr | none |
| **Limit: <name>** — one per filtered or exceeded limit | `limit_<id>_peak_excess`, `limit_<id>_time_above_pct` | metric unit / % | the limit itself; the filter band when a filter exists |

Removed from Trends as standalone entries: `cruise_da_ft` (becomes condition strip data in v2), `egt4_elevation` (already deprecated by Spec 08), `takeoff_map_inhg` raw (replaced by the residual). The Fuel panel is marked **planning** in its header, consistent with Spec 10 §4.2, and sits last.

Event panels are generated, not declared: one per **target** — a limit, or a classified CAS alert (v0.10, §3.7 G1) — that has a filter (Spec 09) or at least one event on an eligible flight; targets never exceeded and never filtered produce no panel. Order: filtered first, then by most recent exceedance.

### 8.3 Common chart behaviour

Every panel strip draws, on one engine-hours axis shared across the panel:

- points (one per eligible flight), linked to Flight view, outlier rings as today (Spec 03 §5.3 v0.11);
- the reference region (hours span, shaded) and the recent window (hours span, shaded differently), with the reference mean and ±1σ band drawn only across the reference span and extended as a dotted line across the recent span, so the eye sees the comparison the statistic made;
- the OM limit (and filter band edge where one exists) as a horizontal line with a label, and the OM margin line of §5.5 as a fainter dashed line labelled with the fraction ("75 % of headroom"), so the one global `om_margin_fraction` is always visible where it applies (Q3);
- a **stratify** toggle per the existing Spec 03 §5.3 rules (hidden for null `band_kind`, off by default), which recolours points by band and splits the reference band per weather band;
- the metric's shift card (plain statement, comparison line, qualifiers) beside or below the strip, identical to its summary row;
- "set reference here" on long-press / right-click of a point or an x-position; a pinned reference shows a pin marker and an "unpin" action.

### 8.4 Event panels (limit and CAS) and the event strip

A CAS panel (v0.10) consists of the event strip and its frequency header only — the `peak_excess` strip, OM zero line and filter band edge below do not apply (§3.7 G2). Each tick's tooltip names the class (`GROUND` / `IN_FLIGHT`) and `not_lane_check_reason` when set.

Every limit panel, and the `overboost_time` strip in Boost / power, begins with an **event strip**: one tick per eligible flight on the shared engine-hours axis — a short, pale tick for a flight with no event, a tall, solid tick for a flight with one — with the reference and recent-window shading running across it like every other strip. Its header states the frequency comparison in words: *"exceeded on 2 of 10 recent flights · 1 of 40 earlier."* When frequency qualifies (§5.8), this header is what the summary row quotes. Ticks do not encode magnitude; that is the strip below.

Beneath it, the `peak_excess` strip plots only the exceeding flights, each point directly under its tall tick and joined to it by a faint vertical guide, so the sparse chart is explained by the row above rather than by a note. The strip header states *"magnitude on exceeding flights only"*. The OM limit is the strip's zero line; the filter band edge is drawn where a filter exists.

`time_above_pct` is not in the default view. It is available behind the same researcher toggle as the whole-history fit (§8.3), muted.

The old whole-history linear fit is no longer drawn by default. It and `time_above_pct` (§8.4) are **detail strips**: each panel that has any shows a *Show detail strips* affordance in its own header (tooltip naming what will appear), off by default, remembered per workspace. This replaces the page-level "researcher view" toggle Session C built, whose label described contents rather than purpose and whose header placement was easy to miss. The fit remains computed in `FleetMetric.trend`, unchanged, so insight triggers that use it are unaffected and is still computed in `FleetMetric.trend` (Spec 01 §8.4), unchanged, so insight triggers that use it are unaffected.

## 9. The rest of the page

### 9.1 Layout

1. Change summary (§7), with Past changes collapsed beneath it.
2. Panels in **three tiers**, so the page reads top to bottom as *what moved → what is being watched → what has never been a problem*:
   - **Tier 1 — qualifying.** Every panel that holds a change-summary row, in summary order. The panel a summary row links to opens expanded.
   - **Tier 2 — trendable, nothing to report.** The register panels in their fixed §8.2 order, then limit panels that are *filtered* or *rare*, by most recent exceedance. Metrics in *building*, *too few flights* or *insufficient* states stay here in their mechanism panels with their badges — those are temporary states, not a category.
   - **Tier 3 — Never exceeded (N).** One collapsed group at the bottom holding every limit whose only badge is *never exceeded*. Its header carries the count (*"11 limits never exceeded on 50 flights"*) so the statement is read without scrolling through eleven empty panels. Expanding lists one row per limit (name, tick count, "never exceeded on N flights"); each row expands to its event strip. These limits are not drawn as full panels until opened. A limit leaves the group on its first event and appears in tier 2 as *rare*; it moves to tier 1 if it ever qualifies.
3. Nothing else. No metric picker; the panels *are* the metric list. Settings for windows, thresholds and pinned baselines are in Baselines & Models.

Tier membership comes from engine output (`change_summary`, readiness, filters), never from web heuristics.

### 9.2 Stale data

Unchanged from Spec 03 principle 3: if `FleetAnalysis` is stale, the summary header shows the stale notice and the one refresh action; the summary and panels still render from the last computed result.

### 9.3 Below `n_min`

A metric whose reference has fewer than `n_min` eligible flights shows its points and, in place of a shift card, *"Building your reference — N more flights before change detection starts."* No band, no fit, no trend line: the page states the gate rather than drawing a VERY_LOW line nobody reads.

**Readiness badge.** The reason a metric cannot be trended must be visible where its name is, not discovered by opening it. Every strip header, and every place a metric is listed (panel headers, the collapsed panel list, Baselines & Models), carries one badge next to the metric name, from a fixed set, in the same position the existing *filtered* note already occupies:

| Badge | When | Text |
|---|---|---|
| *filtered* | a Spec 09 filter is active on the limit (existing) | "filtered" |
| *building* | reference below `n_min` | "building reference · N more flights" |
| *no recent* | fewer than `recent_window_min_flights` eligible flights in total (`RECENT_WINDOW_LOW_N`) | "too few flights" |
| *no events* | a limit never exceeded on any eligible flight (only its event strip has content) | "never exceeded" |
| *rare* | a limit exceeded on fewer than `n_min` flights, so `peak_excess` has no reference but frequency is tracked | "N exceedances" |
| *insufficient* | §5.3's comparison fallback (`SHIFT_COMPARISON_INSUFFICIENT`) | "conditions not comparable yet" |
| *pinned* | baseline pinned (§5.7.1) | "baseline pinned · <label or date>" — with *filtered*, the only badges that do not exclude a metric from ranking |

Badges come from engine output (`Shift` diagnostics and the per-limit counts), not from web logic. A collapsed panel whose every metric carries a badge other than *filtered* shows the panel-level summary of those badges, so a pilot can skip it without expanding it. A metric with a badge other than *filtered* or *pinned* is never ranked in the summary.

### 9.4 Evidence links from insights

`baseline_point` evidence (Spec 03 §5.2) now opens the metric's panel with the flight highlighted, as before. Spec 08's `egtN_deviation` links open the cylinder panel focused on that cylinder, unchanged. Spec 09's Notes-page filter charts link to the corresponding limit panel.

### 9.5 Signal outside Trends (Q4)

No banner on Flights. The **Trends nav item carries a badge** with the number of open shift events (§6), the same pattern as Notes' filter badge (Spec 09 §12.3). It is a passive signal a pilot sees on every visit without anything being pushed at them — principle 3 (the system says something changed) without violating principle 4 (the user decides what to look at). A Flights banner, as Spec 09 uses for Breached and Drifting filters, is deferred: the shift threshold is tuned for a ranked list, not an alert, and a banner would fire on every borderline shift. Promote only if users ask.

## 10. Relationship to Spec 09 and Spec 11

**Spec 09.** The filter change monitor (Drifting / Breached / Review due) stays on the Notes page and keeps its own frozen reference and its 2-flight persistence rule — those are the user's declared tolerances and need a status, not a rank. Trends shows the same per-limit metrics with the filter band, so a pilot can see the drift Notes is reporting. Both use `resolve_outlier_z_threshold`, the R8 band rule, and the same frozen-baseline functions; §5.2's shift is a windowed mean rather than Spec 09's per-flight test, so they can legitimately differ in timing (Notes reacts in two flights; Trends needs the window mean to move). The spec states this so it is not read as a disagreement. Q5 of Spec 09 (a Trends group for per-limit metrics) is resolved by §8.2 and §8.4. **A second source of divergence (B3):** a z-mode filter's edge on Trends is resolved against the metric's current reference, which rolls or is pinned per §5.7, while the same filter's edge on Notes is resolved against the filter's own frozen reference. The two edges agree at filter creation and drift apart as the rolling reference advances; both pages say which reference they used.

**Spec 11 (paused).** Its "what changed" diff was a per-flight, cross-topic view. The change summary here is the long-horizon case. If Spec 11 resumes, its diff should link to Trends for anything about fleet statistics rather than duplicate it; this is noted as a dependency, not decided here.

## 11. Engine contract changes (Spec 01)

### 11.1 `BaselineConfig` (§8.4)

```ts
interface BaselineConfig {
  // existing
  membership: "leave_one_out" | "all";
  band_kind_by_metric: Record<string, "oat_band" | "da_band" | null>;
  outlier_z_threshold: number;
  outlier_z_threshold_overrides?: Record<string, number>;
  // new — Spec 12
  recent_window_hours: number;            // default 10
  recent_window_min_flights: number;      // default 5
  recent_window_max_flights: number;      // default 15
  om_margin_fraction: number;             // default 0.25
  pinned_references?: Record<string, { flight_ids: string[]; set_at: string; label?: string }>;  // metric_id -> frozen membership
}
```

### 11.2 `MetricFleet` (§8.4)

```ts
interface Shift {
  recent: { flight_ids: string[]; n: number; hours_from: number; hours_to: number; mean: number };
  reference: { kind: "rolling" | "pinned"; n: number; hours_from: number; hours_to: number;
               label?: string } & Baseline;          // stratified stats via by_band when band_kind set
  shift_z: number | null;                             // null when comparison.scope == "insufficient"
  direction: "higher" | "lower" | "none";
  comparison: { scope: "band" | "all" | "mixed" | "insufficient";
                by_band?: Record<string, number>; unmatched: number };
  bend?: { reference_slope: number; recent_slope: number; fires: boolean };
  level: { om_margin: boolean; filter_edge: boolean; limit?: number; margin_line?: number };
  qualifies: boolean;                                 // §5.6
}
interface MetricFleet { /* existing fields */ shift?: Shift }   // absent below n_min or with no recent window
```

`FleetAnalysis` gains `change_summary: { metric_id: string; rank: number }[]` (the ordered list of §7, computed once by the engine so every host renders the same order) and `shift_history: ShiftEvent[]` loaded from `fleet/shift_history.json`.

### 11.3 Operations (§7)

| Operation | Change |
|---|---|
| `update_fleet` | Computes `shift` per metric (§5), `change_summary` (§7), and appends/closes shift events (§6). Reads `pinned_references` from `BaselineConfig`. |
| `set_reference(metric_id, flight_ids, label?)` / `clear_reference(metric_id)` | **New.** Writes `pinned_references`; returns the updated `BaselineConfig`. Validates `n_min` (`REFERENCE_LOW_N` warn, still saved). |
| `delete_shift_event(event_id)` | **New.** User deletion from Past changes. |

### 11.4 Diagnostics

| Code | Level | Meaning |
|---|---|---|
| `RECENT_WINDOW_CAPPED` | info | hours condition not met within `recent_window_max_flights` |
| `RECENT_WINDOW_LOW_N` | info | fewer than `recent_window_min_flights` eligible flights in total; no shift |
| `REFERENCE_LOW_N` | warn | pinned reference below `n_min` after exclusions; reverted to rolling |
| `SHIFT_COMPARISON_INSUFFICIENT` | info | more than half the recent flights unmatched (§5.3) |

### 11.5 Registry

`registry.py`'s `MetricDef` is unchanged; the `trends` declaration lives in the topic register (Spec 10), which `update_fleet` reads for `worsening` and the frontend reads for panel layout and phrasing. Per-limit metrics derive `worsening: higher` and their panel from the limit (§8.2).

### 11.7 Per-limit units and frequency

Per-limit fleet metrics carry the limit's unit from the engine profile (`peak_excess` in the limit's unit, `time_above_pct` in %, `limit_overboost_block_s` in s); `TrendsPanel` and `Shift` expose it. Each limit panel also exposes `frequency: { recent: { events: n, flights: n }, reference: { events: n, flights: n }, delta: number, z: number | null, qualifies: boolean }` and the per-flight event flags the event strip draws (§8.4). `Shift.level` carries `filter_edge_value` (B7). `ShiftEvent.kind` gains `"frequency"`.

### 11.6 New fleet metric: `takeoff_map_residual_inhg`

Per flight: the takeoff-MAP model's prediction for that flight's conditions (Spec 01 §8.4 `FleetAnalysis.models.takeoff_map`) minus the observed takeoff MAP, in inHg. Baselined like any other fleet metric (`band_kind` null; the model already absorbs DA). `worsening: either` — a growing positive residual (less boost than predicted) and a growing negative one (more) both matter. Flights without a model prediction (model below its own n gate) have a null value and are ineligible. This metric is what lets the Boost / power panel replace the standalone model view (§12); the model's coefficients and `note` are shown in the strip's caption.

## 12. UI changes (Spec 03 §5.3 — replacement text)

§5.3 of Spec 03 is replaced by a pointer to this spec's §7–§9. Items retained from the old §5.3: engine-hours x-axis; points linking to Flight view; sample counts linking to Flights; the stratification toggle rules of v0.10/v0.11; outlier ring source rules. Items removed: the metric picker; the whole-history trend line as the default statistic; the standalone model view (the `takeoff_map_residual_inhg` strip in Boost / power replaces it, with the coefficients and `note` shown in the strip's caption — §11.6).

Baselines & Models (§5.5) gains the four window/margin fields and a pinned-references table (metric, label, n, set_at, unpin). The nav shell (§4) gains the Trends badge of §9.5.

## 13. Deferred (v2), designed here

| Item | Design intent | Dependency |
|---|---|---|
| **OM headroom projection** | On a strip with an OM line and a qualifying shift, show "at the recent rate, headroom reaches zero at ~N h". Use the recent-window slope only, never the whole-history fit, and only when bend or shift qualifies. | Operating experience with the shift statistic; decide what slope is projectable. |
| **Maintenance annotations on the time axis** | Vertical markers for workspace-level events (oil change, plug change, filter created/edited, engine override, software update). A shift event adjacent to a marker is shown as explained. | Spec 02 change: a workspace event log with no flight to attach to (`events.json`). Filter/override edits can be auto-logged from existing stores. |
| **Condition strip** | Under each panel, a small strip of cruise DA, cruise OAT, duration and dominant climb VS bucket per flight, so a high point can be read against its conditions. | Panel layout settled. `cruise_da_ft` and `cruise_oat_c` feed it. |
| **Change-point detection** | CUSUM or Bayesian change-point per metric, giving a detected step time rather than a window mean. Research mode first; could later supply the shift history with better-placed events. | Research mode (Spec 06). |

## 14. Constants

| Constant | Default | Where |
|---|---|---|
| `recent_window_hours` | 10 | `BaselineConfig` |
| `recent_window_min_flights` | 5 | `BaselineConfig` |
| `recent_window_max_flights` | 15 | `BaselineConfig` |
| `om_margin_fraction` | 0.25 | `BaselineConfig` |
| shift threshold | `resolve_outlier_z_threshold(metric_id)` (2.0 default) | existing |
| `n_min` (reference gate) | existing value (10) | existing |
| bend criterion | 2 × SE of reference slope | code constant |
| insufficient-comparison rule | > 50 % of recent flights unmatched | code constant |

All `BaselineConfig` values are editable in Baselines & Models; the two code constants are not user-facing in v1.

## 15. Acceptance

1. **Window selection** — on the full log set, for every metric, the recent window satisfies both conditions or is capped with `RECENT_WINDOW_CAPPED`; a synthetic short-hop set (many 15-minute flights) hits the flight floor before the hours condition; a synthetic long-hop set hits the cap.
2. **Shift agrees with Spec 09** — for a filtered limit, the shift's stratified comparison uses the same helper as the filter monitor; a unit test with one band constructs both and asserts equal reference statistics.
3. **Seasonal false positive** — a synthetic thermal metric with a cold-weather reference and a hot-weather recent window, both within their own band's reference, produces no shift; the same data with `band_kind` null does. The real log set, replayed chronologically, is checked by hand for `oil_temp_peak` and `egt_spread` to confirm no summer shift appears under stratification.
4. **Known events** — replaying the log set, `overboost_time` enters the summary (level crossing or shift) when the 389 s-block KTOA flight (`log_20260423_135821_KTOA.csv`) enters the window and leaves when it rolls out; a shift event is recorded and closed. EGT spread's known upward trend does **not** produce a shift if the trend is steady across reference and window; a synthetic steepening does produce a bend qualifier.
5. **Rolling vs. pinned** — pinning the reference to the first 20 flights of the real set and replaying shows a slow synthetic drift (added +0.05 σ per flight) qualifying under pinned and not under rolling; unpinning restores the rolling result.
6. **History** — a shift that qualifies then clears appends one event with both timestamps; re-running `update_fleet` with no new flights appends nothing.
7. **Register-driven layout** — removing a topic's `trends` field removes it from Trends with no frontend change; adding a limit filter creates its limit panel; `GROUPS` no longer exists in `Trends.tsx`.
8. **Summary order** — a metric with an OM-margin crossing and `|shift_z| = 1.2` ranks above one with `|shift_z| = 3.0` and no crossing.
9. **Gates** — a metric with 7 eligible flights shows the building-reference message and no shift; nothing on the page draws a trend line with VERY_LOW confidence.
10. **Goldens** — a frozen `FleetAnalysis` fixture for the full log set is added (none existed before Session A; the characterization goldens cover `build_flight_metrics` only) and locks `shift`, `change_summary`, `shift_history` and the new residual metric; the web fixtures render all five panel kinds.
11. **Coupled row** — on the real log set the cylinder panel produces exactly one summary row, naming cylinder 3, and the shift history holds one event for it.
13. **Event strip and frequency** — on the real log set every limit panel opens with an event strip whose tick count equals the eligible flight count; `peak_excess` points sit under tall ticks only; a synthetic limit exceeded on 1 of 40 reference flights and 4 of 10 recent flights qualifies on frequency and opens a `frequency` shift event; the same limit with 1 of 10 recent does not.
14. **Readiness badges** — every metric below `n_min`, every never-exceeded limit and every rarely-exceeded limit shows the matching badge in every list that names it; no badged metric appears in the change summary; a collapsed panel whose metrics are all badged shows the panel-level badge summary.
15. **Units** — every limit strip's axis is labelled with the limit's unit.
17. **Tiers** — on the real log set the page shows tier 1 = Cylinder balance, Boost / power (and the volts_min limit panel while it qualifies); tier 2 = Thermal, Fuel, the four filtered limits, overboost; tier 3 = *Never exceeded (11)*, collapsed. A synthetic first event on a tier-3 limit moves it to tier 2 as *rare*; a synthetic qualification moves it to tier 1.
19. **Zoom-based pin** — on the real log set, zooming `egt_spread` to flights 20–40 and pinning yields a 21-flight pinned baseline at that x-extent, *not used* regions on both sides, and a shift computed against those 21; the alternative pins the recent window; with the full history in view the confirmation shows the notice; with fewer than `n_min` in view the control is disabled with the count.
18. **Detail strips** — no page-level toggle remains; each panel with a fit or `time_above_pct` shows *Show detail strips*; the state persists per workspace; the fit and `time_above_pct` appear only when it is on.
16. **Pin UX** — pinning a metric on the real log set changes its strip (hard-edged reference, pin marker, neutral gap region) and adds the *pinned* badge in every list; the pin confirmation shows the correct n, hours and dates; Unpin is present on the strip and in Baselines & Models; a synthetic shift that qualifies only under the pin closes with `cleared_by: "unpin"` when unpinned; the unpin preview's prediction matches the summary after unpinning.

**Test limitation (recorded):** vitest cannot render ECharts in this repo (no canvas in jsdom). Chart tests assert on the option object handed to ECharts — tick counts, tall/short, mark areas, pin marker — not on pixels. Visual verification is by live browsing against the real log set.
12. **Residual** — `takeoff_map_residual_inhg` is null for flights the model does not cover and baselined for the rest; the Boost / power strip caption shows the model coefficients and `note`.

## 16. Open questions

| # | Question | Status |
|---|---|---|
| Q1 | ~~Pinned-reference shifts: separate "since <label>" group, or merged?~~ | **Resolved (v0.2): merged.** One list, one ranking; the pinned row carries a full-weight "since <label>" qualifier (§7). A pinned reference is only ever set by someone who knows what they did, so the qualifier suffices. Revisit if it confuses in use. |
| Q2 | ~~Does the Fuel panel belong on Trends, given Spec 10 §4.2?~~ | **Resolved (v0.2): keep for v1,** last, labelled planning. The alternative home (a flight-summary surface) has no fleet view yet, so dropping the panel would remove the numbers from the long horizon entirely. Decide again at v2 once that surface exists. |
| Q3 | ~~`om_margin_fraction`: global or per limit?~~ | **Resolved (v0.2): global.** Per-limit margins in the engine profile would be invented policy of the kind the Oct 4 principles rejected; the OM gives a limit, not a margin. One visible user setting instead, with the margin line drawn on every chart it applies to (§8.3). If a skewed metric (overboost) fires too eagerly, the `outlier_z_threshold_overrides` precedent gives a place for a per-metric override later. |
| Q4 | ~~Should a shift surface outside Trends?~~ | **Resolved (v0.2): nav badge, no banner** (§9.5). |
| Q5 | ~~Replay harness: does one exist?~~ | **Resolved (v0.2): no.** Spec 09 acceptance 12 is implemented as an inline loop inside `tests/contract/test_fleet_analysis.py::test_filter_monitor_replay_fuel_pressure`, calling `update_fleet(fas[:m])` per step — correct, but not reusable. Spec 12 builds a reusable harness in Phase 1 (§17) and moves that test onto it. |

## 17. Implementation plan

| Phase | Scope | Notes |
|---|---|---|
| 1 | **Replay harness** in `tests/` (chronological `update_fleet` over a flight list, yielding per-step `FleetAnalysis`, pinnable to a date so new logs don't move results); Spec 09's `test_filter_monitor_replay_fuel_pressure` migrated onto it. Engine: window selection, shift, bend, level crossing, `Shift` on `MetricFleet`, `change_summary`, diagnostics, `BaselineConfig` fields; goldens regenerated | Harness first, so every later phase's temporal behaviour is testable; no UI change yet; CLI prints the summary |
| 2 | Engine: pinned references, `set_reference` / `clear_reference`, shift history and `shift_history.json` | Spec 02 §6 gains the file |
| 3 | Register: `trends` field for every topic; Spec 10 register updated; per-limit panel derivation | Review each assignment under A6 |
| 3b | Engine (Session B, before web): `takeoff_map_residual_inhg` (§11.6); z-mode filter-edge level crossing (§5.5); coupled-panel rows and events (§7.1, D4); frozen `FleetAnalysis` fixture (§15.10) | Small; closes the gaps Session A reported |
| 4 | Web: change summary (with coupled rows), panels, common strip behaviour, Past changes, Baselines & Models fields, Trends nav badge; remove `GROUPS` and the picker | Cylinder-balance panel refactored onto the common strip |
| 5 | Validation against the full log set per §15; constants tuned; Spec 01/03/10 revisions committed | Done (Session B) except the dependent spec revisions, carried to Phase 6 |
| 10 | **Session G.** Zoom-based pin per §5.7 / §5.7.1 v0.8: visible eligible flights → `set_reference`; *Use the recent window instead*; `n_min` floor; full-history notice; single *not used* region kind; pinned region at true extent; vitest and a replay-harness test; acceptance 19. | Small; lifted unchanged from the v0.8 Phase 9 scope |
| 9 | **Session F.** Three-tier panel ordering and the collapsed *Never exceeded (N)* group (§9.1); per-panel *Show detail strips* replacing the page-level toggle (§8.3); **zoom-based pin** with the recent-window alternative, `n_min` floor and full-history notice (§5.7, §5.7.1) — web passes the visible eligible flights to the existing `set_reference`; *not used* as the single outside-pin region; Spec 03's stale pin wording corrected; vitest for tiers, the group and the pin selection. | One session; the pin change is small because the engine operation already exists |
| 8 | **Session E.** Wording and rendering only, no engine change: labels *Pin baseline to these flights* / *Unpin baseline*; confirmation and unpin copy per §5.7.1 v0.6 including the small-baseline caution; badge text *baseline pinned*; muted *not used* region left of the pinned baseline (gap region retained for the moved-on case); Baselines & Models table retitled *Pinned baselines*; help text updated; vitest cases updated for the new region and copy. | Half a session |
| 7 | **Session D.** Pin UX per §5.7.1: visible pinned state and gap region, *pinned* badge, pin confirmation with preview, Unpin on strip and in Baselines & Models, `cleared_by` on events, unpin preview from the engine; vitest for the new states; acceptance 16. | Small, web-heavy; one engine field and one preview operation |
| 6 | **Session C.** Engine: event frequency (§5.8), per-limit units and frequency on the contract (§11.7), `frequency` shift events, readiness states on the contract; frozen fleet fixture updated. Web: event strip and limit-panel layout (§8.4), readiness badges everywhere a metric is named (§9.3), `time_above_pct` behind the toggle; vitest coverage for the Session B components and the new strip. Spec: the R5.2 dependent revisions (Specs 01, 02, 03, 08, 09) if still outstanding. Validation: the EGT3-max and volts-min panels read correctly on the full set, and the volts summary row's reason (shift, OM margin or filter edge) is identified. | No new statistics beyond §5.8 |

Phases 1–9 are done (Sessions A–F); Phase 10 is Session G.

**Session F result (Oct 2026):** tiers render as specified — volts_min, cylinder balance, boost/power (tier 1, summary order), six watched panels (tier 2), *Never exceeded (14)* collapsed (tier 3). Detail strips per panel; page-level toggle gone. Spec 03 → v0.16. Zoom-based pin not delivered (prompt version mismatch); carried to Phase 10.

**Session E result (Oct 2026):** pin wording and regions aligned with v0.6; validated on `egt_spread` (40 not used · 10 pinned · 10 window; badge identical in all three places); no legacy pin strings remain.

**Session D result (Oct 2026):** pin/unpin UX live; validation on the real set exposed that the built semantics (window → baseline) differed from the spec's description (freeze older reference); after review the built semantics were adopted and the spec corrected (v0.6). Also fixed in passing: the reference and recent regions had rendered with one tint since Session B (ECharts markArea styling), so the strips had been missing their main visual cue.

**Session C result (Oct 2026, full log set):** every limit panel opens with a 50-tick event strip; eleven limits are *never exceeded*; overboost is *rare* (one tall tick, KTOA); four filtered limits show *filtered*. No frequency qualified. `volts_min` ranks on shift at `shift_z = −18` with frequency falling (2 of 10 recent vs 21 of 40 reference) — rarer but far larger low-voltage excursions in the recent window; flagged for the pilot to examine before anything else, as a flight-ops question outside this spec. Each phase is testable on its own against the log set.

**Session A result (Oct 2026, full log set):** two qualifying shifts, both cylinder deviations — EGT3 +4.02 σ, EGT2 −2.51 σ over the last 10 h (10 flights vs 40 reference, mixed scope), both with bend; EGT spread +1.76 σ with bend (recent slope ≈ 2.9× reference), below threshold; no level crossings. The coupled-row rule (D4) came from this result. The register already existed at `docs/specs/topics/register.json`, so no new document was created; Spec 10 moved to v0.9.
