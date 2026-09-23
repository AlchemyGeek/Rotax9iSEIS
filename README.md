# SlingologyEIS — Rotax iS Engine Analytics Toolkit

**Version: 0.11.0** — verify with `slingology-eis --version` or `python -c "import slingology_eis; print(slingology_eis.__version__)"`

Free, open-source engine health analytics for Rotax iS FADEC-controlled aircraft engines (912iS, 914iS, 915iS, 916iS). Built from the ground up for how these engines actually work — not retrofitted from the carbureted-engine assumptions that underpin existing tools like Savvy Aviation and FlySto. Analyses Garmin G3X EIS logs against Rotax Operators Manual limits, automatically detects flight phases, tracks EGT spread and cylinder balance over engine hours, classifies CAS alerts, monitors overboost time, builds personal baselines from your own flight history, and produces plain-language per-flight reports — all offline, with your data never leaving your machine.

**Current status:** Python toolkit v0.11.0, validated against 37 flights on N117ZS (Sling TSi, Rotax 916iS, KPAE). Engine profiles 916iS and 915iS are fully verified against their Operators Manuals; 912iS and 914iS are placeholders pending verification. As of v0.11.0 the toolkit is built around a stateless, typed engine contract (see [`docs/specs/01-engine-contract.md`](docs/specs/01-engine-contract.md)) with a unified command-line interface — the same contract a future browser UI will run against unmodified. Long-term goal is a free progressive web app for any Sling / Rotax iS pilot.

See [CHANGELOG.md](CHANGELOG.md) for full version history.

---

## Prerequisites

- Python 3.10 or later
- A Garmin G3X avionics suite with EIS logging enabled
- G3X log files in CSV format (SD card direct or Garmin Pilot export)

---

## Installation

```bash
git clone https://github.com/AlchemyGeek/Rotax9iSEIS.git
cd Rotax9iSEIS
pip install -e .
```

