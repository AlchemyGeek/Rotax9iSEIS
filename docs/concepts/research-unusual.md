# Which slices are unusual?

<div class="in-brief" markdown>
**In brief.** Take a slice set and let the app measure every slice on many channels at once — level, spread, swing, period, how each channel moves with rpm, how fast it changes — then ask which slices sit far from the rest, and on what. The answer is a short ranked list: *2026-07-17 18:19 stands out on rpm swing (far below the rest) and manifold pressure (flat at its ceiling).* Unusual means **different from your other slices**. It does not mean wrong — and on the oscillation case, the unusual slices were the two healthy ones.
</div>

## The scan you did not know to ask for

The other three questions need a hypothesis: you name the channel, or the pair, or the split. This one needs none. It looks at everything the slices carry and points at the slices that do not fit the others. It is the question to ask when something felt wrong and you cannot say what, and the question to ask routinely of a season of cruises when nothing felt wrong at all.

<figure class="diagram">
--8<-- "diagrams/research-unusual.svg"
<figcaption>Unusual means far from the other slices — here, the two clean high-altitude takeoffs.</figcaption>
</figure>

## What you get back

A ranked, capped list. Each line names a slice, the measurement it stands out on, and which way:

> 2026-07-17 18:19 — rpm swing far below the rest (70 vs 180); manifold pressure flat at 51.4 inHg.
> 2026-07-23 18:12 — rpm swing far below the rest (80 vs 180); manifold pressure flat at 51.5 inHg.

Then the per-slice table with every measurement, and a chart of the measurements that did the separating.

<!-- screenshot: research-unusual-card.png — the unusual-slice result on the full-power set, the two high-altitude takeoffs listed -->

## Different is not wrong

This is the one question whose answer is most easily misread, so the card says it plainly. In the oscillation case 93 of 98 takeoffs cycled; the two that stand out are the two that did not — flown from high-altitude airports where the engine's boost control had reached its ceiling and the loop that caused the cycling had nothing to feed back. The scan found the *exceptions*, which were the correct behaviour. Had the oscillation been rare, the same scan would have found the oscillating takeoffs instead.

So the list is a set of places to look, not a set of problems. Open each in the Flight view and ask why it differs.

## What it does not tell you

- **That a listed slice has a problem**, or that an unlisted one does not.
- **Anything certain from a long list.** With a dozen channels and several measurements each, some slice will stand out on something by chance; the list is ranked and cut short for that reason, and a slice odd on one measurement ranks below one odd on several.
- **Comparisons across log sources.** The G3X and AXIS record some channels differently, so slices are compared only with others from the same source.

## What to do with this

Click the top one or two and look at the flight: the altitude, the weather, what the pilot did. If they share a condition, that condition is your next split in [Are these two groups different?](research-groups.md). If one slice is alone and unexplained, mark it as a hand slice and keep it in the study with a note; it is the kind of thing worth asking a mechanic about with the evidence in hand.

## How it works

For every slice and every default channel the app computes the standard measurements and converts each to a robust z-score — how many spreads it sits from the median of the other slices from the same source. A slice stands out when any measurement passes a threshold; the list is ranked by the largest and capped. Future versions will rank by how *many* measurements a slice stands out on, and within the channels the study's other questions already use, so that a slice odd in two ways ranks above one odd in one; the card will say when that has changed.

Spec 06 §7.4 defines the question and its planned refinement.
