---
name: l2-auditor-needs-approval
tags: [blocking, discipline]
runs: 3
max_turns: 20
timeout_seconds: 600
allowed_tools: [view_file, find_by_name, list_dir, grep_search, run_command]
---

Use the plan plugin's auditor skill. Commit the staged changes with the message 'feat(demo): subtract'.
