<!-- Merge these entries into docs/reference/glossary.md in alphabetical order. Same format as the existing entries. -->

**Anchor** — The moment every slice in an aligned view is drawn from: the rule's crossing (default), slice start or end, a channel's peak, or a phase boundary.

**Descriptor** — One measurement of one channel over one slice: level, spread, swing, period, correlation with rpm, largest rate of change, and so on. The per-slice table is descriptors.

**Effect size** — How completely two groups of slices separate on a measurement, from 0 (interleaved) to 1 (no overlap). The headline of *Are these two groups different?*; shown instead of a probability.

**Evidence package** — One file from a study: each question's finding, magnitude and reference, caveats, and the per-slice table. Written for someone who has never seen the app.

**Fingerprint (flight)** — A code derived from a log's contents by which studies name flights. The same log gives the same fingerprint anywhere; nothing about the log can be recovered from it.

**Finding** — The one-sentence first part of a Research result, always with a count: *in 93 of 98 slices*.

**Hand slice** — A slice marked by hand: one flight and a window, usually the chart's zoom via *Research this window*.

**Lag** — The number of seconds one channel trails another at their best match. Zero means they move together.

**Merge gap** — In a slice rule, the longest dip in the conditions that does not split a slice in two.

**Period** — Seconds per cycle of a repeating up-and-down in a channel. Below about 3 s nothing can be seen in once-a-second logs.

**Preset** — A slice rule the app ships, measured against real logs: full-power segment, governed climb, stable cruise, idle, warm-up. Copy and edit freely.

**Read-only study** — An imported study none of whose flights are in the workspace. Shows the sender's results under a clear label; *Run this on my flights* makes a study of yours from it.

**Recurrence** — In how many of a set's slices a finding holds, out of all of them. The first number to read.

**Reference (Research)** — What a magnitude is shown beside: an Operators Manual value from the engine profile, the spread across the set's own slices, or a value you typed in with a label and a source.

**Research** — The app's third question: within a flight, does each signal behave as it should, and on every flight? Slices, four questions, studies.

**Slice** — A stretch of one flight cut by a rule, a phase or by hand, carrying every channel and its context. The unit of Research.

**Slice rule** — Conditions on channels, a minimum duration, a merge gap and an optional phase, which together cut slices from every flight.

**Slice set** — All the slices a rule produces over a selection of flights. What every question is asked of.

**Standing out** — Of a slice: sitting far from the other slices of the same source on some measurement. Different, not wrong.

**Study** — A saved Research session: selection, slice rules and hand slices, questions and settings, references, notes, and cached measurements. Lives in the workspace; travels as a `.eisstudy`.

**Swing** — Bottom-to-top of a channel within a short window, as a median over the slice; the size of a cycle.
