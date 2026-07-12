# Worker Brief Format

Every dispatch is one stateless subagent call containing this brief.
The worker has no conversation context, no memory, and no follow-ups.
Unlike bare-API workers, Claude Code subagents CAN read the repo — so
file paths are legal inputs, but goals, constraints, and acceptance
criteria must be spelled out in full. Never write "as discussed above."

```
You are a worker completing ONE subtask of a larger project. This brief
is everything you get. No follow-ups are possible.

SUBTASK: <one-line goal>
INPUTS: <file paths to read, data pasted inline, exact run commands>
CONSTRAINTS: <files you may touch; conventions to follow; hard limits>
ACCEPTANCE CRITERIA (output fails if any fail):
1. <checkable criterion>
2. <checkable criterion>
3. <checkable criterion>
OUTPUT FORMAT: <exact structure, length, style>
```

Redispatch rule: when a result comes back FIX, send a NEW brief that
quotes the failed criterion and names the specific failure. Never
"continue" the old worker; every dispatch is fresh.

Wave rule: workers in the same wave must be independent — disjoint
files, no reliance on each other's output. Anything dependent goes in
the next wave.
