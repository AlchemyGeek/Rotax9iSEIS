# Compare: the same moment on every flight

<div class="in-brief" markdown>
**In brief.** Compare runs the same measurement on every selected flight. Each slice gets one row, and the rows are grouped by flight. Each row lists the flight's conditions (log source, density altitude, OAT, engine hours, phases) and the analysis values: period, prominence, swing, level, correlation with the reference channel, and best lag. Collapse to one row per flight, or **pin** any row as the reference row; every other row then shows its difference from it. A chart plots any value against date, engine hours, density altitude or OAT. A diagnostics panel lays the windows of chosen rows side by side.
</div>

## From one flight to all of them

[Signal view](research-signal.md) tells you what happens on one flight. Compare asks whether it happens on the others, and how they differ. The slices come from the study's rule: one made from Signal's *Make this a rule*, a preset, a phase, or hand slices. The flights come from the study's selection.

Compare's rows *are* the slice set's measurements. Adding a question summarises those same rows, so a number in Compare and a number in a question's per-slice table never disagree.

## Rows and groups

Each slice is one row. Rows are grouped under their flight, and each group header shows how many slices the flight produced. Close a group to see its **median row** in place of its slices. Tick **one row per flight** to collapse every group: each flight becomes one row of medians, and its slice count is shown. A flight with several takeoffs (a touch-and-go session) then counts once.

Flights that produced no slice are listed under the table. A flight with no full-power segment is a fact worth seeing.

<!-- screenshot: research-compare-rows.png — the full-power set as rows grouped by flight, one group open -->

## The reference row

Pin any row, and it becomes the row every other row is measured from. The table adds a difference column for period, swing and correlation, and the chart marks the pinned point. Pin the flight you know best, such as the one that felt odd, and the table reads as *how is each flight different from that one?*

The pin is saved with the study. If the rule changes and the pinned slice no longer exists, the pin is dropped.

## The chart

Choose any value, for any channel, and plot it against **date**, **engine hours**, **density altitude** or **OAT**. There is one point per row, coloured by flight or by log source. When the value is a channel's level and the Operators Manual gives that channel a limit, the limit is drawn as a line.

A value that climbs with density altitude, or that separates by log source, shows here before any question is asked. [Are these two groups different?](research-groups.md) then puts a number on it.

<!-- screenshot: research-compare-chart.png — swing against density altitude, the pinned takeoff marked -->

## Diagnostics side by side

Open **Diagnostics** to see each chosen row's window drawn the way Signal view draws one: the trace with its drift removed, the autocorrelation with its period marked, and the periodogram with its peak. The pinned row and any rows you tick appear as small multiples on shared axes, each starting at its slice start, so the shapes compare directly.

## The aligned view

The v1 [aligned view](research-aligned-view.md) is a tab of Compare. It shows the same slices as traces on one time axis, lined up at the rule's crossing.

## CSV

**CSV** downloads the rows as they are shown: conditions, every value per channel, and, when a row is pinned, the differences. The file is the same as `slingology-eis research compare --csv` writes.

## What to do with this

Read the counts first: how many flights produced a slice, and how many did not. Then pin the flight you started from and sort by eye. The rows that differ most from it are the next ones to open in Signal view. When you know what you want to say about the whole set, add a question.

## How it works

Compare builds the same slice set the questions use, from the study's cached measurements where it can. The first build over a season of flights takes a few seconds, and the rows return at once after that. Collapsed rows take the median of their slices for each value. The prominent flag becomes the number of slices in which a period stands out. Spec 06 §9.2 defines Compare.
