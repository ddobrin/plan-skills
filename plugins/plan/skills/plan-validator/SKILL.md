---
name: plan-validator
description: Use after an implementation plan is written and BEFORE executing it, to catch ordering bugs and false assumptions while they are still cheap. Dispatches independent skeptic agents that assume the plan WILL fail, read the codebase to check its assumptions, and find the first domino that topples the rest — keeping only findings confirmed by a 2-of-3 majority. Symptoms - "validate this plan", "will this plan work", "review the plan before we start", a freshly written plans/*.md from writing-plans, about to run executing-plans or subagent-driven-development.
---

# Adversarial Plan Validation

## Overview

Dispatch a panel of independent **skeptic** agents that assume the plan **will fail** and
race to predict exactly where and why — *before* a single task runs. Unlike spec
validation, plan skeptics **read the codebase** to check the plan's assumptions against
reality. The highest-value finding is almost always a sequencing or false-assumption bug:
"step 4 modifies a method that step 2 was supposed to create but didn't," or "the plan
says edit `X.dispatch()` but that method does not exist."

**Announce at start:** "I'm using the plan-validator skill to attack this plan with an independent skeptic panel."

## When to Use

- A written implementation plan exists (e.g. from `superpowers:writing-plans`) and you are about to execute it.
- The user asks to "validate", "sanity-check", "stress-test", or "review" a plan before work starts.
- The plan touches existing code whose shape the plan *assumes* — exactly where plans rot.

## When NOT to Use

- The artifact is a spec (use `spec-validator`) or already-written code (use `implementation-validator`).
- A trivial one-step plan with no dependencies and no assumptions about existing code.
- No plan exists yet — write one first.

## Core Principle

Three things turn an ordinary review into adversarial findings. All three are required:

1. **Adversarial framing** — the agent assumes the plan fails and hunts for the failure, rather than judging whether it "seems reasonable."
2. **Default-to-reject** — uncertainty about whether a step is safe resolves *against* the plan. "Looks fine" is a failed review unless the agent shows what it verified.
3. **Independent quorum** — run **N = 3** skeptics that never see each other's output, then keep only findings confirmed by a **majority (2 of 3)**.

The difference from spec stage: plan skeptics must **verify assumptions in the source**.
A predicted failure that the agent did not check against the actual code is a guess, not a
finding — the template forces them to cite `file:line`.

## Attack Surface (what each skeptic hunts for)

- **Ordering / dependency bugs** — step N needs an artifact that step N+M produces; two steps mutate the same file with no merge plan.
- **False assumptions about existing code** — the plan names a function, file, field, table, flag, or signature that does not exist or differs. **Verify by reading the repo.**
- **Unverifiable "verify" steps** — a step that says "verify it works" with no command, test, or observable signal.
- **No rollback** — a step that cannot be undone if the next step fails (irreversible migration, deleted data, force-push).
- **Missing migration / compatibility** — schema or API change with no backfill, versioning, or backward-compat path.
- **Hidden coupling** — a "simple" edit that fans out to callers the plan never mentions.

## Process

### 1. Gather inputs
- The plan text (paste it, or give an absolute path).
- The **repository root** the agents should read — they must be able to open the files the plan touches.

### 2. Author the skeptic prompt
Fill the template in **Skeptic Prompt Template**. Keep the "default to reject", "verify in
source", and "final message MUST be JSON" clauses verbatim.

### 3. Dispatch 3 skeptics in parallel
Make **three `Agent` calls in a single message**. Use `subagent_type: "general-purpose"`
(it can read and grep the codebase). Each runs independently — no shared scratchpad.

### 4. Collect verdicts
Parse each agent's fenced JSON. Re-dispatch any agent that returns prose instead of JSON.

### 5. Dedup by identity
Group findings by stable `id` + the `step` they target. Two skeptics describing the same
ordering bug should collapse to one entry, not three.

### 6. Apply the majority gate
- **Confirmed:** appears in **≥ 2 of 3** outputs.
- **Unconfirmed (1 vote):** keep under "Unconfirmed (FYI)" — never silently drop.
- Severity: most common among agreeing skeptics; tie → higher.

> **Tuning the gate:** 2-of-3 is the default. Drop to **any-one** for a high-risk plan (irreversible migrations, prod data); raise to **unanimous** when re-planning churn is costly.

### 7. Act
- For each **confirmed** finding, apply its `fix` to the plan (reorder steps, add a missing prerequisite step, add a rollback/verify step, correct an assumption).
- List **unconfirmed** findings for the user.
- If you reordered or added steps materially, re-run the panel once.

## Skeptic Prompt Template

Dispatch this **three times, unchanged**, via the `Agent` tool. Replace only `{PLAN}`
and `{REPO_ROOT}`.

```
You are an adversarial plan reviewer. Assume this implementation plan WILL fail. Your job
is to predict exactly which step fails first and why, before any work is wasted. You have
read access to the codebase — USE IT to check every assumption the plan makes.

PLAN:
{PLAN}

REPOSITORY ROOT (read any file you need to verify the plan's assumptions):
{REPO_ROOT}

Attack each step across these categories:
- Ordering/dependency: step N needs an artifact a later step produces; two steps touch
  the same file with no merge plan.
- False assumption about existing code: the plan names a function/file/field/table/flag/
  signature that does not exist or differs. OPEN THE FILE AND CHECK.
- Unverifiable step: "verify it works" with no command, test, or observable signal.
- No rollback: a step that cannot be undone if the next step fails.
- Missing migration/compatibility: schema or API change with no backfill/versioning/
  backward-compat path.
- Hidden coupling: a "simple" edit that fans out to callers the plan never mentions.

Be skeptical. DEFAULT TO REJECT: if you cannot confirm a step is safe, report it. A
predicted failure you did NOT verify in the source is a guess — either verify it and cite
file:line, or label confidence "low".

Find the FIRST domino: the earliest step whose failure invalidates the steps after it.

For each finding assign a STABLE id: a short kebab-case slug (e.g.
"step4-method-missing", "no-rollback-on-migrate"). Two reviewers finding the same problem
should plausibly choose the same slug.

Your final message MUST be exactly one fenced JSON block and nothing else, matching:

```json
{
  "findings": [
    {
      "id": "kebab-case-stable-slug",
      "step": "the plan step number and/or title this concerns",
      "category": "ordering|false-assumption|unverifiable|no-rollback|missing-migration|hidden-coupling|other",
      "failure": "the concrete scenario in which the plan breaks",
      "evidence": "file:line you read, or verbatim plan text, proving it",
      "confidence": "high|medium|low",
      "severity": "high|medium|low",
      "fix": "the concrete change to the plan that prevents the failure"
    }
  ],
  "first_domino": "the id of the earliest finding that invalidates later steps, or null",
  "checks_that_passed": ["short note for each assumption you verified that DID hold"]
}
```
```

## Output Contract

Each skeptic returns the JSON above. The orchestrator aggregates into:

```json
{
  "confirmed": [ { "id": "...", "votes": 2, "step": "...", "severity": "high", "fix": "..." } ],
  "unconfirmed": [ { "id": "...", "votes": 1, "...": "..." } ],
  "first_domino": "id voted most often as the earliest blocking failure"
}
```

## Worked Example

> Plan excerpt: *"Step 2: add `retryCount` to the `Job` record. Step 3: update `JobScheduler.dispatch()` to read `retryCount`. Step 4: migrate existing rows."*

Three skeptics read the repo. After dedup + majority gate:

**Confirmed (≥2 votes):**
- `dispatch-signature-missing` (3 votes, high) — `JobScheduler` has no `dispatch()`; the method is `schedule(Job)` (`scheduler/JobScheduler.java:88`). Fix: retarget step 3 to `schedule()`.
- `migrate-before-default` (2 votes, high) — step 4 migrates rows but no step gives `retryCount` a default, so step 3 NPEs on legacy rows between deploy and migration. Fix: add "step 2b: default `retryCount` to 0" *before* step 3; mark step 3 as requiring 2b.
- `first_domino` = `migrate-before-default`.

**Unconfirmed (1 vote, FYI):**
- `no-rollback-on-migrate` (1 vote, medium) — step 4 has no down-migration. Surfaced for the user.

The plan is reordered and the missing default step inserted before execution begins.

## Red Flags

| Thought | Reality |
|---|---|
| "The plan reads cleanly, it'll be fine." | Clean prose hides dead assumptions. The skeptics must open the files. |
| "The agent says step 3 is wrong but didn't cite a line." | Unverified prediction = guess. Force `file:line` or mark confidence low. |
| "One skeptic found the ordering bug, two didn't." | Keep it unconfirmed and look — ordering bugs are easy to miss and costly to hit. |
| "I'll let the agents discuss the plan together." | Shared context collapses the vote. Dispatch independently. |
| "I'll merge their findings in my own words." | Dedup on stable `id` + step, or the same bug splits into three sub-quorum entries. |

## Calibration Note

Plan skeptics under adversarial framing sometimes flag a "false assumption" that is
actually correct because they grepped the wrong file or an older copy. This is why the
template demands `evidence: file:line` and a `confidence` field: a `high`-confidence
finding with a concrete line is actionable immediately; a `low`-confidence one without a
citation should be re-checked before you reorder the plan around it. The quorum plus the
evidence requirement together filter the "confidently wrong" finding that a single
aggressive reviewer would otherwise produce.
