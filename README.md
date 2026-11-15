# Plan Swarm: Spec-Driven Planning Skills & Agents

A disciplined swarm of role-based agents, deliberative panels, and adversarial validation gates that drive features, bug fixes, or refactors through a robust **spec → plan → execute → audit → commit** lifecycle. 

This repository is optimized for **Google Antigravity CLI (AGY CLI)**, providing a declared topology, per-milestone state tracking, native roles, workflows, tool specifications, and output files.

---

## 🏗️ The Swarm Lifecycle

<!-- BEGIN GENERATED: lifecycle (python3 lib/graph/graph.py sync) -->
<!-- graph_version: plan-swarm@2.1 — edit graph.json, then run sync. -->

```text
 IDEA
  |
  v  Phase 0   research -- plans/research/*.md
  |
  v  Phase 1   product-owner -- spec.md · 00-ROADMAP.md
  |            +- (optional) spec-deliberator -- 3 delegates · disjoint bundles
  |            === GATE spec-validator [3-lens majority gate: internal-consistency · missing-requirement · malicious-compliance]
  |                 -> plans/active_milestones/{moniker}/adversarial-reviews/spec-validation.md
  |
  v  Phase 2   architect -- plan.md · parallel groups
  |            +- (optional) plan-deliberator -- intent · codebase · delivery
  |            === GATE plan-validator [3-lens majority gate: sequencing · ground-truth · blast-radius]
  |                 -> plans/active_milestones/{moniker}/adversarial-reviews/plan-validation.md
  |
  v  Phase 3  *** HUMAN REVIEW GATE *** -- user types "approve"
  |
  v  Phase 4   engineer × N -- ≤ 4 concurrent · disjoint files
  |               fan-out over execution group tasks, max 4 concurrent, files-disjoint
  |            +- (optional) simplifier -- zero behavioral change
  |
  v  Phase 4   auditor -- AUDIT_[Plan_Name].md
  |            === GATE implementation-validator [3-lens majority gate: claim-vs-reality · failure-paths · blast-radius]
  |                 -> plans/active_milestones/{moniker}/adversarial-reviews/implementation-validation.md
  |            +- (optional) visual-implementation-recap -- visual-recap.html
  |
  v  Phase 4  *** COMMIT GATE *** -- green audit + explicit "yes"
  |
  v  Phase 5  release · tag -- product-owner marks Shipped

 feedback edges (cycles):
   spec-validator -> product-owner   when: confirmed findings — fold in tightenings
   plan-validator -> architect   when: confirmed findings — apply fixes · first_domino
   auditor -> engineer   when: code failure — fix the failing task
   auditor -> architect   when: plan failure — step is impossible
   implementation-validator -> engineer   when: confirmed defects — fix at calibrated severity
   commit-gate -> engineer   when: more groups remain — next execution group
```

<!-- END GENERATED: lifecycle -->

---

## 🧭 Swarm Architecture & Graph Engineering Principles

The swarm's structure is declared in [`plugins/plan/graph.json`](./plugins/plan/graph.json) rather than described in prose, and checked by tooling:

1. **Declared Topology (`graph.json`):** 16 nodes, 25 edges (19 forward, 6 feedback), 2 human gates, and 5 invariants. The lifecycle diagram above is generated from it, and `graph.py validate` checks it against the skills and agents on disk.
2. **Declared State (`state.json`):** Every milestone maintains `plans/active_milestones/{moniker}/state.json`. The orchestrator (`supervisor` / `starter`) reads and writes explicit transitions rather than guessing the phase from a directory listing.
3. **Lens-Partitioned Validator Panels:** The adversarial gates (`spec-validator`, `plan-validator`, `implementation-validator`) each dispatch 3 skeptics across 3 distinct lenses and reading assignments. Copies of one prompt are treated as a defect; a 2-of-3 majority confirms a finding, cross-lens agreement ranks first, and single-vote findings must be triaged.
4. **Deliberator Asymmetry Preconditions:** The consensus panels (`spec-deliberator`, `plan-deliberator`) run only if the asymmetry test passes (each delegate holds private facts or territory). If the context can be merged into a single prompt, deliberation is refused in favor of centralized revision.
5. **Sole-Committer Invariant:** `supervisor` (or `starter`) is the **only** role that runs `git commit`, and only after a passing audit and an explicit "yes" from the user.

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

