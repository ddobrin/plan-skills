# GEAP Interactions Core

Shared assets for **`geap-interactions-spec-validator`** and
**`geap-interactions-plan-validator`**: the no-Python siblings of the `geap-*`
validators. Transport is `curl` to the **Interactions API** (with automatic Vertex AI
fallback), executed by the `geap-interactions-caller` subagent; orchestration lives in
[ORCHESTRATION.md](ORCHESTRATION.md); roster and tuning live in [config.json](config.json).

## Setup (once)

```bash
# 1. ADC — the only credential used, minted inline per call (interactive)
gcloud auth application-default login

# 2. Project — config.json's gcp_project_id, or override per shell:
export GOOGLE_CLOUD_PROJECT=<your-project>

# 3. jq must be on PATH (transport parsing) — `jq --version` to confirm
```

## Configuration

| config.json key | Env override | Default |
|---|---|---|
| `skeptic_models` | `GEAP_IX_SKEPTIC_MODELS` (comma-separated) | `gemini-3.5-flash,claude-haiku-4-5,gemini-3.1-flash-lite` |
| `synthesis_model` | `GEAP_IX_SYNTHESIS_MODEL` | `claude-fable-5` |
| `target_agent` | `GEAP_IX_TARGET_AGENT` | `null` (models mode) |
| `transport` | `GEAP_IX_TRANSPORT` (`interactions` \| `vertex`) | `interactions` |
| `gcp_project_id` | `GEAP_IX_PROJECT` or `GOOGLE_CLOUD_PROJECT` | — (required) |
| `max_output_tokens` | `GEAP_IX_MAX_TOKENS` | `8192` |
| `temperature` | `GEAP_IX_TEMP` | `0.15` |
| `api_timeout_seconds` | `GEAP_IX_TIMEOUT` | `120` |

Any number (≥ 2) of `gemini-*` / `claude-*` models may fill `skeptic_models`; lenses
cycle when the roster is longer than the lens count. Setting `target_agent` to a
registered Gemini Enterprise agent switches both skills to **agent mode** (one
`agent:` call, `background: true` + polling — see ORCHESTRATION.md §5).

## Smoke tests

```bash
PROJECT=${GOOGLE_CLOUD_PROJECT:?set project first}

# Primary transport — Interactions API (ADC bearer + quota project)
curl -s -X POST "https://generativelanguage.googleapis.com/v1beta/interactions?api_version=v1beta" \
  -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  -H "x-goog-user-project: $PROJECT" -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.5-flash","input":"Reply with exactly: OK","store":false,"generation_config":{"max_output_tokens":10}}' \
  | jq -r '.output_text // .error.message'

# Fallback transport — Vertex AI global endpoint (both provider verbs)
curl -s -X POST -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  -H "Content-Type: application/json" \
  "https://aiplatform.googleapis.com/v1/projects/$PROJECT/locations/global/publishers/google/models/gemini-3.1-flash-lite:generateContent" \
  -d '{"contents":[{"role":"user","parts":[{"text":"Reply with exactly: OK"}]}],"generationConfig":{"maxOutputTokens":10}}' \
  | jq -r '.candidates[0].content.parts[0].text // .error.message'

curl -s -X POST -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  -H "Content-Type: application/json" \
  "https://aiplatform.googleapis.com/v1/projects/$PROJECT/locations/global/publishers/anthropic/models/claude-haiku-4-5:rawPredict" \
  -d '{"anthropic_version":"vertex-2023-10-16","messages":[{"role":"user","content":"Reply with exactly: OK"}],"max_tokens":10}' \
  | jq -r '([.content[]? | select(.type=="text") | .text] | join("")) + (.error.message // "")'
```

A 401/403/404 from the first curl with working Vertex curls = the Interactions
preview is not enabled for your org → set `transport: "vertex"` (or let the caller
agent fall back automatically, recorded per call in `meta.transport`).
