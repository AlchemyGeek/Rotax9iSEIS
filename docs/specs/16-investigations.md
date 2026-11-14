# Spec 16 — Investigations

**Project:** SlingologyEIS
**Status:** Draft v0.3 — Session D (engine: MCP server, code tool, notebooks, inbox scan) built on `research` (Nov 14 2026); §3.1 records its functional decisions, several for the owner to confirm. Acceptance 1–5 are the owner's Claude Desktop run (§7 interim note); Session E (extension bundle, notebook rendering on the website) follows.
**Suggested repo path:** `docs/specs/16-investigations.md`
**Builds on:** Spec 06 (the Research instrument: slices, descriptors, questions, studies, `.eisstudy`, operations), Spec 01 (§7 operations envelope, §10 privacy), Spec 02 (workspace layout, export/import), Spec 04 (two hosts; server mode and browser mode), Spec 03 (principle 6), Spec 10 (§10 proposals, lifecycle)
**Revises:** Spec 06 (§14.2 Investigations and detectors move here; Session C withdrawn), Spec 04 (a third front door to the engine: the MCP server), Spec 02 (a notebook study document and an inbox), Spec 03 (the Research view renders notebooks; an inbox)
**Model case:** the owner's takeoff RPM/MAP oscillation investigation, done with Claude and scripts in October 2026 (`docs/research/2026-10-takeoff-rpm-oscillation.md`) — what an investigation should look like when the app is the instrument.

**Revision history**

