# Usage Example: Orchestrated API Migration

Scenario: migrate a REST API from Express 4 to Express 5 across four
route modules, update the middleware, and refresh the docs.

## Prompt (Claude Code or Antigravity)

```
Migrate our API from Express 4 to Express 5.
Route modules: routes/users.js, routes/orders.js, routes/payments.js,
routes/admin.js. Middleware lives in middleware/. Docs in docs/api.md.
Use workers in parallel where possible.
```

## What the orchestrator does

1. Plan
   - researcher: list Express 5 breaking changes relevant to this codebase
   - After research returns: 4 parallel workers, one per route module
   - Then: 1 worker for middleware (depends on route conventions chosen)
   - Then: 1 worker for docs + a final test run

2. Delegation (one of the parallel worker prompts)

   ```
   Task: migrate routes/orders.js from Express 4 to Express 5.
   Breaking changes that apply (from research): removed res.send(status),
   async error handling now built-in — remove wrapAsync(), router.param
   signature change.
   Constraints: keep the existing handler names and route paths; do not
   touch other files.
   Return: what changed, files touched, decisions, blockers.
   ```

3. Review and synthesis
   - Orchestrator compares the 4 route summaries, notices two workers
     chose different error-response shapes, delegates a small fix-up
     task to unify them, then delegates the middleware and docs tasks.
   - Final verification: one worker runs the test suite and reports.
   - Orchestrator reports one coherent summary of the migration.

## Token economics

The orchestrator (expensive model) sees only: the plan, six short
summaries, and the test report — a few thousand tokens. The workers
(cheaper model) burn the tens of thousands of tokens reading and
editing files. That is the point of the pattern.

## Tips

- Independent subtasks only in parallel — parallel workers must not edit
  the same files.
- If a worker returns blockers, delegate a follow-up task; don't let the
  orchestrator start editing files itself.
- For research-heavy questions ("how does auth work in this repo?"),
  delegate to `researcher` even when there is nothing to edit — it keeps
  bulk file reading out of the orchestrator's context.
