---
name: swarm-init
description: Prepare a repository for the plan swarm (plan-swarm@3.0) - installs plans/swarm.md (settings), the git approval hooks (pre-commit, pre-merge-commit, pre-push), REVIEW.md, the CI ledger-check workflow, and an AGENTS.md skeleton, never overwriting existing files. Triggers - "set up the plan swarm", "swarm init", "initialize plans/swarm.md", "install the swarm hooks", or when the supervisor reports there is no plans/swarm.md.
tools:
  - run_command
  - view_file
  - ask_question
---

# Swarm init

Installs the project-side pieces of plan-swarm@3.0 into the current repository. The plan plugin's Antigravity hooks (`hooks.json` in the plugin) are active as soon as the plugin is installed; they only start enforcing in a repository that has `plans/swarm.md`.

Commands are written with `$PLAN_LIB`: the plugin's PreToolUse hook expands it to the plugin's `lib/` folder in every repository. If a command fails because `$PLAN_LIB` was not expanded, the plugin's hooks are not running in this Antigravity session (plugin disabled, or hooks turned off): stop and tell the user, because nothing would be enforced.

## Steps

1. **Preview.** Run (Cwd: the repository root):
   `python3 "$PLAN_LIB/swarm_init.py" --dry-run`
   It prints one line per template: `would install`, `exists`, or `skipped`.
2. **Ask.** Show the preview and ask which to install (`ask_question` with multi-select works well). Explain each briefly:
   - `swarm` → `plans/swarm.md`: delivery mode (pr or local), engineer limit, Path A limit, approval lifetime, policy skills, risk-tier rules. Required.
   - `hook` → `.git/hooks/pre-commit`, `pre-merge-commit`, `pre-push`: the second enforcement layer for commits and pushes made by any route (a terminal outside Antigravity included). Strongly recommended.
   - `review` → `REVIEW.md`: review passes and severity thresholds for PR review. Recommended with pr mode.
   - `ci` → `.github/workflows/plan-swarm.yml`: the ledger check (every commit on `swarm/{m}` must match an approval row) and the risk tier as a job output. An AI review job is an optional add-on described in the file; it is not enabled.
   - `agents` → `AGENTS.md` skeleton: build and test commands the auditor runs. Skipped if the repository already has `AGENTS.md` or `GEMINI.md` (Antigravity loads either as project rules, and the swarm reads whichever exists).
3. **Install** what the user chose:
   `python3 "$PLAN_LIB/swarm_init.py" --only swarm,hook,review,ci,agents`
   (keep only the chosen names). Existing files are never overwritten. If another tool already owns one of the git hooks, the script prints the one line to add to that hook; show it to the user.
4. **Check enforcement:** `python3 "$PLAN_LIB/health.py" --status` should now report `"enforcement": "active"`.
5. **Next steps for the user:**
   - Read `plans/swarm.md` and adjust the values; the explanations sit next to them. After it exists, agents can no longer edit it, and the repository is marked active (`.git/plan-swarm/active`): removing `swarm.md` later makes the gate refuse gated steps until a person restores it or deletes that marker.
   - Fill in the build and test commands in `AGENTS.md` (or the existing `GEMINI.md`).
   - Put project policy skills (named in `policies` in `plans/swarm.md`) under `.agents/skills/{name}/SKILL.md`; `templates/skills/policy-example/` in the plugin shows the format.
   - Commit these files themselves, like any other change (a person commits them; the gate is not active until `plans/swarm.md` exists). If `delivery.mode` is `local` and the git hooks are installed, commit from a terminal before starting a swarm conversation, or once its heartbeat is older than 10 minutes: while a session is active in local mode, the `pre-commit` hook refuses commits that carry no approval.
   - Start the swarm by saying "be the supervisor" in a top-level Antigravity conversation. Approval phrases must be typed in that top-level conversation.

## Constraints
- Never overwrite or delete an existing file; the script refuses to anyway.
- Do not create or edit `plans/swarm.md` by hand once it exists; tell the user to edit it.
