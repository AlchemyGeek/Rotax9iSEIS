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

from slingology_eis import workspace as _workspace
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
# `serve` is no longer a stub (Spec 04 §9.2 local-server adapter) — its own
# tests live in tests/unit/test_server.py, since calling `main(["serve"])`
# here would block forever on serve_forever() in-process.

def test_export_bundle_stub_exits_two():
    assert main(["export-bundle", "--quiet"]) == 2


# ── workspace list / create (Spec 01 v0.6 §7.1, Spec 02 v0.5 Q10) ──────────
# `_PACKAGED_HOME` is monkeypatched to an isolated tmp dir and pre-created
# so resolve_registry_path()/resolve_workspaces_root() never touch this
# repo's own real data/registry.json or data/workspaces/ — those three
# resolution functions have no CLI flag to redirect them directly.

@pytest.fixture
def isolated_packaged_home(tmp_path, monkeypatch):
    home = tmp_path / "SlingologyEIS"
    home.mkdir()
    monkeypatch.setattr(_workspace, "_PACKAGED_HOME", home)
    return home


def test_workspace_list_empty_registry(isolated_packaged_home, capsys):
    rc = main(["workspace", "list", "--quiet"])
    assert rc == 0
    assert "No workspaces yet" in capsys.readouterr().out


def test_workspace_create_then_list(isolated_packaged_home, capsys):
    rc = main(["workspace", "create", "N117ZS — all", "--engine", "916iS",
               "--tail-number", "N117ZS", "--json", "--quiet"])
    assert rc == 0
    created = json.loads(capsys.readouterr().out)
    assert created["name"] == "N117ZS — all"
    assert created["engine_model"] == "916iS"
    assert created["primary_tail_number"] == "N117ZS"
    ws_dir = isolated_packaged_home / "workspaces" / created["id"]
    assert (ws_dir / "manifest.json").exists()

    rc = main(["workspace", "list", "--json", "--quiet"])
    assert rc == 0
    entries = json.loads(capsys.readouterr().out)
    assert len(entries) == 1
    assert entries[0]["id"] == created["id"]
    assert entries[0]["flight_count"] == 0


def test_workspace_create_rejects_unknown_engine(isolated_packaged_home, capsys):
    rc = main(["workspace", "create", "bad-engine-ws", "--engine", "917iS", "--quiet"])
    assert rc == 1


def test_workspace_create_duplicate_name_exits_one(isolated_packaged_home, capsys):
    rc = main(["workspace", "create", "dupe", "--engine", "916iS", "--quiet"])
    assert rc == 0
    rc = main(["workspace", "create", "dupe", "--engine", "916iS", "--quiet"])
    assert rc == 1


def test_workspace_missing_subcommand_exits_two():
    with pytest.raises(SystemExit) as exc:
        main(["workspace"])
    assert exc.value.code == 2


# ── --workspace resolves a registered name/id, or falls back to a path ────

def test_dash_dash_workspace_resolves_registered_name(isolated_packaged_home, synthetic_logs_dir, capsys):
    rc = main(["workspace", "create", "by-name", "--engine", "916iS", "--json", "--quiet"])
    assert rc == 0
    created = json.loads(capsys.readouterr().out)

    # --workspace given the registered *name* (not its id, not a literal
    # path) resolves to the same directory workspace.py itself wrote to
    # (Q10) — proven by running `fleet` (which writes fleet/analysis.json
    # into whatever resolve_workspace_dir() resolves to) against the name.
    rc = main(["fleet", "--logs", str(synthetic_logs_dir), "--workspace", "by-name", "--quiet"])
    assert rc == 0
    ws_dir_by_name = isolated_packaged_home / "workspaces" / created["id"]
    assert (ws_dir_by_name / "fleet" / "analysis.json").exists()


def test_dash_dash_workspace_literal_path_still_works_unregistered(tmp_path, isolated_packaged_home, capsys):
    """A literal path that matches no registered workspace — the
    pre-registry CLI behavior must be exactly unchanged."""
    unregistered = tmp_path / "some-dev-checkout-workspace"
    rc = main(["flight", "--logs", str(tmp_path), "--workspace", str(unregistered), "--quiet", "nonexistent.csv"])
    # Not about this specific subcommand succeeding — just confirming
    # resolve_workspace_dir(str(unregistered)) doesn't blow up trying a
    # registry lookup and silently redirect elsewhere; the "log not
    # found" failure proves --logs/--workspace were both honored as
    # literal paths, same as always.
    assert rc == 1
    assert "Log not found" in capsys.readouterr().err


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
