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
| `status`, `summary` | `open` or `finished`; the summary written at the finish (*What it means*, or the older free-text summary) |
| `shape` | `1` for a notebook laid out in the seven sections ([The shape](#the-shape)); absent on older notebooks |
| `top` | the structured Answer of the last finish: `question_scope`, `shows` (3–5 sentences), `means`, `actions` (`what`, `who`, `settles`, `recheck_after_flights`) or `actions_none` |
| `history` | each earlier `top`, with the date it was replaced (`finished`) |
| `finding` | `shows[0]` — the notebook's line in the Journal |
| `followup` | the follow-up open now, if any (its heading cell's id) |
| `card` | the Research home card: origin, channels, flights, dates, evidence counts, tests, outputs, tags, `actions` |
| `inbox_candidate` | the inbox candidate it investigates, if any |
| `engine`, `engine_type` | the EIS engine version that wrote it; the engine model |
| `created`, `updated`, `finished` | times (UTC) |
| `imported`, `converted_from` | where it came from, when it did |

## Cells

Standard markdown and code cells. The first code cell is the **setup cell** (id `setup`), which binds `eis` to the workspace ([the eis library](eis-library.md)). Every cell has a `metadata.slingology.role` ([Cell roles](#cell-roles)). Each code cell carries `metadata.slingology.ran`:

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

An **evidence output** — what `eis.table`, `eis.figure` and `eis.logview(…, caption=)` produce — carries `metadata.slingology.evidence`: `kind` (`table`, `figure`, `logview`), `caption`, and for a table its `units`; a table also carries `slingology.table` (`n_rows`, `n_cols`, `truncated`). The number (*Table 1*) is the renderer's, counted in order, so moving a cell never leaves a stale number.

## The shape

A notebook is laid out in seven sections, in this order. `study_create` writes their headings — markdown cells with role `section`, ids `s1`–`s7`. Spec 16 §5.6.

| Section | Holds | Written by |
|---|---|---|
| **1 The question** | the question; *Scope and qualifications* | the finish (`question_scope`) |
| **2 Answer** | *What the data shows* (3–5 bullets); *What it means* | the finish (`shows`, `means`) |
| **3 Proposed actions** | numbered: what · who · what it would settle · re-check after the next N flights — or *None*, and why | the finish (`actions`) |
| **4 Findings** | each finding: one sentence, then its evidence cell (and the calculation behind it) | Claude |
| **5 How this was done** | the plan, the data and slice rules in words, the method, alternatives ruled out, outside context labelled as context | Claude |
| **6 Follow-ups** | dated subsections (`### Follow-up — 2026-11-27: title`), each ending with what changed above | Claude, after `study_followup` |
| **7 Working** | every scratch cell, in the order written | gathered at the finish |

Sections 1–3 are written from the finish's fields, not from markdown: the `.ipynb` holds them as markdown cells marked `generated: true`, so JupyterLab shows the same text, and a re-finish rewrites them and keeps the earlier Answer in `history`. A follow-up opens when Claude asks for one, or by itself when new analysis lands in a finished notebook.

### Cell roles

| Role | Cell | |
|---|---|---|
| `evidence` | code | a table, figure or log view the reader reads without the code — shown open, numbered, with its caption |
| `support` | code | the computation behind the evidence or sentence after it — folded under *show the calculation*. A code cell without a role is support |
| `scratch` | code or markdown | exploring — kept, folded, under *Working* |
| `narrative` | markdown | a finding's sentence, what a result means, the plan. A markdown cell without a role is narrative |
| `section`, `followup`, `changed`, `setup` | — | written by EIS: the headings, a follow-up's heading and its *What changed above* line, the setup cell |

**Older notebooks** (no `shape`) get roles when first loaded — code cells support, markdown narrative — and nothing moves; they render as before. Moving any cell into a section gives the notebook its seven headings, with its cells under *Findings*.

## The finish rule

`study_finish` takes the Answer as fields — `question_scope`, `shows`, `means`, `actions` (or `actions_none`), and `changed` when a follow-up is open; a `summary` alone is still accepted and stands as *What it means*. It refuses, naming the cells, while:

- a figure or log view has nothing saying what it shows — a caption, or a markdown cell right before or after it;
- a code cell ends in an error;
- an evidence cell's output is plain printed text;
- a support cell has nothing after it — no evidence and no sentence that uses it.

A notebook says what each picture means, and a cell that failed is replaced, not left behind a working copy. Each code cell starts afresh, so it loads what it uses itself; when one fails on a name an earlier cell set, its error says which cell that was. At the finish the scratch cells move under *Working*.

## The two renderings

The Research page and **Export as a page (.html)** use the same renderer — the page on the website and on your computer show the same notebook — and both pass tables through a filter that keeps only plain table markup. A shaped notebook reads as its sections: 1–3 typeset as one block (earlier Answers folded inside it), each finding's evidence open with its number and caption and the calculation folded beside it, then *How this was done*, the dated follow-ups, and *Working (n cells)* folded at the end. The Research home card says *n actions*.
