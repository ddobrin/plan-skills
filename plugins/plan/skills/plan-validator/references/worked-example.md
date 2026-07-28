# Worked Example — plan-validator

> Plan excerpt: *"Step 2: add `retryCount` to the `Job` record. Step 3: update
> `JobScheduler.dispatch()` to read `retryCount`. Step 4: migrate existing rows."*

Three skeptics read the repo. After dedup + majority gate:

**Confirmed (≥ 2 votes):**

- `dispatch-signature-missing` (3 votes, high) — `JobScheduler` has no `dispatch()`; the
  method is `schedule(Job)` (`scheduler/JobScheduler.java:88`). Fix: retarget step 3 to
  `schedule()`.
- `migrate-before-default` (2 votes, high) — step 4 migrates rows but no step gives
  `retryCount` a default, so step 3 NPEs on legacy rows between deploy and migration. Fix:
  add "step 2b: default `retryCount` to 0" *before* step 3; mark step 3 as requiring 2b.
- `first_domino` = `migrate-before-default`.

**Single vote (triage required):**

- `no-rollback-on-migrate` (1 vote, medium) — step 4 has no down-migration
  (`db/migrations/0042_add_retry_count.sql:1`). Triaged: **accepted risk** — the migration is
  additive and the team's rollback procedure restores from snapshot. Recorded in the review
  so the decision is on the record rather than implied by silence.

The plan is reordered and the missing default step inserted before execution begins.
