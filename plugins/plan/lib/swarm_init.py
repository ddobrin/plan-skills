#!/usr/bin/env python3
"""Install plan-swarm project templates into a repository (used by the swarm-init skill).

Usage:
    swarm_init.py [--dry-run] [--only NAME[,NAME...]] [--root DIR]

Names: swarm, hook, review, ci, agents. Default: all of them. `hook` installs
the pre-commit, pre-merge-commit, and pre-push hooks.

Never overwrites an existing file. An existing git hook that is not a
plan-swarm hook is left alone and reported, with the line to add to chain it.
Installing marks the repository as plan-swarm managed (.git/plan-swarm/active).
Prints one line per template: installed, exists, would install, or skipped.
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health  # noqa: E402
import swarmgit as sg  # noqa: E402

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
ITEMS = [
    ("swarm", "swarm.md", os.path.join("plans", "swarm.md")),
    ("hook:pre-commit", os.path.join("git-hooks", "pre-commit"), None),
    ("hook:pre-merge-commit", os.path.join("git-hooks", "pre-merge-commit"), None),
    ("hook:pre-push", os.path.join("git-hooks", "pre-push"), None),
    ("review", "REVIEW.md", "REVIEW.md"),
    ("ci", os.path.join("ci", "plan-swarm.yml"), os.path.join(".github", "workflows", "plan-swarm.yml")),
    ("agents", "AGENTS.md", "AGENTS.md"),
]
ALIASES = {"claude": "agents", "gemini": "agents"}  # older / alternative names of the item


def agents_md_state(root):
    """Why AGENTS.md is not installed, or None to install it.

    Antigravity loads both AGENTS.md and GEMINI.md as project rules, and the
    roles read whichever the project uses, so an existing GEMINI.md is kept as is."""
    if os.path.exists(os.path.join(root, "AGENTS.md")):
        return "AGENTS.md"
    if os.path.exists(os.path.join(root, "GEMINI.md")):
        return "GEMINI.md (the swarm reads it; no AGENTS.md added)"
    return None


def install(root, only=None, dry_run=False):
    results = []
    only = {ALIASES.get(o, o) for o in only} if only else None
    for name, src_rel, dest_rel in ITEMS:
        group = name.split(":")[0]
        hook = name.split(":")[1] if ":" in name else None
        if only and group not in only:
            continue
        src = os.path.join(TEMPLATES, src_rel)
        if not os.path.exists(src):
            results.append((name, "skipped", f"template {src_rel} not shipped"))
            continue
        dest = health.hook_path(root, hook) if hook else os.path.join(root, dest_rel)
        shown = os.path.relpath(dest, root)
        if name == "agents" and agents_md_state(root):
            results.append((name, "exists", agents_md_state(root)))
            continue
        if os.path.exists(dest):
            if hook and not health.git_hook_installed(root, hook):
                mode = '--pre-push "$@"' if hook == "pre-push" else "--git-hook"
                chain = f'python3 "$(git rev-parse --git-common-dir)/plan-swarm/bin/gate.py" {mode} || exit 1'
                results.append((name, "exists", f"{shown} is another tool's hook; add this line to it: {chain}"))
            else:
                results.append((name, "exists", shown))
            continue
        if dry_run:
            results.append((name, "would install", shown))
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)
        if hook:
            os.chmod(dest, 0o755)
        results.append((name, "installed", shown))
    if not dry_run:
        store = sg.store_dir(root)
        if store:
            if not only or "hook" in only:
                health.refresh_bin(root, store)
            if os.path.exists(os.path.join(root, "plans", "swarm.md")):
                sg.mark_active(store)
    return results


def main(argv):
    dry_run = "--dry-run" in argv
    only, root = None, None
    if "--only" in argv:
        only = set(argv[argv.index("--only") + 1].split(","))
    if "--root" in argv:
        root = argv[argv.index("--root") + 1]
    root = sg.repo_root(root)
    if not sg.git("rev-parse", "--git-dir", cwd=root):
        print("swarm_init.py: not a git repository", file=sys.stderr)
        return 2
    for name, state, detail in install(root, only, dry_run):
        print(f"{state:>13}  {name:<7} {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
