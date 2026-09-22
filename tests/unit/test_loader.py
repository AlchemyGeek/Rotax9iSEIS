"""
Unit tests for the Stage 1 bytes-based core loader (Spec 01 §11 Stage 1).

Uses fabricated, synthetic log content only — not real flight data — so
these run without any private local logs.
"""
from slingology_eis.loader import load_log, load_log_bytes

_META = (
    'aircraft_ident="N999XX", product="GDU 460", system_id="123456789", '
    'unit="1", airframe_hours="10.5", engine_hours="20.1", log_version="7"\n'
)
_HEADER = "Date (yyyy-mm-dd),Time (hh:mm:ss),RPM,Oil Temp (deg F)\n"
_ROWS = (
    "2026-01-01,12:00:00,2000,180\n"
    "2026-01-01,12:00:01,2010,181\n"
    "2026-01-01,12:00:02,2020,182\n"
)


def _g3x_direct_bytes() -> bytes:
    return (_META + _HEADER + _ROWS).encode("utf-8")


def _garmin_pilot_bytes() -> bytes:
    return (_META + "#" + _HEADER + _ROWS).encode("utf-8")


def test_load_log_bytes_g3x_direct():
    df, info = load_log_bytes(_g3x_direct_bytes(), "log_20260101_120000_TEST.csv")
    assert info.source_format == "g3x_direct"
    assert info.aircraft_ident == "N999XX"
    assert info.engine_hours == 20.1
    assert len(df) == 3
    assert list(df["rpm"]) == [2000, 2010, 2020]
    assert df["_source_file"].iloc[0] == "log_20260101_120000_TEST.csv"


def test_load_log_bytes_garmin_pilot():
    df, info = load_log_bytes(_garmin_pilot_bytes(), "abc123.csv")
    assert info.source_format == "garmin_pilot"
    assert len(df) == 3


def test_load_log_bytes_unrecognized_format():
    bad = b'aircraft_ident="X"\nnot,a,g3x,header\n1,2,3\n'
    try:
        load_log_bytes(bad, "bad.csv")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "unrecognised header format" in str(e)


def test_load_log_is_a_thin_wrapper_over_load_log_bytes(tmp_path):
    path = tmp_path / "log_20260101_120000_TEST.csv"
    path.write_bytes(_g3x_direct_bytes())

    df_path, info_path = load_log(path)
    df_bytes, info_bytes = load_log_bytes(_g3x_direct_bytes(), path.name)

    assert df_path.equals(df_bytes)
    assert info_path == info_bytes
