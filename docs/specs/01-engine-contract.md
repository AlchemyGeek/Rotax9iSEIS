# Spec 01 — Engine Contract

**Project:** SlingologyEIS web platform
**Status:** Draft v0.4 — for review (no code written)
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
| `flight_id` | Opaque hash of the flight fingerprint (aircraft ident, system ID, start minute) | Identifies one physical flight across export paths. An SD-card export and a Garmin Pilot export of the same flight share a `flight_id` but differ in `source_key`. |
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
| `update_fleet` | `FlightAnalysis[]`, `FleetSelection`, `BaselineConfig` | `FleetAnalysis` | Metrics table, baselines, trends, outliers, models. No raw data. |
| `evaluate_insights` | `FlightAnalysis`, `FleetAnalysis`, `RuleSet` | `InsightSet` | Pure and fast; the **rule playground** re-runs only this. |
| `analyze_ecu` | `FlightAnalysis[]` | `EcuAnalysis` | Runs, classification, lane-check pairing, co-active alerts. |
| `render_report` | `InsightSet`, `FlightAnalysis`, format | text/markdown | Text report from structured data. |
| `validate_rules` | `RuleSet` | diagnostics | Schema and semantic checks. |

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
| `export-bundle` | results bundle (Spec 02) | – |
| `serve` | starts the local server and UI (path 2) | – |

**Global options:** `--logs DIR`, `--workspace DIR`, `--engine NAME`, `--json`, `--anonymize`, `--quiet`. **Exit codes:** `0` success, `1` operation failed, `2` usage error.

`--logs` and `--workspace` are independent — neither implies the other, and neither implies a git checkout. Their defaults, in order of precedence, are resolved by the host (not the engine) as: (1) the flag, if given; (2) a packaged install's own default folder (a named folder under the user's home directory — see Spec 02 §5.1 for the exact path); (3) `<repo-root>/data/logs` and `<repo-root>/data/` respectively, **only** when the CLI is run from inside a git checkout and neither flag nor (2) applies. Case (3) exists for contributors and CI reproducing the current scripts' behavior; it is not the default for anyone who installed the tool rather than cloned it.

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

Diagnostic catalog (v0.1): `INGEST_UNKNOWN_FORMAT`, `INGEST_GROUND_SESSION`, `INGEST_DUPLICATE_OF`, `INGEST_MULTI_POWER_CYCLE`, `INGEST_MISSING_CHANNEL`, `INGEST_SIGNAL_GAP`, `PHASE_TAKEOFF_NOT_DETECTED`, `PHASE_NO_CLIMB`, `PHASE_NO_CRUISE`, `BASELINE_LOW_N`, `MODEL_INSUFFICIENT_DATA`, `ENGINE_PLACEHOLDER_CONFIG`. Added in v0.4: `ENGINE_CUSTOM_OVERRIDE`.

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
| EGT | `egt_spread_mean_f`, `egt_spread_max_f`, `egt4_elevation_f`, `egt_rank_stable` |
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
                        by_band?: { band_kind: "oat_band"|"da_band"; bands: Record<string, Baseline> };
                        points: { flight_id: string; date: string; x: number|null; value: number; band?: string }[];
                        outliers: { flight_id: string; z_score: number }[] }
interface Model    { id: "takeoff_map"; kind: "linear_regression"; features: string[];
                     coefficients: Record<string, number>; n: number; r_squared: number|null;
                     confidence: Baseline["confidence"]; capture: string }  // capture: e.g. "RPM>=5500 during TAKEOFF_ROLL"
interface FleetAnalysis { fleet_key: string; flight_ids: string[]; excluded: {flight_id:string; reason:string}[];
                          metrics: Record<string, MetricFleet>; models: Model[];
                          quality: Diagnostic[]; provenance: Provenance }
