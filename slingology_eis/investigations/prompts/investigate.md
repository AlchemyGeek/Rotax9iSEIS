---
name: investigate
title: Investigate
description: Investigate a question about the engine in a notebook, following the EIS method.
arguments:
  - name: question
    description: The question, in your words (e.g. "Is there an oscillation during takeoff and initial climb?"), or the title of one you marked on the Flight view; leave it empty and Claude takes your newest open question
    required: false
---
Investigate this question about my engine with SlingologyEIS:

> {{question}}

Which question: call `guide` first — it lists the questions I marked on the Flight view (*Mark for Claude*).
If the question above is empty, take my newest open question (`pins_list` names it `newest_open`); if I have
none, ask me what to investigate — you may suggest what my open inbox candidates (`inbox_list`) and recent
flights point to — and wait for my answer. If the text above names one of my questions (its title, or near
it), take that one. Otherwise it is a new question in my words.

1. Call `guide` first and follow its method and writing rules.
2. Find the flight or flights the question names with `flights_find` (or `flights_list`), and read
   `aircraft_get` — my notes say what changed and when.
3. Start a notebook with `study_create`: for one of my questions pass its `question_id`, and the notebook opens
   with my marks — my note, then a log view of the window — so start from what I saw; otherwise the
   question as I asked it. Write the plan under *How this was done* (`"section": 5`) before you measure.
4. Look at one flight first (a log view of the window, `eis.load`), then across all my flights with a slice
   rule, measuring what the question is about — the guide's table says which instrument fits (a test only
   when the question is about steadiness, coupling, a difference or an outlier; otherwise load, slice, plot
   and look). Each finding is one sentence and one evidence cell (`eis.table`, `eis.figure`, a log view, each
   with a caption); a test used for another reason says why beside it. Explore in `scratch` cells.
5. Read what my manuals say about it (`documents_list`, `document_read`) and cite the pages. Anything from
   outside my logs and documents (forums, other owners) is context, under *How this was done*, labelled so.
6. State the mechanism as a hypothesis and name the alternatives you ruled out, each with its evidence, under
   *How this was done*.
7. Finish with the structured Answer: `study_finish` with `question_scope` (flights and dates, references, what
   was taken as given, what the logs can't tell), `shows` (3–5 sentences with numbers — the first is my
   Journal's line), `means` (the hypothesis, your confidence, what would change it) and `actions` (what · who ·
   what it would settle; `recheck_after_flights` when EIS can watch it; or `actions_none` and why); `question`
   when it was one of mine, so it and its marks are resolved; `tags`: two or three topic words for what the
   notebook is about (not what it found).

The notebook is the record (the guide's *The notebook is the record*): every finding is one sentence and one
evidence cell (`eis.table`, `eis.figure` or a log view, with a caption — never a `print`); the plan and the
method go under *How this was done*; exploring is `scratch`. A quick look to decide where to go next is a probe
and stays in the chat. If we talk on after you finish and it changes what the notebook says — or I say "put
that in the notebook" — open a follow-up (`study_followup`), add its cells, and `study_finish` again with the
Answer rewritten as it now stands and `changed` saying what changed above.

Finish with the structured Answer.
