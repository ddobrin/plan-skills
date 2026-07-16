# Plan Swarm Agents (Antigravity CLI Version)

A swarm of role-based agents, deliberative panels, and adversarial validation gates that drive a feature, bug fix, or refactor through a disciplined **spec → plan → execute → audit → commit** lifecycle.

This directory is an **Antigravity-format (`agy`)** version of the planning swarm that lives in Claude Code plugin form at [`plugins/plan/`](../plugins/plan). 
Both copies are maintained: identical roles provided for both harnesses.

These agents are designed to be used together. A single orchestrator (`supervisor`) dispatches the role agents in sequence, stops for human approval at defined gates, and treats files in `plans/` — not chat messages — as the single source of truth. Independent *validator* agents slot in at the boundary between each phase to attack the artifact (spec, plan, or diff) before the next phase consumes it.

---

## The Two Families

| Family | Agents | Purpose |
|---|---|---|
| **Swarm roles** | `supervisor`, `product-owner` (or `visual-product-owner`), `architect` (or `visual-architect`), `engineer`, `auditor`, `visual-implementation-recap` | Perform the lifecycle — discover, spec, plan, build, verify, and recap the result. *(Note: `simplifier` is not a separate agent in this port; its tasks are performed inline or handled by the engineer.)* |
| **Adversarial validators** | `spec-validator`, `plan-validator`, `implementation-validator` | Attack each artifact at its phase boundary with an independent 3-skeptic panel; keep only findings confirmed by a 2-of-3 majority. |
| **Deliberative panels** | `spec-deliberator`, `plan-deliberator` | Improve a drafted artifact via delegates holding deliberately disjoint context (stakeholder bundles for specs, codebase/intent/delivery territories for plans) who deliberate to consensus — the generative counterpart to the validators. |

---

## The Lifecycle

```
 IDEA
  │
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  supervisor (THE PM) — orchestrates everything below                │
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
  │                                                 │
  │                                    ╔════════════▼════════════════════╗
  │                                    ║ implementation-validator (gate) ║
  │                                    ╚═════════════════════════════════╝
  │             🛑 git commit — only on green audit + explicit user "yes"
  │
  ▼  Phase 5  RELEASE & TAG — product-owner marks release "Shipped"
COMMIT / TAG
```

---

## Directory Layout

Antigravity discovers agents as **directories**, each named after the agent and containing a single `agent.md` (whose body acts as the system prompt). A flat file (like `architect.md`) directly in the agents folder is ignored; the directory structure below is strictly required.

```
agents/
├── README.md                           # This guide
├── supervisor/agent.md                 # Orchestrator (formerly starter)
├── product-owner/agent.md              # Socratic spec writer
├── visual-product-owner/               # Self-contained visual spec generator
│   ├── agent.md
│   ├── assets/template.html
│   └── references/exemplar.md
├── architect/agent.md                  # Implementation planner
├── visual-architect/                   # Self-contained visual plan generator
│   ├── agent.md
│   ├── assets/template.html
│   └── references/component-catalog.md
├── engineer/agent.md                   # TDD builder
├── auditor/agent.md                    # Quality control / Verifier
├── visual-implementation-recap/        # Self-contained visual recap generator
│   ├── agent.md
│   └── assets/template.html
├── spec-deliberator/agent.md           # Spec consensus panel
├── plan-deliberator/agent.md           # Plan consensus panel
├── spec-validator/agent.md             # Spec security/correctness gate
├── plan-validator/agent.md             # Plan feasibility gate
└── implementation-validator/agent.md   # Diff review / calibration gate
```

> [!NOTE]
> The three **visual** agents (`visual-product-owner`, `visual-architect`, and `visual-implementation-recap`) are completely self-contained. They bundle their respective HTML `template.html` and reference files inside their own directories. This eliminates any dependency on the original `plugins/plan/skills/` paths, allowing them to resolve paths relatively within their own installation directories.

---

## Agent Reference

