# Slices: pieces of flights

<div class="in-brief" markdown>
**In brief.** Research never looks at a whole flight. It looks at **slices** — stretches of a flight cut out by a rule (*rpm at or above 5,550 for at least 15 seconds*), by a phase (every climb), or by hand (the window you are looking at). A rule applied to all your flights gives a **slice set** — ninety-odd takeoffs, say — and every question in Research is asked of a set. A slice carries every channel the log recorded, so you decide what to look at when you ask, not when you cut.
</div>

## Why pieces, not flights

A flight is too big a thing to compare. Two flights differ in length, route, weather and what the pilot did; a question like *is rpm steady?* has no answer over a whole flight because rpm is meant to change. Ask it of *the thirty seconds after full power is applied* and it has one — and the same thirty seconds exist on every flight, so the question can be asked ninety times and the answers compared.

That is the whole idea. The oscillation case was found by cutting *every stretch of every flight where rpm sat at or above 5,550 for at least 15 seconds* — 98 slices from 60 flights — and looking at them side by side. The slice is what made ninety takeoffs comparable.

<figure class="diagram">
--8<-- "diagrams/research-slice-anatomy.svg"
<figcaption>A slice: a window of one flight carrying every channel and its context.</figcaption>
</figure>

## Three ways to cut

All three produce the same thing.

**By rule.** A rule says what must be true, for how long, and how to treat brief interruptions:

| Part | Meaning | The full-power preset |
|---|---|---|
| Conditions | One or more channels compared with a value; all must hold | rpm ≥ 5,550 |
| Minimum duration | The conditions must hold at least this long | 15 s |
| Merge gap | A dip shorter than this does not split a slice in two | 3 s |
| Phase | Optionally, only within a phase the app already identifies | — |
| Pad | Optionally, seconds added before and after, so you see the onset | 0 |

Rules are built in a small form — channel, comparison, value, duration — and the slice count updates as you edit. The app ships five as **presets**, each measured against a real season of logs so that it gives about one slice per flight that contains the manoeuvre:

| Preset | Rule | What it isolates |
|---|---|---|
| **Full-power segment** | rpm ≥ 5,550 · ≥ 15 s · merge 3 s | Takeoff and go-around power |
| **Governed climb** | rpm 5,300–5,500 · vertical speed ≥ 300 fpm · ≥ 60 s · merge 5 s | Climb under the propeller governor |
| **Stable cruise** | within cruise · rpm 4,800–5,300 · ≥ 300 s · merge 5 s | The steady stretches of a cruise |
| **Idle** | within taxi · rpm < 2,200 · ≥ 30 s · merge 3 s | Idle quality, taxi out and in |
| **Warm-up** | on the ground · rpm ≥ 1,000 · oil below the takeoff minimum · ≥ 60 s | From start until the oil is warm |

The rpm bands are the 916iS's; other engine profiles carry the same values marked *unverified*. Any preset can be copied and edited; the copy becomes a rule of your workspace. The measured counts behind each preset are in [Research presets](../reference/research-presets.md).

**By phase.** Every climb, every takeoff roll, every cruise, exactly as the app labels them in the Flight view. A phase is a rule with no conditions.

**By hand.** On a flight's chart, zoom to the window that interests you and choose *Research this window*. That window, on that flight, becomes a slice — usually to set beside a rule-built set: *this* takeoff against all takeoffs.

<!-- screenshot: research-rule-editor.png — a preset copied and open in the rule form, slice count updating -->

## What a slice carries

Every channel the log recorded in that window — rpm, manifold pressure, fuel flow, all the temperatures and pressures, the electrical channels — plus its context: which log source wrote it (G3X or AXIS), the phases it spans, pressure and density altitude, outside air temperature, engine hours, the flight it came from and when it started.

So slices are cut once and asked many things. The same 98 takeoff slices answer *is rpm cycling?*, *does manifold pressure follow it?*, *does it depend on altitude?* and *which of these is odd?* without being cut again.

## Rules and phases together

The app already finds the phases of a flight by heuristics. Why cut by rule as well?

- **A question may not match a phase.** The oscillation spans the end of the takeoff roll and the first forty seconds of climb; it is defined by an rpm level, not by what the aircraft is doing. Cutting by phase would have split it.
- **Phase detection is itself a heuristic**, and Research is where heuristics get examined. On a touch-and-go session the full-power rule finds seven to nine slices where the phase engine labels one takeoff roll. That is a fact about the phase engine worth knowing.
- **Odd flights** — the ones a researcher looks at — are the flights where phase labels are most likely to be off.

Use phases where they fit, rules where the question says otherwise, and both together (a rule *within cruise*) when that is cleanest.

## What to do with this

Start from a preset: it is the quickest way to a comparable set. Copy it and change one number if your engine or installation differs. Mark a hand slice when one flight is the question. Then open [Seeing slices together](research-aligned-view.md).

## How it works

Cutting slices needs the raw second-by-second data, which the app's normal analysis does not keep, so a rule over a workspace reads the logs again — the same work as the first import, with progress shown. Logs are read one flight at a time and only the slices' samples are kept. A study stores the *definition* of its slices and their measurements, never the samples; reopening a study is immediate, and only the aligned view, which draws the samples, reads the slices' flights again.

Logs are once a second (the AXIS slightly slower, resampled to one second at import, with filled rows marked and left out of rate and period measurements). Every slice knows its source, because the G3X damps some channels: the same manifold-pressure oscillation shows 2 inHg of ripple on a G3X log and 5–7 on an AXIS log.

Spec 06 §5 defines slice rules, presets and their measurement.
