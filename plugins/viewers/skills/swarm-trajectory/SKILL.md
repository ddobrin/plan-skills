---
name: swarm-trajectory
description: Compiles an interactive dark-mode HTML post-run report (.agents/swarm-trajectory.html) for native /swarm runs from AGY swarm board artifacts (swarm.json, members.json, board.jsonl) and member transcripts, detailing what each worker delivered, wall-clock vs swarm_wait time, where time and tokens went, and whether the result was verified.
tools:
  - run_command
  - read_file
  - write_file
---

# Swarm Trajectory Skill

Compiles a self-contained, interactive dark-mode HTML post-run report for native `/swarm` runs, giving you a durable artifact you can keep after the live `/swarm board` closes.

## Triggers
Activate this skill on demand after `/swarm` completes (or stops) when the user asks to:
- `"swarm trajectory"`, `"visualize swarm"`, `"swarm report"`, `"swarm summary"`
- `"what did the swarm deliver"`, `"where did the swarm time and tokens go"`, `"was the swarm verified"`
- `"trace swarm"`, `"post-run swarm visualization"`

## How It Works
`generator.py` reads **native `/swarm` telemetry** (`~/.gemini/antigravity-cli/brain/<swarm_id>/.system_generated/swarm/` + `conversation_summaries.db` + member `transcript_full.jsonl` / `transcript.jsonl`, or `$AGY_DATA_DIR`):
1. **Swarm Discovery:** Locates native `/swarm` runs for the workspace (`swarm.json`, `members.json`, `board.jsonl`), auto-selecting the newest run. Passing any worker or coordinator conversation ID (or unique prefix) to `-c` resolves upward to its swarm root.
2. **Deliverables & Lifecycle Accuracy:** Parses `board.jsonl` `[done]` posts, assignments (`kind: "brief"`), `@mentions`, channels, and `write_file`/`edit_file` outputs so gracefully retired workers (`killed: true` after `[done]`) are accurately shown as **Completed · Retired** rather than interrupted.
3. **Swarm-Aware Timing (`swarm_wait` vs Active Work):** Separates active execution turns from free `swarm_wait` board parking and background task waits, computing core wall-clock span, monitor tail overhead, worker active time vs wait time, parallelism speedup, and peak active worker concurrency.
4. **Where Time & Tokens Went:** Aggregates `input_tokens`, `output_tokens`, `cache_read_tokens`, cache-hit %, and active/wait time per member, per role group (`Coordinator`, `Research & Architecture`, `Implementation`, `Verification`, `Monitor`, `Narrator`), and per model (including mid-run model switches).
5. **Verification & Quality Gate:** Audits whether a `verifier` (or author self-checks) ran after the last author file edit, inspects synchronous and background `run_command` exit codes, and renders an explicit verification verdict (`Verified & Passed`, `Stale Verification`, `Checks Failed`, or `Unverified`) alongside the archived board handoff ledger.
6. Writes the self-contained HTML dashboard to `.agents/swarm-trajectory.html` (overridable via `-o` / `--output`).

## Usage
Run `generator.py` from the target project workspace via `run_command`:

```bash
# Auto-select latest /swarm run in the current workspace
python3 ~/.gemini/config/plugins/viewers/skills/swarm-trajectory/generator.py

# List matching /swarm runs for the current workspace
python3 ~/.gemini/config/plugins/viewers/skills/swarm-trajectory/generator.py --list

# Render a specific swarm or worker conversation ID (full UUID or unique prefix) to a custom path
python3 ~/.gemini/config/plugins/viewers/skills/swarm-trajectory/generator.py -c <conv-id> -o .agents/swarm-trajectory.html
```

If invoked inside the `plan-skills` repository itself, you can also run `python3 plugins/viewers/skills/swarm-trajectory/generator.py`.
