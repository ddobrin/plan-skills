---
name: teamwork-trajectory
description: Automatically scans the .agents/ directory, parses agent briefing and handoff records, and compiles a stunning interactive HTML visualization timeline written directly under .agents/trajectory.html.
tools:
  - run_command
  - view_file
  - write_to_file
  - list_dir
  - grep_search
  - find_by_name
---

# Teamwork Trajectory Skill

This skill allows you to dynamically compile an interactive, dark-mode visual timeline of all agents executed by your swarm.

## Usage
- Trigger this skill when the user asks to "generate trajectory", "visualize teamwork", "trace agents", or "update trajectory dashboard".
- Run the bundled `generator.py` script (located in this skill's directory, e.g. `python3 plugins/plan/skills/teamwork-trajectory/generator.py` or `python3 ~/.gemini/config/plugins/plan/skills/teamwork-trajectory/generator.py`) via `run_command` to scan `.agents/` in the current project workspace and output `.agents/trajectory.html`.
