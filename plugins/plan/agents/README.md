# Plan Swarm Agents (Antigravity CLI Version)

A swarm of role-based agents, deliberative panels, and adversarial validation gates that drive a feature, bug fix, or refactor through a disciplined **spec → plan → execute → audit → commit** lifecycle.

This directory contains the **Antigravity-format (`agy`)** standalone subagents for the planning swarm, complementing the skills packaged under [`plugins/plan/`](../plugins/plan) and [`plugins/orchestrator/`](../plugins/orchestrator). All roles maintain strict alignment with graph engineering principles and invariant enforcement.

These agents are designed to be used together. A single orchestrator (`supervisor`) dispatches the role agents in sequence, stops for human approval at defined gates, and manages the milestone state machine in `plans/active_milestones/{moniker}/state.json` — treating declarative files, not chat messages or directory heuristics, as the single source of truth. Independent *validator* agents slot in at phase boundaries to attack artifacts (spec, plan, or diff) across 3 disjoint evidence lenses before downstream phases consume them.

---

## The Swarm Families

| Family | Agents | Purpose |
|---|---|---|
| **Swarm roles** | `supervisor`, `product-owner` (or `visual-product-owner`), `architect` (or `visual-architect`), `engineer`, `auditor`, `visual-implementation-recap` | Perform the lifecycle — discover, spec, plan, build, verify, and recap the result. `supervisor` is the sole committer and exclusive manager of `state.json`. *(Note: `simplifier` is not a separate agent in this port; its tasks are performed inline or handled by the engineer.)* |
| **Adversarial validators** | `spec-validator`, `plan-validator`, `implementation-validator` | Attack each artifact at its phase boundary using a 3-lens partitioned skeptic panel with disjoint reading assignments; keep findings confirmed by a 2-of-3 majority and mandate explicit triage for the 1-vote tail. |
| **Deliberative panels** | `spec-deliberator`, `plan-deliberator` | Improve a drafted artifact via delegates holding deliberately disjoint context (stakeholder bundles for specs, codebase/intent/delivery territories for plans) who deliberate to consensus across bounded rounds (hard cap of 4) — the generative counterpart to validators. Refuses deliberation if context is mergeable. |

---

## The Lifecycle

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

## Directory Layout

Antigravity discovers agents as **directories**, each named after the agent and containing a single `agent.md` (whose body acts as the system prompt). All 13 reasoning agents in this directory are fully self-contained:

```
agents/
├── README.md                           # This guide
├── supervisor/agent.md                 # Orchestrator, state machine manager & sole committer
├── product-owner/agent.md              # Socratic spec writer
├── visual-product-owner/               # Self-contained visual spec generator
│   ├── agent.md
│   ├── assets/template.html
│   ├── references/component-catalog.md
│   └── references/exemplar.md
├── architect/agent.md                  # Implementation planner
├── visual-architect/                   # Self-contained visual plan generator
│   ├── agent.md
│   ├── assets/template.html
│   ├── references/component-catalog.md
│   └── references/exemplar.md
├── engineer/agent.md                   # TDD builder (disjoint file fanout)
├── auditor/agent.md                    # Quality control & static/dynamic verifier
├── visual-implementation-recap/        # Self-contained visual recap generator
│   ├── agent.md
│   ├── assets/template.html
│   ├── references/component-catalog.md
│   └── references/exemplar.md
├── spec-deliberator/agent.md           # Generative spec consensus panel (asymmetry-gated)
├── plan-deliberator/agent.md           # Generative plan consensus panel (asymmetry-gated)
├── spec-validator/agent.md             # 3-lens adversarial spec gate
├── plan-validator/agent.md             # 3-lens adversarial plan gate (ground truth + first domino)
└── implementation-validator/agent.md   # 3-lens adversarial diff gate & severity calibration
```

> [!NOTE]
> The three **visual** agents (`visual-product-owner`, `visual-architect`, and `visual-implementation-recap`) are completely self-contained. They bundle their respective HTML `template.html` and reference files inside their own directories, eliminating any external path dependencies (`${CLAUDE_PLUGIN_ROOT}`).

---

## The Milestone State Machine (`state.json`)

Every active milestone carries `plans/active_milestones/{moniker}/state.json`. It is the milestone run's declarative record of **where it is**.

