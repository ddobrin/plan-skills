# Advisor-Orchestrator-Worker Pattern

Three tiers: an orchestrator owns the loop (frame, plan, delegate,
verify, synthesize), cheap stateless workers execute subtasks in
parallel waves, and an expensive advisor is consulted exactly where
judgment changes a decision — mandatory plan review before any
dispatch, mandatory taste pass before delivery, and at commitment
boundaries in between. Hard budget: 20 worker dispatches, 5 consults.

Adapted from [advisor-orchestrator-worker](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/agent_skills/advisor-orchestrator-worker)
(Shubham Saboo, Apache-2.0). The original shells out to the Gemini API
with jq/curl; this version uses native subagents, which provide the
same context isolation, parallelism, and per-role model pinning with
none of the shell plumbing.

## Why combine the two simpler patterns

- The orchestrator pattern (`../orchestrator/`) verifies worker outputs
  but nothing checks the orchestrator's own plan. Consult #1 fixes bad
  decompositions BEFORE a wave of workers runs on them — a few hundred
  advisor tokens against up to 20 wasted dispatches.
- The advisor pattern (`../advisor/`) has judgment but no fan-out.
- The main loop no longer needs the strongest model: Fable-grade
  judgment is injected at the two moments it matters, so the loop can
  run on Sonnet. Top-model judgment at boundary prices.
- Even with a strong orchestrator, the advisor is a fresh-context
  critic with no sunk cost in the plan — it catches commitment bias the
  planner cannot see in itself.
- Budgets and the PASS/FIX/ESCALATE ledger make cost and quality
  explicit instead of implicit.

Cost of combining: two mandatory consults + delegation overhead. For
small and medium tasks the simpler patterns win. Use this tier only for
large, decomposable, parallelizable work.

## Contents

```
advisor-orchestrator-worker/
├── claude-code/
│   ├── CLAUDE.md              the loop, boundaries, budgets
│   └── agents/
│       ├── worker.md          Sonnet stateless execution unit
│       └── advisor.md         Fable read-only critic
├── antigravity/
│   ├── AGENTS.md              the loop for Antigravity
│   └── rules/advisor-orchestrator-worker.md
├── references/
│   ├── worker-brief.md        stateless dispatch format
│   └── advisor-consult.md     consult format
└── examples/usage.md          worked example with ledger
```

## Installation — Claude Code

### Per project

```bash
cd your-project
mkdir -p .claude/agents
cp path/to/advisor-orchestrator-worker/claude-code/agents/*.md .claude/agents/
cat path/to/advisor-orchestrator-worker/claude-code/CLAUDE.md >> CLAUDE.md
cp -r path/to/advisor-orchestrator-worker/references .claude/   # brief/consult formats
```

### All projects (user-level)

```bash
mkdir -p ~/.claude/agents
cp path/to/advisor-orchestrator-worker/claude-code/agents/*.md ~/.claude/agents/
cat path/to/advisor-orchestrator-worker/claude-code/CLAUDE.md >> ~/.claude/CLAUDE.md
cp -r path/to/advisor-orchestrator-worker/references ~/.claude/
```

Note: the agent names `worker` and `advisor` collide with the simpler
patterns if installed side by side — these definitions supersede them
(they are compatible: same roles, tighter contracts). To share with
teammates, commit the per-project files to the repo.

### Run

```bash
claude --model sonnet   # the loop runs mid-tier; judgment is pinned per-agent
```

Workers are pinned to `model: sonnet` (drop to `haiku` for high-volume
research waves), the advisor to `model: fable` (use `opus` if Fable is
unavailable). Verify with `/agents`.

## Installation — Antigravity

### Per project

```bash
cd your-project
cp path/to/advisor-orchestrator-worker/antigravity/AGENTS.md .   # or append
mkdir -p .agents/rules
cp path/to/advisor-orchestrator-worker/antigravity/rules/*.md .agents/rules/
```

### All projects (user-level)

```bash
cat path/to/advisor-orchestrator-worker/antigravity/AGENTS.md >> ~/.gemini/GEMINI.md
```

Pick a mid-tier model for the main agent; AGENTS.md instructs it to
spawn cheap workers and a strongest-model advisor as child agents
(per-child model pinning depends on your Antigravity version).

## Usage

```
This is too big for one pass — run the three-tier loop.
Research all 8 candidates in parallel and synthesize a decision memo.
```

See `examples/usage.md` for the full walkthrough: frame → plan →
plan-review consult → parallel waves → verify (with one FIX redispatch)
→ synthesize → taste-pass consult → ledger.

## When to use which pattern

| Task shape | Pattern |
|---|---|
| Routine work, occasional hard calls | `../advisor/` |
| Parallelizable, planning quality dominates | `../orchestrator/` |
| Large + decomposable + high-stakes output | this one |
| Single-file edit, one-pass task | none — just execute |