### 2. Install as Loose Agents & Viewer Skills (Optional)
> 📖 See [plugins/plan/agents/README.md](./plugins/plan/agents/README.md) for the complete agent reference.

Antigravity CLI discovers custom agents as directories, each named after the agent and containing a single `agent.md` file (whose body acts as the system prompt and frontmatter specifies available tools). If you prefer loose installations instead of AGY plugins, you can copy the swarm agents and the viewer skills globally or workspace-locally.

> [!NOTE]
> The `plan` skills are not installed loose: `starter` reads `graph.json` and `lib/graph/STATE.md` from the plugin root, so install them through the `plan` plugin above. The viewer skills are self-contained and work either way.

#### Method A: Loose Global Agents & Viewer Skills
This installs the roles and the viewer skills globally in AGY CLI, making them available across all of your projects:
```bash
mkdir -p "$HOME/.gemini/config/agents" "$HOME/.gemini/config/skills"

for d in plugins/plan/agents/*/; do
  name=$(basename "$d")
  rm -rf "$HOME/.gemini/config/agents/$name"
  cp -R "plugins/plan/agents/$name" "$HOME/.gemini/config/agents/$name"
done

for d in plugins/viewers/skills/*/; do
  name=$(basename "$d")
  rm -rf "$HOME/.gemini/config/skills/$name"
  cp -R "$d" "$HOME/.gemini/config/skills/$name"
done
```
> [!IMPORTANT]
> Always copy the **entire directory** (`cp -R`), not just individual files. Visual agents (`visual-architect`, `visual-product-owner`, `visual-implementation-recap`) carry bundled assets (such as `assets/template.html` and `references/`), and viewer skills (`teamwork-trajectory`, `boost-trajectory`) carry helper scripts next to their `generator.py`; these must remain relatively aligned inside their installation directories.

#### Method B: Project-Scoped (Workspace) Agents & Viewer Skills
To make them available only within a specific project, copy them into `.agents/agents` and `.agents/skills`:
```bash
mkdir -p ".agents/agents" ".agents/skills"

for d in plugins/plan/agents/*/; do
  name=$(basename "$d")
  rm -rf ".agents/agents/$name"
  cp -R "plugins/plan/agents/$name" ".agents/agents/$name"
done

for d in plugins/viewers/skills/*/; do
  name=$(basename "$d")
  rm -rf ".agents/skills/$name"
  cp -R "$d" ".agents/skills/$name"
done
```

---

## 🛠️ Verification & Tooling CLI

The topology tooling ([`plugins/plan/lib/graph/graph.py`](./plugins/plan/lib/graph/graph.py), stdlib-only Python) validates the declaration and keeps the documentation in sync with it:

```bash
# Validate graph.json against the skills and agents on disk, plus every agent's invariants
python3 plugins/plan/lib/graph/graph.py validate --agents-dir

# Validate a loose global install of the agents (expects that directory to hold exactly
# the thirteen swarm agents; any other agent installed there is reported as unexpected)
python3 plugins/plan/lib/graph/graph.py validate-agents --agents-dir ~/.gemini/config/agents

# Check that the generated lifecycle diagrams in the three READMEs are up to date
python3 plugins/plan/lib/graph/graph.py sync --check

# Re-generate them after editing graph.json
python3 plugins/plan/lib/graph/graph.py sync

# Run the tooling's own test suite
python3 plugins/plan/lib/graph/test_graph.py
```

---

## 📚 Documentation Directory

Explore the underlying documentation for details on individual roles, lifecycle stages, and deliverables:

* **Swarm Agents (AGY CLI):** Detailed system prompts, guidelines, and AGY tool specifications are documented in [plugins/plan/agents/README.md](./plugins/plan/agents/README.md).
* **Planning Skills (AGY CLI):** Complete guide to skills, artifacts, lifecycle, topology, and state is documented in [plugins/plan/README.md](./plugins/plan/README.md).
* **Topology (`graph.json`):** The declared nodes, edges, gates, and node contracts live in [plugins/plan/graph.json](./plugins/plan/graph.json).
* **State Schema (`state.json`):** The per-milestone state file and its field semantics are documented in [plugins/plan/lib/graph/STATE.md](./plugins/plan/lib/graph/STATE.md).
* **Viewers Plugin (AGY CLI):** Trajectory and timing dashboard skills (`teamwork-trajectory`, `boost-trajectory`) are documented in [plugins/viewers/README.md](./plugins/viewers/README.md).
