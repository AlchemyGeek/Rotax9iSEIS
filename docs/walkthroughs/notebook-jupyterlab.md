# Run a notebook in JupyterLab

*Fifteen minutes the first time. An investigation is an ordinary Jupyter notebook: you can open it in JupyterLab, run it top to bottom against your own workspace, change it, and save it — and the Research page shows what you ran. For readers who know Python; nothing here is needed to read a notebook.*

## 1. Install JupyterLab with EIS

JupyterLab needs EIS installed in its own Python. In Terminal, with Python 3.10 or newer, and the `slingology_eis-….whl` file from the [latest release](https://github.com/AlchemyGeek/Rotax9iSEIS/releases/latest) in your Downloads folder:

```bash
python3 -m venv ~/eis-jupyter
~/eis-jupyter/bin/pip install "$(ls ~/Downloads/slingology_eis-*.whl | tail -1)[investigations]" jupyterlab ipykernel
~/eis-jupyter/bin/python -m ipykernel install --user --name slingology-eis --display-name "SlingologyEIS"
```

The last line registers a kernel called **SlingologyEIS**. It reads the same EIS data folder as the pages and the extension, so it sees the same workspaces.

## 2. Find the notebook's file

A notebook lives in your EIS data folder:

```
<data folder>/workspaces/<workspace id>/studies/<study id>/notebook.ipynb
```

- **Data folder**: EIS pages → **Settings → App → Data location**.
- **Workspace id**: on the notebook's page, open the first *show code (setup: binds eis to this workspace)* — it reads `eis.open("ws_…")`.
- **Study id**: the end of the page's address, `#/research/st-…`.

Or work on a copy: **Export notebook (.zip)**, unzip it, and open `notebook.ipynb` from there (your changes then stay in the copy).

## 3. Run it

```bash
~/eis-jupyter/bin/jupyter lab
```

Open `notebook.ipynb`, choose the **SlingologyEIS** kernel, and **Kernel → Restart Kernel and Run All Cells**. The setup cell binds `eis` to the workspace; every later cell uses it — `eis.flights()`, `eis.cycling("full_power", "rpm")`, `eis.logview(...)` ([the eis library](../reference/eis-library.md)). Log views show as pictures in JupyterLab; the EIS pages show them as live charts.

Nothing is fenced in JupyterLab: the kernel is yours, with your permissions, unlike the bench Claude's code runs on.

## 4. Save it, and see it in EIS

Saving in place (**⌘S**) updates the notebook EIS holds — it *is* that file. On the Research page the cells you ran are marked **ran elsewhere**, and the header counts them. Then either:

- **Keep outputs that ran elsewhere** — accept them as they are; or
- **Re-run** — EIS runs the cells again on its own bench, and you accept or discard what changed.

If you saved a copy instead, import it from **Research → Import a notebook…**: it arrives as a new notebook.
