# Spec 14 — Settings, Journal, and Rule Editing on the Card

**Project:** SlingologyEIS web platform
**Status:** v0.15 — Settings → App shows a **Storage** panel in the browser host (§5.2.1), for Spec 04 v0.4; v0.14 — Settings → Engine gains **Log channels** (§5.3) for Spec 01 v0.23's general-purpose analog assignments; v0.13 — the Settings changelog is replaced by Journal entries for changed settings (§5, §6.1, §6.3), implemented; the Engine tab's *What's new* waits for Spec 13's generated page. v0.12 — §5.2 (data location in Settings → App) implemented. v0.11: v0.2–v0.5 implemented on `webui` (`ac62b20`…`282631c`; `4839600`…`03c0017`; `c68c145`…`d84ee5d`; `55e6b32`…`dfe88a6`, 2026-10-11/12). v0.6 (tidy-up: §7.5 additions, *Include again* through the exclusion dialog, Settings `n_min` list shows disabled topics) implemented 2026-10-13. **Spec implemented**; remaining follow-ups live elsewhere: Spec 01 revision note (§8), Spec 11 silencing levels, Pyodide preview latency (Q4). §4–§7 decided, §10 open.
**Suggested repo path:** `docs/specs/14-settings-journal-and-card-rule-editing.md`
**Builds on:** Spec 02 (`FleetSelection`, `rules/active.json`, `annotations.json`, app-level vs workspace-level settings §6.4), Spec 03 (§3 principle 6, §4 nav, §5.5 Baselines & models, §5.6 Annotations, §5.7 Settings), Spec 09 (filters, "what would this hide?" preview v0.2, Notes page), Spec 10 (§6.1 rules that do not reflect what runs), Spec 11 (insight layer — paused; three silencing levels, settings shown on the card), Spec 12 (Trends as a change page — recent window, reference pinning)
**Supersedes:** Spec 03 §5.5 (the rule playground as a page) and the part of principle 6 that places all tuning in Baselines & Models
**Baseline reviewed:** branch `webui` at commit `5d029fc` (2026-10-05); `web/src/views/Baselines.tsx`, `Annotations.tsx`, `Settings.tsx`; `insight_rules.json` v1.3; `engines/916iS.json`

**Revision history**

