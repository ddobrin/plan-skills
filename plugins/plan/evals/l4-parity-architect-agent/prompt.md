---
name: l4-parity-architect-agent
tags: [report, parity]
runs: 3
max_turns: 40
timeout_seconds: 600
allowed_tools: [view_file, find_by_name, list_dir, grep_search, invoke_subagent, send_message, write_to_file, replace_file_content, multi_replace_file_content]
---

Dispatch the plan plugin's architect agent (invoke_subagent, TypeName architect) to write the plan for plans/active_milestones/demo/spec.md. Work without asking me questions.
