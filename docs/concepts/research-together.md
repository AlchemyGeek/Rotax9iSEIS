# Do these move together, and who leads?

<div class="in-brief" markdown>
**In brief.** Pick a slice set and two channels. The answer says how closely they rise and fall together and by how many seconds one trails the other: *Manifold pressure follows RPM with no delay; fuel flow follows one second behind.* Moving together is how two signals reveal that they are coupled — by physics, by a controller, or by a sensor. It never says which one causes the other.
</div>

## Why it matters

A wobble in one signal is a symptom. The same wobble in a second signal, at the same instant or a fixed moment later, is a mechanism. In the oscillation case rpm cycled and so did manifold pressure, in lockstep, with fuel flow a second behind — which pointed straight at the loop between the engine's boost control and the propeller governor, and ruled out the governor hunting alone (then manifold pressure would have held still) and the engine computer's speed limiter (then fuel flow would have led, not followed).

<figure class="diagram">
--8<-- "diagrams/research-lag.svg"
<figcaption>Moving together, and who leads: manifold pressure with rpm at lag zero, fuel flow one second behind.</figcaption>
</figure>

## What you get back

> Manifold pressure follows RPM with no delay (median correlation 0.93 on AXIS slices, 0.2 on G3X slices); fuel flow follows 1 s behind.

- **Correlation** — how closely the two rise and fall together within a slice, from 0 (unrelated) to 1 (in step), as a median across slices. A negative value means one rises as the other falls.
- **Lag** — the delay at which the two match best, in seconds; zero means together, positive means the second trails.
- **By source** — stated separately when both log sources are present, because they do not record the same channel the same way.

<!-- screenshot: research-together-card.png — the move-together result for rpm and MAP, with the per-source split -->

## The per-source caveat

That 0.93 against 0.2 is not two different engines; it is two different recorders. The G3X smooths its manifold-pressure channel, so the same oscillation leaves a 2-inHg ripple there and a 5–7-inHg ripple on the AXIS; rpm is recorded identically by both. A correlation read across both sources would be meaningless, so the result never pools them. The caveat names the damped channel.

## What it does not tell you

- **Which one causes the other.** Two signals can move together because a third drives both. The lag is a hint, not a proof.
- **Anything about signals that move slowly.** Over a 30-second takeoff slice, oil temperature and coolant temperature both rise gently; they correlate highly and mean nothing by it. Detrending removes the slow part, but the caveat reminds you to read the chart.
- **Lags beyond the search range.** The range is sized from the period found (a cycle and a half each way) or from the slice length, and is printed on the card; a slow thermal lag of a minute needs long slices.

## What to do with this

Chain it to the previous question. Once a signal cycles, ask whether its natural partners cycle with it: rpm with manifold pressure and fuel flow; fuel pressure with fuel flow; voltage with current. A partner found at zero lag names the loop; a partner that leads names the driver. Put the pair on the aligned view's stack and the chart will show what the number says.

## How it works

Both channels are detrended within each slice, then the correlation is computed at every shift from −L to +L seconds; the value at zero shift and the shift with the highest value are reported. L is set from the dominant period when there is one (±1.5 cycles) or from a tenth of the slice length, floored at ±10 seconds, and shown on the card. Medians across slices; per source. The result states in its caveats what a correlation is not.

Spec 06 §7.2 defines the question; [Research questions and parameters](../reference/research-questions.md) lists its parameters.
