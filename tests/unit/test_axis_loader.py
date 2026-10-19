"""
Spec 01 v0.23 §6.5 — the Garmin AXIS log source, on synthetic files:
header detection, the column mapping, 1-second resampling, channel
assignment gating, the fingerprint's source identity, and the unknown-format
error naming all three layouts.
"""
import numpy as np
import pandas as pd
import pytest

from slingology_eis.limits import load_engine_config
from slingology_eis.loader import flight_fingerprint, flight_id, load_log_bytes
from slingology_eis.operations import analyze_flight

from .test_server import _flying_log_bytes

AXIS_META = ('#airframe_info, log_version="1.04", log_content_version="1.00", Product="AXIS", '
             'unit_software_part_number="006-B4075-07", unit_software_version="2.21", '
             'system_software_part_number="006-B4957-07", mode="NORMAL", tail_number="N999XX"\n')
COLUMNS = ["localDate", "localTime", "utcOffset", "systemTime", "flightTime", "indicatedAirspeed",
           "engine1RevolutionsPerMinute", "engine1OilTemperature", "fuelLevel1", "fuelLevel2",
           "engine1Volts1", "engine1Amps2", "onGroundState", "e1TachTime",
           "engine1GeneralPurposeAnalog7", "crewAlertingSystemAlert"]
UNITS = ["yyyy-mm-dd", "hh:mm:ss", "+/-hh:mm", "millisecond", "hour", "knots", "rotations per minute",
         "fahrenheit", "gallons", "gallons", "volts", "amps", "boolean", "hour", "float", "text"]


def _axis(seconds, cas=None, analog=None, tail="N999XX") -> bytes:
    """An AXIS file with rows at the given whole seconds after 12:00:00."""
    rows = []
    for i, s in enumerate(seconds):
        t = pd.Timestamp("2026-10-14 12:00:00") + pd.Timedelta(seconds=s)
        rows.append([t.strftime("%Y-%m-%d"), t.strftime("%H:%M:%S"), "+00:00", str(s * 1000), "0.1",
                     str(80 + s), str(5000 + 10 * s), str(180 + s), "15.0", "7.0", "13.8", "1.0",
                     "false", "119.6", str(analog(s) if analog else 9.0),
                     (cas(s) if cas else "")])
    body = "\n".join(",".join(r) for r in rows)
    return (AXIS_META.replace("N999XX", tail) + "#" + ",".join(UNITS) + "\n" + ",".join(COLUMNS) + "\n" + body + "\n").encode()


def test_axis_is_detected_and_its_metadata_mapped():
    df, info = load_log_bytes(_axis([0, 1, 2]), "a.csv")
    assert info.source_format == "axis"
    assert info.aircraft_ident == "N999XX" and info.product == "AXIS" and info.system_id == ""
    assert info.engine_hours == 119.6 and info.airframe_hours is None


def test_axis_columns_map_to_registry_ids():
    df, _ = load_log_bytes(_axis([0, 1, 2]), "a.csv")
    for cid in ("ias_kt", "rpm", "oil_temp_f", "fuel_qty_l_gal", "fuel_qty_r_gal", "main_volts", "batt_amps",
                "cas_alert", "on_ground", "flight_time_h", "tach_time_h", "gp_analog_7"):
        assert cid in df.columns, cid
    assert df["rpm"].iloc[0] == 5000 and df["fuel_qty_r_gal"].iloc[0] == 7.0
    assert df["on_ground"].iloc[0] is False or df["on_ground"].iloc[0] == False  # noqa: E712
    assert "co_ppm" not in df.columns                   # never mapped by assumption
    assert "engine1RevolutionsPerMinute" not in df.columns


def test_resampling_fills_short_holes_only_and_marks_them():
    # Holes: 2 s (one missing second at 3), 3 s (two missing at 6, 7), 5 s (four missing, 9–12).
    secs = [0, 1, 2, 4, 5, 8, 13]
    df, info = load_log_bytes(_axis(secs, cas=lambda s: "CO PPM" if s == 2 else ""), "a.csv", max_fill_gap_s=2)
    assert len(df) == 14                                 # 12:00:00–12:00:13 on a 1 s grid
    by_s = df.set_index(df["elapsed_s"].astype(int))
    assert bool(by_s.loc[3, "_filled"]) and bool(by_s.loc[6, "_filled"]) and bool(by_s.loc[7, "_filled"])
    assert by_s.loc[3, "rpm"] == 5030                    # linear between 5020 and 5040
    assert by_s.loc[3, "cas_alert"] == "CO PPM"          # text carried forward
    for s in (9, 10, 11, 12):                            # a 4 s hole is longer than the limit
        assert not bool(by_s.loc[s, "_filled"]) and np.isnan(by_s.loc[s, "rpm"])
    assert info.filled_share == pytest.approx(3 / 14)
    assert not df.loc[df["elapsed_s"].isin([0, 1, 2, 4, 5, 8, 13]), "_filled"].any()


def test_g3x_frames_are_never_resampled():
    df, info = load_log_bytes(_flying_log_bytes(), "g.csv")
    assert info.source_format == "g3x_direct" and "_filled" not in df.columns and info.filled_share == 0


