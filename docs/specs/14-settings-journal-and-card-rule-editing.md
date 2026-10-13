# Spec 14 — Settings, Journal, and Rule Editing on the Card

**Project:** SlingologyEIS web platform
**Status:** v0.6 — v0.2–v0.5 implemented on `webui` (`ac62b20`…`282631c`; `4839600`…`03c0017`; `c68c145`…`d84ee5d`; `55e6b32`…`dfe88a6`, 2026-10-11/12). v0.6 (tidy-up: §7.5 additions, *Include again* through the exclusion dialog, Settings `n_min` list shows disabled topics) implemented 2026-10-13. **Spec implemented**; remaining follow-ups live elsewhere: Spec 01 revision note (§8), Spec 11 silencing levels, Pyodide preview latency (Q4). §4–§7 decided, §10 open.
**Suggested repo path:** `docs/specs/14-settings-journal-and-card-rule-editing.md`
**Builds on:** Spec 02 (`FleetSelection`, `rules/active.json`, `annotations.json`, app-level vs workspace-level settings §6.4), Spec 03 (§3 principle 6, §4 nav, §5.5 Baselines & models, §5.6 Annotations, §5.7 Settings), Spec 09 (filters, "what would this hide?" preview v0.2, Notes page), Spec 10 (§6.1 rules that do not reflect what runs), Spec 11 (insight layer — paused; three silencing levels, settings shown on the card), Spec 12 (Trends as a change page — recent window, reference pinning)
**Supersedes:** Spec 03 §5.5 (the rule playground as a page) and the part of principle 6 that places all tuning in Baselines & Models
**Baseline reviewed:** branch `webui` at commit `5d029fc` (2026-10-05); `web/src/views/Baselines.tsx`, `Annotations.tsx`, `Settings.tsx`; `insight_rules.json` v1.3; `engines/916iS.json`

**Revision history**

| Version | Change |
|---|---|
| 0.6 | **From implementation of v0.5.** §7.5 table gains the controls found outside it: Reference & Models save (*every metric*), copy filters (*every limit copied*), Journal reversals (scope of the decision undone), Trends shift-history delete (*this metric*). *Include again* uses the same dialog and preview as *Exclude* rather than acting in one click (§7.1). Tail-number grouping is a workspace definition, not a §7.5 decision — it goes to the Settings changelog. §7.3 clarified: the collapsed card applies to every topic that has a card; topics with no card (fixed in engine code) get none; *Enable* closes the open `disabled_topic` entry. Settings `n_min` list shows disabled topics marked *disabled* instead of hiding them (§5.1). Spec 01 note made concrete. |
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
| The grouping of top-level destinations by activity (§4) | Each view's own content: Flights (Spec 03 §5.1), Flight view (§5.2), Trends (Spec 12), ECU (§5.4) |
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
| Fly and look | read, every flight | Flights · Flight view · Trends · ECU |
| Decide about results | act in context, review later | **Journal** (§6) |
| Investigate | iterate, produce a finding | Research (Spec 06, reserved) |
| Configure the computation | set, rarely revisit | **Settings** (§5), from the gear icon |

