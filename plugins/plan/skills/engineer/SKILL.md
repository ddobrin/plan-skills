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

### 1. Ingest (Single Parallel Turn)
In Turn 1, read the plan (`plan.md`) and all target source/test files your assigned task touches in a **single parallel `view_file` batch** (when the dispatch prompt names the target files from the plan). Note the task's stated test cases and the plan's Success Criteria, and proceed directly into implementation without pausing for confirmation when the plan path and `Task {X.Y}` were specified in your dispatch.

### 2. Implement, increment by increment
For each step in your task:
- If the target code is untested legacy, build the safety net first (Core Contract 3).
- Red → Green → Refactor.
- Run the build and the tests the plan names in a single combined `run_command` shell invocation (`<build_cmd> && <test_cmd>`).

### 3. Finish & Coalesced Plan Update
- Once all steps in your assigned task pass their build and test verification, tick your task's checkbox(es) (`- [x]`) and step annotations in `plan.md` in a **single atomic `replace_file_content` call** (coalescing `plan.md` writes to task completion prevents write contention when up to 4 `engineer` subagents execute in parallel on the same `plan.md`).
- Check your task against the plan's Success Criteria and report what you built, which tests cover it, and anything you noticed but deliberately left alone.

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
