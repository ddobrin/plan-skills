# Worked Example — plan-deliberator

> Plan excerpt (from `architect`): *"Step 2: add `retryCount` to the `Job` record.
> Step 3: update `JobScheduler.dispatch()` to read `retryCount`. Step 4: migrate
> existing rows. Groups: {2,3} parallel with {4}."*

**Territories (disjoint, each deep-read before speaking):**

- **intent** — the spec. Acceptance criterion: *"failed jobs retry ≤ 3 times; retries
  visible in the ops dashboard."*
- **codebase** — `scheduler/` and `dashboard/`.
- **delivery** — CI config and migration tooling.

**Round 1**

- **codebase** discloses: no `dispatch()` exists — the method is `schedule(Job)`
  (`scheduler/JobScheduler.java:88`); legacy rows have no `retryCount`, and `schedule()`
  NPEs on null fields (`:104`). Amends: retarget step 3, and the plan needs a default
  *before* step 3 (**v1**).
- **intent** objects to the plan's scope, citing the criterion: retries must be *visible in
  the dashboard* — no step touches `dashboard/`. Amends: add step 5, dashboard column +
  test (**v2**).
- **delivery** discloses: there is no maintenance window before the release
  (`deploy/RELEASES.md`), so an offline migration in step 4 cannot run. States the
  trade-off explicitly — offline migration (simpler, needs a window) vs. online default +
  lazy backfill (no window, more code) — and proposes online: step 2b "default `retryCount`
  to 0", step 4 becomes lazy backfill, groups reordered to {2, 2b} → {3, 5} ∥ {4} (**v3**).

**Round 2**

- **codebase** accepts v3 — basis: verified `schedule()` handles default 0 (`:104`).
- **intent** accepts v3 — basis: the criterion now maps to steps 3 + 5.
- **delivery** accepts its own v3.

**Converged on v3 in 2 rounds. Trade-off decided: online backfill, because no deploy window
+ a null-intolerant scheduler.**

## Why this needed a deliberation, not a validation

Compare `plan-validator`'s worked example on the same plan. The validator *finds*
`dispatch-signature-missing` and `migrate-before-default` — both real. But it cannot add the
missing dashboard step (that requires reading the spec's intent against the plan) and it
cannot *choose* the backfill strategy (that requires weighing a delivery constraint against
a code shape). The deliberation did both.

The revised plan still faces the validator afterward. The panel is invested in the trade-off
it just negotiated; consensus is not adversarial survival.
