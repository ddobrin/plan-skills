#!/usr/bin/env python3
"""Unit and integration tests for swarm-trajectory."""

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
from swarm_telemetry import (  # noqa: E402
    list_swarm_runs,
    parse_swarm_run,
    select_swarm_run,
)
from swarm_timeline import (  # noqa: E402
    compute_worker_concurrency,
    format_duration,
    segment_swarm_turns,
)


def _write_transcript(agy_dir: str, conv_id: str, steps: list[dict]) -> None:
    logs_dir = os.path.join(agy_dir, "brain", conv_id, ".system_generated", "logs")
    os.makedirs(logs_dir, exist_ok=True)
    with open(os.path.join(logs_dir, "transcript_full.jsonl"), "w", encoding="utf-8") as f:
        for s in steps:
            f.write(json.dumps(s) + "\n")


def _write_swarm_dir(
    agy_dir: str,
    root_id: str,
    members: dict,
    board_posts: list[dict],
    title: str = "Test Swarm",
) -> None:
    sdir = os.path.join(agy_dir, "brain", root_id, ".system_generated", "swarm")
    os.makedirs(sdir, exist_ok=True)
    with open(os.path.join(sdir, "swarm.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "backend": "local", "swarm_id": root_id}, f)
    with open(os.path.join(sdir, "members.json"), "w", encoding="utf-8") as f:
        json.dump({"title": title, "members": members}, f)
    with open(os.path.join(sdir, "board.jsonl"), "w", encoding="utf-8") as f:
        for p in board_posts:
            f.write(json.dumps(p) + "\n")


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


class SwarmTrajectoryTests(unittest.TestCase):
    def test_format_duration_and_concurrency(self) -> None:
        self.assertEqual(format_duration(0), "0s")
        self.assertEqual(format_duration(0.3), "<1s")
        self.assertEqual(format_duration(125), "2m 5s")
        conc = compute_worker_concurrency([
            ("w1", 100.0, 200.0),
            ("w2", 120.0, 180.0),
            ("w3", 199.0, 250.0),  # only 1s overlap with w1 (< 3s tolerance)
        ])
        self.assertEqual(conc, 2)

    def test_segment_swarm_turns_separates_swarm_wait_and_sdk_reminders(self) -> None:
        steps = [
            {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-18T10:00:00Z", "content": "[Message] sender=coord content=start"},
            {"step_index": 1, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T10:00:20Z", "input_tokens": 100, "output_tokens": 20, "cache_read_tokens": 50, "tool_calls": [{"name": "swarm_wait", "args": {"since": 1}}]},
            {"step_index": 2, "type": "GENERIC", "source": "MODEL", "created_at": "2026-11-18T10:00:21Z", "content": "Waiting for a message that calls on you by name."},
            {"step_index": 3, "type": "SYSTEM_MESSAGE", "source": "SYSTEM_SDK", "created_at": "2026-11-18T10:05:00Z", "content": "reminder"},
            {"step_index": 4, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-18T10:10:21Z", "content": "[Message] sender=coord content=[swarm] new board message #5"},
            {"step_index": 5, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T10:11:01Z", "input_tokens": 200, "output_tokens": 40, "cache_read_tokens": 100, "tool_calls": []},
        ]
        turns, waits = segment_swarm_turns(steps)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["duration_s"], 21.0)
        self.assertEqual(turns[1]["duration_s"], 40.0)
        self.assertEqual(len(waits), 1)
        self.assertEqual(waits[0]["reason"], "swarm_wait")
        self.assertEqual(waits[0]["duration_s"], 600.0)

    def test_completed_retired_workers_tokens_verification_and_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "proj")
            agy = os.path.join(tmp, "agy")
            os.makedirs(ws)
            uri = json.dumps([f"file://{ws}"])

            coord_id = "aaaa0000-0000-0000-0000-000000000001"
            author_id = "bbbb0000-0000-0000-0000-000000000002"
            verifier_id = "cccc0000-0000-0000-0000-000000000003"
            monitor_id = "dddd0000-0000-0000-0000-000000000004"

            _create_db(
                agy,
                [
                    (coord_id, "Build Widget", "", "", 0, 6, "2026-11-18T10:10:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (author_id, "", "widget-author", coord_id, 1, 8, "2026-11-18T10:05:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 1),
                    (verifier_id, "", "verifier", coord_id, 1, 8, "2026-11-18T10:09:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 1),
                    (monitor_id, "", "monitor", coord_id, 1, 4, "2026-11-18T10:12:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                ],
            )

            members = {
                "coordinator": {"conversation_id": coord_id, "role": "coordinator", "killed": False, "model": "gemini-4-hydrogen-high"},
                "widget-author": {"conversation_id": author_id, "role": "worker", "killed": True, "model": "claude-opus-5-5-high"},
                "verifier": {"conversation_id": verifier_id, "role": "worker", "killed": True, "model": "gemini-4-hydrogen-high"},
                "monitor": {"conversation_id": monitor_id, "role": "worker", "killed": False, "model": "gemini-4-hydrogen-high"},
            }
            board = [
                {"seq": 1, "agent": "coordinator", "text": "@widget-author implement src/widget.py and post [done]", "time": "2026-11-18T10:00:05Z", "kind": "brief"},
                {"seq": 2, "agent": "coordinator", "text": "@verifier verify src/widget.py and post [done]", "time": "2026-11-18T10:00:05Z", "kind": "brief"},
                {"seq": 3, "agent": "widget-author", "text": "@verifier [done] Created src/widget.py and unit tests pass.", "time": "2026-11-18T10:05:00Z", "kind": "post"},
                {"seq": 4, "agent": "verifier", "text": "@coordinator [done] All tests passed on src/widget.py.", "time": "2026-11-18T10:09:00Z", "kind": "post"},
                {"seq": 5, "agent": "coordinator", "text": "[done] Widget implemented and verified.", "time": "2026-11-18T10:10:00Z", "kind": "post"},
            ]
            _write_swarm_dir(agy, coord_id, members, board, title="Build Widget <script>alert(1)</script>")

            _write_transcript(agy, coord_id, [
                {"step_index": 0, "type": "USER_INPUT", "source": "USER_EXPLICIT", "created_at": "2026-11-18T10:00:00Z", "content": "<USER_REQUEST>/swarm build widget</USER_REQUEST>"},
                {"step_index": 1, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T10:00:05Z", "model": "gemini-4-hydrogen-high", "input_tokens": 500, "output_tokens": 100, "cache_read_tokens": 1000, "tool_calls": [{"name": "swarm_wait", "args": {"since": 2}}]},
                {"step_index": 2, "type": "GENERIC", "source": "MODEL", "created_at": "2026-11-18T10:00:06Z", "content": "Waiting for a message."},
                {"step_index": 3, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-18T10:09:00Z", "content": "[Message] sender=ver content=[swarm] new board message #4"},
                {"step_index": 4, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T10:10:00Z", "model": "gemini-4-hydrogen-high", "input_tokens": 300, "output_tokens": 80, "cache_read_tokens": 900, "content": "Done!", "tool_calls": []},
            ])
            _write_transcript(agy, author_id, [
                {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-18T10:00:05Z", "content": "[Message] sender=coord content=start"},
                {"step_index": 1, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T10:03:00Z", "model": "gemini-4-hydrogen-high", "input_tokens": 400, "output_tokens": 150, "cache_read_tokens": 800, "tool_calls": [{"name": "write_file", "args": {"Path": os.path.join(ws, "src", "widget.py")}}]},
                {"step_index": 2, "type": "GENERIC", "source": "MODEL", "created_at": "2026-11-18T10:03:01Z", "content": "Created widget.py"},
                {"step_index": 3, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T10:05:00Z", "model": "claude-opus-5-5-high", "input_tokens": 200, "output_tokens": 90, "cache_read_tokens": 600, "tool_calls": [{"name": "post_message", "args": {"text": "@verifier [done]"}}, {"name": "swarm_wait", "args": {"since": 2}}]},
                {"step_index": 4, "type": "GENERIC", "source": "MODEL", "created_at": "2026-11-18T10:05:01Z", "content": "Posted"},
                {"step_index": 5, "type": "GENERIC", "source": "MODEL", "created_at": "2026-11-18T10:05:01Z", "content": "Waiting for a message."},
            ])
            _write_transcript(agy, verifier_id, [
                {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-18T10:00:05Z", "content": "[Message] sender=coord content=start"},
                {"step_index": 1, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T10:00:10Z", "model": "gemini-4-hydrogen-high", "input_tokens": 100, "output_tokens": 20, "cache_read_tokens": 200, "tool_calls": [{"name": "swarm_wait", "args": {"since": 2}}]},
                {"step_index": 2, "type": "GENERIC", "source": "MODEL", "created_at": "2026-11-18T10:00:11Z", "content": "Waiting for a message."},
                {"step_index": 3, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-18T10:05:00Z", "content": "[Message] sender=auth content=[swarm] new board message #3"},
                {"step_index": 4, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T10:06:00Z", "model": "gemini-4-hydrogen-high", "input_tokens": 300, "output_tokens": 60, "cache_read_tokens": 500, "tool_calls": [{"name": "run_command", "args": {"CommandLine": "pytest -q"}}]},
                {"step_index": 5, "type": "GENERIC", "source": "MODEL", "created_at": "2026-11-18T10:06:02Z", "content": f"Tool is running as a background task with task id: {verifier_id}/task-5"},
                {"step_index": 6, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-18T10:08:50Z", "content": f'[Message] sender={verifier_id}/task-5 content=Task id "{verifier_id}/task-5" finished with result:\nCommand exited with code 0.\n3 passed'},
                {"step_index": 7, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T10:09:00Z", "model": "gemini-4-hydrogen-high", "input_tokens": 200, "output_tokens": 50, "cache_read_tokens": 400, "tool_calls": [{"name": "post_message", "args": {"text": "@coordinator [done]"}}]},
            ])
            _write_transcript(agy, monitor_id, [
                {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-18T10:00:05Z", "content": "[Message] sender=coord content=start"},
                {"step_index": 1, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T10:00:10Z", "model": "gemini-4-hydrogen-high", "input_tokens": 50, "output_tokens": 10, "cache_read_tokens": 100, "tool_calls": [{"name": "swarm_wait", "args": {"since": 2}}]},
                {"step_index": 2, "type": "GENERIC", "source": "MODEL", "created_at": "2026-11-18T10:00:11Z", "content": "Waiting for anything."},
                {"step_index": 3, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-18T10:12:00Z", "content": "[Message] sender=timer content=tick"},
                {"step_index": 4, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T10:12:05Z", "model": "gemini-4-hydrogen-high", "input_tokens": 50, "output_tokens": 10, "cache_read_tokens": 100, "tool_calls": []},
            ])

            # Resolve upward from worker prefix
            self.assertEqual(select_swarm_run(agy, ws, "bbbb0000"), coord_id)

            runs = list_swarm_runs(agy, ws)
            self.assertEqual(len(runs), 1)
            self.assertTrue(runs[0]["completed"])
            self.assertTrue(runs[0]["verified"])

            data = parse_swarm_run(agy, coord_id, ws, include_git=False)
            self.assertEqual(data["summary"]["outcome"], "completed")
            self.assertEqual(data["summary"]["completed_workers"], 2)
            self.assertEqual(data["summary"]["retired_workers"], 2)
            self.assertEqual(data["summary"]["monitor_tail_s"], 125.0)
            self.assertEqual(data["verification"]["verdict"], "VERIFIED")
            self.assertEqual(data["verification"]["passed_count"], 1)
            self.assertTrue(data["verification"]["ordered_after_edits"])

            by_name = {a["name"]: a for a in data["agents"]}
            self.assertEqual(by_name["widget-author"]["lifecycle_state"], "completed_retired")
            self.assertTrue(by_name["widget-author"]["model_switched"])
            self.assertEqual(by_name["widget-author"]["docs"][0]["name"], "src/widget.py")
            self.assertGreater(by_name["verifier"]["wait_duration_s"], 200.0)

            out_html = os.path.join(ws, ".agents", "swarm-trajectory.html")
            rc = generator.main(["--agy-dir", agy, "--workspace", ws, "-c", "bbbb0000", "-o", out_html, "--no-git"])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(out_html))
            with open(out_html, encoding="utf-8") as f:
                html = f.read()
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertIn("\\/script>", html)
            self._assert_html_js_renders(html)

    def _assert_html_js_renders(self, html: str) -> None:
        """If node is available, verify embedded JS compiles and populates all panels."""
        # Exercise git_snapshot untracked newline branch too.
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
const mk = (id) => ({ id, textContent: "", innerHTML: "", value: "", className: "", classList: { add(){}, remove(){}, toggle(){} }, addEventListener(){} });
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
for (const id of ["outcomeBadge","verifyBadge","runTitle","summaryGrid","verificationPanel","resourcesPanel","ganttPanel","deliverablesPanel","boardPanel"]) {
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

    def test_render_html_with_git_untracked_snapshot_executes_cleanly(self) -> None:
        sample = {
            "run_title": "Git Untracked Check",
            "root_conversation_id": "aaaa0000-0000-0000-0000-000000000001",
            "workspace_root": "/tmp/ws",
            "tz_label": "EST",
            "summary": {"outcome": "completed", "outcome_label": "Completed", "tokens": {}},
            "verification": {"verdict": "UNVERIFIED", "verdict_label": "Unverified"},
            "agents": [],
            "board": [],
            "handoffs": [],
            "channels": ["main"],
            "gantt": {"rows": [], "markers": [], "has_compressed_gaps": False},
            "role_rollups": [],
            "insights": [],
            "git_snapshot": {"available": True, "modified": ["a.py"], "untracked": ["b.py", "c.py"], "diffstat": "a.py | 1 +"},
        }
        html = generator.render_html(sample)
        self._assert_html_js_renders(html)

    def test_incomplete_swarm_ignores_instructional_done_in_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "proj")
            agy = os.path.join(tmp, "agy")
            os.makedirs(ws)
            uri = json.dumps([f"file://{ws}"])

            coord_id = "eeee0000-0000-0000-0000-000000000001"
            worker_id = "ffff0000-0000-0000-0000-000000000002"
            _create_db(
                agy,
                [
                    (coord_id, "Abandoned Swarm", "", "", 0, 2, "2026-11-18T11:01:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (worker_id, "", "api-author", coord_id, 1, 2, "2026-11-18T11:01:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                ],
            )
            members = {
                "coordinator": {"conversation_id": coord_id, "role": "coordinator", "killed": False, "model": "gemini-4-hydrogen-high"},
                "api-author": {"conversation_id": worker_id, "role": "worker", "killed": False, "model": "gemini-4-hydrogen-high"},
            }
            board = [
                {"seq": 1, "agent": "coordinator", "text": "@api-author when finished post @coordinator [done] summary", "time": "2026-11-18T11:00:00Z", "kind": "brief"},
            ]
            _write_swarm_dir(agy, coord_id, members, board, title="Abandoned Swarm")
            _write_transcript(agy, coord_id, [
                {"step_index": 0, "type": "USER_INPUT", "source": "USER_EXPLICIT", "created_at": "2026-11-18T11:00:00Z", "content": "<USER_REQUEST>/swarm go</USER_REQUEST>"},
            ])
            _write_transcript(agy, worker_id, [
                {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-18T11:00:01Z", "content": "[Message] sender=coord content=start"},
                {"step_index": 1, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T11:00:10Z", "model": "gemini-4-hydrogen-high", "input_tokens": 50, "output_tokens": 10, "cache_read_tokens": 0, "tool_calls": []},
            ])

            data = parse_swarm_run(agy, coord_id, ws, include_git=False)
            self.assertEqual(data["summary"]["outcome"], "incomplete")
            self.assertEqual(data["summary"]["done_post_count"], 0)
            self.assertEqual(data["verification"]["verdict"], "UNVERIFIED")
            by_name = {a["name"]: a for a in data["agents"]}
            self.assertEqual(by_name["api-author"]["lifecycle_state"], "waiting_incomplete")

    def test_stale_verification_when_author_edits_after_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "proj")
            agy = os.path.join(tmp, "agy")
            os.makedirs(ws)
            uri = json.dumps([f"file://{ws}"])

            coord_id = "11110000-0000-0000-0000-000000000001"
            author_id = "22220000-0000-0000-0000-000000000002"
            verifier_id = "33330000-0000-0000-0000-000000000003"
            _create_db(
                agy,
                [
                    (coord_id, "Stale Swarm", "", "", 0, 2, "2026-11-18T12:10:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (author_id, "", "author", coord_id, 1, 2, "2026-11-18T12:10:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (verifier_id, "", "verifier", coord_id, 1, 2, "2026-11-18T12:06:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                ],
            )
            members = {
                "coordinator": {"conversation_id": coord_id, "role": "coordinator", "killed": False, "model": "gemini-4-hydrogen-high"},
                "author": {"conversation_id": author_id, "role": "worker", "killed": True, "model": "gemini-4-hydrogen-high"},
                "verifier": {"conversation_id": verifier_id, "role": "worker", "killed": True, "model": "gemini-4-hydrogen-high"},
            }
            board = [
                {"seq": 1, "agent": "coordinator", "text": "@author build widget", "time": "2026-11-18T12:00:00Z", "kind": "brief"},
                {"seq": 2, "agent": "coordinator", "text": "@verifier test widget", "time": "2026-11-18T12:00:05Z", "kind": "brief"},
                {"seq": 3, "agent": "verifier", "text": "@coordinator [done] tests pass", "time": "2026-11-18T12:05:00Z", "kind": "post"},
                {"seq": 4, "agent": "author", "text": "@coordinator [done] tweaked widget later", "time": "2026-11-18T12:09:00Z", "kind": "post"},
            ]
            _write_swarm_dir(agy, coord_id, members, board, title="Stale Swarm")
            _write_transcript(agy, coord_id, [
                {"step_index": 0, "type": "USER_INPUT", "source": "USER_EXPLICIT", "created_at": "2026-11-18T12:00:00Z", "content": "<USER_REQUEST>/swarm stale</USER_REQUEST>"},
            ])
            _write_transcript(agy, verifier_id, [
                {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-18T12:00:05Z", "content": "[Message] sender=coord content=go"},
                {"step_index": 1, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T12:04:00Z", "model": "gemini-4-hydrogen-high", "input_tokens": 100, "output_tokens": 20, "tool_calls": [{"name": "run_command", "args": {"CommandLine": "pytest -q"}}]},
                {"step_index": 2, "type": "GENERIC", "source": "MODEL", "created_at": "2026-11-18T12:04:30Z", "content": "Command exited with code 0.\n2 passed"},
                {"step_index": 3, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T12:05:00Z", "model": "gemini-4-hydrogen-high", "input_tokens": 50, "output_tokens": 10, "tool_calls": [{"name": "post_message", "args": {"text": "@coordinator [done] tests pass"}}]},
            ])
            _write_transcript(agy, author_id, [
                {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-18T12:00:00Z", "content": "[Message] sender=coord content=go"},
                {"step_index": 1, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T12:08:30Z", "model": "gemini-4-hydrogen-high", "input_tokens": 100, "output_tokens": 20, "tool_calls": [{"name": "edit_file", "args": {"Path": os.path.join(ws, "src", "app.py")}}]},
                {"step_index": 2, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T12:09:00Z", "model": "gemini-4-hydrogen-high", "input_tokens": 50, "output_tokens": 10, "tool_calls": [{"name": "post_message", "args": {"text": "@coordinator [done] tweaked widget later"}}]},
            ])

            data = parse_swarm_run(agy, coord_id, ws, include_git=False)
            self.assertEqual(data["verification"]["verdict"], "STALE")
            self.assertFalse(data["verification"]["ordered_after_edits"])
            self.assertEqual(data["verification"]["passed_count"], 1)

    def test_failed_verification_tracks_background_finish_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "proj")
            agy = os.path.join(tmp, "agy")
            os.makedirs(ws)
            uri = json.dumps([f"file://{ws}"])

            coord_id = "44440000-0000-0000-0000-000000000001"
            verifier_id = "55550000-0000-0000-0000-000000000002"
            _create_db(
                agy,
                [
                    (coord_id, "Failed Swarm", "", "", 0, 2, "2026-11-18T13:10:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (verifier_id, "", "verifier", coord_id, 1, 2, "2026-11-18T13:10:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                ],
            )
            members = {
                "coordinator": {"conversation_id": coord_id, "role": "coordinator", "killed": False, "model": "gemini-4-hydrogen-high"},
                "verifier": {"conversation_id": verifier_id, "role": "worker", "killed": True, "model": "gemini-4-hydrogen-high"},
            }
            board = [
                {"seq": 1, "agent": "coordinator", "text": "@verifier check repo", "time": "2026-11-18T13:00:00Z", "kind": "brief"},
                {"seq": 2, "agent": "verifier", "text": "@coordinator [done] 1 failure found", "time": "2026-11-18T13:09:00Z", "kind": "post"},
            ]
            _write_swarm_dir(agy, coord_id, members, board, title="Failed Swarm")
            _write_transcript(agy, coord_id, [
                {"step_index": 0, "type": "USER_INPUT", "source": "USER_EXPLICIT", "created_at": "2026-11-18T13:00:00Z", "content": "<USER_REQUEST>/swarm fail</USER_REQUEST>"},
            ])
            # Background slow test launches at step 1 (ts 13:01) and fails at step 5 (ts 13:08),
            # AFTER quick lint at step 3 (ts 13:02) passed. Must still count as unresolved failure.
            _write_transcript(agy, verifier_id, [
                {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-18T13:00:01Z", "content": "[Message] sender=coord content=go"},
                {"step_index": 1, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T13:01:00Z", "model": "gemini-4-hydrogen-high", "input_tokens": 100, "output_tokens": 20, "tool_calls": [{"name": "run_command", "args": {"CommandLine": "pytest tests/"}}]},
                {"step_index": 2, "type": "GENERIC", "source": "MODEL", "created_at": "2026-11-18T13:01:02Z", "content": f"Tool is running as a background task with task id: {verifier_id}/task-1"},
                {"step_index": 3, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T13:02:00Z", "model": "gemini-4-hydrogen-high", "input_tokens": 50, "output_tokens": 10, "tool_calls": [{"name": "run_command", "args": {"CommandLine": "ruff check ."}}]},
                {"step_index": 4, "type": "GENERIC", "source": "MODEL", "created_at": "2026-11-18T13:02:10Z", "content": "Command exited with code 0."},
                {"step_index": 5, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-18T13:08:00Z", "content": f'[Message] sender={verifier_id}/task-1 content=Task id "{verifier_id}/task-1" finished with result:\nCommand exited with code 1.\n1 failed'},
                {"step_index": 6, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-18T13:09:00Z", "model": "gemini-4-hydrogen-high", "input_tokens": 50, "output_tokens": 10, "tool_calls": [{"name": "post_message", "args": {"text": "@coordinator [done] 1 failure found"}}]},
            ])

            data = parse_swarm_run(agy, coord_id, ws, include_git=False)
            self.assertEqual(data["verification"]["verdict"], "FAILED")
            self.assertEqual(data["verification"]["passed_count"], 1)
            self.assertEqual(data["verification"]["failed_count"], 1)
            self.assertEqual(data["verification"]["unresolved_failure_count"], 1)


if __name__ == "__main__":
    unittest.main()
