---
name: spec-deliberator
description: Use when a drafted spec depends on knowledge that is siloed across stakeholders, documents, or repos — BEFORE adversarial validation — to improve the spec by deliberation rather than attack. Dispatches delegate agents with deliberately DISJOINT context bundles (product, engineering, ops/security) who deliberate over bounded rounds, relayed verbatim by the orchestrator, until they converge on a single jointly revised spec. Symptoms - "deliberate on this spec", "improve this spec from multiple perspectives", "get product/eng/security input on the spec", "the constraints live in different places", spec touches systems whose limits no single context window can hold, resolving the unconfirmed tail of a spec-validator run.
tools:
  - view_file
  - write_to_file
  - list_dir
  - grep_search
  - invoke_subagent
---

# Deliberative Spec Improvement

## Overview

Dispatch a small panel of **delegate** agents — each seeded with a *different, disjoint*
slice of the relevant knowledge — who deliberate through orchestrator-relayed dialogue
until they converge on **one jointly revised spec**. The pattern instantiates
*deliberative collaboration*: a cooperative joint decision under partial, asymmetric
observability, where dialogue exists to transport information and align beliefs
(arXiv:2607.06157).

This is the **generative** counterpart to `spec-validator`. Skeptics attack a finished
artifact independently and vote; delegates *build* the artifact together and must reach
consensus. Skeptics are forbidden to communicate; for delegates, communication is the
entire mechanism.

**Announce at start:** "I'm using the spec-deliberator skill to improve this spec through a multi-perspective delegate panel."

## When to Use

- A spec draft exists but its correctness depends on constraints scattered across
  sources no single agent naturally holds: user research, infra limits, compliance
  policy, a legacy repo's real behavior.
- Stakeholder perspectives genuinely conflict and the spec must reconcile them
  (latency vs. cost, UX vs. security) rather than pick one silently.
- A `spec-validator` run left **unconfirmed 1-vote findings** the author cannot
  adjudicate alone — deliberation over exactly that disputed tail is the highest-value
  hybrid (see **Relationship to spec-validator**).

## When NOT to Use

- **All relevant context fits comfortably in one prompt.** Merge it and revise
  centrally — a single agent with merged observations empirically beats a deliberating
  panel whenever merging is possible (the paper's centralized baseline wins by up to
  +34 normalized reward). Deliberation earns its cost only when merging is impossible
  or the contexts are genuinely siloed.
- You want defects found, not content improved — use `spec-validator`.
- No spec draft exists — brainstorm or run `product-owner` first.
- The spec is a one-liner; overhead exceeds benefit.

## Core Principle

Four things make deliberation productive instead of theater. All four are required:

1. **Engineered knowledge asymmetry** — each delegate receives a context bundle the
   others do NOT have. Apply the **asymmetry test** before dispatching: for every
   delegate, name at least one concrete fact only that delegate knows that could change
   the spec. If you cannot, you have a panel of clones — fall back to centralized
   revision.
2. **Shared artifact, forced convergence** — delegates do not produce three opinions;
   they accept or amend a single versioned proposal until all accept the same version.
   The output is one revised spec, not a survey.
3. **Bounded, verbatim-relayed dialogue** — subagents cannot talk directly, so the
   orchestrator relays the transcript. Relay utterances **verbatim, never paraphrased**:
   information degrades in transit, and lossy relaying reintroduces exactly the
   information-loss failure deliberation exists to overcome. Hard cap: **4 rounds**.
4. **Earned acceptance** — an acceptance without a stated basis is invalid. Each
   delegate accepting a proposal must say *what it verified against its private bundle*
   or *what argument changed its mind*. This is the guard against sycophantic round-1
   consensus, and it is what preserves deliberation's one empirical edge over
   centralization: reflection — a partner's challenge catching an error the author
   would have kept.

## Panel Composition

Default panel is **3 delegates** (4 max — each extra delegate adds a full turn to every
round). Choose roles so the knowledge partition is natural:

| Delegate | Typical private bundle | Typical concerns |
|---|---|---|
| **Product** | User research, support tickets, roadmap, usage stats | Who needs this, real workflows, what "done" means to a user |
| **Engineering** | Infra limits, API contracts, the actual codebase, perf budgets | Feasibility, timeouts, data shapes, migration cost |
| **Ops / Security** | Compliance policy, ACL model, audit requirements, on-call runbooks | Least privilege, failure modes, observability, data retention |

