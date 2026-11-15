---
name: spec-validator
description: Use after a spec or design doc is drafted and BEFORE writing an implementation plan, to find defects while they are still cheap to fix. Dispatches independent skeptic agents that attack the spec for ambiguity, missing or contradictory requirements, and untestable acceptance criteria, then keeps only findings confirmed by a 2-of-3 majority. Symptoms - "validate this spec", "poke holes in this design", "is this spec ready to plan against", finishing brainstorming before writing-plans, a freshly written specs/*.md.
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

Four things turn an ordinary review into adversarial findings. All four are required:

1. **Adversarial framing** — the agent's success metric is "how many real holes did I find," not "is this good." It is told to *break* the spec, not evaluate it.
2. **Default-to-reject** — uncertainty resolves *against* the spec. Returning "looks complete" is a failed review unless the agent lists what it attacked and why each attack failed.
3. **Partitioned lenses** — the three skeptics are **not** given the same prompt. Each owns a different slice of the attack surface *and* a different reading assignment (the spec against itself · the world outside the spec · the acceptance criteria alone, read as a contract to game). Three identical prompts on one model produce correlated errors: the panel is shaped like three votes and carries close to one.
4. **Independent quorum** — the lenses never see each other's output; keep only findings confirmed by a **majority (2 of 3)**, and rank **cross-lens** agreement above same-lens repetition.

Aggressive framing raises *recall* (catches more real holes) but lowers *precision*
(more noise). The majority quorum restores precision. One without the other is a bad trade.

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

### 2. Author the skeptic prompts
Assemble **one prompt per lens** from **Skeptic Lens Prompts** below: the **Shared
Preamble**, then that lens's own section, then the **Shared Tail**. Keep the framing
verbatim — the "default to reject" and "your final message MUST be JSON" clauses are
load-bearing in every lens.

### 3. Run the asymmetry test, then dispatch one skeptic per lens
Before dispatching, name one hole **only that lens could find** — lens 2 is the only one
looking outside the document; lens 3 is the only one that never reads the prose rationale.
If you cannot name one for a lens (typically because there is no context report and lens 2
has nothing external to read), merge it and run two. With two lenses, a finding both reach
is confirmed and everything else is single-vote. Record which lenses you actually
dispatched.

Then spawn **one skeptic per lens, in parallel, via `invoke_subagent`** — one call each for
Internal Consistency · Missing Requirement · Malicious Compliance, fired in a single turn
so they run concurrently and independently. Use `TypeName: research` (or `research-google`
/ `self` instructed to stay read-only if the spec lives in files they must read). Do
**not** let them share a scratchpad — independence is what makes the vote mean something.

### 4. Collect verdicts
Each agent's final message is a fenced JSON block (see **Output Contract**). Parse all three.
If an agent returns prose instead of JSON, re-dispatch that one — do not hand-guess its findings.

### 5. Dedup by identity
Three skeptics will phrase the same hole three different ways. Group findings by a **stable
identity**, not by exact wording. Use `id` (a kebab-case slug each agent assigns) plus the
quoted `clause`. If you tally on raw text you get three 1-vote findings and nothing reaches
quorum.

### 6. Apply the majority gate
- A finding is **confirmed** when it appears in **≥ 2 of 3** skeptic outputs.
- **Cross-lens vs. same-lens.** Record *which lenses* agreed. Two lenses reaching one
  finding from different evidence is independent corroboration and ranks first. A finding
  both raised by lenses that read the same material is weaker than its vote count
  suggests — read the evidence, not the tally.
- A finding with **exactly 1 vote** is a **single-vote** finding. These go to the
  **Single-Vote Findings (triage required)** section and each one needs an explicit
  decision — tightened, accepted as intended behavior, or refuted with a reason. A lone
  finding is more often a real hole one reviewer happened to reach than noise, so "only one
  agent saw it" is not a reason to close it. Spec holes are the cheapest defects in the
  lifecycle to fix and the most expensive to discover later.
- For severity, take the **most common** severity among the agreeing skeptics; on a tie, take the higher.

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
Fill the **The Review Document** template below verbatim.

### 8. Act
> **Under the Supervisor, report — do not edit.** When `starter` / `supervisor` dispatched
> this panel, its node contract in `graph.json` is to write the review and nothing else:
> return the findings and the tallies, and stop. The Supervisor routes each fix back along
> its edge, to `product-owner`, and owns the single-vote triage — leave the `decision` column and
> **Actions Taken** for it. The bullets below that change the spec or triage the tail
> apply when you run this skill standalone.

- For each **confirmed** finding, apply its `tightening` to the spec (or surface it to the user if it changes intent).
- **Triage every single-vote finding** and record the decision in the review.
- If you rewrote the spec materially, re-run the panel once on the revision.
- Tick the **Actions Taken** checklist in the review file as you apply each fix.
- Report the tallies the Supervisor records in the milestone's `state.json`: the lenses
  dispatched, and the `confirmed`, `single_vote` and `cross_lens` counts, plus whether the
  single-vote tail has been triaged (under the Supervisor it has not — that triage is the
  Supervisor's). You do not write `state.json` yourself.

## Skeptic Lens Prompts

Dispatch **once per lens**, three lenses in parallel, via `invoke_subagent`. Each lens gets
the **Shared Preamble**, then its own **Lens** section, then the **Shared Tail**. Replace
`{SPEC}` and `{CONTEXT}` in the preamble.

> **Why not the same prompt three times?** Three identical prompts on one model produce
> correlated errors: the panel is shaped like three votes and carries close to one. The
> lenses below partition the attack surface *and* the reading assignment, so the three
> skeptics can disagree for real reasons instead of by sampling.

At spec stage there is no codebase to partition, so asymmetry comes from **what each lens
reads and in what order**: lens 1 reads the spec against itself, lens 2 reads the world
the spec must fit into, lens 3 reads only the acceptance criteria and tries to satisfy
them dishonestly.

### Panel Composition

| Lens | Owns these categories | Assigned evidence — reads this FIRST, and is the panel's authority on it |
|---|---|---|
| **1 · Internal Consistency** (`internal-consistency`) | `ambiguity`, `contradiction` | The spec **against itself** — every section cross-referenced with every other. |
| **2 · Missing Requirement** (`missing-requirement`) | `missing-requirement` | The **context report, roadmap, and constraints the spec relies on but does not restate**. The world outside the spec. |
| **3 · Malicious Compliance** (`malicious-compliance`) | `malicious-compliance`, `untestable` | **The acceptance criteria alone**, read as an implementation contract to be gamed. |

A lens may report outside its own categories — it must simply record which lens it was
dispatched as. Two lenses reaching the same finding from different reading assignments is
the strongest signal this panel can produce.

### The Asymmetry Test (run before dispatching)

For each lens, name one hole that **only that lens could find**. Lens 2 is the only one
looking outside the document; lens 3 is the only one that never reads the prose rationale.
If you cannot name such a hole for a lens — typically because there is no context report
and lens 2 has nothing external to read — merge it and run two.

### Shared Preamble (prepend to every lens)

```
You are an adversarial spec reviewer on a three-lens panel. You will implement this spec
as literally and lazily as a hostile or careless engineer could.

You are one of three reviewers, each assigned a different reading. You will not see the
others' findings. Work your own assignment to exhaustion rather than surveying the whole
spec shallowly — breadth is the panel's job, depth is yours.

SPEC:
{SPEC}

ADDITIONAL CONTEXT (constraints the spec relies on but may not restate):
{CONTEXT}
```

### Lens 1 — Internal Consistency Skeptic

```
YOUR LENS: what this document says when read against itself. You are the panel's
authority on the spec's internal coherence.

READ FIRST: the whole spec, twice. On the second pass, cross-reference every section
against every other — requirements against acceptance criteria, the overview against the
detail, each user story against the constraints. Do not look outside the document; your
entire evidence base is the text in front of you.

Hunt for:
- Ambiguity: a requirement readable two ways. Pick the DAMAGING reading and show the harm
  that follows from it. "Should be fast" is trivial; hunt the ambiguity that a reasonable
  engineer would resolve wrongly — an unstated default, an undefined pronoun ("it", "the
  record"), a scope word that could include or exclude ("existing users", "all items").
- Contradictions: two requirements that cannot both hold. Section 3 says entries are
  immutable; section 6 describes an edit flow. The overview promises real-time; the
  criteria allow a nightly batch.
- Terminology drift: the same concept named two ways, or one name covering two concepts.
  This is where contradictions hide — find every term used inconsistently and say which
  meaning each site needs.
- Criteria that do not match the requirement they claim to verify: a Given/When/Then that
  would pass on an implementation the requirement forbids.

Quote both halves of every contradiction verbatim. Your finding is not "section 3 and 6
conflict" — it is the two sentences, side by side, and the single implementation decision
that cannot satisfy both.
```

### Lens 2 — Missing Requirement Skeptic

```
YOUR LENS: everything true of the system that this spec fails to mention. You are the
panel's authority on the world the spec must fit into.

READ FIRST: the ADDITIONAL CONTEXT, the context report, the roadmap, and any prior spec
or document it references — before you read the spec's own requirements. Build a picture
of what already exists and what constrains it. Then read the spec and find what it
forgot.

Work this checklist item by item and record a finding for every one the spec does not
answer:
- Error behavior: what happens when the operation fails? Partially fails? Times out?
- Empty, null, zero, one, and huge inputs. What is the maximum? What happens past it?
- Concurrency and ordering: two users, two tabs, two retries. Last-write-wins, or not?
- Authorization: who may do this? Who may see the result? What does an unauthorized
  attempt return — denied, or not-found?
- Limits and quotas: rate, size, count, retention.
- Units, precision, currency, and time zones. "A date" is not a requirement.
- Backward compatibility: existing data, existing clients, in-flight requests.
- Observability: how would anyone know this broke in production?

For each hole, the `clause` field is "<MISSING>" and the `harm` must be concrete: name the
input or the user and the outcome. "Does not specify concurrency" is not a finding;
"two tabs submitting the same form both succeed and the second silently overwrites the
first, with no version check specified" is.
```

### Lens 3 — Malicious Compliance Skeptic

```
YOUR LENS: the laziest implementation that passes. You are the panel's authority on
whether the acceptance criteria actually constrain anything.

READ FIRST — AND ONLY: the acceptance criteria, as a contract you must satisfy while
doing as little useful work as possible. Deliberately do NOT read the spec's prose
rationale, user stories, or motivation on your first pass. The engineer who implements
this in six months will read the criteria and skim the rest; you are simulating that
engineer at their worst.

For each acceptance criterion, write down the cheapest implementation that makes it pass:
- A hardcoded return value that satisfies the example.
- A function that handles the stated case and throws on everything else.
- Satisfying the letter with a stub, a mock, a cached constant, an empty list.
- A UI that displays the required element without wiring it to anything.

Then ask: does the criterion set, taken together, forbid that implementation? If not,
that is a finding — and the `tightening` is the criterion that WOULD forbid it.

Also hunt untestability, which is the same defect from the other side:
- Vague words with no measurable threshold: "fast", "robust", "intuitive", "reliable",
  "user-friendly", "reasonable", "appropriate".
- Criteria with no observable signal — nothing a test could assert on.
- Criteria that cannot fail: "the system handles errors gracefully".

Only after you have gamed every criterion, read the rest of the spec — and report each
place where the intent you then discovered is NOT protected by any criterion. That gap
is the highest-value finding this lens produces.
```

### Shared Tail (append to every lens)

```
Report every hole you find. Do not pre-filter to the ones you judge important, and do not
hold back a finding because you are unsure it matters — the orchestrator filters, you
report.

Be skeptical. DEFAULT TO REJECT: if you are unsure whether something is a hole, report
it. The spec is "ready" only if you genuinely cannot find a damaging interpretation —
and if so you must still list what you attacked and why each attack failed.

For each finding assign a STABLE id: a short kebab-case slug naming the hole
(e.g. "empty-input-undefined", "timeout-no-threshold"). Two reviewers describing the
same hole should plausibly choose the same slug — this is how the panel recognizes
agreement across lenses, so name the HOLE, not your lens's view of it.

Your final message MUST be exactly one fenced JSON block and nothing else, matching:

```json
{
  "lens": "internal-consistency|missing-requirement|malicious-compliance",
  "findings": [
    {
      "id": "kebab-case-stable-slug",
      "category": "ambiguity|contradiction|missing-requirement|malicious-compliance|untestable|other",
      "clause": "verbatim quote of the offending requirement, or \"<MISSING>\" if absent",
      "interpretation": "the malicious or literal reading this permits",
      "harm": "the user-facing or downstream consequence",
      "severity": "high|medium|low",
      "tightening": "a concrete reworded/added requirement that closes the gap"
    }
  ],
  "attacks_that_failed": ["short note for each serious attack you tried that did NOT find a hole"]
}
```
```

## Output Contract

Each skeptic returns the JSON above, tagged with its `lens`. The orchestrator (you)
aggregates into:

```json
{
  "confirmed": [
    { "id": "...", "votes": 2, "lenses": ["internal-consistency", "malicious-compliance"],
      "cross_lens": true, "severity": "high", "clause": "...", "tightening": "..." }
  ],
  "single_vote": [ { "id": "...", "votes": 1, "lenses": ["missing-requirement"], "...": "..." } ]
}
```

**`cross_lens` is the field that matters.** Two lenses reaching one hole from different
reading assignments is independent corroboration. Two votes are not automatically that —
record which lenses agreed, and rank cross-lens agreement above same-lens repetition.

## The Review Document

This is what step 7 writes to
`plans/active_milestones/{moniker}/adversarial-reviews/spec-validation.md`. It is the
human-readable face of the JSON above — a reviewer should grasp the verdict without ever
opening an agent transcript. Use `date +%Y-%m-%d` for the date. Severity icons: 🔴 high ·
🟠 medium · 🟡 low. Order confirmed findings highest-severity first. Keep every section,
even when empty (write `_None._`).

```markdown
# Spec Adversarial Review — {spec title}

> `spec-validator` · 3-lens partitioned panel (internal-consistency · missing-requirement · malicious-compliance), no shared scratchpad · default-to-reject · {2-of-3} majority gate

| Field | Value |
|---|---|
| Milestone | `{moniker}` |
| Run | {`run_id` supplied by the Supervisor, or `standalone`} |
| Artifact | `plans/active_milestones/{moniker}/spec.md` |
| Date | {YYYY-MM-DD} |
| Lenses dispatched | {internal-consistency · missing-requirement · malicious-compliance — or the two actually run, and why} |
| Gate | {2-of-3 · any-one · unanimous} |
| Result | **{N} confirmed ({X} cross-lens) · {M} single-vote** — highest severity **{high}** |

## Verdict

{1–3 plain-language sentences: is the spec ready to plan against, or what blocks it?}

## Confirmed Findings (≥ 2 votes)

> Fold each **Tightening** into the spec before any plan is drafted.

### 🔴 `{id}` — {one-line name}  · {votes}/3 · lenses: {lenses} · cross-lens: {true|false}
- **Clause:** "{verbatim quote, or `<MISSING>`}"
- **Malicious reading:** {the damaging interpretation this permits}
- **Harm:** {user-facing or downstream consequence}
- **Tightening:** {the concrete reworded / added requirement that closes it}

_(repeat per confirmed finding)_

## Single-Vote Findings (triage required)

> One skeptic found these and the others did not. That is not evidence they are wrong — a
> lone finding is more often a real hole one reviewer happened to reach than noise.
> **Each row needs a decision** — tightened, accepted as intended behavior, or refuted
> with a reason. Do not close this section by ignoring it. Spec holes are the cheapest
> defects in the lifecycle to fix and the most expensive to discover later.

| `id` | lens | severity | clause | decision |
|---|---|---|---|---|
| `{id}` | {lens} | 🟠 medium | "{clause}" | {tightened / intended, confirmed with author / refuted because …} |

## Attacks That Failed

- {short note per serious attack that found no hole} — corroborates the spec holds here.

## Actions Taken

- [x] Folded `{id}` tightening into spec §{n}
- [ ] Triaged single-vote finding `{id}` → {decision}
- [ ] Re-ran panel on revision → `spec-validation-r2.md` _(or: not needed)_
```

## Worked Example

> Spec excerpt: *"The export endpoint returns the user's records as a downloadable file."*

Three lens skeptics dispatched. Results after dedup + majority gate:

**Confirmed (≥2 votes):**
- `format-unspecified` (3 votes, high, cross-lens) — "downloadable file" names no format. Malicious read: return an empty `.txt`. Tightening: *"returns a UTF-8 CSV with header row matching the schema in §2; one record per row."*
- `no-pagination-limit` (2 votes, high — `missing-requirement` + `malicious-compliance`, cross-lens) — no bound on record count. Malicious read: stream 10M rows, OOM the server. Tightening: *"records exceeding 50k are paginated via `?cursor=`; a single response returns ≤ 50k rows."*

**Single vote (triage required):**
- `auth-on-export` (1 vote, medium — `missing-requirement`) — the spec doesn't restate that export honors row-level access. Triaged with the author: **intended** — row-level access is enforced globally at the data layer per the platform spec, so restating it here would be redundant. Recorded so the next reader doesn't re-raise it.

The two confirmed holes get written into the spec before any plan is drafted.

## Red Flags

| Thought | Reality |
|---|---|
| "Three identical prompts give me three independent opinions." | They give one opinion sampled three times. Correlated skeptics manufacture false corroboration — partition the lens *and* the reading assignment. |
| "The spec looks thorough, one skeptic is enough." | One agent trends toward agreement. The vote needs ≥3 independent runs. |
| "I'll let the three agents collaborate." | Shared context collapses them toward consensus; the vote becomes meaningless. |
| "Only 1 skeptic flagged it, so ignore it." | Wrong default. The lone finding is usually real. Triage it and record the decision. |
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
