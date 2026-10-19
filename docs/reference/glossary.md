# Glossary

**Analysis line** — The first line of every topic card: this flight's number, your usual, and the Operators Manual limit. Always present; never a judgement.

**Blip** — An engine-computer alert shorter than three seconds. Counted, never an event.

**Breach** — An event that a filter on that limit does not cover. Shown as an ordinary event, marked *beyond your filter*.

**CAS event** — An occurrence of a panel alert (today, the ENGINE ECU caution) that the app did not expect — on the ground with the engine running but not a lane check, or in flight. Listed with limit events.

**Close call** — Time at takeoff power within 60 seconds of the five-minute limit.

**Contributing flight** — A flight that is part of the reference. Every admitted flight contributes unless you exclude it.

**Density altitude (DA) band** — One of four altitude-and-temperature conditions (low, moderate, high, very high) within which cruise fuel figures and takeoff boost are compared.

**Deviation (cylinder)** — One cylinder's cruise EGT minus the average of the other three.

**Drifting** — A filter whose recent flights have gone further past the limit, or had events more often, than the flights the filter was set against.

**ECU** — The engine control unit, the engine computer. Two lanes, A and B.

**Engine hours** — The engine meter reading, carried in every log. The x-axis of every trend.

**Event** — A reading past an Operators Manual limit for long enough to matter, or an unexpected CAS alert: when, which phase, how long, how far.

**Exclude (from reference)** — Keep a flight's own analysis but stop it shaping what other flights are compared with. Needs a reason.

**FADEC** — Full-authority digital engine control. On a Rotax iS the engine computer sets fuel and spark; the pilot has only the throttle.

**Filter** — Your statement that a limit is exceeded on your aircraft in a way you understand and accept, within bounds you set. Applies to every flight; still watched.

**Flight** — A log the app has admitted: airborne for at least ten minutes, without a long gap, not a duplicate.

**Flight facts** — Fuel burned, cruise miles per gallon, cruise fuel flow and the lane-check result, shown in the Flight view header for planning. Never compared, never alerted.

**Insight** — A short statement on a topic card that something about this flight is worth your attention. Appears only when a trigger fires.

**Journal** — The register of every decision currently in force in the workspace.

**Lane check** — The pre-takeoff single-lane engine test. The app recognises it by RPM and pattern and reports whether both lanes were covered.

**Limit** — An Operators Manual operating limit for your engine model.

**Log** — A file your Garmin avionics wrote during one power-up: G3X, Garmin Pilot export or AXIS.

**n_min** — How many other flights the reference needs before a comparison is made. Default 10.

**OAT band** — One of four outside-air-temperature conditions (cold, mild, warm, hot) within which thermal metrics are compared.

**Outlier** — A flight more than the z-threshold (default 2 standard deviations) from your usual for a metric.

**Phase** — What the aircraft was doing at each second of a flight — pre-start, start, warm-up, taxi, takeoff roll, climb, cruise, descent, approach, landing roll, shutdown — worked out automatically.

**Pin** — Fix a metric's reference to a chosen set of flights instead of the rolling history.

**Recent window** — The newest flights Trends compares against the reference: at least the last 10 engine hours, at least 5 flights, at most 15.

**Reference** — What the app has learned from your own flights about what each metric usually is on this engine: average and spread, by condition where it matters. Also *your usual*.

**Rolling** — A reference that includes every earlier contributing flight and grows as you fly. The default.

**Rule** — A topic's triggers and their values. Editable from the card; one set per workspace.

**Severity** — The label on an event or insight: LIMIT, WARNING, WATCH, INFO (CAUTION on limits). A reading aid; the app does not act on it.

**Shift** — On Trends, the recent window's average sitting far enough from the reference's average to count as a change.

**Skipped** — A log that did not become a flight, listed with its reason. Can be included.

**Spread (EGT)** — Hottest cruise EGT minus coolest.

**Still building** — The reference does not yet have n_min flights for this metric; the number is shown, the comparison withheld.

**Sync** — Rescan the workspace's folders for new or moved logs and offer to analyse them.

**Topic** — One thing the app watches, with a card on every Flight view.

**Trend** — A metric moving steadily with engine hours, reported only when a straight line fits well (R² ≥ 0.5) over at least ten flights.

**Trigger** — A condition on a topic that, when met, produces an insight: baseline deviation, trend or threshold.

**Unverified / not yet validated** — The topic runs on this engine model but no data from such an aircraft has yet confirmed it behaves sensibly.

**Workspace** — The app's view of one aircraft: its log folders plus everything derived and every decision made.

**z-threshold** — How many standard deviations from your usual a reading must be to count as unusual. Default 2.0.
