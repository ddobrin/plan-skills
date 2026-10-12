---
name: implementation-validator
description: Use after code is written and before merge, to confirm the implementation actually does what it claims. Dispatches independent skeptic agents that read the diff and surrounding code with a default-to-reject posture, hunt for real defects (or refute explicit acceptance claims), and assign a corrected severity — keeping only findings confirmed by a 2-of-3 majority. Symptoms - "validate this implementation", "did this actually work", "review this diff adversarially", "verify these findings are real", after completing a feature/task, before merging to main.
tools:
  - run_command
  - invoke_subagent
  - view_file
  - write_to_file
  - replace_file_content
  - multi_replace_file_content
  - list_dir
  - find_by_name
  - grep_search
x-plan-model: opus-5.5-high         # EXACT model for whoever runs this role (effort = suffix); honored by swarm dispatch
x-plan-tier: pro                    # fallback tier when exact pinning is unavailable
x-plan-panel:
  mode: lens-per-model             # lens-per-model (N = seats) | matrix (every seat prompt x every seat model)
  gate: majority                   # majority of N | any-one | unanimous
x-plan-seats:                      # one swarm worker per seat; all seats use the identical prompt template
  - { lens: claim-vs-reality, model: opus-5.5-high,         tier: pro }
  - { lens: failure-paths,    model: gemini-3.1-pro-high,   tier: inherit }
  - { lens: blast-radius,     model: gemini-3.8-flash-high, tier: flash }
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

### 3. Dispatch N skeptics in parallel — one model per seat
Seats are declared in this file's `x-plan-seats` (N = number of seats; gate per
`x-plan-panel.gate`, default majority of N). Every seat runs the **identical** template;
only the model differs, so the votes come from uncorrelated models. `lens` is the seat's
label. Independent runs, no shared scratchpad.

- **Exact route (top-level conversation with the `swarm` tool):** in ONE turn add one
  worker per seat (workers have `run_command`, so they can run `git diff`):
  `swarm{action:"add", name:"impl-<lens>", model:"<seat.model>", brief:"Read
  <PLUGIN>/skills/implementation-validator/SKILL.md → the chosen Skeptic Prompt Template.
  DIFF: git diff <BASE>..<HEAD> in <root>. Stay strictly read-only. INDEPENDENCE: do NOT
  call read_board and do NOT open other seats' files. Write ONLY your fenced-JSON verdict
  to <milestone>/adversarial-reviews/seats/impl-r<k>-<lens>.json, then post
  '@coordinator done <lens>' with no findings in the post."}`
  End the turn; on each wake, check which seat files exist. When all N exist, add the
  chair: `swarm{action:"add", name:"impl-chair", model:"<x-plan-model>", brief:"Read the N
  seat files under <milestone>/adversarial-reviews/seats/ and this skill; dedup by file+id,
  apply the gate, calibrate severity, write implementation-validation.md. Post
  '@coordinator done'."}` Kill the seat workers and the chair afterwards. Take each seat's
  model for the Panel table from `swarm status`, never from a worker's own claim.
- **Portable route (no `swarm`, or running as a subagent):** N parallel `invoke_subagent`
  calls in one turn, `TypeName: self` (instructed to stay strictly read-only so they can
  run `git diff`/`git rev-parse` and read files) or `TypeName: research` / `research-google`
  (passing the diff if shell access is unavailable to them), each with `Model: <seat.tier>`
  and the same template. You act as the chair.
- **Independence.** With `invoke_subagent`, skeptics cannot see each other. With the swarm
  the platform does not prevent it, so: verdicts go to files, not the board; seats are told
  not to call `read_board` or open other seats' files; all seats are added in the same turn.

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

### 7. Persist the review
Write the aggregated result as a Markdown report to
`plans/active_milestones/{moniker}/adversarial-reviews/implementation-validation.md`
(create the folder if it does not exist). `{moniker}` is the active milestone whose
`plan.md`/`spec.md` this diff implements — the orchestrator knows it; if the diff belongs
to no milestone, write to `plans/adversarial-reviews/implementation-validation.md` and say
so. **Always write this file, even on a clean pass** — "zero confirmed defects, here is
what was attacked" is the evidence the gate produced, and the **severity calibration**
table is the highest-value thing this stage emits. A re-validation after fixes goes to
`implementation-validation-r2.md`, `-r3.md`, … so each round is preserved. Fill the **The
Review Document** template below verbatim.

