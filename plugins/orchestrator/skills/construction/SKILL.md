---
name: construction
description: Use when a spec and plan are approved and the plan still has unchecked tasks — to implement each execution group with TDD, refine it, audit it, adversarially attack the diff, and commit per group behind human approval. Symptoms - "start building", "implement the plan", "execute group N", supervisor Phase 3, an approved plan.md with [ ] tasks remaining.
---

# Phase 3 — Construction (Implement → Refine → Audit → Attack → Commit)

## Overview
Turn the approved `plan.md` into committed code, **one execution group at a time**, with a
verify-everything loop. You implement nothing yourself — you sequence `engineer`, `simplifier`,
`auditor`, and `implementation-validator`, and the Supervisor performs the commit. Each
group lands as its own verified, approved commit.

## Precondition
The Supervisor's 🛑 Planning gate passed (user approved `spec.md` + `plan.md`), `plan-validation.md` is
clean, and `plan.md` has unchecked `[ ]` tasks. See Supervisor → Contract 3 & Contract 4.

## Inputs
- `plans/active_milestones/{moniker}/plan.md` (the execution groups + step details)
- `plans/active_milestones/{moniker}/spec.md` (acceptance criteria the audit checks against)

## The group loop
For the **current execution group** in `plan.md`:

1. **Implement — delegate `engineer`** (Supervisor → Contract 2). Hand it the `plan.md` path and the
   group's task IDs. Independent tasks in the group may be dispatched **in parallel (up to 4)**. The
   engineer follows TDD (Red → Green → Refactor), keeps the build green, and marks `[x]` todos in
   `plan.md`.
2. **Refine — delegate `simplifier`** on the files the engineer just wrote. Clarity and consistency only,
   **zero behavioral change**.
3. **Audit — delegate `auditor`.** It builds, runs tests, scans for shortcuts/placeholders/disabled
   tests, and writes `plans/audit/AUDIT_{plan}.md`. **Decision fork:**
   - **Code failure** (tests fail / shortcut found) → back to **`engineer`** to fix the specific task.
   - **Plan impossible** (the plan can't be realized) → back to **`architect`** to amend `plan.md`, then
     re-enter this loop.
   - **Pass** → continue.
4. **Implementation gate (Supervisor → Contract 3).** Capture the diff range and delegate
   `implementation-validator`:
   ```bash
   BASE_SHA=$(git rev-parse origin/main)   # or the group's branch point / HEAD~1
   HEAD_SHA=$(git rev-parse HEAD)
   ```
   Its skeptics attack `git diff $BASE_SHA..$HEAD_SHA`. Aggregate the 2-of-3 verdict and **persist it to**
   `plans/active_milestones/{moniker}/validation/impl-validation.md`. **Report the severity-calibration
   delta** to the user (e.g. "claimed Critical → corrected to High, conditional on concurrency"). For each
   **confirmed** defect, loop back to `engineer`, then **re-run the gate once**.
5. **🛑 Git gate (Supervisor → Contract 4).** The Supervisor drafts a conventional-commit message
   summarizing the group, shows `git status` / `git diff --stat`, and asks. It commits **only** after
   explicit approval — and only because (a) `AUDIT_*` is PASS, (b) `impl-validation.md` is clean, (c) the
   user said yes.
6. **Repeat** for the next group until every `[ ]` in `plan.md` is `[x]` and committed.

## Exit Gate
**Per group:** `auditor` PASS **and** `impl-validation.md` clean **and** the group committed.
**Phase complete:** all groups in `plan.md` are checked off and committed; the milestone is COMPLETED in
`plans/00-ROADMAP.md`.

## Hand-off
`release` runs once every milestone under the active release is COMPLETED.

## Constraints
- **NO untested code** — TDD is mandatory; new capability without tests is an automatic audit FAIL.
- **`auditor` never fixes code** — it reports; `engineer` fixes.
- **`simplifier` never changes behavior.**
- **Only the Supervisor commits** — never commit broken, unaudited, unvalidated, or unapproved code.
- **Per-group commits** — never batch all groups into one commit.

## Red Flags
| Thought | Reality |
|---|---|
| "Tests pass, commit it." | Need auditor PASS **and** impl-validation clean **and** explicit approval. |
| "Skip the diff attack, the audit passed." | The impl gate catches what the audit doesn't (edge/failure/concurrency). Run it. |
| "All three skeptics said Critical, panic." | Read the **corrected** severity — adversarial framing over-rates. Report the delta. |
| "I'll just tweak the code myself." | You delegate. `engineer` writes, `simplifier` refines, `auditor` verifies. |
| "Commit groups 1–3 together at the end." | One commit per group. |
| "The plan's wrong, I'll improvise around it." | Plan failure → back to `architect`; don't silently deviate. |
