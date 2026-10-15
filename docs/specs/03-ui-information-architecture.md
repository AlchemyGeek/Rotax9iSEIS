# Spec 03 — UI Information Architecture

**Project:** SlingologyEIS web platform
**Status:** v0.18 — implementation in progress (`web/src/views`, against the local-server adapter); §4, §5.2, §5.5–§5.7 realigned with Spec 14 as implemented on `webui` (`ac62b20`…`282631c`)
**Suggested repo path:** `docs/specs/03-ui-information-architecture.md`
**Builds on:** Spec 01 — Engine Contract v0.4; Spec 02 — Results Bundle & Workspace v0.7; Spec 04 — Runtime Adapters & Pyodide Spike v0.3 (GO); Spec 14 — Settings, Journal, and Rule Editing on the Card v0.3 (for §4, §5.2, §5.5–§5.7)
**Resolves:** Spec 02 Q1 (series caching scope), Spec 02 Q5 (read-only bundle preview)

**Revision history**

| Version | Change |
|---|---|
| 0.1 | Initial draft. |
| 0.2 | §6.1 corrected: Flight view's timeline is one overlaid chart with each channel indexed to its own 0–100% range and a synced-cursor readout for real values, not stacked per-channel sub-charts. The wireframe went through both stacked and overlaid forms during review; this document should describe the current one. See Spec 05 v0.2 for the fuller account of why. |
| 0.3 | §5.2: severity tags follow the *topic*, not the section — a card in Analysis carries the same severity dot/label as its Insight-list counterpart when `insight != null`, using the shared token set (below); a topic with `insight == null` gets no tag anywhere, in either section. The insight list itself only lists topics with a real fired insight — a no-insight topic is never given a synthetic `info` entry just to appear there. Severity token values fixed: `info` `#64748B`, `watch` `#FDE047`, `warning` `#F5A524`, `limit` `#E5484D`; `warning`/`limit` render as a small triangle, `watch`/`info` as a circle, so severity isn't color-only. (`watch` was originally `#EAB308`, too close to `warning`'s `#F5A524` to distinguish at insight-card scale — changed after review.) |
| 0.4 | §5.2/§6.1: the phase band must recompute against the *visible zoom window*, not the full flight — a wireframe pass initially left it static (full-flight proportions, unchanged by zoom), which made its label nonsensical once zoomed. The full-flight phase overview moved to the minimap instead, so zooming loses no context. |
| 0.5 | §5.2: full 11-phase color palette fixed (below), one hue per phase, none colliding with the severity or channel-color tokens. Text moved out of the phase band itself into a caption line and a persistent, always-shown legend key — the band communicates by color alone, at any zoom size, rather than by fitting a label into whatever width happens to be available. |
| 0.6 | Multi-workspace (Spec 02 v0.5) lands here: §4's nav was wrong — "Flights" pointed straight at single-flight detail, which is not what a log browser is. New §5.1 **Flights tab** (the log browser: every flight in the active workspace, its status, whether it feeds baselines) replaces the old direct link; individual flight detail (old §5.1's numbering, now §5.2 "Flight view") is reached by clicking a row, not from the nav. Import (old §5.1) folds into the Flights tab as a banner + drop zone rather than a separate destination — kept only as a lightweight drop-anywhere shortcut, mainly for Safari. Workspace switcher added to the nav shell, permanent, not buried in Settings. Baselines' fleet-selection panel and Trends' sample count now link out to Flights instead of keeping their own lists. No wireframe yet for the new Flights tab — Spec 02 §3's original proposal is detailed enough (table columns, statuses, filters) to build from prose; flagged as a real gap, not a blocker. |
| 0.7 | §5.2/§6.1: Flight view's timeline drops from two navigational bars to one. The standalone "current zoom phase" band is gone — redundant with the minimap without adding real function of its own. What it showed now lives as a tint on the main chart's own background, directly behind the data, updated on every zoom/pan from the same phase-segment calculation the minimap already used. Net: one fewer element, no loss of either the full-flight overview or the current-window detail. |
| 0.8 | New principle 6 (§3): casual and researcher personas share one active configuration per workspace and diverge only in which surfaces they visit — casual stays on Flights/Flight view/Trends/ECU with no visible tuning; researcher tuning lives in Baselines & Models (§5.5, now also naming `outlier_z_threshold` as something the rule playground edits, per Spec 01 §8.4 v0.8); hard separation between the two, when needed, is an experiment workspace, not a mode switch. Also states how a future Research/Explore mode should fit this split once it's designed. |
| 0.9 | §5.4 renamed "ECU investigation" → **Engine ECU CAS Events**, and its "what counts as an event" definition made explicit (an `IN_FLIGHT`-classified occurrence, not any ENGINE ECU alert). A real bug this surfaced, now fixed: Flight view had a `warning`-severity insight built from *ground-context* ECU presence on a flight with zero real in-flight events — corrected per Spec 01 §8.5 v0.9's firing-condition fix. A second real Flight view (the actual flight behind one of the fleet's genuine in-flight events) was built to demonstrate the correctly-scoped case, since the mockup this event's card previously linked to couldn't show it — every event card should link to its own real flight, not a generic stand-in. |
| 0.10 | §5.3: the "Stratify by" toggle finally has a real behavior spec — it never had one beyond a name. Hidden entirely for a non-stratifiable metric, off by default for the 7 that are (per Spec 01 §8.4 v0.10's real `band_kind_by_metric` values), and honest about lower per-band confidence rather than hiding or upgrading it. |
| 0.11 | §5.3: with stratification on, outlier rings come from the per-band outliers (Spec 01 v0.13, R8), so a ringed point and a "watch" insight always use the same comparison. `baseline_deviation` now compares within the flight's band, so the stratified view is the one that matches the insights for stratified metrics. |
| 0.12 | §5.1 aligned with Spec 02 v0.7's two exclusion tiers (§5.11 there). "Ground session (skipped)" removed as a row status — a skipped log never becomes a flight, so it can't be a row; skipped logs (ground session, short flight, corrupt log, user-skipped) get their own **Skipped** panel instead, with read-only preview and Include, as built. The In baselines column is stated to be Tier 2 only. Status header corrected from "no code written". |
| 0.13 | Realigned with **Spec 14** (Settings, Journal, rule editing on the card). §4: Baselines leaves the top-level nav; Annotations becomes **Journal**; Settings is a tabbed section. §5.5 Baselines & models superseded by Spec 14 §5.1 (Settings → Reference & Models) and §7.2–§7.3 (rule editing on the topic card). §5.6 Annotations superseded by Spec 14 §6 (Journal). §5.7 Settings restated as the tabbed section. §5.2 Flight view gains the topic card's triggers disclosure, the reference-contribution header, exclude-from-card and the "reference changed" / "rule changed" markers. Principle 5 restated: the sandbox is the workspace copy of the rules, wherever it is edited, and nothing applies without a fleet-wide preview. Principle 6 restated: the researcher's extra surface is Settings, not a tuning page; all tuning is done where results are shown. §1 and D6 updated to match. Wireframes `Baselines.dc.html`, `Annotations.dc.html`, `Settings.dc.html` superseded. User-facing "baseline(s)" → "reference" throughout. Q2 moot. |
| 0.14 | **Engine ECU view removed** (ECU review 2026-10-13, Spec 10 D19). Everything §5.4 showed is now a CAS event row in the Flight view's events list (§5.2), a frequency panel on Trends (Spec 12 v0.10) and a lane-check line in the flight summary. §5.4 kept as a tombstone; nav sketch, principles 1 and 6, §4 destination list, design-token note and Q5 updated. §5.2 gains the CAS-event row rule: the row names the class and, when the run nearly matches a lane check, why it isn't one. |
| 0.15 | §5.4 rule: lane-check line reads `both lanes ✓` / `one lane only` / `not detected`; the filter scope caption says "this alert" for a CAS target (Spec 14 §7.5). |
| 0.16 | **Flight view review** (2026-10-13, five decisions; Spec 10 D20). §5.2 rewritten: header gains a **Flight facts** row with an admission rule (Spec 10 §4.3); **Events** becomes a first-class section between the chart and the topic cards (one chronological table for limit and CAS events, row actions, filtered events collapsed), and the `limit_exceedances` card shrinks to its sentence and badges; topic cards are **expanded only when they have something to say** (insight, mirrored badge, change marker, validity note) and otherwise a one-line roster entry — the "analysed with nothing to flag" line is dropped as redundant; the rule editor leaves the card for a **side panel** opened from a read-only triggers summary (Spec 14 v0.9 §7.3). The loader-skipped-log preview leaves Flight view for its own read-only **Log preview** page (new §5.9). |
| 0.17 | **Flights review** (2026-10-15, five decisions; two changes). §5.1: the drop zone shows only while the workspace has **no folders**; afterwards it collapses to an **Add logs…** action beside **Sync**, page-wide drop still accepted, progress as a transient banner. **Sync** discovers, then asks before analysing (*Found N new logs and M flights needing re-analysis — Analyze now? / Not now*); deferred work shows as a *Needs analysis* status with a persistent **Analyze N** button. Insights column, Skipped chip-swap and the column set are confirmed unchanged. Also: §5.9 route is by file name (no fingerprint reaches the web); §5.2 roster rule notes that a *reference changed* marker expands every reference-based card while a *rule changed* marker expands only its topic. |
| 0.18 | §5.7: the Settings changelog is removed (Spec 14 v0.13). Changed settings are marked in Settings and listed in Journal as entries; the Engine tab shows the engine version in effect and its *What's new*. |
**Baseline reviewed:** branch `webui` at commit `282631c` (2026-10-11)

---

## 1. Purpose

Specs 01, 02, and 04 built the machine: a typed, stateless engine; a workspace to hold its output; three ways to run it. None of that is visible to a pilot. This spec is the part they actually see — organized around the goal stated at the very start of this project: someone should be able to look at a flight or a fleet and understand what it means, without combing through pages of text output.

It defines the views, what data each one binds to (from Spec 01 §8 and Spec 02's workspace), how they navigate to each other, and the two features that were explicitly part of the original brief but don't fit inside a single "view": **rule editing with a fleet-wide preview** (originally a standalone rule playground; since v0.13 done on the topic card, Spec 14 §7.2–§7.3), and **evidence links** from an insight to the chart or table row that supports it.

**Explicitly deferred to a later spec (or a per-view addendum):** exact visual design (spacing, color palette, typography), the mockups/wireframes themselves, and ECharts option objects. This spec fixes structure and data flow; visual design is a natural fit for the frontend-design skill once implementation starts.

## 2. Decisions this spec builds on and resolves

| # | Decision | Source |
|---|---|---|
| D1 | React + TypeScript + Vite + Apache ECharts. | Design discussion |
| D2 | Browser-compute is primary (confirmed GO); local server is secondary; both share one UI. | Spec 04 |
| D3 | Non-technical target user; the UI is the *only* thing most pilots ever see — the CLI is a contributor/power-user tool. | Spec 01 §7.1 |
| D4 | iPad is a real target, not just a fallback, for the tested device class; still touch-friendly, responsive design regardless. | Spec 04 Appendix B |
| D5 | Every insight must link to the evidence that produced it (chart, table row, event). | Original design brief |
| D6 | The UI is also meant to help *develop* the analysis — editing a rule and seeing its fleet-wide consequence is a first-class feature, not an afterthought. Since v0.13 this lives on the topic card, not a separate page (Spec 14 §7.3). | Original design brief; Spec 14 |
| **R1** | **Resolves Spec 02 Q1.** Series caching: **not cached** in the workspace for v1. `get_series` (Spec 01 §7) re-parses on demand. The spike measured 2.1–2.6 s for a full flight's load+phases+metrics (Spec 04 Appendix A) — well inside what a "open this flight" wait tolerates, and it avoids a second stale-vs-fresh problem alongside `FlightAnalysis` itself. Revisit only if real usage shows re-parsing is a bottleneck. |
| **R2** | **Resolves Spec 02 Q5.** Bundle import gets a **preview mode**: opening a bundle (drag-in, or a "browse community samples" flow) shows its contents in the same flight-view/trends components, tagged read-only, with an explicit "Add to my workspace" action before anything merges. Nothing merges silently. This is a UI-level choice, as Spec 02 anticipated — the bundle format itself is unchanged. |

## 3. Design principles for this spec

1. **Every screen answers a question a pilot actually has**, not a category of data the engine happens to produce. The views in §5 map to "what should I look at," "what happened on this flight," "is this normal," and "what have I decided" (Journal) — the former "what's wrong with the ECU" is answered inside "what happened on this flight" (v0.14); "what is my engine compared against" is configuration and lives in Settings (Spec 14 §5.1).
2. **Insights are the entry point, charts are the evidence.** A pilot lands on a severity-sorted list of things worth knowing, and each one expands into the specific chart window or table row that justifies it (Spec 01 §8.5 `evidence`). Nobody should have to know which of the 14 topics to go looking for.
3. **Nothing computed is ever silently stale.** Any view showing a `FlightAnalysis`, `FleetAnalysis`, or `InsightSet` also shows Spec 02's `stale` flag when true, with one visible action to refresh — never a background recompute the pilot didn't ask for (cost is real: re-running the reference touches every included flight).
4. **Touch-first, not touch-tolerant.** Every interactive chart element has a tap target, not just a hover state; this is required for D4, not optional polish.
5. **Rule edits are a sandbox, not a settings change.** Editing a trigger — on a topic card, Spec 14 §7.3 — never touches the shipped `insight_rules.json` (Spec 02 §6.4), only the workspace's `rules/active.json` copy, and never applies without showing its fleet-wide consequence first. Experimenting is free of consequence and never silent.
6. **Two personas share one computation; they diverge only in which surfaces they visit, never in what the same data produces.** A casual pilot ("load my log, see the results") and a researcher ("diagnose this, tune that, chase an anomaly across many flights") are both real users of this product, and the wrong way to serve both is two modes that can silently disagree about the same flight. There is exactly one active configuration per workspace at any time — one set of thresholds, one rule set, one reference config — and every view reads it. What differs is exposure, not computation:
   - The **casual persona's world** is Flights, Flight view and Trends. Insights appear, outliers are marked; the setting behind a card is a closed disclosure they need never open.
   - The **researcher's world** adds Settings (Spec 14 §5) — the configuration of the computation — and the open disclosures on the same cards the casual pilot sees. There is no separate tuning page: tuning happens where results are shown, with the implication previewed before apply (Spec 14 §7.2–§7.3), and every decision is recorded in Journal (Spec 14 §6). A value a pilot never opens a disclosure to change simply stays at its default.
   - **Workspaces are the hard-separation mechanism**, not a new one invented for this: an experiment workspace (Spec 02 §5.1) already exists for trying things on a subset of one's own logs. A researcher chasing a hypothesis with aggressive settings does it in a workspace built for that, never the one used for a casual view of the same aircraft. This is the same mechanism the multi-workspace model already provides, applied to a case it wasn't explicitly framed around before now.
   - **A future Research mode** (Spec 06, reserved; not in the nav until designed — Spec 14 Q3) should follow the same split: a distinct destination, not woven into the four operational views, so a casual pilot's screens stay exactly as simple regardless of how much experimentation capability eventually sits behind it. It should also have a defined path *out* — a genuine finding becomes a Journal decision or a Settings change carrying provenance, and potentially, per Spec 01 §9's community-extension model, a real Topic. Research mode is upstream of the operational side, not walled off from it.

## 4. Navigation shell

```
┌─────────────────────────────────────────────────────────────┐
│ [Logo]  [Workspace: N117ZS ▾]  Flights Trends Journal ⚙      │  <- top-level nav, always visible
├─────────────────────────────────────────────────────────────┤
│                                                                │
│                     active view                               │
│                                                                │
└─────────────────────────────────────────────────────────────┘
```

**Workspace switcher, permanent in the nav** (new in v0.6, per Spec 02 v0.5's multi-workspace model) — the active workspace's name, a dropdown to the others (Spec 02 §5.2's registry), and "+ New workspace." Not in Settings: switching workspaces is something a pilot managing more than one aircraft does routinely, not configuration they set once. Settings (§5.7, gear icon) still holds per-workspace and app-level settings, just not the switch action itself.

**Three everyday destinations and Journal** (Spec 14 §4, v0.14): Flights (§5.1), Trends (§5.3), Journal (§5.6, Spec 14 §6), plus Settings (§5.7) from the gear icon. The ECU destination is gone (§5.4). Destinations are grouped by what the user is doing — look, decide, configure — not by who the user is. **Baselines is no longer a destination** (v0.13): what it governed is either configuration (Settings → Reference & Models, Spec 14 §5.1) or a decision made on a card (Spec 14 §7). Its old route redirects to Settings → Reference & Models. **Import is no longer a destination** either — see §5.1. Research (Spec 06) is not shown until designed.

**"Flights" now means the log browser**, not a direct link into one flight's detail. This corrects a real mistake in earlier wireframe rounds: the nav's "Flights" pill pointed straight at single-flight detail (now §5.2, "Flight view"), which is a different thing built for a different question. A pilot lands on Flights, sees every flight in the active workspace, and clicks one to reach Flight view — the nav item was never actually wired to the right destination.

A **global stale banner** appears under the nav bar, not per-view, whenever any part of the workspace needs recomputing after an import — "3 new flights imported — recompute reference?" — because staleness after import is a workspace-wide event, not a single view's concern.

## 5. The views

### 5.1 Flights (the log browser)

**Question answered:** "What's in this workspace, and is anything wrong with how it got there?"

Replaces the old standalone Import destination and the never-built "just a list" gap between Import and Flight view. Grounded directly in Spec 02 v0.5's data model — this view is mostly a straightforward rendering of what §5–§6 of that spec already defines, not new design.

- **Header:** active workspace's name, its log folders (each marked reachable/unreachable per Spec 02 §5.5), a **Rescan** action, and a one-line summary — "48 flights · 45 in reference · 2 missing · 1 other aircraft."
- **Adding logs (v0.17).** While the workspace has **no log folders**, the page is the onboarding surface: a large drop zone / file picker ("Drop your G3X logs here", or pick a folder) with **Add folder** — D3's non-technical first run, unchanged. Once at least one folder exists the panel disappears; the header gains **Add logs…** (drop files, or pick a folder — files are the Safari fallback, since it can't retain folder permissions) beside **Sync**, and dropping anywhere on the page still works. Import progress and the post-import summary (duplicates skipped, not-a-flight skipped) appear as a transient banner above the table, dismissable, never a permanent panel. The model stays Spec 02's: the app references logs where the pilot keeps them; a drop is a way to point at files, not to hand them over.
- **Table, one row per flight** (duplicate exports from Spec 01's `flight_id` matching collapse into one row):

  | Column | Content |
  |---|---|
  | Date / route | Apr 23 · KACV |
  | Duration, engine hours | 4h 30m · 38.2h |
  | Insights | count, colored by worst severity (§5.2's severity tokens) |
  | In reference | ✓, or "excluded — <reason>" (Spec 02 §6.3's `excluded` list — Tier 2 of Spec 02 §5.11; toggle lives here, and since v0.13 also on the insight card, Spec 14 §7.1). User-facing word is "reference"; "baseline" stays internal. |
  | Status | see below |
  | Source | filename + folder, on hover/expand |

  Clicking a row opens Flight view (§5.2).
- **Status values**, matching Spec 02 §5.5/§5.6 exactly rather than inventing UI-only states: Analyzed · Needs analysis (discovered, not yet analysed — v0.17) · Needs re-analysis (rules/overrides/engine version changed since last computed — Spec 02 §8's `stale` flag) · Missing log (Spec 02 §5.5 — results kept, charts unavailable) · Folder unreachable ("Locate folder") · Different aircraft (Spec 02 §5.6 — informational only, never excludes) · Unreadable (parse failure).
- **Skipped panel**, separate from the table (Spec 02 §5.11, Tier 1): logs in the workspace's folders that the admission rules kept from becoming flights — ground session, short flight, corrupt log — plus any the pilot skipped. Each shows its category and reason, opens read-only in Flight view so the call can be checked, and has an **Include** action (an override, never a delete). A chip in the header shows the count; the panel's per-log date/duration is fetched only when it's opened, since that re-reads each file.
- **Grouping:** by date (default) or by folder, mirroring how the pilot already organized their own files — no in-app subset filter beyond that, consistent with Spec 02 §5.4's "subsets are made by organizing folders, not by picking in the app."
- **Status chips filter the table** — e.g. show only Missing, or only Excluded.
- **Sync asks before it analyses (v0.17).** **Sync** discovers: new logs in the folders, missing or moved files (re-matched by fingerprint), and flights whose results are stale (rules, overrides or engine version changed — Spec 02 §8). With nothing to do it reports *No changes*. Otherwise it asks once — *"Found 12 new logs and 3 flights needing re-analysis. Analyze now?"* — with **Analyze now** (runs the batch with per-flight progress, as a banner) and **Not now**. Deferred flights appear in the table with status **Needs analysis** (new) or **Needs re-analysis** (stale), and a persistent **Analyze N** button sits beside Sync until the queue is empty. Dropping files goes through the same question when more than a handful are dropped; a single file analyses at once. Spec 03 principle 3: the cost of analysis is real and never paid silently; the pilot sees the count before the wait.
- **Local-server mode difference:** if the host declares folder-watching (Spec 04 §9.2), the drop zone is replaced by "watching `~/SlingologyEIS/logs/`" with the same status feed. Same component; the trigger differs.

### 5.2 Flight view

**Question answered:** "What happened on this flight, and is anything wrong?"

The most-used view, and the one D5 (evidence links) matters most for. Layout (v0.16):

```
┌───────────────────────────────────────────────────────────┐
│ Header: date, duration, aircraft, [stale? refresh],         │
│         Contributes to reference / Excluded (reason)        │
│ Flight facts: fuel burned · cruise nm/gal · cruise gal/hr · │
│               lane check                                    │
├───────────────────────┬─────────────────────────────────────┤
│ Insight list           │  Timeline chart                     │
│ (severity-sorted,      │  - phase bands / tint, minimap      │
│  fired insights only)  │  - selected channels                │
│  [click → evidence]    │  - markers: limit & CAS events      │
├───────────────────────┴─────────────────────────────────────┤
│ Events — one table, chronological: limit and CAS events,     │
│ with row actions; filtered events collapsed to one line      │
├───────────────────────────────────────────────────────────┤
│ Topic cards — expanded only when they have something to say; │
│ otherwise one roster line each. Triggers read-only on the    │
│ card; "Edit rules…" opens the editor panel (Spec 14 §7.3)    │
└───────────────────────────────────────────────────────────┘
```

- **Flight facts (v0.16, Spec 10 §4.3).** A compact row in the header for per-flight figures a pilot *records* rather than *judges*: fuel burned, cruise nm/gal, cruise fuel flow (Spec 10 §4.2 planning numbers) and the lane-check result (`both lanes ✓` / `one lane only` / `not detected`, Spec 10 D19). Admission is Spec 10 §4.3's rule; nothing here ever carries a limit, a baseline, a severity or an insight, and nothing lands here by default when it leaves the topic set — it must pass the rule.
- **Insight list** is the entry point (principle 2): each item shows severity, the rendered `message.text`, and confidence. Clicking one scrolls/zooms the timeline chart to its `evidence` window (`series_window` evidence → zoom to `[start_s, end_s]`; `exceedance`/`cas_event` evidence → highlight that row in Events and that marker on the chart; `baseline_point` evidence → a "compare to fleet" link into Trends, §5.3). Only topics with `insight != null` appear here. The former "N topics analysed with nothing to flag" line is dropped (v0.16): the topic roster below says the same thing, per topic.
- **Severity travels with the topic, not the section.** The same severity dot/label used in the insight list is repeated on that topic's card whenever `insight != null`; a topic with `insight == null` carries no tag anywhere. One severity token set, defined once: `info` `#64748B`, `watch` `#FDE047`, `warning` `#F5A524`, `limit` `#E5484D`; `warning`/`limit` render with a triangle, `watch`/`info` with a circle.
- **Timeline chart** is the one place `get_series` (R1) is called, lazily — only the channels the visible insights/topics reference are fetched by default, with a channel picker (Spec 01 §6.4 registry) to add more. Phase tint recomputed on zoom/pan; one minimap, no second band; fixed phase palette (table below); no text inside the minimap or tint — a caption line names the visible phases and a persistent legend key maps colours. Markers: one per event in the Events table, same order, two glyphs (limit, CAS). A flight raising `PHASE_TAKEOFF_NOT_DETECTED` shows the plain-language note here ("phase detection didn't find a clear climb or cruise for this flight; some metrics below are unavailable as a result").

  | Phase | Color | Phase | Color |
  |---|---|---|---|
  | `PRE_START` | `#4B5563` | `CRUISE` | `#0EA5E9` |
  | `ENGINE_START` | `#7C6F57` | `DESCENT` | `#A855F7` |
  | `WARMUP` | `#8B7E6A` | `APPROACH` | `#EC4899` |
  | `TAXI` | `#5B7290` | `LANDING_ROLL` | `#14B8A6` |
  | `TAKEOFF_ROLL` | `#6366F1` | `SHUTDOWN` | `#374151` |
  | `CLIMB` | `#22C55E` | `UNKNOWN` | `#1F2937` |

- **Events (v0.16).** A first-class section with its own heading, between the chart and the topic cards: **one chronological table of every event on this flight**, limit and CAS (Spec 01 §8.6 `source`). Columns: time, phase, source/target (limit label with OM value, or alert name), duration, excess (limits only), reason (CAS `not_lane_check_reason`, in words with the band), severity label. Row actions, identical for both sources: open on chart, add a note, filter (duration, or magnitude+duration for limits; Spec 09 §12.1), acknowledge (Spec 11, when built); every workspace-wide action carries its Spec 14 §7.5 scope caption. Events suppressed by a filter collapse to one line per target — *"17 FUEL PRESS events within your filter"* — expandable. A breach on a filtered target is a normal row marked *beyond your filter*. The expanded row shows the event's context (for CAS: IAS, oil-pressure gaps, co-active alerts, and the flight's full ENGINE ECU runs by class). The section is present on every flight; with nothing to show it is one line, *No events on this flight*. `limit_exceedances` remains the owner in the data model (Spec 10 §4.1) but its **card** now carries only its analysis sentence and mirrored badges, and collapses to a roster line like any other when there are no events.
- **Topic cards — the roster rule (v0.16).** Every evaluated topic has a card, but a card is **expanded** only when it has something to say: a fired insight, a mirrored badge (Spec 10 §4.1), a *reference changed* / *rule changed* marker (Spec 14 §7.2), or a validity note (*unavailable: no cruise detected*; *not yet validated on this engine*, Spec 10 §8.1). Otherwise it is **one line** — topic name · its analysis sentence truncated to the measured value · `?` help — expandable by tap. A disabled topic's line reads *disabled · Enable* (Spec 14 §7.3). Expanded cards come first, in severity order, then the roster. Change markers expand by *kind* (v0.17): a *reference changed* marker (an exclusion or pin moved the reference) expands every reference-based card, since every one of them was recomputed; a *rule changed* marker expands only the edited topic. The two-layer format is kept: the "why nothing is wrong" sentence is still there, one tap away, and the absence of a badge is still the signal.
- **Topic card: triggers (v0.16, Spec 14 §7.3).** The card's disclosure shows the topic's triggers **read-only** — current value, met / not met on this flight and by how much (*trend · R² ≥ 0.5 · n ≥ 10 — not met: R² 0.30 over 23 flights*) — plus the topic's `enabled` state. One action, **Edit rules…**, opens the **rule editor panel**: a side sheet over the Flight view that knows which topic and which flight it came from, with inline editing, the fleet-wide preview (this flight highlighted), Apply / Cancel / Reset to shipped, the `enabled` toggle, and Spec 14 §7.5 scope captions. Closing it returns to the same scroll position. No input control is rendered on the card itself. *Edit trigger ↓* on an insight card opens the panel for that topic directly.
- **Reference contribution** is stated in the header — *Contributes to reference* or *Excluded from reference (reason)* — with the toggle (Spec 14 §7.1). **Exclude this flight from reference →** on any `baseline_deviation`, outlier or trend insight; reason required.
- **Markers.** A card whose verdict changed because the reference moved or a rule was edited carries *reference changed* / *rule changed*, showing what, when and why, with **Revert** behind the same preview (Spec 14 §7.2).
- **Annotations** attach inline on any insight card or Events row, writing to Spec 02's `annotations.json` via the host, keyed by `flight_id` (Spec 01 R3); Journal (§5.6) browses them across the fleet.
- **Report / export:** "Download as text" (`render_report`) and "Export flight bundle" (Spec 02 §7, `scope: "single_flight"`) as secondary actions.
- **Not a flight.** A log the loader skipped is no longer rendered by this view; Flights links it to Log preview (§5.9).

<details><summary>v0.15 layout (superseded)</summary>

The v0.13–v0.15 layout had the planning numbers and lane check as an untitled summary line, events inside the `limit_exceedances` topic card, every topic card expanded with a closed inline rule editor, and the skipped-log preview as a mode of this view.

</details>

### 5.3 Trends

**Question answered:** "Is this flight normal for my airplane, over time?"

- One metric at a time (picker from the registry), plotted as engine-hours-on-x, value-on-y, with the leave-one-out reference band (Spec 01 §8.4 R2; "baseline" internally) drawn behind the points, and each point clickable back into that flight's Flight view. The sample count ("n=23") links to Flights (§5.1), pre-filtered to that reference's contributing flights — one click from a summary statistic to which actual flights it's built on.
- **Stratification toggle — never specified beyond a name until now.** Whether it's shown at all, and which kind, is fixed per metric by `band_kind_by_metric` (Spec 01 §8.4) — never a user choice of "stratify by DA or OAT," since a metric only has one physically correct band kind. Concretely:
  - **Disabled/hidden entirely** for a metric where `band_kind_by_metric[metric] === null` (e.g. Overboost Time, Climb Thermal Rate) — no toggle shown, not a grayed-out one, since there's nothing to offer.
  - **Off by default** for every stratifiable metric (5 of the 9 real metrics: EGT Spread, EGT4 Elevation, Oil Temp Peak, Coolant Temp Peak, Oil/Coolant Ratio → `oat_band`; Cruise Efficiency, Cruise Fuel Flow → `da_band`) — the single unstratified reference is the first thing shown, matching principle 6 (§3): a casual pilot never has to understand density altitude banding to read this chart.
  - **On:** redraws as one band per value `band_kind_by_metric` actually produced for this metric's flights (not a fixed 4 — a metric might only have 3 of the 4 bands represented), each with its own reference region and its own `confidence` label — which will typically read lower than the unstratified fleet confidence (Spec 01 §8.4's honest trade-off), and that's shown as-is, not upgraded or hidden. A band with `n < 3` still renders, labeled `VERY_LOW`, not suppressed — consistent with never hiding data over a confidence threshold, only labeling it (same principle as `BASELINE_LOW_N`, Spec 01 §8.4).
  - Each point's own band (from `points[].band`) determines which region it's drawn in; switching the toggle re-groups the same points, it doesn't re-fetch anything.
- Trend line (slope, direction, R², confidence) drawn only when `n` clears the same `n_min` gate as insight triggers (Spec 01 §8.4) — a trend line drawn on 4 points would misrepresent confidence the engine itself doesn't claim. When stratified, this becomes one trend line per band, same gate applied per band's own `n`.
- Outliers visually flagged on the scatter, distinct from points that merely sit outside the baseline band without crossing the z-score threshold. With stratification **off**, rings come from `FleetMetric.outliers`; with it **on**, from each band's `by_band.bands[b].outliers` (Spec 01 R8). Because `baseline_deviation` compares a flight within its own band (falling back to all flights when the band is too small), the stratified view is the one that matches the insights for stratified metrics; the insight text says which comparison was used.
- **Model view** (takeoff MAP, and any future `Model`): a small dedicated panel — predicted vs. actual scatter, coefficients shown as plain text ("MAP drops ~X inHg per 1,000 ft density altitude"), and the `note` field when `n < 5` ("still collecting data").

### 5.4 Engine ECU CAS Events (removed in v0.14)

Removed. The view's content moved, per Spec 10 D19: each `GROUND` or `IN_FLIGHT` ENGINE ECU run is a **CAS event** in the Flight view's events list (§5.2, owned by `limit_exceedances`, Spec 09 filters and Spec 14 acknowledge apply); "how often" is a generated event-frequency panel on Trends (Spec 12 §8.4); lane-check pairing is a flight-summary line (`both lanes ✓` / `one lane only` / `not detected`), informational only. Ground-context classes (`GROUND_START`, `LANE_CHECK`, `GROUND_SHUTDOWN`) are visible in the event's expanded view and nowhere else. The B.U.D.S. banner is gone with the engine's recommended-actions list (Spec 01 v0.19). Route `/ecu` redirects to Flights. The v0.9–v0.13 text is in history.

**CAS-event row rule (§5.2).** A CAS event row reads like a limit row — alert, phase, start, duration — plus its class and, when `not_lane_check_reason` is set, the reason in words: *"ENGINE ECU · TAXI · 7 s · 2,550 rpm — below the lane-check band (4,000 ± 500)"*. The row offers the same actions as a limit row: open on the chart, acknowledge (this flight), filter by duration (workspace-wide, scope-labelled per Spec 14 §7.5). No severity policy: the badge is the rule set's display label.

### 5.5 Reference & Models (moved to Settings in v0.13)

**Superseded by Spec 14 §5.1.** The question this view answered — "what is my engine compared against, and how is that built?" — is configuration, and lives in Settings → Reference & Models (§5.7): contributing flights (linking to Flights, no list of its own), global `outlier_z_threshold`, recent window (Spec 12), per-metric pinning (Spec 12), stratification (read-only), fitted models. The **rule playground is retired**; rule editing happens on the topic card (§5.2, Spec 14 §7.2–§7.3) with the same fleet-wide diff, now shown *before* apply. Engine overrides, when designed, live in Settings → Engine. The v0.12 text is kept below for history.

<details><summary>v0.12 text (superseded)</summary>

This view is Spec 02's `FleetSelection` made visible and editable, plus the **rule playground**:

- **Flight inclusion — no separate list here (changed in v0.6).** Membership isn't stored per Spec 02 v0.5 §5.1/§6.3 — this panel links out to Flights (§5.1) rather than keeping its own copy of the fleet list, which would just be a second place for it to drift out of sync. The exclude toggle and reason still live inline on each row *in Flights*, not duplicated here. Rebuilding baselines (`rebuild_baselines` workflow, Spec 01 §7) is still an explicit action on this panel, never automatic on toggle — matches principle 3.
- **Baseline config:** membership (leave-one-out, fixed per Spec 01 R2 — shown as read-only explanation, not a toggle, since v1 doesn't expose changing it) and `n_min` per metric, if the pilot wants to loosen or tighten the sample-size gate.
- **Rule playground (D6):** the differentiating feature, and principle 6's concrete home — this is the one screen where the researcher persona's tuning actually lives. A rule from `rules/active.json` (Spec 02 §6.4) shown with its threshold/condition editable inline, alongside `BaselineConfig`'s `outlier_z_threshold` and `n_min` (Spec 01 §8.4, global default plus per-metric override) — one editor over two underlying documents, since both are the same kind of thing to a pilot even though they're stored separately. Editing it re-runs `evaluate_insights` (cheap, per Spec 01 §7) against every flight in the current fleet selection and shows, live, which flights' insights would change — added, removed, or altered severity — as a diffed list, not just a recount. "Reset to shipped defaults" always available. This is where a pilot (or a contributor validating a rule change before submitting a PR) actually develops the analysis, which was the second half of the original goal alongside the graphical UI itself.
- **Engine overrides:** editing `engine_overrides.json` (Spec 02 §6.4) lives here too — same pattern as rules, but for limits rather than insight thresholds, and it requires the `reason`/`source` fields Spec 02 made mandatory, shown as required form fields, not optional ones.

</details>

### 5.6 Journal (was Annotations)

**Question answered:** "What have I decided, across all my flights — and has anything changed since?"

**Superseded by Spec 14 §6.** The Annotations page is renamed **Journal** and redefined as the user's decision journal: acknowledged insights, limit filters (Spec 09), disabled topics, rule edits, flight exclusions, pinned references and free-text annotations, each with where it was made, when, the reason, and the counted effect at the time. Entries are created elsewhere in the flow — on a card, in Flights, in Trends — and come here for review, editing and reversal; reversed entries are closed, not deleted. Change notices (Spec 09 §12 drift and its generalisation, Spec 14 §6.2) sit on their entries. Backfilled entries from before Journal existed are marked as such. The inline "add a note" affordance on cards (§5.2) is unchanged and writes a Journal annotation. BACKLOG B4's original motivation — an explanation made months ago is findable later — is still met, as one entry kind among several.

### 5.7 Settings

Not a top-level nav item (§4) — reached via the gear icon. The workspace switcher lives permanently in the nav (§4) and the log browser is Flights (§5.1); Settings duplicates neither. Since v0.13 it is a **tabbed section** (Spec 14 §5) holding everything that changes what the engine computes, split as Spec 02 §6.4 splits the files:

- **Engine** — active profile and version (`engine_model` locked, read-only per Spec 02 §5.6 — changing it is a reason to make a new workspace); the OM limits it ships, read-only, with their phase-aware suppression windows; engine overrides when designed (Spec 02 §6.4, `reason`/`source` mandatory). Until then: "None".
- **Reference & Models** — Spec 14 §5.1 (see §5.5).
- **App** — units, which workspace reopens on launch, anonymize-by-default (Spec 02 §6.6); the **export/import bundle** flow (Spec 02 §7: scope picker, anonymize toggle, download; import is §5.8's drop-and-preview flow from a different entry point); and the **persistence nudge** (Spec 02 §9 — one-time, dismissible, browser mode only).

No changelog (Spec 14 v0.13). A setting that changes results and differs from shipped is marked with its shipped value and links to its Journal entry; display-only settings are unmarked. The Engine tab shows the engine version in effect and its user-facing *What's new* (Spec 13).

### 5.8 Bundle preview (not top-level; a modal/overlay flow)

**Resolves R2.** Triggered by dragging a `.eisbundle.json`/`.eisbundle.zip` anywhere in the app, or a future "browse community samples" entry point (Spec 01 §9 community goal). Opens the bundle's contents in the *same* Flight-view and Trends components used for the live workspace, with:

- A persistent "Previewing: not yet added to your workspace" banner.
- Every write-capable action (annotate, exclude from reference, edit rules) disabled — this is a viewer, not an editing surface, until the pilot commits.
- One explicit "Add to my workspace" button that runs the actual merge (Spec 02 §7.4) and only then makes the data live and editable.

This reuses rather than duplicates the flight/trends UI, which is why it's a flow layered on existing views rather than a seventh destination.

### 5.9 Log preview (v0.16)

**Question answered:** "What is in this log the app didn't treat as a flight, and should it be included?"

Reached from a Flights row whose status is *Ground session*, *Too short*, *Other aircraft* or any other loader skip reason (Spec 02 §5.11). Read-only. Shows: a header (file name, folder, why it was skipped, duration, aircraft ident, engine hours if present); the timeline chart with channel picker, phase tint and minimap exactly as in §5.2 (shared components); the log's CAS alerts and ENGINE ECU runs **by class** (`GROUND_START` / `LANE_CHECK` / `GROUND` / `IN_FLIGHT` / `GROUND_SHUTDOWN`, sub-threshold blips counted) as a plain list — not an Events table, since nothing here is analysed; and one action, **Include this log**, with the Spec 02 §5.11 confirmation and reason. No insights, no reference state, no topic cards, no filters, no notes. Including the log sends the pilot to its Flight view once analysed. Route `/logs/<file name>` (v0.17 — no fingerprint reaches the web; the file name is unique within a workspace's folders); Flight view no longer carries a preview mode.

## 6. Cross-cutting concerns

### 6.1 Charts (ECharts)

- One shared chart wrapper component handles: a synced cursor with a real-value/real-unit readout (Flight view's timeline overlays several channels in one chart, each indexed to its own range so shapes stay comparable — see §5.2), phase-band background shading, and touch-friendly zoom/pan (pinch on iPad, drag-select on desktop) — built once, reused everywhere a time series appears.
- **The minimap and the main chart's phase tint are two renderings of the same phase-segment data at two different scopes, not two independently written features.** The minimap always shows the full flight's phase mix, with the current zoom window outlined on it; the chart tint always shows only the visible window's phase mix, recomputed on every zoom/pan. Implement them from one shared phase-segment calculation (segments clipped/re-proportioned to whichever time range — full flight or current view — the component is asked to render), not as two independently written pieces of logic that happen to agree today. (An earlier version of this spec had the chart tint as a second standalone bar instead of a chart background — cut after review as redundant with the minimap; see §5.2.)
- Downsampling for display follows Spec 01 §8.7 (min/max-preserving envelope); the chart layer never receives more points than the viewport can usefully show, independent of how much `get_series` returns.
- Severity colors are defined once as design tokens (limit/warning/watch/info) and reused across the insight list, chart markers and event rows — a pilot should learn the color meaning once.

### 6.2 Diagnostics and staleness in the UI

Every Spec 01 `Diagnostic` has a UI treatment class, not a one-off: `info` renders as a quiet inline note, `warn` as a visible banner within the relevant view, `error` as a blocking state with no partial render. This mapping is a single lookup table, so a new diagnostic code (e.g. from a future topic, Spec 01 §9) gets sensible default treatment without new UI code.

### 6.3 What loads when

Consistent with R1 and Spec 02 §5's split between small derived data and re-parsed series: opening the app loads the workspace manifest and every flight's `FlightAnalysis` (small — Spec 04 measured under 3 KB per flight), enough to render the Flights table, the Trends list, and the ECU table immediately. Series data loads only when a specific flight's timeline is opened. This ordering is what keeps every view except Flight view fast regardless of fleet size.

## 7. Out of scope for this spec

Visual design tokens and mockups (a natural next step once this structure is agreed, likely via the frontend-design skill); the exact preview diff algorithm (functionally specified in Spec 14 §7.2, implementation detail); the wireframes `design/wireframes/Baselines.dc.html`, `Annotations.dc.html` and `Settings.dc.html`, superseded by Spec 14 and not updated — `web/src/views` is the reference for those screens; mobile phone layout (iPad and desktop only, per Spec 04's tested scope); internationalization; accessibility audit (should follow standard practice but isn't specified here).

## 8. Open questions

| # | Question | Leaning |
|---|---|---|
| Q1 | Should the global stale banner (§4) block navigation until resolved, or just persist as a dismissible notice? | Dismissible — principle 3 says no forced recompute, and blocking navigation would punish a pilot who just wants to check one flight after a big import. |
| Q2 | ~~Does the rule playground (§5.5) need its own "save as a named experiment" beyond the single working copy in `rules/active.json`?~~ | **Moot in v0.13:** the playground is retired. The single working copy in `rules/active.json` stands; comparing two rule sets is an experiment-workspace job, or Research when designed. |
| Q3 | Should Trends (§5.3) support comparing two metrics at once (e.g. EGT spread vs. OAT), or stay one-metric-at-a-time? | One at a time for v1; the model view (§5.3) already covers the one two-variable case (MAP model) that matters today. |
| Q4 | Where does the phase-detection defect note (§5.2) go once finding 9 is actually fixed (Spec 01 migration Stage 2b)? | Becomes dead code to remove; not worth designing a toggle for a temporary state. |
| Q5 | Does the ECU view (§5.4) need a fleet-wide "how often does this happen" summary, or is per-event always the right granularity per B3's original complaint? | **Resolved v0.14:** both, and neither on an ECU page — per-event rows on the Flight view, frequency on Trends (Spec 12 §8.4). |
