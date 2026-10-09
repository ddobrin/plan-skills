---
name: swarm-metrics
description: Report AI-native SDLC indicators for plan-swarm milestones from committed artifacts - lead times (intent → spec → plan → commit → PR), groups committed, first-pass audit rate, failed audit rounds, validator re-runs, cost and declined gates, and intent survival. Triggers - "swarm metrics", "how is the swarm doing", "lead time for this milestone", "show rework and cost".
tools:
  - run_command
  - view_file
---

# Swarm metrics

Reads only committed files (`approvals.md`, `audit.md`, `usage.md`, gate reports, `plans/intents/`), so the numbers are reproducible and match the audit trail.

## Steps
1. Run `python3 "$PLAN_LIB/metrics.py" --format text` (Cwd: the repository root) for every milestone, or add `--milestone {m}` for one. Use `--format json` when the user wants to process the numbers. The plan plugin's PreToolUse hook expands `$PLAN_LIB`; if the command fails because it was not expanded, the plugin's hooks are not running in this session.
2. Present the result and point out what stands out:
   - **Lead time:** which stage waits longest (usually a human gate: that's review latency, not agent time).
   - **Quality:** a first-pass audit rate below 1.0 or several failed rounds means the plan's steps were under-specified; validator re-runs mean the artifact changed materially after review.
   - **Cost:** tokens per milestone (Antigravity does not always report token totals; missing values are logged as blank), and which gates were declined at which tier.
   - **Intents:** survival rate = accepted / (accepted + closed); open intents are waiting for triage.
3. Keep interpretation to what the numbers show; say when a value is missing because the milestone hasn't reached that stage yet.
