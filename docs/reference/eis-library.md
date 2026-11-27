# The `eis` library

The Python a notebook's code cells use — on the bench where Claude's code runs, and in your own Jupyter kernel ([Run a notebook in JupyterLab](../walkthroughs/notebook-jupyterlab.md)). It answers from the EIS engine on your workspace: the same slices, questions and numbers as the Research page, as pandas tables and results you can print. Spec 16 §4.5 and §5.4.

## Binding to a workspace

Every notebook starts with a **setup cell**:

```python
from slingology_eis import eis
eis.open("ws_2b59350ca5ac")
```

`eis.open(workspace_id=None, data_root=None)` opens a workspace from the data folder the EIS pages use (`data_root=` for another), and returns nothing; the functions below then answer through `eis.`. On the bench the cell is already bound and can't open another workspace. `eis.bound()` and `eis.workspace_id()` say what is open. Outside EIS this needs `slingology-eis[investigations]` installed in the kernel's Python.

## Flights and samples

| Call | Returns |
|---|---|
| `eis.flights()` | one row per flight, oldest first: local date and start time with the zone, route, takeoffs and landings, the pilot's name, engine hours, source, flight facts |
| `eis.find("the Oct 24 flight with three landings")` | the flights a description in words names, best first, with what matched (`limit=10`) |
| `eis.load(flight, channels=None, start_s=None, end_s=None)` | one flight's channels, 1 Hz, seconds from the log's start |
| `eis.signal(flight, start_s=None, end_s=None, channels=None)` | what *Signal* shows on the Flight view, for one flight or window: descriptors, numbers with Operators Manual references, diagnostics |

## Trends: the per-flight metrics

What the Trends page is built from, as tables — the same numbers as the `fleet_metrics` and `trends_summary` tools. For a "has X changed" question, start here: plot the metric against date, engine hours or OAT before slicing anything.

| Call | Returns |
|---|---|
| `eis.metrics(flights=None, metrics=None)` | one row per flight, in engine-hours order: flight id, name, local date and start time, engine hours, cruise density altitude (ft) and OAT (°C), log source, then every per-flight metric (`oil_temp_peak`, `cruise_fuel_flow`, `egt_spread`, …; all but the `limit_*` ones unless named in `metrics=`) |
| `eis.trends()` | one row per Trends card, ranked: the metric, its reference (n, mean, std, min, max), its trend over engine hours, the shift if one stands (the recent flights against their reference, `shift_z`, direction, the OM limit beside it), the shifts recorded for it, and the flights it rests on |

```python
m = eis.metrics()
m.plot(x="date", y="oil_temp_peak")            # a level over time
m.plot.scatter(x="cruise_oat_c", y="oil_temp_peak")   # against what it follows
eis.trends()[["rank", "metric_id", "reference_mean", "recent_mean", "shift_z"]]
```

## Slices

A **rule** is a preset id (`"full_power"`, `"governed_climb"`, `"stable_cruise"`, `"idle"`, `"warm_up"` — [Research presets](research-presets.md)) or a rule of your own.

| Call | Returns |
|---|---|
| `eis.slices(rule="full_power", channels=None, flights=None)` | one row per slice: flight, start and end, local time, context, descriptors |
| `eis.samples(rule, channels=None, flights=None, anchor="crossing")` | the slices' 1 Hz samples aligned at an anchor (`crossing`, `start`, `end`, `peak:CHANNEL`) |
| `eis.compare(rule, channels=None, flights=None, pinned=None, collapse=False)` | one row per slice, grouped by flight, with deltas to a pinned row |

## The four tests

Each returns a **Result** — the same answer as the matching tool ([What EIS measures](what-eis-measures.md)):

| Call | Asks |
|---|---|
| `eis.cycling(rule="full_power", channel="rpm")` | Is it steady, or cycling? Period, swing, how many slices |
| `eis.coupling(rule, channels=("rpm", "map_inhg"))` | Do these move together? Correlation and lag |
| `eis.groups(rule, descriptor="rpm.swing", by="source")` | Are these two groups different? `by` is `"source"`, `"rule"`, `"date"` (with `date=`), `"da_band"`, `"oat_band"`, `"engine_hours"`, or `{"by": "flights", "groups": [...]}` |
| `eis.unusual(rule, channels=None)` | Which slices stand apart? |

Extra keyword arguments are the question's parameters.

A **Result** has `.finding` (the sentence), `.magnitude` (the numbers beside their references), `.caveats`, `.rows` (the per-slice table, a DataFrame) and `.figure()` (one dot per slice, grouped, each group's median a bar). `print(result)` prints the finding, magnitude and caveats as the Research page lays them out.

```python
r = eis.cycling("full_power", "rpm")
print(r)
r.rows.head()
```

## Evidence: tables, figures and log views

A finding in a notebook is one sentence and one **evidence** cell — a table, figure or log view the reader can read without the code ([the notebook format](notebook-format.md#the-shape)). Three calls make one; each takes a **caption**, one line saying what it shows, and EIS numbers them in order on the page (*Table 1*, *Figure 2*, *Log view 3*), so a finding's sentence can point at its evidence by number. Raw `print` output is never evidence.

```python
eis.table(df, caption="Full-power swing per slice", units={"swing": "rpm"}, digits=None)
```

A DataFrame (or Series) as a table: column names in words with their units (`fuel_press_psi.mean` → *Fuel pressure mean (psi)*, `duration_s` → *Duration (s)*; a `units` entry wins), numbers rounded (`digits`: one number for every column, a `{column: digits}` dict, or by size — none from 100, one from 10, else two), at most 500 rows (the rest counted below). A caption is required.

```python
fig, ax = plt.subplots()
...
eis.figure(fig, caption="Fuel pressure by phase")
```

A matplotlib figure (or Axes) as a figure, drawn as SVG with its caption.

```python
eis.logview(flight, start_s, end_s, channels=("rpm", "map_inhg"),
            marks=[(367, "takeoff power")], title=None, rule=None,
            caption="First takeoff: the swing starts at full power")
```

A strip chart of one flight's window. The cell's output carries both a picture (what JupyterLab, the exported page and a PDF show) and a reference to the flight and window, which the EIS pages show as the Flight view's live chart with **Open flight** ([the notebook format](notebook-format.md)). Marks are `(seconds, label)`. Without a caption, a log view's title stands in for it.

All three render the same in your own Jupyter kernel: the table as HTML, the figure as SVG, each with its caption.

## Documents

`eis.document(name)` opens one of the aircraft's documents ([Set up your aircraft and documents](../walkthroughs/aircraft-documents.md)), read in place and read-only, for a cell that quotes a page.

## What the bench allows

Claude's code cells run on the **bench**: a separate process with a time and memory cap (60 s and 2 GB by default), no network, no starting other programs, and no writing outside the notebook's own folder — on a Mac enforced by macOS itself as well as by EIS. Code can read any file you can. In your own kernel none of this applies.
