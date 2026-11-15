#!/usr/bin/env python3
"""Test suite for lib/graph/graph.py.

    python3 lib/graph/test_graph.py            # from the plugin root
    python3 -m unittest discover -s lib/graph  # the same, via unittest

Stdlib only, like the module under test.
"""

from __future__ import annotations

import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

# Importing the module under test must not leave __pycache__ behind in the plugin.
sys.dont_write_bytecode = True

# Load graph.py from this directory, so the suite does not depend on what the plugin's
# parent directories are called.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import graph as graph_module  # noqa: E402
from graph import (  # noqa: E402
    AGENTS_DIR,
    EXPECTED_AGENTS,
    FORBIDDEN_CORRELATED_PHRASES,
    PLUGIN_ROOT,
    SKILLS_DIR,
    by_id,
    is_checkout,
    lens_section_count,
    load,
    main,
    phases,
    render_ascii,
    render_mermaid,
    render_svg,
    sync,
    sync_targets,
    validate,
    validate_agents,
)


def populate_clean_agents_directory(base_dir: Path, graph: dict) -> None:
    """Populate a directory with conformant agent definitions for all 13 subagents."""
    node_map = by_id(graph)

    for name in EXPECTED_AGENTS:
        agent_dir = base_dir / name
        agent_dir.mkdir(parents=True, exist_ok=True)

        if name.startswith("visual-"):
            (agent_dir / "assets").mkdir(exist_ok=True)
            (agent_dir / "references").mkdir(exist_ok=True)
            template_file = agent_dir / "assets" / "template.html"
            template_file.write_text("<!DOCTYPE html><html><body>Visual template</body></html>", encoding="utf-8")
            (agent_dir / "references" / "guide.md").write_text("# Reference Guide\n", encoding="utf-8")

        lines: list[str] = [
            "---",
            f"name: {name}",
            f"description: Valid specification for {name}",
            "---",
            f"# Charter for {name}",
            "",
        ]

        if name == "auditor":
            lines.extend([
                "Never run `git commit`.",
                "You must not run `git commit` under any circumstances.",
                "Version control and committing are solely the responsibility of the supervisor.",
            ])
        elif name == "supervisor":
            lines.extend([
                "You are designated as the sole committer permitted to run `git commit`.",
                "Commit protocol requires both a passing green audit report and explicit user confirmation ('yes').",
                "Reads and manages plans/active_milestones/{moniker}/state.json across lifecycle transitions.",
            ])
        elif name in {"spec-validator", "plan-validator", "implementation-validator"}:
            panel = node_map[name]["panel"]
            lines.append("Dispatches 3 independent skeptics across 3 disjoint evidence lenses:")
            for lens in panel["lenses"]:
                lines.extend([
                    f"### Lens: {lens}",
                    f"Dedicated prompt instructions and verification criteria for {lens}.",
                    "",
                ])
        elif name in {"spec-deliberator", "plan-deliberator"}:
            lines.extend([
                "Mandates the asymmetry test: each delegate must hold non-overlapping knowledge.",
                "If the asymmetry test fails, refuse deliberation and record status skipped in state.",
            ])
        else:
            lines.append("Version control is solely the supervisor's job.")

        if name.startswith("visual-"):
            lines.append("Instantiate using local bundled template at `assets/template.html`.")

        (agent_dir / "agent.md").write_text("\n".join(lines), encoding="utf-8")


class TestGraphCore(unittest.TestCase):
    """Tests for core graph loading, validation, rendering, and synchronization."""

    def setUp(self):
        self.graph = load()

    def test_graph_load(self):
        self.assertIn("graph_version", self.graph)
        self.assertIn("nodes", self.graph)
        self.assertIn("edges", self.graph)
        self.assertGreater(len(self.graph["nodes"]), 0)
        self.assertGreater(len(self.graph["edges"]), 0)

    def test_graph_validate_clean(self):
        problems = validate(self.graph)
        self.assertEqual(problems, [], f"graph.json validation reported unexpected problems: {problems}")

    def test_by_id(self):
        node_map = by_id(self.graph)
        self.assertIn("architect", node_map)
        self.assertIn("auditor", node_map)
        self.assertIn("engineer", node_map)
        self.assertIn("product-owner", node_map)

    def test_phases(self):
        grouped = phases(self.graph)
        self.assertGreater(len(grouped), 0)
        phase_names = [p[0] for p in grouped]
        self.assertIn("0", phase_names)
        self.assertIn("4", phase_names)

    def test_render_ascii(self):
        diagram = render_ascii(self.graph)
        self.assertIn("```text", diagram)
        self.assertIn("product-owner", diagram)
        self.assertIn("architect", diagram)
        self.assertIn("auditor", diagram)

    def test_render_mermaid(self):
        diagram = render_mermaid(self.graph)
        self.assertIn("```mermaid", diagram)
        self.assertIn("flowchart TD", diagram)

    def test_render_svg(self):
        svg = render_svg(self.graph)
        self.assertTrue(svg.startswith("<svg"))
        self.assertTrue(svg.rstrip().endswith("</svg>"))
        for node in self.graph["nodes"]:
            self.assertIn(node["label"].replace("&", "&amp;"), svg)

    def test_sync_check(self):
        """The generated lifecycle blocks in all three READMEs match graph.json."""
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
            result = sync(self.graph, check=True)
        self.assertEqual(result, 0, f"README lifecycle block is stale — run `graph.py sync`: {err.getvalue()}")

    def test_validate_detects_corrupt_graph(self):
        corrupt_graph = {
            "nodes": [
                {"id": "node1", "kind": "entry", "phase": "0", "label": "Node 1", "sublabel": ""},
                {"id": "node1", "kind": "role", "phase": "1", "label": "Duplicate Node", "sublabel": ""},
            ],
            "edges": [
                {"from": "node1", "to": "non_existent_node", "when": "always"},
            ],
            "gates": [
                {"id": "g1", "node": "node1"},
            ],
        }
        problems = validate(corrupt_graph)
        self.assertTrue(any("duplicate node id" in p for p in problems))
        self.assertTrue(any("unknown node 'non_existent_node'" in p for p in problems))
        self.assertTrue(any("is not a human-gate" in p for p in problems))


