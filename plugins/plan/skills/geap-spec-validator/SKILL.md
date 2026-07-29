---
name: geap-spec-validator
description: Remote drop-in alternative to spec-validator - runs the adversarial spec review on Vertex AI foundation models (3 configurable skeptics + a synthesis model) instead of local subagents, for an independent perspective from different model families. Symptoms - "run the remote spec panel", "GEAP spec validation", "validate this spec with cloud/Vertex models", "get a second opinion on this spec from other models", spec-validator requested with remote or Gemini/Claude-on-Vertex models.
tools:
  - view_file
  - write_to_file
  - list_dir
  - grep_search
  - run_command
---

# GEAP Remote Spec Validation

## Overview

Runs the same adversarial review as `spec-validator` — 3 independent skeptics,
default-to-reject, quorum gate — but the skeptics are **remote Vertex AI foundation
models** (Gemini and/or Claude via Model Garden), and a fourth **synthesis model**
consolidates their findings and casts an extra validation vote. The whole panel runs in
one Python script; you dispatch no subagents.

- **Skeptic lenses (fixed prompts, configurable models):**
  1. Ambiguity & Malicious-Compliance Skeptic
  2. Logic & Boundary Skeptic
  3. Completeness & Testability Skeptic
- **Quorum:** a finding is confirmed at **≥ 2 votes** out of 4 possible (one per
  agreeing skeptic + 1 if the synthesis model validates it). Vote counting is done
  programmatically in Python — models never self-report vote totals.

**Announce at start:** "I'm using the geap-spec-validator skill to attack this spec with a remote Vertex AI skeptic panel."

## When to Use / When NOT to Use

Same criteria as `spec-validator` (a drafted spec, before planning). Prefer this
variant when the user wants model diversity (opinions from non-Claude models), or an
audit trail produced by an external pipeline. Use the local `spec-validator` when there
is no GCP access or the spec must not leave the machine.

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
python3 ${CLAUDE_PLUGIN_ROOT}/skills/geap-spec-validator/validator.py --file plans/active_milestones/{moniker}/spec.md
```

Flags:
- `--file` (required) — the spec to validate (≤ 1 MB, ≤ 200k chars).
- `--moniker` — force the milestone the report is filed under, when the spec lives outside `plans/active_milestones/`.
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
   `plans/active_milestones/{moniker}/adversarial-reviews/geap-spec-validation.md`
   (fallback `plans/adversarial-reviews/` for bare specs; re-runs get `-r2`, `-r3`, …).
2. **Relay the Verdict** to the user: confirmed count, highest severity, and each
   confirmed finding's `tightening`.
3. For each confirmed finding, apply its tightening to the spec (or surface it if it
   changes intent), ticking the report's **Actions Taken** checklist.
4. If the spec was materially revised, re-run the panel once — the new report
   auto-suffixes `-r2.md`; nothing is overwritten.
