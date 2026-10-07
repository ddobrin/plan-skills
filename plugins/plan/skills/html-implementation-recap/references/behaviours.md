# `html-implementation-recap` · what the reviewer can do on `html-recap.html`

Read this file when you write the hand-over (to describe the page) or when a `# Re:` block comes back (to route each section). Not needed to author the page.

| Behaviour | Block | Comes back as | What the supervisor does with it |
|---|---|---|---|
| Answer **commit-gate questions**: accept a deferred follow-up, agree with a severity downgrade, waive a `⚠️ Partial` step | `doc-ask kind="gate"`, auditor's position `checked` | `## Decisions` → question → **answer** (`_(kept as proposed)_` / `_(not opened; default kept)_`) | records the answers with the commit via the `review/` file path; **never** treats them as the approval phrase |
| Comment on a diff line | `doc-code diff file= start=` | `## Comments` → `file:line` + `> reader text` | hands to the `engineer` as a fix request (new audit round) |
| Tap a changed file → read its post-change body from disk, stamped `<sha>+wt` | `doc-code src= lines=` | — (trust) | — |
| Browse the changed-files tree with `+ ~ -` and per-file `+X/−Y` | `doc-tree` | comment on a row → `## Comments` | — |
| Compare before/after UI | `doc-shot` (before) / `doc-mock` (after), `data-ref` pins | comment on an element → `## Comments` | — |
| Comment on a verdict note, an evidence row, a finding | `doc-note`, table rows, list items | `## Comments` | routes to the `auditor` if it disputes evidence |
| Answers and comments persist across reloads; **Reset** clears | page (`localStorage`) | — | — |
| **Respond → Copy** one markdown block | sheet | the whole `# Re: html-recap …` block | saves it to `review/html-recap.response-N.md` first |
