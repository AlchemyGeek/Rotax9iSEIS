# slingology-eis-research — Rotax 916iS Engine Analytics Toolkit

**Version: 0.9.0** — check this against the version printed by `python -c "import slingology_eis; print(slingology_eis.__version__)"` to confirm you're running the copy you think you are. Full history in [CHANGELOG.md](CHANGELOG.md).

Local Python toolkit for analysing Garmin G3X EIS logs from the Rotax 916iS.  
Part of the **SlingologyEIS** research project (N5512E, Sling TSi, KPAE).

## Quick start

```bash
pip install -r requirements.txt

# Place your G3X log files in data/logs/
# Run the first flight analysis:
python notebooks/01_first_flight_analysis.py
```

## Directory structure

```
toolkit/
├── slingology_eis/           # Analysis library
│   ├── __init__.py           # __version__ lives here
│   ├── loader.py              # G3X CSV parser, dual-format, duplicate detection
│   ├── limits.py               # OM operating limits + exceedance checker
│   ├── phases.py                # Automatic flight phase state machine
│   ├── egt.py                    # EGT health analytics
│   ├── fuel.py                    # FADEC fuel integration, cruise efficiency, sender sanity check
│   ├── cas.py                      # CAS alert parser
│   ├── fleet.py                     # Multi-flight aggregation: baselines/trends/outliers, DA/OAT bands
│   └── climb.py                      # Climb-rate-correlated thermal analysis (oil/coolant vs VS)
├── notebooks/                 # Analysis scripts
│   ├── 01_first_flight_analysis.py     # Deep-dive report on one flight
│   ├── 02_engine_ecu_correlation.py    # ENGINE ECU pattern analysis across flights
│   └── 03_multi_flight_insights.py     # Fleet-level baselines/trends/outliers/ops
├── engines/                  # Engine config files (912iS, 914iS, 915iS, 916iS)
├── data/
│   ├── logs/                  # Place G3X CSV files here
│   └── reports/                # Generated CSV/TXT reports (fleet_metrics.csv, etc.)
├── CHANGELOG.md
├── config.json               # Set your engine here (default: 916iS)
├── CHANGELOG.md
└── requirements.txt
```

## Adding your log files

Copy G3X CSV files into `data/logs/`. **Both export formats are supported and can be mixed freely in the same folder:**

- **G3X-direct** — downloaded straight from the SD card. Filename format: `log_YYYYMMDD_HHMMSS_ICAO.csv`
- **Garmin Pilot export** — shared/exported via the Garmin Pilot app. Filename is typically a UUID (e.g. `08c95ea8-....csv`); rename it to anything ending in `.csv`.

The loader auto-detects which format each file is (Garmin Pilot prefixes its header row with `#`) and normalises both to identical columns — `load_directory()` and all analysis modules treat them interchangeably. The detected format is recorded on `info.source_format` (`"g3x_direct"` or `"garmin_pilot"`) if you ever need to confirm which path a file came from.

### Duplicate flight detection

If the same physical flight ends up as two files — e.g. you downloaded it from the SD card *and* exported it via Garmin Pilot — that flight would silently get double-counted in every fleet statistic. Scripts 02 and 03 both check for this automatically before analysis:

- **Exact match** — same aircraft, same G3X unit, same start minute → almost certainly the same flight exported twice.
- **Overlap match** — same aircraft, time windows overlap ≥80% of the shorter flight's duration → catches a truncated or partial re-export that doesn't start at exactly the same second.

When found, the script keeps the file with more data rows (the fuller capture) and drops the other, printing what it did. You can also call this directly:

```python
from slingology_eis.loader import load_directory, find_duplicate_flights, deduplicate_flights

flights = load_directory("data/logs/")
dups = find_duplicate_flights(flights)        # inspect without removing anything
flights = deduplicate_flights(flights)        # or remove duplicates, keeping the fuller file
```

## Fuel analytics

`fuel.py` integrates FADEC fuel flow per flight (`integrate_fuel`), computes cruise efficiency in nautical miles per gallon (`cruise_efficiency`), and does a rough plausibility check against the wing tank senders (`tank_sanity_check` — the senders are attitude-sensitive and unreliable, so this is a sanity flag only, not a correction).

There is deliberately **no fuel-flow calibration against pump receipts** in this toolkit. For an aircraft always fuelled full-to-full, gallons added at the pump already equals true consumption since the last fill, directly — no flight-log-based calibration adds value over that. See [CHANGELOG.md](CHANGELOG.md) (0.6.0) for the reasoning, and the research paper §6.2 for the full writeup.

## Limits reference (OM-916 i/C24, Ed. 0 Rev. 1)

| Parameter          | Min          | Max               |
|--------------------|--------------|-------------------|
| RPM (continuous)   | 1,800        | 5,500             |
| RPM (5-min max)    | —            | 5,800             |
| Oil temp (flight)  | 122°F / 50°C | 248°F / 120°C     |
| Coolant temp       | —            | 248°F / 120°C     |
| EGT (per cylinder) | —            | 1,742°F / 950°C   |
| EGT spread (cruise)| —            | 392°F / 200°C     |
| Oil press (cruise) | 29 psi       | 72.5 psi          |
| MAP                | 1.77 inHg    | 53.15 inHg        |

## Research paper

See `../research/` for the living research document  
`Rotax_916iS_EIS_Research_v0.2.docx`

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full version history.
