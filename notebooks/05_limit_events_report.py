"""
notebooks/05_limit_events_report.py
===================================
Spec 09 §14.2 log-set report: how exceedance event counts depend on the
merge gap, and how far apart the raw exceedance runs of each limit are.
Use it to choose `exceedance_merge_gap_s` (and any per-limit override)
from real data rather than by guess.

Prints, for every limit with events:

  1. events per limit at a range of merge gaps,
  2. total time past the limit at each gap,
  3. the distribution of within-limit gaps between raw runs,
  4. limit/flight pairs that only have events once runs are merged
     (merging can turn short, discarded runs into one event that passes
     a limit's min-duration or time-limit rule).

Usage
-----
    python notebooks/05_limit_events_report.py [--engine 916iS] [--logs DIR]
"""

import argparse
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_TOOLKIT = _HERE.parent
sys.path.insert(0, str(_TOOLKIT))

from slingology_eis.limits import (  # noqa: E402
    check_exceedances,
    engine_limits_from_config,
    find_runs,
    load_engine_config,
    split_runs_at_time_gaps,
)
from slingology_eis.loader import load_directory  # noqa: E402
from slingology_eis.phases import detect_phases  # noqa: E402

GAPS_S = [0, 5, 10, 30, 60, 120]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--engine", default=None)
    ap.add_argument("--logs", default=str(_TOOLKIT / "data" / "logs"))
    args = ap.parse_args()
    warnings.filterwarnings("ignore")

    cfg = load_engine_config(args.engine)
    flights = load_directory(args.logs, verbose=False)
    print(f"{len(flights)} flights from {args.logs}, engine profile "
          f"{cfg.get('_metadata', {}).get('engine', '?')}, profile merge gap "
          f"{cfg.get('exceedance_merge_gap_s', 0)} s")

    counts = {g: Counter() for g in GAPS_S}
    time_above = {g: defaultdict(float) for g in GAPS_S}
    per_flight = {g: defaultdict(Counter) for g in GAPS_S}
    raw_gaps = defaultdict(list)
    overrides = {lim.id: lim.merge_gap_s for lim in engine_limits_from_config(cfg) if lim.merge_gap_s is not None}

    for df, info in flights:
        name = df["_source_file"].iloc[0]
        df = detect_phases(df, verbose=False)
        for g in GAPS_S:
            # The sweep applies each gap to every limit, ignoring per-limit
            # overrides, so an override's effect is visible in the table.
            c = {**cfg, "exceedance_merge_gap_s": g,
                 "limits": [{k: v for k, v in e.items() if k != "exceedance_merge_gap_s"} for e in cfg["limits"]]}
            for e in check_exceedances(df, c):
                counts[g][e.limit_id] += 1
                time_above[g][e.limit_id] += e.duration_s
                per_flight[g][name][e.limit_id] += 1
        for lim in engine_limits_from_config(cfg):
            if not lim.report_in_exceedances or lim.param not in df.columns:
                continue
            w = df[df["phase"].isin(lim.phases)] if lim.phases and "phase" in df.columns else df
            for side, v in (("MIN", lim.min_val), ("MAX", lim.max_val)):
                if v is None:
                    continue
                s = w[lim.param]
                runs = split_runs_at_time_gaps(w["datetime"], find_runs(s < v if side == "MIN" else s > v))
                t = w["datetime"]
                for (_, a_end), (b_start, _) in zip(runs, runs[1:]):
                    raw_gaps[lim.id].append((t.iloc[b_start] - t.iloc[a_end]).total_seconds() - 1)

    ids = sorted(set().union(*[set(c) for c in counts.values()]))
    header = f"{'limit_id':24}" + "".join(f"{g:>8}" for g in GAPS_S)

    print("\n1. Events per limit, by merge gap (s)")
    print(header)
    for i in ids:
        note = f"   (profile override: {overrides[i]:g} s)" if i in overrides else ""
        print(f"{i:24}" + "".join(f"{counts[g][i]:>8}" for g in GAPS_S) + note)
    print(f"{'TOTAL':24}" + "".join(f"{sum(counts[g].values()):>8}" for g in GAPS_S))

    print("\n2. Total time past the limit (min), by merge gap (s)")
    print(header)
    for i in ids:
        print(f"{i:24}" + "".join(f"{time_above[g][i] / 60:>8.1f}" for g in GAPS_S))

    print("\n3. Within-limit gap between raw runs (s)")
    print(f"{'limit_id':24}{'p25':>7}{'p50':>7}{'p75':>7}{'p90':>8}{'n':>8}{'<=30s':>8}{'<=60s':>8}")
    for i, gs in sorted(raw_gaps.items()):
        a = np.array(gs)
        if len(a) == 0:
            continue
        print(f"{i:24}{np.percentile(a, 25):7.0f}{np.percentile(a, 50):7.0f}{np.percentile(a, 75):7.0f}"
              f"{np.percentile(a, 90):8.0f}{len(a):8}{np.mean(a <= 30):8.2f}{np.mean(a <= 60):8.2f}")

    print("\n4. Limit/flight pairs with events only once runs are merged")
    for g in GAPS_S[1:]:
        new = sorted((f, i) for f, c in per_flight[g].items() for i in c if per_flight[0][f][i] == 0)
        by_limit = Counter(i for _, i in new)
        print(f"  gap {g:>3} s: " + (", ".join(f"{i} x{n}" for i, n in sorted(by_limit.items())) or "none"))


if __name__ == "__main__":
    main()