Nav shell (replaces Spec 03 §4's sketch):

```
[Logo]  [Workspace: N117ZS ▾]   Flights   Trends   ECU   Journal   ⚙
```

Four everyday destinations, Journal beside them, Settings behind the gear. Baselines leaves the top level. Research is **not shown** until Spec 06 is designed (Q3, decided v0.2) — no placeholder. When it arrives it is a distinct destination with a defined path *out*: a finding becomes a Journal decision or a Settings change carrying provenance ("filter created from Research task #4"), per Spec 03 principle 6's Explore → operational path.

## 5. Settings

Settings becomes a section with tabs. It holds everything that changes what the engine computes, split as Spec 02 §6.4 already splits the files.

| Tab | Contents | Source |
|---|---|---|
| **Engine** | Active engine profile and version; the OM limits it ships, read-only, with phase-aware suppression shown per limit; engine overrides when designed (`reason`/`source` mandatory) | `engines/<model>.json`, `engine_overrides.json` |
| **Reference & Models** | §5.1 | `FleetSelection.baseline_config`, `baselines.json`, `models.json` |
| **App** | Units; last active workspace; anonymise-on-export default; platform notes (Safari folder re-pick) | app-level settings |

The three tabs share **one changelog** — "what changed in your analysis settings", newest first, each entry naming the setting, before/after, and who/what changed it (user, Research task, app upgrade). One list rather than three, so a pilot asking "why does this flight look different from last month" has one place to check. Entries are also mirrored into Journal when they resulted from a decision (§6.3).

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

## 6. Journal

The Annotations page (Spec 03 §5.6; "Notes" in Spec 09 and in conversation) is renamed **Journal** and redefined. It is the user's decision journal: every decision (§3) is created somewhere else in the flow — on a card, in Flights, from a Research task — and lands here for review, editing and reversal. Journal creates nothing itself except a free-text annotation.

### 6.1 Entries

| Kind | Created from | Reversible by |
|---|---|---|
| Acknowledged insight (one insight, one flight) | insight card | Journal, the card |
| Limit filter (Spec 09) | limit-exceedance insight card | Journal, the card; editing shows the "what would this hide?" preview |
| Disabled topic | insight card, topic card | Journal |
| Rule edit (§7.2) | insight card | Journal (revert, with preview), the card |
| Flight excluded from reference (§7.1) | insight card, Flights row | Journal, Flights row, Flight view header |
| Reference pinned (Spec 12) | Trends, Reference & Models | Reference & Models |
| Annotation (free text on a flight, event or time) | any card, Trends time axis (Spec 12 v2), Journal | Journal |

Each entry carries: what, where it was made (link), when, the reason/note, and the **counted effect at the time** ("suppressed 7 events on 5 flights"; "removed this insight here and on 3 others").

**Backfilled entries.** Decisions that predate the Journal (existing filters, exclusions, pins) are imported once, marked *backfilled*, dated to the import, and carry no counted effect — the "before" state no longer exists. Backfill is idempotent: keyed on the source record, so two readers opening a workspace at once cannot create the same entry twice.

### 6.2 Change notices

Oct 4 principle 3 — the system's job is to tell the user when something changed in their operations. Journal is where those notices live: a filter whose reference has drifted (Spec 09 §12), a rule edit whose counted effect has grown since it was made, an excluded flight whose exclusion no longer changes any verdict, a pinned reference that is now older than the window. Each notice sits on its entry, with the same preview-and-apply controls as the original decision.

### 6.3 Relationship to the Settings changelog

A Settings change made *because of* a decision (an exclusion from a card, a pin from Trends) appears in both: the Settings changelog records the configuration change; Journal records the decision and its reason. The two link to each other. A Settings change made directly in Settings appears only in the changelog.

### 6.4 Layout

Newest first, with kind chips to filter and the same grouping affordances as Flights (by date, by flight). Change notices float to the top while unresolved. Nothing is deleted: a reversed decision is closed, shown struck through, and keeps its history.

## 7. Workflows

### 7.1 Excluding a flight from the reference

**Terminology.** "In baselines" (Flights column), "Included in baselines / Excluded (reason)" (Flight view header) and "Fleet selection" (Baselines) become **"In reference"**, **"Contributes to reference / Excluded from reference (reason)"**, and **"Contributing flights"**. No internal name changes.

**Three entry points, one outcome.**

- **From an insight card** (new). Any insight that compares against a reference — `baseline_deviation`, outlier, `trend` — offers *Exclude this flight from reference →*. A small dialog takes the reason (required) — one field, since `FleetSelection.excluded` stores one string. This is the entry point most pilots will use: they are looking at the flight that is wrong, and the reason is in front of them.
- **From Flights** (exists). The "In reference" toggle on the row, same dialog.
- **From a Trends point.** Click-through to Flight view, then the card action. No exclusion directly from the chart, so the reason is always given with the flight in view.

**After confirming:** the reference recomputes (explicit rebuild, or the pending-rebuild banner if rebuild is deferred — Spec 03 principle 3); the Flight view header shows the new state; a Journal entry is written; every insight on other flights whose verdict changed because the reference moved carries a **"reference changed"** marker (Spec 11), and Trends' change summary notes the recomputation (Spec 12).

**Reversal:** *Include again* from the Flights toggle, the Flight view header, or the Journal entry — through the same dialog and preview as *Exclude* (v0.6), since it has the same consequence in reverse. The Journal entry is closed, not deleted.

**Not offered:** bulk exclusion by rule ("all flights under 20 minutes"). That is membership, and membership is folders. An excluded flight is still analysed and still shows its own insights; it only stops shaping other flights' reference.

### 7.2 Editing a rule on the card

The Rules playground is retired as a page. Its reason to exist — seeing the fleet-wide consequence of a threshold change *before* committing to it — is kept and moved to where the decision is actually made: the insight card. The user must see the implication of a decision before applying it, and must not have to leave the flight to do so.

**Edit flow**

1. The card shows the setting that produced the insight, e.g. *trend · R² ≥ 0.5 · n ≥ 10* (Spec 11: observation insights ship on by default with their settings on the card). From v0.3 the same edit is available on the topic card whether or not an insight fired — §7.3.
2. The user changes a value inline.
3. Before anything is applied, the card shows the **preview** across the workspace, computed by the existing `whatIfRules` path (`evaluate_insights` against every contributing flight):
   *"On your 42 flights: 4 changes (1 newly flagged, 3 cleared, 0 changed severity)"* — counts are flights, not insights; affected flights are linked. While computing, the card says so rather than promising an instant answer (Pyodide mode, large workspaces).
4. **Apply** writes `rules/active.json` — still one workspace-wide copy (Spec 03 Q2), never a per-flight rule — and a Journal entry with before/after values and the counted effect. **Cancel** discards. **Reset to shipped** is offered per rule on the card.

**Same shape for silencing**, scaled to scope (Spec 11's three levels): acknowledge → "this card only"; filter → "suppresses 7 events across 5 flights"; disable topic → "removes 11 insights across 9 flights". One pattern, learned once, for every decision that changes what is shown. Only the filter level exists today (Spec 09); acknowledge and disable-topic arrive with Spec 11 — Journal shows their kinds empty until then, never fabricated.

**Reverse path.** When a later flight carries a "rule changed" or "reference changed" marker, the card shows what changed, when, and the reason given, and offers **Revert** with the same preview.

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

**Topic card, disclosed detail.** The card keeps its analysis line as today. A disclosure ("triggers") opens the topic's triggers with their current values and, per trigger, whether it was met on this flight and by how much — e.g. *trend · R² ≥ 0.5 · n ≥ 10 — not met: R² 0.30 over 23 flights*. Each value is editable inline with the §7.2 flow unchanged: preview before apply, Apply writes `rules/active.json` and a Journal entry, Cancel discards, Reset to shipped per rule. Closed by default so the analysis card is no busier than today.

**Scope.** All trigger types (`threshold`, `baseline_deviation`, `trend`, structural conditions where only severity is editable) and the topic's `enabled` flag, which is the same thing as Spec 11's disable-topic level and reports its scope before apply like any other edit. Topics whose rules the engine does not evaluate are not shown (§7.2 guards).

**One editor, reachable from the insight (v0.4).** The disclosure is rendered once, on the topic card in Analysis. The insight card above it does not carry a second editor; it carries *edit trigger ↓*, which scrolls to the topic card and opens its disclosure. The pilot who saw the insight gets to the edit in one click; the implementation stays single.

**Disabled topic (v0.5, clarified v0.6).** A disabled topic's card does not disappear. It stays in Analysis, collapsed to one line — *EGT spread · disabled · Enable* — with empty analysis text and no insight, and is not counted among topics "analysed with nothing to flag". *Enable* uses the same preview-before-apply flow and **closes** the open `disabled_topic` Journal entry (no second entry). Uniform for every topic **that has a card**, `egt_cyl_deviation` included; topics whose rules are fixed in engine code and have no card get no collapsed line either (§7.2 guards). The engine still returns a topic result for a disabled topic — `enabled: false`, empty `analysis.text`, no `trigger_status`, no `limit_refs`, no insight — in its usual position (Spec 01 to record).

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
| Journal | the *backfilled* marker; change notices (generic wording — a past decision whose basis has moved — with the limit filter as the example, not the only case) | entry kinds |
| Flight view header | *Excluded from reference* (still analysed; no longer shapes other flights) | *Contributes to reference* |

### 7.5 Scope labelling (v0.4)

**Problem.** A trigger edited on a topic card changes `rules/active.json`, which is workspace-wide — but the pilot is standing on one flight when they edit it, so the natural reading is "fix this flight". The preview ("on your 50 flights…") says otherwise, but only after the edit. Pinning a reference on Trends has the same ambiguity.

**Rule.** Every decision control states its scope **before** the user touches it, with the same fixed wording everywhere, and the Apply button repeats it. There are three scopes:

| Scope | Caption | Controls |
|---|---|---|
| This flight | *This flight only* | acknowledge (Spec 11); exclude from reference and *Include again* — with the note *other flights' comparisons will move* |
| This metric or limit, all flights | *All flights in this workspace — this metric* / *— this limit* | pin / unpin reference (Trends, Reference & Models); limit filters (Spec 09); delete a shift-history event (Trends, Spec 12) |
| This topic, all flights | *All flights in this workspace — this topic* | every trigger edit; `enabled` / *Enable* |
| Every metric or limit, all flights | *All flights in this workspace — every metric* / *— every limit copied* | Reference & Models save (`outlier_z_threshold`, window); copy filters between workspaces (Spec 09 §9) |
| The decision being undone | the caption of the original decision | Journal reversals (Revert, Unpin, Remove, Include again) |

**Not a §7.5 control:** grouping tail numbers as one aircraft is a workspace definition, not a decision about results; it is recorded in the Settings changelog.

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
| **02** | No schema change. `FleetSelection`, `rules/active.json`, `annotations.json` and the settings split are unchanged; only where they are edited moves |
| **10** | §6.1 removals become a prerequisite (§7.2 guards) |

## 9. Acceptance criteria

1. The top-level nav shows Flights, Trends, ECU, Journal and the Settings gear; no Baselines destination and no Research entry.
2. Settings has Engine, Reference & Models and App tabs, and one changelog listing every change made in any of them.
3. No user-facing string says "baseline(s)"; "reference" is used throughout. Internal names unchanged.
4. A flight can be excluded from the reference from a `baseline_deviation`, outlier or trend insight card, with a required reason, and the exclusion appears in Flights, Flight view, Reference & Models and Journal; *Include again* works from each of Flights, Flight view and Journal.
5. Editing a rule value on a topic card (with or without a fired insight) shows the fleet-wide preview (added / removed / severity-changed insights, flights linked) before Apply; Apply writes `rules/active.json` and a Journal entry with the counted effect; Cancel leaves `rules/active.json` byte-identical.
6. The preview from the card equals the retired playground's diff for the same edit, verified on the project logs for at least one `threshold`, one `baseline_deviation` and one `trend` trigger.
7. Each of the three silencing levels states its scope (count of insights / events / flights) before Apply.
8. After an exclusion that changes any other flight's verdict, that flight's card carries the "reference changed" marker and Revert restores the previous verdict.
9. Journal lists every entry kind in §6.1, newest first, with reversal from the entry; reversed entries are closed, not removed.
10. `Baselines.tsx`'s rule playground is removed; no route serves it.
11. (v0.3) Every trigger of every evaluated topic can be edited from the topic card on a flight where it did not fire, verified on the project logs by loosening a `trend` trigger (`egt_spread`, `r2_min`) from a flight with no trend insight and seeing the preview report the flights that would gain one.
12. (v0.3) Opening a workspace that predates `journal.json` from two clients at once produces exactly one backfilled entry per source record.
13. (v0.4) Every evaluated topic, disabled from its topic card, produces no insight on any flight in the project logs; `limit_exceedances` disabled still yields limit events to Spec 09 filters and Trends. Snapshot comparison shows no other change.
14. (v0.4) *edit trigger ↓* on an insight card lands on its topic card with the disclosure open; there is one editor implementation.
15. (v0.4) Every item in §7.4's "Gets help" column has help; no help text exceeds one sentence; all help text is in one registry; nothing in the "Does not" column has help.
16. (v0.4) Every control in §7.5's table shows its scope caption before interaction and on its Apply button, with the fixed wording; no decision control exists outside the table without one.
17. (v0.5) Disabling any topic from its card leaves a one-line collapsed card with *Enable* on every flight; *Enable* previews, applies and closes the Journal entry; `egt_cyl_deviation` behaves identically to the others.
18. (v0.6) *Include again* from Flights and Flight view opens the exclusion dialog with its scope caption and preview; Trends shift-history delete carries its caption; the Settings `n_min` list shows a disabled topic marked *disabled*.

## 10. Open questions

| # | Question | Leaning |
|---|---|---|
| Q1 | Does the Engine tab show overrides in v1, or only the shipped profile until `engine_overrides.json` is designed? | Shipped profile only, read-only, with the suppression windows visible. No evidence yet that a shipped profile needs overriding (Baselines.tsx comment). |
| Q2 | Journal grouping: by kind or by time? | Time, newest first, with kind chips — same as Flights. Change notices pinned to the top while unresolved. |
| Q3 | ~~Is Research shown in the nav before Spec 06 exists?~~ | **Resolved v0.2 — no.** Hidden until Spec 06 is designed; no placeholder. |
| Q4 | Should the card preview run on every keystroke (playground behaviour, debounced) or on an explicit "Preview" step? | **Local-server mode resolved v0.3:** debounced live preview — measured 57 ms mean (48–75 ms, 5 runs) for a what-if round trip on 53 real flights. **Pyodide mode open:** not measurable in the implementation environment; decide when Spec 04's Pyodide path is next exercised, explicit step if > ~1 s. |
| Q5 | Does a reversed rule edit restore the exact previous values or the shipped default? | Exact previous values (the Journal entry holds them); "reset to shipped" is a separate action. |
