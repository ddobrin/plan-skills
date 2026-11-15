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

Four things turn an ordinary review into adversarial findings. All four are required:

1. **Adversarial framing** — the agent's job is to construct the input or sequence that breaks the code, not to judge whether it "looks good."
2. **Default-to-reject** — for finding-hunt, default `isReal=false` (only confirmed, code-grounded defects count). For claim-refutation, default `refuted=true` (a claim survives only if the agent actively tried and failed to break it).
3. **Partitioned lenses** — the three skeptics are **not** given the same prompt. Each owns a different slice of the attack surface *and* a different reading assignment (the diff against its own description · the error branches and tests · the call sites the diff never touches). Three identical prompts on one model produce correlated errors: the panel is shaped like three votes and carries close to one.
4. **Independent quorum** — the lenses never see each other's output; keep only findings confirmed by a **majority (2 of 3)**, and rank **cross-lens** agreement above same-lens repetition.

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

**Uncommitted work.** If the change is not committed yet — the normal case when the
Supervisor dispatches this gate, because it commits only *after* the gate — a commit range
is empty and there is nothing to attack. Attack the working tree instead: in the Shared
Preamble's **DIFF TO ATTACK**, give the skeptics `git diff --stat HEAD` and `git diff HEAD`
in place of the two range commands, and list the untracked files from `git status --short`
so new files are read too. Record the diff in the review as `HEAD..working tree`.

### 2. Author the skeptic prompts
Assemble **one prompt per lens** from **Skeptic Lens Prompts** below: the **Shared
Preamble**, then that lens's own section, then the **Shared Tail** (finding-hunt) or the
**Claim-Refutation Template** (variant). Keep the default-to-reject and "final message MUST
be JSON" clauses verbatim in every lens.

### 3. Run the asymmetry test, then dispatch one skeptic per lens
Before dispatching, name one defect **only that lens could reach** — lens 3 reads files
that are not in the diff at all; lens 2 reads the test suite; lens 1 reads the claim text
neither of the others is given. If you cannot name one for a lens, merge it and run two.
With two lenses, a finding both reach is confirmed and everything else is single-vote.
Record which lenses you actually dispatched.

Then spawn **one skeptic per lens, in parallel, via `invoke_subagent`** — one call each for
Claim vs. Reality · Failure Paths · Blast Radius, fired in a single turn — using
`TypeName: self` (instructed to stay strictly read-only so they can run
`git diff`/`git rev-parse` and read files) or `TypeName: research` / `research-google`
(passing the diff if shell access is unavailable to them). Independent runs, no shared
scratchpad.

### 4. Collect verdicts
Parse each agent's fenced JSON. Re-dispatch any agent that returns prose.

### 5. Dedup by identity
**This is the hard part.** Group findings by a stable identity: `file:location` + the
`id` slug. Three skeptics will phrase "NPE on empty list in `parseTasks`" three ways; if
you tally on raw text, nothing reaches quorum. Normalize to `file:line::id` before counting.

### 6. Apply the majority gate + severity calibration
- **Finding-hunt:** a finding is **confirmed** when **≥ 2 of 3** skeptics report it with `isReal=true`. Its severity is the **most common `correctedSeverity`** among the agreeing skeptics (tie → higher).
- **Claim-refutation:** a claim **survives** when **≥ 2 of 3** skeptics return `refuted=false`. A claim **fails** (the code is broken) when ≥2 return `refuted=true` — those become defects to fix.
- **Cross-lens vs. same-lens.** Record *which lenses* agreed. Two lenses reaching one defect
  from different evidence — the failure-path lens and the blast-radius lens landing on the
  same race — is independent corroboration and ranks first. Two votes are not automatically
  that; read the evidence, not the tally.
- **Single vote:** appears in exactly one output. These go to the **Single-Vote Findings
  (triage required)** section and each one needs an explicit decision — fixed, accepted as a
  known risk, or refuted with a reason. A lone finding is more often a real defect one
  reviewer happened to reach than noise, and concurrency and failure-path bugs are exactly
  the kind two of three readers miss.

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
> **Under the Supervisor, report — do not edit.** When `starter` / `supervisor` dispatched
> this panel, its node contract in `graph.json` is to write the review and nothing else:
> return the findings and the tallies, and stop. The Supervisor routes each fix back along
> its edge, to `engineer`, and owns the single-vote triage — leave the `decision` column and
> **Actions Taken** for it. The bullets below that change source or triage the tail
> apply when you run this skill standalone.

