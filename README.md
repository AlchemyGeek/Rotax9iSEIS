# SlingologyEIS — Rotax iS Engine Analytics

**Version 1.1.0** — check yours with `slingology-eis --version`.

Free, open-source engine health analytics for Rotax iS FADEC-controlled aircraft engines
(912iS, 915iS, 916iS), built for how these engines actually work rather than retrofitted
from the mixture-management assumptions behind tools like Savvy Aviation and FlySto. It reads
Garmin EIS logs (G3X, Garmin Pilot exports and Garmin AXIS) and tells you two things about every
flight: did anything go outside the Rotax Operators Manual limits, and is this flight different from how *your* engine usually
behaves. The rules come from Rotax; the expectations come from your own flight history; you decide
what to accept.

It runs in two ways over the same engine, and either way your logs stay in your own folders —
read where they are, never copied or uploaded:

- **In your browser**, from the hosted site — nothing to install. The analysis runs inside the
  browser (Python under Pyodide, in a Web Worker) and your workspace lives in the browser's own
  storage.
- **As a local server on your own computer** — `pip install`, then `slingology-eis serve`, then
  open it in a browser. Nothing listens on the network.

**Status:** 1.1.0 adds the in-browser mode, the pilot documentation site and the Slingology
visual identity to the 1.0.0 web UI. Validated on one aircraft: N117ZS, a Sling TSi with a Rotax
916iS, 58 flights from a set of 120 logs (Garmin G3X, and Garmin AXIS since October 2026). Engine
profiles for the 912iS, 915iS and 916iS are verified against their Operators Manuals. Analytics
topics validated on the 916iS are marked *unverified* on the other engines until data from such
an aircraft exists.

**Pilot documentation:** https://alchemygeek.github.io/Rotax9iSEIS/ — what EIS tells you and why,
concept by concept, with walkthroughs. This README covers getting the app running; the `?` on every
topic card explains what that topic measures. See [CHANGELOG.md](CHANGELOG.md) for what each
release contains and [BACKLOG.md](BACKLOG.md) for what's next.

---

## What you need

Engine log files in CSV format, from any of three Garmin export paths: G3X copied from the SD
card (`log_YYYYMMDD_HHMMSS_ICAO.csv`), a Garmin Pilot export (any name ending in `.csv`), or a
Garmin AXIS export. The format is detected from the file, and a workspace can mix them. Keep
them in a folder of your own; the app reads from it and never changes it.

Tested on macOS Chrome and macOS Safari. (The local server also works from iPad Safari; the
in-browser mode on iPad is not a current target.)

## Running it in your browser

Open the hosted site. The first visit downloads the engine (a few tens of megabytes: the
Pyodide runtime, numpy, pandas and SlingologyEIS); after that it opens in a few seconds. It
still needs the network to load — working fully offline is on the backlog.

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

```bash
pip install slingology-eis
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

1. **Create a workspace.** The app asks for a name and the engine model. A workspace holds the
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
4. **Read.** Each flight has a timeline chart, an events table (Operators Manual limits and CAS
   alerts), and a card per analytics topic. **Trends** shows whether anything about your engine is
   changing against your own history. **Journal** lists every decision you've made in the
   workspace — a filter, a rule edit, an excluded flight, a pinned reference, a note. **Settings**
   shows the engine's limits, the reference and model parameters, and app preferences.

Your reference (what's normal for this engine) is learned only from this workspace's flights, so
the first ten or so flights report *still building* on the baseline comparisons. Nothing learned
from one aircraft is ever applied to another.

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
| Default engine for the CLI | `config.json` (`"engine"`) | Edit freely |
| Insight trigger rules (shipped defaults) | `insight_rules.json`; each workspace keeps its own edited copy | Edit in the app, on the topic card |

## Hosting it yourself

The browser mode is a static site: `npm run build:browser` in `web/` emits one folder —
`index.html`, the UI, `runtime.json`, the pinned Pyodide files and the engine wheel — that any
static web server can serve over HTTPS (GitHub Pages included; nothing depends on special
response headers). A one-command self-hosting option for the server mode (Docker, Synology) is
on the backlog.

---

## Command-line interface

`slingology-eis` runs the same engine from the terminal, without the UI. It is useful for a quick
look at one log, for scripting, and for development; it is not required to use the app.

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
| `export-workspace [--include-logs] [--anonymise] [--out DIR]` | Export a workspace to share: its settings and decisions, optionally with its logs (a zip the recipient unzips). |
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
│   ├── server.py          #   The HTTP transport: /rpc, /upload, /download, the built UI
│   ├── cli.py             #   The slingology-eis command
│   └── help/topics.md     #   Pilot-facing topic explanations (shipped in the package)
├── web/                   # React + TypeScript + Vite UI, both hosts (see web/README.md)
├── engines/               # Engine profiles (see above)
├── contract/schema/       # JSON Schemas for every contract result type
├── docs/                  # Pilot documentation site (MkDocs; docs/README-docs.md), plus:
│   ├── specs/             #   Specs 01–15: engine contract, workspace, UI, filters, topics, trends, runtimes, branding
│   └── ROTAX 91XiS Engine Data Analytics.md   # Research paper
├── mkdocs.yml · PYODIDE_VERSION · scripts/build_engine_wheel.py
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
pip install -e ".[dev]"          # pytest, jsonschema
python -m pytest -q              # Python suite; real-log tests skip without data/logs/
cd web && npm ci
npm run build                    # server-mode UI → web/dist/ (what `serve` serves from a checkout)
npm run build:browser            # the static site for the browser mode
npx vitest run                   # web tests
```

The operations tests run three ways — in-process, over HTTP, and under Pyodide in Node.js — so
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
one of `docs/specs/01`–`15`, each with its own revision history, and
`insight_rules.json`, `engines/*.json` and `docs/specs/topics/register.json` are the data those
specs point at. The Python package depends only on `pandas` and `numpy`; the web UI on React,
React Router and ECharts.

### Notebooks

`notebooks/01`–`04` are the original interactive scripts the toolkit grew from. They call the same
library as the CLI but keep their own rendering, which is why they remain the characterization
tests' independent oracle. `05_limit_events_report.py` prints per-limit event statistics by
weather band; `06_phase_regression.py` is the snapshot tool above. The `notebooks` extra
(`pip install -e ".[notebooks]"`) adds Jupyter, jupytext and matplotlib for them.

---

## Research paper

`docs/ROTAX 91XiS Engine Data Analytics.md` (Edition 0.3) records the analytical methodology,
findings, open questions and design decisions behind the toolkit.

---

## License

MIT — see [LICENSE.md](LICENSE.md).
