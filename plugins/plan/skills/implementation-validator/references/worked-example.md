# Worked Example — implementation-validator

> Change claims: *"Planner walks precompiled steps; safe under concurrent deliberations."*
> Finding-hunt mode, 3 skeptics over `git diff origin/main..HEAD`.

After dedup + majority gate + calibration:

**Confirmed (≥ 2 votes):**

- `singleton-cursor-race` (3 votes) — claimed **critical** by the skeptics, **corrected to
  high**. The planner is a shared singleton with non-volatile `cursor`/`steps` instance
  fields mutated per run (`Planner.java:59-64`, non-atomic `cursor++` at `:306`). One
  verifier narrowed it: intra-request replan is serialized, so the race is **strictly
  cross-request**, not within one deliberation — which is why "critical" (implying
  unconditional corruption) was an overstatement. Fix: make the planner request-scoped, or
  move per-run state out of the bean.

**Single vote (triage required):**

- `objectmapper-dup` (1 vote, low) — duplicated `ObjectMapper`/serialization setup. Triaged:
  **accepted** — real duplication, but it is a cleanliness issue with no correctness impact
  and the change is already scoped. Recorded so it is a deliberate deferral rather than an
  oversight.

**Calibration reported to the user:** *"1 finding claimed Critical; confirmed real by all 3
skeptics but downgraded to High — impact is gated on concurrent requests, not every run."*

That last sentence is the highest-value line the panel produced. It separates "guaranteed on
every call" from "serious but gated" — the distinction a single aggressive reviewer gets
wrong, and the one that decides whether this blocks the merge.
