"""
Spec 16 D16 — *Mark for Claude*: the owner's questions and pins, run the
three ways every host operation is (in process, over HTTP, under Pyodide
in Node.js) on synthetic flights (no private logs). Acceptance 19's
engine clauses: two windows on two flights under one question "rough
climbs" are one question with two pins; study_create with the question
opens a notebook whose first cells after the question are those marks
(the note, then the log view); study_finish naming the question resolves
it and its pins. Export carries the pins by fingerprint.
"""
import io
import json
import zipfile

import pytest

from tests.unit.test_research_ops import _ok, research_ws  # noqa: F401 — fixtures and helpers
from tests.unit.test_server import (  # noqa: F401 — fixtures
    InProcess, NodeHost, _node_host, isolated_packaged_home, registry_server, rpc,
)


def _has_bench(h) -> bool:
    return not isinstance(h, NodeHost)


def _src(cell: dict) -> str:
    s = cell.get("source")
    return s if isinstance(s, str) else "".join(s or [])


def _mark_two(h, ids):
    a = _ok(rpc(h, "flight_pin", {"flight_id": ids[0], "start_s": 100, "end_s": 160, "channels": ["rpm", "map_inhg"],
                                  "note": "rpm wanders in the climb", "question": {"title": "rough climbs"}}))
    q = a["question"]
    b = _ok(rpc(h, "flight_pin", {"flight_id": ids[1], "start_s": 120, "end_s": 170, "channels": ["rpm"],
                                  "note": "again, less", "question": q["id"]}))
    return a, b, q


def test_two_marks_under_one_question(research_ws):
    h, ids = research_ws
    a, b, q = _mark_two(h, ids)
    assert q["title"] == "rough climbs" and q["status"] == "new" and q["study_id"] is None
    assert a["where"] == "under “rough climbs” (1 mark) in Research → Inbox"
    assert b["where"] == "under “rough climbs” (2 marks) in Research → Inbox"
    pin = a["pin"]
    # A pin is where to look and a sentence — nothing else is stored.
    stored = {k for k in pin if k not in ("flight_here", "date", "flight_name", "when", "route")}
    assert stored == {"id", "question_id", "flight", "start_s", "end_s", "channels", "note", "created"}
    assert pin["flight"] == ids[0] and (pin["start_s"], pin["end_s"]) == (100, 160) and pin["flight_here"] is True
    listing = _ok(rpc(h, "pins_list", {}))
    assert [x["title"] for x in listing["questions"]] == ["rough climbs"]
    one = listing["questions"][0]
    assert one["pin_count"] == 2 and one["newest_note"] == "again, less"
    assert [p["flight"] for p in one["pins"]] == ids[:2]
    assert listing["unassigned"] == [] and listing["newest_open"] == q["id"]
    assert listing["counts"]["new"] == 1


def test_unassigned_edit_move_and_delete(research_ws):
    h, ids = research_ws
    loose = _ok(rpc(h, "flight_pin", {"flight_id": ids[2], "start_s": 10, "end_s": 40, "note": "odd dip"}))
    assert loose["question"] is None and loose["where"] == "in Research → Inbox, under Unassigned"
    assert [p["id"] for p in _ok(rpc(h, "pins_list", {}))["unassigned"]] == [loose["pin"]["id"]]
    # Move it under a new question, edit its note, then back to unassigned.
    moved = _ok(rpc(h, "pin_edit", {"pin_id": loose["pin"]["id"], "question": {"title": "dips"}, "note": "odd dip at 30 s"}))
    assert moved["question"]["title"] == "dips" and moved["pin"]["note"] == "odd dip at 30 s"
    qid = moved["question"]["id"]
    assert _ok(rpc(h, "question_edit", {"question_id": qid, "title": "rpm dips"}))["question"]["title"] == "rpm dips"
    back = _ok(rpc(h, "pin_edit", {"pin_id": loose["pin"]["id"], "question": None}))
    assert back["pin"]["question_id"] is None and back["question"] is None
    # Deleting a question leaves its pins, unassigned.
    _ok(rpc(h, "pin_edit", {"pin_id": loose["pin"]["id"], "question": qid}))
    gone = _ok(rpc(h, "question_delete", {"question_id": qid}))
    assert gone == {"deleted": qid, "pins_unassigned": 1}
    assert len(_ok(rpc(h, "pins_list", {}))["unassigned"]) == 1
    assert _ok(rpc(h, "pin_delete", {"pin_id": loose["pin"]["id"]})) == {"deleted": loose["pin"]["id"]}
    after = _ok(rpc(h, "pins_list", {}))
    assert after["unassigned"] == [] and after["questions"] == []
    # Refusals say why.
    for op, p in (("flight_pin", {"flight_id": "nope", "start_s": 1, "end_s": 2}),
                  ("flight_pin", {"flight_id": ids[0], "start_s": 5, "end_s": 5}),
                  ("flight_pin", {"flight_id": ids[0], "start_s": 1, "end_s": 2, "question": {"title": " "}}),
                  ("pin_edit", {"pin_id": "p-none"}), ("question_resolve", {"question_id": qid, "status": "done"})):
        r = rpc(h, op, p)
        assert not r["ok"] and r["error"]["code"] in ("BAD_PARAMS", "NOT_FOUND"), (op, r)


