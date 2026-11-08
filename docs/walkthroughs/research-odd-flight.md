# “This flight felt odd”

*Ten minutes. Something on one flight didn't feel right — a surge in the climb, a rough patch at a power setting, a temperature that seemed slow to come down — and you want to know whether that flight was different or whether your engine does this every time. You start from the flight, not from a rule.*

## What you will do

Mark the window you felt it in, set it beside the same window on every other flight, and ask whether it stands out. The answer is either *this one is different* — a flight to look at closely — or *they all do this* — a characteristic to investigate on its own, as in [Reproducing a takeoff investigation](research-takeoff.md).

## 1. Open the flight

From **Flights**, open the flight. On the chart, zoom to the stretch where you felt it — the climb after the touch-and-go, say. Put rpm and manifold pressure on the chart if they aren't already; they are the first pair for anything that felt like power.

<!-- screenshot: wt-odd-01-zoom.png — the Flight view zoomed to the climb, rpm and MAP shown -->

## 2. Research this window

Choose **Research this window** above the chart. A new study opens with:

- this flight selected, and the zoomed window as a **hand slice** — flight, start and end seconds, named after the flight;
- the first channel you had on the chart already chosen for the view.

If the window covers a takeoff, the study offers **Add the full-power rule**: the preset that cuts the same stretch out of every other flight. Accept it. If it covers something else — a cruise, a descent — add the preset that fits, or copy one and edit the rpm band to match the window you marked.

<!-- screenshot: wt-odd-02-seeded.png — the new study seeded with the hand slice and the suggested preset -->

## 3. Extend to all flights

In the selection, switch from the one flight to **all flights**. The slice count fills in: your one hand slice, plus every slice the rule found across the workspace. In the slice list, press **Highlight** on your hand slice so it is drawn on top of the others in the **Aligned view**.

Now look. If your slice sits inside the bundle of the others, your engine does this every time. If it leaves the bundle — a bigger swing, a later recovery, a different level — the flight is different, and the next step is to find how.

<!-- screenshot: wt-odd-03-highlight.png — the aligned view with the hand slice highlighted against the rule-built set -->

## 4. Ask whether it stands out

**Add a question** → **Which of these slices is unusual?** **Run**. If your hand slice is in the list, the card names the measurement it stands out on — swing, level, how fast something changed, how a channel moved with rpm. If it is not in the list, the aligned view already told you the same thing with your eyes: that flight was not special.

## 5. Ask what you felt

Whatever you felt has a shape. **Add a question** → **Is this signal steady, or is it cycling?** on the channel the feeling points at — rpm for a surge, fuel pressure for a stumble, oil pressure for a flicker. **Run**. The finding's count tells you the story in one glance: *in 1 of 94* is your flight; *in 90 of 94* is your installation.

<!-- screenshot: wt-odd-04-count.png — a cycling result where the recurrence count is the point -->

## 6. If it is one flight

Click the hand slice to go back to the Flight view at that window. Look at what else was happening — the Events table, the phase, the altitude and temperature, the wind. Add a note to the study saying what you found or didn't. **Save**. A single odd flight is usually weather, a procedure, or a sensor; the note is worth keeping either way.

## 7. If it is every flight

You have found a characteristic, and the question is no longer about this flight. Rename the study for the behaviour, drop the hand slice if you like, and continue as in [Reproducing a takeoff investigation](research-takeoff.md) from step 7: who leads, does it depend on conditions, and then the evidence package.

## Where to go next

- [Slices: pieces of flights](../concepts/research-slices.md) — hand slices and rules together.
- [Which slices are unusual?](../concepts/research-unusual.md) — what *unusual* does and does not mean.
- [From a finding to action](../concepts/research-action.md) — if it turned out to be every flight.
