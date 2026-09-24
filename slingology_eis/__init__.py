"""
slingology_eis — Rotax iS engine data analytics toolkit.

Modules
-------
loader      : G3X CSV parser, dual-format support, duplicate flight detection
limits      : OM-sourced operating limits and exceedance checker
phases      : Automatic flight phase state machine (auto field-elevation, hysteresis)
egt         : EGT health analytics
fuel        : Fuel flow analytics — FADEC integration, cruise efficiency, sensor sanity check
cas         : CAS alert parser and persistence detection
fleet       : Multi-flight aggregation — baselines, trends, outlier detection, DA/OAT stratification
climb       : Climb-rate-correlated thermal analysis (oil/coolant rise rate vs VS)
baselines   : Personal-baseline computation shared by the fleet and contract layers
topics      : The 14 analytics topics — one Analysis line + conditional Insight(s) each
registry    : Metric/topic registries backing the engine contract
contract    : Provenance, Diagnostic, and the shared diagnostic catalog
operations  : The engine contract's four operations — analyze_flight, analyze_ecu,
              update_fleet, evaluate_insights — and their typed result objects
rules       : validate_rules / what_if_rules for insight_rules.json
serialize   : NaN-safe JSON serialization for contract result objects
cli         : The `slingology-eis` command-line adapter
"""

__version__ = "0.12.0"
__author__  = "Slingology EIS Research"
