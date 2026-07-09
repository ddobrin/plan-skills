import os
import re
import datetime

# Matches .../plans/active_milestones/{moniker}/... anywhere in the artifact path,
# keeping the prefix so the report lands next to the artifact rather than in CWD.
MILESTONE_RE = re.compile(r'^(.*?)(plans/active_milestones/([^/]+))/')

SEVERITY_ICONS = {"high": "🔴", "medium": "🟠", "low": "🟡"}
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

# Per-stage rendering of a finding: (label, key, render-as-quote)
FINDING_FIELDS = {
    "spec": (
        ("Clause", "clause", True),
        ("Malicious reading", "interpretation", False),
        ("Harm", "harm", False),
        ("Tightening", "tightening", False),
    ),
    "plan": (
        ("Step", "step", False),
        ("Failure", "failure", False),
        ("Evidence", "evidence", True),
        ("Fix", "fix", False),
    ),
}


def resolve_report_path(file_path: str, stage, moniker_override: str = None) -> tuple:
    """Resolves the report output path and milestone moniker for a validated artifact.

    The moniker is derived from a plans/active_milestones/{moniker}/ segment in the
    artifact path (report goes to its adversarial-reviews/ sibling), can be forced
    with moniker_override (resolved relative to CWD), and falls back to
    plans/adversarial-reviews/ for bare artifacts. Existing reports are never
    overwritten: re-runs get -r2, -r3, ... suffixes.
    """
    moniker = None
    if moniker_override:
        moniker = moniker_override
        out_dir = os.path.join("plans", "active_milestones", moniker_override, "adversarial-reviews")
    else:
        normalized = file_path.replace(os.sep, "/")
        match = MILESTONE_RE.match(normalized)
        if match:
            moniker = match.group(3)
            out_dir = os.path.join(match.group(1) + match.group(2), "adversarial-reviews")
        else:
            out_dir = os.path.join("plans", "adversarial-reviews")

    candidate = os.path.join(out_dir, f"{stage.report_basename}.md")
    suffix = 2
    while os.path.exists(candidate):
        candidate = os.path.join(out_dir, f"{stage.report_basename}-r{suffix}.md")
        suffix += 1

    return candidate, moniker


def _severity_sorted(findings: list) -> list:
    return sorted(findings, key=lambda f: SEVERITY_RANK.get(str(f.get("severity", "")).lower(), 3))


def _highest_severity(findings: list) -> str:
    if not findings:
        return "none"
    return _severity_sorted(findings)[0].get("severity", "none")


def _finding_lines(stage, finding: list) -> list:
    lines = []
    for label, key, as_quote in FINDING_FIELDS[stage.stage]:
        value = finding.get(key, "")
        if as_quote:
            lines.append(f'- **{label}:** `"{value}"`' if value else f"- **{label}:** `<MISSING>`")
        else:
            lines.append(f"- **{label}:** {value}")
    return lines


def _finding_heading(stage, finding: dict, max_votes: int) -> str:
    severity = str(finding.get("severity", "unknown")).lower()
    icon = SEVERITY_ICONS.get(severity, "⚪")
    votes = finding.get("votes", 0)
    heading = f"### {icon} `{finding.get('id')}` · {votes}/{max_votes} votes · severity {severity}"
    if stage.stage == "plan":
        category = finding.get("category")
        confidence = finding.get("confidence")
        if category:
            heading += f" · {category}"
        if confidence:
            heading += f" · confidence {confidence}"
    return heading


def format_markdown_report(stage, target_path: str, moniker, confirmed: list, unconfirmed: list,
                           no_hole_notes: list, agent_models: list, synthesis_model: str,
                           first_domino=None) -> str:
    """Generates the stage-appropriate adversarial review document."""
    date = datetime.date.today().isoformat()
    max_votes = len(agent_models) + 1  # each skeptic + the synthesis vote
    title_target = os.path.basename(target_path)

    lines = []
    lines.append(f"# {stage.report_title} (GEAP remote panel) — {title_target}")
    lines.append("")
    lines.append(
        f"> `{stage.skill_name}` · {len(agent_models)} remote skeptics on Vertex AI "
        f"({', '.join(agent_models)}) · synthesis by {synthesis_model} · default-to-reject · "
        f"2-of-{len(agent_models)} (+synthesis) gate"
    )
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| Milestone | `{moniker or '—'}` |")
    lines.append(f"| Artifact | `{target_path}` |")
    lines.append(f"| Date | {date} |")
    lines.append(f"| Gate | 2 votes of {max_votes} (skeptics + synthesis) |")
    lines.append(
        f"| Result | **{len(confirmed)} confirmed · {len(unconfirmed)} unconfirmed** — "
        f"highest severity **{_highest_severity(confirmed or unconfirmed)}** |"
    )
    if stage.has_first_domino:
        lines.append(f"| 🁢 First domino | `{first_domino}` |" if first_domino else "| 🁢 First domino | `none` |")
    lines.append("")

    lines.append("## Verdict")
    lines.append("")
    if confirmed:
        lines.append(
            f"Validation **FAILED** — {len(confirmed)} confirmed finding(s) must be resolved "
            f"in the {stage.stage} before proceeding."
        )
    else:
        lines.append(
            f"Validation **PASSED** — no finding reached the 2-vote quorum. "
            f"See **{stage.no_hole_heading}** for what was attacked."
        )
    lines.append("")

    lines.append("## Confirmed Findings (≥ 2 votes)")
    lines.append("")
    if not confirmed:
        lines.append("_None._")
    else:
        for finding in _severity_sorted(confirmed):
            lines.append(_finding_heading(stage, finding, max_votes))
            lines.extend(_finding_lines(stage, finding))
            lines.append("")

    lines.append("")
    lines.append("## Unconfirmed (FYI · < 2 votes)")
    lines.append("")
    if not unconfirmed:
        lines.append("_None._")
    else:
        lines.append(f"| `id` | severity | {stage.match_field} | votes |")
        lines.append("|---|---|---|---|")
        for finding in _severity_sorted(unconfirmed):
            severity = str(finding.get("severity", "unknown")).lower()
            icon = SEVERITY_ICONS.get(severity, "⚪")
            match_text = str(finding.get(stage.match_field, "")).replace("|", "\\|")
            lines.append(f"| `{finding.get('id')}` | {icon} {severity} | \"{match_text}\" | {finding.get('votes', 0)}/{max_votes} |")

    lines.append("")
    lines.append(f"## {stage.no_hole_heading}")
    lines.append("")
    if not no_hole_notes:
        lines.append("_None._")
    else:
        for note in no_hole_notes:
            lines.append(f"- `{note}`")

    lines.append("")
    lines.append("## Actions Taken")
    lines.append("")
    for finding in _severity_sorted(confirmed):
        lines.append(f"- [ ] Resolved `{finding.get('id')}` in the {stage.stage}")
    for finding in _severity_sorted(unconfirmed):
        lines.append(f"- [ ] Surfaced `{finding.get('id')}` (unconfirmed) to the user")
    lines.append(f"- [ ] Re-ran panel on revision → `{stage.report_basename}-r2.md` _(or: not needed)_")
    lines.append("")

    return "\n".join(lines)
