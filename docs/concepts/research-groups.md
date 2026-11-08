# Are these two groups different?

<div class="in-brief" markdown>
**In brief.** Split a slice set in two — before and after a date, two altitude bands, two log sources, two of your own sets — and pick one measurement. The answer says how far apart the two groups sit and how sure that difference is, in the measurement's own units: *Swing is 180 rpm below 3,000 ft and 75 rpm above 6,000 ft (92 vs 2 slices — small group).* It is the question for *did the fix work?*, *does it depend on weather?*, and *was it always like this?*
</div>

## Three uses

**Before and after.** You changed something — an injector, a propeller controller's firmware, a sensor — and want to know whether a behaviour changed with it. Split by date at the change and compare the same measurement on each side. This is the honest form of *it feels better now*.

**By conditions.** Split by density altitude, outside air temperature, or wind. In the oscillation case the swing fell with altitude and vanished above 6,000 ft, where the engine's boost control had reached its ceiling and had nothing left to feed back — the clue that pointed at the mechanism.

**Always or recently.** Split by engine hours or by date into early and late and compare. A behaviour that is the same in both halves is a characteristic, not a development; Trends looks for the opposite.

<!-- diagram: research-two-groups.svg — two distributions of a measurement side by side, their medians marked and the gap between them labelled -->

## What you get back

> Swing is 180 rpm below 3,000 ft DA and 75 rpm above 6,000 ft DA (92 vs 2 slices — small group).

- **The two medians**, in the measurement's units, and the **difference** between them.
- **An effect size** — how completely the two groups separate, from 0 (interleaved) to 1 (no overlap). This, not a probability, is the headline.
- **The counts**, with a caution whenever a group is smaller than the app's usual minimum.

Under it: both groups' distributions side by side, every slice a point; the per-slice table; the caveats.

<!-- screenshot: research-groups-card.png — the two-group result for swing by DA band, small-group caution shown -->

## Why no p-value

Statistical tests on engine logs are easily fooled. Consecutive seconds are not independent, so the usual probability calculations treat a 60-second slice as 60 pieces of evidence when it is closer to a handful; the result would look far more certain than it is. The app therefore reports the *size* of a difference, in units you can picture, and how many slices stand behind each side. A 100-rpm difference between 92 slices and 2 is real on the 92 and a guess on the 2 — and the card says so.

## What it does not tell you

- **Why.** A difference by date may be the change you made, the season, or a new habit. Before-and-after is strongest when the two groups are otherwise alike; the aligned view and the per-slice table let you check.
- **Anything from a tiny group.** Two slices make an observation, not a comparison. The caution is not decoration.
- **That no difference means no change.** A behaviour can change in shape without changing the one measurement you compared.

## What to do with this

For a before-and-after, note the finding in the Journal with the date and what changed; it becomes the record that the change did or did not do what was intended. For a conditions split, read the aligned view with the split applied and look at *where* the two groups differ; then ask [Is it steady, or cycling?](research-cycling.md) on each group separately if the shape, not just the size, seems to differ.

## How it works

The measurement is any per-slice descriptor — swing, period, median level, spread, correlation with a reference channel, maximum rate of change. The two groups come from a split on the study's selection (source, density-altitude band, outside-air-temperature band, date, before/after a chosen date) or from two slice sets. The app reports the median of each group, the median difference, and Cliff's delta as the effect size, with a rank test as supporting evidence only. The small-group caution uses the same minimum as the rest of the app (ten by default).

Spec 06 §7.3 defines the question; [Research questions and parameters](../reference/research-questions.md) lists its parameters.
