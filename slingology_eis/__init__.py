"""
slingology_eis — Rotax 916iS engine data analytics toolkit.

Modules
-------
loader    : G3X CSV parser, dual-format support, duplicate flight detection
limits    : OM-sourced operating limits and exceedance checker
phases    : Automatic flight phase state machine (auto field-elevation, hysteresis)
egt       : EGT health analytics
fuel      : Fuel flow analytics — FADEC integration, cruise efficiency, sensor sanity check
cas       : CAS alert parser and persistence detection
fleet     : Multi-flight aggregation — baselines, trends, outlier detection, DA/OAT stratification
climb     : Climb-rate-correlated thermal analysis (oil/coolant rise rate vs VS)
"""

__version__ = "0.9.0"
__author__  = "Slingology EIS Research"
