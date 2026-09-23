# Spec 05 — Frontend Bootstrap (Fixture-Driven)

**Project:** SlingologyEIS web platform
**Status:** Draft v0.1 — implementation brief, for Claude Code
**Suggested repo path:** `docs/specs/05-frontend-bootstrap.md`
**Builds on:** Spec 01 v0.4 (types), Spec 02 v0.3 (schema, not yet implemented), Spec 03 (UI architecture), Spec 04 v0.3 (GO)
**Note on numbering:** "Spec 05" is reserved by this document. A separate "research mode" feature (correlation tools, free channel exploration) was discussed and tabled — if it's revisited, it gets the next number, 06, not this one.

---

## 1. Purpose

Build a first working slice of the web UI — enough to click through, not enough to be the real product — against **hand-authored fixture data that conforms exactly to Spec 01's types**, rather than against a live engine. The goal is to surface gaps in Specs 01 and 03 before more design or more engine-migration work happens: does ECharts actually handle four linked, independently-scaled mini-charts the way the wireframe implies, is the rule-playground diff fast enough to feel live, does `InsightSet.evidence` actually carry what a chart needs to zoom to a window. A wireframe can't answer these; running code can.

**This is deliberately not the real integration.** The engine migration isn't at a point where it could supply this anyway — Stage 2 (topic/insight/baseline logic extraction) is committed, but Stage 3 (typed contract, JSON Schemas) and Stage 4 (the browser worker adapter) haven't landed. Building against fixtures decouples frontend progress from backend migration pace entirely, and doubles as an early conformance check on Spec 01's shapes: if the fixtures are faithful and the UI works against them, swapping in the real worker later should be close to a drop-in.

## 2. Scope

**Build these four views**, matching the wireframes referenced in §4:

1. Flight view — insight list, stacked per-channel timeline with zoom/minimap, analysis topics
2. Trends — metric picker, baseline-band scatter chart
3. Baselines & rule playground — fleet selection, rule editor, live-impact diff table
4. Import — drop zone, per-file status, workflow-progress toast

**Do not build yet:** ECU investigation, Annotations, Settings — not wireframed. iPad/touch layout — not attempted yet at any width. Real Pyodide/worker wiring — Stage 4 isn't ready. A real backend or workspace persistence — Spec 02 isn't implemented.

## 3. Project scaffold

