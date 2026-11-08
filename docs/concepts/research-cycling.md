# Is it steady, or cycling?

<div class="in-brief" markdown>
**In brief.** Pick a slice set and one channel. The answer says whether that channel repeats an up-and-down inside the slices, how long one cycle takes (the **period**), how big it is from bottom to top (the **swing**), and in how many of the slices it happens: *RPM cycles every 3.8 s, swing 180 rpm, in 93 of 98 slices.* The swing is shown beside something to compare it with — the Operators Manual limit, the spread across your own slices, or a value you typed in. A repeating shape is a fact about the signal, not a verdict on the engine.
</div>

## The question behind the question

Many engine signals are *supposed* to hold still for a while: rpm under a governor, manifold pressure at a set throttle, fuel flow in cruise, oil pressure once warm. When one of them wobbles rhythmically instead, two control systems are usually arguing — a governor and a boost controller, a regulator and a pump — or something mechanical is loose. The wobble can be well inside every limit and perfectly consistent from the first flight, which is why neither the limit checker nor Trends will show it. Your body may: the oscillation case was first noticed as a fore-aft surge, in calm air, after 145 hours.

<!-- diagram: research-period-swing.svg — an rpm trace with the period marked between two peaks and the swing marked bottom-to-top -->

## What you get back

> RPM cycles every 3.8 s (IQR 3.6–3.9), swing 180 rpm (170–190), in 93 of 98 slices (AXIS 13 of 14, G3X 80 of 84).

- **Period** — seconds per cycle, as a median across the slices with the middle half of them in brackets.
- **Swing** — bottom-to-top within a short window, likewise.
- **Recurrence** — the count of slices in which a clear cycle was found, out of all of them, split by log source when both are present. This number is the one that separates a characteristic of the installation (93 of 98) from a one-off (3 of 98).

Under the sentence: a chart of every slice's swing, by source; the **magnitude** beside its reference; the caveats; and the per-slice table.

<!-- screenshot: research-cycling-card.png — the cycling result for rpm on the full-power set, all five parts -->

## Reading the magnitude

A 180-rpm swing means little on its own. Beside the Operators Manual's 5,800-rpm limit it shows how much headroom the top of the swing leaves. Beside the spread of swing across your own slices it shows whether some slices are different from the rest. Beside a reference you type in — *Airmaster governing band ±100 rpm, from the controller manual* — it becomes a comparison you can make yourself. The app brings only the Operators Manual value; the rest is yours. See [Reading a result](research-results.md).

## What it does not tell you

- **Whether cycling is bad.** A governor hunting ±90 rpm may be a tuning matter for the propeller maker, a known characteristic, or a fault; the question shows the shape and the comparison, not the cause.
- **Cycles faster than about three seconds.** Logs are once a second; anything quicker is unreliable or invisible, and the caveat says so.
- **Why a slice did not cycle.** The five takeoffs that did not, in the case above, were the high-altitude ones — found by asking [Are these two groups different?](research-groups.md), not by this question.

## What to do with this

If the recurrence is high and the swing is large against its reference, you have an evidence package worth sending: the manufacturer of the governing part recognised the oscillation case from one plot and the per-slice table. If the recurrence is low, open the slices that cycled in the Flight view and look at what else was happening. Either way the next question is usually [Do these move together?](research-together.md): a cycle in one signal almost always has a partner.

## How it works

Each slice is detrended, then the dominant period is found from the autocorrelation — how well the signal matches itself shifted by *n* seconds — and cross-checked against a periodogram that tolerates the AXIS's uneven sampling. A period counts as present when its prominence clears a threshold and the two estimates agree; periods under three seconds are never counted. The swing is the median bottom-to-top within a rolling window. That window is not fixed: the app sizes it from the period it just found (two and a half cycles), or from the slice length when there is no period, never shorter than 12 seconds — and prints the value it used on the card. Medians are used throughout because one-second rpm is quantised in steps of ten and has spikes.

Spec 06 §7.0–7.1 and §6 define the method and its parameters; [Research questions and parameters](../reference/research-questions.md) lists them.
