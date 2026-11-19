#!/usr/bin/env python3
"""Unit and integration tests for workflow-trajectory."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

import generator  # noqa: E402
from workflow_ast import analyze_workflow_script  # noqa: E402
from workflow_telemetry import (  # noqa: E402
    list_workflow_runs,
    parse_script_only,
    parse_workflow_run,
    select_workflow_run,
)
from workflow_timeline import (  # noqa: E402
    compute_worker_concurrency,
    format_duration,
    segment_worker_turns,
)


def _write_transcript(agy_dir: str, conv_id: str, steps: list[dict]) -> None:
    logs_dir = os.path.join(agy_dir, "brain", conv_id, ".system_generated", "logs")
    os.makedirs(logs_dir, exist_ok=True)
    with open(os.path.join(logs_dir, "transcript_full.jsonl"), "w", encoding="utf-8") as f:
        for s in steps:
            f.write(json.dumps(s) + "\n")


def _write_task_log(agy_dir: str, conv_id: str, task_name: str, text: str) -> str:
    tasks_dir = os.path.join(agy_dir, "brain", conv_id, ".system_generated", "tasks")
    os.makedirs(tasks_dir, exist_ok=True)
    p = os.path.join(tasks_dir, f"{task_name}.log")
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def _create_db(agy_dir: str, rows: list[tuple]) -> None:
    os.makedirs(agy_dir, exist_ok=True)
    db_path = os.path.join(agy_dir, "conversation_summaries.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE conversation_summaries (
            conversation_id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            agent_name TEXT NOT NULL DEFAULT '',
            parent_conversation_id TEXT NOT NULL DEFAULT '',
            nesting_depth INTEGER NOT NULL DEFAULT 0,
            step_count INTEGER NOT NULL DEFAULT 0,
            last_modified_time TEXT NOT NULL DEFAULT '',
            workspace_uris TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT '',
            killed INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.executemany("INSERT INTO conversation_summaries VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


class WorkflowTrajectoryTests(unittest.TestCase):
    def _assert_html_js_renders(self, html: str) -> None:
        """If node is available, verify embedded JS compiles and populates panels cleanly."""
        node_bin = shutil.which("node")
        if not node_bin:
            return
        m = re.search(r"<script>([\s\S]*)</script>", html)
        self.assertIsNotNone(m)
        js_harness = r"""
