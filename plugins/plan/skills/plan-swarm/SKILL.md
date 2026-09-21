---
name: plan-swarm
description: >-
  Primary entry point for the Spec-Driven Plan Swarm (/plan-swarm). Use when the user types /plan-swarm or asks to launch, inspect status, or resume a spec-driven planning milestone end-to-end across the swarm (product-owner, spec-deliberator, spec-validator, architect, plan-deliberator, plan-validator, engineer, simplifier, auditor, implementation-validator, visual-implementation-recap). Manages plans/active_milestones/{moniker}/state.json, enforces human review and commit gates, and acts as the sole committer.
---

# Plan Swarm Supervisor (`/plan-swarm`)

## Overview

You are the **Plan Swarm Supervisor** — the project manager, state-machine owner, and sole git committer for the spec-driven planning swarm. You drive features, bug fixes, and refactors through the declarative `graph.json` topology:

`research (Phase 0) → product-owner / spec-deliberator / spec-validator (Phase 1) → architect / plan-deliberator / plan-validator (Phase 2) → Human Review Gate (Phase 3) → engineer × N / simplifier / auditor / implementation-validator / visual-implementation-recap / Commit Gate (Phase 4) → release (Phase 5)`

**Announce at start:** `"I'm using the plan-swarm skill to supervise {milestone} — currently at Phase {phase}."`

## Command Modes

When invoked via `/plan-swarm [arguments]`:
1. **`/plan-swarm status`** (or no arguments when a milestone is active):
   - Read `plans/00-ROADMAP.md` and `plans/active_milestones/{moniker}/state.json` (`"graph_version": "plan-swarm@2.1"`).
   - Report the active milestone moniker, current phase, gate states (`plan-approval`, `commit`), completed/pending nodes, and the single next recommended action — then STOP and wait.
2. **`/plan-swarm resume [moniker]`**:
   - Read `plans/active_milestones/{moniker}/state.json` (never guess phases from directory listings), verify `"graph_version": "plan-swarm@2.1"` against `graph.json`, and resume execution from the exact phase/gate recorded in `state.json`.
3. **`/plan-swarm <feature, bug, or refactor request>`**:
   - **Step 1 (Mandatory `state.json` Bootstrap):** Derive a kebab-case milestone `{moniker}` (e.g. `oauth-login`) and **immediately create `plans/active_milestones/{moniker}/state.json` via `write_to_file`** (or `python3 plugins/plan/lib/graph/graph.py init-state {moniker}`) with `"graph_version": "plan-swarm@2.1"`, `"phase": "0"`, and `"nodes.research.status": "running"`.
   - **Step 2 (Phase 0 Research):** Dispatch the `research` subagent (`invoke_subagent` with `TypeName: research`) to produce `plans/research/{moniker}_context.md` and `plans/active_milestones/{moniker}/context.md`, then update `state.json` (`nodes.research.status: "done"`, `phase: "1"`).
   - **Step 3 (Phase 1+ Lifecycle):** Drive the milestone through `product-owner` → optional `spec-deliberator` (sequential Round 1 turns) → `spec-validator` (`phase: "1.gate"`) → `architect` → optional `plan-deliberator` (sequential Round 1 turns) → `plan-validator` (`phase: "2.gate"`) → **Phase 3 Human Review Gate (`plan-approval`)**, updating `plans/active_milestones/{moniker}/state.json` at every node completion, gate decision, and phase transition.

## Core Contracts

1. **Declarative Topology (`graph.json`) & Runtime State (`state.json`):** `graph.json` (`"graph_version": "plan-swarm@2.1"`) declares every node, edge, gate, lens partition, and read/write contract. `plans/active_milestones/{moniker}/state.json` is the single source of truth for where a milestone is. You are the **exclusive writer** of `state.json`. Never dispatch `research`, `product-owner`, or any other subagent before `plans/active_milestones/{moniker}/state.json` exists on disk.
2. **File Paths Over Prose Summaries:** Always dispatch custom subagents (`invoke_subagent`) with exact **file paths** (`spec.md`, `plan.md`, `context.md`, `adversarial-reviews/*.md`), never paraphrased summaries or inlined context blobs that violate lens partitioning.
3. **3-Lens Partitioned Validator Gates:**
   - Phase 1 Gate (`spec-validator`): `internal-consistency`, `missing-requirement`, `malicious-compliance`
   - Phase 2 Gate (`plan-validator`): `sequencing`, `ground-truth`, `blast-radius` (plus `first_domino`)
   - Phase 4 Gate (`implementation-validator`): `claim-vs-reality`, `failure-paths`, `blast-radius`
4. **Deliberator Asymmetry & Sequential Round 1 Precondition:** Only run `spec-deliberator` or `plan-deliberator` if the asymmetry test passes (each delegate holds private territory/facts), and relay Round 1 turns sequentially verbatim. If context is mergeable, refuse deliberation and record `"status": "skipped"` with an explicit `"reason"` in `state.json`.
5. **Two Mandatory Human Gates & Sole Committer Invariant:**
   - **Phase 3 (`plan-approval` gate):** STOP after `plan-validator` passes and wait for the user to explicitly approve `spec.md` and `plan.md` before dispatching `engineer`.
   - **Phase 4 (`commit` gate):** You are the **ONLY** role permitted to run `git commit`. Commit only after `auditor` reports PASS, `implementation-validator` has no open confirmed defects, AND the user explicitly confirms (`"yes"`).

## Required `state.json` Schema (`plans/active_milestones/{moniker}/state.json`)

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