### Swarm Roles

#### 1. `supervisor` (formerly `starter`) — The Project Manager
The Project Manager and Guardian of the Protocol. **Does no development directly**; it runs the state machine, dispatching the other agents in the correct order and enforcing the lifecycle phases.
- **Owns:** Protocol enforcement, artifact management, human gating, and the git protocol.
- **Key Rules:** Never codes directly (delegates to `engineer`); passes *file paths*, not verbal summaries; **must stop for user approval** after planning and before execution; never commits broken or unapproved code.
- **Triggers:** "be the supervisor", "orchestrate this end to end", "run the swarm", "drive this from idea to commit", or resuming a milestone in `plans/active_milestones/`.

#### 2. `product-owner` — The Socratic Spec Writer
Translates raw, ambiguous human ideas into rigorous, testable specifications, and owns the master roadmap.
- **Produces:** `plans/active_milestones/{moniker}/spec.md` (utilizing Gherkin `Given/When/Then` acceptance criteria) and updates `plans/00-ROADMAP.md`.
- **The "Grill Loop":** Interrogates the user (≤3 Socratic questions at a time) about edge cases, limits, error states, and UX until ambiguity is resolved. No clear acceptance criteria → not a spec.
- **Constraints:** Writes no code and no architecture — defines *what* and *why*, never *how*; never guesses an unspecified edge case.

#### 3. `visual-product-owner` — The Visual Spec Writer
A **drop-in alternative to `product-owner`** for specs that benefit from a human-optimized visual review surface (such as UX-heavy or acceptance-criteria-dense work). Runs the identical Grill Loop and writes the same `spec.md`, then renders that spec as a self-contained, browsable HTML document.
- **Produces:** Same `spec.md` and `00-ROADMAP.md` update **plus** `plans/active_milestones/{moniker}/visual-spec.html`.
- **The Visual File:** A single, zero-build HTML page (opens via `file://`) with eight spec-native surfaces — overview, user-story cards, color-coded Given/When/Then acceptance criteria, user-flow diagrams, edge-cases/constraints, wireframes/prototype, open questions, and author comments.
- **Constraints:** Same as `product-owner` plus: must always emit `spec.md` (which remains the source of truth); self-contained single HTML file; the visual shows *what & why* only (no code or file maps).

#### 4. `architect` — The Chief Planner
Reads the spec, investigates the codebase, and produces a detailed, micro-stepped implementation plan. **Read-only on source code.**
- **Produces:** `plans/active_milestones/{moniker}/plan.md` (and optionally `data-model.md` / `api-contracts.md`).
- **Plan Structure:** Tasks grouped into **parallel execution groups** (tasks in a group must touch independent files); every task includes a test/"characterize behavior" step before any refactor — *"if there is no test, there is no refactoring."*
- **Constraints:** Never edits source files; never commits; verification steps must name exact terminal commands, not generic instructions like "ensure it works".

#### 5. `visual-architect` — The Visual Planner
A **drop-in alternative to `architect`** for plans that deserve a human-optimized review surface. Does the identical planning work, then renders the plan as a self-contained, browsable HTML document.
- **Produces:** Same `plan.md` **plus** `plans/active_milestones/{moniker}/visual-plan.html`.
- **The Visual File:** A single, zero-build HTML page (opens via `file://`) with nine surfaces — overview, architecture diagrams, file map, annotated code, OpenAPI-style API cards, schema map, wireframes/prototype, open questions, and author comments.
- **Constraints:** Same as `architect` plus: must always still emit `plan.md`; self-contained single file; comments are static author callouts, not a live system.

#### 6. `engineer` — The Expert Builder
Implements the plan exactly, one atomic step at a time, under strict Test-Driven Development (TDD).
- **Doctrine:** No untested changes; Red → Green → Refactor; characterization tests + seams for legacy code; incrementalism, deep modules, DRY, fail-fast, and Boy Scout rule.
- **Tracks Progress:** Checks off todos directly in `plan.md`; uses `git mv` to preserve file history.
- **Constraints:** Strict scope — no unrequested refactors or features; no plan → no code; never hands off a broken build; never commits.

