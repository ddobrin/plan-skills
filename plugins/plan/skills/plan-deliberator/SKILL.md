---
name: plan-deliberator
description: Use when a drafted implementation plan spans territories no single agent can hold at once — the spec's intent, multiple subsystems of the real codebase, and the delivery pipeline — BEFORE plan-validator, to improve the plan by deliberation rather than attack. Dispatches delegate agents each assigned a different territory to deep-read and speak for, who deliberate over bounded rounds until they converge on a single jointly revised plan, negotiating the trade-offs (migration strategy, group boundaries, scope) that a validator can only flag, never decide. Symptoms - "deliberate on this plan", "improve this plan from multiple perspectives", "the plan touches three subsystems", "we need to pick a migration strategy", plan.md spans code no one context window can deep-read whole, resolving the single-vote tail of a plan-validator run.
---

# Deliberative Plan Improvement

## Overview

Dispatch a small panel of **delegate** agents — each assigned a *different territory* of
the work (the spec's intent, a partition of the real codebase, the delivery pipeline) to
deep-read and speak for — who deliberate through orchestrator-relayed dialogue until they
converge on **one jointly revised plan**. The pattern instantiates *deliberative
collaboration*: a cooperative joint decision under partial, asymmetric observability,
where dialogue transports what each delegate learned in its territory (arXiv:2607.06157).

This is the **generative** counterpart to `plan-validator`. The validator's skeptics take
the plan as fixed and race to predict where it fails; deliberator delegates **reshape**
it — reorder, regroup, retarget, and above all **decide trade-offs** the plan left open
or got wrong. A validator can flag "step 4 has no rollback"; only a deliberation can
weigh an online backfill against an offline migration and commit the plan to one, with
each territory's constraints on the record.

**Announce at start:** "I'm using the plan-deliberator skill to improve this plan through a multi-territory delegate panel."

## When to Use

- A written plan exists (e.g. from `architect`) and it spans more code than one agent
  can deep-read alongside the spec and the delivery constraints — the very condition
  that makes single-author plans rot.
- The plan contains an **open or contestable trade-off**: migration strategy, execution
  group boundaries, build-vs-reuse, sequencing under a deploy window, test depth vs.
  schedule.
- A `plan-validator` run left **single-vote findings** that need adjudication, not
  another vote (see **Relationship to plan-validator**).

## When NOT to Use

- **The plan touches one small subsystem and everything fits one prompt.** Revise
  centrally — a single agent with merged context empirically beats a deliberating panel
  whenever merging is possible. Deliberation earns its cost only when the territories
  are too large to hold together.
- You want failure prediction on a plan you believe is finished — use `plan-validator`.
- No plan exists yet — run `architect` first; deliberation improves a draft, it does
  not replace planning.
- The artifact is a spec (use `spec-deliberator`) or code (use `implementation-validator`).

## Core Principle

Four things make deliberation productive instead of theater. All four are required:

1. **Engineered territory asymmetry** — at plan stage everything is technically readable
   by everyone, so asymmetry is created by **assigned investigation**: each delegate
   deep-reads only its territory and becomes the panel's sole authority on it. Apply the
   **asymmetry test** before dispatching: for each delegate, name one question about
   this plan that only its territory can answer (a real signature, an acceptance
   criterion, a CI constraint). If you cannot, merge the territories and revise
   centrally instead.
2. **Shared artifact, forced convergence** — delegates accept or amend a single
   versioned plan proposal until all accept the same version. The output is one revised
   `plan.md`, not three reviews.
3. **Bounded, verbatim-relayed dialogue** — the orchestrator relays the transcript
   **verbatim, never paraphrased** (a paraphrased signature or step number is exactly
   the information-loss deliberation exists to overcome). Hard cap: **4 rounds**.
4. **Evidence-grounded turns, earned acceptance** — every objection and every
   disclosure cites its territory: `file:line` for code, a quoted clause for the spec,
   a named config/command for the pipeline. An acceptance without a stated basis (what
   the delegate verified in its territory, or what argument changed its mind) is
   invalid — the guard against sycophantic round-1 consensus, and what preserves
   deliberation's empirical edge: reflection, a partner's challenge catching what the
   author would have kept.

## Panel Composition (territories)

Default panel is **3 delegates** (4 max — each extra delegate adds a full turn to every
round). Partition by territory so each has real authority:

| Delegate | Territory (deep-reads this, speaks for it) | Guards |
|---|---|---|
| **Intent** | `spec.md`, acceptance criteria, `00-ROADMAP.md`, context report | Every acceptance criterion maps to a task; no silent scope cuts; no gold-plating the spec never asked for |
| **Codebase** | The files/subsystems the plan touches — open them, trace callers, read the tests | Real signatures and shapes, hidden coupling, seams for TDD, whether execution groups truly touch disjoint files |
| **Delivery** | Build/CI config, test harness, migration tooling, deploy/rollback runbooks | Every verify-step names a runnable command; migration ordering and reversibility; group parallelism is safe in CI, not just on paper |

For a plan spanning multiple subsystems, split **Codebase** into two territory delegates
(e.g. `codebase-api`, `codebase-worker`) rather than adding new role types. The roles
matter less than the partition: **disjoint territories, jointly covering everything the
plan depends on**.

## Process

### 1. Gather and partition
- Collect the plan text, the spec it implements, and the repository root.
- List every territory the plan depends on and partition it across 2–4 delegates.
  Overlap is tolerable; identical assignments are not.
- Run the **asymmetry test** (Core Principle 1). If it fails, revise centrally and say
  so to the user.

### 2. Author delegate prompts (1 parallel template read)
Read `references/delegate-prompt.md` and `references/deliberation-record.md` in a **single parallel `view_file` batch** (`references/worked-example.md` is author documentation — do **not** read it at runtime). Fill `references/delegate-prompt.md` once per delegate, varying the territory, the investigation instructions, and the guard list.

### 3. Dispatch round 1 (parallel disjoint territory investigation → unified Proposal v1, then sequential dispute resolution)
- **Fast-Path Round 1 Territory Fan-Out:** Because the 3 delegates' assigned territories (`Intent`, `Codebase`, `Delivery`) are **disjoint by construction**, their initial territory deep-reads and initial `disclosures` (`file:line` / spec clause / CI command) + `amendments` against `v0` do not depend on one another. Spawn all 3 delegates **concurrently in a single tool-call message** (`Agent` / `invoke_subagent`, empty transcript) so all 3 territories are deep-read in **1 wall-clock turn** instead of 3 sequential turns (`max(T1, T2, T3)` instead of `T1 + T2 + T3`).
- Parse all 3 JSON turns, append all 3 Round 1 utterances **verbatim** to `{TRANSCRIPT}`, and merge all non-conflicting Round 1 amendments into `current_proposal` (**Proposal `v1`**), flagging any directly conflicting trade-offs or edits.

### 4. Run subsequent rounds via `SendMessage` / `send_message`
For rounds 2+, **continue the same agents with `SendMessage` (`send_message`)** — never respawn when continuation is supported. A respawned delegate loses everything it read in its territory and why it objected; continuation is what makes its authority real across rounds.
- **Fast-Path Round 2 Convergence:** If Round 1 amendments had **zero cross-territory conflicts**, message all 3 delegates concurrently with the verbatim Round 1 transcript + unified **Proposal `v1`** to verify `v1` against their territories and return an earned `acceptance_basis` (allowing compatible territory refinements to converge in **2 wall-clock turns** instead of 6–9 sequential turns).
- **Sequential Trade-Off & Dispute Relay:** Whenever two delegates propose conflicting amendments or `stance: "object"` on a trade-off, relay turns **sequentially** across the disputing delegates so each reacts to the latest version (`v2`, `v3`, …) verbatim until convergence or the 4-round cap.
- If a harness lacks `send_message` and requires re-invoking delegates, embed each delegate's own Round 1 `disclosures` (`territory_evidence_digest`) into its Round 2+ prompt and instruct it **not** to re-open or re-grep files already inspected in Round 1 unless another delegate's turn raises a new `file:line` question.

### 5. Terminate
- **Convergence:** every delegate has accepted the *same* proposal version → done.
- **Round cap (4) reached:** the orchestrator arbitrates — adopt the majority position
  per disputed edit and record every unresolved dispute. Never silently overrule a
  delegate citing a hard constraint (`file:line` that contradicts a step, a failing CI
  requirement, an acceptance criterion); escalate those to the user.
- **Prose instead of JSON:** re-send the turn request; never hand-interpret a stance.

### 6. Apply and persist
- Apply the converged edit list to produce the revised
  `plans/active_milestones/{moniker}/plan.md`. Preserve the plan's structure (parallel
  execution groups, per-task test steps) — deliberation edits the plan, it does not
  reformat it.
