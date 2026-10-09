# Examples

## `e2e_demo.py`: one milestone, every stage

`e2e_demo.py` drives one milestone, `login-rate-limit`, from setup to a tagged release in a
scratch repository. It feeds the plan plugin's hooks the same JSON events Antigravity sends:

- `PreInvocation` goes to `lib/approve.py`. This is the path for anything "you type".
- `PreToolUse` goes to `lib/gate.py`, for every agent `run_command`, `write_to_file`,
  `replace_file_content`, `invoke_subagent`, and `send_message`.

A tool call runs only if the gate prints nothing or an allow (the `$PLAN_LIB` expansion is
applied from the allow's `overwrite`). A deny is recorded with its reason.

```bash
# from the repository root (not from inside the work directory)
python3 examples/e2e_demo.py                 # default work directory: /tmp/swarm-e2e
python3 examples/e2e_demo.py /tmp/my-run     # or choose one
python3 examples/render_usage_e2e.py         # re-render docs/usage-e2e.html from that run
```

Requirements: `python3` and `git`. The scenario's tests run with `pytest` when it is installed,
and with a small stdlib stand-in when it is not. The demo calls no model, uses no network, and
writes only inside the work directory. It ignores your global git config, so a global
`core.hooksPath` cannot bypass the hooks that `swarm-init` installs.

Run it from the repository root. In a live Antigravity session the plan plugin's gate judges your own
tool calls. If the call's working directory were inside the scratch repository, which is a
plan-swarm repository, the gate would apply the swarm's rules to the demo command itself.

### What it does

| Stage | What happens |
|---|---|
| 0 Setup | Runs `swarm_init.py` through the gate. You commit the setup. A new top-level conversation gets the enforcement announcement. Runs `health.py --status`. |
| 1–2 Intent | The product owner writes the intent. A commit before approval is refused. `approve intent …` creates the milestone branch and the first ledger row. |
| 3–4 Research, spec | A research subagent runs, then the Grill Loop. A phrase typed in a subagent conversation is ignored. `send_message` and dispatches that carry a phrase are refused. |
| 5–6 Plan | The architect writes the plan and the tier rises to critical. The plan-validator panel runs. An engineer dispatch and edits to `approvals.md` / `plans/swarm.md` are refused until `approve plan …`. |
| 7–10 Build, audit, commit | Two engineers run in parallel worktrees. WIP commits are allowed there, and a commit in the main checkout is refused. Squash, then audit (real test run), then the commit gate. Reusing an approval is refused. |
| 11 Pull request | The gate and the `pre-push` hook both refuse the push until `approve pr …`. The ledger-only commit and the push follow. `prbody.py` builds the PR text, and the supervisor prints it because there is no `gh`. The CI ledger job runs, and `gh pr merge` is refused. |
| 12–13 Release, measure | Switch and pull run as separate commands. `approve release …` records the release row in `plans/approvals.md`. Then the tag, the tag push, the refused push to `main`, and `metrics.py`. |

### Outputs (in the work directory)

| File | Contents |
|---|---|
| `transcript.json` | Every captured step: `stage`, `label`, `kind`, `input`, `output`, `exit`, `note`. Kinds: `prompt`, `hook`, `ran`, `blocked`, `dispatched`, `file`, `script`, `note`, `git-hook`, `ci`. For tool calls, `note` starts with the gate decision. |
| `hook-events.jsonl` | Every hook payload sent (stdin) and the hook's raw stdout. |
| `git-state.json` | Branch, HEAD, `git status --short`, recent log, and ledger row count at the end of each stage. |
| `shop/`, `origin.git/` | The scratch repository and its bare remote. Inspect them with `git log --oneline --graph --all`. |
| `antigravity/brain/<conversation>/…/transcript_full.jsonl` | Stand-in conversation transcripts read by the hooks (`transcriptPath`). |

Hook decisions, script output, git results, and test results are real. The intent, spec, plan,
code, audit text, and the subagents' replies are example content supplied by the script.

`render_usage_e2e.py` turns a run into [`docs/usage-e2e.html`](../docs/usage-e2e.html). Its
stylesheet is `usage-e2e.css`.