#### 7. `auditor` — The Quality Gatekeeper
Skeptically verifies the engineer's work against the plan with evidence, and acts as the gate before any commit.
- **Verifies:** Evidence-based static checks (cites `file:lines`), dynamic build + test runs, and **anti-shortcut detection** (hunts for `TODO`/`FIXME`/placeholders, deferred-work comments, skipped or gutted tests, fake/hardcoded implementations).
- **Produces:** A formal report at `plans/audit/AUDIT_[Plan_Name].md` (written to a git-ignored directory).
- **Constraints:** Never fixes code (reports findings, hands fixes back to the engineer); no new capability without tests = automatic FAIL; commits/merges only on a **passing audit AND explicit user approval**.

#### 8. `visual-implementation-recap` — The Visual Recap Generator
An **additive** renderer — **not** a drop-in replacement for any role, and never a substitute for the auditor. After the engineer implements `plan.md` and the auditor returns a green audit, it renders everything the milestone changed into a self-contained, browsable HTML document for the human commit gate.
- **Produces:** `plans/active_milestones/{moniker}/visual-recap.html` (purely additive).
- **The Visual File:** A single, zero-build HTML page (opens via `file://`) with nine recap surfaces — overview + metrics, tasks completed, a changed-files tree with diffstat, annotated diffs (the centerpiece), architecture, API & schema changes, before/after UI, the audit verdict with evidence, and author notes.
- **Grounded & Read-Only:** Every diff line, file, and stat is taken verbatim from the real `git diff` + `plan.md` + the audit report (`AUDIT_[Plan_Name].md`) — true by construction, never invented. Read-only on source; **never commits**.

---

### Deliberative Panels

#### `spec-deliberator` — Spec Consensus Panel
Runs **after a spec is drafted, before `spec-validator`**, when the spec depends on knowledge siloed across stakeholders, docs, or repos.
- **Machinery:** Convene 3 delegates (product · engineering · ops/security by default), each seeded with a private context bundle passing the **asymmetry test** (name a fact only that delegate knows that could change the spec). Sequential turns are relayed verbatim, same agents continued across rounds, hard cap of 4 rounds. Acceptance must be earned — each accepting delegate states what it verified or what changed its mind.
- **Output:** Revised `spec.md` plus a deliberation record at `deliberations/spec-deliberation.md` (bundles, disclosures, edits with rationale, disputes, round log).

#### `plan-deliberator` — Plan Consensus Panel
Runs **after a plan is drafted, before `plan-validator`**, when the plan spans more territory — spec intent, multiple subsystems, the delivery pipeline — than one agent can deep-read at once.
- **Machinery:** Convene 3 delegates (intent · codebase · delivery by default), each deep-reading only its territory. Every claim must cite its territory (`file:line`, spec clause, or CI command); sequential verbatim-relayed turns, hard cap of 4 rounds.
- **Output:** Revised `plan.md` plus a deliberation record at `deliberations/plan-deliberation.md` — territories, cited disclosures, trade-offs decided, edits with rationale, disputes, round log.

---

### Adversarial Validators

All three share the same machinery: dispatch **3 independent skeptic agents in parallel** (no shared scratchpad), each framed to *break* the artifact with a **default-to-reject** posture, then keep only findings confirmed by a **2-of-3 majority** (1-vote findings are surfaced as "Unconfirmed (FYI)", never silently dropped).

Every panel then writes a **human-readable Markdown report** to `plans/active_milestones/{moniker}/adversarial-reviews/{stage}-validation.md` — written on every run (even a clean pass), with re-runs preserved as `-r2`/`-r3` — so the verdict is browsable without opening an agent transcript.