| Version | Change |
|---|---|
| 0.6 | **From implementation of v0.5.** §7.5 table gains the controls found outside it: Reference & Models save (*every metric*), copy filters (*every limit copied*), Journal reversals (scope of the decision undone), Trends shift-history delete (*this metric*). *Include again* uses the same dialog and preview as *Exclude* rather than acting in one click (§7.1). Tail-number grouping is a workspace definition, not a §7.5 decision — it goes to the Settings changelog. §7.3 clarified: the collapsed card applies to every topic that has a card; topics with no card (fixed in engine code) get none; *Enable* closes the open `disabled_topic` entry. Settings `n_min` list shows disabled topics marked *disabled* instead of hiding them (§5.1). Spec 01 note made concrete. |
| 0.7 | ECU leaves the top-level nav (Spec 03 v0.14, Spec 10 D19): its content is now Flight-view CAS event rows and a Trends panel. §4 table, activity grouping and nav sketch updated; acceptance 1 amended. No other change. |
| 0.8 | §7.5 scope caption: the object noun follows the filter target — "this limit" for a limit, "this alert" for a CAS target (Spec 09 v0.18). |
| 0.9 | **Editor leaves the card** (Flight view review, 2026-10-13; Spec 03 v0.16). The topic card's disclosure becomes **read-only** (triggers, current values, met/not met, `enabled` state); one action, *Edit rules…*, opens the editor as a **side panel** over the Flight view, in context (topic + originating flight), with the §7.2 flow unchanged (preview, Apply, Cancel, Reset, scope captions, Journal). *Edit trigger ↓* on an insight card opens the panel directly. The decision that there is no rule list in Settings stands; what moves is only where the inputs render. §7.3 amended. |
| 0.14 | **Log channels** (Spec 01 v0.23 decision 3, 2026-10-17). The Engine tab gains a *Log channels* panel (§5.3) where the pilot assigns a source's raw general-purpose analog inputs to registry channels (e.g. AXIS analog 7 → CO ppm). Nothing is assigned by default; an assignment is a changed setting (§5) with a Journal entry. |
| 0.15 | **Storage panel for the browser host (§5.2.1)** (Spec 04 v0.4, 2026-10-17). Where the data location can't be chosen — the browser's data root is the site's private storage — the App tab answers the same question differently: how much space the data uses, whether the browser has promised to keep it, *Export all workspaces…* and *Delete all data on this device*. Shown or hidden by the host's `data_location` / `persistent_storage_status` features (Spec 03 §6.4). Acceptance 21. Q4's Pyodide half is scheduled (Spec 04 Q8). |
| 0.10 | **Journal is a register, not a log** (2026-10-14). The user wants to know what is *in force*, not what happened. §6 rewritten: one entry per live decision; reversing a decision **removes** its entry (no closed/struck-through entries); re-editing a decision **updates** its entry; the counted effect is **live**, recomputed on open, not a snapshot; the *backfilled* badge goes (imported decisions are ordinary entries); the Settings changelog remains the configuration history and Journal does not duplicate or link into it line by line. §7.1 reversal, §7.2 Apply, §7.3 Enable and acceptance 9/12/17 amended. History survives where it is already kept for other reasons — `LimitFilter.history[]` (Spec 09 §9), the Settings changelog, Spec 12 shift history — not on this page. |
| 0.11 | **From implementation of v0.10** (bd9a268). Two corrections the build got right and the spec had loose: (1) rule-edit entries are **derived** — a topic whose `rules/active.json` differs from shipped has an entry, whether or not the edit was made through the app, and the register is reconciled with its sources on every read (imports decisions without an entry, drops entries whose decision is gone); "upsert on edit" was a weaker statement of the same thing. (2) With one entry per rule there is no "previous value": **Revert and Reset to shipped are one action**, named *Reset to shipped*. §6.1 row, §7.2 step 4 and §7.3 wording aligned. Also recorded: notices a pilot has reviewed stay cleared until the decision is edited again. |
| 0.12 | **Data location in Settings → App (§5.2, proposed;** Spec 02 v0.10 §5.8.1**).** The App tab shows where the pilot's data lives and why (default, chosen, or fixed by the environment), with *Change…* and *Use default location*. The flow states what will happen — move into an empty folder, or use one that already holds data — before anything happens. A move keeps the old copy and says where it is. Local server only. Not an analysis setting, so it is not in the changelog. Acceptance 19. |
| 0.13 | **No Settings changelog; Journal is the one register of what is in force** (2026-10-15). The user wants to know what is in effect now, not what happened. v0.10 made Journal a register of decisions but left changed settings in a separate history list, and the line it drew — Settings changes the computation, Journal holds decisions about results — didn't hold: rule edits already change the computation and are derived Journal entries. Now every setting that changes results and differs from shipped is a derived Journal entry, built the same way as a rule edit (§6.1); Settings marks those values and links to the entry (§5). Display-only settings get no entry. The changelog (`settings_changelog.json`) is no longer written or shown. App upgrades are not decisions: the Engine tab shows the version in effect and its user-facing *What's new* (§5, Spec 13). §6.3 rewritten; §7.5's tail-number note and acceptance 2 updated; new acceptance 20. |
| 0.5 | **From implementation of v0.4 steps 1–3.** A disabled topic's card **stays, collapsed** to one line with *Enable*, uniformly for every topic — as built, the engine returned no result for a disabled topic and its card vanished, leaving Journal as the only way back (§7.3). `margin_min_f` and `consecutive_flights` leave the §7.4 list: they are fixed in engine code, not editable triggers; Code's draft wording kept for when they are. Preview wording adopted as built (§7.2). Spec 01 to note that a disabled topic still returns a topic result carrying `enabled: false` and no analysis. §7.5 scope labelling was not built in the v0.4 run and remains pending. |
| 0.4 | **From implementation of v0.3, and inline help.** Insight card keeps a *jump* to its topic card's open disclosure — one editor, reachable from the insight (§7.3). Engine gap found: `overboost_time`, `map_at_takeoff`, `engine_ecu_inflight`, `limit_exceedances` never read their `enabled` flag; disabling them changed the file and Journal but suppressed nothing — made a guard with a uniform test (§7.3). New §7.4 inline help: when a parameter or section gets help, what it says, where the text lives. New §7.5 scope labelling: every decision control says, before it is touched, whether it applies to this flight or to all flights in the workspace — a trigger edited from one flight's topic card is a workspace rule, and nothing said so until the preview. Acceptance 13–16. `trigger_status` per topic now in the engine contract (Spec 01 to note). |
| 0.3 | **From implementation of v0.2.** Rule editing moves from the *insight* card to the *topic* card (§7.3), so a trigger that never fires can still be edited in context — found live: no trend trigger fires on the 53-flight set, so no trend rule had an entry point. `n_min` is per-trigger in `rules/active.json`, not a global field; §5.1 corrected to show it read-only. Backfilled Journal entries are marked as backfilled and carry no counted effect (§6.1); backfill must be idempotent. Exclusion dialog has one field, reason (§7.1). Q4 part-resolved: 57 ms preview on 53 flights, local-server mode; Pyodide unmeasured. Acknowledge and disable-topic levels stay unbuilt until Spec 11 (§7.2). |
| 0.2 | Q3 decided: Research stays out of the nav until Spec 06 exists (§4, §9 criterion 1). |
| 0.1 | Initial draft. Activity-based page grouping (§4); Settings as a tabbed section with Baselines & Models demoted into it as **Reference & Models** (§5); Annotations/Notes renamed **Journal** and defined as the decision journal (§6); "In baselines" → "In reference" and exclusion from an insight card (§7.1); the Rules playground retired as a page, rule editing moved to the insight card with the fleet-wide preview shown before apply (§7.2). |

**Note on numbering:** 06 stays reserved for Research mode. 11 (insight layer), 12 (Trends as a change page) and 13 (documentation system) exist as drafts outside this branch.

---

## 1. Purpose

The Baselines & Models page asks "How are my baselines built, and can I fix one that's wrong?" (Spec 03 §5.5). Evaluated against who actually opens it and what they find there, it does three unrelated jobs — governs the reference, hosts the rule playground, and shows read-outs that belong to other pages — and it does them for a user who has already had the baseline numbers shown to them on the Flight view analysis line and on Trends. A casual pilot gets the value of baselines without ever visiting the page.

This spec puts each of those jobs where a pilot would look for it, under one organising rule: **Settings holds what changes the computation; Journal holds what the user has decided about the results.** It also closes a workflow gap found on the way — a pilot cannot exclude a flight from the insight that made them want to — and decides where rule thresholds are edited now that the playground's page is gone.

## 2. Scope and boundaries

| This spec owns | Owned elsewhere |
|---|---|
| The grouping of top-level destinations by activity (§4) | Each view's own content: Flights (Spec 03 §5.1), Flight view (§5.2), Trends (Spec 12) |
| Settings as a section, its tabs and what each holds (§5) | The settings' *values and semantics*: `outlier_z_threshold`, `n_min` (Spec 01 §8.4), recent window and pinning (Spec 12), engine overrides schema (Spec 02 §6.4) |
| Journal: what it lists, how entries are created, reviewed and reversed (§6) | Each decision's engine behaviour: filters (Spec 09), silencing levels and markers (Spec 11), annotations (Spec 01 R3) |
| The user-facing term "reference", and the exclusion workflow from an insight card (§7.1) | Membership vs contribution, `FleetSelection`, rescan (Spec 02 §5.1, §6.3) |
| Where a rule is edited and what the user sees before applying (§7.2) | Which rules exist and whether they run (Spec 10); the rule schema (Spec 01, `insight_rules.json`) |

