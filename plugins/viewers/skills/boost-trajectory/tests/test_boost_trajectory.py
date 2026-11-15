#!/usr/bin/env python3
"""Unit and integration tests for boost-trajectory."""

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
from boost_telemetry import (  # noqa: E402
    _extract_settings_model_changes,
    _extract_subagent_spawns,
    _is_boost_user_input,
    _parse_dispatch_header,
    _parse_markdown_report,
    list_boost_runs,
    parse_boost_run,
    select_boost_run,
)
from timeline import compute_boost_worker_concurrency, format_duration, segment_active_turns  # noqa: E402


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


class BoostTrajectoryTests(unittest.TestCase):
    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(0), "0s")
        self.assertEqual(format_duration(0.3), "<1s")
        self.assertEqual(format_duration(95), "1m 35s")

    def test_segment_active_turns_splits_short_wakeup_across_sdk_reminder(self) -> None:
        steps = [
            {
                "step_index": 0,
                "source": "SYSTEM_SDK",
                "type": "SYSTEM_MESSAGE",
                "created_at": "2026-11-15T16:00:00Z",
                "content": "periodic system reminder",
            },
            {
                "step_index": 1,
                "source": "SYSTEM",
                "type": "SYSTEM_MESSAGE",
                "created_at": "2026-11-15T16:00:00Z",
                "content": "[Message] timestamp=2026-11-15T16:00:00Z sender=root content=investigate",
            },
            {
                "step_index": 2,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-11-15T16:00:02Z",
                "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "DeepInvestigatorWorkerL0"}}],
            },
            {
                "step_index": 3,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-11-15T16:00:04Z",
                "content": "Spawned worker.",
                "tool_calls": [],
            },
            # 25 seconds later (< 120s idle_gap_s): SYSTEM_SDK arrives right before worker send_message
            {
                "step_index": 4,
                "source": "SYSTEM_SDK",
                "type": "SYSTEM_MESSAGE",
                "created_at": "2026-11-15T16:00:29Z",
                "content": "periodic system reminder",
            },
            {
                "step_index": 5,
                "source": "SYSTEM",
                "type": "SYSTEM_MESSAGE",
                "created_at": "2026-11-15T16:00:29Z",
                "content": "[Message] timestamp=2026-11-15T16:00:28Z sender=worker0 content=report",
            },
            {
                "step_index": 6,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-11-15T16:00:31Z",
                "tool_calls": [{"name": "send_message", "args": {"Recipient": "root", "Message": "done"}}],
            },
        ]
        turns = segment_active_turns(steps)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["duration_s"], 4.0)
        self.assertEqual(turns[1]["duration_s"], 2.0)

    def test_concurrency_ignores_parent_child_handoff_overlap(self) -> None:
        agents = [
            {
                "conv_id": "root",
                "parent_id": "",
                "turns": [{"start_ms": 0, "end_ms": 4000}],
            },
            {
                "conv_id": "t2",
                "parent_id": "root",
                "turns": [
                    {"start_ms": 2000, "end_ms": 6000},
                    {"start_ms": 59000, "end_ms": 63000},
                ],
            },
            {
                "conv_id": "t3_l0",
                "parent_id": "t2",
                "turns": [{"start_ms": 5000, "end_ms": 60500}],
            },
            {
                "conv_id": "t3_imp",
                "parent_id": "t2",
                "turns": [{"start_ms": 62000, "end_ms": 110000}],
            },
        ]
        self.assertEqual(compute_boost_worker_concurrency(agents), 1)

        # Two parallel Tier-3 workers genuinely running concurrently -> 2
        agents_parallel = list(agents) + [
            {
                "conv_id": "t3_l0_b",
                "parent_id": "t2",
                "turns": [{"start_ms": 10000, "end_ms": 50000}],
            }
        ]
        self.assertEqual(compute_boost_worker_concurrency(agents_parallel), 2)

    def test_mixed_multi_boost_scoping_hierarchy_models_and_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "proj")
            agy = os.path.join(tmp, "agy")
            os.makedirs(ws)
            uri = json.dumps([f"file://{ws}"])

            root_id = "aaaaaaaa-0000-0000-0000-000000000001"
            solo_id = "bbbbbbbb-0000-0000-0000-000000000002"
            swarm_id = "cccccccc-0000-0000-0000-000000000003"
            t2_inv_id = "dddddddd-0000-0000-0000-000000000004"
            t3_inv_l0 = "dddddddd-0000-0000-0000-000000000005"
            t2_cod_id = "eeeeeeee-0000-0000-0000-000000000006"
            t3_cod_l0 = "eeeeeeee-0000-0000-0000-000000000007"
            t3_cod_imp = "eeeeeeee-0000-0000-0000-000000000008"

            _create_db(
                agy,
                [
                    (root_id, "Mixed Boost Session", "", "", 0, 20, "2026-11-15T16:25:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (solo_id, "Solo Boost Session", "", "", 0, 4, "2026-11-15T17:00:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (swarm_id, "Teamwork Swarm", "", "", 0, 5, "2026-11-15T18:00:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    ("cccccccc-1111-1111-1111-111111111111", "", "architect", swarm_id, 1, 3, "2026-11-15T18:00:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (t2_inv_id, "", "DeepInvestigator", root_id, 1, 6, "2026-11-15T15:10:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (t3_inv_l0, "", "DeepInvestigatorWorkerL0", t2_inv_id, 2, 12, "2026-11-15T15:09:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (t2_cod_id, "", "DeepCoder", root_id, 1, 8, "2026-11-15T16:25:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (t3_cod_l0, "", "DeepCoderWorkerL0", t2_cod_id, 2, 14, "2026-11-15T16:18:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                    (t3_cod_imp, "", "DeepCoderImprovementWorker", t2_cod_id, 2, 4, "2026-11-15T16:24:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 1),
                ],
            )

            # Non-boost teamwork swarm should be ignored by boost discovery
            _write_transcript(agy, swarm_id, [
                {"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "created_at": "2026-11-15T18:00:00Z", "content": "<USER_REQUEST>be the supervisor</USER_REQUEST>"},
            ])

            # Newer Solo /boost run (should lose auto-select to Delegation root_id)
            _write_transcript(agy, solo_id, [
                {"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "created_at": "2026-11-15T17:00:00Z", "content": "<USER_REQUEST>/boost quick solo fix</USER_REQUEST><ORCHESTRATOR>Solo</ORCHESTRATOR>"},
                {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T17:00:20Z", "model": "gemini-4-hydrogen-high", "content": "Fixed solo.", "tool_calls": []},
            ])

            # Mixed root conversation:
            # - step 0: regular non-boost question + USER_SETTINGS_CHANGE (older build fallback)
            # - step 2: Solo /boost
            # - step 4: Delegation /boost -> DeepInvestigator
            # - step 8: Unmarked follow-up -> DeepCoder (batched Subagents)
            # - step 11: Unmarked redirect -> send_message to DeepCoder
            _write_transcript(agy, root_id, [
                {
                    "step_index": 0,
                    "source": "USER_EXPLICIT",
                    "type": "USER_INPUT",
                    "created_at": "2026-11-14T10:00:00Z",
                    "content": "<USER_REQUEST>how does this repo work?</USER_REQUEST><USER_SETTINGS_CHANGE>The user changed setting `Model Selection` from None to Gemini 4 Hydrogen (High).</USER_SETTINGS_CHANGE>",
                },
                {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-14T10:00:10Z", "content": "Here is how.", "tool_calls": []},
                {
                    "step_index": 2,
                    "source": "USER_EXPLICIT",
                    "type": "USER_INPUT",
                    "created_at": "2026-11-15T14:00:00Z",
                    "content": "<USER_REQUEST>/boost edit README</USER_REQUEST>",
                },
                {"step_index": 3, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T14:00:30Z", "content": "Edited README.", "tool_calls": []},
                {
                    "step_index": 4,
                    "source": "USER_EXPLICIT",
                    "type": "USER_INPUT",
                    "created_at": "2026-11-15T15:00:00Z",
                    "content": "<USER_REQUEST>/boost investigate telemetry</USER_REQUEST><ORCHESTRATOR>Solo or Delegation</ORCHESTRATOR>",
                },
                {
                    "step_index": 5,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "created_at": "2026-11-15T15:00:05Z",
                    "model": "gemini-4-hydrogen-high",
                    "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "DeepInvestigator", "Role": "Boost Investigator", "Prompt": "Investigate telemetry"}}],
                },
                {
                    "step_index": 6,
                    "source": "MODEL",
                    "type": "GENERIC",
                    "created_at": "2026-11-15T15:00:08Z",
                    "content": f'Created the following subagent:\n{{"conversationId": "{t2_inv_id}"}}',
                },
                {"step_index": 7, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T15:10:00Z", "model": "gemini-4-hydrogen-high", "content": "Investigated.", "tool_calls": []},
                {
                    "step_index": 8,
                    "source": "USER_EXPLICIT",
                    "type": "USER_INPUT",
                    "created_at": "2026-11-15T16:10:00Z",
                    "content": "<USER_REQUEST>Now build the boost-trajectory skill</USER_REQUEST>",
                },
                {
                    "step_index": 9,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "created_at": "2026-11-15T16:10:04Z",
                    "tool_calls": [{"name": "invoke_subagent", "args": {"Subagents": [{"TypeName": "DeepCoder", "Role": "Boost Coder", "Model": "inherit", "Prompt": "Implement boost-trajectory"}]}}],
                },
                {
                    "step_index": 10,
                    "source": "MODEL",
                    "type": "GENERIC",
                    "created_at": "2026-11-15T16:10:06Z",
                    "content": f'Created the following subagents:\n{{"conversationId": "{t2_cod_id}"}}',
                },
                {
                    "step_index": 11,
                    "source": "USER_EXPLICIT",
                    "type": "USER_INPUT",
                    "created_at": "2026-11-15T16:12:00Z",
                    "content": "<USER_REQUEST>Update the output filename too</USER_REQUEST>",
                },
                {
                    "step_index": 12,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "created_at": "2026-11-15T16:12:05Z",
                    "tool_calls": [{"name": "send_message", "args": {"Recipient": t2_cod_id, "Message": "TASK CHANGED: use boost-trajectory.html"}}],
                },
                {"step_index": 13, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T16:25:00Z", "content": "Finished</script>", "tool_calls": []},
            ])

            _write_transcript(agy, t2_inv_id, [
                {"step_index": 0, "source": "SYSTEM_SDK", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T15:00:08Z", "content": "periodic reminder"},
                {"step_index": 1, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T15:00:08Z", "content": f"[Message] timestamp=2026-11-15T15:00:08Z sender={root_id} content=Investigate telemetry"},
                {"step_index": 2, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T15:00:10Z", "model": "gemini-4-hydrogen-high", "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "DeepInvestigatorWorkerL0", "Prompt": "Inspect logs"}}]},
                {"step_index": 3, "source": "MODEL", "type": "GENERIC", "created_at": "2026-11-15T15:00:12Z", "content": f'Created the following subagent:\n{{"conversationId": "{t3_inv_l0}"}}'},
                {"step_index": 4, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T15:00:12Z", "model": "gemini-4-hydrogen-high", "tool_calls": []},
                {"step_index": 5, "source": "SYSTEM_SDK", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T15:09:00Z", "content": "periodic reminder"},
                {"step_index": 6, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T15:09:00Z", "content": f"[Message] timestamp=2026-11-15T15:09:00Z sender={t3_inv_l0} content=done"},
                {"step_index": 7, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T15:09:58Z", "model": "gemini-4-hydrogen-high", "tool_calls": [{"name": "send_message", "args": {"Recipient": root_id, "Message": "DeepInvestigator pipeline completed.\n\n# Investigation Report\n\n## Executive Summary\nAll verified."}}]},
            ])

            _write_transcript(agy, t3_inv_l0, [
                {"step_index": 0, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T15:00:12Z", "content": f"[Message] timestamp=2026-11-15T15:00:12Z sender={t2_inv_id} content=Inspect logs"},
                {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T15:09:00Z", "model": "gemini-4-hydrogen-high", "tool_calls": [{"name": "send_message", "args": {"Recipient": t2_inv_id, "Message": "# Investigation Report\n\n## Executive Summary\nFound 3 telemetry patterns.\n\n## Remaining Questions & Gaps\nNone."}}]},
            ])

            # DeepCoder without PLANNER_RESPONSE['model'] -> tests USER_SETTINGS_CHANGE inheritance!
            _write_transcript(agy, t2_cod_id, [
                {"step_index": 0, "source": "SYSTEM_SDK", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T16:10:06Z", "content": "periodic reminder"},
                {"step_index": 1, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T16:10:06Z", "content": f"[Message] timestamp=2026-11-15T16:10:06Z sender={root_id} content=Implement boost-trajectory"},
                {"step_index": 2, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T16:10:08Z", "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "DeepCoderWorkerL0", "Model": "inherit", "Prompt": "Build L0"}}]},
                {"step_index": 3, "source": "MODEL", "type": "GENERIC", "created_at": "2026-11-15T16:10:10Z", "content": f'Created the following subagent:\n{{"conversationId": "{t3_cod_l0}"}}'},
                {"step_index": 4, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T16:10:10Z", "tool_calls": []},
                {"step_index": 5, "source": "SYSTEM_SDK", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T16:18:00Z", "content": "periodic reminder"},
                {"step_index": 6, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T16:18:00Z", "content": f"[Message] timestamp=2026-11-15T16:18:00Z sender={t3_cod_l0} content=done"},
                {"step_index": 7, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T16:18:05Z", "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "DeepCoderImprovementWorker", "Model": "inherit", "Prompt": "Audit L0"}}]},
                {"step_index": 8, "source": "MODEL", "type": "GENERIC", "created_at": "2026-11-15T16:18:07Z", "content": f'Created the following subagent:\n{{"conversationId": "{t3_cod_imp}"}}'},
                {"step_index": 9, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T16:25:00Z", "tool_calls": [{"name": "send_message", "args": {"Recipient": root_id, "Message": "DeepCoder pipeline completed."}}]},
            ])

            _write_transcript(agy, t3_cod_l0, [
                {"step_index": 0, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T16:10:10Z", "content": f"[Message] timestamp=2026-11-15T16:10:10Z sender={t2_cod_id} content=Build L0"},
                {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T16:15:00Z", "input_tokens": 900, "output_tokens": 120, "tool_calls": [{"name": "write_file", "args": {"Path": os.path.join(ws, "plugins/viewers/skills/boost-trajectory/generator.py")}}]},
                {
                    "step_index": 2,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "created_at": "2026-11-15T16:18:00Z",
                    "tool_calls": [{
                        "name": "send_message",
                        "args": {
                            "Recipient": t2_cod_id,
                            "Message": (
                                "> [!WARNING] **Skepticism Disclaimer**\n"
                                "> Tested unit helpers, UI only checked via HTML string assertions.\n\n"
                                "## 1. What I changed\nAdded generator.py.\n\n"
                                "## 3. Verification Record\n- Ran unittest.\n\n"
                                "## 4. Known Issues\n- Shallow Verification — browser rendering not executed.\n\n"
                                "## 5. Untested Edge Cases & Next Step\nCheck empty DB."
                            ),
                        },
                    }],
                },
            ])

            # Killed ImprovementWorker with zero send_message calls
            _write_transcript(agy, t3_cod_imp, [
                {"step_index": 0, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T16:18:07Z", "content": f"[Message] timestamp=2026-11-15T16:18:07Z sender={t2_cod_id} content=Audit L0"},
                {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T16:24:00Z", "tool_calls": [{"name": "read_file", "args": {"Path": "generator.py"}}]},
            ])

            runs = list_boost_runs(agy, ws)
            self.assertEqual(len(runs), 2)  # swarm_id excluded!
            # Auto-select prefers Delegation root_id even though solo_id is newer
            self.assertEqual(select_boost_run(agy, ws), root_id)

            # Default mode: scopes to latest /boost invocation only (DeepCoder pipeline)
            latest_data = parse_boost_run(agy, root_id, ws, all_invocations=False)
            self.assertEqual(latest_data["scope_mode"], "latest")
            self.assertEqual(latest_data["total_boost_invocations"], 3)
            self.assertEqual(latest_data["selected_invocation_indices"], [3])
            self.assertEqual(len(latest_data["pipelines"]), 1)

            p3 = latest_data["pipelines"][0]
            self.assertEqual(p3["routine"], "delegation")
            self.assertEqual(p3["summary"]["tier1_count"], 1)
            self.assertEqual(p3["summary"]["tier2_count"], 1)
            self.assertEqual(p3["summary"]["tier3_count"], 2)
            self.assertEqual(p3["summary"]["peak_concurrency"], 1)
            # Root step 0 (2026-11-14) and earlier invocations must NOT leak into latest invocation!
            self.assertTrue(p3["agents"][0]["wall_start_iso"].startswith("2026-11-15T16:10"))

            by_name = {a["name"]: a for a in p3["agents"]}
            self.assertEqual(by_name["DeepCoder"]["model"], "Gemini 4 Hydrogen (High)")
            self.assertEqual(by_name["DeepCoderWorkerL0"]["reports"][0]["kind"], "coding")
            self.assertIn("Shallow Verification", by_name["DeepCoderWorkerL0"]["reports"][0]["issue_flags"])
            self.assertIn("unit helpers", by_name["DeepCoderWorkerL0"]["reports"][0]["skepticism_disclaimer"])
            self.assertEqual(by_name["DeepCoderImprovementWorker"]["status"], "killed")
            self.assertTrue(by_name["DeepCoderImprovementWorker"]["incomplete_report"])

            # --all-invocations mode: all 3 /boost pipelines grouped separately (Solo, Inv, Coder)
            all_data = parse_boost_run(agy, root_id, ws, all_invocations=True)
            self.assertEqual(all_data["scope_mode"], "all")
            self.assertEqual(all_data["session_routine"], "mixed")
            self.assertEqual(len(all_data["pipelines"]), 3)
            self.assertEqual([p["routine"] for p in all_data["pipelines"]], ["solo", "delegation", "delegation"])
            self.assertEqual(all_data["pipelines"][1]["agents"][1]["reports"][0]["kind"], "investigation")

            # CLI default output path + XSS check
            rc = generator.main(["--workspace", ws, "--agy-dir", agy])
            self.assertEqual(rc, 0)
            out_file = os.path.join(ws, ".agents", "boost-trajectory.html")
            self.assertTrue(os.path.exists(out_file))
            with open(out_file, encoding="utf-8") as f:
                html = f.read()
            self.assertIn("Wall-Clock Execution Waterfall", html)
            self.assertIn("Skepticism Disclaimer", html)
            self.assertNotIn("Finished</script>", html)
            self.assertIn("Finished<\\/script>", html)

            # --full-session flag & --list flag
            all_out = os.path.join(ws, ".agents", "boost-all.html")
            rc_all = generator.main(["--workspace", ws, "--agy-dir", agy, "--full-session", "-o", all_out])
            self.assertEqual(rc_all, 0)
            self.assertTrue(os.path.exists(all_out))
            self.assertEqual(generator.main(["--workspace", ws, "--agy-dir", agy, "--list"]), 0)

            # Solo fallback when only Solo exists
            rc_solo = generator.main(["--workspace", ws, "--agy-dir", agy, "-c", solo_id[:8], "-o", os.path.join(ws, ".agents", "solo.html")])
            self.assertEqual(rc_solo, 0)
            self.assertTrue(os.path.exists(os.path.join(ws, ".agents", "solo.html")))

    def test_solo_auto_select_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "proj")
            agy = os.path.join(tmp, "agy")
            os.makedirs(ws)
            uri = json.dumps([f"file://{ws}"])
            solo_id = "11111111-2222-3333-4444-555555555555"
            _create_db(agy, [
                (solo_id, "Only Solo Boost", "", "", 0, 2, "2026-11-15T12:00:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
            ])
            _write_transcript(agy, solo_id, [
                {"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "created_at": "2026-11-15T12:00:00Z", "content": "<USER_REQUEST>/boost quick check</USER_REQUEST>"},
                {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T12:00:05Z", "model": "gemini-4-hydrogen-high", "content": "Done.", "tool_calls": []},
            ])
            self.assertEqual(select_boost_run(agy, ws), solo_id)
            data = parse_boost_run(agy, solo_id, ws)
            self.assertEqual(data["session_routine"], "solo")
            self.assertEqual(data["summary"]["total_agents"], 1)

    def test_versioned_model_names_and_report_classification_regressions(self) -> None:
        # 1. Versioned model names containing dots must NOT be truncated
        changes = _extract_settings_model_changes([
            {
                "step_index": 0,
                "content": "<USER_SETTINGS_CHANGE>Changed `Model Selection` from Gemini 3.1 Pro (High) to Gemini 3.8 Flash (High).\n</USER_SETTINGS_CHANGE>",
            },
            {
                "step_index": 5,
                "content": "<USER_SETTINGS_CHANGE>Changed `Model Selection` from Gemini 3.8 Flash (High) to Claude Opus 5.5 (High).</USER_SETTINGS_CHANGE>",
            },
        ])
        self.assertEqual(changes, [(0, "Gemini 3.8 Flash (High)"), (1, "Claude Opus 5.5 (High)")])

        # 2. DeepInvestigator report mentioning Verification Record / Known Issues in prose
        inv_text = (
            "# Investigation Report\n\n"
            "## Executive Summary\n"
            "Workers emit Verification Record and Known Issues sections.\n\n"
            "## Findings\n"
            "- Coding workers output Fatal Functional Bug flags.\n"
        )
        parsed_inv = _parse_markdown_report(inv_text, agent_family="investigator")
        self.assertEqual(parsed_inv["kind"], "investigation")
        self.assertEqual(parsed_inv["issue_flags"], [])

        # 3. Bold Skepticism Disclaimer without [!WARNING] tag
        cod_text = (
            "> **Skepticism Disclaimer**: Verified unit tests.\n\n"
            "## 1. What I changed\nFixed regex.\n\n"
            "## 2. Known Issues\n- Fatal Functional Bug: none remaining -> fixed.\n"
        )
        parsed_cod = _parse_markdown_report(cod_text, agent_family="coder")
        self.assertEqual(parsed_cod["kind"], "coding")
        self.assertIn("Verified unit tests.", parsed_cod["skepticism_disclaimer"])
        self.assertIn("Fatal Functional Bug", parsed_cod["issue_flags"])

    def test_boost_detection_dispatch_header_spawns_and_fast_wakeup(self) -> None:
        # 1. Mid-sentence mention of /boost in normal chat is NOT a /boost invocation
        self.assertFalse(_is_boost_user_input("<USER_REQUEST>Explain how /boost works please.</USER_REQUEST>"))
        self.assertTrue(_is_boost_user_input("<USER_REQUEST>  /boost fix this bug</USER_REQUEST>"))

        # 2. USER_INPUT at step 0 followed by [Notice] sender=system at step 1
        spawn_dt, sender_id, prompt = _parse_dispatch_header([
            {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-15T10:00:00Z", "content": "<USER_REQUEST>/boost go</USER_REQUEST>"},
            {"step_index": 1, "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T10:00:01Z", "content": "[Notice] timestamp=2026-11-15T10:00:01Z sender=system content=Notice text"},
        ])
        self.assertIsNone(sender_id)
        self.assertEqual(prompt, "/boost go")
        self.assertIsNotNone(spawn_dt)

        # 3. Failed invoke_subagent before succeeding invoke_subagent must not misalign metadata
        spawns = _extract_subagent_spawns([
            {
                "step_index": 2,
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-11-15T10:00:05Z",
                "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "FailedAgent", "Prompt": "stale"}}],
            },
            {
                "step_index": 3,
                "type": "GENERIC",
                "created_at": "2026-11-15T10:00:06Z",
                "content": "Failed to spawn subagent",
            },
            {
                "step_index": 4,
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-11-15T10:00:10Z",
                "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "DeepCoder", "Model": "inherit", "Prompt": "fresh"}}],
            },
            {
                "step_index": 5,
                "type": "GENERIC",
                "created_at": "2026-11-15T10:00:11Z",
                "content": 'Created the following subagent:\n{"conversationId": "t2-good", "meta": {"nested": true}}',
            },
        ])
        self.assertEqual(list(spawns.keys()), ["t2-good"])
        self.assertEqual(spawns["t2-good"]["requested_type"], "DeepCoder")
        self.assertEqual(spawns["t2-good"]["prompt"], "fresh")

        # 4. Ultra-fast (0.8s) wakeup after SYSTEM_SDK reminder still splits Tier-2 turns
        turns = segment_active_turns([
            {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM_SDK", "created_at": "2026-11-15T10:00:00Z"},
            {"step_index": 1, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-15T10:00:01Z", "content": "[Message] sender=root content=Go"},
            {"step_index": 2, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T10:00:05Z", "tool_calls": []},
            {"step_index": 3, "type": "SYSTEM_MESSAGE", "source": "SYSTEM_SDK", "created_at": "2026-11-15T10:00:05.5Z"},
            {"step_index": 4, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-15T10:00:05.8Z", "content": "[Message] sender=t3 content=Done"},
            {"step_index": 5, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T10:00:08Z", "tool_calls": []},
        ])
        self.assertEqual(len(turns), 2)

    def test_subagent_id_selection_and_unclaimed_window_routing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "proj")
            agy = os.path.join(tmp, "agy")
            os.makedirs(ws)
            uri = json.dumps([f"file://{ws}"])
            root_id = "aaaa0000-0000-0000-0000-000000000001"
            t2_id = "bbbb0000-0000-0000-0000-000000000002"
            t3_id = "cccc0000-0000-0000-0000-000000000003"

            _create_db(agy, [
                (root_id, "Root Boost", "Orchestrator", "", 0, 4, "2026-11-15T11:05:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                (t2_id, "T2", "DeepCoder", root_id, 1, 2, "2026-11-15T10:03:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                (t3_id, "T3", "DeepCoderWorkerL0", t2_id, 2, 2, "2026-11-15T10:02:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
            ])
            _write_transcript(agy, root_id, [
                {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-15T10:00:00Z", "content": "<USER_REQUEST>/boost first run</USER_REQUEST>"},
                {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T10:01:00Z", "tool_calls": []},
                {"step_index": 2, "type": "USER_INPUT", "created_at": "2026-11-15T11:00:00Z", "content": "<USER_REQUEST>/boost second solo run</USER_REQUEST>"},
                {"step_index": 3, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T11:01:00Z", "tool_calls": []},
            ])
            _write_transcript(agy, t2_id, [
                {"step_index": 0, "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T10:00:30Z", "content": f"[Message] timestamp=2026-11-15T10:00:30Z sender={root_id} content=Work"},
            ])
            _write_transcript(agy, t3_id, [
                {"step_index": 0, "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T10:01:00Z", "content": f"[Message] timestamp=2026-11-15T10:01:00Z sender={t2_id} content=Sub"},
            ])

            # Passing Tier-2 or Tier-3 subagent ID resolves upward to root_id
            self.assertEqual(select_boost_run(agy, ws, t2_id[:8]), root_id)
            self.assertEqual(select_boost_run(agy, ws, t3_id), root_id)

            # Unclaimed DB child modified at 10:03 attaches to first invocation (10:00), not second solo invocation (11:00)
            all_data = parse_boost_run(agy, root_id, ws, all_invocations=True)
            self.assertEqual([p["routine"] for p in all_data["pipelines"]], ["delegation", "solo"])
            self.assertEqual(all_data["pipelines"][0]["summary"]["total_agents"], 3)
            self.assertEqual(all_data["pipelines"][1]["summary"]["total_agents"], 1)


if __name__ == "__main__":
    unittest.main()
