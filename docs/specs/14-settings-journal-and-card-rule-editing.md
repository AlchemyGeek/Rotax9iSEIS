# Spec 14 — Settings, Journal, and Rule Editing on the Card

**Project:** SlingologyEIS web platform
**Status:** Draft v0.2 — ready for implementation. Decisions from the screen-by-screen evaluation of 2026-10-11; §4–§7 decided, §10 open.
**Suggested repo path:** `docs/specs/14-settings-journal-and-card-rule-editing.md`
**Builds on:** Spec 02 (`FleetSelection`, `rules/active.json`, `annotations.json`, app-level vs workspace-level settings §6.4), Spec 03 (§3 principle 6, §4 nav, §5.5 Baselines & models, §5.6 Annotations, §5.7 Settings), Spec 09 (filters, "what would this hide?" preview v0.2, Notes page), Spec 10 (§6.1 rules that do not reflect what runs), Spec 11 (insight layer — paused; three silencing levels, settings shown on the card), Spec 12 (Trends as a change page — recent window, reference pinning)
**Supersedes:** Spec 03 §5.5 (the rule playground as a page) and the part of principle 6 that places all tuning in Baselines & Models
**Baseline reviewed:** branch `webui` at commit `5d029fc` (2026-10-05); `web/src/views/Baselines.tsx`, `Annotations.tsx`, `Settings.tsx`; `insight_rules.json` v1.3; `engines/916iS.json`

**Revision history**

| Version | Change |
|---|---|
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
| Comparison | global `outlier_z_threshold` (default 2.0) and `n_min` (default 10); per-metric overrides where set | editable; "reset to shipped" |
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

- **From an insight card** (new). Any insight that compares against a reference — `baseline_deviation`, outlier, `trend` — offers *Exclude this flight from reference →*. A small dialog takes the reason (required) and an optional note. This is the entry point most pilots will use: they are looking at the flight that is wrong, and the reason is in front of them.
- **From Flights** (exists). The "In reference" toggle on the row, same dialog.
- **From a Trends point.** Click-through to Flight view, then the card action. No exclusion directly from the chart, so the reason is always given with the flight in view.

**After confirming:** the reference recomputes (explicit rebuild, or the pending-rebuild banner if rebuild is deferred — Spec 03 principle 3); the Flight view header shows the new state; a Journal entry is written; every insight on other flights whose verdict changed because the reference moved carries a **"reference changed"** marker (Spec 11), and Trends' change summary notes the recomputation (Spec 12).

**Reversal:** *Include again* from the Flights toggle, the Flight view header, or the Journal entry. The Journal entry is closed, not deleted.

**Not offered:** bulk exclusion by rule ("all flights under 20 minutes"). That is membership, and membership is folders. An excluded flight is still analysed and still shows its own insights; it only stops shaping other flights' reference.

### 7.2 Editing a rule on the card

The Rules playground is retired as a page. Its reason to exist — seeing the fleet-wide consequence of a threshold change *before* committing to it — is kept and moved to where the decision is actually made: the insight card. The user must see the implication of a decision before applying it, and must not have to leave the flight to do so.

**Edit flow**

1. The card shows the setting that produced the insight, e.g. *trend · R² ≥ 0.5 · n ≥ 10* (Spec 11: observation insights ship on by default with their settings on the card).
2. The user changes a value inline.
3. Before anything is applied, the card shows the **preview** across the workspace, computed by the existing `whatIfRules` path (`evaluate_insights` against every contributing flight):
   *"On your 42 flights: this insight goes away here and on 3 others · 1 new insight appears (Jun 14) · no severity changes."* Affected flights are linked. While computing, the card says so rather than promising an instant answer (Pyodide mode, large workspaces).
4. **Apply** writes `rules/active.json` — still one workspace-wide copy (Spec 03 Q2), never a per-flight rule — and a Journal entry with before/after values and the counted effect. **Cancel** discards. **Reset to shipped** is offered per rule on the card.

