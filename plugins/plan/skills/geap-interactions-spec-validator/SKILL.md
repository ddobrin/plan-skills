---
name: geap-interactions-spec-validator
description: No-Python remote drop-in for spec-validator - runs the adversarial spec review on remote models over the Interactions API (curl + ADC from caller subagents; configurable roster; Vertex fallback), with a synthesis model casting an extra vote. Symptoms - "run the interactions spec panel", "remote spec validation without Python", "validate this spec via the Interactions API", "GEAP spec validation, no local scripts", geap-spec-validator wanted but no venv/Python available.
---

# GEAP Interactions Spec Validation

Runs the same adversarial review as `spec-validator` / `geap-spec-validator` — N
independent skeptics (default 3), default-to-reject, ≥2-vote quorum with a synthesis
vote — but transport is **curl to the Interactions API with ADC** from
`geap-interactions-caller` subagents, one per skeptic, each in its own context.
**No Python, no venv, no pip.** Falls back per call to the Vertex AI global endpoint
when the Interactions preview is unavailable (recorded in the report's Transport row).

**Announce at start:** "I'm using the geap-interactions-spec-validator skill to attack this spec with a remote skeptic panel over the Interactions API."

## When to Use / When NOT to Use

Same criteria as `spec-validator` (a drafted spec, before planning). Prefer this
variant over `geap-spec-validator` when Python/venv is unavailable or unwanted.
Prefer local `spec-validator` when there is no GCP access or the spec must not leave
the machine. Requires: `gcloud` ADC, `jq`, a GCP project (see
`${CLAUDE_PLUGIN_ROOT}/lib/geap_interactions/README.md` for setup and smoke tests).

## Stage Table

| Parameter | Value |
|---|---|
| stage | `spec` |
| lenses file | `${CLAUDE_PLUGIN_ROOT}/skills/geap-interactions-spec-validator/references/lenses.md` |
| report_basename | `geap-interactions-spec-validation` |
| report_title | `Spec Adversarial Review (Interactions)` |
| finding_required_keys | `id, clause, severity, interpretation, harm, tightening` |
| match_field | `clause` |
| no_hole_key | `failed_attacks` |
| no_hole_heading | `Attacks That Failed` |
| has_first_domino | no |
| synthesis_finding_required_keys | `id, clause, severity, interpretation, harm, tightening, validated_by_synthesis` |
| synthesis_merge_key | `merged_failed_attacks` |

## Run

Follow **every** step §0–§7 in
`${CLAUDE_PLUGIN_ROOT}/lib/geap_interactions/ORCHESTRATION.md` with the stage table
above. Do not skip the preflight, do not let skeptics share context, and count the
votes yourself — models never self-report totals.
