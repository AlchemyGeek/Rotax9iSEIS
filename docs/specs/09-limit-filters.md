# Spec 09 — Limit Filters and Change Monitoring

**Project:** SlingologyEIS
**Status:** v0.8 — implemented (engine 0.19.0), Phases 1–5 (§16); Q5 (Trends group) remains a follow-up
**Suggested repo path:** `docs/specs/09-limit-filters.md`
**Builds on:** Spec 01 (engine contract, baselines §8.4, insight rules, annotations R3), Spec 02 (workspace files, `FleetSelection`), Spec 03 (Flight view, Baselines & models, Notes page), Spec 08 (persistence pattern for consecutive-flight insights)
**Baseline reviewed:** branch `webui` at commit `3f71549` (2026-09-29), engine 0.14.0

**Revision history**

| Version | Change |
|---|---|
| 0.1 | Initial spec from the design discussion of 2026-09-29. |
| 0.2 | Filters are built on the baseline machinery instead of a parallel statistics stack. Per-limit monitor metrics are registered as ordinary baseline metrics for every limit. A filter's reference is a **frozen baseline**: a fixed set of flights, evaluated with the existing baseline functions, honouring excluded flights and OAT/DA stratification. `drift_z` is removed in favour of the metric's `outlier_z_threshold`. The filter editor gains a "what would this hide?" preview reusing the rule playground's diff. New §2: plain-language comparison of baselines and filters. |
| 0.3 | Q8 resolved: `baseline_deviation` moves to stratified comparison as well (Spec 01 v0.13, R8). Filters and baseline insights now share one rule for choosing comparable flights: same band if it has `n_min` points, otherwise all flights. §7.1 and §8.2 reference that rule instead of restating it. |
| 0.4 | Phase 1 implemented. Q3 and Q6 resolved from the log-set report (§6.2, §15). KACV counts corrected: the "77 events" of §1 predate the current checker; before merging it finds 38 on that log. `FlightAnalysis.limits` added (§11.1). Runs split where phase filtering leaves a time gap (§6.2). New §16: phased implementation plan and status. |
| 0.5 | Phase 2 implemented. Q7 resolved: `fuel_press_max` is OAT-stratified (§6.5). Engine-running time and the per-limit metric naming pinned down (§5). |
| 0.6 | Phase 3 implemented, including z mode and the frozen baseline (moved up from Phase 4, since z needs them). Q1 and Q2 adopted as proposed, with 916iS placeholder caps listed in §6.3. Where the computed limits' policies live (§6.3); notes follow a limit across filtered/breach insights (§10.1). |
| 0.7 | Phase 4 implemented. A std floor for `time_above_pct` added to §13; the effective reference, invalid filters and the Drifting windows pinned down (§8, §16). |
| 0.8 | Phase 5 implemented: copy filters between same-model workspaces (§9). |

**Note on numbering:** Number 06 stays reserved for the tabled research mode.

---

## 1. Problem

Limit insights compare every flight against the engine profile's OM limits. On a real aircraft, some parameters sit consistently a little past a limit because of instrumentation, sensor accuracy, or the individual engine. The same exceedance then fires on every flight. The pilot learns to skim past the limits topic, which defeats its purpose.

The KACV log (`log_20260423_200615_KACV.csv`) shows the problem at full scale:

- **Fuel pressure maximum (46.0 psi, CAUTION):** 77 events, 3 h 26 min above the limit in a 4 h 27 min window. (Counted before the current `min_duration_by_phase` rules; the engine 0.16 checker finds 38 events on this log.) Peaks are mostly 46.1–46.4 psi, sometimes 47–48.2 psi, and once 50.4 psi for 33 min.
- **Fragmentation:** most gaps between those 77 events are 3–30 s. The reading dips to 46.0 psi for a second and the checker starts a new event. Each event becomes its own insight.
- **Duplication:** an oil or coolant temperature exceedance fires twice, once in `limit_exceedances` (from the engine profile) and once in `oil_temp_peak` / `coolant_temp_peak` (from a hard-coded `"limit": 248` in `insight_rules.json`).

The pilot needs to silence known, consistent exceedances and still be told when that behaviour changes.

## 2. Baselines and filters in plain language

This section is written for pilots, not developers. It can be reused in the README user manual.

**Your baseline** is the tool's memory of what is normal for your engine. It learns automatically from your flights and keeps learning. It tells you when a flight is unusual *for your aircraft*, even if nothing went past an OM limit.

**A filter** is your own statement about one OM limit: "on my aircraft, this limit is exceeded in a way I understand and accept." You set it, you explain why, and the tool keeps quietly watching that limit for you. If the exceedance gets bigger, longer, or more frequent than when you set the filter, you are told.

| | Baseline | Filter |
|---|---|---|
| **Question it answers** | "Is this flight normal for my engine?" | "Is this limit exceedance one I already know about?" |
| **Who creates it** | The tool, automatically | You, from a limit insight |
| **What it covers** | Engine measurements such as EGT spread, oil and coolant peaks, fuel flow | Only OM limits (the red and yellow lines in the Operators Manual) |
| **What it compares against** | Your own past flights | The OM limit, plus how your engine behaved around it when you set the filter |
| **Over time** | Keeps learning from every new flight | Stays as you set it. Its "normal" is frozen until you choose to re-baseline |
| **Why the difference** | Tracks your engine as it ages | A filter that kept learning would slowly accept a problem that is getting worse |
| **When something is off** | A "watch" insight: unusual for your engine | "Beyond your filter" at the limit's normal severity; everything else is collapsed into one quiet line |
| **How it reports change** | Trends on the Trends page | A status on the Notes page (Stable, Drifting, Breached, Review due) and a badge on Notes |
| **Weather** | Compares flights in similar outside temperature or density altitude where it matters, and falls back to all flights until there are enough similar ones | Same rule |
| **Flights you excluded** | Ignored | Ignored |
| **Where you manage it** | Baselines & models page | Notes page |
| **Risk if misused** | Low: it only adds information. A bad flight can skew it, so exclude that flight | Higher: a filter can hide a real problem. That is why it requires a reason, has limits on red-line parameters, and asks you to review it periodically |

