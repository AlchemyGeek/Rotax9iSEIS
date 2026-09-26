# Spec 02 — Results Bundle & Workspace

**Project:** SlingologyEIS web platform
**Status:** Draft v0.6 — for review (no code written)
**Suggested repo path:** `docs/specs/02-results-bundle-and-workspace.md`
**Builds on:** Spec 01 — Engine Contract v0.5; Spec 04 — Runtime Adapters & Pyodide Spike v0.3 (decision: **GO**)
**Precedes:** Spec 03 (UI Information Architecture)
**Baseline reviewed:** repo `main` at commit `ed0ca33` (2026-07-07); the spike results (Spec 04, Appendix A); `workspaces-and-log-browser.md` design notes (2026-09-23)

**Revision history**

| Version | Change |
|---|---|
| 0.1 | Initial draft. |
| 0.2 | §5.1 rewritten: the local realization is no longer one `<repo-root>/data/` default, but three separate contexts (developer checkout, packaged/local-server install, Docker), because a non-technical path-2 user has no repo at all — just a folder of logs. Adds Spec 01 §7.1's new `--logs DIR` flag and its default-resolution order. New open question Q6. |
| 0.4 | **Multiple workspaces.** A user needs separate analysis contexts for different aircraft, or for experimenting with a subset of their own logs — v0.3 assumed exactly one workspace per install, which silently corrupts baselines the moment two aircraft's logs mix. Rewrites §5 around a workspace **registry** (many workspaces, one active) sitting above the existing per-workspace layout (which is otherwise unchanged in shape). Logs are now explicitly **referenced by folder, never copied**, matched by content fingerprint so renames/moves survive a rescan. `FleetSelection` (§6.3) splits automatic folder-derived membership from the one real in-app selection (baseline exclusion). `settings.json` (§6.6) splits into app-level and workspace-level. New §6.7 (workspace registry document), §5.5 (cross-aircraft and duplicate-folder safeguards). Four new open questions (Q7–Q10), one existing question (Q5) sharpened with a concrete proposal. Source: `workspaces-and-log-browser.md`. |
| 0.5 | Q7–Q10 resolved, each folded into the relevant section rather than left as a table entry: §5.6 splits cross-aircraft handling into a hard, by-construction engine-model constraint (workspace-level, not detected per-log) and a purely informational tail-number difference; §6.1's `aircraft` field restructured accordingly; §5.5 (new) covers the missing-log vs. unreachable-folder distinction; §5.8 notes the Spec 01 CLI change Q10 requires. New open item Q11: no data signal is confirmed to exist for detecting a log's engine variant automatically — the by-construction design sidesteps this rather than solves it. |
| 0.6 | Findings from the first real implementation pass. Two things fixed, not just documented: **`log_folders[].path` was genuinely wrong** — it mixed a JSON-serializable path string with a browser-only `FileSystemDirectoryHandle` in one field, quietly breaking §5.10's "identical JSON" claim; split into a plain display `path` (both realizations) plus a separate non-JSON handle store keyed by a new `folder_id`. **Exact-fingerprint duplicates must not reuse the overlap-duplicate drop-one-keep-one logic** — doing so silently discards a second export path instead of recording it in `imports[]`, defeating the reason that array exists; §5.7 now says so explicitly, plus which import wins when one is picked as primary (reuse the existing `most_rows` comparator). Two things added: `FlightSources.missing` (§6.2 — the field §5.5's persistence rule needed but the original sketch didn't have), and a fingerprint-caching rule (§5.7 — skip re-hashing a file whose path/size/mtime haven't changed, since reading every file's full bytes on every scan was asserted cheap without being addressed). |

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
| D9 | Logs belong to the user, workspaces belong to the app. The app **only reads** logs — never copies, moves, renames, or writes into a log folder — and a workspace is just an app-managed list of folders plus derived results. A pilot can have any number of workspaces (different aircraft, or an experiment on a subset of their own logs), exactly one active at a time. | `workspaces-and-log-browser.md`, §2.1–2.2 |
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

