"""
Rebuild airports.csv.gz from OurAirports (Spec 16 §9 Q5).

    curl -sSfLO https://davidmegginson.github.io/ourairports-data/airports.csv
    curl -sSfLO https://davidmegginson.github.io/ourairports-data/runways.csv
    python -m slingology_eis.airports.trim airports.csv runways.csv

The trim: airports of type small/medium/large airport (no heliports,
balloonports, seaplane bases or closed fields) with at least one open
runway at least 300 m (984 ft) long; columns ident, icao, gps, iata, local,
name, municipality, region, lat, lon (5 decimals ≈ 1 m), elev_ft. Then record the
download date in README.md.
"""
from __future__ import annotations

import csv
import gzip
import sys
from pathlib import Path

MIN_RUNWAY_FT = 984          # 300 m
TYPES = {"small_airport", "medium_airport", "large_airport"}
COLUMNS = ("ident", "icao", "gps", "iata", "local", "name", "municipality", "region", "lat", "lon", "elev_ft")


def trim(airports_csv: Path, runways_csv: Path, out: Path) -> int:
    long_enough: set[str] = set()
    with open(runways_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                ft = float(r["length_ft"] or 0)
            except ValueError:
                continue
            if ft >= MIN_RUNWAY_FT and r.get("closed", "0") != "1":
                long_enough.add(r["airport_ref"])
    rows = []
    with open(airports_csv, newline="", encoding="utf-8") as f:
        for a in csv.DictReader(f):
            if a["type"] not in TYPES or a["id"] not in long_enough:
                continue
            rows.append((a["ident"], a.get("icao_code") or "", a["gps_code"] or "", a["iata_code"] or "",
                         a["local_code"] or "",
                         a["name"], a["municipality"] or "", a["iso_region"] or "",
                         f"{float(a['latitude_deg']):.5f}", f"{float(a['longitude_deg']):.5f}",
                         a["elevation_ft"] or ""))
    rows.sort()
    with gzip.open(out, "wt", encoding="utf-8", newline="") as g:
        w = csv.writer(g)
        w.writerow(COLUMNS)
        w.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    n = trim(Path(sys.argv[1]), Path(sys.argv[2]), Path(__file__).with_name("airports.csv.gz"))
    print(f"{n} airports")