**They work together.** A filter hides known exceedances; it does not switch off the baseline. If you filter oil temperature because your gauge reads a few degrees high, a flight that is unusually hot *for your engine* still gets a "watch" insight from the baseline.

**Example.** Your fuel pressure reads 46.1–46.4 psi against a 46.0 psi maximum on almost every flight. You set a filter: "up to 2.5 psi over is fine; the sender reads high, confirmed by my mechanic." From then on each flight shows one quiet line, "fuel pressure: 17 readings within your filter." A reading of 50.4 psi would still show as a caution, marked "beyond your filter." If, over the next flights, the pressure spends more and more of each flight above 46.0, the Notes page marks the filter **Drifting**, even though no single reading broke your 2.5 psi margin.

## 3. Goals

1. Let the pilot set a workspace-wide **filter** on any OM limit, starting from an exceedance insight, and manage it on the Notes page.
2. Two independent filter conditions, matching two pilot intentions: **magnitude** ("a little high is fine") and **duration** ("brief spikes are fine").
3. Filtered exceedances are **suppressed, not deleted**. They collapse into one informational insight that expands to the individual events.
4. A **change monitor** on every filter reports breaches, drift inside the band, and filters that are overdue for review.
5. **Guardrails** for WARNING-severity limits.
6. Fix fragmentation (one insight per limit per flight, and jitter-tolerant event detection) and duplication (topic threshold insights follow the profile limit).
7. **Reuse the baseline machinery** for all statistics: one set of functions, one exclusion list, one z threshold per metric, the same stratification.

**Non-goals:**

