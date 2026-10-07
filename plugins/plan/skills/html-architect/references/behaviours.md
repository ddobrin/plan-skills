# `html-architect` · what the reviewer can do on `html-plan.html`

Read this file when you write the hand-over (to describe the page) or when a `# Re:` block comes back (to route each section). Not needed to author the page.

| Behaviour | Where | Comes back as | What you do with it |
|---|---|---|---|
| Open / close claims; "N to answer" jumps to the next unopened decision | tree | — (a `_(not opened; default kept)_` flag per decision) | read the flag as "never looked at", not as agreement |
| **Answer a decision** (radio / checkbox / text / range / rank), your recommendation pre-checked | `doc-ask` | `## Decisions` → `[claim no] question → **answer** `value` ✎ (was: …)` | re-plan the affected Task(s) — Path B |
| Choose between forks that change what gets built (migration strategy, limit values, retry policy) | `doc-ask` on the claim it changes | `## Decisions` | re-plan the affected Task(s); update `Risks/Edge Cases` |
| **Strike a proposed call** (`+` / `?` rows) | `doc-calls` | `## Struck from the plan` → the row and `⇒ no longer touched: files` | remove the step / file from `plan.md`; the struck subtree goes with it |
| **Edit a schema** in the project's language | `doc-schema id= lang=sql/ts/proto` | `## Edits` → a unified diff | apply to `data-model.md` **and** the Task that creates it |
| Tap a call row → the real ±6 lines at that `path:line`, SHA-stamped | `doc-calls` + packer | — | — (trust) |
| **Comment** on a real line of existing code ("this throws"), a claim, a call row, a schema line, a mock element, a quote, a note | everywhere | `## Comments` → `- **3.2 <claim>**` + `> reader text` | add a characterization-test step or a risk; answer or address |
| Consequence preview (`data-if`) — what an answer removes or adds | under `doc-ask` | implicit in the answer | — |
| Read the group strip (which Tasks run in parallel) and comment | `.cols.groups` under `aux="shared"` | `## Comments` | regroup |
| Read **what is not changing** | `aux="scope"` | — | — (prevents scope-creep comments) |
| Answers and comments persist across reloads (`localStorage`); **Reset** clears | page | — | — |
| **Respond → Copy** one markdown block | sheet | the whole `# Re:` block | saved to a file first (see Response Handling in the SKILL) |
