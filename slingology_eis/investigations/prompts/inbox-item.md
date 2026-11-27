---
name: inbox-item
title: Look at this inbox item
description: Investigate one candidate the EIS detectors raised and resolve it.
arguments:
  - name: candidate_id
    description: The inbox candidate's id (inbox_list shows them)
    required: true
---
Look at inbox candidate {{candidate_id}} for me.

1. Call `guide` first and follow its method.
2. Read the candidate with `inbox_list`: its preset, measurement, the slices involved and the evidence.
3. Start a notebook with `study_create`, passing `inbox_candidate: "{{candidate_id}}"`, and write the plan
   under *How this was done*.
4. Look at one of its slices in one flight (a log view), then measure across the flights what the candidate
   raised (the same preset, the same measurement — the guide's table names its instrument) and check the
   alternatives that fit it: one log source only, one flight only, the 1 Hz sampling floor for a period,
   altitude or temperature.
5. Finish with the structured Answer — `study_finish` with `question_scope`, `shows`, `means`, `actions` (or
   `actions_none`) — resolving the candidate (`resolution`: nothing-here, watch or acted) with a one-line
   note saying why.

The notebook is the record (the guide's *The notebook is the record*): every finding is one sentence and one
evidence cell (`eis.table`, `eis.figure` or a log view, with a caption — never a `print`); the plan and the
method go under *How this was done*; exploring is `scratch`. A quick look to decide where to go next is a probe
and stays in the chat. If we talk on after you finish and it changes what the notebook says — or I say "put
that in the notebook" — open a follow-up (`study_followup`), add its cells, and `study_finish` again with the
Answer rewritten as it now stands and `changed` saying what changed above.
