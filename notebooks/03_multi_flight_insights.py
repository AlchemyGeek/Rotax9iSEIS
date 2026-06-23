"""
notebooks/03_multi_flight_insights.py
======================================
Fleet-level analytics across ALL logs in data/logs/.

Organised into five insight categories:

  1. BASELINES        — what "normal" looks like for this engine,
                         derived empirically from your own flight history
  2. TRENDS            — is any parameter drifting over engine hours?
                         (includes cylinder balance stability)
  3. OUTLIERS          — does any single flight stick out from the pack?
  4. OPERATIONAL       — efficiency, utilisation, flying patterns,
                         and per-flight engine-health observables
                         (overboost time, oil condensation risk)
  5. DATA QUALITY       — sensor reliability, FADEC fuel totals

This is intentionally a SUMMARY tool — for a deep dive on one specific
flight, use 01_first_flight_analysis.py. For the ENGINE ECU-specific
investigation, use 02_engine_ecu_correlation.py.

Note: fuel-flow calibration against pump receipts (K_fuel) was explored
and deliberately descoped — see CHANGELOG.md and the research paper.
For full-to-full refuelling, gallons added since the last fill already
equals true consumption directly; no flight-log-based calibration is
needed. cruise_nmpg below uses raw (uncalibrated) FADEC fuel flow,
which the OM states is accurate to within ±10% even without correction.

Usage
-----
    python notebooks/03_multi_flight_insights.py
"""

import sys
from pathlib import Path

_HERE    = Path(__file__).resolve().parent
_TOOLKIT = _HERE.parent
sys.path.insert(0, str(_TOOLKIT))

from slingology_eis.loader import load_directory, find_duplicate_flights, deduplicate_flights
from slingology_eis.fleet import (
    build_flight_metrics, baseline, baseline_stratified,
    trend, trend_stratified, outliers, confidence_label,
    MIN_FLIGHTS_FOR_CONFIDENCE,
)
from slingology_eis.climb import VS_BUCKETS
from slingology_eis.limits import load_engine_config

import pandas as pd

LOGS_DIR    = _TOOLKIT / "data" / "logs"
REPORTS_DIR = _TOOLKIT / "data" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def section(title: str):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def subsection(title: str):
    print(f"\n── {title} {'─' * max(0, 58 - len(title))}")