## 5. Multiple workspaces

A pilot can have several workspaces — one per aircraft, or an experiment holding a chosen subset of their own logs. Exactly **one is active** at a time; everything else in this spec (analysis, baselines, the CLI's `--workspace`, the browser store) acts on that one workspace, and the app remembers which one across restarts.

### 5.1 What a workspace is

A workspace is **a list of one or more log folders, plus everything derived from what's in them.** Not a copy of the logs — a reference. Membership isn't a stored list the app maintains; it's *whatever the referenced folders currently contain*, recomputed on every rescan. Subfolders are included automatically. There is no in-app filter for "which of my logs are in this workspace" — that's controlled entirely by how the pilot organizes their own files into folders, which is deliberate (§5.4 explains why this, not an in-app picker).

The one real in-app selection is narrower and different: which *member* flights feed baselines (§6.3) — a pilot can exclude a known-bad log from the fleet statistics without removing it from the workspace or touching their file system.

### 5.2 The registry (app-level, above any one workspace)

Something has to list the workspaces themselves, independent of which one is active. This is new relative to v0.3, which assumed exactly one workspace existed.

```ts
interface WorkspaceRegistryEntry {
  id: string;
  name: string;                          // pilot-chosen, e.g. "N117ZS – all", "ECU investigation"
  engine_model: string;          // e.g. "916iS" — required, set at creation (Q9), locked; selects the EngineProfile for every log in this workspace (§5.6). Not detected per-log — see Q11.
  primary_tail_number?: string;  // informational only, last-seen or pilot-set; never gates anything (§5.6)
  created_at: string;
  last_opened_at: string;
  log_folder_count: number;
  flight_count: number;                  // as of the last scan, for display without opening it
}
```

The registry itself is small and app-level — see §6.7 for where it lives in each realization.

### 5.3 Per-workspace layout

Unchanged in shape from v0.3, just now one of possibly several:

```
workspaces/<workspace_id>/
├── manifest.json                 # now includes log_folders[] and aircraft — see §6.1
├── flights/
│   └── <flight_id>/
│       ├── analysis.json         # FlightAnalysis (Spec 01 §8.3), current engine version
│       ├── sources.json          # folder + relative path + fingerprint per import — see §6.2
│       └── series/                # OPTIONAL cached downsampled series (Spec 01 §8.7); omit to save space
│           └── overview.json
├── fleet/
│   ├── selection.json            # baseline exclusions + BaselineConfig — membership is NOT stored here, see §6.3
│   ├── analysis.json             # FleetAnalysis (Spec 01 §8.4) — current, rebuilt on demand
│   └── models.json               # Model[] (Spec 01 §8.4) — folded into fleet/analysis.json; see §6.3
├── rules/
│   ├── active.json               # the RuleSet in effect (copy of insight_rules.json + local overrides)
│   └── engine_overrides.json     # OPTIONAL: engine-profile overrides, if the pilot edits limits
├── annotations.json              # host-supplied notes, keyed by flight_id (Spec 01 §8.5, R3)
└── settings.json                 # workspace-level only now — see §6.6
```

### 5.4 Why folders, not an in-app subset picker

Two reasons, both from `workspaces-and-log-browser.md` §2.3: it keeps the app from ever needing write access to organize the pilot's own files, and it means the pilot's existing folder structure (by aircraft, by year, by "stuff I'm investigating") is the only thing they have to maintain — the workspace just points at it. An experiment workspace is a second, narrower folder reference into the pilot's own already-organized subset, not a duplicate or a filtered copy.

### 5.5 Missing logs vs. unreachable folders (resolves Q7)

Two different situations, deliberately given different treatment rather than one generic "can't find it" state:

- **A whole folder is unreachable** (moved, external drive unplugged, network share down): one event, not N per-log failures. The workspace shows a single "folder unreachable" state with one "Locate folder" action; nothing under it is individually marked Missing while the folder itself is simply not there to check.
- **A specific log's fingerprint genuinely isn't found** in any reachable folder (actually deleted, or moved somewhere no known folder covers): stays listed as **Missing**, and — this is the part worth stating explicitly — its results and its baseline contribution are **unchanged**, indefinitely, until the pilot explicitly clicks something like "Remove missing flights." The alternative (auto-dropping it) risks a worse failure: a baseline point silently disappearing from a trend chart could read as "the metric improved" when a data point just vanished. A cluttered Missing list is the safer failure mode.

### 5.6 Cross-aircraft safety: engine model vs. tail number (resolves Q8)

These turned out to need genuinely different mechanisms, not just different severities — traced against the actual loader code (`limits.py`), engine model (912iS/914iS/915iS/916iS) **isn't in the log data at all**. It's a setting resolved explicitly → env var → `config.json` → default; the loader only ever extracts `aircraft_ident` (tail number) and `system_id` from the log header. So "detect the wrong engine type and reject it" isn't something the data supports today.

The design instead makes mixing engine types **impossible by construction** rather than something to detect after the fact:

- **`engine_model` is a workspace-level constant**, set once when the workspace is created (or inherited from the first log's context, per Q9), and applied to every log in it unconditionally — it's what selects the `EngineProfile` (Spec 01 §6.3) the whole workspace uses. There is no per-log override and no per-log mismatch check, because there's nothing in a log to check it against. A pilot with aircraft of two different engine types simply has two workspaces; the constraint is structural, not enforced.
- **Tail number is purely informational, never a gate.** A log whose `aircraft_ident` differs from ones the workspace has already seen gets a small "different aircraft: N123AB" indicator and is included normally — no confirmation step, no exclusion. This is what makes managing several same-engine-type aircraft in one workspace (a flight school, a partnership) a supported case rather than something the system is suspicious of.
- **Open gap, not silently solved:** nothing currently catches a pilot accidentally pointing a 912iS log at a 916iS workspace — the wrong limits would be applied without any warning. See Q11.

### 5.7 Other matching rules, unchanged

- **Fingerprint, not path.** Each log is matched by content hash (Spec 01 §6.1's `source_key`, reused as the fingerprint here), not by filename or location. A rename or move inside a known folder is re-matched automatically on rescan — no re-import, no lost annotations.
- **Same log in two folders**, or nested folders producing the same file twice: de-duplicated by fingerprint, one flight either way.
- **Same flight, two export paths** (SD card vs. Garmin Pilot): already Spec 01's `flight_id`/duplicate-detection job (§6.2); unchanged here — **but this is not the same operation as `find_duplicate_flights`'s overlap handling, and must not reuse that code path.** `find_duplicate_flights`/`deduplicate_flights` (used for `match_kind == "overlap"`: different `flight_id`s that are ambiguously the same flight) drop every duplicate but one. Applied to an **exact** fingerprint match — same `flight_id`, genuinely the same flight via two export paths — that's wrong: it would silently discard the second export path instead of recording it as a second `imports[]` entry, which is the entire reason §6.2 has an `imports[]` array instead of a single source. Exact matches merge by `flight_id` into one flight with multiple `imports[]` entries; only overlap matches go through drop-one-keep-one. Two different operations that both happen to be called "duplicate detection" — worth stating this explicitly here because it's exactly the kind of thing that looks right on paper and isn't.
- **Which import "wins" when an exact match merges** (i.e. which file's bytes are actually used for `analysis.json`, even though both are recorded in `imports[]`): use the same comparator the overlap path already has — prefer the more complete file (`most_rows`), not whichever the scan happened to enumerate first. Directory enumeration order isn't a real decision criterion and shouldn't produce a non-deterministic result.
- **Fingerprinting cost is a real, separate concern from `get_series` re-parsing** (§10, Q1 — that claim is about chart data, not this). Computing `source_key` means reading full file bytes for every log in every folder, on every scan. At real scale (hundreds of flights, possibly a network-mounted folder) that's not obviously cheap, and this spec shouldn't imply otherwise by omission. Mitigation: skip re-hashing a file whose path, size, and mtime are unchanged since it was last successfully fingerprinted — reuse the cached `source_key`. The residual risk (same size and mtime, different content) is negligible for this use case; the failure mode if it ever happened is stale results until the next real change, not data corruption. This is a should, not a nice-to-have, once workspaces are large enough for it to matter.
- **No chart-series cache added because of any of this.** Detailed charts still re-read the log on demand (Spec 01 Q1 in this spec stands).

### 5.8 Local realization (CLI, local server)

Extends §5.1's original three contexts (developer checkout, packaged install, Docker) — same resolution order, but the packaged/Docker default is now a *parent* of per-workspace folders, not one workspace folder:

| Context | Registry + workspaces live at | Set by |
|---|---|---|
| Developer checkout | `<repo-root>/data/workspaces/<name>/`, registry alongside | Implicit, only inside a git checkout, only when neither of the below applies |
| Packaged / local-server install | `~/SlingologyEIS/workspaces/<name>/`, registry at `~/SlingologyEIS/registry.json` | The installer creates this on first run |
| Docker | Whatever the person mounts | One mount for the registry + workspaces tree; log folders are separate mounts entirely, one per folder the pilot wants referenced |

`--logs DIR` (Spec 01 §7.1) still resolves the same way for a single-workspace CLI invocation, but a multi-workspace pilot needs the CLI to accept a workspace by **name**, not just by path, and to list/create workspaces without hand-editing the registry — `slingology-eis workspace list` / `workspace create <name>`. This is a Spec 01 §7.1 follow-up this spec flags but doesn't itself specify (out of scope here — see §10).

### 5.9 Browser realization

Two things instead of v0.3's one IndexedDB database: a small **registry** database (§6.7) listing workspaces, and **one IndexedDB database per workspace** — so a pilot can delete, export, or lose (eviction) one workspace without touching any other. Per-workspace store shape is otherwise unchanged from v0.3:

```
IndexedDB database: "slingology-eis-registry"
└── store "workspaces"    → keyed by workspace id, value = WorkspaceRegistryEntry

IndexedDB database: "slingology-eis-workspace-<id>"   (one per workspace)
├── store "manifest"      → one record
├── store "flights"       → keyed by flight_id, value = { analysis, sources }
├── store "fleet"         → one record { selection, analysis }
├── store "rules"         → one record { active, engine_overrides }
├── store "annotations"   → one record (small; keyed internally by flight_id)
└── store "settings"      → one record (workspace-level only, §6.6)
```

Folder access in the browser is realized via the File System Access API (Chrome — a permission grant persisted per folder, asked once) or, on Safari, by the pilot re-picking folders each session (§5.4's folder-reference model is otherwise identical; only how the browser retains permission differs).

Raw log bytes are still **never** written to IndexedDB, in either database — unchanged from v0.3.

### 5.10 Why the schema is identical everywhere

Both realizations store the **same typed objects** from Spec 01 (§8), for any given active workspace. A local-server response to `GET /workspaces/<id>/flights/<flight_id>` and a browser `db.flights.get(flight_id)` (against that workspace's own IndexedDB database) return byte-identical JSON. This is still what lets the CLI and the UI agree (D5), and what makes exporting a bundle from either host trivial.

## 6. Document shapes

### 6.1 `manifest.json` (or the `manifest` store record)

```ts
interface WorkspaceManifest {
  id: string;                    // matches the WorkspaceRegistryEntry.id that points at this workspace
  name: string;                  // pilot-chosen; also in the registry, kept in sync
  engine_model: string;          // matches WorkspaceRegistryEntry.aircraft.engine_model
  primary_tail_number?: string;  // informational (§5.6)
  log_folders: {
    folder_id: string;           // stable key — see below, this is what the browser's handle store is keyed by
    path: string;                // DISPLAY PATH ONLY, in both realizations — see the note after this block
    reachable: boolean;          // false after a scan can't find it — triggers "Locate folder"
    last_scanned_at?: string;
  }[];
  schema_version: string;       // this spec's version, independent semver (Spec 01 R4 precedent)
  created_at: string;           // ISO 8601
  updated_at: string;
  engine_version_seen: string[]; // every engine version that has written into this workspace
  flight_count: number;
  storage_backend: "filesystem" | "indexeddb";
}
```

**`log_folders[].path` fixed after review — it was wrong.** The original wording ("absolute path (local), or a stored File System Access handle reference (browser)") put two different *kinds* of thing in one string-typed field: a real path is JSON-serializable; a `FileSystemDirectoryHandle` is not — it needs structured-clone storage, which JSON isn't. That also meant §5.10's "byte-identical JSON in both realizations" claim was quietly false for this one field. Fixed properly rather than patched: `path` is now **always a plain display string** in both realizations (a real path locally; the folder's human-readable name in the browser, reconstructed for display, not used for actual access). The browser's actual `FileSystemDirectoryHandle` lives in a **separate, non-JSON, structured-clone IndexedDB record**, keyed by the new `folder_id`, outside the manifest document entirely — realization-specific access plumbing, not part of the portable data model. §5.10's claim now correctly means "the JSON documents are identical," not "literally everything the browser needs to hold is JSON."

Every write that touches the workspace updates `updated_at` and adds to `engine_version_seen` if new. A workspace opened by a newer engine than any version it has seen is a normal, expected case (upgrade); a workspace opened by an *older* engine than its newest seen version is a downgrade and produces a `WORKSPACE_NEWER_THAN_ENGINE` diagnostic (host-level, not part of the Spec 01 engine diagnostics catalog — this one belongs to the host, not the core).

### 6.2 `flights/<flight_id>/`

`analysis.json` is exactly a Spec 01 `FlightAnalysis`. `sources.json` records provenance the engine itself doesn't need to know about:

```ts
interface FlightSources {
  flight_id: string;
  imports: {
    source_key: string;         // = the fingerprint used for rematching on rescan (§5.7)
    log_folder_path: string;    // which of manifest.log_folders[] this came from
    relative_path: string;      // path within that folder — never an absolute-path-only reference
    filename: string;           // as provided at import time; not necessarily identifying
    imported_at: string;
    via: "sd_card" | "garmin_pilot" | "unknown";   // best-effort, from filename/path hints
  }[];
  duplicate_of?: string;         // set when ingest_log classified this as a duplicate (Spec 01 §6.2)
  different_tail_number?: string;  // §5.6 — this log's aircraft_ident differs from ones already in the workspace; purely informational, never a gate
  missing: boolean;              // §5.5 — true once every import's fingerprint goes unfound on a scan; persists until the pilot explicitly clears it. Not in the original sketch; added because §5.5 requires durable state and this is its natural home.
}
```

This is where "the same flight from two export paths" (Spec 01 Q1) becomes visible to the user: multiple `imports` entries under one `flight_id`. It's also where a rescan does its rematching: a log's `source_key` fingerprint is looked up first; a `relative_path` change under the same folder and fingerprint is a rename/move, not a new flight.

### 6.3 `fleet/`

`selection.json`:

```ts
interface FleetSelection {
  // Membership is NOT stored here — it's whatever flights/ currently contains,
  // which is itself whatever the workspace's log_folders currently contain
  // (§5.1, §5.4). Storing a separate "included" list would let it drift from
  // the folders, which is exactly the two-sources-of-truth problem §5.4 exists
  // to avoid. The only real selection this document stores is the exclusion.
  excluded: { flight_id: string; reason: string }[];  // the one in-app selection: pilot-set, e.g. a known-bad log — NOT auto-set by a different tail number (§5.6), which is informational only and never excludes anything
  baseline_config: BaselineConfig;   // Spec 01 §8.4 — membership, band_kind_by_metric
}
```

(v0.3 had an `included: string[]` here; dropped in v0.4 — see the comment above.)

`analysis.json` is a Spec 01 `FleetAnalysis`, with `models` (the `Model[]`, e.g. `takeoff_map`) included inline rather than as a separate file — the earlier layout's split between `baselines.json` and `models.json` (finding 2) is a historical accident of what script wrote it, not a meaningful boundary; both are outputs of the same `update_fleet` operation and are staleness-linked (Spec 01 §7).

### 6.4 `rules/`

`active.json` is the `RuleSet` (Spec 01 §8.5) currently governing insight evaluation — normally a copy of the repo's `insight_rules.json`, but the **rule playground** (Spec 01 §5) edits a working copy here without touching the repo file, so experimentation is per-workspace and disposable. `engine_overrides.json` is optional and mirrors the same idea for engine-profile limits, should a pilot ever need to note "my POH says X, not the shipped default" — out of scope to design fully now, listed for completeness.

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

### 6.6 `settings.json` — split app-level vs. workspace-level (new in v0.4)

v0.3 had one `WorkspaceSettings` document. With multiple workspaces, some of what it held is a property of the *pilot's install*, not of any one workspace — units shouldn't reset when switching from "N117ZS" to an experiment workspace. Split in two:

```ts
// Registry-adjacent, one per install — see §6.7 for where this lives
interface AppSettings {
  units: "imperial" | "metric";          // display only; engine always works in the units in Spec 01 §6.4
  last_active_workspace_id: string;      // which workspace reopens on launch
}

// One per workspace, unchanged in spirit from v0.3 minus what moved above
interface WorkspaceSettings {
  anonymize_by_default: boolean;
  active_engine_profile: string;         // e.g. "916iS"
  last_view?: { kind: string; flight_id?: string };  // convenience, not load-bearing
}
```

### 6.7 The registry document

Sits alongside `AppSettings`, one per install, listing every workspace so the switcher (Spec 03) and `slingology-eis workspace list` have something to read without opening each workspace in turn:

```ts
interface WorkspaceRegistry {
  version: string;
  workspaces: WorkspaceRegistryEntry[];   // §5.2
}
```

**Local realization:** `~/SlingologyEIS/registry.json` (or the equivalent developer-checkout / Docker path from §5.8), sibling to the `workspaces/` directory, not inside any one workspace. **Browser realization:** the `slingology-eis-registry` IndexedDB database (§5.9). Both are small — even a hundred workspaces is a trivial amount of JSON — so no special sizing concern beyond what §9 already covers for a single workspace.

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

The chart-ready series cache (`series/overview.json` in §5) is sketched but not fully specified — its downsampling parameters and cache-invalidation rule depend on Spec 03's chart design. The rule-playground's exact diff view is Spec 03. Multi-user or multi-device sync of one workspace is out of scope entirely — the bundle import/export *is* the sync mechanism, deliberately manual, consistent with "no service-side storage." Engine-profile override editing (`engine_overrides.json`) is named but not designed. The **Flights tab** (a log browser showing every flight in the active workspace, its status, and whether it feeds baselines) and the **workspace switcher**'s exact placement are Spec 03's job — this spec defines the data they read (§5, §6.3, §6.7), not their layout.

## 11. Migration and testing

This spec has no engine code to migrate — it's purely a host-side addition, built on top of Spec 01's Stage 3+ (contract) and Stage 4 (adapters). Suggested order:

1. Implement the local-filesystem realization (§5.8) first, since the CLI already has the closest precedent (`data/reports/`) and it's testable without a browser.
2. Implement `export_bundle`/`import_bundle` against the filesystem realization; test round-tripping the 23-flight fleet (pending more raw logs, per Spec 01 Q6, same limitation as before).
3. Implement the IndexedDB realization behind the same interface used by the browser adapter (Spec 04 §9.1), and confirm identical JSON shapes between the two.

## 12. Open questions

| # | Question | Leaning |
|---|---|---|
| Q1 | Should `series/` caching (§5, §10) be in scope for v1, or deferred until Spec 03 defines what the flight-view chart actually needs? | Defer; re-parsing on demand (Spec 01 `get_series`) is cheap per the spike numbers. |
| Q2 | `.eisbundle.json` vs `.eisbundle.zip` for full-workspace exports (§7.3) — worth the added complexity of two formats, or always zip? | Lean toward always zip once `full_workspace` export exists, single JSON only for `single_flight`/small `fleet_subset`; revisit once real fleet sizes are known. |
| Q3 | Should the workspace track its own storage usage and warn before hitting a browser quota, or rely on `navigator.storage.estimate()` at UI level? | UI-level (Spec 03), this spec just needs the data to stay small, which §9 argues it does. |
| Q4 | Does `engine_overrides.json` need a real design now, or can it stay a placeholder until a pilot actually asks for it? | Placeholder; no evidence yet that default engine profiles are wrong for any tested aircraft. |
| Q5 | Bundle import currently always merges (§7.4) — is there a case for a true "read-only, don't merge" viewer mode, e.g. for a community sample bundle someone doesn't want mixed into their own data? | **Sharpened by `workspaces-and-log-browser.md`'s Q3 (below), now folded in here:** with multiple workspaces, "don't merge into what I have" has a natural answer that didn't exist in v0.3 — open an imported bundle as a **new workspace** rather than merging into the active one. That's a real design change to §7.4's "always merges" rule, not just a UI mode; needs a decision, not just a leaning. |
| Q6 | Should the packaged installer's default (`~/SlingologyEIS/`) be a fixed, hardcoded name, or configurable at install time (e.g. macOS `~/Library/Application Support/SlingologyEIS/` vs. a plain home-directory folder a non-technical user can actually find in Finder)? | Lean toward a plain, visible home-directory folder — discoverability by a non-technical pilot matters more than platform convention here. Needs a decision before Spec 04 §9.5 packaging is implemented. |
| Q7 | ~~A log with no fingerprint match reappears "missing" indefinitely — does it drop out on its own, or stay listed until removed?~~ | **Resolved.** Stays listed as Missing, results and baseline contribution unchanged, until the pilot explicitly clears it — distinct from a whole unreachable folder, which is one event, not N missing logs. See §5.5. |
| Q8 | ~~When a scan finds a log for a different aircraft, warn-and-exclude, or offer to create/switch workspace?~~ | **Resolved, and reframed.** Multi-aircraft-same-engine-type is a real, intended use case (a flight school, a partnership), not an edge case to guard against — a different tail number is purely informational, never excludes anything. What actually can't mix is *engine model*, and that's enforced structurally (one `engine_model` per workspace, applied to everything in it) rather than detected per-log, because engine variant isn't present in the log data at all (verified against `limits.py`) — see §5.6, and the resulting gap, Q11. |
| Q9 | ~~Should a first-time pilot ever have to think about creating a workspace?~~ | **Resolved.** No — auto-create from the tail number in their first imported logs, plain fallback name if parsing fails, always renamable. |
| Q10 | ~~Does the CLI need `--workspace <name>` as well as a path, plus `workspace list`/`workspace create`?~~ | **Resolved: yes.** `--workspace` accepts either a registered name/id (looked up in the registry) or a literal path (unchanged behavior — a developer-checkout invocation that predates the registry keeps working). This is a real modification to the CLI Spec 01 §7.1 already shipped (Stage 4a, v0.11.0), not a paper change to an unbuilt spec — flag it to Code as required code, not just a doc update. |
| Q11 | No data signal is confirmed to exist for detecting a log's engine variant (912iS/914iS/915iS/916iS) automatically — `limits.py` shows engine selection is entirely user-configured, never read from the log. The by-construction design in §5.6 sidesteps this (mixing is structurally impossible, not detected-and-blocked), but nothing currently catches a pilot pointing the wrong log at the wrong workspace — it would just silently get the wrong limits. | New. Needs either a real data signal (unconfirmed — the project's dataset is 916iS-only, so this hasn't been checked against other variants) or a manual tail-number-to-engine-model mapping the pilot maintains. Not blocking Q8's resolution; worth its own follow-up. |
