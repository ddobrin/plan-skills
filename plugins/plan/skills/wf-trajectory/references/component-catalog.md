# Component catalog

The template exposes these injection tokens (all replaced by `wf_render.py`):
`{{TITLE}}, {{STATUS}}, {{STATUS_CLASS}}, {{SUMMARY}}, {{TIMELINE}}, {{TREE}},
{{RESULT_JSON}}, {{TIMESTAMP}}`.

## Surfaces
- **Header** — title, status badge (`ok`/`fail`/`run`), stat cells (duration,
  agents, tokens, tool calls, model), theme toggle.
- **Timeline** (`.timeline` / `.trow` / `.track` / `.seg`) — one row per agent;
  a faint `.seg.queued` segment then a solid `.seg.active` bar, positioned by
  percentage. Overlapping active bars show parallelism.
- **Execution tree** (`details.phase` > `details.agent`) — collapsible; each
  agent shows model/duration/tokens/tool-calls/state, expands to prompt & result
  previews and a `file://` transcript link.
- **Result** — collapsed pretty-printed workflow return value.

## Theming
Light/dark via `data-theme` on `<body>`, persisted under the shared `va-theme`
localStorage key. Fully offline: no CDN, no external assets.

## Invariants (verified by tests)
- `<meta charset>` within first 1024 bytes.
- One `.agent` node and one `.trow` per agent.
- No unresolved `{{TOKEN}}` remains.
- All injected strings HTML-escaped.
