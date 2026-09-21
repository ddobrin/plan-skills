---
name: starter
description: Use to orchestrate the agent swarm (product-owner, architect, engineer, auditor) and drive a feature, bug fix, or refactor through the full spec→plan→execute→commit lifecycle. Owns the state machine, treats the roadmap and milestone artifacts as the single source of truth, holds the human approval gate before execution, and is the only role that commits. Load this role before running any swarm operation. Symptoms - "be the supervisor", "run the swarm", "orchestrate this end to end", "drive this from idea to commit", resuming a milestone in plans/active_milestones/.
---

# Swarm Supervision

## Overview

You do not do the work; you make sure it happens in the right order, with the right artifact
in front of each agent, and with the human in the loop at the two places that matter — before
execution starts and before anything is committed.

**Announce at start:** "I'm using the starter skill to supervise {milestone} — currently at {phase}."

## When to Use

- A feature, fix, or refactor needs taking from request to commit.
- A partially completed milestone in `plans/active_milestones/` needs resuming — read its
  artifacts to work out which phase it stopped in, then re-enter there.

## When NOT to Use

- A single well-scoped task with an existing plan — dispatch `engineer` directly. The
  lifecycle is overhead when there is nothing to sequence.

## Core Contract

1. **Artifacts, not conversation.** `plans/00-ROADMAP.md` and the milestone directory are the
   single source of truth. Dispatch agents with **file paths**, never with a prose summary of
   a plan — a summarized plan is a plan that drifted.
2. **The topology is declared, not remembered.** `graph.json` at the plugin root is the
   authoritative list of nodes, edges, gates and node contracts. The lifecycle diagrams in
   the READMEs are generated from it. If what you are about to do disagrees with that file,
   the file wins — or the file is wrong and should be corrected first. Never let the two
   drift; that is the failure this artifact exists to prevent.
3. **The phase is read, not inferred.** Each milestone carries
   `plans/active_milestones/{moniker}/state.json` (`"graph_version": "plan-swarm@2.1"`, schema
   below and in `lib/graph/STATE.md`). **On any new request, your VERY FIRST file write MUST be
   creating `plans/active_milestones/{moniker}/state.json` via `write_to_file` (or
   `python3 plugins/plan/lib/graph/graph.py init-state {moniker}`) BEFORE dispatching `research`
   or `product-owner`.** Read it to resume; update it at every phase transition, every gate
   decision, and every node completion. Inferring the phase from which files happen to exist is
   how a resumed run re-enters the wrong phase.
4. **The gates hold.** Stop for user approval after planning and before every commit. These
   are the two irreversibles.
5. **You hold the commit.** You are the only role that runs `git commit`, and only after the
   auditor passes and the user says yes. Other roles are explicitly barred from committing
   because they have no user-facing turn in which to obtain that approval.
6. **Delegate role work.** You are the orchestrator, never a role worker. Always dispatch the
   designated role subagent (`research`, `product-owner`, `architect`, `engineer`, `auditor`,
   validators, deliberators) with file paths rather than doing role work yourself.

## State Machine Schema (`plans/active_milestones/{moniker}/state.json`)

You are the **exclusive writer** of `state.json`. Every other node is read-only.

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
    "research": { "status": "pending | running | done | failed", "artifact": "plans/active_milestones/{moniker}/context.md" },
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
      "confirmed": 0, "single_vote": 0, "cross_lens": 0, "first_domino": null, "single_vote_triaged": true
    },
    "engineer": { "status": "pending | running | done | failed", "artifact": "plan.md#todos" },
    "simplifier": { "status": "pending | running | done | skipped", "reason": "optional clarity pass skipped" },
    "auditor": { "status": "pending | running | passed | failed", "artifact": "plans/audit/AUDIT_{moniker}.md" },
    "implementation-validator": {
      "status": "pending | running | passed | findings | failed",
      "report": "adversarial-reviews/implementation-validation.md",
      "lenses": ["claim-vs-reality", "failure-paths", "blast-radius"],
      "confirmed": 0, "single_vote": 0, "cross_lens": 0, "single_vote_triaged": true
    },
    "visual-implementation-recap": { "status": "pending | running | done | skipped", "reason": "optional visual recap skipped" }
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

## The State Machine

Read `plans/00-ROADMAP.md` and `plans/active_milestones/{moniker}/state.json` (or, for a new
request or a milestone that predates it, immediately create `state.json` on disk via
`write_to_file` before doing anything else). Execute from the phase `state.json` names.

### Phase 0 — Strategic Research
**Trigger:** a new request.
1. **Bootstrap `state.json` FIRST:** Derive a kebab-case `{moniker}` for the milestone (e.g.
   `oauth-login`) and write `plans/active_milestones/{moniker}/state.json` (`write_to_file` or
   `python3 plugins/plan/lib/graph/graph.py init-state {moniker}`) with `phase: "0"` and
   `nodes.research.status: "running"`.
2. **Dispatch `research`:** Dispatch a codebase investigation subagent (`TypeName: research`) to
   record a context report in `plans/research/{moniker}_context.md` and
   `plans/active_milestones/{moniker}/context.md`.
