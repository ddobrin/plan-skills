#!/usr/bin/env python3
"""Cost and gate-decision log for a milestone: plans/active_milestones/{m}/usage.md.

Usage:
    usage.py log     --milestone M --phase P --agent A [--tokens N] [--tools N] [--ms N] [--note TEXT]
    usage.py decline --milestone M --gate G [--tier T] [--note TEXT]
    usage.py summary --milestone M

The supervisor calls `log` after every agent dispatch with the totals the
dispatch reported, and `decline` whenever the user declines an offered gate,
so skipped checks stay visible with the risk tier they were skipped at.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import swarmgit as sg  # noqa: E402

HEADER = ("# Usage log\n\nOne row per agent dispatch or gate decision. Written by the supervisor through "
          "`lib/usage.py`.\n\n| when (UTC) | phase | agent / gate | event | tokens | tool uses | "
          "duration (s) | tier | note |\n|---|---|---|---|---|---|---|---|---|\n")
COLUMNS = ("when", "phase", "who", "event", "tokens", "tools", "seconds", "tier", "note")


def path_for(root, moniker):
    return os.path.join(sg.milestone_dir(root, moniker), "usage.md")


def append(root, moniker, row):
    path = path_for(root, moniker)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fresh = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as fh:
        if fresh:
            fh.write(HEADER)
        fh.write("| " + " | ".join(str(row.get(c, "")).replace("|", "/") for c in COLUMNS) + " |\n")
    return path


def rows(root, moniker):
    out = []
    try:
        with open(path_for(root, moniker), encoding="utf-8") as fh:
            for line in fh:
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) == len(COLUMNS) and re.match(r"\d{4}-\d\d-\d\dT", cells[0]):
                    out.append(dict(zip(COLUMNS, cells)))
    except OSError:
        pass
    return out


def summary(root, moniker):
    rs = rows(root, moniker)
    num = lambda v: int(v) if str(v).isdigit() else 0  # noqa: E731
    dispatches = [r for r in rs if r["event"] == "dispatch"]
    return {
        "dispatches": len(dispatches),
        "tokens": sum(num(r["tokens"]) for r in dispatches),
        "tool_uses": sum(num(r["tools"]) for r in dispatches),
        "seconds": sum(num(r["seconds"]) for r in dispatches),
        "declined_gates": [f"{r['who']} ({r['tier'] or 'no tier'})" for r in rs if r["event"] == "declined"],
    }


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("log", "decline", "summary"))
    ap.add_argument("--milestone", required=True)
    ap.add_argument("--phase", default="")
    ap.add_argument("--agent", default="")
    ap.add_argument("--gate", default="")
    ap.add_argument("--tier", default="")
    ap.add_argument("--tokens", type=int)
    ap.add_argument("--tools", type=int)
    ap.add_argument("--ms", type=int)
    ap.add_argument("--note", default="")
    a = ap.parse_args(argv)
    if not re.fullmatch(sg.MONIKER, a.milestone):
        print(f"usage.py: invalid milestone {a.milestone!r}", file=sys.stderr)
        return 2
    root = sg.repo_root()
    if a.action == "summary":
        import json
        print(json.dumps(summary(root, a.milestone), indent=2))
        return 0
    tier = a.tier or sg.confirmed_tier(root, a.milestone)
    if a.action == "log":
        if not a.agent:
            print("usage.py: log needs --agent", file=sys.stderr)
            return 2
        row = {"phase": a.phase, "who": a.agent, "event": "dispatch",
               "tokens": "" if a.tokens is None else a.tokens, "tools": "" if a.tools is None else a.tools,
               "seconds": "" if a.ms is None else round(a.ms / 1000), "tier": tier, "note": a.note}
    else:
        if not a.gate:
            print("usage.py: decline needs --gate", file=sys.stderr)
            return 2
        row = {"phase": a.phase, "who": a.gate, "event": "declined", "tier": tier, "note": a.note}
    row["when"] = sg.iso(sg.now())
    print(append(root, a.milestone, row))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