- Fix **confirmed** defects (and **failed claims**) at their calibrated severity, highest first.
- **Triage every single-vote finding** and record the decision in the review.
- Report the calibration explicitly: "3 findings claimed Critical; all 3 confirmed real but downgraded to High because impact is conditional on concurrent requests." This is the single most useful sentence the panel produces — see Calibration Note.
- Tick the **Actions Taken** checklist in the review file as you fix each defect.
- Report the review path and tallies the Supervisor records in the milestone's
  `state.json` (the lenses dispatched, confirmed / single-vote / cross-lens counts, and
  whether the single-vote tail has been triaged — under the Supervisor it has not; that
  triage is the Supervisor's). You do not write `state.json` yourself.

## Skeptic Lens Prompts

Two modes, same machinery. Pick one.

**Finding-hunt (default)** dispatches **once per lens**, three lenses in parallel, via
`invoke_subagent`: each gets the **Shared Preamble**, its own **Lens** section, then the
**Shared Tail**. **Claim-refutation** dispatches once per claim per lens — the lenses give
three genuinely different ways to break the same claim. Replace `{DESCRIPTION}`,
`{BASE_SHA}`, `{HEAD_SHA}` (and `{CLAIM}`).

> **Why not the same prompt three times?** Three identical prompts on one model produce
> correlated errors: the panel is shaped like three votes and carries close to one. The
> lenses below partition the attack surface *and* the reading assignment — one reads the
> diff against its own description, one reads the error branches and tests, one reads the
> call sites the diff does not touch. They can then disagree for real reasons.

### Panel Composition

| Lens | Owns these categories | Assigned evidence — reads this FIRST, and is the panel's authority on it |
|---|---|---|
| **1 · Claim vs. Reality** (`claim-vs-reality`) | `claim-mismatch` | The **diff against its own description** — every claim in the commit/PR text, checked line by line. |
| **2 · Failure Paths** (`failure-paths`) | `failure-path`, `edge-case` | The **error branches and the tests** — every `catch`, early return, default, and the test files that cover them. |
| **3 · Blast Radius** (`blast-radius`) | `concurrency`, `resource`, `regression` | The **call sites and contracts the diff does NOT contain** — callers, subclasses, serialized shapes, shared state. |

A lens may report outside its own categories — it must simply record which lens it was
dispatched as. Two lenses reaching one defect from different evidence is the strongest
signal this panel produces.

### The Asymmetry Test (run before dispatching)

For each lens, name one defect that **only that lens could reach**. Lens 3 reads files
that are not in the diff at all; lens 2 reads the test suite; lens 1 reads the claim text
neither of the others is given. If you cannot name such a defect for a lens, merge it and
run two.

### Shared Preamble (prepend to every lens)

```
You are an adversarial implementation verifier on a three-lens panel. Your job is to
BREAK this change, not to approve it.

You are one of three reviewers, each assigned a different hunting ground and a different
reading assignment. You will not see the others' findings. Work your own assignment to
exhaustion rather than surveying the whole diff shallowly — breadth is the panel's job,
depth is yours.

WHAT THE CHANGE CLAIMS TO DO:
{DESCRIPTION}

DIFF TO ATTACK:
  git diff --stat {BASE_SHA}..{HEAD_SHA}
  git diff {BASE_SHA}..{HEAD_SHA}
Read any file in the repo you need to understand the blast radius.
```

### Lens 1 — Claim vs. Reality Skeptic

```
YOUR LENS: whether the code does what it says. You are the panel's authority on the gap
between the description and the diff.

READ FIRST: the change description, and break it into a numbered list of discrete claims
— one per behavior asserted, including the implicit ones ("adds caching" implies
invalidation exists). Only then read the diff, and check each claim against it one at a
time.

Hunt for:
- A claim the diff does not implement at all.
- A claim implemented for the example case but not the general one.
- A claim implemented in one code path and missed in a parallel path.
- Behavior the diff adds that the description never mentions — undisclosed scope is a
  finding, not a bonus. It is the change nobody reviewed.
- A renamed or moved thing the description calls a refactor but which changes behavior.
- Configuration, feature flags, or defaults that the description assumes and the diff
  does not set.

Your evidence is the pairing: quote the claim, then cite the `file:line` that fails to
deliver it. A finding here is always two halves.
```

### Lens 2 — Failure Path Skeptic

```
YOUR LENS: everything that happens when the happy path does not. You are the panel's
authority on error handling and boundary behavior.

READ FIRST: not the main logic, but the error branches — every catch, rescue, except,
early return, null guard, default value, fallback, and timeout in the changed code AND in
the functions it calls. Then read the test files covering these paths. Come to the diff
already knowing what is tested and what is not.

Hunt for:
- Swallowed errors: a catch that logs and continues, returns null, or returns a success
  shape on failure. Trace what the caller then does with that value.
- Error paths that leave state half-written: the first two of three updates succeeded.
- Empty, null, zero, negative, huge, duplicate, unicode, and off-by-one inputs. For each
  boundary, name the concrete input and the line it breaks on.
- Timeouts and partial responses: what does this do when the dependency is slow rather
  than down?
- Tests that were changed, skipped, or deleted in this diff — and whether the new test
  actually asserts the old test's guarantee or a weaker one.
- New capability with no test at all. Say so explicitly; it is an automatic finding.

Your evidence is the input and the line: "`process([])` reaches line 47 with `items[0]`
undefined". Not "empty input may not be handled".
```

### Lens 3 — Blast Radius Skeptic

```
YOUR LENS: what this diff breaks somewhere it does not appear. You are the panel's
authority on everything outside the changed files.

READ FIRST — and this is the point of your lens — the files the diff does NOT contain.
For every function, method, field, or type the diff modifies, grep the repository for its
callers and read them. Read subclasses and implementations. Read anything that serializes,
caches, or persists the shapes involved. Only then look at the diff itself.

Hunt for:
- Regression: a caller or contract the diff silently broke — changed arity, changed
  return shape, changed nullability, changed exception type, changed ordering guarantee.
- Concurrency: shared mutable state on a singleton or shared instance, non-atomic
  read-modify-write, cross-request races, a cache mutated without a lock. NOTE: this is
  the classic over-rated category — report what you find, but calibrate severity on
  whether the race is reachable in this system's actual concurrency model, and say what
  gates it.
- Resource and correctness: leaks, unbounded growth, wrong math, wrong comparison
  operator, lost precision, integer/float confusion, an unbounded collection.
- Persisted or wire-format shapes that changed without a migration or version bump —
  old rows and in-flight messages still exist.
- A default that changed for existing callers who never asked for the new behavior.

Your evidence is the file the diff never touched: cite the caller at `file:line` that
still expects the old contract.
```

### Shared Tail (append to every lens)

```
Report every defect you find. Do not pre-filter to the ones you judge important, and do not
hold back a finding because you are unsure it matters — the orchestrator filters, you
report.

Be skeptical. DEFAULT isReal=false: report a finding as real ONLY if you can ground it in
the actual code. If a concern is purely stylistic, cannot be confirmed in the source, or
relies on a misreading, set isReal=false and say why.

Assign each finding a STABLE id: a short kebab-case slug (e.g. "empty-list-npe",
"singleton-cursor-race"). Two reviewers finding the same defect should plausibly choose
the same slug — this is how the panel recognizes agreement across lenses, so name the
DEFECT, not your lens's view of it. Calibrate severity HONESTLY: critical = unconditional
data loss/corruption or broken core function on every run; high = serious but conditional
(e.g. only under concurrency); medium = real but narrow; low = minor.

Your final message MUST be exactly one fenced JSON block and nothing else, matching:

```json
{
  "lens": "claim-vs-reality|failure-paths|blast-radius",
  "findings": [
    {
      "id": "kebab-case-stable-slug",
      "title": "short description of the defect",
      "category": "claim-mismatch|failure-path|edge-case|concurrency|resource|regression|other",
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

When you have explicit acceptance claims, dispatch this **once per claim per lens** — the
three lenses attack the same claim from their own evidence, which is exactly the
independence a repeated copy of one prompt cannot give you. Prepend the Shared Preamble and
the lens's own READ FIRST paragraph, then:

```
The implementer claims:

  "{CLAIM}"

Your job is to REFUTE this claim, using YOUR LENS's evidence and hunting ground. Read the
diff (git diff {BASE_SHA}..{HEAD_SHA}) and the surrounding code, then construct the input,
sequence, or edge case that makes the claim false.

Be skeptical. DEFAULT refuted=true. You may only return refuted=false if you ACTIVELY
tried to break the claim from your lens's angle and could not — and you must describe what
you tried and which files you read.

Your final message MUST be exactly one fenced JSON block and nothing else, matching:

```json
{
  "lens": "claim-vs-reality|failure-paths|blast-radius",
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

The orchestrator aggregates skeptic JSON, tagged by `lens`, into:

```json
{
  "confirmed": [
    { "id": "...", "votes": 2, "lenses": ["failure-paths", "blast-radius"],
      "cross_lens": true, "file": "...", "location": "...", "severity": "high", "fix": "..." }
  ],
  "single_vote": [ { "id": "...", "votes": 1, "lenses": ["claim-vs-reality"], "...": "..." } ],
  "failed_claims": [ { "claim": "...", "refuted_by": 2, "lenses": ["..."], "severity": "high" } ],
  "calibration": [ { "id": "...", "claimedSeverity": "critical", "correctedSeverity": "high", "why": "conditional on concurrency" } ]
}
```

**`cross_lens` is the field that matters.** Two lenses reaching one defect from different
evidence is independent corroboration. Two votes are not automatically that — record which
lenses agreed, and rank cross-lens agreement above same-lens repetition.

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

> `implementation-validator` · 3-lens partitioned panel (claim-vs-reality · failure-paths · blast-radius), no shared scratchpad · default-to-reject (`isReal=false` / `refuted=true`) · {2-of-3} majority gate · severity calibration

| Field | Value |
|---|---|
| Milestone | `{moniker}` |
| Run | {`run_id` supplied by the Supervisor, or `standalone`} |
| Diff | `{BASE_SHA}..{HEAD_SHA}` _(or `HEAD..working tree` for uncommitted work)_ |
| Date | {YYYY-MM-DD} |
| Mode | {finding-hunt · claim-refutation} |
| Lenses dispatched | {claim-vs-reality · failure-paths · blast-radius — or the two actually run, and why} |
| Gate | {2-of-3 · any-one · unanimous} |
| Result | **{N} confirmed defects ({X} cross-lens) · {F} failed claims · {M} single-vote** — highest corrected severity **{high}** |

## Verdict

{1–3 plain-language sentences. Lead with the calibration headline, e.g. "3 findings claimed Critical; all confirmed real but downgraded to High — impact is gated on concurrent requests, not every run."}

## Confirmed Defects (≥ 2 votes)

> Fix at the **corrected** severity, highest first.

### 🔴 `{id}` — {one-line title}  · severity {high} · {votes}/3 · lenses: {lenses} · cross-lens: {true|false}
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

| claim | refuted by | lenses | severity | attack |
|---|---|---|---|---|
| "{claim}" | {2}/3 | {lenses} | 🟠 high | {input that falsified it} |

## Single-Vote Findings (triage required)

> One skeptic found these and the others did not. That is not evidence they are wrong — a
> lone finding is more often a real defect one reviewer happened to reach than noise.
> Concurrency and failure-path bugs in particular are easy for two of three readers to
> miss. **Each row needs a decision** — fixed, accepted as a known risk, or refuted with a
> reason. Read the cited evidence; a finding with a real `file:line` behind it is a
> different object from a guess.

| `id` | lens | severity | location | decision |
|---|---|---|---|---|
| `{id}` | {lens} | ⚪ low | `{file}:{loc}` | {fixed / accepted risk because … / refuted because …} |

## Attacks That Failed

- {short note per serious attack that found no defect} — corroborates robustness here.

## Actions Taken

- [x] Fixed `{id}` at {corrected severity}
- [ ] Surfaced calibration delta to user: "{the headline sentence}"
- [ ] Triaged single-vote finding `{id}` → {decision}
- [ ] Re-validated after fixes → `implementation-validation-r2.md` _(or: not needed)_
```

## Worked Example

> Change claims: *"Planner walks precompiled steps; safe under concurrent deliberations."*
> Finding-hunt, 3 lens skeptics over `git diff origin/main..HEAD`.

After dedup + majority gate + calibration:

**Confirmed (≥2 votes):**
- `singleton-cursor-race` (3 votes, cross-lens) — claimed **critical** by the skeptics, **corrected to high**. The planner is a shared singleton with non-volatile `cursor`/`steps` instance fields mutated per run (`Planner.java:59-64`, non-atomic `cursor++` at `:306`). One verifier narrowed it: intra-request replan is serialized, so the race is **strictly cross-request**, not within one deliberation — which is why "critical" (implying unconditional corruption) was an overstatement. Fix: make planner request-scoped or move per-run state out of the bean.

**Single vote (triage required):**
- `objectmapper-dup` (1 vote, low — `blast-radius`) — duplicated `ObjectMapper`/serialization. Triaged: **accepted** — real duplication, but it is a cleanliness issue with no correctness impact and the change is already scoped. Recorded so it is a deliberate deferral rather than an oversight.

**Calibration reported to the user:** *"1 finding claimed Critical; confirmed real by all 3 skeptics but downgraded to High — impact is gated on concurrent requests, not every run."*

## Red Flags

| Thought | Reality |
|---|---|
| "Three identical prompts give me three independent opinions." | They give one opinion sampled three times. Correlated skeptics manufacture false corroboration — partition the lens *and* the reading assignment. |
| "The diff is small, one reviewer is enough." | Small diffs hide concurrency and failure-path bugs. Run the panel. |
| "All three rated it Critical, so it's Critical." | Check the *corrected* severity and the reasoning — adversarial framing over-rates. Calibration is the point. |
| "One skeptic flagged a race, two didn't." | Concurrency bugs are the easiest to miss and the lone finding is usually real. Read the evidence and record a decision. |
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

The same asymmetry explains what the quorum is for. It is a *ranking* device — it tells you
which defects two independent readers reached, and those go first. It is not a filter that
makes the rest disappear. Read the evidence, not the vote count.