### The Anti-Pattern Eliminated
Inferring the phase by listing milestone directories and checking which files (`context.md`, `spec.md`, `plan.md`) happen to exist is an unreliable heuristic. Re-deriving state from directory listings cannot distinguish between a node that passed, failed, or was skipped (e.g. a failed validator run leaves `plan.md` on disk just as a passing one does). `state.json` provides deterministic state recording.

### Writer Contract
- **`supervisor` is the EXCLUSIVE WRITER.** All other nodes are strictly read-only.
- Supervisor updates `state.json`: at milestone creation, at every phase transition, at every gate decision, and upon node completion.
- Unknown fields are left absent or set to `"status": "unknown"`, never fabricated.
- Skipped gates/nodes must be recorded as `"status": "skipped"` with an explicit `"reason"`.

### Schema Specification
```json
{
  "graph_version": "plan-swarm@2.1",
  "run_id": "ms_{moniker}_{hash}",
  "moniker": "{moniker}",
  "phase": "0 | 1 | 1.gate | 2 | 2.gate | 3 | 4 | 4.gate | 5",
  "updated": "ISO-8601 UTC timestamp",

  "gates": [
    { "id": "plan-approval", "state": "not-reached | pending | approved | rejected" },
    { "id": "commit", "state": "not-reached | pending | approved | rejected" }
  ],

  "nodes": {
    "research": { "status": "pending | running | done | failed", "artifact": "plans/research/{topic}_context.md" },
    "product-owner": { "status": "pending | running | done | failed", "artifact": "spec.md" },
    "spec-deliberator": { "status": "pending | running | done | skipped", "reason": "asymmetry test failed — context was mergeable" },
    "spec-validator": {
      "status": "pending | running | passed | findings | failed",
      "report": "adversarial-reviews/spec-validation.md",
      "lenses": ["internal-consistency", "missing-requirement", "malicious-compliance"],
      "confirmed": 0, "single_vote": 0, "cross_lens": 0, "single_vote_triaged": true
    },
    "architect": { "status": "pending | running | done | failed", "artifact": "plan.md" },
    "plan-deliberator": { "status": "pending | running | done | skipped", "reason": "asymmetry test failed — context was mergeable" },
    "plan-validator": {
      "status": "pending | running | passed | findings | failed",
      "report": "adversarial-reviews/plan-validation.md",
      "lenses": ["sequencing", "ground-truth", "blast-radius"],
      "confirmed": 0, "single_vote": 0, "cross_lens": 0,
      "first_domino": null, "single_vote_triaged": true
    }
  },

  "groups": [
    {
      "id": "1",
      "tasks": { "1.A": "done", "1.B": "done" },
      "audit": "not-reached | passed | failed",
      "audit_rounds": 1,
      "implementation_validation": "adversarial-reviews/implementation-validation.md",
      "committed": "git_commit_sha"
    }
  ]
}
```

---

## Invariant Enforcement & Roles

### 1. Sole-Committer Invariant
- **`supervisor` is the SOLE committer in the entire swarm.**
- `auditor`, `engineer`, `architect`, and all other roles have **zero** commit authority.
- `git commit` is executed **only** after two prerequisites are satisfied:
  1. A green audit report (`AUDIT_[Plan_Name].md` is PASS) and verified implementation validation.
  2. Explicit user approval ("yes") obtained in a conversational turn.

### 2. Disjoint Evidence Lenses (No Correlated Skeptics)
Invariant 3 of `graph.json`: *"Every panel node declares n lenses and the same number of entries in panel.lenses; identical prompts are a defect, not a configuration."*

Dispatching identical prompts across three LLM runs produces correlated errors and false corroboration. Each validator panel partitions its attack surface across 3 disjoint evidence lenses with distinct reading assignments:

#### `spec-validator` (Phase 1 Gate)
- **Lens 1 (`internal-consistency`):** Reads the spec against itself twice. Owns `ambiguity`, `contradiction`, `terminology drift`.
- **Lens 2 (`missing-requirement`):** Reads context report, roadmap, and external constraints first. Owns missing errors, limits, concurrency, auth, time zones, and backward compat.
- **Lens 3 (`malicious-compliance`):** Reads the acceptance criteria alone without prose rationale to game them with the laziest passing implementation. Owns `malicious-compliance` and `untestable`.
- **Asymmetry Test:** Name one hole that only that lens could find. If context cannot be partitioned, merge to 2 lenses.
- **Output:** Report at `plans/active_milestones/{moniker}/adversarial-reviews/spec-validation.md` documenting confirmed findings (≥2 votes), cross-lens corroboration, and mandatory triage decisions for every single-vote finding.

