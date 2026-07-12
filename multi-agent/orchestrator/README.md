# Orchestrator Pattern

A strong model (Claude Fable 5 / Opus) runs the main loop for planning,
delegation, review, and synthesis. All token-heavy execution — reading
files, editing code, running tests, research — is delegated to cheaper,
faster subagents (Sonnet). Most tokens bill at the worker rate; the
orchestrator's context stays small and focused on the plan.

Source: [ClaudeDevs on X](https://x.com/ClaudeDevs/status/2074606061567574181)

## Contents

```
orchestrator/
├── claude-code/
│   ├── CLAUDE.md              orchestrator instructions
│   └── agents/
│       ├── worker.md          Sonnet execution subagent
│       └── researcher.md      Sonnet read-only subagent
├── antigravity/
│   ├── AGENTS.md              orchestrator instructions
│   └── rules/orchestrator.md  workspace rule
└── examples/usage.md          worked example
```

## Installation — Claude Code

### Per project

```bash
cd your-project
mkdir -p .claude/agents
cp path/to/orchestrator/claude-code/agents/*.md .claude/agents/
cat path/to/orchestrator/claude-code/CLAUDE.md >> CLAUDE.md
```

### All projects (user-level)

```bash
mkdir -p ~/.claude/agents
cp path/to/orchestrator/claude-code/agents/*.md ~/.claude/agents/
cat path/to/orchestrator/claude-code/CLAUDE.md >> ~/.claude/CLAUDE.md
```

Note: user-level agents apply to every project for your OS user. To share
with teammates ("all users"), commit the per-project `.claude/agents/` and
`CLAUDE.md` to the repo instead — everyone who clones it gets the pattern.

### Run

```bash
claude --model claude-fable-5   # or opus — the orchestrator model
```

Subagent model is pinned to Sonnet via `model: sonnet` in each agent's
frontmatter, so only the main loop runs on the expensive model. Verify
with `/agents` inside Claude Code.

## Installation — Antigravity

Antigravity does not read `.claude/`; it uses `AGENTS.md` plus rules, and
has native child-agent spawning.

### Per project

```bash
cd your-project
cp path/to/orchestrator/antigravity/AGENTS.md .   # or append if one exists
mkdir -p .agents/rules
cp path/to/orchestrator/antigravity/rules/orchestrator.md .agents/rules/
```

### All projects (user-level)

Append the contents of `antigravity/AGENTS.md` to your global rules file:

```bash
cat path/to/orchestrator/antigravity/AGENTS.md >> ~/.gemini/GEMINI.md
```

### Model selection

In Antigravity, pick the strongest available model for the main agent in
the model selector; the AGENTS.md instructions tell it to farm execution
out to child agents. Child-agent progress appears as a task tree in the
Manager view. (Per-child model pinning depends on your Antigravity
version — check the subagent settings.)

## Usage

See `examples/usage.md` for a full worked example. Short version:

```
Migrate our API from Express 4 to Express 5 across routes/*.js.
Use workers in parallel where possible.
```

The orchestrator plans, spawns parallel workers (one per module), reviews
their summaries, resolves conflicts, and reports one coherent result.

## When to use it

Good fit: parallelizable batch work (multi-module refactors, migrations),
research-then-implement tasks, anything where execution reads far more
tokens than the decision requires. Poor fit: small single-file tasks —
delegation overhead exceeds the savings; and tightly coupled edits where
parallel workers would collide on the same files.

## Related

The inverse is the Advisor pattern (`../advisor/`): Sonnet executes the
main loop and calls a Fable/Opus subagent only for hard decisions. Use
Advisor when the work is mostly routine execution with occasional hard
calls; use Orchestrator when planning quality dominates and work
parallelizes. For large, high-stakes decomposable tasks, both combine
into the three-tier `../advisor-orchestrator-worker/` pattern, which
adds mandatory plan review and a pre-delivery taste pass.
