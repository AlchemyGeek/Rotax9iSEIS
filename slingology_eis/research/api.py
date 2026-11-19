"""
One code path for a question (Spec 16 D12, acceptance 12): the host's
`run_test` (the `question_run` tool) and the bench's `eis.cycling(...)`
and friends both call `run_question`, so a notebook's number is the
tool's number.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from . import questions as Q
from .slices import build_slice_set


def channels_for(test_id: str, channels: Optional[list], params: Optional[dict]) -> tuple[list[str], str]:
    from .studies import _channels_for, _test
    return _channels_for(_test({"test_id": test_id, "params": dict(params or {}), "channels": list(channels or [])}))


async def run_question(ws_dir: Path, sources, *, test_id: str, selection: Optional[dict], slice_rules: list,
                       hand_slices: Optional[list] = None, channels: Optional[list] = None,
                       params: Optional[dict] = None, references: Optional[list] = None,
                       windows: Optional[dict] = None, engine_cfg: Optional[dict] = None,
                       assignments: Optional[dict] = None, cache=None, prominence_min: float = 0.2,
                       on_progress: Optional[Callable] = None) -> dict:
    """The §8 result of one test on the slice set the selection, (resolved)
    rules and hand slices make."""
    chans, ref = channels_for(test_id, channels, params)
    ss = await build_slice_set(ws_dir, sources, selection=selection, rules=list(slice_rules or []),
                               hand_slices=hand_slices, channels=chans, reference=ref, windows=windows,
                               prominence_min=float(prominence_min), assignments=assignments, cache=cache,
                               on_progress=on_progress)
    d = ss.to_dict()
    d["selection"] = selection or {"mode": "all"}
    return Q.run(test_id, d, channels=list(channels or []) or None, params=dict(params or {}),
                 references=references, engine_cfg=engine_cfg)


async def compare(ws_dir: Path, sources, *, selection: Optional[dict], slice_rules: list,
                  hand_slices: Optional[list] = None, channels: Optional[list] = None,
                  windows: Optional[dict] = None, pinned: Optional[str] = None, collapse: bool = False,
                  engine_cfg: Optional[dict] = None, assignments: Optional[dict] = None, cache=None,
                  on_progress: Optional[Callable] = None) -> dict:
    """§9.2 Compare over the slice set (the rows_compare tool and eis.compare)."""
    from .. import workspace as ws
    from .compare import compare_rows
    from .slices import _selected_flights
    ss = await build_slice_set(ws_dir, sources, selection=selection, rules=list(slice_rules or []),
                               hand_slices=hand_slices, channels=list(channels or ["rpm", "map_inhg"]),
                               reference="rpm", windows=windows, assignments=assignments, cache=cache,
                               on_progress=on_progress)
    d = ss.to_dict()
    selected, _missing = _selected_flights(ws_dir, selection or {"mode": "all"})
    selected = list(dict.fromkeys(selected + [h["flight"] for h in ss.hand_slices]))
    meta = {}
    for fid in selected:
        if fid in set(d["unreachable_flights"]):
            continue
        fa = ws.load_flight_analysis(ws_dir, fid)
        if fa is not None:
            meta[fid] = {"date": fa.header.get("date"), "start_utc": fa.header.get("start_utc")}
    out = compare_rows(d, channels=ss.channels, pinned=pinned, collapse=bool(collapse), flights=meta,
                       engine_cfg=engine_cfg)
    out["selection"] = selection or {"mode": "all"}
    return out
