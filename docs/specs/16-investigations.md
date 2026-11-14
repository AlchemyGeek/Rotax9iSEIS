# Spec 16 — Investigations

**Project:** SlingologyEIS
**Status:** Draft v0.1 — skeleton. The model (§1–§3) and decisions D1–D2 are taken (Nov 14 2026); D3 onward are open and listed in §9 in the order they will be taken. No code until the decisions close.
**Suggested repo path:** `docs/specs/16-investigations.md`
**Builds on:** Spec 06 (the Research instrument: slices, descriptors, questions, studies, `.eisstudy`, operations), Spec 01 (§7 operations envelope, §10 privacy), Spec 02 (workspace layout, export/import), Spec 04 (two hosts; server mode and browser mode), Spec 03 (principle 6), Spec 10 (§10 proposals, lifecycle)
**Revises:** Spec 06 (§14.2 Investigations and detectors move here; Session C withdrawn), Spec 04 (a third front door to the engine: the MCP server), Spec 02 (a notebook study document and an inbox), Spec 03 (the Research view renders notebooks; an inbox)
**Model case:** the owner's takeoff RPM/MAP oscillation investigation, done with Claude and scripts in October 2026 (`docs/research/2026-10-takeoff-rpm-oscillation.md`) — what an investigation should look like when the app is the instrument.

**Revision history**

| Version | Change |
|---|---|
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

## 4. The MCP server — *to be specified after D3*

## 5. The notebook study — *to be specified after D4*

## 6. The inbox and cadence — *to be specified after D5*

## 7. The Claude Desktop extension — *to be specified after D6*

## 8. Acceptance — *the model case, reproduced by an investigator through the tools*

The acceptance of this spec is the oscillation investigation redone end to end by Claude Desktop against the MCP server on the owner's workspace: from the question in words to a notebook study that states the mechanism, the altitude dependence and the per-takeoff evidence, with every number traceable. Criteria are written once the decisions close.

## 9. Open decisions, in order

| # | Decision | What it settles |
|---|---|---|
| D3 | **Scope of the code tool.** Python in the engine process with the workspace loaded; what it may import, how long it may run, whether it may write files, how its outputs become notebook cells. | The bench: the one capability that lets the investigator compute what nobody packaged. Also the safety envelope on the user's own machine. |
| D4 | **The notebook format.** Cell types, how figures and tables are stored, how a hand study (Spec 06 §10) and an investigator study unify, re-run semantics, `.eisstudy` carrying code. | The record and its sharing. |
| D5 | **The inbox and cadence.** What the deterministic scan emits, gating parameters and their defaults, the inbox document, what "nothing here" records, how a scheduled Claude task reads it. | Proactive without noise. |
| D6 | **The extension and its install.** The bundle's contents (engine, web UI, MCP server), the one-click install, where the workspace lives, how the served EIS pages and the MCP server start and stop, logging. | The advanced tier's one step. |
| D7 | **Tool surface and naming.** The exact tool list per layer, read-only vs writing tools, what context tools return (sizes), rate and size limits for series. | The instrument's API as Claude sees it. |
| D8 | **What the casual website shows of investigations.** Rendering notebooks made elsewhere (imported), the inbox without an investigator, the invitation to install. | The website stays useful and honest about what it lacks. |
| D9 | **Shared detectors.** Whether a finished notebook can be promoted to a rule that runs in the scan, and how it travels. | The community mechanism beyond shared studies; may be deferred. |

## 10. Relationship to other specs

- **Spec 06** owns the instrument and keeps its constraint: the instrument ships no rule beyond the OM. Spec 16 adds no rules either; the inbox's scan is Spec 06 §14.1's, parameterised by the user.
- **Spec 04**: the MCP server is a third transport over the same host operations; browser mode is unchanged.
- **Spec 02**: notebook studies and the inbox are workspace documents, carried by export.
- **Spec 03**: the Research view renders notebooks; the inbox is a section of Research home; nothing is added to Flight view.
- **Program principles (Oct 4 2026)**: the user controls what is investigated and what is concluded; EIS enforces no severity policy; the OM is the only predefined rule.
