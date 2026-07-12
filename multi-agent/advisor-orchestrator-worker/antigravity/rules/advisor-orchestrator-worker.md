# Rule: Three-tier loop discipline

When running the advisor-orchestrator-worker loop:

- The parent agent never does worker-level work and never executes
  through the advisor.
- No wave dispatches before the plan-review consult; no delivery before
  the taste-pass consult.
- Worker briefs are stateless and complete: subtask, inputs,
  constraints, acceptance criteria, output format. Workers in one wave
  touch disjoint files.
- Every worker result gets an explicit verdict: PASS, FIX (fresh brief
  naming the failure), or ESCALATE. Two FIX failures on the same
  subtask force an advisor consult.
- Advisor notes are applied or explicitly rebutted — never silently
  dropped.
- Hard budget: 20 worker spawns, 5 advisor consults per run.
