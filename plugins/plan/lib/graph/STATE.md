# `state.json` — the milestone's declared state

Every milestone carries `plans/active_milestones/{moniker}/state.json`. It is the run's
record of **where it is**, written by the Supervisor and read by anyone resuming.

"The Supervisor" is one role in two packagings: the `starter` skill and the `supervisor`
agent. Wherever this document says `starter`, the `supervisor` agent is bound by the same
contract.

Before this file existed, `starter` resumed by listing the milestone directory and
*inferring* the phase from which artifacts happened to be present. That inference is a
re-derivation of state nobody ever recorded, and it is where a resumed run silently
re-enters the wrong phase — a validator that ran and failed looks identical to one that
never ran, because both leave a `plan.md` on disk.

The artifacts remain the payload. This file is the index over them.

## Contract

- `starter` **writes** it: at milestone creation, at every phase transition, at every gate
  decision, and when a node completes.
- It is created when the milestone is opened — once `plans/active_milestones/{moniker}/`
  exists. Phase 0 (research) runs before there is a milestone, so there is no file yet and
  no `"phase": "0"`: a request with no milestone directory is, by definition, still in
  Phase 0 or at the start of Phase 1. That is the one place absence is the signal.
- Every other node **reads** it. Only `starter` and the gates it holds may write.
- A field you cannot fill honestly is left absent, never guessed. `"status": "unknown"` is
  a legitimate value; a fabricated `"passed"` is not.
- A **skipped gate is recorded as skipped**, with a reason. An unrecorded skipped gate is
  indistinguishable from one that passed, which is the whole problem this file solves.

## Shape

```json
{
  "graph_version": "plan-swarm@2.1",
  "run_id": "ms_checkout-redesign_0c41",
  "moniker": "checkout-redesign",
  "phase": "4",
  "updated": "2026-08-28T14:02:11Z",

  "gates": [
    { "id": "plan-approval", "state": "approved" },
    { "id": "commit", "state": "approved" }
  ],

  "nodes": {
    "research":        { "status": "done",   "artifact": "context.md" },
    "product-owner":   { "status": "done",   "artifact": "spec.md" },
    "spec-deliberator":{ "status": "skipped", "reason": "asymmetry test failed — context was mergeable" },
    "spec-validator":  { "status": "passed",
                         "report": "adversarial-reviews/spec-validation.md",
                         "lenses": ["internal-consistency", "missing-requirement", "malicious-compliance"],
                         "confirmed": 0, "single_vote": 2, "cross_lens": 0,
                         "single_vote_triaged": true },
    "architect":       { "status": "done",   "artifact": "plan.md" },
    "plan-deliberator":{ "status": "skipped", "reason": "single-subsystem plan — no trade-off left open" },
    "plan-validator":  { "status": "passed",
                         "report": "adversarial-reviews/plan-validation.md",
                         "lenses": ["sequencing", "ground-truth", "blast-radius"],
                         "confirmed": 1, "single_vote": 1, "cross_lens": 1,
                         "first_domino": "migrate-before-default",
                         "single_vote_triaged": true }
  },

  "groups": [
    { "id": "1",
      "tasks": { "1.A": "done", "1.B": "done" },
      "audit": "passed",
      "audit_rounds": 1,
      "implementation_validation": {
        "status": "passed",
        "report": "adversarial-reviews/implementation-validation.md",
        "lenses": ["claim-vs-reality", "failure-paths", "blast-radius"],
        "confirmed": 0, "single_vote": 1, "cross_lens": 0,
        "single_vote_triaged": true },
      "committed": "a3f19c2" },
    { "id": "2", "tasks": { "2.A": "pending" }, "audit": "not-reached" }
  ]
}
```

The snapshot above is a run in Phase 4: the plan was approved, group 1 is audited,
validated and committed, and group 2 has not started. The `commit` gate holds the most
recent decision; `groups[].committed` is the per-group record.

## Fields

| Field | Meaning |
|---|---|
| `graph_version` | The topology this run was started against, matching `graph.json`. A mismatch means the swarm changed mid-milestone — say so before continuing. |
| `run_id` | Stable id for the whole milestone run. Stamp it on every report the run produces so an artifact can be traced to the run that made it. |
| `phase` | `"{n}"` for a phase in progress, `"{n}.gate"` when its gate is outstanding: `1` · `1.gate` · `2` · `2.gate` · `3` · `4` · `4.gate` · `5`. `1.gate` and `2.gate` are the validator panels; `3` is the human review gate; `4.gate` is the commit gate. There is no `0` — see the contract above. |
| `gates[].state` | `not-reached` · `pending` · `approved` · `rejected`. Human decisions only: `plan-approval` goes `pending` at phase `3`, `commit` goes `pending` at phase `4.gate` and is decided once per execution group — it holds the latest decision, and `groups[].committed` is the per-group record. |
| `nodes.{id}.status` | `pending` · `running` · `done` · `passed` · `findings` · `skipped` · `failed` · `unknown`. Roles and deliberations end in `done`. Panels end in `passed`; `findings` means a confirmed finding is still unresolved or the single-vote tail is untriaged. `failed` means the node could not complete (for a panel: no usable verdicts). `unknown` is for what cannot be established honestly, typically when reconstructing a milestone that predates this file. |
| `nodes.{id}.reason` | Required whenever status is `skipped`. |
| `nodes.{id}.lenses` | For panels: the lenses actually dispatched. Proof the panel was partitioned rather than run three times identically. |
| `nodes.{id}.cross_lens` | For panels: how many confirmed findings were reached by **more than one lens**. This is the number that says whether the panel produced independent corroboration or the same opinion twice. |
| `nodes.{id}.single_vote_triaged` | The single-vote tail needs an explicit decision per finding; this records that it got one. |
| `nodes.plan-validator.first_domino` | The `id` of the earliest confirmed finding that invalidates the steps after it, or `null`. |
| `groups[].tasks.{id}` | `pending` · `running` · `done` · `failed`. |
| `groups[].audit` | `not-reached` · `passed` · `failed`. The auditor's verdict on the group. |
| `groups[].audit_rounds` | How many audits this group took, counting re-audits after validator fixes. The engineer⇄auditor loop is capped at 3; a group at 3 that is still not green stops and goes to the user. |
| `groups[].implementation_validation` | The third panel's verdict **for this group**, shaped exactly like a panel node: `status`, `report`, `lenses`, `confirmed`, `single_vote`, `cross_lens`, `single_vote_triaged` — or `"status": "skipped"` with a `reason`. Absent until the panel is dispatched. Each group keeps its own review file: a later group never overwrites an earlier review, it takes the next free `-rN` suffix, and `report` records which file is its own. |
| `groups[].committed` | The commit SHA, written only after the human said yes. |

## Node contracts

`graph.json` declares `reads`, `writes` and `must_not_write` for every node. Those are the
edges state is allowed to cross. They are what turns "`architect` is read-only on source"
from a sentence in a prompt into a claim the auditor can check. From the plugin root:

```bash
python3 lib/graph/graph.py validate                # topology and contracts vs. the skills and agents on disk
python3 lib/graph/graph.py validate --agents-dir   # the same, plus every agent's own invariants
```
