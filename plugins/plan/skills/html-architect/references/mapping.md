# `plan.md` → `html-plan.html` — the html-architect mapping

> Read `assets/html-runtime/blocks.md` first; it is the block reference. This file says **which block each
> `plan.md` section becomes**, gives the exact fragment to copy for each, and lists the rules `pack.mjs --role arch`
> enforces. `references/exemplar.src.html` is a complete page built with these fragments — copy its shape.

## 0. The spine

A plan page is a **claim tree**: behaviour › rule › `file:line`. The reader opens a behaviour, sees the rules that
deliver it, taps a rule's call row and lands on the real code. Decisions sit on the claim they change. The last two
branches are always `aux="shared"` (what every group touches) and `aux="scope"` (what is not changing).

```
<header>  h1 · doc-changes · Why thread (doc-quote)
<main><doc-plan>
  doc-claim            level 1 — a behaviour the spec scenario asks for   (exhibit: mock / terminal / machine / code)
    doc-claim          level 2 — one rule, entrypoint or record, Task ID in bold   (exhibit: doc-calls or doc-schema)
      doc-ask          a fork that changes what gets built, recommendation checked
      div[data-if]     the consequence of the other answer
      doc-claim at=    level 3 — a path:line; doc-code src= (exists) or title="… · sketch" (new)
  doc-claim aux="shared"   group strip (.cols.groups) + shared schema
  doc-claim aux="scope"    not changing
</doc-plan></main>
```

## 1. Section → block (design §7.2, expanded)

| `plan.md` section | Page element | Fragment |
|---|---|---|
| **Objective** | `<h1>` — a title of 3–7 words naming the change and the place; no verb, no full stop | §2.1 |
| **Affected Files** | `<doc-changes new= changed= deleted=>` in the header — count files, omit zero attributes | §2.1 |
| the spec's request / research quotes | `<details class="thread">` of `<doc-quote via="prompt|doc|slack|github">` — quoted, not paraphrased | §2.1 |
| **Analysis & Context · Risks/Edge Cases** | a `<doc-ask>` when the risk is a fork the reviewer can decide; otherwise `<doc-note tone="risk">` under the claim it affects | §2.6 |
| **Task Execution (Parallel Groups)** | the group strip `<div class="cols groups">` under `aux="shared"`, one `.card` per group listing its Task IDs; every level-2/3 claim names its Task ID in bold | §2.7 |
| **Step-by-Step Implementation Details** | level-1 = the behaviour a group of tasks delivers (from the spec scenario); level-2 = one entrypoint / rule / record with `<doc-calls>` (`+ - ~ ?`, `@ path:line`) or `<doc-schema>`; level-3 = `at="path:line"` with `<doc-code src= lines=>` (existing code) or `<doc-code title="… · sketch">` (new code) | §2.2–2.4 |
| **Step 1 (The Unit Test Harness)** / Characterize-Behaviour steps | `<doc-code src=>` on the lines under test + `<doc-pin tone="warn">` naming the task step | §2.4 |
| `data-model.md` | `<doc-schema id= lang="sql|ts|proto" diff>` — editable; the reviewer's edit comes back as a unified diff | §2.5 |
| `api-contracts.md` | `<doc-calls>` entrypoints (`POST /api/…`) + a `<doc-schema lang="ts">` for request/response types | §2.3, §2.5 |
| **Global Testing Strategy / Success Criteria** | `<doc-note tone="ok">` on the level-1 claim each criterion proves | §2.6 |
| **Prerequisites / Key Dependencies** | one `<li>` each under `aux="shared"`, or a `<doc-tree>` if it is a layout | §2.7 |
| what is **not** changing (non-goals, untouched modules) | `<doc-claim aux="scope">` — required by `--role arch` | §2.8 |

## 2. Fragments

### 2.1 Header — `h1` + `doc-changes` + the Why thread

