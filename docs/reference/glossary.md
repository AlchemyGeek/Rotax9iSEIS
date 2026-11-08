# Glossary

**Aircraft log** — The log a Garmin AXIS hands to Garmin Pilot, downloaded from flyGarmin as `aircraft-log-<tail number>-<date and time>.csv`. Always covers the whole power-up. When the same flight's AXIS card log is also present, the app keeps both and analyses this one.

**Analysis line** — The first line of every topic card: this flight's number, your usual, and the Operators Manual limit. Always present; never a judgement.

**Anchor** — The moment every slice in an aligned view is drawn from: the rule's crossing (default), slice start or end, a channel's peak, or a phase boundary.

**Blip** — An engine-computer alert shorter than three seconds. Counted, never an event.

**Breach** — An event that a filter on that limit does not cover. Shown as an ordinary event, marked *beyond your filter*.

**CAS event** — An occurrence of a panel alert (today, the ENGINE ECU caution) that the app did not expect — on the ground with the engine running but not a lane check, or in flight. Listed with limit events.

**Close call** — Time at takeoff power within 60 seconds of the five-minute limit.

**Contributing flight** — A flight that is part of the reference. Every admitted flight contributes unless you exclude it.

**Density altitude (DA) band** — One of four altitude-and-temperature conditions (low, moderate, high, very high) within which cruise fuel figures and takeoff boost are compared.

**Descriptor** — One measurement of one channel over one slice: level, spread, swing, period, correlation with rpm, largest rate of change, and so on. The per-slice table is descriptors.

**Deviation (cylinder)** — One cylinder's cruise EGT minus the average of the other three.

**Drifting** — A filter whose recent flights have gone further past the limit, or had events more often, than the flights the filter was set against.

**ECU** — The engine control unit, the engine computer. Two lanes, A and B.

**Effect size** — How completely two groups of slices separate on a measurement, from 0 (interleaved) to 1 (no overlap). The headline of *Are these two groups different?*; shown instead of a probability.

**Engine hours** — The engine meter reading, carried in every log. The x-axis of every trend.

**Event** — A reading past an Operators Manual limit for long enough to matter, or an unexpected CAS alert: when, which phase, how long, how far.

**Evidence package** — One file from a study: each question's finding, magnitude and reference, caveats, and the per-slice table. Written for someone who has never seen the app.

**Exclude (from reference)** — Keep a flight's own analysis but stop it shaping what other flights are compared with. Needs a reason.

**FADEC** — Full-authority digital engine control. On a Rotax iS the engine computer sets fuel and spark; the pilot has only the throttle.

**Filter** — Your statement that a limit is exceeded on your aircraft in a way you understand and accept, within bounds you set. Applies to every flight; still watched.

**Finding** — The one-sentence first part of a Research result, always with a count: *in 93 of 98 slices*.

**Fingerprint (flight)** — A code derived from a log's contents by which studies name flights. The same log gives the same fingerprint anywhere; nothing about the log can be recovered from it.

**Flight facts** — Fuel burned, cruise miles per gallon, cruise fuel flow and the lane-check result, shown in the Flight view header for planning. Never compared, never alerted.

**Flight** — A log the app has admitted: airborne for at least ten minutes, without a long gap, not a duplicate.

**Hand slice** — A slice marked by hand: one flight and a window, usually the chart's zoom via *Research this window*.

**Insight** — A short statement on a topic card that something about this flight is worth your attention. Appears only when a trigger fires.

**Journal** — The register of every decision currently in force in the workspace.

**Lag** — The number of seconds one channel trails another at their best match. Zero means they move together.

**Lane check** — The pre-takeoff single-lane engine test. The app recognises it by RPM and pattern and reports whether both lanes were covered.

**Limit** — An Operators Manual operating limit for your engine model.

**Log** — A file your Garmin avionics wrote during one power-up: a G3X log, its Garmin Pilot export, an AXIS card log or an aircraft log.

