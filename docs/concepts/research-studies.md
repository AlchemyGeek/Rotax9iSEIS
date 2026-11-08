# Studies: saving and sharing

<div class="in-brief" markdown>
**In brief.** A Research session is a **study**: which flights, which slice rules and hand slices, which questions with which settings, your references and your notes. Studies are saved in the workspace and listed on the Research page with their first finding. A study refers to flights by their fingerprint, never by file, so it travels: export it as a `.eisstudy`, and another owner imports it and runs *your* rule on *their* flights. Opened without any of its flights, it shows the sender's results read-only — clearly labelled as theirs — with one button: **Run this on my flights**.
</div>

## What a study holds

Definitions, not data. A study stores:

- the **selection** — all flights, or chosen ones, and any split (by source, altitude band, temperature band, date);
- the **slice rules** (a preset or your edit of one), phase slices, and **hand slices** (a flight and a window);
- the **questions** asked, each with its channels and settings;
- your **references** — label, channel, value, source;
- your **notes**;
- and, for speed, each slice's measurements, so the study reopens instantly.

It does not store the logs or the second-by-second samples. The aligned view reads the slices' flights again when you open it; everything else is already there.

<figure class="diagram">
--8<-- "diagrams/research-study-lifecycle.svg"
<figcaption>A study's life: cut, ask, save, export, import read-only, run on my flights.</figcaption>
</figure>

## Saving

**Save** on the study page writes it into the active workspace. The Research page lists studies by name with their first finding and date; open, rename, delete there. Studies are part of the workspace, so a workspace export carries them along with your decisions.

<!-- screenshot: research-home-studies.png — the Research page listing saved studies with their first findings -->

## Sharing a study

**Export** writes a `.eisstudy` file: the study, its cached measurements, the per-slice table as CSV and a chart image. It is small, and it names flights only by fingerprint — a code derived from each log, meaningless to anyone who does not hold the same log.

Someone who receives it chooses **Import a study** on their Research page. The app matches the study's flights against their workspace:

- **Some flights match** (you shared your logs with them too): the study opens as a normal study over those flights; the ones they lack are listed and simply contribute no slices.
- **None match** (the usual case between two owners): the study opens **read-only**.

## Read-only studies and *Run this on my flights*

A read-only study shows everything the sender saw — findings, charts, tables — under a label that cannot be missed: **Sender's results — none of these flights are in this workspace.** Every control is visible but disabled, so the page reads the same as the sender's; nothing in it is about your engine.

One button is live: **Run this on my flights.** It creates a new study in your workspace with the sender's rules, questions, references and settings, over your own flights, and runs it. Now the same finding sentence is about your engine, and the two can be set side by side.

<!-- screenshot: research-read-only.png — an imported study with the read-only label and the single enabled action -->

This is how a finding spreads without anyone's logs moving: *here is the rule that found the oscillation on my aircraft — run it on yours.* The receiving owner's data never leaves their machine, and the sender's never had to.

## What to do with this

Save a study the moment it says something, even something dull; the measurements are cheap to keep and the comparison next season is free. Before sending one, open it yourself from a fresh workspace to see what the recipient sees. When you receive one, run it on your flights before reading the sender's conclusions too closely.

## How it works

Studies live as documents in the workspace's `studies/` folder and are carried by workspace export like every other decision. The cache of measurements is keyed to each flight's fingerprint and the engine version; if either changes, the affected entries are recomputed, never trusted. Import always creates a new study; a read-only study re-exports the sender's file unchanged. *Run this on my flights* copies the definitions and nothing else.

Spec 06 §10 defines studies, their file and the read-only state.
