# Research: looking at the shape of a flight

<div class="in-brief" markdown>
**In brief.** Limits ask whether a value crossed an Operators Manual line. Trends ask whether a value has been drifting over months. **Research** asks a third question: *does a signal behave the way it should, within a flight, and does it do so on every flight?* You pick pieces of flights — all takeoffs, all climbs, one odd window — and ask plain questions of them: is this steady or cycling, do these two move together, are these groups different, which of these pieces is unusual. Every answer is a sentence, a chart, a number next to something to compare it with, and the caveats. Research never tells you something is wrong; it shows you what the data does and lets you judge.
</div>

## Why a third question

Some things an engine does are invisible to both of the other views. The case that led to this page: an rpm that cycled up and down by about 180 rpm every four seconds on nearly every takeoff of one aircraft, for 145 hours, inside every limit and without ever changing — so no limit fired and no trend moved. It was felt once, in calm air, and found by lining up every full-power segment of every flight and looking at them together. That is what Research does for you, without scripts.

<!-- screenshot: research-home.png — the Research page with the presets and a saved study -->

## Slices

The unit of Research is a **slice**: a stretch of one flight. There are three ways to make slices, and they all produce the same thing:

- **by rule** — a condition on channels that must hold for long enough: *rpm at or above 5,550 for at least 15 seconds*, with short dips bridged. The app ships a few of these as **presets** (full-power segment, governed climb, stable cruise, idle, warm-up), measured against real logs; you can copy and edit any of them;
- **by phase** — every climb, every takeoff roll, as the app already identifies them;
- **by hand** — the window you are looking at on a flight's chart, via *Research this window*.

A slice carries every channel, so you choose what to look at when you ask a question, not when you make the slices. A rule applied to all your flights gives a **slice set** — ninety-odd takeoffs, say — and that set is what every question is asked about.

## The questions

Four in this version. Each is phrased as you would ask it, with the method behind a help icon.

| Question | What it tells you | What it does not tell you |
|---|---|---|
| **Is this signal steady, or is it cycling?** | Whether one channel repeats an up-and-down, how often, by how much, and in how many of the slices | Whether cycling is bad: it is a shape, read against the Operators Manual limit or a value you supply |
| **Do these two move together, and who leads?** | How closely two channels rise and fall together, and the delay between them | Which one causes the other |
| **Are these two groups different?** | How far apart a measurement sits between two groups of slices — before and after a date, two altitude bands, two log sources | Why; and with a small group, the answer says so |
| **Which of these slices is unusual?** | Which slices sit far from the rest on many measurements, and on which one | That an unusual slice is a bad one — on the takeoff case above the two *unusual* slices were the two clean takeoffs |

Windows and lag ranges are not fixed numbers: the app estimates the dominant period first and sizes them from it, falling back to a fraction of the slice length when there is no period, and prints the values it used on every result.

## Reading a result

Every result has the same five parts, in this order:

1. **Finding** — one sentence, always with a count: *RPM cycles every 3.8 s (IQR 3.6–3.9), swing 180 rpm (170–190), in 93 of 98 slices.*
2. **Evidence** — the chart, and the per-slice table one click away (every slice, every measurement, and the conditions it flew in), downloadable as CSV.
3. **Magnitude** — the size of what was found, beside its **reference**: the Operators Manual value where one applies, the spread across your own slices, or a value you typed in with its source (*Airmaster governing band ±100 rpm*).
4. **Caveats** — sampling limits (logs are once a second, so periods under about three seconds are unreliable), differences between log sources, small groups, and what the result does not mean.
5. The **block** the study saves, for the next time and for anyone you share it with.

<!-- screenshot: research-result.png — one question's result in its five parts -->

## Studies

A Research session is a **study**: your selection of flights, your slice rules and hand slices, your questions, your references and notes. Studies are saved in the workspace and listed on the Research page with their first finding. They refer to flights by fingerprint, never by file, so one travels: export it as a `.eisstudy`, and another owner of the same engine imports it and runs *your* rule on *their* flights. Opened without any of its flights, a study shows the sender's results read-only under a clear label — never to be confused with your own — with one action, *Run this on my flights*.

## What comes out

Research is upstream of everything else and changes nothing by itself. A finding leaves it only when you take it somewhere:

- **Note in Journal** — the finding, verbatim, as a *Research finding* entry that links back to the study;
- **Evidence package** — the findings, magnitudes, caveats and per-slice table in one file: what a manufacturer or mechanic can act on;
- **Export** — the `.eisstudy` for another pilot.

## Getting there

From the **Research** item in the top bar, or from the thing that made you wonder: *Research this window* on a flight's chart, *Research this* on a Trends card that shows a change, or on an event's row in the Events table. Each opens a new study already pointed at that window, that metric, or that limit — across all your flights.

## How it works

The engine re-reads your logs to cut the slices (the app's normal analysis keeps only per-flight results), so the first build of a study over a whole workspace takes some seconds with progress shown; a study keeps its per-slice measurements and reopens at once. Measurements are robust (medians, median absolute deviations) because one-second engine data is quantised and has outliers; periods come from the autocorrelation with a periodogram cross-check; group differences are shown as a median difference and an effect size, never as a bare *p*-value. The only numbers the app brings to a result are Operators Manual values already in your engine profile.

The full design is [Spec 06 — Research](https://github.com/AlchemyGeek/Rotax9iSEIS/blob/main/docs/specs/06-research.md); the case that shaped it is the [takeoff RPM/MAP oscillation investigation](https://github.com/AlchemyGeek/Rotax9iSEIS/blob/main/docs/research/2026-10-takeoff-rpm-oscillation.md), which the walkthrough [Reproducing a takeoff investigation](../walkthroughs/research-takeoff.md) repeats in the app.
