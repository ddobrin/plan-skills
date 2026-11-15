#!/usr/bin/env python3
"""Unit and integration tests for teamwork-trajectory."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

import generator  # noqa: E402
from telemetry import list_agy_runs, parse_agy_run, parse_legacy_agents_dir, select_agy_run  # noqa: E402
from timeline import compute_gantt_layout, compute_peak_concurrency, format_duration, segment_active_turns  # noqa: E402


def _write_transcript(agy_dir: str, conv_id: str, steps: list[dict]) -> None:
    logs_dir = os.path.join(agy_dir, "brain", conv_id, ".system_generated", "logs")
    os.makedirs(logs_dir, exist_ok=True)
    with open(os.path.join(logs_dir, "transcript_full.jsonl"), "w", encoding="utf-8") as f:
        for s in steps:
            f.write(json.dumps(s) + "\n")


def _create_db(agy_dir: str, rows: list[tuple]) -> None:
    os.makedirs(agy_dir, exist_ok=True)
    db_path = os.path.join(agy_dir, "conversation_summaries.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE conversation_summaries (
            conversation_id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            preview TEXT NOT NULL DEFAULT '',
            step_count INTEGER NOT NULL DEFAULT 0,
            last_modified_time TEXT NOT NULL DEFAULT '',
            workspace_uris TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            project_id TEXT NOT NULL DEFAULT '',
            agent_name TEXT NOT NULL DEFAULT '',
            parent_conversation_id TEXT NOT NULL DEFAULT '',
            nesting_depth INTEGER NOT NULL DEFAULT 0,
            killed INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO conversation_summaries (
            conversation_id, title, agent_name, parent_conversation_id,
            nesting_depth, step_count, last_modified_time, workspace_uris, status, killed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


class TeamworkTrajectoryTests(unittest.TestCase):
    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(0), "0s")
        self.assertEqual(format_duration(0.4), "<1s")
        self.assertEqual(format_duration(75), "1m 15s")
        self.assertEqual(format_duration(3665), "1h 1m 5s")

    def test_segment_active_turns_splits_idle_human_pause(self) -> None:
        steps = [
            {"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "created_at": "2026-10-23T10:00:00Z", "content": "start"},
            {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-10-23T10:02:00Z", "content": "done round 1", "tool_calls": []},
            {"step_index": 2, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-10-23T15:00:00Z", "content": "[Message] timestamp=2026-10-23T15:00:00Z sender=root content=fix"},
            {"step_index": 3, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-10-23T15:03:00Z", "content": "fixed", "tool_calls": []},
        ]
        turns = segment_active_turns(steps)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["duration_s"], 120.0)
        self.assertEqual(turns[1]["duration_s"], 180.0)

    def test_agy_tree_wall_clock_parallelism_and_gantt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "proj")
            agy = os.path.join(tmp, "agy")
            os.makedirs(ws)
            uri = json.dumps([f"file://{ws}"])

            root_id = "11111111-1111-1111-1111-111111111111"
            c1_id = "22222222-2222-2222-2222-222222222222"
            c2_id = "33333333-3333-3333-3333-333333333333"
            g1_id = "44444444-4444-4444-4444-444444444444"

            _create_db(
                agy,
                [
                    (root_id, "Build Feature", "", "", 0, 10, "2026-10-23T12:15:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (c1_id, "", "plan-validator", root_id, 1, 5, "2026-10-23T10:04:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (c2_id, "", "architect", root_id, 1, 5, "2026-10-23T10:04:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (g1_id, "", "research", c1_id, 2, 3, "2026-10-23T10:03:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                ],
            )

            _write_transcript(agy, root_id, [
                {"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "created_at": "2026-10-23T10:00:00Z", "content": "Run swarm"},
                {
                    "step_index": 1,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "created_at": "2026-10-23T10:00:30Z",
                    "input_tokens": 1000,
                    "output_tokens": 200,
                    "tool_calls": [
                        {"name": "invoke_subagent", "args": {"TypeName": "plan-validator", "Role": "Validator", "Model": "pro", "Prompt": "Validate plan"}},
                        {"name": "invoke_subagent", "args": {"TypeName": "architect", "Role": "Architect", "Model": "pro", "Prompt": "Draft plan"}},
                    ],
                },
                {
                    "step_index": 2,
                    "source": "MODEL",
                    "type": "GENERIC",
                    "created_at": "2026-10-23T10:00:32Z",
                    "content": f'Created the following subagents:\n{{"conversationId": "{c1_id}"}}\n{{"conversationId": "{c2_id}"}}',
                },
                {"step_index": 3, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-10-23T10:00:35Z", "content": "Dispatched.", "tool_calls": []},
                {"step_index": 4, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-10-23T12:14:00Z", "content": "[Message] timestamp=2026-10-23T12:14:00Z sender=user content=resume"},
                {"step_index": 5, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-10-23T12:15:00Z", "content": "All done.</script>", "tool_calls": []},
            ])

            _write_transcript(agy, c1_id, [
                {"step_index": 0, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-10-23T10:00:32Z", "content": f"[Message] timestamp=2026-10-23T10:00:32Z sender={root_id} content=Validate plan"},
                {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-10-23T10:01:00Z", "input_tokens": 500, "output_tokens": 100, "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "research", "Role": "Skeptic", "Model": "flash", "Prompt": "Check assumptions"}}]},
                {"step_index": 2, "source": "MODEL", "type": "GENERIC", "created_at": "2026-10-23T10:01:02Z", "content": f'Created the following subagent:\n{{"conversationId": "{g1_id}"}}'},
                {"step_index": 3, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-10-23T10:04:00Z", "tool_calls": [{"name": "write_file", "args": {"Path": os.path.join(ws, "plans/plan-validation.md")}}]},
                {"step_index": 4, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-10-23T10:04:02Z", "content": "Validation complete.", "tool_calls": []},
            ])

            _write_transcript(agy, c2_id, [
                {"step_index": 0, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-10-23T10:00:32Z", "content": f"[Message] timestamp=2026-10-23T10:00:32Z sender={root_id} content=Draft plan"},
                {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-10-23T10:04:00Z", "input_tokens": 400, "output_tokens": 80, "content": "Plan drafted.", "tool_calls": []},
            ])

            _write_transcript(agy, g1_id, [
                {"step_index": 0, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-10-23T10:01:02Z", "content": f"[Message] timestamp=2026-10-23T10:01:02Z sender={c1_id} content=Check assumptions"},
                {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-10-23T10:03:00Z", "input_tokens": 300, "output_tokens": 50, "content": "Verified.", "tool_calls": []},
            ])

            runs = list_agy_runs(agy, ws)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["subagent_count"], 3)

            selected = select_agy_run(agy, ws)
            self.assertEqual(selected, root_id)

            telemetry = parse_agy_run(agy, root_id, ws)
            self.assertEqual(telemetry["source"], "agy")
            self.assertEqual(telemetry["summary"]["total_agents"], 4)
            self.assertEqual(telemetry["summary"]["max_depth"], 2)
            self.assertGreater(telemetry["summary"]["parallelism_speedup"], 1.5)
            self.assertEqual(telemetry["summary"]["peak_concurrency"], 3)
            self.assertTrue(telemetry["gantt"]["has_compressed_gaps"])

            out_file = os.path.join(ws, ".agents", "trajectory.html")
            rc = generator.main(["--workspace", ws, "--agy-dir", agy, "--output", out_file])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(out_file))
            with open(out_file, encoding="utf-8") as f:
                html = f.read()
            self.assertIn("Wall-Clock Execution Waterfall", html)
            self.assertNotIn("All done.</script>", html)
            self.assertIn("All done.<\\/script>", html)

    def test_legacy_agents_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agents_dir = os.path.join(tmp, ".agents")
            orch_dir = os.path.join(agents_dir, "orchestrator")
            eng_dir = os.path.join(agents_dir, "worker_impl")
            os.makedirs(orch_dir)
            os.makedirs(eng_dir)

            with open(os.path.join(orch_dir, "BRIEFING.md"), "w", encoding="utf-8") as f:
                f.write("| Agent | Type | Work Item | Status | Conv ID |\n|---|---|---|---|---|\n| worker_impl | engineer | Build API | complete | abcdef123456 |\n")
            with open(os.path.join(eng_dir, "handoff.md"), "w", encoding="utf-8") as f:
                f.write("# Summary\n\nImplemented the API endpoints.")

            data = parse_legacy_agents_dir(agents_dir, tmp)
            self.assertEqual(data["source"], "legacy")
            self.assertEqual(len(data["agents"]), 2)
            html = generator.render_html(data)
            self.assertIn("Legacy .agents/ Telemetry", html)

    def test_peak_concurrency_and_empty_gantt(self) -> None:
        self.assertEqual(compute_peak_concurrency([(0, 10), (2, 8), (5, 12)]), 3)
        g = compute_gantt_layout([])
        self.assertFalse(g["has_timing"])


if __name__ == "__main__":
    unittest.main()
