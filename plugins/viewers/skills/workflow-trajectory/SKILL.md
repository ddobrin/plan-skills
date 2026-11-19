---
name: workflow-trajectory
description: Compiles an interactive dark-mode HTML blueprint and post-run report (.agents/workflow-trajectory.html) for AGY dynamic `run_workflow` scripts and executions — statically visualizing script phases, parallel/pipeline topology, agents, skills, and tools before a run, and joining live task logs and child transcripts upon completion to show what each worker delivered, wall-clock speedup, where time and tokens went, and whether results were verified.
tools:
  - run_command
  - read_file
  - write_file
---

# Workflow Trajectory Skill

Compiles a self-contained, interactive dark-mode HTML report for AGY dynamic `/run-workflow` (`run_workflow` tool) scripts — supporting **both** pre-run static blueprint inspection (when you write or start a workflow script) and post-run / in-progress telemetry auditing (upon completion), giving you a durable HTML file you can keep.

## Triggers
Activate this skill on demand before, during, or after a `run_workflow` execution when the user asks to:
- `"workflow trajectory"`, `"visualize workflow"`, `"workflow report"`, `"workflow blueprint"`
- `"inspect workflow script"`, `"visualize run-workflows"`, `"run_workflow report"`
- `"what did the workflow deliver"`, `"where did the workflow time and tokens go"`, `"was the workflow verified"`

## How It Works
`generator.py` supports two complementary modes:
1. **Pre-Run Static Blueprint Mode (`--script /abs/path/workflow.py`):**
   - Uses Python's stdlib `ast` (handling top-level `await`) to parse the workflow script and optional sibling `workflow.json` manifest before execution.
   - Maps `phase(...)`, `parallel(...)`, `pipeline(...)`, one-shot and stateful multi-turn `agent(...)` definitions (`role`, `type_name`, `model`, `workspace`, `schema`), `call_tool(...)`, `trajectory(...)`, `args.get(...)` inputs, and declared skills.
   - Surfaces actionable pre-flight checks (e.g., `parallel` editing prompts on `workspace="inherit"`, un-awaited `agent()` calls, missing `role=` titles, heavy fan-out on `model="inherit"`, or missing verification phases).
2. **Post-Run / In-Progress Telemetry Mode (default auto-select or `-c <conv-id>`):**
   - Discovers `run_workflow` tool calls in AGY parent transcripts (`~/.gemini/antigravity-cli/brain/<id>/.system_generated/logs/transcript_full.jsonl` or `$AGY_DATA_DIR`), reads `tasks/task-<N>.log` and `Logs:` / `Output:`, and links spawned workflow child conversations (which have `parent_conversation_id == ""` in `conversation_summaries.db` and are only linked via the workflow log UUIDs).
   - Joins the static script blueprint with each spawned worker's full transcript to report:
     - **What each worker delivered:** untruncated `finish(result=...)` structured JSON/text payloads, files created/edited, and per-turn prompt history for stateful multi-turn agents.
     - **Skills & tools inventory:** compares script-declared skills and `call_tool(...)` calls against skills actually loaded (`SKILL.md` reads / custom `type_name`) and tools executed by workers at runtime.
     - **Wall-clock & parallelism:** span, cumulative worker active time, peak concurrent workers, speedup factor, and interactive `Compressed Pauses` vs `True Wall-Clock` Gantt waterfall.
     - **Where time & tokens went:** per-worker, per-phase, and per-model token (`input`, `output`, `cache_read`, cache-hit %) and active-time breakdowns with interactive metric toggles.
     - **Verification & Quality Gate:** combines structured verifier `finish` verdicts (`passed`, `ok`, `approved`, `verdict`) with `run_command` exit codes and author-edit vs verifier-check ordering (`VERIFIED`, `STALE`, `FAILED`, `PARTIAL`, `SELF_CHECKED`, `UNVERIFIED`).
3. Writes the self-contained HTML report to `.agents/workflow-trajectory.html` (overridable via `-o` / `--output`).

## Usage
Run `generator.py` from the target project workspace via `run_command`:

```bash
# Post-run: auto-select latest run_workflow run for the current workspace
python3 ~/.gemini/config/plugins/viewers/skills/workflow-trajectory/generator.py

# Pre-run: inspect a workflow script before running it
python3 ~/.gemini/config/plugins/viewers/skills/workflow-trajectory/generator.py --script /abs/path/to/workflow.py

# List discovered run_workflow runs for the current workspace (add --all-workspaces to scan globally)
python3 ~/.gemini/config/plugins/viewers/skills/workflow-trajectory/generator.py --list

# Render a specific parent or workflow-worker conversation ID (or unique prefix), optionally selecting an earlier invocation
python3 ~/.gemini/config/plugins/viewers/skills/workflow-trajectory/generator.py -c <conv-id> --run-index 1 -o .agents/workflow-trajectory.html
```

If invoked inside the `plan-skills` repository itself, you can also run `python3 plugins/viewers/skills/workflow-trajectory/generator.py`.
