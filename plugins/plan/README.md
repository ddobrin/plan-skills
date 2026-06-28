# `plan` Plugin Skills

A swarm of role-based agents and adversarial validation gates that drive a feature, bug fix, or refactor through a disciplined **spec → plan → execute → audit → commit** lifecycle.

These 10 skills are designed to be used together. A single orchestrator (`starter`) dispatches the role agents in sequence, stops for human approval at defined gates, and treats files in `plans/` — not chat messages — as the single source of truth. Three independent *validator* skills slot in at the boundary between each phase to attack the artifact (spec, plan, or diff) before the next phase consumes it.

---

## The Two Families

| Family | Skills | Purpose |
|---|---|---|
| **Swarm roles** | `starter`, `product-owner` (or `visual-product-owner`), `architect` (or `visual-architect`), `engineer`, `simplifier`, `auditor`, `visual-implementation-recap` | Perform the lifecycle — discover, spec, plan, build, refine, verify, and recap the result. |
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

#### 2·alt. `visual-product-owner` — The Visual Product Owner (Spec author + Renderer)
A **drop-in alternative to `product-owner`** for specs that deserve a human-optimized review surface. Runs the identical Grill Loop and writes the same `spec.md`, then renders that spec as a self-contained, browsable HTML document.

- **Produces:** the same `plans/active_milestones/{moniker}/spec.md` (structure-identical, so `spec-validator`/`architect` consume it unchanged) and the same `plans/00-ROADMAP.md` update **plus** `plans/active_milestones/{moniker}/visual-spec.html`.
- **The visual file:** a single, zero-build HTML page (opens via `file://`) with eight spec-native surfaces — overview, user-story cards, color-coded Given/When/Then acceptance criteria, user-flow diagrams, edge-cases/constraints, wireframes/prototype, open questions, and author comments. Diagrams use Mermaid + a raw-source fallback; both via pinned CDN with SRI.
- **Use it instead of `product-owner`** at the Phase-1 spec step when the spec review benefits from visuals (UX-heavy or acceptance-criteria-dense work). The HTML is a **derived view** of `spec.md` — if they disagree, `spec.md` wins.
- **Constraints:** same as `product-owner` (no code, no architecture, no guessing) plus: must always still emit `spec.md`; self-contained single file; the visual shows *what & why* only (no file maps, code, or system internals — those are the Architect's); comments are static author callouts, not a live system.

#### 3. `architect` — The Chief Software Architect (Planner)
Reads the spec, investigates the actual codebase, and produces a detailed, micro-stepped implementation plan. **Read-only on source code.**

- **Produces:** `plans/active_milestones/{moniker}/plan.md` (optionally `data-model.md` / `api-contracts.md`).
- **Plan shape:** tasks grouped into **parallel execution groups** (tasks in a group must touch independent files); every task includes a test/"characterize behavior" step before any refactor — *"if there is no test, there is no refactoring."*
- **Constraints:** never edits source; never commits; verification steps must name exact commands, not "ensure it works".

#### 3·alt. `visual-architect` — The Visual Architect (Planner + Renderer)
A **drop-in alternative to `architect`** for plans that deserve a human-optimized review surface. Does the identical planning work, then renders the plan as a self-contained, browsable HTML document.

- **Produces:** the same `plans/active_milestones/{moniker}/plan.md` (structure-identical, so `plan-validator`/`engineer`/`auditor` consume it unchanged) **plus** `plans/active_milestones/{moniker}/visual-plan.html`.
- **The visual file:** a single, zero-build HTML page (opens via `file://`) with nine surfaces — overview, architecture diagrams, file map, annotated code, OpenAPI-style API cards, schema map, wireframes/prototype, open questions, and author comments. Diagrams use Mermaid + a raw-source fallback; code uses highlight.js; both via pinned CDN with SRI.
- **Use it instead of `architect`** at the Phase-2 planning step when the human review gate benefits from visuals (architecture-heavy or ambiguous work). The HTML is a **derived view** of `plan.md` — if they disagree, `plan.md` wins.
- **Constraints:** same as `architect` (read-only source, never commits) plus: must always still emit `plan.md`; self-contained single file; comments are static author callouts, not a live system.

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

#### 7. `visual-implementation-recap` — The Implementation Recap (Renderer)
An **additive** renderer — **not** a drop-in replacement for any role, and never a substitute for the audit. After the engineer implements `plan.md` and the auditor returns a green audit, it renders everything the milestone changed into a self-contained, browsable HTML document for the human commit gate.

- **Produces:** `plans/active_milestones/{moniker}/visual-recap.html` (purely additive — nothing else in the swarm changes).
- **The visual file:** a single, zero-build HTML page (opens via `file://`) with nine recap surfaces — overview + metrics, tasks completed, a changed-files tree with diffstat, annotated diffs (the centerpiece), architecture, API & schema changes, before/after UI, the audit verdict with evidence, and author notes. Diffs render with pure CSS; diagrams use Mermaid + a raw-source fallback; both libraries load via pinned CDN with SRI.
- **Grounded & read-only:** every diff line, file, and stat is taken verbatim from the real `git diff` + `plan.md` + the audit report (`AUDIT_[Plan_Name].md`) — true by construction, never invented; secrets are redacted; clipped diffs say so. Read-only on source; **never commits** (that stays the auditor's job after approval).
- **Use it** at the commit gate, after a green audit, when the reviewer benefits from seeing the whole change at altitude rather than prose plus a raw diff.

### Adversarial Validators

All three share the same machinery: dispatch **3 independent skeptic agents in parallel** (no shared scratchpad), each framed to *break* the artifact with a **default-to-reject** posture, then keep only findings confirmed by a **2-of-3 majority** (1-vote findings are surfaced as "Unconfirmed (FYI)", never silently dropped). Each skeptic returns a single fenced JSON block; the orchestrator dedups by a stable kebab-case `id` before tallying. The gate is tunable: drop to **any-one** for high-stakes work, raise to **unanimous** when re-work is costly. Every panel then writes a **human-readable Markdown report** to `plans/active_milestones/{moniker}/adversarial-reviews/{stage}-validation.md` — written on every run (even a clean pass), with re-runs preserved as `-r2`/`-r3` — so the verdict is browsable without opening an agent transcript.

#### 8. `spec-validator` — Attack the Spec
Runs **after a spec is drafted, before a plan is written** — defects are cheapest to fix here.

- **Attack surface:** ambiguity, missing requirements (errors, empty/huge inputs, concurrency, auth, limits, units, time), contradictions, untestable acceptance criteria, and *malicious compliance* (the laziest implementation that passes every criterion yet is useless).
- **Output:** confirmed findings each carry a `tightening` — a concrete reworded/added requirement to fold back into the spec.

#### 9. `plan-validator` — Attack the Plan
Runs **after a plan is written, before execution**. Unlike spec skeptics, these **read the codebase** to check the plan's assumptions against reality.

- **Attack surface:** ordering/dependency bugs ("step 4 edits what step 2 forgot to create"), false assumptions about existing code (a named function/field/signature that doesn't exist — *open the file and check*), unverifiable "verify" steps, missing rollback, missing migration/compat, hidden coupling.
- **Output:** each finding cites `file:line` evidence and a `fix`; the panel names the **`first_domino`** — the earliest failure that invalidates later steps.

#### 10. `implementation-validator` — Attack the Diff
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
| `plans/active_milestones/{moniker}/visual-spec.html` | `visual-product-owner` | Self-contained, browsable companion to `spec.md` for spec review (zero build; opens in any browser). |
| `plans/active_milestones/{moniker}/plan.md` | `architect` | Micro-stepped plan with parallel execution groups; engineer checks off todos here. |
| `plans/active_milestones/{moniker}/data-model.md` · `api-contracts.md` | `architect` | Optional supporting design artifacts. |
| `plans/active_milestones/{moniker}/visual-plan.html` | `visual-architect` | Self-contained, browsable companion to `plan.md` for the human review gate (zero build; opens in any browser). |
| `plans/active_milestones/{moniker}/adversarial-reviews/{spec,plan,implementation}-validation.md` | `spec-validator` · `plan-validator` · `implementation-validator` | Human-readable Markdown report from each skeptic panel — verdict, confirmed findings (with `file:line` evidence and fixes), unconfirmed tail, and (for implementation) the severity-calibration table. Written every run, even on a clean pass; re-runs append `-r2`, `-r3`. |
| `plans/audit/AUDIT_[Plan_Name].md` | `auditor` | Evidence-based audit report (the `plans/audit/` dir is git-ignored). |
| `plans/active_milestones/{moniker}/visual-recap.html` | `visual-implementation-recap` | Self-contained, browsable recap of everything the milestone changed — diffstat, annotated diffs, task/audit status — for the human commit gate (zero build; opens in any browser). |

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
9. **🛑 Commit gate** — `visual-implementation-recap` renders `visual-recap.html` so the human can review every change at altitude; commit only on a green audit **and** explicit user approval.
10. **`product-owner`** marks the release "Shipped" and activates the next.

---

## Invoking a Skill

These are Claude Code skills. Invoke one with the **`Skill`** tool (e.g. `plan:starter`), or let it activate from the triggers in each skill's `description`. The natural entry point for an end-to-end run is **`starter`** ("be the supervisor", "run the swarm"); the role and validator skills can also be invoked standalone for a single phase (e.g. "validate this spec" → `spec-validator`, "simplify this file" → `simplifier`).
