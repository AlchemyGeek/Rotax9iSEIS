# Airport table (Spec 16 D10, §4.4, §9 Q5)

`airports.csv.gz` — the airports flight identification resolves GPS fixes
against (`slingology_eis/flight_ident.py`).

- **Source:** OurAirports (public domain), `airports.csv` and `runways.csv`
  from https://davidmegginson.github.io/ourairports-data/
- **Downloaded:** 2026-11-15
- **Trim** (`trim.py`): small, medium and large airports (no heliports,
  balloonports, seaplane bases or closed fields) with at least one open
  runway of 300 m (984 ft) or more — 28 916 airports, 0.9 MB gzipped.
  Columns: ident, icao, gps, iata, local, name, municipality, region, lat,
  lon (5 decimals), elev_ft.
- **Refresh:** by hand with a release — download the two files, run
  `python -m slingology_eis.airports.trim airports.csv runways.csv`, and
  update the date above.
