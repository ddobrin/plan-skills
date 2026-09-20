# Plan Swarm Custom Subagents (v2)

A self-contained suite of **13 custom reasoning subagents** — role specialists, deliberative consensus panels, visual HTML renderers, and 3-lens adversarial validation gates — that drive a feature, bug fix, or refactor through a disciplined **spec → plan → execute → audit → commit** lifecycle.

This directory (`plugins/plan/agents/` and root `agents/`) packages the 13 standalone subagent definitions (`<agent-name>/agent.md`) for Jetski and Antigravity (`agy`), complementing the skills under [`plugins/plan/skills/`](../plugins/plan/skills/). All 13 subagents are strictly governed by the declarative contracts in [`plugins/plan/graph.json`](../plugins/plan/graph.json) (`plan-swarm@2.1`) and verified by `python3 plugins/plan/lib/graph/graph.py validate --agents-dir plugins/plan/agents`.

A single orchestrator subagent (`supervisor`) dispatches the role subagents in sequence, halts for human approval at defined gates, acts as the **sole committer**, and maintains the milestone state machine in [`plans/active_milestones/{moniker}/state.json`](#state-machine-specification-statejson--graphjson) — treating declarative JSON state and file paths, never chat summaries or directory-listing heuristics, as the single source of truth.

---

## The Subagent Families

| Family | Subagents (`13` Total) | Purpose |
|---|---|---|
| **Orchestrator & Sole Committer (`1`)** | `supervisor` | Owns the milestone state machine (`state.json`), dispatches all other subagents by file path, holds the human review and commit gates, and is the **only** subagent permitted to run `git commit`. |
| **Core Swarm Roles (`4`)** | `product-owner`, `architect`, `engineer`, `auditor` | Execute the primary engineering phases: Socratic Gherkin specification (`spec.md`), read-only codebase investigation & parallel group planning (`plan.md`), file-disjoint concurrent TDD implementation (`≤4` instances), and evidence-based `file:line` auditing (`AUDIT_[Plan_Name].md`). |
| **Self-Contained Visual Renderers (`3`)** | `visual-product-owner`, `visual-architect`, `visual-implementation-recap` | Produce zero-build, self-contained HTML review surfaces (`visual-spec.html`, `visual-plan.html`, `visual-recap.html`) using bundled local `assets/template.html` and `references/`. |
| **Deliberative Consensus Panels (`2`)** | `spec-deliberator`, `plan-deliberator` | Generative multi-delegate panels seeded with deliberately disjoint context bundles (`spec-deliberator`) or assigned investigation territories (`plan-deliberator`) that deliberate over bounded verbatim rounds (hard cap `4`) to converge on one revised artifact. |
| **Adversarial 3-Lens Validators (`3`)** | `spec-validator`, `plan-validator`, `implementation-validator` | Evaluative quorum gates that dispatch 3 independent skeptics across **3 disjoint evidence lenses**, retain findings confirmed by a **2-of-3 majority**, calibrate severity, identify the `first_domino`, and mandate explicit triage for every 1-vote finding. |

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

Jetski and Antigravity discover custom subagents as directories under `~/.gemini/config/agents/` (or `plugins/plan/agents/`), each named after the subagent and containing an `agent.md` file whose YAML frontmatter declares its `name`, `description`, and `tools`, and whose Markdown body defines its system prompt. All 13 subagents are completely self-contained:

```text
agents/
├── README.md                           # This documentation (v2)
├── supervisor/agent.md                 # Orchestrator, state.json owner & sole committer
├── product-owner/agent.md              # Phase 1: Socratic Gherkin spec writer & roadmap owner
├── visual-product-owner/               # Phase 1 (alt): Self-contained visual spec generator
│   ├── agent.md
│   ├── assets/template.html
│   ├── references/component-catalog.md
│   └── references/exemplar.md
├── spec-deliberator/agent.md           # Phase 1 (opt): 3-delegate disjoint-bundle spec consensus panel
├── spec-validator/agent.md             # Phase 1.gate: 3-lens adversarial spec validator
├── architect/agent.md                  # Phase 2: Read-only codebase investigator & parallel planner
├── visual-architect/                   # Phase 2 (alt): Self-contained visual plan generator
│   ├── agent.md
│   ├── assets/template.html
│   ├── references/component-catalog.md
│   └── references/exemplar.md
├── plan-deliberator/agent.md           # Phase 2 (opt): 3-territory assigned-investigation plan panel
├── plan-validator/agent.md             # Phase 2.gate: 3-lens codebase ground-truth & first-domino validator
├── engineer/agent.md                   # Phase 4: File-disjoint concurrent TDD builder (≤4 concurrent)
├── auditor/agent.md                    # Phase 4: Static/dynamic verifier & anti-shortcut gatekeeper
├── implementation-validator/agent.md   # Phase 4.gate: 3-lens diff validator & severity calibrator
└── visual-implementation-recap/        # Phase 4 (opt): Self-contained commit-gate visual recap renderer
    ├── agent.md
    ├── assets/template.html
    ├── references/component-catalog.md
    └── references/exemplar.md
```

> [!NOTE]
> The three **visual** subagents (`visual-product-owner`, `visual-architect`, `visual-implementation-recap`) bundle their HTML `assets/template.html` and `references/` inside their own subagent directories. They have zero external path dependencies (`${CLAUDE_PLUGIN_ROOT}` or external `skills/` paths are forbidden and checked by `graph.py validate-agents`).

---

## Comprehensive Explanation of All 13 Custom Subagents

### Summary Matrix (`graph.json` Contracts)

| # | Subagent Name | Phase | Node Kind | `reads` | `writes` | `must_not_write` |
|---|---|---|---|---|---|---|
| 1 | [`supervisor`](#1-supervisor--orchestrator-state-machine-owner--sole-committer) | `0`–`5` | Orchestrator (`starter`) | `state.json`, `00-ROADMAP.md`, all milestone artifacts, `git status/diff` | `state.json`, `git commit`, `git tag` | `<repo source>` (never codes directly) |
| 2 | [`product-owner`](#2-product-owner--socratic-spec-author--roadmap-guardian) | `1`, `5` | `role` | `plans/research/*.md`, `plans/00-ROADMAP.md` | `plans/00-ROADMAP.md`, `context.md`, `spec.md` | `<repo source>`, `git commit` |
| 3 | [`visual-product-owner`](#3-visual-product-owner--spec-author--interactive-html-spec-renderer) | `1` | `role` + `renderer` | `plans/research/*.md`, `plans/00-ROADMAP.md`, local `assets/template.html` | `plans/00-ROADMAP.md`, `context.md`, `spec.md`, `visual-spec.html` | `<repo source>`, `git commit` |
| 4 | [`spec-deliberator`](#4-spec-deliberator--3-delegate-disjoint-context-spec-consensus-panel) | `1` (opt) | `deliberation` | `spec.md`, `context.md`, disjoint stakeholder bundles | `spec.md`, `deliberations/spec-deliberation.md` | `<repo source>`, `git commit` |
| 5 | [`spec-validator`](#5-spec-validator--3-lens-adversarial-specification-gate) | `1.gate` | `panel` (`n=3`) | `spec.md`, `context.md` | `adversarial-reviews/spec-validation.md` | `spec.md`, `<repo source>`, `git commit` |
| 6 | [`architect`](#6-architect--read-only-codebase-investigator--technical-planner) | `2` | `role` | `spec.md`, `<repo>` | `plan.md`, `data-model.md`, `api-contracts.md` | `<repo source>`, `git commit` |
| 7 | [`visual-architect`](#7-visual-architect--technical-planner--interactive-html-plan-renderer) | `2` | `role` + `renderer` | `spec.md`, `<repo>`, local `assets/template.html` | `plan.md`, `data-model.md`, `api-contracts.md`, `visual-plan.html` | `<repo source>`, `git commit` |
| 8 | [`plan-deliberator`](#8-plan-deliberator--3-territory-assigned-investigation-plan-panel) | `2` (opt) | `deliberation` | `plan.md`, `spec.md`, `<repo>` (by territory) | `plan.md`, `deliberations/plan-deliberation.md` | `<repo source>`, `git commit` |
| 9 | [`plan-validator`](#9-plan-validator--3-lens-codebase-ground-truth--first-domino-gate) | `2.gate` | `panel` (`n=3`) | `plan.md`, `<repo>` | `adversarial-reviews/plan-validation.md` | `plan.md`, `<repo source>`, `git commit` |
| 10 | [`engineer`](#10-engineer--file-disjoint-concurrent-tdd-builder) | `4` | `role` (`fanout ≤ 4`) | `plan.md`, `<repo>` | `<repo source>`, `plan.md#todos` | `git commit` |
| 11 | [`auditor`](#11-auditor--evidence-based-quality--anti-shortcut-gatekeeper) | `4` | `role` | `plan.md`, `spec.md`, `<repo>` | `plans/audit/AUDIT_[Plan_Name].md` | `<repo source>`, `git commit` |
| 12 | [`implementation-validator`](#12-implementation-validator--3-lens-adversarial-diff-gate--severity-calibrator) | `4.gate` | `panel` (`n=3`) | `<repo>`, `git diff BASE..HEAD` | `adversarial-reviews/implementation-validation.md` | `<repo source>`, `git commit` |
| 13 | [`visual-implementation-recap`](#13-visual-implementation-recap--commit-gate-html-recap-renderer) | `4` (opt) | `renderer` | `git diff`, `plan.md`, `AUDIT_[Plan_Name].md`, local `assets/template.html` | `visual-recap.html` | `<repo source>`, `git commit` |

---

### Detailed Subagent Breakdown

#### 1. `supervisor` — Orchestrator, State Machine Owner & Sole Committer
- **File:** [`supervisor/agent.md`](supervisor/agent.md)
- **Lifecycle Role:** Master state-machine controller corresponding to `starter` in `graph.json`. Holds all human-facing gates (`human-review-gate` at Phase 3, `commit-gate` at Phase 4, and `release` at Phase 5).
- **Core Responsibilities:**
  1. **Exclusive `state.json` Writer:** Creates `plans/active_milestones/{moniker}/state.json` at milestone initialization and updates it at every phase transition, gate verdict, and node completion. Resumes interrupted milestones by reading `state.json`, never by guessing from directory listings.
  2. **File-Path Dispatch:** Invokes downstream subagents (`product-owner`, `architect`, `engineer`, `auditor`, validators, deliberators) by passing exact workspace file paths (`plans/active_milestones/{moniker}/...`), never prose summaries.
  3. **Human Gate Enforcement:** Stops unconditionally at Phase 3 (`plan-approval`) until the user types `"approve"`, and at Phase 4.gate (`commit`) after each execution group until the user types `"yes"`.
  4. **Sole Committer Invariant:** `supervisor` is the **only** subagent in the swarm permitted to execute `git commit` and `git tag`, and only when both a green `AUDIT_[Plan_Name].md` (`PASS`) and explicit user confirmation (`"yes"`) are present.

---

#### 2. `product-owner` — Socratic Spec Author & Roadmap Guardian
- **File:** [`product-owner/agent.md`](product-owner/agent.md)
- **Phase & Node Kind:** Phase `1` (and Phase `5` release status update) · `kind: "role"` · `dispatched_by: "starter"`.
- **Core Responsibilities:**
  1. **The Socratic "Grill Loop":** Interrogates raw feature requests (asking at most 3 high-leverage questions per turn) to surface unstated edge cases, rate limits, failure states, permissions, and UX boundaries before writing a single requirement.
  2. **Testable Gherkin Specification:** Writes `plans/active_milestones/{moniker}/spec.md` containing unambiguous User Stories and `Given / When / Then` acceptance criteria covering happy paths, boundary conditions, and error states.
  3. **Roadmap Ownership:** Maintains `plans/00-ROADMAP.md`, registering new milestones as `Active` in Phase 1 and marking them `Shipped` in Phase 5.
- **Strict Boundaries:** Defines *what* and *why*, never *how*. Writes no source code and no technical implementation plans; never commits.

---

#### 3. `visual-product-owner` — Spec Author + Interactive HTML Spec Renderer
- **Files:** [`visual-product-owner/agent.md`](visual-product-owner/agent.md), [`assets/template.html`](visual-product-owner/assets/template.html), [`references/component-catalog.md`](visual-product-owner/references/component-catalog.md), [`references/exemplar.md`](visual-product-owner/references/exemplar.md)
- **Phase & Node Kind:** Phase `1` · Drop-in `alternatives` replacement for `product-owner`.
- **Core Responsibilities:**
  1. Performs 100% of `product-owner`'s duties (runs the Grill Loop, updates `plans/00-ROADMAP.md`, and emits a machine-readable `plans/active_milestones/{moniker}/spec.md` consumed unchanged by `spec-validator` and `architect`).
  2. **Renders `visual-spec.html`:** Instantiates its bundled `assets/template.html` to produce a zero-build, self-contained HTML review surface (`plans/active_milestones/{moniker}/visual-spec.html`) featuring 8 spec-native views: Overview, User-Story Cards, Color-Coded Given/When/Then Criteria, Mermaid User-Flow Diagrams, Edge Cases & Constraints, Wireframes/Prototype, Open Questions, and Author Callouts.
- **Strict Boundaries:** `spec.md` remains authoritative if `visual-spec.html` ever diverges; never exposes code/architecture internals; never commits.

---

#### 4. `spec-deliberator` — 3-Delegate Disjoint-Context Spec Consensus Panel
- **File:** [`spec-deliberator/agent.md`](spec-deliberator/agent.md)
- **Phase & Node Kind:** Phase `1` (Optional, runs after `product-owner` and before `spec-validator`) · `kind: "deliberation"`.
- **Core Responsibilities:**
  1. **Mandatory Asymmetry Precondition:** Before spawning delegates, verifies that the spec depends on knowledge siloed across distinct domains (`product`, `engineering`, `ops/security`) and names ≥1 private fact per bundle that could alter the spec. **If all context fits in a single prompt or is mergeable, `spec-deliberator` refuses deliberation**, records `status: "skipped"` (`reason: "asymmetry test failed — context was mergeable"`), and exits so the spec is revised centrally.
  2. **Bounded Verbatim Relay (Max 4 Rounds):** Dispatches 3 delegates with disjoint private bundles, relays their disclosures and proposed edits **verbatim** across up to 4 rounds, and requires **earned acceptance** (every accepting delegate must state its `acceptance_basis`).
  3. **Artifacts:** Writes the consensus-revised `spec.md` and the full audit trail to `plans/active_milestones/{moniker}/deliberations/spec-deliberation.md`.

---

#### 5. `spec-validator` — 3-Lens Adversarial Specification Gate
- **File:** [`spec-validator/agent.md`](spec-validator/agent.md)
- **Phase & Node Kind:** Phase `1.gate` · `kind: "panel"` (`n = 3`, `gate = "majority"`, `blocks = "architect"`).
- **Core Responsibilities:**
  1. **Disjoint 3-Lens Partition:** Dispatches 3 parallel skeptic subagents with non-overlapping reading assignments and default-to-reject postures:
     - **Lens 1 (`internal-consistency`):** Reads `spec.md` against itself twice to catch `ambiguity`, `contradiction`, and terminology drift.
     - **Lens 2 (`missing-requirement`):** Reads `context.md` and `00-ROADMAP.md` first to catch missing error handling, empty/oversized inputs, concurrency races, auth/permissions, units, and time zones.
     - **Lens 3 (`malicious-compliance`):** Reads the Gherkin acceptance criteria in isolation (ignoring prose intent) and constructs the laziest useless implementation that technically passes every `Given/When/Then` clause (`malicious-compliance`, `untestable`).
  2. **Quorum Tally & Single-Vote Triage:** Deduplicates findings by stable kebab-case `id`, retains findings confirmed by a **2-of-3 majority** (each carrying a concrete `tightening`), tracks `cross_lens` corroboration, and mandates explicit triage (`fold-in` or `defer`) for every 1-vote finding.
  3. **Artifact:** Writes `plans/active_milestones/{moniker}/adversarial-reviews/spec-validation.md`. Any confirmed finding routes back to `product-owner` (`when: "confirmed findings"`).

---

#### 6. `architect` — Read-Only Codebase Investigator & Technical Planner
- **File:** [`architect/agent.md`](architect/agent.md)
- **Phase & Node Kind:** Phase `2` · `kind: "role"` · `must_not_write: ["<repo source>"]`.
- **Core Responsibilities:**
  1. **Read-Only Codebase Grounding:** Deep-reads the repository (`<repo>`) and `spec.md` to verify exact file paths, class/function signatures, database schemas, and existing test harnesses before designing a single step.
  2. **Parallel Execution Groups (`plan.md`):** Authors `plans/active_milestones/{moniker}/plan.md` (plus optional `data-model.md` and `api-contracts.md`), organizing tasks into sequential **Execution Groups** (`Group 1`, `Group 2`, ...) where tasks inside the same group (`1.A`, `1.B`, ...) touch **strictly disjoint file sets** so up to 4 `engineer` subagents can execute them in parallel without merge conflicts.
  3. **Test-First Safety Harness:** Embeds characterization tests (for legacy code) and Red → Green → Refactor micro-steps with exact runnable verification commands into every task.
- **Strict Boundaries:** Never modifies repository source code (`<repo source>`); never commits.

---

#### 7. `visual-architect` — Technical Planner + Interactive HTML Plan Renderer
- **Files:** [`visual-architect/agent.md`](visual-architect/agent.md), [`assets/template.html`](visual-architect/assets/template.html), [`references/component-catalog.md`](visual-architect/references/component-catalog.md), [`references/exemplar.md`](visual-architect/references/exemplar.md)
- **Phase & Node Kind:** Phase `2` · Drop-in `alternatives` replacement for `architect`.
- **Core Responsibilities:**
  1. Executes 100% of `architect`'s read-only investigation and produces the identical machine-readable `plans/active_milestones/{moniker}/plan.md` (plus optional `data-model.md` / `api-contracts.md`).
  2. **Renders `visual-plan.html`:** Instantiates its bundled `assets/template.html` to emit `plans/active_milestones/{moniker}/visual-plan.html` with 9 interactive review surfaces: Overview, Mermaid Architecture Diagrams, File Map, Annotated Code Snippets, OpenAPI-Style API Cards, Schema Map, Wireframes, Open Questions, and Author Comments.
- **Strict Boundaries:** `plan.md` wins if `visual-plan.html` ever disagrees; strictly read-only on `<repo source>`; never commits.

---

#### 8. `plan-deliberator` — 3-Territory Assigned-Investigation Plan Panel
- **File:** [`plan-deliberator/agent.md`](plan-deliberator/agent.md)
- **Phase & Node Kind:** Phase `2` (Optional, runs after `architect` and before `plan-validator`) · `kind: "deliberation"`.
- **Core Responsibilities:**
  1. **Territory Asymmetry Precondition:** Assigns 3 delegates to non-overlapping investigation territories:
     - **Delegate 1 (`intent`):** Deep-reads `spec.md` and user-facing invariants.
     - **Delegate 2 (`codebase`):** Deep-reads the affected source subsystems (`<repo>`).
     - **Delegate 3 (`delivery`):** Deep-reads test suites, CI pipelines, migrations, feature flags, and rollback paths.
     If the codebase/plan is small enough for one context window to hold whole, `plan-deliberator` **refuses deliberation** (`status: "skipped"`, `reason: "asymmetry test failed — context was mergeable"`).
  2. **Trade-Off Resolution (Max 4 Rounds):** Relays turns verbatim across up to 4 rounds so delegates negotiate concrete trade-offs (migration strategy, execution-group boundaries, interface contracts) with cited evidence (`file:line`, spec clause, CI command) and earned `acceptance_basis`.
  3. **Artifacts:** Writes the jointly revised `plan.md` and `plans/active_milestones/{moniker}/deliberations/plan-deliberation.md`.

---

#### 9. `plan-validator` — 3-Lens Codebase Ground-Truth & First-Domino Gate
- **File:** [`plan-validator/agent.md`](plan-validator/agent.md)
- **Phase & Node Kind:** Phase `2.gate` · `kind: "panel"` (`n = 3`, `gate = "majority"`, `blocks = "human-review-gate"`).
- **Core Responsibilities:**
  1. **Disjoint 3-Lens Codebase Attack:** Dispatches 3 parallel skeptics that assume `plan.md` will fail and check it against the real repository:
     - **Lens 1 (`sequencing`):** Analyzes the step dependency graph and execution group boundaries before opening source files (`ordering` defects, step `k` depending on an artifact created in step `k+2`, parallel tasks in the same group touching the same file).
     - **Lens 2 (`ground-truth`):** Opens every source file named in `plan.md` and checks that every referenced function, class, parameter, table, and import actually exists with the assumed signature (`false-assumption`; **must cite exact `file:line`**).
     - **Lens 3 (`blast-radius`):** Searches outside the files listed in `plan.md` for callers, subclasses, serializers, tests, and CI jobs broken by the planned changes (`unverifiable`, `no-rollback`, `missing-migration`, `hidden-coupling`).
  2. **First Domino Nomination:** Identifies `first_domino` — the earliest step in `plan.md` whose failure invalidates downstream steps — so `architect` repairs the root ordering flaw first.
  3. **Artifact:** Writes `plans/active_milestones/{moniker}/adversarial-reviews/plan-validation.md`. Confirmed findings block `human-review-gate` and route back to `architect`.

---

#### 10. `engineer` — File-Disjoint Concurrent TDD Builder
- **File:** [`engineer/agent.md`](engineer/agent.md)
- **Phase & Node Kind:** Phase `4` · `kind: "role"` · `fanout: { over: "execution group tasks", max_concurrent: 4, disjoint: "files" }`.
- **Core Responsibilities:**
  1. **Strict TDD Execution (Red → Green → Refactor):** Implements an assigned task (e.g., `Task 1.A`) from an approved `plan.md` one micro-step at a time. Writes a failing test (or a characterization test when touching untested legacy code), writes the minimal code to pass, and refactors while keeping the build green.
  2. **Progress Tracking:** Checks off completed task checkboxes directly in `plans/active_milestones/{moniker}/plan.md#todos`.
- **Strict Boundaries:** Only role (alongside optional `simplifier`) permitted to write `<repo source>`. Never expands scope beyond the assigned task; never leaves a failing build; **never runs `git commit`** (`must_not_write: ["git commit"]`).

---

#### 11. `auditor` — Evidence-Based Quality & Anti-Shortcut Gatekeeper
- **File:** [`auditor/agent.md`](auditor/agent.md)
- **Phase & Node Kind:** Phase `4` · `kind: "role"` · `must_not_write: ["<repo source>", "git commit"]`.
- **Core Responsibilities:**
  1. **Static Verification with Citations:** Inspects every step in the active execution group of `plan.md` and every acceptance criterion in `spec.md` against the actual implementation, citing exact `file:line` evidence.
  2. **Dynamic Build & Test Execution:** Runs the project's build and test commands and captures verbatim exit codes and output.
  3. **Anti-Shortcut Hunting:** Scans modified files for `TODO`, `FIXME`, `HACK`, stub/placeholder bodies, skipped or gutted tests (`@skip`, `.only`, weakened assertions), and hardcoded return values that fake a passing test.
  4. **Routing Verdict (`AUDIT_[Plan_Name].md`):** Writes `plans/audit/AUDIT_[Plan_Name].md` with verdict `PASS` or `FAIL`:
     - `PASS` → advances to `implementation-validator`.
     - `FAIL` due to implementation bug/shortcut → routes to `engineer` (`when: "code failure"`).
     - `FAIL` because a planned step is impossible against the real architecture → routes to `architect` (`when: "plan failure"`).
- **Strict Boundaries:** Never edits `<repo source>` to fix bugs itself; **explicitly prohibited from running `git commit`**.

---

#### 12. `implementation-validator` — 3-Lens Adversarial Diff Gate & Severity Calibrator
- **File:** [`implementation-validator/agent.md`](implementation-validator/agent.md)
- **Phase & Node Kind:** Phase `4.gate` · `kind: "panel"` (`n = 3`, `gate = "majority"`, `blocks = "commit-gate"`).
- **Core Responsibilities:**
  1. **Disjoint 3-Lens Diff Attack (`git diff BASE..HEAD`):**
     - **Lens 1 (`claim-vs-reality`):** Reads the task/plan claims first, then inspects `git diff BASE..HEAD` line by line to catch `claim-mismatch` and unrequested scope creep.
     - **Lens 2 (`failure-paths`):** Inspects error branches, exception handling, early returns, timeouts, null guards, and test assertions for `failure-path` and `edge-case` defects.
     - **Lens 3 (`blast-radius`):** Reads untouched callers, downstream consumers, concurrency primitives, and resource lifecycles for `concurrency`, `resource`, and `regression` defects.
  2. **Severity Calibration:** Evaluates raw skeptic severities against actual exploitability/reachability in the codebase and outputs a **Severity Calibration Table** (`raw_severity` → `calibrated_severity` with rationale) so engineers fix real defects at their true priority.
  3. **Artifact:** Writes `plans/active_milestones/{moniker}/adversarial-reviews/implementation-validation.md`. Confirmed defects route back to `engineer` (`when: "confirmed defects"`).

---

#### 13. `visual-implementation-recap` — Commit-Gate HTML Recap Renderer
- **Files:** [`visual-implementation-recap/agent.md`](visual-implementation-recap/agent.md), [`assets/template.html`](visual-implementation-recap/assets/template.html), [`references/component-catalog.md`](visual-implementation-recap/references/component-catalog.md), [`references/exemplar.md`](visual-implementation-recap/references/exemplar.md)
- **Phase & Node Kind:** Phase `4` (Optional, runs after green `auditor` and clean `implementation-validator`, before `commit-gate`) · `kind: "renderer"`.
- **Core Responsibilities:**
  1. **True-by-Construction Diff & Audit Synthesis:** Reads the real `git diff`, `plan.md`, and `plans/audit/AUDIT_[Plan_Name].md` and instantiates its bundled `assets/template.html` to produce `plans/active_milestones/{moniker}/visual-recap.html`.
  2. **Nine Commit-Gate Surfaces:** Renders Outcome + Metrics, Completed Tasks, Changed-Files Tree with Diffstat, Annotated CSS Diffs (with secret redaction), Architecture Delta, API & Schema Changes, Before/After UI, Audit Verdict with `file:line` Evidence, and Reviewer Notes.
- **Strict Boundaries:** Purely additive — never replaces `auditor`, `implementation-validator`, or human commit approval; strictly read-only on `<repo source>`; **never runs `git commit`**.

---

## Installation (`~/.gemini/config`)

Use the unified installer in [`scripts/install-all.sh`](../scripts/install-all.sh) (or `scripts/install-agents.sh`) to install all 13 subagents into `~/.gemini/config/agents` and validate them against `graph.json`:

```bash
# Install plugins/plan (skills + bundled agents) and ~/.gemini/config/agents
./scripts/install-all.sh

# Or install only the 13 custom subagents into ~/.gemini/config/agents
./scripts/install-agents.sh
```

> [!IMPORTANT]
> Always copy complete subagent directories (`cp -R`), never bare `agent.md` files alone, so the visual subagents (`visual-product-owner`, `visual-architect`, `visual-implementation-recap`) retain their co-located `assets/template.html` and `references/` directories.

---

## State Machine Specification (`state.json` & `graph.json`)

The 13 custom subagents coordinate through two JSON specifications:
1. **`plans/active_milestones/{moniker}/state.json`** — the **runtime milestone state machine** written exclusively by `supervisor` (`starter`) and read by all other subagents.
2. **`plugins/plan/graph.json`** — the **declarative topology and contract schema** defining the 16 nodes, 25 transitions (`edges`), 2 human gates (`gates`), 3-lens panel partitions (`panel`), concurrency limits (`fanout`), and 5 architectural invariants.

### 1. Runtime Milestone State Machine (`plans/active_milestones/{moniker}/state.json`)

#### Complete Annotated `state.json` Payload

```json
{
  "graph_version": "plan-swarm@2.1",
  "run_id": "ms_checkout-redesign_0c41",
  "moniker": "checkout-redesign",
  "phase": "4.gate",
  "updated": "2026-09-20T16:30:00Z",

  "gates": [
    {
      "id": "plan-approval",
      "state": "approved"
    },
    {
      "id": "commit",
      "state": "pending"
    }
  ],

  "nodes": {
    "research": {
      "status": "done",
      "artifact": "plans/research/checkout_context.md"
    },
    "product-owner": {
      "status": "done",
      "artifact": "plans/active_milestones/checkout-redesign/spec.md"
    },
    "spec-deliberator": {
      "status": "skipped",
      "reason": "asymmetry test failed — context was mergeable into single prompt"
    },
    "spec-validator": {
      "status": "passed",
      "report": "plans/active_milestones/checkout-redesign/adversarial-reviews/spec-validation.md",
      "lenses": [
        "internal-consistency",
        "missing-requirement",
        "malicious-compliance"
      ],
      "confirmed": 0,
      "single_vote": 2,
      "cross_lens": 0,
      "single_vote_triaged": true
    },
    "architect": {
      "status": "done",
      "artifact": "plans/active_milestones/checkout-redesign/plan.md"
    },
    "plan-deliberator": {
      "status": "done",
      "artifact": "plans/active_milestones/checkout-redesign/deliberations/plan-deliberation.md"
    },
    "plan-validator": {
      "status": "passed",
      "report": "plans/active_milestones/checkout-redesign/adversarial-reviews/plan-validation.md",
      "lenses": [
        "sequencing",
        "ground-truth",
        "blast-radius"
      ],
      "confirmed": 0,
      "single_vote": 1,
      "cross_lens": 0,
      "first_domino": null,
      "single_vote_triaged": true
    },
    "engineer": {
      "status": "done",
      "artifact": "plans/active_milestones/checkout-redesign/plan.md#todos"
    },
    "simplifier": {
      "status": "skipped",
      "reason": "no high-complexity nesting introduced in group 1"
    },
    "auditor": {
      "status": "passed",
      "artifact": "plans/audit/AUDIT_checkout-redesign.md"
    },
    "implementation-validator": {
      "status": "passed",
      "report": "plans/active_milestones/checkout-redesign/adversarial-reviews/implementation-validation.md",
      "lenses": [
        "claim-vs-reality",
        "failure-paths",
        "blast-radius"
      ],
      "confirmed": 0,
      "single_vote": 1,
      "cross_lens": 0,
      "single_vote_triaged": true
    },
    "visual-implementation-recap": {
      "status": "done",
      "artifact": "plans/active_milestones/checkout-redesign/visual-recap.html"
    }
  },

  "groups": [
    {
      "id": "1",
      "tasks": {
        "1.A": "done",
        "1.B": "done"
      },
      "audit": "passed",
      "audit_rounds": 1,
      "implementation_validation": "plans/active_milestones/checkout-redesign/adversarial-reviews/implementation-validation.md",
      "committed": "a3f19c2"
    },
    {
      "id": "2",
      "tasks": {
        "2.A": "done",
        "2.B": "done"
      },
      "audit": "passed",
      "audit_rounds": 2,
      "implementation_validation": "plans/active_milestones/checkout-redesign/adversarial-reviews/implementation-validation-r2.md",
      "committed": null
    }
  ]
}
```

---

#### Meaning of Every Field in `state.json`

##### A. Top-Level Milestone Metadata Fields

| Field | Type | Allowed Values / Format | Meaning & Subagent Contract |
|---|---|---|---|
| `graph_version` | `string` | `"plan-swarm@2.1"` | Version of `plugins/plan/graph.json` under which this milestone run was initialized. `supervisor` verifies this matches `graph.json` before resuming; a mismatch indicates the swarm's topology changed mid-milestone and requires user confirmation. |
| `run_id` | `string` | `"ms_{moniker}_{short_hash}"` | Immutable identifier for the milestone run. Stamped onto validator and deliberator reports so every artifact can be traced to the exact state-machine execution that produced it. |
| `moniker` | `string` | Kebab-case slug (e.g. `"checkout-redesign"`) | Folder name under `plans/active_milestones/{moniker}/` containing all artifacts for this milestone. |
| `phase` | `string` | `"0"` \| `"1"` \| `"1.gate"` \| `"2"` \| `"2.gate"` \| `"3"` \| `"4"` \| `"4.gate"` \| `"5"` | Active stage of the milestone:<br>• `"0"` — Phase 0 codebase context discovery (`research`).<br>• `"1"` — Phase 1 specification authoring (`product-owner` / `visual-product-owner` and optional `spec-deliberator`).<br>• `"1.gate"` — Phase 1 adversarial validation (`spec-validator`) or tightening cycle.<br>• `"2"` — Phase 2 technical planning (`architect` / `visual-architect` and optional `plan-deliberator`).<br>• `"2.gate"` — Phase 2 adversarial validation (`plan-validator`) or `first_domino` remediation cycle.<br>• `"3"` — Stopped at `human-review-gate` awaiting explicit user `"approve"` on `spec.md` and `plan.md`.<br>• `"4"` — Phase 4 TDD construction (`engineer`), audit (`auditor`), and diff validation (`implementation-validator`) for the current execution group.<br>• `"4.gate"` — Stopped at `commit-gate` after a green audit + clean diff validation, awaiting explicit user `"yes"` before `supervisor` runs `git commit`.<br>• `"5"` — All groups committed; tagging release and updating `plans/00-ROADMAP.md` to `Shipped`. |
| `updated` | `string` | ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`) | Timestamp of the last `state.json` mutation written by `supervisor`. |

##### B. Human Gate Fields (`gates[]`)

| Field | Type | Allowed Values | Meaning & Subagent Contract |
|---|---|---|---|
| `gates[].id` | `string` | `"plan-approval"` \| `"commit"` | Identifies the human gate declared in `graph.json`:<br>• `"plan-approval"` (`node: "human-review-gate"`, Phase 3, `irreversible: false`) gates transition from planning (`Phase 2.gate`) to code execution (`Phase 4`).<br>• `"commit"` (`node: "commit-gate"`, Phase 4.gate, `irreversible: true`, `per: "execution group"`) gates every `git commit` execution by `supervisor`. |
| `gates[].state` | `string` | `"not-reached"` \| `"pending"` \| `"approved"` \| `"rejected"` | Current gate status:<br>• `"not-reached"` — prerequisite validator panel has not yet passed.<br>• `"pending"` — `supervisor` has presented the artifacts/diff to the user and halted execution.<br>• `"approved"` — user explicitly responded `"approve"` (Phase 3) or `"yes"` (Phase 4 commit).<br>• `"rejected"` — user requested revisions, routing back to `product-owner`, `architect`, or `engineer`. |

##### C. Per-Node Status & Validator Panel Fields (`nodes.{node_id}`)

| Field | Type | Applies To | Meaning & Subagent Contract |
|---|---|---|---|
| `nodes.{id}.status` | `string` | All nodes | Current execution state of node `{id}`:<br>• `"pending"` — not yet invoked.<br>• `"running"` — subagent currently active.<br>• `"done"` — role, deliberator, or visual renderer completed its output file.<br>• `"passed"` — `auditor` or validator panel completed with zero confirmed blocking findings.<br>• `"findings"` — validator panel (`spec-validator`, `plan-validator`, `implementation-validator`) produced `confirmed > 0` findings, triggering a feedback cycle.<br>• `"skipped"` — optional node (`spec-deliberator`, `plan-deliberator`, `simplifier`, `visual-implementation-recap`) was bypassed; **must include `reason`**.<br>• `"failed"` — unexpected execution error or failed audit.<br>• `"unknown"` — honest indicator when state cannot be verified; never treated as `"passed"`. |
| `nodes.{id}.artifact` | `string` | Role, deliberation & renderer nodes | Path to the primary output file written by the subagent (`spec.md`, `plan.md`, `visual-plan.html`, `AUDIT_[Plan_Name].md`, etc.). |
| `nodes.{id}.reason` | `string` | Any node with `status == "skipped"` | **Mandatory** explanation when a node is skipped (for example, `"asymmetry test failed — context was mergeable"` when `spec-deliberator` or `plan-deliberator` refuses deliberation). |
| `nodes.{id}.report` | `string` | Validator panels (`spec-validator`, `plan-validator`, `implementation-validator`) | Path to the generated Markdown review report in `plans/active_milestones/{moniker}/adversarial-reviews/`. |
| `nodes.{id}.lenses` | `array<string>` | Validator panels | Exact 3-element array of disjoint evidence lenses dispatched by the validator (`["internal-consistency", "missing-requirement", "malicious-compliance"]`, `["sequencing", "ground-truth", "blast-radius"]`, or `["claim-vs-reality", "failure-paths", "blast-radius"]`). Proves the panel did not run correlated identical prompts. |
| `nodes.{id}.confirmed` | `integer` | Validator panels | Number of deduplicated findings confirmed by ≥2 of 3 skeptic lenses. `confirmed > 0` blocks the gate and routes along the `when: "confirmed findings"` / `"confirmed defects"` feedback edge. |
| `nodes.{id}.single_vote` | `integer` | Validator panels | Number of findings reported by only 1 of 3 lenses. Kept in the report's **Single-Vote Findings (triage required)** section. |
| `nodes.{id}.cross_lens` | `integer` | Validator panels | Number of confirmed findings reached independently by **≥2 distinct lenses** from disjoint reading assignments — the primary metric of independent corroboration. |
| `nodes.{id}.first_domino` | `string \| null` | `plan-validator` | ID or step identifier of the earliest step in `plan.md` whose failure invalidates subsequent steps (`null` when `confirmed == 0`). |
| `nodes.{id}.single_vote_triaged` | `boolean` | Validator panels | `true` once every single-vote finding (`single_vote > 0`) has been explicitly triaged (`fold-in` or `defer` with rationale). Required before advancing past the gate. |

##### D. Execution Group Fields (`groups[]`)

| Field | Type | Allowed Values / Format | Meaning & Subagent Contract |
|---|---|---|---|
| `groups[].id` | `string` | `"1"`, `"2"`, ... | Sequential execution group number from `plan.md`. Group `k` must be audited, validated, and committed (`committed != null`) before Group `k+1` is dispatched. |
| `groups[].tasks` | `object<string, string>` | `{ "1.A": "pending" \| "running" \| "done" \| "failed" }` | Per-task status map within the group. Tasks within a group touch disjoint files and are dispatched across up to 4 concurrent `engineer` subagents. |
| `groups[].audit` | `string` | `"not-reached"` \| `"passed"` \| `"failed"` | Result of `auditor`'s verification (`AUDIT_[Plan_Name].md`) for this execution group. |
| `groups[].audit_rounds` | `integer` | `0`..`3` (hard cap `3`) | Count of `engineer ⇄ auditor` repair iterations for this group. Reaching `3` without `"passed"` forces `supervisor` to halt and escalate to the user. |
| `groups[].implementation_validation` | `string \| null` | Path to `adversarial-reviews/implementation-validation*.md` | Path to `implementation-validator`'s 3-lens review report for this group's diff. |
| `groups[].committed` | `string \| null` | Git commit SHA (e.g. `"a3f19c2"`) or `null` | Written exclusively by `supervisor` after running `git commit` following a green audit, clean `implementation-validator`, and explicit user `"yes"` at `commit-gate`. |

---

### 2. Declarative State Machine Schema (`plugins/plan/graph.json`)

[`plugins/plan/graph.json`](../plugins/plan/graph.json) is the static schema validated by `python3 plugins/plan/lib/graph/graph.py validate --agents-dir plugins/plan/agents`:

| Field in `graph.json` | Type | Meaning & Validation Contract |
|---|---|---|
| `graph_version` | `string` | Topology version (`"plan-swarm@2.1"`), embedded in `state.json` and all generated README lifecycle blocks. |
| `state_file` | `string` | Canonical path pattern (`"plans/active_milestones/{moniker}/state.json"`) for milestone runtime state. |
| `node_kinds` | `object` | Defines the 7 node categories: `entry`, `role`, `panel`, `deliberation`, `human-gate`, `renderer`, and `terminal`. |
| `nodes[].id` | `string` | Unique node ID (`request`, `research`, `product-owner`, `spec-deliberator`, `spec-validator`, `architect`, `plan-deliberator`, `plan-validator`, `human-review-gate`, `engineer`, `simplifier`, `auditor`, `implementation-validator`, `visual-implementation-recap`, `commit-gate`, `release`). |
| `nodes[].kind` & `phase` | `string` | Node archetype (`node_kinds` key) and lifecycle phase (`"0"`–`"5"`). |
| `nodes[].skill` & `agent` | `string` | Binds the node to `skills/<skill>/SKILL.md` and `agents/<agent>/agent.md`. Verified on disk by `graph.py validate`. |
| `nodes[].alternatives` | `array<string>` | Drop-in visual replacement subagents/skills (`visual-product-owner` for `product-owner`, `visual-architect` for `architect`). |
| `nodes[].dispatched_by` / `held_by` | `string` | Declares whether the node is invoked as a subagent by `"starter"` (`supervisor`) or held directly in the user conversation by `"starter"`. |
| `nodes[].blocks` | `string` | Target node blocked until a `panel` node passes (`architect`, `human-review-gate`, or `commit-gate`). |
| `nodes[].panel` | `object` | On `kind: "panel"` nodes: `n` (`3`), `gate` (`"majority"`), `prompt_file`, `lenses` (3 disjoint lens names), and `asymmetry` (reading assignment partition). Checked against each validator's `agent.md` and `prompt_file`. |
| `nodes[].fanout` | `object` | On `engineer`: `{"over": "execution group tasks", "max_concurrent": 4, "disjoint": "files"}`. |
| `nodes[].reads` / `writes` / `must_not_write` | `array<string>` | Strict I/O and side-effect contracts enforced by `graph.py validate` (e.g. `auditor` and `architect` have `must_not_write: ["<repo source>"]`; `engineer` and `auditor` have `must_not_write: ["git commit"]`). |
| `edges[]` | `array<object>` | Directed transitions (`from`, `to`, `when`, optional `label`) defining both forward progression and feedback loops. |
| `gates[]` | `array<object>` | Human approval gate definitions (`id`, `node`, `irreversible`, `per`, `prompt`). |
| `invariants[]` | `array<string>` | The 5 core invariants enforced across skills and subagents (`starter`/`supervisor` sole committer, `engineer`/`simplifier` sole source writers, 3 disjoint lenses per validator panel, human gates require interactive user turn, and file-path-only subagent dispatch). |
