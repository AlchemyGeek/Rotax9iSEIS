# Notebooks you keep and share

<div class="in-brief" markdown>
**In brief.** Every investigation is a **notebook**: the question, Claude's narrative, the code it ran against your logs with each output, figures, tables, and log views of the windows that matter — with your marks at the top when it took up one of your questions. Notebooks are saved in the workspace and listed on the Research page with who wrote them and their finding. A notebook refers to flights by their fingerprint, never by file, so it travels: export it, and another owner imports it, reads your investigation, and with EIS on their computer runs it on *their* flights.
</div>

## What a notebook holds

- the **question** and, when it was one of yours, your **marks** — each note, then a log view of its window;
- Claude's **markdown**: what it saw, what it measured and why, the hypothesis, the alternatives ruled out, what it means and what to do;
- **code cells** with their outputs — numbers, tables, figures — so you can read what was done and disagree with it;
- **log views** — the Flight view's chart for a window, with *Open flight*;
- files Claude wrote (a CSV, a figure) beside the notebook;
- a header: who wrote it, its status, the engine version, and whether its outputs are current for this workspace.

It does not hold your logs. A log view draws its window from the flight in your workspace; where that flight is absent, it shows the picture saved with the notebook.

<figure class="diagram">
--8<-- "diagrams/research-notebook.svg"
<figcaption>A notebook on the Research page: header and summary, then narrative, code folded away, outputs and log views.</figcaption>
</figure>

It is an ordinary Jupyter `.ipynb`: it opens in JupyterLab or VS Code, and runs there against your workspace ([Run a notebook in JupyterLab](../walkthroughs/notebook-jupyterlab.md)).

## Keeping

Notebooks live in the workspace and travel with a workspace export. On the Research page, **Re-run** (with EIS on your computer) runs every code cell again on your current flights; outputs that changed wait for you to **Accept** or **Discard**, cell by cell or all at once. That is the cheap way to ask the same question next season. **Delete…** removes a notebook and its files.

## Sharing

Two exports, on the notebook's page:

- **Export notebook (.zip)** — the notebook and its files. Flights are named by fingerprint — a code derived from each log, meaningless to anyone who does not hold the same log.
- **Export as a page (.html)** — one self-contained page anyone can open in a browser, with no EIS at all: the narrative, outputs, figures and log-view pictures. The one to send a mechanic or a manufacturer.

Someone who receives the `.zip` (or a bare `.ipynb`) chooses **Import a notebook…** on their Research page. EIS matches its flights against their workspace: cells whose flights are here are live; cells whose flights are absent show the sender's outputs, read-only, and say so.

## *Run this on my flights*

An imported notebook has one more button: **Run this on my flights.** It copies the notebook as a new one in your workspace — *… — my flights* — and, with EIS on your computer, runs every code cell against your own flights and keeps the outputs. Now the same measurements are about your engine, beside the sender's.

This is how a finding spreads without anyone's logs moving: *here is the notebook that found the oscillation on my aircraft — run it on yours.* The receiving owner's data never leaves their machine, and the sender's never had to.

## What to do with this

Keep a notebook even when it says something dull; re-running it next season is free. Before sending one, export it as a page and read it as the recipient will. When you receive one, run it on your flights before reading the sender's conclusions too closely.

## How it works

Notebooks live in the workspace's `studies/<id>/` folder (`notebook.ipynb` and `files/`) and are carried by workspace export. Their EIS metadata — author, status, question, summary, the inbox item or question it answered — sits in the notebook's own metadata ([The notebook format](../reference/notebook-format.md)). Import always creates a new notebook. Notebooks made before Research became notebook-only open as notebooks, converted on first load.

[Spec 16 — Investigations](https://github.com/AlchemyGeek/Rotax9iSEIS/blob/main/docs/specs/16-investigations.md) §5 defines the notebook, its export and import.
