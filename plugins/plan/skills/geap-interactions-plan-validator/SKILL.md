---
name: geap-interactions-plan-validator
description: No-Python remote drop-in for plan-validator - runs the adversarial plan review on remote models over the Interactions API (curl + ADC from caller subagents; configurable roster; Vertex fallback), with a synthesis model casting an extra vote and nominating the first domino. Symptoms - "run the interactions plan panel", "remote plan validation without Python", "validate this plan via the Interactions API", "GEAP plan validation, no local scripts", geap-plan-validator wanted but no venv/Python available.
tools:
  - view_file
  - write_to_file
  - list_dir
  - grep_search
  - run_command
  - invoke_subagent
---

# GEAP Interactions Plan Validation

Runs the same adversarial review as `plan-validator` / `geap-plan-validator` — N
independent skeptics (default 3), default-to-reject, ≥2-vote quorum with a synthesis
vote, plus the **first domino** nomination — but transport is **curl to the
Interactions API with ADC** from `geap-interactions-caller` subagents, one per
skeptic, each in its own context. **No Python, no venv, no pip.** Falls back per
call to the Vertex AI global endpoint when the Interactions preview is unavailable.

**Scope caveat (same as geap-plan-validator):** remote skeptics **cannot read the
repository** — they attack the plan text only; unverifiable code assumptions come
back as `false-assumption`/low-confidence. For codebase-verified review use the
local `plan-validator`; the two are complementary.

**Announce at start:** "I'm using the geap-interactions-plan-validator skill to attack this plan with a remote skeptic panel over the Interactions API."

## When to Use / When NOT to Use

Same criteria as `plan-validator` (a written plan, before execution). Prefer this
variant over `geap-plan-validator` when Python/venv is unavailable or unwanted.
Requires: `gcloud` ADC, `jq`, a GCP project (see
`${CLAUDE_PLUGIN_ROOT}/lib/geap_interactions/README.md` for setup and smoke tests).

## Stage Table

| Parameter | Value |
|---|---|
| stage | `plan` |
| lenses file | `${CLAUDE_PLUGIN_ROOT}/skills/geap-interactions-plan-validator/references/lenses.md` |
| report_basename | `geap-interactions-plan-validation` |
| report_title | `Plan Adversarial Review (Interactions)` |
| finding_required_keys | `id, step, category, failure, evidence, confidence, severity, fix` |
| match_field | `evidence` |
| no_hole_key | `checks_that_passed` |
| no_hole_heading | `Checks That Passed` |
| has_first_domino | yes |
| synthesis_finding_required_keys | `id, step, category, failure, evidence, severity, fix, validated_by_synthesis` |
| synthesis_merge_key | `merged_checks_that_passed` |

## Run

Follow **every** step §0–§7 in
`${CLAUDE_PLUGIN_ROOT}/lib/geap_interactions/ORCHESTRATION.md` with the stage table
above. Do not skip the preflight, do not let skeptics share context, and count the
votes yourself — models never self-report totals. Always relay the first domino in
the Verdict.