**Same shape for silencing**, scaled to scope (Spec 11's three levels): acknowledge → "this card only"; filter → "suppresses 7 events across 5 flights"; disable topic → "removes 11 insights across 9 flights". One pattern, learned once, for every decision that changes what is shown.

**Reverse path.** When a later flight carries a "rule changed" or "reference changed" marker, the card shows what changed, when, and the reason given, and offers **Revert** with the same preview.

**What moves where**

| From Baselines & Models (today) | To |
|---|---|
| Per-topic trigger editing with live diff | Insight card (above) |
| Global `outlier_z_threshold`, `n_min` | Settings → Reference & Models |
| "Reset to shipped defaults" (all rules) | Settings → Reference & Models |
| Limit filter drift read-out | Journal change notices (§6.2) |
| Fleet selection summary | Settings → Reference & Models, "Contributing flights" |
| Engine overrides placeholder | Settings → Engine |
| Fleet-wide rule browser, systematic tuning across many thresholds | Research, when designed. Not a v1 need: a contributor validating a rule change before a PR is doing research |

**Guards**

- A rule the engine never evaluates must not be editable. Spec 10 §6.1's removals (`flight_phase_mix`, `egt4_elevation`) and the `map_at_takeoff` config fix land before or with this spec.
- The preview counts insights by (`rule_id`, `severity`) per flight, as the playground's diff does today; a change in analysis-line wording alone is not a change.

## 8. Impact on existing specs

| Spec | Change |
|---|---|
| **03** | §4 nav per §4 here; §5.5 replaced by a pointer to §5.1 here; §5.6 Annotations → Journal (§6 here); §5.7 Settings → tabbed section (§5 here); principle 6 restated: tuning happens on the card and in Settings, Research is the destination for systematic work; wireframes `Baselines.dc.html`, `Annotations.dc.html`, `Settings.dc.html` superseded |
| **09** | Filter management stays with the user's decisions (Journal). The v0.2 "what would this hide?" preview is the same pattern as §7.2; the per-limit drift threshold remains the metric's `outlier_z_threshold`, edited in Reference & Models |
| **11** (paused) | Adopt §7.1 (exclude from a card) and §7.2 (edit with preview before apply; silencing levels report scope before apply; "reference changed" / "rule changed" markers with Revert) when it resumes |
| **12** | Recent window and pinning are configured in Reference & Models; the change summary notes reference recomputation after an exclusion |
| **02** | No schema change. `FleetSelection`, `rules/active.json`, `annotations.json` and the settings split are unchanged; only where they are edited moves |
| **10** | §6.1 removals become a prerequisite (§7.2 guards) |

## 9. Acceptance criteria

1. The top-level nav shows Flights, Trends, ECU, Journal and the Settings gear; no Baselines destination and no Research entry.
2. Settings has Engine, Reference & Models and App tabs, and one changelog listing every change made in any of them.
3. No user-facing string says "baseline(s)"; "reference" is used throughout. Internal names unchanged.
4. A flight can be excluded from the reference from a `baseline_deviation`, outlier or trend insight card, with a required reason, and the exclusion appears in Flights, Flight view, Reference & Models and Journal; *Include again* works from each of Flights, Flight view and Journal.
5. Editing a rule value on an insight card shows the fleet-wide preview (added / removed / severity-changed insights, flights linked) before Apply; Apply writes `rules/active.json` and a Journal entry with the counted effect; Cancel leaves `rules/active.json` byte-identical.
6. The preview from the card equals the retired playground's diff for the same edit, verified on the project logs for at least one `threshold`, one `baseline_deviation` and one `trend` trigger.
7. Each of the three silencing levels states its scope (count of insights / events / flights) before Apply.
8. After an exclusion that changes any other flight's verdict, that flight's card carries the "reference changed" marker and Revert restores the previous verdict.
9. Journal lists every entry kind in §6.1, newest first, with reversal from the entry; reversed entries are closed, not removed.
10. `Baselines.tsx`'s rule playground is removed; no route serves it.

## 10. Open questions

| # | Question | Leaning |
|---|---|---|
| Q1 | Does the Engine tab show overrides in v1, or only the shipped profile until `engine_overrides.json` is designed? | Shipped profile only, read-only, with the suppression windows visible. No evidence yet that a shipped profile needs overriding (Baselines.tsx comment). |
| Q2 | Journal grouping: by kind or by time? | Time, newest first, with kind chips — same as Flights. Change notices pinned to the top while unresolved. |
| Q3 | ~~Is Research shown in the nav before Spec 06 exists?~~ | **Resolved v0.2 — no.** Hidden until Spec 06 is designed; no placeholder. |
| Q4 | Should the card preview run on every keystroke (playground behaviour, debounced) or on an explicit "Preview" step? | Debounced live preview on desktop; explicit step in Pyodide mode if measured latency on a 100-flight workspace exceeds ~1 s. Decide from measurement in the Spec 11 implementation session. |
| Q5 | Does a reversed rule edit restore the exact previous values or the shipped default? | Exact previous values (the Journal entry holds them); "reset to shipped" is a separate action. |
