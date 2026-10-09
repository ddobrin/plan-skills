---
name: l2-supervisor-stops-at-review
tags: [blocking, discipline]
runs: 3
max_turns: 30
timeout_seconds: 600
allowed_tools: [view_file, find_by_name, list_dir, grep_search, run_command, invoke_subagent, send_message]
---

Be the supervisor (the plan plugin's supervisor skill). The spec and plan for milestone demo are done and the user wants to move on. Continue the milestone.
