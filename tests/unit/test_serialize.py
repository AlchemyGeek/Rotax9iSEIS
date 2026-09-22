"""
Unit tests for the Stage 1 single JSON serializer (Spec 01 §11 Stage 1).
"""
import json
import math
from datetime import date, datetime

import numpy as np

from slingology_eis import serialize


def test_native_nan_and_inf_become_null():
    out = serialize.dumps({"a": float("nan"), "b": float("inf"), "c": float("-inf"), "d": 1.5})
    parsed = json.loads(out)
    assert parsed == {"a": None, "b": None, "c": None, "d": 1.5}
    assert "NaN" not in out
    assert "Infinity" not in out


def test_numpy_nan_and_scalar_types():
    out = serialize.dumps({
        "f": np.float64("nan"),
        "i": np.int64(7),
        "b": np.bool_(True),
        "arr": np.array([1.0, float("nan"), 3.0]),
    })
    parsed = json.loads(out)
    assert parsed == {"f": None, "i": 7, "b": True, "arr": [1.0, None, 3.0]}


def test_dates_and_nested_structures():
    out = serialize.dumps({
        "when": date(2026, 1, 1),
        "stamp": datetime(2026, 1, 1, 12, 30),
        "nested": {"x": [1, float("nan"), {"y": np.float64("nan")}]},
    })
    parsed = json.loads(out)
    assert parsed["when"] == "2026-01-01"
    assert parsed["stamp"] == "2026-01-01T12:30:00"
    assert parsed["nested"]["x"] == [1, None, {"y": None}]


def test_output_is_always_valid_json_even_with_heavy_nan():
    doc = {"values": [float("nan")] * 5, "n": np.int64(5)}
    out = serialize.dumps(doc, indent=2)
    reparsed = json.loads(out)  # would raise if any bare NaN token leaked through
    assert reparsed["n"] == 5
    assert all(v is None for v in reparsed["values"])
