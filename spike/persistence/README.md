# Persistence probe (Spec 04 v0.6 §9.4, step 3)

Checks, on a real browser, what the browser host will rely on: OPFS in a
Web Worker, a 50 MB write/read round trip, Pyodide writing Spec 02's
folder layout onto OPFS from Python, and those files still being there
after a reload and after quitting the browser. It also records
`navigator.storage.persist()` and `estimate()`. If OPFS fails, it runs the
same round trip through IndexedDB (IDBFS) instead.

It uses generated data only: no flight log is read, and the results file
holds measurements only.

## Safari on your Mac — about ten minutes

1. **Serve the folder.** In Terminal, from the repo:

   ```bash
   cd spike/persistence
   python3 -m http.server 8000
   ```

   Leave it running.

2. **Open the page in Safari:** <http://localhost:8000/>.
   - Use `localhost`: browsers treat it as a secure site, which OPFS needs.
   - Use a normal window, not a Private one.

3. **Wait.** The page runs step 1/3 (about 10 s; the first time it
   downloads Pyodide, about 30 MB), then **reloads itself** and runs
   step 2/3.

4. **When it says "Now quit the browser completely":**
   - Quit Safari with ⌘Q (closing the window isn't enough).
   - Reopen Safari and go to <http://localhost:8000/> again.
   - If Safari reopened the old tab by itself, press **"I restarted the
     browser — check now"**.

5. **Download.** When it says *Done*, click **Download results (JSON)**.
   - The file goes to your Downloads folder as `persistence-safari-….json`.
   - Copy it into `spike/persistence/results/`.

6. Stop the server with Ctrl-C.

To run it again from the start, press **Reset the probe** (it removes the
probe's own files and markers, nothing else).

### What to watch for on Safari

- If step 1/3 fails on **3. Pyodide on OPFS**, the page runs the IDBFS
  fallback automatically. Note the error text shown in the table.
- **6. persist()** may say `false`. Safari usually grants it only to a
  site added to the Dock or home screen. Record it either way.
- If Safari asks whether to allow the site to store data, choose **Allow**.
  Note that it asked.

## Chromium (automated)

```bash
.venv/bin/python spike/persistence/run_chromium.py           # headless
.venv/bin/python spike/persistence/run_chromium.py --idbfs   # also run the IDBFS fallback
```

- It drives the installed Google Chrome through Playwright, so no browser
  is downloaded. It needs the `playwright` Python package and the network
  (for Pyodide from the jsDelivr CDN).
- It runs the first visit and the reload, quits the browser, relaunches it
  on the same profile for the restart check, and saves
  `results/chromium-<time>.json`.

## Files

| File | What |
|---|---|
| `index.html` | The page: sequences the three visits, calls `persist()`, keeps the eviction marker, shows and downloads the results |
| `probe-worker.js` | The checks that need a worker: OPFS, the round trip, Pyodide on OPFS, IDBFS |
| `run_chromium.py` | The Chromium runner |
| `results/` | One JSON per run |
