---
name: engineer
description: Use when an approved plan.md exists and a specific task from it needs to be built, to implement exactly that task under TDD without expanding scope. Reads the plan as the requirement spec, works in Red→Green→Refactor increments, writes characterization tests before touching untested legacy code, keeps the build green, and ticks the plan's checkboxes as it goes. Symptoms - "implement Task 1.A", "build the plan", "the tests for task 2.B are failing, fix it", executing an approved plans/active_milestones/{moniker}/plan.md, an auditor sent work back for a specific task.
---

# Plan-Driven Implementation

## Overview

Build one task from an approved plan, under test, without deciding anything the plan
already decided. The plan is the requirement specification: it fixes *what* to build and
in what order. You bring judgment about *how* the code should be written.

**Announce at start:** "I'm using the engineer skill to implement Task {X.Y} from {plan path}."

## When to Use

- An approved `plan.md` exists and names the task you were dispatched for.
- An auditor returned a specific task as failing and it needs fixing in place.

## When NOT to Use

- No plan exists — ask for one, or run `architect` first. Improvising the requirement is
  how a swarm loses its audit trail.
- The plan step turns out to be impossible (see **When the plan is wrong**) — that is a
  planning problem, not an implementation problem.

## Core Contract

1. **The plan is the source of truth.** You accept a plan file path and implement the task
   named in your dispatch. Read the whole plan for context; change only what your task covers.
2. **No untested change.** Every behavior you add or alter is covered by a test. For new
   code that means TDD proper — Red, then Green, then Refactor.
3. **Legacy code gets a safety net first.** When the code you must change has no tests,
   apply Feathers' sequence before changing behavior: identify the *seam* that prevents
   testing, make the minimal structural change to open it, write a **characterization test**
   that locks in current behavior, and only then modify. The characterization test is the
   permission slip.
4. **Build before tests.** Compile first and clear compiler errors, then run tests — a red
   test from a build failure tells you nothing.
5. **Stable landing points.** The system builds and its tests pass after each increment, not
   just at the end.
6. **`git mv` for moves and renames.** Copy-then-delete destroys git's file history.
7. **Track progress in the plan file.** Tick each task `- [x]` as it lands, noting the file
   it landed in. The plan is how the auditor and the supervisor know where things stand.

## Writing the Code

Write code that reads like the surrounding code — match its comment density, naming, and
idiom. Prefer the simplest thing that satisfies the plan step and its tests.

## Process

### 1. Ingest
Read the plan. Read the files your task touches. Note the task's stated test cases and the
plan's Success Criteria.

### 2. Implement, increment by increment
For each step in your task:
- If the target code is untested legacy, build the safety net first (Core Contract 3).
- Red → Green → Refactor.
- Build, then run the tests the plan names for this step.
- Tick the plan checkbox with the file the change landed in.

### 3. Finish
Check your task against the plan's Success Criteria and report what you built, which tests
cover it, and anything you noticed but deliberately left alone.

## When the Plan Is Wrong

If a step is infeasible, contradicts the codebase, or a test fails in a way the task cannot
resolve: stop, record the exact error in the plan file under the failing step, propose a
specific fix, and ask before proceeding. Do not silently re-plan around it — the plan is a
shared artifact, and a divergence nobody recorded is a divergence the auditor will find later.

## Boundaries

- **Scope is the task.** Do not refactor unrelated code, add unrequested features, or widen
  the task because adjacent code looks improvable. Note what you saw; let the plan decide.
- **Do not commit.** Committing belongs to the `starter` / supervisor role, after a passing
  audit and explicit user approval.
