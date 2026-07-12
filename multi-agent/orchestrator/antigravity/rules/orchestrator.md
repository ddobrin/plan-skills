# Rule: Orchestrate, don't execute

When a request involves more than one distinct subtask:

- The parent agent plans and delegates; it does not edit files itself.
- Spawn one child agent per independent subtask, in parallel where possible.
- Every child-agent prompt must include: goal, file paths, constraints,
  and required output format (what changed, files touched, decisions,
  blockers). Children have no access to the parent's conversation.
- Children stay within assigned scope; adjacent problems are reported,
  not fixed.
- The parent reviews all child results, resolves conflicts, and merges
  them into a single coherent outcome before responding.
