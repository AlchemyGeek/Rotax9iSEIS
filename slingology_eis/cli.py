"""
cli.py — the `slingology-eis` command (Spec 01 §7.1).

A thin client: converts paths to bytes, calls the §7 operations
in-process, and prints a renderer's output (text or --json). No
analysis logic lives here.

Diagnostics/progress go to stderr; the operation's result (text report
or JSON) goes to stdout. Exit codes: 0 success, 1 operation failed,
2 usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from . import serialize as _json_serialize
from . import workspace as _workspace
from .contract import content_hash
from .limits import _resolve_engine_name, load_engine_config
from .loader import deduplicate_flights, find_duplicate_flights, flight_fingerprint
from .loader import flight_id as _compute_flight_id
from .loader import load_directory
from .operations import (
    EcuAnalysis,
    FlightAnalysis,
    FleetAnalysis,
    InsightSet,
    analyze_ecu,
    analyze_flight,
    evaluate_insights,
    update_fleet,
)
from .rules import validate_rules, what_if_rules

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGED_HOME = Path.home() / "SlingologyEIS"


class CliUsageError(Exception):
    """Exit code 2."""


class CliOperationError(Exception):
    """Exit code 1."""


# ── --logs / --workspace default resolution (Spec 01 §7.1) ──────────────────

def _is_git_checkout(start: Path) -> bool:
    cur = start
    for _ in range(6):
        if (cur / ".git").exists():
            return True
        if cur.parent == cur:
            return False
        cur = cur.parent
    return False


def resolve_logs_dir(cli_arg: Optional[str]) -> Path:
    if cli_arg:
        return Path(cli_arg)
    if (_PACKAGED_HOME / "logs").is_dir():
        return _PACKAGED_HOME / "logs"
    if _is_git_checkout(_REPO_ROOT):
        return _REPO_ROOT / "data" / "logs"
    raise CliUsageError(
        "No --logs given, no packaged install found at "
        f"{_PACKAGED_HOME}, and not running from a git checkout. Pass --logs DIR."
    )


def resolve_workspace_dir(cli_arg: Optional[str]) -> Path:
    """
    Spec 01 v0.6 §7.1 (Q10, resolved): when a value is given, it's tried
    first as a registered workspace name/id (looked up in Spec 02's
    registry); if that doesn't match anything, it's treated exactly as
    before — a literal directory path. That literal-path fallback is
    `resolve_workspace_ref`'s own behavior, so this only adds the lookup,
    it doesn't change what happens when the lookup finds nothing — a
    developer-checkout invocation that predates the registry keeps
    working unmodified. Precedence when no value is given at all
    (packaged install, else a git checkout, else a usage error) is
    unchanged.
    """
    if cli_arg:
        registry_path = _workspace.resolve_registry_path()
        workspaces_root = _workspace.resolve_workspaces_root()
        return _workspace.resolve_workspace_ref(cli_arg, registry_path, workspaces_root)
    if (_PACKAGED_HOME / "workspace").is_dir():
        return _PACKAGED_HOME / "workspace"
    if _is_git_checkout(_REPO_ROOT):
        return _REPO_ROOT / "data"
    raise CliUsageError(
        "No --workspace given, no packaged install found at "
        f"{_PACKAGED_HOME}, and not running from a git checkout. Pass --workspace DIR."
    )


def _resolve_log_path(log_arg: str, logs_dir: Path) -> Path:
    p = Path(log_arg)
    if p.is_absolute() or p.exists():
        return p
    return logs_dir / log_arg


# ── anonymize (Spec 01 §10) ──────────────────────────────────────────────────

def anonymize(flight_analysis_dict: dict) -> dict:
    """Strip aircraft_ident, system_id, and filename airport hints from a
    FlightAnalysis dict. GPS coordinates never appear in the contract's
    header/metrics (only raw series data would carry them, §8.7 — not
    produced by this CLI yet), so there's nothing to strip there today."""
    d = json.loads(json.dumps(flight_analysis_dict))
    header = d.get("header")
    if isinstance(header, dict):
        if isinstance(header.get("aircraft"), dict):
            header["aircraft"] = {"ident": None, "system_id": None}
        header["airport_hint"] = None
    return d


