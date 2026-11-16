"""Spec 13 / Spec 16 §4.2, §4.6: the generated Investigations reference pages
match the tools and prompts the MCP server has (re-run
docs/tools/gen_investigation_reference.py when this fails)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_investigation_reference_pages_current():
    spec = importlib.util.spec_from_file_location("gen_ref", ROOT / "docs" / "tools" / "gen_investigation_reference.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    tools, prompts = gen.build()
    assert gen.TOOLS_PAGE.read_text() == tools, "docs/reference/investigation-tools.md is stale"
    assert gen.PROMPTS_PAGE.read_text() == prompts, "docs/reference/investigation-prompts.md is stale"