- `web/` at the repo root, sibling to `slingology_eis/`, per the monorepo layout in Spec 01's original design discussion.
- React + TypeScript + Vite + Apache ECharts (the design discussion's D1), matching what Specs 03/04 already assume.
- A single shared chart wrapper component (Spec 03 §6.1) — build it once, use it for: Flight view's stacked mini-charts, Trends' scatter, and (if useful) the rule-playground table's implied bar visualization. This is one of the things worth stress-testing: does one component genuinely serve all three, or does the wireframe's assumption not survive contact with a real charting library.
- Simple view-switching (a router is fine, doesn't need to be elaborate) matching the four-destination nav from the wireframes — Flights / Trends / Baselines, with Import as the separate prominent CTA (not a nav tab — see §4 and the wireframes for why).
- No backend. Fixtures (§5) are fetched as static JSON or imported directly; there is nothing to run on a server yet.
- **Design tokens, not literals.** The wireframes' dark/teal/IBM-Plex look is a placeholder — real branding is still pending. Implement colors, spacing, and type as CSS custom properties or a theme object, not hardcoded values scattered through components, so restyling later is a token swap, not a rewrite.

## 4. Wireframe reference

Four `.dc.html` files are provided alongside this brief, under `design/wireframes/` (sibling to `docs/`, not part of `web/`'s build): `FlightView.dc.html`, `Trends.dc.html`, `Baselines.dc.html`, `Import.dc.html`. They won't run standalone — they depend on a runtime that only exists inside the design canvas they were built in — but they're the literal source of truth for exact colors, spacing, copy, and structure. Read them as reference markup, not as something to execute. Screenshots may also be provided alongside as PNGs for a quicker visual check.

Things the wireframes establish that are **not optional interpretation**, because they were deliberate design decisions made in review, not just first-draft choices:

- **Stacked per-channel mini-charts, not one overlaid multi-axis chart**, in Flight view's timeline. Each channel (RPM, IAS, Oil Temp, EGT Spread) gets its own correctly-scaled row and its own unit label. A single shared axis was tried and explicitly rejected — see §6.1 below for why this matters for the fixture shape.
- **Import is a prominent, badged button in the header, not a nav tab.** It's reachable from every screen.
- **The flight header shows the source log filename**, not just the date — e.g. `log_20260423_200615_KACV.csv` — because a flight's identity in Spec 02 is separate from its display date (a flight can have more than one source file).
- **Leave-one-out baseline bands** in Trends, computed excluding the point being compared — this is a real Spec 01 decision (R2), not a chart-styling choice.
- **Zoom/minimap on the timeline is tied to evidence-linking**: clicking an insight is expected to zoom the chart to that insight's evidence window. The wireframe's "zoomed" state is literally what that click produces. If the implementation doesn't wire zoom-state to evidence clicks, the two features will drift apart — build them together, not separately.

## 5. Fixtures

Real data, not placeholder text — generated from the project's own logs and `fleet_metrics.csv`, matching Spec 01 §8's types field-for-field. Provided alongside this brief, under a location of your choosing (e.g. `web/src/fixtures/` or `web/public/fixtures/`, whichever suits the scaffold):

| File | Spec 01 type | Contents |
|---|---|---|
| `flight-kacv-analysis.json` | `FlightAnalysis` | The real KACV flight (`log_20260423_200615_KACV.csv`): header, 5 real phases, all 35 real metrics with correct `missing` reasons, the two real quality diagnostics (`PHASE_TAKEOFF_NOT_DETECTED`, `PHASE_NO_CRUISE`). |
| `flight-kacv-insights.json` | `InsightSet` | The 6 topics shown in the Flight view wireframe — 4 with real insights and populated `evidence` (ENGINE ECU, fuel sender, phase detection, overboost), 2 info-only with no insight (EGT spread, cylinder rank). |
| `fleet-analysis.json` | `FleetAnalysis` | Real 23-flight fleet, 3 metrics (`egt_spread_mean_f`, `oil_temp_max_f`, `overboost_total_s`) with real `points` arrays (`engine_hours` × `value` × `flight_id`) and real baseline stats. |
| `rule-overboost.json` | (fixture-specific, feeds the rule playground) | Real `overboost_total_s` per flight across all 23 flights, sorted, for the live-impact diff table — this is what makes the threshold-drag interaction real instead of the wireframe's two hardcoded states. |

**These are intentionally partial.** `fleet-analysis.json` covers 3 of the ~11 metrics the real engine will eventually produce; add more as needed by copying the same pattern from `fleet_metrics.csv`. Same for insight topics — 6 of 14. Extend fixtures as views need more, rather than trying to front-load everything now.

**The one deliberate gap:** none of these fixtures include `SeriesData` (Spec 01 §8.7) — actual per-second channel values for drawing the timeline's line paths. The wireframe's chart lines are illustrative SVG paths, not real data. Two options, and this is worth a judgment call during implementation rather than deciding it here: (a) extract a real downsampled series from `log_20260423_200615_KACV.csv` as a fixture too, which makes the timeline chart fully real; (b) keep the timeline's line-drawing schematic for this round and focus the fixture fidelity on the insight list, evidence-linking, and the two chart-heavy views (Trends, Baselines) where real numbers matter most. Lean toward (a) if it's cheap — a downsampled series is small — but don't let it block the rest.

## 6. What to report back

This is the actual point of building this now rather than later. Specifically:

### 6.1 Chart library behavior
Does ECharts make the stacked-small-multiples-with-synced-cursor pattern easy, or does ECharts' native multi-axis support push toward a different implementation than the wireframe assumed? If it's a fight, say so rather than forcing it — the wireframe's *intent* (per-channel honest scales, one synced readout) matters more than its exact SVG construction.

### 6.2 Contract fit
Anywhere `FlightAnalysis`/`InsightSet`/`FleetAnalysis` didn't cleanly supply what a view needed — a field that's awkward to consume, something the UI wants that Spec 01 doesn't have, evidence that doesn't map cleanly to a zoomable window. This is real signal for revising Spec 01, not a UI problem to work around silently.

### 6.3 Spec 03 assumptions that didn't hold
Anything where real content length, real data density, or real interaction broke a layout assumption — e.g., does the insight list's severity-sorted card layout still work when a flight has 14 topics with insights instead of the wireframe's 6, does the rule-playground diff table stay legible at 23 rows.

### 6.4 Performance
Rough feel, not formal measurement: does the rule-playground threshold drag feel live against 23 flights' worth of fixture data (it should — the real spike measured `evaluate_insights` as cheap). Does the stacked-chart-plus-minimap combination feel smooth.

## 7. Explicit non-goals for this round

Real Pyodide/worker integration; a real backend or persistence; ECU, Annotations, or Settings views; iPad/touch adaptation; visual polish beyond matching the wireframe's structure and the fixture data's real content; anything about the actual research-mode feature discussed and tabled separately.

## 8. Acceptance

- `web/` scaffold builds and runs locally.
- All four views render against the provided fixtures with the real numbers visible (not lorem ipsum, not the wireframe's illustrative values).
- Clicking an insight with `evidence` in Flight view actually zooms/highlights the corresponding chart region — this is the one interaction most worth getting right, since it's the direct payoff of Spec 01's `evidence` field and the original "insights link to their evidence" design goal.
- Dragging the rule-playground's overboost threshold recomputes the diff table against the real 23-flight fixture, not a hardcoded before/after.
- A short written note (a few paragraphs is plenty) covering §6's four questions, added to this document or as a follow-up, before more views get built.
