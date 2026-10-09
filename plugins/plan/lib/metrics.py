#!/usr/bin/env python3
"""AI-native SDLC indicators for plan-swarm milestones, from committed artifacts.

Usage:
    metrics.py [--milestone M] [--format json|text]

Per milestone:
    lead times   intent → spec → plan → first group commit → PR, from approvals.md
    groups       audited group commits approved
    rework       failed audit rounds (audit.md) and validator re-runs (-r2, -r3 …)
    first-pass   share of groups whose first audit round passed
    cost         dispatches, tokens, and declined gates from usage.md
Across the repo:
    intents      open (inbox), accepted (milestones), closed (plans/intents/closed/),
                 and survival = accepted / (accepted + closed)
"""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import swarmgit as sg  # noqa: E402
import usage  # noqa: E402

ROUND = re.compile(r"^###\s+Group\s+(\d+)\s*[·\-–—]\s*Round\s+(\d+)\s*[·\-–—:]\s*(PASS|FAIL)", re.I | re.M)


def hours(a, b):
    if not a or not b:
        return None
    return round((sg.parse_iso(b) - sg.parse_iso(a)).total_seconds() / 3600, 2)


def milestone_metrics(root, moniker):
    mdir = sg.milestone_dir(root, moniker)
    ledger = sg.read_ledger(root, moniker)
    first = {}
    for row in ledger:
        key = row["kind"] if row["kind"] != "commit" else "commit"
        first.setdefault(key, row["when"])
    commits = [r for r in ledger if r["kind"] == "commit"]
    try:
        audit = open(os.path.join(mdir, "audit.md"), encoding="utf-8").read()
    except OSError:
        audit = ""
    rounds = {}
    for g, r, verdict in ROUND.findall(audit):
        rounds.setdefault(int(g), []).append((int(r), verdict.upper()))
    groups = sorted(rounds)
    first_pass = [g for g in groups if min(rounds[g])[1] == "PASS"]
    failed_rounds = sum(1 for g in groups for _, v in rounds[g] if v == "FAIL")
    reruns = len(glob.glob(os.path.join(mdir, "adversarial-reviews", "*-r[0-9]*.md")) +
                 glob.glob(os.path.join(mdir, "deliberations", "*-r[0-9]*.md")))
    return {
        "milestone": moniker,
        "tier": sg.confirmed_tier(root, moniker) or None,
        "lead_time_hours": {
            "intent_to_spec": hours(first.get("intent"), first.get("spec")),
            "spec_to_plan": hours(first.get("spec"), first.get("plan")),
            "plan_to_first_commit": hours(first.get("plan"), first.get("commit")),
            "first_commit_to_pr": hours(first.get("commit"), first.get("pr")),
            "intent_to_pr": hours(first.get("intent"), first.get("pr")),
        },
        "groups_committed": len({r["group"] for r in commits}),
        "audit_rounds_failed": failed_rounds,
        "first_pass_audit_rate": round(len(first_pass) / len(groups), 2) if groups else None,
        "validator_reruns": reruns,
        "cost": usage.summary(root, moniker),
    }


def intent_metrics(root):
    inbox = [p for p in glob.glob(os.path.join(root, "plans", "intents", "*.md"))]
    closed = glob.glob(os.path.join(root, "plans", "intents", "closed", "*.md"))
    accepted = glob.glob(os.path.join(root, "plans", "active_milestones", "*", "intent.md"))
    decided = len(accepted) + len(closed)
    return {"open": len(inbox), "accepted": len(accepted), "closed": len(closed),
            "survival_rate": round(len(accepted) / decided, 2) if decided else None}


def collect(root, moniker=None):
    names = [moniker] if moniker else sorted(
        os.path.basename(d) for d in glob.glob(os.path.join(root, "plans", "active_milestones", "*")) if os.path.isdir(d))
    return {"intents": intent_metrics(root), "milestones": [milestone_metrics(root, m) for m in names]}


def as_text(data):
    i = data["intents"]
    lines = [f"Intents: {i['open']} open · {i['accepted']} accepted · {i['closed']} closed · survival "
             f"{'n/a' if i['survival_rate'] is None else i['survival_rate']}", ""]
    for m in data["milestones"]:
        lt = m["lead_time_hours"]
        fmt = lambda v: "·" if v is None else f"{v}h"  # noqa: E731
        lines += [f"{m['milestone']} (tier {m['tier'] or 'unconfirmed'})",
                  f"  lead time  intent→spec {fmt(lt['intent_to_spec'])} · spec→plan {fmt(lt['spec_to_plan'])} · "
                  f"plan→commit {fmt(lt['plan_to_first_commit'])} · commit→PR {fmt(lt['first_commit_to_pr'])}",
                  f"  quality    {m['groups_committed']} groups · first-pass audit "
                  f"{'·' if m['first_pass_audit_rate'] is None else m['first_pass_audit_rate']} · "
                  f"{m['audit_rounds_failed']} failed rounds · {m['validator_reruns']} validator re-runs",
                  f"  cost       {m['cost']['dispatches']} dispatches · {m['cost']['tokens']} tokens · declined: "
                  f"{', '.join(m['cost']['declined_gates']) or 'none'}", ""]
    return "\n".join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--milestone")
    ap.add_argument("--format", choices=("json", "text"), default="text")
    a = ap.parse_args(argv)
    data = collect(sg.repo_root(), a.milestone)
    print(json.dumps(data, indent=2) if a.format == "json" else as_text(data))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
