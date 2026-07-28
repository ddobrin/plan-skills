# Worked Example — spec-deliberator

> Spec draft: *"The export endpoint returns the user's records as a downloadable file.
> Exports should be fast and handle large accounts."*

**Bundles (disjoint):**

- **product** — user research: exports are used for tax filing; 95% of accounts hold
  < 10k records; users expect CSV.
- **engineering** — infra docs: 30s gateway timeout, 100MB response cap, sharded store.
- **ops** — data policy: row-level ACLs, audit logging mandatory.

**Round 1**

- **engineering** discloses the 30s timeout: "fast" and "large accounts" cannot both be
  satisfied synchronously. Proposes async-only export (**v1**).
- **product** objects to v1, citing its bundle: 95% of accounts are small and users export
  interactively at tax time — async-only degrades the common case. Amends to sync ≤ 50k
  records, async above (**v2**). Also discloses that the format must be CSV with a stable
  header — "a file" is underspecified.
- **ops** accepts v2's shape but amends: the async worker must run under the requester's
  ACLs, not a service account, and every export is audit-logged (**v3**).

**Round 2**

- **engineering** accepts v3 — basis: checked the sync threshold against the response cap,
  50k rows ≈ 12MB, fits.
- **product** accepts v3 — basis: the interactive path is preserved.
- **ops** accepts v3 — basis: its own amendment.

**Converged on v3 in 2 rounds.**

Three facts from three silos — the timeout, the tax-time workflow, the ACL rule — none of
which any single delegate held. Note that each acceptance carries a *basis*: engineering did
arithmetic against its own bundle rather than deferring, which is the difference between
consensus and sycophancy.

The revised spec then goes to `spec-validator`, which now has real thresholds to attack
instead of "fast".
