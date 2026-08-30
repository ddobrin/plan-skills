#!/usr/bin/env python3
"""Single-source topology tooling for the plan swarm.

`graph.json` at the plugin root declares the swarm's nodes, edges, gates and node
contracts. This module is the only thing allowed to turn that declaration into a
diagram, and the only thing that checks the declaration against the skills on disk.

    python3 lib/graph/graph.py validate                    # topology vs. filesystem
    python3 lib/graph/graph.py validate --agents-dir [DIR] # topology and agents/
    python3 lib/graph/graph.py validate-agents             # verify standalone subagents in agents/
    python3 lib/graph/graph.py render ascii                # the lifecycle diagram
    python3 lib/graph/graph.py render mermaid              # the same graph, for docs
    python3 lib/graph/graph.py render svg                  # themed inline SVG of the whole graph
    python3 lib/graph/graph.py sync                        # rewrite generated blocks in the READMEs
    python3 lib/graph/graph.py sync --check                # non-zero exit if a README is stale

Stdlib only, no third-party imports: this has to run in whatever environment the
plugin is installed into.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PLUGIN_ROOT.parents[1]
GRAPH_FILE = PLUGIN_ROOT / "graph.json"

BEGIN = "<!-- BEGIN GENERATED: lifecycle (python3 lib/graph/graph.py sync) -->"
END = "<!-- END GENERATED: lifecycle -->"


# --------------------------------------------------------------------------- model


def load(path: Path = GRAPH_FILE) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def by_id(graph: dict) -> dict:
    return {n["id"]: n for n in graph["nodes"]}


def phases(graph: dict) -> list[tuple[str, list[dict]]]:
    """Nodes grouped by phase, preserving declaration order."""
    out: list[tuple[str, list[dict]]] = []
    for node in graph["nodes"]:
        if out and out[-1][0] == node["phase"]:
            out[-1][1].append(node)
        else:
            out.append((node["phase"], [node]))
    return out


# ------------------------------------------------------------------------ validate


def validate(graph: dict) -> list[str]:
    """Return a list of problems. Empty list means the declaration matches reality."""
    problems: list[str] = []
    nodes = by_id(graph)

    if len(nodes) != len(graph["nodes"]):
        problems.append("duplicate node id in graph.json")

    # edges point at real nodes
    for edge in graph["edges"]:
        for end in ("from", "to"):
            if edge[end] not in nodes:
                problems.append(f"edge {edge['from']} -> {edge['to']}: unknown node {edge[end]!r}")

    # every non-entry node is reachable
    targets = {e["to"] for e in graph["edges"]}
    for node in graph["nodes"]:
        if node["kind"] != "entry" and node["id"] not in targets:
            problems.append(f"node {node['id']!r} has no inbound edge — unreachable")

    # declared skills and agents exist on disk
    for node in graph["nodes"]:
        skill = node.get("skill")
        if skill and not (PLUGIN_ROOT / "skills" / skill / "SKILL.md").is_file():
            problems.append(f"node {node['id']!r}: skills/{skill}/SKILL.md not found")
        agent = node.get("agent")
        if agent and not (PLUGIN_ROOT / "agents" / f"{agent}.md").is_file():
            problems.append(f"node {node['id']!r}: agents/{agent}.md not found")
        for alt in node.get("alternatives", []):
            if not (PLUGIN_ROOT / "skills" / alt / "SKILL.md").is_file():
                problems.append(f"node {node['id']!r}: alternative skills/{alt}/SKILL.md not found")

    # panels: lens count matches n, and every lens is actually present in the prompt file
    for node in graph["nodes"]:
        panel = node.get("panel")
        if not panel:
            continue
        lenses = panel.get("lenses", [])
        if len(lenses) != panel.get("n"):
            problems.append(
                f"node {node['id']!r}: panel.n={panel.get('n')} but {len(lenses)} lenses declared"
            )
        if len(set(lenses)) != len(lenses):
            problems.append(f"node {node['id']!r}: duplicate lens name")
        prompt_path = PLUGIN_ROOT / panel["prompt_file"]
        if not prompt_path.is_file():
            problems.append(f"node {node['id']!r}: {panel['prompt_file']} not found")
            continue
        text = prompt_path.read_text(encoding="utf-8")
        for lens in lenses:
            if lens not in text:
                problems.append(
                    f"node {node['id']!r}: lens {lens!r} declared in graph.json "
                    f"but absent from {panel['prompt_file']}"
                )
        # the defect this whole exercise exists to prevent
        if "three times, unchanged" in text or "three times**, unchanged" in text:
            problems.append(
                f"node {node['id']!r}: {panel['prompt_file']} still dispatches identical "
                f"prompts — correlated skeptics manufacture false corroboration"
            )

    # write contracts: only the nodes allowed to touch source may declare it
    source_writers = {"engineer", "simplifier"}
    for node in graph["nodes"]:
        if "<repo source>" in node.get("writes", []) and node["id"] not in source_writers:
            problems.append(f"node {node['id']!r} declares it writes repository source")
        if "git commit" in node.get("writes", []) and node.get("held_by") != "starter":
            problems.append(f"node {node['id']!r} declares it commits but is not held by starter")

    # gates reference real nodes of the right kind
    for gate in graph["gates"]:
        node = nodes.get(gate["node"])
        if node is None:
            problems.append(f"gate {gate['id']!r}: unknown node {gate['node']!r}")
        elif node["kind"] != "human-gate":
            problems.append(f"gate {gate['id']!r}: node {gate['node']!r} is not a human-gate")

    return problems


EXPECTED_AGENTS: set[str] = {
    "architect",
    "auditor",
    "engineer",
    "implementation-validator",
    "plan-deliberator",
    "plan-validator",
    "product-owner",
    "spec-deliberator",
    "spec-validator",
    "supervisor",
    "visual-architect",
    "visual-implementation-recap",
    "visual-product-owner",
}

FORBIDDEN_CORRELATED_PHRASES: list[str] = [
    "identical prompt",
    "identical template",
    "three times, unchanged",
    "three times**, unchanged",
]


def validate_agents(agents_dir: Path, graph: dict | None = None) -> list[str]:
    """Validate that agents/ subagents conform to graph contracts and are fully self-contained."""
    if graph is None:
        graph = load()

    problems: list[str] = []

    if not agents_dir.is_dir():
        return [f"agents directory not found: {agents_dir}"]

    # 1. Verify exactly the 13 reasoning subagents exist
    present_subdirs = {d.name for d in agents_dir.iterdir() if d.is_dir() and not d.name.startswith(".")}
    missing_agents = EXPECTED_AGENTS - present_subdirs
    if missing_agents:
        problems.append(f"missing expected agent directory(s): {', '.join(sorted(missing_agents))}")

    unexpected_subdirs = present_subdirs - EXPECTED_AGENTS
    if unexpected_subdirs:
        problems.append(
            f"unexpected agent directory(s): {', '.join(sorted(unexpected_subdirs))} "
            f"(expected exactly the 13 reasoning subagents)"
        )

    node_map = by_id(graph)

    # 2. Inspect each expected agent
    for agent_name in sorted(EXPECTED_AGENTS):
        agent_path = agents_dir / agent_name
        agent_file = agent_path / "agent.md"
        if not agent_file.is_file():
            problems.append(f"agent {agent_name!r}: agent.md not found")
            continue

        text = agent_file.read_text(encoding="utf-8")

        # Frontmatter validation
        if not text.startswith("---"):
            problems.append(f"agent {agent_name!r}: agent.md missing YAML frontmatter ('---')")

        # Self-contained check: no unresolved plugin roots or external skill references
        if "${CLAUDE_PLUGIN_ROOT}" in text or "$CLAUDE_PLUGIN_ROOT" in text:
            problems.append(f"agent {agent_name!r}: contains unresolved ${{CLAUDE_PLUGIN_ROOT}}")

        if re.search(r"plugins/plan/(?:skills|agents|lib)", text):
            problems.append(f"agent {agent_name!r}: contains external reference to 'plugins/plan/'")

        if re.search(r"\bskills/[a-zA-Z0-9_-]+/(?:references|assets|SKILL\.md)", text):
            problems.append(f"agent {agent_name!r}: contains external skill path dependency ('skills/...')")

        # Visual agents must bundle assets/ and references/
        if agent_name.startswith("visual-"):
            assets_dir = agent_path / "assets"
            ref_dir = agent_path / "references"
            if not assets_dir.is_dir():
                problems.append(f"agent {agent_name!r}: missing local assets/ directory")
            elif not (assets_dir / "template.html").is_file():
                problems.append(f"agent {agent_name!r}: missing local assets/template.html")
            if not ref_dir.is_dir():
                problems.append(f"agent {agent_name!r}: missing local references/ directory")
            if "assets/template.html" not in text:
                problems.append(f"agent {agent_name!r}: missing reference to local assets/template.html")

        # 3. Validator panels: 3 disjoint lenses declared in graph.json, no correlated skeptic dispatch
        if agent_name in {"spec-validator", "plan-validator", "implementation-validator"}:
            for phrase in FORBIDDEN_CORRELATED_PHRASES:
                if phrase in text.lower():
                    problems.append(
                        f"validator {agent_name!r}: contains correlated skeptic dispatching phrase: {phrase!r}"
                    )
            node = node_map.get(agent_name)
            if node and node.get("panel"):
                for lens in node["panel"].get("lenses", []):
                    if lens not in text:
                        problems.append(f"validator {agent_name!r}: declared lens {lens!r} absent from agent.md")

        # 4. Auditor: no git commit permissions, positive commit instructions or commands; explicitly prohibit commit
        if agent_name == "auditor":
            has_prohibition = bool(
                re.search(
                    r"(?i)(?:never|do not|must not|cannot|shall not|does not)\s+(?:run\s+)?`?git commit`?|does not commit",
                    text,
                )
            )
            if not has_prohibition:
                problems.append("auditor: must explicitly prohibit running git commit (sole-committer invariant)")

            has_positive_commit = False
            for line in text.splitlines():
                line_lower = line.lower().strip()
                if "commit" not in line_lower:
                    continue
                if any(
                    neg in line_lower
                    for neg in [
                        "never",
                        "do not",
                        "must not",
                        "cannot",
                        "no ",
                        "not permitted",
                        "not allowed",
                        "prohibited",
                        "refuse",
                        "does not",
                        "must_not_write",
                    ]
                ):
                    continue
                if any(role in line_lower for role in ["supervisor", "starter"]) and any(
                    w in line_lower for w in ["sole", "only", "commits", "committer"]
                ):
                    continue
                if re.search(
                    r"\b(?:run\s+`?git commit|commits?\s+only|permitted\s+to\s+commit|authority\s+to\s+commit|execute\s+`?git commit|make\s+(?:the\s+)?commit)\b",
                    line_lower,
                ):
                    has_positive_commit = True
                    break
            if (
                has_positive_commit
                or re.search(r"(?i)\bonly\s+(?:role\s+)?permitted\s+to\s+(?:run\s+)?`?git commit", text)
                or re.search(r"(?i)\bcommits?\s+only\s+on\s+a\s+(?:green|passing)\s+audit", text)
            ):
                problems.append("auditor: contains commit permissions or instructions")

        # 5. Outdated Auditor committer references in other roles
        if agent_name not in {"auditor", "supervisor"}:
            if (
                re.search(r"(?i)(?:version control|committing)\s+is\s+(?:strictly\s+)?the\s+auditor['’]?s\s+job", text)
                or re.search(r"(?i)auditor['’]?s\s+job\s+to\s+commit", text)
                or re.search(r"(?i)only\s+the\s+auditor\s+(?:commits|can\s+commit|runs\s+`?git commit`?)", text)
                or re.search(r"(?i)auditor\s+is\s+the\s+only\s+role\s+permitted\s+to\s+.*commit", text)
            ):
                problems.append(
                    f"agent {agent_name!r}: outdated invariant — refers to Auditor as committer instead of Supervisor"
                )

        # 6. Supervisor: designated sole committer requiring passing audit + explicit user confirmation, and state.json management
        if agent_name == "supervisor":
            if not re.search(
                r"(?i)(?:sole\s+committer|only\s+(?:role|agent)\s+(?:permitted|allowed)\s+to\s+(?:run\s+)?`?git commit`?|only\s+role\s+that\s+runs\s+`?git commit`?)",
                text,
            ):
                problems.append("supervisor: must designate supervisor as the sole committer permitted to run git commit")
            has_audit = bool(
                re.search(r"(?i)(?:green|passing|approved)\s+audit|audit\s+(?:report\s+)?(?:pass|passed|passing)", text)
            )
            has_user = bool(re.search(r"(?i)explicit\s+user\s+(?:approval|confirmation|approve|\"yes\")", text))
            if not (has_audit and has_user):
                problems.append(
                    "supervisor: commit protocol must require both a passing audit report and explicit user confirmation"
                )
            if "plans/active_milestones/{moniker}/state.json" not in text and not re.search(
                r"plans/active_milestones/.*?/state\.json", text
            ):
                problems.append("supervisor: must specify reading and managing 'plans/active_milestones/{moniker}/state.json'")

        # 7. Deliberators: mandate asymmetry test and refuse deliberation if the test fails
        if agent_name in {"spec-deliberator", "plan-deliberator"}:
            if not re.search(r"(?i)asymmetry\s+test", text):
                problems.append(f"deliberator {agent_name!r}: must mandate the asymmetry test")
            if not re.search(
                r"(?i)(?:refuse|refuses|refusing|halt|halts|halting|abort|aborts|aborting|skip|skips|skipping)\s+deliberation|if\s+(?:the\s+)?(?:asymmetry\s+)?test\s+fails?,?\s+(?:refuse|do not deliberate|skip|halt|abort)",
                text,
            ):
                problems.append(f"deliberator {agent_name!r}: must refuse deliberation if the asymmetry test fails")

    return problems


# -------------------------------------------------------------------------- render


def _panel_line(node: dict) -> str:
    lenses = " · ".join(node["panel"]["lenses"])
    return f"[{node['panel']['n']}-lens {node['panel']['gate']} gate: {lenses}]"


def render_ascii(graph: dict) -> str:
    lines: list[str] = ["```text", " IDEA"]
    for phase, group in phases(graph):
        for node in group:
            kind = node["kind"]
            if kind == "entry":
                continue
            if kind == "human-gate":
                lines.append("  |")
                lines.append(f"  v  Phase {phase}  *** {node['label']} *** -- {node['sublabel']}")
                continue
            if kind == "terminal":
                lines.append("  |")
                lines.append(f"  v  Phase {phase}  {node['label']} -- {node['sublabel']}")
                continue
            if kind == "panel":
                lines.append(f"  |            === GATE {node['label']} " + _panel_line(node))
                lines.append(f"  |                 -> {node['writes'][0]}")
                continue
            prefix = "  |            " if node.get("optional") or kind in ("deliberation", "renderer") else "  v  Phase %-2s  " % phase
            tag = ""
            if node.get("optional"):
                tag = "(optional) "
            if kind == "deliberation":
                tag = "(optional) " if node.get("optional") else ""
            if node.get("optional") or kind in ("deliberation", "renderer"):
                lines.append(f"{prefix}+- {tag}{node['label']} -- {node['sublabel']}")
            else:
                lines.append("  |")
                lines.append(f"{prefix}{node['label']} -- {node['sublabel']}")
            if node.get("fanout"):
                fo = node["fanout"]
                lines.append(
                    f"  |               fan-out over {fo['over']}, "
                    f"max {fo['max_concurrent']} concurrent, {fo['disjoint']}-disjoint"
                )

    # cycles are edges that point backwards; they read badly on a spine, so list them
    order = {n["id"]: i for i, n in enumerate(graph["nodes"])}
    back = [e for e in graph["edges"] if order[e["to"]] < order[e["from"]]]
    if back:
        lines.append("")
        lines.append(" feedback edges (cycles):")
        for e in back:
            label = f" — {e['label']}" if e.get("label") else ""
            lines.append(f"   {e['from']} -> {e['to']}   when: {e['when']}{label}")
    lines.append("```")
    return "\n".join(lines)


_MERMAID_SHAPE = {
    "entry": ("([", "])"),
    "role": ("[", "]"),
    "panel": ("{{", "}}"),
    "deliberation": ("[/", "/]"),
    "human-gate": ("[[", "]]"),
    "renderer": ("(", ")"),
    "terminal": ("([", "])"),
}


def render_mermaid(graph: dict) -> str:
    lines = ["```mermaid", "flowchart TD"]
    for node in graph["nodes"]:
        open_s, close_s = _MERMAID_SHAPE[node["kind"]]
        label = node["label"]
        if node["kind"] == "panel":
            label += "<br/>" + " · ".join(node["panel"]["lenses"])
        if node.get("optional"):
            label += "<br/>(optional)"
        lines.append(f'  {node["id"].replace("-", "_")}{open_s}"{label}"{close_s}')
    lines.append("")
    for edge in graph["edges"]:
        src = edge["from"].replace("-", "_")
        dst = edge["to"].replace("-", "_")
        text = edge.get("label") or edge["when"]
        arrow = "-.->" if edge["when"] == "optional" else "-->"
        lines.append(f'  {src} {arrow}|"{text}"| {dst}')
    lines.append("")
    lines.append("  classDef gate fill:#f6eedc,stroke:#8a5a12,stroke-width:2px;")
    lines.append("  classDef panel fill:#e0eff2,stroke:#0e7385,stroke-width:2px;")
    gate_ids = ",".join(n["id"].replace("-", "_") for n in graph["nodes"] if n["kind"] == "human-gate")
    panel_ids = ",".join(n["id"].replace("-", "_") for n in graph["nodes"] if n["kind"] == "panel")
    if gate_ids:
        lines.append(f"  class {gate_ids} gate;")
    if panel_ids:
        lines.append(f"  class {panel_ids} panel;")
    lines.append("```")
    return "\n".join(lines)



# ------------------------------------------------------------------------ svg

ROW_H = 66
SPINE_CX, SPINE_W = 300, 232
BRANCH_CX, BRANCH_W = 578, 208
BOX_H = 40
TOP, BOTTOM_PAD = 26, 30
WIDTH = 760

_SVG_CLASS = {
    "entry": "n-entry", "role": "n-role", "panel": "n-panel",
    "deliberation": "n-delib", "human-gate": "n-gate",
    "renderer": "n-render", "terminal": "n-term",
}


def _layout(graph: dict) -> tuple[dict, list[dict], list[dict]]:
    """Deterministic two-lane layout: a spine of required nodes, optional nodes to the right."""
    nodes = by_id(graph)
    spine = [n for n in graph["nodes"] if not n.get("optional")]
    branch = [n for n in graph["nodes"] if n.get("optional")]

    pos: dict[str, dict] = {}
    for row, node in enumerate(spine):
        pos[node["id"]] = {"row": row, "cx": SPINE_CX, "w": SPINE_W,
                           "y": TOP + row * ROW_H, "lane": "spine"}

    # an optional node sits on the row of the spine node that feeds it
    for node in branch:
        feeder = next((e["from"] for e in graph["edges"]
                       if e["to"] == node["id"] and e["from"] in pos), None)
        row = pos[feeder]["row"] if feeder else 0
        pos[node["id"]] = {"row": row, "cx": BRANCH_CX, "w": BRANCH_W,
                           "y": TOP + row * ROW_H, "lane": "branch"}
    return pos, spine, branch


def render_svg(graph: dict) -> str:
    pos, spine, _branch = _layout(graph)
    order = {n["id"]: i for i, n in enumerate(graph["nodes"])}
    height = TOP + (len(spine) - 1) * ROW_H + BOX_H + BOTTOM_PAD

    o: list[str] = []
    a = o.append
    a(f'<svg class="graphsvg" viewBox="0 0 {WIDTH} {height}" role="img" '
      f'aria-label="The complete plan swarm topology generated from graph.json: '
      f'{len(graph["nodes"])} nodes and {len(graph["edges"])} edges. A vertical spine of required '
      f'nodes runs from request to release, optional nodes branch to the right, and feedback '
      f'edges arc back on the left.">')
    a('<defs>')
    a('<marker id="gh" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
      'orient="auto-start-reverse"><path d="M0,1 L9,5 L0,9 z" fill="currentColor"/></marker>')
    a('</defs>')

    # --- edges first, so nodes paint over them
    back_slot = 0
    for e in graph["edges"]:
        src, dst = pos[e["from"]], pos[e["to"]]
        forward = order[e["to"]] > order[e["from"]]
        optional = e["when"] == "optional" or graph_nodes_optional(graph, e)
        cls = "e-opt" if optional else "e-fwd"

        if not forward:
            # feedback: arc out to the left of the spine
            back_slot += 1
            off = 22 + back_slot * 15
            x = SPINE_CX - SPINE_W / 2
            y1, y2 = src["y"] + BOX_H / 2, dst["y"] + BOX_H / 2
            a(f'<path class="e-back" d="M{x:.0f},{y1:.0f} C{x-off:.0f},{y1:.0f} '
              f'{x-off:.0f},{y2:.0f} {x:.0f},{y2:.0f}" marker-end="url(#gh)"/>')
            label = e.get("label") or e["when"]
            a(f'<text class="e-lbl-back" x="{x-off-4:.0f}" y="{(y1+y2)/2:.0f}" '
              f'text-anchor="end">{_esc(label)}</text>')
            continue

        if src["lane"] == dst["lane"] == "spine" and dst["row"] == src["row"] + 1:
            x = SPINE_CX
            a(f'<line class="{cls}" x1="{x}" y1="{src["y"]+BOX_H}" x2="{x}" '
              f'y2="{dst["y"]}" marker-end="url(#gh)"/>')
            if e.get("label"):
                a(f'<text class="e-lbl" x="{x+8}" y="{src["y"]+BOX_H+16}">{_esc(e["label"])}</text>')
        else:
            x1 = src["cx"] + (src["w"] / 2 if dst["cx"] > src["cx"] else -src["w"] / 2)
            x2 = dst["cx"] + (-dst["w"] / 2 if dst["cx"] > src["cx"] else dst["w"] / 2)
            y1, y2 = src["y"] + BOX_H / 2, dst["y"] + BOX_H / 2
            mx = (x1 + x2) / 2
            a(f'<path class="{cls}" d="M{x1:.0f},{y1:.0f} C{mx:.0f},{y1:.0f} '
              f'{mx:.0f},{y2:.0f} {x2:.0f},{y2:.0f}" marker-end="url(#gh)"/>')

    # --- nodes
    for node in graph["nodes"]:
        p = pos[node["id"]]
        x = p["cx"] - p["w"] / 2
        a(f'<rect class="{_SVG_CLASS[node["kind"]]}" x="{x:.0f}" y="{p["y"]}" '
          f'width="{p["w"]}" height="{BOX_H}" rx="2"/>')
        a(f'<text class="n-lbl" x="{p["cx"]}" y="{p["y"]+17}" text-anchor="middle">'
          f'{_esc(node["label"])}</text>')
        sub = node["sublabel"]
        if node.get("panel"):
            sub = " · ".join(node["panel"]["lenses"])
        a(f'<text class="n-sub" x="{p["cx"]}" y="{p["y"]+31}" text-anchor="middle">'
          f'{_esc(sub)}</text>')

    a('</svg>')
    return "\n".join(o)


def graph_nodes_optional(graph: dict, edge: dict) -> bool:
    nodes = by_id(graph)
    return bool(nodes[edge["to"]].get("optional"))


def _esc(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))

# ---------------------------------------------------------------------------- sync

TARGETS = [
    (PLUGIN_ROOT / "README.md", "ascii"),
    (PLUGIN_ROOT / "agents" / "README.md", "ascii"),
    (REPO_ROOT / "agents" / "README.md", "ascii"),
    (REPO_ROOT / "README.md", "ascii"),
]


def _block(graph: dict, flavor: str) -> str:
    body = {"ascii": render_ascii, "mermaid": render_mermaid, "svg": render_svg}[flavor](graph)
    return (
        f"{BEGIN}\n"
        f"<!-- graph_version: {graph['graph_version']} — edit graph.json, then run sync. -->\n\n"
        f"{body}\n\n{END}"
    )


def sync(graph: dict, check: bool = False) -> int:
    stale: list[str] = []
    for path, flavor in TARGETS:
        if not path.is_file():
            stale.append(f"{path}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        if BEGIN not in text or END not in text:
            stale.append(f"{path}: no generated block — add the BEGIN/END markers")
            continue
        new_block = _block(graph, flavor)
        pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
        updated = pattern.sub(lambda _m: new_block, text)
        if updated == text:
            continue
        if check:
            stale.append(f"{path}: out of date")
        else:
            path.write_text(updated, encoding="utf-8")
            print(f"updated {path.relative_to(REPO_ROOT)}")
    if stale:
        for line in stale:
            print(f"STALE  {line}", file=sys.stderr)
        return 1
    if check:
        print("all generated blocks are up to date")
    return 0


# ----------------------------------------------------------------------------- cli


def _resolve_agents_dir(raw_path: Path | str) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p.resolve()
    if p.is_dir():
        return p.resolve()
    repo_candidate = REPO_ROOT / p
    if repo_candidate.is_dir():
        return repo_candidate.resolve()
    return p.resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="check graph.json against skills on disk, and optionally agents/")
    v.add_argument(
        "--agents-dir",
        type=Path,
        nargs="?",
        const=REPO_ROOT / "agents",
        default=None,
        help="verify standalone subagent definitions in agents/ directory against graph contracts",
    )

    va = sub.add_parser(
        "validate-agents",
        help="verify standalone subagent definitions in agents/ directory against graph contracts",
    )
    va.add_argument(
        "--agents-dir",
        type=Path,
        default=REPO_ROOT / "agents",
        help="path to agents directory (defaults to repo root agents/)",
    )

    r = sub.add_parser("render", help="print a diagram")
    r.add_argument("flavor", choices=["ascii", "mermaid", "svg"])
    s = sub.add_parser("sync", help="rewrite the generated blocks in the READMEs")
    s.add_argument("--check", action="store_true", help="exit non-zero if a block is stale")
    args = parser.parse_args(argv)

    graph = load()

    if args.cmd == "validate-agents":
        agents_dir = _resolve_agents_dir(args.agents_dir)
        problems = validate_agents(agents_dir, graph)
        if problems:
            try:
                rel = agents_dir.relative_to(REPO_ROOT)
            except ValueError:
                rel = agents_dir
            print(f"{len(problems)} problem(s) in {rel}:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 1
        print(f"agents/ OK — all {len(EXPECTED_AGENTS)} subagents conformant to graph engineering specifications")
        return 0

    if args.cmd == "validate":
        problems = validate(graph)
        if args.agents_dir is not None:
            agents_dir = _resolve_agents_dir(args.agents_dir)
            problems.extend(validate_agents(agents_dir, graph))
        if problems:
            print(f"{len(problems)} problem(s):", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 1
        n = len(graph["nodes"])
        panels = sum(1 for x in graph["nodes"] if x["kind"] == "panel")
        gates = sum(1 for x in graph["nodes"] if x["kind"] == "human-gate")
        print(f"graph.json OK — {n} nodes, {len(graph['edges'])} edges, {panels} lens-partitioned panels, {gates} human gates")
        if args.agents_dir is not None:
            print(f"agents/ OK — all {len(EXPECTED_AGENTS)} subagents conformant to graph engineering specifications")
        return 0

    if args.cmd == "render":
        print({"ascii": render_ascii, "mermaid": render_mermaid, "svg": render_svg}[args.flavor](graph))
        return 0

    return sync(graph, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
