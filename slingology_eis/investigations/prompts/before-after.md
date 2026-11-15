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
3. Start a notebook with `study_create`.
4. For the conditions that matter (full power, governed climb, stable cruise), compare the slices before and
   after with `groups` split by date — `eis.groups("full_power", "rpm.swing", by="date", date="…")` — and the
   other measurements that could have changed (rpm period, MAP, fuel flow).
5. Say what changed and what did not, each with its numbers and the group sizes, and the caveats (fewer
   flights after, different seasons or sources). Finish with `study_finish`.
