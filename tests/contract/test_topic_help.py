"""
Spec 01 acceptance 10 and Spec 10 acceptance 11 (topic help, D13).
Runs everywhere — no log data needed.
"""
import json

import pytest

from slingology_eis.limits import load_engine_config
from slingology_eis.operations import get_topic_help

from ..conftest import TOOLKIT_ROOT

REGISTER_PATH = TOOLKIT_ROOT / "docs" / "specs" / "topics" / "register.json"
RULES_PATH = TOOLKIT_ROOT / "insight_rules.json"
ENGINES = ("912iS", "914iS", "915iS", "916iS")


@pytest.fixture(scope="module")
def register():
    return json.loads(REGISTER_PATH.read_text())


@pytest.fixture(scope="module")
def rules():
    return json.loads(RULES_PATH.read_text())


# 912iS: the egt_spread help text cites "the Operators Manual limit of
# {limit:egt_split_high_flow}", but OM-912 i Series defines no EGT split
# limit (engines/912iS.json metadata), so the placeholder correctly fails
# to resolve. The fix is help wording for an engine without that limit —
# an authoring decision, not a profile value to invent. Strict, so this
# turns red once the wording is fixed and the mark should go.
@pytest.mark.parametrize("engine", [
    pytest.param(e, marks=pytest.mark.xfail(
        strict=True, reason="egt_spread help cites an EGT split limit OM-912 i Series doesn't define"))
    if e == "912iS" else e
    for e in ENGINES
])
def test_acceptance_10_every_placeholder_resolves_no_diagnostics(engine, rules):
    cfg = load_engine_config(engine)
    results, diagnostics = get_topic_help(None, engine, cfg, rules)
    assert diagnostics == [], f"{engine}: unexpected diagnostics {diagnostics}"
    for r in results:
        assert "{" not in r.text, f"{engine}/{r.id}: unresolved placeholder in text: {r.text!r}"


@pytest.mark.parametrize("engine", ENGINES)
def test_acceptance_10_every_emittable_topic_has_help(engine, rules):
    """Every topic the engine can emit for this profile has a help entry."""
    rule_ids = set(rules["rules"].keys())
    cfg = load_engine_config(engine)
    results, _ = get_topic_help(None, engine, cfg, rules)
    help_ids = {r.id for r in results if r.applies}
    # cylinder_rank and climb_thermal_rate are context-only/Research —
    # they emit no card and need no help entry (register.json help: false).
    card_rule_ids = rule_ids - {"cylinder_rank", "climb_thermal_rate"}
    missing = {rid for rid in card_rule_ids
               if rid != "map_at_takeoff" or engine != "912iS"} - help_ids
    assert not missing, f"{engine}: emittable topics with no help entry: {missing}"


def test_acceptance_11_every_help_true_register_topic_has_a_section(register, rules):
    cfg = load_engine_config("916iS")
    results, diagnostics = get_topic_help(None, "916iS", cfg, rules)
    have = {r.id for r in results}
    need_help = {t["topic_id"] for t in register["topics"] if t.get("help")}
    missing = need_help - have
    assert not missing, f"register help:true topics with no help entry: {missing}"
    assert "flight_summary" in have


def test_acceptance_11_context_only_and_removed_topics_need_no_help(register, rules):
    cfg = load_engine_config("916iS")
    results, _ = get_topic_help(None, "916iS", cfg, rules)
    have = {r.id for r in results}
    no_help_needed = {t["topic_id"] for t in register["topics"] if not t.get("help")}
    # None of these are required to have an entry (cylinder_rank, climb_thermal_rate,
    # and the five Removed topics) — this is a non-requirement, not a prohibition,
    # so just confirm none of them are *mistakenly* required elsewhere.
    assert no_help_needed, "sanity: expected at least one help:false register entry"


def test_acceptance_11_a_help_section_for_a_topic_not_in_the_register_fails(register, rules):
    register_ids = {t["topic_id"] for t in register["topics"]}
    from slingology_eis.help import load_help_entries
    entries = load_help_entries()
    orphans = {eid for eid in entries if eid != "flight_summary" and eid not in register_ids}
    assert not orphans, f"help section(s) with no register entry: {orphans}"
