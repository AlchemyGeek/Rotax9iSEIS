# What EIS measures

What the instrument behind Research does when you look at a flight with **Signal**, and when Claude measures in a notebook: slices, the measurements on each slice, the four tests, and the shape of every answer. Claude investigates; EIS measures — this page is the measuring. It is the fine print behind [Research](../concepts/research.md) and [Investigations](../concepts/research-investigations.md); the functions are in [the `eis` library](eis-library.md), and the tools in [Investigation tools](investigation-tools.md).

## Slices

EIS measures **slices**, not whole flights. A slice is a stretch of one flight, carrying every channel the log recorded in it and its context. A rule applied to every flight gives a **slice set** — ninety-odd takeoffs, say — and every test is asked of a set. A whole flight is too big a thing to compare; *the thirty seconds after full power is applied* exist on every flight and can be compared ninety times.

<figure class="diagram">
--8<-- "diagrams/research-slice-anatomy.svg"
<figcaption>A slice: a window of one flight carrying every channel and its context.</figcaption>
</figure>

| Cut by | Means | In a notebook |
|---|---|---|
| **A preset** | One of the rules EIS ships, each measured against a season of real logs ([Research presets](research-presets.md)) | `eis.slices("full_power")` |
| **A phase** | Every climb, takeoff roll, cruise… as the Flight view labels them; a rule with no conditions | `eis.slices("phase:CLIMB")` |
| **A rule** | Conditions on channels, held for a minimum duration, short dips bridged, optionally within a phase | a rule object (below) |
| **By hand** | One window of one flight — usually a mark you made with *Mark for Claude* | `hand_slices` |

<figure class="diagram">
--8<-- "diagrams/research-rule-slices.svg"
<figcaption>A rule: conditions, a minimum duration and a merge gap, applied to every flight.</figcaption>
</figure>

| Rule part | Meaning | The full-power preset |
|---|---|---|
| Conditions | One or more channels compared with a value (`>=`, `>`, `<=`, `<`, `=`, `between`); all must hold | rpm ≥ 5,550 |
| Minimum duration | The conditions must hold at least this long | 15 s |
| Merge gap | A dip shorter than this does not split a slice | 3 s |
| Phase | Optionally, only within (or outside) phases EIS already identifies | — |
| Pad | Optionally, seconds added before and after | 0 |

**Context each slice carries:** log source (G3X or AXIS), the phases it spans, pressure and density altitude, outside air temperature, engine hours, its flight and local start time. Logs are once a second; AXIS logs are resampled to one second at import, with filled rows marked and left out of rate and period measurements. The G3X damps some channels: the same manifold-pressure oscillation leaves 2 inHg of ripple on a G3X log and 5–7 inHg on an AXIS log, so sources are never pooled on such a channel.

## Measurements on each slice

Computed for every slice and every channel asked for:

| Group | Measurements |
|---|---|
| Level | mean, median, minimum, maximum |
| Spread | standard deviation, median absolute deviation, **swing** (median bottom-to-top over a rolling window), interquartile range |
| Shape | slope across the slice, largest rate of change |
| Periodicity | **dominant period** and its prominence |
| Coupling | correlation with a reference channel (rpm by default) at zero lag, and the lag of best match |
| Quality | sample count, duration, share of filled rows, dropouts |

<figure class="diagram">
--8<-- "diagrams/research-period-swing.svg"
<figcaption>Period and swing on a cycling rpm trace.</figcaption>
</figure>

Medians and median absolute deviations are used wherever a central value or spread is reported, because once-a-second engine data is quantised (rpm in steps of ten) and has spikes.

**Windows and lag ranges come from the data.** The dominant period is estimated first, on the whole detrended slice. Then:

| Situation | Swing window | Lag range |
|---|---|---|
| At least half the slices have a clear period *P* | 2.5 × *P* | ±1.5 × *P* |
| Otherwise | 0.2 × median slice duration | ±0.1 × median slice duration |
| Never less than | **12 s** | **±10 s** |

The values used, and what they came from, are printed in every answer's caveats; a notebook can override them (`windows`).

**Period detection.** The search runs from 2 s up to a third of the slice. A period counts when the autocorrelation peak is prominent (half its peak-to-trough height at least 0.2) and the periodogram agrees within 20 %. Periods under 3 s are never counted: a cycle that fast is "faster than the 1 Hz log can resolve", and EIS says so rather than report it.

## Signal: one flight, looked at closely

**Signal** on the Flight view lays two strips under each channel over the whole flight: the **swing** (how far the channel moves bottom to top, second by second) and where it **repeats** (lit where a period stands out). Zoom to a window and its numbers appear beside their references: the swing beside the Operators Manual line it approaches, the period, and each other channel's correlation with the first. It is `signal_analyze` — the same numbers Claude gets for that window.

