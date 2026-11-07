# Reproducing a takeoff investigation

*Fifteen minutes. This repeats, inside the app, the investigation that found a 180-rpm, four-second cycle on nearly every takeoff of one aircraft — a behaviour that lived inside every limit and never changed, so neither the Flight view nor Trends could have shown it. Any workspace with a season of flights will do; the numbers below are the original aircraft's.*

## 1. Start from the full-power preset

Open **Research** in the top bar. Under *Start from a preset*, choose **Full-power segment** — *rpm at or above 5,550 for at least 15 seconds*. A new study opens with that rule over all your flights, and the slice count fills in as the logs are read:

> 98 slices from 59 of 60 flights (84 G3X, 14 AXIS)

The aligned view below draws the slices on one time axis, each starting at the moment its rule became true — the instant rpm passed 5,550 — so takeoffs line up whatever the ground roll before them. With more than ten slices the view shows one small panel per slice; the cursor reads every panel at the same moment.

<!-- screenshot: research-slices.png — the study page with the slice count and the aligned view -->

## 2. Ask whether rpm is steady

The preset study already carries the first question, **Is this signal steady, or is it cycling?**, on RPM. Press **Run**. The result reads:

> RPM cycles every 3.8 s (IQR 3.6–3.9), swing 180 rpm (170–190), in 93 of 98 slices (AXIS 13 of 14, G3X 80 of 84).

Under it: the swing of every slice plotted by log source; the magnitude beside the Operators Manual's 5,800-rpm limit, showing how much headroom the top of the swing leaves; and the caveats — including the window the app chose (12 s, the floor for one-second logs) and the reminder that a repeating shape is not by itself a judgement of the engine. *Show the per-slice table* lists all 98 with duration, density altitude, OAT, engine hours, phases, swing, period and prominence; **Download CSV** keeps it.

<!-- screenshot: research-result.png — the cycling result in its five parts -->

## 3. Add a reference

In *Your references*, add one: label *Airmaster governing band*, channel RPM, ±100 rpm, source *AP3/4/5 Operator's Manual V5-1A*. Save and run again: the magnitude now reads beside that band as well, and a 180-rpm swing against a ±100-rpm band is a comparison you can make yourself.

## 4. Ask who leads

Add the question **Do these two move together, and who leads?** with RPM and manifold pressure, then fuel flow. Run.

> Manifold pressure follows RPM with no delay (median correlation 0.93 on AXIS slices, 0.2 on G3X slices); fuel flow follows 1 s behind.

The caveat explains the split by source: the G3X damps its manifold-pressure channel, so the same oscillation shows 2 inHg of ripple there and 5–7 on the AXIS. The result says what a correlation does not: which one causes the other.

## 5. Does it depend on altitude?

Set the selection's split to **density-altitude band** with edges at 3,500 and 6,000 ft, add **Are these two groups different?** on *rpm swing*, run:

> Swing is 180 rpm below 3,500 ft DA, 130 rpm at 3,500–6,000 ft and 75 rpm at 6,000 ft and above (92 / 4 / 2 slices — small groups).

Two slices is a small group and the result says so; it is still the clue that mattered — at high density altitude the boost control sits at its ceiling and the cycle disappears.

## 6. Which slices are unusual?

Add **Which of these slices is unusual?** and run. The two slices that stand out on rpm swing are the two *clean* high-altitude takeoffs: on this aircraft the oscillation was the norm, and *unusual* means different, not wrong. Read it that way.

## 7. Take it somewhere

- **Note this finding in the Journal** on the first question: a *Research finding* entry appears in the Journal with a link back to the study.
- **Evidence package** downloads the findings, magnitudes, caveats and the per-slice table in one file — the material the propeller manufacturer needed to recognise the behaviour.
- **Export .eisstudy** gives another owner of the same engine the rule and the questions; imported without your flights it opens read-only with *Run this on my flights*.

## Where to go next

The same study is the before/after test once something changes — a firmware update, a new propeller: split the selection *before / after a date* and ask the groups question again on rpm swing.

The design and its reasoning are in [Spec 06 — Research](https://github.com/AlchemyGeek/Rotax9iSEIS/blob/main/docs/specs/06-research.md); the original investigation is in the repository under `docs/research/`.
