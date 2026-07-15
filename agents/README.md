# Plan swarm agents — Antigravity CLI (`agy`) port

This directory is an **Antigravity-format** port of the planning swarm that lives, in
Claude Code plugin form, at [`plugins/plan/agents/`](../plugins/plan/agents). Both
copies are kept: the Claude plugin is unchanged, and these directories add the same
roles for the Antigravity CLI (`agy`).

Antigravity discovers agents as **directories**, each named after the agent and
containing a single `agent.md` (the body is the system prompt). A flat `architect.md`
in the agents dir is silently ignored — the directory layout is required.

```
agents/
├── architect/agent.md
├── auditor/agent.md
├── engineer/agent.md
├── implementation-validator/agent.md
├── plan-deliberator/agent.md
├── plan-validator/agent.md
├── product-owner/agent.md
├── spec-deliberator/agent.md
├── spec-validator/agent.md
├── supervisor/agent.md
├── visual-architect/
│   ├── agent.md
│   ├── assets/template.html            # bundled — no dependency on plugins/plan/skills/
│   └── references/{component-catalog,exemplar}.md
├── visual-implementation-recap/        # (same assets/ + references/ layout)
│   └── agent.md
└── visual-product-owner/               # (same assets/ + references/ layout)
    └── agent.md
```

The three **visual** agents are self-contained: each bundles its HTML `template.html`
and the two reference guides inside its own folder, so it never reaches into
`plugins/plan/skills/`. Each `agent.md` resolves those files relative to its own
directory.

`geap-interactions-caller` is intentionally **not** ported — it is a curl transport
shell tied to ADC/Vertex, out of scope for the swarm roles.

## What changed from the Claude versions

The role behavior is identical; only the harness bindings were rewritten:

| Claude Code | Antigravity port |
|---|---|
| `model:` / `color:` / `tools:` frontmatter | Dropped — Antigravity has no documented keys. Capability & model notes moved into a `## Running under Antigravity CLI` body section; model is chosen globally via `/model`. |
| `initialPrompt:` field | Folded into a leading `## On activation` body section. |
| `<example>` / `<commentary>` in `description` | Stripped — they drive Claude auto-delegation and add noise here. |
| `subagent_type: "general-purpose"` skeptic dispatch | `invoke_subagent` with `TypeName: research` (read-only skeptics/delegates). |
| Named dispatch (supervisor → `architect`, etc.) | Two-tier: target the same-named custom agent if the harness allows, else `invoke_subagent` (`TypeName: self`) seeded with the role charter + file path. |
| `SendMessage` across deliberation rounds | Re-invoke the delegate each round with the **full verbatim transcript** (Antigravity `invoke_subagent` is fire-and-return; no persistent channel). |
| `AskUserQuestion` tool | Ask the user directly inline. |
| `${CLAUDE_PLUGIN_ROOT}/skills/<name>/assets/…` (visual agents) | Assets **bundled into each visual agent's own folder** (`assets/template.html` + `references/*.md`), resolved relative to that agent directory. No dependency on `plugins/plan/skills/`. |

## Installation

### Recommended — loose global agents

`~/.gemini/config/agents/<name>/agent.md` is exactly what the `/agents` panel discovers
as top-level "Available Agents", so this is the best fit for selecting a role directly.
From the repo root:

```bash
mkdir -p "$HOME/.gemini/config/agents"
for d in agents/*/; do
  name=$(basename "$d")
  rm -rf "$HOME/.gemini/config/agents/$name"
  cp -R "agents/$name" "$HOME/.gemini/config/agents/$name"
done
```

Copy the **whole directory** (`cp -R`), not just `agent.md` — the visual agents carry a
bundled `assets/` and `references/` alongside their `agent.md`, and each resolves those
files relative to its own install directory. Then launch `agy` and open `/agents` — all
13 should appear. To keep a project-scoped copy instead of a global one, place the same
tree under `<workspace>/.agents/agents/`.

> **Visual agents are self-contained.** `visual-architect`, `visual-product-owner`, and
> `visual-implementation-recap` bundle their `template.html` + reference guides in their
> own folders, so they no longer depend on `plugins/plan/skills/`. The only requirement
> is that the whole agent folder is copied intact (which the `cp -R` loop above does).

### Alternative — bundle as an Antigravity plugin

Best for sharing/distribution. Create a plugin directory with a `plugin.json` and the
agent tree inside it:

```
antigravity/plan-plugin/
├── plugin.json          # {"name":"plan","description":"Planning swarm agents"}
└── agents/
    ├── architect/agent.md
    └── …                # copy the whole agents/ tree here
```

Then install it:

```bash
agy plugin install /abs/path/antigravity/plan-plugin
```

## Usage

- **Discovery:** run `agy`, open `/agents`, confirm the roles under "Available Agents".
- **Selection:** pick `supervisor` to drive a full spec → plan → execute lifecycle, or
  any single role (e.g. `plan-validator`) for a one-off.
- **Launch flag:** the docs describe the `/agents` panel; a `agy --agent=<name>` launch
  flag is not documented — verify with `agy --help | grep -i agent` before relying on it.

## Open risks / to confirm

- **Named custom-agent dispatch** (supervisor → architect/engineer/…) is undocumented
  in Antigravity. Each dispatching agent carries a two-tier fallback (invoke by name,
  else inline-seeded `invoke_subagent`); confirm which path your `agy` build supports.
- **`agy --agent=<name>`** launch flag — confirm it exists (docs only show `/agents`).
- **`tools:` / `model:` frontmatter** — no documented keys; constraints are encoded in
  prose. Revisit if a later `agy` version documents them.
- **Deliberators across rounds** — no persistent subagent channel; the re-invoke-with-
  full-transcript fallback works but re-reads territory each round. Keep territories
  tight and honor the 4-round cap.
- **Visual-agent asset path** — the visual agents reference their bundled
  `assets/template.html` and `references/*.md` relative to their own folder. This
  resolves cleanly as long as the whole agent directory is installed intact; if you
  install only `agent.md`, the render step won't find its template. (Antigravity
  publishes no plugin-root variable, so the path is expressed relative to the agent
  directory rather than an absolute install location.)
- **Asset drift** — the bundled `assets/`/`references/` are *copies* of the originals in
  `plugins/plan/skills/visual-*/`. If the Claude skill templates change later, re-copy
  them into the agent folders to keep the two in sync.
