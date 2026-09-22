# Spec 02 — Results Bundle & Workspace

**Project:** SlingologyEIS web platform
**Status:** Draft v0.3 — for review (no code written)
**Suggested repo path:** `docs/specs/02-results-bundle-and-workspace.md`
**Builds on:** Spec 01 — Engine Contract v0.4; Spec 04 — Runtime Adapters & Pyodide Spike v0.3 (decision: **GO**)
**Precedes:** Spec 03 (UI Information Architecture)
**Baseline reviewed:** repo `main` at commit `ed0ca33` (2026-07-07); the spike results (Spec 04, Appendix A)

**Revision history**

| Version | Change |
|---|---|
| 0.1 | Initial draft. |
| 0.2 | §5.1 rewritten: the local realization is no longer one `<repo-root>/data/` default, but three separate contexts (developer checkout, packaged/local-server install, Docker), because a non-technical path-2 user has no repo at all — just a folder of logs. Adds Spec 01 §7.1's new `--logs DIR` flag and its default-resolution order. New open question Q6. |
| 0.3 | Open questions Q1–Q6 resolved (§12). §6.4 gains a real `engine_overrides.json` design (Q4). Everything else (Q1, Q2, Q3, Q5, Q6) confirmed as proposed — no other section changed. |

---

## 1. Purpose

Spec 01 made the engine **stateless** (principle 2: no filesystem, no globals, same inputs → same outputs). Something still has to persist results between visits, across the CLI, the browser, and the local server, and across every one of a pilot's logs as the fleet grows. This spec defines that something: the **workspace** — a folder layout and a set of JSON documents — and the **results bundle** — a single portable file for export, sharing, and iPad viewing (Spec 01, P3).

It answers: what gets stored, in what shape, where, and how three different hosts (browser, local server, CLI) read and write the same data without stepping on each other.

## 2. Decisions this spec builds on

| # | Decision | Source |
|---|---|---|
| D1 | The engine is stateless; persistence is a host concern. | Spec 01, P2 |
| D2 | Path 1b (browser compute, static hosting) is the primary path; local server/Docker (path 2) is secondary. Both are **GO**. | Spec 01 D2; Spec 04 Appendix B |
| D3 | Browser storage must be treated as **evictable**, especially in Safari; the exported bundle is the source of truth, not the browser cache. | Spec 04 §2.8 |
| D4 | iPad is a viewing target via an exported bundle; whether it can also run full analysis is now confirmed for the tested device (Spec 04), but the bundle-viewer path stays supported regardless of device. | Spec 01 P3; Spec 04 Appendix B |
| D5 | CLI, local server, and browser share one workspace layout, so a report from the command line appears in the UI unchanged. | Spec 01 §7.1 |
| D6 | Annotations are host-supplied input to `evaluate_insights`, keyed by `flight_id` + insight/event ref, not by source file. | Spec 01 R3 |
| D7 | No service-side storage, ever (D3 of the original design discussion). This spec only concerns storage the user's own device or server controls. | Original discussion |
| D8 | A local-server/Docker user has no repo, no git checkout, and no development environment — just a folder of logs. The workspace's default locations must not assume one exists. | Non-technical target user, restated here because §5.1 v0.1 violated it |

## 3. Findings from the code review that shape this spec

