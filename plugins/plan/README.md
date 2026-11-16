# `plan` Plugin Skills

A swarm of role-based agents and adversarial validation gates that drive a feature, bug fix, or refactor through a disciplined **spec → plan → execute → audit → commit** lifecycle.

These skills are designed to be used together. A single orchestrator (`starter`) dispatches the role agents in sequence, stops for human approval at defined gates, and treats files in `plans/` — not chat messages — as the single source of truth. Three *validator* skills slot in at the boundary between each phase to attack the artifact (spec, plan, or diff) before the next phase consumes it, each running a **lens-partitioned** panel whose skeptics hunt different categories from different evidence.

The swarm's structure is itself declared rather than described: [`graph.json`](./graph.json) holds the nodes, edges, gates and node contracts, the lifecycle diagrams below are generated from it, and each milestone's `state.json` records where a run actually is. See [Topology & State](#topology--state).

> **Skills or subagents?** This document describes the **skills** form. The same swarm is also packaged as **Antigravity agents** under [`agents/`](./agents/README.md) — configured with per-role system prompts and tool specifications for AGY CLI. See [`agents/README.md`](./agents/README.md) for the agent-specific details.

---

## The Two Families

| Family | Skills | Purpose |
|---|---|---|
| **Swarm roles** | `starter`, `product-owner` (or `visual-product-owner`), `architect` (or `visual-architect`), `engineer`, `simplifier`, `auditor`, `visual-implementation-recap` | Perform the lifecycle — discover, spec, plan, build, refine, verify, and recap the result. |
| **Adversarial validators** | `spec-validator`, `plan-validator`, `implementation-validator` | Attack each artifact at its phase boundary with an independent, lens-partitioned 3-skeptic panel; keep only findings confirmed by a 2-of-3 majority, and triage every single-vote finding. |
| **Deliberative panels** | `spec-deliberator`, `plan-deliberator` | Improve a drafted artifact via delegates holding deliberately disjoint context (stakeholder bundles for specs, codebase/intent/delivery territories for plans) who deliberate to consensus — the generative counterpart to the validators. Refused when the asymmetry test fails. |

---

## The Lifecycle

> The diagram below is generated from [`graph.json`](./graph.json) — the single
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

`starter` (the Supervisor) orchestrates every node above: it dispatches each role, holds
both human gates, and is the only node that commits.

---

## Skill Reference

### Swarm Roles

#### 1. `starter` — The Supervisor
The Project Manager and Guardian of the Protocol. **Does no work itself**; it runs the state machine, dispatching the other agents in the correct order and enforcing the lifecycle above.

- **Owns:** protocol enforcement, artifact management, the milestone's `state.json`, the validator gates, human gating, the git protocol (sole committer in the swarm).
- **Key rules:** never codes directly (delegates to `engineer`); passes *file paths*, not oral instructions; **reads the phase from `state.json`** rather than inferring it from which files exist; follows the topology in `graph.json`; never skips a gate silently; **must stop for user approval** after planning and before execution; never commits broken or unapproved code.
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
- **Constraints:** never fixes code (reports only, hands fixes back to the engineer); no new capability without tests = automatic FAIL; **never runs `git commit`** (the Supervisor (`starter` / `supervisor`) is the sole committer, and commits only on a **passing audit AND explicit user approval**).

#### 7. `visual-implementation-recap` — The Implementation Recap (Renderer)
An **additive** renderer — **not** a drop-in replacement for any role, and never a substitute for the audit. After the engineer implements `plan.md` and the auditor returns a green audit, it renders everything the milestone changed into a self-contained, browsable HTML document for the human commit gate.

- **Produces:** `plans/active_milestones/{moniker}/visual-recap.html` (purely additive — nothing else in the swarm changes).
- **The visual file:** a single, zero-build HTML page (opens via `file://`) with nine recap surfaces — overview + metrics, tasks completed, a changed-files tree with diffstat, annotated diffs (the centerpiece), architecture, API & schema changes, before/after UI, the audit verdict with evidence, and author notes. Diffs render with pure CSS; diagrams use Mermaid + a raw-source fallback; both libraries load via pinned CDN with SRI.
- **Grounded & read-only:** every diff line, file, and stat is taken verbatim from the real `git diff` + `plan.md` + the audit report (`AUDIT_[Plan_Name].md`) — true by construction, never invented; secrets are redacted; clipped diffs say so. Read-only on source; **never commits** (that stays the Supervisor's job after a passing audit and explicit user approval).
- **Use it** at the commit gate, after a green audit, when the reviewer benefits from seeing the whole change at altitude rather than prose plus a raw diff.

### Deliberative Panel

#### `spec-deliberator` — Deliberate the Spec
Runs **after a spec is drafted, before `spec-validator`**, when the spec depends on knowledge siloed across stakeholders, docs, or repos. The structural inverse of the validators: delegates get *disjoint* context bundles (validators each get the whole artifact, read through a different lens), communication is the mechanism (validators forbid it), and the output is consensus on one revised spec (not a majority vote on findings).

- **Machinery:** 3 delegates (product · engineering · ops/security by default), each seeded with a private context bundle passing the **asymmetry test** (name a fact only that delegate knows that could change the spec — or **refuse deliberation** and fall back to centralized revision, which beats a clone panel; the Supervisor records the node as `skipped` with that reason). Sequential turns relayed **verbatim** by the orchestrator, same agents continued across rounds (`send_message` or full-transcript re-invocation), hard cap 4 rounds. Acceptance must be *earned* — each accepting delegate states what it verified or what changed its mind, the guard against round-1 sycophancy.
- **Output:** the revised `spec.md` plus a deliberation record at `deliberations/spec-deliberation.md` (bundles, disclosures, edits with rationale, disputes, round log). Hard-constraint disputes escalate to the user; the revised spec still goes through `spec-validator`.
- **Hybrid:** a 2-delegate mini-panel over a validator run's *single-vote findings* adjudicates exactly where independent judgment ran out.

#### `plan-deliberator` — Deliberate the Plan
Runs **after a plan is drafted, before `plan-validator`**, when the plan spans more territory — spec intent, multiple subsystems, the delivery pipeline — than one agent can deep-read at once, or leaves a trade-off open. Where the validator predicts failure of a fixed plan, the deliberator **reshapes** it and **decides trade-offs** (migration strategy, group boundaries, scope) with each territory's constraints on the record — the one thing a vote structurally cannot produce.

- **Machinery:** 3 delegates (intent · codebase · delivery by default; split codebase by subsystem rather than adding role types), asymmetry engineered by **assigned investigation** — each delegate deep-reads only its territory and is the panel's sole authority on it (same asymmetry test, same refusal when it fails). Every claim must cite its territory (`file:line`, spec clause, or CI command); sequential verbatim-relayed turns, same agents continued via `send_message` (or re-invoked with the full verbatim transcript), hard cap 4 rounds, acceptance requires a stated basis.
- **Output:** the revised `plan.md` (structure preserved: parallel groups, test-first steps) plus a deliberation record at `deliberations/plan-deliberation.md` — territories, cited disclosures, trade-offs decided, edits with rationale, disputes, round log. Hard-evidence disputes escalate to the user; the revised plan still faces `plan-validator`.
- **Hybrid:** a 2-delegate mini-panel over a `plan-validator` run's single-vote tail → `deliberations/plan-deliberation-tail.md`.

### Adversarial Validators

All three share the same machinery: dispatch **3 lens-partitioned skeptic agents in parallel** (no shared scratchpad), each framed to *break* the artifact with a **default-to-reject** posture, then keep only findings confirmed by a **2-of-3 majority** (1-vote findings go to a **Single-Vote Findings (triage required)** section, never silently dropped).

**The three skeptics are not given the same prompt.** Each owns a different slice of the attack surface *and* a different reading assignment — for the plan panel: the step graph, the source files the plan names, and the callers/tests/CI it disturbs. Three identical prompts on one model produce correlated errors: the panel is shaped like three votes and carries close to one, so a "2-of-3 majority" becomes one opinion counted twice. Each panel's `SKILL.md` therefore ships a shared preamble, three lens sections, and a shared tail, and every panel run must first pass the **asymmetry test** — name one finding only that lens could reach; if you cannot, merge it and run two.

| Panel | Lens 1 | Lens 2 | Lens 3 |
|---|---|---|---|
| `spec-validator` | `internal-consistency` — the spec against itself | `missing-requirement` — the world outside the spec | `malicious-compliance` — the acceptance criteria alone, gamed |
| `plan-validator` | `sequencing` — the plan's step graph | `ground-truth` — the source files the plan names | `blast-radius` — callers, tests, CI, migrations |
| `implementation-validator` | `claim-vs-reality` — the diff against its description | `failure-paths` — error branches and tests | `blast-radius` — call sites the diff never touches |

Each skeptic returns a single fenced JSON block tagged with its `lens`; the orchestrator dedups by a stable kebab-case `id` before tallying, and records **which lenses agreed**. `cross_lens` agreement — two lenses reaching one finding from different evidence — is independent corroboration and ranks above same-lens repetition. The gate is tunable: drop to **any-one** for high-stakes work, raise to **unanimous** when re-work is costly. Every panel then writes a **human-readable Markdown report** to `plans/active_milestones/{moniker}/adversarial-reviews/{stage}-validation.md` — written on every run (even a clean pass), with re-runs preserved as `-r2`/`-r3` — so the verdict is browsable without opening an agent transcript.

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
| `plans/active_milestones/{moniker}/state.json` | `starter` | The run's declared state — phase, gate decisions, per-node status and reports, per-group task and commit status. `starter` **reads** this to resume rather than inferring the phase from which files exist. Schema: [`lib/graph/STATE.md`](./lib/graph/STATE.md). |
| `plans/active_milestones/{moniker}/spec.md` | `product-owner` | The specification (Gherkin acceptance criteria). |
| `plans/active_milestones/{moniker}/visual-spec.html` | `visual-product-owner` | Self-contained, browsable companion to `spec.md` for spec review (zero build; opens in any browser). |
| `plans/active_milestones/{moniker}/deliberations/{spec,plan}-deliberation.md` | `spec-deliberator` · `plan-deliberator` | Deliberation record — panel & private bundles/territories, key disclosures (cited), trade-offs decided, applied edits with rationale and acceptance bases, disputes (converged/arbitrated/escalated), round log. Written every run, even on "no changes"; re-runs append `-r2`; the hybrid tail-panel writes `-tail`. |
| `plans/active_milestones/{moniker}/plan.md` | `architect` | Micro-stepped plan with parallel execution groups; engineer checks off todos here. |
| `plans/active_milestones/{moniker}/data-model.md` · `api-contracts.md` | `architect` | Optional supporting design artifacts. |
| `plans/active_milestones/{moniker}/visual-plan.html` | `visual-architect` | Self-contained, browsable companion to `plan.md` for the human review gate (zero build; opens in any browser). |
| `plans/active_milestones/{moniker}/adversarial-reviews/{spec,plan,implementation}-validation.md` | `spec-validator` · `plan-validator` · `implementation-validator` | Human-readable Markdown report from each skeptic panel — verdict, the lenses dispatched, confirmed findings (with `file:line` evidence, fixes, and which lenses agreed), the single-vote tail for triage, and (for implementation) the severity-calibration table. Written every run, even on a clean pass; re-runs append `-r2`, `-r3`. |
| `plans/audit/AUDIT_[Plan_Name].md` | `auditor` | Evidence-based audit report (the `plans/audit/` dir is git-ignored). |
| `plans/active_milestones/{moniker}/visual-recap.html` | `visual-implementation-recap` | Self-contained, browsable recap of everything the milestone changed — diffstat, annotated diffs, task/audit status — for the human commit gate (zero build; opens in any browser). |

---

## Topology & State

Two files make the swarm's structure explicit rather than remembered.

### `graph.json` — the topology

Every node, edge, gate and node contract in one declaration: which nodes exist, what routes
between them and under what condition, which panels are lens-partitioned and into which
lenses, and what each node is allowed to read and write. **The lifecycle diagrams in this
README, in [`agents/README.md`](./agents/README.md) and in the repository README are
generated from it** — they are not maintained by hand, because three hand-maintained copies
of one topology is how a documented lifecycle and the dispatching state machine drift
apart.

Run the tooling from the plugin root (`plugins/plan/` in a checkout). It is stdlib-only
Python, so it runs wherever the plugin is installed:

```bash
python3 lib/graph/graph.py validate                # topology vs. the skills and agents on disk
python3 lib/graph/graph.py validate --agents-dir   # the same, plus every agent's own invariants
python3 lib/graph/graph.py validate-agents         # only the agents (add --agents-dir DIR for an installed copy)
python3 lib/graph/graph.py render ascii            # the lifecycle diagram
python3 lib/graph/graph.py render mermaid          # the same graph, for docs
python3 lib/graph/graph.py sync                    # rewrite the generated blocks in the three READMEs
python3 lib/graph/graph.py sync --check            # non-zero exit if a README is stale (CI)
python3 lib/graph/test_graph.py                    # the tooling's own test suite
```

`validate` is not decorative. It fails when a declared skill or agent is missing from disk,
when an edge points at a node that does not exist, when a node is unreachable, when a node
declares it writes repository source or commits without the authority to, when a panel's
prompt file (`skills/<validator>/SKILL.md`) is missing a declared lens, lacks a prompt
section of its own for each lens or the shared preamble and tail around them, or does not
tag verdicts with the declared lenses — and specifically when a panel's prompt file has
reverted to dispatching identical skeptics, which is the defect the lens partition exists
to prevent.

`validate-agents` checks the agent family against the same declaration: exactly the
thirteen swarm agents, each self-contained; every validator carrying its declared lenses
and no copy-the-prompt dispatch; the auditor barred from committing; the supervisor named
as sole committer, requiring a passing audit and explicit user approval, and managing
`state.json`; both deliberators mandating the asymmetry test and refusing when it fails.

### `state.json` — the declared state

Per milestone, at `plans/active_milestones/{moniker}/state.json`. The artifacts under
`plans/` remain the payload; this file is the index over them, recording the phase, each
gate's decision, each node's status and report, and each group's tasks and commit SHA. It
exists so `starter` can **read** where a run is instead of inferring it from which files
happen to be present — an inference in which a validator that ran and failed looks exactly
like one that never ran. A skipped gate is recorded as skipped, with a reason; an unrecorded
skip is indistinguishable from a pass. Full schema and field semantics:
[`lib/graph/STATE.md`](./lib/graph/STATE.md).

### The five principles

1. **Declared topology** — `graph.json` is the single source of truth; diagrams are generated, and tooling checks the declaration against disk.
2. **Declared state** — `state.json` is read and written at every transition; the phase is never inferred from a directory listing.
3. **Lens-partitioned panels** — each validator dispatches three skeptics with three different prompts and reading assignments; copies of one prompt are a defect; single-vote findings are triaged, not dropped.
4. **Asymmetry preconditions** — a deliberator runs only if each delegate holds something the others do not; otherwise it refuses and the revision is done centrally.
5. **Sole committer** — only `starter` / `supervisor` runs `git commit`, and only after a passing audit and an explicit user "yes".

---

## How They Work Together

A typical end-to-end run:

1. **`starter`** receives the request and dispatches a codebase investigation → `plans/research/`.
2. **`product-owner`** reads the context report, runs the Grill Loop, and writes `spec.md` + roadmap entry.
   - *(optional)* **`spec-deliberator`** convenes a delegate panel with disjoint context bundles to enrich the spec with siloed constraints before it faces the gate.
3. **`spec-validator`** attacks the spec with three lens-partitioned skeptics (internal-consistency · missing-requirement · malicious-compliance); confirmed `tightening`s are folded back in by `product-owner`, and the single-vote tail is triaged rather than dropped.
4. **`architect`** investigates the code and writes `plan.md` with parallel groups.
   - *(optional)* **`plan-deliberator`** convenes a territory panel (intent · codebase · delivery) to reshape the plan and decide open trade-offs with cited evidence before it faces the gate.
5. **`plan-validator`** attacks the plan against the real codebase with three lens-partitioned skeptics (sequencing · ground-truth · blast-radius, each reading different evidence); the `first_domino` and confirmed fixes are applied by `architect` (reorder steps, add prerequisites, correct assumptions).
6. **🛑 Human review gate** — the user reviews `spec.md` + `plan.md` and types "approve".
7. **`engineer`** (up to ~4 in parallel per group) implements each group under TDD; **`simplifier`** optionally refines; **`auditor`** verifies each group and writes an audit report. The engineer ⇄ auditor cycle is capped at 3 rounds per group.
8. **`implementation-validator`** attacks the group's diff — still uncommitted at this point, so the working tree against the last commit — with three lens-partitioned skeptics (claim-vs-reality · failure-paths · blast-radius); confirmed defects are fixed at their *calibrated* severity, and cross-lens agreement ranks above same-lens repetition.
9. **🛑 Commit gate** — `visual-implementation-recap` renders `visual-recap.html` so the human can review every change at altitude; the Supervisor (`starter` / `supervisor`) commits only on a green audit **and** explicit user approval.
10. **`product-owner`** marks the release "Shipped" and activates the next.

Throughout, `starter` records each transition, gate decision and node verdict in the milestone's `state.json`, so a resumed run reads its phase instead of guessing it.

---

## Invoking a Skill

In **Antigravity CLI (`agy`)**, install the plugin (`agy plugin install plugins/plan`) and let any skill activate from the triggers in its `description` (or read its `SKILL.md` directly via `view_file`). The natural entry point for an end-to-end run is **`starter`** ("be the supervisor", "run the swarm"); the role, deliberator, and validator skills can also be invoked standalone for a single phase (e.g. "validate this spec" → `spec-validator`, "simplify this file" → `simplifier`). You can also invoke the corresponding custom agents via `/agents` or `invoke_subagent` (see [`agents/README.md`](./agents/README.md)).
