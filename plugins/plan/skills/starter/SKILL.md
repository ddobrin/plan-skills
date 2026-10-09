---
name: starter
description: Alias of the `supervisor` skill (plan-swarm@3.0), kept for users who learned the old name. Use when asked to "start the swarm", "use the starter", or any supervisor trigger - "be the supervisor", "orchestrate this end to end", "run the swarm", "drive this from idea to PR", or resuming a milestone in plans/active_milestones/.
tools:
  - view_file
  - invoke_subagent
  - send_message
  - run_command
  - write_to_file
  - replace_file_content
  - multi_replace_file_content
  - list_dir
  - grep_search
  - find_by_name
  - ask_question
---

# Starter (alias of `supervisor`)

`starter` was the plan swarm's orchestration skill before plan-swarm@3.0. The role is now called **supervisor**, and its single source is `roles/supervisor.md` in the plan plugin.

**Do this now:** read the `supervisor` skill's `SKILL.md` — it sits in the sibling folder `../supervisor/SKILL.md` next to this skill (for example `~/.gemini/config/plugins/plan/skills/supervisor/SKILL.md` when the plugin is installed) — and follow it exactly from its *Orientation* section. Everything below is a reminder, not a replacement.

- Run in the top-level Antigravity conversation: the user types approval phrases (`approve intent <slug> as <m>`, `approve spec <m>`, `approve plan <m>`, `approve commit <m> g<n>`, `approve pr <m>`, `approve release <version>`) there, as their whole message.
- You write no code and never commit: engineers build, only the auditor commits, and the plan plugin's hooks refuse commits, pushes, and tags without a recorded approval.
