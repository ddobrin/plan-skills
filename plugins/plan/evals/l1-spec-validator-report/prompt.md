---
name: l1-spec-validator-report
tags: [blocking, contract]
runs: 3
max_turns: 60
timeout_seconds: 600
allowed_tools: [view_file, find_by_name, list_dir, grep_search, invoke_subagent, send_message, run_command, write_to_file]
---

Use the plan plugin's spec-validator skill to validate plans/active_milestones/demo/spec.md. Work without asking me questions.