# ── logging / output helpers ─────────────────────────────────────────────────

def _log(message: str, quiet: bool) -> None:
    if not quiet:
        print(message, file=sys.stderr)


def _print_json(obj) -> None:
    print(_json_serialize.dumps(obj, indent=2))


# ── text rendering ────────────────────────────────────────────────────────

def render_report(fa: FlightAnalysis, iset: InsightSet) -> str:
    h = fa.header
    lines = ["=" * 70, "  SLINGOLOGY EIS — FLIGHT REPORT"]
    ident = (h.get("aircraft") or {}).get("ident") or "—"
    lines.append(f"  {ident}")
    lines.append(f"  Date:         {h.get('date', '—')}")
    lines.append(f"  Airport:      {h.get('airport_hint') or '—'}")
    eh_start, eh_end = h.get("engine_hours_start"), h.get("engine_hours_end")
    eh_str = f"{eh_start if eh_start is not None else '—'}h → {eh_end if eh_end is not None else '—'}h"
    lines.append(f"  Engine hrs:   {eh_str}")
    lines.append("=" * 70)

    for w in iset.header_warnings:
        lines.append(f"\n  ⚠ {w['message']}")

    for topic in iset.topics:
        title = topic["topic_id"].replace("_", " ").upper()
        lines.append(f"\n── {title} " + "─" * max(0, 58 - len(title)))
        lines.append(f"  Analysis: {topic['analysis']['text']}")
        for insight in topic["insights"]:
            lines.append(f"  Insight:  [{insight['severity']}] {insight['message']['text']}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def render_fleet_summary(fleet: FleetAnalysis) -> str:
    lines = ["=" * 70, "  SLINGOLOGY EIS — FLEET SUMMARY", f"  {len(fleet.flight_ids)} flight(s)", "=" * 70]
    if fleet.quality:
        lines.append("\n  NEEDS ATTENTION:")
        for q in fleet.quality:
            lines.append(f"    ⚠ [{q['severity']}] {q['message']}")
    else:
        lines.append("\n  ✓ No fleet-level quality issues.")

    outlier_lines = []
    for metric_id, m in fleet.metrics.items():
        for o in m["outliers"]:
            outlier_lines.append(f"    {metric_id}: {o['flight_id']}  z={o['z_score']:+.2f}")
    if outlier_lines:
        lines.append("\n  OUTLIERS:")
        lines.extend(outlier_lines)

    if fleet.models:
        lines.append("\n  MODELS:")
        for m in fleet.models:
            lines.append(f"    {m['id']}: n={m['n']}  R²={m['r_squared']}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


# ── loading a directory + minimal workspace persistence ──────────────────────

def _load_flight_analyses(
    logs_dir: Path, engine_cfg: dict, engine_name: str, quiet: bool
) -> tuple[list[FlightAnalysis], list[dict], dict[str, Path]]:
    """
    Load every log in `logs_dir`, applying the same ground-session
    filtering and overlap-aware duplicate detection load_directory()/
    find_duplicate_flights() already provide and are tested (Stage 0),
    then run analyze_flight() on what survives.

    Each surviving file is parsed twice — once here (for filtering) and
    once inside analyze_flight() — rather than reusing the DataFrame,
    so analyze_flight() stays the one place a FlightAnalysis gets built.
    A real inefficiency, acceptable for now.

    Also returns flight_id -> source path, so _write_workspace() can
    persist the source log alongside analysis.json (matching what
    server.py's import_files already does) — without this, a flight
    imported via the CLI has no source log in the workspace, and
    get_flight_series/get_series can't build a timeline for it.
    """
    try:
        flights = load_directory(str(logs_dir), verbose=not quiet)
    except ValueError as e:
        raise CliOperationError(str(e))

    excluded: list[dict] = []
    if find_duplicate_flights(flights):
        by_name = {df["_source_file"].iloc[0]: (df, info) for df, info in flights}
        deduped = deduplicate_flights(flights, prefer="most_rows", verbose=not quiet)
        kept_names = {df["_source_file"].iloc[0] for df, _ in deduped}
        for fname, (df, info) in by_name.items():
            if fname not in kept_names:
                fid = _compute_flight_id(flight_fingerprint(df, info))
                excluded.append({"flight_id": fid, "reason": f"duplicate export ({fname})"})
        flights = deduped

    fas = []
    source_paths: dict[str, Path] = {}
    for df, info in flights:
        fname = df["_source_file"].iloc[0]
        path = logs_dir / fname
        try:
            fa = analyze_flight(path.read_bytes(), fname, engine_cfg, engine_name)
            fas.append(fa)
            source_paths[fa.flight_id] = path
            _log(f"  ✓ {fname}", quiet)
        except Exception as e:
            _log(f"  ✗ {fname}: {e}", quiet)
    return fas, excluded, source_paths


def _fleet_analysis_from_dict(d: dict) -> FleetAnalysis:
    return FleetAnalysis(
        fleet_key=d["fleet_key"], flight_ids=d["flight_ids"], excluded=d.get("excluded", []),
        metrics=d.get("metrics", {}), models=d.get("models", []),
        quality=d.get("quality", []), provenance=d.get("provenance", {}),
    )


def _write_workspace(
    workspace_dir: Path, fas: list[FlightAnalysis], fleet: FleetAnalysis,
    source_paths: Optional[dict[str, Path]] = None,
) -> None:
    """
    A deliberately minimal subset of Spec 02's eventual workspace layout
    — just enough for `report`/`rules try` to cache a fleet baseline
    instead of recomputing it from every log on every call. Not
    manifest.json, sources.json, annotations, rules/, or settings.json;
    those are Spec 02 deliverables, not built here.

    source_paths (flight_id -> the log it came from) is optional and
    persists the source log alongside analysis.json when given, matching
    server.py's import_files — without it, get_series has nothing to
    re-parse for this flight later.
    """
    flights_dir = workspace_dir / "flights"
    for fa in fas:
        d = flights_dir / fa.flight_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "analysis.json").write_text(_json_serialize.dumps(fa.to_dict(), indent=2))
        src = (source_paths or {}).get(fa.flight_id)
        if src is not None:
            dest = d / src.name
            if not dest.exists():
                dest.write_bytes(src.read_bytes())
    fleet_dir = workspace_dir / "fleet"
    fleet_dir.mkdir(parents=True, exist_ok=True)
    (fleet_dir / "analysis.json").write_text(_json_serialize.dumps(fleet.to_dict(), indent=2))


def _load_or_build_fleet(logs_dir: Path, workspace_dir: Path, engine_cfg: dict, engine_name: str, quiet: bool) -> FleetAnalysis:
    cache = workspace_dir / "fleet" / "analysis.json"
    if cache.exists():
        _log(f"Using cached fleet baseline from {cache} (run 'fleet' or 'import' to refresh)", quiet)
        return _fleet_analysis_from_dict(json.loads(cache.read_text()))
    _log(f"No cached fleet baseline at {cache} — recomputing from {logs_dir} "
         f"(slow; run 'fleet' or 'import' first to cache)", quiet)
    fas, excluded, _source_paths = _load_flight_analyses(logs_dir, engine_cfg, engine_name, quiet)
    return update_fleet(fas, excluded=excluded)


# ── subcommands ───────────────────────────────────────────────────────────

def cmd_engines(args) -> int:
    engines_dir = _REPO_ROOT / "engines"
    results = []
    for p in sorted(engines_dir.glob("*.json")):
        cfg = json.loads(p.read_text())
        meta = cfg.get("_metadata", {})
        results.append({
            "id": p.stem, "engine": meta.get("engine", p.stem),
            "source_status": meta.get("source_status", "UNKNOWN"),
            "hash": content_hash(cfg),
        })
    if args.json:
        _print_json(results)
    else:
        for r in results:
            print(f"{r['id']:<10} {r['engine']:<20} {r['source_status']}")
    return 0


def cmd_flight(args) -> int:
    logs_dir = resolve_logs_dir(args.logs)
    engine_name = _resolve_engine_name(args.engine)
    engine_cfg = load_engine_config(engine_name)
    log_path = _resolve_log_path(args.log, logs_dir)
    if not log_path.exists():
        raise CliOperationError(f"Log not found: {log_path}")
    fa = analyze_flight(log_path.read_bytes(), log_path.name, engine_cfg, engine_name)
    d = fa.to_dict()
    if args.anonymize:
        d = anonymize(d)
    if args.json:
        _print_json(d)
    else:
        print(f"flight_id: {d['flight_id']}")
        print(f"date: {d['header']['date']}  airport: {d['header']['airport_hint']}")
        print(f"quality: {[q['code'] for q in d['quality']]}")
        print(f"exceedances: {len(d['exceedances'])}  cas_events: {len(d['cas_events'])}  ecu_runs: {len(d['ecu_runs'])}")
    return 0


def cmd_ecu(args) -> int:
    logs_dir = resolve_logs_dir(args.logs)
    engine_name = _resolve_engine_name(args.engine)
    engine_cfg = load_engine_config(engine_name)
    if args.paths:
        log_paths = [_resolve_log_path(p, logs_dir) for p in args.paths]
    else:
        log_paths = sorted(logs_dir.glob("*.csv"))
    fas = [analyze_flight(p.read_bytes(), p.name, engine_cfg, engine_name) for p in log_paths]
    ea = analyze_ecu(fas)
    d = ea.to_dict()
    if args.json:
        _print_json(d)
    else:
        print(f"Flights analysed: {len(fas)}")
        print(f"Classification counts: {d['counts']}")
        for e in d["inflight_pattern"]["events"]:
            print(f"  ⚡ IN_FLIGHT  flight={e['flight_id']}  {e['start_time']}  co_alerts={e['co_alerts']}")
    return 0


def cmd_fleet(args) -> int:
    logs_dir = resolve_logs_dir(args.logs)
    workspace_dir = resolve_workspace_dir(args.workspace)
    engine_name = _resolve_engine_name(args.engine)
    engine_cfg = load_engine_config(engine_name)
    fas, excluded, source_paths = _load_flight_analyses(logs_dir, engine_cfg, engine_name, args.quiet)
    fleet = update_fleet(fas, excluded=excluded)
    _write_workspace(workspace_dir, fas, fleet, source_paths)
    d = fleet.to_dict()
    if args.json:
        _print_json(d)
    else:
        print(render_fleet_summary(fleet))
    return 0


def cmd_report(args) -> int:
    logs_dir = resolve_logs_dir(args.logs)
    workspace_dir = resolve_workspace_dir(args.workspace)
    engine_name = _resolve_engine_name(args.engine)
    engine_cfg = load_engine_config(engine_name)
    log_path = _resolve_log_path(args.log, logs_dir)
    if not log_path.exists():
        raise CliOperationError(f"Log not found: {log_path}")
    fa = analyze_flight(log_path.read_bytes(), log_path.name, engine_cfg, engine_name)
    fleet = _load_or_build_fleet(logs_dir, workspace_dir, engine_cfg, engine_name, args.quiet)
    rules = json.loads((_REPO_ROOT / "insight_rules.json").read_text())
    iset = evaluate_insights(fa, fleet, rules)
    if args.json:
        fa_dict = anonymize(fa.to_dict()) if args.anonymize else fa.to_dict()
        _print_json({"flight_analysis": fa_dict, "insight_set": iset.to_dict()})
    else:
        print(render_report(fa, iset))
    return 0


def cmd_import(args) -> int:
    logs_dir = resolve_logs_dir(args.logs)
    workspace_dir = resolve_workspace_dir(args.workspace)
    engine_name = _resolve_engine_name(args.engine)
    engine_cfg = load_engine_config(engine_name)

    if args.paths:
        # Explicit files/folders named on the command line: analyze exactly
        # what was asked for, no ground-session filtering or dedup magic.
        log_paths: list[Path] = []
        for p in args.paths:
            pp = Path(p)
            if pp.is_dir():
                log_paths.extend(sorted(pp.glob("*.csv")))
            else:
                log_paths.append(_resolve_log_path(p, logs_dir))
        if not log_paths:
            raise CliOperationError("No logs to import.")
        fas = []
        source_paths: dict[str, Path] = {}
        for p in log_paths:
            try:
                fa = analyze_flight(p.read_bytes(), p.name, engine_cfg, engine_name)
                fas.append(fa)
                source_paths[fa.flight_id] = p
                _log(f"  ✓ {p.name}", args.quiet)
            except Exception as e:
                _log(f"  ✗ {p.name}: {e}", args.quiet)
        excluded = []
    else:
        # No paths given: import everything in --logs, with the same
        # ground-session filtering and duplicate detection `fleet` uses.
        fas, excluded, source_paths = _load_flight_analyses(logs_dir, engine_cfg, engine_name, args.quiet)

    fleet = update_fleet(fas, excluded=excluded)
    _write_workspace(workspace_dir, fas, fleet, source_paths)

    if args.json:
        _print_json({"flight_count": len(fas), "fleet_key": fleet.fleet_key, "workspace": str(workspace_dir)})
    else:
        print(f"Imported {len(fas)} flight(s). Workspace: {workspace_dir}")
    return 0


def cmd_rules_check(args) -> int:
    rules = json.loads(Path(args.file).read_text())
    diagnostics = validate_rules(rules)
    if args.json:
        _print_json(diagnostics)
    else:
        if not diagnostics:
            print("✓ Rules file is valid.")
        else:
            for d in diagnostics:
                print(f"  [{d['severity']}] {d['message']}")
    return 1 if any(d["severity"] == "error" for d in diagnostics) else 0


def cmd_rules_try(args) -> int:
    logs_dir = resolve_logs_dir(args.logs)
    workspace_dir = resolve_workspace_dir(args.workspace)
    engine_name = _resolve_engine_name(args.engine)
    engine_cfg = load_engine_config(engine_name)

    if args.flight:
        log_path = _resolve_log_path(args.flight, logs_dir)
    else:
        candidates = sorted(logs_dir.glob("*.csv"))
        if not candidates:
            raise CliOperationError(f"No .csv logs found in {logs_dir} to try rules against.")
        log_path = candidates[0]
        _log(f"No --flight given, using {log_path.name}", args.quiet)
    fa = analyze_flight(log_path.read_bytes(), log_path.name, engine_cfg, engine_name)
    fleet = _load_or_build_fleet(logs_dir, workspace_dir, engine_cfg, engine_name, args.quiet)

    old_rules = json.loads((_REPO_ROOT / "insight_rules.json").read_text())
    new_rules = json.loads(Path(args.file).read_text())
    diff = what_if_rules(fa, fleet, old_rules, new_rules)
    if args.json:
        _print_json(diff)
    else:
        print(f"Flight: {log_path.name}")
        print(f"Added insights ({len(diff['added'])}):")
        for i in diff["added"]:
            print(f"  + [{i['severity']}] {i['message']['text']}")
        print(f"Removed insights ({len(diff['removed'])}):")
        for i in diff["removed"]:
            print(f"  - [{i['severity']}] {i['message']['text']}")
        print(f"Unchanged: {diff['unchanged_count']}")
    return 0


def cmd_export_bundle(args) -> int:
    _log("export-bundle: not yet implemented — needs Spec 02's results-bundle format.", args.quiet)
    return 2


# ── workspace subcommands (Spec 01 v0.6 §7.1, Spec 02 v0.5 Q10) ─────────────
# Flag/subcommand shape not pinned down further by either spec beyond "list"
# and "create <name>" — this follows the existing `rules check`/`rules try`
# nested-subparser style already in this file, and gives `create` an
# optional --tail-number since Spec 02 §5.6 treats it as informational and
# not required at creation (only engine_model is required/locked).

def cmd_workspace_list(args) -> int:
    registry_path = _workspace.resolve_registry_path()
    entries = _workspace.list_workspaces(registry_path)
    if args.json:
        _print_json([e.to_dict() for e in entries])
    else:
        if not entries:
            print("No workspaces yet. Create one with: slingology-eis workspace create <name> --engine <model>")
        for e in entries:
            print(f"{e.id:<20} {e.name:<30} {e.engine_model:<8} {e.flight_count} flight(s)")
    return 0


def cmd_workspace_create(args) -> int:
    registry_path = _workspace.resolve_registry_path()
    workspaces_root = _workspace.resolve_workspaces_root()
    engine_name = _resolve_engine_name(args.engine)
    try:
        manifest = _workspace.create_workspace(
            registry_path, workspaces_root, args.name, engine_name,
            primary_tail_number=args.tail_number,
        )
    except ValueError as e:
        raise CliOperationError(str(e))
    ws_dir = workspaces_root / manifest.id
    if args.json:
        _print_json(manifest.to_dict())
    else:
        print(f"Created workspace {manifest.name!r} (id={manifest.id}, engine={manifest.engine_model}) at {ws_dir}")
    return 0


def cmd_serve(args) -> int:
    from .server import run_server
    run_server(args.logs, args.workspace, args.port, args.quiet)
    return 0


# ── argument parsing ──────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--logs", metavar="DIR", help="Folder of G3X log CSVs")
    common.add_argument("--workspace", metavar="NAME_OR_PATH",
                         help="Registered workspace name/id, or a literal folder path")
    common.add_argument("--engine", metavar="NAME", help="Engine profile (e.g. 916iS)")
    common.add_argument("--json", action="store_true", help="Print the operation result as JSON")
    common.add_argument("--anonymize", action="store_true", help="Strip aircraft ident/system_id/airport hint")
    common.add_argument("--quiet", action="store_true", help="Suppress progress/diagnostic output on stderr")

    parser = argparse.ArgumentParser(prog="slingology-eis", parents=[common])
    parser.add_argument("--version", action="version", version=f"slingology-eis {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("engines", parents=[common], help="List available engine profiles")
    p.set_defaults(func=cmd_engines)

    p = sub.add_parser("flight", parents=[common], help="Analyze one flight")
    p.add_argument("log")
    p.set_defaults(func=cmd_flight)

    p = sub.add_parser("ecu", parents=[common], help="ENGINE ECU correlation across flights")
    p.add_argument("paths", nargs="*", help="Specific logs (default: all logs in --logs)")
    p.set_defaults(func=cmd_ecu)

    p = sub.add_parser("fleet", parents=[common], help="Fleet baselines/trends/models")
    p.set_defaults(func=cmd_fleet)

    p = sub.add_parser("report", parents=[common], help="Plain-language per-flight report")
    p.add_argument("log")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("import", parents=[common], help="Analyze logs/folders and update the workspace")
    p.add_argument("paths", nargs="*", help="Specific logs or folders (default: all logs in --logs)")
    p.set_defaults(func=cmd_import)

    p_rules = sub.add_parser("rules", parents=[common], help="Rule validation / what-if")
    rules_sub = p_rules.add_subparsers(dest="rules_command", required=True)

    p = rules_sub.add_parser("check", parents=[common], help="Validate a rules file")
    p.add_argument("file")
    p.set_defaults(func=cmd_rules_check)

    p = rules_sub.add_parser("try", parents=[common], help="Diff insights under a candidate rules file")
    p.add_argument("file")
    p.add_argument("--flight", metavar="LOG", help="Flight to evaluate (default: first log in --logs)")
    p.set_defaults(func=cmd_rules_try)

    p_workspace = sub.add_parser("workspace", parents=[common], help="Manage workspaces (Spec 02 v0.5)")
    workspace_sub = p_workspace.add_subparsers(dest="workspace_command", required=True)

    p = workspace_sub.add_parser("list", parents=[common], help="List registered workspaces")
    p.set_defaults(func=cmd_workspace_list)

    p = workspace_sub.add_parser("create", parents=[common], help="Create a new workspace")
    p.add_argument("name")
    p.add_argument("--tail-number", metavar="IDENT", help="Primary tail number (informational only, Spec 02 §5.6)")
    p.set_defaults(func=cmd_workspace_create)

    p = sub.add_parser("export-bundle", parents=[common], help="Export a results bundle (not yet implemented)")
    p.set_defaults(func=cmd_export_bundle)

    p = sub.add_parser("serve", parents=[common], help="Start the local server + UI (Spec 04 §9.2 adapter)")
    p.add_argument("--port", type=int, default=8420, help="Port to bind on 127.0.0.1 (default: 8420)")
    p.set_defaults(func=cmd_serve)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CliUsageError as e:
        print(f"usage error: {e}", file=sys.stderr)
        return 2
    except CliOperationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
