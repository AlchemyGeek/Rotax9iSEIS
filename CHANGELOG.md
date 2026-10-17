# Changelog — SlingologyEIS

All notable changes to SlingologyEIS — the `slingology_eis` engine, the `slingology-eis` CLI and
the web UI — are recorded here. Check your installed version with:

```bash
slingology-eis --version
# or
python -c "import slingology_eis; print(slingology_eis.__version__)"
```

The version is the **engine** version: it changes whenever the analysis a stored flight carries
could differ from what the current code would produce, and the web UI's Sync offers to re-analyse
flights whose stored result predates the running engine. Web-only changes don't bump it.

---

## 1.0.0 — October 15, 2026

**The web UI release.** This is the merge of the `webui` branch into `main`: everything built
since 0.11.0 (September 23), when SlingologyEIS was a command-line toolkit with "a future browser
UI" in its README. It now runs as a local web application — `slingology-eis serve`, then open
`http://127.0.0.1:8420/` — over the same engine the CLI uses. Logs stay in your own folders; the
app references them and never copies or uploads them.

**Existing workspaces:** the version jump from 0.30.0 marks every stored flight for re-analysis.
On the next Sync the Flights page will say *"Found N flights needing re-analysis. Analyze now?"*.
Say yes once; nothing about the analysis itself changed between 0.30.0 and 1.0.0.

Engine versions 0.12.0 to 0.30.0 were cut on the branch as the work landed; the ledger at the end
of this entry maps each number to the behaviour change it carried, for anyone reading a stored
`engine_version`. The entries for 0.14.0–0.22.0 below this one were written at the time and are
kept as they were.

### Web UI and local server

- **`slingology-eis serve`** starts a local server on `127.0.0.1` (default port 8420) that serves
  the built web UI from `web/dist/` and a JSON RPC API at `POST /rpc`. The UI is a React/Vite
  single-page app (`web/`), built once with `npm run build`. Nothing listens on the network and
  nothing is sent anywhere.
- **Navigation:** Flights · Trends · Journal · Settings (gear). Each is described below. The
  Baselines, Annotations and ECU pages that existed on the branch at various points are gone;
  their old routes redirect to where the function now lives.
- **Offline-first with fixtures:** every view renders a sample workspace when no server is
  reachable, so the UI can be developed and tested without one. A server error on a page shows
  the error and a way back instead of a blank app.
- Tested on macOS Chrome, macOS Safari and iPad Safari; no other platforms are checked.

### Workspaces (Spec 02)

- **Any number of workspaces, one active at a time.** A workspace is an app-managed folder
  holding derived results only — per-flight analyses, the fleet reference, rules, filters, notes,
  the Journal — under `~/SlingologyEIS/workspaces/<id>/` for a packaged install or `data/workspaces/`
  in a git checkout, with `registry.json` beside them. Create, switch, rename and delete (typed
  `DELETE` confirmation) from the UI; `slingology-eis workspace list|create` from the CLI.
- **Log folders are referenced, never copied.** A workspace watches one or more folders
  (subfolders included). Flights are identified by a content fingerprint, so a renamed or moved
  log is re-matched rather than duplicated; a log that disappears is kept as *missing* and keeps
  its place in the reference until it is removed; a missing log that reappears is recovered.
- **Log admission.** Every discovered file is classified before it becomes a flight: ground
  session (no airborne phase), short flight (airborne time under `min_flight_duration_min`,
  default 10, in `config.json`), or corrupt log (an internal gap over 5 minutes). Skipped logs are
  recorded in `exclusions.json` with the reason, listed under *Skipped* on the Flights page, and
  can be included again. Duplicate exports of the same flight collapse to one. The same classifier
  runs in the CLI loader, the folder scan and drag-and-drop import, so the three can't disagree.
