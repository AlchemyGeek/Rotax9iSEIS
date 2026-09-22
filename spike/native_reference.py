#!/usr/bin/env python3
"""
spike/native_reference.py

Run this on your Mac (native CPython, with the project's own venv active)
to produce a golden.json that the browser harness (spike/index.html) can
diff its Pyodide results against.

Usage
-----
    source ~/venvs/eis/bin/activate     # or wherever pandas/numpy live
    cd <repo-root>
    python3 spike/native_reference.py /path/to/log_20260423_200615_KACV.csv

Writes ./golden.json (repo root) by default; pass --out to change that.
Output shape matches what worker.js produces from the same pipeline, so
index.html's golden-diff view can load it directly.
"""
from __future__ import annotations

import argparse
import json
import math
import resource
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
sys.path.insert(0, str(_REPO))

import pandas as pd  # noqa: E402

from slingology_eis.loader import load_log  # noqa: E402
from slingology_eis.phases import detect_phases, phase_summary  # noqa: E402
from slingology_eis.fleet import build_flight_metrics  # noqa: E402


def clean(v):
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            return str(v)
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", help="Path to a G3X log CSV")
    parser.add_argument("--out", default=None, help="Output path (default: <repo-root>/golden.json)")
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else _REPO / "golden.json"

    results: dict = {"steps_s": {}}

    t0 = time.perf_counter()
    # (imports already happened above; measure re-import cost as ~0 for parity
    #  with the worker, which imports fresh inside its Python process)
    results["steps_s"]["import"] = 0.0

    t0 = time.perf_counter()
    df, info = load_log(args.log)
    results["steps_s"]["load_log"] = time.perf_counter() - t0
    results["rows"] = len(df)
    results["cols"] = len(df.columns)

    t0 = time.perf_counter()
    df = detect_phases(df)
    results["steps_s"]["detect_phases"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    summary = phase_summary(df)
    results["steps_s"]["phase_summary"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    metrics_df = build_flight_metrics([(df, info)], verbose=False)
    results["steps_s"]["build_flight_metrics"] = time.perf_counter() - t0

    row = metrics_df.iloc[0].to_dict()
    results["metrics"] = {k: clean(v) for k, v in row.items()}

    phases_out = []
    for _, r in summary.reset_index().iterrows():
        d = r.to_dict()
        phases_out.append({k: clean(v) for k, v in d.items()})
    results["phases"] = phases_out

    results["source_format"] = getattr(info, "source_format", None)
    results["total_wall_s"] = sum(results["steps_s"].values())

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    results["peak_rss_mb"] = round(rss / 1e6 if sys.platform == "darwin" else rss / 1e3)

    results["env"] = {
        "python_version": sys.version.split()[0],
        "pandas_version": pd.__version__,
        "numpy_version": __import__("numpy").__version__,
        "log_file": Path(args.log).name,
    }

    out_path.write_text(json.dumps(results, indent=2))
    print(f"Wrote {out_path}  ({results['rows']} rows, "
          f"total {results['total_wall_s']:.2f}s, peak {results['peak_rss_mb']} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
