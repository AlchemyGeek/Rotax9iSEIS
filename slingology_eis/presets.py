"""
presets.py — chart preset validation (Spec 07 §6.3).

Pure — no I/O. One function used by both the load path (skip + a
PRESET_INVALID diagnostic, never blocking the app) and the save path
(reject outright) — the same rules either way, so a preset silently
dropped on load is exactly the one that would have been rejected on save.
"""
from __future__ import annotations

from .channels import CHANNEL_REGISTRY, MAX_CHART_SLOTS, SLOT_GROUPS
from .contract import Diagnostic


def validate_chart_preset(preset: dict, existing_ids: frozenset = frozenset()) -> list[dict]:
    """
    Checks one chart preset dict. Returns a list of Diagnostic dicts
    (code PRESET_INVALID, severity warn); empty means valid.

    `existing_ids` is the set of preset ids already accepted earlier in
    the same load/save pass, so a duplicate `id` across presets is
    caught the same way a duplicate channel within one preset is.
    """
    pid = preset.get("id") if isinstance(preset, dict) else None

    def _invalid(message: str) -> list[dict]:
        return [Diagnostic(
            code="PRESET_INVALID", severity="warn", scope="file",
            message=message, refs={"preset_id": pid} if isinstance(pid, str) else None,
        ).to_dict()]

    if not isinstance(preset, dict):
        return _invalid("chart preset entry is not an object")
    if not pid or not isinstance(pid, str):
        return _invalid("chart preset is missing an id")
    if pid in existing_ids:
        return _invalid(f"{pid}: duplicate preset id")

    channels = preset.get("channels")
    if not isinstance(channels, list) or not channels:
        return _invalid(f"{pid}: preset has no channels")
    if len(channels) != len(set(channels)):
        return _invalid(f"{pid}: preset lists a channel more than once")
    if len(channels) > MAX_CHART_SLOTS:
        return _invalid(f"{pid}: preset uses {len(channels)} slots, more than the {MAX_CHART_SLOTS} allowed")

    channel_set = set(channels)
    for cid in channels:
        if cid in SLOT_GROUPS:
            # §7.1: the group and its own members are mutually exclusive
            # on the chart, so a preset can't ask for both at once.
            overlapping = channel_set & set(SLOT_GROUPS[cid].members)
            if overlapping:
                return _invalid(f"{pid}: lists both the {cid!r} group and its own member {sorted(overlapping)[0]!r}")
            continue
        cdef = CHANNEL_REGISTRY.get(cid)
        if cdef is None:
            return _invalid(f"{pid}: references unknown channel {cid!r}")
        if not cdef.chartable:
            return _invalid(f"{pid}: references non-chartable channel {cid!r}")

    return []
