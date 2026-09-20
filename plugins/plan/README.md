# `plan` Plugin — Spec-Driven Planning Swarm (v2)

A self-contained swarm of role-based skills, 13 bundled custom subagents, deliberative panels, and adversarial 3-lens validation gates that drive a feature, bug fix, or refactor through a disciplined **spec → plan → execute → audit → commit** lifecycle.

These skills are designed to operate as a coordinated state machine. A single orchestrator (`starter` / `plan-swarm`) dispatches the role agents in sequence, stops for human approval at defined gates, and treats files under `plans/` — specifically `plans/active_milestones/{moniker}/state.json`, not chat history or directory-listing heuristics — as the single source of truth. Three *validator* gates slot in at phase boundaries to attack each artifact (`spec.md`, `plan.md`, and `git diff`) across **3 disjoint evidence lenses** before the next phase consumes it.

The swarm's structure is declaratively specified in [`graph.json`](graph.json) (`plan-swarm@2.1`): all 16 nodes, 25 edges, 2 human gates, and node read/write contracts live in one JSON file, the lifecycle diagram below is generated directly from it via [`lib/graph/graph.py`](lib/graph/graph.py), and each active milestone's runtime progression is recorded in [`plans/active_milestones/{moniker}/state.json`](#state-machine-specification-statejson--graphjson).

> **Skills and Bundled Subagents:** This plugin bundles both the **21 skills** under [`skills/`](skills/) (invoked via slash commands such as `/plan-swarm` or the `Skill` tool) and the **13 self-contained custom subagents** under [`agents/`](agents/README.md) (invoked via `invoke_subagent`). Both families share the same [`graph.json`](graph.json) contracts and are validated together by `python3 lib/graph/graph.py validate --agents-dir agents`. See [`agents/README.md`](agents/README.md) for the subagent reference.

---

## The Skill Families

| Family | Skills | Purpose |
|---|---|---|
| **Swarm entry & orchestration** | `plan-swarm`, `starter` | Bootstrap or resume a milestone from `plans/active_milestones/{moniker}/state.json`, enforce human review and commit gates, and act as the sole committer. |
| **Swarm roles** | `product-owner` (or `visual-product-owner`), `architect` (or `visual-architect`), `engineer`, `simplifier`, `auditor`, `visual-implementation-recap` | Execute the core lifecycle — discover, spec, plan, build under TDD, simplify, audit with `file:line` evidence, and render the visual commit-gate recap. |
| **Deliberative panels** | `spec-deliberator`, `plan-deliberator` | Improve a drafted artifact via 3 delegates holding deliberately disjoint context (stakeholder bundles for specs; intent, codebase, and delivery territories for plans) who deliberate over bounded verbatim rounds (hard cap 4) to consensus. Refuses deliberation if the asymmetry test fails. |
| **Adversarial validators** | `spec-validator` (+ `geap-spec-validator`, `geap-interactions-spec-validator`), `plan-validator` (+ `geap-plan-validator`, `geap-interactions-plan-validator`), `implementation-validator` | Attack each artifact at its phase boundary with a 3-lens partitioned skeptic panel; keep findings confirmed by a 2-of-3 majority and require explicit triage for the single-vote tail. |
| **Trajectory utilities** | `teamwork-trajectory`, `wf-trajectory` | Out-of-band HTML timeline renderers for `.agents/` handoff trajectories and workflow execution traces (`wf_<runId>.json`). |

---

## The Lifecycle

> The diagram below is generated from [`graph.json`](graph.json) — the single
> declaration of this swarm's nodes, edges and gates. Edit that file and run
> `python3 lib/graph/graph.py sync`; do not hand-edit the block.

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

## Skill Reference

### Swarm Entry & Roles

#### 0. `plan-swarm` & `starter` — The Supervisor & Protocol Guardian
The primary slash-command entry point (`/plan-swarm`) and state-machine orchestrator (`starter`). **Does no coding itself**; it owns `plans/active_milestones/{moniker}/state.json`, dispatches the role agents in sequence, enforces validator and human approval gates, and holds exclusive commit authority.

- **Owns:** protocol enforcement, `state.json` lifecycle management, human gating (`plan-approval` and `commit`), and the git commit protocol. **The only role that runs `git commit`** — it is the only node holding a user-facing turn in which explicit approval (`"yes"`) can be obtained.
- **Key rules:** never edits repository source directly (delegates to `engineer`); dispatches subagents with *file paths*, never oral summaries; **must stop for user approval** at Phase 3 (`human-review-gate`) and Phase 4 (`commit-gate`); never commits without a green audit report (`AUDIT_[Plan_Name].md`) and passing implementation validation.
- **Triggers:** `/plan-swarm`, "be the supervisor", "orchestrate this end to end", "run the swarm", "drive this from idea to commit", or resuming a milestone in `plans/active_milestones/`.

#### 1. `product-owner` — The Product Owner (Phase 1)
Translates raw, ambiguous human ideas into rigorous, testable specifications, and owns the master roadmap.

- **Produces:** `plans/active_milestones/{moniker}/spec.md` (with Gherkin `Given/When/Then` acceptance criteria), `plans/active_milestones/{moniker}/context.md`, and updates `plans/00-ROADMAP.md`.
- **Signature move — the "Grill Loop":** interrogates the user (≤3 Socratic questions at a time) about edge cases, limits, error states, and UX until ambiguity is resolved. No clear acceptance criteria → not a spec.
- **Constraints:** writes no code and no architecture — defines *what* and *why*, never *how*; never guesses an unspecified edge case; never commits.

#### 1·alt. `visual-product-owner` — The Visual Product Owner (Phase 1 + Renderer)
A **drop-in alternative to `product-owner`** for specs that deserve a human-optimized review surface. Runs the identical Grill Loop and writes the same `spec.md`, then renders that spec as a self-contained, browsable HTML document.

- **Produces:** the identical `plans/active_milestones/{moniker}/spec.md` and `plans/00-ROADMAP.md` update **plus** `plans/active_milestones/{moniker}/visual-spec.html`.
- **The visual file:** a single, zero-build HTML page (opens via `file://`) with eight spec-native surfaces — overview, user-story cards, color-coded Given/When/Then acceptance criteria, user-flow diagrams, edge-cases/constraints, wireframes/prototype, open questions, and author comments.
- **Authority rule:** the HTML is a **derived view** of `spec.md` — if they disagree, `spec.md` wins.

#### 2. `architect` — The Chief Software Architect (Phase 2)
Reads `spec.md`, investigates the actual codebase read-only, and produces a detailed, micro-stepped implementation plan. **Strictly read-only on source code (`must_not_write: ["<repo source>"]`).**

- **Produces:** `plans/active_milestones/{moniker}/plan.md` (and optionally `data-model.md` / `api-contracts.md`).
- **Plan shape:** tasks grouped into **parallel execution groups** (tasks within a group must touch file-disjoint sets so up to 4 `engineer` subagents can run concurrently); every task includes a characterization/test step before any refactor (*"if there is no test, there is no refactoring"*).
- **Constraints:** never edits source; never commits; verification steps must name exact runnable commands, not "ensure it works".

#### 2·alt. `visual-architect` — The Visual Architect (Phase 2 + Renderer)
A **drop-in alternative to `architect`** for plans that deserve a human-optimized review surface. Does the identical read-only codebase investigation and writes the same `plan.md`, then renders the plan as a self-contained, browsable HTML document.

- **Produces:** the identical `plans/active_milestones/{moniker}/plan.md` **plus** `plans/active_milestones/{moniker}/visual-plan.html` (nine surfaces: overview, architecture diagrams, file map, annotated code, OpenAPI-style API cards, schema map, wireframes/prototype, open questions, and author comments).
- **Authority rule:** the HTML is a **derived view** of `plan.md` — if they disagree, `plan.md` wins.

#### 3. `engineer` — The Expert Builder (Phase 4)
Implements the approved `plan.md` exactly, one atomic micro-step at a time, under strict Test-Driven Development (`fanout: max_concurrent = 4, disjoint = "files"`).

- **Doctrine:** no untested changes; Red → Green → Refactor; characterization tests + seams before modifying untested legacy code; strict scope — implement the assigned task and nothing more.
- **Writes:** `<repo source>` and checks off completed task checkboxes in `plans/active_milestones/{moniker}/plan.md#todos`.
- **Constraints:** strict scope — no unrequested refactors or features; no plan → no code; never hands off a broken build; **never runs `git commit`** (`must_not_write: ["git commit"]`).

#### 4. `simplifier` — The Refiner (Phase 4, Optional)
Improves clarity, consistency, and maintainability of modified code **with zero behavioral change**.

- **Focus:** reduce nesting and cognitive load, use explicit naming and early returns, and match the surrounding code's idiom.
- **Constraints:** zero-regression — never alters business logic, outputs, or side effects; never commits.

#### 5. `auditor` — The Quality Gatekeeper (Phase 4)
Skeptically verifies the engineer's work against `plan.md` and `spec.md` with cited evidence. It never fixes code and never commits — its passing report is required to unlock `implementation-validator` and `commit-gate`.

- **Verifies:** static code alignment (cites `file:line`), dynamic build + test suite execution, and **anti-shortcut detection** (hunts for `TODO`/`FIXME`/placeholders, deferred-work comments, skipped or gutted tests, hardcoded expected outputs).
- **Produces:** a formal PASS/FAIL audit report at `plans/audit/AUDIT_[Plan_Name].md`.
- **Constraints:** strictly read-only on repository source (`must_not_write: ["<repo source>", "git commit"]`); never fixes what it finds (hands failures back to `engineer` on code failure or `architect` on plan failure); **never commits**.

#### 6. `visual-implementation-recap` — The Implementation Recap Renderer (Phase 4, Optional)
An **additive** renderer run after a green audit and passing implementation validation. Renders everything the milestone changed into a single self-contained HTML document for the human `commit-gate` review.

- **Produces:** `plans/active_milestones/{moniker}/visual-recap.html` (nine surfaces: outcome + metrics, tasks completed, changed-files tree with diffstat, annotated diffs, architecture, API & schema changes, before/after UI, audit verdict with evidence, and author notes).
- **Grounded & read-only:** every line and stat traces to the real `git diff`, `plan.md`, and `AUDIT_[Plan_Name].md`; secrets are redacted; never replaces the auditor or human approval; **never commits**.

---

### Deliberative Panels

#### 7. `spec-deliberator` — Deliberate the Spec (Phase 1, Optional)
Runs **after `spec.md` is drafted, before `spec-validator`**, when the spec depends on knowledge siloed across stakeholders, docs, or repos.

- **Machinery:** 3 delegates (`product`, `engineering`, `ops/security`), each seeded with a private context bundle passing the **asymmetry test** (name ≥1 concrete fact only that delegate holds that could change the spec; if context is mergeable into one prompt, deliberation is refused and recorded as `"status": "skipped"`). Sequential verbatim-relayed turns, hard cap of **4 rounds**, earned acceptance (`acceptance_basis` required).
- **Produces:** revised `plans/active_milestones/{moniker}/spec.md` and `plans/active_milestones/{moniker}/deliberations/spec-deliberation.md`.

#### 8. `plan-deliberator` — Deliberate the Plan (Phase 2, Optional)
Runs **after `plan.md` is drafted, before `plan-validator`**, when the plan spans multiple territories (`intent`, `codebase`, `delivery`) or leaves architectural trade-offs open.

- **Machinery:** 3 delegates assigned disjoint investigation territories (`intent` reads `spec.md`; `codebase` deep-reads affected subsystems; `delivery` reads tests, CI, migrations, and rollout). Every claim must cite `file:line`, spec clause, or CI command. Hard cap of **4 rounds**. Refuses deliberation (`"status": "skipped"`) if the asymmetry test fails.
- **Produces:** revised `plans/active_milestones/{moniker}/plan.md` and `plans/active_milestones/{moniker}/deliberations/plan-deliberation.md`.

---

### Adversarial Validators (3-Lens Partitioned Quorum Gates)

All three validator panels enforce `graph.json` Invariant 3: **dispatch 3 independent skeptics in parallel across 3 disjoint evidence lenses** (no shared scratchpad, never identical prompts), keep findings confirmed by a **2-of-3 majority**, track `cross_lens` corroboration, and require explicit triage (`fold-in` or `defer`) for every single-vote finding (`single_vote_triaged: true`).

#### 9. `spec-validator` — Attack the Spec (Phase 1 Gate, blocks `architect`)
- **Disjoint Lenses (`n = 3`, `gate = majority`):**
  1. `internal-consistency` — reads the spec against itself twice (`ambiguity`, `contradiction`, terminology drift).
  2. `missing-requirement` — reads `context.md`, `00-ROADMAP.md`, and external system constraints first (missing error states, limits, concurrency, auth, units, time zones).
  3. `malicious-compliance` — reads the Gherkin acceptance criteria alone without prose rationale to game them with the laziest passing implementation (`malicious-compliance`, `untestable`).
- **Produces:** `plans/active_milestones/{moniker}/adversarial-reviews/spec-validation.md`.
- **Remote alternatives (internal helpers, `disable-slash-command: true`):** `geap-spec-validator` (Vertex AI Python SDK) and `geap-interactions-spec-validator` (Interactions API via `curl` + ADC).

#### 10. `plan-validator` — Attack the Plan (Phase 2 Gate, blocks `human-review-gate`)
- **Disjoint Lenses (`n = 3`, `gate = majority`):**
  1. `sequencing` — reads the step dependency graph and parallel execution groups before opening source (`ordering`, group file collisions).
  2. `ground-truth` — opens every repository file named in `plan.md` and verifies signatures, types, schemas, and symbols (`false-assumption`, **must cite `file:line`**).
  3. `blast-radius` — reads callers, tests, CI configs, and migrations outside the files the plan modifies (`unverifiable`, `no-rollback`, `missing-migration`, `hidden-coupling`).
- **Produces:** `plans/active_milestones/{moniker}/adversarial-reviews/plan-validation.md`, including the headline **`first_domino`** (earliest step whose failure invalidates downstream steps).
- **Remote alternatives (internal helpers, `disable-slash-command: true`):** `geap-plan-validator` and `geap-interactions-plan-validator` (plan-text-only remote model panels).

#### 11. `implementation-validator` — Attack the Diff (Phase 4 Gate, blocks `commit-gate`)
- **Disjoint Lenses (`n = 3`, `gate = majority`):**
  1. `claim-vs-reality` — compares the plan/commit claim against `git diff BASE..HEAD` line by line (`claim-mismatch`, unrequested scope).
  2. `failure-paths` — inspects error branches, early returns, resource cleanup, and new tests (`failure-path`, `edge-case`).
  3. `blast-radius` — inspects untouched callers, interfaces, concurrency locks, and serialization boundaries (`concurrency`, `resource`, `regression`).
- **Signature output — Severity Calibration:** calibrates inflated finding severities with concrete rationale and writes `plans/active_milestones/{moniker}/adversarial-reviews/implementation-validation.md`.

---

### Trajectory Utilities

- **`teamwork-trajectory`:** Scans `.agents/` briefing and handoff records and compiles an interactive HTML dashboard at `.agents/trajectory.html`.
- **`wf-trajectory`:** Renders a completed dynamic workflow execution log (`wf_<runId>.json`) as a self-contained HTML page with a `run → phase → agent` tree and parallelism timeline.

---

## Artifact Map

| Path | Written by | Contents |
|---|---|---|
| `plans/research/{topic}_context.md` | `research` (Phase 0) | Codebase context report: affected domain, existing patterns, constraints. |
| `plans/00-ROADMAP.md` | `product-owner` | Master roadmap — releases, milestones, and their status (`Active`, `Shipped`). |
| `plans/active_milestones/{moniker}/context.md` | `product-owner` | Milestone context report snapshot. |
| `plans/active_milestones/{moniker}/state.json` | `starter` / `supervisor` | **Single source of truth for milestone execution state** (phase, human gates, per-node status/verdicts, per-group tasks/audit/commit SHA). |
| `plans/active_milestones/{moniker}/spec.md` | `product-owner` · `spec-deliberator` | Testable Gherkin specification (`Given/When/Then`). |
| `plans/active_milestones/{moniker}/visual-spec.html` | `visual-product-owner` | Self-contained HTML review surface for `spec.md`. |
| `plans/active_milestones/{moniker}/deliberations/{spec,plan}-deliberation.md` | `spec-deliberator` · `plan-deliberator` | Deliberation record: bundles/territories, cited disclosures, trade-offs decided, edits with `acceptance_basis`, round log. |
| `plans/active_milestones/{moniker}/adversarial-reviews/{spec,plan,implementation}-validation.md` | `spec-validator` · `plan-validator` · `implementation-validator` | 3-lens adversarial review report: verdict, 2-of-3 confirmed findings, `cross_lens` tally, `first_domino`, severity calibration, and single-vote triage table. |
| `plans/active_milestones/{moniker}/plan.md` | `architect` · `plan-deliberator` · `engineer` (`#todos`) | Micro-stepped implementation plan with file-disjoint parallel execution groups. |
| `plans/active_milestones/{moniker}/data-model.md` · `api-contracts.md` | `architect` | Optional supporting schema and API contract specifications. |
| `plans/active_milestones/{moniker}/visual-plan.html` | `visual-architect` | Self-contained HTML review surface for `plan.md`. |
| `plans/audit/AUDIT_[Plan_Name].md` | `auditor` | Evidence-based PASS/FAIL audit report (`file:line` checks, test output, anti-shortcut scan). |
| `plans/active_milestones/{moniker}/visual-recap.html` | `visual-implementation-recap` | Self-contained HTML commit-gate recap of the diff, completed tasks, and audit verdict. |

---

## State Machine Specification (`state.json` & `graph.json`)

The Plan Swarm is governed by two complementary JSON documents:
1. **`plans/active_milestones/{moniker}/state.json`** — the **runtime milestone state machine** instance tracking the live execution of a single milestone.
2. **`plugins/plan/graph.json`** — the **declarative state machine definition** specifying all valid nodes, phase transitions (`edges`), human gates (`gates`), lens partitions (`panel`), concurrency rules (`fanout`), and read/write invariants.

### 1. Runtime Milestone State Machine (`plans/active_milestones/{moniker}/state.json`)

#### Why `state.json` Exists
Inferring a milestone's current phase by listing files in `plans/active_milestones/{moniker}/` is a bug: a `plan-validator` run that failed with blocking findings leaves `plan.md` on disk identically to a `plan-validator` run that passed or never ran at all. `state.json` records every transition, gate state, lens partition, and commit SHA explicitly so `starter` / `supervisor` can resume deterministically.

#### Writer & Honesty Invariants
- **Exclusive Writer:** Only `starter` (or the `supervisor` subagent) and the human gates it holds (`plan-approval`, `commit`) may write `state.json`. Every other skill and subagent is strictly read-only on `state.json`.
- **No Fabricated State:** Any field whose value is not known with certainty must be omitted or set to `"status": "unknown"` — never guessed as `"passed"`.
- **Mandatory Skip Recording:** Whenever an optional node (`spec-deliberator`, `plan-deliberator`, `simplifier`, `visual-implementation-recap`) or gate is skipped, it **must** be recorded with `"status": "skipped"` and a non-empty `"reason"` (for example, `"reason": "asymmetry test failed — context was mergeable"`).

#### Complete Annotated `state.json` Example

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

#### Field-by-Field Meaning in `state.json`

##### A. Top-Level Fields

| Field | JSON Type | Allowed Values / Format | Meaning & Operational Contract |
|---|---|---|---|
| `graph_version` | `string` | `"plan-swarm@2.1"` | Exact version string of [`graph.json`](graph.json) against which the milestone was initialized. If `state.json.graph_version` does not match `graph.json.graph_version` on resume, the orchestrator must halt and alert the user that the swarm topology changed mid-milestone. |
| `run_id` | `string` | `"ms_{moniker}_{short_hash}"` | Immutable, unique correlation identifier for this milestone execution. Stamped onto generated review and deliberation reports so every artifact can be traced to the run that produced it. |
| `moniker` | `string` | Kebab-case slug (e.g. `"checkout-redesign"`) | Directory name of the milestone under `plans/active_milestones/{moniker}/`. |
| `phase` | `string` | `"0"` \| `"1"` \| `"1.gate"` \| `"2"` \| `"2.gate"` \| `"3"` \| `"4"` \| `"4.gate"` \| `"5"` | Current position of the state machine:<br>• `"0"` — Phase 0 codebase research (`research`) in progress.<br>• `"1"` — Phase 1 specification (`product-owner` / `spec-deliberator`) in progress.<br>• `"1.gate"` — Phase 1 adversarial gate (`spec-validator`) running or awaiting tightening loop.<br>• `"2"` — Phase 2 technical planning (`architect` / `plan-deliberator`) in progress.<br>• `"2.gate"` — Phase 2 adversarial gate (`plan-validator`) running or applying `first_domino` fixes.<br>• `"3"` — Stopped at **`human-review-gate`** waiting for the user to type `"approve"` on `spec.md` + `plan.md`.<br>• `"4"` — Phase 4 TDD construction, simplification, audit, and diff validation in progress for the active execution group.<br>• `"4.gate"` — Stopped at **`commit-gate`** after a green audit + clean `implementation-validator`, waiting for explicit user `"yes"` before `starter` executes `git commit`.<br>• `"5"` — All execution groups committed; tagging release and marking `plans/00-ROADMAP.md` as `Shipped`. |
| `updated` | `string` | ISO-8601 UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`) | UTC timestamp of the most recent state transition written by `starter` / `supervisor`. |

##### B. Human Gate Entries (`gates[]`)

| Field | JSON Type | Allowed Values | Meaning & Operational Contract |
|---|---|---|---|
| `gates[].id` | `string` | `"plan-approval"` \| `"commit"` | Identifier matching `gates[].id` in `graph.json`.<br>• `"plan-approval"` corresponds to node `human-review-gate` (Phase 3, reversible).<br>• `"commit"` corresponds to node `commit-gate` (Phase 4, irreversible, evaluated once per execution group). |
| `gates[].state` | `string` | `"not-reached"` \| `"pending"` \| `"approved"` \| `"rejected"` | Current human decision state:<br>• `"not-reached"` — upstream phases/gates have not yet cleared.<br>• `"pending"` — execution is paused awaiting explicit human input in chat.<br>• `"approved"` — human explicitly approved (`"approve"` for Phase 3, `"yes"` for Phase 4 commit).<br>• `"rejected"` — human requested changes, routing execution back to `product-owner`, `architect`, or `engineer`. |

##### C. Per-Node Status & Validator Telemetry (`nodes.{node_id}`)

| Field | JSON Type | Applies To | Meaning & Operational Contract |
|---|---|---|---|
| `nodes.{id}.status` | `string` | All nodes | Lifecycle status of the node:<br>• `"pending"` — scheduled but not yet dispatched.<br>• `"running"` — currently executing.<br>• `"done"` — role, deliberation, or renderer completed its output artifact.<br>• `"passed"` — validator or auditor cleared the artifact with zero blocking findings.<br>• `"findings"` — validator found confirmed (≥2-of-3) defects requiring a feedback cycle.<br>• `"skipped"` — optional node (`spec-deliberator`, `plan-deliberator`, `simplifier`, `visual-implementation-recap`) was bypassed; **requires `reason`**.<br>• `"failed"` — tool, build, or subagent failure.<br>• `"unknown"` — honest fallback when reconstructing partial state; never treated as `"passed"`. |
| `nodes.{id}.artifact` | `string` | Role, deliberation & renderer nodes | Workspace-relative path to the primary artifact produced or updated by the node (e.g., `"spec.md"`, `"plan.md"`, `"plans/audit/AUDIT_...md"`). |
| `nodes.{id}.reason` | `string` | Skipped nodes (`status == "skipped"`) | **Mandatory** explanation of why the node was not run (e.g. `"asymmetry test failed — context was mergeable"`). Prevents silent gate bypasses. |
| `nodes.{id}.report` | `string` | Panel nodes (`spec-validator`, `plan-validator`, `implementation-validator`) | Workspace-relative path to the Markdown review report written by the panel under `adversarial-reviews/`. |
| `nodes.{id}.lenses` | `array<string>` | Panel nodes | Ordered list of the 3 disjoint evidence lenses actually dispatched (e.g. `["sequencing", "ground-truth", "blast-radius"]`). Serves as cryptographic/audit proof that the panel partitioned its reading assignments rather than running 3 identical prompts. |
| `nodes.{id}.confirmed` | `integer` | Panel nodes | Count of deduplicated findings that achieved the **2-of-3 majority quorum** (or ≥2-of-4 for remote GEAP synthesis panels). Any value `> 0` blocks the downstream gate and triggers the feedback edge in `graph.json`. |
| `nodes.{id}.single_vote` | `integer` | Panel nodes | Count of findings raised by only 1 of the 3 skeptics. These do not automatically block the gate, but cannot be silently discarded. |
| `nodes.{id}.cross_lens` | `integer` | Panel nodes | Count of confirmed findings independently discovered by **two or more distinct lenses** from non-overlapping reading assignments. High `cross_lens` indicates genuine multi-perspective corroboration rather than single-lens repetition. |
| `nodes.{id}.first_domino` | `string \| null` | `plan-validator` | Stable finding ID (or step reference, e.g. `"step-2-missing-migration"`) of the **earliest step failure in `plan.md` whose failure invalidates downstream steps**, or `null` when `confirmed == 0`. Guides `architect` to fix the root ordering defect first. |
| `nodes.{id}.single_vote_triaged` | `boolean` | Panel nodes | Must be `true` before a panel node can transition to `"passed"` when `single_vote > 0`. Confirms every 1-vote finding in the report's Single-Vote Triage table received an explicit `fold-in` or `defer` decision. |

##### D. Execution Group Progress (`groups[]`)

| Field | JSON Type | Allowed Values / Format | Meaning & Operational Contract |
|---|---|---|---|
| `groups[].id` | `string` | `"1"`, `"2"`, ... | Execution group identifier matching the parallel group headers in `plan.md`. Groups execute sequentially (`Group 1` must be audited and committed before `Group 2` begins). |
| `groups[].tasks` | `object<string, string>` | `{ "1.A": "pending" \| "running" \| "done" \| "failed" }` | Map of file-disjoint task IDs within the group to their completion status. Up to 4 `engineer` subagents execute tasks within the same group concurrently. |
| `groups[].audit` | `string` | `"not-reached"` \| `"passed"` \| `"failed"` | Verdict from `auditor` (`AUDIT_[Plan_Name].md`) for this execution group. `"failed"` routes back to `engineer` (code failure) or `architect` (plan failure). |
| `groups[].audit_rounds` | `integer` | `0`, `1`, `2`, `3` (hard cap `3`) | Number of `engineer ⇄ auditor` verification cycles expended on this group. If `audit_rounds` reaches `3` without passing, the orchestrator **must halt and escalate to the human**. |
| `groups[].implementation_validation` | `string \| null` | Path to `adversarial-reviews/implementation-validation*.md` | Path to the 3-lens diff validation report for this group's changes (`git diff BASE..HEAD`). |
| `groups[].committed` | `string \| null` | 7–40 char Git SHA (e.g. `"a3f19c2"`) or `null` | Git commit SHA recorded by `starter` / `supervisor` **only after** `audit == "passed"`, `implementation-validator` is clean, and the user responded `"yes"` at `commit-gate`. |

---

### 2. Declarative Topology Schema (`plugins/plan/graph.json`)

While `state.json` tracks a single milestone run, [`plugins/plan/graph.json`](graph.json) defines the static state machine rules enforced by `python3 lib/graph/graph.py validate`:

| Field in `graph.json` | JSON Type | Meaning & Validation Rule Enforced by `graph.py` |
|---|---|---|
| `graph_version` | `string` | Schema/topology version (`"plan-swarm@2.1"`). Synced into the header comment of every generated README lifecycle diagram. |
| `state_file` | `string` | Template path (`"plans/active_milestones/{moniker}/state.json"`) locating the runtime state file for each milestone. |
| `node_kinds` | `object` | Dictionary of the 7 legal node archetypes: `entry`, `role`, `panel`, `deliberation`, `human-gate`, `renderer`, and `terminal`. |
| `nodes[].id` | `string` | Unique identifier for each of the 16 swarm nodes (e.g., `"product-owner"`, `"spec-validator"`, `"human-review-gate"`). Checked for uniqueness and reachability. |
| `nodes[].kind` | `string` | Must be one of the keys in `node_kinds`. Determines how `graph.py` renders the node and which structural contracts apply. |
| `nodes[].phase` | `string` | Lifecycle phase (`"0"`, `"1"`, `"2"`, `"3"`, `"4"`, `"5"`) used to group nodes vertically in ASCII/Mermaid/SVG diagrams. |
| `nodes[].skill` / `nodes[].agent` | `string` | Maps the node to `plugins/plan/skills/<skill>/SKILL.md` and `plugins/plan/agents/<agent>/agent.md` (or `agents/<agent>/agent.md`). `graph.py validate` fails if either file is missing on disk. |
| `nodes[].alternatives` | `array<string>` | Drop-in replacement skills (e.g., `["visual-product-owner"]` for `product-owner`, `["visual-architect"]` for `architect`). Each alternative `SKILL.md` must exist on disk. |
| `nodes[].dispatched_by` / `nodes[].held_by` | `string` | Declares authority: subagent nodes are `dispatched_by: "starter"`, while human-turn nodes (`human-review-gate`, `commit-gate`, `release`) are `held_by: "starter"`. Only nodes with `held_by: "starter"` may declare `"git commit"` in `writes`. |
| `nodes[].blocks` | `string` | Downstream node ID blocked until this validator panel passes (e.g., `spec-validator` blocks `architect`; `plan-validator` blocks `human-review-gate`; `implementation-validator` blocks `commit-gate`). |
| `nodes[].panel` | `object` | Required on `kind: "panel"` nodes (`n`, `gate`, `prompt_file`, `lenses[]`, `asymmetry`). `graph.py validate` verifies `len(lenses) == n`, ensures every lens name appears in `prompt_file`, and rejects any prompt containing correlated-skeptic phrases (`"three times, unchanged"`). |
| `nodes[].fanout` | `object` | Concurrency specification on `engineer` (`{"over": "execution group tasks", "max_concurrent": 4, "disjoint": "files"}`). |
| `nodes[].reads` / `writes` / `must_not_write` | `array<string>` | Explicit artifact and side-effect contracts. `graph.py validate` enforces that **only** `engineer` and `simplifier` may include `"<repo source>"` in `writes`, and **only** nodes held by `starter` may include `"git commit"` in `writes`. |
| `edges[]` | `array<object>` | Directed transitions (`{"from": "<node_id>", "to": "<node_id>", "when": "<condition>", "label": "<note>"}`). Forward edges (`when: "always" \| "optional" \| "clean" \| "approved" \| "pass"`) drive progression; back-edges (`when: "confirmed findings" \| "code failure" \| "plan failure" \| "confirmed defects" \| "more groups remain"`) define feedback loops. |
| `gates[]` | `array<object>` | Human gate declarations (`id`, `node`, `irreversible`, `per`, `prompt`). Every gate's `node` must exist and have `kind == "human-gate"`. |
| `invariants[]` | `array<string>` | The 5 non-negotiable architectural laws of the swarm (sole committer, restricted source writers, non-correlated lens panels, interactive human gates, and file-path-only dispatch). |
