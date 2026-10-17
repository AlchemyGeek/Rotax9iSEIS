"""
Spec 10 v0.7 §6.3 (D6), acceptance 9-10; Spec 09 v0.15 acceptance 23.
Whole-log-set regression guards for the Phase D limit fixes (D14
volts_min, D16 rpm_idle_min) — real data, skips without it.
"""
import json

import pandas as pd
import pytest

from slingology_eis import workspace as ws
from slingology_eis.limits import check_exceedances, load_engine_config
from slingology_eis.loader import load_log_bytes
from slingology_eis.phases import detect_phases

from ..conftest import LOGS_DIR, TOOLKIT_ROOT, requires_flight_logs

REGISTER_PATH = TOOLKIT_ROOT / "docs" / "specs" / "topics" / "register.json"
WS_DIR = TOOLKIT_ROOT / "data" / "workspaces" / "ws_fb2fd312fde8"

# Two flights' header start_utc is 1 s off from their raw log filename's
# embedded timestamp (same known offset documented in the D16 measurement
# scripts) — hardcoded here rather than re-deriving the correction, since
# it's a fixed fact about these two files, not something that changes.
_FILENAME_FIXUPS = {
    "2ecf6193fb4bba2f": "log_20260508_225855_KPAE.csv",
    "584e022a47517397": "log_20260423_200615_KACV.csv",
}


def _raw_log_filename(fa):
    if fa.flight_id in _FILENAME_FIXUPS:
        return _FILENAME_FIXUPS[fa.flight_id]
    start_utc = fa.header.get("start_utc")
    airport = fa.header.get("airport_hint") or "?"
    if not start_utc:
        return None
    return (f"log_{start_utc[:4]}{start_utc[5:7]}{start_utc[8:10]}_"
            f"{start_utc[11:13]}{start_utc[14:16]}{start_utc[17:19]}_{airport}.csv")


@pytest.fixture(scope="module")
def register():
    return json.loads(REGISTER_PATH.read_text())


@pytest.fixture(scope="module")
def admitted_flights_with_raw():
    if not WS_DIR.exists():
        pytest.skip("no local workspace")
    manifest = ws.load_manifest(WS_DIR)
    engine_cfg = load_engine_config(manifest.engine_model)
    selection = ws.load_selection(WS_DIR)
    all_fas = ws.load_all_flight_analyses(WS_DIR)
    excluded_ids = {e["flight_id"] for e in selection.excluded}
    included = [fa for fa in all_fas if fa.flight_id not in excluded_ids]
    if not included:
        pytest.skip("no admitted flights")

    out = []
    for fa in included:
        fname = _raw_log_filename(fa)
        p = LOGS_DIR / fname if fname else None
        if not p or not p.exists():
            continue
        df, _info = load_log_bytes(p.read_bytes(), fname)
        df = detect_phases(df)
        events = check_exceedances(df, engine_config=engine_cfg)
        out.append((fa, df, events))
    if not out:
        pytest.skip("no admitted flights with a resolvable raw log")
    return out, engine_cfg


@requires_flight_logs
def test_limit_saturation_rate_at_most_half_unless_allowlisted(admitted_flights_with_raw, register):
    flights, _cfg = admitted_flights_with_raw
    n_total = len(flights)
    allowlisted = {e["limit_id"] for e in register["allowlist"] if e["aircraft"] == "N117ZS"}

    flights_with = {}
    for fa, df, events in flights:
        for lid in {e.limit_id for e in events}:
            flights_with.setdefault(lid, set()).add(fa.flight_id)

    report = {lid: len(fids) / n_total for lid, fids in flights_with.items()}
    print(f"\nlimit saturation rates (n={n_total} flights):")
    for lid, rate in sorted(report.items(), key=lambda kv: -kv[1]):
        flag = " (allowlisted)" if lid in allowlisted else ""
        print(f"  {lid}: {rate:.2f} ({len(flights_with[lid])}/{n_total}){flag}")

    violations = {
        lid: rate for lid, rate in report.items()
        if rate > 0.5 and lid not in allowlisted
    }
    assert not violations, f"limit(s) over the 50% saturation bar with no allowlist entry: {violations}"


