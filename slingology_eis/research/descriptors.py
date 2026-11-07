"""
Descriptors (Spec 06 §6) and the §7.0 window rule.

Every function here works on one slice's samples on the 1-second grid
(index = seconds), with NaN where a channel has no reading. Filled rows
— seconds the AXIS resampling filled in (Spec 01 §6.5) — are passed as a
mask and excluded from **rate and period** descriptors (§5.6), and from
coupling, which is a lag search; level and spread descriptors use them.

Numbers are rounded to fixed decimals so the JSON is the same under every
host (Spec 04 parity): the CLI, the server and Pyodide must print
byte-identical results (acceptance 7).

§7.0 (Q9): the multipliers chosen inside the spec's bands are the
constants below. Periods are searched on the whole detrended slice
between `PERIOD_SEARCH_MIN_S` and `PERIOD_MAX_FRACTION` of its duration;
a set whose slices mostly carry a prominent period P gets a swing window
of `WINDOW_PERIODS` × median P and a lag range of ± `LAG_PERIODS` ×
median P; otherwise both scale with the median slice duration. Both are
bounded below by the acceptance case's floors.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

# ── §7.0 window rule (Q9) ──────────────────────────────────────────────────
WINDOW_FLOOR_S = 12            # fixed by the acceptance case
LAG_FLOOR_S = 10               # fixed by the acceptance case
WINDOW_PERIODS = 2.5           # band 2–3 P: whole cycles, so it measures swing rather than noise
LAG_PERIODS = 1.5              # ±1.5 P: the lag of maximum correlation is unambiguous within one period either way
WINDOW_DURATION_FRACTION = 0.2  # no prominent period: a fifth of the median slice
LAG_DURATION_FRACTION = 0.1     # … and a tenth either way for the lag range
PROMINENT_SET_SHARE = 0.5      # "the set has a prominent median period": at least half its slices do

# ── Periodicity (§6, §5.6) ─────────────────────────────────────────────────
PERIOD_SEARCH_MIN_S = 2        # Nyquist at 1 Hz
PERIOD_FLOOR_S = 3.0           # below about 3 s a period is unreliable at 1 Hz (§5.6): never counted as prominent
PERIOD_MAX_FRACTION = 1 / 3    # at least three cycles in the slice, so a trend is never read as half a cycle
PROMINENCE_MIN = 0.2           # default minimum prominence (a test parameter, §7.1)
LS_AGREEMENT = 0.2             # the periodogram's peak must lie within ±20 % of the autocorrelation's
_LS_GRID = 400

STANDARD_CHANNELS = (
    "rpm", "map_inhg", "fuel_flow_gph", "egt1_f", "egt2_f", "egt3_f", "egt4_f",
    "oil_press_psi", "oil_temp_f", "coolant_temp_f", "fuel_press_psi", "main_volts",
)


def _r(x, nd: int = 4):
    """A JSON-stable float (or None)."""
    if x is None:
        return None
    x = float(x)
    if not math.isfinite(x):
        return None
    v = round(x, nd)
    return 0.0 if v == 0 else v


def detrend(y: np.ndarray) -> np.ndarray:
    """Remove the least-squares line through the finite samples."""
    t = np.arange(len(y), dtype=float)
    m = np.isfinite(y)
    if m.sum() < 3:
        return np.full_like(y, np.nan, dtype=float)
    p = np.polyfit(t[m], y[m], 1)
    return y - np.polyval(p, t)


def _acf(y: np.ndarray, max_lag: int) -> np.ndarray:
    """Autocorrelation of a centred series with gaps (NaN): sums over the
    pairs both present, normalised by the total power (the biased
    estimator, which keeps r ≤ 1)."""
    y = y - np.nanmean(y)
    v = np.where(np.isfinite(y), y, 0.0)
    denom = float(np.dot(v, v))
    if denom <= 0:
        return np.zeros(max_lag + 1)
    n = len(v)
    return np.array([float(np.dot(v[:n - k], v[k:])) / denom for k in range(max_lag + 1)])


def lomb_scargle_peak(y: np.ndarray, p_min: float, p_max: float) -> tuple[Optional[float], float]:
    """Period of the Lomb–Scargle periodogram's peak between p_min and
    p_max (seconds), tolerant of gaps; and its normalised power."""
    t = np.flatnonzero(np.isfinite(y)).astype(float)
    if len(t) < 8 or p_max <= p_min:
        return None, 0.0
    v = y[np.isfinite(y)]
    v = v - v.mean()
    var = float(np.dot(v, v))
    if var <= 0:
        return None, 0.0
    f = np.linspace(1.0 / p_max, 1.0 / p_min, _LS_GRID)
    w = 2 * np.pi * f[:, None]
    tau = np.arctan2(np.sin(2 * w * t).sum(axis=1), np.cos(2 * w * t).sum(axis=1))[:, None] / (2 * w)
    c, s = np.cos(w * (t - tau)), np.sin(w * (t - tau))
    power = ((c @ v) ** 2 / (c * c).sum(axis=1) + (s @ v) ** 2 / (s * s).sum(axis=1)) / var
    k = int(np.argmax(power))
    return float(1.0 / f[k]), float(power[k])


def dominant_period(y: np.ndarray, filled: Optional[np.ndarray] = None,
                    prominence_min: float = PROMINENCE_MIN) -> dict:
    """§6 periodicity on the whole detrended slice: the first
    autocorrelation peak beyond lag 1 (refined between samples), its
    prominence — (peak − deepest trough before it) / 2, so a clean sine
    scores 1 — and the periodogram's peak as a cross-check. `prominent`
    when the prominence reaches `prominence_min`, the two estimates agree
    and the period is above the sampling floor."""
    y = np.array(y, dtype=float)
    if filled is not None:
        y[filled] = np.nan
    n = len(y)
    out = {"period_s": None, "period_prominence": 0.0, "period_ls_s": None, "period_prominent": False}
    max_lag = int(n * PERIOD_MAX_FRACTION)
    if max_lag < PERIOD_SEARCH_MIN_S + 1 or np.isfinite(y).sum() < 8:
        return out
    yd = detrend(y)
    r = _acf(yd, max_lag + 1)
    peak = None
    for k in range(PERIOD_SEARCH_MIN_S, max_lag + 1):
        if r[k] >= r[k - 1] and r[k] >= r[k + 1] and r[k] > 0:
            peak = k
            break
    ls_p, _ = lomb_scargle_peak(yd, float(PERIOD_SEARCH_MIN_S), float(max_lag))
    out["period_ls_s"] = _r(ls_p, 3)
    if peak is None:
        return out
    a, b, c = r[peak - 1], r[peak], r[peak + 1]
    den = a - 2 * b + c
    period = peak + (0.5 * (a - c) / den if den != 0 else 0.0)
    prominence = (b - float(r[1:peak + 1].min())) / 2
    agree = ls_p is not None and abs(ls_p - period) <= LS_AGREEMENT * period
    out.update(period_s=_r(period, 3), period_prominence=_r(prominence, 3),
               period_prominent=bool(prominence >= prominence_min and agree and period >= PERIOD_FLOOR_S))
    return out


def swing(y: np.ndarray, window_s: int) -> Optional[float]:
    """Peak-to-peak: the median, over every window of `window_s` seconds
    with at least 80 % of its samples, of max − min. A slice shorter than
    one window gives its own max − min."""
    y = np.asarray(y, dtype=float)
    n, w = len(y), int(window_s)
    if np.isfinite(y).sum() < 2:
        return None
    if n <= w:
        return float(np.nanmax(y) - np.nanmin(y))
    win = np.lib.stride_tricks.sliding_window_view(y, w)
    ok = np.isfinite(win).sum(axis=1) >= 0.8 * w
    if not ok.any():
        return float(np.nanmax(y) - np.nanmin(y))
    win = win[ok]
    with np.errstate(all="ignore"):
        return float(np.median(np.nanmax(win, axis=1) - np.nanmin(win, axis=1)))


def _pearson(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 6:
        return None
    x, y = a[m] - a[m].mean(), b[m] - b[m].mean()
    d = math.sqrt(float(np.dot(x, x)) * float(np.dot(y, y)))
    return float(np.dot(x, y)) / d if d > 0 else None


def coupling(ref: np.ndarray, y: np.ndarray, lag_s: int, filled: Optional[np.ndarray] = None) -> dict:
    """§6 coupling with a reference channel over ±lag_s: zero-lag
    correlation, the lag of maximum correlation (positive: this channel
    follows the reference by that many seconds) and the correlation there.
    Both detrended; filled rows excluded."""
    a, b = np.array(ref, dtype=float), np.array(y, dtype=float)
    if filled is not None:
        a[filled] = np.nan
        b[filled] = np.nan
    a, b = detrend(a), detrend(b)
    n = len(a)
    best_k, best = None, None
    corr0 = _pearson(a, b)
    for k in sorted(range(-int(lag_s), int(lag_s) + 1), key=abs):
        if abs(k) >= n - 6:
            continue
        c = _pearson(a[:n - k], b[k:]) if k >= 0 else _pearson(a[-k:], b[:n + k])
        if c is not None and (best is None or c > best + 1e-12):
            best_k, best = k, c
    return {"corr0": _r(corr0), "lag_s": best_k, "corr_at_lag": _r(best)}


def describe_channel(y: np.ndarray, filled: np.ndarray, anchor_i: int, window_s: int,
                     ref: Optional[np.ndarray] = None, lag_s: Optional[int] = None,
                     prominence_min: float = PROMINENCE_MIN) -> dict:
    """The §6 descriptor set of one channel over one slice."""
    y = np.asarray(y, dtype=float)
    fin = np.isfinite(y)
    out: dict = {"samples": int(fin.sum()), "dropouts": int((~fin).sum())}
    if fin.sum() == 0:
        return out
    v = y[fin]
    q1, q3 = np.percentile(v, [25, 75])
    med = float(np.median(v))
    t = np.flatnonzero(fin).astype(float)
    slope = float(np.polyfit(t, v, 1)[0]) * 60 if len(v) >= 3 else None
    # Rate: consecutive seconds, both read (not filled).
    real = fin & ~filled
    pair = real[1:] & real[:-1]
    rate = float(np.max(np.abs(np.diff(y)[pair]))) if pair.any() else None
    at_anchor = y[anchor_i] if 0 <= anchor_i < len(y) and fin[anchor_i] else v[0]
    out.update({
        "mean": _r(v.mean()), "median": _r(med), "min": _r(v.min()), "max": _r(v.max()), "at_anchor": _r(at_anchor),
        "sd": _r(v.std(ddof=1) if len(v) > 1 else 0.0), "mad": _r(np.median(np.abs(v - med))), "iqr": _r(q3 - q1),
        "swing": _r(swing(y, window_s)), "slope_per_min": _r(slope), "max_rate_per_s": _r(rate),
    })
    out.update(dominant_period(y, filled, prominence_min))
    if ref is not None and lag_s is not None:
        out.update(coupling(ref, y, lag_s, filled))
    return out


# ── §7.0: windows proposed from the data ───────────────────────────────────

def resolve_window(periods: list[dict], durations: list[float], override: Optional[dict] = None) -> dict:
    """Swing window and lag range for one channel over a slice set, from
    its slices' period estimates (pass 1) and durations. Overrides
    (per study, §7.0) win and are reported as such."""
    prominent = [p["period_s"] for p in periods if p.get("period_prominent") and p.get("period_s")]
    n = len(periods)
    median_period = float(np.median(prominent)) if prominent else None
    median_duration = float(np.median(durations)) if durations else 0.0
    if prominent and len(prominent) >= PROMINENT_SET_SHARE * n:
        basis = "period"
        window = max(WINDOW_FLOOR_S, math.ceil(WINDOW_PERIODS * median_period))
        lag = max(LAG_FLOOR_S, math.ceil(LAG_PERIODS * median_period))
    else:
        basis = "duration"
        window = max(WINDOW_FLOOR_S, math.ceil(WINDOW_DURATION_FRACTION * median_duration))
        lag = max(LAG_FLOOR_S, math.ceil(LAG_DURATION_FRACTION * median_duration))
    out = {"window_s": int(window), "lag_s": int(lag), "basis": basis,
           "median_period_s": _r(median_period, 3), "prominent_slices": len(prominent), "slices": n,
           "median_duration_s": _r(median_duration, 1)}
    if override:
        if override.get("window_s") is not None:
            out["window_s"], out["basis"] = int(override["window_s"]), "override"
        if override.get("lag_s") is not None:
            out["lag_s"], out["basis"] = int(override["lag_s"]), "override"
    return out
