# `.claude/workflows`

Project-scoped [Workflow](https://docs.claude.com/en/docs/claude-code) scripts for this repo.
Each `*.js` file here is a workflow the `Workflow` tool can run **by name** (e.g.
`Workflow({ name: 'plan-swarm', args: '…' })`), in addition to any ad-hoc workflow
authored inline.

---

## `plan-swarm`

Drives a milestone through **architect → engineer(s) → auditor**, stopping at the
human commit gate. It turns a `spec.md` into a `plan.md`, implements it under TDD
across the plan's execution groups, audits the result, and **stops before commit** —
it never commits.

### Pipeline

```
architect ──► [plan-validator?] ──► engineer × N ──► auditor ──► [engineer fix ⇄ re-audit] ──► STOP
  (Plan)        (optional GO/NO-GO)   (per task,        (PASS/FAIL)   (bounded loop)         (commit gate)
                                       parallel/group)
```

| Phase | Agent | What it does |
|---|---|---|
| **Plan** | `plan:architect` | Reads `spec.md`, investigates the code, writes `plan.md`, returns the group/task breakdown. Read-only on code. |
| **Validate Plan** *(optional)* | `plan:plan-validator` | Adversarially checks `plan.md` against the codebase; returns GO / NO-GO. On NO-GO the workflow stops before building. |
| **Build** | `plan:engineer` | One engineer per task, under TDD. Tasks **within a group run in parallel**; **groups run sequentially**. A blocked task stops the build before later groups. |
| **Audit** | `plan:auditor` | Verifies the implementation against `plan.md` + `spec.md`, runs build/tests, scans for TODOs/placeholders/skipped tests. Writes `plans/audit/AUDIT_{moniker}.md`. Returns PASS/FAIL. |
| **Fix** *(optional, bounded)* | `plan:engineer` | On a FAIL, dispatches one fix per finding under TDD, then re-audits. Repeats up to `maxFixRounds`. |

> Parallel-within-group is safe because the architect guarantees tasks in the same
> group touch **different files**.

### Prerequisite

A `spec.md` must already exist at:

```
plans/active_milestones/{moniker}/spec.md
```

Writing the spec is the `plan:product-owner`'s job — `plan-swarm` deliberately starts
at the architect. The moniker is **required**; the workflow throws without it.

### Paths it uses

| Path | Role |
|---|---|
| `plans/active_milestones/{moniker}/spec.md` | Input — read by the architect and auditor |
| `plans/active_milestones/{moniker}/plan.md` | Written by the architect, consumed by engineers + auditor |
| `plans/audit/AUDIT_{moniker}.md` | Audit report written by the auditor |

### How to invoke

Workflows spawn many agents, so they need **explicit opt-in** — ask in plain words,
e.g.:

- "Run the plan-swarm workflow on the `auth-mvp` milestone."
- "Use a workflow to plan, build, and audit `checkout-redesign`."
- "ultracode — drive the `auth-mvp` milestone to the commit gate."

Which resolves to:

```js
Workflow({ name: 'plan-swarm', args: 'auth-mvp' })
```

**With options** — pass an object instead of a bare string:

```js
Workflow({ name: 'plan-swarm', args: {
  moniker: 'auth-mvp',
  validatePlan: true,        // insert the adversarial plan-validator before building — default false
  maxFixRounds: 2,           // engineer↔auditor retry budget on a FAIL — default 1
  parallelWithinGroup: true, // default true; set false to build tasks one at a time
}})
```

| Option | Type | Default | Effect |
|---|---|---|---|
| `moniker` | string | — (**required**) | Milestone directory name under `plans/active_milestones/`. A bare string arg is treated as the moniker. |
| `validatePlan` | boolean | `false` | Run `plan:plan-validator` after planning; stop on NO-GO. |
| `parallelWithinGroup` | boolean | `true` | Run a group's tasks concurrently vs. one at a time. |
| `maxFixRounds` | integer | `1` | Max engineer↔auditor fix/re-audit rounds on a FAIL. |

### Where it stops (and how to resume)

The workflow returns a structured result with a `nextStep` hint at every exit:

| Exit | `stopped` | What it means / next step |
|---|---|---|
| Plan validator NO-GO | `plan-validation` | Fix the plan per the validation report, then re-run. |
| Engineer blocked | `engineer-blocked` | Resolve the blockers (usually a plan fix), then re-run. |
| Audit PASS | *(none)* | Review `plans/audit/AUDIT_{moniker}.md`, then approve commit. |
| Audit still FAIL after fixes | *(none)* | Address remaining failures, then re-run (or raise `maxFixRounds`). |

**Committing is out of scope.** The auditor is the only role allowed to commit, and
only on your explicit approval — `plan-swarm` never commits.

### Watching progress

Use `/workflows` to watch live progress. On completion, the audit verdict and the
`AUDIT_{moniker}.md` path are relayed back so you can decide whether to approve the
commit.

### Tips

- **Iterate without resending the script:** every run persists its script and returns
  a `scriptPath`. To tweak the pipeline, edit the file and re-run with `{ scriptPath }`
  — add `resumeFromRunId` to reuse cached agent results for the unchanged prefix (e.g.
  skip re-planning and jump straight to a re-audit).
- **`args` is the reuse seam:** nothing is hard-coded — the moniker flows in at call
  time and every agent resolves its paths from it, so one file serves every milestone.
