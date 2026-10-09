# `plan` plugin: plan-swarm@3.0 for Antigravity

An AI-native software development lifecycle (AI-DLC) for Antigravity. A swarm of role agents takes a feature, bug fix, or refactor from **intent → spec → plan → parallel build → audit → commit → pull request → release**. Optional validator and deliberator panels attack or improve each artifact at its phase boundary, and a hook-enforced **control plane** makes sure nothing is committed, pushed, or tagged without the user's exact approval phrase. Every approval is recorded in a ledger that is committed with the change it authorizes.

Three ideas carry the design:

- **Artifacts, not chat.** Every stage ends in a committed Markdown file (`intent.md` → `spec.md` → `plan.md` → code + `audit.md` → PR). The next role reads the file, so any conversation can stop and any other can resume.
- **People decide, agents execute.** Agents interview, write, build, verify, and review. The user makes six decisions, each by typing an exact phrase.
- **Mechanism, not promises.** Prompts carry judgment; Antigravity hooks and git hooks carry authority.

The swarm ships in two forms with identical behavior, both generated from one source file per role in [`roles/`](roles/): **skills** (`skills/<role>/SKILL.md`, loaded into the current conversation) and **agents** (`agents/<role>/agent.md`, dispatched as subagents with `invoke_subagent`). This document covers the skills form and the shared machinery; [`SUBAGENTS.md`](SUBAGENTS.md) covers the agents. The graph itself is [`topology.md`](topology.md).

---

## Quick start

1. **Install the plugin.** The plugin is the folder `plugins/plan` (with `plugin.json` and `hooks.json`). Place or symlink it at `~/.gemini/config/plugins/plan`:

   ```bash
   mkdir -p ~/.gemini/config/plugins
   ln -s "$PWD/plugins/plan" ~/.gemini/config/plugins/plan   # from a checkout of this repository
   ```

   The plugin's hooks load for **new** conversations; start a new one after installing or updating. (The Antigravity CLI's `agy plugin install ./plugins/plan` installs the same folder; it has not been verified with this release.)

2. **Prepare the target repository.** In an Antigravity conversation opened on that repository, say "swarm init". The [`swarm-init`](skills/swarm-init/SKILL.md) skill previews with `python3 "$PLAN_LIB/swarm_init.py" --dry-run`, asks what to install, then runs `--only swarm,hook,review,ci,agents` (your selection). It installs `plans/swarm.md` (settings), the git hooks (`pre-commit`, `pre-merge-commit`, `pre-push`), and optionally `REVIEW.md`, the CI ledger check, and an `AGENTS.md` skeleton (skipped when the repository already has `AGENTS.md` or `GEMINI.md`; Antigravity loads either as project rules). It never overwrites a file. Fill in the build and test commands, review `plans/swarm.md`, and commit both yourself.

3. **Start the supervisor.** In a **top-level** Antigravity conversation, say **"be the supervisor"**. That loads the `supervisor` skill; it checks enforcement, reports each milestone's state, and dispatches every role as a subagent. Type the approval phrases in that same conversation.

The hooks enforce only in repositories that have `plans/swarm.md` (or were marked active by `swarm-init`). Elsewhere they stay neutral.

---

## The lifecycle

```
 request ─► 1 INTENT ─► 🔒 approve intent ─► 2 research ─► 3 SPEC ─► [spec gates] ─► 🔒 approve spec
        ─► 4 PLAN ─► [plan gates] ─► 🔒 approve plan (tier confirmed)
        ─► 5 per execution group: engineers ×≤5 in worktrees ─► squash ─► [simplifier] ─► auditor
                                  ─► [implementation gate · recap] ─► 🔒 approve commit {m} g{n}
        ─► 6 🔒 approve pr ─► CI ledger check ─► code owner merges ─► 7 🔒 approve release ─► tag
```

