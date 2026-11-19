# Reproducing a takeoff investigation

*Twenty minutes. This repeats, with EIS and Claude, the investigation that found a 180-rpm, four-second cycle on nearly every takeoff of one aircraft — a behaviour that lived inside every limit and never changed, so neither the Flight view's events nor Trends could have shown it. Any workspace with a season of flights will do; the numbers below are the original aircraft's (60 flights, April to October). The original write-up is [here](../research/2026-10-takeoff-rpm-oscillation.md). You need the [extension installed](install-extension.md) for steps 4–6.*

## What you will do

Look at one flight with Signal on, mark the takeoffs that look odd, ask Claude with *Investigate*, and read the notebook it writes.

## 1. Look at the flight it was felt on

Open the three-takeoff AXIS flight of 2026-10-24 (§2.3 of the [write-up](../research/2026-10-takeoff-rpm-oscillation.md)) — **Flights**, or *Find a flight* with *Oct 24 three landings*. Choose rpm and manifold pressure on the chart, and press **Signal** under it.

The swing strip under rpm brightens over the three full-power segments and stays dim through taxi and cruise; the repeat strip lights over the same three stretches, and the line above it reads a period of three to four seconds. Something repeats at takeoff power, and only there.

## 2. Read one takeoff's numbers

Drag across the first takeoff. Under the chart: rpm swings about 170 rpm peak to peak, beside the Operators Manual's takeoff-rpm line it approaches; it repeats every three to four seconds; and manifold pressure moves with it, correlation high at zero lag. Two signals in step is a mechanism, not a wobble — but this is one takeoff on one flight.

## 3. Mark it — and the others

Press **Mark for Claude…**, write *rpm and MAP swing together at full power*, choose **A new question** and call it *takeoff rpm oscillation*. **Mark**.

Zoom to the second and third takeoffs and mark each under the same question (it is offered first). If you remember another flight where it felt the same, mark that too. **Research** shows the question in the inbox with its marks ([Mark something for Claude](mark-for-claude.md)).

## 4. Ask

In Claude Desktop, open a new chat, choose **Investigate** from **+**, and send it with no text. Claude takes *takeoff rpm oscillation*, opens a notebook with your three marks — your note, then a log view of each takeoff — and starts from what you saw. In the chat you will see it:

- read your aircraft notes and find the flight;
- cut every full-power segment of every flight — on the original aircraft, 98 slices from 59 of 60 flights (touch-and-go sessions give several each);
- ask whether rpm cycles across them — *in 93 of 98 slices, every 3.8 s, swing 180 rpm*;
- ask whether manifold pressure and fuel flow move with it — MAP in step, fuel flow a second behind;
- read the boost schedule in your Operators Manual, and the governor's band in the controller manual if it is in your documents folders;
- test the hypothesis against density altitude — the swing fades at high density altitude, where the boost control has reached its ceiling.

Each of those is a cell in the notebook, with its output.

## 5. Steer

Ask what you would ask a colleague. *"Is it the same on G3X and AXIS logs?"* — Claude will say the G3X damps manifold pressure, so the coupling shows weaker there. *"Which takeoffs don't cycle?"* — the two clean ones were high-altitude departures. *"What does the controller manual say about its governing band?"*

## 6. Read the notebook

On the Research page the notebook opens with the question and Claude's summary: what was found, with counts and references; the mechanism, stated as a hypothesis; the alternatives ruled out, each with the cell that did it; and what to do. Your question in the inbox now reads *watching*, with *Open the investigation*.

- Ask Claude to note the finding in the Journal, so the date is kept.
- **Export as a page (.html)** for the person who can act on it ([From a finding to action](../concepts/research-action.md)).
- **Export notebook (.zip)** for another owner of the same engine ([Sharing a notebook](research-sharing.md)).

## What happened next

The owner sent the plot and the per-takeoff table to the propeller controller's manufacturer, who recognised a known behaviour of that controller with this engine and offered a firmware update. Once the update is flown, the **Before / after** prompt with its date compares the takeoffs on each side.

## Where to go next

- [Investigations](../concepts/research-investigations.md) — what Claude does, and what stays true.
- [What EIS measures](../reference/what-eis-measures.md) — the slices and tests behind the numbers.