- Write the deliberation record to
  `plans/active_milestones/{moniker}/deliberations/plan-deliberation.md` (create the
  folder if needed; bare plan with no milestone → `plans/deliberations/plan-deliberation.md`
  and say so). **Always write it, even if the panel converged on "no changes"** — who
  investigated what, which trade-off was decided on which evidence, is the audit trail.
  Re-runs append `-r2`, `-r3`, …

  Fill the template in `references/deliberation-record.md`. See
  `references/worked-example.md` for a complete run.

### 7. Hand off to validation
Deliberation is generative, not evaluative — the delegates were reshaping, and a panel
that just negotiated a trade-off is invested in it. **Run `plan-validator` on the
revised plan** before execution. Consensus is not adversarial survival.

## Relationship to plan-validator

The two skills are inverses; use them in sequence, not as alternatives.

| | `plan-deliberator` | `plan-validator` |
|---|---|---|
| Mode | Generative — reshape the plan, decide trade-offs | Evaluative — predict where the fixed plan fails |
| Information | Partial by assignment — each delegate deep-reads one territory | Complete — every skeptic may read anything |
| Interaction | Multi-turn, sequential, verbatim relay | One-shot, parallel, independent |
| Convergence | Consensus on one versioned proposal | 2-of-3 majority vote on findings |
| Error control | Reflection — a partner's cited challenge | Statistics — uncorrelated votes + `file:line` evidence |
| Can it decide "online backfill vs offline migration"? | Yes — that is its job | No — it can only flag the absence of a decision |

