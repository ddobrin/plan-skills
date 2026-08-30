# The Review Document — spec-validator

Written by Process step 7 to
`plans/active_milestones/{moniker}/adversarial-reviews/spec-validation.md`. It is the
human-readable face of the aggregated JSON — a reviewer should grasp the verdict without
ever opening an agent transcript.

Use `date +%Y-%m-%d` for the date. Severity icons: 🔴 high · 🟠 medium · 🟡 low. Order
confirmed findings highest-severity first. Keep every section, even when empty (write
`_None._`). Keep entries tight: one line per field, no restated summaries.

```markdown
# Spec Adversarial Review — {spec title}

> `spec-validator` · 3 independent skeptics, no shared scratchpad · default-to-reject · {2-of-3} majority gate

| Field | Value |
|---|---|
| Milestone | `{moniker}` |
| Artifact | `plans/active_milestones/{moniker}/spec.md` |
| Date | {YYYY-MM-DD} |
| Gate | {2-of-3 · any-one · unanimous} |
| Result | **{N} confirmed · {M} single-vote** — highest severity **{high}** |

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

## Single-Vote Findings (triage required)

> One skeptic found these and the others did not. That is not evidence they are wrong —
> current-generation skeptics have high precision, so a lone finding is more often a real
> hole one reviewer happened to reach than noise. **Each row needs a decision** — tightened,
> accepted as intended behavior, or refuted with a reason. Do not close this section by
> ignoring it. Spec holes are the cheapest defects in the lifecycle to fix and the most
> expensive to discover later.

| `id` | severity | clause | decision |
|---|---|---|---|
| `{id}` | 🟠 medium | "{clause}" | {tightened / intended, confirmed with author / refuted because …} |

## Attacks That Failed

- {short note per serious attack that found no hole} — corroborates the spec holds here.

## Actions Taken

- [x] Folded `{id}` tightening into spec §{n}
- [ ] Triaged single-vote finding `{id}` → {decision}
- [ ] Re-ran panel on revision → `spec-validation-r2.md` _(or: not needed)_
```
