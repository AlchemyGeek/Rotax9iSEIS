"""
slingology_eis — Rotax iS engine data analytics.

Modules
-------
loader      : G3X CSV parser, dual-format support, duplicate flight detection
limits      : OM-sourced engine profiles, phase-aware exceedance checker
phases      : Automatic flight phase state machine (auto field-elevation, hysteresis)
egt         : EGT spread and cylinder balance analytics
fuel        : Fuel flow analytics — FADEC integration, cruise efficiency, sensor sanity check
cas         : CAS alert parser; ENGINE ECU run extraction and phase-based classification
fleet       : Multi-flight aggregation — reference, trends, outliers, DA/OAT stratification
climb       : Climb-rate-correlated thermal analysis (oil/coolant rise rate vs VS)
baselines   : Personal-baseline computation shared by the fleet and contract layers
topics      : The analytics topics (Spec 10 register) — one Analysis line + conditional Insight(s)
registry    : Metric/topic registries backing the engine contract
contract    : Provenance, Diagnostic, and the shared diagnostic catalog
operations  : The engine contract — analyze_flight, analyze_ecu, update_fleet,
              evaluate_insights, get_topic_help, the filter operations, trends — and
              their typed result objects
filters     : Limit filters and the change monitor (Spec 09)
trends      : The Trends change page: shift statistic, panels, readiness (Spec 12)
exclusions  : Log admission and flight exclusions (Spec 02 §5.11)
help        : topics.md parser, placeholder resolution, TopicHelp (Spec 01 §8.8)
rules       : validate_rules / what_if_rules for insight_rules.json
channels    : Chart channel registry and downsampling (Spec 07)
presets     : Chart presets, shipped and user-defined (Spec 07)
serialize   : NaN-safe JSON serialization for contract result objects
workspace   : Workspace registry, manifests, scans, Journal, settings changelog (Spec 02)
server      : The local HTTP server — /rpc operations and the built web UI
cli         : The `slingology-eis` command-line adapter
"""

__version__ = "1.1.0"
__author__  = "Slingology EIS Research"
