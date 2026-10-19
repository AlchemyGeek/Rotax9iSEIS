# SlingologyEIS — Backlog

Last updated: October 19, 2026 (the 1.0.1 merge of `pyodide` into `main`)
Toolkit version: 1.0.1 · Research paper: Edition 0.3

Open work, organised by the spec or area that owns it. Everything completed is in
[CHANGELOG.md](CHANGELOG.md); this file no longer carries struck-through history.
Each item names its type — **code**, **design**, **research**, **docs** — and, where one exists,
the spec section that already designed it. Nothing here is scheduled; the next phase of the
program is decided when the current screen reviews finish (see §2).

---

## 1. Platform and hosting

### P1. Browser mode — offline and polish (Spec 04 step 6)
**Type:** code · **Owner:** Spec 04 §9.5, Q10
Shipped in 1.0.1: the app runs in the browser from a static site with a self-hosted runtime.
Left from the plan: the service worker that precaches the runtime and wheel so a visited site
opens and analyses with no network (closes Spec 04 S5); wire the persistent-storage request and
the eviction notice fully; a support checklist (which browsers, what storage means); Pyodide interpreter snapshots to cut the warm
start below "a few seconds" once the API is stable on Safari (D13); iPad as a target (deferred —
folder access and storage on iPad still to be assessed).

### P2. Easy self-hosting of the server mode
**Type:** code · **Owner:** Spec 04 D7 (option D)
A one-command option (Docker, Synology) for users who want the server mode without a Python
setup. The browser mode's static site already runs on any static host.

### P3. A browser-mode workspace on more than one device
**Type:** design
A browser-mode workspace lives in one browser on one device. Moving it is *Export all* →
*Import*; there is no sync. Decide whether that stays the answer (it keeps the no-service
promise) or whether an optional user-owned sync (a folder the user controls) is worth designing.

### P4. Time-based engine instead of rows-as-seconds
**Type:** code · **Owner:** Spec 01 §6.5 (decision 1)
AXIS logs at ~0.83 Hz; the loader puts them on a 1-second grid (filled rows flagged) so the
engine's row-counting paths (airborne minutes, phase minutes, overboost blocks, ECU run
durations, cruise dwell, smoothing windows) stay correct. The honest long-term fix is
`elapsed_s` arithmetic throughout. Hardening, not urgent.

