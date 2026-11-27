"""
The notebook's shape and cell roles (Spec 16 D19, §5.6).

Seven sections in a fixed order, each opened by a markdown heading cell
(`role: section`, `section: n`, ids `s1`–`s7`):

  1 The question · 2 Answer · 3 Proposed actions — generated from
    `study_finish`'s structured fields (`question_scope`, `shows`, `means`,
    `actions`), marked `generated: true`, rewritten at every finish, so
    JupyterLab shows the text the page typesets;
  4 Findings · 5 How this was done · 6 Follow-ups · 7 Working — headings
    the cells Claude appends land under.

A cell's `role`: `evidence` (a captioned table, figure or log view, open and
numbered), `support` (the computation behind it, folded), `scratch`
(exploration, gathered under *Working* at finish), `narrative` (markdown).
A code cell with no role is `support`, a markdown cell `narrative`.

A notebook is *shaped* (`slingology.shape` = 1) once it has the headings:
from `study_create`, or — an older notebook — when a call first names a
section, opens a follow-up or finishes with the structured fields. Nothing
in an older notebook moves until then; its cells sit under *Findings*.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from .ipynb import (NotebookError, MAX_FINDING_CHARS, _is_setup, markdown_cell, meta, next_id, slmeta, slmeta_get,
                    text)
from .eis_lib import LOGVIEW_MIME

SHAPE_VERSION = 1
SECTIONS = {1: "The question", 2: "Answer", 3: "Proposed actions", 4: "Findings", 5: "How this was done",
            6: "Follow-ups", 7: "Working"}
GENERATED = (1, 2, 3)
WORKING = 7
FOLLOWUPS = 6
FINDINGS = 4
CODE_ROLES = ("evidence", "support", "scratch")
MARKDOWN_ROLES = ("narrative", "scratch")
ROLES = ("evidence", "support", "scratch", "narrative")
# Roles the engine writes; a cell holding one is never re-roled or moved by a call.
_FIXED = ("setup", "section", "followup")
NARRATIVE_LIKE = ("narrative", "question", "pin", "converted", "followup", "changed")
PLACEHOLDER = "*Written when the notebook is finished.*"
MAX_SHOWS = 5
MAX_ACTIONS = 8
MAX_FIELD_CHARS = 4000


def is_shaped(nb: dict) -> bool:
    return meta(nb).get("shape") == SHAPE_VERSION


def role(c: dict) -> str:
    r = slmeta_get(c).get("role")
    if r:
        return r
    return "support" if c.get("cell_type") == "code" else "narrative"


def section_no(c: dict) -> Optional[int]:
    sm = slmeta_get(c)
    return sm.get("section") if sm.get("role") == "section" else None


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ── The generated sections 1–3 ─────────────────────────────────────────────

def _heading(n: int) -> str:
    return f"## {n} {SECTIONS[n]}"


def action_line(a: dict) -> str:
    """'**Have the shop check the regulator** · A&P · settles whether … · re-check after the next 10 flights'."""
    parts = [f"**{a['what']}**"]
    if a.get("who"):
        parts.append(str(a["who"]))
    if a.get("settles"):
        parts.append(f"settles: {a['settles']}")
    if a.get("recheck_after_flights"):
        n = int(a["recheck_after_flights"])
        parts.append(f"re-check after the next {n} flight{'' if n == 1 else 's'}")
    return " · ".join(parts)


def generated_sources(m: dict) -> dict[int, str]:
    """The markdown of sections 1–3 from the notebook's metadata: the title
    and the question as asked, its scope; what the data shows and what it
    means; the actions. Before a structured finish, the summary stands as
    *What it means* (an older finish) or a placeholder."""
    top = m.get("top") or {}
    s1 = [f"# {m.get('name') or 'Notebook'}", "", _heading(1), "", (m.get("question") or "*No question was given.*").strip()]
    if top.get("question_scope"):
        s1 += ["", "**Scope and qualifications**", "", top["question_scope"].strip()]
    s2 = [_heading(2), ""]
    if top.get("shows"):
        s2 += ["**What the data shows**", ""] + [f"- {s}" for s in top["shows"]] + [""]
    means = top.get("means") or m.get("summary")
    if means:
        s2 += ["**What it means**", "", str(means).strip()]
    elif not top.get("shows"):
        s2.append(PLACEHOLDER)
    s3 = [_heading(3), ""]
    if top.get("actions"):
        s3 += [f"{i}. {action_line(a)}" for i, a in enumerate(top["actions"], 1)]
    elif top.get("actions_none"):
        s3.append(f"None. {top['actions_none'].strip()}")
    elif top:
        s3.append("None.")
    else:
        s3.append(PLACEHOLDER)
    return {1: "\n".join(s1).rstrip() + "\n", 2: "\n".join(s2).rstrip() + "\n", 3: "\n".join(s3).rstrip() + "\n"}


def section_cell(n: int, source: Optional[str] = None) -> dict:
    c = markdown_cell(f"s{n}", source or (_heading(n) + "\n"), role="section")
    slmeta(c)["section"] = n
    if n in GENERATED:
        slmeta(c)["generated"] = True
    return c


def refresh_generated(nb: dict) -> None:
    src = generated_sources(meta(nb))
    for c in nb["cells"]:
        n = section_no(c)
        if n in GENERATED:
            c["source"] = src[n]


def new_cells(m: dict) -> list[dict]:
    """study_create's cells after the setup cell: the seven headings, 1–3
    with their generated text."""
    src = generated_sources(m)
    return [section_cell(n, src.get(n)) for n in SECTIONS]


def ensure_shape(nb: dict) -> bool:
    """Give an older notebook the headings (D19): 1–3 after the setup cell —
    replacing the question cell study_create wrote, which 1 now holds —
    *Findings* over every cell it has, then 5–7 at the end. Nothing else
    moves. True when it changed."""
    if is_shaped(nb):
        return False
    m = meta(nb)
    cells = [c for c in nb["cells"]]
    setup = [c for c in cells if _is_setup(c)]
    rest = [c for c in cells if not _is_setup(c)]
    if rest and rest[0].get("cell_type") == "markdown" and slmeta_get(rest[0]).get("role") == "question" \
            and text(rest[0].get("source")).lstrip().startswith("# "):
        rest = rest[1:]                     # the title and question, now section 1
    fill_roles(nb)
    src = generated_sources(m)
    nb["cells"] = (setup + [section_cell(n, src[n]) for n in GENERATED] + [section_cell(FINDINGS)] + rest
                   + [section_cell(n) for n in (5, FOLLOWUPS, WORKING)])
    m["shape"] = SHAPE_VERSION
    return True


def fill_roles(nb: dict) -> bool:
    """D19 for older notebooks: a cell without a role gets `support` (code)
    or `narrative` (markdown); nothing moves."""
    changed = False
    for c in nb.get("cells") or []:
        if c.get("cell_type") not in ("code", "markdown") or _is_setup(c):
            continue
        if not slmeta_get(c).get("role"):
            slmeta(c)["role"] = "support" if c["cell_type"] == "code" else "narrative"
            changed = True
    return changed


# ── Placing cells ──────────────────────────────────────────────────────────

def bounds(nb: dict, n: int) -> tuple[int, int]:
    """(index of section n's heading, index where it ends: the next heading)."""
    cells = nb["cells"]
    start = next((i for i, c in enumerate(cells) if section_no(c) == n), None)
    if start is None:
        raise NotebookError("BAD_PARAMS", f"this notebook has no section {n}")
    end = next((i for i in range(start + 1, len(cells)) if section_no(cells[i]) is not None), len(cells))
    return start, end


def section_at(nb: dict, idx: int) -> Optional[int]:
    """The section the cell at idx sits in (None before the first heading)."""
    cur = None
    for i, c in enumerate(nb["cells"][:idx + 1]):
        if section_no(c) is not None:
            cur = section_no(c)
    return cur


def check_role(kind: str, r: Optional[str]) -> Optional[str]:
    if r is None:
        return None
    allowed = CODE_ROLES if kind == "code" else MARKDOWN_ROLES
    if r not in allowed:
        what = "a code cell (or a log view)" if kind == "code" else "a markdown cell"
        raise NotebookError("BAD_PARAMS", f"{what}'s role is {', '.join(allowed)}; got {r!r}"
                                          + (" — evidence is a code cell whose output is eis.table, eis.figure or "
                                             "eis.logview" if r == "evidence" else ""))
    return r


def check_section(section) -> Optional[int]:
    if section is None:
        return None
    try:
        n = int(section)
    except (TypeError, ValueError):
        raise NotebookError("BAD_PARAMS", "section is 4 (Findings), 5 (How this was done), 6 (Follow-ups) or 7 (Working)")
    if n not in (4, 5, 6, 7):
        raise NotebookError("BAD_PARAMS", "section is 4 (Findings), 5 (How this was done), 6 (Follow-ups) or 7 "
                                          "(Working); 1–3 are written by study_finish")
    return n


def default_section(nb: dict, r: str) -> int:
    if r == "scratch":
        return WORKING
    return FOLLOWUPS if meta(nb).get("followup") else FINDINGS


def place(nb: dict, cell: dict, section: Optional[int] = None) -> None:
    """Put a new cell at the end of its section (shaped notebooks), else at
    the end of the notebook."""
    if not is_shaped(nb):
        nb["cells"].append(cell)
        return
    n = section or default_section(nb, role(cell))
    _, end = bounds(nb, n)
    nb["cells"].insert(end, cell)


def move(nb: dict, cell: dict, section: int) -> None:
    nb["cells"].remove(cell)
    _, end = bounds(nb, section)
    nb["cells"].insert(end, cell)


def set_role(cell: dict, r: Optional[str]) -> None:
    if r:
        slmeta(cell)["role"] = r


def fixed(cell: dict) -> bool:
    return _is_setup(cell) or slmeta_get(cell).get("role") in _FIXED


# ── Follow-ups (§5.6, F17) ─────────────────────────────────────────────────

def open_followup(nb: dict, date: Optional[str] = None, title: Optional[str] = None) -> dict:
    """A dated subsection at the end of *Follow-ups*; cells appended without a
    section land in it until study_finish closes it."""
    m = meta(nb)
    if m.get("followup"):
        raise NotebookError("BAD_PARAMS", f"a follow-up is already open (cell {m['followup']}); "
                                          "study_finish closes it")
    ensure_shape(nb)
    d = str(date or _today()).strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        raise NotebookError("BAD_PARAMS", "a follow-up's date is YYYY-MM-DD")
    head = f"### Follow-up — {d}" + (f": {' '.join(str(title).split())}" if title and str(title).strip() else "")
    c = markdown_cell(next_id(nb), head + "\n", role="followup")
    slmeta(c)["date"] = d
    _, end = bounds(nb, FOLLOWUPS)
    nb["cells"].insert(end, c)
    m["followup"] = c["id"]
    return c


def close_followup(nb: dict, changed: Optional[str]) -> Optional[dict]:
    """At finish: the open follow-up ends with what changed above."""
    m = meta(nb)
    if not m.get("followup"):
        return None
    line = " ".join(str(changed or "").split())
    if not line:
        raise NotebookError("BAD_PARAMS", f"a follow-up ends with what changed above (the follow-up opened at cell "
                                          f"{m['followup']}): pass changed — e.g. \"Answer: the climb share is 13%, "
                                          "not the largest; actions unchanged\"")
    c = markdown_cell(next_id(nb), f"**What changed above:** {line}\n", role="changed")
    _, end = bounds(nb, FOLLOWUPS)
    nb["cells"].insert(end, c)
    m.pop("followup", None)
    return c


# ── The structured top (study_finish) ──────────────────────────────────────

def _str(v, what: str, limit: int = MAX_FIELD_CHARS) -> Optional[str]:
    if v is None:
        return None
    if not isinstance(v, str):
        raise NotebookError("BAD_PARAMS", f"{what} is text")
    v = v.strip()
    if len(v) > limit:
        raise NotebookError("BAD_PARAMS", f"{what} is at most {limit} characters")
    return v or None


def clean_top(params: dict) -> Optional[dict]:
    """study_finish's structured fields, checked; None when none was given."""
    keys = ("question_scope", "shows", "means", "actions", "actions_none")
    if not any(params.get(k) is not None for k in keys):
        return None
    shows = params.get("shows")
    if isinstance(shows, str):
        shows = [shows]
    if shows is not None and (not isinstance(shows, list) or not all(isinstance(s, str) for s in shows)):
        raise NotebookError("BAD_PARAMS", "shows is a list of sentences, each a number the data shows")
    shows = [" ".join(s.split()) for s in shows or [] if s.strip()]
    if len(shows) > MAX_SHOWS:
        raise NotebookError("BAD_PARAMS", f"shows is 3–5 bullets (at most {MAX_SHOWS}); the findings hold the rest")
    for s in shows:
        if len(s) > MAX_FINDING_CHARS:
            raise NotebookError("BAD_PARAMS", f"each of shows is one sentence (at most {MAX_FINDING_CHARS} characters)")
    actions = params.get("actions")
    if actions is not None and not isinstance(actions, list):
        raise NotebookError("BAD_PARAMS", "actions is a list of {what, who, settles, recheck_after_flights?}, or [] "
                                          "with actions_none saying why")
    out_actions = []
    for a in actions or []:
        if isinstance(a, str):
            a = {"what": a}
        if not isinstance(a, dict) or not str(a.get("what") or "").strip():
            raise NotebookError("BAD_PARAMS", "each action has what (and who, settles; recheck_after_flights when EIS "
                                              "can watch it)")
        item = {"what": " ".join(str(a["what"]).split())}
        for k in ("who", "settles"):
            if a.get(k) is not None and str(a[k]).strip():
                item[k] = " ".join(str(a[k]).split())
        if a.get("recheck_after_flights") is not None:
            try:
                n = int(a["recheck_after_flights"])
            except (TypeError, ValueError):
                raise NotebookError("BAD_PARAMS", "recheck_after_flights is a number of flights")
            if n < 1:
                raise NotebookError("BAD_PARAMS", "recheck_after_flights is at least 1")
            item["recheck_after_flights"] = n
        out_actions.append(item)
    if len(out_actions) > MAX_ACTIONS:
        raise NotebookError("BAD_PARAMS", f"at most {MAX_ACTIONS} actions")
    top = {"question_scope": _str(params.get("question_scope"), "question_scope"), "shows": shows,
           "means": _str(params.get("means"), "means"), "actions": out_actions,
           "actions_none": _str(params.get("actions_none"), "actions_none", 1000)}
    return {k: v for k, v in top.items() if v not in (None, [])} | {"shows": shows, "actions": out_actions}


# ── The finish rules (§5.6, acceptance 26) ─────────────────────────────────

def is_evidence_output(o: dict) -> bool:
    data = o.get("data") or {}
    return bool(((o.get("metadata") or {}).get("slingology") or {}).get("evidence")) or LOGVIEW_MIME in data


def evidence_refusals(nb: dict) -> list[str]:
    """Evidence cells whose output is plain text: a `print` (any stream), or
    no table, figure or log view from eis.table / eis.figure / eis.logview."""
    out = []
    for c in nb["cells"]:
        if c.get("cell_type") != "code" or role(c) != "evidence":
            continue
        outs = c.get("outputs") or []
        if not outs and not slmeta_get(c).get("ran"):
            continue        # not run yet (no bench here): nothing to judge
        if any(o.get("output_type") == "stream" for o in outs) or not any(is_evidence_output(o) for o in outs):
            out.append(c["id"])
    return out


def support_dangling(nb: dict) -> list[str]:
    """Support cells with nothing after them: a run of support cells that the
    next cell — in the same section — doesn't follow with evidence or
    narrative (the floor rule, extended)."""
    cells = nb["cells"]
    out = []
    run: list[str] = []
    for i, c in enumerate(cells):
        is_support = c.get("cell_type") == "code" and not _is_setup(c) and role(c) == "support"
        if is_support:
            run.append(c["id"])
            continue
        if run:
            r = role(c)
            if section_no(c) is not None or r not in ("evidence",) + NARRATIVE_LIKE:
                out += run
            run = []
    return out + run


def _written(c: dict) -> tuple:
    m = re.match(r"^c(\d+)$", str(c.get("id")))
    return (0, int(m.group(1))) if m else (1, 0)


def gather_scratch(nb: dict) -> list[str]:
    """At finish (shaped notebooks): every scratch cell under *Working*, in
    the order they were written (cell ids are numbered as cells are added).
    The ids moved."""
    if not is_shaped(nb):
        return []
    w_start, _ = bounds(nb, WORKING)
    moved = [c for i, c in enumerate(nb["cells"]) if role(c) == "scratch" and i < w_start]
    for c in moved:
        nb["cells"].remove(c)
    w_start, w_end = bounds(nb, WORKING)
    nb["cells"][w_start + 1:w_end] = sorted(moved + nb["cells"][w_start + 1:w_end], key=_written)
    return [c["id"] for c in moved]


def record_top(nb: dict, top: dict) -> None:
    """A re-finish keeps the previous top in history, with its date."""
    m = meta(nb)
    prev = m.get("top")
    if prev and prev != top:
        m["history"] = [*(m.get("history") or []), {**prev, "finished": m.get("finished")}]
    m["top"] = top


def actions_count(m: dict) -> Optional[int]:
    top = m.get("top")
    return len(top.get("actions") or []) if top else None
