"""
replay.py — chronological replay harness (Spec 12 R1.1).

Feeds a flight list to update_fleet incrementally, in engine-hours order
(date tie-break — the same ordering operations._chronological uses for
the recent window), yielding the FleetAnalysis after each flight is
added. Pinnable to a cut-off date so a test recorded against today's log
set doesn't move when new logs are dropped into data/logs/ later.

Shared by Spec 09's filter-monitor replay test and Spec 12's window/
shift/history acceptance tests — one definition of "replay" so both
can't quietly diverge on ordering.
"""
from __future__ import annotations

from typing import Optional

from slingology_eis.operations import FleetAnalysis, FlightAnalysis, update_fleet


def chronological(flight_analyses: list[FlightAnalysis], pinned_to_date: Optional[str] = None) -> list[FlightAnalysis]:
    """`flight_analyses` in engine-hours order (date tie-break). With
    `pinned_to_date`, flights dated after it (header["date"], ISO string
    comparison) are dropped first, so a later-growing log directory can't
    move an already-recorded replay result."""
    fas = flight_analyses
    if pinned_to_date is not None:
        fas = [fa for fa in fas if fa.header["date"] <= pinned_to_date]
    return sorted(fas, key=lambda fa: (fa.header.get("engine_hours_start") or 0, fa.header["date"]))


def replay(
    flight_analyses: list[FlightAnalysis],
    pinned_to_date: Optional[str] = None,
    start: int = 1,
    **update_fleet_kwargs,
) -> list[FleetAnalysis]:
    """The FleetAnalysis after each of the first `start`..len(fas) flights
    have been added, chronologically. `update_fleet_kwargs` (baseline_config,
    engine_config, filters, excluded) are passed through unchanged on every
    step. `start` only controls which steps are returned — update_fleet
    always sees the full prefix, never a gap, so a filter's or pinned
    reference's membership is always resolved against real history."""
    fas = chronological(flight_analyses, pinned_to_date)
    return [update_fleet(fas[:m], **update_fleet_kwargs) for m in range(start, len(fas) + 1)]
