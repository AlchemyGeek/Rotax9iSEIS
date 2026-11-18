# Research: the third question

<div class="in-brief" markdown>
**In brief.** The app asks three questions of your engine. *Did a value cross an Operators Manual line?* — that is **Limits and events**. *Has a value been drifting over the months?* — that is **Trends**. **Research** asks the third: *within a flight, does each signal behave the way it should — and does it do so on every flight?* It works one way: **Claude investigates; EIS measures.** You **look** at a flight in EIS with *Signal* on, **mark** what looks odd for Claude, **ask** in Claude Desktop, and **read** the notebook Claude writes back into EIS. EIS never tells you something is wrong; it measures, and keeps the evidence.
</div>

## Three questions, three blind spots

Each question sees what the other two cannot.

<figure class="diagram">
--8<-- "diagrams/research-three-questions.svg"
<figcaption>Three questions, three blind spots: a limit sees level, a trend sees drift, Research sees shape.</figcaption>
</figure>

- A **limit** is a line. A signal that stays under it is invisible to the limit checker, however oddly it moves.
- A **trend** compares your engine with its own past. A behaviour your engine has had since the first flight is, to Trends, normal.
- **Research** looks at the *shape* of a signal within a flight — steady or swinging, leading or lagging, like the other flights or not — and asks the same of every flight you have.

The case that made this page necessary: one aircraft's rpm cycled up and down by about 180 rpm every four seconds on nearly every takeoff, for 145 engine hours. It stayed inside every limit, so no event fired. It never changed, so no trend moved. It was felt once, in calm air, and found by asking Claude to line up every full-power segment of every flight, read the engine's manual, and test what it found. That loop — look, measure, read, hypothesise, eliminate, write up — is what Research is for. Claude does the loop; EIS is the instrument it uses and the record it keeps.

## Look, mark, ask, read

<figure class="diagram">
--8<-- "diagrams/research-investigation-loop.svg"
<figcaption>You look and mark in EIS; you ask in Claude Desktop; Claude works through EIS and writes the notebook.</figcaption>
</figure>

1. **Look.** Open a flight and turn on **Signal** under its chart. Under each channel a strip shows how far it swings, second by second, and where it repeats. Zoom to a stretch and its numbers appear beside their Operators Manual references: the swing, the period, how the other channels move with it.
2. **Mark.** Something looks odd? With the chart zoomed to it, **Mark for Claude**: a sentence of what you see, and the question it belongs to — a new one with a title, one you already have, or none for now. A mark keeps where to look and your note; nothing is measured. Your questions and their marks gather in the **inbox** on the Research page ([Mark something for Claude](../walkthroughs/mark-for-claude.md)).
3. **Ask.** In Claude Desktop, choose the **Investigate** prompt. With no text it takes your newest open question and starts from your marks; or ask in your own words. Claude finds the flights, measures across them, reads your manuals and notes, and steers by what you say ([Investigations](research-investigations.md)).
4. **Read.** The notebook appears on the Research page as Claude writes it: the question, what was seen on one flight, what was measured across the flights with its numbers and references, the hypothesis and the alternatives ruled out, and what it means for you. Keep it, re-run it next season, export it, share it ([Notebooks you keep and share](research-studies.md)).

Asking needs the EIS extension in Claude Desktop, on your computer. On the website you can look, mark and read; your questions wait in the inbox, and the page says how to hand them to Claude.

## What EIS measures

Claude chooses what to measure; the numbers are EIS's. The instrument cuts flights into **slices** — every takeoff, every climb, the window you marked — measures each one (level, spread, swing, period, how channels move together), and answers four kinds of question with a count and a reference beside every number: *is it steady?*, *do these move together?*, *are these groups different?*, *which flights stand out?* Claude uses those when the question is one of them, and writes its own code against your logs when it is not. [What EIS measures](../reference/what-eis-measures.md) is the fine print.

## The inbox

You don't have to notice something to start. When the Research page opens after new flights, EIS runs its own scan — no AI — over the recent flights and keeps only patterns that hold across many of them. Those wait in the inbox beside your own questions, with the same statuses: *new*, *investigating*, *nothing here*, *watching*, *acted on*.

## What Research does not do

It brings no rules of its own. The only numbers the app contributes are Operators Manual values already in your engine profile; everything else is measured from your own flights or named with its source. It declares nothing *abnormal*, *faulty* or *detected*. It changes nothing elsewhere in the app until you take a finding somewhere — into the Journal, or to the person who can act on it ([From a finding to action](research-action.md)).

A repeating shape in a signal may be a problem, a characteristic of the installation, or nothing. Research gives you the evidence to ask the right person; it does not pretend to be that person.

## How it works

Everything Research does is an operation of the EIS engine, the same on the website and on your computer; Claude reaches the same operations as tools through the extension, so a number in a notebook is the number the page would show. Cutting slices reads the logs again — the normal analysis keeps only per-flight results — so a first measurement over a whole workspace takes some seconds.

The instrument is [Spec 06 — Research](https://github.com/AlchemyGeek/Rotax9iSEIS/blob/main/docs/specs/06-research.md); investigations, marks and the inbox are [Spec 16 — Investigations](https://github.com/AlchemyGeek/Rotax9iSEIS/blob/main/docs/specs/16-investigations.md). The case that shaped both is the owner's [takeoff RPM/MAP oscillation investigation](../research/2026-10-takeoff-rpm-oscillation.md).
