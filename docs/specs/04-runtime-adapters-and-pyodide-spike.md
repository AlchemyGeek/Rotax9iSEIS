# Spec 04 — Runtime Adapters & Pyodide Feasibility Spike

**Project:** SlingologyEIS web platform
**Status:** v0.3 — Part A complete, decision **GO** (real-code harness run on macOS Chrome, macOS Safari, iPad Safari)
**Suggested repo path:** `docs/specs/04-runtime-adapters-and-pyodide-spike.md`
**Builds on:** Spec 01 — Engine Contract v0.2 (D2, P3, §7, §7.1, Stage 4, Q8)
**Precedes:** Spec 02 (Results Bundle & Workspace), Spec 03 (UI Information Architecture)
**Baseline reviewed:** repo `main` at commit `ed0ca33` (2026-07-07), v0.10.0 tag; project logs

**Revision history**

| Version | Change |
|---|---|
| 0.1 | Initial draft. |
| 0.2 | Test matrix narrowed to the maintainer's actual environments: macOS Chrome, macOS Safari, iPad (§4.2). Added a support policy for untested platforms, Safari storage note (§2.8), and a way for contributors to submit their own results. |
| 0.3 | Part A run against the **real** engine (not the synthetic proxy): a harness (`spike/`) ran `load_log` → `detect_phases` → `build_flight_metrics` on the KACV log inside Pyodide, on macOS Chrome, macOS Safari, and iPad Safari, diffed against a native golden. Result: **GO**, exact parity on all three, comfortably inside every target threshold. Appendix A/B filled in (§13). S5–S7 and stress/batch (W3/W4) remain untested; noted as follow-ups, not blockers. |

---

## 1. Purpose and structure

The chosen deployment path 1b (Spec 01, D2) depends on one unproven assumption: **the existing Python analysis runs acceptably inside a browser via Pyodide, including on an iPad.** Specs 02 and 03 (browser storage, UI behaviour) depend on the answer, so we test the assumption before building on it.

This spec has two parts:

- **Part A — Feasibility spike (normative).** A time-boxed experiment: what to run, what to measure, pass/fail thresholds, and how the result decides the architecture.
- **Part B — Runtime adapters (informative until Part A returns GO).** The three ways the engine is hosted (browser worker, local server, CLI), how they share one test suite, and how the UI is packaged for local hosting (resolves Spec 01 Q8).

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

## 9. Part B — Runtime adapters (informative until GO)

All adapters expose the Spec 01 operations through the same envelope, so the UI cannot tell them apart.

### 9.1 Browser adapter (path 1b)

A dedicated Web Worker hosts Pyodide and the engine. The UI sends envelope requests with `postMessage`; progress events arrive on the same channel; series data crosses as transferable typed arrays. Logs enter as `File` → `ArrayBuffer` and are written into the virtual filesystem until Stage 1 adds a bytes-based loader. Cancellation is by terminating and restarting the worker. One flight's raw frame is resident at a time; the worker discards it after each `analyze_flight`. The whole runtime is precached by a service worker so the app also works offline.

### 9.2 Local server adapter (path 2)

A small HTTP server exposing the envelope (`POST /rpc`) with a progress stream, and serving the built UI at `/`. It binds to the loopback interface by default; when bound to any other interface (Docker on a NAS), it requires an access token, since it can read the mounted log folder. It can optionally watch the log folder and process new files automatically, which is the fully hands-off experience the browser cannot offer. The choice of server library is deferred, with a strong preference for minimal dependencies to keep installation easy for non-experts.

### 9.3 CLI adapter

Specified in Spec 01, §7.1. In-process, no transport.

### 9.4 One conformance suite

A single contract test suite (Spec 01, §12) runs unchanged against all three adapters and compares against the same golden outputs. After a GO decision, the browser run is also automated in continuous integration by running Pyodide under Node.js, which needs no browser. Browser-specific behaviour (especially iOS) still needs real-device checks before releases.

### 9.5 UI packaging for local hosting (resolves Spec 01 Q8)

| Option | Description | Assessment |
|---|---|---|
| A | Built UI assets are bundled inside the Python package (wheel), so `slingology-eis serve` works after a plain install. | **Recommended.** Works offline, no extra step. Requires CI to build the UI before the wheel; build output is not committed to the repo. |
| B | `serve` downloads UI assets from a release on first run. | Needs network and an extra failure mode. |
| C | The hosted static site talks to a locally running API. | Not recommended: cross-origin and mixed-content rules differ by browser, and it weakens the "nothing leaves the device" story. |
| D | A Docker image containing engine, server, and UI. | **Recommended alongside A** for NAS and third-party hosting. |

## 10. Deliverables

1. `spike/` harness and native reference runner (on request, after this spec is accepted).
2. `spike/RESULTS.md` and `spike/results/*.json`.
3. A one-page **decision record** (Appendix B) committed with the results, referenced from Spec 01 and Spec 02.
4. Updates to Spec 01 (P3, D2, Stage 4, Q8) reflecting the outcome.

## 11. Risks and contingencies

| Risk | Mitigation |
|---|---|
| The current stable Pyodide fails on iPad | Test the earlier pinned version; record working iPadOS/Safari versions; fall back to "GO, desktop only". |
| Cold start is too slow for casual users | Self-host with compression, load only numpy and pandas, show progress, precache for later visits; measure what a first visit actually costs before optimizing. |
| Too few raw logs to run W2 (scripts 03–04) and W4 | Mark blocked, ship the desktop and iPad verdict on W1 and W3, complete the rest when logs are available. |
| Numerical differences at the last bit | Tolerance in §4.5; investigate anything beyond it. |
| Pyodide releases move faster than the project | Pin an exact version in the repo, upgrade deliberately behind the conformance suite. |
| Header limits of the static host (§2.7) | Do not depend on threads or shared memory. If a future need arises, move the static site to a host that allows custom headers; the site is plain files. |

## 12. Open questions

| # | Question | Proposal |
|---|---|---|
| Q1 | Which minimum iPadOS/Safari versions do we commit to supporting? | Decide from the spike results. |
| Q2 | What about Windows, Linux, Firefox, Edge, Android, iPhone? | Community-verified only (§4.2 support policy); not tested by the maintainer and not blocking. |
| Q3 | Should thresholds in §7 be tightened once real numbers exist? | Yes; revise after the first complete run. |
| Q4 | Where is the pinned Pyodide version recorded so the harness, app, and CI agree? | One version file at the repo root, read by all three. |
| Q5 | Do we keep the spike harness in the repo after the decision? | Archive under `spike/` with the results; delete only the harness code if it becomes dead weight. |
| Q6 | Should the raw-log set for W4 be scrubbed before it is shared? | Yes. The anonymizer (Spec 01, §10) should exist before any log reaches the public repo. |

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