- **Flight exclusions from the reference.** A flight can be excluded from (and re-included in)
  the fleet reference with a reason, from the Flights row or the Flight view header, through one
  dialog that previews how many other flights' verdicts would move. CLI: `flights
  [--show-excluded]`, `exclude FILE --reason`, `include FILE`.
- **Mixed-aircraft notice.** A workspace with more than one tail number is told so (one aircraft
  per workspace is the recommendation), with aliases for ident typos.
- **Sync asks before analysing.** Sync discovers moved, missing, recovered and new logs and stale
  flights, then asks once: *"Found N new logs and M flights needing re-analysis. Analyze now?"*.
  *Not now* leaves the work visible in the table as *Needs analysis* / *Needs re-analysis* with an
  *Analyze N* button. Analysis runs with per-flight progress. Three or more dropped files get the
  same question; one or two analyse immediately.

### Flights

- One row per flight: date, duration, insight count and worst severity, source folder, reference
  membership (✓ / ✕ with the reason on hover). Status filters, a *Skipped (N)* panel for logs that
  were not admitted (category, reason, date, recording and airborne minutes, *Include*), and an
  onboarding drop zone while the workspace has no folders; after that, *Add logs…* and *Sync*.
- **Log preview** (`/logs/<file name>`): a read-only page for a skipped log — header, the full
  timeline chart, CAS alerts and ENGINE ECU runs by class — with one action, *Include this log*.

### Flight view

- **Header** with the flight facts row — figures a pilot records rather than judges: fuel burned,
  cruise nm/gal, cruise fuel flow, lane check (*both lanes ✓ / one lane only / not detected*) —
  and the flight's reference status.
- **Timeline chart** (Spec 07): channel presets (shipped set in `chart_presets.json`, user presets
  saved from the chart and managed under Settings), a searchable grouped channel picker with
  individual cylinder EGTs, per-channel min/max downsampling that preserves peaks, phase tint
  with the phase named in the cursor readout, per-phase time totals, zoom, and an evidence jump
  from any insight that outlines the window it came from. Chart state carries across flights
  within a session.
- **Events section** between the chart and the topic cards: one chronological table of every
  event on the flight — OM-limit exceedances and CAS events (today ENGINE ECU runs on the
  ground or in flight) — each with *Chart*, *Add a note* and *Filter…* actions, numbered markers
  on the chart (▲ limit, ◆ CAS). Events tolerated by a filter collapse to one line per limit;
  a breach is marked *beyond your filter*; a CAS row expands to its engine context and the
  flight's runs by class.
- **Topic cards** follow a roster rule: a card is expanded when it has something to say (a fired
  insight, a mirrored OM-limit badge, a *Reference changed* / *Rule changed* marker, or a validity
  note) and is one line otherwise. Every topic has a `?` with a one-paragraph, aircraft-neutral
  explanation (`slingology_eis/help/topics.md`; CLI `explain`). A disabled topic stays as one line
  with *Enable*.
- **Rules are edited in context.** Triggers show read-only on the topic card; *Edit rules…* (or
  *Edit trigger* from an insight) opens a side panel that edits all of a topic's triggers and its
  enabled flag, previews the effect on every flight in the workspace before *Apply*, and records
  the edit in the Journal. *Reset to shipped* and *Revert* restore the exact previous values. The
  standalone rule playground page is retired.
- **Every decision control states its scope** before use — *This flight only* or *All flights in
  this workspace* — in the dialog and on its Apply button.
- **Notes** on any insight, event or ECU run; they survive re-analysis and the insight-id changes
  of 0.17.0.
- **Insights filtered by flight phase** (persisted), applying inside multi-event cards too.

### Trends — a change page (Spec 12)

- Trends asks *is my engine changing*, not *pick a metric*. A **change summary** ranks metrics by
  **shift** — the recent window (last 10 engine hours, at least 5 flights, at most 15; tunable in
  Settings) against the reference, in σ — with an OM or filter-edge crossing outranking everything
  and **bend** as a qualifier. A **shift history** keeps every past change event; the Trends nav
  item shows a count of open ones.
- **Panels** are declared per topic in `docs/specs/topics/register.json`: cylinder balance (four
  deviation lines, hottest-cylinder strip, usual-hottest chip; coupled cylinders summarise as one
  row), thermal, boost/power (takeoff-MAP residual as a new fleet metric), and a planning panel for
  fuel. **Per-limit panels** are generated for every limit that is filtered or has ever fired, and
  one per classified CAS alert: an event strip, **event frequency** as the primary change signal,
  peak excess under it, time-above behind a toggle, and the OM line with its margin. Panels are
  tiered — qualifying first, trendable next, a collapsed *Never exceeded (N)* group last — with
  per-panel detail strips and a whole-history fit line.
- **Readiness badges** (*filtered / building / no recent / no events / rare / insufficient*) on
  every strip and summary so a metric that cannot yet be trended says so where its name is.
- **Pin the baseline** per metric to the flights visible in the current zoom (or the recent
  window), with a confirmation that predicts whether unpinning changes the summary; pinned state
  is visible on every strip. Stratified metrics compare within their OAT or density-altitude band.

### Limit filters and change monitoring (Spec 09)

- 0.17.0–0.22.0 below describe the mechanism as it shipped: one insight per limit, merged events,
  per-limit baseline metrics, filters by magnitude and duration with preview, the change monitor
  (Breached / Drifting / Review due / Quiet / Collecting / Stable) against a frozen reference, and
  copying filters between same-engine workspaces. Since then:
- **WARNING limits are filterable again, with a required note** (reverses 0.20.0): a consistent
  WARNING exceedance can be a sensor or calibration artifact as easily as a real issue, and the
  engine can't tell which, so the pilot records which it is. `oil_press_min` stays unfilterable.
- **Phase-of-flight exclusion** (Phase 8, 0.30.0): a filter can list phases to exclude; an event
  lying wholly within them is suppressed (*suppressed (phase: …)*), stays in the monitor's metrics
  so growth still drives *Drifting*, and is never a breach. Not offered on `rpm_takeoff_max`,
  overboost or CAS targets. Suppression reason order is phase › magnitude › duration, so a filter
  with no phases keeps the labels it had.
- **Filters on CAS events:** a filter targets a limit or a classified CAS alert (`ENGINE ECU`);
  CAS filters are duration-only and monitored by event frequency.
- **No hidden floors; an advisory instead:** drift compares against the reference flights' actual
  spread, and a limit exceeded on fewer than 5 of the last 20 flights can still be filtered but the
  editor says it isn't advisable. Filter cards read in pilot terms (what was compared with what)
  with the statistics behind *How was this decided?*; reference flights are shaded only while the
  filter is drifting; charts show units; a limit no flight has passed says so instead of showing
  two empty charts.
- **RPM limits and overboost** (0.22.0): the OM's two RPM rules were encoded wrongly — 5,500 rpm
  continuous raised a CAUTION on every takeoff, and a short run above 5,800 rpm went unreported.
  Overboost is now the single owner of the 5-minute takeoff-power rule and is reported by
  `limit_exceedances` as an ordinary event; `rpm_continuous_max` is retired; `rpm_takeoff_max` is
  a plain ceiling.
- Engine-running gates on `fuel_press_min`, `rpm_idle_min` and `volts_min` (checked only at or
  above 1,000 rpm) and an idle-established condition on `rpm_idle_min`, removing the 0 psi / 0 rpm
  / 0 V "exceedances" a log records before start and after shutdown.

### Journal and Settings (Spec 14)

- **Journal** is a register of the decisions in force in the workspace — limit filters, rule
  edits, disabled topics, flight exclusions, pinned references, notes — one entry per decision,
  most recently changed first, with kind chips, grouping by date or flight, the decision's current
  effect computed live (*changes the verdict on N other flights*), and *Edit* / *Remove* with scope
  captions and a preview. Reversing a decision removes its entry; a decision whose basis has moved
  (a Breached or Drifting filter, a zero-effect edit) carries a notice until confirmed. Decisions
  made before the Journal existed are imported on first read. Stored in `journal.json`.
- **Reference-change markers:** when an exclusion or a rule edit moves another flight's verdict,
  that flight's card says *Reference changed* / *Rule changed*, why, and offers *Revert*.
- **Settings** has three tabs. *Engine*: the active profile and its full OM limit catalogue with
  the phase-aware suppression rules, read-only. *Reference & Models*: outlier z-threshold with
  per-metric overrides, the recent window and OM margin, pinned references, contributing flights
  with *Rebuild reference*, the takeoff-MAP model (R², n, residual SD, *Refit*), n_min per topic,
  stratification bands. *App*: chart presets (rename, reorder, duplicate, delete), tail-number
  aliases. Every saved setting is logged with before/after, tab and time in `settings_changelog.json`.
- **Inline help** (ⓘ, opens on click) on the settings and triggers that aren't self-explanatory,
  from one registry.
- Every user-facing "baseline" became **"reference"**; internal identifiers are unchanged.

### Analytics topics — admission and register (Spec 10)

- Every topic now has a written case for existing — admission criteria, evidence grade, and a
  per-engine status (*Admitted / Admitted (provisional) / Unverified / Research / Removed*) —
  recorded in `docs/specs/10-analytics-topic-admission.md` and the test-checked
  `docs/specs/topics/register.json`. Status is per engine profile: topics validated on the 916iS
  are *Unverified* on the 912iS/914iS/915iS until data from such an aircraft exists, and the
  Flight view says so.
- **Removed:** `oil_coolant_ratio` (no sourced mechanism; the oil–coolant balance idea is
  candidate C5), `egt4_elevation` and `flight_phase_mix`. **Moved to Research:** `climb_thermal_rate`
  (no conditioner found that makes it discriminating). **Retired:** `cylinder_rank`'s
  hot-cylinder-changed insight (`egt_cyl_deviation` always fires first; the rank stays as context).
  **Folded:** `egt_spread`'s baseline insight into the cylinder insight whenever both fire.
- **Planning numbers leave the topic set:** cruise nm/gal, cruise fuel flow and fuel burned are
  flight facts in the header, with no insight.
- **One owner for events:** `limit_exceedances` reports every OM-limit and CAS event; a topic that
  references a limit (oil peak, coolant peak, overboost, ENGINE ECU) shows a mirrored badge and
  names it in its analysis line but never emits a second insight. `oil_temp_peak` and
  `coolant_temp_peak` lose their threshold triggers accordingly.
- **Takeoff MAP tolerance comes from the model:** 2 × the leave-one-out residual SD, with a
  fitted-range guard, replacing a hard-coded 20 hPa that fired on half the flights.
- **Limit saturation is ours to fix, not the pilot's:** acceptance tests require a nominal
  synthetic flight to raise zero events on every profile and bound how many real flights any one
  limit may fire on, with a per-aircraft allowlist (`fuel_press_max`, `rpm_idle_min`,
  `rpm_takeoff_max` on N117ZS, each with its diagnosed cause) for the ones traced to the aircraft
  rather than the encoding.
- **Stratified baseline comparison:** `baseline_deviation` compares a flight against the
  leave-one-out baseline of its own weather band (OAT or density altitude) once the band has
  enough flights, and the insight text says which (*your other warm flights, n=14* vs *all your
  flights, n=23*). Removes the seasonal false positives and makes insights agree with the
  stratified Trends view.

### ENGINE ECU and CAS events (Spec 01 §8.6, Spec 10 D18/D19)

- **Runs are classified by flight phase, not by heuristics.** Contiguous ENGINE ECU rows merge
  across gaps under 5 s and count as a run from 3 s; shorter ones are sub-threshold blips. Classes:
  GROUND_START, LANE_CHECK (in the OM run-up band — 4,000 rpm ± 500 on the 912iS/916iS, 2,500 on
  the 915iS — stationary, short), GROUND, IN_FLIGHT (needs rows in an in-flight phase *and* above
  taxi airspeed), GROUND_SHUTDOWN (the engine stops and stays stopped, whatever the phase labels
  say). The old RPM-fraction, voltage-decline and IAS heuristics, the POWERUP/SHUTDOWN names and
  the "requires investigation" text are gone.
- **Corrected finding:** the "four in-flight ENGINE ECU events" the earlier classifier reported on
  N117ZS were ground events — most of them single-row blips at engine start. On the full log set
  the result is **0 in-flight runs**, 3 ground runs (all below the lane-check band), 325 runs in
  all. `engine_ecu_inflight` is *Admitted (provisional)* in the register: mechanism sound, positive
  case never seen.
- **ENGINE ECU runs on the ground or in flight are CAS events** in the same event list as limit
  exceedances, with the reason they are not a lane check; a lane-check summary (both lanes / one
  lane / not detected) is a flight fact. The separate ECU page is removed.

### Phase detection

- Three fixes for real flights that collapsed into one TAXI or ENGINE_START phase (departure and
  arrival elevation mismatch; a takeoff-roll gate that a turbocharged iS spools through within one
  1 Hz sample; a barometric warm-up transient dominating the field-elevation estimate; a 10 kt
  ground-idle IAS ceiling several aircraft never dip under). 0.15.0, 0.16.0.
- Return to the ground after landing at a higher field (0.21.0).
- Ground-session detection uses the phase detector itself (any airborne phase) instead of a
  separate RPM/IAS heuristic.
- `notebooks/06_phase_regression.py --save/--compare` snapshots every log's phases, metrics and
  exceedances and reports exactly what a change moves; CLAUDE.md requires it before touching
  phase, limit or metric heuristics.

### Engine profiles

- **912iS is VERIFIED** against OM-912 i Series Edition 2 / Rev. 2 (September 2025): all limits
  from Chapter 2.1, with the manifold-pressure and EGT-split limits deliberately absent because the
  OM defines none for a naturally aspirated engine. 915iS (OM-915 i A/C24 Ed. 0 Rev. 4) and 916iS
  (OM-916 i/C24 Ed. 0 Rev. 1) were already verified. **914iS remains a PLACEHOLDER.**
- Every limit has a stable `id`; profiles carry `exceedance_merge_gap_s`, per-limit `min_rpm`,
  `requires_reached_since_start`, `stratify_by`, `filter_policy` (filterable, note required,
  phases allowed, pilot-facing reason), the `cas` run-extraction block, `expected_hot_cylinder`,
  and the lane-check run-up band with its OM citation.

### CLI

- New subcommands: `flights [--show-excluded]`, `exclude FILE --reason`, `include FILE
  [--reason]`, `workspace list|create NAME [--tail-number]`, `explain [TOPIC]`, and `serve
  [--port]`. `--workspace` accepts a registered workspace name or id as well as a path. `report`
  applies the workspace's filters. `ecu --json` reflects the new run classes. `export-bundle`
  remains stubbed (exit 2) pending the results-bundle format.

### Notebooks and tests

- `notebooks/05_limit_events_report.py` (per-limit event statistics by weather band, used to
  choose the merge gap and stratification) and `06_phase_regression.py` (above). Notebooks 02/03/04
  use the new ECU classes.
- Python suite: 619 tests (unit, contract, CLI, characterization) at the last branch commit;
  those gated on the private log set skip without it. Web: 129 vitest tests. Frozen fixtures
  (`tests/characterization/golden/`, gitignored; `web/src/fixtures/`) regenerated for the grown log
  set with every regeneration confirmed additive.
- `CLAUDE.md` records how a session fetches the private `EIS-Test-Data` logs and the phase
  regression rule.

### Known at release

- `npm run build` fails type-checking on one test fixture (`web/src/components/EventsTable.test.tsx`,
  a phase-suppressed CAS row typed as a limit event); `npx vite build` alone produces `web/dist/`
  and the UI runs. Tracked in BACKLOG.
- `npx vitest run` reports an unhandled `scrollIntoView is not a function` from jsdom in
  `Trends.cas.test.tsx` and exits non-zero although all 129 tests pass. Tracked in BACKLOG.
- The 912iS topic-help text cites an EGT-split limit the 912iS OM doesn't define (one expected
  test failure).
- `loader.log_summary()` would raise on a log that reaches cruise without a fuel-flow channel;
  no real log in the set lacks one.

### Engine version ledger, 0.12.0 → 0.30.0

Each number is what a stored flight's `engine_version` meant. Entries 0.14.0–0.22.0 are written
up in full below.

| Version | Date | Behaviour change |
|---|---|---|
| 0.12.0 | Sep 24 | Web UI and multi-workspace server. `outlier_z_threshold` resolved from one place; ECU per-run context computed for all fields (was 2 of 10); EcuAnalysis schema/types aligned. |
| 0.13.0 | Sep 26 | Pilot notes; per-channel min/max downsampling (peaks were understated); chart presets. |
| 0.14.0 | Sep 26 | Cylinder balance: learned hottest cylinder, per-cylinder deviations, `egt_rank_stable` fixed. |
| 0.15.0 | Sep 28 | Three phase-detection fixes (flights stuck in TAXI). |
| 0.16.0 | Sep 28 | ENGINE_START → WARMUP gate widened to IAS < 30 kt (7 flights stuck in ENGINE_START). |
| 0.17.0 | Sep 30 | Stable limit ids, 30 s event merging, one insight per limit, `limit_ref` thresholds. |
| 0.18.0 | Sep 30 | Per-limit baseline metrics with `stratify_by`. |
| 0.19.0 | Sep 30 | Limit filters, preview, change monitor, copy filters. |
| 0.20.0 | Oct 1 | WARNING limits unfilterable (since reversed); `fuel_press_min` gated on 1,000 rpm. |
| 0.21.0 | Oct 1 | Return to the ground after landing at a higher field; takeoff MAP from the first real departure. |
| 0.22.0 | Oct 3–4 | Overboost owns the 5-minute rule, `rpm_continuous_max` retired (Spec 09 Phase 6); `rpm_idle_min` gated on 1,000 rpm. |
| 0.23.0 | Oct 4 | Spec 10 Phase A: `oil_coolant_ratio`, `egt4_elevation`, `flight_phase_mix` removed; `climb_thermal_rate` and `cylinder_rank` disabled; planning numbers to the flight summary. |
| 0.24.0 | Oct 4 | Merge of the two 0.22/0.23 lines; no further change. |
| 0.25.0 | Oct 4 | Spec 10 Phase B: `limit_refs` and mirrored badges; cylinder deviation names the hottest-cylinder change; `egt_spread` folds into the cylinder insight. |
| 0.26.0 | Oct 5 | Spec 10 Phase C: takeoff-MAP tolerance from leave-one-out residuals with a fitted-range guard. |
| 0.27.0 | Oct 6 | Spec 10 Phase D: `register.json`; `volts_min` engine-running gate; `rpm_idle_min` idle-established condition; saturation allowlist; `oil_press_min` gate on 912iS/914iS. |
| 0.28.0 | Oct 6 | Spec 10 Phase E: topic help, unverified-on-this-engine note, mixed-aircraft notice and aliases. |
| 0.29.0 | Oct 13 | ENGINE ECU runs classified by flight phase; `cas` block in every profile. |
| 0.30.0 | Oct 15 | Filters: phase-of-flight exclusion; suppression reason order phase › magnitude › duration. |

Web-only work between those numbers (Spec 12 Trends, Spec 14 Settings/Journal, CAS events on
the Flight view, the Flight view restructure, Flights Sync) never changed a stored analysis and so
never bumped the engine; it is described above.

---

## 0.22.0 — October 4, 2026

**Idle RPM minimum no longer fires with the engine stopped.** It is now checked only at or
above 1,000 rpm, the same gate fuel pressure minimum has had since 0.20.0. A log that records
0 rpm for a while before the engine starts counted that as an idle exceedance 1,800 rpm deep,
which also squashed the filter chart for this limit.

- **Effect on the N117ZS logs** (all 107, checked before and after): 2 logs change. Two 0 rpm
  events before engine start are gone (log_20260706_160502, log_20260718_141654). On
  log_20260718_141654, the 35 s of idle below 1,800 rpm right after start is now reported on
  its own, worst 1,080 rpm (the first second of spool-up).
- **Filter charts:** a limit none of your flights has gone past (e.g. fuel pressure minimum)
  shows "nothing to chart" instead of two empty charts. The charts' Y axes show units, and the
  filter row's "from flight" link is gone (Edit works in place).
- **Reference flights are shaded only while a filter is drifting**, with a line under the drift
  reason saying what the shaded area is. Otherwise every flight is one colour (red if beyond
  the filter).
- Existing workspaces re-analyse their flights on the next scan (engine version change).

**Limit filters: no hidden floors; a plain "not advisable" note instead.**

- **Filter editor:** filtering a limit that was exceeded on fewer than 5 of your last 20 flights
  is still allowed, but the editor says it isn't advisable and why. Filters are for exceedances
  that happen regularly, and an occasional one is usually worth looking at each time.
- **Drifting** compares recent flights with your reference flights as they are, without a
  minimum spread. If the reference flights never went past the limit, time past it on 2
  flights in a row reads "…; your reference flights never did." (The z-mode filter band keeps
  its minimum spread.)
- `propose_limit_filter` returns `advisory`; `FilterHealth.drift_details` drops `std_floor`,
  and its `z` is `null` against a zero-spread reference. Analysis results are unchanged, so no
  re-analysis.

## 0.21.0 — October 1, 2026

**Phase detection: landing somewhere higher than you took off.** The flight phases measured
height above the *departure* airport for the whole log, and the airborne phases only returned
to the ground through that height test. After landing at a higher airport the test never
passed, so the flight stayed "descent" or "approach" through rollout, taxi and shutdown
(11 of the N117ZS logs), and a log with several legs couldn't see its next takeoff (5 logs).

- **New ground test:** airspeed below 30 kt with RPM below 2,000 for 10 seconds means the
  aircraft is on the ground — impossible in flight (it stalls well above 30 kt, and an
  engine-out glide keeps airspeed up). Phase detection then switches to taxi and re-measures
  the field elevation there, so later takeoffs and approaches are judged against the airport
  the aircraft is actually at.
- **Takeoff MAP** uses the first real departure only (a takeoff roll followed by a climb), not
  every takeoff roll in the log pooled together, and no longer counts a high-power runup.
- **Effect on the N117ZS logs** (all 107, checked before and after): 18 logs change, all as
  intended — tails relabelled taxi/shutdown, second-leg takeoffs detected, descent minutes no
  longer including ground time, one takeoff MAP no longer blended with a runup. No exceedance
  changes; no log changes between flight and ground session.
- **New tool:** `notebooks/06_phase_regression.py --save NAME` / `--compare NAME` snapshots
  every log's phases, metrics and exceedances and reports exactly what a code change moves.
- Existing workspaces re-analyse their flights on the next scan (engine version change).

---

## 0.20.0 — October 1, 2026

- **WARNING limits can never be filtered.** They are the Operators Manual red lines: a reading
  past one is either real or a sensor fault to fix, never something to hide. The engine refuses
  such a filter whatever the profile says, and the Flight view's limit card offers "Why can't I
  filter this?" instead. The placeholder caps shipped in 0.19.0 are removed. Overboost, treated
  as WARNING, is locked too. CAUTION limits (e.g. fuel pressure maximum, max continuous RPM, bus
  voltage) stay filterable.
- **Fuel pressure minimum no longer fires with the engine stopped.** It is checked only at or
  above 1,000 rpm (new per-limit `min_rpm`). On the N117ZS logs this removes 102 false WARNING
  events — one or two on every flight, all readings near 0 psi before start or at shutdown —
  and no real ones. A phase list couldn't do it: some logs label post-shutdown rows as descent
  or approach.
- Existing workspaces re-analyse their flights on the next scan (engine version change).

---

## 0.19.0 — September 30, 2026

**Limit filters and change monitoring (Spec 09 Phases 3–5).** Silence a known, consistent
exceedance without losing it, and still be told when that behaviour changes.

- **Filter this limit…** on any limit card in the Flight view opens an inline editor,
  pre-filled with this aircraft's typical and worst excess and a suggested band. Two separate
  conditions, and an event needs only one to be tolerated: **magnitude** (absolute, % of the
  limit, or z against the filter's reference flights) and **duration** (events up to N s).
  **Preview** shows how many events on how many flights the filter would hide, and how many
  flights would still breach it, before you save.
- **Suppressed, not deleted:** a filtered limit's tolerated events collapse into one quiet
  insight (info for CAUTION limits, watch for WARNING) that still expands to every event;
  anything beyond the filter is reported at the limit's normal severity, marked "beyond your
  filter". Topic thresholds (oil/coolant peak, overboost) follow the same filter; baseline
  deviation and trend insights are never filtered.
- **Guardrails, enforced in the engine:** WARNING limits are filterable only up to caps the
  engine profile declares, never in z mode, and only with a note. `oil_press_min` is never
  filterable. The 916iS ships **PLACEHOLDER caps** (e.g. oil and coolant temperature 5°F / 10 s,
  EGT 20°F / 10 s, MAP 0.5 inHg / 5 s, fuel pressure minimum 1 psi / 10 s, overboost +30 s) —
  review them. Other profiles have no caps, so their WARNING limits aren't filterable yet. An
  invalid or hand-edited filter is ignored with a diagnostic; the limit reports unfiltered.
- **Overboost:** a band moves both the effective limit and the close call.
- **Change monitor:** every filter is watched against a frozen reference (the 20 most recent
  flights when it was set). Its status is **Breached** (an event beyond it since the last
  review), **Drifting** (peak excess or time past the limit above the reference on 2 flights
  running, at the metric's own outlier z; or events on 30 points more of the last 10 flights
  than in the reference), **Review due** (50 engine hours for CAUTION limits, 25 for WARNING),
  **Quiet** (no events in 10 flights), **Collecting** or **Stable**. Stratified limits compare
  within the flight's weather band once it has 10 reference flights.
- **Notes page:** a *Limit filters* section with a card per filter: status and reasons, two
  charts over flights (peak excess with the band drawn, and time past the limit; reference
  flights shaded, breaching flights red), last breach, hours since review, and **Edit**,
  **Re-baseline**, **Mark reviewed**, **History**, **Remove**. Plus a short explanation of how
  filters differ from baselines.
- **Copy filters from…** another workspace with the same engine model (Notes page). Copies
  get a fresh reference from this workspace's own flights; limits already filtered here are
  skipped. A different engine model is refused.
- **Attention:** the Notes nav item shows a badge, and the Flights page a one-line banner,
  when a filter is Breached or Drifting.
- **Rule playground:** a *Limit filter drift* group sets the per-limit metrics'
  `outlier_z_threshold` overrides — one number for both the Trends outliers and drift.
- **Storage:** `filters.json` in the workspace, with each filter's history. The CLI `report`
  command applies the workspace's filters too.
- **Contract:** `evaluate_insights(…, filters=)`; `InsightSet.filters_hash`; new operations
  `validate_limit_filter`, `propose_limit_filter`, `preview_limit_filter`,
  `evaluate_filter_health`; server ops `list_filters`, `propose_filter`, `preview_filter`,
  `save_filter`, `delete_filter`, `filter_health`, `review_filter`, `rebaseline_filter`,
  `copy_filters`.
- Existing workspaces re-analyse their flights on the next scan (engine version change), so
  each flight carries the new filter policies.

---

## 0.18.0 — September 30, 2026

**Per-limit baseline metrics (Spec 09 Phase 2).** Groundwork for limit filters: each limit's
behaviour is now tracked per flight and baselined like every other metric.

- **New per-flight metrics** for every limit checked for exceedances:
  `lim_<limit_id>_peak_excess` (largest excess of any event; missing when the flight had none)
  and `lim_<limit_id>_time_above_pct` (time past the limit as a share of engine-running time,
  PRE_START and SHUTDOWN excluded). Overboost gets `lim_overboost_block_s` instead.
- **Fleet:** `update_fleet` baselines them as `limit_<limit_id>_…`, with trend, outliers at the
  metric's own `outlier_z_threshold`, and weather bands from the limit's new `stratify_by`
  (temperatures and EGT split by OAT, MAP and overboost by density altitude, others none).
  Their definitions are generated from the engine profile, not hand-listed. No insight rules
  use them and the Trends view doesn't list them yet.
- **Fuel pressure maximum is OAT-stratified** (916iS, 915iS): its peak excess varies with OAT
  on the N117ZS log set (cold +4.1 psi vs mild +3.3 psi); `notebooks/05_limit_events_report.py`
  now prints each limit metric's variation by band.
- Existing workspaces re-analyse their flights on the next scan (engine version change).

---

## 0.17.0 — September 30, 2026

**Limit exceedances, one card per limit (Spec 09 Phase 1).** Fixes the fragmentation and
duplication that made the limits topic easy to skim past. Filters come in a later phase.

- **Stable limit ids:** every limit in all four engine profiles has an `id` (e.g.
  `fuel_press_max`), plus `egt_split_high_flow`, `egt_split_low_flow` and `overboost` for the
  computed limits. A profile with a missing or duplicate id no longer loads.
- **Event merging:** a reading that dips back within a limit for less than
  `exceedance_merge_gap_s` (30 s) no longer ends the event; duration rules apply to the merged
  event. Chosen from the N117ZS log set (`notebooks/05_limit_events_report.py`): fuel pressure
  maximum drops from 573 to 158 events. `rpm_idle_min` keeps a 0 s gap (per-limit override),
  since merging would join brief governor dips into long events.
- **Fixed:** a phase-filtered limit no longer joins exceedances either side of an excluded
  phase into one event.
- **One insight per limit per flight:** `limit_exceedances` shows a count, the worst reading
  and the total time past the limit; the card expands to its events, each zooming the chart.
  Insight ids no longer depend on the message text, so notes stay attached. Notes on the old
  per-event insights move to the new per-limit insight when the flight is re-analysed.
- **Topic thresholds follow the engine profile:** `oil_temp_peak`, `coolant_temp_peak` and
  `overboost_time` reference a limit (`limit_ref`) instead of a hard-coded 248°F / 300 s, and
  fire only when the flight has an event for that limit. Fixes the 915iS (266°F oil limit).
  Rules go to v1.3; a workspace's older rule copy is read as `limit_ref`. The overboost
  close call now comes from the profile (`close_call_margin_s`, 60 s).
- **Contract:** exceedances gain `limit_id`, `event_id`, `excess`; `FlightAnalysis.limits`
  carries the profile's limit catalogue; limit insights carry `limit_id` and `events`.
- Existing workspaces re-analyse their flights on the next scan (engine version change).

---

## 0.14.0 — September 26, 2026

**Cylinder balance (Spec 08).** The toolkit no longer assumes cylinder 4 is the hottest. It
learns each aircraft's usual hottest cylinder from its own flights and flags when that changes.

- **New per-flight metrics:** `egt1..4_deviation_f` (each cylinder's cruise EGT minus the
  mean of the others), `egt_hottest_cyl`, `egt_hottest_margin_f`, `egt_rank_order`.
  `egt4_elevation_f` remains as a deprecated alias of `egt4_deviation_f`.
- **Fixed:** `egt_rank_stable` now means "the same cylinder was hottest for ≥ 80% of cruise".
  It used to test only whether the most common hottest cylinder was unique.
- **Fleet:** four new baselined metrics (`egt1..4_deviation`, OAT-stratified) and
  `FleetAnalysis.cylinder_balance`: per-flight hottest cylinder plus the aircraft's usual one
  (learned after 10 clear flights at ≥ 70% agreement, else the engine profile's new
  `expected_hot_cylinder`: 4 for the 916iS/915iS, none for the 912iS/914iS).
- **Insights:** `cylinder_rank` is wired. It warns when a different cylinder runs hottest by
  ≥ 15°F for 2 consecutive flights; it is informational only when the aircraft's own pattern
  isn't learned yet. New `egt_cyl_deviation` watches each cylinder's balance against its own
  baseline and trend in either direction. The `egt4_elevation` rule now ships disabled.
- **Rules:** `applies_to` (one rule block for several metrics) and trend `"direction": "either"`.
- **Web UI:** Trends → EGT → *cylinder balance*: four deviation lines, a hottest-cylinder strip
  and the usual-hottest chip. The rule playground edits the new rule parameters.
- Existing workspaces re-analyse their flights on the next scan (engine version change), which
  fills in the new metrics.

---

## 0.11.0 — September 23, 2026

**The engine contract refactor (Stages 0–4a) and the new `slingology-eis` CLI.** The
per-flight/fleet analysis logic that used to live only in `notebooks/` scripts now lives in
a pure, stateless library (`slingology_eis/operations.py`) behind a typed contract, driven
by `docs/specs/01-engine-contract.md` (through v0.6) and `docs/specs/02-results-bundle-and-workspace.md`.
The goal: the same engine a future browser UI runs unmodified via Pyodide (`docs/specs/04-runtime-adapters-and-pyodide-spike.md`
reached a GO decision this cycle — numpy+pandas only, no SciPy/Matplotlib/Jupyter needed at runtime).

- **New: `slingology-eis` command-line interface** (`slingology_eis/cli.py`, installed via
  `pyproject.toml`). Subcommands: `engines`, `flight`, `ecu`, `fleet`, `report`, `import`,
  `rules check`, `rules try`; `export-bundle` and `serve` are present but intentionally stubbed
  (exit 2) pending Spec 02's bundle format and the Stage 4b local-server adapter. Global
  options `--logs`/`--workspace`/`--engine`/`--json`/`--anonymize`/`--quiet`; exit codes
  0/1/2. `--json` output validates against the new JSON Schemas in `contract/schema/`.
  See the README's Command-line interface section for the full reference.
- **New: the engine contract.** Four operations — `analyze_flight`, `analyze_ecu`,
  `update_fleet`, `evaluate_insights` — each returning a typed, `.to_dict()`-serializable
  result object (`FlightAnalysis`, `EcuAnalysis`, `FleetAnalysis`, `InsightSet`) with a
  shared `Provenance`/`Diagnostic` envelope (`slingology_eis/contract.py`). Every result
  validates against a hand-authored JSON Schema in `contract/schema/`. Missing metrics
  always carry a reason code (`NO_PHASE`, `CHANNEL_MISSING`, `INSUFFICIENT_DATA`,
  `NOT_APPLICABLE`, `EXCLUDED`) instead of a bare `null`.
- **New: minimal workspace persistence.** `fleet`/`import`/`report`/`rules try` cache
  results under `<workspace>/flights/<flight_id>/analysis.json` and
  `<workspace>/fleet/analysis.json` — a deliberately minimal subset of Spec 02's eventual
  layout, just enough to avoid recomputing the fleet baseline from every log on every call.
- **New: `slingology_eis/rules.py`** — `validate_rules()` (schema/semantic checks on an
  `insight_rules.json`-shaped file) and `what_if_rules()` (diffs the insights a candidate
  rule set would produce against the currently-shipped one, for one flight). Backs the new
  `rules check`/`rules try` subcommands.
- **New: `slingology_eis/baselines.py` and `topics.py`**, extracted from the notebook
  scripts (Stage 2) — the personal-baseline computation and all 14 analytics topics are now
  importable library functions, not print statements. `notebooks/03` and `04` call into
  them but still own their own orchestration/rendering (see "Known duplication" below).
- **New: `tests/` suite** — 119 tests across `characterization/` (locks legacy notebook
  behaviour against frozen goldens), `unit/`, `contract/` (schema validation + purity checks
  against real and synthetic flights), and `cli/` (18 tests: schema validation, exit codes,
  `--anonymize`, rules check/try, gated real-data subcommands).
- **Packaging: `pyproject.toml` replaces `requirements.txt`.** Install with
  `pip install -e .`; core runtime deps are just `pandas` and `numpy` — nothing else is
  actually imported anywhere in `slingology_eis/` or `notebooks/`. `pytest`/`jsonschema` are
  now a `dev` extra; `jupyter`/`jupytext`/`matplotlib` are a `notebooks` extra.
  `requirements.txt` (which overstated the dependency list, including an unused `scipy`
  pin) is removed.
- **Fixed: a 2.5-month-old bug that silenced all limit checking.**
  `engine_limits_from_config()` built each `Limit` inside a shadowed local list that was
  discarded every loop iteration, so `check_exceedances()` silently returned zero events for
  every engine, for every flight, since commit `a7af9ad` (July 3). One-line fix, plus
  regression tests (`tests/unit/test_limits.py`) asserting a non-empty limit list. This
  surfaced real exceedances (mostly fuel-pressure related) in the golden fixtures that were
  previously hidden — root-causing which are genuine versus sensor/CAN-dropout artifacts is
  deliberately deferred until after this release.
  Characterization tests didn't catch it because they skip when no private log data is
  present, so a silent-empty-result regression like this produced no test failure.
- **Fixed: duplicate oil-temperature insight** — `topics.oil_temp_peak()` had its
  threshold/baseline-deviation insight loop duplicated, firing the same insight twice.
  Dormant in every golden report until now; fixed with a unit test asserting single-insight
  behaviour.
- **Fixed: `overboost_time()` crash on a log missing `power_pct`**, `update_fleet([])`
  crash on an empty flight list, and a bare `NaN` (instead of `None`) surviving into
  `FlightMetrics` JSON output — all caught via contract-layer testing against synthetic
  logs, none previously exercised by the notebook path.
- **Known duplication, tracked for cleanup:** `notebooks/03`'s `write_baselines()` and
  `notebooks/04`'s report loop still duplicate orchestration/rendering logic that
  `operations.py` + `cli.py`'s `render_report`/`render_fleet_summary` now do independently
  — the two aren't byte-identical. Kept through this release as the characterization tests'
  independent oracle; slated for retirement or simplification to thin plotting wrappers
  once the CLI has a track record post-release. See `BACKLOG.md`.
- **Engine coverage:** `engines/915iS.json` is now fully **VERIFIED** against
  OM-915 i A/C24, Edition 0/Rev. 4 (previously a placeholder). 912iS and 914iS remain
  placeholders.

This release is the agreed milestone before UI work (Spec 03/05) begins — a released,
documented, conformance-checked CLI to build the browser UI against, per the refactor's own
"characterize before you change it" pattern.

---

## 0.10.0 — July 7, 2026

**New script: `04_flight_report.py`** — per-flight pilot report with two-layer Analysis/Insight format. Accepts a log filename alone (resolved against `data/logs/`) or a full path, matching script 01 behaviour. Report header shows flight date, time, airport (from filename where available), engine hours start→end, airborne duration, max altitude, max IAS, and FADEC fuel used. Saves report to `data/reports/report_<logname>.txt`.

**Two-layer Analysis/Insight format (A1 complete).** Every analytics topic produces an Analysis line (always present, descriptive) and a conditional Insight line (only when something is worth flagging). Trigger rules defined in `insight_rules.json` at the toolkit root — three trigger types: `threshold`, `baseline_deviation`, `trend`. Adding or adjusting triggers requires only editing the JSON file, no code changes.

**`insight_rules.json`** — new file at toolkit root. Defines trigger rules for all 14 analytics topics. Three trigger types: `threshold` (hard limit check), `baseline_deviation` (z-score vs personal average), `trend` (R²-gated directional trend). Same z-score threshold across all stratification bands.

**`reports/baselines.json`** — written by script 03 after every run. Contains per-metric mean, std, n, confidence label, stratified sub-baselines by DA/OAT band, trend coefficients (R²-gated), and raw per-flight data points for future visualisation. Read by script 04 for all baseline comparisons without reloading all logs.

**`reports/models.json`** — written by script 03 alongside baselines. Contains empirical regression models. Currently holds the `takeoff_map` model: linear regression MAP = f(pressure_alt_ft, oat_c), RPM ≥ 5,500 capture threshold during TAKEOFF_ROLL phase. Confidence thresholds: n<5 = "still collecting data", n 5–14 = LOW, n≥15 = MODERATE. Current model: n=15, MODERATE, R²=0.71. Extensible for future models (A5 fuel flow, etc.).

**All 14 A2 analytics topics implemented in script 04:**
- EGT spread — baseline deviation + trend triggers; cruise mean vs personal average vs OM 392°F limit
- EGT4 elevation — baseline deviation; EGT4 vs cylinders 1–3 vs personal average
- Cylinder rank stability — which cylinder is consistently hottest; fleet stable count context; insight if rank unstable during cruise
- Oil temperature — threshold (OM 248°F) + baseline deviation; personal average comparison
- Coolant temperature — threshold (OM 248°F) + baseline deviation; personal average comparison
- Oil/coolant ratio — baseline deviation; personal average comparison
- Overboost time — threshold trigger (300s OM limit) with close-call flag at 240–300s
- Cruise efficiency — DA-stratified baseline deviation; DA context note added
- Cruise fuel flow — baseline deviation; cruise DA vs fleet average DA context; note if this flight significantly above average DA
- MAP at takeoff — empirical linear regression model; shows "still collecting data (n=X)" until n≥5; 1.5 inHg deviation threshold for insight
- ENGINE ECU — uses `extract_engine_ecu_runs()` classifier from `cas.py`; per-event detail for IN_FLIGHT events including co-active alerts; OIL PRESS specifically flagged
- Operating limit exceedances — phase-filtered, duration-thresholded; `report_in_exceedances` flag suppresses guidance bands
- Climb thermal rate — baseline deviation; oil temp rise rate °F/min during climb
- Flight phase mix — DROPPED as standalone; replaced with "no cruise detected" header warning when cruise data is missing

**Fleet Insights section added to script 03.** Appears at end of output and saved as `reports/fleet_insights.txt`. Tight summary of major findings only — no noise. `⚠` lines for: hard OM limit exceedances, IN-FLIGHT ENGINE ECU events, confirmed trends (R²≥0.5, n≥10), outliers (z≥2.5). `✓` lines only for safety-critical clean checks (no limit exceedances, no IN-FLIGHT ENGINE ECU events).

**`cas.py` — ENGINE ECU classifier refactored into library.**
- `classify_engine_ecu_run()` and `extract_engine_ecu_runs()` moved from `02_engine_ecu_correlation.py` into `cas.py` as importable library functions
- Script 02 and script 04 both import from `cas.py` — single source of truth, no code duplication
- Lane check pairing logic included in `extract_engine_ecu_runs()` — LANE_CHECK events within `_LANE_CHECK_PAIR_WINDOW_S` seconds of each other are marked as paired
- Classifier constants (`_RPM_RUNNING`, `_VOLTAGE_DECLINE_THRESHOLD`, `_LANE_CHECK_MAX_IAS_KT`, `_LANE_CHECK_PAIR_WINDOW_S`) are signal-processing heuristics that live in code; engine-specific thresholds (lane check RPM band, max duration) are read from engine config
- Additional SHUTDOWN gate added: low IAS + low-medium RPM + duration >30s → SHUTDOWN, preventing long taxi/shutdown sequences from being misclassified as IN_FLIGHT

**`limits.py` — phase filtering and duration thresholds.**
- `Limit` dataclass extended with four new fields: `phases` (list of flight phases where limit applies), `min_duration_s` (flat minimum duration), `min_duration_by_phase` (per-phase duration dict, `null` = suppress entirely), `report_in_exceedances` (bool, default true)
- `check_exceedances()` honours all new fields — phase filtering applied before checking, duration filtering applied per event
- Eliminates false positives from sensor noise, pre-flight readings, and expected transient events

**`engines/916iS.json` — phase-aware exceedance suppression.**
- Fuel pressure maximum: `min_duration_by_phase` — suppressed entirely during TAXI/TAKEOFF_ROLL/LANDING (pump test and tank switching transients), 10s minimum during CLIMB/DESCENT, 30s minimum during CRUISE (covers full tank switching sequence)
- Fuel pressure minimum: `min_duration_s: 10` — filters brief sensor transients
- Idle RPM minimum: `min_duration_s: 30` — filters normal governor variation (1780–1790 rpm is within normal range)
- Oil temp optimal band: `report_in_exceedances: false` — guidance band reported in oil temp analysis section, not exceedances
- Oil temp min (takeoff): `phases: ["TAKEOFF_ROLL", "CLIMB", "CRUISE"]` — excludes pre-flight readings
- Oil pressure min (>3500 rpm): `phases: ["CLIMB", "CRUISE", "DESCENT"]` — excludes engine start and taxi

**`fleet.py` — new `FlightMetrics` fields.**
- `takeoff_map_inhg` — median MAP during TAKEOFF_ROLL with RPM ≥ 5,500
- `takeoff_pressure_alt_ft` — median pressure altitude during same window
- `takeoff_oat_c` — median OAT during same window
- `inflight_ecu_count` — count of genuine IN_FLIGHT ENGINE ECU events per flight using `cas.py` classifier (replaces unreliable `cas_inflight_anomaly_count` for fleet-level reporting)
- `cruise_da_ft` added to `baselines.json` metric definitions for DA context in cruise fuel flow section

**`loader.py` — datetime parsing fix.** Explicit `format="%Y-%m-%d %H:%M:%S"` added to `pd.to_datetime()` call, eliminating per-element dateutil fallback warning on every log load.

**Aircraft registration corrected** — N5512E → N117ZS throughout research paper and all scripts.

**Fleet count clarified** — 23 real flights (50 total log files, 27 ground sessions filtered at loader level). All analytics, baselines, and insights correctly use 23 flights.

**`__version__` bumped to `0.10.0`** in `slingology_eis/__init__.py`.

---

## 0.9.0 — June 23, 2026

**Multi-engine support via external config files.** All operating limits previously hardcoded in `limits.py` are now loaded from JSON engine config files in the `engines/` directory. Engine selection resolves in priority order: explicit argument → `SLINGOLOGY_ENGINE` environment variable → `config.json` in the toolkit root → default (916iS).

**Engine configs:**
- `engines/916iS.json` — fully sourced from OM-916 i/C24, Edition 0 / Rev. 1. Status: `VERIFIED`.
- `engines/915iS.json`, `engines/914iS.json`, `engines/912iS.json` — placeholder configs with estimated values from published specs. Status: `PLACEHOLDER`. Attempting to use these fires a `UserWarning` reminding you to verify against the official OM before operational use.

**`config.json`** added to toolkit root — set `"engine": "916iS"` (or another engine name) once, and all scripts pick it up automatically. No per-run argument needed.

**All hardcoded engine-specific thresholds replaced:**
- `limits.py` — all `Limit` objects and EGT spread conditional thresholds now read from the engine config
- `phases.py` — `overboost_time()` reads RPM threshold, power threshold, and time limit from the engine config's `overboost` block
- `02_engine_ecu_correlation.py` — LANE_CHECK RPM band and max duration read from the engine config's `phase_detection` block
- `03_multi_flight_insights.py` — overboost section uses config-driven limit values; engine name shown in report header

**`limits_report()` now shows engine name** and flags PLACEHOLDER configs explicitly in the output.

**Backlog item D1 completed.** Adding a new engine requires only a new JSON file sourced from its OM — no code changes.

---

## 0.8.0 — June 23, 2026

**Ground-session filtering moved to the loader.** Ground-only sessions are now excluded at `load_directory()` time by default (`skip_ground_sessions=True`). Detection: a file is excluded if estimated airborne time (rows with RPM > 3,000 AND IAS > 30kt) is under 3 minutes. Ground sessions print as `·` with an explicit "ground session — skipped" label; the summary line reports "Loaded N flight(s), skipped M ground session(s)."

`real_flights_only()` in `fleet.py` and `MIN_AIRBORNE_MIN_FOR_FLEET_STATS` removed — superseded by the loader-level filter. Pass `skip_ground_sessions=False` to `load_directory()` to examine ground sessions directly.

**Community data backlog item removed.** Fleet-level comparisons using logs from other aircraft removed as out of scope.

---

## 0.7.0 — June 20, 2026

**New module: `climb.py`** — climb-rate-correlated thermal analysis. Bins CLIMB-phase rows by VS (gentle <500fpm, normal 500–1000fpm, aggressive >1000fpm) and computes °F/min rise rate per bucket via linear fit. First real finding: oil temp rise rate roughly tripled (+4.4 → +12.8°F/min) from normal to aggressive climb rate. Wired into `01_first_flight_analysis.py` and `fleet.py`.

**DA/OAT stratification in `fleet.py`.** `FlightMetrics` now carries `cruise_da_ft`, `cruise_oat_c`, `da_band`, `oat_band`. New `baseline_stratified()` and `trend_stratified()` group by band before computing statistics. Cruise efficiency moved to DA-banded trend; EGT spread gained OAT-banded trend in script 03.

**Overboost distribution / throttle-discipline view.** Script 03 now reports exceeded/close-call/comfortable buckets across all flights plus a trend.

**Script 02 text report** now includes the IN-FLIGHT interpretation section that was previously console-only.

**Validated against 50-flight dataset** — 23 real flights, 27 ground sessions. Found 1 genuine IN_FLIGHT ENGINE ECU event (KSFF, OIL PRESS co-active) and one real overboost exceedance (confirmed ATC-workload-related, 381s).

---

## 0.6.0 — June 20, 2026

**Fuel-flow calibration (K_fuel) deliberately descoped.** For full-to-full refuelling, gallons added at the pump already equals true consumption directly. Removed: `FillEvent`, `save_fills`, `load_fills`, `fadec_gallons_for_window`, `import_fills_csv`, `import_and_save_fills`, `compute_k_fuel`, `scripts/import_fills.py`. See research paper §6.2.

**Script 03 reorganized** from 6 sections to 5 — "Maintenance" section was a mislabel; metrics redistributed to Trends and Operational.

**Changelog split** from README into this file.

---

## 0.5.0 — June 19, 2026

Fuel CSV import multi-flight gap handling — `fadec_gallons` summed across all flights in the window between consecutive fills. *(Superseded by 0.6.0 — entire feature removed.)*

---

## 0.4.0 — June 19, 2026

Fuel fill-up CSV import (`scripts/import_fills.py`). Version tracking added to README and `__version__`. *(Superseded by 0.6.0 — entire feature removed.)*

---

## 0.3.0 — June 19, 2026

Duplicate flight detection (`find_duplicate_flights`, `deduplicate_flights`) wired into scripts 02 and 03. Catches same flight exported twice (SD-card + Garmin Pilot).

---

## 0.2.0 — June 16, 2026

`03_multi_flight_insights.py` and `fleet.py` added: baselines, trends, outliers, operational/data-quality summaries. Phase detection fixes: auto field-elevation estimation per flight; hysteresis added to CRUISE/CLIMB/DESCENT transitions. `01_first_flight_analysis.py` takes a filename argument.

---

## 0.1.x — June 16, 2026

Initial toolkit: `loader`, `limits`, `phases`, `egt`, `fuel`, `cas` modules. `02_engine_ecu_correlation.py` with POWERUP/LANE_CHECK/SHUTDOWN/IN_FLIGHT classification. Dual-format log loading (G3X-direct + Garmin Pilot). Case-insensitive directory glob.