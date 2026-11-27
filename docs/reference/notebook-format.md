# The notebook format

An investigation is a standard Jupyter notebook (nbformat 4) — it opens in JupyterLab, VS Code or anything that reads `.ipynb` — with a few EIS fields in places the format reserves for tools. Spec 16 §5.

## Where it lives

```
<data folder>/workspaces/<workspace id>/studies/<study id>/
    notebook.ipynb
    files/              anything a cell wrote (figures, tables), referenced relatively
```

**Export notebook (.zip)** is that folder. Flights are named by **fingerprint** in an export (`src:…`, derived from each log, meaningless without the same file), so a notebook travels without your logs; importing it maps the fingerprints back to the importer's flights, and cells whose flights aren't there are read-only.

## The notebook's metadata

`metadata.slingology`:

| Field | |
|---|---|
| `id`, `name` | the study's id and title |
| `kind` | `investigation`, or `question-for-type` (a question for every owner of the engine type) |
| `author` | `claude` or `user` |
| `question` | the question as asked |
| `status`, `summary` | `open` or `finished`; the summary written at the finish |
| `inbox_candidate` | the inbox candidate it investigates, if any |
| `engine`, `engine_type` | the EIS engine version that wrote it; the engine model |
| `created`, `updated`, `finished` | times (UTC) |
| `imported`, `converted_from` | where it came from, when it did |

## Cells

Standard markdown and code cells. The first code cell is the **setup cell** (id `setup`), which binds `eis` to the workspace ([the eis library](eis-library.md)). Each code cell carries `metadata.slingology.ran`:

| Field | |
|---|---|
| `engine` | the engine version it ran on |
| `flights` | the flights its output depends on (ids here; fingerprints once exported) |
| `at`, `ms`, `status` | when, how long, and whether it ran to the end |

A cell whose outputs were saved by a kernel outside EIS (JupyterLab, say) no longer matches its `ran`: EIS shows it **ran elsewhere** until it is re-run on the bench or its outputs are kept as they are.

After **Re-run**, a code cell whose output changed holds the new outputs in `metadata.slingology.pending`, beside the stored `outputs`, until they are accepted or discarded.

## Outputs

Standard nbformat outputs: `stream` (printed text), and `execute_result` / `display_data` with `text/plain`, `text/html` (tables) and `image/svg+xml` (figures).

A **log view** is one output with two representations:

| MIME type | Holds |
|---|---|
| `image/svg+xml` | the strip chart, drawn — what Jupyter, the exported page and a PDF show |
| `application/vnd.slingology.logview+json` | a reference, never samples: `flight`, `flight_date_local`, `start_s`, `end_s`, `channels`, `marks` (`{t_s, label}`), `title`, `window_label`, `rule` |

The EIS pages read the reference and show the Flight view's chart for that window, with **Open flight**. If the flight isn't in the workspace they show the picture, marked *Flight not in this workspace*.

## The finish rule

`study_finish` refuses a notebook that has no summary, a figure or log view without a markdown cell right before or after it saying what it shows, or a code cell that ends in an error — and names the cells. A notebook says what each picture means, and a cell that failed is replaced, not left behind a working copy. Each code cell starts afresh, so it loads what it uses itself; when one fails on a name an earlier cell set, its error says which cell that was.

## The two renderings

The Research page and **Export as a page (.html)** use the same renderer — the page on the website and on your computer show the same notebook — and both pass tables through a filter that keeps only plain table markup.