#### `plan-validator` (Phase 2 Gate)
- **Lens 1 (`sequencing`):** Reads the plan steps in order before opening source. Owns `ordering`, step dependency graph, and execution group file collisions.
- **Lens 2 (`ground-truth`):** Opens every source file named in the plan. **Must cite `file:line`**. Owns `false-assumption` (missing/differing signatures, fields, tables, flags).
- **Lens 3 (`blast-radius`):** Reads callers, tests, CI, and migration tooling outside the changed files. Owns `unverifiable`, `no-rollback`, `missing-migration`, `hidden-coupling`.
- **Asymmetry Test:** Name one finding only that lens could reach (lens 2 opens files lens 1 never reads; lens 3 traces callers neither visits).
- **Output:** Report at `plans/active_milestones/{moniker}/adversarial-reviews/plan-validation.md` featuring the headline **First domino** (earliest failure that invalidates subsequent steps) and single-vote triage table.

#### `implementation-validator` (Phase 4 Gate)
- **Lens 1 (`claim-vs-reality`):** Reads change description first, then diff line by line. Owns `claim-mismatch` and undisclosed scope.
- **Lens 2 (`failure-paths`):** Reads error branches, early returns, null guards, timeouts, and tests. Owns `failure-path` and `edge-case`.
- **Lens 3 (`blast-radius`):** Reads files the diff does not touch (call sites, subclasses, serializers). Owns `concurrency`, `resource`, `regression`.
- **Asymmetry Test:** Name one defect only that lens could reach.
- **Output:** Report at `plans/active_milestones/{moniker}/adversarial-reviews/implementation-validation.md` featuring the **Severity Calibration** table (downgrading over-rated findings with explicit rationale) and single-vote triage.

### 3. Deliberator Preconditions & Bounded Relay
Deliberation is generative consensus-building, whereas validation is evaluative attack.
- **Mandatory Asymmetry Precondition:** Before convening delegates, run the asymmetry test.
  - For `spec-deliberator`: Name ≥1 concrete fact each delegate holds that others do not.
  - For `plan-deliberator`: Name ≥1 question about the plan that only that territory can answer.
  - **MANDATORY REFUSAL RULE:** If the asymmetry test fails — context fits in one prompt or can be merged — **REFUSE DELIBERATION**: STOP immediately, skip the node in `state.json` (`reason: "asymmetry test failed — context was mergeable"`), and tell the user/supervisor to revise centrally. Empirically, centralized revision beats deliberation whenever merging is possible.
- **Bounded Verbatim Relay:** Delegates cannot communicate directly. The orchestrator relays transcripts **verbatim, never paraphrased**. Under Antigravity's fire-and-return subagent harness, each round re-invokes delegates with the full verbatim transcript and private bundle. Hard cap: **4 rounds**.
- **Earned Acceptance:** Every `"accept"` stance requires an explicit `acceptance_basis` stating what was verified against the bundle/territory or what argument changed the delegate's mind.

---

## Agent Reference

### Swarm Roles

#### 1. `supervisor` — Project Manager & Sole Committer
The orchestrator and Guardian of the Protocol. Writes code only via delegation; owns milestone state machine in `state.json`; dispatches roles in sequence; enforces validation gates and human approval gates; and is the **sole committer**.
- **Owns:** Protocol enforcement, `state.json` management, human review gates, and git commits.
- **Key Rules:** Passes *file paths*, never oral summaries; must stop for user approval at Phase 3 (`plan-approval`) and Phase 4.gate (`commit`); commits only on green audit + passing implementation validation + explicit user "yes".

#### 2. `product-owner` — Socratic Spec Writer
Translates raw ideas into testable specifications (`spec.md`) and maintains `plans/00-ROADMAP.md`.
- **Produces:** `plans/active_milestones/{moniker}/spec.md` with Gherkin Given/When/Then acceptance criteria.
- **Grill Loop:** Asks targeted Socratic questions until all critical ambiguities are resolved.
- **Constraints:** Never edits source code; never commits.

#### 3. `visual-product-owner` — Visual Spec Writer
Drop-in alternative to `product-owner`. Runs identical Grill Loop and produces `spec.md`, then renders `visual-spec.html` (8 surfaces: overview, user stories, acceptance criteria, user flows, edge cases, wireframes, open questions, comments). Never commits.

