# `plan` plugin agents (subagents): plan-swarm@3.0

The agents packaging of the swarm. The [skills form](README.md) and this agents form are **generated from the same role files** in [`roles/`](roles/), so they describe the same lifecycle, write the same `plans/` artifacts, and are held by the same control plane. What differs is delivery: a skill loads into the current conversation, an agent runs as a subagent in its own conversation and context, dispatched with `invoke_subagent` (`TypeName` = the role name).

Lifecycle, control plane, approval phrases, artifact map, and configuration are documented once in [README.md](README.md).

---

## Anatomy of an agent

Each `agents/<role>/agent.md` is rendered by `lib/render_roles.py` from the `<!-- @agent:frontmatter -->` block and the body of `roles/<role>.md` (shared text plus `<!-- @agent -->` sections). Never edit `agents/` directly; see [`agents/README.md`](agents/README.md) for the directory layout.

| Field | Purpose |
|---|---|
| `name` | The `TypeName` to dispatch, e.g. `architect`. |
| `description` | Purpose and when to dispatch; the runtime shows it when choosing a subagent. |
| `tools` | A capability contract in Antigravity tool names. `architect` and `product-owner` have no `run_command` (read-only on code, cannot run git). Roles that build, verify, or render (`engineer`, `auditor`, `simplifier`, the visual roles) have `run_command`. The supervisor, validators, and deliberators have `invoke_subagent` because they dispatch their own subagents. |
| `mainAgent`, `subagent` | Both `true` for every role: each can run as the conversation's agent or be dispatched as a subagent. |

The model is selected globally in Antigravity; agents carry no `model` field.

When dispatched, an agent is written to stop on an ambiguous target and put the question in its final message, which the supervisor relays to you. The control plane applies to agents exactly as to skills: an engineer's `git commit` outside its worktree, an auditor's commit without an approval, or an engineer dispatched before `approve plan` is refused by the `PreToolUse` gate, and the agent reports the reason.

---

## Agents

| Agent | Tools (besides `view_file`, `list_dir`, `grep_search`, `find_by_name`, `write_to_file`, `replace_file_content`) | Notes |
|---|---|---|
| `supervisor` | `invoke_subagent`, `send_message`, `run_command`, `multi_replace_file_content`, `ask_question` | Orchestrates the state machine; prints approval phrases; runs `health.py`, `tier.py`, `worktree.py`, `usage.py`, `prbody.py`. Best run as a skill in the top-level conversation (see below). |
| `product-owner` | `multi_replace_file_content`, `ask_question` | Grill Loop uses `ask_question`; intent mode; roadmap. The supervisor moves accepted intents. |
| `visual-product-owner` | … + `run_command` | Drop-in; renders `visual-spec.html`. |
| `architect` | `multi_replace_file_content`, `ask_question` | Read-only on code; plans parallel groups with disjoint files. |
| `visual-architect` | … + `run_command` | Drop-in; renders `visual-plan.html`. |
| `engineer` | `run_command`, `multi_replace_file_content`, `ask_question` | TDD; worktree mode (WIP commits on `swarm-wip/*` only). |
| `simplifier` | `run_command`, `multi_replace_file_content` | Clarity-only pass on the staged diff. |
| `auditor` | `run_command`, `multi_replace_file_content`, `ask_question` | Audit rounds in `audit.md`; the only committer. |
| `visual-implementation-recap` | `run_command`, `multi_replace_file_content` | Renders `visual-recap.html`; never commits. |
| `spec-deliberator`, `plan-deliberator` | `invoke_subagent`, `send_message`, `run_command`, `multi_replace_file_content`, `ask_question` | Delegate panels; continue delegates across rounds with `send_message`; may revise their artifact. |
| `spec-validator`, `plan-validator`, `implementation-validator` | `invoke_subagent`, `run_command` (+ `multi_replace_file_content`, `ask_question` on some) | Skeptic panels; **report only**. `implementation-validator` has a PR mode. |

The exact lists are in each role's `@agent:frontmatter` block in [`roles/`](roles/).

---

## Invoking an agent

**Recommended layout: the supervisor as a skill in the top-level conversation, every other role as a subagent.** Say "be the supervisor" in a new top-level Antigravity conversation on the target repository. The supervisor dispatches each role:

```text
invoke_subagent  Subagents: [{TypeName: "architect", Role: "Plan login-rate-limit",
                              Prompt: "Read plans/active_milestones/login-rate-limit/spec.md. Write plan.md …"}]
```

- **Parallel work** (the engineers of one group, the skeptics of a panel) goes in **one** `invoke_subagent` call with several entries. Each subagent sends a message back when it finishes; the supervisor does not poll.
- **More work for an existing subagent** goes through `send_message` to its conversation ID. Deliberators use this to continue the same delegates across rounds.
- **Nested dispatch works.** Validators and deliberators dispatched by the supervisor fan out their own skeptics and delegates.
- **Approval phrases only count from the human in the top-level conversation.** The `PreInvocation` hook ignores a conversation that has a parent, and the gate refuses dispatches and `send_message` calls whose whole message is an approval phrase. This is why the supervisor runs as a skill at the top level: your phrases reach it directly. When the supervisor itself runs as a subagent, it ends its turn with the phrase for you to type in the top-level conversation and is continued with `send_message` once the hook has recorded it.

Calling one role yourself:

| How | Example |
|---|---|
| Ask the conversation to dispatch it | "Dispatch the architect agent (invoke_subagent, TypeName architect) to write the plan for `plans/active_milestones/x/spec.md`." |
| Load the skill instead | "Use the plan plugin's architect skill to write the plan for …" (runs in the current context) |

Use agents rather than role skills when you want separation: a skill loads into the current context, an agent gets its own. The utility skills (`swarm-init`, `swarm-metrics`) are meant for the top-level conversation. `architect` and `product-owner` have no `invoke_subagent` and cannot dispatch; run the `product-owner` skill directly if you want the Grill Loop's questions in your own conversation.

---

## Differences from the skills form

| Aspect | Skills | Agents |
|---|---|---|
| Source | `roles/<role>.md` (`@skill` sections) | `roles/<role>.md` (`@agent` sections) |
| Location | `skills/<role>/SKILL.md` | `agents/<role>/agent.md` (+ `assets/`, `references/` for the visual roles) |
| Context | the current conversation | a subagent conversation of its own |
| Utilities | `swarm-init`, `swarm-metrics`, `starter`, `teamwork-trajectory` | none (utilities stay skills) |
| Invocation | load by trigger phrase or name | `invoke_subagent` with `TypeName: "<role>"` |

The eval suite includes parity cases (`evals/l4-parity-architect-agent` and `-skill`) that run the same task through both forms.
