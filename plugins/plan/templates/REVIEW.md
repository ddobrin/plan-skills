# Review policy

Automated reviewers read this file: the plan swarm's `implementation-validator` in PR mode, and any AI review job you add to CI (see the optional add-on in `.github/workflows/plan-swarm.yml`). People read it too. Keep it short and specific to this repository.

## What to review, in order

1. **Claim vs. reality.** Does the change do what its PR description, intent, and spec say? Flag any acceptance criterion the diff does not satisfy.
2. **Failure paths.** Errors, timeouts, and empty inputs are handled and surfaced, not swallowed.
3. **Security.** Input validation, authorization checks on every new endpoint, no secrets or personal data in code or logs.
4. **Concurrency and state.** Shared mutable state, non-atomic read-modify-write, races across requests.
5. **Tests.** New behavior has tests that would fail without the change. No skipped or weakened tests.
6. **Regressions.** Callers and contracts outside the diff that the change silently breaks.

## Severity

- **Important:** would break behavior, lose or corrupt data, leak data or credentials, or block a rollback. The swarm's critical and high findings map here.
- **Nit:** real but minor: naming, style, small refactors, narrow edge cases. The swarm's medium and low findings map here.
- **Pre-existing:** a problem in code the PR did not change. Report it separately; it does not block the PR.

Report at most five Nits per review. If there are more, say "plus N similar items."

## Repository-specific rules

<!-- Replace these examples with your own. -->
- Every database query that takes user input is parameterized.
- Public API changes need a changelog entry.
- Log lines never include request bodies.
