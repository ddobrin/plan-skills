---
name: discovery
description: Use when a context report exists for a request but no validated spec yet — to turn the idea into a rigorous, testable spec and pass it through an adversarial spec gate before any planning begins. Symptoms - "write the spec", "we have research, what's next", supervisor Phase 1, a spec.md that has not yet passed spec-validation.
---

# Phase 1 — Discovery (Spec + Spec Gate)

## Overview
Produce a **validated** `spec.md`. Delegate the authoring to `product-owner` (which grills the user and
writes a Gherkin-testable contract), then **attack the spec** with `spec-validator`. Nothing advances to
planning until the spec gate is clean — *unless* the milestone is trivial.

## Precondition
A Context Report exists at `plans/research/{topic}_context.md` (or the Supervisor has flagged a trivial
fast-path). See Supervisor → Contract 1.

## Inputs
- `plans/research/{topic}_context.md` (the Context Report).

## Steps
1. **Triviality check (Supervisor → Contract 3).** If the milestone is trivial, instruct `product-owner`
   to take its fast-path (record a quick task in `plans/00-ROADMAP.md`, no grilling), **skip the spec
   gate**, and hand off. Otherwise continue.
2. **Delegate `product-owner`** (Supervisor → Contract 2). Provide the Context Report path. It will:
   - run the **Grill Loop** with the user (≤3–5 targeted questions at a time) until ambiguity is gone;
   - assign a milestone `{moniker}` and add it to `plans/00-ROADMAP.md` under a release;
   - move the report to `plans/active_milestones/{moniker}/context.md`;
   - write `plans/active_milestones/{moniker}/spec.md` (Gherkin acceptance criteria + edge cases +
     constraints).
3. **Spec gate (Supervisor → Contract 3).** Delegate `spec-validator` on the new `spec.md`. Aggregate its
   2-of-3 majority verdict and **persist it to** `plans/active_milestones/{moniker}/validation/spec-validation.md`.
   - For each **confirmed** finding, loop back to `product-owner` to apply the finding's `tightening`,
     then **re-run the gate once**.
   - Surface **unconfirmed** findings to the user as FYI.

## Exit Gate
`spec.md` exists **and** `validation/spec-validation.md` records no unresolved confirmed findings
(or the trivial fast-path is documented in the roadmap).

## Hand-off
`planning` reads `plans/active_milestones/{moniker}/spec.md` and `…/context.md`.

## Constraints
- **No architecture or code** — `product-owner` defines *what* and *why*, never *how*.
- **Mandatory testable spec** — acceptance criteria must be Gherkin / measurable before the gate.
- **Gate is mandatory** for complex milestones; only the trivial fast-path skips it.

## Red Flags
| Thought | Reality |
|---|---|
| "The request is clear, skip grilling." | Only the trivial fast-path skips grilling. Complex → grill. |
| "Spec reads well, no need to validate." | Run `spec-validator`. A clean read is not a clean gate. |
| "One skeptic flagged a hole, ignore it." | Confirmed → fix & re-run. Unconfirmed → surface to user. |
| "I'll let the architect handle the vague parts." | Ambiguity is cheapest to kill in the spec. Resolve it here. |