**Non-goals:** designing Research mode (Spec 06, reserved) — §4 only fixes where it sits and that it needs a path out; designing engine overrides; changing any threshold or default; mobile phone layout (Spec 04's tested scope stands).

## 3. Definitions

- **Reference** — user-facing word for what a flight is compared against: the personal baseline (mean, σ, n) for a metric, built from the contributing flights, stratified where the metric is, and either rolling or pinned (Spec 12). "Baseline" remains the internal term (`baselines.json`, Spec 09 frozen baselines, function names).
- **Contributing flight** — a workspace member whose metrics feed the reference. Membership is decided by folders (Spec 02 §5.1); contribution is the only in-app selection.
- **Decision** — a user action that changes what is *shown* without changing what is *computed*: acknowledging an insight, filtering a limit, disabling a topic, editing a rule, annotating a flight. Excluding a flight is also a decision, though it does change the computation (§7.1 explains why it lives in both places).
- **Preview** — the fleet-wide consequence of a pending change, computed before it is applied: insights added, removed, or changed in severity, with the flights concerned.

## 4. Destinations by activity

Pages are grouped by **what the user is doing**, not by who the user is. There is no "advanced" area: the same pilot is casual on one day and investigating a worrying trend the next, and an "advanced" drawer collects everything with no internal logic while teaching the casual user that its contents are not for them.

| Activity | Shape | Destinations |
|---|---|---|
| Fly and look | read, every flight | Flights · Flight view · Trends |
| Decide about results | act in context, review later | **Journal** (§6) |
| Investigate | iterate, produce a finding | Research (Spec 06, reserved) |
| Configure the computation | set, rarely revisit | **Settings** (§5), from the gear icon |

Nav shell (replaces Spec 03 §4's sketch):

```
[Logo]  [Workspace: N117ZS ▾]   Flights   Trends   Journal   ⚙
```

Four everyday destinations, Journal beside them, Settings behind the gear. Baselines leaves the top level. Research is **not shown** until Spec 06 is designed (Q3, decided v0.2) — no placeholder. When it arrives it is a distinct destination with a defined path *out*: a finding becomes a Journal decision or a Settings change carrying provenance ("filter created from Research task #4"), per Spec 03 principle 6's Explore → operational path.

## 5. Settings

Settings becomes a section with tabs. It holds everything that changes what the engine computes, split as Spec 02 §6.4 already splits the files.

| Tab | Contents | Source |
|---|---|---|
| **Engine** | Active engine profile and version; the OM limits it ships, read-only, with phase-aware suppression shown per limit; engine overrides when designed (`reason`/`source` mandatory); **Log channels** (§5.3, v0.14) | `engines/<model>.json`, `engine_overrides.json`, `WorkspaceSettings.channel_assignments` |
| **Reference & Models** | §5.1 | `FleetSelection.baseline_config`, `baselines.json`, `models.json` |
| **App** | Units; last active workspace; workspace export and import (Spec 02 v0.11 §7; anonymise-on-export default removed); platform notes (Safari folder re-pick); data location (§5.2, local server only, v0.12) or Storage (§5.2.1, browser only, v0.15) | app-level settings; the location file (Spec 02 §5.8.1) |

~~The three tabs share **one changelog**~~ — removed in v0.13. A pilot asking "why does this flight look different?" wants what is in effect now, and that has one home: Journal (§6).

- **Changed settings are marked.** Every setting that changes results and differs from its shipped value shows the shipped value beside it and links to its Journal entry (§6.1). *Reset to shipped* is available in both places.
- **Which settings count.** Those that change what the engine computes or reports: the Reference & Models fields held in `FleetSelection.baseline_config` — global `outlier_z_threshold`, per-metric overrides, the recent window, the OM-margin fraction, per-metric band kind — and engine overrides once designed. Display-only settings (units, workspace reopened on launch, anonymise-on-export default, chart presets) change nothing about results and get no entry. Pins, exclusions, filters and rule edits are already Journal entries of their own.
- **App upgrades** are not decisions, so nothing is in force to list. The Engine tab shows the engine version in effect and the user-facing *What's new* for it (Spec 13's generated page); Sync's re-analysis prompt (Spec 03 §5.1) is the signal that a new version changed results.

### 5.1 Reference & Models

**Question answered:** "What is my engine being compared against, and how is that built?"

Presented as what the engine is compared against, grouped by metric, with controls inline and tables one click deep. It is a control-and-provenance surface, not a report.

| Panel | Contents | Control |
|---|---|---|
| Contributing flights | "23 of 26 flights contribute · 3 excluded", excluded flights listed with reasons | Links to Flights filtered to excluded; no list of its own (Spec 03 v0.6). **Rebuild reference** stays an explicit action |
| Comparison | global `outlier_z_threshold` (default 2.0), per-metric overrides where set; `n_min` shown per trigger, read-only (it lives in `rules/active.json` and is edited on the topic card, §7.3); disabled topics listed and marked *disabled*, not hidden (v0.6) | `outlier_z_threshold` editable; "reset to shipped" |
| Window | recent window — last 10 engine hours with ≥ 5 flights, capped at 15 (Spec 12) | editable within Spec 12's bounds |
| Reference per metric | rolling or **pinned** at a date/engine-hour, with the pin's reason (Spec 12) | pin / unpin per metric; Spec 09 filters keep their own frozen reference, shown read-only here with a link to the filter in Journal |
| Stratification | which metrics stratify by DA band, which by OAT band, and the band edges | read-only in v1 (bands are research-paper §9 constants) |
| Models | fitted models — takeoff MAP vs PA/OAT: R², n, residual SD, last refit | refit; link to the Trends residual panel (Spec 12 v0.3) |

What is **not** here: baseline values as the page's main content (they are on cards and Trends); per-topic rule editing (§7.2); limit filter management and drift (Journal, §6).

### 5.2 Data location (App tab, v0.12)

**Question answered:** "Where is my data, and can I put it somewhere else?" The behaviour is Spec 02 §5.8.1; this section is only how it shows.

- **Shown:** the data root's full path, and how many workspaces it holds. One line says how the path was chosen: *Default location*, *Chosen by you*, or *Set by the environment (SLINGOLOGY_EIS_HOME)*. A note says log folders stay where they are.
- **Change…** opens a path field, the same control as Add folder (Spec 03 §5.1). Once a path is entered, the panel says what will happen before anything does. It's one of:
  - *Move your data here*, with the number of workspaces and the size to copy.
  - *Use the data already here*, with the number of workspaces it holds and a note that the current data stays where it is.
  - The reason it can't be used (Spec 02 §5.8.1's refusals).

  The confirm button names the action: **Move data** or **Use this location**.
