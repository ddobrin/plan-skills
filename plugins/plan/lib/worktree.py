#!/usr/bin/env python3
"""Per-task git worktrees for parallel engineers.

Usage:
    worktree.py create  --milestone M --task T     print the worktree path to dispatch into
    worktree.py squash  --milestone M              stage every task's work, no commit
    worktree.py cleanup --milestone M              remove worktrees and swarm-wip branches
    worktree.py list    --milestone M

Each task gets branch swarm-wip/{M}/{T} and a checkout under .swarm/worktrees/
(excluded through .git/info/exclude), both starting at the milestone checkout's
current HEAD. Engineers may make WIP commits there.

`squash` commits any uncommitted work in each worktree as WIP, then refuses to
integrate (exit 3, JSON report) when two tasks changed the same file or a task
changed plans/: both mean the plan's groups were wrong (Path B). Otherwise it
runs `git merge --squash` for each task, which stages the group's diff without
committing; the auditor audits it and the commit gate commits it.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import swarmgit as sg  # noqa: E402

TASK = r"[A-Za-z0-9][A-Za-z0-9._-]*"


def wt_root(root):
    return os.path.join(root, ".swarm", "worktrees")


def ensure_excluded(root):
    info = sg.git("rev-parse", "--git-path", "info/exclude", cwd=root)
    path = info if os.path.isabs(info) else os.path.join(root, info)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    if ".swarm/" not in existing.split():
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(("\n" if existing and not existing.endswith("\n") else "") + ".swarm/\n")


def task_branches(root, moniker):
    out = sg.git("for-each-ref", "--format=%(refname:short)", f"refs/heads/swarm-wip/{moniker}/", cwd=root)
    return [b for b in out.splitlines() if b]


def worktree_paths(root):
    paths, current = {}, None
    for line in sg.git("worktree", "list", "--porcelain", cwd=root).splitlines():
        if line.startswith("worktree "):
            current = line[9:]
        elif line.startswith("branch refs/heads/") and current:
            paths[line[len("branch refs/heads/"):]] = current
    return paths


def create(root, moniker, task):
    ensure_excluded(root)
    branch = sg.wip_branch(moniker, task)
    path = os.path.join(wt_root(root), moniker, task)
    if branch in worktree_paths(root):
        return {"task": task, "branch": branch, "path": worktree_paths(root)[branch], "created": False}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sg.git("worktree", "add", "-b", branch, path, "HEAD", cwd=root, check=True)
    return {"task": task, "branch": branch, "path": path, "created": True}


def squash(root, moniker):
    tracked_dirty = [p for p in sg.changed_paths(root, include_unstaged=True)
                     if not p.startswith("plans/") and not p.startswith(".swarm/")]
    if tracked_dirty:
        return 3, {"error": "milestone checkout has uncommitted non-plans changes", "paths": sorted(tracked_dirty)}
    paths = worktree_paths(root)
    touched, problems = {}, []
    for branch in task_branches(root, moniker):
        task = branch.rsplit("/", 1)[1]
        wt = paths.get(branch)
        if wt and sg.git("status", "--porcelain", cwd=wt):
            sg.git("add", "-A", cwd=wt, check=True)
            sg.git("commit", "-q", "-m", f"wip({moniker}): {task}", cwd=wt, check=True)
        files = [f for f in sg.git("diff", "--name-only", f"HEAD...{branch}", cwd=root).splitlines() if f]
        for f in files:
            touched.setdefault(f, []).append(task)
            if f.startswith("plans/"):
                problems.append(f"task {task} changed {f}; engineers must not edit plans/ in worktree mode")
    overlaps = {f: ts for f, ts in touched.items() if len(ts) > 1}
    if overlaps or problems:
        return 3, {"error": "cannot integrate: plan defect (Path B)", "overlapping_files": overlaps,
                   "violations": problems}
    squashed = []
    for branch in task_branches(root, moniker):
        sg.git("merge", "--squash", "--quiet", branch, cwd=root, check=True)
        squashed.append(branch.rsplit("/", 1)[1])
    return 0, {"squashed": squashed, "files": sorted(touched)}


def cleanup(root, moniker):
    removed = []
    paths = worktree_paths(root)
    for branch in task_branches(root, moniker):
        if branch in paths:
            sg.git("worktree", "remove", "--force", paths[branch], cwd=root)
        sg.git("branch", "-D", branch, cwd=root)
        removed.append(branch)
    sg.git("worktree", "prune", cwd=root)
    return {"removed": removed}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("create", "squash", "cleanup", "list"))
    ap.add_argument("--milestone", required=True)
    ap.add_argument("--task")
    a = ap.parse_args(argv)
    if not re.fullmatch(sg.MONIKER, a.milestone) or (a.task and not re.fullmatch(TASK, a.task)):
        print("worktree.py: invalid milestone or task id", file=sys.stderr)
        return 2
    root = sg.repo_root()
    code = 0
    try:
        if a.action == "create":
            if not a.task:
                print("worktree.py: create needs --task", file=sys.stderr)
                return 2
            out = create(root, a.milestone, a.task)
        elif a.action == "squash":
            code, out = squash(root, a.milestone)
        elif a.action == "cleanup":
            out = cleanup(root, a.milestone)
        else:
            paths = worktree_paths(root)
            out = {b: paths.get(b) for b in task_branches(root, a.milestone)}
    except RuntimeError as err:
        print(f"worktree.py: {err}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
