# `modernize` Plugin Agents

Legacy modernization and clean-room domain extraction agents for **Google Antigravity CLI (AGY CLI)**.

## Credits
* Jason De Lorme - [link](https://github.com/jjdelorme/plan-commands/tree/main/agents/reverse_engineer)

## Included Agents

### `reverse_engineer` — DDD Reverse Engineer & Domain Analyst
Deconstructs existing applications, data stores, schemas, batch jobs, and visual assets into a stack-agnostic **Open Knowledge Format (`okf/`)** bundle (OKF v0.3) designed for clean-room modernization.

- **Adapted from:** [`jjdelorme/plan-commands/agents/reverse_engineer/agent.md`](https://github.com/jjdelorme/plan-commands/blob/main/agents/reverse_engineer/agent.md)
- **Produces:** `okf/` bundle containing:
  - `okf/index.md` — Tier 1 progressive-disclosure catalog (`okf_version: "0.3"`), system overview, and Mermaid architecture diagram.
  - `okf/log.md` — Chronological extraction and verification log.
  - Tier 2 self-contained `kebab-case.md` concept files (Bounded Contexts, Aggregates, Capabilities with executable Gherkin scenarios, Schemas/Lookups, and Attested Computations) with per-claim provenance footnotes (`[^source]`).
- **Four Laws:** Clean-Room Zero-Assumption Rule, Implementation-Agnostic DDD Extraction, Two-Tier Progressive Disclosure, and Cross-Artifact Reconciliation.
- **Built-In Verification Pass:** Defines and invokes a clean-context, read-only reviewer subagent (passing only source and `okf/` paths) to audit completeness, clean-room compliance, Gherkin coverage, and OKF v0.3 conformance, remediating up to 2 passes before stamping `verified` metadata.
- **Constraints:** Read-only on application code (writes exclusively under `okf/`); no invented rules or silent omissions; no Git operations (`commit`, `tag`, `push`).

---

## Directory Layout

```text
plugins/modernize/
├── plugin.json                         # Antigravity plugin manifest
├── README.md                           # This guide
└── agents/
    └── reverse_engineer/
        └── agent.md                    # DDD Reverse Engineer custom agent / subagent
```

---

## Installation

### 1. Install as an AGY Plugin (Recommended)

#### From a Local Clone / Folder
From the repository root:

```bash
agy plugin validate ./plugins/modernize
agy plugin install ./plugins/modernize
agy plugin list
```

To refresh an already-installed copy after pulling or editing files:

```bash
agy plugin uninstall modernize && agy plugin install ./plugins/modernize
```

#### From the GitHub Repository
Clone the repository and install the `modernize` plugin directory:

```bash
git clone https://github.com/ddobrin/plan-skills.git
cd plan-skills
agy plugin validate ./plugins/modernize
agy plugin install ./plugins/modernize
```

### 2. Install as a Loose Agent (Optional)
`reverse_engineer` is completely self-contained. To install globally or workspace-locally without the plugin wrapper, copy the entire directory (`cp -R`):

```bash
# Global loose install
mkdir -p "$HOME/.gemini/config/agents"
for d in plugins/modernize/agents/*/; do
  name=$(basename "$d")
  rm -rf "$HOME/.gemini/config/agents/$name"
  cp -R "$d" "$HOME/.gemini/config/agents/$name"
done

# Or project-scoped loose install
mkdir -p ".agents/agents"
for d in plugins/modernize/agents/*/; do
  name=$(basename "$d")
  rm -rf ".agents/agents/$name"
  cp -R "$d" ".agents/agents/$name"
done
```

---

## Usage

- **As a Main Agent (`/agents`):** Launch `agy`, open `/agents`, select `reverse_engineer`, and point it at the legacy codebase and schemas to extract into `okf/`.
- **As a Subagent (`invoke_subagent`):** Dispatch `TypeName: "reverse_engineer"` from an orchestrator or interactive session to generate and verify an `okf/` bundle in a dedicated context window.
- **Clean-Room Modernization with `plugins/plan`:**
  1. Run `reverse_engineer` on the legacy repository to extract a verified `okf/` bundle.
  2. Copy `okf/` into a clean target workspace (zero access to legacy source) and use the `plan` swarm (`supervisor` / `product-owner` → `architect` → `engineer` → `auditor`) to rebuild on the target stack strictly from `okf/`.