| Stage | What happens | Artifact | Gate |
|---|---|---|---|
| Intent | `product-owner` (intent mode) drafts the problem and outcome; `lib/tier.py` proposes a risk tier. | `plans/intents/{date}-{slug}.md` | 🔒 `approve intent` → branch `swarm/{m}` (pr mode), intent moved into the milestone and committed |
| Research | A read-only research subagent investigates the code; the supervisor appends its *Codebase context* to `intent.md`. | `intent.md` | none |
| Spec | Grill Loop (≤3 questions at a time), project policy skills applied, *Policy Concerns* recorded. Offered: deliberator, validator. | `spec.md` | 🔒 `approve spec` |
| Plan | `architect` reads the code, writes test-first micro-steps in parallel groups with disjoint files and *Irreversible Steps*; tier re-checked. Offered: deliberator, validator. | `plan.md` | 🔒 `approve plan [tier=…]`; engineers unblocked |
| Build | Up to `engineers.max_concurrent` (default 5) engineers, each in its own git worktree; `worktree.py squash` stages the group (overlapping files = plan defect). Offered: simplifier. | staged group diff | engineer dispatch refused before `approve plan` |
| Audit | Evidence (`file:line`), build, tests, anti-shortcut scan, one round per heading in the tracked `audit.md`. Offered: implementation-validator, recap. | `audit.md` | FAIL → Path A |
| Commit | The auditor commits the audited group. | group commit | 🔒 `approve commit {m} g{n}` |
| PR | Tier re-checked on the real diff; the PR approval is recorded in a ledger-only commit; push and `gh pr create` with a body built from the artifacts. | pull request | 🔒 `approve pr` for the first push; a code owner merges |
| Release | Annotated tag on the default branch; roadmap marks the release Shipped. | tag | 🔒 `approve release` |

