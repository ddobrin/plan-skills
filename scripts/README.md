# Installation Scripts (`scripts/`)

This directory contains automated installation scripts for setting up the **Plan Swarm** (`plugins/plan`) and the **13 self-contained reasoning subagents** (`agents/` and `plugins/plan/agents/`) directly into `~/.gemini/config` (or `./.agents` for project-scoped installation).

## What Gets Installed into `~/.gemini/config`

Running `./scripts/install-all.sh` creates and configures the following artifacts directly in `~/.gemini/config` (no external `agy` binary required):

```text
~/.gemini/config/
├── config.json                        # Atomically merges "plan": {"enabled": true}
├── agents/                            # All 13 self-contained reasoning subagents (global discovery)
│   ├── architect/agent.md
│   ├── auditor/agent.md
│   ├── engineer/agent.md
│   ├── implementation-validator/agent.md
│   ├── plan-deliberator/agent.md
│   ├── plan-validator/agent.md
│   ├── product-owner/agent.md
│   ├── spec-deliberator/agent.md
│   ├── spec-validator/agent.md
│   ├── supervisor/agent.md
│   ├── visual-architect/              # Includes bundled assets/template.html & references/
│   ├── visual-implementation-recap/   # Includes bundled assets/template.html & references/
│   └── visual-product-owner/          # Includes bundled assets/template.html & references/
└── plugins/
    └── plan/                          # Complete self-contained Plan Swarm plugin bundle
        ├── plugin.json
        ├── graph.json
        ├── lib/graph/graph.py
        ├── agents/                    # Bundled 13 custom subagents
        └── skills/                    # 17 skills (including /plan-swarm + role, panel, and trajectory skills)
```

Every install run automatically executes `python3 ~/.gemini/config/plugins/plan/lib/graph/graph.py validate --agents-dir ...` to verify the installed topology and subagent contracts.

---

## Available Scripts

| Script | Description |
| :--- | :--- |
| **[`install-all.sh`](./install-all.sh)** | **Recommended.** Installs both the 13 custom subagents (`install-agents.sh`) and the `plan` plugin/skills (`install-skills.sh`) into `~/.gemini/config`, enables `plan` in `~/.gemini/config/config.json`, and validates the installed graph. |
| **[`install-skills.sh`](./install-skills.sh)** | Installs `plugins/plan` into `~/.gemini/config/plugins/plan/` (or `./.agents/plugins/plan/` with `--project`) and enables `plan` in `~/.gemini/config/config.json`. |
| **[`install-agents.sh`](./install-agents.sh)** | Installs the 13 standalone custom subagent definitions into `~/.gemini/config/agents/` (or `./.agents/agents/` with `--project`) and validates them with `graph.py validate-agents`. |

---

## Usage

### 1. From a Local Checkout (Recommended during development or after cloning)

When run from a local checkout of `plan-skills`, the scripts automatically detect the local workspace and install directly from it without re-cloning from GitHub:

```bash
chmod +x scripts/*.sh
./scripts/install-all.sh
```

### 2. One-Liner Remote Installation (`curl | bash`)

To install directly from GitHub without manually cloning first:

```bash
curl -fsSL https://raw.githubusercontent.com/ddobrin/plan-skills/main/scripts/install-all.sh | bash
```

To install from a specific branch (e.g., `refine`):

```bash
curl -fsSL https://raw.githubusercontent.com/ddobrin/plan-skills/refine/scripts/install-all.sh | bash -s -- -b refine
```

### 3. Command-Line Options

All three scripts (`install-all.sh`, `install-skills.sh`, `install-agents.sh`) accept the same flags:

| Option | Description | Default |
| :--- | :--- | :--- |
| `-g`, `--global` | Install globally into `~/.gemini/config` (`agents/`, `plugins/`, `config.json`). | **Default** |
| `-p`, `--project` | Install into the current repository's `./.agents/` directory (`./.agents/agents/`, `./.agents/plugins/`). | — |
| `--config-dir <dir>` | Override the target global configuration directory (can also be set via `GEMINI_CONFIG_DIR`). | `~/.gemini/config` |
| `--standalone-skills` | Also copy unwrapped skill folders into `~/.gemini/config/skills/` (in addition to `plugins/<name>/skills/`). | `false` |
| `--local` | Force installing from the local repository checkout. | Auto-detected |
| `--remote` | Force cloning from the remote Git repository (`--repo` / `--branch`) into a temporary directory before installing. | Auto-detected |
| `-b`, `--branch <name>` | Git branch or tag to clone when running in remote mode (implies `--remote`). | `main` |
| `-r`, `--repo <url>` | Git repository URL to clone when running in remote mode (implies `--remote`). | `https://github.com/ddobrin/plan-skills.git` |
| `-h`, `--help` | Print usage information and exit. | — |
