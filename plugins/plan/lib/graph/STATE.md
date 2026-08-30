# `state.json` — the milestone's declared state

Every milestone carries `plans/active_milestones/{moniker}/state.json`. It is the run's
record of **where it is**, written by `starter` and read by anyone resuming.

Before this file existed, `starter` resumed by listing the milestone directory and
*inferring* the phase from which artifacts happened to be present. That inference is a
re-derivation of state nobody ever recorded, and it is where a resumed run silently
re-enters the wrong phase — a validator that ran and failed looks identical to one that
never ran, because both leave a `plan.md` on disk.

The artifacts remain the payload. This file is the index over them.

## Contract

- `starter` **writes** it: at milestone creation, at every phase transition, at every gate
  decision, and when a node completes.
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
  "phase": "2.gate",
  "updated": "2026-08-28T14:02:11Z",

  "gates": [
    { "id": "plan-approval", "state": "pending" },
    { "id": "commit", "state": "not-reached" }
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
    "plan-validator":  { "status": "running" }
  },

  "groups": [
    { "id": "1",
      "tasks": { "1.A": "done", "1.B": "done" },
      "audit": "passed",
      "audit_rounds": 1,
      "implementation_validation": "adversarial-reviews/implementation-validation.md",
      "committed": "a3f19c2" },
    { "id": "2", "tasks": { "2.A": "pending" }, "audit": "not-reached" }
  ]
}
```

## Fields

| Field | Meaning |
|---|---|
| `graph_version` | The topology this run was started against, matching `graph.json`. A mismatch means the swarm changed mid-milestone — say so before continuing. |
| `run_id` | Stable id for the whole milestone run. Stamp it on every report the run produces so an artifact can be traced to the run that made it. |
| `phase` | `"{n}"` for a phase in progress, `"{n}.gate"` when its gate is outstanding. |
| `gates[].state` | `not-reached` · `pending` · `approved` · `rejected`. Human decisions only. |
| `nodes.{id}.status` | `pending` · `running` · `done` · `passed` · `findings` · `skipped` · `failed`. |
| `nodes.{id}.reason` | Required whenever status is `skipped`. |
| `nodes.{id}.lenses` | For panels: the lenses actually dispatched. Proof the panel was partitioned rather than run three times identically. |
| `nodes.{id}.cross_lens` | For panels: how many confirmed findings were reached by **more than one lens**. This is the number that says whether the panel produced independent corroboration or the same opinion twice. |
| `nodes.{id}.single_vote_triaged` | The single-vote tail needs an explicit decision per finding; this records that it got one. |
| `groups[].audit_rounds` | How many engineer⇄auditor cycles this group took. The loop is capped at 3; a group at 3 stops and goes to the user. |
| `groups[].committed` | The commit SHA, written only after the human said yes. |

## Node contracts

`graph.json` declares `reads`, `writes` and `must_not_write` for every node. Those are the
edges state is allowed to cross. They are what turns "`architect` is read-only on source"
from a sentence in a prompt into a claim the auditor can check:

```bash
python3 lib/graph/graph.py validate   # topology and contracts vs. the skills on disk
```
