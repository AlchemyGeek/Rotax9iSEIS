# Reading a result

<div class="in-brief" markdown>
**In brief.** Every Research answer has the same five parts in the same order: a one-sentence **finding** with a count in it; the **evidence** — a chart, and the table of every slice one click away; the **magnitude**, always beside a **reference** you can see; the **caveats**, including the exact settings the app used; and the saved **details** for next time. No part is a verdict. If you can read a finding and check it against the chart and the table, you have read the result.
</div>

## The five parts

<figure class="diagram">
--8<-- "diagrams/research-result-anatomy.svg"
<figcaption>The five parts of every result.</figcaption>
</figure>

**1. Finding.** One sentence, in plain words, always with a recurrence count and, where both log sources are present, a per-source split:

> RPM cycles every 3.8 s (IQR 3.6–3.9), swing 180 rpm (170–190), in 93 of 98 slices (AXIS 13 of 14, G3X 80 of 84).

The count is the part to read first. *In 93 of 98* is a characteristic; *in 4 of 98* is four flights to look at.

**2. Evidence.** The chart that fits the question — aligned slices, a distribution, two groups side by side — and, behind *Show the per-slice table*, every slice with its measurements and the conditions it flew in: duration, density altitude, outside air temperature, engine hours, phases, source. **Download CSV** keeps the table. This table is what a manufacturer or mechanic can work from; it is the heart of the evidence package.

<!-- screenshot: research-per-slice-table.png — the per-slice table open under a result -->

**3. Magnitude, beside its reference.** The size of what was found never stands alone. It appears next to one or more of:

| Reference | Where it comes from | Example |
|---|---|---|
| **Operators Manual value** | your engine profile — the only number the app brings | the 5,800-rpm limit, as headroom above the top of the swing |
| **Your own slices** | the spread of the same measurement across the set | this slice's swing against the middle half of all slices |
| **A value you typed in** | your study, with a label and a source | *Airmaster governing band ±100 rpm — AP3/4/5 manual* |

A number beside a reference is a comparison you can make; a number alone is a decoration.

**4. Caveats.** Fixed items — the once-a-second sampling floor, differences between log sources, group sizes — plus the one sentence each question carries about what its answer does not mean (*a correlation does not say which one causes the other*). Also here: the **settings the app chose for this run**, such as the 12-second swing window and the ±10-second lag range, and what it chose them from. If you override them, the card says so.

**5. Details.** The machine-readable block the study saves: the question, its settings, the slice definition, every slice's measurements, the references used, and the engine version. It is what reopens instantly and what travels in a shared study.

## Why there is no verdict

The app ships no thresholds of its own beyond the Operators Manual. Anything else — *this swing is too large*, *this lag is suspicious* — would be a rule the app invented, and the app's principle is that the Manual is the only pre-set rule and the rest of the judgement is the pilot's. So a result says what the signal did, how big, how often, and compared with what; the words *abnormal*, *fault* and *detected* do not appear, and a test over the app's own text keeps it that way.

That is not timidity. A repeating rpm shape can be a propeller controller needing a firmware update, a known characteristic of an engine-and-governor pairing, or a sensor; the right person to say which is not a web page. The result gives you what that person needs.

## What to do with this

Read the count, look at the chart, open the table. If the magnitude is large against its reference and the count is high, go to [From a finding to action](research-action.md). If the count is low, open the few slices in the Flight view. If a caveat names your situation — a damped channel, a small group — believe it before the number.

## How it works

Measurements are robust: medians and median absolute deviations rather than means and standard deviations, because one-second engine data is quantised and spiky. Windows and lag ranges are proposed from the data (the period first, then the window from it, with a floor set by the sampling rate) and recorded in the block. References are resolved at run time: the OM value from the active profile, the set spread from the slices in the run, the user's references from the study. The block is stable across sessions and versions of the page, so a study made today reads the same next year.

Spec 06 §8 defines the result contract; §7.0 the window rule.