| Version | Change |
|---|---|
| 0.3 | **After Session D.** Built: the §4.3 operations (`code_run`, `study_cells_append` / `_rerun` / `_accept` / `_discard`, `study_finish`, `aircraft_get` / `_set`, `documents_list`, `document_read` / `_add` / `_remove`, `inbox_scan` / `_list` / `_resolve`), the notebook study (§5), the inbox (§6), the MCP server `slingology-eis mcp` with 24 tools (§4.2 as built), `slingology-eis mcp tools` / `mcp call`. §3.1 records the functional decisions Session D made; §4.2 the tool list with its caps; §4.5 the bench's caps, namespace and envelope — two layers, the audit hook everywhere and the kernel's sandbox on macOS; §9 Q1–Q2 resolved; §7 an interim note for running the server from a dev install in Claude Desktop. Acceptance 5 (engine part), 6, 7 and 8 (the engine's clauses) pass in the test suite; Spec 06 acceptance 14–17 pass. Engine version unchanged (1.0.2): no stored flight's analysis changes. |
| 0.2 | **D3–D9 decided**; §4 MCP server and tool surface, §5 notebook format, §6 inbox and cadence, §7 extension, §8 acceptance written. Shared detectors (D9) resolved as *questions in shared notebooks* run by the recipient's Claude — no unattended non-OM rule. Session plan in §11. |
| 0.1 | Skeleton. The reframing: Research as built (Spec 06) is the *instrument*; the *scientist* is the user's own Claude, reaching the instrument through an MCP server that runs on the user's computer inside the Claude Desktop extension. Two tiers of user: the casual user on the website, the advanced user with the Desktop extension. A study authored by the investigator is a notebook. Proactive detection is deterministic and recurrence-gated; the AI interprets, on request or on a cadence the user sets. Decisions D1–D2 recorded; the open decisions listed. |

---

## 1. Why

The takeoff rpm/MAP cycle was found by a loop, not by a statistic: cut every full-power segment, notice the MAP lockstep, read the OM engine deck, form the limit-cycle hypothesis, test it against altitude, eliminate the clutch-slip and ECU-limiter alternatives, write it up so the manufacturer recognised it in one email. The statistics were twenty-minute scripts; the loop was Claude's, steered by the owner. Spec 06 built a UI around the scripts and left the loop out — which is why it kept needing another level of screens (v0.6, withdrawn).

The app's job is therefore not to reproduce the loop in forms, but to make a good investigator possible: give the user's own AI an instrument (tools), a bench (code against the data), the literature (the OM and the aircraft's configuration), a way to keep evidence (a notebook), and a reason to look (an inbox). The pilot asks in words; the investigator works; the study appears in EIS.

## 2. The model

### 2.1 Two tiers of user

| Tier | Runs | Gets |
|---|---|---|
| **Casual** | the website (browser mode, Pyodide, nothing installed) | Flights, Trends, Journal, the manual Research tools (Spec 06). Logs never leave the browser. No investigations. |
| **Advanced** | the **Claude Desktop extension**, one install, which carries the EIS engine and serves the EIS pages locally | everything above, plus investigations: their own Claude connected to EIS through MCP |

The website keeps its workspace in browser storage; the extension keeps its on disk. Both read the same log folders; decisions move between them by workspace export/import (Spec 02 §7). A smoother hand-off is a later concern.

### 2.2 Where the pieces run

On the user's computer: the **EIS engine** (Python, the same one Spec 04 describes), with two front doors — the local web server for the browser tab, and the **MCP server** for Claude Desktop. Both see the same workspace: a notebook cell written by the investigator appears in the browser's Research page; a filter pinned in the browser is seen by the investigator's next tool call. Claude Desktop launches the MCP server from the extension bundle; the only network traffic is Claude's own conversation with Anthropic. The AI never reads log files; it calls tools.

### 2.3 Where the user works

The user asks in the Claude app — *"the climb after my touch-and-go at KBLI on Oct 24 felt like a surge; look into it"* — and steers there. The study forms in EIS as the investigator writes it. Claude is where the user thinks; EIS is the instrument and the record. There is no chat box inside EIS: that would mean EIS hosting the AI loop with a key, a service the owner will not run, and a worse Claude than the real one (no Projects, memory, attachments or skills). A Claude Project for the aircraft — OM, SBs, propeller manual, prior write-ups — is the standing context every investigation starts with.

### 2.4 What the MCP server exposes (layers)

1. **Raw material** — flights, channels and series, phases, events, the cached per-flight analysis, fleet metrics, baselines and trends.
2. **Research instrument** — Spec 06's operations: presets, slices, descriptors, the four questions, samples, `analyze_signal`, `compare_rows`, studies.
3. **Bench** — a code tool: run Python against the workspace in the local engine process (scope: D3).
4. **Context** — the engine profile, the aircraft configuration, prior studies and Journal, and documents the user has placed in the workspace (the OM stays the user's copy; Spec 06 §1 constraint).
5. **Record** — notebook-writing tools: append a cell, attach a figure or table, finish a study; the inbox (D5).

### 2.5 A study is a notebook

Narrative cells, code cells with their outputs, figures and tables — authored by the investigator through tools, rendered by EIS in the Research view, saved in the workspace, re-runnable (on new flights, after a change, on another owner's workspace), shareable as a `.eisstudy`. Hand studies (Spec 06) and investigator studies share one format. The model case's write-up — question, what was looked at, what was found, what it means, what to do, every number traceable — is what a finished notebook should read like. Format: D4.

### 2.6 Proactive: detection decides *when*, the AI decides *what it means*

The AI does not read every flight. After each import EIS runs its deterministic, recurrence-gated scan on the preset slices (Spec 06 §14.1): a pattern in N of M recent slices, a descriptor shifted against the fleet reference, a physics flag such as a prominent period in governed rpm. Candidates go to a **Research inbox**, never onto flight cards, each with its evidence table. The user's AI investigates on request (*"look into this"*) or on a cadence the user sets, which Claude's own scheduling can drive. An investigation ends as a study in the inbox; "nothing here" is a legitimate outcome and is recorded so a candidate is not re-investigated. A single odd flight is the Flight view's job, not the inbox's. Details: D5.

### 2.7 Trust and privacy

Every claim in a notebook traces to a tool result, a code cell's output, or a cited document, or is labelled a hypothesis; the pilot sees the code. No verdict words without their reference (Spec 06 §8 applies to notebooks). The engine runs no AI and stores nothing on anyone's behalf; the user's Claude account carries the conversation. Only what the investigator asked for leaves the machine, in Claude's conversation; raw logs never do unless the user attaches one.

## 3. Decisions

| # | Decision | Rationale |
|---|---|---|
| **D1** | **Research as built is the instrument; the scientist is the user's own Claude through an MCP server in the Claude Desktop extension.** Two tiers: casual on the website, advanced with the extension. | The loop that found the oscillation was Claude's; building it into forms misses it. The user already has Claude; the owner runs no service and manages no keys. |
| **D2** | **Spec 06 v1 stays as the manual workbench; the v0.6 Signal/Compare screens are withdrawn; their engine operations become tools; Session C is replaced by Spec 16's first session.** | Nothing built is lost; nothing more is built for a UI the investigator will not need. |
| **D3** | **Restricted bench.** The code tool runs full scientific Python (numpy, pandas, scipy, matplotlib) in the engine process with the workspace loaded; no network, no subprocesses, writes confined to the study's folder, time and memory caps; outputs (text, tables, figures) become notebook cells; every executed cell is stored. Declared as a writing tool so Claude Desktop asks before first use. | The oscillation needed computations nobody had packaged; the next finding will too. The envelope closes the obvious ways a bad cell reaches beyond EIS, on the user's own machine, with the code visible. |
| **D4** | **The notebook extends the Spec 06 study document** with a `cells` list (markdown, code with captured outputs, question, figure, table); hand studies are notebooks whose cells are their questions; re-run executes cells in order, producing new outputs *beside* stored ones until accepted; each code cell records the engine version and workspace fingerprint set it ran against; one renderer, one `.eisstudy`; one-way export to `.ipynb`. | One format for hand and Claude studies; a shared notebook keeps the author's results until the recipient runs it (the read-only pattern per cell); Jupyter users can continue elsewhere. |
| **D5** | **Deterministic scan, fixed defaults, three-position sensitivity.** After each import (or on demand) the scan runs on each preset's slices over Trends' recent window and emits recurring patterns (N of M = 6 of 10), shifts (Spec 12's shift statistic), and groups apart; one candidate per preset-and-descriptor; a candidate returns only after the window has moved half-way on; *quiet / normal / curious* maps onto the parameters, shown on every candidate; "nothing here" is a recorded resolution. `inbox_list` / `inbox_resolve` tools; scheduling is the user's Claude's; EIS never calls out. | Proactive without noise, and without the AI reading every flight. Agreement with Trends on "recent" and "shift" so the two never disagree. The investigator may propose a gating change in a notebook; it never changes one. |
| **D6** | **Self-contained Claude Desktop extension**: standalone Python runtime + EIS wheel + dependencies + built web UI, one bundle per platform, built in CI; one process started by Claude Desktop running the MCP server (stdio) and the EIS web server on 127.0.0.1:8420; workspace at the server-mode data root (Spec 02 §5.8.1) so pip and extension users share one; log folders chosen in either place; one-click install from the GitHub release. Bundle mechanics to be verified by Code against current Claude Desktop documentation. | No prerequisites for non-technical users; the version run is the version tested; pages up while Claude Desktop is, `slingology-eis serve` for EIS without Claude. |
| **D7** | **Curated tool surface (~22 tools) in five layers** (§4.2), summaries by default and detail on request, size limits on series, documents paged, writing tools marked; a façade over the Spec 01 envelope, so parity is testable. Nothing in the surface deletes logs, changes filters or limits, or touches Journal entries other than study findings. | Claude works best with a moderate number of well-described tools whose results are small. |
| **D8** | **The website reads and renders, doesn't author.** Notebooks render fully (code cells show stored outputs, marked *ran elsewhere*); the deterministic scan fills a website inbox whose candidates offer *Run the question by hand* and the install invitation; *Run this on my flights* on an imported Claude notebook runs its question cells and skips its code cells. One notebook renderer for both tiers. No Pyodide bench. | A friend's notebook must be readable on the casual tier; the bench is not duplicated across two sandboxes. |
| **D9** | **No unattended detectors.** A notebook may mark itself *a question to ask of any engine of this type*; the Research page lists such shared notebooks and the recipient's Claude runs them on request or on the user's schedule. True detectors stay deferred until there are several engines and several such notebooks to judge them by. | Spec 06's constraint stays whole: nothing but the OM runs as a rule without the user asking. The author's explanation travels as narrative, not as a verdict. |

### 3.1 Functional decisions made in Session D

Decisions Session D had to make to build §4–§6. ◆ marks those the owner should confirm; each carries the revision text it would need if confirmed.

| # | Decision | Why | Owner |
|---|---|---|---|
| S1 | **The bench runs each cell in a worker process** (`python -m slingology_eis.investigations.bench_worker`), not in the engine process. The worker reads the workspace through the same loaders and the inbox's descriptor cache; the engine process never runs cell code. | A runaway or crashing cell can't take the MCP server or the pages with it; the wall-clock cap is a kill, and the memory cap and the kernel sandbox (S2) are per process. | ◆ D3: replace "in the engine process with the workspace loaded" by "in a worker process the engine starts per cell, with the workspace readable". |
| S2 | **The envelope has two layers** (§4.5): a PEP 578 audit hook in the worker on every platform, and on macOS the kernel's sandbox (`sandbox-exec` profile: no network, no new processes, writes only under `files/` and the bench's scratch). On Linux and Windows only the hook applies. | The hook alone is not a boundary — a cell written to defeat it can (tested: it reaches the hook's state through `gc` and switches it off); the kernel layer holds when it does. `sandbox-exec` is deprecated by Apple but present and working on current macOS. | ◆ Accept that only macOS has the kernel layer until a Linux/Windows bundle exists (Q4). |
| S3 | **Each code cell starts in a fresh namespace.** State between cells passes through `FILES` or is recomputed; helpers are fast with the descriptor cache. | Re-run in order (D4) gives the same outputs whether or not earlier cells were re-run; a stored cell is reproducible alone. | ◆ §5: add "a code cell runs in a fresh namespace; nothing but `files/` carries between cells". |
| S4 | **A question cell names its question by `test_index`** into the study's `tests[]` (the Spec 06 study document), not by carrying `test_id`/`params`/`result` itself; a question added as a cell may carry its own `slices` (selection, rules, hand slices), else it uses the study's. | One home for a question's definition and result: hand studies, the Spec 06 page and the notebook read the same `tests[]`; a notebook's questions can ask about different slice sets. | ◆ §5's example: `{ "id": "c3", "kind": "question", "test_index": 0 }`, the question in `tests[0]` with an optional `slices`. |
| S5 | **`ran.flights` holds the flight ids a cell read** (every helper records what it touches), not content fingerprints. With `ran.engine` it is what "ran against" means; re-run marks a cell *pending* only when its outputs differ. | Flight ids are stable across re-imports of the same log (Spec 02); an analysis change shows as an engine version change. | ◆ §5's example: `"flights": ["<flight_id>", …]`. |
| S6 | **`code_run` is a server-host operation** (Spec 04 §9.5 `_HOST_ONLY`): the browser host answers `UNSUPPORTED_IN_HOST`, and `get_capabilities` has `bench: false`. A server host running under Pyodide (the Node conformance run) answers `NOT_SUPPORTED`. | Spec 04's rule for an operation a host lacks; the UI gates on the capability, never on the host. | ◆ §4.3: "the Pyodide path answers `UNSUPPORTED_IN_HOST` (Spec 04 §9.5); `bench` is false". |
| S7 | **The scan runs lazily**: `inbox_list` rescans when the workspace's fingerprint (flights, engine version, sensitivity) has changed since the last scan; `inbox_scan` scans on demand; imports don't call it. | "After each import" without making an import wait 6–11 s (cold) for it; a cached rescan is 0.1 s. | ◆ §6 Scan: "when the inbox is next read after an import, and on demand". |
| S8 | **Sensitivity** maps to N of M and the shift threshold: *quiet* 8 of 10 and 2.0 × Spec 12's outlier threshold, *normal* 6 of 10 and 1.5 ×, *curious* 4 of 10 and 1.0 ×. Stand-out is robust z ≥ 3.5 against ≥ 10 older slices; group apart is two or more descriptors past 0.75 of the shift threshold. Stored as the workspace setting `research_sensitivity` (default *normal*, carried by export). | Normal is D5's default; on the G3X-only part of the real set as of 2026-10-05, quiet/normal/curious raise 4/5/8 candidates. | ◆ The multipliers and the stand-out z. |
| S9 | **Comparisons are within source**: stand-out against older slices of the same source; a shift within the recent window's dominant source, skipped (and said so in the scan's info) when it has fewer than 10 older flights of that source. | G3X damps MAP and its rpm resolution differs from AXIS: across sources the scan found the source change, not the engine. | — |
| S10 | **Scan scope**: channels rpm, MAP, fuel flow; descriptors swing and median; the recurring-period check on the governed-rpm presets (full power, governed climb, stable cruise). | The descriptors the Spec 06 presets were measured on; a period is meaningful where the governor holds rpm. | ◆ The scope. |
| S11 | **`documents/` is local**: not carried by workspace export or `.eisstudy` (marked *local* in Spec 02's table). | The files are the user's own copies of manuals; an export to a friend must not carry an OM. | ◆ §4.4 / Q3. |
| S12 | **Code-cell outputs and `files/` travel** with the study: in `.eisstudy` and in workspace export (`studies/*/files/*`). | D8: a shared notebook keeps the author's results until the recipient runs it. | — |
| S13 | **`list_flights` takes `summary: true`** (source, flight facts, minutes per phase, event count) so `flights_list` maps onto one operation; omitted, the result is unchanged. | §4.2 asks for a phase summary; a façade computes nothing. | — |
| S14 | **The aircraft document has no registration field**; the tail number stays in the logs (Spec 01 §10). Fields: airframe, engine serial, propeller, prop controller, firmware, avionics, notes; 2000 characters each. | Nothing the investigation needed; one less identifying fact in an export. | — |
| S15 | **The MCP transport is written in the package** (newline-delimited JSON-RPC over stdio, protocol versions 2024-11-05 to 2025-11-25), no SDK dependency; the data root is re-read on every call, so a workspace switched to in the pages is the one the next tool sees; `--serve` starts the web server on a thread of the same process (§7's shape). | One fewer dependency in the bundle; the tool surface is small and fixed. | — |
| S16 | **matplotlib's cache is per user** (`~/Library/Caches/SlingologyEIS/matplotlib`, XDG elsewhere), not per data root. | It describes the machine's fonts; building it costs ~10 s once. | — |
| S17 | **The scientific stack is an optional extra** (`pip install slingology-eis[investigations]`: scipy, matplotlib, pypdf; `dev` includes it); the engine and the browser runtime need none of it. | The website bundle and a plain CLI install stay small. | — |
| S18 | Spec 16 D2 says Spec 06 Session C was withdrawn; it was built (Spec 06 v0.7: Signal view, Compare) before this spec was written, and its operations are the `signal_analyze` / `rows_compare` tools. | Recorded so the two specs agree. | ◆ D2: "…the v0.6 Signal/Compare screens stay as built (Spec 06 v0.7) and are not extended; their operations are tools." |

## 4. The MCP server (D1, D3, D7)

### 4.1 Transport and process
A third front door to the host (Spec 04): `slingology-eis mcp` runs the MCP server over stdio in the same process as the engine and, in the extension, the web server (§7). Every tool is a thin façade over a Spec 01 host operation or a composition of them; results are the operations' JSON, trimmed to summaries where §4.2 says so. The host is unchanged except for the new operations §4.3 lists. Capability gating: the surface is present only when a workspace is open; otherwise every tool answers *no workspace yet — open the EIS pages at 127.0.0.1:8420*.

### 4.2 Tool surface (D7)

| Layer | Tool | Returns | Notes |
|---|---|---|---|
| Raw material | `flights_list` | flights with header facts and phase summary; filters by date, source, airport, engine hours | paged |
| | `flight_get` | one flight: header, phases, events, flight facts, topic findings | — |
| | `series_get` | channels over a window of one flight | refuses more than a cap of samples without a window and says why; decimated above the cap when a window is given |
| | `fleet_metrics` | the Spec 12 per-flight metrics table | paged |
| | `trends_summary` | the change summary and shift history | — |
| Instrument | `presets_list`, `slices_build`, `samples_get`, `question_run`, `signal_analyze`, `rows_compare` | Spec 06 §11 operations | `samples_get` capped as `series_get` |
| Bench | `code_run` ✎ | stdout, returned tables, figures; written as cells into the named study | D3 envelope; declared as writing |
| Context | `profile_get`, `aircraft_get` | engine profile; aircraft configuration (Settings → Log channels, airframe/prop/controller fields — new, §4.4) | — |
| | `documents_list`, `document_read` | files the user placed under the workspace's `documents/`; `document_read` returns pages | never whole manuals |
| | `journal_list`, `studies_list`, `study_read` | as the UI shows them | notebook cells included |
| Record | `study_create` ✎, `cell_append` ✎, `study_finish` ✎ | notebook writing (§5) | — |
| | `inbox_list`, `inbox_resolve` ✎ | candidates with evidence and status; resolution | §6 |

Rules: every result carries engine version and workspace id; writing tools (✎) are marked so Claude Desktop asks before first use; no tool deletes logs, changes filters, limits or settings, or writes Journal entries other than study findings. Series caps and page sizes are parameters recorded in the spec after Session D.

**As built (Session D).** 24 tools (`slingology-eis mcp tools` lists them). Each calls the operation(s) named and returns its JSON after the trim stated; the parity test re-applies each trim to the operation's JSON fetched independently. Every result is `{engine_version, workspace_id, result}` (text and structured content alike); a refusal (a cap, a missing argument, an operation's error code) is a tool error whose text says why and what to ask instead. Annotations: ✎ tools `readOnlyHint: false`, all others `true`; none destructive; none open-world.

| Tool | Operation | Trim and caps |
|---|---|---|
| `flights_list` | `list_flights` (`summary: true`) | flat rows (date, engine hours, airport, source, filename, flight facts, minutes per phase, events, quality notes); filters `date_from`/`date_to`, `source`, `airport`, `hours_min`/`hours_max`; pages of **50** (`offset`, `limit` ≤ 50) |
| `flight_get` | `get_flight` | header, phases and minutes per phase, facts (value, unit), events (the limit/CAS fields the Events list shows), available channels, quality, enabled topics (analysis text, insights, triggers), reference state |
| `series_get` | `get_flight_series` (`max_points` 600) | ≤ **6** channels; ≤ **600** points per channel: a window of ≤ 600 s at every row, a longer one as the 600-point min/max envelope (`decimated: true`); without a window refused for a flight longer than 600 s; columnar `{t_s[], value[]}` |
| `fleet_metrics` | `get_fleet` | one row per flight (engine-hours order) with the chosen metrics (default all but `limit_*`); each metric's baseline, trend, outliers, shift; pages of 50 |
| `trends_summary` | `get_fleet` | the change summary, each ranked metric with baseline/trend/outliers/shift; the shift history |
| `presets_list` | `list_slice_presets` | as is |
| `slices_build` | `build_slices` | set summary (count, by source, windows, missing), rule ids; slices (ids, span, context, descriptors) in pages of 50 |
| `samples_get` | `get_slice_samples` | as is under **6000** values (slices × seconds × channels); above it refused, pointing at `slice_ids` or `code_run` |
| `question_run` | `run_test` | finding, magnitude, caveats, summary, params, slice-set summary, references, evidence columns; evidence rows in pages of 50 (the duplicate `per_slice` dropped) |
| `signal_analyze` | `analyze_signal` (`include_values: false`) | strips summarised as lit runs per channel (start, end, median period, max swing; ≤ **40** runs); the window's context, descriptors, numbers with references, derived rule; diagnostics as periods, the **5** strongest periodogram peaks and the correlation at the best lag (detrended series, ACF and lag curve dropped) |
| `rows_compare` | `compare_rows` | set and pin summary, deltas, OM limits; groups as (flight, date, source, count); rows in pages of 50 |
| `code_run` ✎ | `code_run` | the cell: status, `ran`, outputs with stdout/stderr ≤ **8000** characters (head kept, `clipped`), tables ≤ 50 rows, traceback ≤ 20 lines; up to **4** figures as PNG image blocks (the study keeps every output whole) |
| `profile_get` | `get_engine_limits` | as is |
| `aircraft_get` | `aircraft_get` | as is |
| `documents_list` | `documents_list` | as is |
| `document_read` | `document_read` | as is: ≤ **3** pages and ≤ **12 000** characters per read; `find` → ≤ 20 pages with 240-character snippets |
| `journal_list` | `get_journal` | entries (the fields the Journal shows) in pages of 50 |
| `studies_list` | `list_studies` | as is |
| `study_read` | `load_study` | the definition without the descriptor cache; questions' results as `question_run` trims them with ≤ 10 evidence rows; markdown and streams ≤ **2000** characters |
| `study_create` ✎ | `save_study` | a notebook (`kind` investigation or question-for-type, `author: claude`, question, optional inbox candidate); returns its id |
| `cell_append` ✎ | `study_cells_append` | the cell, and a question's result trimmed as `question_run` |
| `study_finish` ✎ | `study_finish` | as is (summary, inbox resolution, Journal study finding) |
| `inbox_list` | `inbox_list` | as is |
| `inbox_resolve` ✎ | `inbox_resolve` | as is |

### 4.3 New host operations
`code_run` (D3), `study_cells_*` (D4), `inbox_scan` / `inbox_list` / `inbox_resolve` (D5), `aircraft_get` (§4.4), `documents_*`. All on the Spec 01 envelope, covered by the operations tests all three ways; the Pyodide path implements `code_run` as `NOT_SUPPORTED` (D8).

As built (Spec 01 lists their parameters): `code_run`; `study_cells_append`, `study_cells_rerun`, `study_cells_accept`, `study_cells_discard`, `study_finish`; `aircraft_get`, `aircraft_set`; `documents_list`, `document_read`, `document_add`, `document_remove`; `inbox_scan`, `inbox_list`, `inbox_resolve`. `export_study` gains `format: "ipynb"`; `list_flights` gains `summary` (S13). The browser host answers `code_run` with `UNSUPPORTED_IN_HOST` (S6). Capabilities: `investigations` (both hosts), `bench` (server host with worker processes).

### 4.4 Aircraft configuration
A small per-workspace document (Settings → Aircraft): airframe, engine serial, propeller and controller models, firmware versions, avionics — the facts the oscillation investigation needed on its first line. Free text fields; aircraft-neutral in the UI; returned by `aircraft_get`. Carried by export.

### 4.5 The code tool (D3)
Runs a cell of Python in the engine process with a prepared namespace: the workspace handle, helpers to load a flight's series or a slice set as pandas frames, the engine profile, and the scientific stack. Envelope: no network (sockets disabled), no subprocesses, file writes only under `workspaces/<id>/studies/<study>/files/`, wall-clock and memory caps (defaults recorded after Session D), captured stdout, returned objects rendered as table cells (frames) or figure cells (matplotlib figures as SVG). The executed source, its outputs, timing, engine version and the fingerprints of the flights it touched are stored as the cell. Errors are returned as cell output, not as tool errors, so the investigator can read and retry.

**As built (Session D; §9 Q2).**

- *Caps*: wall clock 60 s by default, 1–300 s per cell (`timeout_s`); memory 2048 MB by default, 256–8192 MB (`memory_mb`), as the worker's peak resident size; stdout and stderr kept to 100 000 characters each in the cell; tables to 500 rows (`n_rows` says how many there were); figures as SVG in `files/fig-<hash>.svg`, with a 72-dpi PNG returned to the investigator only. A cell stopped at a cap keeps what it printed and ends with an error output saying which cap (`ran.status`: `timeout`, `memory`).
- *Namespace*: `np`, `pd`, `plt` (Agg), `matplotlib`, `scipy` (`scipy.signal`, `scipy.stats` loaded); `ws`; `flights()`; `flight_info(id)`; `load_flight(id, channels=None, start_s=None, end_s=None)` (the 1-second grid Research slices from, index `t_s`, column `filled`); `load_slices(rule="full_power", channels=None, flights=None)` (one row per slice, descriptors as `channel.descriptor`); `load_slice_samples(rule, channels=None, flights=None, anchor="crossing")` (long form); `profile`; `aircraft`; `study`; `FILES`; `show(obj, title=None)`. A rule is a preset id, `"phase:CLIMB"` or a §5.1 rule object. The value of a cell's last expression is an output, as in Jupyter. Each cell starts afresh (S3).
- *Enforcement*: a worker process per cell (S1) with a minimal environment, started in its own process group (the wall-clock cap kills the group), a watchdog on resident memory, and two layers (S2): (1) a PEP 578 audit hook installed before the cell runs — refuses socket, ctypes, `subprocess`/`os.system`/`os.exec*`/`posix_spawn`/`fork`/`kill`, `http.client`, `urllib` and `webbrowser` events, a second audit hook, and any open-for-writing, remove, rename, mkdir, chmod or similar outside `files/`; `_posixsubprocess.fork_exec` (which raises no audit event) is replaced and fresh loads of `_posixsubprocess`, `_ctypes`, `_socket`, `_ssl` refused; (2) on macOS, the kernel's sandbox profile: network denied, process fork and exec denied (but the interpreter's own start), file writes denied outside `files/`, the bench's scratch and the matplotlib cache.
- *What it cannot enforce*: **reads are not confined** — a cell can read any file the user can, and what it prints goes to the investigator (Claude) and into the study; **on Linux and Windows the hook is the only layer**, and the hook is not a security boundary: Python code in the same interpreter can reach and disable it (demonstrated in the tests, where on macOS the kernel layer then refuses); the memory cap samples resident size, so a sudden allocation can overshoot before the process is stopped; CPU use within the wall clock is not limited; the envelope guards against mistakes and casual misuse in code the user can read before approving, not against code written to escape on a platform without the kernel layer.

## 5. The notebook study (D4)

The Spec 06 study document gains:

```jsonc
"cells": [
  { "id": "c1", "kind": "markdown", "source": "…" },
  { "id": "c2", "kind": "code", "source": "…", "outputs": [ { "kind": "text" | "table" | "figure", … } ],
    "ran": { "engine": "…", "flights": ["<fp>", …], "at": "…", "ms": 0 }, "pending_outputs": null },
  { "id": "c3", "kind": "question", "test_id": "cycling", "params": { … }, "channels": ["rpm"], "result": { /* §8 block */ } },
  { "id": "c4", "kind": "figure" | "table", "ref": "files/…" }
],
"kind": "hand" | "investigation" | "question-for-type",
"author": "user" | "claude", "question": "the question as asked"
```

- A **hand study** (Spec 06 UI) is a notebook whose cells are its questions; existing studies load unchanged.
- **Re-run** executes cells in order against the current workspace: question cells recompute; code cells run only where a bench exists (server/extension), producing `pending_outputs` beside the stored outputs until the user accepts or discards them; on the website code cells are marked *ran elsewhere*.
- `.eisstudy` carries cells and `files/`; read-only import and *Run this on my flights* apply per cell (D8).
- `kind: "question-for-type"` marks a shared notebook as a question to ask of any engine of the profile's type (D9); Research home lists these separately.
- **Export to `.ipynb`**: one-way, code and markdown cells with outputs; question cells become markdown with their §8 result.
- Rendering: one component for both tiers (Research page); narrative, code with outputs, question results in the §8 layout, figures, tables; the study header shows author, question, engine version, and whether outputs are current for this workspace.

## 6. The inbox and cadence (D5)

- **Scan** (`inbox_scan`): after each import, and on demand. Over each preset's slices in Trends' recent window (Spec 12: last 10 engine hours, ≥ 5 flights, capped at 15): (a) **recurring pattern** — a prominent period in a governed-rpm preset, or any descriptor standing out (Spec 06 §7.4 within source), in ≥ N of M recent slices; (b) **shift** — a descriptor's recent median vs the fleet reference by Spec 12's shift statistic beyond its threshold; (c) **group apart** — recent slices clustering away from the reference on two or more measurements. Each candidate: preset, descriptor(s), the slices involved, the evidence table, the parameters that fired, sensitivity level.
- **Gating**: defaults N of M = 6 of 10; one open candidate per preset-and-descriptor; a resolved candidate returns only after the recent window has moved on by half its flights; three-position sensitivity *quiet / normal / curious* (Settings → Research) mapping onto N, M and the shift threshold, shown on every candidate. The investigator may propose a change in a notebook; only the user changes it.
- **Document**: `workspaces/<id>/inbox.json` — candidates with status *new / investigating / nothing-here / watch / acted*, linked study, resolution note, dates; carried by export.
- **Reading**: `inbox_list` (filter by status), `inbox_resolve` (status, study link, note). Research home shows the inbox on both tiers (D8). Scheduling is the user's own Claude task (*"Sundays, review new EIS inbox items"*); EIS schedules nothing and never calls out.
- **Not an inbox item**: a single odd flight (Flight view), a limit event (Events), a Trends shift already on the Trends page (the inbox links to it rather than repeating it).

## 7. The Claude Desktop extension (D6)

- **Bundle**: standalone Python runtime, the EIS wheel with dependencies, the built web UI, the MCP server entry; one bundle per platform (macOS arm64, macOS x86-64; Windows later), built in CI beside the wheel and static site, attached to the GitHub release. Mechanics (manifest, runtime declaration, user configuration for the log folder) to be verified by Code against current Claude Desktop extension documentation and recorded here.
- **Process**: Claude Desktop starts one process when a chat with the connection opens: MCP over stdio plus the EIS web server on 127.0.0.1:8420; stops it when Desktop does. Logging to a file under the data root.
- **Data**: the server-mode data root (Spec 02 §5.8.1); a pip install and the extension share it. Log folders chosen in the extension's settings or in the EIS pages — one registry. First run: tools answer *no workspace yet*; the pages show the first-workspace flow.
- **Install**: one click in Claude Desktop's extensions from the release asset; the docs' Investigations page links it beside the sample workspace. Signing deferred.

> **Interim (until Session E's bundle): running the server from a dev install.** Install the engine with the extra (`pip install -e ".[investigations]"` in the checkout's venv). In Claude Desktop → Settings → Developer → Edit Config, add to `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`):
>
> ```json
> {
>   "mcpServers": {
>     "slingology-eis": {
>       "command": "/Users/<you>/src/Rotax9iSEIS/.venv/bin/slingology-eis",
>       "args": ["mcp"],
>       "env": { "SLINGOLOGY_EIS_HOME": "/Users/<you>/EIS-dev-data" }
>     }
>   }
> }
> ```
>
> and restart Claude Desktop. `env` picks the data root (Spec 02 §5.8.1); leave it out to use the one the pages use. Add `"--serve"` to `args` to have the same process serve the pages on 127.0.0.1:8420 (don't, while `slingology-eis serve` is already running there). The server logs to Claude Desktop's MCP log (`~/Library/Logs/Claude/mcp-server-slingology-eis.log`). Check the surface without Claude: `slingology-eis mcp tools`, `slingology-eis mcp call flights_list '{"limit": 3}'`. This note is for development and goes when §7's bundle exists; it is not user documentation.

## 8. Acceptance

The oscillation investigation redone end to end by Claude Desktop through the tools, on the owner's workspace (flights dated through 2026-10-28), from one question in words. Checked by reading the resulting notebook:

1. The notebook identifies the full-power segments across the workspace (98 slices), the cycle (period 3.5–4.1 s, swing ≈ 180 rpm, recurrence ≥ 90 of 98), the rpm–MAP coupling at lag 0 with the per-source caveat, and the altitude dependence — each with a cell whose output states it.
2. It reads the engine deck from the OM placed in `documents/` (the owner's copy) and states the boost schedule between 5,500 and 5,800 rpm with a page citation.
3. It states the mechanism as a hypothesis and names at least two alternatives it tested and ruled out, each with the cell that did so.
4. It ends with what it means and what to do, without verdict words unreferenced (Spec 06 §8 rendering test extended to notebooks).
5. The notebook re-runs on the workspace with identical outputs; exported as `.eisstudy`, imported into a workspace lacking the flights it opens read-only per cell; *Run this on my flights* on another workspace re-executes question cells and marks code cells.
6. `code_run` refuses network and subprocess access and writes outside the study folder; a runaway cell is stopped at the cap with its partial output kept.
7. The scan on the owner's workspace emits the full-power rpm cycle as a *recurring pattern* candidate at *normal* sensitivity and emits no candidate from a nominal synthetic workspace; resolving it *nothing-here* keeps it out until the window moves on.
8. Every tool runs from the CLI with byte-identical JSON (Spec 04 parity); the Pyodide host answers `code_run` with `NOT_SUPPORTED` and renders a notebook with stored outputs (D8).
9. The extension installs on a clean Mac with one click, opens the pages at 127.0.0.1:8420, and Claude Desktop lists the tools (Session E).

## 9. Open questions

| # | Question | Leaning |
|---|---|---|
| Q1 | Series cap and page sizes for `series_get`, `samples_get`, `document_read` | **Resolved (v0.3):** pages of 50 rows; `series_get` ≤ 6 channels × 600 points; `samples_get` ≤ 6000 values; `document_read` ≤ 3 pages / 12 000 characters; the rest in §4.2 *As built*. |
| Q2 | Code tool caps (wall clock, memory) and the prepared namespace's helper names | **Resolved (v0.3):** 60 s (1–300), 2048 MB (256–8192); helpers in §4.5 *As built*. |
| Q3 | Where `documents/` lives and whether the website tier can hold documents (OPFS size) | Workspace folder; website: yes, same limit as logs. |
| Q4 | Windows bundle | After the macOS bundles are proven. |

## 10. Relationship to other specs

- **Spec 06** owns the instrument and keeps its constraint: the instrument ships no rule beyond the OM. Spec 16 adds no rules either; the inbox's scan is Spec 06 §14.1's, parameterised by the user.
- **Spec 04**: the MCP server is a third transport over the same host operations; browser mode is unchanged.
- **Spec 02**: notebook studies and the inbox are workspace documents, carried by export.
- **Spec 03**: the Research view renders notebooks; the inbox is a section of Research home; nothing is added to Flight view.
- **Program principles (Oct 4 2026)**: the user controls what is investigated and what is concluded; EIS enforces no severity policy; the OM is the only predefined rule.

## 11. Implementation plan

Branch `research`, after the Spec 06 v0.7 cut.

- **Session D — engine:** the new host operations (§4.3) including `code_run` with its envelope, the notebook extension of the study document (§5) with re-run semantics and `.ipynb` export, the aircraft document (§4.4) and `documents/`, the inbox scan and document (§6), the MCP server over stdio with the curated surface (§4.2) as a façade with a parity test against the host, CLI `slingology-eis mcp`; `analyze_signal` and `compare_rows` from Spec 06 §11; acceptance 6–8, and 1–5 run by the owner through Claude Desktop against a dev install (the MCP server configured by hand in Claude Desktop, before the bundle exists).
- **Session E — extension and web:** the self-contained bundle in CI (§7), the notebook renderer on the Research page for both tiers, the website inbox (D8), Settings → Aircraft and Settings → Research (sensitivity), docs: Investigations page completed, the install walkthrough, the inbox page; acceptance 9 and the D8 items.
