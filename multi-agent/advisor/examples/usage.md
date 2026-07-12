# Usage Example: Advisor-Assisted Webhook Fix

Scenario: a payments service where Stripe webhook events fail during
brief database outages. The executor (Sonnet) does the work; the advisor
(Fable/Opus) is consulted once, at the design fork.

## Prompt (Claude Code or Antigravity)

```
Add retry logic to our Stripe webhook handler in webhooks/stripe.ts.
Events sometimes fail when the DB is briefly unavailable (~30s outages).
```

## What happens

1. Executor works normally
   - Reads `webhooks/stripe.ts`, traces the DB writes, checks existing
     infra in `jobs/` — all at the cheap executor rate.

2. Executor hits a design fork and escalates (matches trigger:
   "choosing between viable designs")

   ```
   Executor → advisor:
   Stripe webhook handler in webhooks/stripe.ts writes to Postgres
   directly. DB has brief outages (~30s). Options:
   A) In-process retry with exponential backoff
   B) Persist raw event to a durable table, process async with a worker
   C) Push to existing BullMQ queue (already used in jobs/)
   Constraints: Stripe retries failed webhooks for 3 days but expects a
   2xx within 20s. Must avoid double-processing. Which approach?
   ```

3. Advisor reads the two relevant files and answers

   ```
   Advisor → executor:
   1. Recommendation: C.
   2. Why: BullMQ already exists, so B duplicates infrastructure. A is
      unsafe — backoff past 20s means Stripe times out and re-sends,
      and there is no idempotency handling, so events double-process.
   3. Risks: if the queue itself is down, events are lost until Stripe's
      3-day retry re-delivers — acceptable fallback.
   4. Avoid: any synchronous retry in the request path; anything that
      delays the 2xx.
   ```

4. Executor implements the full plan itself
   - Handler validates signature, enqueues, returns 200 immediately.
   - Worker processes with an idempotency check on `event.id` (unique
     constraint + migration).
   - BullMQ retry/backoff config, plus tests.

## Token economics

The advisor (expensive model) saw one distilled question and two files —
a few hundred tokens. The executor (cheap model) burned the thousands of
tokens on exploration and implementation. Inverse of the orchestrator
pattern: here the cheap model owns the loop.

## Tips

- The escalation triggers live in CLAUDE.md / AGENTS.md; tune the
  thresholds (failed attempts, file count) to your risk tolerance.
- The quality of the consultation depends on the distillation: options +
  constraints in, one decision out. If you see raw logs being sent to
  the advisor, tighten the instructions.
- If the executor overrides advice repeatedly, that's a smell — either
  the questions lack constraints or the triggers fire too often.