**Pipeline:** `architect` (draft plan) → `plan-deliberator` (reshape with territory
evidence, decide trade-offs) → `plan-validator` (attack) → fold fixes → 🛑 human gate →
execute.

**The hybrid round:** after a `plan-validator` run, its *single-vote findings* are where
independent judgment ran out. Convene a mini-panel (2 delegates, 2 rounds max) over only
those findings — one delegate briefed to defend the plan's approach, one assigned the
territory the finding concerns, both citing evidence. Record it as
`deliberations/plan-deliberation-tail.md`.

## Red Flags

| Thought | Reality |
|---|---|
| "I'll let every delegate read the whole repo so they're all informed." | Then no one is the authority on anything and you have three shallow generalists — a single merged-context agent beats that. Assign territories. |
| "They all accepted in round 1, great." | Round-1 unanimity with thin `acceptance_basis` is sycophancy. Re-prompt: acceptance requires cited verification or a changed mind. |
| "A delegate asserted `dispatch()` doesn't exist but cited nothing." | Uncited territory claims are guesses. Send it back for `file:line` before the panel reacts to it. |
| "I'll summarize the transcript between turns." | Verbatim relay is load-bearing — a paraphrased signature or step number corrupts exactly what deliberation transports. |
| "They can keep talking until they agree." | Cap at 4 rounds; arbitrate, escalate hard-evidence disputes to the user. |
| "I'll respawn fresh agents each round with the transcript." | A respawn forgets everything it read in its territory. Continue the same agents with SendMessage. |
| "The panel agreed, so skip plan-validator." | The panel is invested in the trade-off it just negotiated. Consensus is not adversarial survival — run the validator. |
| "More delegates, more coverage." | Each delegate adds a turn to every round. Split territories across 3 (max 4); never add headcount without a disjoint territory to assign. |

## Calibration Note

Deliberation is the expensive path, and the evidence says so: with mergeable context, a
centralized agent dominates (arXiv:2607.06157 — oracle-merged baselines beat
deliberating panels by up to +34 normalized reward, and information demonstrably
degrades in dialogue transit). What deliberation buys at plan stage is (a) **depth per
territory** — three delegates can each *actually read* their subsystem where one agent
skims all three, and (b) **decided trade-offs with constraints on the record** — the
one thing a validator structurally cannot produce. Every rule above serves one of
those: the asymmetry test and territory assignment protect (a); evidence-grounded
turns, earned acceptance, and verbatim relay protect (b). When you relax a rule, check
which one you just gave up — and remember the panel's consensus is a *draft decision*,
not a verdict: the verdict belongs to `plan-validator` and the human gate.
