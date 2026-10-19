# Spec 04 — Runtime Adapters & Pyodide Feasibility Spike

**Project:** SlingologyEIS web platform
**Status:** v0.5 — §9.1 aligned with step 1 as built (two progress streams, uploads registry); v0.4 — Part B **normative**: one host, three transports; decisions D1–D7 (§9.0) and the plan (§10). Part A complete, decision **GO** (v0.3)
**Suggested repo path:** `docs/specs/04-runtime-adapters-and-pyodide-spike.md`
**Builds on:** Spec 01 — Engine Contract v0.23 (D2, P3, §5, §7, §7.1, §8.7, Q8); Spec 02 — Results Bundle & Workspace v0.17 (§5.8, §5.9, §7); Spec 03 v0.23 and Spec 14 v0.15 for the mode-specific UI
**Precedes:** Spec 02 (Results Bundle & Workspace), Spec 03 (UI Information Architecture)
**Baseline reviewed:** repo `main` at commit `ed0ca33` (2026-07-07), v0.10.0 tag; project logs. v0.4 against `main` at `761c8b7` (2026-10-17, 1.0.0): `server.py` 90 operations, `workspace.py`, `engineClient.ts` seam

**Revision history**

| Version | Change |
|---|---|
| 0.1 | Initial draft. |
| 0.2 | Test matrix narrowed to the maintainer's actual environments: macOS Chrome, macOS Safari, iPad (§4.2). Added a support policy for untested platforms, Safari storage note (§2.8), and a way for contributors to submit their own results. |
| 0.3 | Part A run against the **real** engine (not the synthetic proxy): a harness (`spike/`) ran `load_log` → `detect_phases` → `build_flight_metrics` on the KACV log inside Pyodide, on macOS Chrome, macOS Safari, and iPad Safari, diffed against a native golden. Result: **GO**, exact parity on all three, comfortably inside every target threshold. Appendix A/B filled in (§13). S5–S7 and stress/batch (W3/W4) remain untested; noted as follow-ups, not blockers. |
| 0.4 | **Part B made normative** (2026-10-17). Written against 1.0.0, where the host has 90 operations and a 2,500-line workspace layer, so the September sketch (analysis in Python, workspace re-implemented in TypeScript over IndexedDB) is withdrawn. Decisions D1–D7 (§9.0): the **whole host runs in the browser** under Pyodide against an **OPFS**-backed filesystem; one transport-neutral host module behind HTTP, the worker and the CLI; logs enter the browser by page-side enumeration with Python classifying; a static `runtime.json` plus `get_capabilities` select the mode; progress is a host callback; packaging pins and self-hosts Pyodide and ships the engine as a CI-built wheel that also carries the built UI (resolves Spec 01 Q8, BACKLOG P3). Local-server mode stays fully supported — two hosts of one engine, neither a fallback. Desktop browsers first; the iPad's persistence probe is deferred. §9 rewritten, §10 is the six-step plan, §11–§12 updated. Part A and the appendices unchanged. |
| 0.5 | **Step 1 implemented** (2026-10-19, branch `pyodide`): `slingology_eis/host.py` holds the operations, `dispatch`, `reply`, the context and one error table; `server.py` is HTTP only; `get_capabilities` live. Two details corrected to match what was built: progress has **two streams** (scan, data move), so the callback is `emit_progress(stream, update)`; files the page supplies (import, log upload) enter through an **uploads registry** the transport fills and the host reads by id — the inbound twin of `deliver_file`. The dispatcher refuses requests during a data move only; a scan blocks just the data-location change (as before). §10 step 1 marked done. |

---

## 1. Purpose and structure

The chosen deployment path 1b (Spec 01, D2) depends on one unproven assumption: **the existing Python analysis runs acceptably inside a browser via Pyodide, including on an iPad.** Specs 02 and 03 (browser storage, UI behaviour) depend on the answer, so we test the assumption before building on it.

This spec has two parts:

- **Part A — Feasibility spike (normative).** A time-boxed experiment: what to run, what to measure, pass/fail thresholds, and how the result decides the architecture.
- **Part B — Runtime hosts (normative from v0.4).** How one host module serves three transports (browser worker, local server, CLI), how logs and files cross the browser boundary, how the browser persists the workspace, how the UI knows which host it has, one conformance suite, packaging, and the plan.

**Out of scope:** the harness code itself (written when you ask for it), the UI, the results bundle format, any engine changes.

## 2. What we already know

Findings from the code and log review that shape the spike:

1. **Only numpy and pandas are needed.** Nothing in `slingology_eis/` or `notebooks/` imports SciPy, Matplotlib, or Jupyter; SciPy appears only in `requirements.txt`. That is the heaviest Pyodide package we do *not* have to download. The spike must confirm this by loading only numpy and pandas. (Housekeeping, separate from this spec: `requirements.txt` overstates the core dependencies.)
2. **The unmodified library can run in Pyodide's virtual filesystem.** The code opens logs by path and resolves `engines/` relative to `__file__`. That is awkward for a clean browser design (Spec 01, finding 2), but it works if the repo files are mounted into the virtual filesystem. So the spike does **not** depend on the Stage 1 refactor, and its result tells us how urgent Stage 1 is.
3. **The scripts run headless.** Script 01 runs unmodified on the provided log in about 2 s natively (peak ≈ 129 MB RSS, 86 output lines). Scripts 02–04 read and write under a `data/` layout relative to their own location.
4. **Native reference figures** (my sandbox, CPython, pandas 3.0.2 / numpy 2.4.4, log `log_20260423_200615_KACV.csv`, 8.3 MB, 16,196 rows): import 0.44 s, `load_log` 0.41 s, `build_flight_metrics` (phases and all per-flight modules) 1.45 s, resident DataFrame ≈ 46.5 MB at 129 columns. Your machine will differ, so the spike records its own native reference (§6.1).
5. **Package versions look close to the native environment.** At the time of writing, the Pyodide package channel lists pandas 3.0.2 and numpy 2.4.3 (May 2026), against 3.0.2 and 2.4.4 in the environment where the engine reproduced `fleet_metrics.csv` exactly. Numerical parity risk is therefore low but not zero, and `requirements.txt` says `pandas>=2.0`, a range I have not exercised.
6. **iOS is the known weak point.** Pyodide 0.27.1 and later were reported broken on iOS/Safari (crashes on load, GitHub issue #5428), and a later release note describes a wasm-gc feature-detection workaround for iOS. Safari on iOS also terminates tabs for memory much more aggressively than desktop browsers, with limits Apple does not publish. So iPad results depend on exact Pyodide and iPadOS versions and must be measured, not assumed.
7. **GitHub Pages cannot set custom response headers** (as far as I know; verify). That rules out cross-origin isolation (COOP/COEP), and therefore `SharedArrayBuffer`, threads, and the precise browser memory API. The design must not depend on them.
8. **Safari may clear a site's stored data** after a period without visits, unless the site is installed to the Home Screen (as far as I know: WebKit's tracking-prevention storage limits; verify). The spike cannot test the time-based behaviour, so it records what is available and Spec 02 treats browser storage as evictable, with the exportable results bundle as the source of truth.

## 3. Questions the spike must answer

| # | Question | Why it matters |
|---|---|---|
| S1 | **Correctness:** does the engine produce identical results in Pyodide? | Without parity there is nothing to build on. |
| S2 | **Speed:** how long do cold start, warm start, and analysis take? | Determines whether a non-expert user accepts the experience. |
| S3 | **Memory:** what is the peak and steady-state footprint, and does it grow across flights? | Decides whether iPad is viable and whether "one flight resident at a time" (Spec 01, principle 8) is enough. |
| S4 | **iPad:** does it load and run at all, on which iPadOS/Safari versions? | Decides the fate of P3 (iPad as a working platform vs. a viewer). |
| S5 | **Offline packaging:** can the whole runtime be self-hosted and cached so the app works with no network? | Pilots use this at airfields; also required for the "logs never leave the device" claim to be verifiable. |
| S6 | **Worker architecture:** does the UI stay responsive while analysis runs off the main thread? | Required design assumption (Spec 01, D2). |
| S7 | **Persistence primitives:** what storage is available, and how much, on each browser? | Input to Spec 02. Long-term eviction cannot be tested in a spike. |
| S8 | **Failure behaviour:** when memory runs out, does it fail with a catchable error or crash the tab? | Determines the guard rails the UI needs. |

## 4. Part A — Spike design

### 4.1 Approach

Run the **unmodified** library and scripts from a pinned commit of `main`, mounted into Pyodide's virtual filesystem, inside a **Web Worker**, on a plain static page with no framework. A plain page isolates runtime risk from UI-stack risk; the React/Vite shell is a separate concern.

### 4.2 Test matrix

| Priority | Environment | Notes |
|---|---|---|
| Reference | Native CPython on your Mac | Golden outputs and native timings. |
| P0 | macOS Chrome | Primary development and user platform. |
| P0 | iPad Safari | Record iPadOS version, device model, RAM. |
| P1 | macOS Safari | Different storage and memory behaviour from Chrome; also the closest desktop proxy for iOS WebKit behaviour. |
| P1 | iPad Safari, installed to Home Screen (PWA mode) | Different storage and memory behaviour is possible. |

These are the environments you can test yourself, so they define the **supported** set. Windows, Linux, Firefox, Edge, Android, and iPhone are not tested by the maintainer.

**Support policy.** The project documents support only for tested environments and lists the rest as *community-verified*: they should work on current browsers, but nobody has confirmed it. The harness is built so anyone can run it and submit the results JSON (which contains timings and parity verdicts, never log data). A table in the docs records who ran what, on which versions. This suits the community goals in Spec 01 (D5) and keeps the maintainer's testing burden fixed.

**Pyodide versions:** the current stable release (the 314.x line at the time of writing) and one earlier pinned release, because of the iOS history in §2.6. Record the exact Pyodide, numpy, and pandas versions loaded in every run.

### 4.3 Workloads

