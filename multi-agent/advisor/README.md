# Advisor Pattern

A fast, cheap model (Sonnet) is the executor running the main loop —
reading, editing, testing. It calls a strong model (Claude Fable 5 /
Opus) as a read-only advisor only when it needs high-level judgment:
design forks, repeated failures, large or security-sensitive changes.
Most tokens bill at the executor rate; the advisor sees only distilled
questions.

Source: [ClaudeDevs on X](https://x.com/ClaudeDevs/status/2074606058128224365)

## Contents

```
advisor/
├── claude-code/
│   ├── CLAUDE.md              executor instructions + escalation rules
│   └── agents/
│       └── advisor.md         Fable/Opus read-only advisor subagent
├── antigravity/
│   ├── AGENTS.md              executor instructions
│   └── rules/advisor.md       workspace rule
└── examples/usage.md          worked example
```

## Installation — Claude Code

### Per project

```bash
cd your-project
mkdir -p .claude/agents
cp path/to/advisor/claude-code/agents/advisor.md .claude/agents/
cat path/to/advisor/claude-code/CLAUDE.md >> CLAUDE.md
```

### All projects (user-level)

```bash
mkdir -p ~/.claude/agents
cp path/to/advisor/claude-code/agents/advisor.md ~/.claude/agents/
cat path/to/advisor/claude-code/CLAUDE.md >> ~/.claude/CLAUDE.md
```

To share with teammates, commit the per-project `.claude/agents/` and
`CLAUDE.md` to the repo — everyone who clones it gets the pattern.

### Run

```bash
claude --model sonnet   # the cheap executor owns the main loop
```

The advisor is pinned to the strong model via `model: fable` in its
frontmatter (change to `opus` if Fable isn't available on your plan).
Verify with `/agents` inside Claude Code.

## Installation — Antigravity

Antigravity does not read `.claude/`; it uses `AGENTS.md` plus rules.

### Per project

```bash
cd your-project
cp path/to/advisor/antigravity/AGENTS.md .        # or append if one exists
mkdir -p .agents/rules
cp path/to/advisor/antigravity/rules/advisor.md .agents/rules/
```

### All projects (user-level)

```bash
cat path/to/advisor/antigravity/AGENTS.md >> ~/.gemini/GEMINI.md
```

### Model selection

Pick a fast/cheap model for the main agent in the model selector; the
AGENTS.md instructions tell it to spawn a strong-model child agent only
for hard decisions. (Per-child model pinning depends on your Antigravity
version — check the subagent settings.)

## Usage

See `examples/usage.md` for a full worked example. Short version: give
the executor a normal task. It works alone until it hits an escalation
trigger (design fork, 2 failed attempts, >5-file change, security), then
sends the advisor one distilled question — options + constraints — gets
one recommendation back, and implements it.

## When to use it

Good fit: day-to-day development where most work is routine and hard
calls are occasional; long sessions where executor-rate tokens dominate.
Poor fit: tasks that are one big hard decision (just use the strong
model directly), or highly parallelizable batch work.

## Related

The inverse is the Orchestrator pattern (`../orchestrator/`): the strong
model owns the loop and delegates execution to cheap workers. Use
Orchestrator when planning dominates and work parallelizes; use Advisor
when execution dominates and judgment is only occasionally needed. For
large, high-stakes decomposable tasks, both combine into the three-tier
`../advisor-orchestrator-worker/` pattern, which adds mandatory plan
review and a pre-delivery taste pass.
