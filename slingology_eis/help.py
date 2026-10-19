"""
help.py — topic help: parsing slingology_eis/help/topics.md (Spec 01
§8.8), resolving its placeholders against an engine profile, rule set
and analysis config, and building TopicHelp objects.

Kept outside code on purpose (Spec 01 §8.8): this module is the
*mechanism* — the pilot-facing content itself lives in topics.md, not
here, and is never rewritten by this module.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .contract import Diagnostic
from .resources import resource

_PACKAGE_ROOT = Path(__file__).resolve().parent
_TOOLKIT_ROOT = _PACKAGE_ROOT.parent
_HELP_PATH = _PACKAGE_ROOT / "help" / "topics.md"
# docs/specs/topics/register.json lives outside slingology_eis/ by design
# (Spec 10 §5) — resolved the same repo-root-relative way engines/*.json
# already is (limits.py's _TOOLKIT_ROOT), not as declared package data.
# See pyproject.toml's package-data comment for why.
_REGISTER_PATH = resource("docs/specs/topics/register.json")

_REQUIRED_KEYS = ("title", "applies_to", "last_reviewed")
_HEADING_RE = re.compile(r"^## (.+)$")
_KEY_RE = re.compile(r"^([a-zA-Z_]+):\s*(.*)$")
_PLACEHOLDER_RE = re.compile(r"\{(limit|profile|rule|config):([^}]+)\}")

# Spec 01 §8.8's unit table for the `profile` namespace. Matched against
# the final dotted path segment's underscore-separated tokens: "rpm" only
# as the first token (the spec writes it "rpm_", a prefix, unlike the
# others written "_x", a suffix); every other unit token may appear
# anywhere in the segment (e.g. "power_pct_threshold" carries "pct" in
# the middle, not at the very end, but is still unambiguously a percent).
_PROFILE_UNIT_TOKENS = {
    "s": "s", "f": "°F", "c": "°C", "psi": "psi",
    "inhg": "inHg", "lph": "L/h", "pct": "%",
}

# Units rendered with no space before them in canonical text, matching
# topics.py's existing analysis-line convention (e.g. "248°F", "100%");
# everything else (s, rpm, psi, inHg, L/h) gets a space (e.g. "60 s",
# "5,800 rpm", "+2.5 psi" — filters.py's existing convention).
_NO_SPACE_UNITS = {"°F", "°C", "%"}


@dataclass
class HelpEntry:
    id: str
    title: str
    applies_to: object          # "all" or list[str]
    last_reviewed: str
    template: str


def parse_help_file(text: str) -> dict[str, HelpEntry]:
    """
    Parse topics.md into {id: HelpEntry}. Raises ValueError on a missing
    key, more than one paragraph, or a duplicate heading. Text before the
    first '##' heading is ignored.
    """
    lines = text.splitlines()
    starts = [i for i, l in enumerate(lines) if l.startswith("## ")]
    entries: dict[str, HelpEntry] = {}
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        block = lines[start:end]
        m = _HEADING_RE.match(block[0])
        entry_id = m.group(1).strip()
        if entry_id in entries:
            raise ValueError(f"topics.md: duplicate heading '## {entry_id}'")

        fields: dict[str, str] = {}
        i = 1
        while i < len(block) and block[i].strip():
            km = _KEY_RE.match(block[i])
            if km:
                fields[km.group(1)] = km.group(2).strip()
            i += 1
        missing = [k for k in _REQUIRED_KEYS if k not in fields]
        if missing:
            raise ValueError(f"topics.md: '{entry_id}' is missing {missing}")

        # Skip the blank separator line(s), then collect paragraph(s).
        while i < len(block) and not block[i].strip():
            i += 1
        paragraphs = []
        current: list[str] = []
        for line in block[i:]:
            if line.strip():
                current.append(line.strip())
            elif current:
                paragraphs.append(" ".join(current))
                current = []
        if current:
            paragraphs.append(" ".join(current))
        if len(paragraphs) != 1:
            raise ValueError(
                f"topics.md: '{entry_id}' has {len(paragraphs)} paragraphs, expected exactly 1"
            )

        applies_to_raw = fields["applies_to"]
        if applies_to_raw == "all":
            applies_to = "all"
        else:
            applies_to = [s.strip() for s in applies_to_raw.strip("[]").split(",") if s.strip()]

        entries[entry_id] = HelpEntry(
            id=entry_id, title=fields["title"], applies_to=applies_to,
            last_reviewed=fields["last_reviewed"], template=paragraphs[0],
        )
    return entries


def load_help_entries() -> dict[str, HelpEntry]:
    return parse_help_file(_HELP_PATH.read_text())


def load_register() -> Optional[dict]:
    if not _REGISTER_PATH.exists():
        return None
    return json.loads(_REGISTER_PATH.read_text())


def _profile_unit_for(segment: str) -> Optional[str]:
    tokens = segment.split("_")
    if tokens and tokens[0] == "rpm":
        return "rpm"
    for tok in tokens:
        if tok in _PROFILE_UNIT_TOKENS:
            return _PROFILE_UNIT_TOKENS[tok]
    return None


def _resolve_one(
    namespace: str, key: str, *,
    engine_config: dict, rules: dict, baseline_config: dict,
) -> tuple[Optional[object], Optional[str]]:
    """(value, unit) for one placeholder key, or (None, None) if it can't
    be resolved — the caller turns that into a diagnostic, never a raise."""
    if namespace == "limit":
        from .limits import limit_catalog
        entry = next((l for l in limit_catalog(engine_config) if l["id"] == key), None)
        if entry is None:
            return None, None
        return entry["limit_value"], entry["unit"]

    if namespace == "profile":
        parts = key.split(".")
        node = engine_config
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                return None, None
            node = node[part]
        unit = _profile_unit_for(parts[-1])
        if unit is None:
            raise ValueError(f"topics.md: profile key '{key}' has no recognizable unit suffix")
        return node, unit

    if namespace == "rule":
        parts = key.split(".")
        if len(parts) != 3:
            return None, None
        rule_id, trigger_type, param = parts
        topic_rule = (rules.get("rules") or {}).get(rule_id)
        if not isinstance(topic_rule, dict):
            return None, None
        trig = next((t for t in topic_rule.get("triggers", [])
                     if isinstance(t, dict) and t.get("type") == trigger_type), None)
        if trig is None or param not in trig:
            return None, None
        return trig[param], None

    if namespace == "config":
        if key not in baseline_config:
            return None, None
        return baseline_config[key], None

    return None, None


def resolve_template(
    template: str, *, engine_config: dict, rules: dict, baseline_config: dict,
) -> tuple[dict[str, dict], str, list[str]]:
    """
    (values, text, unresolved_keys) for one help entry's template.
    `values` is keyed by the literal placeholder text ("{limit:oil_temp_max}"),
    each a {"value", "unit"} dict, for the UI to format in the pilot's
    chosen unit system (Spec 02 §6.6 — imperial/metric is a display
    concern, not the engine's). `text` is the canonical-unit rendering
    (the engine's one fixed internal unit per value, same convention
    analysis lines already use), for the CLI and other plain-text
    consumers that don't do unit conversion. `unresolved_keys` lists any
    placeholder that couldn't be resolved, for the caller to turn into a
    HELP_PLACEHOLDER_UNRESOLVED diagnostic.
    """
    values: dict[str, dict] = {}
    unresolved: list[str] = []

    def _sub(m: re.Match) -> str:
        namespace, key = m.group(1), m.group(2)
        placeholder = m.group(0)
        value, unit = _resolve_one(
            namespace, key, engine_config=engine_config, rules=rules, baseline_config=baseline_config,
        )
        if value is None:
            unresolved.append(placeholder)
            return placeholder
        values[placeholder] = {"value": value, "unit": unit}
        if unit is None:
            return str(value)
        return f"{value}{unit}" if unit in _NO_SPACE_UNITS else f"{value} {unit}"

    text = _PLACEHOLDER_RE.sub(_sub, template)
    return values, text, unresolved


@dataclass
class TopicHelp:
    id: str
    title: str
    template: str
    values: dict[str, dict]
    text: str
    applies: bool
    validated: bool
    last_reviewed: str

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "template": self.template,
            "values": self.values, "text": self.text, "applies": self.applies,
            "validated": self.validated, "last_reviewed": self.last_reviewed,
        }
