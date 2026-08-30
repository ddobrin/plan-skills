# The Review Document — plan-validator

Written by Process step 7 to
`plans/active_milestones/{moniker}/adversarial-reviews/plan-validation.md`. It is the
human-readable face of the aggregated JSON — a reviewer should grasp where the plan breaks
without opening an agent transcript.

Use `date +%Y-%m-%d` for the date. Severity icons: 🔴 high · 🟠 medium · 🟡 low. The
**First domino** is the headline; lead with it. Every confirmed finding must carry its
`file:line` evidence — an uncited prediction is a guess, not a finding. Keep every section,
even when empty (write `_None._`). Keep entries tight: one line per field, no restated
summaries.

```markdown
# Plan Adversarial Review — {plan title}

> `plan-validator` · 3 independent skeptics, no shared scratchpad · default-to-reject · skeptics READ the codebase · {2-of-3} majority gate

| Field | Value |
|---|---|
| Milestone | `{moniker}` |
| Artifact | `plans/active_milestones/{moniker}/plan.md` |
| Date | {YYYY-MM-DD} |
| Gate | {2-of-3 · any-one · unanimous} |
| Result | **{N} confirmed · {M} single-vote** — highest severity **{high}** |
| 🁢 First domino | `{id}` — {earliest failure that invalidates the steps after it, or `none`} |

## Verdict

{1–3 plain-language sentences: will the plan survive execution, and which step topples first?}

## Confirmed Findings (≥ 2 votes)

> Apply each **Fix** to the plan — reorder steps, insert a prerequisite, add a rollback/verify, or correct the assumption.

### 🔴 `{id}` — {one-line name}  · {category} · {votes}/3 · confidence {high}
- **Step:** {step number / title this concerns}
- **Failure:** {the concrete scenario in which the plan breaks}
- **Evidence:** `{file:line}` you read _(or verbatim plan text)_
- **Fix:** {the concrete change to the plan that prevents the failure}

_(repeat per confirmed finding; the First domino first)_

## Single-Vote Findings (triage required)

> One skeptic found these and the others did not. That is not evidence they are wrong —
> current-generation skeptics have high precision, so a lone finding is more often a real
> defect one reviewer happened to reach than noise. **Each row needs a decision** — fixed,
> accepted as a known risk, or refuted with a reason. Do not close this section by ignoring it.

| `id` | severity | step | evidence | decision |
|---|---|---|---|---|
| `{id}` | 🟠 medium | {step} | `{file:line}` | {fixed / accepted risk / refuted because …} |

## Checks That Passed

- {assumption the skeptics verified that DID hold} — `{file:line}`

## Actions Taken

- [x] Reordered: inserted step {2b} before step {3} (`{id}`)
- [x] Corrected step {3} target to `{realName()}` (`{id}`)
- [ ] Triaged single-vote finding `{id}` → {decision}
- [ ] Re-ran panel on revision → `plan-validation-r2.md` _(or: not needed)_
```
