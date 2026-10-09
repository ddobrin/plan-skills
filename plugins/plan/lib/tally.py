#!/usr/bin/env python3
"""Count skeptic votes for the spec, plan, and implementation validators.

Usage:
    tally.py [--gate N] s1.json s2.json s3.json

Each file holds one skeptic's final verdict: the JSON object from its fenced block
(a surrounding ```json fence is tolerated). The gate defaults to 2.

Finding mode (verdicts with a top-level "findings" array):
    Findings are grouped by their stable "id", and by "file" when the finding
    carries one, so the same slug in two files counts as two defects. A skeptic
    votes for a finding when it reports that id at least once with isReal not set
    to false. Findings at or above
    the gate are confirmed; one vote below it (or more, with a gate of 3) is
    unconfirmed; ids every reporting skeptic marked isReal=false are rejected.
    Severity is the most common correctedSeverity/severity among the votes, and a
    tie goes to the higher level; severity_votes lists each vote's rating. Plan
    verdicts' top-level first_domino ids are counted into first_domino_votes.

Claim-refutation mode (verdicts with a top-level "claim", or a list of them):
    Verdicts are grouped by claim text. A claim fails when refuted=true reaches the
    gate, survives when refuted=false reaches it, and is unconfirmed otherwise.

Prints one JSON object on stdout. Exits 2 on unreadable input.
"""
import collections
import json
import re
import sys

RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def load(path):
    text = open(path, encoding="utf-8").read().strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    return json.loads(text)


def majority(values):
    counts = collections.Counter(v for v in values if v)
    if not counts:
        return None
    best = max(counts.values())
    tied = [v for v, n in counts.items() if n == best]
    return max(tied, key=lambda v: RANK.get(str(v).lower(), 0))


def tally_findings(verdicts, gate):
    reports = collections.defaultdict(list)  # (file, id) -> [(skeptic index, finding)]
    for index, verdict in enumerate(verdicts):
        for finding in verdict.get("findings", []):
            ident = finding.get("id") or finding.get("clause") or finding.get("title")
            if ident:
                reports[(finding.get("file") or "", ident)].append((index, finding))

    result = {"confirmed": [], "unconfirmed": [], "rejected": []}
    for (_path, ident), entries in reports.items():
        real = [f for _, f in entries if f.get("isReal", True) is not False]
        voters = {i for i, f in entries if f.get("isReal", True) is not False}
        entry = dict(real[0] if real else entries[0][1])
        entry["id"] = ident
        entry["votes"] = len(voters)
        entry["reported_by"] = sorted({i + 1 for i, _ in entries})
        entry["severity"] = majority(f.get("correctedSeverity") or f.get("severity") for f in real)
        entry["severity_votes"] = [f.get("correctedSeverity") or f.get("severity") for f in real]
        if not voters:
            result["rejected"].append(entry)
        elif len(voters) >= gate:
            result["confirmed"].append(entry)
        else:
            result["unconfirmed"].append(entry)

    for bucket in result.values():
        bucket.sort(key=lambda e: (-e["votes"], -RANK.get(str(e["severity"]).lower(), 0)))
    dominoes = collections.Counter(
        v.get("first_domino") for v in verdicts if isinstance(v, dict) and v.get("first_domino"))
    if dominoes:
        result["first_domino_votes"] = dict(dominoes.most_common())
    return result


def tally_claims(verdicts, gate):
    by_claim = collections.defaultdict(list)
    for verdict in verdicts:
        for item in verdict if isinstance(verdict, list) else [verdict]:
            by_claim[item.get("claim", "").strip()].append(item)

    result = {"failed_claims": [], "surviving_claims": [], "unconfirmed": []}
    for claim, items in by_claim.items():
        refuting = [i for i in items if i.get("refuted") is True]
        holding = [i for i in items if i.get("refuted") is False]
        entry = {
            "claim": claim,
            "refuted_by": len(refuting),
            "held_by": len(holding),
            "severity": majority(i.get("correctedSeverity") for i in refuting),
            "attacks": [i.get("attack") for i in refuting or holding],
        }
        if len(refuting) >= gate:
            result["failed_claims"].append(entry)
        elif len(holding) >= gate:
            result["surviving_claims"].append(entry)
        else:
            result["unconfirmed"].append(entry)
    return result


def main(argv):
    gate, paths = 2, []
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--gate":
            gate = int(args.pop(0))
        else:
            paths.append(arg)
    if not paths:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        verdicts = [load(p) for p in paths]
    except (OSError, ValueError) as err:
        print(f"tally.py: cannot read verdict: {err}", file=sys.stderr)
        return 2

    claim_mode = all(
        isinstance(v, list) or (isinstance(v, dict) and "claim" in v and "findings" not in v)
        for v in verdicts
    )
    result = tally_claims(verdicts, gate) if claim_mode else tally_findings(verdicts, gate)
    result = {"mode": "claim-refutation" if claim_mode else "finding", "gate": gate,
              "skeptics": len(verdicts), **result}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
