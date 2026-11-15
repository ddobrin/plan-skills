---
name: plan-validator
description: Use after an implementation plan is written and BEFORE executing it, to catch ordering bugs and false assumptions while they are still cheap. Dispatches independent skeptic agents that assume the plan WILL fail, read the codebase to check its assumptions, and find the first domino that topples the rest — keeping only findings confirmed by a 2-of-3 majority. Symptoms - "validate this plan", "will this plan work", "review the plan before we start", a freshly written plans/*.md from architect / visual-architect, about to run engineer or starter.
tools:
  - invoke_subagent
  - view_file
  - write_to_file
  - replace_file_content
  - multi_replace_file_content
  - list_dir
  - find_by_name
  - grep_search
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

- A written implementation plan exists (e.g. from `architect` or `visual-architect`) and you are about to execute it.
- The user asks to "validate", "sanity-check", "stress-test", or "review" a plan before work starts.
- The plan touches existing code whose shape the plan *assumes* — exactly where plans rot.

## When NOT to Use

- The artifact is a spec (use `spec-validator`) or already-written code (use `implementation-validator`).
- A trivial one-step plan with no dependencies and no assumptions about existing code.
- No plan exists yet — write one first.

## Core Principle

Four things turn an ordinary review into adversarial findings. All four are required:

1. **Adversarial framing** — the agent assumes the plan fails and hunts for the failure, rather than judging whether it "seems reasonable."
2. **Default-to-reject** — uncertainty about whether a step is safe resolves *against* the plan. "Looks fine" is a failed review unless the agent shows what it verified.
3. **Partitioned lenses** — the three skeptics are **not** given the same prompt. Each owns a different slice of the attack surface *and* a different reading assignment (the step graph · the source files the plan names · the callers, tests and CI it disturbs). Three identical prompts on one model produce correlated errors: the panel is shaped like three votes and carries close to one.
4. **Independent quorum** — the lenses never see each other's output; keep only findings confirmed by a **majority (2 of 3)**, and rank **cross-lens** agreement above same-lens repetition.

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

### 2. Author the skeptic prompts
Assemble **one prompt per lens** from **Skeptic Lens Prompts** below: the **Shared
Preamble**, then that lens's own section, then the **Shared Tail**. Keep the "default to
reject", "verify in source", and "final message MUST be JSON" clauses verbatim in every
lens.

### 3. Run the asymmetry test, then dispatch one skeptic per lens
Before dispatching, name one finding **only that lens could reach** — lens 2 opens files
lens 1 never reads; lens 3 traces callers neither of the others visits. If you cannot name
one for a lens, merge it and run two: a panel of near-clones is worse than an honest pair,
because it manufactures false corroboration. With two lenses, a finding both reach is
confirmed and everything else is single-vote. Record which lenses you actually dispatched.

Then spawn **one skeptic per lens, in parallel, via `invoke_subagent`** — one call each for
Sequencing · Ground Truth · Blast Radius, fired in a single turn. Use `TypeName: research`
(or `research-google` / `self` instructed to stay read-only — it can read and grep the
codebase). Each runs independently — no shared scratchpad.

### 4. Collect verdicts
Parse each agent's fenced JSON. Re-dispatch any agent that returns prose instead of JSON.

### 5. Dedup by identity
Group findings by stable `id` + the `step` they target. Two skeptics describing the same
ordering bug should collapse to one entry, not three.

### 6. Apply the majority gate
- **Confirmed:** appears in **≥ 2 of 3** outputs.
- **Cross-lens vs. same-lens.** Record *which lenses* agreed. Two lenses reaching one
  finding from different evidence is independent corroboration and ranks first. A finding
  both raised by lenses that read the same material is weaker than its vote count
  suggests — read the evidence, not the tally.
- **Single vote:** appears in exactly one. These go to the **Single-Vote Findings (triage
  required)** section and each one needs an explicit decision — fixed, accepted as a known
  risk, or refuted with a reason. A lone finding is more often a real defect one reviewer
  happened to reach than noise, so "only one agent saw it" is not a reason to close it.
  Ordering bugs in particular are easy to miss and expensive to hit.
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
goes to `plan-validation-r2.md`, `-r3.md`, … so every round is preserved. Fill the **The
Review Document** template below verbatim.

### 8. Act
> **Under the Supervisor, report — do not edit.** When `starter` / `supervisor` dispatched
> this panel, its node contract in `graph.json` is to write the review and nothing else:
> return the findings and the tallies, and stop. The Supervisor routes each fix back along
> its edge, to `architect`, and owns the single-vote triage — leave the `decision` column and
> **Actions Taken** for it. The bullets below that change the plan or triage the tail
> apply when you run this skill standalone.

- For each **confirmed** finding, apply its `fix` to the plan (reorder steps, add a missing prerequisite step, add a rollback/verify step, correct an assumption).
- **Triage every single-vote finding** and record the decision in the review.
- If you reordered or added steps materially, re-run the panel once.
- Tick the **Actions Taken** checklist in the review file as you apply each fix.
- Report the tallies the Supervisor records in the milestone's `state.json`: the lenses
  dispatched, the `confirmed`, `single_vote` and `cross_lens` counts, the `first_domino`,
  and whether the single-vote tail has been triaged (under the Supervisor it has not — that
  triage is the Supervisor's). You do not write `state.json` yourself.

## Skeptic Lens Prompts

Dispatch **once per lens**, three lenses in parallel, via `invoke_subagent`. Each lens gets
the **Shared Preamble**, then its own **Lens** section, then the **Shared Tail**. Replace
`{PLAN}` and `{REPO_ROOT}` in the preamble.

> **Why not the same prompt three times?** Three identical prompts on one model produce
> correlated errors: the panel is shaped like three votes and carries close to one. The
> lenses below partition the attack surface *and* the reading assignment, so the three
> skeptics can disagree for real reasons instead of by sampling. The gate arithmetic is
> unchanged — what changes is how much information reaches it.

### Panel Composition

| Lens | Owns these categories | Assigned evidence — reads this FIRST, and is the panel's authority on it |
|---|---|---|
| **1 · Sequencing** (`sequencing`) | `ordering` | The plan's own step graph: every step in order, what each produces and consumes. |
| **2 · Ground Truth** (`ground-truth`) | `false-assumption` | The **source files the plan names** — opened, not inferred. Signatures, fields, tables, flags. |
| **3 · Blast Radius** (`blast-radius`) | `unverifiable`, `no-rollback`, `missing-migration`, `hidden-coupling` | **Callers, tests, CI and migration tooling** — what the plan touches indirectly and how it is undone. |

A lens may report a finding outside its own categories — it must simply record which lens
it was dispatched as. Two lenses reaching the same finding from different evidence is the
strongest signal this panel can produce; the orchestrator is told to weight it accordingly.

### The Asymmetry Test (run before dispatching)

For each lens, name one finding that **only that lens could reach**. Lens 2 opens files
lens 1 never reads; lens 3 traces callers neither of the others visits. If you cannot name
such a finding for a lens, merge it and run two — a panel of near-clones is worse than an
honest pair, because it produces false corroboration.

### Shared Preamble (prepend to every lens)

```
You are an adversarial plan reviewer on a three-lens panel. Assume this implementation
plan WILL fail. Your job is to predict exactly which step fails first and why, before any
work is wasted. You have read access to the codebase — USE IT to check every assumption
the plan makes.

You are one of three reviewers, each assigned a different hunting ground and a different
reading assignment. You will not see the others' findings. Work your own assignment to
exhaustion rather than surveying everything shallowly — breadth is the panel's job,
depth is yours.

PLAN:
{PLAN}

REPOSITORY ROOT (read any file you need to verify the plan's assumptions):
{REPO_ROOT}
```

### Lens 1 — Sequencing Skeptic

```
YOUR LENS: sequencing and dependency. You are the panel's authority on the plan's step
graph.

READ FIRST: the plan's steps in order, start to finish, before opening any source file.
Build the dependency graph explicitly — for each step, write down what it produces and
what it consumes. Then look for the edges that do not exist.

Hunt for:
- A step that consumes an artifact only a LATER step produces.
- Two steps in the same execution group that mutate the same file with no merge plan.
  (Execution groups run concurrently — tasks inside one MUST touch disjoint files.)
- Circular dependencies between steps, or between a step and its verification.
- Preconditions established nowhere in the plan: a step that assumes setup, seed data,
  a running service, or a prior migration the plan never performs.
- Group boundaries that are wrong: a task placed in group N that cannot start until
  something in group N+1 finishes.

Your evidence is the plan's own text: quote the two steps whose order is wrong and say
which artifact is missing at the moment the earlier one runs. Open source files only when
you need to confirm that an artifact does not ALREADY exist — a step that recreates
something already present is a different finding from one that consumes something absent.
```

### Lens 2 — Ground Truth Skeptic

```
YOUR LENS: what the plan asserts about code that already exists. You are the panel's
authority on the actual state of the repository.

READ FIRST: open every source file the plan names, before forming any opinion about the
plan. For each function, method, class, field, table, column, flag, config key, or
signature the plan mentions — go find it. Read the real definition. Read its callers.
Read its tests.

Hunt for:
- A named function/file/field/table/flag/signature that DOES NOT EXIST.
- One that exists but DIFFERS: different arity, different types, different return shape,
  different nullability, different name by a character.
- A plan step that describes existing behavior incorrectly — it says the method does X;
  read it and find it does Y.
- An assumed library, version, or capability that the manifest does not provide.
- Tests the plan assumes exist (or assumes do not exist) — check the test files.

DO NOT GUESS. A predicted failure you did NOT verify by opening the file is a guess, not
a finding: either cite `file:line` from a file you actually read, or set confidence "low"
and say what you could not check. Your `evidence` field must be `file:line` for every
finding in your own category — this is the lens where the citation is mandatory.

Also record, in checks_that_passed, each assumption you verified that DID hold. A plan
whose assumptions you confirmed one by one is a materially different object from one
nobody checked, and the panel needs to know which it is looking at.
```

### Lens 3 — Blast Radius Skeptic

```
YOUR LENS: what happens when a step goes wrong, and what the plan touches without saying
so. You are the panel's authority on reversibility and second-order effects.

READ FIRST: not the plan's steps, but their surroundings — the callers of every function
the plan modifies, the tests that cover them, the build and CI configuration, and any
migration or deploy tooling in the repo. Come to the plan already knowing what it will
disturb.

Hunt for:
- Unverifiable steps: "verify it works", "ensure correctness", "confirm the behavior" —
  any verification with no named command, test, or observable signal. A step whose
  verification cannot fail is a step with no verification.
- No rollback: a step that cannot be undone if the NEXT step fails. Irreversible
  migrations, deleted data, dropped columns, force-pushes, one-way config changes.
- Missing migration or compatibility: a schema or API change with no backfill, no
  versioning, no backward-compatible window for in-flight clients or old rows.
- Hidden coupling: a "simple" edit whose blast radius reaches callers, subclasses,
  serialized formats, cached values, or downstream systems the plan never mentions.
  Grep for every caller. The plan's "Affected Files" list is a claim, not a fact.
- Parallelism that is unsafe in practice: an execution group that is file-disjoint on
  paper but collides in the test database, a shared fixture, a port, or a CI runner.

Your evidence is the thing the plan did not mention: cite the caller at `file:line` that
the plan omits, or the CI command that will fail, or the migration with no down path.
```

### Shared Tail (append to every lens)

```
Report every problem you find. Do not pre-filter to the ones you judge important, and do
not hold back a finding because you are unsure it matters — the orchestrator filters, you
report.

Be skeptical. DEFAULT TO REJECT: if you cannot confirm a step is safe, report it. A
predicted failure you did NOT verify in the source is a guess — either verify it and cite
file:line, or label confidence "low".

Find the FIRST domino: the earliest step whose failure invalidates the steps after it.

For each finding assign a STABLE id: a short kebab-case slug (e.g.
"step4-method-missing", "no-rollback-on-migrate"). Two reviewers finding the same problem
should plausibly choose the same slug — this is how the panel recognizes agreement across
lenses, so name the DEFECT, not your lens's view of it.

Your final message MUST be exactly one fenced JSON block and nothing else, matching:

```json
{
  "lens": "sequencing|ground-truth|blast-radius",
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

Each skeptic returns the JSON above, tagged with its `lens`. The orchestrator aggregates
into:

```json
{
  "confirmed": [
    { "id": "...", "votes": 2, "lenses": ["ground-truth", "blast-radius"],
      "cross_lens": true, "step": "...", "severity": "high", "fix": "..." }
  ],
  "single_vote": [ { "id": "...", "votes": 1, "lenses": ["sequencing"], "...": "..." } ],
  "first_domino": "id voted most often as the earliest blocking failure"
}
```

**`cross_lens` is the field that matters.** Two lenses reaching one finding from different
evidence is independent corroboration. Two votes are not automatically that — record which
lenses agreed, and rank cross-lens agreement above same-lens repetition.

## The Review Document

This is what step 7 writes to
`plans/active_milestones/{moniker}/adversarial-reviews/plan-validation.md`. It is the
human-readable face of the JSON above — a reviewer should grasp where the plan breaks
without opening an agent transcript. Use `date +%Y-%m-%d` for the date. Severity icons:
🔴 high · 🟠 medium · 🟡 low. The **First domino** is the headline; lead with it. Every
confirmed finding must carry its `file:line` evidence — an uncited prediction is a guess,
not a finding. Keep every section, even when empty (write `_None._`).

```markdown
# Plan Adversarial Review — {plan title}

> `plan-validator` · 3-lens partitioned panel (sequencing · ground-truth · blast-radius), no shared scratchpad · default-to-reject · skeptics READ the codebase · {2-of-3} majority gate

| Field | Value |
|---|---|
| Milestone | `{moniker}` |
| Run | {`run_id` supplied by the Supervisor, or `standalone`} |
| Artifact | `plans/active_milestones/{moniker}/plan.md` |
| Date | {YYYY-MM-DD} |
| Lenses dispatched | {sequencing · ground-truth · blast-radius — or the two actually run, and why} |
| Gate | {2-of-3 · any-one · unanimous} |
| Result | **{N} confirmed ({X} cross-lens) · {M} single-vote** — highest severity **{high}** |
| 🁢 First domino | `{id}` — {earliest failure that invalidates the steps after it, or `none`} |

## Verdict

{1–3 plain-language sentences: will the plan survive execution, and which step topples first?}

## Confirmed Findings (≥ 2 votes)

> Apply each **Fix** to the plan — reorder steps, insert a prerequisite, add a rollback/verify, or correct the assumption.

### 🔴 `{id}` — {one-line name}  · {category} · {votes}/3 · lenses: {lenses} · cross-lens: {true|false} · confidence {high}
- **Step:** {step number / title this concerns}
- **Failure:** {the concrete scenario in which the plan breaks}
- **Evidence:** `{file:line}` you read _(or verbatim plan text)_
- **Fix:** {the concrete change to the plan that prevents the failure}

_(repeat per confirmed finding; the First domino first)_

## Single-Vote Findings (triage required)

> One skeptic found these and the others did not. That is not evidence they are wrong — a
> lone finding is more often a real defect one reviewer happened to reach than noise.
> **Each row needs a decision** — fixed, accepted as a known risk, or refuted with a
> reason. Do not close this section by ignoring it. A finding with a real `file:line`
> behind it is a different object from a guess.

| `id` | lens | severity | step | decision |
|---|---|---|---|---|
| `{id}` | {lens} | 🟠 medium | {step} | {fixed / accepted risk because … / refuted because …} |

## Checks That Passed

- {assumption the skeptics verified that DID hold} — `{file:line}`

## Actions Taken

- [x] Reordered: inserted step {2b} before step {3} (`{id}`)
- [x] Corrected step {3} target to `{realName()}` (`{id}`)
- [ ] Triaged single-vote finding `{id}` → {decision}
- [ ] Re-ran panel on revision → `plan-validation-r2.md` _(or: not needed)_
```

## Worked Example

> Plan excerpt: *"Step 2: add `retryCount` to the `Job` record. Step 3: update `JobScheduler.dispatch()` to read `retryCount`. Step 4: migrate existing rows."*

Three lens skeptics read the repo. After dedup + majority gate:

**Confirmed (≥2 votes):**
- `dispatch-signature-missing` (3 votes, high, cross-lens) — `JobScheduler` has no `dispatch()`; the method is `schedule(Job)` (`scheduler/JobScheduler.java:88`). Fix: retarget step 3 to `schedule()`.
- `migrate-before-default` (2 votes, high — `sequencing` + `blast-radius`, cross-lens) — step 4 migrates rows but no step gives `retryCount` a default, so step 3 NPEs on legacy rows between deploy and migration. Fix: add "step 2b: default `retryCount` to 0" *before* step 3; mark step 3 as requiring 2b.
- `first_domino` = `migrate-before-default`.

**Single vote (triage required):**
- `no-rollback-on-migrate` (1 vote, medium — `blast-radius`) — step 4 has no down-migration (`db/migrations/0042_add_retry_count.sql:1`). Triaged: **accepted risk** — the migration is additive and the team's rollback procedure restores from snapshot. Recorded in the review so the decision is on the record rather than implied by silence.

The plan is reordered and the missing default step inserted before execution begins.

## Red Flags

| Thought | Reality |
|---|---|
| "Three identical prompts give me three independent opinions." | They give one opinion sampled three times. Correlated skeptics manufacture false corroboration — partition the lens *and* the reading assignment. |
| "The plan reads cleanly, it'll be fine." | Clean prose hides dead assumptions. The skeptics must open the files. |
| "The agent says step 3 is wrong but didn't cite a line." | Unverified prediction = guess. Force `file:line` or mark confidence low. |
| "One skeptic found the ordering bug, two didn't — so it's noise." | Wrong default. The lone finding is usually real — ordering bugs are easy to miss and costly to hit. Triage it and record the decision. |
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

Note what the quorum is and is not for. It is a *ranking* device — it tells you which
findings two independent readers reached, and those go first. It is not a filter that makes
the rest disappear: an uncorroborated finding with a real `file:line` behind it is a
different object from an uncorroborated guess, and only the citation distinguishes them.
Read the evidence, not the vote count.
