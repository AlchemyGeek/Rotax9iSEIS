# Spec 03 — UI Information Architecture

**Project:** SlingologyEIS web platform
**Status:** Draft v0.10 — for review (no code written)
**Suggested repo path:** `docs/specs/03-ui-information-architecture.md`
**Builds on:** Spec 01 — Engine Contract v0.4; Spec 02 — Results Bundle & Workspace v0.3; Spec 04 — Runtime Adapters & Pyodide Spike v0.3 (GO)
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
**Baseline reviewed:** repo `main` at commit `1740d1b`

---

## 1. Purpose

Specs 01, 02, and 04 built the machine: a typed, stateless engine; a workspace to hold its output; three ways to run it. None of that is visible to a pilot. This spec is the part they actually see — organized around the goal stated at the very start of this project: someone should be able to look at a flight or a fleet and understand what it means, without combing through pages of text output.

It defines the views, what data each one binds to (from Spec 01 §8 and Spec 02's workspace), how they navigate to each other, and the two features that were explicitly part of the original brief but don't fit inside a single "view": the **rule playground**, and **evidence links** from an insight to the chart or table row that supports it.

**Explicitly deferred to a later spec (or a per-view addendum):** exact visual design (spacing, color palette, typography), the mockups/wireframes themselves, and ECharts option objects. This spec fixes structure and data flow; visual design is a natural fit for the frontend-design skill once implementation starts.

## 2. Decisions this spec builds on and resolves

| # | Decision | Source |
|---|---|---|
| D1 | React + TypeScript + Vite + Apache ECharts. | Design discussion |
| D2 | Browser-compute is primary (confirmed GO); local server is secondary; both share one UI. | Spec 04 |
| D3 | Non-technical target user; the UI is the *only* thing most pilots ever see — the CLI is a contributor/power-user tool. | Spec 01 §7.1 |
| D4 | iPad is a real target, not just a fallback, for the tested device class; still touch-friendly, responsive design regardless. | Spec 04 Appendix B |
| D5 | Every insight must link to the evidence that produced it (chart, table row, event). | Original design brief |
| D6 | The UI is also meant to help *develop* the analysis — the rule playground is a first-class feature, not an afterthought. | Original design brief |
| **R1** | **Resolves Spec 02 Q1.** Series caching: **not cached** in the workspace for v1. `get_series` (Spec 01 §7) re-parses on demand. The spike measured 2.1–2.6 s for a full flight's load+phases+metrics (Spec 04 Appendix A) — well inside what a "open this flight" wait tolerates, and it avoids a second stale-vs-fresh problem alongside `FlightAnalysis` itself. Revisit only if real usage shows re-parsing is a bottleneck. |
| **R2** | **Resolves Spec 02 Q5.** Bundle import gets a **preview mode**: opening a bundle (drag-in, or a "browse community samples" flow) shows its contents in the same flight-view/trends components, tagged read-only, with an explicit "Add to my workspace" action before anything merges. Nothing merges silently. This is a UI-level choice, as Spec 02 anticipated — the bundle format itself is unchanged. |

## 3. Design principles for this spec

1. **Every screen answers a question a pilot actually has**, not a category of data the engine happens to produce. The six views in §5 map to "what should I look at," "what happened on this flight," "is this normal," "what's wrong with the ECU," "how are my baselines built," and "what have I already explained."
2. **Insights are the entry point, charts are the evidence.** A pilot lands on a severity-sorted list of things worth knowing, and each one expands into the specific chart window or table row that justifies it (Spec 01 §8.5 `evidence`). Nobody should have to know which of the 14 topics to go looking for.
3. **Nothing computed is ever silently stale.** Any view showing a `FlightAnalysis`, `FleetAnalysis`, or `InsightSet` also shows Spec 02's `stale` flag when true, with one visible action to refresh — never a background recompute the pilot didn't ask for (cost is real: re-running fleet baselines touches every included flight).
4. **Touch-first, not touch-tolerant.** Every interactive chart element has a tap target, not just a hover state; this is required for D4, not optional polish.
5. **The rule playground is a sandbox, not a settings page.** Edits there never touch the shipped `insight_rules.json` (Spec 02 §6.4) — only the workspace's `rules/active.json` copy — so experimenting is free of consequence.
6. **Two personas share one computation; they diverge only in which surfaces they visit, never in what the same data produces.** A casual pilot ("load my log, see the results") and a researcher ("diagnose this, tune that, chase an anomaly across many flights") are both real users of this product, and the wrong way to serve both is two modes that can silently disagree about the same flight. There is exactly one active configuration per workspace at any time — one set of thresholds, one rule set, one baseline config — and every view reads it. What differs is exposure, not computation:
   - The **casual persona's world** is Flights, Flight view, Trends, and ECU. Insights appear, outliers are marked, nothing asks them to understand a threshold exists.
   - The **researcher's world** adds Baselines & Models, where every tunable thing actually lives — this is where principle 5's sandbox does its job. A value a pilot never visits this screen to change simply stays at its default; a value only becomes visible to someone who went looking for it by design, not by accident.
   - **Workspaces are the hard-separation mechanism**, not a new one invented for this: an experiment workspace (Spec 02 §5.1) already exists for trying things on a subset of one's own logs. A researcher chasing a hypothesis with aggressive settings does it in a workspace built for that, never the one used for a casual view of the same aircraft. This is the same mechanism the multi-workspace model already provides, applied to a case it wasn't explicitly framed around before now.
   - **A future Research/Explore mode** (tabled as its own feature, not designed here) should follow the same split: a distinct destination, not woven into the four operational views, so a casual pilot's screens stay exactly as simple regardless of how much experimentation capability eventually sits behind Baselines & Models. It should also have a defined path *out* — a genuine finding becomes an annotation, and potentially, per Spec 01 §9's community-extension model, a real Topic. Research mode is upstream of the operational side, not walled off from it.

## 4. Navigation shell

```
┌─────────────────────────────────────────────────────────────┐
│ [Logo]  [Workspace: N117ZS ▾]  Flights Trends ECU Baselines ⚙│  <- top-level nav, always visible
├─────────────────────────────────────────────────────────────┤
│                                                                │
│                     active view                               │
│                                                                │
└─────────────────────────────────────────────────────────────┘
```

**Workspace switcher, permanent in the nav** (new in v0.6, per Spec 02 v0.5's multi-workspace model) — the active workspace's name, a dropdown to the others (Spec 02 §5.2's registry), and "+ New workspace." Not in Settings: switching workspaces is something a pilot managing more than one aircraft does routinely, not configuration they set once. Settings (§5.7, gear icon) still holds per-workspace and app-level settings, just not the switch action itself.

**Five top-level destinations** (§5.1–§5.5: Flights, Trends, ECU, Baselines, Annotations — the last reached the same way as before, not shown in the ASCII sketch above for space), plus Settings (§5.7) from the gear icon. This drops to five from the original six because **Import is no longer a destination** — see §5.1.

**"Flights" now means the log browser**, not a direct link into one flight's detail. This corrects a real mistake in earlier wireframe rounds: the nav's "Flights" pill pointed straight at single-flight detail (now §5.2, "Flight view"), which is a different thing built for a different question. A pilot lands on Flights, sees every flight in the active workspace, and clicks one to reach Flight view — the nav item was never actually wired to the right destination.

A **global stale banner** appears under the nav bar, not per-view, whenever any part of the workspace needs recomputing after an import — "3 new flights imported — recompute fleet baselines?" — because staleness after import is a workspace-wide event, not a single view's concern.

## 5. The views

### 5.1 Flights (the log browser)

**Question answered:** "What's in this workspace, and is anything wrong with how it got there?"

Replaces the old standalone Import destination and the never-built "just a list" gap between Import and Flight view. Grounded directly in Spec 02 v0.5's data model — this view is mostly a straightforward rendering of what §5–§6 of that spec already defines, not new design.

- **Header:** active workspace's name, its log folders (each marked reachable/unreachable per Spec 02 §5.5), a **Rescan** action, and a one-line summary — "48 flights · 45 in baselines · 2 missing · 1 other aircraft."
- **Drop zone / file picker**, same role Import used to have alone — still large and unmissable for D3's non-technical-user onboarding, now living as the top of this view rather than a separate destination. Dropping a folder (or files, as a fallback — mainly needed on Safari, which can't retain folder permissions the way Chrome does) triggers a scan the same way an explicit Rescan does.
- **Table, one row per flight** (duplicate exports from Spec 01's `flight_id` matching collapse into one row):

  | Column | Content |
  |---|---|
  | Date / route | Apr 23 · KACV |
  | Duration, engine hours | 4h 30m · 38.2h |
  | Insights | count, colored by worst severity (§5.2's severity tokens) |
  | In baselines | ✓, or "excluded — <reason>" (Spec 02 §6.3's `excluded` list; toggle lives here) |
  | Status | see below |
  | Source | filename + folder, on hover/expand |

  Clicking a row opens Flight view (§5.2).
- **Status values**, matching Spec 02 §5.5/§5.6 exactly rather than inventing UI-only states: Analyzed · Needs re-analysis (rules/overrides/engine version changed since last computed — Spec 02 §8's `stale` flag) · Missing log (Spec 02 §5.5 — results kept, charts unavailable) · Folder unreachable ("Locate folder") · Different aircraft (Spec 02 §5.6 — informational only, never excludes) · Ground session (skipped) · Unreadable (parse failure).
- **Grouping:** by date (default) or by folder, mirroring how the pilot already organized their own files — no in-app subset filter beyond that, consistent with Spec 02 §5.4's "subsets are made by organizing folders, not by picking in the app."
- **Status chips filter the table** — e.g. show only Missing, or only Excluded.
- **A running "Analyze N new flights" action** after a scan finds new logs, same as Import's old batch-action reasoning: not automatic per-file, so dropping 50 logs doesn't mean waiting through 50 sequential renders.
- **Local-server mode difference:** if the host declares folder-watching (Spec 04 §9.2), the drop zone is replaced by "watching `~/SlingologyEIS/logs/`" with the same status feed. Same component; the trigger differs.

### 5.2 Flight view

**Question answered:** "What happened on this flight, and is anything wrong?"

The most-used view, and the one D5 (evidence links) matters most for. Layout:

```
┌───────────────────────────────────────────────────────────┐
│ Header: date, duration, aircraft, [stale? refresh]         │
├───────────────────────┬─────────────────────────────────────┤
│ Insight list           │  Timeline chart                     │
│ (severity-sorted,      │  - phase bands (color-coded)        │
│  from InsightSet)      │  - selected channels                │
│  ⚡ limit               │  - markers: exceedance/CAS/ECU      │
│  ⚠ warning              │  - linked cursor across sub-charts  │
│  ⚑ watch                │                                      │
│  ℹ info                 │                                      │
│  [click → highlights    │                                      │
│   the evidence window]  │                                      │
├───────────────────────┴─────────────────────────────────────┤
│ Analysis lines (the 14 topics, TopicResult.analysis.text,    │
│ shown even where no insight fired — this is the "why nothing │
│ is wrong" half of the two-layer format, Spec 01 §8.5)        │
└───────────────────────────────────────────────────────────┘
```

- **Insight list** is the entry point (principle 2): each item shows severity, the rendered `message.text`, and confidence. Clicking one scrolls/zooms the timeline chart to its `evidence` window (`series_window` evidence → zoom to `[start_s, end_s]`; `exceedance`/`ecu_run` evidence → jump to and highlight that event; `baseline_point` evidence → a "compare to fleet" link into Trends, §5.3, pre-filtered to that flight). Only topics with `insight != null` appear here — a topic with no fired insight is never listed with a placeholder `info` severity just to have an entry; it belongs in Analysis only (below). A short line below the list states how many topics were analyzed with nothing to flag, so the list's shortness reads as "nothing more to report," not as missing content.
- **Severity travels with the topic, not the section.** `InsightSet.topics` already bundles each topic's `analysis` and `insight` together (Spec 01 §8.5), so the same severity dot/label used in the insight list is repeated on that topic's card in Analysis, whenever `insight != null` — same color, same shape, same token. A topic with `insight == null` carries no tag in either place; the *absence* of a tag is itself the "nothing flagged" signal, not a separate `info` badge. One severity token set, defined once, referenced everywhere it appears (insight list, Analysis grid, and anywhere else a topic's severity is shown, e.g. the fleet-wide rule-playground table in §5.5): `info` `#64748B`, `watch` `#FDE047`, `warning` `#F5A524`, `limit` `#E5484D`. `warning` and `limit` render with a small triangle indicator, `watch` and `info` with a circle, so severity is never conveyed by color alone.
- **Timeline chart** is the one place `get_series` (R1) is called, lazily — only the channels the visible insights/topics reference are fetched by default, with a channel picker (from the Spec 01 §6.4 registry) to add more. This bounds the re-parse cost from R1 to what's actually shown.
- **Phase bands** double as the visible marker for the finding-9 defect: a flight that's entirely one phase band (per `PHASE_TAKEOFF_NOT_DETECTED`, Spec 01 §8.1) shows a plain-language note here, not just a diagnostic code — "phase detection didn't find a clear climb or cruise for this flight; some metrics below are unavailable as a result."
- **Only one navigational bar, not two.** An earlier pass had a second, separate "current zoom phase" band alongside the minimap — cut after review, because it was redundant with the minimap without adding real function of its own, and because two different-scope representations (local detail vs. full-flight overview) crammed into one bar would have meant sacrificing one or the other rather than genuinely merging them. What that band showed — which phase(s) the current zoom window covers — moved into the main chart itself instead, as a tint behind the data (below), which puts the information exactly where it's already being read rather than in a strip that has to be cross-checked. The minimap is now the only bar, and it keeps its original job unchanged: full-flight orientation and drag-to-navigate.
- **The chart's background is tinted with the visible window's phase color(s), recomputed on every zoom/pan.** A window inside one phase (the common case on a flight where detection didn't find real transitions) is a flat, low-opacity wash behind the data; a window spanning a real phase change shows adjacent tinted regions sized to their share of the visible time. This is not optional for the same reason the old band's zoom-tracking wasn't: a phase indicator that doesn't update with zoom is actively misleading, not just stale.
- **Every phase gets its own fixed color — a real palette, not two grays and a blue.** With 11 real phases (`PRE_START`, `ENGINE_START`, `WARMUP`, `TAXI`, `TAKEOFF_ROLL`, `CLIMB`, `CRUISE`, `DESCENT`, `APPROACH`, `LANDING_ROLL`, `SHUTDOWN`; `UNKNOWN` as a 12th fallback), a chart that only distinguishes "ground" from "one big airborne block" isn't doing its job on a flight where phase detection actually worked. Fixed tokens, chosen to avoid any collision with the severity palette (§5.2 above) or the channel-picker colors (so nothing on the Flight view screen accidentally reads as a severity signal):

  | Phase | Color | Phase | Color |
  |---|---|---|---|
  | `PRE_START` | `#4B5563` | `CRUISE` | `#0EA5E9` |
  | `ENGINE_START` | `#7C6F57` | `DESCENT` | `#A855F7` |
  | `WARMUP` | `#8B7E6A` | `APPROACH` | `#EC4899` |
  | `TAXI` | `#5B7290` | `LANDING_ROLL` | `#14B8A6` |
  | `TAKEOFF_ROLL` | `#6366F1` | `SHUTDOWN` | `#374151` |
  | `CLIMB` | `#22C55E` | `UNKNOWN` | `#1F2937` |

- **No text inside the minimap or the chart tint.** At small sizes, and at whatever width a short zoom window leaves the chart, a label reliably either doesn't fit or gets truncated into something unreadable. Both communicate by color alone; what's currently showing is named in a caption line, and the phase-to-color mapping lives in a persistent legend key — shown in full always, not trimmed to only the phases present in the current flight, since it's meant to be learned once and reused across every flight a pilot looks at.
- **Annotations** attach inline: any insight or event card has an "add a note" affordance, writing to Spec 02's `annotations.json` via the host, keyed by `flight_id` (Spec 01 R3) — no separate annotations screen for single-flight notes; §5.6 is for browsing/managing them across the fleet.
- **Report / export:** "Download as text" (the familiar script 04 report, via `render_report`) and "Export flight bundle" (Spec 02 §7, `scope: "single_flight"`) live here as secondary actions.

### 5.3 Trends

**Question answered:** "Is this flight normal for my airplane, over time?"

- One metric at a time (picker from the registry), plotted as engine-hours-on-x, value-on-y, with the leave-one-out baseline band (Spec 01 §8.4 R2) drawn behind the points, and each point clickable back into that flight's Flight view. The sample count ("n=23") links to Flights (§5.1), pre-filtered to that baseline's contributing flights — one click from a summary statistic to which actual flights it's built on.
- **Stratification toggle — never specified beyond a name until now.** Whether it's shown at all, and which kind, is fixed per metric by `band_kind_by_metric` (Spec 01 §8.4) — never a user choice of "stratify by DA or OAT," since a metric only has one physically correct band kind. Concretely:
  - **Disabled/hidden entirely** for a metric where `band_kind_by_metric[metric] === null` (e.g. Overboost Time, Climb Thermal Rate) — no toggle shown, not a grayed-out one, since there's nothing to offer.
  - **Off by default** for every stratifiable metric (5 of the 9 real metrics: EGT Spread, EGT4 Elevation, Oil Temp Peak, Coolant Temp Peak, Oil/Coolant Ratio → `oat_band`; Cruise Efficiency, Cruise Fuel Flow → `da_band`) — the single unstratified fleet baseline is the first thing shown, matching principle 6 (§3): a casual pilot never has to understand density altitude banding to read this chart.
  - **On:** redraws as one band per value `band_kind_by_metric` actually produced for this metric's flights (not a fixed 4 — a metric might only have 3 of the 4 bands represented), each with its own baseline region and its own `confidence` label — which will typically read lower than the unstratified fleet confidence (Spec 01 §8.4's honest trade-off), and that's shown as-is, not upgraded or hidden. A band with `n < 3` still renders, labeled `VERY_LOW`, not suppressed — consistent with never hiding data over a confidence threshold, only labeling it (same principle as `BASELINE_LOW_N`, Spec 01 §8.4).
  - Each point's own band (from `points[].band`) determines which region it's drawn in; switching the toggle re-groups the same points, it doesn't re-fetch anything.
- Trend line (slope, direction, R², confidence) drawn only when `n` clears the same `n_min` gate as insight triggers (Spec 01 §8.4) — a trend line drawn on 4 points would misrepresent confidence the engine itself doesn't claim. When stratified, this becomes one trend line per band, same gate applied per band's own `n`.
- Outliers (`FleetMetric.outliers`) visually flagged on the scatter, distinct from points that merely sit outside the baseline band without crossing the z-score threshold.
- **Model view** (takeoff MAP, and any future `Model`): a small dedicated panel — predicted vs. actual scatter, coefficients shown as plain text ("MAP drops ~X inHg per 1,000 ft density altitude"), and the `note` field when `n < 5` ("still collecting data").

### 5.4 Engine ECU CAS Events

**Question answered:** "Did the ENGINE ECU alert mean anything, or is this routine?" Renamed from "ECU investigation" — the old name was vague enough to suggest either every CAS alert or a whole diagnostic mode; this view is specifically about one alert (ENGINE ECU) and specifically about the occurrences of it that are actually worth attention.

**What counts as an event, precisely:** an ENGINE ECU alert occurrence classified `IN_FLIGHT` (Spec 01 §8.6) — not a ground-context occurrence during `POWERUP`, `LANE_CHECK`, or `SHUTDOWN`, which is the routine case on nearly every flight (141 of 145 real fleet ECU runs) and isn't shown as an individual event here. This distinction is what makes the view worth building at all: without it, a genuine anomaly (real oil-pressure correlation on one flight) is statistically indistinguishable from ordinary power-up behavior repeated 140 times.

Built directly on Spec 01 §8.6/finding 9's BACKLOG B3 fix (per-event co-active alerts, not pooled):

- A table of `EcuRun`s across the fleet (or filtered to one flight), classification-colored (POWERUP / SHUTDOWN / LANE_CHECK / IN_FLIGHT), lane-check pairs visually linked.
- **IN_FLIGHT runs get their own expanded card**, each showing its own co-active alerts (not a fleet-wide frequency table) — this is the fix for the KSFF-flight problem that motivated B3 in the first place: the OIL PRESS co-alert on one specific event must not get lost in an aggregate count.
- **Ground-context runs (POWERUP/LANE_CHECK/SHUTDOWN) are not "ignored" — they're rolled up rather than expanded**, because their classification already explains them; the lane-check pairing check (every pair correctly matched, none orphaned) is real verification, not a dismissal.
- Each in-flight event's flight-date link goes to that specific flight's Flight view, scrolled to the event — not a generic destination. A wireframe pass initially routed every event card to the same single mocked flight regardless of source, which meant clicking through from a real event landed somewhere that couldn't show its insight; fixed by building the actual destination flight rather than leaving the link generic.
- Each run links to its flight's Flight view, scrolled to that moment.
- A "pull B.U.D.S. fault log" reminder banner when the current-flight ECU report would have shown one (matching script 04's existing "Action required" line), so the actionable guidance survives the move from text to UI.

### 5.5 Baselines & models

**Question answered:** "How are my baselines built, and can I fix one that's wrong?"

This view is Spec 02's `FleetSelection` made visible and editable, plus the **rule playground**:

- **Flight inclusion — no separate list here (changed in v0.6).** Membership isn't stored per Spec 02 v0.5 §5.1/§6.3 — this panel links out to Flights (§5.1) rather than keeping its own copy of the fleet list, which would just be a second place for it to drift out of sync. The exclude toggle and reason still live inline on each row *in Flights*, not duplicated here. Rebuilding baselines (`rebuild_baselines` workflow, Spec 01 §7) is still an explicit action on this panel, never automatic on toggle — matches principle 3.
- **Baseline config:** membership (leave-one-out, fixed per Spec 01 R2 — shown as read-only explanation, not a toggle, since v1 doesn't expose changing it) and `n_min` per metric, if the pilot wants to loosen or tighten the sample-size gate.
- **Rule playground (D6):** the differentiating feature, and principle 6's concrete home — this is the one screen where the researcher persona's tuning actually lives. A rule from `rules/active.json` (Spec 02 §6.4) shown with its threshold/condition editable inline, alongside `BaselineConfig`'s `outlier_z_threshold` and `n_min` (Spec 01 §8.4, global default plus per-metric override) — one editor over two underlying documents, since both are the same kind of thing to a pilot even though they're stored separately. Editing it re-runs `evaluate_insights` (cheap, per Spec 01 §7) against every flight in the current fleet selection and shows, live, which flights' insights would change — added, removed, or altered severity — as a diffed list, not just a recount. "Reset to shipped defaults" always available. This is where a pilot (or a contributor validating a rule change before submitting a PR) actually develops the analysis, which was the second half of the original goal alongside the graphical UI itself.
- **Engine overrides:** editing `engine_overrides.json` (Spec 02 §6.4) lives here too — same pattern as rules, but for limits rather than insight thresholds, and it requires the `reason`/`source` fields Spec 02 made mandatory, shown as required form fields, not optional ones.

### 5.6 Annotations (browse/manage)

**Question answered:** "What have I already explained, across all my flights?"

A simple filterable list of every entry in `annotations.json` (Spec 02 §6.5): flight, what it's attached to, the note, when. Exists mainly so an annotation made months ago (e.g. "overboost was intentional, checking density altitude tolerance") is findable later without hunting through individual flights — this is the direct answer to BACKLOG B4's original motivation. Edit and delete happen here or inline in Flight view; both write to the same store.

### 5.7 Settings

Not a top-level nav item (§4) — reached via the gear icon. **Narrower than v0.5's version of this section, deliberately**: the workspace switcher now lives permanently in the nav (§4), and the per-flight log browser (folder list, rescan, missing-log table) is now Flights (§5.1) — Settings doesn't duplicate either.

- **App-level** (Spec 02 §6.6 `AppSettings`): units, which workspace reopens on launch.
- **Workspace-level** (Spec 02 §6.6 `WorkspaceSettings`): `engine_model` (locked, shown read-only per Spec 02 §5.6 — changing it isn't an edit, it's a reason to make a new workspace), engine overrides, anonymize-by-default.
- **Export/import bundle** (Spec 02 §7): scope picker (single flight / fleet subset / full workspace), anonymize toggle, download. Import here is the same drop-and-preview flow as §5.8 below, just reached from a different entry point.
- **Persistence nudge** (Spec 02 §9): a one-time (dismissible, not recurring — principle 3's "no silent background work" extends to not nagging) prompt to request persistent storage and a reminder to export a backup bundle periodically, in browser mode only.

### 5.8 Bundle preview (not top-level; a modal/overlay flow)

**Resolves R2.** Triggered by dragging a `.eisbundle.json`/`.eisbundle.zip` anywhere in the app, or a future "browse community samples" entry point (Spec 01 §9 community goal). Opens the bundle's contents in the *same* Flight-view and Trends components used for the live workspace, with:

- A persistent "Previewing: not yet added to your workspace" banner.
- Every write-capable action (annotate, exclude from baseline, edit rules) disabled — this is a viewer, not an editing surface, until the pilot commits.
- One explicit "Add to my workspace" button that runs the actual merge (Spec 02 §7.4) and only then makes the data live and editable.

This reuses rather than duplicates the flight/trends UI, which is why it's a flow layered on existing views rather than a seventh destination.

## 6. Cross-cutting concerns

### 6.1 Charts (ECharts)

- One shared chart wrapper component handles: a synced cursor with a real-value/real-unit readout (Flight view's timeline overlays several channels in one chart, each indexed to its own range so shapes stay comparable — see §5.2), phase-band background shading, and touch-friendly zoom/pan (pinch on iPad, drag-select on desktop) — built once, reused everywhere a time series appears.
- **The minimap and the main chart's phase tint are two renderings of the same phase-segment data at two different scopes, not two independently written features.** The minimap always shows the full flight's phase mix, with the current zoom window outlined on it; the chart tint always shows only the visible window's phase mix, recomputed on every zoom/pan. Implement them from one shared phase-segment calculation (segments clipped/re-proportioned to whichever time range — full flight or current view — the component is asked to render), not as two independently written pieces of logic that happen to agree today. (An earlier version of this spec had the chart tint as a second standalone bar instead of a chart background — cut after review as redundant with the minimap; see §5.2.)
- Downsampling for display follows Spec 01 §8.7 (min/max-preserving envelope); the chart layer never receives more points than the viewport can usefully show, independent of how much `get_series` returns.
- Severity colors are defined once as design tokens (limit/warning/watch/info) and reused across the insight list, chart markers, and the ECU table — a pilot should learn the color meaning once.

### 6.2 Diagnostics and staleness in the UI

Every Spec 01 `Diagnostic` has a UI treatment class, not a one-off: `info` renders as a quiet inline note, `warn` as a visible banner within the relevant view, `error` as a blocking state with no partial render. This mapping is a single lookup table, so a new diagnostic code (e.g. from a future topic, Spec 01 §9) gets sensible default treatment without new UI code.

### 6.3 What loads when

Consistent with R1 and Spec 02 §5's split between small derived data and re-parsed series: opening the app loads the workspace manifest and every flight's `FlightAnalysis` (small — Spec 04 measured under 3 KB per flight), enough to render the Flights table, the Trends list, and the ECU table immediately. Series data loads only when a specific flight's timeline is opened. This ordering is what keeps every view except Flight view fast regardless of fleet size.

## 7. Out of scope for this spec

Visual design tokens and mockups (a natural next step once this structure is agreed, likely via the frontend-design skill); the exact rule-playground diff algorithm (functionally specified in §5.5, implementation detail); mobile phone layout (iPad and desktop only, per Spec 04's tested scope); internationalization; accessibility audit (should follow standard practice but isn't specified here).

## 8. Open questions

| # | Question | Leaning |
|---|---|---|
| Q1 | Should the global stale banner (§4) block navigation until resolved, or just persist as a dismissible notice? | Dismissible — principle 3 says no forced recompute, and blocking navigation would punish a pilot who just wants to check one flight after a big import. |
| Q2 | Does the rule playground (§5.5) need its own "save as a named experiment" beyond the single working copy in `rules/active.json`? | Not for v1 — Spec 02's schema only anticipates one active copy; revisit if pilots want to compare two rule sets side by side. |
| Q3 | Should Trends (§5.3) support comparing two metrics at once (e.g. EGT spread vs. OAT), or stay one-metric-at-a-time? | One at a time for v1; the model view (§5.3) already covers the one two-variable case (MAP model) that matters today. |
| Q4 | Where does the phase-detection defect note (§5.2) go once finding 9 is actually fixed (Spec 01 migration Stage 2b)? | Becomes dead code to remove; not worth designing a toggle for a temporary state. |
| Q5 | Does the ECU view (§5.4) need a fleet-wide "how often does this happen" summary, or is per-event always the right granularity per B3's original complaint? | Per-event is the fix B3 asked for; a fleet summary could be added as a secondary rollup later without contradicting this, so not blocking. |
