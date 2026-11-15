---
name: boost-trajectory
description: Compiles an interactive dark-mode HTML trajectory dashboard (.agents/boost-trajectory.html) for /boost runs from AGY live telemetry (conversation_summaries.db + transcript*.jsonl), visualizing the 3-tier Orchestrator -> DeepCoder/DeepInvestigator -> *WorkerL0/*ImprovementWorker hierarchy, wall-clock Gantt waterfall, models, and structured send_message report cards.
tools:
  - run_command
  - read_file
  - write_file
---

# Boost Trajectory Skill

Compiles a self-contained, interactive dark-mode HTML execution dashboard for `/boost` runs (both **Delegation** and **Solo** routines).

## Triggers
Activate this skill on demand after `/boost` completes when the user asks to:
- `"boost trajectory"`, `"visualize boost"`, `"trace boost"`, `"update boost trajectory"`
- `"boost timeline"`, `"boost report"`, `"visualize /boost execution"`

## How It Works
`generator.py` reads **AGY live telemetry** (`~/.gemini/antigravity-cli/conversation_summaries.db` or `$AGY_DATA_DIR`, plus `brain/<id>/.system_generated/logs/transcript_full.jsonl` / `transcript.jsonl`):
1. Discovers root `/boost` conversations for the current workspace (identifying both explicit `/boost` / `<ORCHESTRATOR>` turns and unmarked follow-ups that spawn `DeepCoder` / `DeepInvestigator`), **preferring Delegation `/boost` runs** on auto-select and falling back to Solo `/boost` runs when none exist.
2. Defaults to the **latest `/boost` invocation** in mixed/multi-`/boost` root conversations (pass `--all-invocations` or `--full-session` to render every `/boost` invocation grouped as separate pipelines).
3. Walks the 3-tier `/boost` hierarchy:
   - **Tier 1:** `Orchestrator` (root conversation slice for the invocation)
   - **Tier 2:** `DeepCoder` / `DeepInvestigator` (handles `steps[0]` `SYSTEM_SDK` reminders + `steps[1]` dispatch header, plus batched `Subagents` and flat `invoke_subagent` calls)
   - **Tier 3:** `DeepCoderWorkerL0`, `DeepCoderImprovementWorker`, `DeepInvestigatorWorkerL0`, `DeepInvestigatorImprovementWorker` (including interrupted/incomplete workers)
4. Extracts model telemetry (`PLANNER_RESPONSE["model"]` or `<USER_SETTINGS_CHANGE>`), active turn segmentation without `SYSTEM_SDK` turn-merging, worker concurrency without parent-child handoff overlap inflation, and **structured `send_message` report cards** (with `Skepticism Disclaimer` callouts, `Known Issues` severity pills, and collapsible Markdown sections).
5. Writes the self-contained HTML dashboard to `.agents/boost-trajectory.html` (overridable via `-o` / `--output`).

## Usage
Run `generator.py` from the target project workspace via `run_command`:

```bash
# Auto-select latest /boost run (prefers Delegation, scopes to latest invocation)
python3 ~/.gemini/config/plugins/viewers/skills/boost-trajectory/generator.py

# List matching /boost AGY runs for the current workspace
python3 ~/.gemini/config/plugins/viewers/skills/boost-trajectory/generator.py --list

# Render all /boost invocations in a mixed/multi-/boost conversation
python3 ~/.gemini/config/plugins/viewers/skills/boost-trajectory/generator.py --all-invocations

# Render a specific conversation ID (full UUID or unique prefix) to a custom path
python3 ~/.gemini/config/plugins/viewers/skills/boost-trajectory/generator.py -c <conv-id> -o .agents/boost-trajectory.html
```

If invoked inside the `plan-skills` repository itself, you can also run `python3 plugins/viewers/skills/boost-trajectory/generator.py`.
