export const meta = {
  name: 'plan-swarm',
  description: 'Drive a milestone through architect → engineer(s) → auditor, stopping at the human commit gate',
  whenToUse:
    'After a spec.md exists for a milestone. Turns the spec into plan.md, implements it under TDD ' +
    'across the plan\'s execution groups, audits the result, and stops BEFORE commit (the commit gate ' +
    'stays with the human + auditor). Pass the milestone moniker as args.',
  phases: [
    { title: 'Plan', detail: 'architect reads spec.md → writes plan.md + returns group/task breakdown' },
    { title: 'Validate Plan', detail: 'optional: plan-validator adversarially checks plan.md before build' },
    { title: 'Build', detail: 'engineer per task, parallel within a group, groups run sequentially (TDD)' },
    { title: 'Audit', detail: 'auditor verifies against plan.md + spec.md, returns PASS/FAIL' },
    { title: 'Fix', detail: 'optional bounded loop: engineer fixes audit failures, then re-audit' },
  ],
}

// ─────────────────────────────────────────────────────────────────────────────
// Args
//   Pass a bare moniker string, or an object for more control:
//     { moniker, validatePlan?, parallelWithinGroup?, maxFixRounds? }
// ─────────────────────────────────────────────────────────────────────────────
const cfg = typeof args === 'string' ? { moniker: args } : (args || {})
const moniker = cfg.moniker
const validatePlan = cfg.validatePlan === true
const parallelWithinGroup = cfg.parallelWithinGroup !== false // default true
const maxFixRounds = Number.isInteger(cfg.maxFixRounds) ? cfg.maxFixRounds : 1

if (!moniker) {
  throw new Error(
    'plan-swarm requires a milestone moniker. Invoke with args: "auth-mvp" ' +
    'or args: { moniker: "auth-mvp", validatePlan: true, maxFixRounds: 2 }'
  )
}

const milestoneDir = `plans/active_milestones/${moniker}`
const specPath = `${milestoneDir}/spec.md`
const planPath = `${milestoneDir}/plan.md`

// ─────────────────────────────────────────────────────────────────────────────
// Schemas — force structured output so the deterministic script can branch on it
// ─────────────────────────────────────────────────────────────────────────────
const ARCHITECT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    planPath: { type: 'string', description: 'Path to the plan.md that was written' },
    objective: { type: 'string' },
    groups: {
      type: 'array',
      description: 'Execution groups in order. Groups run sequentially; tasks within a group are independent.',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          id: { type: 'string', description: 'e.g. "Group 1"' },
          tasks: {
            type: 'array',
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                id: { type: 'string', description: 'e.g. "Task 1.A"' },
                title: { type: 'string' },
                targetFiles: { type: 'array', items: { type: 'string' } },
              },
              required: ['id', 'title'],
            },
          },
        },
        required: ['id', 'tasks'],
      },
    },
  },
  required: ['planPath', 'groups'],
}

const ENGINEER_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    taskId: { type: 'string' },
    status: { type: 'string', enum: ['done', 'blocked'] },
    notes: { type: 'string', description: 'What was implemented, or why it is blocked' },
  },
  required: ['taskId', 'status'],
}

const AUDIT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    status: { type: 'string', enum: ['PASS', 'FAIL'] },
    completionRate: { type: 'string', description: 'e.g. "6/6 steps verified"' },
    reportPath: { type: 'string' },
    summary: { type: 'string' },
    failures: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          taskId: { type: 'string' },
          issue: { type: 'string' },
          fix: { type: 'string', description: 'Actionable fix for the engineer' },
        },
        required: ['issue'],
      },
    },
  },
  required: ['status', 'summary'],
}

const PLAN_VALIDATION_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    verdict: { type: 'string', enum: ['GO', 'NO-GO'] },
    firstDomino: { type: 'string', description: 'Earliest step whose failure invalidates the rest, or "none"' },
    confirmedFindings: { type: 'array', items: { type: 'string' } },
    reportPath: { type: 'string' },
  },
  required: ['verdict'],
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase 1 — PLAN
// ─────────────────────────────────────────────────────────────────────────────
phase('Plan')
log(`Planning milestone "${moniker}" from ${specPath}`)

const plan = await agent(
  `You are planning the milestone "${moniker}".\n` +
  `Read the spec at ${specPath} and investigate the affected code, then write the ` +
  `micro-stepped plan to ${planPath} exactly as your role requires (READ-ONLY on code, never commit).\n\n` +
  `In your structured return, mirror the plan's execution groups: list every Group in order, and ` +
  `within each Group list its Tasks with their id, title, and the exact target file(s). Tasks within ` +
  `a Group MUST be independent (they must not modify the same files).`,
  { agentType: 'plan:architect', phase: 'Plan', schema: ARCHITECT_SCHEMA }
)

if (!plan || !plan.groups || plan.groups.length === 0) {
  throw new Error(`Architect produced no execution groups for "${moniker}". Check that ${specPath} exists.`)
}
log(`Plan written to ${plan.planPath || planPath}: ${plan.groups.length} group(s), ` +
    `${plan.groups.reduce((n, g) => n + g.tasks.length, 0)} task(s)`)

