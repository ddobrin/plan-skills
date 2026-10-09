#!/usr/bin/env python3
"""Enforcement status for the plan-swarm control plane, and the session announcement.

    health.py --status   print enforcement status; exit 0 when active, 1 when not

Antigravity has no session-start hook that plan-swarm relies on, so lib/approve.py
(the PreInvocation hook) calls announce() once per conversation: it marks the
repository active, refreshes the git hooks' copy of the gate, and returns the
message the session sees, including PLAN_LIB, the absolute path of these scripts.

Every plan-swarm hook refreshes the heartbeat in .git/plan-swarm/heartbeat.json.
Running `--status` through Antigravity's run_command fires the PreToolUse gate first,
so a fresh heartbeat proves the hooks are firing in this session. If the
plugin's hooks are disabled (plugin turned off, or hooks blocked by policy), the
heartbeat goes stale and the supervisor refuses gated steps. Roles call this as
`python3 "$PLAN_LIB/health.py" --status`; the gate expands $PLAN_LIB, so when
the hooks are not running the command fails outright, which is also a signal.
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import antigravity  # noqa: E402
import swarmdoc  # noqa: E402
import swarmgit as sg  # noqa: E402

LIB = os.path.dirname(os.path.abspath(__file__))
HOOK_MARKER = "plan-swarm git hook"
BIN_FILES = ("gate.py", "swarmdoc.py", "swarmgit.py", "antigravity.py", "approve.py")
HOOK_NAMES = ("pre-commit", "pre-merge-commit", "pre-push")


def plugin_version():
    try:
        with open(os.path.join(os.path.dirname(LIB), "plugin.json"), encoding="utf-8") as fh:
            return json.load(fh).get("version", "unknown")
    except (OSError, ValueError):
        return "unknown"


def hook_path(root, name="pre-commit"):
    path = sg.git("rev-parse", "--git-path", f"hooks/{name}", cwd=root)
    return os.path.join(root, path) if path and not os.path.isabs(path) else path


def git_hook_installed(root, name="pre-commit"):
    try:
        with open(hook_path(root, name), encoding="utf-8") as fh:
            return HOOK_MARKER in fh.read()
    except OSError:
        return False


def refresh_bin(root, store):
    """Copy the gate into the store so the git hooks run the current version."""
    dest = os.path.join(store, "bin")
    os.makedirs(dest, exist_ok=True)
    for name in BIN_FILES:
        shutil.copyfile(os.path.join(LIB, name), os.path.join(dest, name))


def status(root):
    info = {"swarm_repo": os.path.exists(os.path.join(root, swarmdoc.CONFIG_PATH)), "plan_lib": LIB}
    if not info["swarm_repo"]:
        info["message"] = "not a plan-swarm repository (no plans/swarm.md); run the swarm-init skill"
        return info, False
    try:
        cfg = swarmdoc.load_config(root)
        info.update(config="valid", mode=cfg["delivery"]["mode"],
                    max_engineers=cfg["engineers"]["max_concurrent"],
                    max_path_a_rounds=cfg["audit"]["max_path_a_rounds"])
    except swarmdoc.SwarmDocError as err:
        info.update(config=f"INVALID: {err}")
    store = sg.store_dir(root)
    age = sg.age_seconds((sg.heartbeat(store) or {}).get("updated"))
    missing = [n for n in HOOK_NAMES if not git_hook_installed(root, n)]
    info.update(heartbeat_age_seconds=None if age is None else int(age),
                git_hook="installed" if not missing else "missing: " + ", ".join(missing),
                plugin_version=plugin_version())
    active = age is not None and age <= sg.HEARTBEAT_FRESH_SECONDS and info["config"] == "valid"
    info["enforcement"] = "active" if active else "OFF"
    if not active:
        info["message"] = ("enforcement off: plan-swarm hooks are not firing (the plan plugin or its "
                           "hooks may be disabled) or plans/swarm.md is invalid. Do not run gated steps.")
    return info, active


def announce(event, root):
    """Once per conversation in a plan-swarm repository: the message the session sees."""
    if not os.path.exists(os.path.join(root, swarmdoc.CONFIG_PATH)):
        return None
    store = sg.store_dir(root)
    sg.mark_active(store)
    sg.touch_heartbeat(store, started=sg.iso(sg.now()), conversation=event.get("conversationId", ""),
                       plugin_version=plugin_version())
    if any(git_hook_installed(root, n) for n in HOOK_NAMES):
        refresh_bin(root, store)
    info, _active = status(root)
    lib_note = f" PLAN_LIB={LIB} (write it as \"$PLAN_LIB\" in commands; the gate expands it)."
    if info.get("config") != "valid":
        return f"plan-swarm: plans/swarm.md is {info['config']}. Gated operations are refused until it is fixed.{lib_note}"
    if antigravity.is_subagent(event):
        return (f"plan-swarm {info['plugin_version']}: enforcement active in this repository. Commits, pushes, "
                f"and tags need a human approval phrase; only the auditor commits.{lib_note}")
    hook = "" if info["git_hook"] == "installed" else f" Git hooks {info['git_hook']}; run the swarm-init skill."
    return (f"plan-swarm {info['plugin_version']}: enforcement active. Delivery mode {info['mode']}, "
            f"up to {info['max_engineers']} engineers, Path A capped at {info['max_path_a_rounds']} rounds. "
            f"Commits, pushes, and tags need an exact approval phrase typed by the user in this "
            f"conversation.{hook}{lib_note}")


def main(argv):
    if "--status" in argv:
        info, active = status(sg.repo_root())
        print(json.dumps(info, indent=2))
        return 0 if active else 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
