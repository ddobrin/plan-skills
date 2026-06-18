# `plan` Plugin Skills

A swarm of role-based agents and adversarial validation gates that drive a feature, bug fix, or refactor through a disciplined **spec → plan → execute → audit → commit** lifecycle.

These 9 skills are designed to be used together. A single orchestrator (`starter`) dispatches the role agents in sequence, stops for human approval at defined gates, and treats files in `plans/` — not chat messages — as the single source of truth. Three independent *validator* skills slot in at the boundary between each phase to attack the artifact (spec, plan, or diff) before the next phase consumes it.

---

## The Two Families

| Family | Skills | Purpose |
|---|---|---|
| **Swarm roles** | `starter`, `product-owner`, `architect`, `engineer`, `simplifier`, `auditor` | Perform the lifecycle — discover, spec, plan, build, refine, verify. |
| **Adversarial validators** | `spec-validator`, `plan-validator`, `implementation-validator` | Attack each artifact at its phase boundary with an independent 3-skeptic panel; keep only findings confirmed by a 2-of-3 majority. |

---

## The Lifecycle

```
 IDEA
  │
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  starter (THE SUPERVISOR) — orchestrates everything below            │
└─────────────────────────────────────────────────────────────────────┘
  │
  ▼  Phase 0  Strategic Research ─────────────► plans/research/*.md
  │
  ▼  Phase 1  product-owner   ── "Grill Loop" ─► spec.md + 00-ROADMAP.md
  │                                                  │
  │                                    ╔═════════════▼═════════════╗
  │                                    ║   spec-validator (gate)   ║
  │                                    ╚═══════════════════════════╝
  ▼  Phase 2  architect        ── plan ────────► plan.md (+ data-model.md)
  │                                                  │
  │                                    ╔═════════════▼═════════════╗
  │                                    ║   plan-validator (gate)   ║
  │                                    ╚═══════════════════════════╝
  ▼  Phase 3  🛑 HUMAN REVIEW GATE — user must "approve"
  │
  ▼  Phase 4  CONSTRUCTION LOOP, per execution group:
  │             engineer (×N parallel, TDD) ⇄ auditor (verify)
  │                  │                            │
  │             simplifier (optional refine)      │
  │                                    ╔══════════▼══════════════════════╗
  │                                    ║ implementation-validator (gate) ║
  │                                    ╚═════════════════════════════════╝
  │             🛑 git commit — only on green audit + explicit user "yes"
  │
  ▼  Phase 5  RELEASE & TAG — product-owner marks release "Shipped"
COMMIT / TAG
```

---

## Skill Reference

### Swarm Roles

#### 1. `starter` — The Supervisor
The Project Manager and Guardian of the Protocol. **Does no work itself**; it runs the state machine, dispatching the other agents in the correct order and enforcing the lifecycle above.

- **Owns:** protocol enforcement, artifact management, human gating, the git protocol.
- **Key rules:** never codes directly (delegates to `engineer`); passes *file paths*, not oral instructions; **must stop for user approval** after planning and before execution; never commits broken or unapproved code.
- **Triggers:** "be the supervisor", "orchestrate this end to end", "run the swarm", "drive this from idea to commit", or resuming a milestone in `plans/active_milestones/`.

#### 2. `product-owner` — The Product Owner
Translates raw, ambiguous human ideas into rigorous, testable specifications, and owns the master roadmap.

- **Produces:** `plans/active_milestones/{moniker}/spec.md` (with Gherkin `Given/When/Then` acceptance criteria) and updates `plans/00-ROADMAP.md`.
- **Signature move — the "Grill Loop":** interrogates the user (≤3 Socratic questions at a time) about edge cases, limits, error states, and UX until ambiguity is resolved. No clear acceptance criteria → not a spec.
- **Constraints:** writes no code and no architecture — defines *what* and *why*, never *how*; never guesses an unspecified edge case.

#### 3. `architect` — The Chief Software Architect (Planner)
Reads the spec, investigates the actual codebase, and produces a detailed, micro-stepped implementation plan. **Read-only on source code.**

- **Produces:** `plans/active_milestones/{moniker}/plan.md` (optionally `data-model.md` / `api-contracts.md`).
- **Plan shape:** tasks grouped into **parallel execution groups** (tasks in a group must touch independent files); every task includes a test/"characterize behavior" step before any refactor — *"if there is no test, there is no refactoring."*
- **Constraints:** never edits source; never commits; verification steps must name exact commands, not "ensure it works".

#### 4. `engineer` — The Expert Builder
Implements the plan exactly, one atomic step at a time, under strict Test-Driven Development.

- **Doctrine:** no untested changes; Red → Green → Refactor; characterization tests + seams for legacy code (Feathers); incrementalism, deep modules, DRY, fail-fast, Boy Scout rule.
- **Tracks progress** by checking off todos directly in `plan.md`; uses `git mv` to preserve history.
- **Constraints:** strict scope — no unrequested refactors or features; no plan → no code; never hands off a broken build; never commits.

#### 5. `simplifier` — The Refiner
Improves clarity, consistency, and maintainability of existing code **with zero behavioral change**.

- **Focus:** reduce nesting and cognitive load, explicit naming, early returns, no nested ternaries; clarity over brevity; match the project's existing style.
- **Constraints:** zero-regression — never alters business logic, fixes unrelated bugs, or adds features. Use when asked to "simplify", "refactor for clarity", or "clean up this file".

#### 6. `auditor` — The Quality Gatekeeper (Verifier)
Skeptically verifies the engineer's work against the plan, with evidence, and is the gate before any commit.

