#!/usr/bin/env python3
"""Unit and integration tests for teamwork-trajectory."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

import generator  # noqa: E402
from telemetry import (  # noqa: E402
    _extract_produced_docs,
    _extract_settings_model_changes,
    _extract_subagent_spawns,
    _extract_summary,
    _parse_step0_header,
    list_agy_runs,
    parse_agy_run,
    parse_legacy_agents_dir,
    select_agy_run,
)
from timeline import (  # noqa: E402
    compute_gantt_layout,
    compute_peak_concurrency,
    compute_worker_concurrency,
    format_duration,
    segment_active_turns,
)


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
            # Parent c1_id waiting/overlapping on child g1_id does not inflate worker concurrency (c2_id + g1_id = 2)
            self.assertEqual(telemetry["summary"]["peak_concurrency"], 2)
            self.assertTrue(telemetry["gantt"]["has_compressed_gaps"])

            out_file = os.path.join(ws, ".agents", "trajectory.html")
            rc = generator.main(["--workspace", ws, "--agy-dir", agy, "--output", out_file])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(out_file))
            with open(out_file, encoding="utf-8") as f:
                html = f.read()
            self.assertIn("Wall-Clock Execution Waterfall", html)
            self.assertIn("Open ${escapeHtml(transcriptName)}", html)
            self.assertIn("transcript_full.jsonl", html)
            self.assertIn("status-badge", html)
            self.assertIn("data-conv-id=", html)
            self.assertIn("agentsShareWave", html)
            self.assertIn("applyTimelineFilter", html)
            self.assertIn("Models, Steps & Tokens", html)
            self.assertNotIn("All done.</script>", html)
            self.assertIn("All done.<\\/script>", html)
            m = re.search(r"<script>([\s\S]*)</script>", html)
            self.assertIsNotNone(m)
            proc = subprocess.run(["node", "--input-type=commonjs", "--check"], input=m.group(1), text=True, capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_legacy_agents_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agents_dir = os.path.join(tmp, ".agents")
            sentinel_dir = os.path.join(agents_dir, "sentinel")
            orch_dir = os.path.join(agents_dir, "orchestrator")
            eng_dir = os.path.join(agents_dir, "worker_impl")
            vic_dir = os.path.join(agents_dir, "victory_auditor")
            for d in (sentinel_dir, orch_dir, eng_dir, vic_dir):
                os.makedirs(d)

            with open(os.path.join(orch_dir, "BRIEFING.md"), "w", encoding="utf-8") as f:
                f.write("| Agent | Type | Work Item | Status | Conv ID |\n|---|---|---|---|---|\n| worker_impl | engineer | Build API | complete | unknown |\n")
            with open(os.path.join(eng_dir, "handoff.md"), "w", encoding="utf-8") as f:
                f.write("# Summary\n\nImplemented the API endpoints.")

            data = parse_legacy_agents_dir(agents_dir, tmp)
            self.assertEqual(data["source"], "legacy")
            self.assertEqual(len(data["agents"]), 4)
            # Every agent gets a unique DOM id even when conv_id is "unknown"
            self.assertEqual(len({a["id"] for a in data["agents"]}), 4)
            html = generator.render_html(data)
            self.assertIn("Legacy .agents/ Telemetry", html)
            self.assertIn("data-agent-key=", html)
            m = re.search(r"<script>([\s\S]*)</script>", html)
            self.assertIsNotNone(m)
            # Execute the generated dashboard script in Node with a lightweight DOM to verify search & phase sync
            dom_probe = (
                "class MockClassList{constructor(){this.set=new Set()}add(...c){c.forEach(x=>this.set.add(x))}remove(...c){c.forEach(x=>this.set.delete(x))}contains(c){return this.set.has(c)}toggle(c){if(this.set.has(c)){this.set.delete(c);return false}this.set.add(c);return true}}"
                "class MockEl{constructor(t='div'){this.tagName=t;this.attrs={};this.style={};this.children=[];this.classList=new MockClassList();this._ih='';this._tc='';this.value='';this.dataset={}}set className(v){this.attrs.class=v;this.classList.set=new Set(String(v).split(/\\s+/).filter(Boolean))}get className(){return Array.from(this.classList.set).join(' ')}set id(v){this.attrs.id=v}get id(){return this.attrs.id||''}setAttribute(k,v){this.attrs[k]=String(v);if(k==='class')this.className=v;if(k.startsWith('data-'))this.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=String(v)}getAttribute(k){return this.attrs[k]??null}appendChild(c){this.children.push(c);return c}set innerHTML(v){this._ih=String(v)}get innerHTML(){return this._ih}set textContent(v){this._tc=String(v)}get textContent(){return this._tc||this._ih}querySelectorAll(sel){const r=[],cls=sel.startsWith('.')?sel.slice(1):null;const w=e=>{for(const ch of e.children){if(cls&&ch.classList.contains(cls))r.push(ch);w(ch)}};w(this);return r}querySelector(sel){return this.querySelectorAll(sel)[0]||null}}"
                "const ids={};for(const id of ['sourceBadge','tzBadge','rootIdBadge','runTitle','runSubtitle','searchInput','summaryGrid','ganttPanel','trajectoryTimeline','copiedToast']){ids[id]=new MockEl('div');ids[id].id=id}"
                "const root=new MockEl('body');Object.values(ids).forEach(e=>root.appendChild(e));"
                "global.document={getElementById:id=>ids[id]||null,createElement:t=>new MockEl(t),querySelectorAll:s=>root.querySelectorAll(s)};"
                "global.navigator={};global.setTimeout=()=>0;\n"
                + m.group(1)
                + "\nids.searchInput.value='sentinel';filterSwarm();"
                + "const gr=(ids.ganttPanel.innerHTML.match(/class=\"gantt-row\"/g)||[]).length;"
                + "const vi=root.querySelectorAll('.timeline-item').filter(e=>e.style.display!=='none').length;"
                + "if(gr!==1||vi!==1){console.error({gr,vi});process.exit(2);}"
            )
            proc = subprocess.run(["node", "-"], input=dom_probe, text=True, capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_peak_concurrency_and_empty_gantt(self) -> None:
        self.assertEqual(compute_peak_concurrency([(0, 10), (2, 8), (5, 12)]), 3)
        g = compute_gantt_layout([])
        self.assertFalse(g["has_timing"])

    def test_timeline_sdk_reminders_notices_fast_wakeup_and_user_input_gap(self) -> None:
        # SYSTEM_SDK and sender=system [Notice] preserve idle_since_dt;
        # fast wakeup >= 0.5s splits; [Notice] is NOT treated as wakeup;
        # [Notice] quoted inside a real message IS a wakeup;
        # USER_INPUT gap is measured from cur_end (not trailing SDK step).
        steps = [
            {"step_index": 0, "source": "SYSTEM_SDK", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T10:00:00Z", "content": "reminder"},
            {"step_index": 1, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T10:00:00Z", "content": "[Notice] timestamp=2026-11-15T10:00:00Z sender=system content=ignore notice"},
            {"step_index": 2, "source": "USER_EXPLICIT", "type": "USER_INPUT", "created_at": "2026-11-15T10:00:01Z", "content": "<USER_REQUEST>Start</USER_REQUEST>"},
            {"step_index": 3, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T10:00:05Z", "content": "Waiting", "tool_calls": []},
            {"step_index": 4, "source": "SYSTEM_SDK", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T10:00:05.5Z", "content": "reminder"},
            {"step_index": 5, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T10:00:05.8Z", "content": "[Notice] timestamp=2026-11-15T10:00:05.8Z sender=system content=system notice"},
            {"step_index": 6, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T10:00:06.0Z", "content": "[Message] timestamp=2026-11-15T10:00:06Z sender=child1 content=Handle [Notice] sender=system"},
            {"step_index": 7, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T10:00:08Z", "content": "Round 2 done", "tool_calls": []},
            {"step_index": 8, "source": "SYSTEM_SDK", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-15T10:00:19.5Z", "content": "reminder"},
            {"step_index": 9, "source": "USER_EXPLICIT", "type": "USER_INPUT", "created_at": "2026-11-15T10:00:20Z", "content": "<USER_REQUEST>Next prompt</USER_REQUEST>"},
            {"step_index": 10, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T10:00:25Z", "content": "Round 3 done", "tool_calls": []},
        ]
        turns = segment_active_turns(steps)
        self.assertEqual(len(turns), 3)
        self.assertEqual(turns[0]["duration_s"], 4.0)
        self.assertEqual(turns[1]["duration_s"], 2.0)
        self.assertEqual(turns[2]["duration_s"], 5.0)

    def test_step0_header_spawns_guards_docs_and_summary(self) -> None:
        # 1. Step0 header skips SYSTEM_SDK and sender=system [Notice], keeps message quoting [Notice], strips XML tags
        dt, sender, prompt = _parse_step0_header([
            {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM_SDK", "created_at": "2026-11-15T10:00:00Z", "content": "sdk"},
            {"step_index": 1, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-15T10:00:00Z", "content": "[Notice] timestamp=2026-11-15T10:00:00Z sender=system content=ignore"},
            {"step_index": 2, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-15T10:00:01Z", "content": "[Message] timestamp=2026-11-15T10:00:01Z sender=parent-1 content=Check [Notice] handling</SYSTEM_MESSAGE>"},
        ])
        self.assertIsNotNone(dt)
        self.assertEqual(sender, "parent-1")
        self.assertEqual(prompt, "Check [Notice] handling")

        _, root_sender, root_prompt = _parse_step0_header([
            {
                "step_index": 0,
                "type": "USER_INPUT",
                "created_at": "2026-11-15T10:00:00Z",
                "content": "<ADDITIONAL_METADATA>meta</ADDITIONAL_METADATA><USER_REQUEST>Build feature</USER_REQUEST><USER_SETTINGS_CHANGE>Changed `Model Selection` from None to Gemini 4 Argon (Medium).</USER_SETTINGS_CHANGE>",
            }
        ])
        self.assertIsNone(root_sender)
        self.assertEqual(root_prompt, "Build feature")

        # 2. Spawns gating, nested JSON raw_decode, USER_INPUT + error clearing
        spawns = _extract_subagent_spawns([
            {"step_index": 0, "type": "GENERIC", "created_at": "2026-11-15T10:00:01Z", "content": 'Created the following subagent:\n{"conversationId": "phantom-read-file"}'},
            {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T10:00:02Z", "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "Old", "Prompt": "old"}}]},
            {"step_index": 2, "type": "USER_INPUT", "created_at": "2026-11-15T10:00:03Z", "content": "Cancel"},
            {"step_index": 3, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T10:00:04Z", "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "ErrAgent", "Prompt": "err"}}]},
            {"step_index": 4, "type": "GENERIC", "created_at": "2026-11-15T10:00:05Z", "content": "Encountered error in step execution: subagent failed"},
            {"step_index": 5, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T10:00:06Z", "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "GoodAgent", "Prompt": "good"}}]},
            {"step_index": 6, "type": "GENERIC", "created_at": "2026-11-15T10:00:07Z", "content": 'Created the following subagent:\n{"conversationId": "good-1", "extra": {"nested": 1}}\n{"conversationId": "phantom-extra"}'},
        ])
        self.assertEqual(list(spawns.keys()), ["good-1"])
        self.assertEqual(spawns["good-1"]["requested_type"], "GoodAgent")

        # 3. Settings change extraction scoped to USER_INPUT and <USER_SETTINGS_CHANGE> tag
        changes = _extract_settings_model_changes([
            {"step_index": 0, "type": "USER_INPUT", "content": "<USER_REQUEST>Model Selection from A to B</USER_REQUEST><USER_SETTINGS_CHANGE>Changed `Model Selection` from None to Gemini 3.8 Flash (High).</USER_SETTINGS_CHANGE>"},
            {"step_index": 1, "type": "GENERIC", "content": "<USER_SETTINGS_CHANGE>Changed `Model Selection` from A to FakeModel.</USER_SETTINGS_CHANGE>"},
        ])
        self.assertEqual(changes, [(0, "Gemini 3.8 Flash (High)")])

        # 4. Failed write tool calls are excluded from produced docs
        with tempfile.TemporaryDirectory() as ws:
            docs = _extract_produced_docs([
                {"step_index": 1, "type": "PLANNER_RESPONSE", "tool_calls": [{"name": "write_to_file", "args": {"TargetFile": "bad.py"}}]},
                {"step_index": 2, "type": "GENERIC", "content": "Created At: 2026-11-15\nError invalid tool call: missing Overwrite"},
                {"step_index": 3, "type": "PLANNER_RESPONSE", "tool_calls": [{"name": "write_to_file", "args": {"TargetFile": "error_handler.py"}}]},
                {"step_index": 4, "type": "GENERIC", "content": f"Created At: 2026-11-15\nCreated file file://{os.path.join(ws, 'error_handler.py')}"},
            ], ws)
            self.assertEqual([d["name"] for d in docs], ["error_handler.py"])

        # 5. Summary preserves JSON-only responses and falls back to send_message
        json_summary = _extract_summary([
            {"step_index": 0, "type": "PLANNER_RESPONSE", "content": '```json\n{"verdict": "REJECT", "findings": ["bug1"]}\n```'},
        ], "idle")
        self.assertNotEqual(json_summary, "[code/json output]")
        self.assertIn('"verdict": "REJECT"', json_summary)

        msg_summary = _extract_summary([
            {"step_index": 0, "type": "PLANNER_RESPONSE", "content": "", "tool_calls": [{"name": "send_message", "args": {"Recipient": "coord", "Message": "@coordinator done: PASS."}}]},
        ], "idle")
        self.assertEqual(msg_summary, "@coordinator done: PASS.")

    def test_run_selection_models_sequential_siblings_phase_and_cli_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "proj")
            agy = os.path.join(tmp, "agy")
            os.makedirs(ws)
            uri = json.dumps([f"file://{ws}"])

            boost_root = "boost_00-0000-0000-0000-000000000001"
            boost_t2 = "boost_02-0000-0000-0000-000000000002"
            swarm_root = "swarm_00-0000-0000-0000-000000000003"
            spec_val = "specval1-0000-0000-0000-000000000004"
            spec_aud = "specaud1-0000-0000-0000-000000000005"
            eng_id = "eng11111-0000-0000-0000-000000000006"
            no_db_child = "nodbchld-0000-0000-0000-000000000007"

            _create_db(agy, [
                # Newer /boost-only multi-agent run (must be deprioritized behind swarm_root)
                (boost_root, "Boost Only", "", "", 0, 4, "2026-11-15T18:00:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                (boost_t2, "", "DeepCoder", boost_root, 1, 2, "2026-11-15T18:00:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                # Older non-/boost swarm run (must win auto-select!)
                (swarm_root, "Swarm Run", "", "", 0, 12, "2026-11-15T15:00:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                (spec_val, "", "spec-validator", swarm_root, 1, 4, "2026-11-15T14:10:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                # DB row with missing parent_conversation_id & nesting_depth=0 to verify BFS fallback
                (spec_aud, "", "auditor", "", 0, 2, "2026-11-15T14:05:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                (eng_id, "", "engineer", swarm_root, 1, 6, "2026-11-15T14:55:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
            ])

            _write_transcript(agy, boost_root, [
                {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-15T18:00:00Z", "content": "<USER_REQUEST>/boost fix</USER_REQUEST>"},
            ])
            _write_transcript(agy, boost_t2, [
                {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-15T18:00:02Z", "content": f"[Message] timestamp=2026-11-15T18:00:02Z sender={boost_root} content=Work"},
            ])

            # Root swarm transcript has two <USER_SETTINGS_CHANGE> events; spec_val spawned under Model A, eng under Model B
            _write_transcript(agy, swarm_root, [
                {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-15T14:00:00Z", "content": "<USER_REQUEST>Start swarm</USER_REQUEST><USER_SETTINGS_CHANGE>Changed `Model Selection` from None to Model Alpha (Med).</USER_SETTINGS_CHANGE>"},
                {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T14:00:05Z", "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "spec-validator", "Model": "inherit", "Prompt": "Validate spec"}}]},
                {"step_index": 2, "type": "GENERIC", "created_at": "2026-11-15T14:00:06Z", "content": f'Created the following subagent:\n{{"conversationId": "{spec_val}"}}'},
                {"step_index": 3, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T14:00:07Z", "content": "Spec validation started.", "tool_calls": []},
                {"step_index": 4, "type": "USER_INPUT", "created_at": "2026-11-15T14:20:00Z", "content": "<USER_REQUEST>Proceed to build</USER_REQUEST><USER_SETTINGS_CHANGE>Changed `Model Selection` from Model Alpha (Med) to Model Beta (High).</USER_SETTINGS_CHANGE>"},
                {"step_index": 5, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T14:20:05Z", "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "engineer", "Model": "inherit", "Prompt": "Build it"}}]},
                {"step_index": 6, "type": "GENERIC", "created_at": "2026-11-15T14:20:06Z", "content": f'Created the following subagent:\n{{"conversationId": "{eng_id}"}}'},
                {"step_index": 7, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T14:55:00Z", "content": "Swarm complete.", "tool_calls": []},
            ])

            # spec_val runs in two separate turns (14:00:06..14:01:00 and 14:10:00..14:11:00); eng runs at 14:20:06..14:25:00
            # Wait: spec_val and eng do NOT overlap (eng starts at 14:20:06, after spec_val's 14:11:00),
            # and even if spec_val had a 2nd turn at 14:30:00..14:31:00, they STILL do not overlap in active turns!
            _write_transcript(agy, spec_val, [
                {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-15T14:00:06Z", "content": f"[Message] timestamp=2026-11-15T14:00:06Z sender={swarm_root} content=Validate spec"},
                {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T14:00:10Z", "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "auditor", "Role": "Adversarial Spec Reviewer", "Model": "inherit", "Prompt": "Review"}}]},
                {"step_index": 2, "type": "GENERIC", "created_at": "2026-11-15T14:00:11Z", "content": f'Created the following subagent:\n{{"conversationId": "{spec_aud}"}}'},
                {"step_index": 3, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T14:01:00Z", "content": "Waiting.", "tool_calls": []},
                {"step_index": 4, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-15T14:30:00Z", "content": f"[Message] timestamp=2026-11-15T14:30:00Z sender={swarm_root} content=Followup"},
                {"step_index": 5, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T14:31:00Z", "content": "Done.", "tool_calls": []},
            ])
            _write_transcript(agy, spec_aud, [
                {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-15T14:00:11Z", "content": f"[Message] timestamp=2026-11-15T14:00:11Z sender={spec_val} content=Review"},
                {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T14:05:00Z", "model": "gemini-4-hydrogen-high", "content": "Audited.", "tool_calls": []},
            ])
            _write_transcript(agy, eng_id, [
                {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-15T14:20:06Z", "content": f"[Message] timestamp=2026-11-15T14:20:06Z sender={swarm_root} content=Build it"},
                {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T14:20:10Z", "tool_calls": [{"name": "invoke_subagent", "args": {"TypeName": "builder", "Prompt": "Subbuild"}}]},
                {"step_index": 2, "type": "GENERIC", "created_at": "2026-11-15T14:20:11Z", "content": f'Created the following subagent:\n{{"conversationId": "{no_db_child}"}}'},
                {"step_index": 3, "type": "PLANNER_RESPONSE", "created_at": "2026-11-15T14:25:00Z", "content": "Built.", "tool_calls": []},
            ])
            # Child with NO DB row at all; tests BFS fallback_parent and fallback_depth + descendant spawn_meta protection
            _write_transcript(agy, no_db_child, [
                {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-15T14:20:11Z", "content": f"[Message] timestamp=2026-11-15T14:20:11Z sender={eng_id} content=Subbuild"},
                {"step_index": 1, "type": "GENERIC", "created_at": "2026-11-15T14:21:00Z", "content": f'Created the following subagent:\n{{"conversationId": "{eng_id}"}}'},
            ])

            # 1. Auto-select picks swarm_root over newer boost_root
            self.assertEqual(select_agy_run(agy, ws), swarm_root)
            # 2. Subagent -c <id> resolves upward to root; LIKE wildcard '_' does not match arbitrary chars
            self.assertEqual(select_agy_run(agy, ws, spec_aud[:8]), swarm_root)
            self.assertEqual(select_agy_run(agy, ws, boost_t2[:8]), boost_root)
            self.assertIsNone(select_agy_run(agy, ws, "swarm_99"))

            data = parse_agy_run(agy, swarm_root, ws)
            by_id = {a["conv_id"]: a for a in data["agents"]}

            # 3. Multi-turn sequential siblings (spec_val 14:00..14:01 & 14:30..14:31, eng 14:20..14:25) stay serial
            self.assertEqual(by_id[spec_val]["mode"], "serial")
            self.assertEqual(by_id[eng_id]["mode"], "serial")

            # 4. Validator child phase inheritance + BFS fallback depth/parent
            self.assertEqual(by_id[spec_val]["phase"], "discovery")
            self.assertEqual(by_id[spec_aud]["phase"], "discovery")
            self.assertEqual(by_id[spec_aud]["depth"], 2)
            self.assertEqual(by_id[spec_aud]["parent_id"], spec_val)
            self.assertEqual(by_id[no_db_child]["depth"], 2)
            self.assertEqual(by_id[no_db_child]["parent_id"], eng_id)
            self.assertEqual(by_id[eng_id]["spawn_step_index"], 5)

            # 5. Model resolution: spec_val spawned under Model Alpha, eng under Model Beta, spec_aud via PLANNER_RESPONSE
            self.assertEqual(by_id[spec_val]["model"], "Model Alpha (Med)")
            self.assertEqual(by_id[eng_id]["model"], "Model Beta (High)")
            self.assertEqual(by_id[no_db_child]["model"], "Model Beta (High)")
            self.assertEqual(by_id[spec_aud]["model"], "gemini-4-hydrogen-high")
            self.assertEqual(
                set(data["summary"]["models_used"]),
                {"Model Beta (High)", "Model Alpha (Med)", "gemini-4-hydrogen-high"},
            )

            # 6. CLI catches ValueError cleanly instead of raising traceback
            empty_id = "empty000-0000-0000-0000-000000000009"
            os.makedirs(os.path.join(agy, "brain", empty_id))
            rc = generator.main(["--workspace", ws, "--agy-dir", agy, "-c", empty_id])
            self.assertEqual(rc, 1)

    def test_boost_fallback_when_no_swarm_exists_and_worker_concurrency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "proj")
            agy = os.path.join(tmp, "agy")
            os.makedirs(ws)
            uri = json.dumps([f"file://{ws}"])
            boost_root = "boostrun-0000-0000-0000-000000000001"
            boost_t2 = "boostt20-0000-0000-0000-000000000002"
            _create_db(agy, [
                (boost_root, "Only Boost", "", "", 0, 2, "2026-11-15T18:00:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
                (boost_t2, "", "DeepCoder", boost_root, 1, 2, "2026-11-15T18:00:00Z", uri, "CASCADE_RUN_STATUS_IDLE", 0),
            ])
            _write_transcript(agy, boost_root, [
                {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-15T18:00:00Z", "content": "<USER_REQUEST>/boost fix</USER_REQUEST>"},
            ])
            _write_transcript(agy, boost_t2, [
                {"step_index": 0, "type": "SYSTEM_MESSAGE", "source": "SYSTEM", "created_at": "2026-11-15T18:00:02Z", "content": f"[Message] timestamp=2026-11-15T18:00:02Z sender={boost_root} content=Work"},
            ])
            self.assertEqual(select_agy_run(agy, ws), boost_root)

        # Parent waiting on child with 2s handoff overlap must report concurrency = 1 (not 2)
        self.assertEqual(
            compute_worker_concurrency([
                {"conv_id": "p", "parent_id": "", "turns": [{"start_ms": 0, "end_ms": 5000}, {"start_ms": 28000, "end_ms": 32000}]},
                {"conv_id": "c", "parent_id": "p", "turns": [{"start_ms": 3000, "end_ms": 30000}]},
            ]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
