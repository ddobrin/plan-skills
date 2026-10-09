# `agents/` — generated agent definitions

This directory holds the **agents form** of the plan swarm (plan-swarm@3.0): one folder per role, each with an `agent.md` whose front matter declares the role's Antigravity tools and whose body is its system prompt. Antigravity discovers them from the installed plugin and dispatches them with `invoke_subagent` (`TypeName` = the folder name).

> [!IMPORTANT]
> Everything here is **generated**. Edit `../roles/<role>.md`, then run `python3 plugins/plan/lib/render_roles.py` from the repository root. `--check` fails when these files are stale, and the test suite runs it.

How to use the agents, the tool contract of each role, and the differences from the skills form are in [`../SUBAGENTS.md`](../SUBAGENTS.md). The lifecycle and control plane are in [`../README.md`](../README.md).

---

## Layout

```
agents/
├── supervisor/agent.md                 orchestrator (usually loaded as the supervisor skill instead)
├── product-owner/agent.md              intents, Grill Loop, spec.md, roadmap
├── visual-product-owner/               drop-in for product-owner + visual-spec.html
│   ├── agent.md
│   ├── assets/template.html
│   └── references/{component-catalog,exemplar}.md
├── architect/agent.md                  plan.md (read-only on code)
├── visual-architect/                   drop-in for architect + visual-plan.html
│   ├── agent.md
│   ├── assets/template.html
│   └── references/{component-catalog,exemplar}.md
├── engineer/agent.md                   one task under TDD, worktree mode
├── simplifier/agent.md                 clarity-only pass on the staged diff
├── auditor/agent.md                    audit.md rounds; the only committer
├── visual-implementation-recap/        visual-recap.html for the commit gate
│   ├── agent.md
│   ├── assets/template.html
│   └── references/{component-catalog,exemplar}.md
├── spec-validator/agent.md             3 skeptics on the spec, report only
├── plan-validator/agent.md             3 skeptics on the plan, first domino
├── implementation-validator/agent.md   3 skeptics on the diff, calibrated severity
├── spec-deliberator/agent.md           disjoint-context panel on the spec
└── plan-deliberator/agent.md           territory panel on the plan
```

The `assets/` and `references/` folders of the three visual agents are copied by `render_roles.py` from `../skills/visual-*/`, so an agent resolves them relative to its own folder. Change them in `skills/`, never here.

---

## Installation

Install the whole plugin folder (`plugins/plan`, for example symlinked at `~/.gemini/config/plugins/plan`; see the [plugin README](../README.md#quick-start)). That brings the agents, the skills, and the hooks together.

Copying agent folders out of the plugin (into `~/.gemini/config/agents/` or a workspace `.agents/agents/`) makes them dispatchable, but without the plugin's hooks there is no approval capture, no gate, and no `$PLAN_LIB`: the roles' `python3 "$PLAN_LIB/…"` commands fail and the supervisor reports enforcement as off. If you copy them anyway, copy each folder whole (`cp -R`) so the visual agents keep their `assets/` and `references/`.
