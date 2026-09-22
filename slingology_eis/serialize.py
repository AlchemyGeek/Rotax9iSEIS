"""
serialize.py — the single JSON serializer for the toolkit.

Replaces the ad hoc pattern used by notebook 03 (json.dumps with a
`default=` hook, followed by a regex substitution of bare `NaN` tokens
for `null`). A `default=` hook is never invoked for native Python
floats — json.dumps handles those itself, writing a literal `NaN`,
which is not valid JSON — so numpy NaN values were being caught while
plain Python float('nan') values needed the regex patch to fix up
after the fact.

This module instead walks the structure once before calling json.dumps,
converting every NaN/Infinity (numpy or native) to None up front, so no
post-processing is needed and no bare NaN can ever be emitted.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from typing import Any

import numpy as np


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, np.floating):
        val = float(obj)
        return None if (math.isnan(val) or math.isinf(val)) else val
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return [_sanitize(v) for v in obj.tolist()]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


def dumps(obj: Any, **kwargs) -> str:
    """json.dumps, with NaN/Infinity (numpy or native) sanitized to null
    and numpy scalar/array and date/datetime types made serializable."""
    return json.dumps(_sanitize(obj), **kwargs)
