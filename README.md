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

## 🚀 Quick Start & Installation (`~/.gemini/config`)

### One-Step Automated Install (Recommended)

Run `./scripts/install-all.sh` from a local checkout (or via `curl | bash`) to install and enable all plugins, skills, and the 13 custom reasoning subagents directly in `~/.gemini/config`:

```bash
# From a local checkout of this repository:
./scripts/install-all.sh

# Or directly via curl from GitHub:
curl -fsSL https://raw.githubusercontent.com/ddobrin/plan-skills/main/scripts/install-all.sh | bash
```

What `./scripts/install-all.sh` creates in `~/.gemini/config`:
1. **`~/.gemini/config/agents/`**: All 13 self-contained reasoning subagents (`architect`, `auditor`, `engineer`, `implementation-validator`, `plan-deliberator`, `plan-validator`, `product-owner`, `spec-deliberator`, `spec-validator`, `supervisor`, `visual-architect`, `visual-implementation-recap`, `visual-product-owner`) along with bundled `assets/` and `references/`.
2. **`~/.gemini/config/plugins/plan/`**: Complete self-contained Plan Swarm plugin bundle containing both `skills/` (19 skills including `/plan-swarm`) and `agents/` (the 13 subagents) plus `graph.json` and `lib/graph/graph.py`.
3. **`~/.gemini/config/plugins/orchestrator/`**: Meta-orchestrator plugin bundle (`/orchestrator`).
4. **`~/.gemini/config/config.json`**: Atomically enables `"plan"` and `"orchestrator"` under `"plugins"` and validates the installed topology via `graph.py validate`.

For project-scoped installation into `./.agents/` (`./.agents/agents/` and `./.agents/plugins/`), pass `--project`:
```bash
./scripts/install-all.sh --project
```
> 📖 See [`scripts/README.md`](scripts/README.md) for individual installers (`install-skills.sh`, `install-agents.sh`) and CLI flags (`--config-dir`, `--branch`, `--standalone-skills`).

---

### Using the `"plan"` Commands in Chat

Once installed, invoke the swarm or individual roles directly from chat:

* **`/plan-swarm`** — Start a new milestone (`plans/active_milestones/{moniker}/state.json`) or resume an existing milestone at its exact `state.json` stage across the 4-phase lifecycle.
* **Phase 1 (Spec):** `/product-owner`, `/visual-product-owner`, `/spec-deliberator`, `/spec-validator`
* **Phase 2 (Plan):** `/architect`, `/visual-architect`, `/plan-deliberator`, `/plan-validator`
* **Phase 3 (Execute):** `/engineer`, `/simplifier`, `/visual-implementation-recap`
* **Phase 4 (Verify & Gate):** `/auditor`, `/implementation-validator`
* **Cross-Project Meta-Orchestration:** `/orchestrator`

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