1. **Persistence already exists, informally.** Script 03 writes `data/reports/baselines.json` and `data/reports/models.json`; script 04 reads them back. This is a real precedent for the workspace's fleet-level documents — not a green-field design.
2. **The current baselines document mixes three things in one file:** per-metric summary statistics, a `raw` array of every contributing flight's value (used to draw trend charts), and a `by_band` stratification. The new schema keeps this shape rather than inventing a new one, since it already serves the UI's actual need (Spec 01 §8.4's `points` array is this `raw` array, typed).
3. **`NaN` handling is a post-hoc regex patch:** `json.dumps(doc, default=_serialise)` followed by `re.sub(r'\bNaN\b', 'null', raw_json)`. Spec 01 (finding 3) already flags this; this spec's schemas make the patch unnecessary by construction (no `NaN` is ever produced, because `MetricValue.value` is `null` with a `missing` reason instead).
4. **Directory layout is filesystem- and `__file__`-relative:** `LOGS_DIR = _TOOLKIT / "data" / "logs"`, `REPORTS_DIR = _TOOLKIT / "data" / "reports"`, both resolved from the script's own location. This works for a contributor running the CLI from a git checkout, but **not** for the browser, which has no such path, and **not** for a packaged local-server install (Docker, `pipx install`), whose user has no repo at all — just a folder of logs they copied off an SD card. v0.1 of this spec only fixed the browser half of that; §5.1 (v0.2) fixes the other half.
5. **The takeoff-MAP model's `raw` array duplicates source data** (`date`, `engine_hours`, `map_inhg`, …) already present in each flight's own metrics. The workspace schema stores this once, in `FleetAnalysis.metrics[id].points` (Spec 01 §8.4), and the model references flight IDs rather than re-embedding values.
6. **BACKLOG B4** proposed `annotations.json` keyed by source file. Spec 01 (R3) already redirected this to be keyed by `flight_id`; this spec gives it a concrete file.
7. **Browser storage is evictable in Safari** (Spec 04 §2.8, unverified mechanism but real risk) and **was not stress-tested** in the Spec 04 run (S7 persistence probes weren't part of the harness that returned GO). This spec treats browser storage as a cache with an explicit rebuild path, never as the only copy of anything the pilot cares about.
8. **The spike confirmed real memory numbers** for one flight: about 156 MB of Pyodide heap after processing one 4.5-hour flight (Spec 04 Appendix A). A pilot with, say, 100 flights processed in a session (not all held in memory at once, per Spec 01 principle 8) needs the workspace to hold only *derived* results in memory/storage, not raw frames — this spec's split between "engine cache" (small, derived) and "raw logs" (never persisted by the engine layer) follows directly from that.

## 4. Two things, not one

| | **Workspace** | **Results bundle** |
|---|---|---|
| What | A live, growing store: every flight's analysis, the fleet baselines, models, insights, annotations, and settings | A single exported file: a snapshot, or a chosen subset |
| Where it lives | Browser storage (OPFS/IndexedDB), or a folder on disk (CLI/local server) | Wherever the user saves or shares it |
| Lifetime | Grows as logs are imported; rebuilt from raw logs if lost | Point-in-time; immutable once exported |
| Who writes it | The host, after calling engine operations | The host, on export; nothing writes to an imported bundle in place |
| Purpose | Make "import once, browse forever" possible | Backup, sharing, cross-device viewing (iPad), community sample data |

The bundle format is a **read of the workspace**, not a separate schema: it is a subset of the same JSON documents, plus a manifest. This keeps them from drifting apart.

## 5. Workspace layout

One logical layout, two physical realizations.

```
workspace/
├── manifest.json                 # workspace-level metadata, schema version, engine profile in use
├── flights/
│   └── <flight_id>/
│       ├── analysis.json         # FlightAnalysis (Spec 01 §8.3), current engine version
│       ├── sources.json          # which source_keys map to this flight, import history
│       └── series/                # OPTIONAL cached downsampled series (Spec 01 §8.7); omit to save space
│           └── overview.json
├── fleet/
│   ├── selection.json            # FleetSelection + BaselineConfig (which flights are included/excluded, why)
│   ├── analysis.json             # FleetAnalysis (Spec 01 §8.4) — current, rebuilt on demand
│   └── models.json               # Model[] (Spec 01 §8.4) — folded into fleet/analysis.json; see §6.3
├── rules/
│   ├── active.json               # the RuleSet in effect (copy of insight_rules.json + local overrides)
│   └── engine_overrides.json     # OPTIONAL: engine-profile overrides, if the pilot edits limits
├── annotations.json              # host-supplied notes, keyed by flight_id (Spec 01 §8.5, R3)
└── settings.json                 # UI/workspace preferences (units, anonymize default, last-opened view)
```

### 5.1 Local realization (CLI, local server)

A real directory on disk. `flights/`, `fleet/`, `rules/` map to real subfolders. Raw logs are **never** inside the workspace tree — they're always a separate, independently configured location (finding 8; also keeps the workspace small enough to zip and hand over).

The mistake in v0.1 of this spec was treating "the local realization" as one thing with one default (`<repo-root>/data/`). It's really **three different people**, and only one of them has a repo:

| Context | Who | Logs default | Workspace default | Set by |
|---|---|---|---|---|
| **Developer checkout** | A contributor running the CLI from a git clone, or CI reproducing golden outputs | `<repo-root>/data/logs/` | `<repo-root>/data/` | Implicit, only inside a git checkout, only when neither of the below applies |
| **Packaged / local-server install** | The path-2 pilot: `pipx install slingology-eis`, or the packaged app from Spec 04 §9.5 | `~/SlingologyEIS/logs/` | `~/SlingologyEIS/workspace/` | The installer creates this folder on first run; no repo exists |
| **Docker** | Same pilot, running the container instead | Whatever the person mounts | Whatever the person mounts | Two independent volume mounts, not one repo checkout |

None of the three implies the others. A pilot who installs the packaged tool never sees a repository, a `.git` folder, or the word "checkout" — they see one folder (`~/SlingologyEIS/`) that the installer creates for them, exactly the "known folder" idea from the earliest design discussion. The CLI's `--logs DIR` and `--workspace DIR` flags (Spec 01 §7.1, v0.3) make both locations explicit and independent when either default doesn't fit — for example, a pilot who already keeps logs somewhere else, or wants the workspace on external storage.

**Docker example**, showing the two mounts as genuinely separate — logs are read/written by the pilot's own file manager; the workspace is opaque, managed only by the tool:

```
docker run \
  -v ~/RotaxLogs:/data/logs \
  -v ~/RotaxLogs/.slingology-workspace:/data/workspace \
  slingology-eis serve
```

The example above happens to nest the workspace under the logs folder for convenience; nothing requires that — the two mounts are independent by design, and a pilot could equally point them at two unrelated folders, or put the workspace on a different drive.

**Resolution order** (host-side, mirrors Spec 01 §7.1 v0.3): (1) `--logs`/`--workspace` flag; (2) the packaged install's own `~/SlingologyEIS/…` default; (3) `<repo-root>/data/…`, only inside a git checkout with neither of the above. A CLI invocation that is both inside a checkout *and* has a packaged-style config file present (unusual, but possible for a contributor who also installed the packaged tool) prefers (2) — an explicit install always outranks an implicit one.

### 5.2 Browser realization

Each JSON document above becomes one record in a small embedded store — **IndexedDB**, not OPFS, because IndexedDB has a query-by-key model that matches "get the analysis for flight X" directly, while OPFS is a real filesystem better suited to large binary blobs (a use we don't have yet). A `flight_id` becomes the record key.

```
IndexedDB database: "slingology-eis"
├── store "manifest"      → one record
├── store "flights"       → keyed by flight_id, value = { analysis, sources }
├── store "fleet"         → one record { selection, analysis }
├── store "rules"         → one record { active, engine_overrides }
├── store "annotations"   → one record (small; keyed internally by flight_id)
└── store "settings"      → one record
```

Raw log bytes are **never** written to IndexedDB. They're read once (File System Access API where available, or a picked/dropped `File` otherwise), passed to `analyze_flight`, and discarded — matching Spec 01 principle 8 and keeping the browser's storage quota spent on kilobytes of derived JSON, not megabytes of raw CSV.

### 5.3 Why the schema is identical either way

Both realizations store the **same typed objects** from Spec 01 (§8). A local-server response to `GET /flights/<id>` and a browser `db.flights.get(id)` return byte-identical JSON. This is what lets the CLI and the UI agree (D5), and it's what makes exporting a bundle from either host trivial: read the records, wrap them in a manifest, done.

## 6. Document shapes

### 6.1 `manifest.json` (or the `manifest` store record)

```ts
interface WorkspaceManifest {
  schema_version: string;       // this spec's version, independent semver (Spec 01 R4 precedent)
  created_at: string;           // ISO 8601
  updated_at: string;
  engine_version_seen: string[]; // every engine version that has written into this workspace
  flight_count: number;
  storage_backend: "filesystem" | "indexeddb";
}
```

Every write that touches the workspace updates `updated_at` and adds to `engine_version_seen` if new. A workspace opened by a newer engine than any version it has seen is a normal, expected case (upgrade); a workspace opened by an *older* engine than its newest seen version is a downgrade and produces a `WORKSPACE_NEWER_THAN_ENGINE` diagnostic (host-level, not part of the Spec 01 engine diagnostics catalog — this one belongs to the host, not the core).

### 6.2 `flights/<flight_id>/`

`analysis.json` is exactly a Spec 01 `FlightAnalysis`. `sources.json` records provenance the engine itself doesn't need to know about:

```ts
interface FlightSources {
  flight_id: string;
  imports: {
    source_key: string;
    filename: string;           // as provided at import time; not necessarily identifying
    imported_at: string;
    via: "sd_card" | "garmin_pilot" | "unknown";   // best-effort, from filename/path hints
  }[];
  duplicate_of?: string;         // set when ingest_log classified this as a duplicate (Spec 01 §6.2)
}
```

This is where "the same flight from two export paths" (Spec 01 Q1) becomes visible to the user: multiple `imports` entries under one `flight_id`.

### 6.3 `fleet/`

`selection.json`:

```ts
interface FleetSelection {
  included: string[];            // flight_ids
  excluded: { flight_id: string; reason: string }[];  // pilot- or rule-excluded (e.g. known bad log)
  baseline_config: BaselineConfig;   // Spec 01 §8.4 — membership, band_kind_by_metric
}
```

`analysis.json` is a Spec 01 `FleetAnalysis`, with `models` (the `Model[]`, e.g. `takeoff_map`) included inline rather than as a separate file — the earlier layout's split between `baselines.json` and `models.json` (finding 2) is a historical accident of what script wrote it, not a meaningful boundary; both are outputs of the same `update_fleet` operation and are staleness-linked (Spec 01 §7).

### 6.4 `rules/`

`active.json` is the `RuleSet` (Spec 01 §8.5) currently governing insight evaluation — normally a copy of the repo's `insight_rules.json`, but the **rule playground** (Spec 01 §5) edits a working copy here without touching the repo file, so experimentation is per-workspace and disposable.

`engine_overrides.json` (resolved, Q4) lets a pilot note "my POH/placard says X, not the shipped default" without editing the repo's `engines/<name>.json`:

```ts
interface EngineOverrides {
  version: string;
  base_engine: string;            // e.g. "916iS" — which shipped profile this overrides
  base_profile_hash: string;      // hash of the shipped profile when overrides were created,
                                   // so a later update to the shipped profile is detectable
  overrides: {
    param: string;                // matches a Limit.param in the base profile's limits[]
    field: "min_val" | "max_val" | "time_limit_s" | "severity" | "note";
    value: number | string;
    reason: string;                // required — why, not just what
    source: string;                // citation, e.g. "POH rev 4, p.12" or "placard S/N 4471"
  }[];
  created_at: string;
  updated_at?: string;
}
```

The host — never the engine — merges the base profile and this file into one effective `EngineProfile` before calling `analyze_flight`: a deep copy of the base profile with each override applied by `(param, field)`. `profile_hash` is recomputed over the *merged* content, and `source_status` becomes `CUSTOM` (Spec 01 v0.4, §6.3), which the engine surfaces as the `ENGINE_CUSTOM_OVERRIDE` diagnostic so reports and insights visibly flag that displayed limits aren't the shipped defaults. If `base_profile_hash` no longer matches the current shipped profile (the maintainer updated `engines/<name>.json`), the host warns the pilot that their overrides were computed against a now-stale base, rather than silently merging onto a moved target.

### 6.5 `annotations.json`

```ts
interface AnnotationStore {
  version: string;
  annotations: {
    id: string;                  // stable id, e.g. uuid
    flight_id: string;
    ref: { kind: "insight"; insight_id: string } | { kind: "exceedance" | "ecu_run" | "cas_event"; ref: string };
    note: string;
    created_at: string;
    updated_at?: string;
  }[];
}
```

Passed to `evaluate_insights` as the `annotations` argument (Spec 01 §8.5, R3) filtered to the relevant `flight_id`. The host is responsible for matching; the engine only attaches.

### 6.6 `settings.json`

```ts
interface WorkspaceSettings {
  units: "imperial" | "metric";          // display only; engine always works in the units in Spec 01 §6.4
  anonymize_by_default: boolean;
  active_engine_profile: string;         // e.g. "916iS"
  last_view?: { kind: string; flight_id?: string };  // convenience, not load-bearing
}
```

## 7. The results bundle

A single file, `.eisbundle.json` (or `.eisbundle.zip` — see §7.3), containing a snapshot of some or all of the workspace, self-describing enough to be opened cold on another device.

### 7.1 Manifest-first shape

```ts
interface ResultsBundle {
  bundle_version: string;                 // this spec's version
  exported_at: string;
  exported_by: { app: string; version: string };   // e.g. "slingology-eis-web" "0.1.0"
  scope: "single_flight" | "fleet_subset" | "full_workspace";
  anonymized: boolean;                    // whether identifying fields were stripped (Spec 01 §10)
  flights: FlightAnalysis[];              // Spec 01 §8.3, per scope
  fleet?: FleetAnalysis;                  // present unless scope === "single_flight"
  annotations?: AnnotationEntry[];        // filtered to the included flights
  rules_used?: RuleSet;                   // the rules that produced flights[].insights, for reproducibility
}
```

Deliberately excluded from the bundle: raw log bytes, full-resolution series data (Spec 01 §8.7) beyond what's needed for the flight-view charts, and any engine-internal cache. The bundle is meant to be readable and diffable, and to stay small — the "no service-side storage" principle (D7) extends naturally to "no accidental raw-data leakage in something meant to be shared."

### 7.2 GPS handling

Per Spec 01 §10, `anonymize` strips GPS along with `aircraft_ident`/`system_id`. The bundle format defaults `anonymized: true` for any bundle created via a "share" or "export for community" action, and `false` for a personal backup a pilot exports for themselves — this is a UI-level choice (Spec 03), not an engine one, but the bundle schema needs the field regardless so a consumer can tell which kind it's opening.

### 7.3 File format: JSON vs. a zip

A `full_workspace` bundle for a pilot with 100+ flights could reach a few megabytes of JSON — fine to read, awkward to browse by hand. Proposal: `.eisbundle.json` for `single_flight` and small `fleet_subset` exports (the common "check this one flight" or "here's my ECU issue" case); `.eisbundle.zip` (containing `manifest.json` + one file per flight, mirroring the workspace's own `flights/<id>/analysis.json` layout) for `full_workspace` exports. Both share the same manifest shape; the zip just splits `flights` across files instead of inlining the array. This is a proposal, not fixed — see Q2.

### 7.4 Import

Importing a bundle merges it into the target workspace: flights are added or updated by `flight_id` (an imported analysis from a newer engine version wins; from an older one, the host warns and keeps the newer local copy — never silently discards either), fleet analysis is recomputed locally rather than trusted from the bundle (since `update_fleet` is cheap and the local `FleetSelection` may differ), and annotations are merged additively by `id`. A bundle is never "opened in place" as the live workspace; it's always merged, even into an empty one — this keeps exactly one code path instead of two.

## 8. Staleness and the workspace

Spec 01 §7 already defines when a `FlightAnalysis`, `FleetAnalysis`, or `InsightSet` is stale. The workspace's job is to **store the inputs that staleness is computed from** — `analysis_key`, `fleet_key`, `rules_hash` — right alongside each document, so a host can answer "is this still current?" without recomputing anything:

```ts
// appended to what's stored, not part of the engine's own FlightAnalysis
interface StoredFlightAnalysis {
  analysis: FlightAnalysis;      // includes analysis_key already (Spec 01 §8.3)
  computed_at: string;
  stale: boolean;                // set by the host when a dependency it tracks has changed
}
```

`stale` is a host-computed cache hint, not engine output — it lets the UI show "this needs recomputing" without a round trip, and workflows (`import_and_update`, `rebuild_baselines`, Spec 01 §7) are what actually clear it by recomputing.

## 9. Storage budget and eviction (browser)

Per finding 8 and Spec 04 §2.8:

- **Typical size:** one `FlightAnalysis` is small — the spike's real pipeline output was under 5 KB of JSON for the metrics and phases alone (Spec 04's uploaded results contained the full structure at under 3 KB serialized in the worker). Even a few hundred flights of derived results should stay in the low tens of megabytes, nowhere near typical browser storage quotas (which run to hundreds of MB or more, though never guaranteed — see Q3).
- **The browser can evict IndexedDB data**, especially in Safari after a period of disuse. The workspace is therefore always a rebuildable cache from the host's perspective: on open, the UI checks whether the workspace is empty or partial and offers "re-import your logs" or "restore from a bundle" rather than treating an empty store as a first-run state indistinguishable from data loss.
- **Recommendation, not yet decided:** prompt for `navigator.storage.persist()` (where available) on first meaningful use, and periodically remind the pilot to export a backup bundle. Both are UI behavior for Spec 03; this spec just ensures the underlying data is small and self-contained enough for that to work.

## 10. What this spec does not cover

The chart-ready series cache (`series/overview.json` in §5) is sketched but not fully specified — its downsampling parameters and cache-invalidation rule depend on Spec 03's chart design. The rule-playground's exact diff view is Spec 03. Multi-user or multi-device sync of one workspace is out of scope entirely — the bundle import/export *is* the sync mechanism, deliberately manual, consistent with "no service-side storage." Engine-profile override editing (`engine_overrides.json`) is named but not designed.

## 11. Migration and testing

This spec has no engine code to migrate — it's purely a host-side addition, built on top of Spec 01's Stage 3+ (contract) and Stage 4 (adapters). Suggested order:

1. Implement the local-filesystem realization (§5.1) first, since the CLI already has the closest precedent (`data/reports/`) and it's testable without a browser.
2. Implement `export_bundle`/`import_bundle` against the filesystem realization; test round-tripping the 23-flight fleet (pending more raw logs, per Spec 01 Q6, same limitation as before).
3. Implement the IndexedDB realization behind the same interface used by the browser adapter (Spec 04 §9.1), and confirm identical JSON shapes between the two.

## 12. Open questions — resolved (2026-09-22)

| # | Question | Decision |
|---|---|---|
| Q1 | Should `series/` caching (§5, §10) be in scope for v1, or deferred until Spec 03 defines what the flight-view chart actually needs? | **Defer to Spec 03.** Re-parsing on demand (Spec 01 `get_series`) is cheap per the spike numbers (2.1–2.6 s for a full 4.5-hour flight's load+phases+metrics, Spec 04 Appendix A). |
| Q2 | `.eisbundle.json` vs `.eisbundle.zip` for full-workspace exports (§7.3)? | **Two formats by scope**, as proposed in §7.3: `.eisbundle.json` for `single_flight`/small `fleet_subset` (readable, diffable); `.eisbundle.zip` for `full_workspace`. |
| Q3 | Should the workspace track its own storage usage and warn before hitting a browser quota, or rely on `navigator.storage.estimate()` at UI level? | **UI-level, Spec 03.** This spec keeps the data small (§9); quota warnings are a UI concern. |
| Q4 | Does `engine_overrides.json` need a real design now? | **Designed now** — see §6.4. Merged host-side into a `CUSTOM`-status `EngineProfile` (Spec 01 v0.4, §6.3); triggers `ENGINE_CUSTOM_OVERRIDE`. |
| Q5 | Bundle import currently always merges (§7.4) — is there a case for a true "read-only, don't merge" viewer mode? | **Defer to Spec 03.** UI choice ("preview" vs. "import" button), not a schema change — the bundle format is unaffected either way. |
| Q6 | Should the packaged installer's default (`~/SlingologyEIS/`) be a fixed, hardcoded name, or configurable/platform-conventional? | **Fixed, plain home-directory folder** (`~/SlingologyEIS/`, not e.g. macOS's `~/Library/Application Support/…`). Discoverability by a non-technical pilot in Finder/Explorer outweighs platform convention. |
