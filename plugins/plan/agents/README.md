# `plan` Plugin Agents (Subagents)

A swarm of role-based **subagents** and adversarial validation gates that drive a feature, bug fix, or refactor through a disciplined **spec → plan → execute → audit → commit** lifecycle.

This is the **subagent** packaging of the swarm. The [skills form](../README.md) and this agents form describe the *same* lifecycle and produce the *same* `plans/` artifacts — they are kept in sync. The difference is purely how a role is **delivered and dispatched**: a skill is invoked with the `Skill` tool; an agent is a standalone subagent with its own model, tool allowlist, and a bootstrap `initialPrompt`, dispatched with the `Task` tool, auto-delegated from its `description`, or launched from the CLI.

A single orchestrator (`supervisor`) dispatches the role agents in sequence, stops for human approval at defined gates, and treats files in `plans/` — not chat messages — as the single source of truth. Independent *validator* agents slot in at the boundary between each phase to attack the artifact (spec, plan, or diff) before the next phase consumes it.

> The orchestrator is named **`supervisor`** here; in the skills family the same role is called **`starter`**. That is the only role that is renamed between the two families.

---

## Anatomy of an Agent

Every agent is a single Markdown file (`agents/{name}.md`) whose YAML frontmatter carries the fields a subagent runtime needs. This is what makes the agents form different from the skills form:

| Field | Purpose |
|---|---|
| `name` | The agent's identifier. Dispatch it as `plan:{name}` (e.g. `plan:architect`). |
| `description` | What the agent is for **plus `<example>` trigger blocks** (`Context` / `user` / `assistant` / `commentary`). The runtime reads these to **auto-delegate** — i.e. pick this agent when a request matches — so the examples are functional, not decorative. |
| `model` | The model the subagent runs on. Most use `inherit` (run on the caller's model); **`engineer` pins `claude-sonnet-5`** — TDD implementation is high-volume, well-scoped work suited to a faster model. |
| `color` | The agent's color in the subagent UI (blue architects, red validators, green engineer, magenta product/deliberators, cyan orchestrator/recap, yellow auditor). |
| `tools` | An explicit tool allowlist that **bounds the agent's authority**. It is a capability contract: `architect`/`product-owner` get no `Bash` (read-only, can't run builds or commit); `auditor`/`engineer` get `Bash`; the validators and deliberators get all tools because they fan out their own skeptic/delegate subagents. |
| `initialPrompt` | **The agent-specific bootstrap.** See below. |

### `initialPrompt` — orient before acting

The `initialPrompt` is the field with no equivalent in the skills form, and it is the heart of how these agents behave. It is a short prompt **injected the moment the subagent activates**, before it does any work. Its job is to force the agent to *establish state and confirm the target* rather than charging ahead — the discipline that keeps a swarm from acting on the wrong file or a stale assumption.

Every agent's `initialPrompt` follows the same shape:

1. **Orient** — read the relevant `plans/` artifacts (roadmap, milestone folder, the specific `spec.md` / `plan.md` / diff range) to reconstruct where the work stands.
2. **Confirm the target with the user** — which spec to plan against, which task to build, which diff range to attack — and *stop* if it is ambiguous.
3. **State the guardrails** — re-assert the role's hard constraints (read-only on code, never commit, never expand scope) so they are active from the first token.

Representative examples straight from the agents:

- **`supervisor`** — reads `plans/00-ROADMAP.md`, inventories `plans/active_milestones/`, determines the current lifecycle phase, reports *(active milestone, next action, which agent it dispatches to)*, then **STOPS and waits** — it never modifies code or dispatches execution before the human confirms.
- **`architect`** — lists specs that have no `plan.md` yet, confirms which one to plan, and refuses to plan blind: *"Investigate the affected code with Glob/Grep/Read before writing anything — blind planning is forbidden."*
- **`engineer`** — *"Do not write code until you have a plan and a task"*: it asks which `plan.md` and which `Task [X.Y]`, recites the step to confirm scope, then proceeds strictly under Red → Green → Refactor.
- **`spec-deliberator` / `plan-deliberator`** — run the **asymmetry test** in the bootstrap itself: name a fact each delegate holds that the others do not; if it fails (the context is mergeable), **STOP** and tell the user to revise centrally instead of convening a panel.
- **`spec-validator` / `plan-validator` / `implementation-validator`** — establish the artifact (or the `BASE..HEAD` diff range and mode), then dispatch the 3 independent skeptics, apply the 2-of-3 gate, and write the review document.