| Id | Workload | Purpose |
|---|---|---|
| W0 | Load Pyodide, load numpy and pandas only. No engine. | Separates runtime start-up cost from our code. |
| W1 | `log_20260423_200615_KACV.csv` (4.5-hour flight, 8.3 MB): `load_log` → `detect_phases` → `build_flight_metrics`. | Core single-flight case, longest realistic input. |
| W2 | Scripts 01 and 02 run unmodified with `runpy` against the same log; stdout captured. | Exercises report generation and ECU code paths. Scripts 03–04 join once a baseline set exists (needs the fleet's raw logs). |
| W3 | Stress: the W1 log repeated end to end with shifted timestamps to 2× and 4× length (≈ 32k and 65k rows). | Headroom, and finds the failure point (S8). |
| W4 | Batch: every raw log you can provide, processed sequentially, one flight resident at a time. | Memory growth, throughput, leak check (S3). Ideally the 23 real flights plus the ground sessions. |
| W5 | Fleet step: the fleet baseline and trend functions in `fleet.py` on `fleet_metrics.csv` (7 kB, derived). | Confirms the small fleet-level path. |

W1 and W3 use the single raw log currently in the project. W2 (scripts 03–04) and W4 need more raw logs; until then they are marked **blocked, not failed**.

### 4.4 Measurements

Every run records, per environment and workload, into one results JSON (§5):

| Group | Measurement | How |
|---|---|---|
| Environment | User agent, OS/iPadOS version, device model, hardware concurrency, Pyodide/numpy/pandas versions, pinned repo commit | Captured by the harness. |
| Download | Bytes transferred on a cold start, per resource | Browser resource-timing entries. |
| Start-up | `t_runtime` (Pyodide ready), `t_packages` (numpy + pandas loaded), `t_import` (engine importable), `t_ready` total | Timestamps inside the worker. Measured **cold** (empty cache), **warm** (cached), and **offline** (network disabled). |
| Analysis | Per-step time (load, phases, metrics), total, first vs. second run | Timestamps inside the worker; run each workload three times. |
| Memory | Size of WASM linear memory after each step; Python-side peak via `tracemalloc`; on Chrome the legacy heap counter where available | Harness reads the module's heap size. The precise browser memory API needs cross-origin isolation (§2.7), so do not rely on it. |
| Leak check | Heap size after flight N vs. after flight 1, after a forced garbage collection | W4. |
| Responsiveness | Longest gap between animation frames on the main thread while a workload runs in the worker | `requestAnimationFrame` sampler; compare against a deliberately main-thread run. |
| Parity | Field-by-field comparison with native goldens (§6.1) | Automated diff. |
| Persistence | OPFS and IndexedDB availability, a write/read round-trip of a 50 MB blob, storage estimate, persistence request result | S7. |
| Failure | For W3 stress steps: outcome ∈ {ok, catchable error, tab reload/crash} | **Crash marker**: the harness writes a "run started" flag to session storage before each step and clears it on completion; if the page reloads and finds a flag, the previous step crashed the tab. iOS gives no crash event, so this is the only reliable signal. |

### 4.5 Parity definition

Native and Pyodide results are compared against golden outputs produced by the native reference runner on the **same** commit:

- **Per-flight metrics** (all 35 fields the current code emits, including the four the provided `fleet_metrics.csv` predates): integers, booleans, and strings must match exactly; floats must match within `|Δ| ≤ 1e-9 · max(1, |x|)`. Nulls must match.
- **Phase sequence** (labels and transition seconds) must match exactly.
- **ECU runs** for the provided log (2 `POWERUP`, 2 `LANE_CHECK`, 1 `SHUTDOWN`) must match exactly.
- **Text reports** from scripts 01 and 02 should be byte-identical. Differences are classified as *numeric-format*, *ordering*, or *logic*; only *logic* differences fail parity.

The known phase-detection defect (Spec 01, finding 9) is part of the golden, not a parity failure: the spike verifies that Pyodide reproduces today's behaviour, defects included.

## 5. Results format

A single JSON document per run plus one human-readable summary, both committed under `spike/results/` and `spike/RESULTS.md`. Informal shape:

```jsonc
{
  "run_id": "…", "date": "…",
  "env":    { "ua": "…", "os": "…", "device": "…", "cores": 0, "pyodide": "…", "numpy": "…", "pandas": "…", "commit": "…" },
  "cold":   { "bytes": 0, "t_runtime_s": 0, "t_packages_s": 0, "t_import_s": 0, "t_ready_s": 0 },
  "warm":   { "t_ready_s": 0 },
  "offline":{ "ok": true, "t_ready_s": 0 },
  "workloads": { "W1": { "runs": [ { "steps_s": { "load": 0, "phases": 0, "metrics": 0 }, "total_s": 0,
                                      "heap_mb": 0, "py_peak_mb": 0 } ],
                          "parity": { "metrics": "pass|fail", "phases": "pass|fail", "diffs": [] } } },
  "responsiveness": { "max_frame_gap_ms": 0, "main_thread_max_frame_gap_ms": 0 },
  "persistence": { "opfs": true, "indexeddb": true, "estimate_mb": 0, "persist_granted": false, "blob_roundtrip": true },
  "stress": [ { "rows": 32392, "outcome": "ok|error|crash", "heap_mb": 0 } ],
  "notes": ""
}
```

## 6. Procedure

### 6.1 Native reference (once)

Run the native reference runner on your machine at the pinned commit: it writes golden per-flight metrics, phases, ECU runs, and report text for the provided log, and records native timings and peak memory in the same JSON shape. These goldens double as the seed of the Stage 0 characterization tests (Spec 01, §11).

### 6.2 macOS Chrome (P0), then macOS Safari (P1)

1. W0, then W1, cold: clear site data, load, run, record.
2. Reload for a warm run; then disconnect the network and reload for the offline run.
3. W2, W5, then W3 stress steps in increasing size until a failure or the largest step passes.
4. W4 when raw logs are available.
5. Persistence probes (S7).
6. Repeat steps 1–5 on macOS Safari.

### 6.3 iPad Safari (P0), then Home Screen mode (P1)

Repeat the desktop sequence in Safari, then in Home Screen mode. Run stress steps in **increasing** order and rely on the crash marker. Note whether closing other apps changes the outcome. Do the same on the earlier pinned Pyodide version if the current one fails.

### 6.4 Reporting

Fill `spike/RESULTS.md` (template in Appendix A) and attach the JSON files. Time budget, as an estimate: about half a day for the desktop runs, an hour or two for the iPad session, plus the one-off harness build.

## 7. Pass/fail criteria

In the table, "Desktop" means macOS Chrome (P0) and macOS Safari (P1). The numbers below are **proposals**, chosen as plausible user-tolerance thresholds, not measured facts. Adjust them once the first run gives real figures; the *structure* (target vs. limit) is what matters.

| Criterion | Target | Limit (fail beyond) | Scope |
|---|---|---|---|
| Parity (§4.5) | all pass | any *logic* difference | Desktop and iPad |
| Cold start to ready (first visit) | ≤ 30 s | 60 s | Desktop; iPad limit 90 s |
| Warm start to ready | ≤ 8 s | 15 s | Desktop and iPad |
| Offline start after caching | works | must work | Desktop (P0), iPad (P1) |
| W1 single-flight analysis | ≤ 10 s | 20 s | Desktop; iPad limit 40 s |
| Batch of 23 real flights (W4) | ≤ 4 min | 8 min | Desktop |
| Cold download size | ≤ 60 MB | 120 MB | Informational unless exceeded |
| WASM heap, W1 | ≤ 500 MB | 1.5 GB | Desktop |
| iPad W1 and W4 | complete, no crash | any crash | iPad |
| Heap growth over a batch | ≤ 25% vs. flight 1 | > 50% | W4 |
| Main-thread frame gap during a worker run | ≤ 50 ms | 100 ms | Desktop and iPad |
| Stress (W3, desktop) | passes 2×; fails gracefully beyond | tab crash without catchable error | Desktop |

### 7.1 Decision table

| Outcome | Condition | Consequence |
|---|---|---|
| **GO** | All P0 desktop criteria and iPad W1 pass | Path 1b proceeds as designed; iPad can run full analysis. Adopt Part B. |
| **GO, desktop only** | Desktop passes; iPad fails on version, memory, or crash | Path 1b for desktop. iPad becomes a results-bundle viewer only (Spec 01, P3), which is a supported design already. Record the minimum iPadOS/Safari versions that work. |
| **CONDITIONAL** | Parity or performance failures trace to specific steps | Fix in place (for example replace an expensive pandas operation with a numpy one, or reduce columns held in memory), then re-run the failing workloads. Time-box to one iteration before choosing a fallback. |
| **NO-GO** | Desktop parity fails, or memory/time infeasible after one iteration | Revisit D2. Fallbacks in order: (1) stateless server compute with explicit user consent and a clear privacy statement (path 1a), (2) a packaged local app. Spec 02/03 continue unchanged because the engine contract is transport-independent. |

## 8. Harness requirements (for when code is requested)

- One static page under `spike/` in the repo, not part of the shipped app; archived or deleted after the decision.
- Loads a **self-hosted** copy of Pyodide (a CDN variant is optional, for comparison) so offline and network-transfer measurements are meaningful.
- Runs everything in a Web Worker. Messages use the Spec 01 envelope shape where practical, so the harness doubles as a prototype of the browser adapter (§9.1).
- Mounts the pinned commit's `slingology_eis/`, `engines/`, `config.json`, `insight_rules.json`, and `notebooks/` from a single archive into the virtual filesystem. The commit hash is embedded and reported.
- File picker and drag-and-drop for logs, one button per workload, "run all", and a downloadable results JSON. No log ever leaves the page: the results JSON contains timings and parity verdicts only, and the harness shows the list of network requests it made so the claim is checkable.
- Implements the crash marker, the frame-gap sampler, and the persistence probes.
- A separate native reference runner script produces the goldens and native timings (§6.1).

## 9. Part B — Runtime hosts (normative from v0.4)

Part A answered "can the engine run in a browser?" (yes). Part B answers "how does the one app run in two places?" It was written as a sketch in v0.1; with the 1.0.0 host at 90 operations and a 2,500-line workspace layer, the sketch's assumptions no longer hold and this revision makes it normative.

### 9.0 Decisions (2026-10-17)

| # | Decision | Chosen | Rejected | Why |
|---|---|---|---|---|
| D1 | How much Python runs in the browser | **The whole host.** Every operation, the workspace layer, registry, filters, journal, export and import run unchanged inside Pyodide against a filesystem the browser persists. | Analysis in Python, workspace re-implemented in TypeScript over IndexedDB (Spec 02 v0.4–v0.16 §5.9) | A second workspace implementation would be the largest piece of code in the project and would have to track every host change forever. One host means one conformance suite and new operations work in both modes for free. |
| D2 | How the browser persists the filesystem | **OPFS** (Origin Private File System) mounted as the data root, in the worker. | IDBFS (needs explicit sync after every write, loads everything into memory); whole-workspace blob export after each change | Real files, synchronous access in a worker, memory stays flat, maps one-to-one onto the data-root concept. Desktop browsers first; the iPad is verified later (§9.4). Persistence across reloads, restarts and updates is a hard requirement either way. |
| D3 | How logs reach the browser | **The page enumerates, Python classifies.** The UI obtains a folder (or files); JavaScript lists them and streams bytes to the worker; fingerprinting, de-duplication, admission and analysis run exactly as on the server. A `LogSource` abstraction separates *disk folder* from *browser folder*. | Mounting the directory handle into Pyodide so Python walks it (Chrome only); drop-files only, no folder concept | Works on all three maintained platforms and keeps Spec 02's folder model. Handle mounting may return later as a Chrome-only fast path. |
| D4 | How the UI knows its host | **One build, a static `runtime.json` beside `index.html`, and a `get_capabilities` operation.** | Probing `/rpc` at start-up; two builds | Probing is racy and makes a "nothing leaves your device" site open with a failing network call; two builds double the test matrix. |
| D5 | Progress for long operations | **A progress callback given to every operation by the host.** The server stores it for polling (unchanged for the UI); the worker forwards it as a `progress` message. | Splitting scan into UI-driven steps | Invisible to the UI; one scan implementation. |
| D6 | Where this lives | **Spec 04 Part B made normative;** Spec 02 §5.9 revised to the filesystem-on-OPFS realization; Spec 03 and 14 take the mode-specific UI. | A new spec | Part B always owned the adapters; project convention is to revise the owning spec. |
| D7 | Packaging | Pinned, self-hosted Pyodide (numpy and pandas only); the engine delivered to the browser as one wheel built by CI from the same commit as `web/dist`; the same wheel carries `web/dist` so `pip install` suffices for the server (resolves Spec 01 Q8 → §9.5 option A, with D for Docker); conformance under Pyodide-in-Node in CI; service worker last. | — | Everything else stays a developer-only setup. |

### 9.1 One host, three transports

```
   ┌────────────────┐    ┌──────────────────────┐    ┌─────────────────┐
   │  CLI (argparse)│    │ HTTP server          │    │ Web Worker      │
   │  in-process    │    │ POST /rpc, /download │    │ postMessage     │
   └───────┬────────┘    └──────────┬───────────┘    └────────┬────────┘
           │        envelope (Spec 01 §7) + progress          │
   ┌───────▼───────────────────────▼─────────────────────────▼────────┐
   │  Host module — transport-neutral                                 │
   │  dispatch(op, params, ctx) · the 90 operations · capabilities    │
   │  ctx: data root, registry, active workspace, emit_progress,      │
   │       deliver_file, log_source factory                           │
   ├──────────────────────────────────────────────────────────────────┤
   │  workspace.py · operations.py · engine (Spec 01)                 │
   ├──────────────────────────────────────────────────────────────────┤
   │  Filesystem:  ~/SlingologyEIS (disk)   |   /data (OPFS mount)    │
   └──────────────────────────────────────────────────────────────────┘
```

**The host module** holds everything that today sits in `server.py` apart from HTTP: the operation table, the dispatcher, the active-workspace context, data-root resolution and the capabilities declaration. A transport only converts its wire format to and from the envelope and supplies the host with the few things it cannot know on its own:

| The host asks the transport for | Disk (server, CLI) | Browser (worker) |
|---|---|---|
| Where the data root is | Spec 02 §5.8.1 resolution | The OPFS mount, fixed |
| `emit_progress(stream, update)` — streams: `scan`, `data_location` | Store the latest update per stream for `get_*_progress` polling | Post a `progress` message tagged with the `request_id` and stream |
| `deliver_file(path, filename)` | Register a one-shot `/download/<token>` URL | Transfer the bytes to the page, which saves them |
| Inbound files (`ctx["uploads"]`, looked up by id) | `/upload` writes the file and registers it | The page transfers bytes; the worker writes them to a scratch path and registers them |
| A `LogSource` for a folder | Walk the disk (§9.3) | Listing and bytes supplied by the page (§9.3) |

The dispatcher, not the transport, enforces the rules every mode shares: an operation that needs an active workspace, operations allowed while the data location is missing, the busy check during a data move (a running scan blocks only a change of data location). The host keeps its own busy flags; the progress store is for clients. The contract suite calls `dispatch` directly (§9.6), so a transport cannot change behaviour without the suite noticing.

### 9.2 Browser transport

- **Worker.** One dedicated Web Worker loads the pinned Pyodide, numpy, pandas and the engine wheel, mounts OPFS at the data root, imports the host module and enters a message loop. The page never runs Python. The UI's `BrowserWorkerClient` implements the same `EngineClient` interface as `LocalServerClient`; `getEngineClient()` chooses from `runtime.json` (§9.4). No view changes.
- **Messages.** Requests are the Spec 01 §7 envelope objects, one `postMessage` each; the result or error comes back with the same `request_id`; progress messages carry the `request_id` of the operation they belong to. Two things cross as transferables, not JSON: log bytes going in (`ArrayBuffer`, written straight into the virtual filesystem under a scratch path and released after the operation) and series going out (typed arrays, `NaN` for null, as Spec 01 §8.7 already states). Base64 (`content_base64`) stays an HTTP-only encoding.
- **Start-up.** The page shows a loading state with progress ("Setting up the analysis engine… about 30 MB, once"). On later visits the runtime comes from the browser cache. The worker reports `ready` with the engine version, Pyodide version and the data-root state; until then the client queues requests.
- **One operation at a time.** The worker is single-threaded; the client serialises requests. A long operation (scan with analysis) blocks later requests, which is why progress is a message rather than a second request. The page warns on navigate-away while an operation is running ("Analysis in progress"), as it would for unsaved edits.
- **Cancellation and failure.** Cancel = terminate the worker and start a new one; the workspace is on OPFS, so nothing in worker memory is lost beyond the operation in flight. A worker that dies (out of memory, an uncaught error) is restarted by the client, the pending request fails with `HOST_RESTARTED`, and the page says so once. A half-written analysis is prevented the same way as on disk: workspace writes are atomic per document (write to a temporary name, rename).
- **Memory.** One flight's raw frame resident at a time (Spec 01 principle 8); the worker discards it after each operation. The spike measured 156 MB after one 4.5-hour flight; a 100-log scan must not grow beyond that by more than the §7 batch criterion. Verified in step 4 (§10).

### 9.3 Log sources

A workspace references folders (Spec 02 §5.1). What differs by host is how a folder's contents are listed and read:

| | Disk folder | Browser folder |
|---|---|---|
| Added how | A typed path (`add_log_folder`) | **Choose folder…** — Chrome: `showDirectoryPicker`; Safari: `<input webkitdirectory>` or a dropped folder |
| Listed how | Python walks it recursively (`*.csv`) | The page walks the handle or the file list, recursively, and sends `[ {relative_path, size, last_modified} ]` |
| Read how | Python opens the file | The page sends bytes for the files the host asks for, one at a time, as transferables |
| Remembered how | Path in the manifest | Chrome: the `FileSystemDirectoryHandle` persisted in a small IndexedDB store keyed by `folder_id` (Spec 02 §6.1); permission is re-confirmed with one click when the browser asks. Safari: nothing persists; the folder shows **Not connected — reconnect** until re-picked. |
| Rescan | One click | Chrome: one click. Safari: *Reconnect folder*, then Sync |
| Dropped files (no folder) | n/a | Supported in both browsers; they are classified and analysed like any other log and recorded as a source without a folder, exactly as the existing upload path records them |

The host's scan operation therefore accepts, besides a folder to walk itself, an **externally supplied listing plus a byte provider**. Everything downstream — fingerprinting, duplicate detection, admission rules (Spec 02 §5.11), missing/moved re-matching (§5.5), the "needs re-analysis" bookkeeping, the per-log progress line — is the same code. In the browser a byte provider is a request to the page, so the scan is naturally incremental: the page is asked for one file, sends it, the host processes it, reports progress, asks for the next.

Raw logs are never written to OPFS. The scratch copy of the file being processed is deleted as soon as the operation returns.

### 9.4 Persistence (browser)

- **Data root.** OPFS is mounted in the worker at a fixed path and holds exactly Spec 02 §5.8's layout: `registry.json`, app `settings.json`, `workspaces/<id>/…`. The documents are byte-identical to the disk realization — Spec 02 §5.10 becomes a statement of fact rather than a rule to police. The manifest's `storage_backend` reads `opfs`.
- **What survives.** Reload, tab close, browser restart, machine reboot, and updates of the app (a new build reads the same storage; engine-version staleness works as today). This is the persistence requirement.
- **What removes it.** The user clearing the site's data; Chrome under disk pressure if persistence was not granted; Safari's inactivity eviction. Mitigations, all in scope: the app requests durable storage (`navigator.storage.persist()`) when the first workspace is created (Spec 02 §9's open recommendation is now decided: yes); Settings → App shows a **Storage** panel — space used, *Persistent: yes/no*, **Export all workspaces…**, **Delete all data on this device** (Spec 14 §5.2); and if the app opens to an empty store where it had recorded a registry before (a marker in `localStorage`), it shows "Your workspace data isn't on this device any more — import an export or add your log folders again" instead of a silent first run.
- **Backup** is the workspace export (Spec 02 §7), the same file in both modes, importable in either.
- **Verification.** Before step 4 (§10) a short probe on macOS Chrome and Safari: OPFS available in a worker, a 50 MB write/read round trip, the Pyodide mount, data present after a reload and after a browser restart, `persist()` outcome. The iPad runs the same probe when it becomes a priority; until then the iPad is out of the supported set for browser mode (the Part A result stands as evidence it will work).

### 9.5 Mode selection and capabilities

- **`runtime.json`**, fetched by the page before anything else, is one of:
  - `{ "host": "server" }` — served by `slingology-eis serve` beside the built UI; the client is `LocalServerClient` on the page's own origin (Vite dev keeps its fixed cross-origin default).
  - `{ "host": "browser", "pyodide": "<pinned version>", "engine_wheel": "<file>" }` — shipped with the static site; the client is `BrowserWorkerClient`.
  
  Missing or unreadable: the page says the installation is incomplete rather than guessing.
- **`get_capabilities`** (new operation, both hosts) returns `{ host: "server"|"browser", engine_version, host_version, features: { data_location, add_folder_by_path, choose_folder, persistent_storage_status, download_url, folder_watching } }` — booleans, extended as hosts diverge. The UI gates on `features`, never on `host`.
- **Mode-specific operations** (data location, `add_log_folder` by path, `get_*_progress` polling) exist only in the host that supports them; calling one elsewhere returns `UNSUPPORTED_IN_HOST`. Nothing in the UI reaches them without the matching feature flag.

### 9.6 One conformance suite

The contract tests (Spec 01 §12, `tests/contract`) run three ways with no test changes:

1. **In-process** — against `dispatch()` directly. This is the default and the fastest; it covers every operation and is where behaviour is specified.
2. **Over HTTP** — against a server started by the test, to catch transport mistakes (encoding, the download route, error mapping).
3. **Under Pyodide in Node.js** — the worker's entry module loaded by Node, OPFS replaced by Node's in-memory filesystem, the same tests sent as messages. No browser needed; runs in CI on every commit. It catches package-version and WebAssembly differences (the spike found none, but pandas under Pyodide lags the native release).

Real-browser behaviour — folder pickers, handle persistence, OPFS, memory — is checked by hand on macOS Chrome and Safari before each release, using a checklist kept with the spec; the iPad joins when it is in scope.

### 9.7 Packaging and delivery

| Item | Rule |
|---|---|
| Pyodide version | One version file at the repo root, read by the static-site build, the worker, the Node conformance run and the docs (closes Q4). Upgraded deliberately, behind the suite. |
| Pyodide files | Self-hosted with the static site (core runtime, numpy, pandas only), not loaded from a CDN. |
| Engine delivery | CI builds one wheel of `slingology_eis` (which already carries the engine profiles and topic help as package data) from the tagged commit; the browser installs that wheel into Pyodide; the same wheel, with `web/dist` included, is what `pip install` gives the server user — BACKLOG P3 closes with this. |
| Static site | A build target that emits `index.html`, `web/dist`, `runtime.json`, the Pyodide files and the wheel into one folder suitable for any static host. GitHub Pages cannot set headers, so nothing depends on cross-origin isolation (threads, `SharedArrayBuffer`). |
| Offline | A service worker precaches the runtime and the wheel after the first visit, so the site opens and analyses with no network (closes S5). Added last so it does not complicate debugging the steps before it. |
| Server packaging for NAS and Docker | Spec 04 v0.3 §9.5 options A and D stand; Docker is BACKLOG P2 and not part of this work. |

### 9.8 User experience by host

The principle: same app, same screens, same workspace documents. Differences exist only where the browser physically cannot do what a local process can.

| | Local server | Browser |
|---|---|---|
| First visit | `slingology-eis serve`, open the page | Open the site; one-time engine download with progress (~3 s on broadband); later visits under a second |
| Add logs | Type a path, or drop files | **Choose folder…** (OS picker) or drop files; Chrome remembers the folder, Safari asks again each session |
| Sync | One click | Chrome: one click; Safari: reconnect folder, then Sync |
| Where data lives | `~/SlingologyEIS` (movable, Settings → App) | The site's private storage; Settings → App shows **Storage** instead of *Data location* |
| Export | Browser download from the server | Browser download from the page — same file |
| Import | Pick the zip | Pick the zip |
| Long sync | Progress line; other requests still answered | Progress line; the page warns before closing the tab |
| Offline | Always | After the first visit (step 6) |
| Visible mode indicator | None; Settings → Engine's About line names the host | Same |
| Hidden in this host | — | Data location, add-folder-by-path, CLI, folder watching |

The only new screen in the whole app is the browser's engine-loading state.

## 10. Plan (v0.4)

Work happens on branch `pyodide`, off `main` at 1.0.0, merged back when step 4 passes on macOS Chrome and Safari. Each step leaves the server mode behaving exactly as before and the full suite green; steps 1–2 may be merged to `main` on their own.

| Step | What | Done when |
|---|---|---|
| 1 ✅ | **Extract the host.** The operations, their table and the dispatcher move out of `server.py` into a transport-neutral host module; `server.py` keeps only HTTP. The host receives `emit_progress` and `deliver_file` from its transport. `get_capabilities` added. The contract suite runs against `dispatch()` in-process (§9.6 mode 1) and over HTTP (mode 2). | Done 2026-10-19 (`57fb871`): `host.py`; 99 ops tests × 2 call paths; 792 passed. |
| 2 | **Log sources.** `LogSource` with a disk implementation wrapping today's walk; the scan accepts an external listing plus byte provider; export returns a file to the host, which decides between `/download/` and bytes. Still server-only. | Suite green; a test drives a scan with a supplied listing and in-memory bytes and gets the same workspace as the disk walk. |
| 3 | **Persistence probe** (§9.4) on macOS Chrome and Safari. Half a day. Decides whether D2 stands or IDBFS is needed. | Written results in Appendix D. |
| 4 | **Browser host.** Worker entry module, `worker.ts`, `BrowserWorkerClient`, OPFS data root, `runtime.json`, capability gating in the UI (Flights folder picker and reconnect state, Settings → App Storage panel, export download, loading state, navigate-away warning). Node conformance run (§9.6 mode 3). | A workspace of the full test-log set created, synced, browsed, exported and re-imported in Chrome and Safari; documents byte-identical to the server's; memory within §7; suite green three ways. |
| 5 | **Packaging.** Version file, self-hosted Pyodide, CI-built wheel including `web/dist`, static-site build target; `pip install` then `serve` works without Node (P3). | A clean machine runs both modes from release artifacts. |
| 6 | **Offline and polish.** Service worker, persistence request and eviction notice wired, support checklist, static-site docs. | The site opens and analyses with the network off. |

Each step gets its own Claude Code prompt, written when the previous step is accepted. Prompts are functional; Code owns names and structure.

## 11. Risks and contingencies

| Risk | Mitigation |
|---|---|
| OPFS mount or `persist()` behaves differently than expected on Safari | Step 3 finds out before anything depends on it; IDBFS is the documented fallback with the same layout. |
| Cold start too slow on airfield Wi-Fi | Self-hosted, compressed, numpy and pandas only, progress shown; the service worker makes it a one-time cost. |
| Worker memory over a 100-log scan | One frame resident at a time; measured in step 4 against §7's batch criterion; the worker restarts cleanly if it dies. |
| Pandas under Pyodide lags native and diverges | The Node conformance run on every commit; the pinned version moves only behind it. |
| The scan's host-driven byte provider is slow in the browser | Files are streamed one at a time as transferables; if enumeration itself is slow on Chrome, mount the handle (`mountNativeFS`) as a Chrome-only fast path. |
| Two hosts drift | There is one host module; the transports contain no behaviour; the suite runs against all three. |
| GitHub Pages header limits (§2.7) | Nothing depends on threads or shared memory. |
| Pyodide releases move faster than the project | One pinned version, upgraded deliberately. |

## 12. Open questions

| # | Question | Status |
|---|---|---|
| Q1 | Minimum iPadOS/Safari versions | Deferred with the iPad (§9.4); the Part A result is the known-good point. |
| Q2 | Windows, Linux, Firefox, Edge, Android, iPhone | Community-verified only (§4.2). |
| Q3 | Tighten §7 thresholds | After step 4's first full browser run. |
| Q4 | Where the pinned Pyodide version lives | **Resolved (v0.4):** one version file at the repo root (§9.7). |
| Q5 | Keep the spike harness | Kept under `spike/` as the Part A record; its `worker.js` is superseded by step 4's worker and may be deleted then. |
| Q6 | Scrub the raw-log set before sharing | Unchanged; the anonymiser exists (Spec 02 §7.6). |
| Q7 | Should the Chrome handle mount (`mountNativeFS`) replace page-side enumeration once it proves itself? | Open; decide after step 4's timings. |
| Q8 | Rule-edit live preview under Pyodide (Spec 14 Q4) — debounced or explicit? | Measure in step 4; explicit step if a what-if round trip exceeds about 1 s. |
| Q9 | Folder watching in server mode (Spec 03 §5.1's "watching" state) | Not part of this work; capability flag reserved. |

---

## Appendix A — Results (filled 2026-09-22)

Harness: `spike/` (index.html + worker.js, real engine code, not the synthetic
proxy), diffed field-by-field against `spike/native_reference.py`'s golden
output for `log_20260423_200615_KACV.csv` (16,196 rows). Warm start and W3
stress steps were not re-run with the real-code harness (only with the
earlier synthetic benchmark, at 1×–8× scale — see note below); offline,
persistence, and the frame-gap sampler were not exercised this round.

| Environment | Pyodide | Cold ready | W1 (real pipeline) | Heap init → run | Parity (35 metrics, 5 phases) | Crash? | Verdict |
|---|---|---|---|---|---|---|---|
| Native (reference, Mac, Python 3.12.3) | – | – | 2.33 s | – → 141 MB RSS | golden | – | – |
| macOS Chrome | 0.28.0 | 2.82 s | 2.37 s | 75 → 156 MB | **exact match** | No | **Pass** |
| macOS Safari | 0.28.0 | 2.90 s | 2.11 s | 75 → 156 MB | **exact match** | No | **Pass** |
| iPad Safari (A17 Pro, iPadOS 18.7 / Safari 26.6.1) | 0.28.0 | 3.41 s | 2.56 s | 75 → 156 MB | **exact match** | No | **Pass** |

All three browsers loaded numpy 2.2.5 / pandas 2.3.0 under Pyodide, versus
numpy 2.5.3 / pandas 3.0.6 natively — the version difference produced zero
observable output difference on this log.

Per-step breakdown (`load_log` → `detect_phases` → `phase_summary` →
`build_flight_metrics`), seconds:

| | import | load_log | detect_phases | phase_summary | build_flight_metrics |
|---|---|---|---|---|---|
| Native | 0.00 | 0.44 | 0.34 | 0.01 | 1.54 |
| Chrome | 0.02 | 0.46 | 0.34 | 0.02 | 1.50 |
| Safari | 0.03 | 0.49 | 0.30 | 0.02 | 1.26 |
| iPad Safari | 0.02 | 0.44 | 0.38 | 0.02 | 1.69 |

`detect_phases` — the row-by-row Python loop flagged as the main risk in
§2 finding 1 — was the concern with the least basis in fact: it ran within
0.04–0.08 s of native on every platform, including the iPad.

**Separately, the earlier synthetic pandas benchmark** (random data, not
the real pipeline; see the chat record) ran up to `k=8` (≈129,600 rows, 8×
a real flight) on all three platforms with no crash, heap topping out at
841–922 MB. That is evidence stress headroom likely exists, but it used
synthetic data through a different code path, so it is not a substitute
for running W3/W4 against real logs once more are available.

Not yet run: warm-start timing and the offline/service-worker case (S5),
the frame-gap responsiveness sampler (S6), OPFS/IndexedDB persistence
probes (S7), and stress/batch on the real pipeline (W3/W4 — blocked on
more raw logs per §6/Spec 01 Q6). None of these are expected to overturn
the decision below; they close remaining gaps in the picture.

## Appendix B — Decision record

| Field | Value |
|---|---|
| Date | 2026-09-22 |
| Pyodide version(s) adopted | 0.28.0 |
| Outcome | **GO.** Path 1b (Spec 01 D2) proceeds as designed. iPad runs full analysis, not just the results-bundle viewer (P3 can be relaxed for the iPad Mini A17 Pro / iPadOS 18.7 class of device; older/lower-memory iPads remain unverified — §2 finding 6). |
| Minimum browser and iPadOS versions | Not yet floored — only current-generation browsers and one iPad (A17 Pro, iPadOS 18.7, Safari 26.6.1) were tested. Treat as the known-good point, not a minimum, until an older device is tried. |
| Measured cold start, W1 time, peak heap | Cold ready 2.8–3.4 s; real pipeline (load → phases → metrics) 2.1–2.6 s; heap 75 MB at ready, 156 MB after one flight — all far inside the §7 targets. |
| Consequences for Spec 01, 02, 03 | None required. Spec 01's transport-independent contract and P3 stand; Spec 02 (results bundle, browser storage) and Spec 03 (UI) can proceed without a server fallback. Spec 02 should still treat browser storage as evictable (§2.8) — that's a storage-lifetime question, independent of this compute result. |
| Follow-ups | (1) Offline/service-worker test (S5). (2) Frame-gap responsiveness sampler while a run is in progress (S6). (3) OPFS/IndexedDB persistence probes (S7) — feeds Spec 02 directly. (4) Stress/batch on the real pipeline once more raw logs are available (W3/W4, Spec 01 Q6). (5) Self-host Pyodide instead of the jsdelivr CDN before this becomes the production build. None of these block starting Spec 02. |

## Appendix C — References

- Pyodide project and release notes: https://pyodide.org/ and https://pyodide.org/en/stable/project/changelog.html
- Pyodide 0.27.1+ not working on iOS (issue #5428): https://github.com/pyodide/pyodide/issues/5428
- Pyodide package channel (numpy, pandas versions): https://anaconda.org/pyodide/repo
- Safari on iOS memory constraints for WebAssembly (general discussion): https://groups.google.com/g/emscripten-discuss/c/SlmrsE9hpwE

## Appendix D — Persistence probe results (step 3; to be filled)

| Browser | OPFS in worker | 50 MB round trip | Pyodide mount | After reload | After browser restart | `persist()` | Notes |
|---|---|---|---|---|---|---|---|
| macOS Chrome | | | | | | | |
| macOS Safari | | | | | | | |
| iPad Safari | deferred | | | | | | |
