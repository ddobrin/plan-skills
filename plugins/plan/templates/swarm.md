# Swarm configuration

This file configures the plan swarm (plan-swarm@3.0) for this repository. People read the prose; the swarm's hooks and scripts read only the single `json swarm-config` block at the end. Keep exactly one such block. If it is missing or invalid, every gated operation (commit, push, tag) is refused until it is fixed.

Change a value by editing the block, and write down why in the matching section below. The swarm never edits this file.

## Delivery

`delivery.mode` decides where finished work lands:

- `"pr"` (default): each milestone gets a branch `swarm/{milestone}`, one audited commit per execution group, and a pull request at the end. A code owner merges it on GitHub.
- `"local"`: commits land on your current branch and no PR is opened. Use it for solo or offline work. Every approval row records `mode=local`.

`delivery.host` is `"github"`, the only host supported today.

## Engineers

`engineers.max_concurrent` caps how many engineers build in parallel, each in its own git worktree. The default is 5. Lower it if your machine struggles to run several test suites at once.

## Audit

`audit.max_path_a_rounds` is how many times one task may fail the audit and go back to an engineer before the supervisor stops and asks you what to do. The default is 3.

## Approvals

`approvals.nonce_ttl_minutes` is how long an approval phrase stays valid after you type it. The default is 15. Approvals are single-use and also expire if the branch moves.

## Policy skills

`policies` lists project skills (under `.agents/skills/`, Antigravity's workspace skills folder) that the product owner, spec-validator, and implementation-validator load, for example your security or API-convention rules. Leave it empty if you have none.

## Risk tiers

A script proposes a tier for each milestone: `critical` if any critical rule matches, else `elevated` if any elevated rule matches, else `routine`. It checks the intent's wording (`keywords`), the files the plan names (`paths`), and before the PR the real diff (`paths`, `diff_lines_over`). The tier can rise on its own, never fall; you confirm it when you approve the plan. Tiers change how strongly the supervisor recommends the optional checks. They never force one.

Why these rules: authentication, payments, and migrations are hard to undo or leak data when wrong; public API changes affect callers you do not control.

```json swarm-config
{
  "version": 1,
  "delivery": { "mode": "pr", "host": "github" },
  "engineers": { "max_concurrent": 5 },
  "audit": { "max_path_a_rounds": 3 },
  "approvals": { "nonce_ttl_minutes": 15 },
  "policies": [],
  "tiers": {
    "critical": {
      "paths": ["**/auth/**", "**/payments/**", "**/migrations/**"],
      "keywords": ["password", "credential", "token", "payment", "pii", "migration", "delete"]
    },
    "elevated": {
      "paths": ["**/api/**", "**/public/**"],
      "keywords": ["concurrency", "cache", "schema", "public api"],
      "diff_lines_over": 400
    }
  }
}
```
