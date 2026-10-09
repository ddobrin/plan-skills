# Registering the plan-swarm gate outside the plugin (for platform teams)

The plan swarm's approval capture and gate run as the plan plugin's Antigravity hooks
(`hooks.json` at the plugin root):

| Event | Script | Job |
|---|---|---|
| `PreInvocation` | `lib/approve.py` | records approval phrases the user types in the top-level conversation, refreshes the heartbeat, and announces enforcement and `PLAN_LIB` once per conversation |
| `PreToolUse` | `lib/gate.py` | refuses unapproved commits, pushes, tags, protected-file writes, early engineer dispatches, and planted approval phrases; expands `$PLAN_LIB` |

If a developer disables the plugin, or turns its hook off (`"enabled": false`), nothing
is enforced in Antigravity: the supervisor detects this ("enforcement off": stale heartbeat,
or `$PLAN_LIB` left unexpanded) and refuses gated steps, and the git hooks plus the CI
ledger check still apply. To make the gate independent of the plugin toggle, install the
plugin's `lib/` folder at a fixed path (for example `/opt/plan-swarm/lib/`) and register
the same two hooks in a hooks file Antigravity always loads:

- **Global, per machine:** `~/.gemini/config/hooks.json`
- **Per workspace:** `.agents/hooks.json` at the repository root 

Hook commands run from the folder that holds the hooks file's customization root, so
use absolute paths:

```json
{
  "plan-swarm-managed": {
    "PreInvocation": [
      { "type": "command", "command": "python3 /opt/plan-swarm/lib/approve.py", "timeout": 20 }
    ],
    "PreToolUse": [
      {
        "matcher": "^(run_command|write_to_file|replace_file_content|multi_replace_file_content|notebook_edit|invoke_subagent|run_workflow|send_message)$",
        "hooks": [
          { "type": "command", "command": "python3 /opt/plan-swarm/lib/gate.py", "timeout": 20 }
        ]
      }
    ]
  }
}
```

Notes:
- Running these hooks next to the enabled plugin's own copy is safe: approvals are
  processed exactly once per user input, and the gate's checks give the same answer
  twice. It only costs a second Python start per gated tool call.
- `$PLAN_LIB` expands to the `lib/` folder of whichever `gate.py` runs, so the role
  prompts keep working.
- The hooks do nothing in repositories without `plans/swarm.md` (apart from expanding
  `$PLAN_LIB` and refusing planted approval phrases), so installing them fleet-wide does
  not affect other projects.
- The gate refuses agent writes to these hooks files, the plan plugin, and Antigravity's
  settings while a plan-swarm repository is active.
- Keep the installed copy in step with the plugin version your teams use
  (`python3 /opt/plan-swarm/lib/health.py --status` reports `plugin_version`).
- The approval hook reads the conversation transcript (`transcriptPath`) and refuses
  to record an approval when it cannot tell a top-level conversation from a subagent.
