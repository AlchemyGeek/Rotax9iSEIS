"""
notebooks/06_phase_regression.py
================================
Before/after check for changes to phase detection (or anything else that
feeds per-flight metrics and exceedances). Phase detection is a set of
heuristics tuned on real logs; a tweak that fixes one flight can quietly
change others. Snapshot first, change the code, then compare: the report
lists every log whose phase labels, metrics or exceedances moved, so each
change can be confirmed as intended before it's committed.

Usage
-----
    # 1. before touching the code
    python notebooks/06_phase_regression.py --save before
    # 2. make the change, then
    python notebooks/06_phase_regression.py --compare before

Snapshots are written to data/phase_snapshots/<name>.pkl. They are derived
from private flight logs, so they stay under data/ (gitignored) — never
commit them.

The comparison prints, per changed log, the phase sequence around the first
changed row (before and after, as phase:rows segments), then every changed
metric and every exceedance added or removed. Ground sessions and other
logs the loader would skip are included: phase detection runs on them too.
"""

import argparse
import math
import pickle
import sys
import warnings
from dataclasses import asdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TOOLKIT = _HERE.parent
sys.path.insert(0, str(_TOOLKIT))

from slingology_eis.fleet import compute_flight_metrics  # noqa: E402
from slingology_eis.limits import check_exceedances, load_engine_config  # noqa: E402
from slingology_eis.loader import load_log_bytes  # noqa: E402
from slingology_eis.phases import detect_phases  # noqa: E402

SNAPSHOT_DIR = _TOOLKIT / "data" / "phase_snapshots"


def _snapshot(logs_dir: Path, engine: str) -> dict:
    cfg = load_engine_config(engine)
    out = {}
    paths = sorted(p for p in logs_dir.iterdir() if p.suffix.lower() == ".csv")
    for i, path in enumerate(paths, 1):
        print(f"\r  {i}/{len(paths)} {path.name[:50]:50}", end="", file=sys.stderr)
        try:
            df, info = load_log_bytes(path.read_bytes(), path.name)
            df = detect_phases(df, verbose=False)
            fm = asdict(compute_flight_metrics(df, info, cfg))
            exc = sorted((e.limit_id, str(e.started_at), round(e.observed_value, 2), e.duration_s)
                         for e in check_exceedances(df, cfg))
            out[path.name] = {"phases": df["phase"].tolist(), "metrics": fm, "exceedances": exc}
        except Exception as e:  # a log that fails to load is itself worth reporting
            out[path.name] = {"error": f"{type(e).__name__}: {e}"}
    print(file=sys.stderr)
    return out


def _segments(phases: list[str]) -> list[str]:
    segs: list[list] = []
    for p in phases:
        if segs and segs[-1][0] == p:
            segs[-1][1] += 1
        else:
            segs.append([p, 1])
    return [f"{p}:{n}" for p, n in segs]


def _same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return (math.isnan(a) and math.isnan(b)) or abs(a - b) < 1e-6
    return a == b


def _fmt(v) -> str:
    return f"{v:.2f}" if isinstance(v, float) else str(v)


def _compare(before: dict, after: dict) -> int:
    changed = 0
    for name in sorted(set(before) | set(after)):
        b, a = before.get(name), after.get(name)
        if b is None or a is None:
            print(f"== {name}: {'new log' if b is None else 'log no longer present'}")
            changed += 1
            continue
        if "error" in b or "error" in a:
            if b.get("error") != a.get("error"):
                print(f"== {name}: error before={b.get('error')} after={a.get('error')}")
                changed += 1
            continue
        rows = [i for i, (x, y) in enumerate(zip(b["phases"], a["phases"])) if x != y]
        metrics = {k: (b["metrics"][k], a["metrics"].get(k)) for k in b["metrics"]
                   if not _same(b["metrics"][k], a["metrics"].get(k))}
        removed = sorted(set(b["exceedances"]) - set(a["exceedances"]))
        added = sorted(set(a["exceedances"]) - set(b["exceedances"]))
        if not (rows or metrics or removed or added):
            continue
        changed += 1
        print(f"== {name}")
        if rows:
            start = max(0, rows[0] - 5)
            print(f"   phases: {len(rows)} of {len(b['phases'])} rows changed, first at row {rows[0]}")
            print("     before: " + " > ".join(_segments(b["phases"][start:])[:14]))
            print("     after:  " + " > ".join(_segments(a["phases"][start:])[:14]))
        for k, (x, y) in metrics.items():
            print(f"   metric {k}: {_fmt(x)} -> {_fmt(y)}")
        for e in removed:
            print(f"   exceedance removed: {e}")
        for e in added:
            print(f"   exceedance added:   {e}")
    print(f"\n{changed} of {len(after)} logs changed")
    return changed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--save", metavar="NAME", help="snapshot the current code's results as NAME")
    group.add_argument("--compare", metavar="NAME", help="compare the current code against snapshot NAME")
    ap.add_argument("--logs", default=str(_TOOLKIT / "data" / "logs"))
    ap.add_argument("--engine", default=None)
    args = ap.parse_args()
    warnings.filterwarnings("ignore")

    current = _snapshot(Path(args.logs), args.engine)
    if args.save:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SNAPSHOT_DIR / f"{args.save}.pkl"
        pickle.dump(current, open(path, "wb"))
        print(f"saved {len(current)} logs to {path}")
        return
    path = SNAPSHOT_DIR / f"{args.compare}.pkl"
    if not path.exists():
        sys.exit(f"no snapshot {path}; run with --save {args.compare} first")
    _compare(pickle.load(open(path, "rb")), current)


if __name__ == "__main__":
    main()