def main():
    engine_cfg_early = load_engine_config()
    engine_name_early = engine_cfg_early.get("_metadata", {}).get("engine", "unknown engine")
    source_status = engine_cfg_early.get("_metadata", {}).get("source_status", "")
    section(f"SLINGOLOGY EIS — Multi-Flight Insights  [{engine_name_early}]")
    if source_status == "PLACEHOLDER":
        print(f"  ⚠  Engine config is a PLACEHOLDER — verify limits against the official OM")

    print(f"\nLoading logs from: {LOGS_DIR}")
    try:
        flights = load_directory(str(LOGS_DIR), verbose=True)
    except ValueError as e:
        print(f"\nError: {e}")
        return

    if not flights:
        print("No flights loaded.")
        return

    # ── Duplicate flight detection ───────────────────────────────────────────
    # The same physical flight can end up as two files — e.g. downloaded
    # directly from the SD card AND exported via Garmin Pilot. Left
    # unchecked, this silently double-counts the flight in every fleet
    # statistic below (baselines, trends, totals). Catch it here, once,
    # rather than in every individual analysis.
    dup_groups = find_duplicate_flights(flights)
    if dup_groups:
        print(f"\n⚠  {len(dup_groups)} duplicate flight group(s) detected:")
        for g in dup_groups:
            print(f"    {g}")
        flights = deduplicate_flights(flights, prefer="most_rows", verbose=True)
        print(f"  Proceeding with {len(flights)} unique flight(s).")
    else:
        print("\n✓ No duplicate flights detected.")

    n_flights = len(flights)
    print(f"\nBuilding per-flight metrics for {n_flights} flight(s)...")
    metrics = build_flight_metrics(flights, field_elev_ft=None, verbose=True)

    if len(metrics) == 0:
        print("No metrics could be computed.")
        return

    overall_conf = confidence_label(n_flights)
    print(f"\nFlights in dataset: {n_flights} — {overall_conf}")
    if n_flights < MIN_FLIGHTS_FOR_CONFIDENCE:
        print(f"⚠  Below the {MIN_FLIGHTS_FOR_CONFIDENCE}-flight threshold for stable baselines.")
        print(f"   Numbers below are shown anyway, but treat them as indicative, not definitive.")
        print(f"   Re-run this script as you accumulate more logs — figures will sharpen.")

    # ═══════════════════════════════════════════════════════════════════════
    section("1. BASELINES — What 'normal' looks like for this engine")
    # ═══════════════════════════════════════════════════════════════════════
    print("\nEmpirical baselines from YOUR flight history (not OM limits — those")
    print("are absolute ceilings; these are what your specific engine actually does).\n")

    baseline_metrics = [
        ("egt_spread_mean_f",   "EGT spread, cruise mean (°F)"),
        ("egt4_elevation_f",    "EGT4 elevation vs cyl 1-3 (°F)"),
        ("oil_temp_max_f",      "Oil temp, per-flight max (°F)"),
        ("coolant_temp_max_f",  "Coolant temp, per-flight max (°F)"),
        ("oil_coolant_ratio",   "Oil/coolant temp ratio"),
        ("cruise_fuel_flow_gph","Cruise fuel flow (gal/hr)"),
        ("cruise_nmpg",         "Cruise efficiency (nm/gal)"),
    ]
    for col, label in baseline_metrics:
        b = baseline(metrics, col)
        print(f"  {label:<38} {b}")

    # ═══════════════════════════════════════════════════════════════════════
    section("2. TRENDS — Is anything drifting over engine hours?")
    # ═══════════════════════════════════════════════════════════════════════
    has_engine_hours = metrics["engine_hours"].notna().sum() >= 3
    if not has_engine_hours:
        print("\n⚠  Insufficient engine-hours data across flights to compute trends.")
        print("   (Need engine_hours populated in at least 3 logs' airframe metadata.)")
    else:
        print("\nLinear trend vs engine hours. 'Flat' means no statistically clear")
        print("relationship was found (R² below threshold) — NOT necessarily that")
        print("nothing is happening, just that we can't distinguish it from noise yet.\n")

        trend_metrics = [
            ("egt_spread_mean_f",   "EGT spread (cylinder balance health)"),
            ("egt4_elevation_f",    "EGT4 elevation"),
            ("oil_coolant_ratio",   "Oil/coolant ratio (cooling system health)"),
            ("oil_temp_below_optimal_pct", "% time oil below optimal band"),
        ]
        for col, label in trend_metrics:
            t = trend(metrics, col, x="engine_hours")
            flag = "⚠ " if t.direction in ("increasing", "decreasing") and (t.r_squared or 0) > 0.3 else "  "
            print(f"  {flag}{label:<38} {t}")

    subsection("Cruise efficiency — by density altitude band")
    print("  cruise_nmpg depends heavily on density altitude, so a single trend")
    print("  blended across all conditions can look misleading (a real engine")
    print("  trend and seasonal/altitude variation are easy to confuse). Trended")
    print("  separately per DA band instead — see research paper §9.\n")
    da_trends = trend_stratified(metrics, "cruise_nmpg", x="engine_hours", band_column="da_band")
    if da_trends:
        for band in ["low", "moderate", "high", "very_high"]:
            if band in da_trends:
                print(f"  {band:<12} {da_trends[band]}")
    else:
        print("  No density-altitude-banded data available yet.")

    subsection("EGT spread — by OAT band")
    print("  Thermal metrics depend on outside air temperature, not just density")
    print("  altitude (ambient air is also the cooling medium) — see research")
    print("  paper §9. Trended separately per OAT band:\n")
    oat_trends = trend_stratified(metrics, "egt_spread_mean_f", x="engine_hours", band_column="oat_band")
    if oat_trends:
        for band in ["cold", "mild", "warm", "hot"]:
            if band in oat_trends:
                print(f"  {band:<12} {oat_trends[band]}")
    else:
        print("  No OAT-banded data available yet.")

    subsection("Cylinder balance stability")
    stable_count = metrics["egt_rank_stable"].sum() if "egt_rank_stable" in metrics.columns else 0
    total_with_data = metrics["egt_rank_stable"].notna().sum()
    if total_with_data:
        print(f"  Flights with a single consistently-hottest cylinder: "
              f"{stable_count}/{total_with_data}")
        print(f"  (Instability here can be an early signal of an injector or")
        print(f"  ignition imbalance developing — worth tracking over time.)")
    else:
        print("  No cylinder rank data available.")

    # ═══════════════════════════════════════════════════════════════════════
    section("3. OUTLIERS — Does any single flight stick out?")
    # ═══════════════════════════════════════════════════════════════════════
    print("\nFlights flagged where a metric is ≥2 standard deviations from the")
    print("fleet mean. With few flights this is noisy by nature — a flagged")
    print("flight is a prompt to look closer, not a verdict.\n")

    outlier_metrics = [
        ("egt_spread_max_f",    "EGT spread max"),
        ("egt4_elevation_f",    "EGT4 elevation"),
        ("oil_temp_max_f",      "Oil temp max"),
        ("coolant_temp_max_f",  "Coolant temp max"),
        ("overboost_total_s",   "Overboost time"),
        ("cruise_nmpg",         "Cruise efficiency"),
    ]
    any_outliers = False
    for col, label in outlier_metrics:
        flagged = outliers(metrics, col)
        if flagged:
            any_outliers = True
            print(f"  {label}:")
            for o in flagged:
                print(f"    {o.date}  {o.source_file}  value={o.value}  (z={o.z_score:+.2f})")
    if not any_outliers:
        print("  No outlier flights detected across tracked metrics.")

    # Load engine config once for the whole report
    engine_cfg  = load_engine_config()
    engine_name = engine_cfg.get("_metadata", {}).get("engine", "unknown engine")
    ob_cfg      = engine_cfg.get("overboost", {})
    ob_limit_s  = ob_cfg.get("time_limit_s", 300)
    ob_rpm      = ob_cfg.get("rpm_threshold", 5500)
    ob_close_s  = int(ob_limit_s * 0.8)   # "close call" = within 80% of the limit

    section(f"4. OPERATIONAL — Efficiency, utilisation, flying patterns & engine health")
    subsection("Flight activity")
    total_duration_hr  = metrics["duration_min"].sum() / 60
    total_airborne_hr  = metrics["airborne_min"].sum() / 60
    avg_duration_min   = metrics["duration_min"].mean()
    print(f"  Flights logged:          {n_flights}")
    print(f"  Total session time:      {total_duration_hr:.1f} hr")
    print(f"  Total airborne time:     {total_airborne_hr:.1f} hr")
    print(f"  Average flight length:   {avg_duration_min:.0f} min")
    if metrics["engine_hours"].notna().any():
        eh_min = metrics["engine_hours"].min()
        eh_max = metrics["engine_hours"].max()
        print(f"  Engine hours span:       {eh_min:.1f} → {eh_max:.1f}  "
              f"(Δ{eh_max - eh_min:.1f}h across logged flights)")

    subsection("Phase time distribution")
    for ph_col, label in [("phase_climb_min", "Climb"),
                          ("phase_cruise_min", "Cruise"),
                          ("phase_descent_min", "Descent")]:
        total = metrics[ph_col].sum()
        pct   = total / total_airborne_hr / 60 * 100 if total_airborne_hr > 0 else 0
        print(f"  {label:<10} {total:>7.1f} min total  ({pct:.0f}% of airborne time)")

    subsection("Efficiency over time")
    nmpg_series = metrics[["date", "cruise_nmpg"]].dropna()
    if len(nmpg_series) >= 2:
        first, last = nmpg_series.iloc[0], nmpg_series.iloc[-1]
        delta = last["cruise_nmpg"] - first["cruise_nmpg"]
        print(f"  First flight w/ data:    {first['date']}  {first['cruise_nmpg']:.1f} nm/gal")
        print(f"  Latest flight w/ data:   {last['date']}  {last['cruise_nmpg']:.1f} nm/gal")
        print(f"  Change:                  {delta:+.1f} nm/gal")
    elif len(nmpg_series) == 1:
        print(f"  Only one flight with cruise efficiency data so far: "
              f"{nmpg_series.iloc[0]['cruise_nmpg']:.1f} nm/gal")
    else:
        print("  No cruise efficiency data available yet.")

    subsection("Highest / lowest flights")
    if metrics["max_altitude_ft"].notna().any():
        hi = metrics.loc[metrics["max_altitude_ft"].idxmax()]
        print(f"  Highest flight: {hi['date']}  {hi['max_altitude_ft']:.0f} ft  ({hi['source_file']})")
    if metrics["max_ias_kt"].notna().any():
        fast = metrics.loc[metrics["max_ias_kt"].idxmax()]
        print(f"  Fastest IAS:    {fast['date']}  {fast['max_ias_kt']:.0f} kt  ({fast['source_file']})")

    subsection(f"Overboost (RPM>{ob_rpm} / Power>100%)")
    total_ob_s = metrics["overboost_total_s"].sum()
    max_block  = metrics["overboost_max_block_s"].max()
    print(f"  Cumulative overboost time (all logged flights): {total_ob_s:.0f}s "
          f"({total_ob_s/60:.1f} min)")
    print(f"  Longest single continuous block:                 {max_block:.0f}s  "
          f"(OM limit: {ob_limit_s}s)")
    if max_block and max_block > ob_limit_s:
        print(f"  ⚠  {ob_limit_s//60}-minute overboost limit was exceeded in at least one flight!")

    ob_data = metrics[metrics["overboost_max_block_s"] > 0]
    if len(ob_data):
        print(f"\n  Throttle discipline — how close to the {ob_limit_s}s limit you typically run")
        print(f"  (the OM limit exists because Takeoff/POWER mode is meant to be brief;")
        print(f"  this isn't just a hard-limit check, it's a habit signal — promptly")
        print(f"  pulling back to climb power after takeoff keeps you well clear):\n")

        exceeded    = ob_data[ob_data["overboost_max_block_s"] > ob_limit_s]
        close_call  = ob_data[(ob_data["overboost_max_block_s"] > ob_close_s) &
                               (ob_data["overboost_max_block_s"] <= ob_limit_s)]
        comfortable = ob_data[ob_data["overboost_max_block_s"] <= ob_close_s]

        print(f"  Exceeded limit (>{ob_limit_s}s):      {len(exceeded)}/{len(ob_data)} flights")
        for _, row in exceeded.iterrows():
            over_by = row["overboost_max_block_s"] - ob_limit_s
            print(f"      ⚠ {row['date']}  {row['overboost_max_block_s']:.0f}s  "
                  f"(+{over_by:.0f}s over)  {row['source_file']}")
        print(f"  Close call ({ob_close_s}–{ob_limit_s}s): {len(close_call)}/{len(ob_data)} flights")
        print(f"  Comfortable (≤{ob_close_s}s):      {len(comfortable)}/{len(ob_data)} flights")

        t = trend(ob_data, "overboost_max_block_s", x="engine_hours")
        if t.slope is not None:
            print(f"\n  Trend over time: {t}")
            if t.direction == "increasing" and (t.r_squared or 0) > 0.2:
                print(f"  ⚠ Time spent at takeoff power before throttling back appears")
                print(f"    to be growing — may be worth a deliberate focus on the")
                print(f"    TO-to-climb-power transition.")
            elif t.direction == "decreasing" and (t.r_squared or 0) > 0.2:
                print(f"  ✓ Trending shorter over time — habit appears to be improving.")

    subsection("Oil temperature — condensation risk")
    below_pct = metrics["oil_temp_below_optimal_pct"].dropna()
    if len(below_pct):
        avg_below = below_pct.mean()
        worst = metrics.loc[metrics["oil_temp_below_optimal_pct"].idxmax()] \
            if metrics["oil_temp_below_optimal_pct"].notna().any() else None
        print(f"  Avg % of each flight below optimal oil temp band (194°F/90°C): "
              f"{avg_below:.0f}%")
        if worst is not None:
            print(f"  Worst flight: {worst['date']}  "
                  f"{worst['oil_temp_below_optimal_pct']:.0f}% below optimal  "
                  f"({worst['source_file']})")
        print(f"  Note: OM recommends reaching 100°C (212°F) at least once daily")
        print(f"  to drive off condensation in the sump.")
    else:
        print("  No oil temperature data available.")

    subsection("Climb thermal rate — does climb steepness affect cooling margin?")
    climb_data = metrics.dropna(subset=["climb_oil_rise_f_per_min"])
    if len(climb_data):
        b_oil = baseline(climb_data, "climb_oil_rise_f_per_min")
        b_coolant = baseline(climb_data, "climb_coolant_rise_f_per_min")
        print(f"  Overall climb oil rise rate:      {b_oil}")
        print(f"  Overall climb coolant rise rate:  {b_coolant}")
        if "climb_vs_bucket_dominant" in climb_data.columns:
            bucket_counts = climb_data["climb_vs_bucket_dominant"].value_counts()
            print(f"  Typical climb profile across flights: "
                  f"{dict(bucket_counts)}")
        print(f"  (°F/min computed via linear fit across CLIMB-phase rows;")
        print(f"  positive = warming during climb. Per-VS-bucket breakdown")
        print(f"  available via slingology_eis.climb.climb_thermal_profile()")
        print(f"  for any individual flight — steeper climbs are expected to")
        print(f"  show faster rise rates; the question worth watching is")
        print(f"  whether that relationship itself is changing over time.)")
    else:
        print("  No climb thermal data available yet (requires sustained")
        print("  CLIMB-phase segments — short pattern-work flights won't")
        print("  contribute here).")

    # ═══════════════════════════════════════════════════════════════════════
    section("5. DATA QUALITY — Sensor reliability & FADEC fuel totals")
    # ═══════════════════════════════════════════════════════════════════════
    subsection("FADEC fuel flow total vs flights")
    total_fadec_gal = metrics["fadec_gallons"].sum()
    flights_with_fuel = metrics["fadec_gallons"].notna().sum()
    print(f"  Total FADEC-calculated fuel across {flights_with_fuel} flight(s): "
          f"{total_fadec_gal:.1f} gal")
    print(f"  (FADEC fuel flow is a model-based estimate, not a physical sensor —")
    print(f"  the OM states ±10% tolerance. For full-to-full refuelling, gallons")
    print(f"  added at the pump is the more accurate ground-truth consumption figure.)")

    subsection("ENGINE ECU anomaly tracking")
    print(f"  For full ENGINE ECU classification (powerup/lane-check/shutdown/")
    print(f"  in-flight), run 02_engine_ecu_correlation.py — that script applies")
    print(f"  the dedicated classifier this summary doesn't duplicate.")

    # ═══════════════════════════════════════════════════════════════════════
    section("Saving outputs")
    # ═══════════════════════════════════════════════════════════════════════
    out_csv = REPORTS_DIR / "fleet_metrics.csv"
    metrics.to_csv(out_csv, index=False)
    print(f"\n  Per-flight metrics table saved: {out_csv}")
    print(f"  ({len(metrics)} rows × {len(metrics.columns)} columns)")
    print(f"  Open in Excel/Sheets for further exploration, or feed into future plotting work.")

    print(f"\n{'=' * 70}\n")


if __name__ == "__main__":
    main()
