# From a finding to action

<div class="in-brief" markdown>
**In brief.** A finding changes nothing by itself. It leaves Research only when you take it somewhere: into the **Journal**, as a dated record; into an **evidence package**, the one file a mechanic or manufacturer needs; or to another owner, as a shared study. What you then *do* about it — fly differently, call someone, change a part, nothing — is a decision between you, the Operators Manual and the people who built the parts. This page is about getting the finding to those people in a form they can act on.
</div>

## The question a finding raises

*So what do I do with this?* was the question that shaped Research. A pilot who is handed *RPM cycles every 3.8 s in 93 of 98 takeoffs* and nothing else has been given a worry, not help. A finding is useful when it comes with its evidence, in a form that lets the right person recognise it. In the oscillation case the right person was the propeller controller's manufacturer, who identified a known behaviour from one email containing a plot and the per-takeoff table, and offered a firmware update the same day. The owner had spent an evening with scripts to produce that table. Research produces it in a click.

<figure class="diagram">
--8<-- "diagrams/research-paths-out.svg"
<figcaption>Where a finding goes: the Journal, an evidence package, a shared study — and, in time, a shared detector.</figcaption>
</figure>

## Three ways out

**Note in Journal.** The finding sentence, verbatim, becomes a *Research finding* entry in the Journal with a link back to the study and room for your note. The Journal is the record of what you decided and why; a finding that led to a call, a change or a deliberate decision to do nothing belongs there with the date. Remove the entry later and the study is untouched.

<!-- screenshot: research-journal-entry.png — a Research finding entry in the Journal, linking back to its study -->

**Evidence package.** One file, downloaded from the study page, holding for each question: the finding, the magnitude beside its reference, the caveats, and the full per-slice table. It is written so that someone who has never seen the app can read it — a mechanic at the annual, the engine or propeller manufacturer's support desk, a type-club forum. Send it with the aligned-view chart and two sentences of your own: what you felt, and what you would like them to look at.

<!-- screenshot: research-evidence-package.png — the evidence package opened, finding and table visible -->

**Share the study.** Another owner of the same engine imports your `.eisstudy` and runs your rule on their flights ([Studies: saving and sharing](research-studies.md)). Two aircraft showing the same shape is a different conversation with a manufacturer from one.

## What a finding is not

It is not an airworthiness judgement, and Research does not make one. Whether a repeating rpm shape is acceptable for flight is answered by the Operators Manual's limits (which the app checks separately, under Limits and events), by the manufacturers of the engine and the governing parts, and by you. In the oscillation case the limits were respected throughout, the manufacturer confirmed a known behaviour with a fix, and the owner chose an interim operating practice until the fix was applied — a decision made with the Manual open, not with Research.

## Writing to a manufacturer

The evidence package answers the questions a support engineer will ask first. Add what it cannot know:

- the installation — engine, propeller and controller models and serials, firmware versions, the avionics that wrote the logs;
- what you observed in the aircraft, when, and in what conditions;
- what you have already ruled out, and how (the two-group question by altitude; the aligned view showing the shape identical in April and October);
- the one question you want answered.

Keep the finding sentence as the app wrote it; its count is the most persuasive thing in the message.

## What comes next, in time

A finding that recurs on several aircraft is a candidate for the app to watch for routinely. The path is a proposal through the topic register, with the study as its evidence; and, further off, a shared **detector** — the study's rule and measurement packaged with its author's explanation of what the pattern may mean and what to do, installed by owners who want it. The app will never ship such detectors itself; they will be the work of people who understood a finding well enough to write that explanation. Until then, the Journal and the evidence package are the ways out, and they are the ones a manufacturer can act on today.

## What to do with this

Note it in the Journal before you do anything else, so the date is kept. If the finding is large against its reference and recurs, build the evidence package and send it, with the installation details above, to whoever made the part the finding points at. If it is small or rare, keep the study and ask again in a season.

## How it works

The Journal entry is a `Research finding` record carrying the finding text and the study's identity; one per study and question. The evidence package is a Markdown file with the per-slice table embedded as CSV, readable in any text editor. Studies travel as described on their own page. None of these actions changes any analysis, trend or event elsewhere in the app.

Spec 06 §10.3 defines the paths out; §14.3 the future detectors.
