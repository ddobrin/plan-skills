---
name: implementation-validator
description: Use after code is written and before merge, to confirm the implementation actually does what it claims. Dispatches independent skeptic agents that read the diff and surrounding code with a default-to-reject posture, hunt for real defects (or refute explicit acceptance claims), and assign a corrected severity — keeping only findings confirmed by a 2-of-3 majority. Symptoms - "validate this implementation", "did this actually work", "review this diff adversarially", "verify these findings are real", after completing a feature/task, before merging to main.
---

# Adversarial Implementation Validation

## Overview

Dispatch a panel of independent **skeptic** agents that read a diff (and the code around
it) trying to **break** the implementation, not bless it. This is the stage where
adversarial verification earns its keep twice over: it culls plausible-but-wrong findings,
**and** it *calibrates severity* — a defect three reviewers agree is real may still be
over-rated, and the corrected severity is part of the output.

Two modes, same machinery:

- **Finding-hunt (default):** each skeptic independently hunts the diff for defects with a default-to-reject posture. Best when you want "what's broken in this change."
- **Claim-refutation (variant):** you supply explicit acceptance claims (e.g. from the spec's acceptance criteria) and each skeptic tries to *refute* each one. Best when you have a checklist the code must satisfy.

**Announce at start:** "I'm using the implementation-validator skill to attack this diff with an independent skeptic panel."

## When to Use

- A change is complete (a diff, a finished task, a feature branch) and you want it validated before merge.
- The user asks to "validate", "verify", "adversarially review", or "confirm" an implementation.
- You already have candidate findings (from a prior reviewer) and want them adversarially verified before acting.

## When NOT to Use

- The artifact is a spec (use `spec-validator`) or a plan (use `plan-validator`).
- A trivial diff (typo, comment, version bump) — overhead exceeds benefit.
- You need to confirm the app *runs* end-to-end — that's a manual/`verify`-style task; this skill reasons about the code, it does not launch the app.

## Core Principle

Three things turn an ordinary review into adversarial findings. All three are required:

1. **Adversarial framing** — the agent's job is to construct the input or sequence that breaks the code, not to judge whether it "looks good."
2. **Default-to-reject** — for finding-hunt, default `isReal=false` (only confirmed, code-grounded defects count). For claim-refutation, default `refuted=true` (a claim survives only if the agent actively tried and failed to break it).
3. **Independent quorum** — run **N = 3** skeptics that never see each other's output, then keep only findings confirmed by a **majority (2 of 3)**.

Default-to-reject is a demand for **evidence**, not for restraint. It asks the skeptic to
ground every claim in a real `file:line`; it does not ask for a shorter list. Never tell a
skeptic to be conservative or to report only what matters — a review prompt that asks for
restraint gets restraint, the model reports *less*, and what it drops is not reliably the
noise. Recall is the skeptic's job; precision is the gate's.

## Attack Surface (what each skeptic hunts for)

- **Claim vs. reality** — the code does not actually do what the diff/PR/commit message says.
- **Failure paths** — the happy path works but the error/empty/timeout path is broken or swallows errors silently.
- **Edge cases** — empty, null, zero, negative, huge, duplicate, unicode, boundary-off-by-one inputs.
- **Concurrency** — shared mutable state on a singleton/shared instance, non-atomic read-modify-write, races across requests (see Calibration Note — this is the classic over-rated category).
- **Resource / correctness** — leaks, unbounded growth, incorrect math, wrong comparison, lost precision.
- **Regression** — a caller or contract the diff silently broke.

## Process

### 1. Gather inputs
- The diff range: `BASE_SHA` and `HEAD_SHA` (so agents can run `git diff {BASE}..{HEAD}`).
- A one-line description of what the change *claims* to do.
- For claim-refutation mode: the explicit list of acceptance claims.

Get the SHAs:
```bash
BASE_SHA=$(git rev-parse origin/main)   # or HEAD~1, or the branch point
HEAD_SHA=$(git rev-parse HEAD)
```

### 2. Author the skeptic prompt
Pick the **Finding-Hunt** or **Claim-Refutation** template in
`references/skeptic-prompts.md`, which also carries the aggregation **Output Contract**.

### 3. Dispatch 3 skeptics in parallel
Make **three `Agent` calls in a single message**, `subagent_type: "general-purpose"`
(it can run `git diff` and read files). Independent runs, no shared scratchpad.

> **Perspective-diverse variant:** instead of three identical skeptics, give each a distinct lens — e.g. one `correctness`, one `concurrency`, one `failure-paths`. Diversity catches failure modes that three identical refuters would all miss together. Then the "majority" becomes "≥2 lenses independently land on the same defect."

> **Panel cost.** Review accuracy holds up well below the top model tier, so a routine
> pre-merge gate does not need the most expensive panel you can build — pass
> `model: "sonnet"` for the skeptics and reserve the default for security-sensitive
> changes, concurrency-heavy diffs, or a re-validation after fixes. A panel cheap enough to
> run on every branch beats a thorough one that gets skipped. (In a `Workflow` script, the
> same lever is `effort: "low"` / `"medium"` on `agent()`; the `Agent` tool exposes `model`
> only.)

### 4. Collect verdicts
Parse each agent's fenced JSON. Re-dispatch any agent that returns prose.

### 5. Dedup by identity
**This is the hard part.** Group findings by a stable identity: `file:location` + the
`id` slug. Three skeptics will phrase "NPE on empty list in `parseTasks`" three ways; if
you tally on raw text, nothing reaches quorum. Normalize to `file:line::id` before counting.

### 6. Apply the majority gate + severity calibration
- **Finding-hunt:** a finding is **confirmed** when **≥ 2 of 3** skeptics report it with `isReal=true`. Its severity is the **most common `correctedSeverity`** among the agreeing skeptics (tie → higher).
- **Claim-refutation:** a claim **survives** when **≥ 2 of 3** skeptics return `refuted=false`. A claim **fails** (the code is broken) when ≥2 return `refuted=true` — those become defects to fix.
- **Single vote:** appears in exactly one output. These go to the **Single-Vote Findings
  (triage required)** section and each one needs an explicit decision — fixed, accepted as a
  known risk, or refuted with a reason. A lone finding from a current-generation skeptic is
  more often a real defect one reviewer happened to reach than noise, and concurrency and
  failure-path bugs are exactly the kind two of three readers miss.

> **Tuning the gate:** 2-of-3 is the default. For a security-critical change, drop to **any-one** so a single skeptic's real catch isn't lost. When fix-churn is expensive, raise to **unanimous**.

### 7. Persist the review
Write the aggregated result as a Markdown report to
`plans/active_milestones/{moniker}/adversarial-reviews/implementation-validation.md`
(create the folder if it does not exist). `{moniker}` is the active milestone whose
`plan.md`/`spec.md` this diff implements — the orchestrator knows it; if the diff belongs
to no milestone, write to `plans/adversarial-reviews/implementation-validation.md` and say
so. **Always write this file, even on a clean pass** — "zero confirmed defects, here is
what was attacked" is the evidence the gate produced, and the **severity calibration**
table is the highest-value thing this stage emits. A re-validation after fixes goes to
`implementation-validation-r2.md`, `-r3.md`, … so each round is preserved.

Fill the template in `references/review-template.md`. See `references/worked-example.md`
for a complete run.

### 8. Act
- Fix **confirmed** defects (and **failed claims**) at their calibrated severity, highest first.
- **Triage every single-vote finding** and record the decision in the review.
- Report the calibration explicitly: "3 findings claimed Critical; all 3 confirmed real but downgraded to High because impact is conditional on concurrent requests." This is the single most useful sentence the panel produces — see Calibration Note.
- Tick the **Actions Taken** checklist in the review file as you fix each defect.

## Red Flags

| Thought | Reality |
|---|---|
| "The diff is small, one reviewer is enough." | Small diffs hide concurrency and failure-path bugs. Run the panel. |
| "All three rated it Critical, so it's Critical." | Check the *corrected* severity and the reasoning — adversarial framing over-rates. Calibration is the point. |
| "One skeptic flagged a race, two didn't." | Concurrency bugs are the easiest to miss and the lone finding is usually real. Read the evidence and record a decision. |
| "I'll tell them to only report the serious stuff." | The model will comply and report less. Ask for everything; filter at the gate. |
| "I'll tally findings by their titles." | Titles differ across agents. Normalize to `file:line::id` or quorum never forms. |
| "The agent said it's broken — fix it." | Read the cited `evidence` first. A finding without a real `file:line` is a guess, not a defect. |
| "I verified the code, so the feature works." | This skill reasons about code; it does not run the app. For runtime confirmation, do a manual `verify` pass too. |

## Calibration Note

Past runs show the highest-value output of this stage is **severity calibration, not
deletion**. In a real review, three findings entered at **Critical** and *all three survived
as real* — but every one was **downgraded to High** because the impact was conditional (a
cross-request race on a singleton, not corruption on every call). Zero were deleted; zero
stayed Critical. That Critical→High move is the signal: it separates "guaranteed on every
call" from "serious but gated," which is exactly what a single aggressive reviewer gets
wrong. Always surface the calibration delta to the user — it is more decision-useful than
the raw verdict.

The same asymmetry explains what the quorum is for. It is a *ranking* device — it tells you
which defects two independent readers reached, and those go first. It is not a filter that
makes the rest disappear. Read the evidence, not the vote count.
