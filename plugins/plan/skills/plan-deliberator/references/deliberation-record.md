# The Deliberation Record — plan-deliberator

Written by Process step 6 to
`plans/active_milestones/{moniker}/deliberations/plan-deliberation.md`. A reader should
understand what changed in the plan and *which territory's evidence forced it* without
opening any transcript.

Use `date +%Y-%m-%d` for the date. Keep every section, even when empty (write `_None._`).
Match length to substance — the Round Log is one line per delegate per round, not a
retelling of the dialogue.

```markdown
# Plan Deliberation — {plan title}

> `plan-deliberator` · {N} delegates with disjoint territories · evidence-grounded turns · verbatim relay · {R} rounds to convergence

| Field | Value |
|---|---|
| Milestone | `{moniker}` |
| Artifact | `plans/active_milestones/{moniker}/plan.md` |
| Date | {YYYY-MM-DD} |
| Panel | {intent · codebase · delivery} |
| Outcome | **{converged on v{n} · arbitrated · escalated}** — {K} edits applied, {T} trade-offs decided |

## Verdict

{1–3 sentences: what materially changed in the plan and which territory's evidence drove
the biggest change or decided the central trade-off.}

## Panel & Territories

| Delegate | Territory (what it deep-read) | Key disclosure (with evidence) |
|---|---|---|
| codebase | {files/subsystems} | {the fact that mattered} — `{file:line}` |

## Trade-offs Decided

### {topic}
- **Chosen:** {option} — **over** {rejected option}
- **Because:** {each territory's constraint, cited}
- **Accepted by:** all, round {r}

## Edits Applied (converged proposal v{n})

### {target: step/group} — {one-line description}
- **Before:** "{original step/ordering, or `<ABSENT>`}"
- **After:** "{revised}"
- **Driven by:** {delegate} — {cited territory fact}
- **Accepted by:** all, round {r} _(bases: {one clause per delegate})_

_(repeat per edit)_

## Disputes

| Topic | Positions | Resolution |
|---|---|---|
| {topic} | intent: {…} / delivery: {…} | {converged v{n} · arbitrated (majority) · 🛑 escalated to user} |

## Round Log

- **R1:** {one line per delegate: investigated X, disclosed Y, proposed/objected Z}
- **R2:** {…}

## Handoff

- [ ] Revised plan written to `plan.md` (structure preserved: groups, test-first steps)
- [ ] `plan-validator` run on the revision → `adversarial-reviews/plan-validation.md`
- [ ] Escalated disputes decided by user _(or: none)_
```
