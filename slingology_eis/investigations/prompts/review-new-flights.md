---
name: review-new-flights
title: Review new flights
description: A short review of the flights since the last study finding, the inbox, and anything that stands out.
arguments: []
---
Review my new flights.

1. Call `guide` first.
2. Find the flights since my last study finding (`journal_list` shows the study findings; `flights_list` with
   `date_from`), and read the inbox (`inbox_list`) and the questions I marked (`pins_list`).
3. Start a short notebook with `study_create` ("Review of flights since …").
4. For each new flight: one line on where it went and anything that stands out (events, Trends shifts, and
   `eis.unusual` — this review is about what stands out). For each open inbox candidate and each open
   question of mine: what it is, and whether it needs a closer look (*Investigate* takes a question).
5. Finish with the structured Answer, briefly: `shows` — what stands out; `means` — what needs a closer look
   and what doesn't; `actions` — each closer look as *what · who · what it would settle*, or `actions_none`.

The notebook is the record (the guide's *The notebook is the record*): every finding is one sentence and one
evidence cell (`eis.table`, `eis.figure` or a log view, with a caption — never a `print`); the plan and the
method go under *How this was done*; exploring is `scratch`. A quick look to decide where to go next is a probe
and stays in the chat. If we talk on after you finish and it changes what the notebook says — or I say "put
that in the notebook" — open a follow-up (`study_followup`), add its cells, and `study_finish` again with the
Answer rewritten as it now stands and `changed` saying what changed above.