- **During a move:** progress, like a scan's. The rest of the app is unavailable until the move finishes, as it would be during a switch of workspace.
- **After a move:** "Your data now lives in …. The previous copy is still in …; you can delete it once you're happy." The app never offers to delete it.
- **Use default location** appears only when a location has been chosen. It runs the same flow against the default folder.
- **Fixed by the environment:** path and source are shown; *Change…* and *Use default location* are not.
- **Missing location:** if the chosen location can't be reached at launch, the app opens on a notice in place of every page, not just this tab. The notice names the folder and offers *Try again* and *Choose another location*, the latter opening this flow.
- **Not a Journal entry:** the data location changes where results are kept, not what is computed (§5), so it has no entry (v0.13; was: not in the changelog).
- **Browser mode:** the section isn't shown (Spec 02 §5.9); §5.2.1 takes its place.

### 5.2.1 Storage (App tab, browser host, v0.15)

**Question answered:** "Is my data safe on this device, and how do I keep a copy?" Shown when the host reports `persistent_storage_status` and not `data_location` (Spec 03 §6.4).

- **Shown:** space used by all workspaces (`navigator.storage.estimate()`), and one line: *The browser has agreed to keep this data* or *The browser may clear this data if space runs low — export a copy to be safe*. A note says logs stay in the pilot's own folders and are never stored here.
- **Export all workspaces…** runs Spec 02 §7.2's export for each workspace in turn, one file each.
- **Delete all data on this device** removes the data root after a confirmation that names the number of workspaces; the next launch is a first run. It never touches log folders.
- **Not a Journal entry**, for the same reason as the data location.
- The one-time durable-storage request happens when the first workspace is created (Spec 02 §9), not from this panel; the panel only reports the outcome.

### 5.3 Log channels (Engine tab, v0.14)

**Question answered:** "My avionics log a channel the app doesn't know the meaning of — what is it?"

Some sources (Garmin AXIS today) write general-purpose analog inputs under generic names; what they carry is wired per aircraft — CO ppm on one, a backup bus voltage on another. The app never guesses (Spec 01 §6.5). This panel is where the pilot says.

- **Shown:** one row per raw general-purpose channel seen in any log of the workspace (`gp_analog_3`, `gp_analog_7`, …), with the source that logs it, the value range observed, and its assignment — *Not assigned* (default) or a registry channel name with its unit. Rows appear only once a source logging such channels is in the workspace; a G3X-only workspace shows the panel with *No general-purpose channels in this workspace's logs.*
- **Assigning:** a picker listing registry channels the source does **not** log natively (so `co_ppm` is offered for an AXIS log, `rpm` is not), plus *Not assigned*. A one-line inline help (§7.4) explains that the meaning comes from the aircraft's EIS configuration and that an unassigned channel stays viewable under its raw name.
- **Scope label (§7.5):** *All flights in this workspace.*
- **Effect:** the assigned channel appears under its registry name in charts, the channel picker and any CAS co-active readings (Spec 01 §8.6); the raw name disappears from the picker for that channel. Flights whose logs carry the raw channel become *Needs re-analysis* (Spec 02 §8); Sync asks before re-running (Spec 03 §5.1).
- **Changed setting:** an assignment differs from the shipped value (none), so it carries the §5 marker, a Journal entry *Log channels — analog 7 is CO ppm (AXIS)*, and *Reset to shipped* (clears it).
- **Export:** assignments travel with the workspace (Spec 02 §7.1), so a recipient sees the same channel names.
- **Not here:** renaming or re-uniting native channels; engine overrides (their own row when designed); Research-mode channel definitions (Spec 06).

## 6. Journal

The Annotations page (Spec 03 §5.6; "Notes" in Spec 09 and in conversation) is renamed **Journal** and redefined. It is the user's **register of decisions in force**: every decision (§3) is created somewhere else in the flow — on a card, in Flights, in the editor panel, from a Research task — and is listed here while it stands, for review, editing and reversal. Journal creates nothing itself except a free-text annotation.

**Register, not log (v0.10; reconciled v0.11).** An entry exists exactly as long as its decision does, and the register is **derived from its sources** — `filters.json`, `rules/active.json` against shipped, exclusions, pins, annotations — and reconciled with them on every read, so a decision made or undone by any path (the app, a CLI, a hand edit) is reflected without a separate write. Reversing a decision (removing a filter, enabling a topic, including a flight again, reverting a rule, unpinning, deleting a note) **removes** the entry. Re-editing a decision **updates** its entry in place — a filter edited three times is one entry showing its current values. The page never shows closed, struck-through or superseded entries, and never shows a sequence of changes to one decision. History is not Journal's job, and since v0.13 there is no separate configuration history either: filter history stays in `LimitFilter.history[]` (Spec 09 §9), reference history in Spec 12's shift history.