## The four tests

Instruments for four kinds of question, asked of a slice set. A notebook uses one when the question is about what it measures, and says why when it uses one for another reason; any other question is answered by loading, slicing and plotting.

### Is it steady, or cycling? — `eis.cycling`

> RPM cycles every 3.8 s (IQR 3.6–3.9), swing 180 rpm (170–190), in 93 of 98 slices (AXIS 13 of 14, G3X 80 of 84).

| | |
|---|---|
| Channels | one |
| Reports | median and IQR of period and swing; the count of slices with a clear period (recurrence), per source |
| References | the Operators Manual limit for the channel where one exists; the set's own spread |
| Does not mean | that cycling is bad; nothing under 3 s can be seen |

The count is the number to read first: 93 of 98 is a characteristic of the installation; 3 of 98 is three flights to look at.

### Do these move together, and who leads? — `eis.coupling`

> Manifold pressure follows RPM with no delay (median correlation 0.93 on AXIS slices, 0.2 on G3X slices); fuel flow follows 1 s behind.

<figure class="diagram">
--8<-- "diagrams/research-lag.svg"
<figcaption>Moving together, and who leads.</figcaption>
</figure>

| | |
|---|---|
| Channels | one, plus one or more to compare with |
| Reports | median correlation at zero lag and the median lag of best match, per pair, per source |
| Does not mean | which one causes the other; slow co-movement (two temperatures rising together) is removed by detrending, but read the chart |

The 0.93 against 0.2 is two recorders, not two engines: the G3X damps manifold pressure.

### Are these groups different? — `eis.groups`, `eis.compare`

> Swing is 180 rpm below 3,500 ft DA, 130 rpm at 3,500–6,000 ft and 75 rpm at 6,000 ft and above (92 / 4 / 2 slices — small groups).

<figure class="diagram">
--8<-- "diagrams/research-two-groups.svg"
<figcaption>Two groups on one measurement: the gap between the medians and how many slices stand behind each.</figcaption>
</figure>

| | |
|---|---|
| Split | by log source, before/after a date, density-altitude or OAT bands, engine hours, rule, or named groups of flights |
| Measurement | any per-slice measurement above, written `channel.measure` (`rpm.swing`, `oil_temp_f.median`) |
| Reports | each group's median, the median difference, an effect size (Cliff's delta, 0 = interleaved to 1 = no overlap), the counts; a rank test as supporting evidence only |
| Does not mean | why; a group below the minimum (ten by default) gets the small-group caution; no *p*-value is a headline |

Consecutive seconds are not independent, so a probability would look far more certain than the data is; the size of the gap and the count behind each side are the headline. `eis.compare` gives the same set one row per slice, grouped by flight, with each row's difference from a slice you pin — *this* takeoff against all the others.

### Which slices are unusual? — `eis.unusual`

> 2026-07-17 18:19 — rpm swing far below the rest (70 vs 180); manifold pressure flat at 51.4 inHg.

<figure class="diagram">
--8<-- "diagrams/research-unusual.svg"
<figcaption>Unusual means far from the other slices — here, the two clean high-altitude takeoffs.</figcaption>
</figure>

| | |
|---|---|
| Channels | by default rpm, manifold pressure, fuel flow, EGT 1–4, CHT, oil pressure and temperature, coolant temperature, fuel pressure, volts |
| Reports | a ranked list of at most ten slices, each with the measurement it stands out on (a robust z of 3.5 or more against slices of the same source) and the direction |
| Does not mean | that a listed slice has a problem, or that an unlisted one does not |

Unusual means *different from your other slices*. On the oscillation case the two slices that stood out were the two that did not cycle.

## Every answer has the same shape

1. **Finding** — one sentence with a count, split by source when both are present.
2. **Evidence** — a chart, and the table of every slice with its measurements and conditions.
3. **Magnitude beside a reference** — the Operators Manual value from the engine profile (the only number EIS brings), the set's own spread, or a reference Claude or you name with its source.
4. **Caveats** — the sampling floor, source differences, group sizes, the windows used, and what the answer does not mean.
5. **Details** — the machine-readable record of the run: question, settings, slices, references, engine version.

No answer carries a verdict. The words *abnormal*, *fault* and *detected* do not appear, and a test over EIS's own text keeps it so; whether a shape matters is for the Operators Manual, the people who built the part, and you.

The instrument is [Spec 06 — Research](https://github.com/AlchemyGeek/Rotax9iSEIS/blob/main/docs/specs/06-research.md): slices §5, measurements §6, the tests §7, the result §8.
