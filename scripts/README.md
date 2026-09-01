# Installation Scripts

Convenience scripts to install the **Plan Swarm** standalone agents and plugin skills directly from GitHub (supporting any specific branch or fork).

---

## Available Scripts

| Script | Purpose |
| :--- | :--- |
| [`install-agents.sh`](install-agents.sh) | Installs the 13 standalone Antigravity subagents globally or project-scoped. |
| [`install-skills.sh`](install-skills.sh) | Installs the `plan` and `orchestrator` plugin skills via `agy plugin install`. |
| [`install-all.sh`](install-all.sh) | Installs both the 13 subagents and all plugin skills in a single command. |

---

## Prerequisites

- **Git** (`git` CLI command)
- **Antigravity CLI** (`agy` CLI command)

Ensure the scripts are executable before running:
```bash
chmod +x scripts/*.sh
```

---

## Usage Examples

### 1. Install Everything (`install-all.sh`)

```bash
# Install from default branch (plan-graph) globally
./scripts/install-all.sh

# Install from a specific branch (e.g., main or a feature branch)
./scripts/install-all.sh --branch main

# Install from a custom fork
./scripts/install-all.sh --repo https://github.com/my-fork/plan-skills.git --branch dev

# Install agents project-scoped to current directory (.agents/agents)
./scripts/install-all.sh --project
```

### 2. Install Only Agents (`install-agents.sh`)

```bash
# Global installation (~/.gemini/config/agents)
./scripts/install-agents.sh

# Install from a specific branch
./scripts/install-agents.sh --branch plan-graph

# Project-scoped installation (.agents/agents)
./scripts/install-agents.sh --project
```

### 3. Install Only Plugin Skills (`install-skills.sh`)

```bash
# Install planning & orchestrator skills from default branch
./scripts/install-skills.sh

# Install from a specific branch
./scripts/install-skills.sh --branch plan-graph
```

---

## Options & Flags

All scripts accept the following flags:

| Flag | Description | Default |
| :--- | :--- | :--- |
| `-b, --branch <branch>` | Target Git branch to clone and install from | `plan-graph` (or `$BRANCH` env var) |
| `-r, --repo <url>` | Target Git repository URL | `https://github.com/ddobrin/plan-skills.git` (or `$REPO` env var) |
| `-p, --project` | Install subagents to workspace `.agents/agents/` | `global` (`~/.gemini/config/agents/`) |
| `-g, --global` | Install subagents globally to `~/.gemini/config/agents/` | Enabled by default |
| `-h, --help` | Display help and usage information | — |

---

## Verification

After running any installation script, verify that the components are properly registered:

```bash
# Check installed subagents
agy agents

# Check installed plugins
agy plugin list
```
