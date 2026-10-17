# Spec 02 — Results Bundle & Workspace

**Project:** SlingologyEIS web platform
**Status:** v0.13 — import links only the export folder's own `logs/` (§7.4 step 3); v0.12 — §7 **workspace export and import** implemented (`workspace_export.py`, server ops, CLI `export-workspace` / `import-workspace`, Settings → App, the workspace switcher, Flights); v0.11 rewrote §7; v0.10: v0.7 implemented for the filesystem realization (local server + CLI: `workspace.py`, `exclusions.py`); the IndexedDB realization (§5.9) is not yet built; §5.8.1 (choosing the data location) implemented (`data_location.py`, server ops, CLI `data-location`)
**Suggested repo path:** `docs/specs/02-results-bundle-and-workspace.md`
**Builds on:** Spec 01 — Engine Contract v0.5 (incl. phase detection, used by §5.11's admission rules); Spec 04 — Runtime Adapters & Pyodide Spike v0.3 (decision: **GO**)
**Precedes:** Spec 03 (UI Information Architecture)
**Baseline reviewed:** repo `main` at commit `ed0ca33` (2026-07-07); the spike results (Spec 04, Appendix A); `workspaces-and-log-browser.md` design notes (2026-09-23); v0.7 checked against branch `webui` at commit `fee6577` (2026-10-01)
**Supersedes:** `docs/specs/08-flight-exclusions.md` (Workspace Flight Exclusions) and the never-committed companion spec "Ground Session Detection" — both folded into §5.11 and §6.8

**Revision history**

| Version | Change |
|---|---|
| 0.1 | Initial draft. |
| 0.2 | §5.1 rewritten: the local realization is no longer one `<repo-root>/data/` default, but three separate contexts (developer checkout, packaged/local-server install, Docker), because a non-technical path-2 user has no repo at all — just a folder of logs. Adds Spec 01 §7.1's new `--logs DIR` flag and its default-resolution order. New open question Q6. |
| 0.4 | **Multiple workspaces.** A user needs separate analysis contexts for different aircraft, or for experimenting with a subset of their own logs — v0.3 assumed exactly one workspace per install, which silently corrupts baselines the moment two aircraft's logs mix. Rewrites §5 around a workspace **registry** (many workspaces, one active) sitting above the existing per-workspace layout (which is otherwise unchanged in shape). Logs are now explicitly **referenced by folder, never copied**, matched by content fingerprint so renames/moves survive a rescan. `FleetSelection` (§6.3) splits automatic folder-derived membership from the one real in-app selection (baseline exclusion). `settings.json` (§6.6) splits into app-level and workspace-level. New §6.7 (workspace registry document), §5.5 (cross-aircraft and duplicate-folder safeguards). Four new open questions (Q7–Q10), one existing question (Q5) sharpened with a concrete proposal. Source: `workspaces-and-log-browser.md`. |
| 0.5 | Q7–Q10 resolved, each folded into the relevant section rather than left as a table entry: §5.6 splits cross-aircraft handling into a hard, by-construction engine-model constraint (workspace-level, not detected per-log) and a purely informational tail-number difference; §6.1's `aircraft` field restructured accordingly; §5.5 (new) covers the missing-log vs. unreachable-folder distinction; §5.8 notes the Spec 01 CLI change Q10 requires. New open item Q11: no data signal is confirmed to exist for detecting a log's engine variant automatically — the by-construction design sidesteps this rather than solves it. |
| 0.6 | Findings from the first real implementation pass. Two things fixed, not just documented: **`log_folders[].path` was genuinely wrong** — it mixed a JSON-serializable path string with a browser-only `FileSystemDirectoryHandle` in one field, quietly breaking §5.10's "identical JSON" claim; split into a plain display `path` (both realizations) plus a separate non-JSON handle store keyed by a new `folder_id`. **Exact-fingerprint duplicates must not reuse the overlap-duplicate drop-one-keep-one logic** — doing so silently discards a second export path instead of recording it in `imports[]`, defeating the reason that array exists; §5.7 now says so explicitly, plus which import wins when one is picked as primary (reuse the existing `most_rows` comparator). Two things added: `FlightSources.missing` (§6.2 — the field §5.5's persistence rule needed but the original sketch didn't have), and a fingerprint-caching rule (§5.7 — skip re-hashing a file whose path/size/mtime haven't changed, since reading every file's full bytes on every scan was asserted cheap without being addressed). |
| 0.7 | **Log admission and flight exclusions folded in** (new §5.11, §6.8), replacing the separate Workspace Flight Exclusions spec (filed as a second "Spec 08") and recording the never-committed Ground Session Detection spec it depended on. Written against the implementation, and corrects four things the former spec got wrong: (1) `exclusions.json` governs **admission** (does a log become a flight at all), not baseline contribution — baseline contribution is, and stays, `fleet/selection.json`'s `excluded` list (§6.3). The two are deliberately separate tiers keyed differently (filename vs. `flight_id`), not two copies of one list; §5.11 states why. (2) Parse failures are not `corrupt_log` entries — an unreadable file is never recorded, it surfaces as the Unreadable status (Spec 03 §5.1). (3) `include` never deletes an entry, including a `user_defined` one — it sets `user_override`. (4) `exclusions.json` lives at the workspace root, not `data/`. §5.1, §5.3, §5.9, §6.3 and §7.1 updated to reference the new sections. Status header corrected — it still read "no code written" well after the filesystem realization shipped. New open questions Q12–Q14. |
| 0.8 | **Mixed-aircraft workspaces made explicit (§5.6).** Tail number stays informational — never a gate, never an exclusion — but v0.7 called several same-engine aircraft in one workspace "a supported case" without noting that the per-aircraft layer (baselines, models, learned patterns, filters, change monitor — Spec 10 §1) then treats them as **one** aircraft. A workspace whose admitted flights carry more than one tail number now shows a persistent notice saying so and recommending one workspace per aircraft; the pilot can confirm that differing tail numbers are the same aircraft (a G3X ident typo, a re-registration), which clears it (`WorkspaceSettings.aircraft_aliases`, §6.6). OM limit checks are unaffected. Per-aircraft learning inside one workspace, with a fleet view comparing aircraft, becomes a future investigation (Q15). |
| 0.9 | §6.3 gains `fleet/shift_history.json` (Spec 12 §6) — a `ShiftEvent[]`, alongside `selection.json`, append-only except user deletion. Pinned references are not a new file; they're `selection.json`'s `BaselineConfig.pinned_references` (Spec 12 §5.7). |
| 0.10 | **Choosing the data location (§5.8.1, proposed).** The data root (registry, app settings and `workspaces/`, always together) can be moved. The resolution order is `SLINGOLOGY_EIS_HOME`, then a `location.json` in the per-user configuration folder, then the existing defaults; a configured location wins in every context, a developer checkout included. Changing it from Settings → App (Spec 14 v0.12) or the CLI either **moves** the data into an empty folder (copied, checked, then switched; the old copy is kept until the pilot deletes it) or **uses** a folder that already holds a registry; anything else is refused. A configured location that's missing opens on a notice, never on the defaults. Log folders are unaffected. Q6 resolved. §6.7 points at §5.8.1. |
| 0.11 | **Workspace export and import replace the results bundle (§7)** (2026-10-15). The primary use is a pilot sharing a workspace and its logs with someone else for custom analysis or debugging, so the recipient sees exactly what the sender sees. Getting something useful from an export *without* the logs is out of scope. An export carries the workspace's configuration and decisions, never analyses; the recipient's app re-analyses the logs (§7.1). Import always creates a new workspace (§7.4). A manifest of the sender's flights drives matching: missing flights are reported and their decisions stay dormant; extra logs are held out (§7.5). *Include logs* packs the logs into a zip the recipient unzips and opens as a folder (§7.3); *Anonymise logs* rewrites the copies' identity fields (§7.6). Engine versions: an older recipient is refused, a newer one warned (§7.7). Retired: the `ResultsBundle` schema, single-flight and subset scopes, the anonymise-by-default workspace setting (§6.6), read-only bundle preview (Spec 03 R2 / §5.8). Q2 and Q5 closed; Q12 gains the export's fingerprint keying. The spec keeps its title and file name. |
| 0.12 | **From the implementation of v0.11** (2026-10-15). Decided with the owner: (1) *Anonymise logs* also blanks the columns that place the aircraft — Nav Identifier, Nav Distance, Nav Bearing, Nav Course, Nav Cross Track Distance, COM 1/2 and NAV frequencies — besides latitude and longitude (§7.6); none feeds the analysis (ground speed does, and is kept). (2) **One pseudonym per aircraft**, not one for all: tails the sender grouped as one aircraft share it, and each distinct system ID within an aircraft keeps its own token, so duplicate detection (which compares tail and system ID) can't merge two aircraft's flights; a single-aircraft workspace gets `ANON-1` as before. Garmin Pilot's `flightstream_header`, which embeds the system ID, is rewritten too. (3) The engine reads `airport_hint` only from Garmin's `log_YYYYMMDD_HHMMSS_<airport>.csv` names, so a neutral `flight_001.csv` has none; no real log's result changes. Recorded as built: an anonymised export is refused while any flight's log can't be read (its `flight_id` can't be recomputed, and the old one is a low-entropy hash of the tail number); annotations on insights are re-keyed to the recomputed insight ids; admission entries whose file isn't in the workspace's folders are left out (the export says how many); in an imported workspace a log not in the manifest is recorded in the admission record as `not_in_sender` (*Include* is the ordinary override); the sender manifest lives in the imported workspace's `import.json` (local: not carried by a later export); device-specific settings (`last_view`, Trends detail-strip state) are not carried. The document classification is in `workspace_export.DOCUMENTS`; an export stops on any file it doesn't cover. Also decided: (4) the sender's own text is never rewritten, but when *Anonymise logs* is chosen the export dialog lists where the tail number or system ID appears in it (workspace name, notes, filter notes, exclusion reasons, pin labels, Journal notes and reasons), so the sender can change it first or export as it is (§7.6); (5) a later export of an imported workspace describes what that workspace holds — its manifest is built from its own flights, and flights still missing from the original sender are not carried on (§7.5); (6) a Journal exclusion entry is labelled with its log's current file name whenever the flight is in the workspace, so after an import or a rename it names this machine's file; a dormant one keeps the label it was given. |
| 0.13 | **Import links only the export's own logs** (owner decision, 2026-10-16). Linking other folders during import needed a typed path — a browser can't hand a picked folder's path to the page — and was judged too complex for the flow. §7.4 step 3: an unzipped export folder's `logs/` is linked automatically (also when the `.eisworkspace` inside that folder is chosen); without a `logs/` the workspace is created **empty**, listing the sender's flights, and logs are added later from Flights like any workspace's. The import flow has no folder step and no *Add another folder*; step 4's match result is shown only when logs were linked. A typed log-folder path elsewhere (Flights' *Add folder*) must name an existing folder. |

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

