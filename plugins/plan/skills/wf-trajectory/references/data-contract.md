# Data contract: `wf_<runId>.json`

Written by the Workflow engine to
`$CLAUDE_CONFIG_DIR|~/.claude/projects/<encoded-launch-dir>/<sessionId>/workflows/wf_<runId>.json`.
`<encoded-launch-dir>` = the launch directory's absolute path with `/` → `-`.

## Run header (consumed)
`runId, workflowName, summary, status, durationMs, agentCount, totalTokens,
totalToolCalls, defaultModel, timestamp, result`.

## `phases[]`
`{ title, detail }`.

## `workflowProgress[]`
Mixed array. Records with `type == "workflow_agent"` are agents:
`index, label, phaseIndex, phaseTitle, agentId, model, state, queuedAt,
startedAt, durationMs, lastProgressAt, tokens, toolCalls, lastToolName,
promptPreview, resultPreview`. Other records are phase markers (`type, index,
title`); the parser matches each marker to a `phases[]` entry by title and keys
the phase by the marker `index`, so agents attach via their `phaseIndex`.

## Transcripts
Per-agent full transcript:
`<sessionId>/subagents/workflows/<runId>/agent-<agentId>.jsonl` — linked via
`file://`, never embedded.

All fields are read defensively; any missing field renders as `—` and never
crashes the generator.