```html
<header>
  <h1>Response Stamp for html-* Pages</h1>                      <!-- Objective, as a 3–7 word title -->
  <doc-changes new="1" changed="2"></doc-changes>               <!-- Affected Files, counted; omit zeros -->
  <details class="thread"><summary>Why · 2 sources</summary>
    <doc-quote via="prompt" from="the user">add a stamp so I can file the response without guessing</doc-quote>
    <doc-quote via="doc" from="spec.md" where="Scenario 2">Given a packed page … Then the response names the page</doc-quote>
  </details>
</header>
```

`from=` is the bare name or handle; context goes in `where=`. Quote the spec's Gherkin, not your summary of it.

### 2.2 Level-1 — a behaviour claim

```html
<doc-claim id="names">
  <p>The response names the page and the code SHA it answers.</p>      <!-- falsifiable, ≤12 words -->
  <doc-mock frame="terminal" title="Respond → Copy" w="470"><template>…</template>
    <doc-pin ref="stamp" title="Two new lines">Task 1.A builds them; Task 2.A places them.</doc-pin>
  </doc-mock>
  <!-- level-2 claims follow -->
</doc-claim>
```

The exhibit is **what the user sees when the behaviour holds**: a `doc-mock` for UI, a `frame="terminal"` mock or a
`doc-code` for text output, a `doc-machine` for a lifecycle. Not a diagram of the code.

### 2.3 Level-2 — a rule claim with `doc-calls`

```html
<doc-claim>
  <p><b>Task 1.A</b> · <code>responseStamp()</code> reads the page name and the packed <code>sha=</code>.</p>
  <doc-calls title="The stamp" caption="Tap the first row to open the sketch. The dashed row hangs on decision 1.1.">
<script type="text/plain">
+ **responseStamp**()                        @ assets/html-runtime/html-runtime.js:559   -- goes after this divider
+   location.pathname                        @ assets/html-runtime/html-runtime.js:561   -- basename; '' when unsaved
~ buildResponse()                            @ assets/html-runtime/html-runtime.js:560
-   legacyTitleOnly()                        @ assets/html-runtime/html-runtime.js:562   -- no longer used
?   document.documentElement.dataset.sha     @ assets/html-runtime/pack.mjs:311          -- only if decision 1.1 says so
</script>
  </doc-calls>
</doc-claim>
```

- Column 0: `+` new call, `-` removed, `~` changed entrypoint, `?` proposed (dashed; the reviewer can strike it), space for context.
- `**bold**` = a **new symbol**. A `+` row without bold is a new call to something that exists.
- Every row ends `@ path:line`. For a new function in a file that exists, cite **the line it goes after**. The packer embeds ±6 real lines for every row whose file exists under `--root`, stamped with the checkout's SHA.
- A blank line starts a new entrypoint. Keep a tree under ~15 rows; split by entrypoint.

### 2.4 Level-3 — `at="path:line"`: existing code vs a sketch

```html
<!-- code that EXISTS: the packer fills it; you type nothing -->
<doc-claim at="assets/html-runtime/html-runtime.js:562">
  <p><b>html-runtime.js:562</b> · the title line</p>
  <doc-code src="assets/html-runtime/html-runtime.js" lines="560-575" hl="562">
    <doc-pin line="562" title="The stamp lines go right after this push">Nothing above it changes.</doc-pin>
  </doc-code>
</doc-claim>

<!-- code that DOES NOT EXIST yet: say "sketch" in the title; start= numbers the gutter from the line it goes after -->
<doc-claim at="assets/html-runtime/html-runtime.js:559">
  <p><b>html-runtime.js:559</b> · responseStamp()</p>
  <doc-code title="html-runtime.js · sketch" lang="js" start="559">
<script type="text/plain">
function responseStamp() {
  const page = decodeURIComponent(location.pathname.split('/').pop() || '');
  const sha = document.querySelector('[sha]')?.getAttribute('sha') || '';
  return { page, sha };
}
</script>
  </doc-code>
</doc-claim>

<!-- a Characterize-Behaviour step: the lines under test, with the warning pin -->
<doc-code src="assets/html-runtime/html-runtime.js" lines="539-557" hl="543">
  <doc-pin line="543" tone="warn" title="No test covers this today">Characterize it first — Task 2.A, step 1.</doc-pin>
</doc-code>
```

