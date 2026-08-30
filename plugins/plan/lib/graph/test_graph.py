#!/usr/bin/env python3
"""Comprehensive test suite for plugins/plan/lib/graph/graph.py."""

from __future__ import annotations

import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from plugins.plan.lib.graph.graph import (
    EXPECTED_AGENTS,
    FORBIDDEN_CORRELATED_PHRASES,
    by_id,
    load,
    main,
    phases,
    render_ascii,
    render_mermaid,
    sync,
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

    def test_sync_check(self):
        result = sync(self.graph, check=True)
        self.assertEqual(result, 0)

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
    """Invariant 1: Exact 13 subagents, no missing agents, no extra transport shells."""

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
        (self.agents_dir / "geap-interactions-caller").mkdir()
        problems = validate_agents(self.agents_dir, self.graph)
        self.assertTrue(any("unexpected agent directory(s): geap-interactions-caller" in p for p in problems))

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


if __name__ == "__main__":
    unittest.main()