**Merge gap** — In a slice rule, the longest dip in the conditions that does not split a slice in two.

**n_min** — How many other flights the reference needs before a comparison is made. Default 10.

**OAT band** — One of four outside-air-temperature conditions (cold, mild, warm, hot) within which thermal metrics are compared.

**Outlier** — A flight more than the z-threshold (default 2 standard deviations) from your usual for a metric.

**Period** — Seconds per cycle of a repeating up-and-down in a channel. Below about 3 s nothing can be seen in once-a-second logs.

**Phase** — What the aircraft was doing at each second of a flight — pre-start, start, warm-up, taxi, takeoff roll, climb, cruise, descent, approach, landing roll, shutdown — worked out automatically.

**Pin** — Fix a metric's reference to a chosen set of flights instead of the rolling history.

**Preset** — A slice rule the app ships, measured against real logs: full-power segment, governed climb, stable cruise, idle, warm-up. Copy and edit freely.

**Read-only study** — An imported study none of whose flights are in the workspace. Shows the sender's results under a clear label; *Run this on my flights* makes a study of yours from it.

**Recent window** — The newest flights Trends compares against the reference: at least the last 10 engine hours, at least 5 flights, at most 15.

**Recurrence** — In how many of a set's slices a finding holds, out of all of them. The first number to read.

**Reference (Research)** — What a magnitude is shown beside: an Operators Manual value from the engine profile, the spread across the set's own slices, or a value you typed in with a label and a source.

**Reference** — What the app has learned from your own flights about what each metric usually is on this engine: average and spread, by condition where it matters. Also *your usual*.

**Research** — The app's third question: within a flight, does each signal behave as it should, and on every flight? Slices, four questions, studies.

**Rolling** — A reference that includes every earlier contributing flight and grows as you fly. The default.

**Rule** — A topic's triggers and their values. Editable from the card; one set per workspace.

**Severity** — The label on an event or insight: LIMIT, WARNING, WATCH, INFO (CAUTION on limits). A reading aid; the app does not act on it.

**Shift** — On Trends, the recent window's average sitting far enough from the reference's average to count as a change.

**Skipped** — A log that did not become a flight, listed with its reason. Can be included.

**Slice rule** — Conditions on channels, a minimum duration, a merge gap and an optional phase, which together cut slices from every flight.

**Slice set** — All the slices a rule produces over a selection of flights. What every question is asked of.

**Slice** — A stretch of one flight cut by a rule, a phase or by hand, carrying every channel and its context. The unit of Research.

**Spread (EGT)** — Hottest cruise EGT minus coolest.

**Standing out** — Of a slice: sitting far from the other slices of the same source on some measurement. Different, not wrong.

**Still building** — The reference does not yet have n_min flights for this metric; the number is shown, the comparison withheld.

**Storage** — Where the app keeps your workspaces when it runs in your browser: the browser's private storage for the site, on this device. Shown under *Settings → App*. Logs are never kept there.

**Study** — A saved Research session: selection, slice rules and hand slices, questions and settings, references, notes, and cached measurements. Lives in the workspace; travels as a `.eisstudy`.

**Swing** — Bottom-to-top of a channel within a short window, as a median over the slice; the size of a cycle.

**Sync** — Rescan the workspace's folders for new or moved logs and offer to analyse them.

**Topic** — One thing the app watches, with a card on every Flight view.

**Trend** — A metric moving steadily with engine hours, reported only when a straight line fits well (R² ≥ 0.5) over at least ten flights.

**Trigger** — A condition on a topic that, when met, produces an insight: baseline deviation, trend or threshold.

**Unverified / not yet validated** — The topic runs on this engine model but no data from such an aircraft has yet confirmed it behaves sensibly.

**Workspace** — The app's view of one aircraft: its log folders plus everything derived and every decision made. Lives in the browser it was made in (or, when the app runs as a program, in its data folder); moves by export and import.

**z-threshold** — How many standard deviations from your usual a reading must be to count as unusual. Default 2.0.