def test_channel_assignment_gating():
    data = _axis([0, 1, 2], analog=lambda s: 4.0 + s)
    df, _ = load_log_bytes(data, "a.csv")
    assert "co_ppm" not in df.columns
    df, _ = load_log_bytes(data, "a.csv", channel_assignments={"gp_analog_7": "co_ppm"})
    assert list(df["co_ppm"]) == [4.0, 5.0, 6.0] and "gp_analog_7" in df.columns
    # Never onto a channel the source logs natively, nor from a channel it lacks.
    df, _ = load_log_bytes(data, "a.csv", channel_assignments={"gp_analog_7": "rpm", "gp_analog_3": "co_ppm"})
    assert df["rpm"].iloc[0] == 5000 and "co_ppm" not in df.columns
    # A G3X log has no raw general-purpose channels: nothing to apply.
    g, _ = load_log_bytes(_flying_log_bytes(), "g.csv", channel_assignments={"gp_analog_7": "co_ppm"})
    assert "co_ppm" not in g.columns


def test_fingerprint_source_identity():
    d1, i1 = load_log_bytes(_axis([0, 1, 2]), "a.csv")
    d2, i2 = load_log_bytes(_axis([0, 1, 2]), "copy-elsewhere.csv")
    assert flight_fingerprint(d1, i1)[1] == "AXIS"
    assert flight_id(flight_fingerprint(d1, i1)) == flight_id(flight_fingerprint(d2, i2))
    g, gi = load_log_bytes(_flying_log_bytes(), "g.csv")
    assert flight_fingerprint(g, gi)[1] == gi.system_id      # G3X unchanged


def test_unknown_format_names_all_three_layouts():
    with pytest.raises(ValueError) as e:
        load_log_bytes(b'#airframe_info, Product="OTHER"\n#a,b\nx,y\n1,2\n', "x.csv")
    msg = str(e.value)
    assert "unrecognised header format" in msg
    assert "G3X-direct" in msg and "Garmin Pilot" in msg and "AXIS" in msg


def test_analyze_flight_reports_the_resampling():
    fa = analyze_flight(_axis(list(range(0, 600, 1)) + [601, 602]), "a.csv", load_engine_config("916iS"), "916iS")
    codes = [q["code"] for q in fa.quality]
    assert "LOG_RESAMPLED_TO_1HZ" in codes
    g = analyze_flight(_flying_log_bytes(), "g.csv", load_engine_config("916iS"), "916iS")
    assert "LOG_RESAMPLED_TO_1HZ" not in [q["code"] for q in g.quality]
    assert "channel_assignments" not in g.provenance


def test_cas_aliases_and_separator_normalised_to_g3x_wording():
    """Spec 01 v0.24 §6.5: one name per alert across sources; unknown tokens
    pass through; `TER N/A` (which holds the separator) stays one alert."""
    cas = {0: "EFIS ON BACKUP/NAV ON BACKUP/ENGINE ECU", 1: "TER N/A/TRAFFIC FAIL", 2: "SOME NEW ALERT"}
    df, _ = load_log_bytes(_axis([0, 1, 2], cas=lambda s: cas[s]), "a.csv")
    assert list(df["cas_alert"]) == ["EFIS ON BKUP / NAV ON BKUP / ENGINE ECU", "TER NA / TRAFFIC FAIL", "SOME NEW ALERT"]
    from slingology_eis.cas import _split_cas
    assert _split_cas(df["cas_alert"].iloc[1]) == ["TER NA", "TRAFFIC FAIL"]


def test_column_set_is_mapped_by_name_not_position():
    """Spec 01 v0.24: the AXIS writes only the channels that carried data, so
    columns come and go — unknown ones are tolerated, order doesn't matter."""
    base = _axis([0, 1, 2]).decode().splitlines()
    meta, units, header, rows = base[0], base[1].lstrip("#").split(","), base[2].split(","), [r.split(",") for r in base[3:]]
    order = list(reversed(range(len(header))))
    shuffled = "\n".join([
        meta,
        "#" + ",".join([units[i] for i in order] + ["degrees"]),
        ",".join([header[i] for i in order] + ["flightDirectorPitchCommand"]),
        *[",".join([r[i] for i in order] + ["1.5"]) for r in rows],
    ]) + "\n"
    a, _ = load_log_bytes(_axis([0, 1, 2]), "a.csv")
    b, info = load_log_bytes(shuffled.encode(), "b.csv")
    assert info.source_format == "axis"
    for cid in ("rpm", "ias_kt", "oil_temp_f", "fuel_qty_l_gal", "cas_alert", "gp_analog_7"):
        pd.testing.assert_series_equal(a[cid], b[cid], check_names=False, obj=cid)


def test_a_log_opening_with_the_engine_running_raises_nothing():
    """AXIS never logs the engine start (Spec 01 v0.24): no diagnostic beyond
    the resampling note, and no GROUND_START run."""
    fa = analyze_flight(_axis(list(range(0, 600))), "a.csv", load_engine_config("916iS"), "916iS")
    codes = [q["code"] for q in fa.quality]
    assert "LOG_RESAMPLED_TO_1HZ" in codes
    assert not [c for c in codes if any(w in c for w in ("START", "POWER", "CYCLE", "CORRUPT"))], codes
    assert not [r for r in fa.ecu_runs if r["classification"] == "GROUND_START"]
