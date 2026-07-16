# Plan Swarm: Spec-Driven Planning Skills & Agents

A disciplined swarm of role-based agents, deliberative panels, and adversarial validation gates that drive features, bug fixes, or refactors through a robust **spec → plan → execute → audit → commit** lifecycle. 

This repository supports both **Antigravity CLI (AGY CLI)** and **Claude Code**, providing identical roles, workflows, and output files across both harnesses.

---

## 🚀 Quick Start & Installation

### 1. How to Install Agents in AGY CLI
> 📖 See [agents/README.md](file:///Users/ddobrin/work/dan/danrepos/agentic/active/plan-skills/agents/README.md) for the complete reference.

Antigravity CLI discovers agents as directories, each named after the agent and containing a single `agent.md` file (whose body acts as the system prompt). You can install the swarm agents globally or workspace-locally.

#### Method A: Loose Global Agents (Recommended)
This method installs the roles globally, making them available in all of your projects:
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

#### Method C: Bundle as an Antigravity Plugin
Alternatively, bundle the agents inside a plugin structure (`plugin.json` + `agents/` folder) and install it using:
```bash
agy plugin install /absolute/path/to/your/plan-plugin
```

---

### 2. How to Install Skills in AGY CLI
> 📖 See [plugins/plan/README.md](file:///Users/ddobrin/work/dan/danrepos/agentic/active/plan-skills/plugins/plan/README.md) for details on the skill set.

Skills are registered via Antigravity plugins. To install the planning skills as an AGY plugin directly from this GitHub repository, execute the following command in your terminal:
```bash
agy plugin install https://github.com/ddobrin/plan-skills
```

---

### 3. How to Install Skills in Claude Code
> 📖 See [plugins/plan/README.md](file:///Users/ddobrin/work/dan/danrepos/agentic/active/plan-skills/plugins/plan/README.md) for the complete skill reference.

In Claude Code, you add the repository to your plugin marketplace and install the relevant plugins:
```bash
/plugin marketplace add ddobrin/plan-skills
/plugin install plan@plan-skills
/plugin install orchestrator@plan-skills
```

---

### 4. How to Install Agents in Claude Code
> 📖 See [plugins/plan/agents/README.md](file:///Users/ddobrin/work/dan/danrepos/agentic/active/plan-skills/plugins/plan/agents/README.md) for the subagent reference.

Subagents (agents) in Claude Code are packaged and distributed directly within the `plan` plugin. 

* **Installation:** Simply installing the `plan` plugin (as shown above using `/plugin install plan@plan-skills`) automatically makes these subagents available to Claude Code. No additional commands or directory copies are required.
* **Usage & Invocation:** Once installed, there are three ways to invoke a subagent:
  1. **Explicitly via the `Task` tool:** Set the `subagent_type` field to `plan:{name}` (e.g., `plan:supervisor`, `plan:architect`).
  2. **Automatically via Auto-Delegation:** The runtime automatically picks an agent when a user request matches the patterns/examples inside the agent's frontmatter description.
  3. **From the CLI:** Run `claude --agent {name}` to launch a single role directly.

---

## 📚 Documentation Directory

Explore the underlying documentation for details on individual roles, lifecycle stages, and deliverables:

* **Swarm Agents (AGY CLI):** Detailed system prompts and guidelines are documented in [agents/README.md](file:///Users/ddobrin/work/dan/danrepos/agentic/active/plan-skills/agents/README.md).
* **Planning Skills (Claude Code):** Complete guide to skills, artifacts, and lifecycle is documented in [plugins/plan/README.md](file:///Users/ddobrin/work/dan/danrepos/agentic/active/plan-skills/plugins/plan/README.md).
* **Planning Subagents (Claude Code):** Complete guide to subagents, frontmatter schema, and auto-delegation triggers is documented in [plugins/plan/agents/README.md](file:///Users/ddobrin/work/dan/danrepos/agentic/active/plan-skills/plugins/plan/agents/README.md).
* **Supervisor Orchestrator Plugin:** Documentation for the spec-driven coordinator and validation gates is in [plugins/orchestrator/README.md](file:///Users/ddobrin/work/dan/danrepos/agentic/active/plan-skills/plugins/orchestrator/README.md).