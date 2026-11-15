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
1. Queries `~/.gemini/antigravity-cli/conversation_summaries.db` (or `$AGY_DATA_DIR`) to locate root conversations for the current workspace and auto-selects the newest run with subagents.
2. Walks the full parent → child → grandchild subagent tree and parses each conversation's `brain/<id>/.system_generated/logs/transcript_full.jsonl` (falling back to `transcript.jsonl`).
3. Segments each agent's transcript into active execution turns (splitting on `USER_INPUT` or `send_message` wakeups across idle boundaries) to compute:
   - **Wall-clock start / end** (local clock + UTC ISO timestamps)
   - **Active wall-clock time** (merged active intervals excluding human review pauses) vs. **Cumulative subagent time**
   - **Parallelism speedup** and **peak concurrency**
   - **Gantt / Waterfall coordinates** with both **Compressed Pauses** (default when human-idle gaps exist) and **True Wall-Clock** views
   - **Step, tool-call, token counts**, and **produced/modified file links**
4. Writes the self-contained HTML dashboard to `.agents/trajectory.html` (auto-creating `.agents/` if absent).

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
