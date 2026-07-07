# SlingologyEIS — Rotax iS Engine Analytics Toolkit

**Version: 0.10.0** — verify with `python -c "import slingology_eis; print(slingology_eis.__version__)"`

Free, open-source engine health analytics for Rotax iS FADEC-controlled aircraft engines (912iS, 914iS, 915iS, 916iS). Built from the ground up for how these engines actually work — not retrofitted from the carbureted-engine assumptions that underpin existing tools like Savvy Aviation and FlySto. Analyses Garmin G3X EIS logs against Rotax Operators Manual limits, automatically detects flight phases, tracks EGT spread and cylinder balance over engine hours, classifies CAS alerts, monitors overboost time, builds personal baselines from your own flight history, and produces plain-language per-flight reports — all offline, with your data never leaving your machine.

**Current status:** Python research toolkit v0.10.0, validated against 23 flights on N117ZS (Sling TSi, Rotax 916iS, KPAE). Long-term goal is a free progressive web app for any Sling / Rotax iS pilot.

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
pip install -r requirements.txt
```

---

## Directory structure

```
Rotax9iSEIS/
├── slingology_eis/                     # Core analytics library
│   ├── __init__.py                     # __version__ lives here
│   ├── loader.py                       # G3X CSV parser, dual-format, duplicate detection
│   ├── limits.py                       # OM operating limits, phase filtering, exceedance detection
│   ├── phases.py                       # Automatic flight phase state machine
│   ├── egt.py                          # EGT spread, cylinder rank, trend detection
│   ├── fuel.py                         # FADEC fuel integration, cruise efficiency
│   ├── cas.py                          # CAS alert parser, ENGINE ECU classifier
│   ├── fleet.py                        # Multi-flight baselines, trends, outlier detection
│   └── climb.py                        # Climb-rate-correlated thermal analysis
├── notebooks/
│   ├── 01_first_flight_analysis.py     # Deep-dive diagnostic report — one flight
│   ├── 02_engine_ecu_correlation.py    # ENGINE ECU pattern analysis across all flights
│   ├── 03_multi_flight_insights.py     # Fleet baselines, trends, outliers, Fleet Insights
│   └── 04_flight_report.py             # Per-flight pilot report (plain language)
├── engines/
│   ├── 916iS.json                      # VERIFIED — sourced from OM-916 i/C24 Ed.0 Rev.1
│   ├── 915iS.json                      # PLACEHOLDER — verify before operational use
│   ├── 914iS.json                      # PLACEHOLDER — verify before operational use
│   └── 912iS.json                      # PLACEHOLDER — verify before operational use
├── data/
│   ├── logs/                           # Place your G3X CSV files here
│   └── reports/                        # Generated reports (auto-created on first run)
├── config.json                         # Set your engine here (default: 916iS)
├── insight_rules.json                  # Analytics trigger rules — edit to tune thresholds
├── CHANGELOG.md
└── requirements.txt
```

---

## Setup

### 1. Set your engine

Edit `config.json` at the toolkit root:

```json
{
  "engine": "916iS"
}
```

Valid values: `916iS`, `915iS`, `914iS`, `912iS`. The 916iS config is fully verified against the Rotax OM. The others are placeholders — verify limits against your engine's OM before use.

### 2. Add your log files

Copy G3X CSV files into `data/logs/`. Both export formats are supported and can be mixed freely:

- **G3X-direct** — downloaded from the SD card. Filename format: `log_YYYYMMDD_HHMMSS_ICAO.csv`
- **Garmin Pilot export** — exported via the Garmin Pilot app. Filename is typically a UUID; rename it to anything ending in `.csv`.

The loader auto-detects the format and normalises both to identical columns. Ground sessions (engine runs where the aircraft never flew) are automatically filtered out.

---

## User Manual

### Recommended workflow

Run the scripts in this order after every few flights:

```
Script 03  →  Script 04  →  Script 02  (Script 01 on demand)
```

**Script 03 first** — processes all logs and writes the fleet baselines and models that scripts 02 and 04 depend on.

**Script 04 after** — reads baselines from script 03 and produces a per-flight plain-language report in seconds without reloading all logs.

**Script 02 when flagged** — run when Fleet Insights or the per-flight report flags an IN-FLIGHT ENGINE ECU event. Provides full CAN bus pattern analysis and recommended actions.

**Script 01 on demand** — a deep technical diagnostic for a specific flight. Use when you want to understand what happened in detail.

---

### Script 03 — Fleet Summary

```bash
python notebooks/03_multi_flight_insights.py
```

Processes all logs in `data/logs/`, produces five analytical sections (Baselines, Trends, Outliers, Operational, Data Quality), and appends a Fleet Insights section. Writes:

- `data/reports/fleet_metrics.csv` — one row per flight, 34 columns of per-flight metrics
- `data/reports/baselines.json` — personal baselines for all analytics topics
- `data/reports/models.json` — empirical regression models (currently: takeoff MAP)
- `data/reports/fleet_insights.txt` — tight summary of major findings only

**Fleet Insights** is the section to read first after every run. It shows only what needs your attention:

```
⚠ Overboost limit exceeded — log_20260423_135821_KTOA.csv (381s, limit 300s).
⚠ IN-FLIGHT ENGINE ECU event — log_20260527_200344_KSFF.csv (1 event(s)).
⚠ EGT spread max outlier — log_20260613_193731_KAWO.csv (value=145, z=+2.56).

