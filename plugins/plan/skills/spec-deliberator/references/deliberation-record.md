# The Deliberation Record — spec-deliberator

Written by Process step 6 to
`plans/active_milestones/{moniker}/deliberations/spec-deliberation.md`. A reader should
understand what changed and *why* without opening any transcript.

Use `date +%Y-%m-%d` for the date. Keep every section, even when empty (write `_None._`).
Match length to substance — the Round Log is one line per delegate per round, not a
retelling of the dialogue.

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
