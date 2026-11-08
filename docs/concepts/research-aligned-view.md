# Seeing slices together

<div class="in-brief" markdown>
**In brief.** A slice set is drawn on one time axis, every slice starting from the same moment — by default the instant its rule became true — so ninety takeoffs line up whatever happened before them. Up to about ten slices overlay each other; more than that and each gets a small panel of its own, with a cursor that reads every panel at the same instant. Several channels stack under the same axis, which is how the eye catches two signals moving in step. Click a slice and the Flight view opens at that window.
</div>

## Lining up is the whole trick

Stacked flights are not comparable until they are **aligned** on something meaningful. A takeoff slice may begin after twenty seconds of ground roll or, on a touch-and-go, two seconds after the throttle went in. Draw both from their first sample and the shapes smear; draw both from the moment rpm passed 5,550 and they sit on top of each other.

<!-- diagram: research-alignment.svg — the same three slices drawn twice: aligned on slice start (smeared) and on the rule's crossing (coincident) -->

The app offers a few **anchors**, each a rule the study can store, so the view is reproducible:

| Anchor | Zero is… | Use it for |
|---|---|---|
| **Crossing** (default for rule slices) | the moment the slice's conditions became true | onset behaviour — what happens as power comes in |
| **Slice start** (default for hand and phase slices) | the first sample | windows you cut yourself |
| **Slice end** | the last sample | what happens as a condition ends |
| **Peak of a channel** | the slice's highest value of the channel you choose | comparing responses around a maximum |
| **Phase boundary** | the start or end of a phase inside the slice | climbs that begin at different points of the slice |

Time runs in elapsed seconds; each channel shares one vertical scale across all slices, so a tall swing is tall everywhere.

## Overlay and small multiples

With a handful of slices, an **overlay** — one colour per slice, keyed to the slice table — shows differences directly. Beyond about ten the overlay turns to mud, so the view switches to **small multiples**: one panel per slice, same axes, in a grid you can scan. Either can be forced.

A **scrubbing cursor** moves across every panel at once and reads each slice's value at that instant. On the oscillation case it is how the rpm–manifold-pressure lockstep is seen before any question is asked: every panel's two traces rise and fall together.

<!-- screenshot: research-small-multiples.png — the full-power set as small multiples, rpm and MAP stacked, the cursor reading all panels -->

## Channels

Pick the channels to draw; they stack as strips under the shared time axis. Rpm, manifold pressure and fuel flow is the natural first stack for a power question; the four EGTs for a cylinder question; oil and coolant temperature with outside air temperature for a thermal one. The slices carry every channel, so changing the stack costs only a redraw.

## From the view to a flight

Click any slice to open the flight in the Flight view at that window, with all its events and topic cards. Research is for comparing; the Flight view is for understanding one flight. Going between them is meant to be constant.

## What to do with this

Look before you ask. Most findings are visible in the aligned view first, and the question then puts a number on what you saw. If nothing lines up, check the anchor: a smeared overlay is usually a wrong anchor, not a wrong engine. Then ask a question — [Is it steady, or cycling?](research-cycling.md) is the one to start with for any signal that should hold still.

## How it works

The view reads only the flights its slices came from, not the whole selection, so changing anchor or channels on a set of 98 slices is quick after the first build. Overlay is used up to 10 slices and small multiples above; the cursor is the chart library's linked pointer, so values are read from the data, not interpolated. Hand slices store an offset field for a future **splicer**, in which slices can be dragged into alignment by eye and trimmed; the format is ready, the control is not yet built.

Spec 06 §9 and D6 define the aligned view and its anchors.
