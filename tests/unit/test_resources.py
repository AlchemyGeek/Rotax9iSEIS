"""
Spec 04 v0.8 §9.7 (D7): one lookup rule for the engine's runtime files —
the repo root in a developer checkout, the wheel's packaged copies
elsewhere — and the built UI likewise.
"""
import subprocess
import sys
import zipfile
from pathlib import Path

from slingology_eis import resources

REPO = Path(__file__).resolve().parents[2]


def test_a_checkout_reads_the_repo_root():
    assert resources.is_checkout()
    assert resources.resource("engines") == REPO / "engines"
    assert resources.resource("insight_rules.json") == REPO / "insight_rules.json"


def test_elsewhere_the_packaged_copies(tmp_path):
    data, web = tmp_path / "_data", tmp_path / "_web"
    (data / "engines").mkdir(parents=True)
    (web / "index.html").parent.mkdir()
    (web / "index.html").write_text("<html></html>")
    not_a_checkout = tmp_path / "site-packages"
    not_a_checkout.mkdir()
    assert resources.resource("engines", root=not_a_checkout, data=data) == data / "engines"
    assert resources.web_dist(root=not_a_checkout, web=web) == web
    assert resources.web_dist(root=not_a_checkout, web=tmp_path / "none") is None


def test_the_built_wheel_runs_from_its_package_data(tmp_path):
    """The wheel unpacked outside the checkout: engine profiles, rules,
    presets, config, register and help all load from the package."""
    subprocess.run([sys.executable, str(REPO / "scripts" / "build_engine_wheel.py"), "--out", str(tmp_path / "w")],
                   check=True, capture_output=True)
    wheel = next((tmp_path / "w").glob("*.whl"))
    site = tmp_path / "site"
    zipfile.ZipFile(wheel).extractall(site)
    names = zipfile.ZipFile(wheel).namelist()
    for rel in ("engines/916iS.json", "insight_rules.json", "chart_presets.json", "config.json",
                "docs/specs/topics/register.json"):
        assert f"slingology_eis/_data/{rel}" in names, rel
    assert "slingology_eis/help/topics.md" in names
    assert not [n for n in names if not n.startswith(("slingology_eis/", "slingology_eis-"))]   # nothing at top level
    probe = (
        "from slingology_eis import resources, limits, help, host\n"
        "assert not resources.is_checkout(), resources.CHECKOUT_ROOT\n"
        "assert '_data' in str(limits._ENGINES_DIR)\n"
        "cfg = limits.load_engine_config('916iS')\n"
        "assert cfg and host._DEFAULT_RULES_PATH.is_file() and host._CHART_PRESETS_PATH.is_file()\n"
        "assert help._REGISTER_PATH.is_file()\n"
        "print('ok')\n"
    )
    r = subprocess.run([sys.executable, "-c", probe], cwd=tmp_path, capture_output=True, text=True,
                       env={"PYTHONPATH": str(site), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr


def test_serve_starts_on_a_fresh_install_with_no_logs_folder_or_workspace(tmp_path, monkeypatch):
    """BACKLOG P3 / Spec 04 step 5: outside a checkout, with no --logs and
    no workspace yet, the server starts and stays in its data root — it
    used to stop with "No --logs given … not running from a git checkout"."""
    from slingology_eis import cli, data_location, host, server
    home = tmp_path / "SlingologyEIS"
    monkeypatch.setattr(data_location, "_PACKAGED_HOME", home)
    monkeypatch.setattr(data_location, "_is_git_checkout", lambda p: False)
    monkeypatch.setattr(cli, "_PACKAGED_HOME", home)
    monkeypatch.setattr(cli, "_is_git_checkout", lambda p: False)
    monkeypatch.setattr(host, "is_checkout", lambda: False)
    httpd = server.build_server(logs_dir=None, workspace_dir=None, port=0, quiet=True)
    try:
        assert httpd.slingology_workspace_dir == home                 # the data root, not a checkout's data/
    finally:
        httpd.server_close()
