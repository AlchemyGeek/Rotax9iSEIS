# Spec 16 — Investigations

**Project:** SlingologyEIS
**Status:** Draft v0.2 — decisions D1–D9 closed (Nov 14 2026); §4–§8 specified. Session D (engine: MCP server, code tool, notebooks, inbox scan) ready to prompt; Session E (extension bundle, notebook rendering on the website) follows.
**Suggested repo path:** `docs/specs/16-investigations.md`
**Builds on:** Spec 06 (the Research instrument: slices, descriptors, questions, studies, `.eisstudy`, operations), Spec 01 (§7 operations envelope, §10 privacy), Spec 02 (workspace layout, export/import), Spec 04 (two hosts; server mode and browser mode), Spec 03 (principle 6), Spec 10 (§10 proposals, lifecycle)
**Revises:** Spec 06 (§14.2 Investigations and detectors move here; Session C withdrawn), Spec 04 (a third front door to the engine: the MCP server), Spec 02 (a notebook study document and an inbox), Spec 03 (the Research view renders notebooks; an inbox)
**Model case:** the owner's takeoff RPM/MAP oscillation investigation, done with Claude and scripts in October 2026 (`docs/research/2026-10-takeoff-rpm-oscillation.md`) — what an investigation should look like when the app is the instrument.

**Revision history**

| Version | Change |
|---|---|
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

### 4.3 New host operations
`code_run` (D3), `study_cells_*` (D4), `inbox_scan` / `inbox_list` / `inbox_resolve` (D5), `aircraft_get` (§4.4), `documents_*`. All on the Spec 01 envelope, covered by the operations tests all three ways; the Pyodide path implements `code_run` as `NOT_SUPPORTED` (D8).

### 4.4 Aircraft configuration
A small per-workspace document (Settings → Aircraft): airframe, engine serial, propeller and controller models, firmware versions, avionics — the facts the oscillation investigation needed on its first line. Free text fields; aircraft-neutral in the UI; returned by `aircraft_get`. Carried by export.

### 4.5 The code tool (D3)
Runs a cell of Python in the engine process with a prepared namespace: the workspace handle, helpers to load a flight's series or a slice set as pandas frames, the engine profile, and the scientific stack. Envelope: no network (sockets disabled), no subprocesses, file writes only under `workspaces/<id>/studies/<study>/files/`, wall-clock and memory caps (defaults recorded after Session D), captured stdout, returned objects rendered as table cells (frames) or figure cells (matplotlib figures as SVG). The executed source, its outputs, timing, engine version and the fingerprints of the flights it touched are stored as the cell. Errors are returned as cell output, not as tool errors, so the investigator can read and retry.

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
| Q1 | Series cap and page sizes for `series_get`, `samples_get`, `document_read` | Set in Session D from Claude's context budget; record here. |
| Q2 | Code tool caps (wall clock, memory) and the prepared namespace's helper names | Set in Session D; record here. |
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
