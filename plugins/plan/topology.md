# plan-swarm@3.0 — Topology

> **Status: implemented** (plugin 3.0.0). This file defines the swarm's topology; the role prompts in `roles/` (rendered to `agents/<role>/agent.md` and `skills/<role>/SKILL.md`) and the control plane in `lib/` + `hooks.json` (Antigravity PreInvocation and PreToolUse hooks) implement it. The as-built description is in `README.md` (lifecycle, control plane, approval phrases) and `SUBAGENTS.md` (agent anatomy and dispatch); the diagrams there are views of this graph. `lib/tests/test_swarmdoc.py` checks the graph's consistency, including that every actor is a role in `roles/`.

## How to read this file

The topology is one directed graph with four parts:

- **Spine** — the ordered lifecycle every milestone walks. Nodes are `step` (mandatory work), `human-gate` (a human approval phrase mints a single-use nonce), or `offered-gate` (an AI validator the supervisor offers; runs only on the user's yes).
- **Add-ons** — optional work that `attaches_to` a spine node and `returns_to` a later one (deliberators, simplifier, recap).
- **Swap-ins** — alternatives that `replace` a spine node and emit the same artifacts, so downstream nodes cannot tell the difference.
- **Loops** — numbered feedback edges. 1–6 keep their plan-swarm@2.1 numbers; 7 and 8 are new.

Anything the swarm or its hooks read at runtime (limits, delivery mode, tiers) lives in the project's `plans/swarm.md`; this file only names those keys in `config_keys` so the graph and the config cannot silently drift.

The graph is the single fenced `json plan-swarm-topology` block below. Scripts find it **by that info-string tag** (regex `^```json plan-swarm-topology\n(.*?)^```` with multiline) and parse it with stdlib `json`. Don't reuse `lib/tally.py`'s `load()` as-is: its untagged pattern captures the tag as part of the payload and the parse fails.

## Versioning

- **Major** (`4.0`): a spine node, human gate, or loop is added, removed, or reordered.
- **Minor** (`3.1`): an add-on or swap-in changes, or a default limit moves.
- Record every bump in the changelog at the end of this file.

## Graph

```json plan-swarm-topology
{
  "name": "plan-swarm",
  "version": "3.0",
  "status": "implemented",
  "supersedes": "plan-swarm@2.1",
  "config_file": "plans/swarm.md",

  "kinds": {
    "step": "mandatory work; cannot be skipped",
    "human-gate": "mandatory; a human approval phrase mints a single-use nonce that a hook consumes",
    "offered-gate": "AI validator; offered at the phase boundary, runs only on the user's yes; tier sets how strongly it is recommended",
    "add-on": "optional work attached to a spine node; offered, off by default",
    "swap-in": "alternative that replaces a spine node and emits the same artifacts",
    "future": "specified but not part of the current end state"
  },

  "approvals": ["intent", "spec", "plan", "commit", "pr", "release"],

  "nodes": [
    { "id": "request", "lane": "spine", "kind": "step",
      "label": "request · signal", "actor": "human", "artifacts": [] },

    { "id": "intent", "lane": "spine", "kind": "step",
      "label": "intent triage", "actor": "product-owner", "mode": "intent",
      "approval": "intent", "effects": ["create branch swarm/{m} (pr mode)", "move the intent into the milestone (git mv when tracked)"],
      "artifacts": ["plans/intents/{date}-{slug}.md", "plans/active_milestones/{m}/intent.md"] },

    { "id": "research", "lane": "spine", "kind": "step",
      "label": "research", "actor": "research",
      "artifacts": ["plans/active_milestones/{m}/intent.md#codebase-context"] },

    { "id": "product-owner", "lane": "spine", "kind": "step",
      "label": "product-owner", "actor": "product-owner", "approval": "spec",
      "artifacts": ["plans/active_milestones/{m}/spec.md", "plans/00-ROADMAP.md"] },

    { "id": "spec-validator", "lane": "spine", "kind": "offered-gate",
      "label": "spec-validator", "actor": "spec-validator",
      "quorum": { "skeptics": 3, "default_gate": 2 },
      "artifacts": ["plans/active_milestones/{m}/adversarial-reviews/spec-validation.md"] },

    { "id": "architect", "lane": "spine", "kind": "step",
      "label": "architect", "actor": "architect",
      "artifacts": ["plans/active_milestones/{m}/plan.md",
                    "plans/active_milestones/{m}/data-model.md",
                    "plans/active_milestones/{m}/api-contracts.md"] },

    { "id": "plan-validator", "lane": "spine", "kind": "offered-gate",
      "label": "plan-validator", "actor": "plan-validator",
      "quorum": { "skeptics": 3, "default_gate": 2 }, "emits": ["first_domino"],
      "artifacts": ["plans/active_milestones/{m}/adversarial-reviews/plan-validation.md"] },

    { "id": "review-gate", "lane": "spine", "kind": "human-gate",
      "label": "HUMAN REVIEW GATE", "approval": "plan", "confirms": ["tier"],
      "effects": ["commit the plan and gate reports"],
      "artifacts": ["plans/active_milestones/{m}/approvals.md"] },

    { "id": "engineer", "lane": "spine", "kind": "step",
      "label": "engineer × N", "actor": "engineer",
      "parallel": { "config_key": "engineers.max_concurrent", "default": 5,
                    "isolation": "worktree", "worktree_tool": "lib/worktree.py",
                    "worktree_path": ".swarm/worktrees/{m}/{task}", "branch": "swarm-wip/{m}/{task}",
                    "wip_commits": true, "integration": "squash-no-commit" },
      "artifacts": ["source + tests", "plans/active_milestones/{m}/plan.md#checkboxes"] },

    { "id": "auditor", "lane": "spine", "kind": "step",
      "label": "auditor", "actor": "auditor",
      "artifacts": ["plans/active_milestones/{m}/audit.md"] },

    { "id": "implementation-validator", "lane": "spine", "kind": "offered-gate",
      "label": "implementation-validator", "actor": "implementation-validator",
      "quorum": { "skeptics": 3, "default_gate": 2 }, "emits": ["severity_calibration"],
      "modes": ["finding-hunt", "claim-refutation", "pr"],
      "artifacts": ["plans/active_milestones/{m}/adversarial-reviews/implementation-validation.md"] },

    { "id": "commit-gate", "lane": "spine", "kind": "human-gate",
      "label": "COMMIT GATE", "approval": "commit", "requires": ["audit PASS"],
      "committer": "auditor", "per": "execution group",
      "artifacts": ["group commit on swarm/{m}"] },

    { "id": "pull-request", "lane": "spine", "kind": "human-gate",
      "label": "pull request", "approval": "pr", "when": { "config_key": "delivery.mode", "equals": "pr" },
      "effects": ["push swarm/{m}", "open PR with recap + gate verdicts + ledger"],
      "merge": "code owner on the host", "artifacts": ["PR"] },

    { "id": "release", "lane": "spine", "kind": "human-gate",
      "label": "release · tag", "approval": "release", "actor": "supervisor",
      "effects": ["annotated tag", "product-owner marks release Shipped"],
      "artifacts": ["plans/00-ROADMAP.md"] },

    { "id": "maintain", "lane": "spine", "kind": "future",
      "label": "maintain", "actor": "triage",
      "trigger": "bands.md breach at propose tier",
      "artifacts": ["plans/intents/{date}-{slug}.md"] },

    { "id": "spec-deliberator", "lane": "add-on", "kind": "add-on",
      "attaches_to": "product-owner", "returns_to": "spec-validator",
      "panel": { "delegates": 3, "max_rounds": 4, "context": "disjoint bundles" },
      "artifacts": ["plans/active_milestones/{m}/deliberations/spec-deliberation.md"] },

    { "id": "plan-deliberator", "lane": "add-on", "kind": "add-on",
      "attaches_to": "architect", "returns_to": "plan-validator",
      "panel": { "delegates": 3, "max_rounds": 4, "context": "assigned territories" },
      "artifacts": ["plans/active_milestones/{m}/deliberations/plan-deliberation.md"] },

    { "id": "simplifier", "lane": "add-on", "kind": "add-on",
      "attaches_to": "engineer", "returns_to": "auditor",
      "constraint": "zero behavioral change", "artifacts": [] },

    { "id": "visual-implementation-recap", "lane": "add-on", "kind": "add-on",
      "attaches_to": "implementation-validator", "returns_to": "commit-gate",
      "artifacts": ["plans/active_milestones/{m}/visual-recap.html"] },

    { "id": "visual-product-owner", "lane": "swap-in", "kind": "swap-in",
      "replaces": "product-owner",
      "extra_artifacts": ["plans/active_milestones/{m}/visual-spec.html"] },

    { "id": "visual-architect", "lane": "swap-in", "kind": "swap-in",
      "replaces": "architect",
      "extra_artifacts": ["plans/active_milestones/{m}/visual-plan.html"] },

    { "id": "local-mode", "lane": "swap-in", "kind": "swap-in",
      "replaces": "pull-request", "returns_to": "release",
      "when": { "config_key": "delivery.mode", "equals": "local" },
      "effect": "commits land on the current branch; no PR; ledger rows carry mode=local" }
  ],

  "flow": [
    ["request", "intent"], ["intent", "research"], ["research", "product-owner"],
    ["product-owner", "spec-validator"], ["spec-validator", "architect"],
    ["architect", "plan-validator"], ["plan-validator", "review-gate"],
    ["review-gate", "engineer"], ["engineer", "auditor"],
    ["auditor", "implementation-validator"], ["implementation-validator", "commit-gate"],
    ["commit-gate", "pull-request"], ["pull-request", "release"],
    ["release", "maintain"]
  ],

  "loops": [
    { "n": 1, "from": "spec-validator", "to": "product-owner",
      "trigger": "confirmed finding with a tightening", "applied_by": "product-owner" },
    { "n": 2, "from": "plan-validator", "to": "architect",
      "trigger": "confirmed fix; first_domino first", "applied_by": "architect" },
    { "n": 3, "from": "auditor", "to": "engineer", "name": "Path A",
      "trigger": "tests fail or anti-shortcut hit",
      "limit": { "config_key": "audit.max_path_a_rounds", "default": 3, "then": "escalate to human" } },
    { "n": 4, "from": "implementation-validator", "to": "engineer",
      "trigger": "confirmed defect at calibrated severity" },
    { "n": 5, "from": "commit-gate", "to": "engineer",
      "trigger": "group committed and groups remain" },
    { "n": 6, "from": "auditor", "to": "architect", "name": "Path B",
      "trigger": "plan impossible, engineer blocked, or worktree squash conflict",
      "requires_approval": "plan" },
    { "n": 7, "from": "pull-request", "to": "engineer",
      "trigger": "CI review or code-owner findings", "new_in": "3.0" },
    { "n": 8, "from": "maintain", "to": "intent", "kind": "future",
      "trigger": "band breach at propose tier", "new_in": "3.0" }
  ],

  "config_keys": [
    "delivery.mode", "delivery.host", "engineers.max_concurrent",
    "audit.max_path_a_rounds", "approvals.nonce_ttl_minutes", "policies", "tiers"
  ]
}
```

## Changelog

### 3.0 on Antigravity (plugin 3.0.0)
- Same graph. The `research` actor is a read-only research subagent (`invoke_subagent`), not a built-in agent.
- Human gates: each approval phrase is typed in the top-level Antigravity conversation; the PreInvocation hook mints the nonce, the PreToolUse gate consumes it.

### 3.0 (implemented, plugin 3.0.0)
- **Spine:** adds `intent` (inbox → accepted intent) at the top and `pull-request` before `release`.
- **Human gates:** six nonce-gated approvals — intent, spec, plan, commit, pr, release (was: review gate and commit gate typed in chat, plus release).
- **Engineers:** up to **5** concurrent (was 4), one git worktree each (`.swarm/worktrees/`, created by `lib/worktree.py`), WIP commits on `swarm-wip/{m}/{task}`, squashed per group without committing. (Worktree branches cannot live under `swarm/{m}/…` because git refuses a ref below an existing branch.)
- **Branch:** in pr mode `swarm/{m}` is created when the intent is accepted, so the intent, spec, and plan commits ship inside the PR.
- **Loops:** Path A capped at 3 rounds, then escalation; adds loop 7 (PR review → engineer) and loop 8 (maintain → intent, future).
- **Swap-ins:** adds `local-mode` as the alternative to `pull-request`.
- **Validators:** still offered; now report-only, with fixes applied by the author role.

### 2.1
- Baseline: request → research → spec → plan → review gate → build → audit → commit gate → tag; loops 1–6; add-ons spec-deliberator, plan-deliberator, simplifier, visual-implementation-recap.