> The `initialPrompt` is orientation, not a straitjacket. It seeds the first move; the agent's full body (below the frontmatter) carries the complete doctrine.

---

## The Families

| Family | Agents | Purpose |
|---|---|---|
| **Swarm roles** | `supervisor`, `product-owner` (or `visual-product-owner`), `architect` (or `visual-architect`), `engineer`, `auditor`, `visual-implementation-recap` | Perform the lifecycle — orchestrate, spec, plan, build, verify, and recap the result. |
| **Adversarial validators** | `spec-validator`, `plan-validator`, `implementation-validator` | Attack each artifact at its phase boundary with an independent 3-skeptic panel; keep only findings confirmed by a 2-of-3 majority. |
| **Deliberative panels** | `spec-deliberator`, `plan-deliberator` | Improve a drafted artifact via delegates holding deliberately disjoint context (stakeholder bundles for specs, codebase/intent/delivery territories for plans) who deliberate to consensus — the generative counterpart to the validators. |
| **Transport** | `geap-interactions-caller` | Not a reasoning role. A shell that calls one remote Vertex AI / Interactions-API model and returns its verdict JSON; dispatched (one per skeptic) by the `geap-interactions-*-validator` **skills**. |

> **Not ported to the agents family** (available only as [skills](../README.md)): `simplifier`, `teamwork-trajectory`, and the four `geap-*` remote validators (`geap-spec-validator`, `geap-plan-validator`, `geap-interactions-spec-validator`, `geap-interactions-plan-validator`). The remote validators remain skills because they orchestrate a Python script or a fleet of `curl` callers; in the agents world their only footprint is the `geap-interactions-caller` transport shell. See [Differences from the Skills family](#differences-from-the-skills-family).

---

## The Lifecycle

```
 IDEA
  │
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  supervisor (THE ORCHESTRATOR) — dispatches everything below         │
└─────────────────────────────────────────────────────────────────────┘
  │
  ▼  Phase 0  Strategic Research ─────────────► plans/research/*.md
  │
  ▼  Phase 1  product-owner   ── "Grill Loop" ─► spec.md + 00-ROADMAP.md
  │                                                  │
  │                              ┌───────────────────▼───────────────────┐
  │                              │ spec-deliberator (optional — enrich   │
  │                              │ spec with siloed stakeholder context) │
  │                              └───────────────────┬───────────────────┘
  │                                    ╔═════════════▼═════════════╗
  │                                    ║   spec-validator (gate)   ║
  │                                    ╚═══════════════════════════╝
  ▼  Phase 2  architect        ── plan ────────► plan.md (+ data-model.md)
  │                                                  │
  │                              ┌───────────────────▼───────────────────┐
  │                              │ plan-deliberator (optional — reshape  │
  │                              │ plan, decide trade-offs by territory) │
  │                              └───────────────────┬───────────────────┘
  │                                    ╔═════════════▼═════════════╗
  │                                    ║   plan-validator (gate)   ║
  │                                    ╚═══════════════════════════╝
  ▼  Phase 3  🛑 HUMAN REVIEW GATE — user must "approve"
  │
  ▼  Phase 4  CONSTRUCTION LOOP, per execution group:
  │             engineer (×N parallel, TDD) ⇄ auditor (verify)
  │                                            │
  │                                    ╔══════▼══════════════════════════╗
  │                                    ║ implementation-validator (gate) ║
  │                                    ╚═════════════════════════════════╝
  │             🛑 git commit — only on green audit + explicit user "yes"
  │
  ▼  Phase 5  RELEASE & TAG — product-owner marks release "Shipped"
COMMIT / TAG
```

> **Renderer aside:** `visual-product-owner`, `visual-architect`, and `visual-implementation-recap` are drop-in / additive companions that render the phase-1, phase-2, and commit-gate artifacts as self-contained HTML review surfaces. In the skills family the `simplifier` role also runs inside the Construction Loop; there is no `simplifier` agent — see below.

---

## Agent Reference

### Swarm Roles

#### 1. `supervisor` — The Orchestrator
`model: inherit` · `color: cyan` · `tools: all` — The Project Manager and Guardian of the Protocol. **Does no work itself**; it runs the state machine, dispatching the other agents in the correct order and enforcing the lifecycle above. (This is the agent form of the skills family's `starter`.)

- **Owns:** protocol enforcement, artifact management, human gating, the git protocol.
- **`initialPrompt` behavior:** read the roadmap, inventory every active milestone, determine the current phase, report *(milestone, next action, target agent)* — then **stop and wait** for the user before dispatching anything.
- **Key rules:** never codes directly (delegates to `engineer`); passes *file paths*, not oral instructions; **must stop for user approval** after planning and before execution; never commits broken or unapproved code.

#### 2. `product-owner` — The Product Owner
`model: inherit` · `color: magenta` · `tools: Read, Write, Edit, Glob, Grep, AskUserQuestion` (no `Bash` — read-only on code) — Translates raw, ambiguous human ideas into rigorous, testable specifications, and owns the master roadmap.

- **Produces:** `plans/active_milestones/{moniker}/spec.md` (with Gherkin `Given/When/Then` acceptance criteria) and updates `plans/00-ROADMAP.md`.
- **Signature move — the "Grill Loop":** interrogates the user (≤3 Socratic questions at a time) about edge cases, limits, error states, and UX until ambiguity is resolved. No clear acceptance criteria → not a spec. (Note the `AskUserQuestion` tool in its allowlist — the Grill Loop is why it needs it.)
- **`initialPrompt` behavior:** read `plans/research/*.md` and the roadmap first; if a feature was named, start grilling; otherwise ask what to specify. Never write `spec.md` until the critical ambiguities are resolved.

#### 2·alt. `visual-product-owner` — The Visual Product Owner (Spec author + Renderer)
`model: inherit` · `color: magenta` · `tools: … + Bash` — A **drop-in alternative to `product-owner`**. Runs the identical Grill Loop and writes the same `spec.md`, then renders that spec as a self-contained, browsable HTML document (`visual-spec.html`).

- **Produces:** the same `spec.md` (structure-identical, so `spec-validator`/`architect` consume it unchanged) and roadmap update **plus** `plans/active_milestones/{moniker}/visual-spec.html`.
- **`initialPrompt` behavior:** same orientation as `product-owner`, plus: render `visual-spec.html` **only after `spec.md` is complete** — the HTML is a derived view, so no requirement may live only in it.

#### 3. `architect` — The Chief Software Architect (Planner)
`model: inherit` · `color: blue` · `tools: Read, Write, Edit, Glob, Grep` (no `Bash` — **read-only on source code**) — Reads the spec, investigates the actual codebase, and produces a detailed, micro-stepped implementation plan.

- **Produces:** `plans/active_milestones/{moniker}/plan.md` (optionally `data-model.md` / `api-contracts.md`).
- **Plan shape:** tasks grouped into **parallel execution groups** (tasks in a group must touch independent files); every task includes a test/"characterize behavior" step before any refactor — *"if there is no test, there is no refactoring."*
- **`initialPrompt` behavior:** find specs with no `plan.md`, confirm the target, and **investigate the code before writing** — blind planning is forbidden.

#### 3·alt. `visual-architect` — The Visual Architect (Planner + Renderer)
`model: inherit` · `color: blue` · `tools: … + Bash` — A **drop-in alternative to `architect`**. Does the identical planning work, then renders the plan as `visual-plan.html`.

- **Produces:** the same `plan.md` (structure-identical) **plus** `plans/active_milestones/{moniker}/visual-plan.html`.
- **`initialPrompt` behavior:** same orientation as `architect`, plus: produce `plan.md` **first**, then render the HTML from it; no decision may live only in the HTML.

#### 4. `engineer` — The Expert Builder
**`model: claude-sonnet-5`** · `color: green` · `tools: Read, Write, Edit, Glob, Grep, Bash` — Implements the plan exactly, one atomic step at a time, under strict Test-Driven Development. (The only agent that pins a specific model — high-volume, well-scoped TDD work.)

- **Doctrine:** no untested changes; Red → Green → Refactor; characterization tests + seams for legacy code (Feathers); incrementalism, deep modules, DRY, fail-fast, Boy Scout rule.
- **Tracks progress** by checking off todos directly in `plan.md`; uses `git mv` to preserve history.
- **`initialPrompt` behavior:** *do not write code until you have a plan and a task* — confirm the `plan.md` and `Task [X.Y]`, recite the step to confirm scope, then proceed under TDD. Never expand scope; never commit.

#### 5. `auditor` — The Quality Gatekeeper (Verifier)
`model: inherit` · `color: yellow` · `tools: Read, Write, Edit, Glob, Grep, Bash` — Skeptically verifies the engineer's work against the plan, with evidence, and is the gate before any commit. **The only agent authorized to `git commit`** — and only on a passing audit plus explicit user approval.

- **Verifies:** evidence-based static checks (cite `file:lines`), dynamic build + test runs, and **anti-shortcut detection** (`TODO`/`FIXME`/placeholders, deferred-work comments, skipped or gutted tests, fake/hardcoded implementations).
- **Produces:** a formal report at `plans/audit/AUDIT_[Plan_Name].md`.
- **`initialPrompt` behavior:** identify the plan and the just-completed tasks, verify statically then dynamically (build + tests), write the PASS/FAIL report — never fix code, commit only on green + explicit approval.

#### 6. `visual-implementation-recap` — The Implementation Recap (Renderer)
`model: inherit` · `color: cyan` · `tools: Read, Write, Edit, Glob, Grep, Bash` — An **additive** renderer — **not** a drop-in replacement for any role, and never a substitute for the audit. After a green audit, it renders everything the milestone changed into `visual-recap.html` for the human commit gate.

- **Produces:** `plans/active_milestones/{moniker}/visual-recap.html` (purely additive).
- **Grounded & read-only:** every diff line, file, and stat comes verbatim from the real `git diff` + `plan.md` + `AUDIT_[Plan_Name].md` — true by construction, never invented; secrets redacted; clipped diffs say so. **Never commits.**
- **`initialPrompt` behavior:** confirm the milestone and that an audit exists (mark the verification surface "not yet run" if not), gather grounding read-only (`git diff HEAD`, `--stat`, `status`, `plan.md`, audit), then render.

### Deliberative Panels

#### `spec-deliberator` — Deliberate the Spec
`model: inherit` · `color: magenta` · `tools: all` (it fans out its own delegate subagents) — Runs **after a spec is drafted, before `spec-validator`**, when the spec depends on knowledge siloed across stakeholders, docs, or repos. The structural inverse of the validators: delegates get *disjoint* context bundles, communication is the mechanism, and the output is consensus on one revised spec.

- **Machinery:** 3 delegates (product · engineering · ops/security by default), each seeded with a private bundle passing the **asymmetry test**. Sequential turns relayed **verbatim**, same agents continued across rounds, hard cap 4 rounds; acceptance must be *earned*.
- **Output:** the revised `spec.md` plus `deliberations/spec-deliberation.md`; the revised spec still goes through `spec-validator`.
- **`initialPrompt` behavior:** inventory the spec's context sources, **run the asymmetry test in the bootstrap** — if the context is mergeable, STOP and tell the user to revise centrally instead of deliberating.

#### `plan-deliberator` — Deliberate the Plan
`model: inherit` · `color: magenta` · `tools: all` — Runs **after a plan is drafted, before `plan-validator`**, when the plan spans more territory — spec intent, multiple subsystems, delivery pipeline — than one agent can deep-read at once, or leaves a trade-off open. It **reshapes** the plan and **decides trade-offs** with each territory's constraints on the record.

- **Machinery:** 3 delegates (intent · codebase · delivery by default; split codebase by subsystem), asymmetry engineered by **assigned investigation**; every claim cites its territory (`file:line`, spec clause, or CI command); 4-round cap.
- **Output:** the revised `plan.md` (structure preserved) plus `deliberations/plan-deliberation.md`; still faces `plan-validator`.
- **`initialPrompt` behavior:** list every territory the plan depends on, run the asymmetry test (name a question only each territory can answer), partition and begin round 1 — or STOP if everything fits one prompt.

### Adversarial Validators

All three share the same machinery: dispatch **3 independent skeptic subagents in parallel** (no shared scratchpad), each framed to *break* the artifact with a **default-to-reject** posture, then keep only findings confirmed by a **2-of-3 majority** (1-vote findings surfaced as "Unconfirmed (FYI)", never silently dropped). Each skeptic returns a single fenced JSON block; the orchestrator dedups by a stable kebab-case `id` before tallying. The gate is tunable (any-one for high-stakes, unanimous when re-work is costly). Every panel writes a human-readable Markdown report to `plans/active_milestones/{moniker}/adversarial-reviews/{stage}-validation.md` — on every run, re-runs preserved as `-r2`/`-r3`. All three carry `tools: all` because they spawn their own skeptic subagents.

#### 7. `spec-validator` — Attack the Spec
`model: inherit` · `color: red` — Runs **after a spec is drafted, before a plan is written** — defects are cheapest to fix here.

- **Attack surface:** ambiguity, missing requirements (errors, empty/huge inputs, concurrency, auth, limits, units, time), contradictions, untestable acceptance criteria, and *malicious compliance* (the laziest implementation that passes every criterion yet is useless).
- **Output:** confirmed findings each carry a `tightening` — a concrete reworded/added requirement to fold back into the spec.
- **`initialPrompt` behavior:** identify the `spec.md` and milestone moniker, note context the spec depends on but doesn't restate, then dispatch the 3 skeptics and write `adversarial-reviews/spec-validation.md`.

#### 8. `plan-validator` — Attack the Plan
`model: inherit` · `color: red` — Runs **after a plan is written, before execution**. Unlike spec skeptics, these **read the codebase** to check the plan's assumptions against reality.

- **Attack surface:** ordering/dependency bugs ("step 4 edits what step 2 forgot to create"), false assumptions about existing code (a named function/field/signature that doesn't exist — *open the file and check*), unverifiable "verify" steps, missing rollback, missing migration/compat, hidden coupling.
- **Output:** each finding cites `file:line` evidence and a `fix`; the panel names the **`first_domino`** — the earliest failure that invalidates later steps.
- **`initialPrompt` behavior:** identify the `plan.md` and the repository root the skeptics must read, then dispatch the 3 codebase-reading skeptics and write `adversarial-reviews/plan-validation.md`.

#### 9. `implementation-validator` — Attack the Diff
`model: inherit` · `color: red` — Runs **after code is written, before merge**. Reasons about the code (it does *not* launch the app).

- **Two modes:** *finding-hunt* (default — hunt the diff for defects, default `isReal=false`) and *claim-refutation* (try to refute explicit acceptance claims, default `refuted=true`).
- **Attack surface:** claim vs. reality, broken/swallowed failure paths, edge cases, concurrency races, resource/correctness, regressions.
- **Signature output — severity calibration:** the panel's most valuable product isn't deletion but *corrected severity* (e.g. three reviewers call a singleton race "Critical"; confirmed real but downgraded to "High" because impact is gated on concurrent requests). Always surface the calibration delta.
- **`initialPrompt` behavior:** establish the `BASE..HEAD` diff range (`git rev-parse origin/main` / `HEAD`) and a one-line statement of what the change claims, confirm the mode, then dispatch the 3 skeptics and write `adversarial-reviews/implementation-validation.md`.

### Transport

#### `geap-interactions-caller` — Remote Model Transport Shell
`tools: Bash, Read` (no `model`/`color`/`initialPrompt` — it is not a reasoning role) — Given one remote model, one system prompt (a skeptic lens or the synthesis prompt), and one document path, it calls the model over the **Interactions API** via `curl` with ADC auth (falling back to the Vertex AI global endpoint), validates the returned verdict JSON, self-repairs up to 3 attempts, and returns **only** the fenced JSON verdict. It performs no adversarial reasoning itself — the remote model does.

- **Dispatched by** the `geap-interactions-spec-validator` and `geap-interactions-plan-validator` **skills** (one caller per skeptic); not intended for direct interactive use.

---

## Differences from the Skills family

The agents mirror the [skills](../README.md), with a few deliberate divergences:

| Aspect | Skills family | Agents family |
|---|---|---|
| **Orchestrator name** | `starter` | `supervisor` (same role) |
| **`simplifier`** | Present — refines code with zero behavioral change inside the Construction Loop | **Not ported.** Use the skill, or fold clarity work into the `engineer`'s refactor step. |
| **`teamwork-trajectory`** | Present — utility that renders `.agents/trajectory.html` | **Not ported** (utility, out of lifecycle). |
| **Remote `geap-*` validators** | Four skills (`geap-spec-validator`, `geap-plan-validator`, `geap-interactions-spec-validator`, `geap-interactions-plan-validator`) | Represented only by the `geap-interactions-caller` transport shell; the validator *orchestration* stays in the skills. |
| **Per-role runtime config** | Implicit | Explicit frontmatter: `model`, `color`, `tools`, `initialPrompt`. |
| **Invocation** | `Skill` tool | `Task` tool (`subagent_type`), auto-delegation from `description`, or `claude --agent <name>`. |

---

## Artifact Map

The swarm communicates through files under `plans/` — the layout is identical to the skills family (the agents write the same artifacts).

| Path | Written by | Contents |
|---|---|---|
| `plans/research/*.md` | Phase 0 investigator | Context report: affected domain, existing patterns, constraints. |
| `plans/00-ROADMAP.md` | `product-owner` | Master roadmap — releases, milestones, and their status. |
| `plans/active_milestones/{moniker}/context.md` | `product-owner` | The context report, moved in once the milestone is opened. |
| `plans/active_milestones/{moniker}/spec.md` | `product-owner` | The specification (Gherkin acceptance criteria). |
| `plans/active_milestones/{moniker}/visual-spec.html` | `visual-product-owner` | Self-contained, browsable companion to `spec.md` (zero build). |
| `plans/active_milestones/{moniker}/deliberations/{spec,plan}-deliberation.md` | `spec-deliberator` · `plan-deliberator` | Deliberation record — panel & private bundles/territories, cited disclosures, trade-offs decided, edits with rationale & acceptance bases, disputes, round log. Written every run; re-runs append `-r2`; the hybrid tail-panel writes `-tail`. |
| `plans/active_milestones/{moniker}/plan.md` | `architect` | Micro-stepped plan with parallel execution groups; engineer checks off todos here. |
| `plans/active_milestones/{moniker}/data-model.md` · `api-contracts.md` | `architect` | Optional supporting design artifacts. |
| `plans/active_milestones/{moniker}/visual-plan.html` | `visual-architect` | Self-contained, browsable companion to `plan.md` for the human review gate (zero build). |
| `plans/active_milestones/{moniker}/adversarial-reviews/{spec,plan,implementation}-validation.md` | `spec-validator` · `plan-validator` · `implementation-validator` | Human-readable report from each skeptic panel — verdict, confirmed findings (with `file:line` evidence and fixes), unconfirmed tail, and (for implementation) the severity-calibration table. Written every run; re-runs append `-r2`, `-r3`. |
| `plans/active_milestones/{moniker}/adversarial-reviews/geap-interactions-{spec,plan}-validation.md` | `geap-interactions-*-validator` skills (via `geap-interactions-caller`) | Report from the **no-Python** remote panel (Interactions API via curl/ADC, Vertex fallback) — per-model transport and a Panel Health section. |
| `plans/audit/AUDIT_[Plan_Name].md` | `auditor` | Evidence-based audit report (the `plans/audit/` dir is git-ignored). |
| `plans/active_milestones/{moniker}/visual-recap.html` | `visual-implementation-recap` | Self-contained, browsable recap of everything the milestone changed — diffstat, annotated diffs, task/audit status — for the human commit gate (zero build). |

---

## How They Work Together

A typical end-to-end run:

1. **`supervisor`** receives the request and dispatches a codebase investigation → `plans/research/`.
2. **`product-owner`** reads the context report, runs the Grill Loop, and writes `spec.md` + roadmap entry.
   - *(optional)* **`spec-deliberator`** convenes a delegate panel with disjoint context bundles to enrich the spec before it faces the gate.
3. **`spec-validator`** attacks the spec; confirmed `tightening`s are folded back in.
4. **`architect`** investigates the code and writes `plan.md` with parallel groups.
   - *(optional)* **`plan-deliberator`** convenes a territory panel (intent · codebase · delivery) to reshape the plan and decide open trade-offs before the gate.
5. **`plan-validator`** attacks the plan against the real codebase; the `first_domino` and confirmed fixes are applied.
6. **🛑 Human review gate** — the user reviews `spec.md` + `plan.md` and types "approve".
7. **`engineer`** (up to ~4 in parallel per group) implements each group under TDD; **`auditor`** verifies each group and writes an audit report.
8. **`implementation-validator`** attacks the diff before merge; confirmed defects (at calibrated severity) are fixed.
9. **🛑 Commit gate** — `visual-implementation-recap` renders `visual-recap.html` so the human can review every change at altitude; commit only on a green audit **and** explicit user approval.
10. **`product-owner`** marks the release "Shipped" and activates the next.

---

## Invoking an Agent

These are Claude Code subagents. There are three ways to run one:

1. **Explicitly, with the `Task` tool** — set `subagent_type` to `plan:{name}` (e.g. `plan:supervisor`, `plan:architect`, `plan:spec-validator`).
2. **Automatically** — the runtime auto-delegates to an agent whose `description` (and its `<example>` blocks) matches the request. This is why the examples in each agent's frontmatter are functional, not decorative.
3. **From the CLI** — `claude --agent <name>` launches a single role directly.

The natural entry point for an end-to-end run is **`supervisor`** ("be the supervisor", "run the swarm"); the role and validator agents can also be dispatched standalone for a single phase (e.g. "validate this spec" → `spec-validator`, "plan this milestone" → `architect`). When an agent activates, its `initialPrompt` runs first — expect it to orient and confirm the target before doing any work.
