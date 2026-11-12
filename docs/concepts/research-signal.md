# Signal view: one flight, looked at closely

<div class="in-brief" markdown>
**In brief.** Signal view shows one flight with its channels stacked on a shared time axis and the phases shaded. Under each channel are two coloured **strips**. One shows how far the channel swings, second by second. The other shows how often it repeats, and is coloured only where a repeat stands out clearly. A bright stretch tells you where to look. Drag across the chart or a strip to choose a **window**. The app then shows that window's numbers beside the Operators Manual value and your own references, with the diagnostics behind them. *Make this a rule* turns the window into a slice rule, so Compare can find the same moment in every other flight.
</div>

## Why start with one flight

Most investigations begin with one flight that felt odd. Before you ask *does every flight do this?*, you need to know what *this* is: where in the flight it happens, which channels it shows in, how big it is and how often it repeats. Signal view answers those for the one flight, and then hands the answer to [Compare](research-compare.md) as a rule.

It is the first of Research's three levels:

| Level | Looks at | Answers |
|---|---|---|
| **Signal** | one flight | where in this flight does the signal swing and repeat, and what does it look like there? |
| **Compare** | a selection of flights | does every flight do this, and how do they differ? |
| **Questions** | a slice set | what is true of the set as a whole? |

## The strips

Each strip is a channel read through a short window that slides along the flight one second at a time.

- **Swing** is how far the channel went from bottom to top inside the window, in the channel's own units. Dark means still and bright means moving.
- **Period** is the time between repeats that stands out most inside the window. It is coloured only where the repeat is **prominent**, meaning it clears the same threshold that [Is it steady, or cycling?](research-cycling.md) uses. Everywhere else the strip stays empty. An empty period strip does not say the signal is still. It says no single rhythm stands out.

A range beside each strip gives the lowest and highest values it shows. Read the numbers from that range, not from the colour alone.

<!-- screenshot: research-signal-strips.png — one flight, rpm and MAP stacked, phases shaded, the swing and period strips lit over three takeoffs -->

The value of a strip at any second is exactly what a slice of that window would carry as its swing and period. The strips and the questions measure the same thing.

## The window

Drag across the chart or either strip, and the seconds you covered become the **window**. If you came from a flight's chart through *Research this window*, the window is the chart's zoom. For the window you get the following.

- **This flight's numbers.** Swing, period and its prominence, and level for each channel. For each channel other than the reference, you also get its correlation with the reference at zero lag and the lag at which they match best. Each number sits beside the nearest Operators Manual value, phrased as headroom, and beside any reference you have typed in. There is no verdict and no threshold, only numbers beside other numbers.
- **The windows used.** These are the analysis windows the app chose for this stretch, printed so the numbers can be reproduced.
- **Diagnostics.** These are the four pictures the numbers come from:
    - the trace with its slow drift removed;
    - its autocorrelation, with the period marked;
    - its periodogram, with its peak;
    - for a channel other than the reference, its correlation with the reference at each lag, with the best lag marked.

<!-- screenshot: research-signal-window.png — a window over one takeoff: the numbers table, the diagnostics, Make this a rule -->

## Make this a rule

*Make this a rule* proposes a slice rule from the window:

- **the band** is the channel's range over the window, widened a little above the top so that slices which swing slightly more still match;
- **the length** is half the window's length, so that shorter versions of the same moment still count;
- **a merge gap** of 3 seconds bridges brief dips out of the band.

The rule opens in the ordinary rule form under Compare. Adjust the band or the duration, and the slice count updates as you type. Choose a different channel in the menu beside the button to base the rule on that channel instead. The rule remembers which flight and window it came from.

## What to do with this

Use the strips to find the stretch, and the window to measure it. Then make it a rule and go to Compare to see whether the other flights do the same. If the strips are dark everywhere, the signal is quiet on this flight and there is nothing to carry forward. If they are lit everywhere, the rhythm belongs to the whole flight, and a phase slice is a better start than a window.

## How it works

The sliding window is 12 seconds, the floor for once-a-second logs, unless the flight's own clear periods are long enough to call for a wider one (2.5 periods). The strip header prints the window used and the share of the flight where a period stands out. The flight is read once, for its strips. Moving the window re-reads only the window. A flight with three channels takes a couple of seconds on a laptop, and longer in the browser. Spec 06 §9.1 defines Signal view.
