"""Locate the wf_<runId>.json run record for the current project."""
from __future__ import annotations

import glob
import json
import os
import re


class LocatorError(Exception):
    pass


def _claude_root() -> str:
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def _projects_dir() -> str:
    return os.path.join(_claude_root(), "projects")


def encode_path(p: str) -> str:
    # Claude Code encodes the launch dir by replacing EVERY non-alphanumeric
    # character with '-' (verified against ~/.claude/projects; e.g. a dotted path
    # /Users/x/.claude -> -Users-x--claude). Not a '/'-only replacement — each
    # separator maps individually and consecutive separators are not collapsed.
    return re.sub(r"[^a-zA-Z0-9]", "-", os.path.abspath(p))


def find_project_dir(cwd: str, projects: str | None = None):
    projects = projects or _projects_dir()
    p = os.path.abspath(cwd)
    while True:
        cand = os.path.join(projects, encode_path(p))
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


def _run_timestamp(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("timestamp", "")
    except Exception:
        return ""


def find_latest_run(project_dir: str):
    cands = glob.glob(os.path.join(project_dir, "*", "workflows", "wf_*.json"))
    if not cands:
        return None
    cands.sort(key=lambda p: (_run_timestamp(p), os.path.getmtime(p)))
    return cands[-1]


def find_run_by_id(project_dir: str | None, run_id: str, projects: str | None = None):
    if project_dir is not None:
        hits = glob.glob(os.path.join(project_dir, "*", "workflows", f"{run_id}.json"))
        if hits:
            return hits[0]
    # design §5: global fallback so an explicit runId resolves from anywhere,
    # including a cwd that is not inside any registered project.
    projects = projects or _projects_dir()
    hits = glob.glob(os.path.join(projects, "*", "*", "workflows", f"{run_id}.json"))
    return hits[0] if hits else None


def available_run_ids(project_dir: str) -> list:
    cands = glob.glob(os.path.join(project_dir, "*", "workflows", "wf_*.json"))
    return sorted({os.path.splitext(os.path.basename(c))[0] for c in cands})


def locate_run(cwd: str, run_id: str | None = None) -> str:
    project_dir = find_project_dir(cwd)
    if run_id:
        # design §5: try the resolved project first, then a global scan — this
        # must run even when no project dir matches the cwd.
        path = find_run_by_id(project_dir, run_id)
        if path is None:
            avail = ", ".join(available_run_ids(project_dir)) if project_dir else "(none)"
            raise LocatorError(f"Run '{run_id}' not found. Available runs: {avail}")
        return path
    if project_dir is None:
        raise LocatorError(
            f"No Claude project directory found for {os.path.abspath(cwd)} under {_projects_dir()}."
        )
    path = find_latest_run(project_dir)
    if path is None:
        raise LocatorError(f"No workflow runs found under {project_dir}.")
    return path
