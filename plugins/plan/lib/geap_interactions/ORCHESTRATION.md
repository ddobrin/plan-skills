# GEAP Interactions Orchestration (shared driver)

You (the orchestrating Claude) run these steps for both geap-interactions skills.
The SKILL.md that sent you here provides the **stage table** (report names, schema
keys, lens file). `{CORE}` below = `${CLAUDE_PLUGIN_ROOT}/lib/geap_interactions`.

## §0 Resolve configuration

```bash
CFG={CORE}/config.json
PROJECT=${GEAP_IX_PROJECT:-${GOOGLE_CLOUD_PROJECT:-$(jq -r '.gcp_project_id // empty' "$CFG")}}
TRANSPORT=${GEAP_IX_TRANSPORT:-$(jq -r '.transport' "$CFG")}
SKEPTICS=${GEAP_IX_SKEPTIC_MODELS:-$(jq -r '.skeptic_models | join(",")' "$CFG")}
SYNTH=${GEAP_IX_SYNTHESIS_MODEL:-$(jq -r '.synthesis_model' "$CFG")}
TARGET_AGENT=${GEAP_IX_TARGET_AGENT:-$(jq -r '.target_agent // empty' "$CFG")}
MAXTOK=${GEAP_IX_MAX_TOKENS:-$(jq -r '.max_output_tokens' "$CFG")}
TEMP=${GEAP_IX_TEMP:-$(jq -r '.temperature' "$CFG")}
TIMEOUT=${GEAP_IX_TIMEOUT:-$(jq -r '.api_timeout_seconds' "$CFG")}
```

Abort with a clear message if: PROJECT is empty; SKEPTICS has < 2 entries; any model
lacks a `gemini-`/`claude-` prefix.

## §1 Preflight

- Document exists; `wc -c` ≤ 1000000 and `wc -m` ≤ 200000 — else abort before any call.
- `gcloud auth application-default print-access-token >/dev/null 2>&1` — on failure,
  STOP and ask the user to run `! gcloud auth application-default login`
  (interactive; you cannot run it for them). Surface `FAILED_PRECONDITION` /
  org-policy errors verbatim; never retry them blindly.

## §2 Skeptic fan-out  *(models mode — if TARGET_AGENT is set, skip to §5)*

Read the stage's `references/lenses.md`. Lens for skeptic *i* (1-based) =
lens `((i-1) mod L) + 1` where L = number of lenses — extra roster models add vote
diversity, not new lenses. Full lens text = its unique paragraph + the file's
**Shared tail**.

Dispatch **one `geap-interactions-caller` subagent per skeptic model, ALL IN ONE
MESSAGE** (parallel, independent contexts — no shared scratchpad), each with:

```
You are running one remote skeptic of an adversarial review panel.
MODEL: {model i}
PROJECT: {PROJECT}
TRANSPORT: {TRANSPORT}
GENERATION: max_output_tokens={MAXTOK}, temperature={TEMP}, timeout={TIMEOUT}s
DOCUMENT: {absolute document path}
REQUIRED_KEYS: {stage table: finding_required_keys}
NO_HOLE_KEY: {stage table: no_hole_key}
SYSTEM PROMPT (use verbatim as system_instruction):
---
{full lens text}
---
Follow your transport recipe. Return ONLY the fenced JSON verdict with meta.
```

A subagent returning `{"error": ...}` is a **failed skeptic**. ≥ 2 must succeed;
otherwise abort as **"Quorum unreachable"** — no report.

## §3 Synthesis

One more `geap-interactions-caller` dispatch: `MODEL={SYNTH}`; SYSTEM PROMPT = the
lens file's **Synthesis Prompt**; `REQUIRED_KEYS` = stage table's
`synthesis_finding_required_keys`; `NO_HOLE_KEY` = stage table's
`synthesis_merge_key`; plus:

```
RAW FINDINGS:
Agent 1 ({model 1}, {lens 1 name}):
{agent 1 verdict JSON}
Agent 2 (...): ...
```

(only successful skeptics, keeping their original numbering). If the synthesis
subagent returns an error: **hard abort, no report, no substitution** — report the
error to the user.

