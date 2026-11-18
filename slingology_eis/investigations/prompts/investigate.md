---
name: investigate
title: Investigate
description: Investigate a question about the engine in a notebook, following the EIS method.
arguments:
  - name: question
    description: The question, in your words (e.g. "Is there an oscillation during takeoff and initial climb?"); leave it empty and Claude asks
    required: false
---
Investigate this question about my engine with SlingologyEIS:

> {{question}}

If the question above is empty, I haven't given one yet: call `guide` first, then ask me what to investigate —
you may suggest what my open inbox candidates (`inbox_list`) and recent flights point to — and wait for my
answer before going on.

1. Call `guide` first and follow its method and writing rules.
2. Find the flight or flights the question names with `flights_find` (or `flights_list`), and read
   `aircraft_get` — my notes say what changed and when.
3. Start a notebook with `study_create`, the question as I asked it.
4. Look at one flight first (a log view of the window, `signal_analyze`), then across all my flights with a
   slice rule and the questions (`eis.cycling`, `eis.coupling`, `eis.groups`, `eis.unusual`), each as a
   notebook cell whose output states the number.
5. Read what my manuals say about it (`documents_list`, `document_read`) and cite the pages.
6. State the mechanism as a hypothesis, name the alternatives you ruled out with the cells that did it, and
   finish with `study_finish`: what was found, what it means, what I should do.
