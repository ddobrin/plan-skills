# Skeptic Lens Prompts — plan-validator

Dispatch **once per lens**, three lenses in parallel, via the `Agent` tool. Each lens gets
the **Shared Preamble**, then its own **Lens** section, then the **Shared Tail**. Replace
`{PLAN}` and `{REPO_ROOT}` in the preamble.

> **Why not the same prompt three times?** Three identical prompts on one model produce
> correlated errors: the panel is shaped like three votes and carries close to one. The
> lenses below partition the attack surface *and* the reading assignment, so the three
> skeptics can disagree for real reasons instead of by sampling. The gate arithmetic is
> unchanged — what changes is how much information reaches it.

The "default to reject", "verify in source", and "final message MUST be JSON" clauses are
load-bearing — keep them verbatim in every lens.

---

## Panel Composition

| Lens | Owns these categories | Assigned evidence — reads this FIRST, and is the panel's authority on it |
|---|---|---|
| **1 · Sequencing** | `ordering` | The plan's own step graph: every step in order, what each produces and consumes. |
| **2 · Ground Truth** | `false-assumption` | The **source files the plan names** — opened, not inferred. Signatures, fields, tables, flags. |
| **3 · Blast Radius** | `unverifiable`, `no-rollback`, `missing-migration`, `hidden-coupling` | **Callers, tests, CI and migration tooling** — what the plan touches indirectly and how it is undone. |

A lens may report a finding outside its own categories — it must simply record which lens
it was dispatched as. Two lenses reaching the same finding from different evidence is the
strongest signal this panel can produce; the orchestrator is told to weight it accordingly.

## The Asymmetry Test (run before dispatching)

For each lens, name one finding that **only that lens could reach**. Lens 2 opens files
lens 1 never reads; lens 3 traces callers neither of the others visits. If you cannot name
such a finding for a lens, merge it and run two — a panel of near-clones is worse than an
honest pair, because it produces false corroboration.

---

## Shared Preamble (prepend to every lens)

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

---

## Lens 1 — Sequencing Skeptic

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

---

## Lens 2 — Ground Truth Skeptic

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

---

## Lens 3 — Blast Radius Skeptic

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

---

## Shared Tail (append to every lens)

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

---

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