### P5. Web test hygiene
**Type:** code
`npx vitest run` exits 1 on an unhandled `scrollIntoView is not a function` from jsdom
(`Trends.tsx`'s panel scroll after a setTimeout) while all 169 tests pass. Stub it in the
test setup or guard the call.

### P6. Documentation site — next steps
**Type:** docs · **Owner:** Spec 13
The first edition shipped in 1.0.1 (concept pages, walkthroughs, reference; MkDocs Material on
GitHub Pages). Open: retake the screenshot batch after each UI change; the generated "what's new"
page the Settings → Engine tab points at; a browser-mode walkthrough (Choose folder, Storage,
reconnect on Safari); searchable/askable via an AI assistant, as Spec 13 first imagined.

### P7. Feedback channel for non-technical users
**Type:** infrastructure
A way for pilots without a GitHub account to report bugs and suggest features. Chosen:
self-hosted Fider on the Synology NAS (DDNS hostname, Gmail sign-in mail, DSM reverse proxy),
doubling as the self-hosting testbed for P2. Paused until after this release.

---

## 2. Screens, workflows and program direction

### U1. Screen reviews still open
**Type:** design · **Owner:** Spec 03, Spec 14
Each web screen is being re-evaluated for relevance and value, one at a time (Oct 7–15: Baselines
→ Settings, Notes → Journal, ECU retired, Flight view restructured, Flights Sync/Add logs).
Remaining: **Journal as built** (Spec 14 v0.10's register of decisions in force). After that the
next phase of the program is chosen.

### U2. Research mode
**Type:** design · **Owner:** Spec 06 (number reserved; not in the nav until designed)
Review a metric outside expected thresholds over many flights — improving, worsening or stable —
and a path from an Explore finding to the operational side (Spec 03 principle 6). Must follow the
spec format and numbering. Depends on and feeds: change-point detection (T4), the Research-status
topics in §4, and C5/C6.

### U3. Insights under the program principles
**Type:** design · **Owner:** Spec 11 (drafted v0.1, paused by decision)
The Oct 4 reset: (1) the OM is the only predefined rule; (2) the user overrides OM limits through
operations such as filters; (3) the system's job is to say when something changed in those
operations; (4) the user has tools to analyse anomalies and silences them as they choose — no
severity-based policy. Decided for Spec 11 so far: observation insights on by default with their
settings shown on the card; severity as a display label only; three silencing levels —
acknowledge one insight on one flight (not built), filter workspace-wide (built, Spec 09),
disable a topic (built, Spec 14). To be reassessed after U1.

### U4. Sharing insights and research with other pilots
**Type:** design
Users aren't software engineers, so sharing needs a simple path — possibly a custom website.
Builds on workspace export/import (shipped 1.0.0) and U6. Community-wide aggregation of data remains out of scope.

### U5. Fleet workspaces
**Type:** design · **Owner:** Spec 02 §5.6 (interim)
A workspace holding many aircraft with the same engine, to get engine-type insights rather than
single-aircraft ones. Interim: the mixed-aircraft notice (one workspace per aircraft recommended;
same-aircraft confirmation for ident typos). Needs a decision on which learned numbers may cross
aircraft — today none do (Spec 10 §1).

### U6. Imported workspaces — the sender's view
**Type:** design · **Owner:** Spec 02 §7, Spec 03 §5.8
Export/import shipped (Oct 15–17). Open: a later export of an imported workspace carries only its
own flights; the sender's decisions stay dormant until the matching log arrives; nothing yet tells
the recipient when their own reference diverges from what the sender saw. Revisit with U4.

### U7. Scope labels on the remaining one-click actions
**Type:** code · **Owner:** Spec 14 §7.5
Still unlabelled: tail-number grouping (labelling only — comparisons already treat the workspace
as one aircraft). Everything else in §7.5's table carries its scope caption.

---

## 3. Trends — v2 (designed in Spec 12 §13)

### T1. OM headroom projection
**Type:** code · **Owner:** Spec 12 §13
"At the recent rate, headroom reaches zero at ~N h" on a strip with an OM line and a qualifying
shift; recent-window slope only. Wait for operating experience with the shift statistic.

### T2. Maintenance annotations on the time axis
**Type:** code + design · **Owner:** Spec 12 §13; Spec 02 change needed
Vertical markers for workspace-level events (oil change, plug change, filter created, software
update) so a shift next to a marker reads as explained. Needs a workspace event log with no
flight to attach to. Supersedes the old maintenance-log and post-maintenance-baseline ideas; the
arbitrary historical pin ("before the oil change") is covered by zoom-based pinning already.

### T3. Condition strip
**Type:** code · **Owner:** Spec 12 §13
Cruise DA, cruise OAT, duration and dominant climb-VS bucket per flight under each panel, so a
high point can be read against its conditions. `cruise_da_ft`/`cruise_oat_c` already exist.

### T4. Change-point detection
**Type:** research → code · **Owner:** Spec 12 §13, Spec 06
CUSUM or Bayesian change-point per metric, giving a detected step time rather than a window
mean. Research mode first.

### T5. Engine hours as the trend x-axis
**Type:** research
Engine hours in the log header are the Hobbs at log creation. Compare against cumulative
airborne hours derived from the logs. Low urgency.

---

## 4. Analytics topics (Spec 10 register)

### A1. Topics are single-aircraft evidence
**Type:** research · **Owner:** Spec 10 §4, §5.1, §8.2
Every admitted topic rests on N117ZS alone and is *Unverified* on the 912iS/915iS. A
re-audit is triggered by data from a new aircraft or engine type. The practical path is other
pilots' logs (U4, U5).

### A2. `engine_ecu_inflight` — Admitted (provisional)
**Type:** research · **Owner:** Spec 10 D18
Mechanism sound, positive case never seen: 0 in-flight runs on 115 logs after the phase-based
classifier. Condition to close: a first true positive, or a deliberate test.

### A3. C5 — oil–coolant temperature balance
**Type:** research · **Owner:** Spec 10 §7 (Proposed)
Successor to the dropped `oil_coolant_ratio`. Must first show industry use and a sourced
mechanism before any code.

### A4. C6 — lane-check adherence
**Type:** design · **Owner:** Spec 10 §7 (procedure class, undefined)
Pilot procedure, not an engine signal, so not a topic; the lane-check result is a flight fact.
Needs a defined "procedure" class before it can be anything more.

### A5. `climb_thermal_rate` — Research
**Type:** research · **Owner:** Spec 10 D2
Rise-rate metrics are still computed; both proposed conditioners (climb VS bucket, OAT) were
tested and found insufficient to make it discriminating. Needs a new predictor.

### A6. Peak temperature vs flight duration
**Type:** research · **Owner:** Spec 10 D7 (revised)
Oil-temperature peak correlates with airborne time (r ≈ 0.6) at every candidate threshold, so no
minimum-duration cut was applied. Predicting the peak from flight length is a Research item.

### A7. Power × density-altitude fuel-flow model
**Type:** research · **Owner:** Spec 10 §4.2
A DA band × power setting → expected gph model. Cruise fuel flow is a flight fact now, not a
topic, so this is research until it earns admission.

### A8. ECO/POWER mode detection
**Type:** research → code
Blocked on a ground-truth flight with deliberate known throttle positions. The 912iS OM states no
throttle-position threshold for the switch-over (profile notes it as intentionally absent).

### A9. Fuel pump state inference
**Type:** research → code · **Owner:** Spec 01 §6.4
The G3X log carries no pump-selection channel (`FPCM FAULT` is a fault flag). `fuel_press_psi`
is the only signal; a rule-based model of pump transitions from the pressure signature could
feed a derived channel. Needs flights with a known pump schedule to validate. Relevant to E2.

### A10. Takeoff-MAP model altitude diversity
**Type:** research
Most departures are near sea level (KPAE). The model's fitted-range guard means the extreme
flight on each axis is never judged under leave-one-out. Revisit with 5+ departures above 2,000 ft.

### A11. Topic help for engines without an EGT-split limit
**Type:** docs · **Owner:** Spec 10 §9 item 11
`egt_spread`'s help cites `{limit:egt_split_high_flow}`, which OM-912 doesn't define; one strict
xfail test. An authoring decision: wording for an engine with no such limit.

---

## 5. Limit filters (Spec 09)

### F1. Rename "overboost" for the 912iS
**Type:** code · **Owner:** Spec 09 Q9 (deferred)
A misnomer on a normally aspirated engine (`takeoff_power_time`). Renaming an id needs a filter
and annotation migration.

### F2. Phase-scoped bands
**Type:** design · **Owner:** Spec 09 Q10 (deferred by decision, Oct 11)
"Tolerate +2 psi, but only in CRUISE." Phase *exclusion* shipped first (Phase 8); a band that
applies only within chosen phases is the follow-on.

### F3. z-mode divergence between Journal filter cards and Trends
**Type:** design · **Owner:** Spec 12 §10
A z-mode filter's reference and the Trends recent/reference comparison use different windows;
documented, not yet reconciled.

---

## 6. Engine profiles

### E1. Other iS engines
**Type:** docs + code
Three profiles exist (912iS, 915iS, 916iS), each verified against its OM. The 914iS placeholder
was removed — the 914 is a carburetted turbo engine, not an iS. A new profile (a 912iS variant,
say) is added from its OM with every limit cited, the run-up band and `expected_hot_cylinder`,
and its per-engine topic status in `docs/specs/topics/register.json`. (OMs are never stored in
the repo.)

### E2. Fuel-pressure exceedances — root cause on N117ZS
**Type:** research
`fuel_press_max` fires on most flights with a steady +0.9–1.6 psi offset through climb, cruise
and descent (Spec 10 D15, cause 3a: likely sender calibration vs regulator pressure; confirm
with a mechanic). Allowlisted and filterable with a note. A9 would separate pump cycling from
sensor or pressure problems. Deliberately kept apart from building the tool.

---

## 7. Phase detection and signal quality

### S1. In-flight labels persisting through taxi-in and the engine cut
**Type:** code · **Owner:** CLAUDE.md regression rule
After landing, `DESCENT`/`APPROACH` can run through the taxi-in (taxi power is above the
on-ground test's 2,000 rpm) and `LANDING_ROLL` only leaves on IAS < 5 kt, which some logs never
show at rest, so an in-flight label can outlast the engine cut. The ENGINE ECU classifier works
around it (engine-state rule); exceedance phase windows and airborne-time metrics inherit it.
Likely fix: an on-ground test independent of rpm (ground speed) and a `SHUTDOWN` transition from
any phase when rpm stops. Snapshot before and after.

### S2. Touch-and-go detection
**Type:** code
`LANDING_ROLL` exits only to `TAXI` (IAS < 5 kt, rpm < 2,500) or `SHUTDOWN`; a touch-and-go
satisfies neither, so every later circuit is misclassified. Stop-and-goes and go-arounds are
handled. Needs a real pattern-work log to confirm before fixing.

### S3. Mid-log power cycle
**Type:** code · **Owner:** Spec 02 §5.11
A log with an internal gap over 5 minutes is admitted as *corrupt log*; a mid-log POWERUP
(the EIS restarting within one file) is not detected as such.

### S4. AXIS: ENGINE ECU naming and power-up capture
**Type:** research · **Owner:** Spec 01 Q9, Q10
Two AXIS logs so far; neither carries an ECU alert and both start with the engine already
running. Confirm on the first AXIS log with an engine start and lane check that AXIS names the
alert `ENGINE ECU` (else the classifier is untested on AXIS) and that power-up is captured at all.
The CAS alias table (Spec 01 v0.24) is where any other wording difference goes.
Separately decide whether `onGroundState` should feed phase detection once the reference is
AXIS-dominated — no change while G3X and AXIS flights share a reference.

### S5. `log_summary()` on a log with no fuel-flow channel
**Type:** code
`loader.log_summary()` reads `cruise["fuel_flow_gph"]` guarded on `len(cruise)` only; a real log
reaching cruise without that column would raise `KeyError` in `build_flight_metrics()`. Every
real log has the channel; the synthetic test fixtures work around it.

---

## 8. Housekeeping

### H1. Retire notebook/CLI duplication
**Type:** code
`notebooks/03`'s `write_baselines()` and `04`'s report loop duplicate what `operations.py` +
`cli.py` do (not byte-identical), kept as the characterization tests' independent oracle. Once
the web UI has a release behind it: delete 01/02/04 or shrink 03/04 to plotting wrappers, and
rework the characterization tests that run them live.

### H2. Research paper — Edition 0.4
**Type:** docs (on explicit instruction only)
Edition 0.3 predates the web UI. Known corrections: §7's "four in-flight ENGINE ECU events" is
superseded by the phase-based classifier's zero; the topic register (removed/Research topics,
flight facts); the web UI, workspaces, filters, Trends change page and Journal; the AXIS source
and its 1-second grid; 58 flights from 120 logs.

### H3. Community announcement
**Type:** docs
The Discord post draft in the project space, updated for 1.0.1: the hosted site needs no
install, the documentation site, and the `pip install` path for the server mode.

---

## Descoped, intentionally

- **Fuel-flow calibration against pump receipts** — full-to-full refuelling already gives true
  consumption (CHANGELOG 0.6.0, paper §6.2).
- **Community data aggregation** — out of scope; sharing (U4) is between pilots, not a pool.
- **Maintenance-interval tracking (100-hr / annual)** — those metrics are engine-health
  observables; interval bookkeeping isn't this tool's job.
- **Ground-only sessions** — excluded at admission (Spec 02 §5.11), never post-hoc.
- **In-app subsets or filters of the log set** — users organise subsets in their own folders;
  an experiment is a workspace over a chosen folder.