#### 4. `architect` — Technical Planner
Reads spec, investigates codebase, and produces `plans/active_milestones/{moniker}/plan.md` with parallel execution groups and test-first micro-steps.
- **Constraints:** Read-only on source code; never commits; verification steps must name explicit runnable commands.

#### 5. `visual-architect` — Visual Planner
Drop-in alternative to `architect`. Produces identical `plan.md`, then renders `visual-plan.html` (9 surfaces: overview, architecture, file map, annotated code, API cards, schema map, wireframes, open questions, comments). Never commits.

#### 6. `engineer` — TDD Builder
Implements tasks from `plan.md` strictly under TDD (Red → Green → Refactor). Up to 4 engineers run concurrently on file-disjoint tasks within an execution group.
- **Constraints:** Strict scope; never commits (committing is strictly the Supervisor's responsibility).

#### 7. `auditor` — Quality Gatekeeper
Verifies implementation with static checks (cites `file:line`), runs builds and tests, and performs anti-shortcut detection (hunting TODOs, placeholders, and gutted tests).
- **Produces:** `plans/audit/AUDIT_[Plan_Name].md`.
- **Constraints:** Never fixes code; **NEVER runs git commit** (version control is strictly the Supervisor's responsibility).

#### 8. `visual-implementation-recap` — Visual Recap Generator
Additive renderer for the human commit gate. Reads `git diff`, `plan.md`, and audit report to generate `visual-recap.html` (9 surfaces). Never commits.

---

## How They Work Together (End-to-End Walkthrough)

1. **Phase 0 (Research):** `supervisor` initializes `state.json` and dispatches `research` → `plans/research/{topic}_context.md`. Transition: `phase: "0"` → `"1"`.
2. **Phase 1 (Spec):** `product-owner` runs Grill Loop and drafts `spec.md` + roadmap. Optional `spec-deliberator` enriches spec if asymmetry test passes. Transition: `phase: "1"` → `"1.gate"`.
3. **Phase 1.gate (Spec Gate):** `spec-validator` runs 3 disjoint lenses (`internal-consistency`, `missing-requirement`, `malicious-compliance`). Tightenings folded into spec. Transition: `phase: "1.gate"` → `"2"`.
4. **Phase 2 (Plan):** `architect` investigates code and writes `plan.md` with execution groups. Optional `plan-deliberator` decides trade-offs if asymmetry test passes. Transition: `phase: "2"` → `"2.gate"`.
5. **Phase 2.gate (Plan Gate):** `plan-validator` runs 3 disjoint lenses (`sequencing`, `ground-truth`, `blast-radius`), cites `file:line`, identifies first domino. Fixes applied to `plan.md`. Transition: `phase: "2.gate"` → `"3"`.
6. **Phase 3 (Human Review Gate):** `supervisor` sets `gates.plan-approval: "pending"` and stops for user review. User approves → `state.json` records approval; transition to `phase: "4"`.
7. **Phase 4 (Construction Loop):** For each execution group in `plan.md`:
   - `engineer` instances execute file-disjoint tasks in parallel under TDD.
   - `auditor` verifies tasks, runs build/tests, anti-shortcut scan → `AUDIT_[Plan_Name].md`.
   - `implementation-validator` runs 3 disjoint lenses on `git diff BASE..HEAD`, calibrating severity.
   - *(optional)* `visual-implementation-recap` renders `visual-recap.html`.
   - **Phase 4.gate (Commit Gate):** `supervisor` checks `git status`, drafts commit message, and stops for explicit user "yes". Upon confirmation, **`supervisor` runs `git commit`**, records commit SHA in `state.json#groups[].committed`, and advances to next group.
8. **Phase 5 (Release & Tag):** `supervisor` asks user to confirm release, tags git version (`git tag -a`), and `product-owner` marks milestone "Shipped" in `plans/00-ROADMAP.md`.

---

## Installation in `agy`

### Method 1: Recommended — Loose Global Agents
```bash
mkdir -p "$HOME/.gemini/config/agents"
for d in agents/*/; do
  name=$(basename "$d")
  rm -rf "$HOME/.gemini/config/agents/$name"
  cp -R "agents/$name" "$HOME/.gemini/config/agents/$name"
done
```

> [!IMPORTANT]
> Always copy entire directories (`cp -R`), not just `agent.md`. Visual agents bundle local `assets/` and `references/` directories that must remain co-located.

### Method 2: Project-Scoped Agents
```bash
mkdir -p ".agents/agents"
cp -R agents/* .agents/agents/
```
