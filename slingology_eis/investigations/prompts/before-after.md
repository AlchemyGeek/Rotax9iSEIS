---
name: before-after
title: Before / after
description: Compare the engine before and after a change (a date, or the change in words).
arguments:
  - name: change
    description: The date of the change (YYYY-MM-DD) or the change in words (e.g. "the new propeller")
    required: true
---
Compare my engine before and after this change: {{change}}.

1. Call `guide` first and follow its method.
2. If I gave the change in words, find its date in my notes (`aircraft_get`) or the Journal (`journal_list`);
   if you can't, ask me.
3. Start a notebook with `study_create`, and write the plan under *How this was done* before measuring.
4. For the conditions the change could affect (full power, governed climb, stable cruise), compare the
   slices before and after with `groups` split by date — `eis.groups("full_power", "rpm.swing", by="date",
   date="…")` — for the measurements the change could have moved (for a propeller: rpm, its swing and period,
   MAP, fuel flow; for an oil change: oil temperature and pressure). Say why each measurement was chosen.
5. Each thing that changed or did not is a finding: one sentence with its numbers and the group sizes, and
   its evidence table. The caveats (fewer flights after, different seasons or sources) go in
   `question_scope`. Finish with the structured Answer — `study_finish` with `question_scope`, `shows`,
   `means` and `actions` (or `actions_none`).

The notebook is the record (the guide's *The notebook is the record*): every finding is one sentence and one
evidence cell (`eis.table`, `eis.figure` or a log view, with a caption — never a `print`); the plan and the
method go under *How this was done*; exploring is `scratch`. A quick look to decide where to go next is a probe
and stays in the chat. If we talk on after you finish and it changes what the notebook says — or I say "put
that in the notebook" — open a follow-up (`study_followup`), add its cells, and `study_finish` again with the
Answer rewritten as it now stands and `changed` saying what changed above.
