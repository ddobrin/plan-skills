---
name: policy-security
description: Security rules for this repository. Loaded by the plan swarm's product-owner, spec-validator, and implementation-validator when listed under `policies` in plans/swarm.md. Use when writing or reviewing requirements or code that touches authentication, user input, personal data, or secrets.
---

# Security policy (example: replace with your own)

Copy this folder to `.agents/skills/policy-security/`, edit the rules, and list `policy-security` under `policies` in `plans/swarm.md`. The product owner applies these rules while writing specs and records conflicts under *Policy Concerns*; the validators attack specs and diffs against them.

## Rules

1. **Authentication.** Every new endpoint states who may call it. Lockouts and rate limits never reveal whether an account exists.
2. **Input.** All external input is validated at the boundary; queries are parameterized.
3. **Personal data.** Name every new field that holds personal data, its retention period, and who can read it.
4. **Secrets.** No secrets in code, config committed to git, logs, or error messages.
5. **Owner.** Questions about these rules go to: <security contact>.