```

`confidence.level` is a **structured enum**; the human sentence ("MODERATE (n=15 …)") is a renderer concern. The `points` array replaces the `raw` blocks in `baselines.json` and is what the trend charts draw.

**Baseline membership (resolved, R2).** The current code builds one baseline over all flights (script 03) and script 04 compares each flight against it, so a flight is compared against a baseline that includes itself. The contract instead specifies:

- `FleetAnalysis` keeps the all-flights baseline for display (trend charts, baseline bands) and the per-flight `points` array.
- `evaluate_insights` compares each flight against a **leave-one-out** baseline derived from `points` (mean and standard deviation excluding that flight).
- `baseline_deviation` triggers require a minimum sample size, `n_min` (proposed default 10, matching the existing trend triggers; tunable per rule through the rule playground). Below it, the analysis line is shown with a `BASELINE_LOW_N` note and no insight fires.

```ts
interface BaselineConfig {
  membership: "leave_one_out" | "all";   // default "leave_one_out"
  band_kind_by_metric: Record<string, "oat_band" | "da_band" | null>;
}
```

Evidence from the review (23 real flights in `fleet_metrics.csv`, |z| ≥ 2.0): self-inclusion changed four borderline results (z between 1.8 and 2.1, always damped); a "prior flights only" baseline was unstable and order-dependent. At n = 23, about one chance trigger per metric is expected at this threshold, which is why the sample-size gate matters more for new users with few flights.

### 8.5 Topics, analysis lines, insights (the two-layer format as data)

```ts
interface TopicResult {
  topic_id: string;               // rule id: egt_spread, egt4_elevation, cylinder_rank, oil_temp_peak,
                                  // coolant_temp_peak, oil_coolant_ratio, overboost_time, cruise_efficiency,
                                  // cruise_fuel_flow, map_at_takeoff, engine_ecu_inflight, flight_phase_mix,
                                  // limit_exceedances, climb_thermal_rate
  analysis: { template: string; values: Record<string, number|string|null>; text: string };  // always present
  insight: Insight | null;                                                                    // conditional
  metric_ids: string[];
}
interface Insight {
  id: string; topic_id: string; rule_id: string;
  trigger: "threshold" | "baseline_deviation" | "trend";
  severity: "info" | "watch" | "warning" | "limit";
  message: { template: string; values: Record<string, unknown>; text: string };
  evidence: (
    | { kind: "metric"; metric_id: string }
    | { kind: "baseline_point"; metric_id: string; flight_id: string }
    | { kind: "series_window"; channels: string[]; start_s: number; end_s: number }
    | { kind: "exceedance" | "ecu_run"; ref: string })[];
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

`EcuRun` mirrors the current `engine_ecu_runs.csv` columns: `start`/`end` (UTC + `elapsed_s`), `duration_s`, `classification` (`POWERUP` | `SHUTDOWN` | `LANE_CHECK` | `IN_FLIGHT`), `lane_check_pair` + `lane_check_note`, `co_alerts`, and the per-run context means (RPM, power %, oil pressure/temp, coolant temp, main volts, battery amps, fuel pressure, IAS, baro altitude, `volts_delta`, `rpm_accel_pre`, `oil_nan_frac`). `EcuAnalysis` adds per-classification counts and, per BACKLOG B3, **per-event** co-active alerts for each `IN_FLIGHT` event rather than a pooled table.

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

## 9. Extension model (community)

A **Topic** is the unit of extension. A topic module declares:

- `id` and the metrics it produces (registry entries with unit, description, stratification band kind),
- required channels and phases (so missing inputs yield `CHANNEL_MISSING` / `NO_PHASE`, not exceptions),
- a per-flight compute function returning `MetricValue`s, events, and analysis-line values,
- named conditions it contributes to the rule engine (today's hard-coded ones: `rank_changed`, `vs_om_expected`, `any_inflight`, `any_exceedance`),
- optional **view hints** (which chart type and channels best explain it), so a new topic renders in the UI without UI code.

The rule engine is generic over the three existing trigger types (`threshold`, `baseline_deviation`, `trend`) plus registered conditions. Engine profiles and rule sets remain plain JSON. This section is an **interface sketch**: it will be frozen only after Migration Stage 2 shows what the extracted code actually needs.

## 10. Configuration, options, and privacy

- `AnalysisParams` collects today's tunables (phase thresholds such as `min_cruise_vs_fpm`, `min_cruise_duration_s`, `warmup_oil_target_f`; `skip_ground_sessions`, `min_airborne_min`; DA/OAT band tables; takeoff RPM threshold 5,500) into one hashed object. Values not overridden come from the engine profile.
- `anonymize` option strips `aircraft_ident`, `system_id`, GPS coordinates, and filename airport hints from results and series. It is the basis for the scrubbed fixtures and shareable bundles (Spec 02).
- The engine performs no network access and no persistence. Any host that stores results is responsible for the workspace format (Spec 02).

## 11. Migration plan

Each stage must leave the current CLI output byte-identical (or explicitly diffed) on the provided logs.

| Stage | Work | Verified by |
|---|---|---|
| 0 | **Characterization tests**: golden outputs from the current code for the provided log, `fleet_metrics.csv`, `engine_ecu_runs.csv`, and the current text reports, labelled a **known-defect baseline** (finding 9). | Tests pass on unmodified code. |
| 1 | **I/O and config decoupling**: `load_log_bytes`, engine profile passed explicitly, remove import-time default profile and `__file__`-relative reads from the core (thin wrappers keep old signatures), single JSON serializer replacing the NaN regex, fix `__version__`. | Stage 0 tests unchanged. |
| 2 | **Extract script logic into the library**: fleet baseline/trend/model construction (from 03), insight evaluation and topic analysis lines (from 04), ECU run building (from 02). Scripts become thin renderers. Add `severity` and evidence to rules/insights. | Reports identical to Stage 0; new structured results match reports field-for-field. |
| 3 | **Contract**: metric/channel registries, result types, missing-reason codes, diagnostics, provenance; generate JSON Schemas into `contract/`; add contract tests and fixture bundles. UI development can begin against fixtures here. | Schema validation of all results on the provided data. |
| 4 | **Adapters and CLI**: browser worker RPC (Pyodide), local server, and the unified `slingology-eis` CLI (§7.1) per Spec 04; run the contract tests under Pyodide. | Same tests, both runtimes; CLI parity check. |

The phase-detector fix (finding 9) is **not** part of these stages. It lands as its own reviewed change after Stage 0, with the resulting golden-output diffs inspected line by line, so the effect of the fix on fleet baselines is visible rather than mixed into the refactor.

## 12. Acceptance criteria (tested against the provided project data)

1. `analyze_flight` on `log_20260423_200615_KACV.csv` reproduces all 31 columns of its `fleet_metrics.csv` row with zero differences, and additionally populates the four newer metrics with explicit missing reasons where null (expected here: `takeoff_*` → `NO_PHASE`, `cruise_nmpg` → `NO_PHASE`).
2. The same run emits `PHASE_TAKEOFF_NOT_DETECTED` (finding 9) and `PHASE_NO_CRUISE`.
3. `analyze_ecu` on that log reproduces its rows in `engine_ecu_runs.csv` (2 `POWERUP`, 2 `LANE_CHECK`, 1 `SHUTDOWN`; no `IN_FLIGHT`).
4. `update_fleet` on the 23 flight rows of `fleet_metrics.csv` reproduces current baseline and trend values (n, mean, std, slope, R²) and the stratified baselines.
5. Every result validates against the generated JSON Schemas; serialization contains no bare `NaN`.
6. No core function reads the filesystem, environment, or wall clock (enforced by a test that runs the core with file access blocked).
7. Adding a hypothetical topic requires no edits outside its own module, its rule entries, and (optionally) a view hint.
8. `evaluate_insights` with leave-one-out membership reproduces the review's trigger counts on the 23 flights in `fleet_metrics.csv` (|z| ≥ 2.0, no `n_min` gating effect since every metric has n ≥ 12): EGT spread 2, EGT4 elevation 1, oil temp peak 1, coolant temp peak 1, oil/coolant ratio 2, cruise efficiency 1, cruise fuel flow 1, climb oil rise 2.
9. Scripts 01–04 produce output identical to the Stage 0 goldens after Stages 1–3; every §7 workflow is reachable via a `slingology-eis` subcommand whose `--json` output validates against the schemas.

**Testing limitation.** Only one raw log is available in the project space. Criteria 1–3 are fully testable now; criterion 4 uses the derived metrics table, not raw logs. Full-fleet regression (all 23 flights end to end, ECU events including the four genuine `IN_FLIGHT` runs) needs the raw log set, either shared in the project or run locally to produce golden outputs.

## 13. Out of scope for this spec

Results bundle and workspace format (Spec 02); UI layout and chart choices (Spec 03); Pyodide feasibility and performance measurements (Spec 04); new analytics or detector changes, including the phase-detection miss in finding 9 (proposed as a separate BACKLOG item); README, CHANGELOG, and research-paper updates.

## 14. Open questions

**Resolved in v0.2:** Q2 → R1, Q4 → R2, Q5 → R3, Q7 → R4, Q1 → R5 (provisional).

| # | Question | Status |
|---|---|---|
| Q1 | Should `flight_id` also survive re-exports that shift the start minute? | Provisionally resolved (R5). Confirm by running duplicate detection over the full log set and counting `exact` vs `overlap` groups. Needs the raw logs. |
| Q3 | Is the `Topic` plugin interface worth freezing before Stage 2? | Deferred. Freeze after two structurally different topics (a simple threshold topic such as overboost and a model-based one such as takeoff MAP) are ported in Stage 2 without special-casing. |
| Q6 | Are the four `IN_FLIGHT` ECU events and the KSFF `OIL PRESS` co-alert to remain test fixtures? | Proposed: yes, as short scrubbed excerpts (GPS dropped or offset). Needs the raw logs. |
| Q8 | How are the built UI assets packaged so that `slingology-eis serve` works from a plain `pip`/`pipx` install (bundled in the wheel, or fetched at first run)? | New. To be settled in Spec 04. |