#### `spec-validator` — Attack the Spec
Runs **after a spec is drafted, before a plan is written** — defects are cheapest to fix here.
- **Attack Surface:** Ambiguity, missing requirements (errors, empty/huge inputs, concurrency, auth, limits, units, time), contradictions, untestable acceptance criteria, and *malicious compliance* (the laziest implementation that passes every criterion yet is useless).
- **Output:** Confirmed findings each carry a `tightening` — a concrete reworded/added requirement to fold back into the spec.

#### `plan-validator` — Attack the Plan
Runs **after a plan is written, before execution**. Unlike spec skeptics, these **read the codebase** to check the plan's assumptions against reality.
- **Attack Surface:** Ordering/dependency bugs, false assumptions about existing code (a named function/field/signature that doesn't exist — *open the file and check*), unverifiable "verify" steps, missing rollback, missing migration/compat, hidden coupling.
- **Output:** Each finding cites `file:line` evidence and a `fix`; the panel names the **`first_domino`** — the earliest failure that invalidates later steps.

#### `implementation-validator` — Attack the Diff
Runs **after code is written, before merge**. Reasons about the code (it does *not* launch the app).
- **Two Modes:** *finding-hunt* (default — hunt the diff for defects) and *claim-refutation* (try to refute explicit acceptance claims).
- **Attack Surface:** Claim vs. reality, broken/swallowed failure paths, edge cases, concurrency races, resource/correctness, regressions.
- **Signature Output:** Severity calibration. The panel's most valuable product is *corrected severity* (e.g., three reviewers call a singleton race "Critical"; it's confirmed real but downgraded to "High" because impact is gated on concurrent requests). Always surface the calibration delta.

---

## How They Work Together

A typical end-to-end run:

1. **`supervisor`** receives the request and dispatches a codebase investigation → `plans/research/`.
2. **`product-owner`** reads the context report, runs the Grill Loop, and writes `spec.md` + roadmap entry.
   - *(optional)* **`spec-deliberator`** convenes a delegate panel with disjoint context bundles to enrich the spec before it faces the gate.
3. **`spec-validator`** attacks the spec; confirmed `tightening`s are folded back in.
4. **`architect`** investigates the code and writes `plan.md` with parallel groups.
   - *(optional)* **`plan-deliberator`** convenes a territory panel (intent · codebase · delivery) to reshape the plan and decide open trade-offs with cited evidence.
5. **`plan-validator`** attacks the plan against the real codebase; the `first_domino` and confirmed fixes are applied (reorder steps, add prerequisites, correct assumptions).
6. **🛑 Human review gate** — the user reviews `spec.md` + `plan.md` and types "approve".
7. **`engineer`** implements each group under TDD; **`auditor`** verifies each group and writes an audit report.
8. **`implementation-validator`** attacks the diff before merge; confirmed defects (at calibrated severity) are fixed.
9. **🛑 Commit gate** — `visual-implementation-recap` renders `visual-recap.html` so the human can review every change at altitude; commit only on a green audit **and** explicit user approval.
10. **`product-owner`** marks the milestone "Shipped" and activates the next.

---

## Installation in `agy`

Antigravity CLI discovered agents are installed either **globally** or **workspace-locally**. Follow one of the methods below to make the plan swarm available on your system.

### Method 1: Recommended — Loose Global Agents
Installing as loose global agents places the folders directly into the directory where `agy` discovers top-level "Available Agents". This is the best fit for selecting any role directly from `/agents` in any project.

From the repository root, run:
```bash
mkdir -p "$HOME/.gemini/config/agents"
for d in agents/*/; do
  name=$(basename "$d")
  rm -rf "$HOME/.gemini/config/agents/$name"
  cp -R "agents/$name" "$HOME/.gemini/config/agents/$name"
done
```

> [!IMPORTANT]
> Always copy the **entire directory** (`cp -R`), not just the `agent.md` file. The visual agents (`visual-architect`, `visual-product-owner`, and `visual-implementation-recap`) carry bundled directories (`assets/` and `references/`) alongside their `agent.md`. They resolve these assets relatively; if you only copy `agent.md`, the visual rendering steps will fail.