| | **Workspace** | **Workspace export** (v0.11, §7) |
|---|---|---|
| What | A live, growing store: every flight's analysis, the fleet baselines, models, insights, annotations, and settings | A single file: the workspace's configuration, decisions and flight manifest, optionally with its logs |
| Where it lives | Browser storage (OPFS/IndexedDB), or a folder on disk (CLI/local server) | Wherever the user saves or shares it |
| Lifetime | Grows as logs are imported; rebuilt from raw logs if lost | Point-in-time; immutable once exported |
| Who writes it | The host, after calling engine operations | The host, on export; importing it creates a new workspace |
| Purpose | Make "import once, browse forever" possible | Share a workspace with someone else so they see what the sender sees |

The export is a **read of the workspace**, not a separate schema: the same JSON documents, minus everything derivable from the logs, plus a manifest. This keeps them from drifting apart. (Until v0.10 this column described a *results bundle* of analyses; it is retired, §7.)

## 5. Multiple workspaces

A pilot can have several workspaces — one per aircraft, or an experiment holding a chosen subset of their own logs. Exactly **one is active** at a time; everything else in this spec (analysis, baselines, the CLI's `--workspace`, the browser store) acts on that one workspace, and the app remembers which one across restarts.

### 5.1 What a workspace is

A workspace is **a list of one or more log folders, plus everything derived from what's in them.** Not a copy of the logs — a reference. Membership isn't a stored list the app maintains; it's *whatever the referenced folders currently contain*, recomputed on every rescan. Subfolders are included automatically. There is no in-app filter for "which of my logs are in this workspace" — that's controlled entirely by how the pilot organizes their own files into folders, which is deliberate (§5.4 explains why this, not an in-app picker).

Two in-app controls narrow this, and they answer different questions (§5.11): **admission** — whether a log in a referenced folder becomes a flight at all (ground sessions, short hops and corrupt logs are skipped automatically, visibly, and overridably, recorded in `exclusions.json`, §6.8) — and **baseline exclusion** — which admitted flights feed baselines (§6.3), so a pilot can hold a known-bad flight out of the fleet statistics without removing it from the workspace or touching their file system. Neither is a subset picker: both are per-log exceptions to "everything in the folders," never a list of what's in.

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
├── exclusions.json               # log admission record — skipped logs and overrides, keyed by filename, see §5.11, §6.8
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
- **Tail number is purely informational, never a gate.** A log whose `aircraft_ident` differs from ones the workspace has already seen gets a small "different aircraft: N123AB" indicator and is included normally — no confirmation step, no exclusion.
- **But a mixed workspace is one aircraft as far as learning goes (v0.8).** Everything learned from history — baselines, trends, the takeoff-MAP model, the learned hottest cylinder, the change monitor — and every filter is computed over all of a workspace's admitted flights. With several aircraft in it, each flight is judged against a blend of aircraft rather than its own aircraft's history: one aircraft's normal can look abnormal, a real change on another can disappear into the difference between them, and a filter accepting one aircraft's characteristic silences it on all of them. Per-flight OM limit checks (the engine profile) are unaffected. So, rather than calling it a supported case:
  - **Notice.** When admitted flights carry more than one distinct `aircraft_ident` (after aliases, below), the workspace shows a persistent notice — on the Flights tab, and as a one-line note on every baseline-, trend- or model-driven card and chart (Spec 03): *"This workspace contains flights from N aircraft (N117ZS, N456CD…). Comparisons with your usual treat them as one aircraft. For per-aircraft results, use one workspace per aircraft."* Splitting is done with the existing tools — one workspace per aircraft's log folder (§5.1–5.4).
  - **Same-aircraft confirmation.** A differing tail number can be a G3X ident set wrong for a few flights, or a re-registration. The pilot can confirm that a group of tail numbers is one aircraft (`aircraft_aliases`, §6.6); the notice then counts them as one. The confirmation is the pilot's statement, recorded, and reversible.
  - **Nothing else changes:** no flight is excluded, no baseline is split, and the notice never blocks anything. It makes the blend visible; it doesn't fix it.
  - Per-aircraft learning within one workspace, plus a fleet view comparing aircraft of the same engine type — the route to engine-type insights rather than single-aircraft ones — is a future investigation (Q15).
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

### 5.8.1 Choosing the data location (v0.10)

The table above gives the **default** location. A pilot can choose another: an external drive, a synced folder, a folder they can find in Finder. What moves is the whole **data root**, one folder holding `registry.json`, the app-level `settings.json` (§6.6) and `workspaces/`. These three always stay together: the registry names workspaces by id and finds each at `workspaces/<id>/`. Log folders don't move. A workspace references them by path wherever the pilot keeps them (§5.1), so they must stay reachable from the new location as before.

**Resolution order** — the first that applies wins, in every context including a developer checkout:

1. The **`SLINGOLOGY_EIS_HOME`** environment variable: the data root's path. This is the way for Docker, scripts and tests. While it's set, the app shows the location as fixed by the environment and doesn't offer a change.
2. The **location file**: `location.json` in the per-user configuration folder — macOS `~/Library/Application Support/SlingologyEIS/`, Linux `$XDG_CONFIG_HOME/slingology-eis/` (default `~/.config/slingology-eis/`), Windows `%APPDATA%\SlingologyEIS\`. It is written only by a change of location (below) and holds `{ version: 1, data_root: <absolute path>, set_at: <ISO time> }`. It lives outside the data root because the root can't record its own whereabouts, and outside `~/SlingologyEIS/` because that folder's existence is itself a step in the default order.
3. **The defaults** in the table above, unchanged.

A location file whose `data_root` doesn't exist or can't be read (an unplugged drive) is **not** skipped silently in favour of the defaults: that would show a pilot an empty app, or someone else's data, without saying why. The app opens on a notice naming the missing folder, with *Try again* and *Choose another location*; the CLI exits with a usage error naming it.

**Changing the location** (local server: Settings → App, Spec 14 §5; CLI: `slingology-eis data-location set PATH`). The pilot gives a folder path, the same way Add folder takes one (Spec 03 §5.1). Before anything happens the app says what will happen, which depends on the folder:

| Target folder | What happens |
|---|---|
| Doesn't exist, or empty | **Move.** The current data root's contents are copied there, then checked: every file arrived, the registry loads, every workspace's manifest loads. Only then is the location file written and the app switched to it. The old copy is **left in place**; the app says where it is and that it can be deleted once the pilot is satisfied. It is never deleted automatically. |
| Holds a `registry.json` | **Use existing.** The app switches to it as it is, after showing how many workspaces it holds. The current data root is not touched or copied. This is how a pilot reconnects to data already on a drive, or goes back to an earlier location. |
| Not empty, no `registry.json` | Refused: the data won't be mixed into an unrelated folder. The message suggests a new, empty folder inside it. |
| The current root, inside it, or containing it; not writable | Refused, saying which. |

- A change is refused while a scan or analysis is running.
- A failed copy or check leaves everything as it was: no location file is written, the half-copied target is removed (it was empty before), and the error says what failed.
- **Use default location** removes the location file. It offers the same choice against the default folder: move there, or use what's already there.
- After a switch, the workspace that opens is the new root's `last_active_workspace_id` (§6.6). After a move that's the one that was open.
- The data location is install-level, not an analysis setting. It is not recorded in any workspace's Settings changelog (Spec 14 §5).
- `slingology-eis data-location` (no argument) prints the data root in use and which of the three steps chose it.
- **Browser realization:** not applicable. The browser's data lives in IndexedDB (§5.9), and the setting isn't shown there.

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
├── store "exclusions"    → one record, the §6.8 document
└── store "settings"      → one record (workspace-level only, §6.6)
```

Folder access in the browser is realized via the File System Access API (Chrome — a permission grant persisted per folder, asked once) or, on Safari, by the pilot re-picking folders each session (§5.4's folder-reference model is otherwise identical; only how the browser retains permission differs).

Raw log bytes are still **never** written to IndexedDB, in either database — unchanged from v0.3.

### 5.10 Why the schema is identical everywhere

Both realizations store the **same typed objects** from Spec 01 (§8), for any given active workspace. A local-server response to `GET /workspaces/<id>/flights/<flight_id>` and a browser `db.flights.get(flight_id)` (against that workspace's own IndexedDB database) return byte-identical JSON. This is still what lets the CLI and the UI agree (D5), and what makes exporting a bundle from either host trivial.

### 5.11 Log admission and flight exclusions (new in v0.7)

Folded in from the former Workspace Flight Exclusions spec (and its never-committed companion, Ground Session Detection), and written against what was built. The problem it solves: ground sessions used to be dropped silently at load time with no record, and the only way to keep any other unwanted log out was to move the file out of the folder.

#### 5.11.1 Two tiers, two documents — deliberately

| | **Tier 1 — Admission** | **Tier 2 — Baseline exclusion** |
|---|---|---|
| Question | Is this log a flight at all? | Should this flight feed fleet statistics? |
| Document | `exclusions.json` (§6.8) | `fleet/selection.json` → `excluded` (§6.3) |
| Keyed by | filename | `flight_id` |
| Set by | automatic rules at first sight of a file (§5.11.2), or the pilot | the pilot only — never automatic |
| Effect | the file never becomes a `flight_id`: no `flights/<id>/`, no analysis, no insights, absent from every view except the Skipped panel | the flight stays fully analyzed and visible, with its insights; it is only left out of `rebuild_fleet`'s input |
| Undo | set `user_override: true` — the entry itself is permanent (§5.11.4) | remove the entry |
| UI | Flights tab **Skipped** panel: preview the log, Include it | Flights table **In baselines** column toggle |

The former spec said `exclusions.json` drives *baseline contribution* and that excluded flights stay known to the workspace. That is not what was built, and the built behavior is the right one: a ground session has no airborne data to analyze, so admitting it as a flight and then hiding it from baselines would show the pilot an empty Flight view and a row of "unavailable" metrics for something that was never a flight. Conversely, folding Tier 2 into `exclusions.json` would mean throwing away a real flight's analysis and insights just to keep it out of the averages. "Single source of truth" holds **within** each tier; across tiers, two documents answering two questions is the correct shape, not a duplication to be merged.

A third, transient case belongs to neither tier: an **overlap duplicate** (§5.7) dropped during a scan is reported in that scan's result but persisted nowhere — it's re-derived from the folder contents on every scan, exactly like membership itself.

#### 5.11.2 Automatic admission rules

Applied in priority order by one shared classifier, `exclusions.classify_for_auto_exclusion()`, used by both ingestion paths — `scan_workspace()` (web UI / local server) and `load_directory()` (CLI / notebooks). Before v0.7's implementation, `scan_workspace()` had no filtering at all while `load_directory()` did; one classifier is what keeps the two from disagreeing again. The classifier runs on an already phase-annotated frame (Spec 01 phase detection), so it adds no second pass.

1. **`ground_session`** — no row lands in an airborne phase. `AIRBORNE_PHASES` = {`CLIMB`, `CRUISE`, `DESCENT`, `APPROACH`, `LANDING_ROLL`}. `TAKEOFF_ROLL` is **deliberately not** airborne: `TAXI → TAKEOFF_ROLL` fires on RPM alone (with a fallback back to `TAXI`), and only `TAKEOFF_ROLL → CLIMB`'s altitude-gain gate actually confirms liftoff; every other airborne phase is reachable only downstream of that gate. The case that proved it: `log_20260706_180003_KAWO.csv`, a ground run-up that pushed RPM past 4,500 with altitude flat at 158–168 ft, would have been admitted as a flight otherwise. This rule replaced the earlier proxy (RPM > 3,000 and IAS > 30 kt for ≥ 3 min); on the full local fleet at the time of the change (54 files) the two agreed exactly, so no golden fixtures moved.
2. **`short_flight`** — total airborne-phase time below `min_flight_duration_min` (toolkit `config.json`, default **10**; `0` disables). Conservative on purpose: it targets three-minute circuits, not a twelve-minute hop to a neighbouring field.
3. **`corrupt_log`** — a time gap of more than 5 minutes inside one session (an avionics restart or SD-card error). Mid-log power-cycle detection (BACKLOG B2) would also belong here and is not yet implemented. **Parse failures are not recorded here**: a file that fails to load is skipped by the scan and shown with the Unreadable status (Spec 03 §5.1), with no `exclusions.json` entry.

Without a workspace (`load_directory(workspace_dir=None)`), only rule 1 applies and nothing is persisted — the CLI still works against a bare log folder.

#### 5.11.3 Classified once, not on every scan

The rules run only when a file is **first seen**. An existing entry is authoritative and the file is not re-parsed to confirm it, and an admitted flight is not re-tested on later scans. This keeps routine Sync cost proportional to what's new, not to the size of the workspace. The consequence, stated plainly: changing `min_flight_duration_min`, or improving phase detection, does **not** retroactively affect flights already admitted or logs already skipped.

The one deliberate retroactive path is the explicit, pilot-triggered **reclassify** operation (`reclassify_existing_flights`, server op `reclassify_flights`), written for workspaces built before `scan_workspace()` had any filtering. It re-applies the rules to admitted flights; one that now classifies as excludable gets its `exclusions.json` entry written **first** and is then removed, so the next scan rediscovers the file, finds the entry, and doesn't re-admit it. Overrides are respected. It does not run the other way — a skipped log that would now pass stays skipped until overridden (Q14).

#### 5.11.4 Overrides and user entries

- **`user_override: true`** admits the log as though it had never been excluded. The entry stays, so the rule that fired (or the pilot's own earlier exclusion) remains on record with the override reason beside it. There is **no delete** — including for `user_defined` entries; the CLI's `include` sets the override rather than removing the entry (the former spec's CLI section said otherwise, contradicting its own permanence rule; the permanence rule won).
- An override takes effect in the **same** scan: the classifier re-reads the file from disk rather than the copy loaded at the scan's start.
- Writing an automatic entry is idempotent and never clobbers an existing entry, so an override survives every later rescan. A pilot's explicit exclusion of a file replaces any existing entry for it with a fresh `user_defined` one.
- Including a skipped log from the UI sets the override and immediately rescans, rebuilding the fleet if a flight appeared. A browser-uploaded file has no saved bytes to rescan (§5.9 — raw bytes are never stored), so for that case the override only clears the way for a re-upload of the same file to be admitted.

#### 5.11.5 Surfaces

| Surface | Tier 1 (admission) | Tier 2 (baselines) |
|---|---|---|
| CLI | `flights [--show-excluded]` (header counts from `exclusion_summary()`), `exclude FILENAME --reason …`, `include FILENAME [--reason …]` | — (see Q13) |
| Server ops | `list_exclusions` (`enrich` opt-in: re-locates and re-parses each skipped file for date/duration — real I/O, so only when the panel is open), `include_excluded_log`, `preview_excluded_log`, `get_excluded_log_series`, `reclassify_flights` | `exclude_flight`, `include_flight` |
| UI | Flights tab Skipped panel; a skipped log opens read-only in Flight view (`/skipped/:filename`) with nothing persisted, so a pilot can check the call was right before Including it | In baselines toggle (Spec 03 §5.1) |

`exclusions.json` records filenames, never paths, so the Skipped panel re-locates a skipped file by name across the workspace's currently reachable folders (`find_log_file_by_name`). A skipped file in an unreachable folder, or one that was browser-uploaded, still lists — just without its own date or duration.

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
  excluded: { flight_id: string; reason: string }[];  // Tier 2 of §5.11: the one in-app *baseline* selection, pilot-set only, e.g. a known-bad flight — NOT auto-set by anything: not a different tail number (§5.6, informational only), and not the admission rules, whose skipped logs never become flight_ids at all (§5.11, §6.8)
  baseline_config: BaselineConfig;   // Spec 01 §8.4 — membership, band_kind_by_metric
}
```

(v0.3 had an `included: string[]` here; dropped in v0.4 — see the comment above.)

`analysis.json` is a Spec 01 `FleetAnalysis`, with `models` (the `Model[]`, e.g. `takeoff_map`) included inline rather than as a separate file — the earlier layout's split between `baselines.json` and `models.json` (finding 2) is a historical accident of what script wrote it, not a meaningful boundary; both are outputs of the same `update_fleet` operation and are staleness-linked (Spec 01 §7).

`shift_history.json` (Spec 12 §6, new in v0.9): a bare `ShiftEvent[]` array, alongside `selection.json` — append-only except user deletion (`delete_shift_event`). Pinned references are not a separate file; they live in `selection.json`'s `BaselineConfig.pinned_references` (Spec 12 §5.7/§11.1), since a pin is part of the same baseline configuration as everything else there, not a distinct concern.

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
  // anonymize_by_default: removed in v0.11 — anonymisation is a per-export choice (§7.6)
  active_engine_profile: string;         // e.g. "916iS"
  aircraft_aliases?: string[][];         // v0.8, §5.6: groups of aircraft_ident values the pilot confirmed are one aircraft, e.g. [["N117ZS", "N117Z"]]
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

**Local realization:** `registry.json` at the data root — by default `~/SlingologyEIS/registry.json`, or the developer-checkout / Docker path from §5.8, or a location the pilot chose (§5.8.1) — sibling to the `workspaces/` directory, not inside any one workspace. **Browser realization:** the `slingology-eis-registry` IndexedDB database (§5.9). Both are small — even a hundred workspaces is a trivial amount of JSON — so no special sizing concern beyond what §9 already covers for a single workspace.

### 6.8 `exclusions.json` (new in v0.7)

Tier 1 of §5.11 — the admission record. One per workspace, at the workspace root alongside `manifest.json` (the former spec's `data/exclusions.json` predates multiple workspaces and is wrong). Absent file = no entries. Written atomically (temp file + rename).

```ts
interface ExclusionStore {
  version: 1;
  entries: {
    filename: string;            // log filename only — never a path (see Q12)
    source: "auto" | "user";
    category: "ground_session" | "short_flight" | "corrupt_log" | "user_defined";
    reason: string;              // human-readable, e.g. "below minimum flight duration (8 min < 10 min)"
    excluded_at: string;         // ISO 8601, when the entry was written
    user_override: boolean;      // true → admitted despite the entry (§5.11.4)
    override_reason?: string;
  }[];
}
```

`source: "auto"` pairs with the three rule categories, `source: "user"` with `user_defined`. `exclusion_summary()` reports a count for every category (zero included) plus a separate `overridden` tally — category counts include overridden entries, so the two are additive, not partitioned.

## 7. Workspace export and import (v0.11)

Replaces v0.3–v0.10's results bundle. **Purpose:** a pilot shares a workspace, usually with its logs, with someone else for custom analysis or debugging, and the recipient sees what the sender sees. The export is the workspace's *configuration and decisions*; the logs are the data; the recipient's app recomputes everything else. A recipient who has the export but not the logs gets an empty workspace that tells them which logs to ask for — getting something useful without the logs is deliberately out of scope.

### 7.1 What an export carries

Everything in the workspace that the logs and the app can't reproduce, and nothing they can:

| Carried | Source |
|---|---|
| Workspace settings: engine profile, aircraft aliases | `settings.json` (§6.6), minus device-specific fields |
| Reference & Models settings, reference exclusions, pins | `fleet/selection.json` (§6.3) |
| Reference history | `fleet/shift_history.json` and any other reference-change record (Spec 12) |
| Rules in effect, including disabled topics and rule edits | `rules/active.json` (§6.4) |
| Filters | `filters.json` (Spec 09 §9) |
| Journal entries and their records | `journal.json` (Spec 14 §6) |
| Annotations, including acknowledged insights | `annotations.json` (§6.5) |
| Log admission record, re-keyed by file fingerprint (§7.5) | `exclusions.json` (§6.8) |
| **Manifest of the sender's flights**: per flight, `flight_id`, every source's fingerprint (`source_key`) and file name, date, duration, airport hint | `flights/*/sources.json`, `analysis.json` headers |
| Provenance: app name and version, **engine version**, export time, workspace name, whether logs are included and anonymised | — |

Not carried: flight and fleet analyses, models and baselines (all recomputed from the logs); `log_folders` (paths mean nothing on another machine); app-level settings (units, last workspace, chart presets); caches. A workspace document not covered by this table is a defect in the export — the implementation lists every workspace document and classifies it as carried or derived, so new documents can't be silently dropped.

### 7.2 Export

From Settings → App: *Export workspace…* exports the **whole active workspace**. There is no subset scope: to share some flights, the sender makes an experiment workspace with just those logs (§5.4) and exports that.

- **Include logs** (default on). Without it the output is one small file, `<name>.eisworkspace`, and the recipient links their own copies of the logs (§7.4 step 3).
- **Anonymise logs** (default off; available only with *Include logs*, §7.6).
- **Privacy notice**, always shown: logs carry the tail number, system ID, dates, times and GPS track unless anonymised; annotation text, filter notes and the workspace name go as written.

Only admitted flights' logs are included — the logs in the manifest. Skipped logs, duplicates and logs outside the workspace's folders are not.

### 7.3 Format

- Without logs: `<name>.eisworkspace` — a zip holding `workspace.json` (provenance and manifest) and the carried documents under their workspace names.
- With logs: `<name>.zip` holding a folder `<name>/` with `<name>.eisworkspace` and `logs/`, the included logs under their original file names (or neutral names when anonymised, §7.6). The recipient **unzips it themselves** (Finder, Files, Explorer) and imports the folder. The app never extracts archives and never writes log files: logs always live in a folder the user owns and can see (a workspace references logs, never stores them — §5.1), and the flow is identical on every platform including Safari and iPad.

### 7.4 Import

*Import workspace…* (Settings → App, and the workspace switcher). Always creates a **new** workspace; an import never merges into, or changes, an existing one.

1. **Choose.** Pick an `.eisworkspace` file, or an unzipped export folder. A summary shows before anything is created: the sender's workspace name, engine model and engine version, flight count and date range, what it carries (e.g. "4 filters, 2 rule edits, 3 flights excluded from the reference, 12 notes"), and whether logs are included and anonymised. The engine check (§7.7) runs here.
2. **Name.** Default: the sender's workspace name + " (imported)". Renamable later.
3. **Link logs.** With an unzipped export folder (or the `.eisworkspace` inside one), its `logs/` is linked automatically. Otherwise the workspace is created **empty** — no folder step in the import (v0.13) — and shows an empty state: *Link your logs to see this workspace's analysis*, with the manifest's flight list; logs are added later from Flights (*Add logs…*).
4. **Match, without analysing.** When logs were linked, the folder is scanned against the manifest (§7.5) and the result shown: *38 of 40 flights found · 2 missing (listed) · 12 other logs held out*. The user continues.
5. **Analyse.** The ordinary Sync confirmation (Spec 03 §5.1) analyses the matched flights with the imported configuration and decisions, then opens Flights.

After import the workspace is an ordinary workspace: *Add logs…* and Sync work as usual, and the manifest's role continues through §7.5.

### 7.5 Matching the logs to the manifest

Flights match by `flight_id`, which is derived from the log's content (tail number, system ID, start time — Spec 01 §6.1), so file names and folder structure don't matter. Every decision in the export is keyed by `flight_id`, except the admission record, which the export re-keys from file name to `source_key` so a renamed file can't lose or gain a skip (Q12).

- **Missing flights** — in the manifest, no log found. Listed in the import result and kept in the Skipped panel as *In the sender's workspace — log not found* (date, airport, the sender's file name), so the recipient knows what to ask for. Decisions tied to them are kept, dormant. When a later Sync finds the log, the flight is admitted and its decisions apply.
- **Extra logs** — found, not in the manifest. **Held out by default**: they appear in the Skipped panel as *Not in the sender's workspace*, each with *Include*. This keeps the recipient's view identical to the sender's even when the folder holds other logs. Included extras behave as ordinary flights.
- The manifest is kept with the imported workspace for this purpose. It has no role in a workspace that wasn't imported. A later export of an imported workspace builds its manifest from the flights it holds; still-missing flights aren't carried on (v0.12).

### 7.6 Anonymised logs

*Anonymise logs* rewrites the **copies** written into the export; the sender's own logs and workspace are untouched.

- Tail number and system ID → a consistent pseudonym per aircraft (`ANON-1`, `ANON-2`, …; tails the sender grouped as one aircraft share one, v0.12), across all logs, including Garmin Pilot's `flightstream_header`.
- GPS latitude and longitude → blanked; so are the navigation and radio columns that place the aircraft — Nav Identifier, Nav Distance, Bearing, Course and Cross Track Distance, COM and NAV frequencies (v0.12).
- File names → neutral (`flight_001.csv`, …), removing Garmin's airport suffix; the manifest's airport hints are dropped.
- `flight_id`s are recomputed from the rewritten logs, and every carried document is remapped to them consistently. Aircraft aliases are replaced by the pseudonym.
- **Not changed:** dates and times, engine hours, and free text the sender wrote (annotations, filter notes, workspace name) — stated in the export dialog. Where that text names the aircraft (tail number or system ID), the dialog says so before export (v0.12).
- **Requirement:** an anonymised export re-analysed by the recipient produces the same results as the sender's workspace, apart from the identity fields. Anything in the analysis that depends on a rewritten field is a blocker to be reported, not worked around.

### 7.7 Engine versions

The export records the sender's engine version. At import (step 1):

- **Recipient's engine older** than the sender's: import refused — *This workspace needs engine X or later. Update the app to import it.* An older engine can't faithfully apply decisions it predates (e.g. a phase filter would be treated as invalid and its events shown unfiltered).
- **Newer:** import proceeds with a notice — *Exported with engine X; you have Y. Results reflect your newer engine and may differ.* Older documents are upgraded by the app's existing upgrade paths.
- **Same:** no message.

### 7.8 CLI

`export-bundle` is replaced by `export-workspace` (`--include-logs`, `--anonymise`) and `import-workspace` (`--name`, `--logs <folder>`), with the same behaviour as §7.2–7.7. The CLI reports the match result (§7.4 step 4) and requires confirmation before analysing, as the UI does.

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

The chart-ready series cache (`series/overview.json` in §5) is sketched but not fully specified — its downsampling parameters and cache-invalidation rule depend on Spec 03's chart design. The rule-playground's exact diff view is Spec 03. Multi-user or multi-device sync of one workspace is out of scope entirely — the bundle import/export *is* the sync mechanism, deliberately manual, consistent with "no service-side storage." Engine-profile override editing (`engine_overrides.json`) is named but not designed. Mid-log power-cycle detection for `corrupt_log` (§5.11.2) is BACKLOG B2, not this spec. The **Flights tab** (a log browser showing every flight in the active workspace, its status, and whether it feeds baselines) and the **workspace switcher**'s exact placement are Spec 03's job — this spec defines the data they read (§5, §6.3, §6.7), not their layout.

## 11. Migration and testing

This spec has no engine code to migrate — it's purely a host-side addition, built on top of Spec 01's Stage 3+ (contract) and Stage 4 (adapters). Suggested order:

1. Implement the local-filesystem realization (§5.8) first, since the CLI already has the closest precedent (`data/reports/`) and it's testable without a browser.
2. Implement workspace export and import (§7) against the filesystem realization; acceptance: round-trip a real workspace with logs (with and without anonymisation) and get identical insights, Journal and Trends.
3. Implement the IndexedDB realization behind the same interface used by the browser adapter (Spec 04 §9.1), and confirm identical JSON shapes between the two.

Status as of v0.7: step 1 is done (registry, scan, admission, baseline selection); steps 2 and 3 are not. §5.11's admission behavior is covered by `tests/unit/test_exclusions.py`, `test_loader.py`, `test_workspace.py` (including reclassify), `test_server.py` (Skipped list, preview) and `tests/cli/test_cli.py` (`flights` / `exclude` / `include`) — run against the project's logs, including the run-up case in §5.11.2.

## 12. Open questions

| # | Question | Leaning |
|---|---|---|
| Q1 | Should `series/` caching (§5, §10) be in scope for v1, or deferred until Spec 03 defines what the flight-view chart actually needs? | Defer; re-parsing on demand (Spec 01 `get_series`) is cheap per the spike numbers. |
| Q2 | ~~`.eisbundle.json` vs `.eisbundle.zip`~~ | **Closed (v0.11):** the results bundle is retired; workspace export is always a zip (§7.3). |
| Q3 | Should the workspace track its own storage usage and warn before hitting a browser quota, or rely on `navigator.storage.estimate()` at UI level? | UI-level (Spec 03), this spec just needs the data to stay small, which §9 argues it does. |
| Q4 | Does `engine_overrides.json` need a real design now, or can it stay a placeholder until a pilot actually asks for it? | Placeholder; no evidence yet that default engine profiles are wrong for any tested aircraft. |
| Q5 | ~~Read-only, don't-merge viewer mode for bundles?~~ | **Closed (v0.11):** import always creates a new workspace and never merges (§7.4); read-only preview is retired with the bundle. |
| Q6 | Should the packaged installer's default (`~/SlingologyEIS/`) be a fixed, hardcoded name, or configurable at install time (e.g. macOS `~/Library/Application Support/SlingologyEIS/` vs. a plain home-directory folder a non-technical user can actually find in Finder)? | **Resolved (v0.10):** the default stays a plain, visible home-directory folder, `~/SlingologyEIS/` — discoverability by a non-technical pilot matters more than platform convention — and the pilot can move it anywhere afterwards (§5.8.1). Only the small location file uses the platform's configuration folder. |
| Q7 | ~~A log with no fingerprint match reappears "missing" indefinitely — does it drop out on its own, or stay listed until removed?~~ | **Resolved.** Stays listed as Missing, results and baseline contribution unchanged, until the pilot explicitly clears it — distinct from a whole unreachable folder, which is one event, not N missing logs. See §5.5. |
| Q8 | ~~When a scan finds a log for a different aircraft, warn-and-exclude, or offer to create/switch workspace?~~ | **Resolved, and reframed.** Multi-aircraft-same-engine-type is a real, intended use case (a flight school, a partnership), not an edge case to guard against — a different tail number is purely informational, never excludes anything. What actually can't mix is *engine model*, and that's enforced structurally (one `engine_model` per workspace, applied to everything in it) rather than detected per-log, because engine variant isn't present in the log data at all (verified against `limits.py`) — see §5.6, and the resulting gap, Q11. |
| Q9 | ~~Should a first-time pilot ever have to think about creating a workspace?~~ | **Resolved.** No — auto-create from the tail number in their first imported logs, plain fallback name if parsing fails, always renamable. |
| Q10 | ~~Does the CLI need `--workspace <name>` as well as a path, plus `workspace list`/`workspace create`?~~ | **Resolved: yes.** `--workspace` accepts either a registered name/id (looked up in the registry) or a literal path (unchanged behavior — a developer-checkout invocation that predates the registry keeps working). This is a real modification to the CLI Spec 01 §7.1 already shipped (Stage 4a, v0.11.0), not a paper change to an unbuilt spec — flag it to Code as required code, not just a doc update. |
| Q11 | No data signal is confirmed to exist for detecting a log's engine variant (912iS/914iS/915iS/916iS) automatically — `limits.py` shows engine selection is entirely user-configured, never read from the log. The by-construction design in §5.6 sidesteps this (mixing is structurally impossible, not detected-and-blocked), but nothing currently catches a pilot pointing the wrong log at the wrong workspace — it would just silently get the wrong limits. | New. Needs either a real data signal (unconfirmed — the project's dataset is 916iS-only, so this hasn't been checked against other variants) or a manual tail-number-to-engine-model mapping the pilot maintains. Not blocking Q8's resolution; worth its own follow-up. |
| Q12 | `exclusions.json` is keyed by **filename**, while everything else in the workspace matches logs by content fingerprint (§5.7). Renaming a skipped file makes it look new — it gets classified again (usually re-skipped, but a user override or `user_defined` entry is lost to the renamed copy); and two different files with the same name in two referenced folders share one entry. | New. Leaning: add the file's `source_key` to each entry and match on it first, keeping `filename` for display and for the browser-upload case. Low urgency — G3X names embed date, time and airport, so collisions are rare in practice — but it's the one place the workspace breaks its own matching rule. **v0.11:** workspace export re-keys the admission record by `source_key` (§7.5); whether the live `exclusions.json` should do the same stays open here. |
| Q13 | The CLI's `exclude`/`include` act on **Tier 1** (admission), while the UI's exclude toggle acts on **Tier 2** (baselines). The same verb means different things on two surfaces, and the CLI's Tier 1 entry behaves differently by path: the CLI's own fleet commands honor it on their next run (`load_directory()` reads `exclusions.json` every time), but in a folder-scanned workspace (the web UI's path) a file that's *already* a flight stays one — rules only run on newly seen files (§5.11.3). | New, needs a decision. Options: (a) CLI `exclude` given an already-admitted file targets Tier 2, and only a not-yet-admitted file gets a Tier 1 `user_defined` entry; (b) rename the CLI's Tier 1 verbs `skip`/`unskip` and add `exclude`/`include` for Tier 2, matching the UI. Leaning (b): explicit beats overloaded. |
| Q14 | `min_flight_duration_min` lives in the toolkit's `config.json` — install-wide — although per-workspace settings exist (§6.6) and an experiment workspace is exactly where a pilot might want a different threshold. And because rules apply once (§5.11.3), changing it affects only new files; `reclassify` only tightens (removes newly-short flights), never loosens (re-admits newly-long-enough skipped logs). | New. Leaning: move it into `WorkspaceSettings`, and make reclassify symmetric for `auto` entries (re-admit a skipped log whose rule no longer fires, leaving `user_defined` entries and overrides untouched). |
| Q15 | **Fleet workspaces (future investigation).** Should one workspace hold several aircraft of the same engine type with the per-aircraft layer kept **per aircraft** — baselines, models, learned patterns, filters and change monitor keyed by aircraft — plus a fleet view comparing them side by side (per-aircraft baselines, per-limit saturation by aircraft)? That is where engine-type insights would come from: a limit saturating the same way on every aircraft points to the profile (Spec 10 D6 cause 1), on one aircraft to that installation (cause 3a). | New in v0.8; deferred, by decision, until after the current Spec 10 stage. Until then, the mixed-aircraft notice (§5.6) is the interim. Touches baselines, models, filters, Trends and the change monitor, so it needs its own spec; it is also the natural path for multi-aircraft evidence into Spec 10's register. |
