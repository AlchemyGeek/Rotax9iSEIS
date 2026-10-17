# SlingologyEIS — Rotax iS Engine Analytics

**Version 1.0.0** — check yours with `slingology-eis --version`.

Free, open-source engine health analytics for Rotax iS FADEC-controlled aircraft engines
(912iS, 915iS, 916iS), built for how these engines actually work rather than retrofitted
from the mixture-management assumptions behind tools like Savvy Aviation and FlySto. It reads
Garmin G3X EIS logs and tells you two things about every flight: did anything go outside the
Rotax Operators Manual limits, and is this flight different from how *your* engine usually
behaves. The rules come from Rotax; the expectations come from your own flight history; you decide
what to accept.

It runs as a local web app on your own computer. Your logs stay in your own folders — the app
references them, never copies or uploads them — and nothing listens on the network.

**Status:** 1.0.0 is the first release with the web UI, merged from the `webui` branch on
October 15, 2026. Validated on one aircraft: N117ZS, a Sling TSi with a Rotax 916iS — 53 flights
from a set of 115 logs. Engine profiles for the 912iS, 915iS and 916iS are verified against their
Operators Manuals. Analytics topics validated on the 916iS are
marked *unverified* on the other engines until data from such an aircraft exists.

See [CHANGELOG.md](CHANGELOG.md) for what 1.0.0 contains and the full version history, and
[BACKLOG.md](BACKLOG.md) for what's next. A documentation site for pilots is planned; until then
this README covers getting the app running, and the `?` on every topic card explains what that
topic measures.

---

## Running the app on your computer

### What you need

- **Python 3.10 or later** — runs the analysis engine and the local server.
- **Node.js 20 or later** — only to build the web UI once. (A packaged build that removes this
  step is on the backlog.)
- G3X log files in CSV format: either copied from the SD card
  (`log_YYYYMMDD_HHMMSS_ICAO.csv`) or exported from Garmin Pilot (any name ending in `.csv`).
  Both formats are detected automatically and can be mixed.

### Install

```bash
git clone https://github.com/AlchemyGeek/Rotax9iSEIS.git
cd Rotax9iSEIS
pip install -e .                      # the engine and the slingology-eis command
cd web && npm ci && npx vite build && cd ..   # build the web UI once into web/dist/
```

`pip install -e .` brings in the only runtime dependencies, `pandas` and `numpy`.

> `npm run build` currently fails its type check on one test file; `npx vite build` produces the
> same `web/dist/` and is what the command above uses. See BACKLOG.

### Start

```bash
slingology-eis serve
```

prints

```
SlingologyEIS local server: http://127.0.0.1:8420/  (workspace: ...)
POST /rpc for the API. Ctrl-C to stop.
```

Open **http://127.0.0.1:8420/** in your browser (tested on macOS Chrome, macOS Safari and iPad
Safari). Use `--port` for a different port. Leave the terminal open; `Ctrl-C` stops the server.

### First use

1. **Create a workspace.** The app asks for a name and the engine model. A workspace holds the
   derived results for one aircraft — analyses, your reference, filters, notes, the Journal — and
   you can have as many as you like (another aircraft, or an experiment on a subset of your logs),
   one active at a time. The engine model is fixed when the workspace is created; a workspace is
   deleted from the Flights page with a typed `DELETE` confirmation.
2. **Add your logs.** On the Flights page, *Add logs…* → *Add a folder* and type the path to the
   folder your G3X logs live in (subfolders are included); or drop files onto the page. Add as
   many folders as you want. The app only references them: rename, move or add logs and *Sync*
   finds them again.
3. **Analyze.** Sync tells you what it found — *"Found N new logs. Analyze now?"* — and analyses
   with per-flight progress when you say yes. A large first folder takes a minute or two. Logs
   that are not flights (a ground run, a flight shorter than 10 minutes, a log with a gap in it)
   are listed under *Skipped* with the reason, and can be included.
4. **Read.** Each flight has a timeline chart, an events table (Operators Manual limits and CAS
   alerts), and a card per analytics topic. **Trends** shows whether anything about your engine is
   changing against your own history. **Journal** lists every decision you've made in the
   workspace — a filter, a rule edit, an excluded flight, a pinned reference, a note. **Settings**
   shows the engine's limits, the reference and model parameters, and app preferences.

Your reference (what's normal for this engine) is learned only from this workspace's flights, so
the first ten or so flights report *still building* on the baseline comparisons. Nothing learned
from one aircraft is ever applied to another.

### Where things are stored

| What | Where | Yours? |
|---|---|---|
| Your logs | Wherever you keep them | Yes — never copied or modified |
| Workspaces (derived results) | `~/SlingologyEIS/workspaces/<id>/` for a packaged install, `data/workspaces/` in a git checkout; `registry.json` beside them | Derived; safe to delete and rebuild |
| Default engine for the CLI | `config.json` (`"engine"`) | Edit freely |
| Insight trigger rules (shipped defaults) | `insight_rules.json`; each workspace keeps its own edited copy | Edit in the app, on the topic card |

### Other ways to run it

Only the local server exists today. The engine is pure Python on `pandas`/`numpy` and has already
been proven to run in the browser under Pyodide (`docs/specs/04-runtime-adapters-and-pyodide-spike.md`,
decision GO), so a hosted static site where the analysis runs entirely in your browser, and an
easy self-hosting option, are planned next. The local server will keep working alongside them.

---

## Command-line interface

`slingology-eis` runs the same engine from the terminal, without the UI. It is useful for a quick
look at one log, for scripting, and for development; it is not required to use the app.

```bash
slingology-eis <command> [options]
slingology-eis --help           # every command
slingology-eis <command> --help # that command's options
```

**Global options** (before or after the subcommand):

| Option | Meaning |
|---|---|
| `--logs DIR` | Folder of G3X CSVs. Default: `data/logs/` in a git checkout, `~/SlingologyEIS/logs/` for a packaged install. |
| `--workspace NAME_OR_PATH` | A registered workspace's name or id, or a folder path for derived results. Default: `data/` in a git checkout, `~/SlingologyEIS/workspace/` packaged. |
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
│   ├── workspace.py       #   Workspace registry, manifests, scans, Journal, settings changelog
│   ├── server.py          #   The local HTTP server: /rpc operations and web/dist
│   ├── cli.py             #   The slingology-eis command
│   └── help/topics.md     #   Pilot-facing topic explanations (shipped in the package)
├── web/                   # React + TypeScript + Vite UI (see web/README.md)
├── engines/               # Engine profiles (see above)
├── contract/schema/       # JSON Schemas for every contract result type
├── docs/specs/            # Specs 01–14: the engine contract, workspace, UI, filters, topics, trends…
├── docs/ROTAX 91XiS Engine Data Analytics.md   # Research paper
├── notebooks/             # Diagnostic scripts: 01–04 legacy reports, 05 limit events, 06 phase regression
├── tests/                 # pytest: unit, contract, cli, characterization (goldens gitignored)
├── spike/                 # Pyodide feasibility harness (Spec 04)
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
cd web && npm ci && npx vitest run && npx vite build
```

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
same engine is what a future in-browser (Pyodide) build will run. Design is spec-first: every
behaviour is owned by one of `docs/specs/01`–`14`, each with its own revision history, and
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