class TestAgentsValidationSyntheticClean(unittest.TestCase):
    """Tests that a fully conformant synthetic agents directory passes validation."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.agents_dir = Path(self.tmp_dir.name) / "agents"
        self.agents_dir.mkdir()
        self.graph = load()
        populate_clean_agents_directory(self.agents_dir, self.graph)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_clean_agents_directory_passes(self):
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertEqual(problems, [])

    def test_cli_validate_agents_clean(self):
        stdout_buf = io.StringIO()
        with redirect_stdout(stdout_buf):
            exit_code = main(["validate-agents", "--agents-dir", str(self.agents_dir)])
        self.assertEqual(exit_code, 0)
        self.assertIn("agents/ OK — all 13 subagents conformant to graph engineering specifications", stdout_buf.getvalue())

    def test_cli_validate_with_agents_dir_clean(self):
        stdout_buf = io.StringIO()
        with redirect_stdout(stdout_buf):
            exit_code = main(["validate", "--agents-dir", str(self.agents_dir)])
        self.assertEqual(exit_code, 0)
        output = stdout_buf.getvalue()
        self.assertIn("graph.json OK", output)
        self.assertIn("agents/ OK — all 13 subagents conformant to graph engineering specifications", output)


class TestAgentsValidationInvariant1_SubagentsCount(unittest.TestCase):
    """Invariant 1: Exact 13 subagents, no missing agents, no extra agent directories."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.agents_dir = Path(self.tmp_dir.name) / "agents"
        self.agents_dir.mkdir()
        self.graph = load()
        populate_clean_agents_directory(self.agents_dir, self.graph)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_missing_subagent_directory(self):
        shutil.rmtree(self.agents_dir / "supervisor")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("missing expected agent directory(s): supervisor" in p for p in problems))

    def test_unexpected_subagent_directory_rejected(self):
        (self.agents_dir / "unrelated-helper").mkdir()
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("unexpected agent directory(s): unrelated-helper" in p for p in problems))

    def test_missing_agent_md(self):
        (self.agents_dir / "engineer" / "agent.md").unlink()
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("agent 'engineer': agent.md not found" in p for p in problems))

    def test_missing_yaml_frontmatter(self):
        f = self.agents_dir / "engineer" / "agent.md"
        f.write_text("No frontmatter here\nJust text.", encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("missing YAML frontmatter" in p for p in problems))

    def test_nonexistent_directory(self):
        bad_dir = Path(self.tmp_dir.name) / "does_not_exist"
        problems = validate_agents(bad_dir, self.graph)
        self.assertTrue(any("agents directory not found" in p for p in problems))


