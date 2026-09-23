"""
rules.py — validate_rules and what_if_rules (Spec 01 §7).

Pure — no I/O. Callers (the CLI, a future rule-playground UI) read the
RuleSet JSON and pass the parsed dict in.
"""
from __future__ import annotations

from .contract import Diagnostic
from .operations import FlightAnalysis, FleetAnalysis, evaluate_insights

_VALID_TRIGGER_TYPES = {"threshold", "baseline_deviation", "trend"}
_VALID_SEVERITIES = {"info", "watch", "warning", "limit"}


def validate_rules(rules: dict) -> list[dict]:
    """
    Schema and semantic checks on a RuleSet (insight_rules.json shape).
    Returns a list of Diagnostic dicts; empty means valid (errors use
    severity "error", looser issues "warn").
    """
    diagnostics: list[Diagnostic] = []

    if not isinstance(rules, dict) or not isinstance(rules.get("rules"), dict):
        diagnostics.append(Diagnostic(
            code="RULES_SCHEMA_ERROR", severity="error", scope="file",
            message="Missing or invalid top-level 'rules' object.",
        ))
        return [d.to_dict() for d in diagnostics]

    for topic_id, topic in rules["rules"].items():
        if not isinstance(topic, dict):
            diagnostics.append(Diagnostic(
                code="RULES_SCHEMA_ERROR", severity="error", scope="topic",
                message=f"{topic_id}: rule entry must be an object.",
                refs={"topic_id": topic_id},
            ))
            continue
        if not isinstance(topic.get("enabled"), bool):
            diagnostics.append(Diagnostic(
                code="RULES_SCHEMA_ERROR", severity="warn", scope="topic",
                message=f"{topic_id}: missing or non-boolean 'enabled'.",
                refs={"topic_id": topic_id},
            ))
        triggers = topic.get("triggers")
        if not isinstance(triggers, list):
            diagnostics.append(Diagnostic(
                code="RULES_SCHEMA_ERROR", severity="error", scope="topic",
                message=f"{topic_id}: 'triggers' must be a list.",
                refs={"topic_id": topic_id},
            ))
            continue
        for i, trig in enumerate(triggers):
            if not isinstance(trig, dict) or trig.get("type") not in _VALID_TRIGGER_TYPES:
                diagnostics.append(Diagnostic(
                    code="RULES_SCHEMA_ERROR", severity="error", scope="topic",
                    message=f"{topic_id}.triggers[{i}]: unknown or missing trigger type.",
                    refs={"topic_id": topic_id, "index": i},
                ))
                continue
            severity = trig.get("severity")
            if severity is not None and severity not in _VALID_SEVERITIES:
                diagnostics.append(Diagnostic(
                    code="RULES_SCHEMA_ERROR", severity="warn", scope="topic",
                    message=f"{topic_id}.triggers[{i}]: unknown severity {severity!r}.",
                    refs={"topic_id": topic_id, "index": i},
                ))

    return [d.to_dict() for d in diagnostics]


def what_if_rules(
    flight_analysis: FlightAnalysis,
    fleet_analysis: FleetAnalysis,
    old_rules: dict,
    new_rules: dict,
) -> dict:
    """
    Spec 01 §7 `what_if_rules` workflow: re-run evaluate_insights with a
    candidate RuleSet and diff against the currently-shipped one for one
    flight. Diffs by insight id (flight_id+topic_id+trigger+text) — a
    severity-only change on an insight that fires under both rule sets
    shows as unchanged, not as a diff; a real limitation of id-based
    diffing, not a bug, kept simple for this first pass.
    """
    old_iset = evaluate_insights(flight_analysis, fleet_analysis, old_rules)
    new_iset = evaluate_insights(flight_analysis, fleet_analysis, new_rules)

    def _by_id(iset):
        return {i["id"]: i for t in iset.topics for i in t["insights"]}

    old_ids, new_ids = _by_id(old_iset), _by_id(new_iset)
    added = [new_ids[i] for i in new_ids if i not in old_ids]
    removed = [old_ids[i] for i in old_ids if i not in new_ids]
    return {
        "flight_id": flight_analysis.flight_id,
        "added": added,
        "removed": removed,
        "unchanged_count": len(set(old_ids) & set(new_ids)),
    }
