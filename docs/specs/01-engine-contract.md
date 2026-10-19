# Spec 01 — Engine Contract

**Project:** SlingologyEIS web platform
**Status:** Draft v0.24 — for review (v0.23–0.24: Garmin AXIS log source, §6.5)
**Suggested repo path:** `docs/specs/01-engine-contract.md`
**Baseline reviewed:** repo snapshot at commit `ed0ca33` (2026-07-07); provided project logs
**Follows:** design discussion (Sept 2026). **Precedes:** Spec 02 (Results Bundle & Workspace), Spec 03 (UI Information Architecture), Spec 04 (Pyodide Spike Plan)

**Revision history**

| Version | Change |
|---|---|
| 0.1 | Initial draft. |
| 0.2 | Open questions Q2, Q4, Q5, Q7 resolved and folded in; Q1 provisionally resolved (§2, §8.4, §8.5, §14). New §7.1 CLI front end. Finding 9 rescoped: the phase-detection miss affects at least 8 of 23 real flights, not one. Migration and acceptance criteria updated (§11, §12). New open question Q8. |
| 0.3 | Added `--logs DIR` to the CLI global options (§7.1), independent of `--workspace DIR`. A non-technical, no-repo user (Spec 02 §5.1) must be able to point both flags at plain folders with no git checkout involved; see Spec 02 v0.2 for the workspace-side default resolution this supports. |
| 0.4 | Added `CUSTOM` to `EngineProfile.source_status` (§6.3, §8.1) and diagnostic `ENGINE_CUSTOM_OVERRIDE`, for a host-merged profile built from a shipped profile plus a pilot's `engine_overrides.json` (Spec 02 §6.4). The engine itself is unchanged — it still only ever receives one `EngineProfile`; merging happens host-side. |
| 0.5 | Stage 4 split into 4a (CLI adapter) and 4b (browser worker + local server) (§11). The CLI ships first: it's the cheapest adapter to build, it's a live conformance check on the Stage 3 contract before the harder browser work starts, and its `--json` output becomes the source for regenerating Spec 05's fixtures from real data instead of hand-authored values. No change to D2 (browser-compute remains the primary deployment path) — this only reorders *building* the adapters, not which one users get. |
| 0.6 | §7.1 needs a real follow-up: multi-workspace support (Spec 02 v0.5, Q10, resolved) requires `--workspace` to accept a registered name/id — looked up in the registry — as well as a literal path, plus `workspace list`/`workspace create` subcommands. This is a modification to the CLI already shipped (Stage 4a, v0.11.0), not a paper change to an unbuilt spec. Not designing the exact flag/subcommand shape in this revision — flagged here so it isn't missed, full design deferred to when Spec 02's registry lands in code. |
| 0.7 | The CLI shape from §0.6 is now built: `workspace list [--json]`, `workspace create <name> [--tail-number IDENT] [--engine NAME] [--json]`, nested-subparser style matching `rules check`/`rules try`. One thing decided rather than left as shipped: `workspace create` had been resolving a missing `--engine` through the same fallback chain every other command uses (flag → env var → `config.json` → 916iS default) — reasonable for a one-off `flight`/`report` run, wrong for `workspace create`, where the choice is locked for the workspace's lifetime (Spec 02 §5.6: the only fix for a wrong `engine_model` is abandoning the workspace and making a new one). **`--engine` is now required on `workspace create` specifically, with no default** — every other command's fallback chain is unchanged. A permanent, hard-to-undo choice shouldn't silently inherit a throwaway command's low-stakes default. |
| 0.8 | §8.4: `BaselineConfig` gains `outlier_z_threshold` (global default 2.0) and a per-metric `outlier_z_threshold_overrides` map — one number, driving both `FleetMetric.outliers` and the `baseline_deviation` insight trigger, which were previously implicitly separate. Per-metric override exists because a badly skewed metric (`overboost_total_s`) doesn't mean the same thing under a z-score threshold tuned for a roughly normal one. Follows Spec 03 §3's new persona principle: this lives in the rule playground, never surfaced to the casual-pilot workflow. |
| 0.9 | §8.5: `engine_ecu_inflight` firing condition made explicit — only when the flight has a real `IN_FLIGHT`-classified `EcuRun`, never for ground-context presence alone. A wireframe had this backwards (warning-severity insight built from ground-context data, on a flight with zero real in-flight events); fixture and mockup corrected, this is the spec-level fix so it can't recur. Ground-context ECU presence is Analysis-only on every flight where that's all there is — flagging it per-flight would warn on nearly every flight in the fleet, the opposite of what an insight is for. |
| 0.10 | §8.4: documented, not designed — `by_band`/`band_kind_by_metric` were typed with no real content; checked the actual repo and `baseline_stratified`/`trend_stratified` already exist, are already wired into `update_fleet`, and are backed by real physical reasoning ("the research paper §9") that was never written into this spec. Added the real `DA_BANDS`/`OAT_BANDS` boundaries, the real per-metric assignment (5 metrics → `oat_band`, 2 → `da_band`, the rest `null`), and the confidence-per-band trade-off, all pulled from the shipped code rather than invented. |
| 0.11 | §8.4: `outlier_z_threshold` confirmed wired and unified (one resolver, both consumers) during implementation. One thing clarified rather than fixed: `outliers[]` (all-flights baseline) and the `baseline_deviation` insight (leave-one-out, R2) can legitimately disagree in count per metric — always by the same amount R2's own damping evidence predicts. Only the threshold was ever meant to be shared; the two baseline statistics were always meant to differ. Written down explicitly so it isn't mistaken for unfinished unification later. |
| 0.12 | Spec 08 (cylinder balance) lands: §8.2 EGT registry gains `egt1..4_deviation_f`, `egt_hottest_cyl`, `egt_hottest_margin_f`, `egt_rank_order` (the first list-valued metric — `MetricValue.value` may now be an integer array); `egt4_elevation_f` stays one minor version as a deprecated alias of `egt4_deviation_f`. §8.4 `FleetAnalysis` gains optional `cylinder_balance` and the four `egtN_deviation` fleet metrics (`oat_band`). §8.5 `cylinder_rank` is wired (it was the one unimplemented topic) and `egt_cyl_deviation` is new; `egt4_elevation` ships disabled. `update_fleet` takes an optional engine config for the profile's `expected_hot_cylinder` prior. |
| 0.13 | §8.4: new **R8** — `baseline_deviation` compares a flight against the leave-one-out baseline **of its own weather band** for stratified metrics, falling back to the unstratified leave-one-out baseline when the flight has no band or its band has fewer than `n_min` other flights. Removes the seasonal false positives the unstratified comparison produced and makes insights agree with the stratified Trends view. `by_band.bands[*]` gains per-band `outliers`; insight `values` record which comparison was used. Acceptance criterion 8 (§12) is superseded: its counts are regenerated on the full log set. Decided in the Spec 09 discussion (Q8); Spec 09's filter monitor uses the same comparison rule. |
| 0.14 | §6.4: documented, not designed — `fuel_press_psi` is the only signal the logs carry for fuel pump activity; the G3X CSV has no pump-selection or pump-running channel (`FPCM FAULT` is a fault flag, not a state indicator — confirmed against the full fleet's column set, which is identical across logs). Noted as a known gap, with a future pump-state inference model (predicting which pump(s) are running from the pressure signature) tracked as BACKLOG A7. Raised investigating the real fuel-pressure exceedances from BACKLOG G1. |
| 0.15 | New **§8.8 Topic help**: a one-paragraph, pilot-facing explanation per topic, kept outside code in one markdown file shipped in the package (`slingology_eis/help/topics.md`), with placeholders for limit values, profile values, rule parameters and baseline config, resolved by the engine and returned as structured values so the UI formats them in the pilot's units. New operation `get_topic_help` (§7), CLI subcommand `explain` (§7.1), §9 topic modules declare their help entry, §12 acceptance 10. Requested in Spec 10 v0.5 (help text is part of admission). Also §8.5: `TopicResult.limit_refs` (each referenced limit resolved to this flight's `limit_exceedances` insight, for the mirrored badge — Spec 09 v0.13 §10.2, Spec 10 §4.1); the `topic_id` comment now defers to Spec 10's register and lists the eight visible topics. Planning numbers (fuel burned, cruise nm/gal, cruise fuel flow) stay in `FlightAnalysis.metrics` and are no longer topics (Spec 10 §4.2). |
| 0.16 | §8.8: `TopicHelp.validated` — whether the topic is validated on the active engine profile (Spec 10 v0.7 §8.1, from `register.json`); `false` drives the "not yet validated on this engine" note (Spec 03 §5.2). |
| 0.17 | Spec 12 lands: §8.4 `BaselineConfig` gains `recent_window_hours`/`recent_window_min_flights`/`recent_window_max_flights`/`om_margin_fraction`/`pinned_references`; `MetricFleet` gains `shift?`; `FleetAnalysis` gains `change_summary`/`shift_history` (full `Shift`/`ShiftEvent` shapes defined in Spec 12 §11.2/§6, not duplicated here). §7 `update_fleet` takes an optional `LimitFilter[]` and computes the change statistic; new operations `set_reference`/`clear_reference`/`delete_shift_event`. §8.1 diagnostic catalog gains `RECENT_WINDOW_CAPPED`/`RECENT_WINDOW_LOW_N`/`REFERENCE_LOW_N`/`SHIFT_COMPARISON_INSUFFICIENT`. |
| 0.18 | Spec 12 Phase 6 lands: §8.4 `MetricFleet` gains `unit?`, `frequency?`, `events?`, `readiness?` — a per-limit metric's unit from the engine profile; event frequency (the primary limit-panel signal) and its per-flight event ticks; the fixed readiness-badge classification (`filtered`/`building`/`no_recent`/`no_events`/`rare`/`insufficient`), computed engine-side so no UI infers one from raw numbers. Full `Frequency`/`Readiness`/`EventTick` shapes defined in Spec 12 §11.7, not duplicated here. `ShiftEvent.kind` gains `"frequency"` (Spec 12 §6/§11.7). |
| 0.19 | §8.6 rewritten. `IN_FLIGHT` was a residual bucket (anything not POWERUP/SHUTDOWN/LANE_CHECK) with no flight test, no startup window and no minimum duration; on review (2026-10-11, the project's `engine_ecu_runs.csv`) all four of its `IN_FLIGHT` runs are on the ground at idle — three are single 1 Hz rows at or just after engine start, one is a 5 s idle CAN dropout (the full log set's fifth, counted in Spec 10 Appendix A, is to be classified the same way). Classification now comes from the phase detector (`GROUND_START` / `LANE_CHECK` / `GROUND` / `IN_FLIGHT` / `GROUND_SHUTDOWN`), with a minimum event duration and merge gap from the engine profile. The corrected fleet finding is **zero in-flight ENGINE ECU events**. §8.5's `engine_ecu_inflight` paragraph, §12 criterion 3, the testing-limitation note and Q6 updated to match. `RECOMMENDED_ACTIONS_ENGINE_ECU_INFLIGHT`, `analyze_inflight_pattern` and ENGINE ECU's `ALWAYS_ABNORMAL` membership leave the engine. |
| 0.20 | §8.6 amended after the v0.19 implementation run (115 logs). Two findings. (1) The `IN_FLIGHT`-wins rule promoted four ordinary shutdowns to `IN_FLIGHT`: the phase detector keeps the first 4–11 rows after engine cut labelled LANDING_ROLL (taxiing at 7–9 kt) or DESCENT (at 0 kt) before switching to SHUTDOWN, and the alert starts as the engine stops. New **engine-state rule**: a run during which RPM falls below the engine-running threshold and stays there to the run's end is `GROUND_SHUTDOWN` whatever the phase labels; and the `IN_FLIGHT`-wins exception now also requires IAS above the taxi ceiling during the overlap. The phase-detector slop itself (DESCENT at 0 kt, LANDING_ROLL during taxi) is a `phases.py` defect, logged to BACKLOG, not fixed here. (2) The 2026-06-04 21:17:17 run is a shutdown (2 rows TAXI at 1,760 rpm, then RPM and oil pressure stop, 3 rows SHUTDOWN, log ends) — `GROUND_SHUTDOWN`, not the ground CAN dropout v0.19 called it. Criterion 3 and Q6 corrected. Corrected fleet result on 115 logs: 0 `IN_FLIGHT`, 2 `GROUND`, 31 sub-threshold blips. |
| 0.21 | **CAS events** (ECU review decisions 1–4, 2026-10-13; Spec 10 D19). Events gain a `source`: `limit` (the existing exceedances) or `cas` (a classified CAS alert occurrence). Every `GROUND` and `IN_FLIGHT` `EcuRun` is emitted as a CAS event (`cas_id: "ENGINE ECU"`) in the same per-flight event list as limit exceedances, with `classification`, `phase`, `phase_uncertain`, duration, context and — when the run is close to the lane-check signature — `not_lane_check_reason`. Evidence gains kind `cas_event`; `ecu_run` evidence is retired. `engine_ecu_inflight` follows Spec 10 §4.1: it references the event, emits no second insight, keeps the class counts and the `lane_check` line. Spec 09 filters attach to a limit or a CAS id (duration condition only for CAS). Spec 12 generates an event-frequency panel per CAS id. `ecu_runs` stays as the classifier's full output. |
| 0.24 | **Second AXIS log reviewed** (2026-10-18, 2 h 14 min flight). §6.5: the AXIS column set is **variable** (102 columns on 10-14, 117 on 10-18 — autopilot/flight-director fields and `terrainAlert`/`trafficAlert` appear only when used); mapping is by column name, unknown columns are tolerated, nothing may depend on column count or position. AXIS CAS wording differs from the G3X for some alerts (`EFIS ON BACKUP`, `NAV ON BACKUP`, `TER N/A`) — a per-source alert alias table. **Q9 resolved:** AXIS uses `ENGINE ECU`; the log shows a two-lane check (4 s at ~4,310 rpm, 4 s at ~3,985 rpm, on ground) and a shutdown run. **Q10 (power-up) resolved:** AXIS starts logging after the engine is already running, so `GROUND_START` never appears on AXIS logs and the ECU classifier must not treat a log that opens mid-run as a mid-log power cycle; the `on_ground` phase-detection question stays open. Criterion 12. |
| 0.23 | **Garmin AXIS log source** (2026-10-17, four decisions). N117ZS moved from a G3X to a Garmin AXIS; the AXIS CSV has a three-row header, camelCase column names, ~0.83 Hz sampling, no `engine_hours`/`system_id` header fields, and two general-purpose analog channels. New §6.5 defines the source formats the engine reads and how each normalises to the one channel registry. Decisions: (1) AXIS logs are **reindexed to a 1-second grid at the loader** with filled rows flagged (the engine's rows-as-seconds assumptions stand; a time-based engine is BACKLOG); (2) `engine_hours` for AXIS is the first-row `e1TachTime` — same meter as the G3X value; (3) general-purpose analog channels are **never mapped by assumption** — they stay raw until the pilot assigns them in Settings (Spec 14 §5.3, Spec 02 §6.6); (4) the flight fingerprint's second element becomes *source identity* (G3X `system_id`, AXIS product name) (§6.1). Acceptance criterion 11; open questions Q9–Q10. |
| 0.22 | Tidy after 430c1a8: `not_lane_check_reason` loses `unpaired` (a lone in-band run is `LANE_CHECK`/`single`, so the case cannot arise); lane-check summary wording is `both lanes ✓` / `one lane only` / `not detected` — the log cannot identify the lane; CAS events carry the lane-check band so rows can print it. The event list is `FlightAnalysis.exceedances[]` with `source`, as implemented. |

---

## 1. Purpose

Define the boundary between the **analysis engine** (Python) and everything that consumes it: the CLI scripts, the browser UI, and a local-server mode. The contract specifies:

- what operations the engine exposes,
- the typed, serializable result objects those operations return,
- how inputs, configuration, quality problems, and provenance are represented,
- how the current code is migrated to meet it.

The UI can only be as good as the structured output behind it. Today the engine's primary output is printed text; this spec makes **structured results primary** and text a rendering of them.

## 2. Decisions this spec builds on

**Agreed in discussion**

| # | Decision |
|---|---|
| D1 | Single repository for engine, contract, and web UI (monorepo). |
| D2 | Two deployment paths, one UI: **(1b)** static hosting with the engine running in the user's browser via Pyodide, so logs never leave the device; **(2)** a local server / Docker option for sophisticated users. |
| D3 | No service-side storage of user data. The project hosts code, never data. |
| D4 | Target users are non-technical: their only step is providing log files. |
| D5 | Community extensibility is a goal (new analyses, rules, engine configs). |

**Proposed here — needs confirmation**

| # | Proposal |
|---|---|
| P1 | The engine is a library first; scripts and UI are peer clients (no UI-only logic). |
| P2 | The engine is **stateless and pure**: persistence belongs to the host (Spec 02). |
| P3 | iPad is a *viewing* target via an exported results bundle; desktop is the working platform. |

**Resolved in v0.2** (recommendations from the open-questions review; revert any you disagree with)

| # | Resolution | Origin |
|---|---|---|
| R1 | Insight severity is defined per trigger in `insight_rules.json`, with defaults by trigger type (§8.5). | Q2 |
| R2 | Baseline comparisons use **leave-one-out** membership, and baseline-deviation triggers require a minimum sample size (§8.4). | Q4 |
| R3 | Pilot annotations are host-supplied input to `evaluate_insights`, keyed by `flight_id` plus insight/event reference, not by source file (§8.5). | Q5 |
| R4 | The contract uses its own semantic version, independent of the toolkit version. | Q7 |
| R5 | `flight_id` stays fingerprint-based; overlap matches surface as `INGEST_DUPLICATE_OF` and the host keeps an alias list. Provisional until checked against the full log set. | Q1 |
| R6 | The CLI is retained as a thin client and becomes a single `slingology-eis` command with subcommands (§7.1). | new |
| R7 | Stage 0 golden outputs are captured as a **known-defect baseline** (finding 9); the detector fix is a separate reviewed change (§11). | new |
| R8 | For stratified metrics, baseline comparisons use the leave-one-out baseline of the flight's own band, with an unstratified fallback below `n_min` (§8.4). | Spec 09 Q8 |

## 3. Findings from the code review that shape the contract

Reviewed against the repo snapshot and the logs in the project space.

1. **Much analysis logic lives in the scripts, not the library.** `slingology_eis/` is ~3,000 lines; `notebooks/` holds ~1,900 more. Script 03 owns baseline/trend/model serialization (`write_baselines`) and fleet insights; script 04 owns per-flight insight evaluation (`_baseline_triggered`, `_trend_triggered`, `_predict_map`) and the entire 14-topic report; script 02 still builds ECU runs (`_build_run`) although classification moved to `cas.py`. A UI cannot reuse logic that only exists as print statements.
2. **The library assumes a filesystem.** `load_log(path)` opens files by path; `load_directory` globs a directory; `limits.py` resolves `engines/` relative to `__file__` and loads a default engine config **at import time** from an environment variable or `config.json`. None of this works cleanly under Pyodide or with files that arrive as bytes.
3. **Output is text-first.** Reports are strings; JSON output goes through a `NaN`→`null` regex patch (`write_baselines`). There is no single serializer.
4. **Missing values are ambiguous.** A `NaN` cruise metric can mean "no cruise phase detected", "sensor missing", or "not enough data". The UI must distinguish these; the "no cruise detected" header warning shows the need, but it is a text special case today.
5. **Identity is coarse.** `flight_fingerprint` = (aircraft ident, system ID, start minute). It is good for duplicate detection (SD-card vs Garmin Pilot exports of one flight differ in bytes) but contains identifying data and is not a storable ID.
6. **Raw column names are inconsistent.** The loaded frame has 129 columns mixing normalized ids (`rpm`, `egt1_f`) with raw Garmin names (`GPS Time of Week (sec)`, `Selected Heading (deg)`).
7. **Scale (measured on the provided log, native CPython, 16,196 rows):** load 0.67 s, phase detection 0.35 s, 129 columns, ≈46.5 MB resident for one 4.5-hour flight. Per-flight cost is small; holding many flights' raw frames at once is the memory risk in a browser.
8. **Test-data reality check.** The project space contains **one raw log** (`log_20260423_200615_KACV.csv`) plus derived files `fleet_metrics.csv` (50 rows, 23 of them real flights) and `engine_ecu_runs.csv` (145 runs). Re-running the current `build_flight_metrics` on the raw log reproduces its `fleet_metrics.csv` row exactly (all 31 columns, zero differences), so the current behavior is a valid characterization baseline. The current code also emits four columns the CSV predates (`takeoff_map_inhg`, `takeoff_pressure_alt_ft`, `takeoff_oat_c`, `inflight_ecu_count`).
9. **A phase-detection miss on the provided log** (reported here because it shapes the quality model in §8; *not* fixed by this spec). This log is a 4.5-hour flight (241 airborne minutes, max 8,062 ft, max IAS 130 kt) but `detect_phases` labels 15,997 of 16,196 seconds as `TAXI`; there is no `TAKEOFF_ROLL`/`CLIMB`/`CRUISE`. `fleet_metrics.csv` consequently shows zero climb and cruise minutes and null cruise efficiency for this flight. Working hypothesis, unverified: the `TAXI → TAKEOFF_ROLL` transition requires smoothed RPM > 4,500 while smoothed IAS < 35 kt, but in this log RPM ramps from ~3,200 to ~5,500 in about six seconds while IAS is already 34–38 kt (a rolling takeoff), so the transition never fires and the state machine stays in `TAXI`. **Scope check (v0.2):** in `fleet_metrics.csv`, 9 of the 23 real flights have zero cruise minutes, and 8 of those also have zero climb and descent minutes, the same signature as the KACV flight. They include the 241-minute and 293-minute cross-country flights. The mechanism was traced only on KACV, so the other eight are unconfirmed, but the signature is consistent. It also explains why cruise efficiency exists for only 12 of 23 flights, so cruise-dependent fleet baselines are currently built on partial data. Proposed as a backlog item, separate from this spec.
10. **Version inconsistency in the snapshot:** `slingology_eis/__init__.py` reports `0.9.0` while CHANGELOG, README, and BACKLOG say `0.10.0`.

## 4. Principles

1. **Structured first.** Every operation returns typed data. Text reports are produced by renderers from that data.
2. **Pure and stateless.** Same inputs → same outputs. No filesystem, environment variables, globals, or clock reads inside the core. Hosts supply bytes, configuration, and prior results.
3. **Explicit configuration.** Engine profile, rules, and parameters are arguments, never import-time state.
4. **Honest about missingness.** Every null carries a reason code.
5. **Provenance on everything.** Each result records the engine version, schema version, configuration hashes, and parameters that produced it.
6. **Incremental by construction.** Results are content-addressed so hosts can recompute only what changed.
7. **One code path.** CLI, browser worker, and local server call identical engine code; only the transport differs.
8. **Bounded memory.** The engine processes one flight's raw frame at a time and discards it; fleet-level steps consume derived results only.
9. **Forward-compatible schema.** Additive changes are minor versions; consumers reject unknown major versions.

## 5. Architecture

```
            ┌──────────────┬───────────────────┬────────────────────┐
  Clients   │  CLI scripts │  Browser UI       │  Local server (UI) │
            │  (renderers) │  (worker RPC)     │  (HTTP JSON)       │
            └──────┬───────┴─────────┬─────────┴──────────┬─────────┘
                   │      Operation envelope (§7)          │
            ┌──────▼───────────────────────────────────────▼─────────┐
  Workflows │ import_logs · update_fleet · evaluate_insights · ...   │
            ├────────────────────────────────────────────────────────┤
  Core      │ ingest → session/flight → phases → topic analyses →    │
            │ fleet aggregation → insight evaluation · ECU analysis  │
            ├────────────────────────────────────────────────────────┤
  Renderers │ text report · JSON serializer · series downsampler     │
            └────────────────────────────────────────────────────────┘
   I/O adapters (outside core): path→bytes · browser File→bytes · HTTP body→bytes
```

The core never touches I/O. Adapters convert whatever the host has (a path, a browser `File`, an HTTP upload) into `LogSource{ name, bytes }`.

## 6. Domain model

### 6.1 Identifiers

| Id | Definition | Purpose |
|---|---|---|
| `source_key` | SHA-256 of the file bytes (hex, first 16 chars shown) | Identifies one exported file. |
| `flight_id` | Opaque hash of the flight fingerprint (aircraft ident, **source identity**, start minute). Source identity is the G3X `system_id` for G3X-direct and Garmin Pilot files and the product name (`AXIS`) for AXIS files, which carry no system id (v0.23, §6.5) | Identifies one physical flight across export paths. An SD-card export and a Garmin Pilot export of the same flight share a `flight_id` but differ in `source_key`. |
| `analysis_key` | Hash of (`flight_id`, engine-profile hash, analysis-parameters hash, engine major.minor) | Cache key for a `FlightAnalysis`. |
| `fleet_key` | Hash of the sorted set of included `analysis_key`s plus baseline configuration | Cache key for a `FleetAnalysis`. |

`flight_id` is an opaque handle, **not** an anonymization mechanism (the underlying values are low-entropy). Identifying fields (`aircraft_ident`, `system_id`, GPS) are carried separately and are removable by the `anonymize` option (§10).

### 6.2 Sessions vs flights

A log file may contain several avionics power cycles (BACKLOG B2), and ground-only sessions are excluded (loader `skip_ground_sessions`). The contract models `LogSource → Session[] → Flight?`: a session may or may not be a flight. v0.1 emits exactly one session per file (current behavior) but the schema allows N, so B2 is not a breaking change later.

### 6.3 Engine profile

`EngineProfile` is the parsed content of `engines/<name>.json` (limits, thresholds, suppression rules) passed explicitly, with `profile_hash` and `source_status` (`VERIFIED` | `PLACEHOLDER` | `CUSTOM`). A placeholder profile yields the diagnostic `ENGINE_PLACEHOLDER_CONFIG` (replacing today's Python `warnings.warn`).

`CUSTOM` (v0.4) marks a profile the host built by merging a shipped profile with a pilot's `engine_overrides.json` (Spec 02 §6.4) — e.g. "my POH says 250°F max oil temp, not the shipped 248°F." The engine has no concept of overrides; it only ever receives one already-merged `EngineProfile` and doesn't know or care that it's not the stock one. `profile_hash` is computed over the merged content, so an overridden flight gets its own `analysis_key` rather than colliding with the stock profile's cache entries. `CUSTOM` yields the diagnostic `ENGINE_CUSTOM_OVERRIDE`, so reports and insights visibly flag that the limits shown aren't the shipped defaults.

### 6.4 Channel registry

The public API exposes **normalized channel ids only** (snake_case, unit-suffixed where the current code does: `rpm`, `oil_temp_f`, `egt1_f`, `egt_spread_f`, `fuel_flow_gph`, `map_inhg`, `ias_kt`, `vs_fpm`, `da_ft`, …). Raw Garmin column names are not part of the contract. The registry declares, per channel: id, unit, description, source (`raw` | `derived`), and whether it is charted by default. `get_series` accepts only registry ids.

**No direct fuel pump state (v0.14).** `fuel_press_psi` is sensitive to which fuel pump(s) are running — a pump dropping out or a second pump cutting in shows up as a step or dip in the pressure trace — but the G3X log has no channel that reports pump selection or pump-running state directly. `FPCM FAULT` is a fault flag (fires on a pump-system fault), not a status indicator; it does not distinguish "pump 1 running," "pump 2 running," or "both." This is a real gap for root-causing fuel-pressure exceedances (BACKLOG G1), not something the current engine can paper over with another channel. A future capability — inferring pump state from the pressure signature (and any other correlated channels) rather than reading it directly — is tracked as BACKLOG A7, deliberately out of scope here: it would be a model (trained or rule-based, in the same vein as the `map_at_takeoff` empirical model already built from fleet data, §8.5) feeding a derived channel or metric, not a new raw channel the log itself provides.

### 6.5 Log sources and formats (v0.23)

The engine reads Garmin EIS logs from three export paths. All three normalise, inside the loader, to the §6.4 channel registry; nothing downstream of `ingest_log` knows which path produced a frame except through `source_format` on the airframe info and the diagnostics listed here. Raw column names of any source are not part of the contract.

| `source_format` | Identification | Header layout | Notes |
|---|---|---|---|
| `g3x_direct` | Row 1 `#airframe_info … product="GDU 4xx"`; row 2 starts `Date (yyyy-mm-dd)` | metadata · column names · optional short-name sub-header · 1 Hz rows | Today's primary source. |
| `garmin_pilot` | As above with row 2 prefixed `#` | same | Same columns; `#` stripped. |
| `axis` | Row 1 `#airframe_info … Product="AXIS"`; row 2 is a `#`-prefixed **units** row; row 3 camelCase column names | metadata · units · column names · ~0.83 Hz rows | New. **Variable column set** (v0.24): the AXIS writes only channels that carried data in the session — 102 columns on one log, 117 on the next (autopilot and flight-director commands, `terrainAlert`, `trafficAlert`). Columns shared between logs keep their relative order, but the loader maps by **name only**, tolerates unknown columns, and never depends on column count or position. |

A file matching none of these is `unknown` and is rejected with the existing diagnostic, naming all three accepted layouts.

**AXIS metadata.** The ident is `tail_number` (G3X: `aircraft_ident`) and maps to `aircraft_ident`. There is no `system_id`, `airframe_hours` or `engine_hours` field. `engine_hours` is taken from the first row's `e1TachTime` channel — on N117ZS this is the same hour meter the G3X wrote into its header (119.6 h on 2026-10-14, continuous with the G3X series), so trends, baselines and the Spec 12 recent window carry straight across the avionics change with no user input. `airframe_hours` is absent (null). Software part numbers and the `mode` field are kept in `raw`.

**AXIS channels.** Every channel the analytics consume has a direct AXIS column: time (`localDate`/`localTime`/`utcOffset`), position, GPS/pressure/baro altitude, IAS/TAS/ground speed/vertical speed, OAT, density altitude, baro setting, wind, attitude and accelerations, RPM, MAP, power %, oil temperature and pressure, coolant temperature, fuel flow and pressure, fuel levels 1/2 (→ L/R), EGT1–4, Volts1/Volts2/Amps2, flap position, elevator trim, CAS alerts, autopilot state, nav source. Code owns the exact mapping table. Three points are functional:

- **CAS alerts.** AXIS joins alert tokens with `/` and no spaces (`ESP OFF/NO AOA CAL`); G3X uses ` / `. The CAS splitter already tolerates both. AXIS names the ECU alert `ENGINE ECU`, as the G3X does (Q9, resolved v0.24 on the 2026-10-18 log). Some other alerts are worded differently — `EFIS ON BACKUP` / `NAV ON BACKUP` (G3X `EFIS ON BKUP` / `NAV ON BKUP`), `TER N/A`, `TER TEST`; `FUEL PRESS`, `OIL PRESS`, `ALT FAIL`, `CO PPM`, `RAGL FAIL`, `TRAFFIC FAIL` match. The loader normalises alert tokens to the G3X wording through a per-source alias table so that CAS events, filters and Journal entries use one name per alert; unknown tokens pass through unchanged.
- **General-purpose analog inputs** (`engine1GeneralPurposeAnalog<n>`) carry whatever the aircraft's EIS configuration wired to them — CO ppm on one aircraft, a backup bus voltage on another. **The loader never maps these by assumption.** They enter the frame under a raw id `gp_analog_<n>` (registry source `raw`, unit unknown, not charted by default), and the host may supply a *channel assignment* — `{ "gp_analog_7": "co_ppm" }` — as part of the ingest/analysis inputs, in which case the loader also exposes the channel under the assigned registry id and unit. Assignments are a per-workspace setting (Spec 02 §6.6, Spec 14 §5.3), not engine configuration, and may only target registry channels the source lacks natively. On N117ZS the pilot will assign analog 7 → `co_ppm` (the `CO PPM` CAS alert rises exactly when that channel exceeds ~10). Unassigned analog channels are still viewable raw (Spec 07's channel picker lists them under their raw ids). The same mechanism is the natural hook for Research-mode channels later (Spec 06).
- **New AXIS-only channels** — `onGroundState` (boolean), `flightTime`, `e1TachTime` — are carried as raw channels (`on_ground`, `flight_time_h`, `tach_time_h`) and are **not** used by phase detection or the admission rules in this revision: phases must behave identically for G3X and AXIS logs of the same aircraft so the reference built from G3X flights remains valid. Using `on_ground` as a phase-detection input is a separate decision (Q10).

Channels the G3X writes and AXIS does not (EFIS/NAV backup volts, the eight discretes, HFOM/VFOM, `co_ppm` as a named column) are simply absent — missingness is already a first-class concept (§8.2).

**Sampling.** The AXIS log is written at roughly 0.83 Hz: `systemTime` shows a repeating pattern of four 1,000 ms steps and one 2,000 ms step, so about one sample in six is missing and the whole-second timestamps carry 1–2 s holes throughout. Several engine paths count rows as seconds (ground-session airborne minutes, phase minutes, overboost total and longest block, ECU run durations, cruise dwell, smoothing windows). **Decision 1:** the loader reindexes AXIS frames onto a 1-second grid from the first to the last timestamp. Numeric channels are linearly interpolated across holes of at most `max_fill_gap_s` (AnalysisParams, default 2 s); text, boolean and CAS channels carry the previous value forward across the same holes; longer holes stay missing (and remain subject to Spec 02 §5.11.2's gap rule). Filled rows are marked in a boolean `_filled` column, the frame carries the filled-row share, and `ingest_log`/`analyze_flight` emit the informational diagnostic `LOG_RESAMPLED_TO_1HZ` with that share (expected ≈ 17 % for AXIS; 0 for G3X, which is never resampled). G3X and AXIS frames are therefore sample-for-sample comparable, and no engine module changes. Making the engine time-based throughout (`elapsed_s` arithmetic instead of row counts) is the honest long-term fix and goes to BACKLOG as hardening, not as part of this change.

**Flight fingerprint** (§6.1): the second element is the source identity — `system_id` for G3X-derived files, the product name for AXIS. The same AXIS file copied into two folders still collapses to one flight; a G3X and an AXIS log cannot share a fingerprint, so the mixed-source case stays visible in `imports[]` (Spec 02 §6.2).

**Anonymisation** (§10) strips `tail_number`-derived `aircraft_ident` exactly as it strips the G3X ident; there is no system id to strip.

**Not changed by this revision:** phase detection, admission rules, limits, topics — each must produce the same classes on an AXIS flight as it would on a G3X flight of the same profile.

**AXIS logs begin with the engine already running (v0.24).** Both AXIS logs open 1–2 minutes after boot: engine at 1,780–2,800 rpm, oil already warm, display still in power-on test, GPS `NoSoln`. The AXIS does not record the engine start, so the `GROUND_START` ECU class never occurs on an AXIS log; `LANE_CHECK` and `GROUND_SHUTDOWN` do (10-18: two 4 s runs at ~4,310 and ~3,985 rpm on the ground, then a 16 s run at 1,850 rpm to end of log). Consequences: (1) the ECU classifier's startup window (§8.6) is anchored to the log start as before — a log that opens mid-run is normal for AXIS and is not a mid-log power cycle (Spec 02 §5.11.2 BACKLOG B2) nor a `corrupt_log`; (2) the lane-check summary line and `engine_ecu_inflight` topic behave as on a G3X log with `GROUND_START` absent — no diagnostic is raised for the missing start; (3) any future per-start metric (warm-up time from engine start) is unavailable on AXIS and must report missingness rather than measure from the first row.

## 7. Operations

All operations use one envelope, regardless of transport.

```jsonc
// request
{ "op": "analyze_flight", "request_id": "r-17", "params": { ... } }
// response
{ "request_id": "r-17", "ok": true,  "result": { ... },
  "diagnostics": [ ... ], "provenance": { ... } }
{ "request_id": "r-17", "ok": false, "error": { "code": "...", "message": "..." } }
// progress (long operations only)
{ "request_id": "r-17", "progress": { "stage": "phases", "done": 3, "total": 23 } }
```

| Operation | Inputs | Output | Notes |
|---|---|---|---|
| `list_engines` | – | `EngineProfileInfo[]` | Ids, status, hash. |
| `get_engine_profile` | `engine` | `EngineProfile` | For UI display of limits. |
| `ingest_log` | `LogSource`, `IngestOptions` | `IngestResult` | Parse, normalize, classify (flight / ground / duplicate). Cheap; no analytics. |
| `analyze_flight` | `LogSource`, `EngineProfile`, `AnalysisParams` | `FlightAnalysis` | Full per-flight pipeline. Raw frame is discarded on return. |
| `get_series` | `LogSource`, `flight_id`, channels, window, resolution | `SeriesData` | Re-parses on demand for full-resolution zoom (avoids holding frames). |
| `update_fleet` | `FlightAnalysis[]`, `FleetSelection`, `BaselineConfig`, `LimitFilter[]` | `FleetAnalysis` | Metrics table, baselines, trends, outliers, models, and (Spec 12 §5/§7) `shift` per metric, `change_summary`, append/close of `shift_history`. No raw data. |
| `set_reference` / `clear_reference` | `metric_id`, `flight_ids?`, `label?` | `BaselineConfig` | Spec 12 §5.7/§11.3 — pin/unpin a metric's shift reference. |
| `delete_shift_event` | `event_id` | `{ shift_history: ShiftEvent[] }` | Spec 12 §6/§11.3 — the one exception to the history's append-only rule. |
| `evaluate_insights` | `FlightAnalysis`, `FleetAnalysis`, `RuleSet` | `InsightSet` | Pure and fast; the **rule playground** re-runs only this. |
| `analyze_ecu` | `FlightAnalysis[]` | `EcuAnalysis` | Runs, classification, lane-check pairing, co-active alerts. |
| `render_report` | `InsightSet`, `FlightAnalysis`, format | text/markdown | Text report from structured data. |
| `validate_rules` | `RuleSet` | diagnostics | Schema and semantic checks. |
| `get_topic_help` | `topic_id[]` (optional — all if omitted), `EngineProfile`, `RuleSet`, `BaselineConfig` | `TopicHelp[]` | §8.8. Static per profile + rules + config, not per flight; the UI caches it. |

**Workflows** compose operations and declare inputs/outputs so the UI can show what is stale:

| Workflow | Steps |
|---|---|
| `import_and_update` | `ingest_log`×N → (`analyze_flight` for new/changed) → `update_fleet` → `evaluate_insights` |
| `rebuild_baselines` | `update_fleet` with a new `FleetSelection`/`BaselineConfig` → `evaluate_insights` |
| `what_if_rules` | `validate_rules` → `evaluate_insights` only |
| `ecu_check` | `analyze_ecu` |

**Staleness rules** (drives incremental recompute): a `FlightAnalysis` is stale if its log, profile, params, or engine major.minor changed; a `FleetAnalysis` if its set of flight analyses, selection, or baseline config changed; an `InsightSet` if its flight, fleet, or rules changed.

### 7.1 CLI front end

The CLI is **retained** as a thin client of the engine. It is not the interface for non-technical users; it serves contributors, headless batch runs, CI and golden-output tests, reproducing the numbers in the research paper, and local hosting (path 2).

**Rules**

- No analysis logic in the CLI. It converts paths to `LogSource`, calls the §7 operations in-process, and prints a renderer's output.
- **Parity:** every §7 workflow is reachable from the CLI, and `--json` prints the operation's result (validated against the schemas). UI-only interactions (chart zoom, rule playground editing) are excluded.
- One installable command, `slingology-eis`, with subcommands. Diagnostics go to stderr, results to stdout.

| Subcommand | Maps to | Replaces |
|---|---|---|
| `flight <log>` | `analyze_flight` (text summary) | script 01 |
| `ecu [paths]` | `analyze_ecu` | script 02 |
| `fleet` | `update_fleet` + fleet insights | script 03 |
| `report <log \| flight_id>` | `analyze_flight` + `evaluate_insights` + `render_report` | script 04 |
| `import <paths>` | `import_and_update` (files or folders) | – |
| `rules check <file>` / `rules try <file>` | `validate_rules` / `what_if_rules` (prints which insights change) | – |
| `engines` | `list_engines` | – |
| `explain [topic_id]` | `get_topic_help` (all topics if omitted) | – |
| `export-bundle` | results bundle (Spec 02) | – |
| `serve` | starts the local server and UI (path 2) | – |
| `workspace list [--json]` | reads the registry (Spec 02 §5.2/§6.7) | – |
| `workspace create <name> [--tail-number IDENT] [--engine NAME] [--json]` | creates a registry entry + workspace (Spec 02 §5.1) | – |

**Global options:** `--logs DIR`, `--workspace NAME-OR-DIR`, `--engine NAME`, `--json`, `--anonymize`, `--quiet`. **Exit codes:** `0` success, `1` operation failed, `2` usage error.

`--workspace` now resolves against the registry first (a matching name or id) before falling back to treating the value as a literal path — a developer-checkout invocation that predates the registry is unaffected. `--logs` and `--workspace` are independent — neither implies the other, and neither implies a git checkout.

**`--engine` is required on `workspace create`, with no default** — the one deliberate exception to every other command's fallback chain (below). `engine_model` is locked for the workspace's lifetime (Spec 02 §5.6); the only fix for a wrong choice is abandoning the workspace and creating a new one, so it shouldn't silently inherit a throwaway command's low-stakes default. Every other command's defaults, in order of precedence, are resolved by the host (not the engine) as: (1) the flag, if given; (2) a packaged install's own default folder (a named folder under the user's home directory — see Spec 02 §5.1 for the exact path); (3) `<repo-root>/data/logs` and `<repo-root>/data/` respectively, **only** when the CLI is run from inside a git checkout and neither flag nor (2) applies. Case (3) exists for contributors and CI reproducing the current scripts' behavior; it is not the default for anyone who installed the tool rather than cloned it.

**Compatibility**

- Scripts 01–04 keep their current behavior through Stage 3. From Stage 4 they remain as thin aliases that print a deprecation notice for at least one minor release.
- The legacy layout (`data/logs/`, `data/reports/`) stays readable. `reports/baselines.json` and `reports/models.json` are written as today through Stage 3, and afterwards only with `--legacy-outputs`.
- The CLI, the local server, and the UI share one workspace layout, defined in Spec 02, so a report produced on the command line appears in the UI unchanged.
- Whether `serve` can ship inside a `pip` install depends on how the built UI assets are packaged (Q8).

## 8. Result model

Type sketches are illustrative; normative JSON Schemas will be generated into `contract/schema/` and used by both Python and TypeScript tests. `T | null` always pairs with a reason (§8.2).

### 8.1 Envelope objects

```ts
interface Provenance {
  engine_version: string;        // e.g. "0.11.0"
  schema_version: string;        // contract version, semver
  engine_profile: { id: string; hash: string; source_status: "VERIFIED"|"PLACEHOLDER"|"CUSTOM" };
  params_hash: string;
  rules_hash?: string;
  source_keys: string[];
}
interface Diagnostic {
  code: string;                  // catalog below
  severity: "info" | "warn" | "error";
  scope: "file" | "flight" | "fleet" | "topic";
  message: string;
  refs?: Record<string, string | number>;
}
```

Diagnostic catalog (v0.1): `INGEST_UNKNOWN_FORMAT`, `INGEST_GROUND_SESSION`, `INGEST_DUPLICATE_OF`, `INGEST_MULTI_POWER_CYCLE`, `INGEST_MISSING_CHANNEL`, `INGEST_SIGNAL_GAP`, `PHASE_TAKEOFF_NOT_DETECTED`, `PHASE_NO_CLIMB`, `PHASE_NO_CRUISE`, `BASELINE_LOW_N`, `MODEL_INSUFFICIENT_DATA`, `ENGINE_PLACEHOLDER_CONFIG`. Added in v0.4: `ENGINE_CUSTOM_OVERRIDE`. Added by Spec 12 §11.4 (full catalog, including Spec 09/Spec 10's own additions, is `contract.py`'s `DIAGNOSTIC_CATALOG` — this list is illustrative, not re-synced release to release): `RECENT_WINDOW_CAPPED`, `RECENT_WINDOW_LOW_N`, `REFERENCE_LOW_N`, `SHIFT_COMPARISON_INSUFFICIENT`.

**Phase cross-check (new, informational).** `PHASE_TAKEOFF_NOT_DETECTED` is raised when airborne time (from altitude/speed) exceeds a small threshold but no `TAKEOFF_ROLL`/`CLIMB` phase was labelled. It does not change the detector; it makes finding 9 visible in the UI and in fleet quality summaries. The provided KACV log is the acceptance case (§12).

### 8.2 Metrics and missingness

```ts
type MissingReason = "NO_PHASE" | "CHANNEL_MISSING" | "INSUFFICIENT_DATA"
                   | "NOT_APPLICABLE" | "EXCLUDED";
interface MetricValue {
  id: string;                    // metric registry id
  value: number | boolean | string | null;
  unit?: string;
  missing?: MissingReason;       // present iff value is null
  window?: { phase?: string; start_s: number; end_s: number };  // what it was computed over
}
```

The **metric registry** replaces the implicit `FlightMetrics` dataclass. Ids are the current field names, so existing baselines and CSVs remain comparable.

| Group | Metric ids |
|---|---|
| Header | `date`, `engine_hours`, `duration_min`, `airborne_min`, `max_altitude_ft`, `max_ias_kt`, `fadec_gallons` |
| Phases | `phase_climb_min`, `phase_cruise_min`, `phase_descent_min` |
| EGT | `egt_spread_mean_f`, `egt_spread_max_f`, `egt1_deviation_f`…`egt4_deviation_f`, `egt_hottest_cyl`, `egt_hottest_margin_f`, `egt_rank_order`, `egt_rank_stable`, `egt4_elevation_f` (deprecated alias of `egt4_deviation_f`; Spec 08) |
| Fuel | `cruise_nmpg`, `cruise_fuel_flow_gph` |
| Thermal | `oil_temp_max_f`, `oil_temp_below_optimal_pct`, `coolant_temp_max_f`, `oil_coolant_ratio`, `climb_oil_rise_f_per_min`, `climb_coolant_rise_f_per_min`, `climb_vs_bucket_dominant` |
| Boost | `overboost_total_s`, `overboost_max_block_s` |
| Conditions | `cruise_da_ft`, `cruise_oat_c`, `da_band`, `oat_band` |
| Takeoff MAP | `takeoff_map_inhg`, `takeoff_pressure_alt_ft`, `takeoff_oat_c` |
| Events | `cas_inflight_anomaly_count`, `inflight_ecu_count` |

### 8.3 Flight analysis

```ts
interface FlightAnalysis {
  flight_id: string; analysis_key: string; source_keys: string[];
  header: { date: string; start_utc: string; engine_hours_start?: number; engine_hours_end?: number;
            airport_hint?: string; aircraft?: { ident?: string; system_id?: string } };  // aircraft removable
  phases: { phase: string; start_s: number; end_s: number }[];    // [start,end) on elapsed_s
  metrics: Record<string, MetricValue>;
  exceedances: Exceedance[];      // from limits.check_exceedances
  cas_events: AlertEvent[];
  ecu_runs: EcuRun[];
  quality: Diagnostic[];
  provenance: Provenance;
}
```

`Exceedance` and `AlertEvent` mirror the existing `ExceedanceEvent` / `AlertEvent` dataclasses with timestamps expressed as `elapsed_s` plus `start_utc`.

### 8.4 Fleet analysis

```ts
interface Baseline { n: number; mean: number|null; std: number|null; min: number|null; max: number|null;
                     confidence: { level: "VERY_LOW"|"LOW"|"MODERATE"|"GOOD"; n: number } }
interface Trend    { n: number; slope: number|null; r_squared: number|null;
                     direction: "increasing"|"decreasing"|"flat"|"insufficient_data";
                     x: "engine_hours"; confidence: Baseline["confidence"] }
interface MetricFleet { metric_id: string; baseline: Baseline; trend: Trend;
                        by_band?: { band_kind: "oat_band"|"da_band";
                                    bands: Record<string, Baseline & { trend?: Trend;
                                                                       outliers: { flight_id: string; z_score: number }[] }> };  // per-band outliers: R8
                        points: { flight_id: string; date: string; x: number|null; value: number; band?: string }[];
                        outliers: { flight_id: string; z_score: number }[];   // computed against the ALL-FLIGHTS baseline (`baseline` above), not leave-one-out — see note below
                        shift?: Shift;   // Spec 12 §5/§11.2 — absent below n_min or with no recent window; full shape in Spec 12, not repeated here
                        unit?: string;        // Spec 12 §11.7 — per-limit metrics (and overboost_time) only
                        frequency?: Frequency; // Spec 12 §5.8/§11.7 — per-limit metrics (and overboost_time) only
                        events?: EventTick[];  // Spec 12 §8.4/§11.7 — one tick per eligible flight, same metrics as frequency
                        readiness?: Readiness }  // Spec 12 §9.3/§11.7 — present instead of a normal shift/trend read wherever one of the fixed badges applies
interface Model    { id: "takeoff_map"; kind: "linear_regression"; features: string[];
                     coefficients: Record<string, number>; n: number; r_squared: number|null;
                     confidence: Baseline["confidence"]; capture: string }  // capture: e.g. "RPM>=5500 during TAKEOFF_ROLL"
interface FleetAnalysis { fleet_key: string; flight_ids: string[]; excluded: {flight_id:string; reason:string}[];
                          metrics: Record<string, MetricFleet>; models: Model[];
                          quality: Diagnostic[]; provenance: Provenance;
                          cylinder_balance?: CylinderBalance;  // Spec 08 §5; absent in pre-Spec-08 results
                          change_summary: { metric_id: string; rank: number; panel?: string; members?: string[] }[];  // Spec 12 §7/§7.1/§11.2
                          shift_history: ShiftEvent[] }        // Spec 12 §6/§11.2, loaded from fleet/shift_history.json (Spec 02 §6.3)
```

`Shift`, `ShiftEvent`, `Frequency`, `Readiness` and `EventTick` are defined in full in Spec 12 §11.2/§6/§11.7 — not retyped here to avoid two sources of truth; this contract only records that `MetricFleet`/`FleetAnalysis` carry them and where to look. `takeoff_map_residual_inhg` (Spec 12 §11.6) is an ordinary fleet metric like any other — no new `MetricFleet` shape for it.

`confidence.level` is a **structured enum**; the human sentence ("MODERATE (n=15 …)") is a renderer concern. The `points` array replaces the `raw` blocks in `baselines.json` and is what the trend charts draw.

**Stratification (`by_band`) — documenting real, already-implemented behavior.** This was typed but never written up; `baseline_stratified`/`trend_stratified` already exist in `fleet.py`, already wired into `update_fleet`, with real reasoning behind the design (the code cites "the research paper §9" directly):

- **Density altitude (`da_band`) is the correct normalizer for performance metrics** (cruise efficiency, fuel flow) — two flights at the same DA present the engine with the same oxygen for combustion regardless of how that DA was reached, so DA alone is the right single variable.
- **Outside air temperature (`oat_band`) is separately needed for thermal metrics** (EGT spread, oil/coolant temps) — DA alone isn't sufficient there, because ambient air is simultaneously the *cooling* medium: a hot-and-high flight and a cold-and-low flight can share the same DA and still have very different cooling margins.

Real band boundaries, exactly as implemented:

```ts
const DA_BANDS  = [[-2000, 2000, "low"], [2000, 5000, "moderate"], [5000, 9000, "high"], [9000, 20000, "very_high"]];  // ft
const OAT_BANDS = [[-40, 5, "cold"], [5, 20, "mild"], [20, 30, "warm"], [30, 55, "hot"]];  // °C
```

Real per-metric assignment (this is `band_kind_by_metric`'s actual populated content, not a placeholder):

| Metric | `band_kind` | Metric | `band_kind` |
|---|---|---|---|
| `egt_spread_mean_f` | `oat_band` | `cruise_nmpg` (cruise efficiency) | `da_band` |
| `egt1..4_deviation_f` (and deprecated `egt4_elevation_f`) | `oat_band` | `cruise_fuel_flow_gph` | `da_band` |
| `oil_temp_max_f` | `oat_band` | `overboost_total_s` | `null` — no physical reason to stratify a boost event by weather |
| `coolant_temp_max_f` | `oat_band` | `climb_oil_rise_f_per_min` | `null` |
| `oil_coolant_ratio` | `oat_band` | `cruise_da_ft`, `takeoff_map_inhg` | `null` — these describe the condition itself |

Every metric not listed defaults to `null` (no stratification) unless a future topic explicitly assigns one.

**Confidence is honestly lower per band, by design, not a bug to fix.** `confidence_label(n)`: `n<3` → `VERY_LOW` ("essentially anecdotal"), `n<10` → `LOW`, `n<30` → `MODERATE`, else `GOOD` (`MIN_FLIGHTS_FOR_CONFIDENCE = 10`, same threshold used fleet-wide). Splitting 23 flights into 4 DA bands means each band typically lands in `LOW` or `MODERATE` even when the unstratified fleet baseline is `GOOD` — this is the correct, stated trade-off for a cleaner comparison, not something a UI should try to hide or upgrade.

**`outliers[]` and the `baseline_deviation` insight can legitimately disagree in count per metric — confirmed during implementation, not a bug to chase.** They share one threshold (`outlier_z_threshold`, above) but compare against two different statistics by design: `outliers[]` is computed against the **all-flights** baseline (the same `baseline` field used for the Trends display band), while the insight trigger uses the **leave-one-out** baseline (R2, below). Leave-one-out will always find equal-or-more flights crossing the threshold than all-flights does, for the reason R2's own evidence already documents — self-inclusion damps a flight's own z-score. So a point can be ringed as an outlier on Trends without a matching insight having fired, and that's the all-flights/leave-one-out difference showing through correctly, not the threshold-unification work leaving something half-fixed. Only the threshold was ever meant to be one number; the two baseline statistics were always meant to differ.

**Baseline membership (resolved, R2).** The current code builds one baseline over all flights (script 03) and script 04 compares each flight against it, so a flight is compared against a baseline that includes itself. The contract instead specifies:

- `FleetAnalysis` keeps the all-flights baseline for display (trend charts, baseline bands) and the per-flight `points` array.
- `evaluate_insights` compares each flight against a **leave-one-out** baseline derived from `points` (mean and standard deviation excluding that flight).
- `baseline_deviation` triggers require a minimum sample size, `n_min` (proposed default 10, matching the existing trend triggers; tunable per rule through the rule playground). Below it, the analysis line is shown with a `BASELINE_LOW_N` note and no insight fires.
- For stratified metrics, the leave-one-out baseline is taken **within the flight's own band** (R8, below).

**Stratified comparison (R8).** Until v0.13, stratification was display-only: the Trends view could split a metric by band, but `baseline_deviation` always compared a flight against every other flight regardless of weather. For thermal metrics that produced seasonal noise. A hot-day oil temperature peak stood out against a fleet that included winter flights and fired a "watch" insight every summer, while a winter flight running warm for winter could hide inside the all-season spread. It also made the chart and the insights disagree: a point sitting well inside its own band on the stratified Trends view could still carry a "higher than usual" insight.

The rule, applied per metric by `evaluate_insights`:

1. If `band_kind_by_metric[metric]` is `null`, compare against the unstratified leave-one-out baseline (unchanged behaviour).
2. Otherwise, if the flight has a band (`points[].band` present) and at least `n_min` **other** flights share that band, compare against the leave-one-out baseline of that band.
3. Otherwise, fall back to the unstratified leave-one-out baseline.
4. If that is also below `n_min`, no insight fires and the analysis line carries `BASELINE_LOW_N`, as before.

The same `outlier_z_threshold` applies whichever baseline is used; only the comparison set changes. Trend triggers are unaffected: a trend is always over engine hours across all flights.

The insight's `message.values` gain `comparison: { scope: "band" | "all"; band?: string; n: number }`, and the text names it ("higher than your other warm-day flights, n=14" or "higher than all your flights, n=23"), so a pilot can always see what the flight was compared with. A fallback is not a diagnostic; it is just visible in `comparison`.

For the display side to agree, `update_fleet` computes `outliers` per band as well (`by_band.bands[b].outliers`, against that band's all-flights baseline, same threshold). The Trends view rings per-band outliers when stratification is on and the fleet-wide `outliers` when it is off (Spec 03 §5.3). The existing all-flights versus leave-one-out difference (above) carries over unchanged within each band.

Consequences, accepted deliberately: per-band samples are smaller, so a new aircraft spends longer in fallback before band comparisons start (the `confidence` trade-off already described for stratified baselines), and existing insights change for stratified metrics, including Spec 08's `egt1..4_deviation`, which are `oat_band`. Spec 09's filter monitor uses this same rule for its frozen baselines, so filters and baseline insights share one definition of "comparable flights".

```ts
interface BaselineConfig {
  membership: "leave_one_out" | "all";   // default "leave_one_out"
  band_kind_by_metric: Record<string, "oat_band" | "da_band" | null>;   // real values above, not empty
  outlier_z_threshold: number;                              // global default: 2.0
  outlier_z_threshold_overrides?: Record<string, number>;    // metric_id -> override, sparse
  // Spec 12 §11.1 — the change statistic's window/margin, edited in Baselines & Models (§8.3/Spec 03 §5.5).
  recent_window_hours: number;            // default 10
  recent_window_min_flights: number;      // default 5
  recent_window_max_flights: number;      // default 15
  om_margin_fraction: number;             // default 0.25
  pinned_references?: Record<string, { flight_ids: string[]; set_at: string; label?: string }>;  // Spec 12 §5.7, sparse
}
```


**One threshold, two consumers — not two independently configurable numbers.** `outlier_z_threshold` (resolved per metric as `overrides[metric_id] ?? outlier_z_threshold`) is the single value that decides both (a) which points `update_fleet` marks in `FleetMetric.outliers` (below) and (b) whether `evaluate_insights`'s `baseline_deviation` trigger fires for that metric. Earlier drafts of this spec left the two implicitly separate — a real gap, since a pilot seeing a point ringed as an outlier on a trend chart with no corresponding insight (or the reverse) would have no idea why they disagreed, when the honest answer should be "they can't disagree, they're the same number." Default 2.0 (roughly the two-tailed 95% mark) covers any metric with no override. Per-metric overrides exist because some metrics are badly skewed — `overboost_total_s` is mostly near-zero with occasional spikes, and a z-score threshold tuned for a roughly normal metric like EGT spread doesn't mean the same thing statistically there. (A skewed metric like that may eventually want a percentile-based threshold instead of a z-score at all — not solved here, just noted as a real limit of this mechanism, not something per-metric tuning alone fixes.)

Both `outlier_z_threshold` and `n_min` are edited in the same place: the rule playground (Spec 03 §5.5), alongside the threshold/condition edits it already makes to `insight_rules.json`. One UI surface over two underlying documents (`fleet/selection.json`'s `BaselineConfig` and `rules/active.json`) — not a new settings screen. This is also where Spec 03's persona principle (§3) applies concretely: a casual pilot never opens Baselines & Models and never sees this number; a value that lives here is, by construction, something only a pilot who went looking for it can touch.

Evidence from the review (23 real flights in `fleet_metrics.csv`, |z| ≥ 2.0): self-inclusion changed four borderline results (z between 1.8 and 2.1, always damped); a "prior flights only" baseline was unstable and order-dependent. At n = 23, about one chance trigger per metric is expected at this threshold, which is why the sample-size gate matters more for new users with few flights.

### 8.5 Topics, analysis lines, insights (the two-layer format as data)

```ts
interface TopicResult {
  topic_id: string;               // rule id; the set is governed by Spec 10's register. Visible topics (v0.15):
                                  // egt_spread, egt_cyl_deviation, oil_temp_peak, coolant_temp_peak,
                                  // overboost_time, map_at_takeoff, engine_ecu_inflight, limit_exceedances
  analysis: { template: string; values: Record<string, number|string|null>; text: string };  // always present
  insight: Insight | null;                                                                    // conditional
  metric_ids: string[];
  limit_refs?: { limit_id: string; insight_id: string | null }[];  // v0.15: the rule's limit_refs (Spec 09 §10.2), each
                                  // resolved to this flight's limit_exceedances insight for that limit, or null if none
                                  // fired. Drives the mirrored badge (Spec 03 §5.2); never an insight of its own.
}
```

**`engine_ecu_inflight` is a referencing topic (v0.21, Spec 10 §4.1 / D19).** The event itself — any `GROUND` or `IN_FLIGHT` ENGINE ECU run — is a CAS event owned by the events owner (`limit_exceedances`, §8.6), reported once, filterable (Spec 09) and acknowledgeable (Spec 14). `engine_ecu_inflight` emits **no insight of its own**: its analysis line gives the class counts for the flight (`GROUND_START` n, `LANE_CHECK` n, `GROUND` n, `IN_FLIGHT` n, blips n), the `lane_check` summary, and — when the flight has a `GROUND` or `IN_FLIGHT` event — a link to that event with its severity badge mirrored, exactly as `overboost_time` references its limit event. Ground-context classes (`GROUND_START`, `LANE_CHECK`, `GROUND_SHUTDOWN`) never produce an event or an insight; they are the routine case on nearly every flight. The topic's Spec 10 status (Admitted, provisional — D18) is unchanged: its condition closes on the first `IN_FLIGHT` event, which will surface as a CAS event.

```ts
interface Insight {
  id: string; topic_id: string; rule_id: string;
  trigger: "threshold" | "baseline_deviation" | "trend";
  severity: "info" | "watch" | "warning" | "limit";
  message: { template: string; values: Record<string, unknown>; text: string };
  evidence: (
    | { kind: "metric"; metric_id: string }
    | { kind: "baseline_point"; metric_id: string; flight_id: string }
    | { kind: "series_window"; channels: string[]; start_s: number; end_s: number }
    | { kind: "exceedance" | "cas_event"; ref: string })[];   // ecu_run retired v0.21
  confidence: Baseline["confidence"];
  note?: string;                  // pilot annotation (BACKLOG B4) attached by the host
}
interface InsightSet { flight_id: string; analysis_key: string; fleet_key: string; rules_hash: string;
                       topics: TopicResult[]; header_warnings: Diagnostic[]; provenance: Provenance }
```

`text` fields are included for convenience, generated from `template` + `values`. The UI renders from structured fields; templates make later localization and rule-playground diffs ("which insight text changed?") possible. **Evidence** is what lets the UI link every insight card to the chart or table row that supports it, which is the core UX requirement.

Severity is defined in the rule set (R1): `insight_rules.json` gains an optional `severity` per trigger, defaulting to `limit` for OM threshold triggers and `watch` for statistical triggers; `warning` and `info` are set explicitly. `baseline_deviation` triggers also gain `n_min` (§8.4). Both are rules-schema changes, listed under §11 migration.

**Annotations (R3).** The host passes annotations to `evaluate_insights` as `{ flight_id, insight_id | ref, note }[]`. The engine attaches them to the matching insight (`Insight.note`) without suppressing it, and stores nothing. Keying by `flight_id` rather than source file (as BACKLOG B4 first proposed) keeps a note attached when the same flight arrives through two export paths.

### 8.6 ECU analysis

**Run extraction.** Contiguous rows with `ENGINE ECU` in the CAS string form a run. Runs separated by less than `cas.merge_gap_s` (engine profile; default 5 s) are merged. Runs shorter than `cas.min_event_duration_s` (default 3 s) after merging are **not** `EcuRun`s; they are counted in `EcuAnalysis.sub_threshold_blips` per flight, for data quality only. At 1 Hz a single-row CAS token is indistinguishable from a sampling artefact. (These are distinct from the exceedance checker's `exceedance_merge_gap_s`, which is per limit.)

**Classification** is by the flight phase (§8.3 / `phases.py`) the run overlaps — no private RPM, IAS or voltage heuristics:

| `classification` | Phases | Meaning |
|---|---|---|
| `GROUND_START` | PRE_START, ENGINE_START, WARMUP | Avionics boot, RS-232 fallback, engine catching. Expected. |
| `LANE_CHECK` | WARMUP or TAXI **and** the lane-check signature (run-up RPM band, stationary, ≤ `lane_check_max_duration_s`, paired within `lane_check_pair_window_s`) | Deliberate single-lane run-up. Expected. |
| `GROUND` | TAXI (not a lane check), or LANDING_ROLL after ground speed < 5 kt | Engine running on the ground, not starting, not a lane check. |
| `IN_FLIGHT` | TAKEOFF_ROLL, CLIMB, CRUISE, DESCENT, APPROACH, LANDING_ROLL | The only flight event. |
| `GROUND_SHUTDOWN` | SHUTDOWN | Expected. |

Rules, in order:

1. **Engine-state rule (v0.20).** If RPM falls below the engine-running threshold during the run and stays there to the run's end, the run is `GROUND_SHUTDOWN`, whatever phases its rows carry. The ENGINE ECU alert routinely starts as the engine is cut, and the phase detector can lag the cut by several rows (LANDING_ROLL while taxiing in, DESCENT at 0 kt). Symmetrically, a run whose rows all precede the first RPM above the running threshold is `GROUND_START`.
2. **`IN_FLIGHT`-wins.** A run overlapping an in-flight phase for ≥ `min_event_duration_s` **with IAS above the taxi ceiling during that overlap** is `IN_FLIGHT`. Phase label alone is not enough (v0.20).
3. **Majority.** Otherwise the run takes the phase holding the majority of its rows.

A run in UNKNOWN phase is classified by the nearest preceding known phase and flagged `phase_uncertain: true`. The former `POWERUP`/`SHUTDOWN` voltage-decline test is retired; the phase detector separates PRE_START from SHUTDOWN, and rule 1 covers the boundary rows it gets late.

**`EcuRun`** keeps the existing columns (`start`/`end` (UTC + `elapsed_s`), `duration_s`, `lane_check_pair`, `lane_check_note`, `co_alerts`, the per-run context means — RPM, power %, oil pressure/temp, coolant temp, main volts, battery amps, fuel pressure, IAS, baro altitude — `volts_delta`, `rpm_accel_pre`, `oil_nan_frac`) and adds `phase` (the deciding phase) and `phase_uncertain`.

**`EcuAnalysis`** carries per-classification counts, `sub_threshold_blips`, per-event co-active alerts for every `GROUND` and `IN_FLIGHT` run (BACKLOG B3 — per event, never a pooled table), and `lane_check: "both" | "single" | "none"` per flight, displayed as *both lanes ✓* / *one lane only* / *not detected*. It no longer carries a recommended-actions list or a pooled in-flight pattern analysis: `analyze_inflight_pattern` and `RECOMMENDED_ACTIONS_ENGINE_ECU_INFLIGHT` leave the engine (the correlation study was a one-time research question, answered; it survives as a notebook at most). `ENGINE ECU` leaves `ALWAYS_ABNORMAL` — its abnormality is decided by classification, not a static list. The topic's help entry (§8.8) describes the classes in plain language and may name the OM/Rotax-generic follow-up (fault-log read); it carries no aircraft-specific wiring guidance (Spec 10 §9 item 11).

**CAS events (v0.21).** Every `GROUND` and `IN_FLIGHT` run is also emitted as an **event** in the flight's event list, alongside limit exceedances. Events share one shape with a `source` discriminator:

```ts
type Event = Exceedance & { source: "limit" }            // existing, unchanged otherwise
           | { source: "cas"; cas_id: "ENGINE ECU";      // the only classified CAS alert today; others join via Spec 10 §8
               event_id: string;                         // cas_id + start UTC, stable for annotations/filters
               classification: "GROUND" | "IN_FLIGHT"; phase: string; phase_uncertain: boolean;
               start_utc: string; elapsed_s: number; duration_s: number;
               context: { rpm: number; ias_kt: number; oil_nan_frac: number; co_alerts: string[] };
               not_lane_check_reason?: "rpm_below_band" | "rpm_above_band" | "too_long" | "moving";
               lane_check_band?: { rpm: number; tolerance: number } };
```

Whether the list is the existing `exceedances` array with `source` added or a sibling array is an implementation choice; consumers must see one list. `not_lane_check_reason` is set when the run matches every part of the lane-check signature but one — it is what lets the Flight view say "7 s during TAXI, 2,550 rpm — below the lane-check band" and makes the obvious filter obvious (Spec 03 §5.2). CAS events have no `excess` and no OM value; magnitude filters do not apply to them (Spec 09 §7). `Insight.evidence` gains `{ kind: "cas_event"; ref: event_id }`; the `ecu_run` kind is retired. Ground-context classes never become events. `ecu_runs` remains on `FlightAnalysis` as the classifier's full output for the event's expanded view and for research.

**Phase-detector dependence.** This classification is only as good as `phases.py`. Finding 9 (takeoff not detected on some flights) must not silently turn a flight's TAKEOFF_ROLL run into `GROUND`: when `PHASE_TAKEOFF_NOT_DETECTED` is raised for a flight, any `GROUND` run with IAS above the taxi ceiling is reported as `IN_FLIGHT` with `phase_uncertain: true`. The phase-regression snapshot (`notebooks/06_phase_regression.py`, per CLAUDE.md) is taken before and after this change.

**Why v0.19.** The previous classifier labelled a run `IN_FLIGHT` whenever it was not POWERUP (< 30 % engine-running rows in *that run*), SHUTDOWN (voltage decline) or LANE_CHECK. It never tested for flight. A one-row blip seconds after the engine catches is 100 % "running" and fell through. Review of the project snapshot's 145 runs: 2026-04-23 19:44:50 (1 s, 1,720 rpm, 2.5 min after power-on, EFIS/NAV still on backup), 2026-04-30 18:30:26 (1 s, 1,770 rpm, on the ground), 2026-05-27 20:06:38 (1 s, 510 rpm, oil 2 psi, OIL PRESS + FUEL PRESS co-active — the engine catching), 2026-06-04 21:17:17 (5 s, 1,760 rpm, oil-pressure NaN 3/5 rows — read at the time as a CAN dropout at idle; the raw log shows RPM and oil pressure stopping after two rows and the log ending — a shutdown, v0.20). Zero in-flight events.

### 8.7 Series for charts

```ts
interface SeriesData {
  flight_id: string; t0_utc: string; source_rows: number;
  t: number[];                                    // elapsed_s
  stride: number;                                 // 1 = full resolution
  channels: Record<string, (number | null)[]>;    // registry ids only
  phases: { phase: string; start_s: number; end_s: number }[];
  markers: { t: number; kind: "exceedance"|"cas"|"ecu"|"phase_change"; ref: string }[];
}
```

Downsampling uses a min/max-preserving envelope (so peaks such as max EGT or oil temperature are never averaged away) with `stride` reported. In-memory transport between worker and UI uses typed arrays (`NaN` = null); persistence and HTTP use JSON with explicit `null`. Rough sizing: 40 channels × 16,196 rows × 4 bytes ≈ 2.6 MB at full resolution for a 4.5-hour flight; a 10× reduced overview ≈ 260 kB.

### 8.8 Topic help (new in v0.15)

Every topic a pilot can see has a one-paragraph explanation — what it checks, what it compares against, why that matters, and what to do if it fires — shown behind a `?` on its card (Spec 03 §5.2). Whether a topic needs one, and when, is Spec 10's call (admission requires it); this section defines the format and how it's delivered.

**Kept outside code, in one file.** All help text lives in a single markdown file, `slingology_eis/help/topics.md`, one `##` section per entry. The heading is the `topic_id` — or, for a non-topic entry such as the flight-summary line, a `help_id` (`flight_summary`). It is followed by `key: value` lines, a blank line, and exactly one paragraph. The file ships inside the package (declared as package data), because it's product content needed at runtime by the UI, the CLI and notebooks alike — not a design document — and one file is easier to review and edit as a whole.

```markdown
## oil_temp_peak
title: Oil temperature peak
applies_to: all                    # or a list of engine profile names, e.g. [914iS, 915iS, 916iS]
last_reviewed: 2026-10-02

One paragraph of plain text, with placeholders such as {limit:oil_temp_max}.
```

A section with a missing key, more than one paragraph, or a duplicate heading is a validation error.

**Placeholders, not numbers.** The text never hard-codes a value that a profile, rule or setting controls — "248 °F" would be wrong in metric units, wrong on another engine profile, and wrong the day a threshold changes. Four namespaces:

| Placeholder | Resolves to | Example |
|---|---|---|
| `{limit:<limit_id>}` | The entry's `limit_value` and `unit` from `limit_catalog()` | `{limit:oil_temp_max}` |
| `{profile:<dotted.path>}` | A value in the engine profile; unit from the key's suffix (`_s` s, `_f` °F, `_c` °C, `_psi` psi, `_inhg` inHg, `_lph` L/h, `_pct` %, `rpm_` rpm). A key with no recognizable unit is a validation error, not a bare number | `{profile:overboost.time_limit_s}` |
| `{rule:<rule_id>.<trigger_type>.<param>}` | A trigger parameter from the active `RuleSet` | `{rule:egt_cyl_deviation.baseline_deviation.n_min}` |
| `{config:<key>}` | A `BaselineConfig` / analysis setting | `{config:outlier_z_threshold}` |

**Returned structured, like analysis lines (§8.5).** The engine works in canonical units (§6.4); units are display-only (Spec 02 §6.6). So the engine doesn't render "248 °F" — it returns the template and the values, and the UI formats each value in the pilot's units:

```ts
interface TopicHelp {
  id: string;                    // topic_id, or help_id for a non-topic entry
  title: string;
  template: string;              // the paragraph with placeholders intact
  values: Record<string, { value: number | string; unit: string | null }>;  // keyed by the placeholder text
  text: string;                  // canonical-unit rendering, for the CLI and plain-text use
  applies: boolean;              // false when the active profile isn't in applies_to (the UI hides the ?)
  validated: boolean;            // v0.16: Admitted (not Unverified) for the active engine profile in Spec 10's register
  last_reviewed: string;
}
```

**Errors are caught at build time, not shown to pilots.** `get_topic_help` returns a diagnostic (`HELP_PLACEHOLDER_UNRESOLVED`, `HELP_MISSING`) rather than raising; acceptance 10 makes every one of them a test failure, so a shipped app never shows a raw `{limit:…}`.

## 9. Extension model (community)

A **Topic** is the unit of extension. A topic module declares:

- `id` and the metrics it produces (registry entries with unit, description, stratification band kind),
- required channels and phases (so missing inputs yield `CHANNEL_MISSING` / `NO_PHASE`, not exceptions),
- a per-flight compute function returning `MetricValue`s, events, and analysis-line values,
- named conditions it contributes to the rule engine (today's hard-coded ones: `rank_changed`, `vs_om_expected`, `any_inflight`, `any_exceedance`),
- optional **view hints** (which chart type and channels best explain it), so a new topic renders in the UI without UI code,
- its **help entry** in `slingology_eis/help/topics.md` (§8.8) — required for any topic shown to pilots (Spec 10), so a community topic arrives with its own explanation.

The rule engine is generic over the three existing trigger types (`threshold`, `baseline_deviation`, `trend`) plus registered conditions. Engine profiles and rule sets remain plain JSON. This section is an **interface sketch**: it will be frozen only after Migration Stage 2 shows what the extracted code actually needs.

## 10. Configuration, options, and privacy

- `AnalysisParams` collects today's tunables (phase thresholds such as `min_cruise_vs_fpm`, `min_cruise_duration_s`, `warmup_oil_target_f`; `skip_ground_sessions`, `min_airborne_min`; DA/OAT band tables; takeoff RPM threshold 5,500) into one hashed object. Values not overridden come from the engine profile.
- `anonymize` option strips `aircraft_ident` (G3X `aircraft_ident` or AXIS `tail_number`), `system_id`, GPS coordinates, and filename airport hints from results and series. It is the basis for the scrubbed fixtures and shareable bundles (Spec 02).
- The engine performs no network access and no persistence. Any host that stores results is responsible for the workspace format (Spec 02).

## 11. Migration plan

Each stage must leave the current CLI output byte-identical (or explicitly diffed) on the provided logs.

| Stage | Work | Verified by |
|---|---|---|
| 0 | **Characterization tests**: golden outputs from the current code for the provided log, `fleet_metrics.csv`, `engine_ecu_runs.csv`, and the current text reports, labelled a **known-defect baseline** (finding 9). | Tests pass on unmodified code. |
| 1 | **I/O and config decoupling**: `load_log_bytes`, engine profile passed explicitly, remove import-time default profile and `__file__`-relative reads from the core (thin wrappers keep old signatures), single JSON serializer replacing the NaN regex, fix `__version__`. | Stage 0 tests unchanged. |
| 2 | **Extract script logic into the library**: fleet baseline/trend/model construction (from 03), insight evaluation and topic analysis lines (from 04), ECU run building (from 02). Scripts become thin renderers. Add `severity` and evidence to rules/insights. | Reports identical to Stage 0; new structured results match reports field-for-field. |
| 3 | **Contract**: metric/channel registries, result types, missing-reason codes, diagnostics, provenance; generate JSON Schemas into `contract/`; add contract tests and fixture bundles. UI development can begin against fixtures here. | Schema validation of all results on the provided data. |
| 4a | **CLI adapter**: the unified `slingology-eis` command (§7.1), in-process against the Stage 3 contract — no Pyodide, no worker, no browser. `--json` output validated against the schemas becomes the live source for Spec 05's fixtures, replacing the hand-authored ones. | Contract tests pass via the CLI; `--json` output round-trips through the schemas; scripts 01–04 still match Stage 0 goldens (unchanged, still calling the same operations). |
| 4b | **Browser worker and local server**: self-hosted Pyodide worker RPC and the local-server adapter, per Spec 04. Built after 4a because it's the harder, higher-risk adapter, and 4a should have already caught most contract-shape problems cheaply. | Same contract tests, run under Pyodide; browser/local-server output matches 4a's CLI output on the same inputs. |

The phase-detector fix (finding 9) is **not** part of these stages. It lands as its own reviewed change after Stage 0, with the resulting golden-output diffs inspected line by line, so the effect of the fix on fleet baselines is visible rather than mixed into the refactor.

## 12. Acceptance criteria (tested against the provided project data)

1. `analyze_flight` on `log_20260423_200615_KACV.csv` reproduces all 31 columns of its `fleet_metrics.csv` row with zero differences, and additionally populates the four newer metrics with explicit missing reasons where null (expected here: `takeoff_*` → `NO_PHASE`, `cruise_nmpg` → `NO_PHASE`).
2. The same run emits `PHASE_TAKEOFF_NOT_DETECTED` (finding 9) and `PHASE_NO_CRUISE`.
3. `analyze_ecu` on that log yields 2 `GROUND_START`, 2 `LANE_CHECK`, 1 `GROUND_SHUTDOWN`, `lane_check: "both"`, no `GROUND`, no `IN_FLIGHT` (the pre-v0.19 goldens read 2 `POWERUP`, 2 `LANE_CHECK`, 1 `SHUTDOWN`). On the full local log set (all logs the loader can read, ground sessions included): `IN_FLIGHT` = 0 on every log; the four shutdown runs the v0.19 rule promoted (04-17 12:13:55, 04-22 19:08:23, 06-17 17:25:09 and its duplicate export) are `GROUND_SHUTDOWN`; 2026-06-04 21:17:17 is `GROUND_SHUTDOWN`; the 2026-04-23, 2026-04-30 and 2026-05-27 blips appear only in `sub_threshold_blips`; the two `GROUND` runs are listed with phase, RPM, IAS and duration; every former `POWERUP`/`SHUTDOWN` run lands in `GROUND_START`/`GROUND_SHUTDOWN`, and any that does not is listed for review.
4. `update_fleet` on the 23 flight rows of `fleet_metrics.csv` reproduces current baseline and trend values (n, mean, std, slope, R²) and the stratified baselines.
5. Every result validates against the generated JSON Schemas; serialization contains no bare `NaN`.
6. No core function reads the filesystem, environment, or wall clock (enforced by a test that runs the core with file access blocked).
7. Adding a hypothetical topic requires no edits outside its own module, its rule entries, and (optionally) a view hint.
8. `evaluate_insights` with leave-one-out membership reproduces the review's trigger counts on the 23 flights in `fleet_metrics.csv` (using the default `outlier_z_threshold` of 2.0, no per-metric overrides set, no `n_min` gating effect since every metric has n ≥ 12): EGT spread 2, EGT4 elevation 1, oil temp peak 1, coolant temp peak 1, oil/coolant ratio 2, cruise efficiency 1, cruise fuel flow 1, climb oil rise 2. **Superseded by R8 (v0.13)** for the stratified metrics: the counts are regenerated on the full log set with stratified comparison, reported per metric as band comparisons, fallbacks, and insights added/removed versus the unstratified rule. Climb oil rise (unstratified) must be unchanged.
9. Scripts 01–04 produce output identical to the Stage 0 goldens after Stages 1–3; every §7 workflow is reachable via a `slingology-eis` subcommand whose `--json` output validates against the schemas.
10. **Topic help (§8.8).** For every bundled engine profile and the default rule set: every topic the engine can emit has a help entry; every placeholder in every applicable entry resolves; `get_topic_help` returns no diagnostics; the rendered `text` contains no `{`. Runs everywhere (no log data needed).
11. **AXIS log source (§6.5).** `ingest_log` on the 2026-10-14 AXIS log (`e5d43072-….csv`) reports `source_format: "axis"`, `aircraft_ident: "N117ZS"`, `engine_hours: 119.6`, `airframe_hours: null`, 2,722 rows after reindexing (18:24:47–19:10:08) of which ≈ 439 are `_filled`, and emits `LOG_RESAMPLED_TO_1HZ` with a share near 0.16. The frame holds every §6.4 channel the analytics consume with the coverage the raw file has (RPM, MAP, power %, oil/coolant temperatures, oil/fuel pressure, fuel flow, EGT1–4, fuel L/R, IAS, altitudes, OAT, DA: full). `gp_analog_3` and `gp_analog_7` are present raw and **no** `co_ppm` channel exists unless the assignment `{ "gp_analog_7": "co_ppm" }` is supplied, in which case `co_ppm` ranges 0–22 and is ≥ 10 on every row whose CAS string contains `CO PPM`. `analyze_flight` classifies the log as a flight (airborne ≈ 38 min, max IAS 126 kt, max baro altitude 6,520 ft, RPM max 5,900), runs the full topic set without error, and reports no `ENGINE ECU` CAS events. The ground-session, short-flight and corrupt-log rules do not fire. G3X logs load byte-for-byte as before: the Stage 0 goldens and criteria 1–3 are unchanged, and no G3X frame gains a `_filled` row.
12. **Second AXIS log (§6.5, v0.24).** `ingest_log` on the 2026-10-18 AXIS log (`d87f9dcb-….csv`, 117 columns) loads with the same mapping as criterion 11's 102-column log; the 15 extra columns raise no diagnostic. `analyze_flight` classifies it as a flight (≈ 107 min airborne, max IAS 135 kt, RPM max 5,820, tach 122.2 → 124.4 h) and `analyze_ecu` yields 2 `LANE_CHECK` (19:57:28 and 19:57:39 UTC, both on the ground), 1 `GROUND_SHUTDOWN` (22:07:09, to end of log), 0 `GROUND_START`, no `GROUND`, no `IN_FLIGHT`, lane check `both lanes ✓`, and no mid-log power-cycle or `corrupt_log` finding for the log opening with the engine running. CAS tokens `EFIS ON BACKUP` and `NAV ON BACKUP` appear in results as `EFIS ON BKUP` / `NAV ON BKUP`.

**Testing limitation.** Only one raw log is available in the project space. Criteria 1–3 are fully testable now; criterion 4 uses the derived metrics table, not raw logs. Full-fleet regression (all 23 flights end to end, ECU events including the two `GROUND` runs, the four late-phase shutdowns and the sub-threshold blips (v0.20)) needs the raw log set, either shared in the project or run locally to produce golden outputs.

## 13. Out of scope for this spec

Results bundle and workspace format (Spec 02); UI layout and chart choices (Spec 03); Pyodide feasibility and performance measurements (Spec 04); new analytics or detector changes, including the phase-detection miss in finding 9 (proposed as a separate BACKLOG item); README, CHANGELOG, and research-paper updates.

## 14. Open questions

**Resolved in v0.2:** Q2 → R1, Q4 → R2, Q5 → R3, Q7 → R4, Q1 → R5 (provisional).

| # | Question | Status |
|---|---|---|
| Q1 | Should `flight_id` also survive re-exports that shift the start minute? | Provisionally resolved (R5). Confirm by running duplicate detection over the full log set and counting `exact` vs `overlap` groups. Needs the raw logs. |
| Q3 | Is the `Topic` plugin interface worth freezing before Stage 2? | Deferred. Freeze after two structurally different topics (a simple threshold topic such as overboost and a model-based one such as takeoff MAP) are ported in Stage 2 without special-casing. |
| Q6 | Which ECU excerpts remain test fixtures now that no `IN_FLIGHT` runs exist? | Proposed (v0.20): one of the two `GROUND` runs, one late-phase shutdown (e.g. 06-17 17:25:09 — exercises rule 1), the 2026-05-27 engine-catch blip (sub-threshold, `OIL PRESS` co-alert) and one paired lane check, as short scrubbed excerpts (GPS dropped or offset). |
| Q9 | ~~Does AXIS name the ECU alert `ENGINE ECU`, and does the CAS text otherwise match?~~ | **Resolved (v0.24).** Yes to `ENGINE ECU`; a few alerts are worded differently and are aliased in the loader (§6.5). |
| Q10 | AXIS logs `onGroundState` directly. Should phase detection use it as an input to the ground/airborne split once the reference is AXIS-dominated? | Open (v0.23). Deferred: no phase-detection change while the reference mixes G3X and AXIS flights. The power-up half of the question is resolved in v0.24: AXIS never logs the engine start (§6.5). |
| Q8 | How are the built UI assets packaged so that `slingology-eis serve` works from a plain `pip`/`pipx` install (bundled in the wheel, or fetched at first run)? | New. To be settled in Spec 04. |