### Method 2: Project-Scoped (Workspace) Agents
To keep a project-scoped copy of the swarm instead of a global one, place the same tree under your workspace directory:
```bash
mkdir -p ".agents/agents"
cp -R agents/* .agents/agents/
```

### Method 3: Bundle as an Antigravity Plugin
This method is best for structured plugin distribution. Create a dedicated plugin directory with a `plugin.json` and nest the agent tree inside it:

1. Draft the directory structure:
   ```
   antigravity/plan-plugin/
   ├── plugin.json
   └── agents/
       ├── supervisor/agent.md
       ├── architect/agent.md
       └── ...  # copy the entire agents/ tree here
   ```
2. Write the `plugin.json` structure:
   ```json
   {
     "name": "plan",
     "description": "Planning swarm agents"
   }
   ```
3. Install the plugin using `agy`:
   ```bash
   agy plugin install /absolute/path/to/antigravity/plan-plugin
   ```

---

## How the Antigravity Port Differs from Claude Code

To run cleanly under the Antigravity CLI harness, the original Claude Code skills underwent specific structural adaptations:

| Claude Code Plugin | Antigravity Port Adaptation |
|---|---|
| `model:` / `color:` / `tools:` frontmatter | Dropped — Antigravity has no documented keys. Capability & model notes are moved into a `## Running under Antigravity CLI` body section; model is chosen globally via `/model`. |
| `initialPrompt:` field | Folded into a leading `## On activation` body section in `agent.md`. |
| `<example>` / `<commentary>` in `description` | Stripped to reduce context noise. |
| `subagent_type: "general-purpose"` skeptic dispatch | Invokes subagent with `TypeName: research` (read-only skeptics/delegates). |
| Named dispatch (supervisor → `architect`, etc.) | Two-tier fallback: target the same-named custom agent if the harness allows, else `invoke_subagent` (`TypeName: self`) seeded with the role charter (mission + constraints) and target file paths. |
| `SendMessage` across deliberation rounds | Simulates persistent channel by re-invoking the delegate each round with the **full verbatim transcript** (since Antigravity's `invoke_subagent` is fire-and-forget). |
| `AskUserQuestion` tool | Prompts the user directly inline. |
| `${CLAUDE_PLUGIN_ROOT}/skills/<name>/assets/...` | Assets **bundled directly within each visual agent's subdirectory** (`assets/template.html` + `references/*.md`) and resolved relatively. |

---

## Usage

- **Discovery:** Run `agy`, open `/agents`, and confirm that the roles appear under **Available Agents**.
- **Execution:** Select the `supervisor` agent to drive an end-to-end milestone lifecycle, or select an individual agent (such as `plan-validator` or `auditor`) for a targeted, one-off task.
- **Interactive Slash Commands:** Encourage and utilize active slash commands to streamline your sessions:
  - Use `/plan` when a task requires deep step-by-step planning before any code is modified.
  - Use `/grill-me` to initiate an interactive alignment interview to resolve ambiguous requirements.
  - Use `/goal` for long-running or thorough executions (e.g., automated overnight builds).

---

## Open Risks & Considerations

- **Named Agent Dispatch:** Explicit custom-agent dispatch (e.g., `supervisor` calling `architect`) is not standardly documented in Antigravity. The dispatching agents carry a two-tier fallback (attempting named invocation, falling back to an inline-seeded `invoke_subagent` with `TypeName: self`). Confirm which path your specific `agy` build resolves.
- **Deliberators Across Rounds:** Because there is no persistent subagent channel, re-invoking with full transcripts means delegates re-analyze the codebase/spec each round. Keep territories narrow and respect the hard 4-round cap.
- **Asset Drifting:** The bundled `assets/` and `references/` are copies of those in `plugins/plan/skills/visual-*/`. If the master skill templates are updated, remember to re-copy them into the agents directory to prevent behavior drift.
