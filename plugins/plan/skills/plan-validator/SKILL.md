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

- A written implementation plan exists (e.g. from `architect` or `superpowers:writing-plans`) and you are about to execute it.
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

Never tell a skeptic to be conservative or to report only what matters. A review prompt
that asks for restraint gets restraint: the model reports *less*, and what it drops is not
reliably the noise. Recall is the skeptic's job; precision is the gate's.

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
Fill the template in `references/skeptic-prompt.md`, which also carries the aggregation
**Output Contract**.

### 3. Dispatch 3 skeptics in parallel
Make **three `Agent` calls in a single message**. Use `subagent_type: "general-purpose"`
(it can read and grep the codebase). Each runs independently — no shared scratchpad.

> **Panel cost.** Review accuracy holds up well below the top model tier, so a routine
> pre-execution gate does not need the most expensive panel you can build — pass
> `model: "sonnet"` for the skeptics and reserve the default for irreversible migrations,
> security-sensitive plans, or a re-run after a material reorder. A panel cheap enough to
> run every time beats a thorough one that gets skipped. (In a `Workflow` script, the same
> lever is `effort: "low"` / `"medium"` on `agent()`; the `Agent` tool exposes `model` only.)

### 4. Collect verdicts
Parse each agent's fenced JSON. Re-dispatch any agent that returns prose instead of JSON.

### 5. Dedup by identity
Group findings by stable `id` + the `step` they target. Two skeptics describing the same
ordering bug should collapse to one entry, not three.

### 6. Apply the majority gate
- **Confirmed:** appears in **≥ 2 of 3** outputs.
- **Single vote:** appears in exactly one. These go to the **Single-Vote Findings (triage
  required)** section and each one needs an explicit decision — fixed, accepted as a known
  risk, or refuted with a reason. A lone finding from a current-generation skeptic is more
  often a real defect one reviewer happened to reach than noise, so "only one agent saw it"
  is not a reason to close it. Ordering bugs in particular are easy to miss and expensive to hit.
- Severity: most common among agreeing skeptics; tie → higher.

> **Tuning the gate:** 2-of-3 is the default. Drop to **any-one** for a high-risk plan (irreversible migrations, prod data); raise to **unanimous** when re-planning churn is costly.

### 7. Persist the review
Write the aggregated result as a Markdown report to
`plans/active_milestones/{moniker}/adversarial-reviews/plan-validation.md` (create the
folder if it does not exist). Derive `{moniker}` from the plan's path — the plan you
reviewed lives at `plans/active_milestones/{moniker}/plan.md`; if you were handed a bare
plan with no milestone, write to `plans/adversarial-reviews/plan-validation.md` and say so.
**Always write this file, even on a clean pass** — "zero confirmed findings, here are the
assumptions verified" is the evidence the gate produced. A re-run after a material reorder
goes to `plan-validation-r2.md`, `-r3.md`, … so every round is preserved.

Fill the template in `references/review-template.md`. See `references/worked-example.md`
for a complete run.

### 8. Act
- For each **confirmed** finding, apply its `fix` to the plan (reorder steps, add a missing prerequisite step, add a rollback/verify step, correct an assumption).
- **Triage every single-vote finding** and record the decision in the review.
- If you reordered or added steps materially, re-run the panel once.
- Tick the **Actions Taken** checklist in the review file as you apply each fix.

## Red Flags

| Thought | Reality |
|---|---|
| "The plan reads cleanly, it'll be fine." | Clean prose hides dead assumptions. The skeptics must open the files. |
| "The agent says step 3 is wrong but didn't cite a line." | Unverified prediction = guess. Force `file:line` or mark confidence low. |
| "One skeptic found the ordering bug, two didn't — so it's noise." | Wrong default. Modern skeptics are precise; the lone finding is usually real. Triage it and record the decision. |
| "I'll tell them to only report the serious stuff." | The model will comply and report less. Ask for everything; filter at the gate. |
| "I'll let the agents discuss the plan together." | Shared context collapses the vote. Dispatch independently. |
| "I'll merge their findings in my own words." | Dedup on stable `id` + step, or the same bug splits into three sub-quorum entries. |

## Calibration Note

Plan skeptics under adversarial framing sometimes flag a "false assumption" that is
actually correct because they grepped the wrong file or an older copy. This is why the
template demands `evidence: file:line` and a `confidence` field: a `high`-confidence
finding with a concrete line is actionable immediately; a `low`-confidence one without a
citation should be re-checked before you reorder the plan around it.

Note what the quorum is and is not for. It is a *ranking* device — it tells you which
findings two independent readers reached, and those go first. It is not a filter that makes
the rest disappear: an uncorroborated finding with a real `file:line` behind it is a
different object from an uncorroborated guess, and only the citation distinguishes them.
Read the evidence, not the vote count.
