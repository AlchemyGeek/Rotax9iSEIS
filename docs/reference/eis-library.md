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

## Log views

```python
eis.logview(flight, start_s, end_s, channels=("rpm", "map_inhg"),
            marks=[(367, "takeoff power")], title=None, rule=None)
```

A strip chart of one flight's window. The cell's output carries both a picture (what JupyterLab, the exported page and a PDF show) and a reference to the flight and window, which the EIS pages show as the Flight view's live chart with **Open flight** ([the notebook format](notebook-format.md)). Marks are `(seconds, label)`.

## Documents

`eis.document(name)` opens one of the aircraft's documents ([Set up your aircraft and documents](../walkthroughs/aircraft-documents.md)), read in place and read-only, for a cell that quotes a page.

## What the bench allows

Claude's code cells run on the **bench**: a separate process with a time and memory cap (60 s and 2 GB by default), no network, no starting other programs, and no writing outside the notebook's own folder — on a Mac enforced by macOS itself as well as by EIS. Code can read any file you can. In your own kernel none of this applies.
