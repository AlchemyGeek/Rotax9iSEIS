# Research questions and parameters

What each of the four questions takes, what it measures, the settings it chooses for itself and prints on every card, the references it shows a result against, and the caveats it always carries. The questions are explained in plain terms on their own pages; this page is the fine print.

## Common to all four

**Input.** A slice set — the slices one or more rules, phases and hand slices produce over the study's selection — and the channels named in the question. The selection may be *all flights*, chosen flights, or split (by log source, density-altitude band, outside-air-temperature band, date, or before/after a date).

**Measurements per slice.** Computed for every slice and every channel a question names, and listed in the per-slice table:

| Group | Measurements |
|---|---|
| Level | mean, median, minimum, maximum, value at the alignment anchor |
| Spread | standard deviation, median absolute deviation, **swing** (median bottom-to-top over a rolling window), interquartile range |
| Shape | slope across the slice, largest rate of change, time from the anchor to reach a level |
| Periodicity | **dominant period** and its prominence |
| Coupling | correlation with a reference channel (rpm by default) at zero lag, and the lag of best match |
| Quality | sample count, duration, share of filled rows, dropouts |
| Context | source, phases, pressure and density altitude, OAT, engine hours, start time, flight |

Robust statistics (medians, median absolute deviations) are used wherever a central value or spread is reported, because once-a-second engine data is quantised (rpm in steps of ten) and has spikes.

**Windows and lag ranges are proposed from the data.** No question carries a fixed window. First the dominant period is estimated on the whole detrended slice — it needs no window. Then:

| Situation | Swing window | Lag range |
|---|---|---|
| At least half the slices have a clear period *P* | 2.5 × *P* | ±1.5 × *P* |
| Otherwise | 0.2 × median slice duration | ±0.1 × median slice duration |
| In all cases, never less than | **12 s** | **±10 s** |

Values are rounded to whole seconds. The resolved values and what they were derived from (period, duration or your override) are printed in every card's caveats and saved in the result. You can override them per study.

**Period detection.** The search runs from 2 seconds up to a third of the slice length (so a trend is never read as half a cycle). A period counts as present when the autocorrelation's peak is prominent — half its peak-to-trough height at least 0.2 — and the periodogram's peak agrees within 20 %. Periods under 3 seconds are never counted: logs are once a second, and anything faster is unreliable or invisible.

**Sources.** Garmin G3X and Garmin AXIS logs are never pooled on a channel they record differently; results are stated per source when both are present. The G3X damps its manifold-pressure channel.

**Fixed caveats** on every card: the sampling floor; source differences where they apply; group sizes where they apply; the resolved windows; and the question's own sentence on what its answer does not mean.

**Minimum group size.** The app's usual minimum — *n_min*, ten by default, in *Settings → Reference & Models* — triggers the small-group caution.

## Is this signal steady, or is it cycling?

| | |
|---|---|
| Channels | one |
| Settings | swing window (proposed); minimum prominence for a period to count (0.2) |
| Reports | median and interquartile range of period and swing across the set; the count of slices with a clear period (recurrence), per source |
| Chart | every slice's swing, by source |
| References | the Operators Manual limit for the channel where one exists (drawn on the chart); the set's own spread; your references for that channel |
| Does not mean | that cycling is bad; periods under 3 s cannot be seen |

## Do these two move together, and who leads?

| | |
|---|---|
| Channels | one, plus one or more to compare with |
| Settings | lag range (proposed) |
| Reports | median correlation at zero lag and the median lag of best match, per pair, per source |
| Chart | correlation by slice and source; the two channels aligned |
| References | none from the Manual; the set's own spread |
| Does not mean | which one causes the other; slow co-movement over a short slice is removed by detrending but read the chart |

## Are these two groups different?

| | |
|---|---|
| Input | a split on the selection (source, DA band, OAT band, date, before/after a date) or two slice sets; one measurement from the table above |
| Settings | band edges for altitude and temperature splits (blank = the app's fleet bands); the split date |
| Reports | each group's median, the median difference, an effect size (Cliff's delta, 0 = interleaved to 1 = no overlap), the counts; a rank test as supporting evidence only |
| Chart | the two distributions side by side, one point per slice |
| References | the two groups are each other's reference |
| Does not mean | why; a group below *n_min* gets the small-group caution; no *p*-value is shown as a headline |

## Which of these slices is unusual?

| | |
|---|---|
| Channels | by default rpm, manifold pressure, fuel flow, EGT 1–4, CHT, oil pressure and temperature, coolant temperature, fuel pressure, volts; editable |
| Settings | the standing-out threshold (a robust z of 3.5) and the list cap (10) |
| Reports | a ranked list of at most ten slices, each with the measurement it stands out on and the direction; six measurements per channel are scanned (median, swing, spread, slope, largest rate of change, correlation with rpm); computed within each log source |
| Chart | the measurements that separated the listed slices |
| References | the rest of the set |
| Does not mean | that a listed slice is wrong or an unlisted one right; with many measurements some slice will stand out by chance |

A planned refinement will rank slices by how *many* measurements they stand out on and within the channels the study's other questions use; the card will say when that is in effect.

## Where the settings live

Per study: windows and lag ranges (override), band edges, split date, references. Workspace-wide: *n_min*. Nothing about Research is set app-wide.

Spec 06 §6–§8 define the measurements, the questions and the result; §7.0 the window rule.