## §4 Quorum — you count, models never self-report totals

For each finding across skeptic outputs, group by stable `id`; where ids differ but
the stage table's `match_field` quotes the same text, treat as the same finding
(note the merge in the report). Then:

- `votes(f)` = number of skeptic outputs containing f **+ 1** if the synthesis
  `consolidated_findings` entry for f has `validated_by_synthesis: true`.
- **≥ 2 votes ⇒ Confirmed.** Exactly 1 ⇒ Unconfirmed (FYI — never silently dropped).
- Severity: most common among agreeing skeptics; tie ⇒ higher.
- If the stage has `first_domino`: take synthesis's nomination; if it names a
  non-confirmed finding, say so in the report rather than promoting it.

## §5 Agent mode  *(only when TARGET_AGENT is set)*

One curl (you may run it directly — a single call needs no subagent), then poll:

```bash
DOC="<absolute path to the document under review>"   # same file preflighted in §1
jq -n --rawfile doc "$DOC" --arg agent "$TARGET_AGENT" --arg stage "{stage}" \
  '{agent:$agent, input:("STAGE: "+$stage+"\n\nValidate the following document:\n\n"+$doc),
    background:true, store:false}' > /tmp/geap_ix_agent_req.json
curl -s -X POST "https://generativelanguage.googleapis.com/v1beta/interactions?api_version=v1beta" \
  -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  -H "x-goog-user-project: $PROJECT" -H "Content-Type: application/json" \
  -d @/tmp/geap_ix_agent_req.json | jq -r '.id'
# every 30s, budget 10 × TIMEOUT total:
curl -s "https://generativelanguage.googleapis.com/v1beta/interactions/{id}?api_version=v1beta" \
  -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  -H "x-goog-user-project: $PROJECT" | jq -r '.status'
```

On `completed`, parse the returned `output_text` as the synthesis-shaped verdict and
continue at §4 (votes = `sources` length + 1 if validated). On `failed`/timeout:
abort with the raw status payload.

## §6 Report

Path: `plans/active_milestones/{moniker}/adversarial-reviews/{report_basename}.md`
(moniker from the document's path; bare artifacts → `plans/adversarial-reviews/`;
if the file exists, suffix `-r2`, `-r3`, … — never overwrite). **Write it even on a
clean pass.** Use `date +%Y-%m-%d`. Severity icons: 🔴 high · 🟠 medium · 🟡 low.

```markdown
# {report_title} — {document title}

> `{skill name}` · {N} remote skeptics + synthesis vote · Interactions API (ADC) · ≥2-of-{N+1} gate

| Field | Value |
|---|---|
| Milestone | `{moniker}` |
| Artifact | `{document path}` |
| Date | {YYYY-MM-DD} |
| Panel | {model → lens name, one per line} · synthesis: {SYNTH} |
| Transport | {per model: interactions | vertex, from each verdict's meta} |
| Result | **{C} confirmed · {U} unconfirmed** — highest severity **{sev}** |

## Verdict

{1–3 sentences: ready or blocked, and by what. If the stage has a first domino, name it here.}

## Confirmed Findings (≥ 2 votes)

### {icon} `{id}` — {one-line name} · {votes}/{N+1} {(+synthesis) if validated}
{stage-specific finding fields, one bold label per line — spec: Clause / Malicious
reading / Harm / Tightening; plan: Step / Category / Failure / Evidence / Fix}

## Unconfirmed (FYI · 1 vote)

| `id` | severity | {match_field} | note |
|---|---|---|---|

## {no_hole_heading}

- {merged no-hole notes from synthesis}

## Panel Health

- {per skeptic: model, lens, transport used, attempts, or FAILED + reason}

## Actions Taken

- [ ] {one checkbox per confirmed finding's fix}
```

## §7 After the run

1. Relay the Verdict: confirmed count, highest severity, each confirmed finding's
   fix/tightening (and the first domino for plan stage).
2. Apply each confirmed fix to the document (or surface it if it changes intent),
   ticking **Actions Taken**.
3. If the document was materially revised, re-run once — the new report auto-suffixes
   `-r2.md`.