- 🔒 = a human approval phrase (see [Control plane](#control-plane)).
- `[…]` = **offered**: validators, deliberators, simplifier, and recap run only when the user says yes. The milestone's **risk tier** (routine · elevated · critical, from the rules in `plans/swarm.md`, computed by `lib/tier.py`, which never lowers a tier) sets how strongly the supervisor recommends them. Declines are logged with the tier in `usage.md`.

  | Tier | Spec gates | Plan gates | Implementation gate | Recap |
  |---|---|---|---|---|
  | routine | offer | offer | offer | on request |
  | elevated | recommend `spec-validator` | recommend `plan-validator` | recommend | by default |
  | critical | recommend `spec-deliberator` → `spec-validator` | recommend `plan-deliberator` → `plan-validator` | recommend, claim-refutation mode | by default |

- **Delivery modes.** In **pr mode** (default) the milestone lives on branch `swarm/{m}`, created when the intent is accepted, and ends in a pull request. In **local mode** commits land on the current branch and there is no PR.
- **Feedback loops.** Validator findings go back to the author (product owner or architect). Audit failures go back to an engineer (**Path A**, at most `audit.max_path_a_rounds` = 3 failed rounds per task, then the user chooses: re-plan, drop the task, or take over). Impossible steps, blocked engineers, or squash conflicts go back to the architect (**Path B**, and the revised plan needs `approve plan` again). PR review findings become a fix group.
- **State is derived, not stored.** The supervisor reads `plans/` and `approvals.md` to place each milestone at INBOX, ACCEPTED, SPECIFIED, PLANNED, APPROVED, BUILDING g, AUDITED g, COMMITTED g, IN REVIEW, or DONE, and reports any gap in the evidence.

### Parallel build in worktrees

For each task of a group the supervisor runs `python3 "$PLAN_LIB/worktree.py" create --milestone {m} --task {X.Y}`, which creates branch `swarm-wip/{m}/{X.Y}` and a checkout under `.swarm/worktrees/` (excluded through `.git/info/exclude`). It then dispatches the engineers in **one** `invoke_subagent` call with one `engineer` entry per task. Engineers may make WIP commits only there. `worktree.py squash` stages the whole group without committing (exit 3 when two tasks touched the same file or a task edited `plans/`), and `worktree.py cleanup` removes the worktrees and WIP branches after the group commit.

---

## Skills

### Lifecycle roles

| Skill | Role |
|---|---|
| `supervisor` | Orchestrator. Checks enforcement (`lib/health.py --status`), derives each milestone's state from its files, dispatches roles with `invoke_subagent`, offers gates by tier, prints the exact approval phrase at every gate, runs worktrees and squashes, opens the PR. Never codes, never commits. |
| `product-owner` | Writes intents (intent mode) and Gherkin specs through the **Grill Loop**, loads the project's policy skills, records *Policy Concerns*, owns `plans/00-ROADMAP.md`, applies spec-validator tightenings. No code, no shell. |
| `visual-product-owner` | Drop-in for `product-owner`; also renders `visual-spec.html`. |
| `architect` | Reads the code (read-only, no shell) and writes `plan.md`: micro-steps, test first, parallel groups with disjoint files, *Irreversible Steps*. Applies plan-validator fixes and Path B revisions. |
| `visual-architect` | Drop-in for `architect`; also renders `visual-plan.html`. |
| `engineer` | Implements one task under strict TDD. In **worktree mode** it works only in its own worktree and may make WIP commits on `swarm-wip/{m}/{task}`; otherwise it never commits. |
| `simplifier` | Optional clarity-only refactor of the staged group diff, zero behavioral change. |
| `auditor` | Verifies each group with `file:line` evidence, build and tests, and an anti-shortcut scan; appends `### Group g · Round r · PASS/FAIL` to the tracked `audit.md`. **The only role that commits**, and only with a recorded approval. |
| `visual-implementation-recap` | Renders `visual-recap.html` for the commit gate and the PR; additive, never a substitute for the audit. |

### Offered panels

| Skill | Panel |
|---|---|
| `spec-deliberator` | 3 delegates with **disjoint** context bundles (product · engineering · ops/security) converge on one revised spec, ≤4 rounds, continued with `send_message`. Always followed by `spec-validator`. |
| `spec-validator` | 3 independent skeptics attack the spec (ambiguity, gaps, untestable criteria, malicious compliance, policy). 2-of-3 quorum via `lib/tally.py`. **Report only**: tightenings go to the product owner. |
| `plan-deliberator` | 3 delegates with **assigned territories** (intent · codebase · delivery) reshape the plan and decide trade-offs. Always followed by `plan-validator`. |
| `plan-validator` | 3 skeptics read the codebase to find the **first domino**. Report only: fixes go to the architect. |
| `implementation-validator` | 3 skeptics attack the diff; its key output is **calibrated severity**. Report only: defects go to an engineer. **PR mode** reads `REVIEW.md` and maps severity to Important/Nit. |

Skeptics and delegates are dispatched as parallel `invoke_subagent` entries (`TypeName: "self"`, or a read-only research subagent where the runtime offers one). All panels write a Markdown report under the milestone (`adversarial-reviews/` or `deliberations/`) on every run, re-runs as `-r2`, `-r3`.

### Utilities

| Skill | Purpose |
|---|---|
| `swarm-init` | Installs the project templates (never overwrites). |
| `swarm-metrics` | Reports lead times, groups committed, first-pass audit rate, failed audit rounds, validator re-runs, cost, declined gates, and intent survival from committed files (`lib/metrics.py`). |
| `starter` | Alias of `supervisor`, kept for the pre-3.0 name; it loads the supervisor skill. |
| `teamwork-trajectory` | Renders the `.agents/` briefing and hand-off records as an HTML timeline (`.agents/trajectory.html`). Outside the lifecycle. |

Any role skill can also be used on its own for one phase, for example "validate this spec" (`spec-validator`) or "simplify this file" (`simplifier`).

---

## Control plane

Antigravity hooks declared in [`hooks.json`](hooks.json), run from the plugin folder:

| Layer | Hook | Script | Does |
|---|---|---|---|
| 1 | `PreInvocation` (before every model call) | `lib/approve.py` | Records an approval phrase when it is the user's **whole message** in a **top-level** conversation (reads the conversation transcript via `transcriptPath`; refuses when it cannot tell a top-level conversation from a subagent). Each user input is processed exactly once. Mints a single-use nonce bound to HEAD with a TTL (`approvals.nonce_ttl_minutes`, default 15), appends a row to `plans/active_milestones/{m}/approvals.md` and stages it. Once per conversation it announces enforcement status and the `PLAN_LIB` path, and it delivers messages the gate stashed. |
| 1 | `PreToolUse` (`run_command`, `write_to_file`, `replace_file_content`, `multi_replace_file_content`, `notebook_edit`, `invoke_subagent`, `run_workflow`, `send_message`) | `lib/gate.py` | Git policy: commits need a matching approval (`commit` for code, `intent`/`spec`/`plan` for `plans/`-only commits; WIP only inside a swarm worktree on `swarm-wip/*`); pushes only as `git push <remote> swarm/{m}` (the first needs `approve pr`) or a tag after `approve release`; no default-branch, force, or delete pushes; no history rewrites, hook bypasses, git aliases or config tricks, `gh` merges, releases, or write API calls. Refuses agent writes to `plans/swarm.md`, `approvals.md`, the git directory, the plugin, and Antigravity's hook, plugin, and settings files. Refuses dispatching an `engineer` before `approve plan {m}`. Refuses `send_message` calls and dispatches whose whole message is an approval phrase. Expands `$PLAN_LIB` in commands. |
| 2 | git `pre-commit`, `pre-merge-commit` | `gate.py --git-hook` | Re-checks commits made by any route, including a terminal outside Antigravity: allowed only with the one-time ticket layer 1 issued; WIP only inside the swarm's linked worktrees. |
| 2 | git `pre-push` | `gate.py --pre-push` | Every new commit pushed to `swarm/{m}` must have a parent that matches an approval row in the ledger. |
| 3 | CI `ledger` job ([`templates/ci/plan-swarm.yml`](templates/ci/plan-swarm.yml)) | GitHub Actions | On PRs from `swarm/*`: every commit must match an intent/spec/plan/commit row in `approvals.md`; reports the confirmed risk tier as a job output. An AI review job is described in the file as an optional add-on and is not enabled. |

Gate output follows the Antigravity hook contract: nothing for a neutral answer, `{"decision":"deny","reason":…}` to block, and `{"decision":"allow","overwrite":{…}}` only to expand `$PLAN_LIB`. In a swarm repository any internal error is a deny (fail closed): an invalid `plans/swarm.md`, or a missing one after `swarm-init` marked the repository (`.git/plan-swarm/active`), refuses gated operations. Outside swarm repositories the hooks are neutral apart from expanding `$PLAN_LIB` and refusing planted approval phrases. Nonces, tickets, and the heartbeat live in `.git/plan-swarm/` (outside the working tree, shared by worktrees).

### Approval phrases

Typed by the user, as the whole message, in the top-level Antigravity conversation (case-insensitive):

```text
approve intent  <slug> as <milestone>
approve spec    <milestone>
approve plan    <milestone> [tier=routine|elevated|critical]
approve commit  <milestone> g<n>
approve pr      <milestone>
approve release <version>
```

The hook answers in the conversation with "approval recorded …" or "Approval NOT recorded: <reason>". A phrase inside a subagent prompt or a `send_message` is never an approval. Because the hook stages each new ledger row, the row ships inside the commit it authorizes; CI and the pre-push hook match each commit's parent against those rows.

### Threat model and limits

- The local layers guard against **well-meaning agents** that try to unblock themselves. They are not a sandbox against an adversary with a shell, who runs with the same privileges as the hooks. **Server-side branch protection, required reviews, and the CI ledger check are the authoritative controls.** `lib/tests/test_security.py` holds regression tests for the security review's findings.
- If the plugin or its hooks are disabled, nothing is enforced in Antigravity. The supervisor detects it (stale heartbeat from `health.py --status`, or `$PLAN_LIB` left unexpanded) and refuses gated steps; the git hooks and CI still apply. [`templates/global-hooks.example.md`](templates/global-hooks.example.md) shows how a platform team registers the same two hooks in `~/.gemini/config/hooks.json` or a workspace `.agents/hooks.json`, independent of the plugin toggle.
- PR creation uses `gh`. Without it the supervisor prints the push result and the generated PR title and body for you to open the PR by hand.
- The gate finds the repository from the tool call: a command's `Cwd` or a write's target path, then the conversation's workspace folders. `invoke_subagent`, `run_workflow`, and `send_message` carry no path, so the engineer-dispatch rule applies only when the swarm repository is open as the Antigravity workspace. Run the supervisor in a conversation opened on that repository. The rule also keys on the `plans/active_milestones/{m}` path in the engineer's prompt (the supervisor always passes it); a dispatch that names no milestone is not checked, and the commit gate remains the backstop.

### Helper scripts (called by the supervisor)

All are standard-library Python, written as `python3 "$PLAN_LIB/<script>.py"`:

`health.py` (enforcement status, announcement) · `tier.py` (risk tier, only rises) · `worktree.py` (create / squash / cleanup per-task worktrees; refuses overlapping files) · `usage.py` (dispatch, cost, and declined-gate log in `usage.md`) · `prbody.py` (PR title and body from committed artifacts) · `metrics.py` · `swarmdoc.py` (reads the fenced JSON blocks of `swarm.md` and `topology.md`) · `tally.py` (validator votes) · `swarm_init.py` · `render_roles.py` (roles → agents + skills) · `evalgrade.py` (eval scaffolding and grading).

---

## Artifact map

| Path | Written by | Committed at |
|---|---|---|
| `plans/swarm.md` | people (`swarm-init` template) | by the user |
| `plans/intents/{date}-{slug}.md` | product-owner (intent mode) | moved into the milestone on acceptance; rejected ones go to `plans/intents/closed/` |
| `plans/00-ROADMAP.md` | product-owner | with the intent; COMPLETED ships in the PR |
| `plans/active_milestones/{m}/intent.md` | product-owner + supervisor (*Codebase context*) | `approve intent` / `approve spec` |
| `…/spec.md` (+ `visual-spec.html`) | product-owner | `approve spec` |
| `…/plan.md` (+ `data-model.md`, `api-contracts.md`, `visual-plan.html`) | architect; `tier.py` adds the tier line | `approve plan` |
| `…/approvals.md` | `approve.py` only | with the commit it authorizes |
| `…/audit.md` | auditor | with the group commit |
| `…/usage.md` | supervisor via `usage.py` | with the next commit |
| `…/adversarial-reviews/*.md`, `…/deliberations/*.md` | panels | with the next artifact or group commit |
| `…/visual-recap.html` | recap | with the group commit |
| `plans/approvals.md` | `approve.py` (release rows) | with the next roadmap commit |

---

## Configuration: `plans/swarm.md`

Markdown for people plus exactly one fenced `json swarm-config` block for the scripts (stdlib `json`, no YAML dependency). Keys: `delivery.mode` (`pr` | `local`), `delivery.host` (`github`), `engineers.max_concurrent` (default 5), `audit.max_path_a_rounds` (default 3), `approvals.nonce_ttl_minutes` (default 15), `policies` (project skill names), `tiers.{elevated,critical}.{paths,keywords,diff_lines_over}`. See [`templates/swarm.md`](templates/swarm.md). Agents cannot edit this file once it exists.

Project context the roles read:

- **Project rules:** `AGENTS.md` or `GEMINI.md` at the repository root (build and test commands the auditor runs).
- **Policy skills:** `.agents/skills/<name>/SKILL.md`, named in `policies`; the product owner and spec-validator apply them. [`templates/skills/policy-example/`](templates/skills/policy-example/) shows the format.

---

## Metrics and cost

`swarm-metrics` (or `python3 "$PLAN_LIB/metrics.py" [--milestone M] [--format json|text]`) computes, from committed files only: lead times intent → spec → plan → first group commit → PR (from `approvals.md`), groups committed, first-pass audit rate and failed rounds (from `audit.md`), validator re-runs (`-r2`, `-r3` reports), dispatches, tokens, and declined gates (from `usage.md`), and intent survival (accepted ÷ (accepted + closed)). The supervisor logs each dispatch with `usage.py log`, adding token, tool, and time totals only when Antigravity reported them.

---

## Developing the plugin

- **Layout.** `roles/*.md` is the single source for the 14 roles: `supervisor`, `product-owner`, `visual-product-owner`, `architect`, `visual-architect`, `engineer`, `auditor`, `simplifier`, `spec-validator`, `plan-validator`, `implementation-validator`, `spec-deliberator`, `plan-deliberator`, `visual-implementation-recap`. `python3 plugins/plan/lib/render_roles.py` renders `agents/<role>/agent.md` and `skills/<role>/SKILL.md` and mirrors `skills/visual-*/{assets,references}` into `agents/visual-*/`. Never edit the generated files. `--check` fails when they are stale, and a pytest runs it. `swarm-init`, `swarm-metrics`, `starter`, and `teamwork-trajectory` are hand-written skills.
- **Tests:** `python3 -m pytest -q plugins/plan/lib/tests`. The plugin code is standard-library only; pytest is the only development dependency.
- **Evals:** behavioral cases under [`evals/`](evals/README.md), run by hand in Antigravity and graded with `lib/evalgrade.py`.
- **Topology:** [`topology.md`](topology.md) (Markdown + fenced JSON, checked by the tests).