Substitute freely (e.g. swap Ops for a *Data* delegate holding schema docs, or a
*Legacy* delegate that has read the old system's source). The roles matter less than
the partition: **disjoint bundles, jointly covering everything the spec depends on**.

## Process

### 1. Gather and partition
- Collect the spec text and inventory every context source it depends on: docs,
  constraints, research, code the delegates may need to read.
- Partition the sources into 2–4 **disjoint bundles**, one per delegate. Overlap is
  tolerable (real observations overlap); identical bundles are not.
- Run the **asymmetry test** (Core Principle 1). If it fails, stop and revise
  centrally instead — say so to the user.

### 2. Author delegate prompts
Fill the **Delegate Prompt Template** below once per delegate, varying only the role,
the private bundle, and the concern list. The "acceptance requires a basis" and
"your final message MUST be JSON" clauses are load-bearing — keep them verbatim.

### 3. Dispatch round 1 (sequential turns)
Turns are **sequential, not parallel** — delegate 2 must see delegate 1's utterance,
or proposals oscillate instead of converging.

- Spawn delegate 1 via the `Agent` tool with its prompt (spec + private bundle,
  empty transcript). Parse its JSON turn.
- Spawn delegate 2 with its own prompt **plus the transcript so far** (verbatim).
  Then delegate 3.
- Track `current_proposal` as a **versioned edit list** (v1, v2, …): whenever a
  delegate's turn contains amendments, apply them to produce the next version and
  record which version each delegate has accepted.
- Use `subagent_type: "general-purpose"` (or `"Explore"` if a bundle is "go read this
  part of the codebase").

### 4. Run subsequent rounds via SendMessage
For rounds 2+, **continue the same agents with `SendMessage`** — never respawn. A
respawned delegate loses its private reasoning context and its memory of why it
objected; continuation is what makes its stance consistent across rounds. Each
message contains only the new transcript entries since that delegate's last turn,
verbatim, plus the current proposal version.

### 5. Terminate
- **Convergence:** every delegate has accepted the *same* proposal version → done.
- **Round cap (4) reached without convergence:** the orchestrator arbitrates — adopt
  the majority position on each disputed edit, and record every unresolved dispute
  in the deliberation record for the user to decide. Never silently pick a side on a
  dispute where a delegate cited a hard constraint (a policy, a real timeout);
  escalate those to the user.
- **A delegate returns prose instead of JSON:** re-send the turn request; do not
  hand-interpret its stance.

### 6. Apply and persist
- Apply the converged edit list to produce the revised
  `plans/active_milestones/{moniker}/spec.md`. Do not rewrite untouched sections.
- Write the deliberation record to
  `plans/active_milestones/{moniker}/deliberations/spec-deliberation.md` (create the
  folder if needed; bare spec with no milestone → `plans/deliberations/spec-deliberation.md`
  and say so). **Always write it, even if the panel converged on "no changes"** —
  who knew what, who conceded what, and why is the audit trail. Re-runs append
  `-r2`, `-r3`, … Fill the **Deliberation Record** template verbatim.

### 7. Hand off to validation
Deliberation is generative, not evaluative — the delegates were building, and builders
have blind spots that consensus does not cure. **Run `spec-validator` on the revised
spec** before any plan is written. The panel improving a spec is not evidence the spec
survives attack.

## Delegate Prompt Template

Dispatch once per delegate via the `Agent` tool. Replace `{ROLE}`, `{CONCERNS}`,
`{PRIVATE_BUNDLE}`, `{SPEC}`, `{TRANSCRIPT}`, and `{CURRENT_PROPOSAL}`.

```
You are the {ROLE} delegate on a spec deliberation panel. The panel's shared goal is
ONE revised spec that every delegate can accept. You share the reward: a spec that
fails in production fails for all of you, whichever delegate's blind spot caused it.

You hold PRIVATE KNOWLEDGE the other delegates do not have. Your job is to
(a) surface every private fact that should change the spec — an undisclosed
constraint is a defect you caused — and (b) challenge proposals that contradict
your knowledge, citing the specific fact, not your intuition.

SPEC UNDER DELIBERATION:
{SPEC}

YOUR PRIVATE BUNDLE (only you can see this):
{PRIVATE_BUNDLE}

YOUR CONCERNS: {CONCERNS}

TRANSCRIPT SO FAR (verbatim, may be empty in round 1):
{TRANSCRIPT}

CURRENT PROPOSAL: version {v}, edits: {CURRENT_PROPOSAL}

Rules of deliberation:
- Ground every objection in a fact from your bundle. Cite it. "This feels risky"
  is not a turn.
- Do not concede to end the conversation. Accept ONLY if the proposal is consistent
  with everything in your bundle, and state your acceptance basis: what you checked,
  or what argument changed your mind.
- Do not restate what the transcript already establishes; add information or
  challenge, or accept.
- Propose amendments as concrete spec edits, not sentiments.

Your final message MUST be exactly one fenced JSON block and nothing else, matching:

```json
{
  "utterance": "what you say to the panel this turn — arguments, disclosures, reactions",
  "disclosures": ["each private fact you introduced into the record this turn"],
  "amendments": [
    {
      "section": "spec section or heading the edit targets",
      "edit": "the concrete replacement/added text",
      "reason": "the private fact or transcript argument motivating it"
    }
  ],
  "stance": "accept|amend|object",
  "acceptance_basis": "REQUIRED when stance is accept: what you verified against your bundle, or what changed your mind. Empty otherwise."
}
```
```

## Output Contract

Each turn returns the JSON above. The orchestrator (you) maintains:

```json
{
  "proposal_versions": [ { "version": 2, "edits": ["..."], "produced_by": "engineering, round 1" } ],
  "acceptances": { "product": 2, "engineering": 2, "ops": 1 },
  "disputes": [ { "topic": "...", "positions": {"product": "...", "ops": "..."}, "resolution": "converged v2 | escalated" } ]
}
```

Convergence = all delegates' accepted version equals the latest version.

## The Deliberation Record

Written in step 6 to `plans/active_milestones/{moniker}/deliberations/spec-deliberation.md`.
A reader should understand what changed and *why* without opening any transcript. Use
`date +%Y-%m-%d` for the date. Keep every section, even when empty (write `_None._`).

```markdown
# Spec Deliberation — {spec title}

> `spec-deliberator` · {N} delegates with disjoint context bundles · verbatim relay · {R} rounds to convergence

| Field | Value |
|---|---|
| Milestone | `{moniker}` |
| Artifact | `plans/active_milestones/{moniker}/spec.md` |
| Date | {YYYY-MM-DD} |
| Panel | {product · engineering · ops} |
| Outcome | **{converged on v{n} · arbitrated · escalated}** — {K} edits applied |

## Verdict

{1–3 sentences: what materially changed in the spec and why the panel was needed —
which siloed fact drove the biggest edit.}

## Panel & Bundles

| Delegate | Private bundle (summary) | Key disclosure |
|---|---|---|
| product | {what only it saw} | {the fact that mattered} |

## Edits Applied (converged proposal v{n})

### `{section}` — {one-line description}
- **Before:** "{original clause, or `<ABSENT>`}"
- **After:** "{revised clause}"
- **Driven by:** {delegate} — {the private fact or challenge that forced it}
- **Accepted by:** all, round {r} _(bases: {one clause per delegate})_

_(repeat per edit)_

## Disputes

| Topic | Positions | Resolution |
|---|---|---|
| {topic} | product: {…} / ops: {…} | {converged v{n} · arbitrated (majority) · 🛑 escalated to user} |

## Round Log

- **R1:** {one line per delegate: disclosed X, proposed Y / objected to Z}
- **R2:** {…}

## Handoff

- [ ] Revised spec written to `spec.md`
- [ ] `spec-validator` run on the revision → `adversarial-reviews/spec-validation.md`
- [ ] Escalated disputes decided by user _(or: none)_
```

## Relationship to spec-validator

The two skills are inverses; use them in sequence, not as alternatives.

| | `spec-deliberator` | `spec-validator` |
|---|---|---|
| Mode | Generative — improve the spec | Evaluative — break the spec |
| Information | Partial, disjoint bundles — dialogue transports it | Complete, identical — communication forbidden |
| Interaction | Multi-turn, sequential, verbatim relay | One-shot, parallel, independent |
| Convergence | Consensus on one versioned proposal | 2-of-3 majority vote on findings |
| Error control | Reflection — a partner's challenge | Statistics — uncorrelated votes |

**Pipeline:** `product-owner` (draft) → `spec-deliberator` (enrich with siloed
constraints) → `spec-validator` (attack) → fold tightenings → plan.

**The hybrid round:** after a `spec-validator` run, its *unconfirmed 1-vote findings*
are precisely where independent judgment ran out. Convening a mini-panel (2 delegates,
2 rounds max) over only those findings — one delegate briefed to defend the spec's
intent, one holding the skeptic's finding — imports deliberation's reflection benefit
at the point of maximum uncertainty without contaminating the validator's independent
pass. Record it as `deliberations/spec-deliberation-tail.md`.

## Worked Example

> Spec draft: *"The export endpoint returns the user's records as a downloadable file. Exports should be fast and handle large accounts."*

Bundles: **product** gets user research (exports used for tax filing; 95% of accounts
< 10k records; CSV expected), **engineering** gets infra docs (30s gateway timeout,
100MB response cap, sharded store), **ops** gets the data policy (row-level ACLs,
audit logging mandatory).

- **R1 — engineering** discloses the 30s timeout: "fast" and "large accounts" cannot
  both be synchronous; proposes async-only export (v1).
- **R1 — product** objects to v1 citing its bundle: 95% of accounts are small and
  users export interactively at tax time; amends to sync ≤ 50k records, async above
  (v2). Also discloses: format must be CSV with a stable header — "a file" is
  underspecified.
- **R1 — ops** accepts v2's shape but amends: the async worker must run under the
  requester's ACLs, not a service account, and every export is audit-logged (v3).
- **R2 —** engineering accepts v3 (basis: checked v3's sync threshold against the
  response cap — 50k rows ≈ 12MB, fits); product accepts v3 (basis: interactive path
  preserved); ops accepts v3 (basis: its own amendment). **Converged, v3, 2 rounds.**

Three facts from three silos — the timeout, the tax-time workflow, the ACL rule —
none of which any single delegate held. The revised spec then goes to
`spec-validator`, which now has real thresholds to attack instead of "fast".

## Red Flags

| Thought | Reality |
|---|---|
| "I'll give every delegate the full context so they're all informed." | That's a panel of clones — and a single merged-context agent beats it. Asymmetry is the entire reason to deliberate. |
| "They all accepted in round 1, great." | Round-1 unanimous acceptance with thin `acceptance_basis` is sycophancy, not consensus. Re-prompt: acceptance requires a stated verification or a changed mind. |
| "I'll summarize the transcript between turns to save tokens." | Verbatim relay is load-bearing. Paraphrase loses the exact constraint values whose transport is the point. |
| "They can keep talking until they agree." | Cap at 4 rounds. Past that, positions are entrenched; arbitrate and escalate hard-constraint disputes. |
| "I'll respawn a fresh agent each round with the transcript." | A respawn forgets its private reasoning and why it objected. Continue the same agent with SendMessage. |
| "The panel agreed, so the spec is validated." | The panel *built* it; builders share blind spots. Consensus is not adversarial survival — run `spec-validator`. |
| "More delegates, more perspectives." | Each delegate adds a turn to every round. 3 is the default, 4 the max; split bundles, not headcount. |

## Calibration Note

Deliberation is the expensive path, and the evidence says so: with mergeable context, a
centralized agent dominates (arXiv:2607.06157 finds oracle-merged baselines beat
deliberating pairs by up to +34 normalized reward, and information demonstrably degrades
in dialogue transit). What deliberation buys — the only thing it buys — is (a) access to
knowledge that *cannot* be merged, and (b) reflection: the measurable cases where a
partner's challenge corrected an error a solo agent kept. Every rule above serves one of
those two: the asymmetry test protects (a); earned acceptance, verbatim relay, and
grounded objections protect (b). When you find yourself relaxing a rule, check which of
the two you just gave up.
