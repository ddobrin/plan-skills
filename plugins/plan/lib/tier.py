#!/usr/bin/env python3
"""Deterministic risk-tier classifier for a milestone.

Usage:
    tier.py --milestone M --stage intent|plan|diff [--write] [--intent-file PATH]

Rules come from plans/swarm.md `tiers`: a milestone is `critical` if any
critical rule matches, else `elevated` if any elevated rule matches, else
`routine`. Inputs grow with the stage:

    intent  keywords in the intent text
    plan    + keywords in spec.md and plan.md, + file paths named in plan.md
    diff    + paths and changed-line count of the milestone diff against the default branch

The tier only rises: the result is the highest of the computed tier, the tier
already proposed in intent.md / plan.md, and the tier confirmed in approvals.md.
--write records the proposal as a `Risk tier (proposed)` line in plan.md (plan,
diff) or intent.md (intent). Prints JSON: tier, reasons, previous, raised.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import swarmdoc  # noqa: E402
import swarmgit as sg  # noqa: E402

RANK = {t: i for i, t in enumerate(swarmdoc.TIERS)}
LINE = re.compile(r"^\**Risk tier \(proposed\)\W*(routine|elevated|critical)\b.*$", re.I | re.M)
PATH = re.compile(r"`([A-Za-z0-9_.\-/]+\.[A-Za-z0-9]+|[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-/]+)`")


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def keyword_hits(text, keywords):
    low = text.lower()
    return [k for k in keywords if re.search(r"(?<![a-z0-9])" + re.escape(k.lower()) + r"(?![a-z0-9])", low)]


def classify(cfg, text, paths, diff_lines=None):
    reasons = {"critical": [], "elevated": []}
    for tier in ("critical", "elevated"):
        rule = cfg["tiers"].get(tier)
        if not rule:
            continue
        for k in keyword_hits(text, rule["keywords"]):
            reasons[tier].append(f"keyword '{k}'")
        for pattern in rule["paths"]:
            hit = next((p for p in sorted(paths) if swarmdoc.path_matches(p, pattern)), None)
            if hit:
                reasons[tier].append(f"path {hit} matches {pattern}")
        if diff_lines is not None and "diff_lines_over" in rule and diff_lines > rule["diff_lines_over"]:
            reasons[tier].append(f"{diff_lines} changed lines > {rule['diff_lines_over']}")
    for tier in ("critical", "elevated"):
        if reasons[tier]:
            return tier, reasons[tier]
    return "routine", []


def plan_paths(plan_text):
    return {m.group(1).lstrip("./") for m in PATH.finditer(plan_text) if not m.group(1).startswith("plans/")}


def diff_stats(root):
    base = ""
    for ref in ("origin/HEAD", "origin/main", "main", "origin/master", "master"):
        base = sg.git("merge-base", "HEAD", ref, cwd=root)
        if base:
            break
    if not base:
        return set(), 0
    names = set(filter(None, sg.git("diff", "--name-only", f"{base}...HEAD", cwd=root).splitlines()))
    stat = sg.git("diff", "--shortstat", f"{base}...HEAD", cwd=root)
    lines = sum(int(n) for n in re.findall(r"(\d+) (?:insertion|deletion)", stat))
    return {n for n in names if not n.startswith("plans/")}, lines


def evaluate(root, moniker, stage, intent_file=None):
    cfg = swarmdoc.load_config(root)
    mdir = sg.milestone_dir(root, moniker)
    intent_path = intent_file or os.path.join(mdir, "intent.md")
    text = read(intent_path)
    paths, lines = set(), None
    if stage in ("plan", "diff"):
        plan = read(os.path.join(mdir, "plan.md"))
        text += "\n" + read(os.path.join(mdir, "spec.md")) + "\n" + plan
        paths |= plan_paths(plan)
    if stage == "diff":
        dpaths, lines = diff_stats(root)
        paths |= dpaths
    tier, reasons = classify(cfg, text, paths, lines)

    previous = "routine"
    for name in (intent_path, os.path.join(mdir, "plan.md")):
        m = LINE.search(read(name))
        if m and RANK[m.group(1).lower()] > RANK[previous]:
            previous = m.group(1).lower()
    confirmed = sg.confirmed_tier(root, moniker)
    if confirmed and RANK[confirmed] > RANK[previous]:
        previous = confirmed
    if RANK[previous] > RANK[tier]:
        tier, reasons = previous, [f"kept at {previous} (tiers never fall automatically)"]
    return {"tier": tier, "reasons": reasons, "previous": previous,
            "confirmed": confirmed or None, "raised": RANK[tier] > RANK[previous],
            "exceeds_confirmed": bool(confirmed) and RANK[tier] > RANK[confirmed],
            "intent_path": intent_path}


def write_line(path, result):
    text = read(path)
    why = "; ".join(result["reasons"]) or "no rule matched"
    line = f"**Risk tier (proposed):** `{result['tier']}` ({why})"
    if LINE.search(text):
        text = LINE.sub(line, text, count=1)
    else:
        lines = text.splitlines(keepends=True)
        at = next((i + 1 for i, l in enumerate(lines) if l.startswith("# ")), 0)
        lines.insert(at, "\n" + line + "\n")
        text = "".join(lines)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--milestone", required=True)
    ap.add_argument("--stage", required=True, choices=("intent", "plan", "diff"))
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--intent-file")
    a = ap.parse_args(argv)
    root = sg.repo_root()
    try:
        result = evaluate(root, a.milestone, a.stage, a.intent_file)
    except swarmdoc.SwarmDocError as err:
        print(f"tier.py: {err}", file=sys.stderr)
        return 2
    if a.write:
        target = result["intent_path"] if a.stage == "intent" else os.path.join(sg.milestone_dir(root, a.milestone), "plan.md")
        if os.path.exists(target):
            write_line(target, result)
    result.pop("intent_path")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