✓ No IN-FLIGHT ENGINE ECU events across all flights.
```

Re-run script 03 after every few new flights to keep baselines current.

---

### Script 04 — Per-Flight Pilot Report

```bash
# Filename only (resolved against data/logs/ automatically):
python notebooks/04_flight_report.py log_20260527_200344_KSFF.csv

# Or with full path:
python notebooks/04_flight_report.py data/logs/log_20260527_200344_KSFF.csv
```

Produces a plain-language report for one flight. Requires `reports/baselines.json` and `reports/models.json` from a recent script 03 run.

The report uses a two-layer format:

- **Analysis line** — always present. States this flight's measurement and personal baseline comparison.
- **Insight line** — only appears when something is worth flagging.

Example output:

```
══════════════════════════════════════════════════════════════════════
  SLINGOLOGY EIS — FLIGHT REPORT
  N117ZS  |  Rotax 916iS
  Date:         2026-05-27  20:06
  Airport:      KSFF
  Engine hrs:   56.2h → 58.6h
  Duration:     142 min airborne
  Max altitude: 9,500 ft
  Max IAS:      136 kt
  Fuel used:    18.4 gal (FADEC)
══════════════════════════════════════════════════════════════════════

── EGT SPREAD ────────────────────────────────────────────────
  Analysis: Cruise mean 55°F. Your average: 56°F ± 5°F (23 flights). OM limit: 392°F.

── OVERBOOST ─────────────────────────────────────────────────
  Analysis: Max continuous block: 274s. Total this flight: 274s. OM limit: 300s.
  Insight:  ⚠ Close call — 26s below the OM limit. Pull back to climb power promptly.

── ENGINE ECU ────────────────────────────────────────────────
  Analysis: 1 IN-FLIGHT ENGINE ECU event(s) detected — requires investigation.
    ⚡ 20:06:38  1s  oil_NaN:0%
  Insight:  ⚠ Co-active: OIL PRESS — only IN-FLIGHT event with a direct engine-parameter correlation.

── LIMIT EXCEEDANCES ─────────────────────────────────────────
  Analysis: No OM hard-limit exceedances this flight.

══════════════════════════════════════════════════════════════════════
```

Report saved to `data/reports/report_<logname>.txt`.

---

### Script 02 — ENGINE ECU Correlation

```bash
python notebooks/02_engine_ecu_correlation.py
```

Run when an IN-FLIGHT ENGINE ECU event is flagged. Analyses all flights, classifies every ENGINE ECU occurrence as POWERUP / LANE_CHECK / SHUTDOWN / IN_FLIGHT, and produces a detailed report covering:

- Per-flight summary of all ENGINE ECU runs
- Co-active alert analysis for IN_FLIGHT events
- Oil pressure NaN pattern (CAN dropout signature)
- Recommended inspection actions

Output saved to `data/reports/engine_ecu_report.txt` and `data/reports/engine_ecu_runs.csv`.

---

### Script 01 — Single Flight Deep Dive

```bash
python notebooks/01_first_flight_analysis.py log_20260527_200344_KSFF.csv
```

Detailed technical diagnostic for one flight — per-cylinder EGT analysis, full phase timeline, fuel flow by phase, CAS alert log, all exceedances with timestamps. Use when the per-flight report flags something and you want to understand it in detail.

---

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

No code changes needed — edit the JSON and re-run.

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

---

## Fuel analytics note

There is deliberately no fuel-flow calibration against pump receipts in this toolkit. For an aircraft always fuelled full-to-full, gallons added at the pump already equals true consumption since the last fill — no flight-log-based calibration adds value. See CHANGELOG.md (0.6.0) and research paper §6.2.

---

## Research paper

See `Rotax_916iS_EIS_Research_v0.2.docx` for the full analytical methodology, findings, open questions, and design decisions behind this toolkit.

---

## License

MIT License — see LICENSE file.