@requires_flight_logs
def test_no_event_lies_wholly_within_start_warmup_or_post_shutdown(admitted_flights_with_raw):
    from slingology_eis.phases import Phase
    excluded_phases = {Phase.ENGINE_START, Phase.WARMUP, Phase.SHUTDOWN, Phase.PRE_START}
    flights, _cfg = admitted_flights_with_raw
    offenders = []
    for fa, df, events in flights:
        for e in events:
            mask = (df["datetime"] >= e.started_at) & (df["datetime"] <= e.ended_at)
            phases_seen = set(df.loc[mask, "phase"])
            if phases_seen and phases_seen.issubset(excluded_phases):
                offenders.append((fa.flight_id, e.limit_id, e.started_at, phases_seen))
    assert not offenders, f"event(s) wholly inside a start/warmup/shutdown phase: {offenders}"


@requires_flight_logs
def test_no_event_built_from_engine_stopped_readings(admitted_flights_with_raw):
    flights, cfg = admitted_flights_with_raw
    gated_limit_ids = {l["id"] for l in cfg["limits"] if l.get("min_rpm")}
    offenders = []
    for fa, df, events in flights:
        for e in events:
            if e.limit_id not in gated_limit_ids:
                continue
            mask = (df["datetime"] >= e.started_at) & (df["datetime"] <= e.ended_at)
            rpm_window = df.loc[mask, "rpm"].fillna(0)
            if (rpm_window < 1000).any():
                offenders.append((fa.flight_id, e.limit_id, e.started_at, rpm_window.min()))
    assert not offenders, f"gated limit event(s) with an engine-stopped reading in their window: {offenders}"


@requires_flight_logs
def test_kfcm_spool_up_raises_no_rpm_idle_min_event(admitted_flights_with_raw):
    flights, _cfg = admitted_flights_with_raw
    kfcm = next((f for f in flights if f[0].header.get("date") == "2026-07-18"
                 and f[0].header.get("airport_hint") == "KFCM"), None)
    if kfcm is None:
        pytest.skip("KFCM 2026-07-18 not in the admitted log set")
    fa, df, events = kfcm
    idle_events = [e for e in events if e.limit_id == "rpm_idle_min"]
    assert idle_events == [], f"KFCM spool-up unexpectedly raised rpm_idle_min event(s): {idle_events}"


@requires_flight_logs
def test_volts_min_survivors_are_all_engine_running(admitted_flights_with_raw):
    """Spec 09 acceptance 23: after the gate, no volts_min event remains
    at 0.0 V with the engine stopped — report every survivor and its rpm
    context."""
    flights, _cfg = admitted_flights_with_raw
    survivors = []
    for fa, df, events in flights:
        for e in events:
            if e.limit_id != "volts_min":
                continue
            mask = (df["datetime"] >= e.started_at) & (df["datetime"] <= e.ended_at)
            rpm_window = df.loc[mask, "rpm"].fillna(0)
            survivors.append((fa.flight_id, fa.header.get("date"), e.observed_value,
                              e.duration_s, float(rpm_window.min())))
    print(f"\nvolts_min survivors after the min_rpm gate: {len(survivors)}")
    for s in survivors:
        print(f"  {s}")
    zero_volt_stopped = [s for s in survivors if s[2] == 0.0 and s[4] < 1000]
    assert zero_volt_stopped == [], f"survivor(s) still at 0.0 V with the engine stopped: {zero_volt_stopped}"
    for s in survivors:
        assert s[4] >= 1000, f"survivor {s} has rpm below the gate — min_rpm isn't actually excluding it"


def test_volts_min_synthetic_inflight_drop_raises_one_event():
    cfg = load_engine_config("916iS")
    n = 120
    df = pd.DataFrame({
        "datetime": pd.date_range("2026-01-01 12:00:00", periods=n, freq="1s"),
        "rpm": [5000.0] * n,
        "main_volts": [13.0] * 30 + [11.0] * 60 + [13.0] * 30,
    })
    events = [e for e in check_exceedances(df, cfg) if e.limit_id == "volts_min"]
    assert len(events) == 1
    assert events[0].observed_value == 11.0
    assert events[0].duration_s == 60.0
