"""
CLI tests (Spec 01 §7.1, Stage 4a).

Exercises `slingology_eis.cli.main()` in-process (no subprocess — main()
returns an int rather than calling sys.exit(), except where argparse
itself exits for --version/usage errors, which we catch via SystemExit).
Schema-checked subcommands are validated against the same contract
schemas contract/ tests use, so the CLI and the library can't silently
drift apart.
"""
import json
from pathlib import Path

import jsonschema
import pytest

from slingology_eis.cli import anonymize, main

from ..conftest import LOGS_DIR, requires_flight_logs

_CONTRACT_ROOT = Path(__file__).resolve().parent.parent.parent / "contract"


def load_schema(name: str) -> dict:
    return json.loads((_CONTRACT_ROOT / "schema" / name).read_text())


_META = (
    'aircraft_ident="N999XX", product="GDU 460", system_id="123456789", '
    'unit="1", airframe_hours="10.5", engine_hours="20.1", log_version="7"\n'
)
_HEADER = "Date (yyyy-mm-dd),Time (hh:mm:ss),RPM,Oil Temp (deg F)\n"
_ROWS = "".join(f"2026-01-01,12:{i//60:02d}:{i%60:02d},{2000+i},180\n" for i in range(120))
_SYNTHETIC_LOG = _META + _HEADER + _ROWS
_SYNTHETIC_NAME = "log_20260101_120000_TEST.csv"


@pytest.fixture
def synthetic_logs_dir(tmp_path):
    (tmp_path / _SYNTHETIC_NAME).write_text(_SYNTHETIC_LOG)
    return tmp_path


# ── --version / usage errors (argparse itself calls sys.exit) ───────────────

def test_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "slingology-eis" in capsys.readouterr().out


def test_missing_subcommand_exits_two():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_unknown_subcommand_exits_two():
    with pytest.raises(SystemExit) as exc:
        main(["bogus-command"])
    assert exc.value.code == 2


# ── engines ───────────────────────────────────────────────────────────────

def test_engines_json_lists_916is(capsys):
    rc = main(["engines", "--json"])
    assert rc == 0
    results = json.loads(capsys.readouterr().out)
    assert any(r["id"] == "916iS" for r in results)


# ── flight ────────────────────────────────────────────────────────────────

def test_flight_json_validates_against_schema(synthetic_logs_dir, capsys):
    rc = main(["flight", _SYNTHETIC_NAME, "--logs", str(synthetic_logs_dir), "--json", "--quiet"])
    assert rc == 0
    d = json.loads(capsys.readouterr().out)
    jsonschema.validate(d, load_schema("flight_analysis.schema.json"))


def test_flight_anonymize_strips_identity(synthetic_logs_dir, capsys):
    rc = main(["flight", _SYNTHETIC_NAME, "--logs", str(synthetic_logs_dir),
               "--json", "--anonymize", "--quiet"])
    assert rc == 0
    d = json.loads(capsys.readouterr().out)
    header = d["header"]
    assert header["aircraft"]["ident"] is None
    assert header["aircraft"]["system_id"] is None
    assert header["airport_hint"] is None


def test_flight_text_output_not_anonymized_by_default(synthetic_logs_dir, capsys):
    rc = main(["flight", _SYNTHETIC_NAME, "--logs", str(synthetic_logs_dir), "--quiet"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "flight_id:" in out


def test_flight_missing_log_exits_one(synthetic_logs_dir, capsys):
    rc = main(["flight", "nonexistent.csv", "--logs", str(synthetic_logs_dir), "--quiet"])
    assert rc == 1
    assert "error:" in capsys.readouterr().err


def test_flight_bad_logs_dir_exits_one(tmp_path, capsys):
    missing = tmp_path / "does_not_exist_xyz"
    rc = main(["flight", "whatever.csv", "--logs", str(missing), "--quiet"])
    assert rc == 1


# ── anonymize() helper directly ──────────────────────────────────────────

def test_anonymize_helper_is_pure_and_non_mutating():
    d = {"header": {"aircraft": {"ident": "N117ZS", "system_id": "60002D19C364F"},
                     "airport_hint": "KACV"}}
    out = anonymize(d)
    assert out["header"]["aircraft"] == {"ident": None, "system_id": None}
    assert out["header"]["airport_hint"] is None
    # original dict passed in is untouched
    assert d["header"]["aircraft"]["ident"] == "N117ZS"


# ── rules check / try ─────────────────────────────────────────────────────

def test_rules_check_valid_file_exits_zero(capsys):
    rules_path = Path(__file__).resolve().parent.parent.parent / "insight_rules.json"
    rc = main(["rules", "check", str(rules_path), "--quiet"])
    assert rc == 0
    assert "valid" in capsys.readouterr().out.lower()


def test_rules_check_invalid_file_exits_one(tmp_path, capsys):
    bad = tmp_path / "bad_rules.json"
    bad.write_text(json.dumps({"rules": {"oil_temp": {"enabled": "not-a-bool", "triggers": "nope"}}}))
    rc = main(["rules", "check", str(bad), "--json", "--quiet"])
    assert rc == 1
    diagnostics = json.loads(capsys.readouterr().out)
    assert any(d["severity"] == "error" for d in diagnostics)


# ── stubs ─────────────────────────────────────────────────────────────────

def test_export_bundle_stub_exits_two():
    assert main(["export-bundle", "--quiet"]) == 2


def test_serve_stub_exits_two():
    assert main(["serve", "--quiet"]) == 2


# ── real-data subcommands (gated: private logs, may be absent) ──────────────

@requires_flight_logs
def test_fleet_json_validates_against_schema_and_writes_workspace(tmp_path, capsys):
    workspace = tmp_path / "workspace"
    rc = main(["fleet", "--logs", str(LOGS_DIR), "--workspace", str(workspace),
               "--json", "--quiet"])
    assert rc == 0
    d = json.loads(capsys.readouterr().out)
    jsonschema.validate(d, load_schema("fleet_analysis.schema.json"))
    assert (workspace / "fleet" / "analysis.json").exists()
    assert len(d["flight_ids"]) > 0


@requires_flight_logs
def test_ecu_json_validates_against_schema(capsys):
    rc = main(["ecu", "--logs", str(LOGS_DIR), "--json", "--quiet"])
    assert rc == 0
    d = json.loads(capsys.readouterr().out)
    jsonschema.validate(d, load_schema("ecu_analysis.schema.json"))


@requires_flight_logs
def test_report_text_output_for_first_log(capsys):
    first_log = sorted(LOGS_DIR.glob("*.csv"))[0]
    rc = main(["report", first_log.name, "--logs", str(LOGS_DIR), "--quiet"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "SLINGOLOGY EIS" in out
    assert "FLIGHT REPORT" in out


@requires_flight_logs
def test_import_then_fleet_uses_cached_workspace(tmp_path, capsys):
    workspace = tmp_path / "workspace"
    rc = main(["import", "--logs", str(LOGS_DIR), "--workspace", str(workspace),
               "--json", "--quiet"])
    assert rc == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported["flight_count"] > 0
    assert (workspace / "fleet" / "analysis.json").exists()

    rc = main(["rules", "try", str(Path(__file__).resolve().parent.parent.parent / "insight_rules.json"),
               "--logs", str(LOGS_DIR), "--workspace", str(workspace), "--json", "--quiet"])
    assert rc == 0
    diff = json.loads(capsys.readouterr().out)
    # Trying the currently-shipped rules against themselves: no diff.
    assert diff["added"] == []
    assert diff["removed"] == []