class TestAgentsValidationInvariant2_SelfContained(unittest.TestCase):
    """Invariant 2: Self-contained, no ${CLAUDE_PLUGIN_ROOT}, no external skills, visual assets exist."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.agents_dir = Path(self.tmp_dir.name) / "agents"
        self.agents_dir.mkdir()
        self.graph = load()
        populate_clean_agents_directory(self.agents_dir, self.graph)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_unresolved_claude_plugin_root(self):
        f = self.agents_dir / "architect" / "agent.md"
        f.write_text(f.read_text(encoding="utf-8") + "\nPath: ${CLAUDE_PLUGIN_ROOT}/skills/x", encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("contains unresolved ${CLAUDE_PLUGIN_ROOT}" in p for p in problems))

    def test_external_plugin_reference(self):
        f = self.agents_dir / "architect" / "agent.md"
        f.write_text(f.read_text(encoding="utf-8") + "\nPoints to plugins/plan/skills/architect/SKILL.md", encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("contains external reference to 'plugins/plan/'" in p for p in problems))

    def test_external_skill_dependency(self):
        f = self.agents_dir / "spec-validator" / "agent.md"
        f.write_text(f.read_text(encoding="utf-8") + "\nLoad skills/spec-validator/SKILL.md", encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("contains external skill path dependency ('skills/...')" in p for p in problems))

    def test_visual_agent_missing_assets(self):
        shutil.rmtree(self.agents_dir / "visual-architect" / "assets")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("visual-architect': missing local assets/ directory" in p for p in problems))

    def test_visual_agent_missing_template_html(self):
        (self.agents_dir / "visual-architect" / "assets" / "template.html").unlink()
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("visual-architect': missing local assets/template.html" in p for p in problems))

    def test_visual_agent_missing_references(self):
        shutil.rmtree(self.agents_dir / "visual-architect" / "references")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("visual-architect': missing local references/ directory" in p for p in problems))

    def test_visual_agent_missing_template_reference_in_markdown(self):
        f = self.agents_dir / "visual-architect" / "agent.md"
        content = f.read_text(encoding="utf-8").replace("assets/template.html", "other/file.html")
        f.write_text(content, encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("visual-architect': missing reference to local assets/template.html" in p for p in problems))


class TestAgentsValidationInvariant3_ValidatorPanels(unittest.TestCase):
    """Invariant 3: 3 disjoint lenses, no identical prompt/template or correlated dispatch."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.agents_dir = Path(self.tmp_dir.name) / "agents"
        self.agents_dir.mkdir()
        self.graph = load()
        populate_clean_agents_directory(self.agents_dir, self.graph)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_validator_identical_prompt_phrase_rejected(self):
        f = self.agents_dir / "plan-validator" / "agent.md"
        f.write_text(f.read_text(encoding="utf-8") + "\nDispatch with identical prompt below.", encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("correlated skeptic dispatching phrase: 'identical prompt'" in p for p in problems))

    def test_validator_identical_template_phrase_rejected(self):
        f = self.agents_dir / "spec-validator" / "agent.md"
        f.write_text(f.read_text(encoding="utf-8") + "\nSpawn three skeptics with identical template.", encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("correlated skeptic dispatching phrase: 'identical template'" in p for p in problems))

    def test_validator_three_times_unchanged_rejected(self):
        f = self.agents_dir / "implementation-validator" / "agent.md"
        f.write_text(f.read_text(encoding="utf-8") + "\nRun three times, unchanged for corroboration.", encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("correlated skeptic dispatching phrase: 'three times, unchanged'" in p for p in problems))

    def test_validator_agent_missing_a_lens_section_rejected(self):
        """Naming a lens is not enough: each declared lens needs its own prompt section."""
        f = self.agents_dir / "plan-validator" / "agent.md"
        content = f.read_text(encoding="utf-8").replace("### Lens: blast-radius", "Also covers blast-radius.")
        f.write_text(content, encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(
            any("validator 'plan-validator': agent.md has 2 lens prompt section(s) for 3 declared lenses" in p for p in problems),
            problems,
        )

    def test_validator_missing_declared_lens(self):
        f = self.agents_dir / "plan-validator" / "agent.md"
        content = f.read_text(encoding="utf-8").replace("blast-radius", "omitted-lens")
        f.write_text(content, encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("validator 'plan-validator': declared lens 'blast-radius' absent from agent.md" in p for p in problems))


class TestAgentsValidationInvariant4_AuditorInvariants(unittest.TestCase):
    """Invariant 4: Auditor has NO commit authority, positive instructions, and explicitly prohibits commit."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.agents_dir = Path(self.tmp_dir.name) / "agents"
        self.agents_dir.mkdir()
        self.graph = load()
        populate_clean_agents_directory(self.agents_dir, self.graph)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_auditor_positive_commit_permission_rejected(self):
        f = self.agents_dir / "auditor" / "agent.md"
        f.write_text(f.read_text(encoding="utf-8") + "\nYou are the only role permitted to git commit.", encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("auditor: contains commit permissions or instructions" in p for p in problems))

    def test_auditor_commits_only_on_green_audit_rejected(self):
        f = self.agents_dir / "auditor" / "agent.md"
        f.write_text(f.read_text(encoding="utf-8") + "\nAuditor commits only on a green audit.", encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("auditor: contains commit permissions or instructions" in p for p in problems))

    def test_auditor_run_git_commit_command_rejected(self):
        f = self.agents_dir / "auditor" / "agent.md"
        f.write_text(f.read_text(encoding="utf-8") + "\nRun `git commit` on a green audit.", encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("auditor: contains commit permissions or instructions" in p for p in problems))

    def test_auditor_missing_commit_prohibition_rejected(self):
        f = self.agents_dir / "auditor" / "agent.md"
        content = "---\nname: auditor\n---\n# Charter\nVerifies code against plan and spec.\n"
        f.write_text(content, encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("auditor: must explicitly prohibit running git commit (sole-committer invariant)" in p for p in problems))


class TestAgentsValidationInvariant5_SupervisorInvariants(unittest.TestCase):
    """Invariant 5: Supervisor is sole committer upon passing audit + user approval, manages state.json."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.agents_dir = Path(self.tmp_dir.name) / "agents"
        self.agents_dir.mkdir()
        self.graph = load()
        populate_clean_agents_directory(self.agents_dir, self.graph)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_supervisor_missing_sole_committer(self):
        f = self.agents_dir / "supervisor" / "agent.md"
        content = f.read_text(encoding="utf-8").replace("sole committer permitted to run `git commit`", "general manager")
        f.write_text(content, encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("supervisor: must designate supervisor as the sole committer permitted to run git commit" in p for p in problems))

    def test_supervisor_missing_passing_audit(self):
        f = self.agents_dir / "supervisor" / "agent.md"
        content = f.read_text(encoding="utf-8").replace("passing green audit report", "quick review")
        f.write_text(content, encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("supervisor: commit protocol must require both a passing audit report and explicit user confirmation" in p for p in problems))

    def test_supervisor_missing_user_confirmation(self):
        f = self.agents_dir / "supervisor" / "agent.md"
        content = f.read_text(encoding="utf-8").replace("explicit user confirmation ('yes')", "automated approval")
        f.write_text(content, encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("supervisor: commit protocol must require both a passing audit report and explicit user confirmation" in p for p in problems))

    def test_supervisor_missing_state_json(self):
        f = self.agents_dir / "supervisor" / "agent.md"
        content = f.read_text(encoding="utf-8").replace("plans/active_milestones/{moniker}/state.json", "legacy_status.txt")
        f.write_text(content, encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("supervisor: must specify reading and managing 'plans/active_milestones/{moniker}/state.json'" in p for p in problems))


class TestAgentsValidationInvariant6_DeliberatorInvariants(unittest.TestCase):
    """Invariant 6: Deliberators mandate asymmetry tests and refuse deliberation on failure."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.agents_dir = Path(self.tmp_dir.name) / "agents"
        self.agents_dir.mkdir()
        self.graph = load()
        populate_clean_agents_directory(self.agents_dir, self.graph)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_spec_deliberator_missing_asymmetry_test(self):
        f = self.agents_dir / "spec-deliberator" / "agent.md"
        content = f.read_text(encoding="utf-8").replace("asymmetry test", "perspective check")
        f.write_text(content, encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("deliberator 'spec-deliberator': must mandate the asymmetry test" in p for p in problems))

    def test_spec_deliberator_missing_refusal(self):
        f = self.agents_dir / "spec-deliberator" / "agent.md"
        content = f.read_text(encoding="utf-8").replace(
            "If the asymmetry test fails, refuse deliberation and record status skipped in state.",
            "If the asymmetry test fails, just revise and keep deliberating.",
        )
        f.write_text(content, encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("deliberator 'spec-deliberator': must refuse deliberation if the asymmetry test fails" in p for p in problems))

    def test_plan_deliberator_missing_asymmetry_test(self):
        f = self.agents_dir / "plan-deliberator" / "agent.md"
        content = f.read_text(encoding="utf-8").replace("asymmetry test", "perspective check")
        f.write_text(content, encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("deliberator 'plan-deliberator': must mandate the asymmetry test" in p for p in problems))

    def test_plan_deliberator_missing_refusal(self):
        f = self.agents_dir / "plan-deliberator" / "agent.md"
        content = f.read_text(encoding="utf-8").replace(
            "If the asymmetry test fails, refuse deliberation and record status skipped in state.",
            "If the asymmetry test fails, revise the plan anyway.",
        )
        f.write_text(content, encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("deliberator 'plan-deliberator': must refuse deliberation if the asymmetry test fails" in p for p in problems))


class TestAgentsValidationInvariant7_OutdatedCommitterReferences(unittest.TestCase):
    """Invariant 7: No role refers to Auditor as committer instead of Supervisor."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.agents_dir = Path(self.tmp_dir.name) / "agents"
        self.agents_dir.mkdir()
        self.graph = load()
        populate_clean_agents_directory(self.agents_dir, self.graph)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_architect_outdated_committer(self):
        f = self.agents_dir / "architect" / "agent.md"
        f.write_text(f.read_text(encoding="utf-8") + "\nVersion control is the Auditor's job.", encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("agent 'architect': outdated invariant — refers to Auditor as committer instead of Supervisor" in p for p in problems))

    def test_engineer_outdated_committer(self):
        f = self.agents_dir / "engineer" / "agent.md"
        f.write_text(f.read_text(encoding="utf-8") + "\ncommitting is strictly the Auditor's job.", encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("agent 'engineer': outdated invariant — refers to Auditor as committer instead of Supervisor" in p for p in problems))

    def test_product_owner_outdated_committer(self):
        f = self.agents_dir / "product-owner" / "agent.md"
        f.write_text(f.read_text(encoding="utf-8") + "\nIt is the auditor's job to commit code.", encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("agent 'product-owner': outdated invariant — refers to Auditor as committer instead of Supervisor" in p for p in problems))

    def test_visual_agent_outdated_committer(self):
        f = self.agents_dir / "visual-architect" / "agent.md"
        f.write_text(f.read_text(encoding="utf-8") + "\nonly the auditor commits to the branch.", encoding="utf-8")
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("agent 'visual-architect': outdated invariant — refers to Auditor as committer instead of Supervisor" in p for p in problems))


