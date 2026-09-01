# Plan Swarm: Spec-Driven Planning Skills & Agents

A disciplined swarm of role-based agents, deliberative panels, and adversarial validation gates that drive features, bug fixes, or refactors through a robust **spec → plan → execute → audit → commit** lifecycle. 

This repository is optimized for **Google Antigravity CLI (AGY CLI)** and **Claude Code**, providing declarative topology, state-machine tracking, native agent roles, workflows, tool specifications, and output files.

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

The swarm operates on strict graph engineering principles declared in [`plugins/plan/graph.json`](plugins/plan/graph.json):

1. **Declarative Topology (`graph.json`):** 16 swarm nodes, 25 edges (19 forward, 6 feedback cycles), 2 human gates, and 5 invariants. Tooling automatically enforces and syncs documentation.
2. **Deterministic State Machine (`state.json`):** Every milestone maintains `plans/active_milestones/{moniker}/state.json`. The orchestrator (`supervisor` / `starter`) reads and updates explicit state transitions rather than guessing phases from directory listings.
3. **Disjoint 3-Lens Validator Panels:** Adversarial gates (`spec-validator`, `plan-validator`, `implementation-validator`) dispatch 3 skeptics across disjoint evidence lenses. Identical prompts are treated as defects; 2-of-3 majority decides findings, and single votes mandate triage.
4. **Deliberator Asymmetry Preconditions:** Deliberative consensus panels (`spec-deliberator`, `plan-deliberator`) require passing the asymmetry test (each delegate holds private facts/territory). If context can be merged into a single prompt, deliberation is refused in favor of centralized revision.
5. **Sole-Committer Invariant:** Version control authority is strictly isolated. `supervisor` (or `starter`) is the **sole committer**, requiring both a passing audit report and explicit conversational approval ("yes") from the user.

---

## 🚀 Quick Start & Installation

### 1. How to Install Custom Subagents in AGY CLI
> 📖 See [`agents/README.md`](agents/README.md) for the complete reference.

Antigravity CLI discovers custom agents as directories, each named after the agent and containing a single `agent.md` file (whose body acts as the system prompt and frontmatter specifies available tools). All 13 reasoning agents are packaged under [`agents/`](agents/).

#### Method A: Loose Global Agents (Recommended)
This method installs the 13 standalone roles globally in AGY CLI, making them available across all of your projects:
```bash
mkdir -p "$HOME/.gemini/config/agents"
for d in agents/*/; do
  name=$(basename "$d")
  rm -rf "$HOME/.gemini/config/agents/$name"
  cp -R "agents/$name" "$HOME/.gemini/config/agents/$name"
done
```
> [!IMPORTANT]
> Always copy the **entire directory** (`cp -R`), not just individual files. Visual agents (`visual-architect`, `visual-product-owner`, `visual-implementation-recap`) carry bundled assets (such as `assets/template.html` and `references/`) that must remain relatively aligned inside their installation directories to prevent rendering errors.

#### Method B: Project-Scoped (Workspace) Agents
To make the swarm agents available only within a specific project, place them in a `.agents/agents` subfolder:
```bash
mkdir -p ".agents/agents"
cp -R agents/* .agents/agents/
```

---

### 2. How to Install Skills as AGY Plugins
> 📖 See [`plugins/plan/README.md`](plugins/plan/README.md) for details on the skill set.

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

## 🛠️ Verification & Tooling CLI

The single-source topology tooling ([`plugins/plan/lib/graph/graph.py`](plugins/plan/lib/graph/graph.py)) validates graph contracts and keeps documentation synchronized:

```bash
# Validate graph.json topology against disk
python3 plugins/plan/lib/graph/graph.py validate

# Validate standalone subagents in agents/
python3 plugins/plan/lib/graph/graph.py validate-agents

# Validate installed global agents
python3 plugins/plan/lib/graph/graph.py validate-agents --agents-dir ~/.gemini/config/agents

# Verify documentation lifecycle diagrams are up to date
python3 plugins/plan/lib/graph/graph.py sync --check

# Re-generate documentation lifecycle diagrams
python3 plugins/plan/lib/graph/graph.py sync
```

---

## 📚 Documentation Directory

Explore the underlying documentation for details on individual roles, lifecycle stages, and deliverables:

* **[Standalone Agents (`agents/README.md`)](agents/README.md):** 13 AGY CLI subagents, system prompts, 3-lens partitioned validator panels, and standalone packaging.
* **[Planning Skills (`plugins/plan/README.md`)](plugins/plan/README.md):** Complete guide to skills, state machine, adversarial reviews, and artifacts.
* **[State Schema (`plugins/plan/lib/graph/STATE.md`)](plugins/plan/lib/graph/STATE.md):** Declarative milestone state machine lifecycle and schema.
* **[Supervisor Orchestrator Plugin (`plugins/orchestrator/README.md`)](plugins/orchestrator/README.md):** Documentation for the spec-driven coordinator and validation gates.
