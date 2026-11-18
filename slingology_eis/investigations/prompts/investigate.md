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
   question as I asked it.
4. Look at one flight first (a log view of the window, `eis.load`), then across all my flights with a slice
   rule, measuring what the question is about — the guide's table says which instrument fits (a test only
   when the question is about steadiness, coupling, a difference or an outlier; otherwise load, slice, plot
   and look). Each measurement is a notebook cell whose output states the number; a test used for another
   reason says why beside it.
5. Read what my manuals say about it (`documents_list`, `document_read`) and cite the pages.
6. State the mechanism as a hypothesis, name the alternatives you ruled out with the cells that did it, and
   finish with `study_finish`: what was found, what it means, what I should do — with `question` when it was
   one of mine, so it and its marks are resolved.
