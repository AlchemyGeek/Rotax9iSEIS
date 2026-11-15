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
3. Start a notebook with `study_create`, passing `inbox_candidate: "{{candidate_id}}"`.
4. Look at one of its slices in one flight (a log view), then measure across the flights (the same preset,
   the same measurement) and check the obvious alternatives: one log source only, one flight only, the 1 Hz
   sampling floor, altitude or temperature.
5. Finish with `study_finish`, resolving the candidate (`resolution`: nothing-here, watch or acted) with a
   one-line note saying why.
