---
name: spec-validator
description: Use after a spec or design doc is drafted and BEFORE writing an implementation plan, to find defects while they are still cheap to fix. Dispatches independent skeptic agents that attack the spec for ambiguity, missing or contradictory requirements, and untestable acceptance criteria, then keeps only findings confirmed by a 2-of-3 majority. Symptoms - "validate this spec", "poke holes in this design", "is this spec ready to plan against", finishing brainstorming before writing-plans, a freshly written specs/*.md.
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

# Adversarial Spec Validation (TypeSafe Accelerated)

## Overview

Dispatch a panel of independent **skeptic** agents whose only job is to break a spec
*before* anyone writes a plan or code against it. At spec stage there is no code to test,
so the attack surface is the **language of the spec itself**: ambiguity, gaps,
contradictions, and acceptance criteria that cannot actually be verified.

This skill is powered by a **Hybrid System One (TypeSafe Jev) + System Two (LLM Skeptics)**
architecture:
1. **Pre-flight Sieve (<250ms)**: Fast-screens the spec for untestable buzzwords or missing error paths before launching skeptics.
2. **System Two Skeptics**: 3 parallel LLMs actively attack the spec with a default-to-reject posture.
3. **Semantic Dedup & Quorum**: Clusters findings by semantic root cause via TypeSafe rather than brittle kebab-case slug matching.
4. **SDE Tail Cascade**: Automatically promotes high-confidence solo catches ($P \ge 0.85$) and filters noise ($P < 0.40$).
5. **Calibrated Severity**: Uses TypeSafe's continuous 4-level ordinal Score rubric.

**Announce at start:** "I'm using the spec-validator skill to attack this spec with a TypeSafe-accelerated skeptic panel."

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
3. **Independent quorum + TypeSafe alignment** — run **N = 3** skeptics that never see each other's output, cluster them semantically, and keep findings confirmed by a **majority (2 of 3)** or promoted via SDE cascade.

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

### 2. Run Pre-Flight Sieve (Advisory Screen)
Run the fast pre-flight screen via `run_command` in advisory mode:
```bash
python3 plugins/plan/tools/typesafe_validator_engine.py preflight --stage spec --file path/to/spec.md
```
- If advisory warnings are flagged (e.g. unquantified buzzwords or missing error paths), inject them into the skeptic prompt so skeptics specifically attack those weaknesses.
- Add `--strict` if you want to abort immediately on fatal structural gaps.

### 3. Author the skeptic prompt
Fill the template in **Skeptic Prompt Template** below. Keep the framing verbatim — the
"default to reject" and "your final message MUST be JSON" clauses are load-bearing.

### 4. Dispatch 3 skeptics in parallel
Spawn the **3 skeptics in parallel via `invoke_subagent`** so they run concurrently and
independently. Use `TypeName: research` (or `research-google` / `self` instructed to stay
read-only if the spec lives in files they must read). Do **not** let them share a
scratchpad — independence is what makes the vote mean something.

### 5. Collect verdicts
Each agent's final message is a fenced JSON block (see **Output Contract**). Save each
fenced JSON to a temporary file (e.g. `/tmp/s1.json`, `/tmp/s2.json`, `/tmp/s3.json`).

### 6. Semantic Dedup, Tail Triage & Report Synthesis
Run the validator engine synthesizer to cluster findings by semantic root cause, triage the
1-vote tail, calibrate severity, and generate the review markdown report:
```bash
python3 plugins/plan/tools/typesafe_validator_engine.py synthesize \
  --stage spec \
  --target path/to/spec.md \
  --skeptics /tmp/s1.json /tmp/s2.json /tmp/s3.json \
  --out plans/active_milestones/{moniker}/adversarial-reviews/spec-validation.md
```
- **Quorum gate:** Confirmed when ≥2 skeptics land on the same semantic root cause.
- **SDE Tail Triage:** 1-vote findings with $P(\text{defect}) \ge 0.85$ are auto-promoted to confirmed; noise ($P < 0.40$) is filtered out.
- **Calibrated Severity:** Scored against an objective 4-level descriptive rubric.
*(If `TYPESAFE_API_KEY` is not set, the engine automatically falls back to heuristic token matching and mode severity.)*

### 7. Act
- For each **confirmed** finding, apply its `tightening` to the spec (or surface it to the user if it changes intent).
- Review surviving **unconfirmed** tail items.
- If you rewrote the spec materially, re-run the panel once on the revision.
- Tick the **Actions Taken** checklist in the review file as you apply each fix.

## Skeptic Prompt Template

Dispatch this **three times, unchanged**, via `invoke_subagent`. Replace only `{SPEC}`
(and `{CONTEXT}` if any).

```
You are an adversarial spec reviewer. You will implement this spec as literally and
lazily as a hostile or careless engineer could. Your goal is to find every way the
letter of this spec can be satisfied while its intent is violated, and every place it
is ambiguous, incomplete, contradictory, or untestable.

SPEC:
{SPEC}

ADDITIONAL CONTEXT (constraints the spec relies on but may not restate):
{CONTEXT}

Attack the spec across these categories:
- Ambiguity: a requirement readable two ways — pick the damaging reading.
- Missing requirements: error behavior, empty/null/huge inputs, concurrency and
  ordering, auth, limits, units, time, backward compatibility.
- Contradictions: two requirements that cannot both hold; architecture vs. features.
- Untestable acceptance criteria: vague words with no measurable threshold.
- Malicious compliance: the laziest implementation that passes every stated criterion
  yet is useless.

Be skeptical. DEFAULT TO REJECT: if you are unsure whether something is a hole, report
it. The spec is "ready" only if you genuinely cannot find a damaging interpretation —
and if so you must still list what you attacked and why each attack failed.

For each finding assign a STABLE id: a short kebab-case slug naming the hole
(e.g. "empty-input-undefined", "timeout-no-threshold"). Two reviewers describing the
same hole should plausibly choose the same slug.

Your final message MUST be exactly one fenced JSON block and nothing else, matching:

```json
{
  "findings": [
    {
      "id": "kebab-case-stable-slug",
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

Each skeptic returns the JSON above. The orchestrator (you) aggregates into:

```json
{
  "confirmed": [ { "id": "...", "votes": 3, "severity": "high", "clause": "...", "tightening": "..." } ],
  "unconfirmed": [ { "id": "...", "votes": 1, "...": "..." } ]
}
```

## The Review Document

This is what step 7 writes to
`plans/active_milestones/{moniker}/adversarial-reviews/spec-validation.md`. It is the
human-readable face of the JSON above — a reviewer should grasp the verdict without ever
opening an agent transcript. Use `date +%Y-%m-%d` for the date. Severity icons: 🔴 high ·
🟠 medium · 🟡 low. Order confirmed findings highest-severity first. Keep every section,
even when empty (write `_None._`).

```markdown
# Spec Adversarial Review — {spec title}

> `spec-validator` · 3 independent skeptics, no shared scratchpad · default-to-reject · {2-of-3} majority gate

| Field | Value |
|---|---|
| Milestone | `{moniker}` |
| Artifact | `plans/active_milestones/{moniker}/spec.md` |
| Date | {YYYY-MM-DD} |
| Gate | {2-of-3 · any-one · unanimous} |
| Result | **{N} confirmed · {M} unconfirmed** — highest severity **{high}** |

## Verdict

{1–3 plain-language sentences: is the spec ready to plan against, or what blocks it?}

## Confirmed Findings (≥ 2 votes)

> Fold each **Tightening** into the spec before any plan is drafted.

### 🔴 `{id}` — {one-line name}  · {votes}/3
- **Clause:** "{verbatim quote, or `<MISSING>`}"
- **Malicious reading:** {the damaging interpretation this permits}
- **Harm:** {user-facing or downstream consequence}
- **Tightening:** {the concrete reworded / added requirement that closes it}

_(repeat per confirmed finding)_

## Unconfirmed (FYI · 1 vote)

| `id` | severity | clause | note |
|---|---|---|---|
| `{id}` | 🟠 medium | "{clause}" | surfaced for the author to confirm intent |

## Attacks That Failed

- {short note per serious attack that found no hole} — corroborates the spec holds here.

## Actions Taken

- [x] Folded `{id}` tightening into spec §{n}
- [ ] Surfaced `{id}` (unconfirmed) to the user
- [ ] Re-ran panel on revision → `spec-validation-r2.md` _(or: not needed)_
```

## Worked Example

> Spec excerpt: *"The export endpoint returns the user's records as a downloadable file."*

Three skeptics dispatched. Results after dedup + majority gate:

**Confirmed (≥2 votes):**
- `format-unspecified` (3 votes, high) — "downloadable file" names no format. Malicious read: return an empty `.txt`. Tightening: *"returns a UTF-8 CSV with header row matching the schema in §2; one record per row."*
- `no-pagination-limit` (2 votes, high) — no bound on record count. Malicious read: stream 10M rows, OOM the server. Tightening: *"records exceeding 50k are paginated via `?cursor=`; a single response returns ≤ 50k rows."*

**Unconfirmed (1 vote, FYI):**
- `auth-on-export` (1 vote, medium) — spec doesn't restate that export honors row-level access. Surfaced for the author to confirm intent.

The two confirmed holes get written into the spec before any plan is drafted.

## Red Flags

| Thought | Reality |
|---|---|
| "The spec looks thorough, one skeptic is enough." | One agent trends toward agreement. The vote needs ≥3 independent runs. |
| "I'll let the three agents collaborate." | Shared context collapses them toward consensus; the vote becomes meaningless. |
| "Only 1 skeptic flagged it, so ignore it." | Log it as unconfirmed. That tail is the recall you paid for. |
| "I'll paraphrase their findings together." | Dedup on stable `id` + quoted clause, not by re-summarizing — or real holes vanish in the merge. |
| "An agent returned prose, I'll interpret it." | Re-dispatch for valid JSON. Don't guess the contract. |

## Calibration Note

The quorum's value is not only deletion. Skeptics frequently *over*-rate severity under
adversarial framing. When agreeing skeptics disagree on severity, the aggregation step is
doing real work: a hole two reviewers call "high" and one calls "medium" lands at high,
but the spread itself tells you the finding is real and the impact is debatable — worth a
sentence to the user rather than a silent edit.
