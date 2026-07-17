import json
import os
import subprocess
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(SKILL_DIR, "generator.py")
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "wf_c8873586-bae.json")


def _seed(tmp_path):
    """Create a fake ~/.claude with the fixture under the project's encoded dir."""
    root = tmp_path / "claude"
    project = tmp_path / "work" / "proj"
    project.mkdir(parents=True)
    enc = str(project).replace(os.sep, "-")
    wdir = root / "projects" / enc / "sessX" / "workflows"
    wdir.mkdir(parents=True)
    with open(FIXTURE, "r", encoding="utf-8") as f:
        data = f.read()
    (wdir / "wf_c8873586-bae.json").write_text(data, encoding="utf-8")
    return root, project


def _run(cwd, root, *args):
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(root))
    return subprocess.run([sys.executable, GEN, *args], cwd=str(cwd), env=env,
                          capture_output=True, text=True)


def test_generates_html_and_gitignore(tmp_path):
    root, project = _seed(tmp_path)
    r = _run(project, root)
    assert r.returncode == 0, r.stderr
    out = project / "wf-trajectory" / "wf_c8873586-bae.html"
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "proofread-pr6408-review" in html
    assert "class=\"trow\"" in html
    gi = (project / ".gitignore").read_text(encoding="utf-8")
    assert "wf-trajectory/" in gi.split()


def test_unknown_runid_exits_2(tmp_path):
    root, project = _seed(tmp_path)
    r = _run(project, root, "wf_does_not_exist")
    assert r.returncode == 2
    assert "wf_c8873586-bae" in r.stderr  # lists available runs


def test_malformed_run_exits_2_with_path(tmp_path):
    root = tmp_path / "claude"
    project = tmp_path / "work" / "proj"
    project.mkdir(parents=True)
    enc = str(project).replace(os.sep, "-")
    wdir = root / "projects" / enc / "sessX" / "workflows"
    wdir.mkdir(parents=True)
    (wdir / "wf_broken.json").write_text('{ "runId": "wf_broken", truncated', encoding="utf-8")
    r = _run(project, root)
    assert r.returncode == 2, r.stderr
    assert "wf_broken.json" in r.stderr
