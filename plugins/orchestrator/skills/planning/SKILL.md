---
name: planning
description: Use when a validated spec exists but no validated plan yet — to translate the spec into a micro-stepped, parallel-grouped implementation plan and pass it through an adversarial plan gate before any code is written. Symptoms - "write the plan", "how do we build this", supervisor Phase 2, a plan.md that has not yet passed plan-validation.
---

# Phase 2 — Planning (Plan + Plan Gate)

## Overview
Produce a **validated** `plan.md`. Delegate authoring to `architect` (which maps the spec onto the real
codebase and writes a micro-stepped plan with safe parallel groups and test-first steps), then **attack
the plan** with `plan-validator`, whose skeptics assume the plan *will fail* and read the
source to find the **first domino**. No execution until the plan gate is clean and the user approves.

## Precondition
`spec.md` exists and the spec gate is clean (`validation/spec-validation.md`), or a documented trivial
fast-path. See Supervisor → Contract 1 & Contract 3.

## Inputs
- `plans/active_milestones/{moniker}/spec.md`
- `plans/active_milestones/{moniker}/context.md`

## Steps
1. **Delegate `architect`** (Supervisor → Contract 2). Provide the `spec.md` and `context.md` paths. It
   investigates the codebase **read-only** and writes:
   - `plans/active_milestones/{moniker}/plan.md` — analysis, **parallel task groups** (tasks in a group
     must not touch the same files), and explicit step-by-step details with exact paths + test commands;
   - optionally `data-model.md` / `api-contracts.md`.
2. **Plan gate (Supervisor → Contract 3).** Delegate `plan-validator` with the `plan.md`
   path **and the repository root** (its skeptics must open the files the plan assumes). Aggregate the
   2-of-3 verdict and **persist it to** `plans/active_milestones/{moniker}/validation/plan-validation.md`,
   recording the `first_domino`.
   - For each **confirmed** finding, loop back to `architect` to apply its `fix` (reorder steps, insert a
     missing prerequisite, correct a false assumption about existing code), then **re-run the gate once**.
   - Surface **unconfirmed** findings to the user.
3. **Hand to the 🛑 Planning gate (Supervisor → Contract 4).** Once the plan gate is clean, STOP and let
   the Supervisor present `spec.md` + `plan.md` for explicit user approval.

## Exit Gate
`plan.md` exists **and** `validation/plan-validation.md` is clean (the `first_domino` and all confirmed
findings resolved). User approval is then pending at the Supervisor's Planning gate.

## Hand-off
`construction` reads `plan.md` once the user approves.

## Constraints
- **READ-ONLY codebase** — `architect` plans, it never edits source.
- **No commits** in this phase.
- **Explicit verification** — every task carries a concrete test command, never "ensure it works".
- **Safe parallelism** — tasks within a group must be independent (no shared files).

## Red Flags
| Thought | Reality |
|---|---|
| "Plan reads cleanly, skip the gate." | Clean prose hides dead assumptions. Run `plan-validator`. |
| "A skeptic says step 3 is wrong but cited no line." | Unverified prediction = guess. Require `file:line` or re-check before reordering. |
| "Let me start coding to save time." | No execution before the plan gate is clean **and** the user approves. |
| "I'll group everything into one big step." | Micro-step it; group only independent tasks for parallelism. |
