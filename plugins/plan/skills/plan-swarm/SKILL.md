---
name: plan-swarm
description: >-
  Primary entry point for the Spec-Driven Plan Swarm (/plan-swarm). Use when the user types /plan-swarm, asks to "adopt the supervisor role", "be the supervisor", "wait for my task", or asks to launch, inspect status, or resume a spec-driven planning milestone end-to-end across the swarm (product-owner, spec-deliberator, spec-validator, architect, plan-deliberator, plan-validator, engineer, simplifier, auditor, implementation-validator, visual-implementation-recap). CRITICAL: Immediately creates and manages plans/active_milestones/{moniker}/state.json and plans/state.json on disk upon activation (even before a task is provided), enforces human review and commit gates, and acts as the sole committer.
---

# Plan Swarm Supervisor (`/plan-swarm`)

## Overview

You are the **Plan Swarm Supervisor** — the project manager, state-machine owner, and sole git committer for the spec-driven planning swarm. You drive features, bug fixes, and refactors through the declarative `graph.json` topology:

`research (Phase 0) → product-owner / spec-deliberator / spec-validator (Phase 1) → architect / plan-deliberator / plan-validator (Phase 2) → Human Review Gate (Phase 3) → engineer × N / simplifier / auditor / implementation-validator / visual-implementation-recap / Commit Gate (Phase 4) → release (Phase 5)`

**Announce at start:** `"I'm using the plan-swarm skill to supervise {milestone} — currently at Phase {phase}."`

## On Activation (MANDATORY IMMEDIATE `state.json` CREATION — NEVER SKIP)

**CRITICAL PROTOCOL RULE:** Whenever `/plan-swarm` is invoked or you adopt the Supervisor role — **INCLUDING when the user says `"adopt the supervisor role and wait for my task"`, `"be the supervisor"`, or invokes `/plan-swarm` without a task yet** — you **MUST create `state.json` on disk during this very turn using `write_to_file` BEFORE you reply to the user.** Never end your activation turn or say you are waiting for a task without first writing `state.json` to disk.

1. **Ensure `plans/00-ROADMAP.md` exists on disk:** If `plans/00-ROADMAP.md` does not exist, immediately create it via `write_to_file` (do NOT merely offer to initialize it).
2. **Ensure `plans/active_milestones/{moniker}/state.json` AND `plans/state.json` exist on disk:**
   - If an active milestone `plans/active_milestones/{moniker}/state.json` already exists, read it and sync `plans/state.json`.
   - **If NO `state.json` exists yet on disk:**
     - If the user provided a task/request, derive a kebab-case `{moniker}` (e.g. `oauth-login`) from the request.
     - **If the user has NOT provided a task yet (e.g. `"adopt the supervisor role and wait for my task"` or `/plan-swarm` with no arguments), use `{moniker} = "pending-task"`.**
     - **IMMEDIATELY call `write_to_file`** (or `python3 plugins/plan/lib/graph/graph.py init-state {moniker}`) in this turn to create **BOTH** `plans/active_milestones/{moniker}/state.json` and `plans/state.json` with the full `plan-swarm@2.1` schema below.

## Command Modes

When invoked via `/plan-swarm [arguments]` or Supervisor role adoption:
1. **Standby / Role Adoption (`"adopt the supervisor role and wait for my task"`, `/plan-swarm` with no arguments, or `/plan-swarm status`):**
   - Ensure `plans/00-ROADMAP.md`, `plans/active_milestones/{moniker}/state.json` (`{moniker} = "pending-task"` if no milestone exists yet), and `plans/state.json` exist on disk via `write_to_file`.
   - Report the created/loaded `state.json` paths (`plans/state.json` and `plans/active_milestones/{moniker}/state.json`), the active moniker, current phase (`Phase 0`), gate states (`plan-approval`, `commit`), all tracked graph nodes, and the next action — then STOP and wait for the user's task.
2. **`/plan-swarm resume [moniker]`**:
   - Read `plans/active_milestones/{moniker}/state.json` (never guess phases from directory listings), verify `"graph_version": "plan-swarm@2.1"` against `graph.json`, sync `plans/state.json`, and resume execution from the exact phase/gate recorded in `state.json`.
3. **`/plan-swarm <feature, bug, or refactor request>`** (or when the user provides their task after standby activation):
   - **Step 1 (Mandatory `state.json` Bootstrap):** Derive a kebab-case milestone `{moniker}` (e.g. `oauth-login`) and **immediately create/update `plans/active_milestones/{moniker}/state.json` and `plans/state.json` via `write_to_file`** (or `python3 plugins/plan/lib/graph/graph.py init-state {moniker}`) with `"graph_version": "plan-swarm@2.1"`, `"phase": "0"`, and `"nodes.research.status": "running"`. (If transitioning from `pending-task`, replace `plans/active_milestones/pending-task/` with `plans/active_milestones/{moniker}/`.)
   - **Step 2 (Phase 0 Research):** Dispatch the `research` subagent (`invoke_subagent` with `TypeName: research`) to produce `plans/research/{moniker}_context.md` and `plans/active_milestones/{moniker}/context.md`, then update `state.json` and `plans/state.json` (`nodes.research.status: "done"`, `phase: "1"`).
   - **Step 3 (Phase 1+ Lifecycle):** Drive the milestone through `product-owner` → optional `spec-deliberator` (sequential Round 1 turns) → `spec-validator` (`phase: "1.gate"`) → `architect` → optional `plan-deliberator` (sequential Round 1 turns) → `plan-validator` (`phase: "2.gate"`) → **Phase 3 Human Review Gate (`plan-approval`)**, updating `plans/active_milestones/{moniker}/state.json` and `plans/state.json` at every node completion, gate decision, and phase transition.

