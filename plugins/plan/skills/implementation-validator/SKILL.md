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
Pick **Finding-Hunt Template** or **Claim-Refutation Template** below. Keep the
default-to-reject and "final message MUST be JSON" clauses verbatim.

### 3. Dispatch 3 skeptics in parallel
Make **three `Agent` calls in a single message**, `subagent_type: "general-purpose"`
(it can run `git diff` and read files). Independent runs, no shared scratchpad.

> **Perspective-diverse variant:** instead of three identical skeptics, give each a distinct lens — e.g. one `correctness`, one `concurrency`, one `failure-paths`. Diversity catches failure modes that three identical refuters would all miss together. Then the "majority" becomes "≥2 lenses independently land on the same defect."

### 4. Collect verdicts
Parse each agent's fenced JSON. Re-dispatch any agent that returns prose.

### 5. Dedup by identity
**This is the hard part.** Group findings by a stable identity: `file:location` + the
`id` slug. Three skeptics will phrase "NPE on empty list in `parseTasks`" three ways; if
you tally on raw text, nothing reaches quorum. Normalize to `file:line::id` before counting.

### 6. Apply the majority gate + severity calibration
- **Finding-hunt:** a finding is **confirmed** when **≥ 2 of 3** skeptics report it with `isReal=true`. Its severity is the **most common `correctedSeverity`** among the agreeing skeptics (tie → higher).
- **Claim-refutation:** a claim **survives** when **≥ 2 of 3** skeptics return `refuted=false`. A claim **fails** (the code is broken) when ≥2 return `refuted=true` — those become defects to fix.
- **Unconfirmed (1 vote):** never silently drop. List under "Unconfirmed (FYI)".

> **Tuning the gate:** 2-of-3 is the default. For a security-critical change, drop to **any-one** so a single skeptic's real catch isn't lost. When fix-churn is expensive, raise to **unanimous**.

### 7. Act
- Fix **confirmed** defects (and **failed claims**) at their calibrated severity, highest first.
- Surface **unconfirmed** findings for human eyeballing.
- Report the calibration explicitly: "3 findings claimed Critical; all 3 confirmed real but downgraded to High because impact is conditional on concurrent requests." This is the single most useful sentence the panel produces — see Calibration Note.

## Finding-Hunt Template (default)

Dispatch **three times, unchanged**. Replace `{DESCRIPTION}`, `{BASE_SHA}`, `{HEAD_SHA}`.

```
You are an adversarial implementation verifier. Your job is to BREAK this change, not to
approve it. Read the diff and the surrounding code, then construct the inputs or sequences
that make it misbehave.

WHAT THE CHANGE CLAIMS TO DO:
{DESCRIPTION}

DIFF TO ATTACK:
  git diff --stat {BASE_SHA}..{HEAD_SHA}
  git diff {BASE_SHA}..{HEAD_SHA}
Read any file in the repo you need to understand the blast radius.

Hunt across these categories:
- Claim vs. reality: the code does not actually do what it claims.
- Failure paths: error/empty/timeout path broken or silently swallowing errors.
- Edge cases: empty, null, zero, negative, huge, duplicate, unicode, off-by-one.
- Concurrency: shared mutable state, non-atomic read-modify-write, cross-request races.
- Resource/correctness: leaks, unbounded growth, wrong math/comparison, lost precision.
- Regression: a caller or contract the diff silently broke.

Be skeptical. DEFAULT isReal=false: report a finding as real ONLY if you can ground it in
the actual code. If a concern is purely stylistic, cannot be confirmed in the source, or
relies on a misreading, set isReal=false and say why.

Assign each finding a STABLE id: a short kebab-case slug (e.g. "empty-list-npe",
"singleton-cursor-race"). Two reviewers finding the same defect should plausibly choose
the same slug. Calibrate severity HONESTLY: critical = unconditional data loss/corruption
or broken core function on every run; high = serious but conditional (e.g. only under
concurrency); medium = real but narrow; low = minor.

Your final message MUST be exactly one fenced JSON block and nothing else, matching:

```json
{
  "findings": [
    {
      "id": "kebab-case-stable-slug",
      "title": "short description of the defect",
      "file": "path relative to repo root",
      "location": "line number(s) or method/class",
      "isReal": true,
      "confidence": "high|medium|low",
      "correctedSeverity": "critical|high|medium|low",
      "attack": "the input/sequence/edge case that triggers it",
      "evidence": "file:line and the specific code that proves it",
      "reasoning": "why it breaks (or, if isReal=false, why it does not)",
      "fix": "concrete remediation"
    }
  ],
  "attacks_that_failed": ["short note for each serious attack that did NOT find a defect"]
}
```
```