`at=` must equal a row's `@ path:line` exactly for the tap-through to work. `lines=` is 10–25 lines; over 40 warns.
`doc-pin line=` uses the number the gutter shows (the file's line, or `start=` + offset in a sketch).

### 2.5 `doc-schema` — a data shape the reviewer can edit

```html
<doc-schema id="scheduled" lang="sql" diff title="migrations/0042_scheduled_messages.sql" caption="Green is proposed. Red goes away.">
<script type="text/plain">
 CREATE TABLE scheduled_messages (
   id       uuid PRIMARY KEY,
-  state    text NOT NULL,
+  status   text NOT NULL CHECK (status IN ('scheduled','sent','failed')),
   send_at  timestamptz NOT NULL
 );
</script>
</doc-schema>
```

`lang` is required; `id` keeps edits across reloads; `diff` needs `+`, `-` or one leading space on every line. If
the shape exists, cite it with `src= lines=` instead of retyping it. An edit comes back under `## Edits` as a unified
diff — apply it to `data-model.md` **and** to the Task that creates the shape.

### 2.6 `doc-ask` — a decision with the recommendation checked, and its consequence

```html
<doc-ask id="sha-source">
  <p>Where does the SHA come from?</p>                                            <!-- ≤15 words -->
  <label><input type="radio" name="sha" value="first" checked> The first <code>sha=</code> the packer stamped on a block</label>
  <label><input type="radio" name="sha" value="html"> A <code>data-sha</code> on <code>&lt;html&gt;</code> <small>adds a pack.mjs task</small></label>
</doc-ask>
<div data-if="sha=html"><doc-note tone="warn"><strong>Then</strong> Task 1.C (pack.mjs:311) joins Group 1.</doc-note></div>
```

- `checked` is **your recommendation** — what you would build. Never leave a radio group without one.
- Put the ask **on the claim it changes**, after that claim's exhibit. Never stack two asks with nothing between.
- `data-if="name=value"` (`!=`, `~`, `&&`) shows the consequence of the other answer: which Task appears, which claim goes.
- Control names are unique across the page. Short options go side by side in `<div class="opts-row">`.
- A risk that is not a fork is a `<doc-note tone="risk">`, not an ask. A success criterion is a `<doc-note tone="ok">`.

### 2.7 `aux="shared"` — the group strip and what every group touches

```html
<doc-claim aux="shared">
  <p>Shared: two groups, one record that grows.</p>
  <div class="cols groups">
    <div class="card"><h4>Group 1 · parallel</h4><p><b>Task 1.A</b> responseStamp() · <code>html-runtime.js</code></p><p><b>Task 1.B</b> sha= check · <code>html-smoke.sh</code></p></div>
    <div class="card"><h4>Group 2 · after Group 1</h4><p><b>Task 2.A</b> stamp + count in buildResponse() · <code>html-runtime.js</code></p></div>
  </div>
  <doc-schema id="response" lang="ts" diff title="Response · html-runtime.js:605" caption="Green is new.">…</doc-schema>
</doc-claim>
```

One card per group from **Task Execution (Parallel Groups)**, in order, each listing its Task IDs and the file each
owns — the reviewer checks here that tasks in one group touch disjoint files. The strip is not an exhibit; the claim
still gets one (the shared schema, a `doc-tree` of new folders, or a `doc-flow` of the parts).

### 2.8 `aux="scope"` — what is not changing

```html
<doc-claim aux="scope">
  <p>Not changing: the sheet, the storage key, the title line, pack.mjs.</p>
  <ul>
    <li>The Respond sheet and its Copy button stay as they are.</li>
    <li><code>pack.mjs</code> is not touched unless decision 1.1 picks <code>data-sha</code>.</li>
  </ul>
</doc-claim>
```

Required by `--role arch`. Name the modules, calls and tables the plan leaves alone; it is what stops scope-creep comments.

## 3. Rules for the tree

1. **Split the top level by behaviour, not by file or by group.** A level-1 claim is what the spec scenario asks for ("The response names the page…"), never "Changes to html-runtime.js" or "Group 1".
2. **Every level-1 and level-2 claim is one falsifiable sentence, ≤12 words**, ending in a full stop. It can be true or false after the build. Not a heading, not a task name.
3. **One exhibit per claim.** A second exhibit means a second claim. Level-3 claims hold the code; level-2 claims hold the call tree or schema; level-1 claims hold what the user sees.
4. **≤5 children per claim, ≤3 levels, ≤5 top-level claims** plus `shared` and `scope`. Group or cut.
5. **2–5 decisions** (`doc-ask`). Ask only about forks that change what gets built; default the rest in prose. Zero asks is a hand-over sentence ("no fork worth a decision"), never a page with nothing to answer.
6. **Real over drawn.** Code that exists is cited (`src= lines=`, `@ path:line`) and pulled by the packer at a stated SHA. Code that does not exist is a `sketch`. Never type code that exists; never present a sketch as existing.
7. **Label Task IDs in bold inside the claim** (`<b>Task 1.A</b> · …`) on every level-2 and level-3 claim, and list them in the group strip. The reviewer must be able to go from a claim to the `plan.md` task and back.
8. **Every claim, ask and block traces to a line of `plan.md`** (or `spec.md`, `data-model.md`, `api-contracts.md`). A fork found while rendering is **appended to `plan.md` first** (Risks/Edge Cases or an `### Open Questions` subsection), then rendered as an ask.
9. **All block sources go in `<script type="text/plain">`** as the block's first child. Never write a `doc-*` tag in angle brackets inside an HTML comment — the packer scans comments too and will match it as a block.
10. `h1` is a title (3–7 words, no sentence punctuation); `<title>` equals it. The `.tldr` div, if used, is ≤40 words. Prose stays under ~350 words for the page and ~30 per block; the blocks are the document.

## 4. What `pack.mjs --role arch` enforces

From `assets/html-runtime/ORIGIN.md` (role lints), plus the general lints that bite plan pages most:

| Level | Check |
|---|---|
| **error** | no `<doc-plan>` — a plan page is a claim tree |
| **error** | no `<doc-claim aux="scope">` — end with what is not changing |
| **error** | a block whose source holds `<` outside `<script type="text/plain">`; an unknown `doc-*` element; a duplicate `id`; a `data-if` naming a control that does not exist; a `doc-pin line=` the gutter does not show; a `doc-ask` with no named control or a radio without `value`; `src=` not found under `--root`, or `lines=` past the end of the file |
| **error** | a file the packer **refuses**: outside `--root` and the page's folder, a secrets-looking file name, or text matching a secret pattern — the slice and the whole `src=` block are dropped. `pack.mjs` itself trips this (its secret regex holds the literal patterns); so would a fixture of fake keys. Cite such files by `title="… · sketch"` or in prose, and say so in the hand-over |
| **warning** | no `<doc-changes>` in the header; no `<doc-ask>` on the page; >5 top-level claims; >5 children; level 4; a claim over ~12–16 words or without a verb; two exhibits under one claim; a claim with nothing under it; a radio group with no `checked`; a question over ~15 words; two asks stacked; a `doc-calls` with no `+ − ~` row, no caption, or >2 changed rows without `@ path:line`; a `src=` slice over 40 lines without `collapsed`; three or more sketch lines over 90 chars; prose budgets (paragraph >40 words, sentence >25, page >350) |
| **info** | `doc-calls` rows whose `@ path` does not exist under `--root` — fine for files the plan **creates**; a **planning defect** (an ungrounded path) for files the plan claims exist. Check every one before hand-over |
| off | the ASD-STE100 vocabulary / contraction / tense / voice lints (`--role` implies `--no-ste`); the word and phone-width budgets stay |

Errors stop the write. Fix them. Warnings are reported in the hand-over line with the reason each was accepted.
