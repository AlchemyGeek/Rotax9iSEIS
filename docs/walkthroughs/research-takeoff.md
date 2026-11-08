# Reproducing a takeoff investigation

*Twenty minutes. This repeats, inside the app, the investigation that found a 180-rpm, four-second cycle on nearly every takeoff of one aircraft — a behaviour that lived inside every limit and never changed, so neither the Flight view nor Trends could have shown it. Any workspace with a season of flights will do; the numbers below are the original aircraft's (60 flights, April to October), and the sample workspace reproduces them exactly. The original write-up is [here](../research/2026-10-takeoff-rpm-oscillation.md).*

## What you will do

Cut every takeoff out of every flight, line them up, and ask four questions: is rpm steady, does manifold pressure move with it, does it depend on altitude, and which takeoffs are unlike the rest. Then take the finding somewhere.

## 1. Open Research

**Research** in the top bar. If this is your first visit the page shows the five presets, each with the question it was made for, and nothing else.

<!-- screenshot: wt-takeoff-01-home.png — the Research page before any study exists -->

## 2. Start from the full-power preset

Under *Start from a preset*, choose **Full-power segment** — *rpm at or above 5,550 for at least 15 seconds, gaps under 3 s bridged*. A new study opens over all your flights with that rule in place, and the slice count fills in while the logs are read, with a progress bar:

> 98 slices from 59 of 60 flights (84 G3X, 14 AXIS)

Why 98 from 60? Touch-and-go sessions: one flight contributed nine takeoffs. The one flight without a slice never reached full power.

<!-- screenshot: wt-takeoff-02-slices.png — the study page with the rule, the slice count and the slice list -->

## 3. Look before you ask

The **Aligned view** draws every slice from the moment rpm passed 5,550 — *Align on: crossing* — so takeoffs coincide whatever the ground roll before them. With 98 slices it shows small multiples; set **Channels** to rpm and manifold pressure and move the cursor. In nearly every panel the two traces rise and fall together, about every four seconds. You have seen the finding; the questions put numbers on it.

<!-- screenshot: wt-takeoff-03-aligned.png — small multiples of the full-power set, rpm and MAP stacked -->

## 4. Is rpm steady?

The preset study already carries **Is this signal steady, or is it cycling?** on RPM. Press **Run**.

> RPM cycles every 3.8 s (IQR 3.6–3.9), swing 180 rpm (170–190), in 93 of 98 slices (AXIS 13 of 14, G3X 80 of 84).

Read the count first: 93 of 98 is a characteristic, not an incident. Below the sentence: every slice's swing by log source; the magnitude beside the Operators Manual's rpm limit, drawn on the chart; and the caveats, including the window the app chose (12 s — the floor for once-a-second logs) and the reminder that a repeating shape is not a judgement.

<!-- screenshot: wt-takeoff-04-cycling.png — the cycling result in its five parts -->

## 5. Open the table

*Show the per-slice table*: all 98 slices with duration, density altitude, OAT, engine hours, phases, source, swing, period and prominence. Sort by swing. **Download CSV** keeps it — this table is what the propeller manufacturer worked from.

## 6. Add a reference

In **Your references**, add one — label *Airmaster governing band*, channel RPM, kind band, value 100, source *AP3/4/5 Operator's Manual V5-1A*. **Save**, then **Run** again. The magnitude now also reads against ±100 rpm, and a 180-rpm swing beside a ±100-rpm band is a comparison you can make yourself. The app brought the Operators Manual line; you brought the 100.

## 7. Who leads?

**Add a question** → **Do these two move together, and who leads?** — channel RPM, compare with manifold pressure. Add fuel flow as a second comparison. **Run**.

> Manifold pressure follows RPM with no delay (median correlation 0.93 on AXIS slices, 0.2 on G3X slices); fuel flow follows 1 s behind.

The split by source is the recorder, not the engine: the caveat explains that the G3X damps its manifold-pressure channel. The lockstep points at a loop between the engine's boost control and the propeller governor, and the one-second fuel-flow lag says fuel is following, not leading — which rules out the engine computer's speed limiter.

<!-- screenshot: wt-takeoff-05-together.png — the move-together result with the per-source split -->

## 8. Does it depend on altitude?

In the selection, set **Split by** → *DA band* with **Band edges** `3500, 6000`. **Add a question** → **Are these two groups different?** on the descriptor *rpm swing*. **Run**.

> Swing is 180 rpm below 3,500 ft DA, 130 rpm at 3,500–6,000 ft and 75 rpm at 6,000 ft and above (92 / 4 / 2 slices — small groups).

Two slices is a small group and the card says so. It was still the decisive clue: at high density altitude the boost control sits at its ceiling and has nothing left to feed back, and the cycle fades.

<!-- screenshot: wt-takeoff-06-groups.png — the two-group result by DA band with the small-group caution -->

## 9. Which takeoffs are unlike the rest?

**Add a question** → **Which of these slices is unusual?** **Run**. The two slices listed as standing out on rpm swing are the two *clean* high-altitude takeoffs. On this aircraft the oscillation was the norm; *unusual* means different, not wrong. Click one to open it in the Flight view and see where it was flown.

<!-- screenshot: wt-takeoff-07-unusual.png — the unusual-slice list with the two high-altitude takeoffs -->

## 10. Save

Give the study a name — *Takeoff rpm oscillation* — and **Save**. It appears on the Research page with its first finding, and reopens instantly.

## 11. Take it somewhere

- **Note this finding in the Journal** on the first question: a *Research finding* entry with the sentence and a link back.
- **Evidence package**: findings, magnitudes, caveats and the per-slice tables in one file — what the manufacturer needed to recognise the behaviour from one email.
- **Export .eisstudy**: the rule and the questions for another owner of the same engine. Imported without your flights it opens read-only with *Run this on my flights* — see [Sharing a study](research-sharing.md).

<!-- screenshot: wt-takeoff-08-journal.png — the Research finding entry in the Journal -->

## What happened next

The owner sent the plot and the table to the propeller controller's manufacturer, who recognised a known behaviour of that controller with this engine and offered a firmware update. The same study will be the before/after test: once the update is flown, set **Split by** → *date* at the update and ask the groups question on rpm swing again — see [Are these two groups different?](../concepts/research-groups.md). A walkthrough for that comparison follows once the update has been flown.

## Where to go next

- [Research: the third question](../concepts/research.md) — why neither Limits nor Trends could see this.
- [Reading a result](../concepts/research-results.md) — the five parts, and why there is no verdict.
- [From a finding to action](../concepts/research-action.md) — writing to a manufacturer.
