# The Review Document — implementation-validator

Written by Process step 7 to
`plans/active_milestones/{moniker}/adversarial-reviews/implementation-validation.md`. It is
the human-readable face of the aggregated JSON — a reviewer should grasp what is broken, at
what *corrected* severity, without opening an agent transcript.

Use `date +%Y-%m-%d` for the date. Severity icons: 🔴 critical · 🟠 high · 🟡 medium ·
⚪ low. The **Severity Calibration** table is the centerpiece — never omit it when any
severity was revised. Drop the **Failed Claims** section in finding-hunt mode. Keep the
other sections even when empty (write `_None._`). Keep entries tight: one line per field,
no restated summaries.

```markdown
# Implementation Adversarial Review — {change title}

> `implementation-validator` · 3 independent skeptics, no shared scratchpad · default-to-reject (`isReal=false` / `refuted=true`) · {2-of-3} majority gate · severity calibration

| Field | Value |
|---|---|
| Milestone | `{moniker}` |
| Diff | `{BASE_SHA}..{HEAD_SHA}` |
| Date | {YYYY-MM-DD} |
| Mode | {finding-hunt · claim-refutation} |
| Gate | {2-of-3 · any-one · unanimous} |
| Result | **{N} confirmed defects · {F} failed claims · {M} single-vote** — highest corrected severity **{high}** |

## Verdict

{1–3 plain-language sentences. Lead with the calibration headline, e.g. "3 findings claimed Critical; all confirmed real but downgraded to High — impact is gated on concurrent requests, not every run."}

## Confirmed Defects (≥ 2 votes)

> Fix at the **corrected** severity, highest first.

### 🔴 `{id}` — {one-line title}  · severity {high} · {votes}/3
- **Location:** `{file}:{location}`
- **Attack:** {the input / sequence / edge case that triggers it}
- **Evidence:** `{file:line}` — {the specific code that proves it}
- **Why it breaks:** {reasoning}
- **Fix:** {concrete remediation}

_(repeat per confirmed defect)_

## Severity Calibration

| `id` | claimed | corrected | why |
|---|---|---|---|
| `{id}` | 🔴 critical | 🟠 high | {impact gated on concurrent requests, not every run} |

## Failed Claims  _(claim-refutation mode only)_

| claim | refuted by | severity | attack |
|---|---|---|---|
| "{claim}" | {2}/3 | 🟠 high | {input that falsified it} |

## Single-Vote Findings (triage required)

> One skeptic found these and the others did not. That is not evidence they are wrong —
> current-generation skeptics have high precision, so a lone finding is more often a real
> defect one reviewer happened to reach than noise. Concurrency and failure-path bugs in
> particular are easy for two of three readers to miss. **Each row needs a decision** —
> fixed, accepted as a known risk, or refuted with a reason. Read the cited evidence; a
> finding with a real `file:line` behind it is a different object from a guess.

| `id` | severity | location | decision |
|---|---|---|---|
| `{id}` | ⚪ low | `{file}:{loc}` | {fixed / accepted risk because … / refuted because …} |

## Attacks That Failed

- {short note per serious attack that found no defect} — corroborates robustness here.

## Actions Taken

- [x] Fixed `{id}` at {corrected severity}
- [ ] Surfaced calibration delta to user: "{the headline sentence}"
- [ ] Triaged single-vote finding `{id}` → {decision}
- [ ] Re-validated after fixes → `implementation-validation-r2.md` _(or: not needed)_
```
