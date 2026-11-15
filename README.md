# Plan Swarm: Spec-Driven Planning Skills & Agents

A disciplined swarm of role-based agents, deliberative panels, and adversarial validation gates that drive features, bug fixes, or refactors through a robust **spec → plan → execute → audit → commit** lifecycle. 

This repository is optimized for **Google Antigravity CLI (AGY CLI)**, providing native roles, workflows, tool specifications, and output files.

---

## 🚀 Quick Start & Installation

This repository ships two AGY plugins under `plugins/`:
- **`plugins/plan`** — Core planning swarm (14 skills + 13 custom agents)
- **`plugins/viewers`** — Trajectory & timing viewers (`teamwork-trajectory` and `boost-trajectory` skills)

### 1. Install as AGY Plugins (Recommended)
> 📖 See [plugins/plan/README.md](./plugins/plan/README.md) and [plugins/viewers/README.md](./plugins/viewers/README.md) for details on each plugin's skills.

#### From a Local Folder
From the repository root, validate and install each plugin directory directly into AGY:

```bash
# Optional: validate plugin manifests and layouts
agy plugin validate ./plugins/plan
agy plugin validate ./plugins/viewers

# Install both plugins into ~/.gemini/config/plugins/
agy plugin install ./plugins/plan
agy plugin install ./plugins/viewers

# Verify installed plugins and components
agy plugin list
```

To update an already-installed local copy after pulling or editing files:
```bash
agy plugin uninstall plan && agy plugin install ./plugins/plan
agy plugin uninstall viewers && agy plugin install ./plugins/viewers
```

> [!TIP]
> If you are actively developing this repo and want AGY to read directly from the local folder without reinstalling, add `{"entries": [{"path": "/absolute/path/to/plan-skills/plugins"}]}` to `~/.gemini/config/plugins.json` (global) or `.agents/plugins.json` (project-scoped).

#### From the GitHub Repository
Clone the repository and install the plugin subdirectories:

```bash
git clone https://github.com/ddobrin/plan-skills.git
cd plan-skills

agy plugin install ./plugins/plan
agy plugin install ./plugins/viewers
```

---

### 2. Install as Loose Agents & Skills (Optional)
> 📖 See [plugins/plan/agents/README.md](./plugins/plan/agents/README.md) for the complete agent reference.

Antigravity CLI discovers custom agents as directories, each named after the agent and containing an `agent.md` file. If you prefer loose installations instead of AGY plugins, you can copy them globally or workspace-locally.

#### Method A: Loose Global Agents & Skills
This installs the roles and viewer skill globally in AGY CLI across all projects:
```bash
mkdir -p "$HOME/.gemini/config/agents" "$HOME/.gemini/config/skills"

for d in plugins/plan/agents/*/; do
  name=$(basename "$d")
  rm -rf "$HOME/.gemini/config/agents/$name"
  cp -R "plugins/plan/agents/$name" "$HOME/.gemini/config/agents/$name"
done

for d in plugins/plan/skills/*/ plugins/viewers/skills/*/; do
  name=$(basename "$d")
  rm -rf "$HOME/.gemini/config/skills/$name"
  cp -R "$d" "$HOME/.gemini/config/skills/$name"
done
```
> [!IMPORTANT]
> Always copy the **entire directory** (`cp -R`), not just individual files. Visual roles (`visual-architect`, `visual-product-owner`, `visual-implementation-recap`) and viewer skills (`teamwork-trajectory`, `boost-trajectory`) carry bundled assets, templates, or helper scripts that must remain relatively aligned inside their installation directories.

#### Method B: Project-Scoped (Workspace) Agents & Skills
To scope them to a single project, copy them into `.agents/agents` and `.agents/skills`:
```bash
mkdir -p ".agents/agents" ".agents/skills"

for d in plugins/plan/agents/*/; do
  name=$(basename "$d")
  rm -rf ".agents/agents/$name"
  cp -R "plugins/plan/agents/$name" ".agents/agents/$name"
done

for d in plugins/plan/skills/*/ plugins/viewers/skills/*/; do
  name=$(basename "$d")
  rm -rf ".agents/skills/$name"
  cp -R "$d" ".agents/skills/$name"
done
```

---

## 🎛️ Models per role

Each role declares its own model in the frontmatter of **both** its `agent.md` and `SKILL.md`: `model:` is the enforced tier (`flash` / `pro`), `x-plan-model` is the exact id (e.g. `opus-5.5-high`), and panel roles list one `x-plan-seats` entry per skeptic or delegate so every seat runs on a different model family. The supervisor (`starter`) reads these keys and dispatches each role on its declared model — exactly via `swarm add model=` where the swarm tool exists (Antigravity), by tier via `invoke_subagent` everywhere else, including agy.

- **Run:** in a normal conversation, `/model gemini-4-hydrogen-high`, then "be the supervisor". The supervisor prints the routing table before dispatching anything.
- **Change a model:** edit `x-plan-model` (and `model:` if the tier changes) in the role's two files; start a new conversation.
- **Full table, routes, and consistency checks:** [plugins/plan/README.md → Models per role](./plugins/plan/README.md#models-per-role).

---

## 📚 Documentation Directory

Explore the underlying documentation for details on individual roles, lifecycle stages, and deliverables:

* **Swarm Agents (AGY CLI):** Detailed system prompts, guidelines, and AGY tool specifications are documented in [plugins/plan/agents/README.md](./plugins/plan/agents/README.md).
* **Planning Skills (AGY CLI):** Complete guide to skills, artifacts, and lifecycle is documented in [plugins/plan/README.md](./plugins/plan/README.md).
* **Viewers Plugin (AGY CLI):** Trajectory and timing dashboard skills documentation is in [plugins/viewers/README.md](./plugins/viewers/README.md).