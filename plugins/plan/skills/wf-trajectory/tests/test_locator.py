import json
import os
import pytest

import wf_locator as L


def _enc(path):
    # Independent reimplementation of Claude Code's on-disk encoding:
    # every non-alphanumeric char -> '-'. Deliberately NOT wf_locator.encode_path,
    # so these fixtures would catch a regression in that function.
    return "".join(ch if ch.isalnum() else "-" for ch in os.path.abspath(path))


def _write_run(root, project_path, session, run_id, timestamp):
    enc = _enc(project_path)
    wdir = os.path.join(root, "projects", enc, session, "workflows")
    os.makedirs(wdir, exist_ok=True)
    path = os.path.join(wdir, f"{run_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"runId": run_id, "timestamp": timestamp}, f)
    return path


def test_find_project_dir_longest_ancestor(tmp_path, monkeypatch):
    root = tmp_path / "claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(root))
    project = tmp_path / "work" / "proj"
    subdir = project / "src" / "deep"
    subdir.mkdir(parents=True)
    # Register BOTH the deep project AND a competing shorter ancestor.
    # A correct longest-ancestor walk must return the deeper `project`,
    # not the shorter `tmp_path/work`; this makes the test falsify a
    # broken shortest-ancestor implementation.
    shorter = tmp_path / "work"
    _write_run(str(root), str(project), "sessA", "wf_aaa", "2026-01-01T00:00:00Z")
    _write_run(str(root), str(shorter), "sessB", "wf_bbb", "2026-01-01T00:00:00Z")
    found = L.find_project_dir(str(subdir))
    assert found == os.path.join(str(root), "projects", _enc(str(project)))


def test_find_latest_run_by_timestamp(tmp_path, monkeypatch):
    root = tmp_path / "claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(root))
    project = tmp_path / "work" / "proj"
    project.mkdir(parents=True)
    _write_run(str(root), str(project), "s1", "wf_old", "2026-01-01T00:00:00Z")
    _write_run(str(root), str(project), "s2", "wf_new", "2026-06-01T00:00:00Z")
    pdir = L.find_project_dir(str(project))
    latest = L.find_latest_run(pdir)
    assert os.path.basename(latest) == "wf_new.json"


def test_locate_run_unknown_id_lists_available(tmp_path, monkeypatch):
    root = tmp_path / "claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(root))
    project = tmp_path / "work" / "proj"
    project.mkdir(parents=True)
    _write_run(str(root), str(project), "s1", "wf_real", "2026-01-01T00:00:00Z")
    with pytest.raises(L.LocatorError) as ei:
        L.locate_run(str(project), "wf_missing")
    assert "wf_real" in str(ei.value)


def test_locate_run_no_project(tmp_path, monkeypatch):
    root = tmp_path / "claude"
    (root / "projects").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(root))
    with pytest.raises(L.LocatorError):
        L.locate_run(str(tmp_path / "nowhere"))


def test_encode_path_matches_ground_truth_encoding(tmp_path, monkeypatch):
    # Ground truth (verified against ~/.claude/projects): EVERY non-alphanumeric
    # char in the launch path is replaced by '-'. A launch path containing '.' or
    # '_' must still resolve. The seed dir is named via _enc (independent of
    # wf_locator.encode_path), so a '/'-only regression in encode_path is caught.
    root = tmp_path / "claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(root))
    project = tmp_path / "work" / "my.proj_v2"
    project.mkdir(parents=True)
    _write_run(str(root), str(project), "sessX", "wf_dot", "2026-01-01T00:00:00Z")
    found = L.find_project_dir(str(project))
    assert found == os.path.join(str(root), "projects", _enc(str(project)))
    enc = L.encode_path(str(project))
    assert ".proj_v2" not in enc
    assert enc.endswith("my-proj-v2")


def test_locate_run_by_id_global_fallback_without_project(tmp_path, monkeypatch):
    # design §5: an explicit runId resolves via a global scan even when cwd is
    # not inside any registered project directory.
    root = tmp_path / "claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(root))
    other = tmp_path / "work" / "other"
    _write_run(str(root), str(other), "s1", "wf_global", "2026-01-01T00:00:00Z")
    nowhere = tmp_path / "elsewhere"
    nowhere.mkdir()
    path = L.locate_run(str(nowhere), "wf_global")
    assert os.path.basename(path) == "wf_global.json"