- Filtering `baseline_deviation` or `trend` insights. They are measured against the aircraft's own history, so a constant bias doesn't make them repeat; their tuning belongs to the rule playground and per-metric overrides.
- New insights from the per-limit baseline metrics (§5). They are baselined and charted, but no rule in `insight_rules.json` triggers on them. Their only consumer in this spec is the filter monitor.
- Changing OM limit values. `engine_overrides.json` (Spec 02) remains a separate, undesigned idea. A filter never changes the displayed limit.
- Shutdown artifacts (e.g. KACV's −0.6 psi fuel pressure and 0.0 V bus at 00:35). These are a phase-suppression gap to be investigated separately, not something to filter.
- A Trends-view group for the per-limit metrics (follow-up, §15).

## 4. Concepts

**Limit.** One entry in an engine profile's `limits` list, plus the two computed EGT split limits and the overboost limit. Identified by a new stable `limit_id` (§6.1).

**Filter.** A per-workspace record attached to exactly one limit. It holds a magnitude condition, a duration condition, or both. The UI presents the two as separate toggles. At most one filter per limit per workspace.

**Excess.** How far an event went past the limit, in engine units (Spec 01 §6.4): `observed − limit` for MAX, `limit − observed` for MIN. Always positive for a real exceedance.

**Suppression rule (either-filter).** An event is suppressed if the magnitude condition tolerates it **or** the duration condition tolerates it. Each condition says "this kind of exceedance is fine"; an event needs only one reason to be fine.

**Breach.** An event on a filtered limit that neither condition tolerates. It is reported at the limit's normal severity, marked "beyond your filter".

**Live baseline.** The existing all-flights baseline from `update_fleet` (Spec 01 §8.4): every included flight, recomputed on "Rebuild baselines".

**Frozen baseline.** A baseline over a fixed list of flight IDs chosen when a filter is created or re-baselined, computed with the same functions (`baseline`, `baseline_stratified`) as the live baseline. The **membership** is frozen; the numbers are recomputed from the current flight analyses, so they stay correct after an engine upgrade re-analyses the flights, and a flight later excluded from baselines drops out of the frozen baseline as well.

## 5. Per-limit baseline metrics

Every limit in the workspace's engine profile gets two per-flight metrics, filtered or not:

| Metric id | Flight metric column | Definition |
|---|---|---|
| `limit_<limit_id>_peak_excess` | `lim_<limit_id>_peak_excess` | Largest excess of any (merged) event on the flight. Missing (NaN) if the flight had no event. |
| `limit_<limit_id>_time_above_pct` | `lim_<limit_id>_time_above_pct` | Total duration of the limit's events ÷ engine-running time, in %. 0 if no events. |

For `overboost`, `peak_excess` is replaced by `limit_overboost_block_s`, the longest continuous block (`ob_max`), and `time_above_pct` is not produced.

- Computed in `analyze_flight` from `FlightAnalysis.exceedances` after merging (§6.2). Engine-running time uses phase detection (engine start to shutdown), so the metric doesn't depend on flight length. Implemented as the span of rows not labelled `PRE_START` or `SHUTDOWN` (`limits.engine_running_s`).
- Limits never checked for events (`report_in_exceedances: false`, e.g. `oil_temp_optimal_low`) get no metrics. `peak_excess` is missing with reason `NOT_APPLICABLE` on a flight without events, and both are `CHANNEL_MISSING` when the log lacks the limit's channel.
- The overboost metric is `lim_overboost_block_s` on the flight and `limit_overboost_block_s` in the fleet.
- `BASELINE_LOW_N` fleet diagnostics are not emitted for these metrics; the filter monitor reports its own (`FILTER_REFERENCE_LOW_N`).
- Registered in the metric registry and added to `BASELINE_METRIC_DEFS`, generated from the engine profile rather than hand-listed. Their stratification band comes from the limit's `stratify_by` (§6.5).
- `update_fleet` baselines them exactly like every other metric: points, trend over engine hours, outliers at `resolve_outlier_z_threshold(metric_id)`, and stratified baselines.
- They have no insight rules (§3 non-goals) and are hidden from the Trends view until the follow-up (§15).
- **Share of flights with events** is derived from the `time_above_pct` points (value > 0); it is not a separate metric.

## 6. Engine profile changes

### 6.1 Stable limit IDs

Add `id` to every entry in `limits` in all four `engines/*.json`. `param` plus side is not unique today: `rpm` has three limits and `oil_press_psi` has two MAX limits.

Proposed IDs for the 916iS:

| Label | `id` |
|---|---|
| Idle RPM minimum | `rpm_idle_min` |
| Max continuous RPM | `rpm_continuous_max` |
| Takeoff RPM (5-min limit) | `rpm_takeoff_max` |
| Oil pressure min (>3500 rpm) | `oil_press_min` |
| Oil pressure max (>3500 rpm) | `oil_press_max` |
| Oil pressure max (cold start) | `oil_press_cold_max` |
| Oil temp minimum (takeoff) | `oil_temp_takeoff_min` |
| Oil temp maximum | `oil_temp_max` |
| Oil temp optimal band (low) | `oil_temp_optimal_low` |
| Coolant temp maximum | `coolant_temp_max` |
| EGT1–4 maximum | `egt1_max` … `egt4_max` |
| Manifold pressure maximum | `map_max` |
| Fuel pressure minimum | `fuel_press_min` |
| Fuel pressure maximum | `fuel_press_max` |
| Bus voltage minimum | `volts_min` |
| Bus voltage maximum | `volts_max` |

The two computed EGT split limits get fixed IDs `egt_split_high_flow` and `egt_split_low_flow`, declared in the profile's `egt_spread` section. The overboost limit gets `overboost` in the `overboost` section. The same ID means the same limit across engine models. `limits.py` fails loudly on a missing or duplicate ID.

### 6.2 Exceedance merge gap

New profile-level field:

```json
"exceedance_merge_gap_s": 30
```

An event ends only when the reading has stayed within the limit for at least this many seconds. Shorter dips are absorbed into the event. The gap is measured in **time** (`datetime`), not rows, because phase filtering (`lim.phases`) makes rows non-contiguous. Merging happens **before** the existing `time_limit_s`, `min_duration_s` and `min_duration_by_phase` checks, so those apply to the merged event. Value is a placeholder to be tuned on the full log set (§14).

On KACV, fuel pressure max goes from 38 events to 33 at a 5 s gap, 7 at 30 s, and 3 at 120 s.

**Chosen value (Phase 1, from `notebooks/05_limit_events_report.py` on the N117ZS log set, 107 logs):** 30 s. Across the log set fuel pressure max drops from 573 events to 158 at 30 s (138 at 60 s); 82% of its within-limit gaps between raw runs are ≤ 30 s, and the curve flattens past 30 s. No limit gains a time-limit (5-minute rule) event from merging.

**Per-limit override** `exceedance_merge_gap_s` on a limit entry replaces the profile value for that limit (Q3). `rpm_idle_min` ships with 0: its `min_duration_s: 30` exists to ignore brief governor dips, and merging joins those dips into events that then pass the 30 s rule (54 → 100 events at a 30 s gap, 10–18 flights with idle events that had none).

**Runs split at time gaps.** Phase filtering drops rows, so two exceeding stretches either side of an excluded phase were adjacent in the filtered frame and read as one run. A run now breaks wherever consecutive rows are more than 1.5× the median sample period apart; merging then decides, in time, whether to re-join them. This also applied before Spec 09 and is fixed regardless of the gap.

### 6.3 Filter policy

New optional per-limit field:

```json
"filter_policy": {
  "filterable": true,
  "max_band_abs": 35.0,
  "max_duration_s": 10,
  "review_interval_h": 25
}
```

Defaults, when the field is absent:

| Profile severity | `filterable` | Magnitude modes | Band cap | Duration cap | Note | Review interval |
|---|---|---|---|---|---|---|
| CAUTION | true | absolute, percent, z | none | none | optional | 50 h |
| WARNING | **false unless `max_band_abs` and `max_duration_s` are declared** | absolute, percent | `max_band_abs` | `max_duration_s` | required | 25 h |

The WARNING default is fail-safe: a WARNING limit becomes filterable only once its profile declares caps. The 916iS ships with placeholder caps marked `PLACEHOLDER`, the same way the 912iS/914iS profiles mark unverified values. The z mode is never allowed on WARNING limits.

`filterable: false` makes a limit non-filterable regardless of severity. Proposed default for `oil_press_min`: non-filterable (Q1).

**As implemented (Phase 3).** `oil_press_min` carries `"filter_policy": {"filterable": false}` in all four profiles. The computed limits' policies live in their own sections: `egt_spread.high_flow_filter_policy` / `low_flow_filter_policy`, and `overboost.filter_policy` (band cap in seconds; no duration cap). The 916iS placeholder caps, each marked `PLACEHOLDER` in the profile, chosen conservatively (about sensor-accuracy scale) pending real values (Q2):

| Limit | `max_band_abs` | `max_duration_s` |
|---|---|---|
| `rpm_takeoff_max` | 50 rpm | 10 s |
| `oil_temp_takeoff_min`, `oil_temp_max`, `coolant_temp_max` | 5 °F | 10 s |
| `egt1_max` … `egt4_max`, `egt_split_high_flow`, `egt_split_low_flow` | 20 °F | 10 s |
| `map_max` | 0.5 inHg | 5 s |
| `fuel_press_min` | 1.0 psi | 10 s |
| `overboost` | 30 s | — |

The 912iS, 914iS and 915iS profiles declare no caps, so their WARNING limits are not filterable yet (fail-safe default).

### 6.4 Overboost

`overboost` gains `close_call_margin_s: 60`, replacing the hard-coded 240 s in `topics.overboost()`. The overboost limit is a time (300 s maximum continuous block), so:

- Its filter supports magnitude only (absolute or percent, in seconds). No duration condition.
- It is treated as WARNING (it is the same OM 5-minute rule as takeoff RPM).
- With a band `b`, the effective limit is `300 + b` and the close-call threshold is `300 + b − close_call_margin_s`. A pilot whose normal procedure produces 250 s blocks can set +20 s: the effective limit becomes 320 s, the close call starts at 260 s, and 250 s is silent.

### 6.5 Stratification

New optional per-limit field `stratify_by: "oat_band" | "da_band" | null`, used for the §5 metrics. Defaults follow the research paper §9 convention already used by `BASELINE_METRIC_DEFS`:

| Limits | Default |
|---|---|
| Oil temp, coolant temp, EGT1–4, EGT split | `oat_band` |
| MAP, overboost | `da_band` |
| Everything else (fuel pressure, oil pressure, RPM, volts) | none |

Whether fuel pressure depends on OAT (fuel temperature) is an open question (Q7); the log-set report in §14.2 should show whether any unstratified limit metric clearly varies by band.

**From the log-set report (Phase 2, 53 flights):** `fuel_press_max` peak excess varies with OAT band (eta² 0.18; cold +4.1 psi, mild +3.3 psi), so the 916iS and 915iS profiles set `stratify_by: "oat_band"` on it; its time-above share does not (eta² 0.07). The large density-altitude effects on the `time_above_pct` of `fuel_press_min` and `rpm_continuous_max` (eta² 0.40) follow flight profile (short low-DA flights with more takeoffs and pattern work), not weather, so those stay unstratified. The other stratified limits (temperatures, EGT, MAP, overboost) have too few events on this aircraft to test.

## 7. Filter semantics

### 7.1 Magnitude condition

| Mode | Stored value | Tolerated when |
|---|---|---|
| `absolute` | `value` in engine units | `excess ≤ value` |
| `percent` | `value` in % | `excess ≤ |limit| × value / 100` (computed in engine units) |
| `z` | `value` (z) | `(excess − ref.mean) / ref.std ≤ value`, where `ref` is the filter's frozen baseline of `peak_excess` |

For percent and z, the UI always shows the resolved band in display units next to the setting ("3% → up to 47.4 psi"). Percent is computed in engine units, so switching the display between imperial and metric doesn't change what is filtered.

**z reference.** The frozen baseline of `limit_<id>_peak_excess` over the filter's reference flights (§8.1), choosing the comparison set by the same rule `baseline_deviation` uses (Spec 01 §8.4, R8): the event's flight band if the limit is stratified and the reference has at least `n_min` flights with events in that band, otherwise the unstratified frozen baseline. `n_min` is the same value used by `baseline_deviation` (10). Below it, the z mode is not offered, and an existing z filter becomes invalid (§11.4). A `std` floor (§13) prevents a near-constant reference from making every event a breach.

### 7.2 Duration condition

`max_event_s`: an event is tolerated if its (merged) duration is at most this. Measured per event, after merging. For WARNING limits, `max_event_s ≤ filter_policy.max_duration_s`.

### 7.3 Validation

The engine validates filters, not only the UI:

- `limit_id` exists in the workspace's engine profile, and the limit is filterable.
- The mode is allowed for the limit's severity; band and duration are within caps.
- A note is present for WARNING limits.
- A z reference has `n ≥ n_min`.

An invalid filter is ignored (the limit reports as unfiltered) and produces a diagnostic (§11.4). Filters are per workspace and the workspace's engine model is fixed by construction (Spec 02 §5.6), so a filter can't silently apply to the wrong engine.

### 7.4 Scope in time

Filters apply retroactively to every flight in the workspace. A flight's insights always reflect the current filters, not the filters that existed when it was first analysed.

## 8. Change monitor

Every valid filter is monitored. Computation is stateless and reads the per-limit metrics from the `FleetAnalysis` (§11.2).

### 8.1 Reference and monitored flights

- **Reference flights:** the `reference_n` most recent **included** flights (by flight date) when the filter was created or last re-baselined. Only the flight IDs are stored. If fewer than `reference_min_n` exist, the reference extends forward over the next included flights until it reaches `reference_min_n`; status is **Collecting** until then.
- **Frozen baseline:** the §5 metrics' points from `FleetAnalysis` restricted to the reference flight IDs, run through `baseline` / `baseline_stratified`. Because `FleetAnalysis` points already omit excluded flights, a reference flight the pilot later excludes drops out automatically.
- **Monitored flights:** included flights dated after the last reference flight. A log imported later but dated earlier appears on the chart and is not used for drift.
- **Editing the band or duration** resets the reference to the current most recent flights and adds a history entry (§9).
- **Timing matches baselines.** Like `evaluate_insights`, the monitor uses the exclusion list and `baseline_config` carried in the `FleetAnalysis` provenance. Toggling an exclusion takes effect on the next "Rebuild baselines", consistent with Spec 03 §5.5.

### 8.2 Statuses

Evaluated in priority order; the first match wins.

| Status | Condition |
|---|---|
| **Breached** | At least one breach (magnitude or duration) on a monitored flight since the filter was last reviewed. |
| **Drifting** | On each of the 2 most recent monitored flights, `peak_excess` or `time_above_pct` sits more than *z* above the frozen baseline mean (worsening direction only), where *z* = `resolve_outlier_z_threshold(metric_id)`. Stratified limits choose the comparison set by the Spec 01 R8 rule: the flight's own band where the band has `n_min` reference points, else the unstratified frozen baseline. **Or**: over the last `frequency_window` monitored flights, the share with events exceeds the reference share by at least `frequency_delta`. |
| **Review due** | Engine hours since creation or last review exceed the limit's `review_interval_h`. |
| **Quiet** | No events on the last `quiet_window` monitored flights. Informational: the filter may no longer be needed. |
| **Collecting** | Reference not yet at `reference_min_n`. |
| **Stable** | None of the above. |

Using the metric's own `outlier_z_threshold` keeps Spec 01's "one threshold, two consumers" principle: the same number marks a point as an outlier on the chart and decides drift. Adjusting it in the rule playground changes both. The 2-flight persistence reuses the Spec 08 `cylinder_rank` pattern.

**Mark reviewed** records the time and engine hours. It clears Breached and Review due. It does not clear Drifting, which clears only when the condition stops holding or the pilot re-baselines.

## 9. Storage — `filters.json`

New workspace file, next to `annotations.json` (Spec 02 §6):

```ts
interface LimitFilterStore {
  version: "1";
  filters: LimitFilter[];
}

interface LimitFilter {
  id: string;                          // stable, e.g. uuid
  limit_id: string;                    // §6.1
  magnitude?: {
    mode: "absolute" | "percent" | "z";
    value: number;                     // engine units / % / z
  };
  duration?: { max_event_s: number };
  note: string;                        // required for WARNING limits
  created_from?: { flight_id: string; insight_id: string };
  reference: { flight_ids: string[]; set_at: string };   // frozen membership only; stats are recomputed
  created_at: string;
  updated_at?: string;
  reviewed_at?: string;
  reviewed_engine_hours?: number;
  history: {
    at: string;
    action: "created" | "edited" | "rebaselined" | "reviewed";
    before?: Partial<LimitFilter>;
    after?: Partial<LimitFilter>;
  }[];
}
```

At least one of `magnitude` or `duration` must be present. Removing a filter deletes the record; history is not kept after removal.

**Copying between workspaces:** a "Copy filters from…" action on the Notes page copies filters from another workspace **with the same engine model**. Copies get new IDs and a fresh reference from the target workspace's flights. If the target has too few flights for a z filter, the copy is flagged invalid. Nothing is copied automatically.

## 10. Insights

### 10.1 One insight per limit per flight

`limit_exceedances` changes from one insight per event to one insight per limit per flight. This applies whether or not a filter exists. Each insight carries its events; the UI expands to them.

| Situation | Insights for that limit on the flight |
|---|---|
| No filter | One insight at the rule's severity: event count, worst peak, total time above. |
| Filter, all events suppressed | One `filtered` insight: `info` for CAUTION limits, `watch` for WARNING limits. "N events within your filter." |
| Filter, some events breach | One breach insight at the rule's severity ("beyond your filter"), listing only the breaching events. Plus one `filtered` insight for the suppressed rest, if any. |

Insight IDs become `content_hash({flight_id, topic_id, limit_id, kind})`, where `kind` is `exceedance | filtered | breach`. That makes them stable across wording changes, which also fixes the note-orphaning edge noted in `evaluate_insights` for this topic.

Because `kind` is part of the id, adding a filter (or a flight gaining its first breach) changes which id a limit's insight has. A note keyed to one kind of a limit's insight is therefore also shown on that limit's first insight when its own kind has none, rather than disappearing from view (Phase 3).

### 10.2 Topic threshold insights follow the limit

`threshold` triggers in `insight_rules.json` stop carrying a number and reference a profile limit:

```json
{ "type": "threshold", "limit_ref": "oil_temp_max", "severity": "limit" }
```

Applies to `oil_temp_peak` (`oil_temp_max`), `coolant_temp_peak` (`coolant_temp_max`) and `overboost_time` (`overboost`). A topic threshold insight fires only if the flight has at least one **unsuppressed** event for that limit. Filters therefore work on topics automatically, including duration filters, and the two places can't disagree.

The topics' `baseline_deviation` triggers are unaffected: a filter never suppresses them (§2, "They work together").

This is a behaviour change even without filters: a peak above 248°F that the profile's own phase or minimum-duration rules exclude no longer fires the topic threshold insight. `insight_rules.json` version goes to 1.3. A `limit_ref` that doesn't resolve is a rules-load error.

### 10.3 Overboost

The overboost topic applies the filter band to `ob_max` and shifts the close call with it (§6.4). A filtered overboost produces the `filtered` insight at `watch`; the close call follows the effective limit.

### 10.4 Where the change monitor surfaces

- **Notes page:** the home for filter health (§12.2).
- **Nav badge on Notes:** count of filters that are Breached or Drifting.
- **Flight view:** breach insights only (§10.1). Drift is a fleet-level fact and is **not** repeated as a per-flight insight.
- **Flights view (landing):** one-line banner when any filter is Breached or Drifting, linking to Notes. This replaces the old `fleet_insights.txt` line; the web UI has no separate fleet-summary view.

## 11. Engine contract changes (Spec 01)

### 11.1 Exceedances and flight metrics

`FlightAnalysis.exceedances[]` gains:

- `limit_id: string`
- `event_id: string` — `limit_id` + start UTC; stable reference for annotations and drill-down
- `excess: number`
- merged durations (§6.2)

`FlightAnalysis.metrics` gains the §5 columns. `analysis_key` changes, because event detection and metrics change.

`FlightAnalysis.limits` (added in Phase 1): the engine profile's limit catalogue this flight was checked against, one entry per limit side: `{id, param, label, unit, limit_type, limit_value, severity, time_limit_s, report_in_exceedances, stratify_by, filter_policy?, close_call_margin_s?}`. It lets `evaluate_insights` resolve a `limit_ref` and a filter's limit without taking the engine profile as a new argument, and it is covered by `analysis_key` through the profile hash. Empty for analyses written before engine 0.17; those fall back to the legacy numeric thresholds until re-analysed.

### 11.2 Operations

| Operation | Change |
|---|---|
| `update_fleet` | Baselines the §5 metrics like every other metric, from the generated `BASELINE_METRIC_DEFS`. No new arguments. |
| `evaluate_insights(fa, fleet, rules, annotations?, filters?)` | New `filters` argument (the workspace's `LimitFilter[]`). Applies §7 and §10. z-mode filters read their frozen baseline from `fleet`. `InsightSet` gains `filters_hash`; the host's insight cache key includes it. `analysis_key` and `fleet_key` do not depend on filters. |
| `evaluate_filter_health(flight_analyses, fleet, filters, engine_config)` | **New.** Returns `FilterHealth[]` (§11.3). Frozen and live baselines come from `fleet`; breach detection reads the flights' events. |
| `propose_limit_filter(flight_analyses, fleet, limit_id, engine_config)` | **New.** Returns a pre-filled draft: the limit, its policy (allowed modes, caps, note requirement), the live baseline of this limit's `peak_excess` and `time_above_pct`, a suggested absolute band (the live baseline's max excess, rounded up), the proposed reference flight IDs, and whether z is available. |
| `preview_limit_filter(flight_analyses, fleet, rules, filters, draft)` | **New.** Re-runs `evaluate_insights` over every included flight with and without the draft and returns the per-flight diff: events newly suppressed, breaches, topic insights removed. Same diff shape as the rule playground (Spec 03 §5.5). |
| `validate_limit_filter(filter, engine_config, fleet?)` | **New.** Returns diagnostics; used by the host before saving and internally by the operations above. `fleet` is needed only to check a z reference's `n`. |

### 11.3 Types

```ts
interface Insight {
  // …existing fields
  limit_id?: string;
  filter?: { filter_id: string; outcome: "suppressed" | "breach" };
  events?: {
    event_id: string;
    elapsed_s: number; duration_s: number;
    observed_value: number; excess: number;
    suppressed_by: "magnitude" | "duration" | null;
  }[];
}

interface FilterHealth {
  filter_id: string; limit_id: string;
  valid: boolean;
  status: "breached" | "drifting" | "review_due" | "quiet" | "collecting" | "stable";
  reasons: string[];                       // e.g. "time above limit rose on the last 2 flights"
  resolved_band?: { value: number; unit: string };
  frozen_baseline: {                       // same Baseline shape as FleetMetric.baseline / by_band
    peak_excess: Baseline & { by_band?: Record<string, Baseline> };
    time_above_pct?: Baseline & { by_band?: Record<string, Baseline> };
    share_with_events: number;
  };
  series: { flight_id: string; date: string; engine_hours: number; band?: string;
            in_reference: boolean; peak_excess?: number; time_above_pct?: number;
            events: number; suppressed: number; breaches: number }[];
  last_breach?: { flight_id: string; event_id: string };
  hours_since_review: number;
  diagnostics: Diagnostic[];
}
```

### 11.4 Diagnostics

| Code | Level | When |
|---|---|---|
| `FILTER_UNKNOWN_LIMIT` | warn | `limit_id` not in the engine profile |
| `FILTER_NOT_ALLOWED` | warn | Limit not filterable, mode not allowed, or cap exceeded |
| `FILTER_NOTE_REQUIRED` | warn | WARNING limit filter without a note |
| `FILTER_REFERENCE_LOW_N` | warn | z reference below `n_min`, including after exclusions removed reference flights |
| `FILTER_MULTIPLE_FOR_LIMIT` | warn | More than one filter for the same limit; all but the newest ignored |

### 11.5 Host / server

`server.py` gains ops mirroring annotations: `list_filters`, `propose_filter`, `preview_filter`, `save_filter` (validates first), `delete_filter`, `review_filter`, `rebaseline_filter`, `filter_health`, `copy_filters`. `workspace.py` gains load/save for `filters.json`. Saving or deleting a filter invalidates cached insight sets for the workspace, not flight or fleet analyses.

## 12. UI (Spec 03)

### 12.1 Flight view — limits topic

- One card per limit (§10.1). Collapsed: label, event count, worst peak, total time above. Expanded: one row per event, each with the existing click-to-zoom evidence.
- `filtered` cards render quietly (info or watch styling) with the filter summary: "17 events within your filter: up to +2.5 psi".
- Breach cards show "beyond your filter" and the band.
- Every limit card has **Filter this limit…** next to **Add a note**. It opens an inline editor, pre-filled from `propose_limit_filter`: limit and OM value, this flight's peak, your aircraft's typical and worst excess, suggested band. Magnitude and duration are separate toggles. Only allowed modes are shown, caps are enforced, and the note is required where applicable. If a filter already exists, the action reads **Edit filter…**.
- **Preview before saving.** The editor shows the `preview_limit_filter` result: "This would hide 412 events on 38 flights; 2 flights would still show a breach," with the list of affected flights.

### 12.2 Notes page

A new **Limit filters** section above the existing notes list, with a short link to the §2 explanation ("How filters differ from baselines"). One card per filter:

- Status badge (§8.2) and the reasons.
- Limit, OM value, resolved band and duration, and the note.
- Two small charts over flights: `peak_excess` and `time_above_pct`, with the reference flights shaded and the band drawn on the peak chart. Breaching flights marked. For stratified limits, points are coloured by band, matching the Trends view's stratified style.
- Last breach (links to the flight), hours since review.
- Actions: **Edit**, **Re-baseline**, **Mark reviewed**, **Remove**, and a collapsible history.
- Section-level action: **Copy filters from…** (§9).

The Flight view editor saves into the same store, and the new filter appears here.

### 12.3 Nav and Flights view

The Notes nav item shows a badge with the number of filters that are Breached or Drifting. The Flights view shows the one-line banner from §10.4.

### 12.4 Baselines & models

No new controls. The per-limit metrics' `outlier_z_threshold` overrides appear in the rule playground's per-metric list like any other metric, so the pilot has one place to tune how sensitive drift detection is.

## 13. Constants

All values are initial placeholders, to be tuned on the full log set.

| Constant | Value | Where |
|---|---|---|
| `exceedance_merge_gap_s` | 30 s | engine profile |
| `n_min` for z reference and band comparison | 10 | shared with `baseline_deviation` |
| Drift z | the metric's `outlier_z_threshold` (default 2.0) | `BaselineConfig`, shared |
| z `std` floor | 5% of the limit value, min 0.1 engine units | engine |
| `time_above_pct` drift `std` floor | 1 percentage point (added in Phase 4) | engine |
| `reference_n` | 20 flights | engine |
| `reference_min_n` | 5 flights | engine |
| `frequency_window` | 10 monitored flights | engine |
| `frequency_delta` | 0.30 | engine |
| `quiet_window` | 10 monitored flights | engine |
| `review_interval_h` | 50 h CAUTION, 25 h WARNING | profile default |
| `close_call_margin_s` | 60 s | profile `overboost` |
| WARNING caps (`max_band_abs`, `max_duration_s`) | PLACEHOLDER per limit | profile `filter_policy` |
| `stratify_by` | per §6.5 | profile |

## 14. Acceptance

All tests run in Claude Code against the full log set (100+ logs), plus KACV as the reference case.

1. **Limit IDs:** every limit in all four profiles has a unique `id`; the loader rejects a missing or duplicate ID.
2. **Merge gap and metrics report:** event counts per limit across the log set before and after merging, with the gap distribution, to support the chosen value. For each limit, the §5 metrics by OAT and DA band, to support the `stratify_by` defaults. KACV fuel pressure max drops from 77 events. No merged event spans a gap longer than `exceedance_merge_gap_s`.
3. **Per-limit baselines:** `update_fleet` produces baselines, trends, outliers and (where configured) stratified baselines for every limit's §5 metrics, using the same functions as existing metrics. Excluded flights are absent from their points.
4. **One insight per limit:** without filters, each flight has at most one `limit_exceedances` insight per limit, and its events match `FlightAnalysis.exceedances`. Characterization goldens are updated deliberately, with the diff reviewed.
5. **Topic parity:** across the log set, `oil_temp_peak`, `coolant_temp_peak` and `overboost_time` threshold insights fire exactly when there is an unsuppressed event for the referenced limit. No `"limit": <number>` remains in threshold triggers. A filter on `oil_temp_max` never removes an `oil_temp_peak` `baseline_deviation` insight.
6. **Magnitude filter:** KACV with `fuel_press_max` absolute +2.5 psi: the 50.4 psi event is the only breach; all others are suppressed; one `filtered` insight and one breach insight.
7. **Duration filter and either-filter:** an event within the duration condition but beyond the band is suppressed; an event outside both is a breach.
8. **Guardrails enforced in the engine:** z on a WARNING limit, a band or duration over the cap, a missing note, or a non-filterable limit all produce a diagnostic and leave the limit unfiltered, even if `filters.json` is hand-edited.
9. **Overboost:** band shifts both the effective limit and the close call; duration condition rejected.
10. **Frozen baseline:** the frozen baseline equals `baseline()` over the reference flights' points. Excluding a reference flight and rebuilding baselines removes it from the frozen baseline; if that drops a z reference below `n_min`, the filter becomes invalid with `FILTER_REFERENCE_LOW_N`.
11. **One threshold:** changing a per-limit metric's `outlier_z_threshold` override changes both its chart outliers and the filter's drift decision.
12. **Change monitor on real data:** replay the log set chronologically, create a filter at flight *k*, and check the status sequence against a hand-verified expectation for at least fuel pressure max. Unit tests with synthetic series cover each status transition, the 2-flight persistence, and the stratified comparison (a filter set in cold weather does not report Drifting on a stratified limit when warmer flights sit within their own band's reference).
13. **Preview:** `preview_limit_filter` counts match the insights produced after saving the same filter.
14. **Caching:** changing a filter changes `filters_hash` and the insight cache key, not `analysis_key` or `fleet_key`.
15. **Retroactivity:** after a filter is saved, reopening an older flight shows its exceedances filtered.
16. **Copy:** copying to a workspace with a different engine model is refused; copying to a same-model workspace selects a fresh reference.

## 15. Open questions

| # | Question | Proposed answer |
|---|---|---|
| Q1 | Should `oil_press_min` (>3500 rpm) be non-filterable? It is the most direct sign of lubrication failure. | **Adopted as proposed (Phase 3):** `filterable: false` in all profiles. Reversible in the profile. |
| Q2 | Where do the WARNING caps come from? | Rotax FADEC sensor accuracy and Garmin display resolution, if published; otherwise placeholders that you set from your own data. **Phase 3:** 916iS ships the placeholder caps in §6.3, marked `PLACEHOLDER`; still to be replaced with sourced values. |
| Q3 | One global merge gap, or per limit? | **Resolved (Phase 1).** Global 30 s, with a per-limit override; `rpm_idle_min` uses 0 s (§6.2). |
| Q4 | Overboost and `rpm_takeoff_max` both encode the 5-minute rule with different thresholds. Should they be unified? | Out of scope here; filtered independently for now. |
| Q5 | Should the per-limit metrics get a Trends-view group? They are already baselined, so this is UI only. | Follow-up, once the Notes charts have been used. |
| Q6 | Existing annotations attached to per-event `limit_exceedances` insights will be orphaned by the new insight IDs. Migrate them? | **Resolved (Phase 1).** On re-analysis, each note on an old per-event insight moves to the new per-limit insight for the same flight and limit; several notes on one limit are joined (`workspace.migrate_limit_annotations`). |
| Q7 | Does fuel pressure vary with OAT enough to need stratification? | **Resolved (Phase 2).** Peak excess does, time above doesn't; `fuel_press_max` is OAT-stratified (§6.5). |
| Q8 | ~~Filters compare within the flight's band, but `baseline_deviation` compares against all flights. Align them?~~ | **Resolved (option B).** `baseline_deviation` moves to stratified leave-one-out comparison with an unstratified fallback below `n_min`: Spec 01 v0.13, R8; Spec 03 v0.11 §5.3 for the Trends outlier rings. Implemented as its own change, not part of Spec 09, but Spec 09's frozen-baseline comparison calls the same helper. |

## 16. Implementation plan and status

Built in phases, each shippable on its own.

| Phase | Scope | Status |
|---|---|---|
| 1 | Limit ids (§6.1), merge gap (§6.2), overboost `close_call_margin_s` (§6.4), one insight per limit without filters (§10.1), topic thresholds via `limit_ref` (§10.2), exceedance fields and `FlightAnalysis.limits` (§11.1), log-set report, note migration (Q6) | Done, engine 0.17.0 |
| 2 | Per-limit baseline metrics (§5) and `stratify_by` (§6.5) | Done, engine 0.18.0 |
| 3 | Filters: `filter_policy` (§6.3), magnitude (absolute, percent, z) and duration semantics and validation (§7), frozen baseline and reference selection (§8.1), `filters.json` (§9), filtered and breach insights (§10.1, §10.3), `evaluate_insights(filters=)`, propose/preview/validate operations and server ops (§11), Flight view editor (§12.1), basic Notes list | Done, engine 0.19.0 |
| 4 | Change monitor (§8.2), `evaluate_filter_health`, review and re-baseline, Notes page filter cards with charts, nav badge and Flights banner (§10.4, §12.2–12.3), per-limit z overrides in the rule playground (§12.4) | Done, engine 0.19.0 |
| 5 | Copy filters between workspaces (§9) | Done, engine 0.19.0 |

**Phase 1 notes.** Rules v1.3 drop the numeric `limit` on threshold triggers; a workspace's
older `rules/active.json` is read with `limit_ref` substituted (`workspace.upgrade_limit_refs`),
and the rule playground shows these triggers as "follows OM limit". A `limit_ref` that doesn't
resolve is an error in `validate_rules(rules, limit_ids)` and, at evaluation time, a
`RULES_LIMIT_REF_UNRESOLVED` header warning with the threshold insight left out.

**Phase 3 notes.** Server ops: `list_filters` (each filter with its limit, policy, whether it
currently applies and a band summary), `propose_filter`, `preview_filter`, `save_filter`
(validates first and refuses an invalid filter with `INVALID_FILTER`; a second filter on the
same limit is `ALREADY_EXISTS` — edit the existing one), `delete_filter`. A new filter, and an
edit to its band or duration, takes the `REFERENCE_N` most recent flights with the limit's
channel as its reference; a note-only edit keeps it. `created_engine_hours` is stored for the
review interval (Phase 4). The CLI `report` command reads the workspace's `filters.json`.

**Phase 4 notes.**

- *Drift floor for `time_above_pct`.* §13 gave a std floor only for z-mode peak excess. A limit
  rarely exceeded in its reference has a `time_above_pct` std near zero, so any event would read
  as Drifting; the drift test floors that std at 1 percentage point. Peak excess uses the z-mode
  floor (5% of the limit value), and overboost's block time a floor of 1 s.
- *Effective reference* is computed, not stored: the stored reference flights still included,
  extended forward chronologically until `reference_min_n`. Monitored flights are those after the
  last reference flight in that order.
- *Drifting windows.* The two-flight persistence needs at least 2 monitored flights; the
  frequency test needs a full `frequency_window` (10) of monitored flights, and Quiet a full
  `quiet_window`. The frequency test compares the share of monitored flights with events against
  the share of reference flights with events (for overboost, blocks past the limit).
- *Breached* counts breaches on monitored flights whose start is after `reviewed_engine_hours`
  (all monitored flights if never reviewed). `created_engine_hours` / `reviewed_engine_hours`
  are the workspace's latest engine hours when the filter was saved / reviewed.
- *An invalid filter* is still monitored for drift, review and quiet, but never reported as
  Breached (it hides nothing); its first reason says it is not applied and why.
- *Operations and ops.* `evaluate_filter_health` returns, per filter, the §11.3 fields plus
  `summary`, `reference` (effective ids, collecting) and `series[].monitored`. Server ops
  `filter_health` (with `attention_count`, the Breached + Drifting count behind the Notes badge
  and Flights banner), `review_filter`, `rebaseline_filter`.
- *Acceptance 12* runs as `tests/contract/test_fleet_analysis.py::test_filter_monitor_replay_fuel_pressure`
  on the N117ZS logs: filter at flight 20, +4.0 psi — Stable until 50 h have passed, then
  Review due, Drifting once (10 of 10 monitored flights with events vs 70% of the reference),
  never Breached.

**Phase 5 notes.** Server op `copy_filters(source_workspace_id)` into the active workspace:
refused with `ENGINE_MISMATCH` across engine models (and `BAD_PARAMS` from a workspace into
itself). Each copy keeps the source's magnitude, duration and note, gets a new id, a fresh
`REFERENCE_N` reference from the target's flights and `copied_from: {workspace_id, filter_id}`.
A limit the target already filters is skipped and reported rather than overwritten. A copy that
doesn't validate in the target (e.g. a z filter whose new reference has too few flights with
events) is still copied, reported as not valid, and shows as *not applied* on the Notes page.

**Still open.** Q5 (a Trends-view group for the per-limit metrics) is a follow-up. The private
characterization goldens (§14.4, "updated deliberately") must be regenerated and their diff
reviewed wherever they are kept, since limit insights and exceedances changed shape.