This installs the `slingology-eis` command and the core runtime dependencies (`pandas`, `numpy` — that's genuinely all the engine needs). Two optional extras:

```bash
pip install -e ".[dev]"        # pytest, jsonschema — for running the test suite
pip install -e ".[notebooks]"  # jupyter, jupytext, matplotlib — for the legacy interactive notebooks
```

---

## Directory structure

```
Rotax9iSEIS/
├── slingology_eis/                     # Core analytics library + CLI
│   ├── __init__.py                     # __version__ lives here
│   ├── loader.py                       # G3X CSV parser, dual-format, duplicate detection
│   ├── limits.py                       # OM operating limits, phase filtering, exceedance detection
│   ├── phases.py                       # Automatic flight phase state machine
│   ├── egt.py                          # EGT spread, cylinder rank, trend detection
│   ├── fuel.py                         # FADEC fuel integration, cruise efficiency
│   ├── cas.py                          # CAS alert parser, ENGINE ECU classifier
│   ├── fleet.py                        # Multi-flight baselines, trends, outlier detection
│   ├── climb.py                        # Climb-rate-correlated thermal analysis
│   ├── baselines.py                    # Personal-baseline computation
│   ├── topics.py                       # The 14 analytics topics (Analysis + Insight)
│   ├── registry.py                     # Metric/topic registries backing the contract
│   ├── contract.py                     # Provenance, Diagnostic, diagnostic catalog
│   ├── operations.py                   # analyze_flight / analyze_ecu / update_fleet / evaluate_insights
│   ├── rules.py                        # validate_rules / what_if_rules
│   ├── serialize.py                    # NaN-safe JSON serialization
│   └── cli.py                          # The `slingology-eis` command
├── contract/
│   └── schema/                         # JSON Schemas for every contract result type
├── notebooks/                          # Legacy interactive scripts (Jupyter, via jupytext) —
│   │                                    # kept for now for plotting/deep-dive use; superseded
│   │                                    # by the CLI as the primary interface, see CHANGELOG 0.11.0
│   ├── 01_first_flight_analysis.py     # Deep-dive diagnostic report — one flight
│   ├── 02_engine_ecu_correlation.py    # ENGINE ECU pattern analysis across all flights
│   ├── 03_multi_flight_insights.py     # Fleet baselines, trends, outliers, Fleet Insights
│   └── 04_flight_report.py             # Per-flight pilot report (plain language)
├── engines/
│   ├── 916iS.json                      # VERIFIED — sourced from OM-916 i/C24 Ed.0 Rev.1
│   ├── 915iS.json                      # VERIFIED — sourced from OM-915 i A/C24 Ed.0 Rev.4
│   ├── 914iS.json                      # PLACEHOLDER — verify before operational use
│   └── 912iS.json                      # PLACEHOLDER — verify before operational use
├── data/
│   ├── logs/                           # Place your G3X CSV files here (default --logs)
│   └── reports/                        # Legacy notebook output / default --workspace
├── docs/specs/                         # Engine contract, workspace, and runtime-adapter specs
├── tests/                              # pytest suite — characterization, unit, contract, cli
├── config.json                         # Set your default engine here (default: 916iS)
├── insight_rules.json                  # Analytics trigger rules — edit to tune thresholds
├── pyproject.toml                      # Packaging — installs the slingology-eis command
├── CHANGELOG.md
└── BACKLOG.md
```

---

## Setup

### 1. Set your engine

Resolved in this order: the `--engine` flag → the `SLINGOLOGY_ENGINE` environment variable → `config.json` → default (`916iS`).

Edit `config.json` at the toolkit root to change the default:

```json
{
  "engine": "916iS"
}
```

Valid values: `916iS`, `915iS`, `914iS`, `912iS`. The 916iS and 915iS configs are fully verified against their Operators Manuals. 914iS and 912iS are placeholders — verify limits against your engine's OM before relying on them.

### 2. Add your log files

Copy G3X CSV files into `data/logs/` (or point `--logs` at wherever you keep them). Both export formats are supported and can be mixed freely:

- **G3X-direct** — downloaded from the SD card. Filename format: `log_YYYYMMDD_HHMMSS_ICAO.csv`
- **Garmin Pilot export** — exported via the Garmin Pilot app. Filename is typically a UUID; rename it to anything ending in `.csv`.

The loader auto-detects the format and normalises both to identical columns. Ground sessions (engine runs where the aircraft never flew) and duplicate exports of the same flight are automatically filtered out.

---

## Command-line interface

`slingology-eis` is the primary way to use the toolkit. It's a thin client over the engine contract in `slingology_eis/operations.py` — every subcommand converts inputs to bytes, calls one contract operation in-process, and prints the result as a plain-language report or as JSON.

```bash
slingology-eis <command> [options]
```

**Global options** (work before or after the subcommand):

| Option | Meaning |
|---|---|
| `--logs DIR` | Folder of G3X log CSVs. Default: `data/logs/` in a git checkout, or `~/SlingologyEIS/logs/` for a packaged install. |
| `--workspace DIR` | Folder for cached/derived results (fleet baseline, per-flight analyses). Default: `data/` in a git checkout, or `~/SlingologyEIS/workspace/` for a packaged install. |
| `--engine NAME` | Engine profile override (e.g. `916iS`). See engine resolution order above. |
| `--json` | Print the operation result as JSON instead of a plain-language report. |
| `--anonymize` | Strip aircraft ident, system ID, and airport hint from `--json` output. |
| `--quiet` | Suppress progress/diagnostic output on stderr. |

**Exit codes:** `0` success, `1` operation failed (bad path, malformed log), `2` usage error or a not-yet-implemented subcommand.

### Subcommands

| Command | Purpose |
|---|---|
| `engines` | List available engine profiles and their verification status. |
| `flight LOG` | Analyze one flight. `LOG` is a filename (resolved against `--logs`) or a full path. |
| `ecu [LOGS...]` | ENGINE ECU correlation across flights — classifies every ENGINE ECU occurrence as POWERUP / LANE_CHECK / SHUTDOWN / IN_FLIGHT. |
| `fleet` | Build fleet baselines, trends, and outlier detection across all logs in `--logs`; writes the workspace cache. |
| `report LOG` | Plain-language per-flight report — the two-layer Analysis/Insight format, evaluated against the cached (or freshly built) fleet baseline. |
| `import [PATHS...]` | Analyze logs/folders and write/refresh the workspace cache, without printing a report. |
| `rules check FILE` | Validate an `insight_rules.json`-shaped file; exits 1 if any error-severity diagnostic is found. |
| `rules try FILE` | Diff the insights a candidate rules file would produce, for one flight, against the currently-shipped rules. |
| `export-bundle` | *Not yet implemented* — needs Spec 02's results-bundle format. Exits 2. |
| `serve` | *Not yet implemented* — needs the Stage 4b local server adapter. Exits 2. |

### Examples

```bash
# List engine profiles
slingology-eis engines

# Analyze one flight, plain-language summary
slingology-eis flight log_20260527_200344_KSFF.csv

# Same, as JSON, validated against contract/schema/flight_analysis.schema.json
slingology-eis flight log_20260527_200344_KSFF.csv --json

# Build fleet baselines from everything in data/logs/, cache to the workspace
slingology-eis fleet

# Full per-flight pilot report (uses the cached fleet baseline if present)
slingology-eis report log_20260527_200344_KSFF.csv

# ENGINE ECU correlation across all flights
slingology-eis ecu

# Validate a candidate rules file, then see what it would change for one flight
slingology-eis rules check my_rules.json
slingology-eis rules try my_rules.json --flight log_20260527_200344_KSFF.csv

# Anonymized JSON output (strips aircraft ident/system_id/airport) for sharing
slingology-eis flight log_20260527_200344_KSFF.csv --json --anonymize
```

### Tuning insight triggers

Edit `insight_rules.json` at the toolkit root to adjust when insights fire. For example, to make EGT spread more sensitive:

```json
"egt_spread": {
  "enabled": true,
  "triggers": [
    {"type": "baseline_deviation", "z_score_threshold": 1.5},
    {"type": "trend", "direction": "increasing", "r2_min": 0.5, "n_min": 10}
  ]
}
```

No code changes needed — edit the JSON, then `slingology-eis rules check insight_rules.json` to validate it before use.

---

## Legacy notebooks

`notebooks/01`–`04` are the original interactive scripts (Jupyter-compatible via `jupytext`) the toolkit grew from. Since the engine-contract refactor they call into the same `slingology_eis/` library as the CLI, but still own their own report-rendering logic independently of `cli.py` — the two aren't guaranteed byte-identical. They're kept for now as Stage 0's characterization-test oracle (`tests/characterization/`) and for ad hoc plotting/deep-dive work; see CHANGELOG 0.11.0 and `BACKLOG.md` for the planned cleanup once the CLI has some track record. Prefer the `slingology-eis` CLI for day-to-day use.

```bash
python notebooks/01_first_flight_analysis.py log_20260527_200344_KSFF.csv   # single-flight deep dive
python notebooks/02_engine_ecu_correlation.py                               # ENGINE ECU pattern analysis
python notebooks/03_multi_flight_insights.py                                # fleet baselines/models/insights
python notebooks/04_flight_report.py log_20260527_200344_KSFF.csv           # per-flight pilot report
```

---

## Understanding baselines and confidence

The toolkit builds personal baselines from your own flights — not generic fleet averages. Each metric reports a confidence level based on sample size:

| Label | n | Meaning |
|---|---|---|
| LOW | < 10 | Indicative only — keep accumulating |
| MODERATE | 10–29 | Usable baseline, keep accumulating |
| sufficient | ≥ 30 | Reliable baseline |

The takeoff MAP model additionally requires altitude diversity across departure airports and notes "still collecting data" until n≥5 takeoff events are available.

---

## Limits reference (OM-916 i/C24, Ed. 0 Rev. 1)

| Parameter | Min | Max |
|---|---|---|
| RPM (continuous) | 1,800 | 5,500 |
| RPM (5-min max) | — | 5,800 |
| Oil temp (flight) | 122°F / 50°C | 248°F / 120°C |
| Coolant temp | — | 248°F / 120°C |
| EGT (per cylinder) | — | 1,742°F / 950°C |
| EGT spread (cruise, FF >3 L/hr) | — | 392°F / 200°C |
| Oil press (cruise) | 29 psi | 72.5 psi |
| MAP | — | 53.15 inHg |

915iS limits are sourced separately from OM-915 i A/C24 Ed. 0 Rev. 4 — see `engines/915iS.json`. Run `slingology-eis engines` for the full list of available profiles and their verification status.

---

## Fuel analytics note

There is deliberately no fuel-flow calibration against pump receipts in this toolkit. For an aircraft always fuelled full-to-full, gallons added at the pump already equals true consumption since the last fill — no flight-log-based calibration adds value. See CHANGELOG.md (0.6.0) and research paper §6.2.

---

## For developers

```bash
pip install -e ".[dev]"
pytest tests/
```

Most of the suite runs against synthetic data and needs nothing further. A subset — the characterization tests, and some contract/CLI tests — are gated on real flight logs (`data/logs/`) and frozen golden fixtures (`tests/characterization/golden/`), both private and gitignored; they skip automatically when absent. See `docs/specs/01-engine-contract.md` for the engine contract this all sits on top of, and `docs/specs/` generally for the design behind the refactor.

---

## Research paper

See `ROTAX 91XiS Engine Data Analytics.md` for the full analytical methodology, findings, open questions, and design decisions behind this toolkit.

---

## License

MIT License — see LICENSE.md.
