"""
Spec 16 D17 — *Move my workspace*: the website's workspace, exported in
its page and posted to the local server, becomes a new workspace here.

The sender runs the three ways (in process, over HTTP, and under Pyodide
in Node.js — the browser host itself); the receiver is always the HTTP
server, since the probe and the move route are HTTP routes. Acceptance
21's engine clauses on synthetic logs: two flights, a question with two
pins and a journal entry arrive; after the log folder is linked and
synced the pins name flights of this workspace. And the cross-origin
rule: the website's origin reaches the probe and the move only.
"""
import json
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from slingology_eis import data_location
from slingology_eis.server import MOVE_PATH, PROBE_PATH, WEBSITE_ORIGINS, build_server

from .test_server import (  # noqa: F401 — fixtures
    InProcess, NodeHost, _node_host, isolated_packaged_home, registry_server, rpc,
)
from .test_workspace_export import _export, _logs_folder

WEBSITE = WEBSITE_ORIGINS[0]


@pytest.fixture
def receiver(tmp_path, monkeypatch):
    """A second machine's EIS: its own data root, already holding a
    workspace (the move must add one, never merge)."""
    home = tmp_path / "receiver-home"
    home.mkdir()
    monkeypatch.setattr(data_location, "_PACKAGED_HOME", home)
    httpd = build_server(logs_dir=None, workspace_dir=None, port=0, quiet=True)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{httpd.server_port}"
    rpc(url, "create_workspace", {"name": "Already here", "engine_model": "916iS"})
    yield url
    httpd.shutdown()
    httpd.server_close()
    t.join(timeout=5)


def _req(url, method="GET", data=None, origin=None, headers=None):
    h = dict(headers or {})
    if origin:
        h["Origin"] = origin
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _browser_workspace(h, tmp_path):
    """The website's workspace: two flights, a question with two pins, a
    journal entry."""
    assert rpc(h, "create_workspace", {"name": "My Sling", "engine_model": "916iS"})["ok"]
    folder = _logs_folder(tmp_path, days=(1, 2))
    rpc(h, "add_log_folder", {"path": str(folder)})
    rpc(h, "scan_workspace", {})
    fids = sorted(r["flight_id"] for r in rpc(h, "list_flights", {})["result"])
    assert len(fids) == 2
    for fid, (a, b) in zip(fids, ((100, 160), (120, 170))):
        r = rpc(h, "flight_pin", {"flight_id": fid, "start_s": a, "end_s": b, "channels": ["rpm"],
                                  "note": "rough", "question": {"title": "rough climbs"} if a == 100 else None})
        assert r["ok"], r
        if a == 100:
            qid = r["result"]["question"]["id"]
    rpc(h, "pin_edit", {"pin_id": rpc(h, "pins_list", {})["result"]["unassigned"][0]["id"], "question": qid})
    assert rpc(h, "save_annotation", {"flight_id": fids[0], "ref": {"kind": "flight"}, "note": "felt rough"})["ok"]
    return folder, fids


def test_acceptance_21_move_my_workspace(registry_server, receiver, tmp_path):
    (tmp_path / "sender").mkdir()
    folder, fids = _browser_workspace(registry_server, tmp_path / "sender")
    res, data = _export(registry_server, include_logs=False)

    # The page asks first; the website's origin may.
    status, headers, body = _req(receiver + PROBE_PATH, origin=WEBSITE)
    assert status == 200 and headers.get("Access-Control-Allow-Origin") == WEBSITE
    assert json.loads(body)["move_workspace"] is True

    status, headers, body = _req(f"{receiver}{MOVE_PATH}?filename={urllib.parse.quote(res['filename'])}", "POST", data, origin=WEBSITE,
                                 headers={"Content-Type": "application/octet-stream"})
    assert status == 200 and headers.get("Access-Control-Allow-Origin") == WEBSITE, body
    moved = json.loads(body)
    assert moved["ok"], moved
    wid = moved["result"]["workspace_id"]
    assert moved["result"]["open_url"].endswith(f"/?moved={wid}#/flights")

    # An additional workspace, never a merge; the moved one is active.
    names = sorted(w["name"] for w in rpc(receiver, "list_workspaces", {})["result"])
    assert names == ["Already here", "My Sling (imported)"]
    assert rpc(receiver, "get_active_workspace", {})["result"]["manifest"]["id"] == wid

    # The question, its two pins and the journal entry arrived.
    pins = rpc(receiver, "pins_list", {})["result"]
    assert [q["title"] for q in pins["questions"]] == ["rough climbs"] and len(pins["questions"][0]["pins"]) == 2
    assert any(e["kind"] == "annotation" and e["what"] == "felt rough"
               for e in rpc(receiver, "get_journal", {})["result"]["entries"])

    # Linked and synced, the pins name this workspace's flights.
    rpc(receiver, "add_log_folder", {"path": str(folder)})
    rpc(receiver, "scan_workspace", {})
    here = {r["flight_id"] for r in rpc(receiver, "list_flights", {})["result"]}
    assert here == set(fids)
    assert {p["flight"] for p in rpc(receiver, "pins_list", {})["result"]["questions"][0]["pins"]} == set(fids)


def test_only_the_probe_and_the_move_are_open_to_the_website(receiver):
    rpc_body = json.dumps({"op": "list_workspaces", "params": {}}).encode()
    # The website: the probe yes, /rpc no — no CORS, and a POST refused.
    status, headers, _ = _req(receiver + "/rpc", "OPTIONS", origin=WEBSITE,
                              headers={"Access-Control-Request-Method": "POST"})
    assert "Access-Control-Allow-Origin" not in headers
    status, headers, _ = _req(receiver + "/rpc", "POST", rpc_body, origin=WEBSITE, headers={"Content-Type": "text/plain"})
    assert status == 403
    status, _, _ = _req(receiver + "/upload?filename=x.csv", "POST", b"x", origin=WEBSITE)
    assert status == 403
    # The probe answers a Private Network Access preflight.
    status, headers, _ = _req(receiver + MOVE_PATH, "OPTIONS", origin=WEBSITE,
                              headers={"Access-Control-Request-Method": "POST",
                                       "Access-Control-Request-Private-Network": "true"})
    assert headers.get("Access-Control-Allow-Origin") == WEBSITE
    assert headers.get("Access-Control-Allow-Private-Network") == "true"
    # Any other site: nothing, anywhere.
    for path in (PROBE_PATH, "/rpc", "/"):
        _, headers, _ = _req(receiver + path, origin="https://example.com")
        assert "Access-Control-Allow-Origin" not in headers
    for path in ("/rpc", MOVE_PATH):
        status, _, _ = _req(receiver + path, "POST", rpc_body, origin="https://example.com",
                            headers={"Content-Type": "text/plain"})
        assert status == 403
    # This machine's pages (the server's own, npm run dev, a local static
    # site) keep every route; so do callers with no Origin (curl, tests).
    for origin in ("http://127.0.0.1:8420", "http://localhost:5173", "http://[::1]:8000"):
        status, headers, body = _req(receiver + "/rpc", "POST", rpc_body, origin=origin,
                                     headers={"Content-Type": "application/json"})
        assert status == 200 and headers.get("Access-Control-Allow-Origin") == origin and json.loads(body)["ok"]
    assert json.loads(_req(receiver + "/rpc", "POST", rpc_body)[2])["ok"]