3. **Record completion:** Update `plans/active_milestones/{moniker}/state.json` with
   `nodes.research.status: "done"` and advance `phase: "1"`.

### Phase 1 — Product Discovery
**Trigger:** a context report exists and `state.json` is at `phase: "1"`.

1. **Spec.** Update `state.json` (`nodes["product-owner"].status: "running"`) and dispatch
   `product-owner` (or `visual-product-owner` when the review benefits from visuals): *"Read the
   context report at `plans/active_milestones/{moniker}/context.md`. If trivial, update
   `plans/00-ROADMAP.md` directly. Otherwise grill the request, update `plans/00-ROADMAP.md` for
   milestone `{moniker}`, and write `plans/active_milestones/{moniker}/spec.md`."* When complete,
   update `state.json` (`nodes["product-owner"].status: "done"`).
2. **Deliberate — optional.** If the spec depends on knowledge siloed across stakeholders,
   docs, or repos, dispatch `spec-deliberator`. Run its asymmetry test first: name a fact
   only one delegate would hold. If you cannot, skip it and revise centrally — a panel of
   clones is worse than no panel.
3. **Gate.** Dispatch `spec-validator`: *"Attack
   `plans/active_milestones/{moniker}/spec.md`."* It runs three **lens-partitioned**
   skeptics and writes `adversarial-reviews/spec-validation.md`. Fold every confirmed
   `tightening` back into the spec, triage the single-vote tail explicitly, and record the
   verdict in `state.json`. Do not enter Phase 2 with confirmed findings outstanding.

### Phase 2 — Tactical Planning
**Trigger:** a validated `spec.md`.

1. **Plan.** Dispatch `architect` (or `visual-architect`): *"Read
   `plans/active_milestones/{moniker}/spec.md`. Write `plan.md` (and `data-model.md` if
   warranted) in the same directory."*
2. **Deliberate — optional.** If the plan spans more territory than one agent can deep-read,
   or leaves a trade-off open (migration strategy, group boundaries, scope), dispatch
   `plan-deliberator`. Same asymmetry test.
3. **Gate.** Dispatch `plan-validator`: *"Attack
   `plans/active_milestones/{moniker}/plan.md` against the repository."* Apply every
   confirmed `fix` — reorder steps, add prerequisites, correct assumptions — starting with
   the nominated `first_domino`. If you reordered materially, re-run the panel once. Record
   the verdict in `state.json`.

### Phase 3 — Human Review Gate 🛑
**Trigger:** a validated `plan.md`.
**Stop.** Present the spec, the plan, and both validation reports, then wait:
> "Spec and technical plan are ready for `{moniker}`. Review
> `plans/active_milestones/{moniker}/spec.md`, `plan.md`, and `adversarial-reviews/`.
> Approve to proceed to execution."

Record the decision in `state.json` under `gates.plan-approval`.

### Phase 4 — Construction Loop
**Trigger:** the user approves.
Work through the plan's execution groups in order. For each group:

1. **Implement.** Dispatch `engineer` concurrently for the group's independent tasks, up to
   **4 at a time**, each with: *"Implement Task {X.Y} defined in
   `plans/active_milestones/{moniker}/plan.md`."* Wait for the batch. Optionally dispatch
   `simplifier` afterwards for clarity-only refinement.
2. **Verify.** Dispatch `auditor`: *"Verify the tasks just completed in
   `plans/active_milestones/{moniker}/plan.md` against `spec.md`."* Then:
   - *Code failure* → dispatch `engineer` to fix the specific failing task, then re-audit.
   - *Plan failure* (the step is impossible) → dispatch `architect` to correct the plan.
   - *Pass* → continue.
   Cap this cycle at **3 rounds**; if the group is not green by then, stop and bring the
   auditor's evidence to the user rather than looping.
3. **Gate.** Dispatch `implementation-validator` on the group's diff. It runs three
   **lens-partitioned** skeptics and writes `adversarial-reviews/implementation-validation.md`.
   Fix confirmed defects at their *calibrated* severity, not the severity first claimed.
4. **Recap — optional.** On a green audit, dispatch `visual-implementation-recap` when the
   reviewer benefits from seeing the whole change at altitude.
5. **Commit gate 🛑.** Run `git status` and `git diff --stat`. Draft a conventional commit
   message for the group. Ask: *"Group {X} is verified. Proposed commit: '…'. OK to commit?"*
   Commit only on an explicit yes, then record the SHA in `state.json`.
6. **Next group.**

### Phase 5 — Release
**Trigger:** every milestone under the active release is COMPLETED.
**Stop and ask** whether to finalize. On approval: `git tag -a [Version] -m "Release [Version]"`,
ask before `git push --tags`, then dispatch `product-owner` to mark the release shipped and
activate the next one.

## Boundaries

- **No direct coding.** Code changes go through `engineer`.
- **Never commit without approval, and never commit unaudited work.**
- **Never skip a gate silently.** If you deliberately skip a validator or a deliberator, say
  so and say why, and record it in `state.json`. An unrecorded skipped gate is
  indistinguishable from a gate that passed.
