---
name: teamwork-trajectory
description: Compiles an interactive dark-mode HTML trajectory dashboard (.agents/trajectory.html) with wall-clock timestamps, turn/round timing, parallelism speedup, and a Gantt waterfall from AGY live telemetry (conversation_summaries.db + transcript*.jsonl), with legacy .agents/ fallback.
tools:
  - run_command
  - read_file
  - write_file
---

# Teamwork Trajectory Skill

Compiles a self-contained, interactive HTML trajectory and timing dashboard for multi-agent AGY runs.

## Triggers
Activate this skill when the user asks to:
- "generate trajectory", "visualize teamwork", "trace agents", "update trajectory dashboard"
- "agent timing", "wall clock trajectory", "show swarm timeline"

## How It Works
`generator.py` reads **AGY live telemetry** first (falling back to legacy `.agents/<role>/BRIEFING.md` and `handoff.md` directories if no AGY multi-agent run matches):
1. Queries `~/.gemini/antigravity-cli/conversation_summaries.db` (or `$AGY_DATA_DIR`) to locate root conversations for the current workspace and auto-selects the newest non-`/boost` multi-agent swarm run (deprioritizing `/boost`-only runs behind non-`/boost` swarm runs, while keeping `/boost` runs selectable via `-c` or as a fallback when no non-`/boost` multi-agent run exists). Passing any subagent ID or unique prefix to `-c` resolves upward to its root conversation.
2. Walks the full parent → child → grandchild subagent tree (gating `"Created the following subagent"` parsing on pending `invoke_subagent` calls, clearing stale pending calls on `USER_INPUT` / new batches / case-insensitive error `GENERIC` responses, and protecting parent `spawn_meta` from descendant overwrites) and parses each conversation's `brain/<id>/.system_generated/logs/transcript_full.jsonl` (falling back to `transcript.jsonl`).
3. Segments each agent's transcript into active execution turns while preserving idle boundaries across `SYSTEM_SDK` periodic reminders and ignoring `sender=system` `[Notice]` steps, splitting `USER_INPUT` gaps (`>= 1s` from `cur_end`) and `send_message` wakeups (`>= 0.5s` across idle boundaries) to compute:
   - **Wall-clock start / end** (local clock + UTC ISO timestamps)
   - **Active wall-clock time** (merged active intervals excluding human review pauses) vs. **Cumulative subagent time**
   - **Parallelism speedup**, **active turn-interval sibling parallelism** (with 3s handoff tolerance), and **worker/leaf peak concurrency** (excluding parent-child wait/handoff overlap)
   - **Resolved models & `models_used` summary** (`PLANNER_RESPONSE["model"]` → explicit `Model` arg → `USER_INPUT`-scoped `<USER_SETTINGS_CHANGE>` active at `spawn_step_index` → top-down parent inheritance)
   - **Gantt / Waterfall coordinates** with both **Compressed Pauses** (default when human-idle gaps exist) and **True Wall-Clock** views
   - **Agent status badges, step/tool-call/token counts, summaries** (preserving JSON-only outputs and falling back to `send_message` payloads), and **successful produced/modified file links** (filtering failed write tool calls)
4. Writes the self-contained HTML dashboard to `.agents/trajectory.html` (auto-creating `.agents/` if absent), with synchronized phase + search filtering across the Gantt waterfall and timeline cards, separate parallel wave containers, and clickable transcript links (`transcript_full.jsonl` or `transcript.jsonl`).

## Usage
Run `generator.py` from the target project workspace via `run_command`:

```bash
# Auto-select latest multi-agent AGY run in the current workspace
python3 ~/.gemini/config/plugins/viewers/skills/teamwork-trajectory/generator.py

# List matching AGY runs for the current workspace
python3 ~/.gemini/config/plugins/viewers/skills/teamwork-trajectory/generator.py --list

# Render a specific conversation ID (full UUID or unique prefix) to a custom path
python3 ~/.gemini/config/plugins/viewers/skills/teamwork-trajectory/generator.py -c <conv-id> -o .agents/trajectory.html
```

If invoked inside the `plan-skills` repository itself, you can also run `python3 plugins/viewers/skills/teamwork-trajectory/generator.py`.
