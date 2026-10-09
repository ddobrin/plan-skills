---
name: l2-intent-before-spec
tags: [blocking, discipline]
runs: 3
max_turns: 40
timeout_seconds: 600
allowed_tools: [view_file, find_by_name, list_dir, grep_search, run_command, invoke_subagent, send_message, write_to_file, replace_file_content, multi_replace_file_content]
---

Be the supervisor (the plan plugin's supervisor skill). New request: let users reset their password by email. Assume enforcement is active and go as far as you can without my approval.