### 6.1 Entries

| Kind | Created from | Updated by | Removed by |
|---|---|---|---|
| Acknowledged insight (one insight, one flight) | insight card | — | un-acknowledge on the card or here |
| Limit / alert filter (Spec 09) | Events row, insight card | editing the filter (preview first) | removing the filter |
| Disabled topic | topic card, editor panel | — | *Enable* |
| Rule edit (§7.2) — derived: exists while `rules/active.json` differs from shipped for the topic | editor panel (or any edit of the active rules) | a further edit of the same rule | *Reset to shipped* |
| Changed setting (v0.13) — derived: exists while a results-affecting setting (§5) differs from shipped; one entry per setting, per-metric overrides one entry per metric | Settings → Reference & Models (or any edit of `baseline_config`) | a further edit of the same setting | *Reset to shipped*, here or in Settings |
| Flight excluded from reference (§7.1) | insight card, Flights row, Flight view header | editing the reason | *Include again* |
| Reference pinned (Spec 12) | Trends, Reference & Models | re-pinning | *Unpin* |
| Annotation (free text on a flight, event or time) | any card, Events row, Trends time axis (Spec 12 v2), Journal | editing the text | deleting it |

Each entry carries: what the decision is **now** (current values; for a rule edit, the current value and the shipped default), where it applies (link to the flight, limit, topic or metric), the reason/note, when it was made and last changed, and its **live counted effect** — recomputed when the page opens, not stored: "suppressing 9 events on 6 flights", "removing 11 insights on 9 flights", "excluded: changes 2 verdicts". A decision whose live effect is zero is shown with that fact ("currently suppresses nothing"), which is itself the cue to remove it.

**Imported decisions.** Decisions that predate `journal.json` (existing filters, exclusions, pins) are imported once, as ordinary entries dated to the import. No *backfilled* badge: with live effects there is no missing "before" state to apologise for. Import is idempotent, keyed on the source record.

### 6.2 Change notices

Oct 4 principle 3 — the system's job is to tell the user when something changed in their operations. Journal is where those notices live, on the live entry: a filter whose reference has drifted (Spec 09 §8), an excluded flight whose exclusion no longer changes any verdict, a pinned reference now older than the recent window, a decision whose live effect has fallen to zero. Each notice sits on its entry with the same preview-and-apply controls as the original decision, and clears when the decision is edited, confirmed or removed. "Effect has grown since made" is no longer a separate notice: the live effect on the entry says so.

### 6.3 Journal and Settings (v0.13)

**Journal answers one question: what is in force now that makes my results differ from the shipped app?** Decisions about results (filters, exclusions, acknowledgements, disabled topics, pins, annotations) and changed settings (rule edits, Reference & Models values) are all entries, derived from their sources and removed when reverted. **Settings is where settings are edited**; it marks changed values and links to their entries, and keeps no history. The v0.10–v0.11 split — Settings for what changes the computation, Journal for decisions about results, with a changelog for history — is withdrawn: the line didn't hold for rule edits, and the question it served (history) isn't one the user asks.

### 6.4 Layout

Most recently changed first, with kind chips to filter and grouping by date or by flight as in Flights. Change notices float to the top while unresolved. Every entry offers edit (where the kind allows) and remove, each with the §7.5 scope caption and the preview the original decision had. An empty Journal says so in one line.

## 7. Workflows

### 7.1 Excluding a flight from the reference

**Terminology.** "In baselines" (Flights column), "Included in baselines / Excluded (reason)" (Flight view header) and "Fleet selection" (Baselines) become **"In reference"**, **"Contributes to reference / Excluded from reference (reason)"**, and **"Contributing flights"**. No internal name changes.

**Three entry points, one outcome.**

- **From an insight card** (new). Any insight that compares against a reference — `baseline_deviation`, outlier, `trend` — offers *Exclude this flight from reference →*. A small dialog takes the reason (required) — one field, since `FleetSelection.excluded` stores one string. This is the entry point most pilots will use: they are looking at the flight that is wrong, and the reason is in front of them.
- **From Flights** (exists). The "In reference" toggle on the row, same dialog.
- **From a Trends point.** Click-through to Flight view, then the card action. No exclusion directly from the chart, so the reason is always given with the flight in view.

**After confirming:** the reference recomputes (explicit rebuild, or the pending-rebuild banner if rebuild is deferred — Spec 03 principle 3); the Flight view header shows the new state; a Journal entry is written; every insight on other flights whose verdict changed because the reference moved carries a **"reference changed"** marker (Spec 11), and Trends' change summary notes the recomputation (Spec 12).

**Reversal:** *Include again* from the Flights toggle, the Flight view header, or the Journal entry — through the same dialog and preview as *Exclude* (v0.6), since it has the same consequence in reverse. The Journal entry is removed (§6, v0.10).

**Not offered:** bulk exclusion by rule ("all flights under 20 minutes"). That is membership, and membership is folders. An excluded flight is still analysed and still shows its own insights; it only stops shaping other flights' reference.

### 7.2 Editing a rule on the card

The Rules playground is retired as a page. Its reason to exist — seeing the fleet-wide consequence of a threshold change *before* committing to it — is kept and moved to where the decision is actually made: the insight card. The user must see the implication of a decision before applying it, and must not have to leave the flight to do so.

**Edit flow**

1. The card shows the setting that produced the insight, e.g. *trend · R² ≥ 0.5 · n ≥ 10* (Spec 11: observation insights ship on by default with their settings on the card). From v0.3 the same edit is available on the topic card whether or not an insight fired — §7.3.
2. The user changes a value inline.
3. Before anything is applied, the card shows the **preview** across the workspace, computed by the existing `whatIfRules` path (`evaluate_insights` against every contributing flight):
   *"On your 42 flights: 4 changes (1 newly flagged, 3 cleared, 0 changed severity)"* — counts are flights, not insights; affected flights are linked. While computing, the card says so rather than promising an instant answer (Pyodide mode, large workspaces).