### 8. Act
- Fix **confirmed** defects (and **failed claims**) at their calibrated severity, highest first.
- Surface **unconfirmed** findings for human eyeballing.
- Report the calibration explicitly: "3 findings claimed Critical; all 3 confirmed real but downgraded to High because impact is conditional on concurrent requests." This is the single most useful sentence the panel produces — see Calibration Note.
- Tick the **Actions Taken** checklist in the review file as you fix each defect.

## Finding-Hunt Template (default)

Dispatch **once per seat, unchanged** (N seats, each on its own model — see step 3). Replace `{DESCRIPTION}`, `{BASE_SHA}`, `{HEAD_SHA}`.

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

When you have explicit acceptance claims, dispatch this **once per seat per claim**
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

## The Review Document

This is what step 7 writes to
`plans/active_milestones/{moniker}/adversarial-reviews/implementation-validation.md`. It is
the human-readable face of the JSON above — a reviewer should grasp what is broken, at what
*corrected* severity, without opening an agent transcript. Use `date +%Y-%m-%d` for the
date. Severity icons: 🔴 critical · 🟠 high · 🟡 medium · ⚪ low. The **Severity
Calibration** table is the centerpiece — never omit it when any severity was revised. Drop
the **Failed Claims** section in finding-hunt mode. Keep the other sections even when empty
(write `_None._`).

```markdown
# Implementation Adversarial Review — {change title}

> `implementation-validator` · {N} independent skeptics on {M} model families, no shared scratchpad · default-to-reject (`isReal=false` / `refuted=true`) · {majority-of-N} gate · severity calibration

## Panel
| Seat (lens) | Model | Route | Verdict file |
|---|---|---|---|
| claim-vs-reality | opus-5.5-high | swarm | seats/impl-r1-claim-vs-reality.json |
| failure-paths | gemini-3.1-pro-high | swarm | seats/impl-r1-failure-paths.json |
| blast-radius | gemini-3.8-flash-high | swarm | seats/impl-r1-blast-radius.json |
| chair | opus-5.5-high | swarm | — |

| Field | Value |
|---|---|
| Milestone | `{moniker}` |
| Diff | `{BASE_SHA}..{HEAD_SHA}` |
| Date | {YYYY-MM-DD} |
| Mode | {finding-hunt · claim-refutation} |
| Gate | {majority (2-of-3 with 3 seats) · any-one · unanimous} |
| Result | **{N} confirmed defects · {F} failed claims · {M} unconfirmed** — highest corrected severity **{high}** |

## Verdict

{1–3 plain-language sentences. Lead with the calibration headline, e.g. "3 findings claimed Critical; all confirmed real but downgraded to High — impact is gated on concurrent requests, not every run."}

## Confirmed Defects (≥ 2 votes)

> Fix at the **corrected** severity, highest first.

### 🔴 `{id}` — {one-line title}  · severity {high} · {votes}/{N} · {agreeing models, e.g. opus + gemini-pro}
- **Location:** `{file}:{location}`
- **Attack:** {the input / sequence / edge case that triggers it}
- **Evidence:** `{file:line}` — {the specific code that proves it}
- **Why it breaks:** {reasoning}
- **Fix:** {concrete remediation}

_(repeat per confirmed defect)_

## Severity Calibration

| `id` | claimed | corrected | why |
|---|---|---|---|
| `{id}` | 🔴 critical | 🟠 high | {impact gated on concurrent requests, not every run} |

## Failed Claims  _(claim-refutation mode only)_

| claim | refuted by | severity | attack |
|---|---|---|---|
| "{claim}" | {2}/3 | 🟠 high | {input that falsified it} |

## Unconfirmed (FYI · 1 vote)

| `id` | severity | location | note |
|---|---|---|---|
| `{id}` | ⚪ low | `{file}:{loc}` | surfaced, not blocking |

## Attacks That Failed

- {short note per serious attack that found no defect} — corroborates robustness here.

## Actions Taken

- [x] Fixed `{id}` at {corrected severity}
- [ ] Surfaced calibration delta to user: "{the headline sentence}"
- [ ] Re-validated after fixes → `implementation-validation-r2.md` _(or: not needed)_
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
