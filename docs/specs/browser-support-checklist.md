# Browser support checklist (Spec 04 §9.6)

The manual release checks for the in-browser app, run on **macOS Chrome** and **macOS Safari** before
each release. The automated runs (`spike/browser-host/run_walkthrough.py`, `run_offline.py`,
`run_parity.py`) cover the same ground headless in Chrome; these steps cover what they can't — the real
folder picker, permission prompts, Safari, and a browser restart.

Use the release's site (the CI artifact, unzipped and served as plain files, or the published URL), a
copy of a few real logs in a folder of their own, and a browser profile with no data for the site:
Chrome → Settings → Privacy → Site data, or Safari → Settings → Privacy → Manage Website Data. Note the
browser version at the top of the run.

| # | Step | Expected |
|---|---|---|
| 1 | Open the site. | *Setting up the analysis engine… Downloading about 30 MB, once*, with progress; then the app, with **+ New workspace** in the top bar. |
| 2 | **+ New workspace**, give it a name, **Create**. | Flights for the new workspace, with the drop area and **Choose folder…**. |
| 3 | **Choose folder…** and pick the log folder. | Chrome: the system folder picker. Safari: the folder dialog, then the browser's upload confirmation. The folder appears as a row; the top button reads *Analyze N*. |
| 4 | Click **Analyze N**. | A progress line counting the logs (*Analyzing k/N*); then the flights listed, and *N new flights analyzed*. |
| 5 | Open a flight. | The flight view: facts, insights, the timeline chart with the phase strip, Events. |
| 6 | **Edit rules…** on a card, change a value, **Apply to all flights**. | The card marks *rule changed*; Journal lists the edit. |
| 7 | Settings → App → **Export workspace…** with *Include logs*. | A `.zip` download. |
| 8 | Quit the browser fully (⌘Q) and open the site again. | *Starting the analysis engine… Loading from this device*; the workspace is there. Chrome: the folder row offers **Allow access**. Safari: the row reads **Not connected — reconnect**, with a one-time note about Safari. |
| 9 | Chrome: **Allow access**. Safari: **Not connected — reconnect** and pick the same folder. | The row is connected again. |
| 10 | **Sync**. | *No changes* — nothing re-analysed. |
| 11 | Settings → App → **Storage**. | Space used (a few MB), *Persistent: yes* or *no*, **Export all workspaces…**, **Delete all data on this device**. |
| 12 | Turn Wi-Fi off. Reload the page, then quit the browser and open the site again. | Both times the app opens from this device; a flight opens with its chart. |
| 13 | With Wi-Fi still off, drop one log file on Flights. | It is analysed and listed. |
| 14 | Wi-Fi on. **Delete all data on this device**, confirm. | The first-run state — **+ New workspace**, no workspaces — without a reload; nothing from the old workspace anywhere. |
| 15 | Settings → App → **Import workspace…**, pick the export from step 7. | The workspace with its flights and the rule edit from step 6. |

After a new build is published, open the site once more with Wi-Fi on: within a few seconds the page
reloads and says **Updated to version …** once; Settings → Engine's About line shows the new version.

Record the outcome per browser — pass, or the step that failed and what was seen — in the release notes
or the session report.