// ─────────────────────────────────────────────────────────────────────────────
// Phase 2 — VALIDATE PLAN (optional, adversarial)
// ─────────────────────────────────────────────────────────────────────────────
if (validatePlan) {
  phase('Validate Plan')
  const pv = await agent(
    `Adversarially validate the plan at ${planPath} against the codebase and ${specPath}. ` +
    `Find the first domino — the earliest step whose failure invalidates the rest. ` +
    `Return GO only if no confirmed blocking finding survives your 2-of-3 majority gate.`,
    { agentType: 'plan:plan-validator', phase: 'Validate Plan', schema: PLAN_VALIDATION_SCHEMA }
  )
  if (pv && pv.verdict === 'NO-GO') {
    log(`plan-validator returned NO-GO (first domino: ${pv.firstDomino || 'n/a'}). Stopping before build.`)
    return {
      moniker,
      stopped: 'plan-validation',
      planPath: plan.planPath || planPath,
      planValidation: pv,
      nextStep: `Fix the plan per ${pv.reportPath || 'the validation report'} and re-run plan-swarm.`,
    }
  }
  log('plan-validator: GO')
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase 3 — BUILD (groups sequential = barrier; tasks within a group parallel)
// ─────────────────────────────────────────────────────────────────────────────
phase('Build')
const buildResults = []

function engineerTask(task, groupId) {
  return agent(
    `Implement ${task.id} — "${task.title}" — from the approved plan at ${planPath} ` +
    `(milestone "${moniker}", ${groupId}). Read the plan for the exact steps, then proceed strictly ` +
    `under TDD (Red → Green → Refactor), keep the build green, and mark this task's todos [x] in ${planPath}. ` +
    `Stay strictly within ${task.id}; never expand scope and never commit. ` +
    `If you hit a blocker you cannot resolve within scope, return status "blocked" with the reason.`,
    { agentType: 'plan:engineer', phase: 'Build', label: `build:${task.id}`, schema: ENGINEER_SCHEMA }
  )
}

for (const group of plan.groups) {
  log(`${group.id}: ${group.tasks.length} task(s) — ${parallelWithinGroup ? 'parallel' : 'sequential'}`)
  let results
  if (parallelWithinGroup) {
    results = await parallel(group.tasks.map(t => () => engineerTask(t, group.id)))
  } else {
    results = []
    for (const t of group.tasks) results.push(await engineerTask(t, group.id))
  }
  const blocked = results.filter(Boolean).filter(r => r.status === 'blocked')
  buildResults.push(...results.filter(Boolean))
  if (blocked.length) {
    log(`${group.id} has ${blocked.length} blocked task(s). Stopping the build before later groups.`)
    return {
      moniker,
      stopped: 'engineer-blocked',
      planPath: plan.planPath || planPath,
      blocked,
      nextStep: 'Resolve the blockers (they usually mean the plan needs a fix), then re-run plan-swarm.',
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase 4 + 5 — AUDIT, then a bounded FIX↔RE-AUDIT loop
// ─────────────────────────────────────────────────────────────────────────────
async function runAudit() {
  return agent(
    `Audit the implementation of milestone "${moniker}" against ${planPath} and ${specPath}. ` +
    `Verify each step statically (cite file:line), run the build and the relevant tests, and scan ` +
    `modified files for TODO/placeholder/deferred-work and gutted/skipped tests. ` +
    `Write the evidence-based PASS/FAIL report to plans/audit/AUDIT_${moniker}.md. ` +
    `DO NOT COMMIT — return your verdict only.`,
    { agentType: 'plan:auditor', phase: 'Audit', schema: AUDIT_SCHEMA }
  )
}

phase('Audit')
let audit = await runAudit()

let round = 0
while (audit && audit.status === 'FAIL' && round < maxFixRounds) {
  round++
  phase('Fix')
  const failures = (audit.failures && audit.failures.length)
    ? audit.failures
    : [{ issue: audit.summary }]
  log(`Audit FAIL (round ${round}/${maxFixRounds}): dispatching ${failures.length} fix(es)`)

  await parallel(failures.map((f, i) => () =>
    agent(
      `The auditor rejected milestone "${moniker}". Fix this specific finding under TDD, staying in scope, ` +
      `and update ${planPath}:\n\n` +
      `Task: ${f.taskId || 'unspecified'}\nIssue: ${f.issue}\n` +
      `${f.fix ? 'Suggested fix: ' + f.fix : ''}\n\nNever expand scope and never commit.`,
      { agentType: 'plan:engineer', phase: 'Fix', label: `fix:${f.taskId || i}` }
    )
  ))

  phase('Audit')
  audit = await runAudit()
}

// ─────────────────────────────────────────────────────────────────────────────
// STOP at the commit gate — hand the verdict back to the human
// ─────────────────────────────────────────────────────────────────────────────
const passed = audit && audit.status === 'PASS'
log(passed
  ? `Audit PASS — stopping at the commit gate.`
  : `Audit still FAIL after ${round} fix round(s) — stopping.`)

return {
  moniker,
  planPath: plan.planPath || planPath,
  tasksImplemented: buildResults.map(r => ({ taskId: r.taskId, status: r.status })),
  audit,
  fixRounds: round,
  nextStep: passed
    ? `Review plans/audit/AUDIT_${moniker}.md, then approve commit. The auditor is the only role ` +
      `allowed to commit, and only on your explicit approval — plan-swarm never commits.`
    : `Read plans/audit/AUDIT_${moniker}.md, address the remaining failures, and re-run plan-swarm ` +
      `(or raise maxFixRounds).`,
}