def test_study_create_with_the_question_opens_with_the_marks_and_finish_resolves_it(research_ws):
    h, ids = research_ws
    _a, _b, q = _mark_two(h, ids)
    view = _ok(rpc(h, "study_create", {"name": "Rough climbs", "question_id": q["id"]}))
    sid = view["study_id"]
    cells = view["notebook"]["cells"]
    assert view["question"] == "rough climbs"
    # setup, the question, then per mark: the owner's note, its log view.
    body = cells[2:]
    assert [c["cell_type"] for c in body] == ["markdown", "code", "markdown", "code"]
    assert "> rpm wanders in the climb" in _src(body[0]) and "> again, less" in _src(body[2])
    assert _src(body[1]).startswith(f"eis.logview({ids[0]!r}, 100, 160, channels=['rpm', 'map_inhg']")
    assert _src(body[3]).startswith(f"eis.logview({ids[1]!r}, 120, 170, channels=['rpm']")
    ran = [bool(c.get("outputs")) for c in (body[1], body[3])]
    assert ran == ([True, True] if _has_bench(h) else [False, False])
    q1 = _ok(rpc(h, "pins_list", {}))["questions"][0]
    assert (q1["status"], q1["study_id"]) == ("investigating", sid)
    assert all("status" not in p for p in q1["pins"])           # an open question's pins carry none
    # The notebook passes the floor rule as written (a note beside each log view).
    done = _ok(rpc(h, "study_finish", {"study_id": sid, "summary": "Two climbs; rpm wanders by 40 rpm.", "question": q["id"]}))
    assert done["question"]["status"] == "watch" and done["question"]["study_id"] == sid
    q2 = _ok(rpc(h, "pins_list", {}))["questions"][0]
    assert q2["status"] == "watch" and {(p["status"], p["study_id"]) for p in q2["pins"]} == {("watch", sid)}
    assert _ok(rpc(h, "pins_list", {}))["newest_open"] is None
    # question_resolve reopens it; the pins drop the resolution.
    _ok(rpc(h, "question_resolve", {"question_id": q["id"], "status": "investigating"}))
    assert all("status" not in p for p in _ok(rpc(h, "pins_list", {}))["questions"][0]["pins"])


def test_guide_lists_open_questions_with_their_marks(research_ws):
    h, ids = research_ws
    assert "The owner's questions: none open, no marks." in _ok(rpc(h, "guide", {}))["document"]
    _a, _b, q = _mark_two(h, ids)
    _ok(rpc(h, "flight_pin", {"flight_id": ids[3], "start_s": 1, "end_s": 30, "note": "loose"}))
    g = _ok(rpc(h, "guide", {}))
    line = next(x for x in g["document"].splitlines() if q["id"] in x)
    assert line == (f"- `{q['id']}` **rough climbs** — new, 2 marks; newest note: \"again, less\" *(newest)*")
    assert "- 1 unassigned mark (no question)" in g["document"]
    assert g["workspace"]["questions_open"] == 1 and g["workspace"]["pins_unassigned"] == 1


def test_pins_travel_by_fingerprint_and_map_back(registry_server, tmp_path):
    if isinstance(registry_server, NodeHost):
        pytest.skip("workspace export round trip: in process and over HTTP (test_workspace_export)")
    from tests.unit.test_workspace_export import _active_dir, _export, _sender, _upload
    url = registry_server
    _f, fids = _sender(url, tmp_path)
    a = _ok(rpc(url, "flight_pin", {"flight_id": fids[0], "start_s": 10, "end_s": 50, "note": "look here",
                                    "question": {"title": "rough climbs"}}))
    _res, data = _export(url, include_logs=True)
    inner = next(n for n in zipfile.ZipFile(io.BytesIO(data)).namelist() if n.endswith(".eisworkspace"))
    sent = json.loads(zipfile.ZipFile(io.BytesIO(zipfile.ZipFile(io.BytesIO(data)).read(inner))).read("pins.json"))
    assert sent["pins"][0]["flight"].startswith("src:") and fids[0] not in json.dumps(sent)
    up = _upload(url, data, "Sender.zip")
    rpc(url, "import_workspace", {"upload_id": up})
    assert json.loads((_active_dir() / "pins.json").read_text())["pins"][0]["flight"].startswith("src:")
    rpc(url, "scan_workspace", {})
    got = _ok(rpc(url, "pins_list", {}))["questions"][0]
    assert got["title"] == "rough climbs" and got["pins"][0]["flight"] == a["pin"]["flight"] == fids[0]
    assert got["pins"][0]["flight_here"] is True