- **Verifies:** evidence-based static checks (cite `file:lines`), dynamic build + test runs, and **anti-shortcut detection** (hunts for `TODO`/`FIXME`/placeholders, deferred-work comments, skipped or gutted tests, fake/hardcoded implementations).
- **Produces:** a formal report at `plans/audit/AUDIT_[Plan_Name].md`.
- **Constraints:** never fixes code (reports only, hands fixes back to the engineer); no new capability without tests = automatic FAIL; commits/merges only on a **passing audit AND explicit user approval**.

### Adversarial Validators

All three share the same machinery: dispatch **3 independent skeptic agents in parallel** (no shared scratchpad), each framed to *break* the artifact with a **default-to-reject** posture, then keep only findings confirmed by a **2-of-3 majority** (1-vote findings are surfaced as "Unconfirmed (FYI)", never silently dropped). Each skeptic returns a single fenced JSON block; the orchestrator dedups by a stable kebab-case `id` before tallying. The gate is tunable: drop to **any-one** for high-stakes work, raise to **unanimous** when re-work is costly.

#### 7. `spec-validator` — Attack the Spec
Runs **after a spec is drafted, before a plan is written** — defects are cheapest to fix here.

- **Attack surface:** ambiguity, missing requirements (errors, empty/huge inputs, concurrency, auth, limits, units, time), contradictions, untestable acceptance criteria, and *malicious compliance* (the laziest implementation that passes every criterion yet is useless).
- **Output:** confirmed findings each carry a `tightening` — a concrete reworded/added requirement to fold back into the spec.

#### 8. `plan-validator` — Attack the Plan
Runs **after a plan is written, before execution**. Unlike spec skeptics, these **read the codebase** to check the plan's assumptions against reality.

- **Attack surface:** ordering/dependency bugs ("step 4 edits what step 2 forgot to create"), false assumptions about existing code (a named function/field/signature that doesn't exist — *open the file and check*), unverifiable "verify" steps, missing rollback, missing migration/compat, hidden coupling.
- **Output:** each finding cites `file:line` evidence and a `fix`; the panel names the **`first_domino`** — the earliest failure that invalidates later steps.

#### 9. `implementation-validator` — Attack the Diff
Runs **after code is written, before merge**. Reasons about the code (it does *not* launch the app).

- **Two modes:** *finding-hunt* (default — hunt the diff for defects, default `isReal=false`) and *claim-refutation* (try to refute explicit acceptance claims, default `refuted=true`).
- **Attack surface:** claim vs. reality, broken/swallowed failure paths, edge cases, concurrency races, resource/correctness, regressions.
- **Signature output — severity calibration:** the panel's most valuable product isn't deletion but *corrected severity* (e.g. three reviewers call a singleton race "Critical"; it's confirmed real but downgraded to "High" because impact is gated on concurrent requests). Always surface the calibration delta.

---

## Artifact Map

The swarm communicates through files under `plans/`. Knowing this layout is the fastest way to understand any in-flight milestone.

| Path | Written by | Contents |
|---|---|---|
| `plans/research/*.md` | Phase 0 investigator | Context report: affected domain, existing patterns, constraints. |
| `plans/00-ROADMAP.md` | `product-owner` | Master roadmap — releases, milestones, and their status. |
| `plans/active_milestones/{moniker}/context.md` | `product-owner` | The context report, moved in once the milestone is opened. |
| `plans/active_milestones/{moniker}/spec.md` | `product-owner` | The specification (Gherkin acceptance criteria). |
| `plans/active_milestones/{moniker}/plan.md` | `architect` | Micro-stepped plan with parallel execution groups; engineer checks off todos here. |
| `plans/active_milestones/{moniker}/data-model.md` · `api-contracts.md` | `architect` | Optional supporting design artifacts. |
| `plans/audit/AUDIT_[Plan_Name].md` | `auditor` | Evidence-based audit report (the `plans/audit/` dir is git-ignored). |

---

## How They Work Together

A typical end-to-end run:

1. **`starter`** receives the request and dispatches a codebase investigation → `plans/research/`.
2. **`product-owner`** reads the context report, runs the Grill Loop, and writes `spec.md` + roadmap entry.
3. **`spec-validator`** attacks the spec; confirmed `tightening`s are folded back in.
4. **`architect`** investigates the code and writes `plan.md` with parallel groups.
5. **`plan-validator`** attacks the plan against the real codebase; the `first_domino` and confirmed fixes are applied (reorder steps, add prerequisites, correct assumptions).
6. **🛑 Human review gate** — the user reviews `spec.md` + `plan.md` and types "approve".
7. **`engineer`** (up to ~4 in parallel per group) implements each group under TDD; **`simplifier`** optionally refines; **`auditor`** verifies each group and writes an audit report.
8. **`implementation-validator`** attacks the diff before merge; confirmed defects (at calibrated severity) are fixed.
9. **🛑 Commit gate** — only on a green audit **and** explicit user approval.
10. **`product-owner`** marks the release "Shipped" and activates the next.

---

## Invoking a Skill

These are Claude Code skills. Invoke one with the **`Skill`** tool (e.g. `plan:starter`), or let it activate from the triggers in each skill's `description`. The natural entry point for an end-to-end run is **`starter`** ("be the supervisor", "run the swarm"); the role and validator skills can also be invoked standalone for a single phase (e.g. "validate this spec" → `spec-validator`, "simplify this file" → `simplifier`).
