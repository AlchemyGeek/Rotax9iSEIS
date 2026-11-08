# Research: the third question

<div class="in-brief" markdown>
**In brief.** The app asks three questions of your engine. *Did a value cross an Operators Manual line?* — that is **Limits and events**. *Has a value been drifting over the months?* — that is **Trends**. **Research** asks the third: *within a flight, does each signal behave the way it should — and does it do so on every flight?* You choose pieces of flights, ask plain questions of them, and get back a sentence, a chart, a number beside something to compare it with, and the caveats. Research never tells you something is wrong. It shows you what the data does, across all your flights at once, and leaves the judgement to you.
</div>

## Three questions, three blind spots

Each question sees what the other two cannot.

<!-- diagram: research-three-questions.svg — three panels over the same rpm trace: a limit line (level), a slow drift across months (drift), a repeating wobble inside one flight (shape) -->

- A **limit** is a line. A signal that stays under it is invisible to the limit checker, however oddly it moves.
- A **trend** compares your engine with its own past. A behaviour your engine has had since the first flight is, to Trends, normal.
- **Research** looks at the *shape* of a signal within a flight — steady or cycling, leading or lagging, like the others or not — and asks the same of every flight you have.

The case that made this page necessary: one aircraft's rpm cycled up and down by about 180 rpm every four seconds on nearly every takeoff, for 145 engine hours. It stayed inside every limit, so no event fired. It never changed, so no trend moved. A test pilot, an instructor and the owner all flew behind it without noticing; it was felt once, in calm air, and found by lining up every full-power segment of every flight and looking at them together. The owner did that with scripts. Research does it in the app.

## What Research is made of

Four ideas, each with its own page.

| Idea | In one line | Page |
|---|---|---|
| **Slice** | A piece of one flight — all takeoffs, all climbs, or one window you mark — and the unit everything else works on | [Slices: pieces of flights](research-slices.md) |
| **Aligned view** | Many slices on one time axis, lined up at the moment that matters, so your eye can compare them | [Seeing slices together](research-aligned-view.md) |
| **Question** | One of four things you can ask of a set of slices, phrased as you would ask it | [Is it steady, or cycling?](research-cycling.md) · [Do these move together?](research-together.md) · [Are these two groups different?](research-groups.md) · [Which slices are unusual?](research-unusual.md) |
| **Study** | Your selection, slices, questions, references and notes, saved and shareable | [Studies: saving and sharing](research-studies.md) |

Every answer comes in the same shape — [Reading a result](research-results.md) — and every answer has somewhere to go afterwards — [From a finding to action](research-action.md).

<!-- screenshot: research-home.png — the Research page: presets with their questions, saved studies with their first finding -->

## What Research does not do

It brings no rules of its own. The only numbers the app contributes to a result are Operators Manual values already in your engine profile; everything else is measured from your own flights or typed in by you, with its source. It declares nothing *abnormal*, *faulty* or *detected*. It changes nothing elsewhere in the app until you take a finding somewhere — into the Journal, into an evidence package, or to another owner.

That restraint is deliberate. A repeating shape in a signal may be a problem, a characteristic of the installation, or nothing. Research gives you the evidence to ask the right person; it does not pretend to be that person.

## Getting there

From **Research** in the top bar, or from the thing that made you wonder:

- *Research this window* on a flight's chart — the window you are zoomed into becomes a slice, compared with every flight;
- *Research this* on a Trends card that shows a change — a study split into before and after;
- *Research this* on a row of the Events table — the event's window, across every flight with that limit.

## What to do with this

If something felt odd on a flight, start with the walkthrough [“This flight felt odd”](../walkthroughs/research-odd-flight.md). If you want to see the whole method on a real case, [Reproducing a takeoff investigation](../walkthroughs/research-takeoff.md) repeats the oscillation case step by step on any season of flights.

## How it works

Research runs on the same engine as the rest of the app and reads your logs again to cut slices — the normal analysis keeps only per-flight results — so the first build of a study over a whole workspace takes some seconds, with progress shown; a saved study keeps its measurements and reopens at once. Everything the page does is an operation the command line can also run, so a study is reproducible outside the browser, and a future assistant could drive the same questions.

The design is [Spec 06 — Research](https://github.com/AlchemyGeek/Rotax9iSEIS/blob/main/docs/specs/06-research.md). The case that shaped it is the owner's [takeoff RPM/MAP oscillation investigation](../research/2026-10-takeoff-rpm-oscillation.md).
