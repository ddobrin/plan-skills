---
name: geap-plan-validator
description: Remote drop-in alternative to plan-validator - runs the adversarial implementation-plan review on Vertex AI foundation models (3 configurable skeptics + a synthesis model) instead of local subagents, attacking the plan text for ordering defects, hidden assumptions, and missing failure handling. Symptoms - "run the remote plan panel", "GEAP plan validation", "validate this plan with cloud/Vertex models", "get a second opinion on this plan from other models", plan-validator requested with remote or Gemini/Claude-on-Vertex models.
---

# GEAP Remote Plan Validation

## Overview

Runs an adversarial review of an implementation plan on **remote Vertex AI foundation
models**: 3 skeptics attack the plan in parallel, then a **synthesis model**
consolidates their findings, casts an extra validation vote, and nominates the **first
domino** — the earliest step whose failure invalidates everything after it. The whole
panel runs in one Python script; you dispatch no subagents.

- **Skeptic lenses (fixed prompts, configurable models):**
  1. Dependency & Ordering Skeptic — step N consumes what step N+2 produces, unstated preconditions
  2. Hidden-Assumption Skeptic — files/flags/credentials the plan names but never creates or verifies
  3. Integration & Failure-Mode Skeptic — unverifiable "verify it works" steps, no rollback, blast radius
- **Quorum:** a finding is confirmed at **≥ 2 votes** out of 4 possible (one per
  agreeing skeptic + 1 if the synthesis model validates it). Votes are counted
  programmatically in Python.

**Announce at start:** "I'm using the geap-plan-validator skill to attack this plan with a remote Vertex AI skeptic panel."

## Scope Caveat (important)

The remote skeptics **cannot read the repository** — they attack only the plan text
itself. Their `evidence` is verbatim plan quotes, and claims about existing code they
cannot verify are reported as category `false-assumption` with confidence `low`. For a
review that checks the plan *against the codebase*, use the local `plan-validator`
skill; the two are complementary, not interchangeable.

## Prerequisites

Canonical setup guide: `${CLAUDE_PLUGIN_ROOT}/lib/geap_validator_core/README.md` (Setup section). In short:

1. Python deps (once): `pip install httpx google-auth` (pure REST transport, no Vertex SDK) — the repo `.venv` already has them, so usually just `source .venv/bin/activate`.
2. GCP Application Default Credentials:
   ```bash
   gcloud auth application-default login
   ```
   If the script exits with `Authentication Error`, ask the user to run this — it is interactive and cannot be run for them.
3. A GCP project with Vertex AI enabled, resolved in this order:
   `GOOGLE_CLOUD_PROJECT` env → `GEAP_VALIDATOR_PROJECT` env → `gcp_project_id` in config.json.

## Running the Panel

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/geap-plan-validator/validator.py --file plans/active_milestones/{moniker}/plan.md
```

Flags:
- `--file` (required) — the plan to validate (≤ 1 MB, ≤ 200k chars).
- `--moniker` — force the milestone the report is filed under, when the plan lives outside `plans/active_milestones/`.
- `--config` — alternate config.json path.
- `--verbose` — INFO-level logging of retries and model calls.

The script prints the **absolute report path** on stdout and exits **0** on a clean
pass, **1** when confirmed findings exist (or on infra errors, which are written to
stderr instead of a report).

## Configuration

Defaults live in `${CLAUDE_PLUGIN_ROOT}/lib/geap_validator_core/config.json`. Every key
can be overridden per-run with environment variables:

| config.json key | env override | default |
|---|---|---|
| `gcp_project_id` | `GOOGLE_CLOUD_PROJECT` / `GEAP_VALIDATOR_PROJECT` | — (required) |
| `gcp_location` | `GEAP_VALIDATOR_LOCATION` | `global` (only supported value — clamped) |
| `agent_1_model` | `GEAP_VALIDATOR_AGENT_1_MODEL` | `gemini-3.5-flash` |
| `agent_2_model` | `GEAP_VALIDATOR_AGENT_2_MODEL` | `claude-haiku-4-5` |
| `agent_3_model` | `GEAP_VALIDATOR_AGENT_3_MODEL` | `gemini-3.1-flash-lite` |
| `synthesis_model` | `GEAP_VALIDATOR_SYNTHESIS_MODEL` | `claude-fable-5` |

Every model slot — the 3 skeptics **and** `synthesis_model` — accepts any `gemini-*`
or `claude-*` model name; the prefix only picks the REST verb (`:generateContent` vs
`:rawPredict`), and all calls go directly to the Vertex AI global endpoint. A failing
synthesis model is never silently substituted. The panel tolerates one failed skeptic
(2 of 3 proceed); with fewer it aborts as "Quorum unreachable".

## After the Run (driver instructions)

1. **Read the report** at the path printed on stdout — it is written to
   `plans/active_milestones/{moniker}/adversarial-reviews/geap-plan-validation.md`
   (fallback `plans/adversarial-reviews/` for bare plans; re-runs get `-r2`, `-r3`, …).
2. **Relay the Verdict** to the user: confirmed count, highest severity, the **first
   domino** (fix it first — later findings may dissolve once it is fixed), and each
   confirmed finding's `fix`.
3. For each confirmed finding, apply its fix to the plan (or surface it if it changes
   scope), ticking the report's **Actions Taken** checklist.
4. If the plan was materially revised, re-run the panel once — the new report
   auto-suffixes `-r2.md`; nothing is overwritten.
