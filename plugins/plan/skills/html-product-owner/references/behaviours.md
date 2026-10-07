# `html-product-owner` · what the reviewer can do on `html-spec.html`

Read this file when you write the hand-over (to describe the page) or when a `# Re:` block comes back (to route each section). Not needed to author the page.

| Behaviour | Block | Comes back as | What you do with it |
|---|---|---|---|
| Open/close claims; "N to answer" jumps to the next unopened decision | the tree | — (`_(not opened; default kept)_` per untouched decision) | read the flag as "never looked at", not as agreement |
| Answer a residual Grill-Loop question with your recommendation pre-checked | `doc-ask` | `## Decisions` → question → **answer** `value` ✎ (was: …) | apply as a spec tightening; remove from Open Questions |
| See what an answer removes or adds ("scenario 4 goes") | `data-if` under the `doc-ask` | implicit in the answer | — |
| Comment on a claim | the claim row | `## Comments` → **1.2 ‹claim›** + `> text` | rewrite the scenario |
| Comment on a Given/When/Then step | the step `<li>` in the 3-card strip | `## Comments` → the step text + `> text` | rewrite that step or the scenario |
| Comment on a mock element ("this button is wrong") | `doc-mock` + `data-ref` | `## Comments` → mockup › element + `> text` | update the UI/UX section and the mock |
| Click through a lifecycle and comment on a state | `doc-machine` state + its screen | `## Comments` → state "…" + `> text` | add or change a scenario for that state |
| Edit long copy (error text, email body, empty-state text) | `doc-draft` | `## Edits` → a unified diff | paste the new text into `spec.md` verbatim |
| Comment on a quote or a note | `doc-quote`, `doc-note` | `## Comments` | treat as feedback on the framing |
| Answers and comments persist across reloads; **Reset** clears | the page (`localStorage`) | — | — |
| **Respond → Copy** one markdown block | the sheet | the whole `# Re:` block | save under `review/` (see Response Handling in the SKILL) |
