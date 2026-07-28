---
name: spec-validator
description: Use after a spec or design doc is drafted and BEFORE writing an implementation plan, to find defects while they are still cheap to fix. Dispatches independent skeptic agents that attack the spec for ambiguity, missing or contradictory requirements, and untestable acceptance criteria, then keeps only findings confirmed by a 2-of-3 majority. Symptoms - "validate this spec", "poke holes in this design", "is this spec ready to plan against", finishing brainstorming before writing-plans, a freshly written specs/*.md.
---

# Adversarial Spec Validation

## Overview

Dispatch a panel of independent **skeptic** agents whose only job is to break a spec
*before* anyone writes a plan or code against it. At spec stage there is no code to test,
so the attack surface is the **language of the spec itself**: ambiguity, gaps,
contradictions, and acceptance criteria that cannot actually be verified.

A skeptic plays the role of a hostile or careless implementer who will satisfy the
*letter* of the spec while violating its *intent*. Anything they can twist is a defect
in the spec, not the implementer.

**Announce at start:** "I'm using the spec-validator skill to attack this spec with an independent skeptic panel."

## When to Use

- A spec / design doc exists (spec.md) and you are about to write an implementation plan.
- The user asks to "validate", "stress-test", "poke holes in", or "review" a spec or design.
- You are the author and want an independent perspective uncontaminated by your own reasoning.

## When NOT to Use

- There is no written spec yet — brainstorm first.
- The artifact is a plan (use `plan-validator`) or code (use `implementation-validator`).
- A one-line, unambiguous change where the spec is a single sentence — overhead exceeds benefit.

## Core Principle

Three things turn an ordinary review into adversarial findings. All three are required:

1. **Adversarial framing** — the agent's success metric is "how many real holes did I find," not "is this good." It is told to *break* the spec, not evaluate it.
2. **Default-to-reject** — uncertainty resolves *against* the spec. Returning "looks complete" is a failed review unless the agent lists what it attacked and why each attack failed.
3. **Independent quorum** — run **N = 3** skeptics that never see each other's output, then keep only findings confirmed by a **majority (2 of 3)**.

Never tell a skeptic to be conservative or to report only what matters. A review prompt
that asks for restraint gets restraint: the model reports *less*, and what it drops is not
reliably the noise. Recall is the skeptic's job; precision is the gate's.

## Attack Surface (what each skeptic hunts for)

- **Ambiguity** — a requirement that can be read two ways; pick the worse reading and show the harm.
- **Missing requirements** — error behavior, empty/null/huge inputs, concurrency/ordering, auth, limits, units, time zones.
- **Contradictions** — two sections that cannot both be satisfied; the architecture not matching the feature description.
- **Untestable acceptance criteria** — "fast", "robust", "user-friendly" with no measurable threshold.
- **Malicious compliance** — the laziest implementation that passes every stated criterion yet is useless.

## Process

### 1. Gather inputs
- The spec text (paste it into each prompt, or give an absolute path the agents can read).
- Any context the spec depends on but does not restate (linked docs, constraints).

### 2. Author the skeptic prompt
Fill the template in `references/skeptic-prompt.md`, which also carries the aggregation
**Output Contract**.

### 3. Dispatch 3 skeptics in parallel
Make **three `Agent` calls in a single message** so they run concurrently and independently.
Use `subagent_type: "general-purpose"` (or `"Explore"` if the spec lives in files they must
read). Do **not** let them share a scratchpad — independence is what makes the vote mean
something.

> **Panel cost.** Review accuracy holds up well below the top model tier, so a routine
> pre-planning gate does not need the most expensive panel you can build — pass
> `model: "sonnet"` for the skeptics and reserve the default for a security-sensitive spec
> or a re-run after a material rewrite. A panel cheap enough to run every time beats a
> thorough one that gets skipped. (In a `Workflow` script, the same lever is
> `effort: "low"` / `"medium"` on `agent()`; the `Agent` tool exposes `model` only.)

### 4. Collect verdicts
Each agent's final message is a fenced JSON block. Parse all three. If an agent returns
prose instead of JSON, re-dispatch that one — do not hand-guess its findings.

### 5. Dedup by identity
Three skeptics will phrase the same hole three different ways. Group findings by a **stable
identity**, not by exact wording: `id` (a kebab-case slug each agent assigns) plus the
quoted `clause`. If you tally on raw text you get three 1-vote findings and nothing reaches
quorum.

### 6. Apply the majority gate
- **Confirmed:** appears in **≥ 2 of 3** outputs.
- **Single vote:** appears in exactly one. These go to the **Single-Vote Findings (triage
  required)** section and each one needs an explicit decision — tightened, accepted as
  intended behavior, or refuted with a reason. A lone finding from a current-generation
  skeptic is more often a real hole one reviewer happened to reach than noise, so "only one
  agent saw it" is not a reason to close it. Spec holes are the cheapest defects in the
  lifecycle to fix and the most expensive to discover later.
- Severity: most common among agreeing skeptics; tie → higher.

> **Tuning the gate:** 2-of-3 is the default. For a high-stakes or security-sensitive spec, drop to **any-one** (1 of 3) for maximum recall and triage the tail yourself. When fix-churn is expensive, raise to **unanimous** (3 of 3).

### 7. Persist the review
Write the aggregated result as a Markdown report to
`plans/active_milestones/{moniker}/adversarial-reviews/spec-validation.md` (create the
folder if it does not exist). Derive `{moniker}` from the spec's path — the spec you
reviewed lives at `plans/active_milestones/{moniker}/spec.md`; if you were handed a bare
spec with no milestone, write to `plans/adversarial-reviews/spec-validation.md` and say so.
**Always write this file, even on a clean pass** — "zero confirmed findings, here is what
was attacked" is itself the evidence the gate produced. A re-run after a material revision
goes to `spec-validation-r2.md`, `-r3.md`, … so every round is preserved for comparison.

Fill the template in `references/review-template.md`. See `references/worked-example.md`
for a complete run.

### 8. Act
- For each **confirmed** finding, apply its `tightening` to the spec (or surface it to the user if it changes intent).
- **Triage every single-vote finding** and record the decision in the review.
- If you rewrote the spec materially, re-run the panel once on the revision.
- Tick the **Actions Taken** checklist in the review file as you apply each fix.

## Red Flags

| Thought | Reality |
|---|---|
| "The spec looks thorough, one skeptic is enough." | One agent trends toward agreement. The vote needs ≥3 independent runs. |
| "I'll let the three agents collaborate." | Shared context collapses them toward consensus; the vote becomes meaningless. |
| "Only 1 skeptic flagged it, so ignore it." | Wrong default. Modern skeptics are precise; the lone finding is usually real. Triage it and record the decision. |
| "I'll tell them to only report the serious stuff." | The model will comply and report less. Ask for everything; filter at the gate. |
| "I'll paraphrase their findings together." | Dedup on stable `id` + quoted clause, not by re-summarizing — or real holes vanish in the merge. |
| "An agent returned prose, I'll interpret it." | Re-dispatch for valid JSON. Don't guess the contract. |

## Calibration Note

The quorum's value is not only deletion. Skeptics frequently *over*-rate severity under
adversarial framing. When agreeing skeptics disagree on severity, the aggregation step is
doing real work: a hole two reviewers call "high" and one calls "medium" lands at high,
but the spread itself tells you the finding is real and the impact is debatable — worth a
sentence to the user rather than a silent edit.

Note what the quorum is and is not for. It is a *ranking* device — it tells you which
findings two independent readers reached, and those go first. It is not a filter that makes
the rest disappear. Read the evidence, not the vote count.