const vm = require("vm");
const fs = require("fs");
const code = fs.readFileSync(process.argv[2], "utf8");
const els = {};
const mk = (id) => ({
  id, textContent: "", innerHTML: "", value: "", className: "", style: {},
  classList: { add(){}, remove(){}, toggle(){} },
  addEventListener(){},
});
const ctx = {
  document: {
    getElementById: (id) => els[id] || (els[id] = mk(id)),
    querySelectorAll: () => [],
    addEventListener: () => {},
  },
  navigator: { clipboard: { writeText: async () => {} } },
  setTimeout: () => {},
  Number, String, Math, Array, Object, Boolean, JSON, console,
};
vm.runInNewContext(code, ctx);
for (const id of ["outcomeBadge", "verifyBadge", "runTitle", "summaryGrid", "blueprintPanel", "verificationPanel"]) {
  const el = els[id];
  if (!el || Math.max(el.textContent.length, el.innerHTML.length) === 0) {
    throw new Error("Empty rendered DOM element: " + id);
  }
}
"""
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as jf:
            jf.write(m.group(1))
            js_path = jf.name
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as hf:
            hf.write(js_harness)
            harness_path = hf.name
        try:
            proc = subprocess.run([node_bin, harness_path, js_path], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"JS render failed: {proc.stderr}\n{proc.stdout}")
        finally:
            os.unlink(js_path)
            os.unlink(harness_path)

    def test_ast_parses_top_level_await_phases_parallel_pipeline_tools_and_warnings(self) -> None:
        script = '''
import json
target = args.get("target", "src")

phase("Discover")
prev = await trajectory(tools=["run_command"], last=10)
out = await call_tool("read_file", Path="README.md")

phase("Fix")
fixes = await parallel(
    ["a.py", "b.py"],
    lambda f: agent(
        f"Fix bugs in {f}. Follow the simplifier skill.",
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        role=f"Fix {f}",
        type_name="engineer",
    ),
)

unused = agent("Never awaited agent", schema={"type": "string"})

phase("Audit")
auditor = agent("Audit fixes.", role="Auditor", type_name="auditor", model="pro")
verdict = await auditor(f"Check {fixes}", {"type": "object", "properties": {"passed": {"type": "boolean"}}})
'''
        bp = analyze_workflow_script(script)
        self.assertTrue(bp["available"])
        self.assertIsNone(bp["parse_error"])
        self.assertEqual(bp["args_keys"], ["target"])
        self.assertEqual(bp["counts"]["phases"], 3)
        self.assertEqual(bp["counts"]["parallel_blocks"], 1)
        self.assertEqual(bp["counts"]["tool_calls"], 1)
        self.assertEqual(bp["counts"]["trajectory_calls"], 1)
        self.assertEqual(bp["counts"]["agents"], 3)
        self.assertIn("simplifier", bp["skills_declared"])
        self.assertIn("agent:engineer", bp["skills_declared"])
        self.assertIn("agent:auditor", bp["skills_declared"])
        warn_codes = {w["code"] for w in bp["warnings"]}
        self.assertIn("unawaited_agent", warn_codes)
        self.assertIn("parallel_inherit_write", warn_codes)
        self.assertIn("parallel_default_model", warn_codes)
        self.assertNotIn("no_verify_stage", warn_codes)

        # Read-only parallel research + Verify phase should produce zero false-positive warnings
        ro_bp = analyze_workflow_script(
            'phase("Inspect")\n'
            'await parallel(["a.py"], lambda p: agent(f"Read {p}. Do not edit anything.", role=f"Read {p}", type_name="research", model="flash_lite"))\n'
            'phase("Verify")\n'
            'v = agent("Verify summaries", role="Workflow Verifier", type_name="research", model="flash_lite")\n'
            'await v("Check all")\n'
        )
        ro_warns = {w["code"] for w in ro_bp["warnings"]}
        self.assertNotIn("parallel_inherit_write", ro_warns)
        self.assertNotIn("no_verify_stage", ro_warns)
        self.assertEqual(ro_warns, set())

    def test_timeline_turns_and_concurrency(self) -> None:
        self.assertEqual(format_duration(0), "0s")
        self.assertEqual(format_duration(125), "2m 5s")
        steps = [
            {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-19T10:00:00Z", "content": "Turn 1 prompt"},
            {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-11-19T10:00:30Z", "input_tokens": 100, "output_tokens": 20, "cache_read_tokens": 50, "tool_calls": [{"name": "finish", "args": {}}]},
            {"step_index": 2, "type": "USER_INPUT", "created_at": "2026-11-19T10:01:00Z", "content": "Turn 2 prompt"},
            {"step_index": 3, "type": "PLANNER_RESPONSE", "created_at": "2026-11-19T10:01:20Z", "input_tokens": 120, "output_tokens": 30, "cache_read_tokens": 100, "tool_calls": [{"name": "finish", "args": {}}]},
        ]
        turns = segment_worker_turns(steps)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["duration_s"], 30.0)
        self.assertEqual(turns[1]["duration_s"], 20.0)

        conc = compute_worker_concurrency([
            {"turns": [{"start_ms": 0, "end_ms": 20_000}]},
            {"turns": [{"start_ms": 5_000, "end_ms": 25_000}]},
        ])
        self.assertEqual(conc["peak_concurrency"], 2)
        self.assertGreater(conc["parallelism_speedup"], 1.5)

    def test_pre_run_blueprint_cli_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "proj")
            os.makedirs(ws)
            wf_dir = os.path.join(ws, "my_wf")
            os.makedirs(wf_dir)
            script_path = os.path.join(wf_dir, "workflow.py")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(
                    'phase("Scan")\n'
                    'res = await parallel(args.get("files", []), lambda p: agent(f"Scan {p}", {"type": "string"}, role=f"Scan {p}", model="flash_lite"))\n'
                )
            with open(os.path.join(wf_dir, "workflow.json"), "w", encoding="utf-8") as f:
                json.dump({"name": "scanner", "description": "Parallel File Scanner"}, f)

            data = parse_script_only(script_path, ws)
            self.assertEqual(data["mode"], "blueprint")
            self.assertEqual(data["run_title"], "Parallel File Scanner")
            self.assertEqual(data["blueprint"]["counts"]["parallel_blocks"], 1)

            out_html = os.path.join(ws, ".agents", "workflow-trajectory.html")
            rc = generator.main(["--script", script_path, "-w", ws, "-o", out_html, "--no-git"])
            self.assertEqual(rc, 0)
            with open(out_html, encoding="utf-8") as f:
                html = f.read()
            self.assertNotIn("__TELEMETRY_DATA_PLACEHOLDER__", html)
            self._assert_html_js_renders(html)

    def test_post_run_linking_orphan_children_skills_verification_and_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "proj")
            agy = os.path.join(tmp, "agy")
            os.makedirs(ws)
            uri = json.dumps([f"file://{ws}"])

            parent_id = "aaaa1111-0000-0000-0000-000000000001"
            author_id = "bbbb2222-0000-0000-0000-000000000002"
            verifier_id = "cccc3333-0000-0000-0000-000000000003"

            # Mirror real AGY behavior: workflow child agents have parent_conversation_id == "" and nesting_depth == 0!
            _create_db(
                agy,
                [
                    (parent_id, "Run Workflow Test", "", "", 0, 10, "2026-11-19 15:05:00+00:00", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (author_id, "", "engineer", "", 0, 5, "2026-11-19 15:02:00+00:00", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (verifier_id, "", "auditor", "", 0, 6, "2026-11-19 15:04:00+00:00", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                ],
            )

            script_src = (
                'phase("Build")\n'
                'out = await agent("Build widget", {"type": "string"}, role="Widget Author", type_name="engineer", model="flash")\n'
                'phase("Verify")\n'
                'v = agent("Verify widget", role="Widget Verifier", type_name="auditor", model="flash")\n'
                'ok = await v(f"Check {out}", {"type": "object", "properties": {"passed": {"type": "boolean"}}})\n'
                'print("DONE:", ok)\n'
            )

            task_log = (
                "- [phase] Build\n"
                f"- [agent:engineer] Widget Author: done ({author_id}): Built widget...\n"
                "- [phase] Verify\n"
                f'- [agent:auditor] Widget Verifier: done, turn 1 ({verifier_id}): {{"passed": true}}\n'
                "Output:\n"
                "DONE: {'passed': True}\n"
            )
            log_path = _write_task_log(agy, parent_id, "task-2", task_log)

            _write_transcript(
                agy,
                parent_id,
                [
                    {"step_index": 0, "type": "USER_INPUT", "source": "USER_EXPLICIT", "created_at": "2026-11-19T15:00:00Z", "content": "Run workflow"},
                    {
                        "step_index": 1,
                        "type": "PLANNER_RESPONSE",
                        "source": "MODEL",
                        "created_at": "2026-11-19T15:00:05Z",
                        "model": "gemini-4-neon-high",
                        "tool_calls": [
                            {
                                "name": "run_workflow",
                                "args": {
                                    "Script": script_src,
                                    "Description": "Build & Verify <script>alert(1)</script>",
                                    "Args": {"module": "widget"},
                                },
                            }
                        ],
                    },
                    {
                        "step_index": 2,
                        "type": "GENERIC",
                        "source": "MODEL",
                        "status": "RUNNING",
                        "created_at": "2026-11-19T15:00:06Z",
                        "content": f"Tool is running as a background task with task id: {parent_id}/task-2\nTask logs are available at: file://{log_path}",
                    },
                    {
                        "step_index": 3,
                        "type": "SYSTEM_MESSAGE",
                        "source": "SYSTEM",
                        "created_at": "2026-11-19T15:04:10Z",
                        "content": f'Task id "{parent_id}/task-2" finished with result:\nWorkflow "Build & Verify <script>alert(1)</script>" completed.\nLogs:\n{task_log}',
                    },
                ],
            )

            _write_transcript(
                agy,
                author_id,
                [
                    {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-19T15:00:10Z", "content": "Build widget"},
                    {
                        "step_index": 1,
                        "type": "PLANNER_RESPONSE",
                        "created_at": "2026-11-19T15:00:30Z",
                        "model": "gemini-3.5-flash",
                        "input_tokens": 500,
                        "output_tokens": 120,
                        "cache_read_tokens": 1000,
                        "tool_calls": [
                            {"name": "read_file", "args": {"Path": "/Users/x/.gemini/config/skills/simplifier/SKILL.md"}},
                            {"name": "write_file", "args": {"Path": os.path.join(ws, "src", "widget.py")}},
                        ],
                    },
                    {
                        "step_index": 2,
                        "type": "PLANNER_RESPONSE",
                        "created_at": "2026-11-19T15:01:30Z",
                        "model": "gemini-3.5-flash",
                        "input_tokens": 400,
                        "output_tokens": 80,
                        "cache_read_tokens": 1200,
                        "tool_calls": [{"name": "finish", "args": {"result": "Implemented src/widget.py cleanly."}}],
                    },
                ],
            )

            _write_transcript(
                agy,
                verifier_id,
                [
                    {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-19T15:02:00Z", "content": "Check widget"},
                    {
                        "step_index": 1,
                        "type": "PLANNER_RESPONSE",
                        "created_at": "2026-11-19T15:02:30Z",
                        "model": "gemini-3.5-flash",
                        "input_tokens": 600,
                        "output_tokens": 90,
                        "cache_read_tokens": 1500,
                        "tool_calls": [{"name": "run_command", "args": {"CommandLine": "pytest -q"}}],
                    },
                    {"step_index": 2, "type": "GENERIC", "created_at": "2026-11-19T15:03:00Z", "content": "Command exited with code 0.\n4 passed"},
                    {
                        "step_index": 3,
                        "type": "PLANNER_RESPONSE",
                        "created_at": "2026-11-19T15:03:40Z",
                        "model": "gemini-3.5-flash",
                        "input_tokens": 300,
                        "output_tokens": 70,
                        "cache_read_tokens": 1600,
                        "tool_calls": [{"name": "finish", "args": {"result": {"passed": True, "notes": "All 4 tests passed."}}}],
                    },
                ],
            )

            # Resolve upward from child workflow worker UUID prefix!
            self.assertEqual(select_workflow_run(agy, ws, "bbbb2222"), parent_id)
            runs = list_workflow_runs(agy, ws)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["worker_count"], 2)

            data = parse_workflow_run(agy, parent_id, ws, include_git=False)
            self.assertEqual(data["summary"]["outcome"], "completed")
            self.assertEqual(data["summary"]["done_workers"], 2)
            self.assertEqual(data["summary"]["unique_file_count"], 1)
            self.assertEqual(data["verification"]["verdict"], "VERIFIED")
            self.assertEqual(data["verification"]["passed_count"], 2)  # 1 pytest + 1 structured verdict
            self.assertTrue(data["verification"]["ordered_after_edits"])
            self.assertIn("simplifier", data["inventory"]["skills_observed"])
            self.assertIn("agent:engineer", data["inventory"]["skills_observed"])

            out_html = os.path.join(ws, ".agents", "workflow-trajectory.html")
            rc = generator.main(["--agy-dir", agy, "-w", ws, "-c", "bbbb2222", "-o", out_html, "--no-git"])
            self.assertEqual(rc, 0)
            with open(out_html, encoding="utf-8") as f:
                html = f.read()
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertIn("\\/script>", html)
            self._assert_html_js_renders(html)

    def test_stale_and_failed_verification_verdicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "proj")
            agy = os.path.join(tmp, "agy")
            os.makedirs(ws)
            uri = json.dumps([f"file://{ws}"])

            parent_id = "dddd4444-0000-0000-0000-000000000001"
            author_id = "eeee5555-0000-0000-0000-000000000002"
            verifier_id = "ffff6666-0000-0000-0000-000000000003"
            _create_db(
                agy,
                [(parent_id, "Stale Workflow", "", "", 0, 4, "2026-11-19 16:10:00+00:00", uri, "CASCADE_RUN_STATUS_IDLE", 0)],
            )
            log_text = (
                "- [phase] Check\n"
                f'- [agent:auditor] Verifier: done ({verifier_id}): {{"passed": true}}\n'
                "- [phase] LateEdit\n"
                f"- [agent:engineer] Author: done ({author_id}): tweaked\n"
            )
            _write_transcript(
                agy,
                parent_id,
                [
                    {
                        "step_index": 0,
                        "type": "PLANNER_RESPONSE",
                        "created_at": "2026-11-19T16:00:00Z",
                        "tool_calls": [{"name": "run_workflow", "args": {"Script": 'phase("Check")', "Description": "Stale Check"}}],
                    },
                    {
                        "step_index": 1,
                        "type": "GENERIC",
                        "created_at": "2026-11-19T16:09:00Z",
                        "content": f'Workflow "Stale Check" completed.\nLogs:\n{log_text}',
                    },
                ],
            )
            _write_transcript(
                agy,
                verifier_id,
                [
                    {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-19T16:01:00Z", "content": "Verify"},
                    {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-11-19T16:02:00Z", "model": "gemini-3.5-flash", "tool_calls": [{"name": "finish", "args": {"result": {"passed": True}}}]},
                ],
            )
            _write_transcript(
                agy,
                author_id,
                [
                    {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-19T16:05:00Z", "content": "Edit later"},
                    {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-11-19T16:07:00Z", "model": "gemini-3.5-flash", "tool_calls": [{"name": "edit_file", "args": {"Path": os.path.join(ws, "app.py")}}]},
                    {"step_index": 2, "type": "PLANNER_RESPONSE", "created_at": "2026-11-19T16:08:00Z", "model": "gemini-3.5-flash", "tool_calls": [{"name": "finish", "args": {"result": "edited"}}]},
                ],
            )

            data = parse_workflow_run(agy, parent_id, ws, include_git=False)
            self.assertEqual(data["verification"]["verdict"], "STALE")
            self.assertFalse(data["verification"]["ordered_after_edits"])

            # Now simulate failed structured verdict
            _write_transcript(
                agy,
                verifier_id,
                [
                    {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-19T16:09:00Z", "content": "Verify"},
                    {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-11-19T16:09:30Z", "model": "gemini-3.5-flash", "tool_calls": [{"name": "finish", "args": {"result": {"passed": False, "notes": "Broken import"}}}]},
                ],
            )
            data2 = parse_workflow_run(agy, parent_id, ws, include_git=False)
            self.assertEqual(data2["verification"]["verdict"], "FAILED")
            self.assertEqual(data2["verification"]["unresolved_failure_count"], 1)

            # Now simulate a subsequent remediation & re-verification phase starting after the earlier failure
            remed_id = "cccc3333-0000-0000-0000-000000000004"
            _write_transcript(
                agy,
                parent_id,
                [
                    {
                        "step_index": 0,
                        "type": "PLANNER_RESPONSE",
                        "created_at": "2026-11-19T16:00:00Z",
                        "tool_calls": [
                            {"name": "run_workflow", "args": {"Description": "Remediated test", "Script": 'phase("Run")'}}
                        ],
                    },
                    {
                        "step_index": 1,
                        "type": "GENERIC",
                        "created_at": "2026-11-19T16:12:00Z",
                        "content": (
                            'Workflow "Remediated test" completed.\n'
                            "Logs:\n"
                            "- [phase] Run\n"
                            f"- [agent:auditor] Reviewer: done ({verifier_id}): failed\n"
                            f"- [agent:engineer] Author: done ({author_id}): edited\n"
                            f"- [agent:auditor] Remediation Verifier: done ({remed_id}): success\n"
                        ),
                    },
                ],
            )
            _write_transcript(
                agy,
                remed_id,
                [
                    {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-19T16:10:00Z", "content": "Fix and re-verify"},
                    {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-11-19T16:11:00Z", "model": "gemini-3.5-flash", "tool_calls": [{"name": "finish", "args": {"result": {"status": "SUCCESS", "notes": "Fixed and passed"}}}]},
                ],
            )
            data3 = parse_workflow_run(agy, parent_id, ws, include_git=False)
            self.assertEqual(data3["verification"]["verdict"], "VERIFIED")
            self.assertEqual(data3["verification"]["unresolved_failure_count"], 0)
            self.assertEqual(data3["verification"]["resolved_earlier_failure_count"], 1)
            remed_sv = [sv for sv in data3["verification"]["structured_verdicts"] if not sv["passed"]][0]
            self.assertTrue(remed_sv["remediated"])


if __name__ == "__main__":
    unittest.main()
