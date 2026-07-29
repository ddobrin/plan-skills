# Plan Swarm: Spec-Driven Planning Skills & Agents

A disciplined swarm of role-based agents, deliberative panels, and adversarial validation gates that drive features, bug fixes, or refactors through a robust **spec → plan → execute → audit → commit** lifecycle. 

This repository is optimized for **Google Antigravity CLI (AGY CLI)**, providing native roles, workflows, tool specifications, and output files.

---

## 🚀 Quick Start & Installation

### 1. How to Install Custom Agents in AGY CLI
> 📖 See [agents/README.md](file:///Users/ddobrin/work/dan/danrepos/agentic/active/plan-skills/agents/README.md) for the complete reference.

Antigravity CLI discovers custom agents as directories, each named after the agent and containing a single `agent.md` file (whose body acts as the system prompt and frontmatter specifies available tools). You can install the swarm agents globally or workspace-locally.

#### Method A: Loose Global Agents (Recommended)
This method installs the roles globally in AGY CLI, making them available across all of your projects:
```bash
mkdir -p "$HOME/.gemini/config/agents"
for d in agents/*/; do
  name=$(basename "$d")
  rm -rf "$HOME/.gemini/config/agents/$name"
  cp -R "agents/$name" "$HOME/.gemini/config/agents/$name"
done
```
> [!IMPORTANT]
> Always copy the **entire directory** (`cp -R`), not just individual files. Visual agents (`visual-architect`, `visual-product-owner`, etc.) carry bundled assets (such as `assets/template.html` and `references/`) that must remain relatively aligned inside their installation directories to prevent rendering errors.

#### Method B: Project-Scoped (Workspace) Agents
To make the swarm agents available only within a specific project, place them in a `.agents/agents` subfolder:
```bash
mkdir -p ".agents/agents"
cp -R agents/* .agents/agents/
```

---

### 2. How to Install Skills as AGY Plugins
> 📖 See [plugins/plan/README.md](file:///Users/ddobrin/work/dan/danrepos/agentic/active/plan-skills/plugins/plan/README.md) for details on the skill set.

Skills in AGY CLI are registered via Antigravity plugins. You can install the planning plugins directly into AGY using `agy plugin install`:

```bash
# Install the core planning plugin
agy plugin install plugins/plan

# Install the supervisor orchestrator plugin
agy plugin install plugins/orchestrator
```

Or install the repository plugin bundle directly from GitHub:
```bash
agy plugin install https://github.com/ddobrin/plan-skills
```

---

## 📚 Documentation Directory

Explore the underlying documentation for details on individual roles, lifecycle stages, and deliverables:

* **Swarm Agents (AGY CLI):** Detailed system prompts, guidelines, and AGY tool specifications are documented in [agents/README.md](file:///Users/ddobrin/work/dan/danrepos/agentic/active/plan-skills/agents/README.md).
* **Planning Skills (AGY CLI):** Complete guide to skills, artifacts, and lifecycle is documented in [plugins/plan/README.md](file:///Users/ddobrin/work/dan/danrepos/agentic/active/plan-skills/plugins/plan/README.md).
* **Supervisor Orchestrator Plugin:** Documentation for the spec-driven coordinator and validation gates is in [plugins/orchestrator/README.md](file:///Users/ddobrin/work/dan/danrepos/agentic/active/plan-skills/plugins/orchestrator/README.md).