## Claim-Refutation Template (variant)

When you have explicit acceptance claims, dispatch this **three times per claim**
(or once with the full claim list). Replace `{CLAIM}`, `{DESCRIPTION}`, `{BASE_SHA}`, `{HEAD_SHA}`.

```
You are an adversarial verifier. The implementer claims:

  "{CLAIM}"

Your job is to REFUTE this claim. Read the diff (git diff {BASE_SHA}..{HEAD_SHA}) and the
surrounding code, then construct the input, sequence, or edge case that makes the claim
false. Consider the failure path, not just the happy path; consider concurrency and
boundary inputs.

CONTEXT — what the change claims overall:
{DESCRIPTION}

Be skeptical. DEFAULT refuted=true. You may only return refuted=false if you ACTIVELY
tried to break the claim and could not — and you must describe what you tried.

Your final message MUST be exactly one fenced JSON block and nothing else, matching:

```json
{
  "claim": "the claim verbatim",
  "refuted": true,
  "confidence": "high|medium|low",
  "correctedSeverity": "critical|high|medium|low",
  "attack": "the input/sequence you used to break it (or tried, if not refuted)",
  "evidence": "file:line proving the refutation (or proving robustness)",
  "reasoning": "why the claim fails or holds, citing the actual code"
}
```
```

## Output Contract

The orchestrator aggregates skeptic JSON into:

```json
{
  "confirmed":   [ { "id": "...", "votes": 2, "file": "...", "location": "...", "severity": "high", "fix": "..." } ],
  "unconfirmed": [ { "id": "...", "votes": 1, "...": "..." } ],
  "failed_claims": [ { "claim": "...", "refuted_by": 2, "severity": "high" } ],
  "calibration": [ { "id": "...", "claimedSeverity": "critical", "correctedSeverity": "high", "why": "conditional on concurrency" } ]
}
```

## Worked Example

> Change claims: *"Planner walks precompiled steps; safe under concurrent deliberations."*
> Finding-hunt, 3 skeptics over `git diff origin/main..HEAD`.

After dedup + majority gate + calibration:

**Confirmed (≥2 votes):**
- `singleton-cursor-race` (3 votes) — claimed **critical** by the skeptics, **corrected to high**. The planner is a shared singleton with non-volatile `cursor`/`steps` instance fields mutated per run (`Planner.java:59-64`, non-atomic `cursor++` at `:306`). One verifier narrowed it: intra-request replan is serialized, so the race is **strictly cross-request**, not within one deliberation — which is why "critical" (implying unconditional corruption) was an overstatement. Fix: make planner request-scoped or move per-run state out of the bean.

**Unconfirmed (1 vote, FYI):**
- `objectmapper-dup` (1 vote, low) — duplicated `ObjectMapper`/serialization. Surfaced, not blocking.

**Calibration reported to the user:** *"1 finding claimed Critical; confirmed real by all 3 skeptics but downgraded to High — impact is gated on concurrent requests, not every run."*

## Red Flags

| Thought | Reality |
|---|---|
| "The diff is small, one reviewer is enough." | Small diffs hide concurrency and failure-path bugs. Run the panel. |
| "All three rated it Critical, so it's Critical." | Check the *corrected* severity and the reasoning — adversarial framing over-rates. Calibration is the point. |
| "One skeptic flagged a race, two didn't." | Concurrency bugs are easy to miss. Keep it unconfirmed and look at the evidence. |
| "I'll tally findings by their titles." | Titles differ across agents. Normalize to `file:line::id` or quorum never forms. |
| "The agent said it's broken — fix it." | Read the cited `evidence` first. A finding without a real `file:line` is a guess, not a defect. |
| "I verified the code, so the feature works." | This skill reasons about code; it does not run the app. For runtime confirmation, do a manual `verify` pass too. |

## Calibration Note

Your own past runs show the highest-value output of this stage is **severity calibration,
not deletion**. In a real review, three findings entered at **Critical** and *all three
survived as real* — but every one was **downgraded to High** because the impact was
conditional (a cross-request race on a singleton, not corruption on every call). Zero were
deleted; zero stayed Critical. That Critical→High move is the signal: it separates
"guaranteed on every call" from "serious but gated," which is exactly what a single
aggressive reviewer gets wrong. Always surface the calibration delta to the user — it is
more decision-useful than the raw verdict.
