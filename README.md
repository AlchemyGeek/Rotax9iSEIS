# SlingologyEIS — Rotax iS Engine Analytics

**Version 1.1.2** — check yours with `slingology-eis --version`.

Free, open-source engine health analytics for Rotax iS FADEC-controlled aircraft engines
(912iS, 915iS, 916iS), built for how these engines actually work rather than retrofitted
from the mixture-management assumptions behind tools like Savvy Aviation and FlySto. It reads
Garmin EIS logs (G3X, Garmin Pilot exports, and the Garmin AXIS's SD-card log and aircraft log) and tells you two things about every
flight: did anything go outside the Rotax Operators Manual limits, and is this flight different from how *your* engine usually
behaves. The rules come from Rotax; the expectations come from your own flight history; you decide
what to accept.

It runs in three ways over the same engine, and every way your logs stay in your own folders —
read where they are, never copied or uploaded:

- **In your browser**, from https://alchemygeek.github.io/Rotax9iSEIS/app/ — nothing to install. The analysis runs inside the
  browser (Python under Pyodide, in a Web Worker) and your workspace lives in the browser's own
  storage.
- **As a local server on your own computer** — `pip install`, then `slingology-eis serve`, then
  open it in a browser. Nothing listens on the network.
- **As a Claude Desktop extension** — one `.mcpb` file from the
  [latest release](https://github.com/AlchemyGeek/Rotax9iSEIS/releases/latest), nothing else to
  install. Your own Claude investigates your engine with EIS's instruments and writes the
  investigation as a notebook; the EIS pages run at `127.0.0.1:8420` while Desktop is open. See
  *Investigations* below.

**Status:** 1.1.0 adds *Investigations*: a Claude Desktop extension through which your own Claude
asks questions of your flights with EIS's deterministic instruments, reads the Operators Manual
and service bulletins from your folders, and writes a Jupyter notebook you read in the app or run
in JupyterLab; period/swing strips and *Mark for Claude* on the flight chart; an inbox that raises
recurring patterns; routes resolved from GPS; an aircraft record with your notes and documents.
It also ships the 1.0.2 aircraft-log work (the second AXIS log Garmin Pilot uploads to flyGarmin,
merged with the SD-card log of the same flight). Validated on one aircraft: N117ZS, a Sling TSi
with a Rotax 916iS, 62 flights from a set of 125 logs (Garmin G3X, and since October 2026 the
Garmin AXIS); the acceptance case is its takeoff rpm oscillation
(`docs/research/2026-10-takeoff-rpm-oscillation.md`). Engine profiles for the 912iS, 915iS and
916iS are verified against their Operators Manuals. Analytics topics validated on the 916iS are
marked *unverified* on the other engines until data from such an aircraft exists.

**Pilot documentation:** https://alchemygeek.github.io/Rotax9iSEIS/ — what EIS tells you and why,
concept by concept, with walkthroughs. This README covers getting the app running; the `?` on every
topic card explains what that topic measures. See [CHANGELOG.md](CHANGELOG.md) for what each
release contains and [BACKLOG.md](BACKLOG.md) for what's next.

**Bugs and feature requests:** https://feedback.slingology.synology.me/ — no GitHub account
needed. The speech-bubble icon in the app's top bar opens it; quote the *This build* line from
Settings → App → About in a bug report.

---

## What you need

Engine log files in CSV format, in any of four Garmin formats:

| Shown as | What it is |
|---|---|
| *G3X* | A G3X log copied from the SD card (`log_YYYYMMDD_HHMMSS_ICAO.csv`) |
| *Garmin Pilot* | Garmin Pilot's export of a G3X log (any name ending in `.csv`) |
| *AXIS card* | A Garmin AXIS log copied from its SD card |
| *Aircraft log* | The log the AXIS hands to Garmin Pilot, downloaded from flyGarmin as `aircraft-log-<IDENT>-<UTC start>.csv`. The tail number is read from this file name, so keep it |

The format is detected from the file, and a workspace can mix them. The same flight in two
formats is one flight: a G3X log and its Garmin Pilot export collapse to the more complete file;
an AXIS card log and the aircraft log of the same flight are both kept and the aircraft log is
analysed (it always covers the whole power-up, with the engine start, a reliable clock and the
throttle position). Keep the logs in a folder of your own; the app reads from it and never
changes it.

No logs of your own yet? The [sample workspace](https://github.com/AlchemyGeek/Rotax9iSEIS/releases/tag/sample-workspace)
— 19 flights of N117ZS with its owner's filters — imports from Settings → App → *Import workspace…*.

Tested on macOS Chrome and macOS Safari. (The local server also works from iPad Safari; the
in-browser mode on iPad is not a current target.) Investigations need Claude Desktop on macOS
(Apple silicon or Intel) and a Claude account; the extension bundles everything else.

## Running it in your browser

Open https://alchemygeek.github.io/Rotax9iSEIS/app/. The first visit downloads the engine (about
30 MB: the Pyodide runtime, numpy, pandas and SlingologyEIS) and keeps it; after that the app
opens in a few seconds and works with no network. When a new version is published, the next
visit with a network switches to it and says *Updated to version …* once.

- **Your workspace is in this browser.** It is kept in the browser's origin private file system
  and survives reloads and restarts. Settings → App → *Storage* shows the space used, whether the
  browser has granted persistent storage, *Export all*, and *Delete all data*. Clearing site data
  in the browser deletes it too, so export before you do.
- **Your logs stay in your folder.** On Flights, *Choose folder…* points the app at the folder
  with your logs (subfolders included). Chrome remembers the folder — on the next visit click
  *Allow access* once. Safari can't keep folder access between visits: your analyses are still
  there, and *Not connected — reconnect* is only needed to sync new logs or open a chart. You can
  also drop a folder onto the page in either browser.
- Everything else — Sync, Flight view, Trends, Journal, Settings, export and import — is the same
  as the server mode. Exports arrive as ordinary downloads.

## Running the local server

Python 3.10 or later.

Download the `slingology_eis-….whl` file from the latest
[release](https://github.com/AlchemyGeek/Rotax9iSEIS/releases), then:

```bash
pip install slingology_eis-*.whl
slingology-eis serve
```

prints

```
SlingologyEIS local server: http://127.0.0.1:8420/  (workspace: ...)
POST /rpc for the API. Ctrl-C to stop.
```

Open **http://127.0.0.1:8420/** in your browser. Use `--port` for a different port. Leave the
terminal open; `Ctrl-C` stops the server. The package carries the built web UI, the engine
profiles and the topic help; its only runtime dependencies are `pandas` and `numpy`.

From a git checkout, `pip install -e .` then build the UI once (`cd web && npm ci && npm run
build`, Node.js 20 or later) before `serve` — see *For developers*.

## First use

1. **Create a workspace** — from logs you pick, from a workspace export, or by loading a folder
   of logs. The app asks for a name and the engine model. A workspace holds the
   derived results for one aircraft — analyses, your reference, filters, notes, the Journal — and
   you can have as many as you like (another aircraft, or an experiment on a subset of your logs),
   one active at a time. The engine model is fixed when the workspace is created; a workspace is
   deleted from the Flights page with a typed `DELETE` confirmation.
2. **Add your logs.** On the Flights page, choose the folder your logs live in — in the browser
   mode with *Choose folder…*, in the server mode with *Add logs…* → *Add a folder* and the
   folder's path (subfolders are included); or drop files or a folder onto the page. Add as many
   folders as you want. The app only references them: rename, move or add logs and *Sync* finds
   them again.
3. **Analyze.** Sync tells you what it found — *"Found N new logs. Analyze now?"* — and analyses
   with per-flight progress when you say yes. A large first folder takes a minute or two. Logs
   that are not flights (a ground run, a flight shorter than 10 minutes, a log with a gap in it)
   are listed under *Skipped* with the reason, and can be included; a file the app can't read is
   listed as *Unreadable* with the reason.
4. **Read.** Each flight has a timeline chart (zoom to ten minutes or less for every reading; a
   selected limit event is marked where it started and where it reached its worst value), an events table (Operators Manual limits and CAS
   alerts), and a card per analytics topic. **Trends** shows whether anything about your engine is
   changing against your own history. **Journal** lists every decision you've made in the
   workspace — a filter, a rule edit, an excluded flight, a pinned reference, a note. **Settings**
   shows the engine's limits, the reference and model parameters, app preferences (units,
   light or dark theme, and the build you are running), the **aircraft** record (propeller,
   controller, firmware, your notes for Claude, your manuals' folders) and **Research** (inbox
   sensitivity). The **Flights** list shows each flight's route, resolved from GPS, and *Find a
   flight* searches by description; a flight can be named in place.

Your reference (what's normal for this engine) is learned only from this workspace's flights, so
the first ten or so flights report *still building* on the baseline comparisons. Nothing learned
from one aircraft is ever applied to another.

## Investigations — your Claude and your engine

EIS tells you *what* crossed a limit and *whether* your engine is changing. Investigating *why*
— the oscillation that is not an exceedance, the temperature that is higher only in one kind of
flight — takes a scientist's loop: look at one flight, then across all of them, propose a
mechanism, rule out the alternatives, say what it means. 1.1.0 gives that loop to your own Claude.

**How it works.** *Claude investigates; EIS measures.* The Claude Desktop extension runs the EIS
engine on your computer and exposes it to Claude as 33 tools: your flights (with routes and
names), slices of them, the four deterministic questions (*is this signal cycling? do these two
move together? are these groups different? which slice is unusual?*), a sandboxed Python bench
with the `eis` library, your aircraft record and notes, and the manuals in your folders. Claude
writes what it finds as a Jupyter notebook in your workspace; the Research page renders it with
live flight charts, and it opens and runs unchanged in JupyterLab. Nothing is sent anywhere except
Claude Desktop's own conversation with Anthropic; EIS stores nothing outside your data folder.

**The loop in the app.**

1. **Look.** On a flight, turn on *Signal*: strips over the whole flight light where a channel
   cycles; zoom in and the window's swing, period and coupling appear beside their Operators
   Manual references.
2. **Mark.** *Mark for Claude* on any zoomed window — a note, and the question it belongs to. Your
   questions sit in the Research page's inbox beside what EIS raised itself (a recurring pattern
   in your recent flights, found by a scan after each import; nothing runs unattended).
3. **Ask.** In Claude Desktop, `+` → *SlingologyEIS* → *Investigate* (or *Look at this inbox
   item*, *Before/after*, *Review new flights*). Claude calls `guide` first — the method and your
   aircraft's context — and starts from your marks.
4. **Read.** The notebook on the Research page: one flight first, then across flights, the
   mechanism as a hypothesis, alternatives ruled out, what to do; every number from an `eis`
   function with its reference beside it. A log-view cell takes you back to the flight.

**Install.** Download `slingology-eis-<version>-macos-arm64.mcpb` (Intel Macs: `x86_64`) from the
release; in Claude Desktop, Settings → Extensions → Advanced settings → *Install Extension…*; set
the *EIS data folder* (default `~/SlingologyEIS`); quit and reopen Desktop. The bundle is unsigned
for now, so Desktop warns once. Been using the website? Open it with Desktop running and press
**Move my workspace** — your browser workspace is imported into the extension in one step; from
then on you work at `127.0.0.1:8420`. Developers can instead `pip install -e ".[investigations]"`
and add `slingology-eis mcp` to `claude_desktop_config.json` (Spec 16 §7).

**JupyterLab.** `python -m ipykernel install --user --name slingology-eis` in the environment
where the package is installed; a notebook's first cell binds `eis` to your workspace. Outside
EIS there is no sandbox — it is your own kernel.

The documentation site's *Investigating your engine* section has the walkthroughs; Spec 16
(`docs/specs/16-investigations.md`) is the design, Spec 06 the instrument.

## Sharing a workspace

Settings → App → *Export workspace…* writes a file you can send to another pilot or to someone
helping you read your engine: your settings and decisions with a list of your flights, and — with
*Include logs* — the logs themselves in one zip. *Anonymise logs* replaces the aircraft with a
pseudonym and blanks the position, nav and radio columns; the dialog shows where your own notes
still name the aircraft. The recipient uses *Import workspace…* (or the workspace switcher) on the
file as is and gets a new workspace with your flights and decisions.

## Where things are stored

| What | Where | Yours? |
|---|---|---|
| Your logs | Wherever you keep them | Yes — never copied or modified (an imported export's logs are copied into that workspace) |
| Workspaces (derived results), browser mode | The browser's origin private file system for the site, same layout as below; Settings → App → *Storage* | Derived; export before clearing site data |
| Workspaces (derived results), server mode | The *data location*: `~/SlingologyEIS/` by default (`data/` in a git checkout), holding `registry.json`, app settings and `workspaces/<id>/`. Change it from Settings → App or `slingology-eis data-location set PATH`; the choice is kept in a per-user `location.json`, and `SLINGOLOGY_EIS_HOME` overrides it | Derived; safe to delete and rebuild |
| Aircraft record and notes | `aircraft/<id>/` in the data location (`aircraft.json`, `notes.md`); documents folders are paths to your own folders, read in place, with an index cache under `cache/documents/` | Yours; the cache is derived |
| Investigation notebooks | `workspaces/<id>/studies/<id>/notebook.ipynb` + `files/` — standard Jupyter notebooks | Yours; carried by export |
| Default engine for the CLI | `config.json` (`"engine"`) | Edit freely |
| Insight trigger rules (shipped defaults) | `insight_rules.json`; each workspace keeps its own edited copy | Edit in the app, on the topic card |

## Hosting it yourself

The browser mode is a static site: `npm run build:browser` in `web/` emits one folder —
`index.html`, the UI, `runtime.json`, the pinned Pyodide files and the engine wheel — that any
static web server can serve over HTTPS (GitHub Pages included; nothing depends on special
response headers). [docs/hosting.md](docs/hosting.md) describes how the project's own copy is
published beside the documentation and how a release is tagged. A one-command self-hosting option for the server mode (Docker, Synology) is
on the backlog.

---

## Command-line interface

`slingology-eis` runs the same engine from the terminal, without the UI. It is useful for a quick
look at one log, for scripting, and for development; it is not required to use the app.
`slingology-eis mcp` is the MCP server Claude Desktop runs (`mcp tools` lists the tools;
`mcp call <tool> '<json>'` calls one).

```bash
slingology-eis <command> [options]
slingology-eis --help           # every command
slingology-eis <command> --help # that command's options
```

**Global options** (before or after the subcommand; the one nearer the subcommand wins):

| Option | Meaning |
|---|---|
| `--logs DIR` | Folder of log CSVs. Default: `data/logs/` in a git checkout, `~/SlingologyEIS/logs/` for a packaged install. |
| `--workspace NAME_OR_PATH` | A registered workspace's name or id, or a folder path for derived results. Default: the active workspace in the data location. |
| `--engine NAME` | Engine profile. Resolved as `--engine` → `SLINGOLOGY_ENGINE` env var → `config.json` → `916iS`. |
| `--json` | Print the result as JSON (validates against `contract/schema/`). |
| `--anonymize` | Strip aircraft ident, system id and airport from `--json` output. |
| `--quiet` | Suppress progress on stderr. |

**Exit codes:** `0` success, `1` the operation failed (bad path, malformed log), `2` usage error or
a not-yet-implemented command.

| Command | Purpose |
|---|---|
| `serve [--port N]` | Start the local server and web UI (default port 8420). |
| `engines` | List engine profiles and their verification status. |
| `flight LOG` | Analyze one flight — a filename (resolved against `--logs`) or a path. |
| `report LOG` | Plain-language per-flight report, evaluated against the workspace's reference and filters. |
| `fleet` | Build the reference, trends and models from every log in `--logs`; writes the workspace cache. |
| `import [PATHS...]` | Analyze logs or folders into the workspace without printing a report. |
| `flights [--show-excluded]` | List known flights, and which are excluded from the reference and why. |
| `exclude FILE --reason TEXT` / `include FILE` | Exclude a flight from the reference, or bring one back. |
| `ecu [LOGS...]` | ENGINE ECU runs across flights, classified by phase (ground start, lane check, ground, in flight, shutdown). |
| `explain [TOPIC]` | The pilot-facing explanation of one topic, or all of them. |
| `rules check FILE` / `rules try FILE --flight LOG` | Validate a rules file; diff the insights it would produce for one flight. |
| `workspace list` / `workspace create NAME [--tail-number N]` | Manage registered workspaces. |
| `data-location [set PATH]` | Show where workspaces are kept and how that was decided, or move them. |
| `export-workspace [--include-logs] [--anonymise] [--out DIR]` | Export a workspace to share: its settings and decisions, optionally with its logs in one zip. |
| `import-workspace PATH [--name N] [--logs FOLDER] [--yes]` | Import an export as a new workspace, match its flights to the logs, and analyse after confirming. |

```bash
slingology-eis engines
slingology-eis flight log_20260423_200615_KACV.csv --json
slingology-eis report log_20260423_200615_KACV.csv
slingology-eis explain overboost_time
```

---

## Engine profiles

`engines/<model>.json` holds each engine's operating limits, sourced from its Operators Manual
with the edition cited in the file. The OM text itself is never stored in the repository.

| Profile | Source | Status |
|---|---|---|
| `916iS` | OM-916 i/C24, Edition 0 / Rev. 1 (Dec 2023) | VERIFIED |
| `915iS` | OM-915 i A/C24, Edition 0 / Rev. 4 (Sep 2022) | VERIFIED |
| `912iS` | OM-912 i Series, Edition 2 / Rev. 2 (Sep 2025) | VERIFIED — no MAP or EGT-split limit, as the OM defines none |

Beyond the limits, a profile declares how each limit is checked (phase-aware suppression, minimum
duration, engine-running gates), whether a pilot may filter it and on what terms, the ENGINE ECU
run-extraction parameters, the lane-check run-up band, and the expected hottest cylinder.
`slingology-eis engines` lists what's installed.

Which analytics topics exist, why, and their status per engine is recorded in
`docs/specs/10-analytics-topic-admission.md` and `docs/specs/topics/register.json`.

---

## For developers

### Repository layout

```
Rotax9iSEIS/
├── slingology_eis/        # The engine (pure Python, pandas + numpy), CLI, local server, workspaces
│   ├── operations.py      #   The engine contract: analyze_flight, analyze_ecu, update_fleet,
│   │                      #   evaluate_insights, get_topic_help, filters, trends
│   ├── loader.py, phases.py, limits.py, egt.py, fuel.py, cas.py, climb.py, fleet.py,
│   │   baselines.py, topics.py, filters.py, trends.py, exclusions.py, presets.py, channels.py
│   ├── host.py            #   The transport-neutral host: the operations, dispatcher, capabilities
│   ├── browser_host.py    #   The Web Worker's Python entry (Pyodide, OPFS data root)
│   ├── log_sources.py     #   Where logs come from: disk, or supplied by the page
│   ├── workspace.py       #   Workspace registry, manifests, scans, Journal
│   ├── workspace_export.py, data_location.py   # Sharing a workspace; where the data root lives
│   ├── server.py          #   The HTTP transport: /rpc, /upload, /download, the built UI, /eis/probe + move-workspace
│   ├── investigations/    #   Spec 16: MCP server (mcp_server.py, mcp_tools.py), bench (bench*.py), the eis
│   │                      #   library (eis_lib.py), notebooks (notebook.py, ipynb.py, nbhtml.py), inbox, pins,
│   │                      #   documents, aircraft, guide.md and prompts/, the extension entry (extension.py)
│   ├── research/          #   Spec 06, the instrument: slices, descriptors, the four tests, analyze_signal
│   ├── eis.py             #   `from slingology_eis import eis` — the library for notebooks outside EIS
│   ├── cli.py             #   The slingology-eis command
│   └── help/topics.md     #   Pilot-facing topic explanations (shipped in the package)
├── web/                   # React + TypeScript + Vite UI, both hosts (see web/README.md)
├── engines/               # Engine profiles (see above)
├── contract/schema/       # JSON Schemas for every contract result type
├── docs/                  # Pilot documentation site (MkDocs; docs/README-docs.md), plus:
│   ├── specs/             #   Specs 01–16: engine contract, workspace, UI, filters, topics, trends, runtimes, branding, research, investigations
│   ├── research/          #   The owner's investigation write-ups (the takeoff rpm oscillation)
│   └── ROTAX 91XiS Engine Data Analytics.md   # Research paper
├── mkdocs.yml · PYODIDE_VERSION · scripts/build_engine_wheel.py · scripts/build_extension.py (the .mcpb)
├── notebooks/             # Diagnostic scripts: 01–04 legacy reports, 05 limit events, 06 phase regression
├── tests/                 # pytest: unit, contract, cli, characterization (goldens gitignored)
├── spike/                 # Spec 04 harnesses: Pyodide feasibility, persistence probe, browser-host parity
├── config.json            # Default engine, min_flight_duration_min
├── insight_rules.json     # Shipped insight trigger rules
├── chart_presets.json     # Shipped chart presets
├── CLAUDE.md              # Working notes for Claude Code sessions (test data, regression rule)
├── CHANGELOG.md · BACKLOG.md · LICENSE.md
```

### Setup and tests

```bash
pip install -e ".[dev,investigations]"   # pytest, jsonschema; the MCP server, bench and eis library
python -m pytest -q              # Python suite; real-log tests skip without data/logs/
cd web && npm ci
npm run build                    # server-mode UI → web/dist/ (what `serve` serves from a checkout)
npm run build:browser            # the static site for the browser mode
npx vitest run                   # web tests
```

`slingology-eis mcp tools` lists the MCP tools; `slingology-eis mcp` is the stdio server Claude
Desktop runs (`SLINGOLOGY_EIS_HOME` selects the data root). The operations tests run three ways — in-process, over HTTP, and under Pyodide in Node.js — so
the browser host is checked without a browser; `web/README.md` describes the two hosts, the
engine wheel (`scripts/build_engine_wheel.py`, version pinned in `PYODIDE_VERSION`) and the
parity and walk-through runs under `spike/browser-host/`.

Real flight logs are private and gitignored (`/data/`). The characterization, contract and CLI
tests that need them, and the frozen goldens under `tests/characterization/golden/`, skip
automatically when absent; `CLAUDE.md` explains how a session gets the private log set. Never
commit logs or anything derived from them.

Before changing phase detection, limit checking or per-flight metrics, snapshot and compare:

```bash
python notebooks/06_phase_regression.py --save before
# make the change
python notebooks/06_phase_regression.py --compare before
```

### How the pieces fit

The engine (`operations.py`) is stateless: bytes in, typed results out, validated against
`contract/schema/`. Everything else — CLI, local server, web UI — is a host around it, and the
same engine runs in the browser under Pyodide. Design is spec-first: every behaviour is owned by
one of `docs/specs/01`–`16`, each with its own revision history, and
`insight_rules.json`, `engines/*.json` and `docs/specs/topics/register.json` are the data those
specs point at. The Python package depends only on `pandas` and `numpy`; the web UI on React,
React Router and ECharts.

### Notebooks (the repo's diagnostic scripts)

Not the investigation notebooks above. `notebooks/01`–`04` are the original interactive scripts the toolkit grew from. They call the same
library as the CLI but keep their own rendering, which is why they remain the characterization
tests' independent oracle. `05_limit_events_report.py` prints per-limit event statistics by
weather band; `06_phase_regression.py` is the snapshot tool above. The `notebooks` extra
(`pip install -e ".[notebooks]"`) adds Jupyter, jupytext and matplotlib for them.

---

## Research paper

`docs/ROTAX 91XiS Engine Data Analytics.md` (Edition 0.4) records the analytical methodology,
findings, open questions and design decisions behind the toolkit. It is also published on the
documentation site: https://alchemygeek.github.io/Rotax9iSEIS/reference/research-paper/

---

## License

MIT — see [LICENSE.md](LICENSE.md).
