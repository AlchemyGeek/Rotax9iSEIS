# Research: the third question

<div class="in-brief" markdown>
**In brief.** The app asks three questions of your engine. *Did a value cross an Operators Manual line?* — that is **Limits and events**. *Has a value been drifting over the months?* — that is **Trends**. **Research** asks the third: *within a flight, does each signal behave the way it should — and does it do so on every flight?* Research is an **instrument**: pieces of flights, measurements, four plain questions, and studies that keep the evidence. You can work the instrument by hand on this website. With the Claude Desktop extension, your own Claude works it for you — you ask about a flight in words, and the investigation appears in EIS as a notebook. Either way Research never tells you something is wrong; it shows what the data does and leaves the judgement to you.
</div>

## Three questions, three blind spots

Each question sees what the other two cannot.

<figure class="diagram">
--8<-- "diagrams/research-three-questions.svg"
<figcaption>Three questions, three blind spots: a limit sees level, a trend sees drift, Research sees shape.</figcaption>
</figure>

- A **limit** is a line. A signal that stays under it is invisible to the limit checker, however oddly it moves.
- A **trend** compares your engine with its own past. A behaviour your engine has had since the first flight is, to Trends, normal.
- **Research** looks at the *shape* of a signal within a flight — steady or cycling, leading or lagging, like the others or not — and asks the same of every flight you have.

The case that made this page necessary: one aircraft's rpm cycled up and down by about 180 rpm every four seconds on nearly every takeoff, for 145 engine hours. It stayed inside every limit, so no event fired. It never changed, so no trend moved. A test pilot, an instructor and the owner all flew behind it without noticing; it was felt once, in calm air, and found by asking Claude to line up every full-power segment of every flight, look at them together, read the engine's manual, and test what it found. That loop — look, measure, read, hypothesise, eliminate, write up — is what Research is for. The app is the instrument the loop uses; the investigator is you, or your Claude.

## Two ways to use it

**By hand, on this website.** Choose a preset, see the slices lined up, ask one of the four questions, read the result, save the study. No install, nothing leaves your browser. The pages below describe the instrument.

**With Claude, through the Desktop extension.** Install the EIS extension in Claude Desktop — one step, and it also runs the EIS pages on your computer. Then ask Claude about your engine in words. Claude works the same instrument through its tools, writes code against your logs where no tool fits, reads the manuals you give it, and writes the investigation into EIS as a **notebook** — narrative, code, figures, tables — that you can reopen, re-run and share. An **inbox** on the Research page collects patterns that recur across your recent flights, found by the app without any AI, for Claude to look into when you ask or on a schedule you set. See [Investigations](research-investigations.md).

## What the instrument is made of

Six ideas, each with its own page. Research works at three levels: one flight (**Signal**), every flight (**Compare**), and the set as a whole (**Questions**).

| Idea | In one line | Page |
|---|---|---|
| **Slice** | A piece of one flight — all takeoffs, all climbs, or one window you mark — and the unit everything else works on | [Slices: pieces of flights](research-slices.md) |
| **Aligned view** | Many slices on one time axis, lined up at the moment that matters, so your eye can compare them | [Seeing slices together](research-aligned-view.md) |
| **Signal view** | One flight with a swing strip and a period strip under each channel: where it swings and repeats, a window's numbers, and *Make this a rule* | [Signal view: one flight, looked at closely](research-signal.md) |
| **Compare** | The same measurement on every flight, one row per slice grouped by flight, a pinned reference row, and a chart against conditions | [Compare: the same moment on every flight](research-compare.md) |
| **Question** | One of four things you can ask of a set of slices, phrased as you would ask it | [Is it steady, or cycling?](research-cycling.md) · [Do these move together?](research-together.md) · [Are these two groups different?](research-groups.md) · [Which slices are unusual?](research-unusual.md) |
| **Study** | Your selection, slices, questions, references and notes, saved and shareable | [Studies: saving and sharing](research-studies.md) |

Every answer comes in the same shape — [Reading a result](research-results.md) — and every answer has somewhere to go afterwards — [From a finding to action](research-action.md). Studies, hand-made or Claude-made, are [notebooks you keep and share](research-studies.md).

<!-- screenshot: research-home.png — the Research page: presets with their questions, saved studies with their first finding -->

## What Research does not do

It brings no rules of its own. The only numbers the app contributes to a result are Operators Manual values already in your engine profile; everything else is measured from your own flights or typed in by you, with its source. It declares nothing *abnormal*, *faulty* or *detected*. It changes nothing elsewhere in the app until you take a finding somewhere — into the Journal, into an evidence package, or to another owner.

That restraint is deliberate. A repeating shape in a signal may be a problem, a characteristic of the installation, or nothing. Research gives you the evidence to ask the right person; it does not pretend to be that person.

## Getting there

From **Research** in the top bar, or from the thing that made you wonder:

- *Research this window* on a flight's chart — the study opens in Signal view on that flight, with the window you were zoomed into;
- *Research this* on a Trends card that shows a change — a study split into before and after;
- *Research this* on a row of the Events table — the event's window, across every flight with that limit.

## What to do with this

If something felt odd on a flight and you have the Desktop extension, ask Claude about it — that is the whole method. On the website, [Reproducing a takeoff investigation](../walkthroughs/research-takeoff.md) shows the instrument worked by hand on the real case.

## How it works

Research runs on the same engine as the rest of the app and reads your logs again to cut slices — the normal analysis keeps only per-flight results — so the first build of a study over a whole workspace takes some seconds, with progress shown; a saved study keeps its measurements and reopens at once. Everything the page does is an operation that the command line can run and that Claude can call as a tool: the website and the investigator use one instrument.

The instrument is [Spec 06 — Research](https://github.com/AlchemyGeek/Rotax9iSEIS/blob/main/docs/specs/06-research.md); investigations are [Spec 16 — Investigations](https://github.com/AlchemyGeek/Rotax9iSEIS/blob/main/docs/specs/16-investigations.md). The case that shaped both is the owner's [takeoff RPM/MAP oscillation investigation](../research/2026-10-takeoff-rpm-oscillation.md).