class TestAgentsValidationSelfReference(unittest.TestCase):
    """An agent may name its own bundled directory inside the plugin, and nothing else there.

    On this branch the agents are packaged under `plugins/plan/agents/`, and the visual
    agents tell the reader where their own `assets/` live in a checkout. That is not an
    external dependency — the directory travels with the agent — but a path into
    `skills/`, `lib/` or a sibling agent is.
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.agents_dir = Path(self.tmp_dir.name) / "agents"
        self.agents_dir.mkdir()
        self.graph = load()
        populate_clean_agents_directory(self.agents_dir, self.graph)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _append(self, agent: str, line: str) -> list[str]:
        f = self.agents_dir / agent / "agent.md"
        f.write_text(f.read_text(encoding="utf-8") + "\n" + line, encoding="utf-8")
        return validate_agents(self.agents_dir, self.graph)

    def test_own_bundled_directory_in_checkout_allowed(self):
        problems = self._append(
            "visual-architect",
            "Template: `plugins/plan/agents/visual-architect/assets/template.html` in a checkout.",
        )
        self.assertEqual(problems, [])

    def test_own_bundled_directory_when_installed_allowed(self):
        problems = self._append(
            "visual-architect",
            "Or `~/.gemini/config/plugins/plan/agents/visual-architect/…` when installed.",
        )
        self.assertEqual(problems, [])

    def test_sibling_agent_directory_rejected(self):
        problems = self._append("architect", "See plugins/plan/agents/engineer/agent.md for the builder.")
        self.assertTrue(any("agent 'architect': contains external reference to 'plugins/plan/'" in p for p in problems))

    def test_bare_agents_directory_rejected(self):
        problems = self._append("architect", "All roles live under plugins/plan/agents.")
        self.assertTrue(any("agent 'architect': contains external reference to 'plugins/plan/'" in p for p in problems))

    def test_plugin_lib_reference_rejected(self):
        problems = self._append("supervisor", "Schema: plugins/plan/lib/graph/STATE.md")
        self.assertTrue(any("agent 'supervisor': contains external reference to 'plugins/plan/'" in p for p in problems))

    def test_own_directory_at_end_of_sentence_allowed(self):
        problems = self._append("visual-architect", "Bundled files live in plugins/plan/agents/visual-architect.")
        self.assertEqual(problems, [])

    def test_lookalike_directory_name_rejected(self):
        problems = self._append("architect", "See plugins/plan/agents/architect.v2/agent.md.")
        self.assertTrue(any("agent 'architect': contains external reference to 'plugins/plan/'" in p for p in problems))

    def test_longer_agent_name_with_same_prefix_rejected(self):
        problems = self._append("architect", "See plugins/plan/agents/architect-extra/agent.md.")
        self.assertTrue(any("agent 'architect': contains external reference to 'plugins/plan/'" in p for p in problems))

    def test_climbing_out_of_own_directory_rejected(self):
        problems = self._append("architect", "See plugins/plan/agents/architect/../engineer/agent.md.")
        self.assertTrue(any("agent 'architect': contains external reference to 'plugins/plan/'" in p for p in problems))

    def test_own_directory_does_not_excuse_other_references(self):
        problems = self._append(
            "visual-architect",
            "Own: plugins/plan/agents/visual-architect/assets/. Also plugins/plan/skills/visual-architect/SKILL.md.",
        )
        self.assertTrue(any("agent 'visual-architect': contains external reference to 'plugins/plan/'" in p for p in problems))


class TestPluginTreeConforms(unittest.TestCase):
    """The real skills and agents shipped in this plugin satisfy the declaration."""

    def setUp(self):
        self.graph = load()

    def test_paths_are_inside_the_plugin(self):
        self.assertEqual(SKILLS_DIR, PLUGIN_ROOT / "skills")
        self.assertEqual(AGENTS_DIR, PLUGIN_ROOT / "agents")
        self.assertTrue((PLUGIN_ROOT / "graph.json").is_file())

    def test_shipped_agents_pass_validation(self):
        problems = validate_agents(AGENTS_DIR, self.graph)
        self.assertEqual(problems, [], f"plugin agents/ violate the graph invariants: {problems}")

    def test_expected_agents_match_agent_directories(self):
        present = {d.name for d in AGENTS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")}
        self.assertEqual(present, EXPECTED_AGENTS)

    def test_every_node_agent_is_an_expected_agent(self):
        for node in self.graph["nodes"]:
            if node.get("agent"):
                self.assertIn(node["agent"], EXPECTED_AGENTS, f"node {node['id']!r}")

    def test_panel_prompt_file_is_the_validator_skill(self):
        """Lens prompts live inline in each validator's SKILL.md on this branch."""
        panels = [n for n in self.graph["nodes"] if n.get("panel")]
        self.assertEqual({n["id"] for n in panels}, {"spec-validator", "plan-validator", "implementation-validator"})
        for node in panels:
            self.assertEqual(node["panel"]["prompt_file"], f"skills/{node['skill']}/SKILL.md")
            self.assertTrue((PLUGIN_ROOT / node["panel"]["prompt_file"]).is_file())

    def test_each_lens_has_its_own_prompt_section_in_skill_and_agent(self):
        """A lens that is only named, with no section of its own, is not a partition."""
        for node in self.graph["nodes"]:
            panel = node.get("panel")
            if not panel:
                continue
            for path in (PLUGIN_ROOT / panel["prompt_file"], AGENTS_DIR / node["agent"] / "agent.md"):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(text.count("### Lens "), panel["n"], f"{path}: expected one '### Lens' section per lens")
                self.assertIn("### Shared Preamble", text, str(path))
                self.assertIn("### Shared Tail", text, str(path))
                self.assertIn("Asymmetry Test", text, str(path))
                self.assertIn("Single-Vote Findings (triage required)", text, str(path))
                self.assertIn("cross_lens", text, str(path))
                self.assertIn('"lens": "' + "|".join(panel["lenses"]) + '"', text, str(path))

    def test_validator_skill_and_agent_carry_identical_lens_prompts(self):
        """The two families are kept in sync: same preamble, lenses and tail in both."""

        def block(text: str, heading: str) -> str:
            """The prompt under a heading, up to the next heading, without its fences."""
            start = text.index(heading)
            nxt = text.find("\n#", text.index("\n", start))
            body = text[start : nxt if nxt != -1 else len(text)]
            prompt = body[body.index("```\n") + 4 : body.rindex("\n```")]
            # the agent packaging inlines the JSON contract without a nested ```json fence
            return "\n".join(line for line in prompt.splitlines() if line.strip() not in ("```json", "```")).strip()

        def lens_blocks(text: str) -> list[str]:
            headings = ("### Shared Preamble", "### Lens 1", "### Lens 2", "### Lens 3", "### Shared Tail")
            return [block(text, h) for h in headings]

        for node in self.graph["nodes"]:
            if not node.get("panel"):
                continue
            skill = (PLUGIN_ROOT / node["panel"]["prompt_file"]).read_text(encoding="utf-8")
            agent = (AGENTS_DIR / node["agent"] / "agent.md").read_text(encoding="utf-8")
            self.assertEqual(lens_blocks(skill), lens_blocks(agent), f"{node['id']}: skill and agent lens prompts differ")

    def test_supervisor_family_declares_the_state_machine(self):
        """Both packagings of the Supervisor read and write state.json and name every gate."""
        for path in (SKILLS_DIR / "starter" / "SKILL.md", AGENTS_DIR / "supervisor" / "agent.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("plans/active_milestones/{moniker}/state.json", text, str(path))
            self.assertIn(self.graph["graph_version"], text, str(path))
            for gate in self.graph["gates"]:
                self.assertIn(f"`{gate['id']}`", text, f"{path}: gate {gate['id']!r} not mentioned")
            for node in self.graph["nodes"]:
                if node["kind"] in ("panel", "deliberation"):
                    self.assertIn(f"`{node['id']}`", text, f"{path}: never dispatches {node['id']!r}")
                if node.get("panel"):
                    for lens in node["panel"]["lenses"]:
                        self.assertIn(lens, text, f"{path}: lens {lens!r} of {node['id']!r} not named")
            for phase in ("1.gate", "2.gate", "4.gate"):
                self.assertIn(phase, text, f"{path}: phase {phase!r} missing")
            self.assertIn("audit_rounds", text, str(path))
            self.assertIn("skipped", text, str(path))

    def test_implementation_gate_runs_on_the_working_tree(self):
        """Only the Supervisor commits, and only after this gate: a commit range would be empty."""
        for path in (SKILLS_DIR / "starter" / "SKILL.md", AGENTS_DIR / "supervisor" / "agent.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("git diff HEAD", text, str(path))
            self.assertIn("git status --short", text, str(path))
            self.assertNotIn("{BASE}..{HEAD}", text, f"{path}: dispatches the panel on a commit range")
        for path in (
            SKILLS_DIR / "implementation-validator" / "SKILL.md",
            AGENTS_DIR / "implementation-validator" / "agent.md",
        ):
            text = path.read_text(encoding="utf-8")
            self.assertIn("git diff HEAD", text, f"{path}: no way to attack uncommitted work")

    def test_every_gate_verdict_has_a_place_in_state(self):
        """All three panels, including the per-group one, are recorded with a status."""
        import json
        import re

        text = (PLUGIN_ROOT / "lib" / "graph" / "STATE.md").read_text(encoding="utf-8")
        example = json.loads(re.search(r"```json\n(.*?)\n```", text, re.S).group(1))
        panel_fields = {"status", "report", "lenses", "confirmed", "single_vote", "cross_lens", "single_vote_triaged"}
        records = {
            "spec-validator": example["nodes"]["spec-validator"],
            "plan-validator": example["nodes"]["plan-validator"],
            "implementation-validator": example["groups"][0]["implementation_validation"],
        }
        for node in self.graph["nodes"]:
            if not node.get("panel"):
                continue
            record = records[node["id"]]
            self.assertIsInstance(record, dict, f"{node['id']}: verdict must be a record, not a bare path")
            self.assertLessEqual(panel_fields, set(record), node["id"])
            self.assertEqual(record["lenses"], node["panel"]["lenses"], node["id"])
        self.assertEqual({g["id"] for g in example["gates"]}, {g["id"] for g in self.graph["gates"]})
        self.assertEqual(example["graph_version"], self.graph["graph_version"])

        phases_documented = re.search(r"\| `phase` \|[^\n]*", text).group(0)
        self.assertIn(f"`{example['phase']}`", phases_documented)
        self.assertNotIn("`0` ·", phases_documented, "state.json is created in Phase 1; there is no phase 0 to record")
        for path in (SKILLS_DIR / "starter" / "SKILL.md", AGENTS_DIR / "supervisor" / "agent.md", AGENTS_DIR / "README.md"):
            shape = path.read_text(encoding="utf-8")
            self.assertIn('"phase": "1 | 1.gate | 2 | 2.gate | 3 | 4 | 4.gate | 5"', shape, str(path))
            self.assertIn('"implementation_validation": {', shape, str(path))

    def test_state_schema_document_matches_the_graph(self):
        text = (PLUGIN_ROOT / "lib" / "graph" / "STATE.md").read_text(encoding="utf-8")
        self.assertIn(self.graph["graph_version"], text)
        self.assertEqual(self.graph["state_file"], "plans/active_milestones/{moniker}/state.json")
        self.assertIn(self.graph["state_file"], text)
        for gate in self.graph["gates"]:
            self.assertIn(f'"id": "{gate["id"]}"', text)


class TestValidateAgainstMutatedPluginTree(unittest.TestCase):
    """`validate` catches the regressions it exists for, on a copy of the real plugin tree."""

    def setUp(self):
        self.graph = load()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name) / "plan"
        for family, filename in (("skills", "SKILL.md"), ("agents", "agent.md")):
            for src in (PLUGIN_ROOT / family).glob(f"*/{filename}"):
                dst = self.root / family / src.parent.name / filename
                dst.parent.mkdir(parents=True)
                shutil.copyfile(src, dst)
        patcher = mock.patch.multiple(
            graph_module,
            PLUGIN_ROOT=self.root,
            SKILLS_DIR=self.root / "skills",
            AGENTS_DIR=self.root / "agents",
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp_dir.cleanup)

    def _skill(self, name: str) -> Path:
        return self.root / "skills" / name / "SKILL.md"

    def test_copy_of_real_tree_is_clean(self):
        self.assertEqual(validate(self.graph), [])

    def test_reverted_identical_dispatch_is_detected(self):
        f = self._skill("plan-validator")
        f.write_text(f.read_text(encoding="utf-8") + "\nDispatch this **three times, unchanged**.\n", encoding="utf-8")
        problems = validate(self.graph)
        self.assertTrue(
            any("'plan-validator'" in p and "still dispatches identical prompts" in p for p in problems), problems
        )

    def test_missing_lens_in_prompt_file_is_detected(self):
        f = self._skill("spec-validator")
        f.write_text(f.read_text(encoding="utf-8").replace("malicious-compliance", "lazy-pass"), encoding="utf-8")
        problems = validate(self.graph)
        self.assertTrue(
            any("lens 'malicious-compliance' declared in graph.json but absent from skills/spec-validator/SKILL.md" in p for p in problems),
            problems,
        )

    def test_deleted_lens_section_is_detected_even_though_the_lens_is_still_named(self):
        """SKILL.md names every lens in passing; `validate` must still notice a missing section."""
        f = self._skill("spec-validator")
        text = f.read_text(encoding="utf-8")
        start = text.index("### Lens 3 — Malicious Compliance Skeptic")
        end = text.index("### Shared Tail")
        mutated = text[:start] + text[end:]
        self.assertIn("malicious-compliance", mutated, "the lens is still named elsewhere in the file")
        f.write_text(mutated, encoding="utf-8")
        problems = validate(self.graph)
        self.assertTrue(
            any("skills/spec-validator/SKILL.md has 2 lens prompt section(s) for 3 declared lenses" in p for p in problems),
            problems,
        )

    def test_missing_shared_frame_is_detected(self):
        f = self._skill("plan-validator")
        f.write_text(f.read_text(encoding="utf-8").replace("### Shared Tail", "### Closing Notes"), encoding="utf-8")
        problems = validate(self.graph)
        self.assertTrue(any("skills/plan-validator/SKILL.md has no 'Shared Tail' section" in p for p in problems), problems)

    def test_verdicts_not_tagged_with_declared_lenses_is_detected(self):
        f = self._skill("implementation-validator")
        f.write_text(
            f.read_text(encoding="utf-8").replace('"lens": "claim-vs-reality|failure-paths|blast-radius"', '"lens": "any"'),
            encoding="utf-8",
        )
        problems = validate(self.graph)
        self.assertTrue(
            any("skills/implementation-validator/SKILL.md does not tag skeptic verdicts with the declared lenses" in p for p in problems),
            problems,
        )

    def test_lens_section_count(self):
        self.assertEqual(lens_section_count("## Lens 1 — A\n\n### Lens 2 — B\n#### Lens: c\n"), 3)
        self.assertEqual(lens_section_count("Lens 1 is named in prose.\n# Lens top-level title\n"), 0)
        self.assertEqual(lens_section_count("### Lenses overview\n"), 0)

    def test_missing_prompt_file_is_detected(self):
        self._skill("implementation-validator").unlink()
        problems = validate(self.graph)
        self.assertTrue(any("skills/implementation-validator/SKILL.md not found" in p for p in problems), problems)

    def test_missing_agent_is_detected(self):
        (self.root / "agents" / "auditor" / "agent.md").unlink()
        problems = validate(self.graph)
        self.assertTrue(any("node 'auditor': agents/auditor/agent.md not found" in p for p in problems), problems)

    def test_missing_alternative_skill_is_detected(self):
        self._skill("visual-architect").unlink()
        problems = validate(self.graph)
        self.assertTrue(any("alternative skills/visual-architect/SKILL.md not found" in p for p in problems), problems)


class TestValidateContracts(unittest.TestCase):
    """Topology and write-contract checks on altered copies of the declaration."""

    def setUp(self):
        self.graph = load()

    def _copy(self) -> dict:
        import copy

        return copy.deepcopy(self.graph)

    def test_lens_count_must_match_n(self):
        g = self._copy()
        by_id(g)["plan-validator"]["panel"]["lenses"].pop()
        self.assertTrue(any("panel.n=3 but 2 lenses declared" in p for p in validate(g)))

    def test_duplicate_lens_rejected(self):
        g = self._copy()
        lenses = by_id(g)["plan-validator"]["panel"]["lenses"]
        lenses[2] = lenses[0]
        self.assertTrue(any("'plan-validator': duplicate lens name" in p for p in validate(g)))

    def test_only_engineer_and_simplifier_may_write_source(self):
        g = self._copy()
        by_id(g)["architect"]["writes"].append("<repo source>")
        self.assertTrue(any("node 'architect' declares it writes repository source" in p for p in validate(g)))

    def test_only_a_starter_held_node_may_commit(self):
        g = self._copy()
        by_id(g)["auditor"]["writes"].append("git commit")
        self.assertTrue(any("node 'auditor' declares it commits but is not held by starter" in p for p in validate(g)))

    def test_unreachable_node_rejected(self):
        g = self._copy()
        g["edges"] = [e for e in g["edges"] if e["to"] != "simplifier"]
        self.assertTrue(any("node 'simplifier' has no inbound edge" in p for p in validate(g)))

    def test_declared_counts(self):
        """The numbers quoted in the READMEs."""
        order = {n["id"]: i for i, n in enumerate(self.graph["nodes"])}
        feedback = [e for e in self.graph["edges"] if order[e["to"]] < order[e["from"]]]
        self.assertEqual(len(self.graph["nodes"]), 16)
        self.assertEqual(len(self.graph["edges"]), 25)
        self.assertEqual(len(feedback), 6)
        self.assertEqual(len(self.graph["gates"]), 2)
        self.assertEqual(len(self.graph["invariants"]), 5)


class TestSync(unittest.TestCase):
    """`sync` rewrites generated blocks, `sync --check` reports stale ones."""

    def setUp(self):
        self.graph = load()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.tmp = Path(self.tmp_dir.name)
        self.readme = self.tmp / "README.md"

    def _sync(self, targets, check):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(graph_module, "TARGETS", targets), redirect_stdout(out), redirect_stderr(err):
            code = sync(self.graph, check=check)
        return code, out.getvalue(), err.getvalue()

    def test_stale_block_is_reported_then_rewritten(self):
        self.readme.write_text(
            f"# Title\n\n{graph_module.BEGIN}\nhand-edited diagram\n{graph_module.END}\n\ntail\n", encoding="utf-8"
        )
        targets = [(self.readme, "ascii")]

        code, _, err = self._sync(targets, check=True)
        self.assertEqual(code, 1)
        self.assertIn("out of date", err)
        self.assertIn("hand-edited diagram", self.readme.read_text(encoding="utf-8"), "--check must not write")

        code, _, _ = self._sync(targets, check=False)
        self.assertEqual(code, 0)
        text = self.readme.read_text(encoding="utf-8")
        self.assertNotIn("hand-edited diagram", text)
        self.assertIn(render_ascii(self.graph), text)
        self.assertIn(f"graph_version: {self.graph['graph_version']}", text)
        self.assertTrue(text.startswith("# Title\n") and text.endswith("\ntail\n"), "text outside the block is preserved")

        code, _, _ = self._sync(targets, check=True)
        self.assertEqual(code, 0)

    def test_missing_markers_are_reported(self):
        self.readme.write_text("# Title\n\nno generated block here\n", encoding="utf-8")
        code, _, err = self._sync([(self.readme, "ascii")], check=True)
        self.assertEqual(code, 1)
        self.assertIn("no generated block", err)

    def test_missing_readme_is_reported(self):
        code, _, err = self._sync([(self.readme, "ascii")], check=True)
        self.assertEqual(code, 1)
        self.assertIn("missing", err)


class TestSyncTargets(unittest.TestCase):
    """The repository README is a target exactly when the plugin sits in a checkout."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.repo = Path(self.tmp_dir.name) / "somewhere"
        self.plugin = self.repo / "plugins" / "plan"
        (self.plugin / "agents").mkdir(parents=True)

    def test_checkout_includes_the_repository_readme(self):
        (self.repo / ".git").mkdir()
        self.assertTrue(is_checkout(self.repo, self.plugin))
        self.assertEqual(
            sync_targets(self.repo, self.plugin),
            [
                (self.plugin / "README.md", "ascii"),
                (self.plugin / "agents" / "README.md", "ascii"),
                (self.repo / "README.md", "ascii"),
            ],
        )

    def test_git_worktree_counts_as_a_checkout(self):
        (self.repo / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n", encoding="utf-8")
        self.assertTrue(is_checkout(self.repo, self.plugin))

    def test_installed_plugin_excludes_whatever_readme_sits_above_it(self):
        """No repository around the plugin: an unrelated README two levels up is not ours."""
        (self.repo / "README.md").write_text("# someone else's notes\n", encoding="utf-8")
        self.assertFalse(is_checkout(self.repo, self.plugin))
        self.assertEqual(
            sync_targets(self.repo, self.plugin),
            [(self.plugin / "README.md", "ascii"), (self.plugin / "agents" / "README.md", "ascii")],
        )

    def test_plugin_outside_plugins_plan_is_not_a_checkout(self):
        (self.repo / ".git").mkdir()
        elsewhere = self.repo / "vendor" / "plan"
        elsewhere.mkdir(parents=True)
        self.assertFalse(is_checkout(self.repo, elsewhere))

    def test_missing_repository_readme_fails_in_a_checkout(self):
        """Deleting or renaming the repository README must not pass `sync --check` silently."""
        (self.repo / ".git").mkdir()
        graph = load()
        targets = sync_targets(self.repo, self.plugin)
        for path, _flavor in targets[:2]:
            path.write_text(f"{graph_module.BEGIN}\n{graph_module.END}\n", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(graph_module, "TARGETS", targets), redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(sync(graph, check=False), 1, "the plugin READMEs are written, the missing one is reported")
            code = sync(graph, check=True)
        self.assertEqual(code, 1)
        self.assertEqual(err.getvalue().count(f"{self.repo / 'README.md'}: missing"), 2)
        self.assertNotIn("out of date", err.getvalue(), "the first sync brought the plugin READMEs up to date")

    def test_this_tree_declares_the_expected_targets(self):
        expected = [(PLUGIN_ROOT / "README.md", "ascii"), (AGENTS_DIR / "README.md", "ascii")]
        if is_checkout():
            expected.append((graph_module.REPO_ROOT / "README.md", "ascii"))
        self.assertEqual(graph_module.TARGETS, expected)


class TestCLIInvocations(unittest.TestCase):
    """Tests for CLI subcommand invocations via main(argv)."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.agents_dir = Path(self.tmp_dir.name) / "agents"
        self.agents_dir.mkdir()
        self.graph = load()
        populate_clean_agents_directory(self.agents_dir, self.graph)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_cli_validate_agents_valid(self):
        stdout_buf = io.StringIO()
        with redirect_stdout(stdout_buf):
            exit_code = main(["validate-agents", "--agents-dir", str(self.agents_dir)])
        self.assertEqual(exit_code, 0)
        self.assertIn("agents/ OK — all 13 subagents conformant to graph engineering specifications", stdout_buf.getvalue())

    def test_cli_validate_agents_invalid(self):
        shutil.rmtree(self.agents_dir / "auditor")
        stderr_buf = io.StringIO()
        with redirect_stderr(stderr_buf):
            exit_code = main(["validate-agents", "--agents-dir", str(self.agents_dir)])
        self.assertEqual(exit_code, 1)
        self.assertIn("problem(s) in", stderr_buf.getvalue())
        self.assertIn("missing expected agent directory(s): auditor", stderr_buf.getvalue())

    def test_cli_validate_with_agents_dir_valid(self):
        stdout_buf = io.StringIO()
        with redirect_stdout(stdout_buf):
            exit_code = main(["validate", "--agents-dir", str(self.agents_dir)])
        self.assertEqual(exit_code, 0)
        output = stdout_buf.getvalue()
        self.assertIn("graph.json OK", output)
        self.assertIn("agents/ OK — all 13 subagents conformant to graph engineering specifications", output)

    def test_cli_validate_with_agents_dir_invalid(self):
        shutil.rmtree(self.agents_dir / "auditor")
        stderr_buf = io.StringIO()
        with redirect_stderr(stderr_buf):
            exit_code = main(["validate", "--agents-dir", str(self.agents_dir)])
        self.assertEqual(exit_code, 1)
        self.assertIn("problem(s):", stderr_buf.getvalue())
        self.assertIn("missing expected agent directory(s): auditor", stderr_buf.getvalue())

    def test_cli_validate_standard(self):
        stdout_buf = io.StringIO()
        with redirect_stdout(stdout_buf):
            exit_code = main(["validate"])
        self.assertEqual(exit_code, 0)
        self.assertIn("graph.json OK", stdout_buf.getvalue())

    def test_cli_validate_bare_agents_dir_uses_plugin_agents(self):
        stdout_buf = io.StringIO()
        with redirect_stdout(stdout_buf):
            exit_code = main(["validate", "--agents-dir"])
        self.assertEqual(exit_code, 0)
        self.assertIn("graph.json OK", stdout_buf.getvalue())
        self.assertIn("agents/ OK", stdout_buf.getvalue())

    def test_cli_validate_agents_defaults_to_plugin_agents(self):
        stdout_buf = io.StringIO()
        with redirect_stdout(stdout_buf):
            exit_code = main(["validate-agents"])
        self.assertEqual(exit_code, 0)
        self.assertIn("agents/ OK", stdout_buf.getvalue())

    def test_cli_render_each_flavor(self):
        for flavor, marker in (("ascii", "```text"), ("mermaid", "flowchart TD"), ("svg", "<svg")):
            stdout_buf = io.StringIO()
            with redirect_stdout(stdout_buf):
                exit_code = main(["render", flavor])
            self.assertEqual(exit_code, 0)
            self.assertIn(marker, stdout_buf.getvalue())

    def test_cli_sync_check_is_clean(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            exit_code = main(["sync", "--check"])
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