4. **Apply** writes `rules/active.json` — still one workspace-wide copy (Spec 03 Q2), never a per-flight rule — and a Journal entry showing the rule's current value against the shipped default (a further edit updates the same entry; *Reset to shipped* removes it, §6 v0.10). **Cancel** discards. **Reset to shipped** is offered per rule in the editor panel and from the Journal entry; it is the only reversal of a rule edit — there is no separate *Revert* to a previous value (v0.11).

**Same shape for silencing**, scaled to scope (Spec 11's three levels): acknowledge → "this card only"; filter → "suppresses 7 events across 5 flights"; disable topic → "removes 11 insights across 9 flights". One pattern, learned once, for every decision that changes what is shown. Only the filter level exists today (Spec 09); acknowledge and disable-topic arrive with Spec 11 — Journal shows their kinds empty until then, never fabricated.

**Reverse path.** When a later flight carries a "rule changed" or "reference changed" marker, the card shows what changed, when, and the reason given, and offers the decision's reversal with the same preview — *Reset to shipped* for a rule change, *Include again* / *Unpin* for a reference change (v0.11: the marker's action is the Journal entry's removal, not a separate undo).

**What moves where**

| From Baselines & Models (today) | To |
|---|---|
| Per-topic trigger editing with live diff | Topic card on Flight view (§7.3), including the insight card when one fired |
| Global `outlier_z_threshold` | Settings → Reference & Models (`n_min` stays per trigger, edited on the topic card) |
| "Reset to shipped defaults" (all rules) | Settings → Reference & Models |
| Limit filter drift read-out | Journal change notices (§6.2) |
| Fleet selection summary | Settings → Reference & Models, "Contributing flights" |
| Engine overrides placeholder | Settings → Engine |
| Fleet-wide rule browser, systematic tuning across many thresholds | Research, when designed. Not a v1 need: a contributor validating a rule change before a PR is doing research |

**Guards**

- A rule the engine never evaluates must not be editable. Spec 10 §6.1's removals (`flight_phase_mix`, `egt4_elevation`) and the `map_at_takeoff` config fix land before or with this spec.
- The preview counts insights by (`rule_id`, `severity`) per flight, as the playground's diff does today; a change in analysis-line wording alone is not a change.

### 7.3 Editing a rule on the topic card (v0.3)

**Problem found in implementation.** An insight card exists only once its trigger has fired. A trigger that never fires — today, every `trend` trigger, since no metric reaches R² ≥ 0.5 on the real flight set — has no card and therefore no entry point. The retired playground could edit any rule; the insight card cannot.

**Decision.** The edit affordance lives on the **topic card** in Flight view's Analysis section, which exists for every topic on every flight (Spec 03 §5.2: the analysis line is always present, the insight line conditional). The insight card is the topic card with an insight; the edit is the same control in both states. Settings gains no rule list — a trigger threshold decides what is *shown*, so it is a decision made where results are shown, not configuration.

**Topic card, disclosed detail (amended v0.9).** The card keeps its analysis line. A disclosure ("triggers") opens the topic's triggers with their current values and, per trigger, whether it was met on this flight and by how much — e.g. *trend · R² ≥ 0.5 · n ≥ 10 — not met: R² 0.30 over 23 flights* — and the topic's `enabled` state. **Nothing on the card is editable.** One action, **Edit rules…**, opens the rule editor panel.

**Rule editor panel (v0.9).** A side sheet over the Flight view, opened from a topic card or from an insight card's *Edit trigger ↓*. It carries the topic, the originating flight and the current rule set. Each value is editable with the §7.2 flow unchanged: preview before apply (fleet-wide, the originating flight highlighted), Apply writes `rules/active.json` and a Journal entry, Cancel discards, Reset to shipped per rule; the `enabled` toggle is here too. Every control carries its §7.5 scope caption. Closing the panel returns to the card at the same scroll position. The panel is the one editor; no inputs are rendered anywhere on the Flight view outside it. Why: the Flight view is a reading surface for every pilot; the editor is a mode a researcher asks for (Spec 03 principle 6). v0.3's reason for editing from the card — a never-firing trigger needs an entry point — is unchanged, since the panel is opened from that card.

**Scope.** All trigger types (`threshold`, `baseline_deviation`, `trend`, structural conditions where only severity is editable) and the topic's `enabled` flag, which is the same thing as Spec 11's disable-topic level and reports its scope before apply like any other edit. Topics whose rules the engine does not evaluate are not shown (§7.2 guards).

**One editor, reachable from the insight (v0.4, amended v0.9).** The editor panel is rendered once. The insight card carries *Edit trigger ↓*, which opens the panel for that topic; the topic card's disclosure carries *Edit rules…*, which does the same. The pilot who saw the insight gets to the edit in one click; the implementation stays single.

**Disabled topic (v0.5, clarified v0.6).** A disabled topic's card does not disappear. It stays in Analysis, collapsed to one line — *EGT spread · disabled · Enable* — with empty analysis text and no insight, and is not counted among topics "analysed with nothing to flag". *Enable* uses the same preview-before-apply flow and **removes** the `disabled_topic` Journal entry (§6 v0.10). Uniform for every topic **that has a card**, `egt_cyl_deviation` included; topics whose rules are fixed in engine code and have no card get no collapsed line either (§7.2 guards). The engine still returns a topic result for a disabled topic — `enabled: false`, empty `analysis.text`, no `trigger_status`, no `limit_refs`, no insight — in its usual position (Spec 01 to record).

**Guard (v0.4).** Every evaluated topic honours its `enabled` flag before evaluating — found in v0.3 that four did not (`overboost_time`, `map_at_takeoff`, `engine_ecu_inflight`, `limit_exceedances`), so disabling them wrote the file and the Journal but suppressed nothing. The fix is a correctness change, not a heuristic change, but goes through the Spec 10 / `CLAUDE.md` snapshot comparison like any engine edit. For `limit_exceedances`, disabling the topic hides its *insights*; limit *events* are still detected and still feed Spec 09 filters and the Trends per-limit metrics, since those are not the topic.

### 7.4 Inline help (v0.4)

**When.** A parameter or section gets inline help only when its label and value do not tell a pilot what it does and what changing it affects. Not every field; the test is "would a pilot who has never read a spec know what happens if they change this?"

**What.** One sentence, plain language. It names the consequence, not the statistic: *R² ≥ 0.5* alone is not help; *how clearly the points must line up before a trend is reported — lower reports trends sooner, with more false alarms* is. No sentence longer than the field it explains deserves.

**How.** Disclosed — an ⓘ or a short caption under the field — never a paragraph in the layout. All help text lives in **one registry keyed by setting or trigger id**, so Spec 13's documentation can reuse it and the two cannot drift.

**Where (v1 list; nothing added outside it without reporting).**

| Surface | Gets help | Does not |
|---|---|---|
| Settings → Reference & Models | `outlier_z_threshold`; recent window; pinning; "contributing flights"; stratification (why DA for some metrics, OAT for others) | the flight count itself; *Rebuild reference* |
| Settings → Engine | phase-aware suppression windows; what "overrides: none" means | the limit values (they carry the OM reference) |
| Topic card triggers | `r2_min`, `n_min`; `baseline_deviation` (what the reference is, what σ means here); `enabled` (*stops this topic reporting; past Journal entries stay*) | `threshold` against an OM limit; severity. (`margin_min_f`, `consecutive_flights` are fixed in engine code, not editable — if they become triggers: *how much hotter than the next cylinder the hottest must be before it counts — lower notices a change sooner but reacts to near-ties*; *how many flights in a row a different cylinder must be hottest before it is reported — fewer reports sooner, more ignores one-off flights*) |
| Preview | what *N changes (x newly flagged, y cleared, z changed severity)* counts — flights, not insights | — |
| Journal | live counted effect (what it counts, that it is recomputed); change notices (generic wording — a decision whose basis has moved — with the limit filter as the example, not the only case) | entry kinds |
| Flight view header | *Excluded from reference* (still analysed; no longer shapes other flights) | *Contributes to reference* |

### 7.5 Scope labelling (v0.4)

**Problem.** A trigger edited on a topic card changes `rules/active.json`, which is workspace-wide — but the pilot is standing on one flight when they edit it, so the natural reading is "fix this flight". The preview ("on your 50 flights…") says otherwise, but only after the edit. Pinning a reference on Trends has the same ambiguity.

**Rule.** Every decision control states its scope **before** the user touches it, with the same fixed wording everywhere, and the Apply button repeats it. There are three scopes:

| Scope | Caption | Controls |
|---|---|---|
| This flight | *This flight only* | acknowledge (Spec 11); exclude from reference and *Include again* — with the note *other flights' comparisons will move* |
| This metric or limit, all flights | *All flights in this workspace — this metric* / *— this limit*. For a CAS target the noun is *this alert*. | pin / unpin reference (Trends, Reference & Models); limit filters (Spec 09); delete a shift-history event (Trends, Spec 12) |
| This topic, all flights | *All flights in this workspace — this topic* | every trigger edit; `enabled` / *Enable* |
| Every metric or limit, all flights | *All flights in this workspace — every metric* / *— every limit copied* | Reference & Models save (`outlier_z_threshold`, window); copy filters between workspaces (Spec 09 §9) |
| The decision being undone | the caption of the original decision | Journal reversals (Reset to shipped, Unpin, Remove, Include again) |

**Not a §7.5 control:** grouping tail numbers as one aircraft is a workspace definition, not a decision about results; it is shown where it is defined (the workspace's settings), not in Journal (v0.13).

**Placement.** A one-line caption at the top of the disclosure or dialog; the Apply button reads *Apply to this flight* or *Apply to all flights*; the preview then confirms the count. The caption is not help text (§7.4) — it is always visible, not disclosed.

## 8. Impact on existing specs

| Spec | Change |
|---|---|
| **03** | §5.2 Flight view: topic card gains the triggers disclosure (§7.3), the "Contributes to reference / Excluded" header, exclude-from-card, and the "reference changed" / "rule changed" markers; §4 nav per §4 here; §5.5 replaced by a pointer to §5.1 here; §5.6 Annotations → Journal (§6 here); §5.7 Settings → tabbed section (§5 here); principle 6 restated: tuning happens on the card and in Settings, Research is the destination for systematic work; wireframes `Baselines.dc.html`, `Annotations.dc.html`, `Settings.dc.html` superseded |
| **09** | Filter management stays with the user's decisions (Journal). The v0.2 "what would this hide?" preview is the same pattern as §7.2; the per-limit drift threshold remains the metric's `outlier_z_threshold`, edited in Reference & Models |
| **01** | `trigger_status` and `enabled` per topic are now in the engine contract (v0.3 implementation); every evaluated topic honours `enabled` (§7.3 guard); a disabled topic still returns a topic result in its usual position with `enabled: false`, empty `analysis.text`, no `trigger_status`, no `limit_refs` and no insight; topics with no card return nothing (v0.5–0.6). To be recorded at Spec 01's next revision |
| **13** (deferred) | Inline help text (§7.4) is the first tier of user documentation; Spec 13 reuses the registry rather than rewriting it |
| **11** (paused) | Adopt §7.1 (exclude from a card), §7.2 and §7.3 (edit with preview before apply, on the topic card; silencing levels report scope before apply; "reference changed" / "rule changed" markers with Revert) when it resumes. The topic `enabled` flag edited per §7.3 *is* the disable-topic level |
| **12** | Recent window and pinning are configured in Reference & Models; the change summary notes reference recomputation after an exclusion |
| **02** | No schema change. `FleetSelection`, `rules/active.json`, `annotations.json` and the settings split are unchanged; only where they are edited moves. v0.12: the data location (§5.2) is Spec 02 v0.10 §5.8.1 |
| **10** | §6.1 removals become a prerequisite (§7.2 guards) |

## 9. Acceptance criteria

1. The top-level nav shows Flights, Trends, Journal and the Settings gear; no Baselines, ECU or Research entry (ECU removed v0.7).
2. Settings has Engine, Reference & Models and App tabs. No changelog is shown or written (v0.13); every results-affecting setting that differs from shipped is marked with its shipped value and links to its Journal entry.
3. No user-facing string says "baseline(s)"; "reference" is used throughout. Internal names unchanged.
4. A flight can be excluded from the reference from a `baseline_deviation`, outlier or trend insight card, with a required reason, and the exclusion appears in Flights, Flight view, Reference & Models and Journal; *Include again* works from each of Flights, Flight view and Journal.
5. Editing a rule value on a topic card (with or without a fired insight) shows the fleet-wide preview (added / removed / severity-changed insights, flights linked) before Apply; Apply writes `rules/active.json` and a Journal entry with the counted effect; Cancel leaves `rules/active.json` byte-identical.
6. The preview from the card equals the retired playground's diff for the same edit, verified on the project logs for at least one `threshold`, one `baseline_deviation` and one `trend` trigger.
7. Each of the three silencing levels states its scope (count of insights / events / flights) before Apply.
8. After an exclusion that changes any other flight's verdict, that flight's card carries the "reference changed" marker and *Include again* from it restores the previous verdict.
9. Journal lists every entry kind in §6.1, most recently changed first, each with its live counted effect and removal from the entry; a reversed decision's entry is **gone** (v0.10), a re-edited decision has **one** entry.
10. `Baselines.tsx`'s rule playground is removed; no route serves it.
11. (v0.3) Every trigger of every evaluated topic can be edited from the topic card on a flight where it did not fire, verified on the project logs by loosening a `trend` trigger (`egt_spread`, `r2_min`) from a flight with no trend insight and seeing the preview report the flights that would gain one.
12. (v0.3, v0.10) Opening a workspace that predates `journal.json` from two clients at once produces exactly one imported entry per source record, indistinguishable from a user-made one apart from its date.
13. (v0.4) Every evaluated topic, disabled from its topic card, produces no insight on any flight in the project logs; `limit_exceedances` disabled still yields limit events to Spec 09 filters and Trends. Snapshot comparison shows no other change.
14. (v0.4) *edit trigger ↓* on an insight card lands on its topic card with the disclosure open; there is one editor implementation.
15. (v0.4) Every item in §7.4's "Gets help" column has help; no help text exceeds one sentence; all help text is in one registry; nothing in the "Does not" column has help.
16. (v0.4) Every control in §7.5's table shows its scope caption before interaction and on its Apply button, with the fixed wording; no decision control exists outside the table without one.
17. (v0.5) Disabling any topic from its card leaves a one-line collapsed card with *Enable* on every flight; *Enable* previews, applies and removes the Journal entry; `egt_cyl_deviation` behaves identically to the others.
18. (v0.6) *Include again* from Flights and Flight view opens the exclusion dialog with its scope caption and preview; Trends shift-history delete carries its caption; the Settings `n_min` list shows a disabled topic marked *disabled*.
19. (v0.12) In local-server mode, Settings → App shows the data root and its source.
    - A move into an empty folder copies every workspace. The app reopens on the same workspace, and flights, filters, Journal and app settings are identical. The old folder is untouched.
    - Choosing a folder that holds a registry switches to it without copying.
    - A non-empty folder without a registry is refused, and nothing is written.
    - With `SLINGOLOGY_EIS_HOME` set, the location can't be changed from the UI.
    - A missing chosen location opens on the notice, not on the defaults.
20. **Changed settings in Journal (v0.13).** Changing the global `outlier_z_threshold`, a per-metric override or the recent window creates one Journal entry per setting showing current and shipped values and the live effect; a further change updates it in place; *Reset to shipped* (in Journal or Settings) removes it and leaves `baseline_config` at the shipped value. Changing units creates no entry. An existing `settings_changelog.json` is ignored and not deleted. With every setting at shipped, Journal shows no setting entries.
21. (v0.15) In the browser host, Settings → App shows the Storage panel (§5.2.1) and not the data location; the reverse in local-server mode; both decided by the host's features, not by inspecting the URL.

## 10. Open questions

| # | Question | Leaning |
|---|---|---|
| Q1 | Does the Engine tab show overrides in v1, or only the shipped profile until `engine_overrides.json` is designed? | Shipped profile only, read-only, with the suppression windows visible. No evidence yet that a shipped profile needs overriding (Baselines.tsx comment). |
| Q2 | Journal grouping: by kind or by time? | Time, newest first, with kind chips — same as Flights. Change notices pinned to the top while unresolved. |
| Q3 | ~~Is Research shown in the nav before Spec 06 exists?~~ | **Resolved v0.2 — no.** Hidden until Spec 06 is designed; no placeholder. |
| Q4 | Should the card preview run on every keystroke (playground behaviour, debounced) or on an explicit "Preview" step? | **Local-server mode resolved v0.3:** debounced live preview — measured 57 ms mean (48–75 ms, 5 runs) for a what-if round trip on 53 real flights. **Pyodide mode:** measured in Spec 04 §10 step 4 (Spec 04 Q8); explicit step if > ~1 s. |
| Q5 | Does a reversed rule edit restore the exact previous values or the shipped default? | Exact previous values (the Journal entry holds them); "reset to shipped" is a separate action. |