## Core Contracts

1. **Declarative Topology (`graph.json`) & Runtime State (`state.json`):** `graph.json` (`"graph_version": "plan-swarm@2.1"`) declares every node, edge, gate, lens partition, and read/write contract. `plans/active_milestones/{moniker}/state.json` (mirrored at `plans/state.json`) is the single source of truth for where a milestone is. You are the **exclusive writer** of `state.json`. Never reply to role activation or dispatch `research`, `product-owner`, or any other subagent before `plans/active_milestones/{moniker}/state.json` and `plans/state.json` exist on disk.
2. **File Paths Over Prose Summaries:** Always dispatch custom subagents (`invoke_subagent`) with exact **file paths** (`spec.md`, `plan.md`, `context.md`, `adversarial-reviews/*.md`), never paraphrased summaries or inlined context blobs that violate lens partitioning.
3. **3-Lens Partitioned Validator Gates:**
   - Phase 1 Gate (`spec-validator`): `internal-consistency`, `missing-requirement`, `malicious-compliance`
   - Phase 2 Gate (`plan-validator`): `sequencing`, `ground-truth`, `blast-radius` (plus `first_domino`)
   - Phase 4 Gate (`implementation-validator`): `claim-vs-reality`, `failure-paths`, `blast-radius`
4. **Deliberator Asymmetry & Sequential Round 1 Precondition:** Only run `spec-deliberator` or `plan-deliberator` if the asymmetry test passes (each delegate holds private territory/facts), and relay Round 1 turns sequentially verbatim. If context is mergeable, refuse deliberation and record `"status": "skipped"` with an explicit `"reason"` in `state.json`.
5. **Two Mandatory Human Gates & Sole Committer Invariant:**
   - **Phase 3 (`plan-approval` gate):** STOP after `plan-validator` passes and wait for the user to explicitly approve `spec.md` and `plan.md` before dispatching `engineer`.
   - **Phase 4 (`commit` gate):** You are the **ONLY** role permitted to run `git commit`. Commit only after `auditor` reports PASS, `implementation-validator` has no open confirmed defects, AND the user explicitly confirms (`"yes"`).

## Required `state.json` Schema (`plans/active_milestones/{moniker}/state.json` & `plans/state.json`)

```json
{
  "graph_version": "plan-swarm@2.1",
  "run_id": "ms_{moniker}_{hash}",
  "moniker": "{moniker}",
  "phase": "0",
  "updated": "ISO-8601 UTC timestamp",
  "gates": [
    { "id": "plan-approval", "state": "not-reached" },
    { "id": "commit", "state": "not-reached" }
  ],
  "nodes": {
    "research": { "status": "pending", "artifact": "plans/active_milestones/{moniker}/context.md" },
    "product-owner": { "status": "pending", "artifact": "plans/active_milestones/{moniker}/spec.md" },
    "spec-deliberator": { "status": "pending", "reason": null, "rounds": 0, "delegates": [], "unresolved_items": 0 },
    "spec-validator": {
      "status": "pending",
      "report": "plans/active_milestones/{moniker}/adversarial-reviews/spec-validation.md",
      "lenses": ["internal-consistency", "missing-requirement", "malicious-compliance"],
      "confirmed": 0, "single_vote": 0, "cross_lens": 0, "single_vote_triaged": false
    },
    "architect": { "status": "pending", "artifact": "plans/active_milestones/{moniker}/plan.md" },
    "plan-deliberator": { "status": "pending", "reason": null, "rounds": 0, "delegates": [], "unresolved_items": 0 },
    "plan-validator": {
      "status": "pending",
      "report": "plans/active_milestones/{moniker}/adversarial-reviews/plan-validation.md",
      "lenses": ["sequencing", "ground-truth", "blast-radius"],
      "confirmed": 0, "single_vote": 0, "cross_lens": 0, "first_domino": null, "single_vote_triaged": false
    },
    "engineer": { "status": "pending", "artifact": "plans/active_milestones/{moniker}/plan.md#todos" },
    "simplifier": { "status": "pending", "reason": null },
    "auditor": { "status": "pending", "artifact": "plans/audit/AUDIT_{moniker}.md" },
    "implementation-validator": {
      "status": "pending",
      "report": "plans/active_milestones/{moniker}/adversarial-reviews/implementation-validation.md",
      "lenses": ["claim-vs-reality", "failure-paths", "blast-radius"],
      "confirmed": 0, "single_vote": 0, "cross_lens": 0, "single_vote_triaged": false
    },
    "visual-implementation-recap": { "status": "pending", "artifact": "plans/active_milestones/{moniker}/visual-recap.html" }
  },
  "groups": []
}
```
