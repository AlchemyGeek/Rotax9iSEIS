"""
Spec 10 v0.7 §5 (D12), acceptance 1: docs/specs/topics/register.json
must list every topic that's actually live (every rule id in
insight_rules.json, and every topic_id evaluate_insights emits across
the log set) with no orphans either way, and its 916iS statuses must
agree with the register table in Spec 10 §5.2 — parsed from the spec
file itself, not a second hard-coded copy.
"""
import json
import re

import pytest

from slingology_eis import workspace as ws
from slingology_eis.limits import load_engine_config
from slingology_eis.operations import evaluate_insights, update_fleet

from ..conftest import TOOLKIT_ROOT, requires_flight_logs

REGISTER_PATH = TOOLKIT_ROOT / "docs" / "specs" / "topics" / "register.json"
SPEC_10_PATH = TOOLKIT_ROOT / "docs" / "specs" / "10-analytics-topic-admission.md"
RULES_PATH = TOOLKIT_ROOT / "insight_rules.json"

# Pre-v0.7 wording in the §5.2 table that now means a terminal §8.1 stage:
# "Dropped"/"to leave the topic set"/"Deprecated ...; Removed" all describe
# a topic that Spec 10 Phase A actually took out of insight_rules.json —
# the table's prose predates that, but the current state is Removed.
_RESEARCH_RE = re.compile(r"\bResearch\b")
_REMOVED_RE = re.compile(r"\bRemoved\b")
_ADMITTED_RE = re.compile(r"\bAdmitted\b")
_DROPPED_RE = re.compile(r"\bDropped\b")


def normalize_status_cell(cell: str) -> str:
    """The terminal §8.1 stage a §5.2 'Status today' cell describes now."""
    if _RESEARCH_RE.search(cell):
        return "Research"
    if _REMOVED_RE.search(cell):
        return "Removed"
    if _DROPPED_RE.search(cell):
        return "Removed"
    if _ADMITTED_RE.search(cell) and "to leave the topic set" in cell:
        return "Removed"
    if _ADMITTED_RE.search(cell):
        return "Admitted"
    raise ValueError(f"can't normalize §5.2 status cell: {cell!r}")


def parse_register_table(spec_text: str) -> dict:
    """{topic_id: normalized 916iS status} from Spec 10 §5.2's table."""
    lines = spec_text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("###") and "5.2" in l)
    header = next(i for i in range(start, len(lines)) if "Status today" in lines[i])
    out = {}
    for line in lines[header + 2:]:  # skip the header row and its --- separator
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        m = re.match(r"`([a-z0-9_]+)`", cells[0])
        if not m:
            continue
        out[m.group(1)] = normalize_status_cell(cells[-1])
    return out


@pytest.fixture(scope="module")
def register():
    return json.loads(REGISTER_PATH.read_text())


@pytest.fixture(scope="module")
def spec_table():
    return parse_register_table(SPEC_10_PATH.read_text())


def test_register_topic_ids_cover_every_live_rule(register):
    rule_ids = set(json.loads(RULES_PATH.read_text())["rules"].keys())
    register_ids = {t["topic_id"] for t in register["topics"]}
    missing = rule_ids - register_ids
    assert not missing, f"rule ids with no register entry: {missing}"


@requires_flight_logs
def test_every_emitted_topic_has_a_register_entry(register):
    manifest_dirs = list((TOOLKIT_ROOT / "data" / "workspaces").glob("ws_*"))
    if not manifest_dirs:
        pytest.skip("no local workspace to evaluate")
    ws_dir = manifest_dirs[0]
    manifest = ws.load_manifest(ws_dir)
    engine_cfg = load_engine_config(manifest.engine_model)
    selection = ws.load_selection(ws_dir)
    all_fas = ws.load_all_flight_analyses(ws_dir)
    excluded_ids = {e["flight_id"] for e in selection.excluded}
    included = [fa for fa in all_fas if fa.flight_id not in excluded_ids]
    if not included:
        pytest.skip("no admitted flights in the local workspace")
    fleet = update_fleet(included, excluded=selection.excluded,
                         baseline_config=selection.baseline_config, engine_config=engine_cfg)
    rules = json.loads(RULES_PATH.read_text())
    register_ids = {t["topic_id"] for t in register["topics"]}

    emitted = set()
    for fa in included:
        iset = evaluate_insights(fa, fleet, rules, filters=[])
        emitted.update(t["topic_id"] for t in iset.topics)

    orphans = emitted - register_ids
    assert not orphans, f"topics emitted with no register entry: {orphans}"


def test_register_916is_statuses_agree_with_spec_10_5_2(register, spec_table):
    register_statuses = {t["topic_id"]: t["status"]["916iS"] for t in register["topics"]}
    assert set(register_statuses) == set(spec_table), (
        f"topic id mismatch between register.json and spec §5.2: "
        f"register-only={set(register_statuses) - set(spec_table)}, "
        f"spec-only={set(spec_table) - set(register_statuses)}"
    )
    mismatches = {
        tid: (register_statuses[tid], spec_table[tid])
        for tid in register_statuses
        if register_statuses[tid] != spec_table[tid]
    }
    assert not mismatches, f"register vs. spec §5.2 status disagreement (register, spec): {mismatches}"


def test_map_at_takeoff_is_na_only_on_the_non_turbo_912is(register):
    entry = next(t for t in register["topics"] if t["topic_id"] == "map_at_takeoff")
    assert entry["status"]["912iS"] == "n/a"
    for engine in ("914iS", "915iS", "916iS"):
        assert entry["status"][engine] != "n/a"


def test_every_admitted_topic_has_unverified_or_admitted_on_every_applicable_engine(register):
    for t in register["topics"]:
        if t["status"]["916iS"] != "Admitted":
            continue
        for engine in ("912iS", "914iS", "915iS"):
            assert t["status"][engine] in ("Admitted", "Unverified", "n/a"), (
                f"{t['topic_id']}/{engine}: expected Admitted/Unverified/n/a, got {t['status'][engine]!r}"
            )


def test_removed_and_research_topics_carry_the_same_status_on_every_engine(register):
    for t in register["topics"]:
        s16 = t["status"]["916iS"]
        if s16 in ("Removed", "Research"):
            for engine in ("912iS", "914iS", "915iS"):
                assert t["status"][engine] == s16, f"{t['topic_id']}/{engine}: expected {s16!r}"


def test_allowlist_has_the_three_cause_3a_entries(register):
    allowlist = {e["limit_id"]: e for e in register["allowlist"]}
    assert set(allowlist) == {"fuel_press_max", "rpm_idle_min", "rpm_takeoff_max"}
    for lid, entry in allowlist.items():
        assert entry["aircraft"] == "N117ZS"
        assert entry["cause"] == "3a"
        assert entry["evidence"]
        assert entry["register_ref"] in ("D15", "D16", "D17")
