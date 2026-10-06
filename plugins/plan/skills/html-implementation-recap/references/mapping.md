# Evidence → page mapping for `html-recap.html`

> Read with `assets/html-runtime/blocks.md` (block syntax) and `exemplar.src.html` (a page that passes `pack --role recap --lint-only`). This file says **which evidence becomes which block**, with the exact commands and HTML fragments. Design source: `plans/html-plan-feasibility-v2.md` §7.3.

| Evidence | Page element | Required by `--role recap` |
|---|---|---|
| `git diff --stat HEAD` + `git status --short` | `doc-changes new= changed= deleted=` in the `<header>` | **error** when missing |
| outcome brief (spec/plan) | `<h1>` + one `doc-quote` of the original request | — |
| `plan.md` checklist × audit | `<h2>Tasks</h2>`: table Task · ✅/⚠️/❌ · files | — |
| `git status` / `--stat` | `<h2>Files</h2>`: `doc-tree` with `+ ~ -`, per-file `+X/−Y` in the comment column | — |
| key hunks of `git diff HEAD` | `<h2>Changes</h2>`: 3–8 `doc-code diff file= start=` blocks | warning when missing |
| post-change code worth reading whole | `doc-code src= lines=` (packer fills; stamped `<sha>` / `<sha>+wt`) | — |
| audit verdict, evidence, anti-shortcut scan, findings | `<h2>Verification</h2>`: `doc-note tone=ok\|risk`, evidence table, findings list | **error** when missing |
| deferred items, downgrades, partials | `<h2>Gate</h2>`: `doc-ask kind="gate"` with the auditor's stance checked | — |
| before/after UI | `doc-shot` (before) / `doc-mock` (after) | — |
| decisions, excluded files, inferences | `<h2>Notes</h2>`: short `<ul>` or `doc-note` | — |

The page is **section-based**. Do not wrap it in `doc-plan` — a recap is retrospective; `--role recap` warns on a `doc-plan`.

---

## 0. The commands (run all of them first, keep the output)

```bash
REPO=$(git rev-parse --show-toplevel)
MS=plans/active_milestones/{moniker}

git -C "$REPO" status --short                          # ?? new · M modified · D deleted · A added
git -C "$REPO" add -N <new paths>                      # intent-to-add so untracked files appear in the stat …
git -C "$REPO" diff --stat HEAD                        # … per-file "| 334 +++" and the summary line
git -C "$REPO" diff HEAD                               # the hunks; keep the "@@ -a,b +c,d @@" headers
git -C "$REPO" reset -q <new paths>                    # undo the intent-to-add; the tree is as you found it
git -C "$REPO" rev-parse --short HEAD                  # the sha the packer will stamp

sed -n '12,38p' path/to/file                           # verify every lines="a-b" before you cite it
```

Also read: `$MS/plan.md` (checklist, `[x]`, `(Status: …)`), the audit (`plans/audit/AUDIT_*.md` or `$MS/audit.md`, latest round), optionally `$MS/spec.md`.

If the group was committed on a worktree branch, replace `HEAD` with `<base>..HEAD` throughout; the packer still stamps the current checkout.

---

## 1. Header: `doc-changes` from the stat

`git diff --stat` ends with `N files changed, I insertions(+), D deletions(-)`. `doc-changes` wants **file counts by kind**, not line counts:

| From `git status --short` | Count as |
|---|---|
| `??` (untracked, in scope) and `A` | `new` |
| `M`, `MM`, `R` (renamed → count once as `changed`) | `changed` |
| `D` | `deleted` |

```html
<header>
  <h1>Runtime Adopted into the Plan Plugin</h1>
  <doc-changes new="8" changed="1"></doc-changes>                 <!-- omit an attribute that is 0 -->
  <details class="thread"><summary>Why · 1 request</summary>
    <doc-quote via="prompt" from="the user">…the request, quoted, trimmed with …</doc-quote>
  </details>
</header>
```

Line totals (`+3102 −0`) go to the Outcome metric cards, not here.

---

## 2. Outcome: cards

```html
<h2>Outcome</h2>
<p>One to three sentences: what the milestone delivers, in the spec's words.</p>
<div class="cols">
  <div class="card"><h4>9 files</h4><p>8 new · 1 changed</p></div>
  <div class="card"><h4>+3102 / −0</h4><p>lines, from <code>git diff --stat</code></p></div>
  <div class="card"><h4>Tasks 5 / 6</h4><p>one ⚠️ Partial</p></div>
  <div class="card"><h4>Audit PASS</h4><p>round 2 · 2026-10-06</p></div>
</div>
```

The fourth card says `PASS`, `FAIL`, or `not yet run` — exactly what the audit file says.

---

## 3. Tasks: table from `plan.md` × audit

| `plan.md` says | audit says | Status cell |
|---|---|---|
| `[x]` | step verified | ✅ Done |
| `[x]` | step partial / finding open | ⚠️ Partial |
| `[ ]` or `(Status: deferred)` | — | ⚠️ Partial (deferred → also a gate ask) |
| any | step failed | ❌ Failed |

```html
<h2>Tasks</h2>
<table>
  <thead><tr><th>Task</th><th>Status</th><th>Files</th></tr></thead>
  <tbody>
    <tr><td><b>1.1</b> Rename the runtime</td><td>✅ Done</td><td><code>assets/html-runtime/html-runtime.js</code>, <code>…css</code></td></tr>
    <tr><td><b>1.4</b> Smoke script</td><td>⚠️ Partial</td><td><code>scripts/html-smoke.sh</code> — see Gate 1</td></tr>
  </tbody>
</table>
```

Table cells are not counted against the prose budget; put detail here rather than in paragraphs.

---

## 4. Files: `doc-tree` from the stat

One path per line, directories end with `/`, two spaces per level. The mark is the status; the `# comment` is the per-file stat (≤ 60 chars — the packer warns above that).

```html
<h2>Files</h2>
<doc-tree caption="Marks: + new · ~ changed · − deleted. Comments are +added/−removed lines.">
<script type="text/plain">
plugins/plan/
  agents/
    ~ supervisor/agent.md        # +27/−0 · review-response routing
  assets/
    + html-runtime/              # all new
      + html-runtime.js          # +1299
      + html-runtime.css         # +576
      + pack.mjs                 # +334
  scripts/
    + html-smoke.sh              # +81
</script>
</doc-tree>
```

A `-` row for a deleted file keeps its path so the reviewer can comment on it. Fold an unchanged directory into one `+ dir/  # all new` row when every file under it is new.

---

## 5. Changes: `doc-code diff` from a hunk

**One file per block.** Paste the hunk lines **verbatim** from `git diff HEAD`, inside `<script type="text/plain">`.

### 5a. A modified file — keep the real `@@` header

```html
<doc-code diff file="agents/supervisor/agent.md" caption="Hunk 1 of 1." wrap>
<script type="text/plain">
@@ -110,6 +110,33 @@
   Please review `plans/active_milestones/{moniker}/spec.md` and `plan.md`. Type
   'approve' to proceed to execution."
 
+**Review responses from `html-*` pages.** When an `html-*` role …
+…
 ### PHASE 4: CONSTRUCTION LOOP (Engineer ⇄ Auditor → Git)
</script>
  <doc-pin line="113" tone="info" title="Reads as the only supervisor change">Routing only; no gate logic moved.</doc-pin>
</doc-code>
```

The packer **counts** the lines after each `@@ -a,b +c,d @@`: context lines count on both sides, `+` on the new side, `-` on the old. More lines than the header says → **error**. Fewer → warning ("fine if you only cut the tail"). Drop the text after the second `@@` (the function context) or leave it with a leading space — the packer warns when text is jammed against the `@@`.

### 5b. Cutting a hunk honestly

- You may **cut the tail** of a hunk. Say so: `caption="Showing the first 24 of 61 lines of this hunk."`
- You may **never** remove leading or middle lines, and never write a `…` or `...` line inside a hunk — the packer **errors** ("the gutter can't know how many lines you cut; split into two hunks").
- To show two parts of one long hunk, write **two `@@` headers** in one block, each with the correct `+c,d` for its own lines.

### 5c. A new file — a `+`-only slice with `start=`

A new file's real hunk is `@@ -0,0 +1,N @@` for the whole file. Showing all of it is rarely useful, so slice it: every line starts with `+`, and `start="N"` numbers the gutter from the file line where the slice begins. With `start=` and no `@@` header, the packer does no count check — so the honesty burden is yours: the slice must be contiguous and `start` must be the real first line number.

```html
<doc-code diff file="assets/html-runtime/pack.mjs" start="24" caption="Lines 24–26 of a 334-line new file." wrap>
<script type="text/plain">
+const ROLES = ['po', 'arch', 'recap']; const role = opt('--role', '');
+if (role && !ROLES.includes(role)) { console.error(`--role must be one of ${ROLES.join(', ')}`); process.exit(2); }
+const noSte = argv.includes('--no-ste') || !!role;
</script>
  <doc-pin line="26" tone="info" title="--role implies --no-ste">Budgets stay; vocabulary lints go.</doc-pin>
</doc-code>
```

### 5d. Pins

- `doc-pin line="N"` uses the **new-side** gutter number; `old="N"` pins a removed line. A pin on a number the gutter does not show is an **error**.
- `tone="info|warn|risk|ok"`. A pin is a clause, ≤ 20 words. It is **your inference** about the line — phrase it so ("reads as…", "looks like…"), never as a fact lifted from the diff.
- Add `wrap` when the source has lines over 90 characters (the packer warns at 3 or more); never reflow the lines themselves.
- The packer warns above ~40 lines without `collapsed`, and above 120. Prefer the 10–25 lines that carry the point.

### 5e. What you redact before pasting

The packer scans only what **it** reads (`src=` slices, call excerpts). A hunk you paste is scanned by nobody but you. Mask keys, tokens, passwords, connection strings: `+const key = 'sk-••••'` and say `caption="One literal masked."`. Never paste from a file the packer refused as a `src=` (it printed "looks like it holds a secret").

---

## 6. Post-change code: `doc-code src= lines=`

For a function or block the reviewer should read **as it now is**, cite it; the packer pulls the text from `--root` at pack time and stamps it:

```html
<doc-code src="scripts/html-smoke.sh" lines="70-74" caption="The agent/skill body parity check, as it now stands.">
  <doc-pin line="71" tone="info" title="Body = everything after the second ---">Frontmatter may differ.</doc-pin>
</doc-code>
```

- `lines="a-b"` — verify with `sed -n 'a,bp' path` first; `b` past the end of the file is an **error** ("is --root at the commit you're citing?").
- Paths are **relative to `--root`**. With `--root <repo>` write `plugins/plan/scripts/html-smoke.sh`; the exemplar uses `--root plugins/plan` so its paths start at `assets/` and `scripts/`.
- The stamp: the packer writes `sha="<short sha>"` of the root checkout. **`+wt`** means the file on disk differs from `HEAD:` — the normal case for a recap before the commit (the engineer has not committed), and for a new untracked file. A stamp **without** `+wt` on a recap page means the file is already committed — say which commit in Notes.
- The packer refuses a file whose **whole text** matches a secret pattern, not just the slice. If that happens, the file cannot be `src=`-cited at all; show the lines as a diff block instead (after your own redaction) and say why in Notes.
- The packer's last line lists every file whose text is now inside the page. Copy it into the hand-over.

---

## 7. Verification: verdict, evidence, scan, findings

```html
<h2>Verification</h2>
<doc-note tone="ok"><strong>Audit PASS</strong> Round 2, 2026-10-06, <code>plans/audit/AUDIT_runtime.md</code>. All six steps verified; one finding downgraded (Gate 2).</doc-note>
<!-- tone="risk" for FAIL, or when the audit is not yet run: -->
<!-- <doc-note tone="risk"><strong>Audit not yet run</strong> This page recaps the diff only; the Verification evidence below is what the recap could check itself.</doc-note> -->

<h3>Evidence</h3>
<table>
  <thead><tr><th>Step</th><th>Evidence</th><th>Result</th></tr></thead>
  <tbody>
    <tr><td>1.2 pack --role lints</td><td><code>assets/html-runtime/pack.mjs:289-295</code></td><td>✅ verified</td></tr>
  </tbody>
</table>

<h3>Anti-shortcut scan</h3>
<ul>
  <li>TODO / FIXME / placeholder: none in the diff</li>
  <li>Skipped or gutted tests: none; the smoke script adds 14 checks</li>
</ul>

<h3>Findings</h3>
<ul>
  <li><b>F1</b> <code>SECRET_TEXT</code> in <code>pack.mjs</code> was one literal regex, so the file matched its own pattern and could not be cited with <code>src=</code>. Closed in this change: the pattern is now built from pieces. implementation-validator: <s>Medium</s> → Low — see Gate 2.</li>
</ul>
```

Use the audit's own words for the verdict and the step results; a step result the audit did not state is not on this page.

---

## 8. Gate: `doc-ask kind="gate"`

One ask per deferral, downgrade, or partial. The auditor's stance is `checked`. Put a sentence between consecutive asks (the packer warns on stacked asks). `id` and `name` are unique on the page; the question is ≤ 15 words.

```html
<h2>Gate</h2>
<p>Each question records the reviewer's position for the commit notes. It is not the approval phrase.</p>

<doc-ask id="g1" kind="gate">
  <p>Defer the per-role smoke sub-commands to the next milestone?</p>
  <label><input type="radio" name="g1" value="defer" checked> Yes, defer <small>the auditor's stance</small></label>
  <label><input type="radio" name="g1" value="now"> No, add them before the commit</label>
</doc-ask>
<div data-if="g1=now"><doc-note tone="warn">Then Task 1.4 reopens and the engineer runs again.</doc-note></div>

<p>The second question concerns the one finding the validators downgraded.</p>
<doc-ask id="g2" kind="gate">
  <p>Agree that finding F1 is Low, not Medium?</p>
  <label><input type="radio" name="g2" value="low" checked> Yes, Low <small>the auditor's stance</small></label>
  <label><input type="radio" name="g2" value="medium"> No, keep Medium and fix now</label>
  <textarea name="g2_why" placeholder="Why (optional)"></textarea>
</doc-ask>
```

What comes back (`## Decisions` in the Respond block) is recorded in `review/html-recap.response-N.md` and cited by the supervisor in the commit notes. It is never pasted into the commit message and never read as approval.

---

## 9. UI (optional) and Notes

```html
<h2>UI</h2>
<p>No user-facing UI in this milestone; the CLI output is below.</p>
<doc-mock frame="terminal" title="html-smoke.sh" w="470"><template><span class="dim">$</span> plugins/plan/scripts/html-smoke.sh --lint-only
<span class="g">✓</span> node v22.14.0
<span class="g">✓</span> example packs with --role arch</template></doc-mock>

<h2>Notes</h2>
<ul>
  <li><b>Excluded from this recap:</b> <code>plans/*.md</code> design drafts — dirty, not part of the milestone.</li>
  <li><b>Inference:</b> the tone pins in Changes are the recap's reading of the lines, not audit findings.</li>
</ul>
```

Terminal mocks show **real** output you captured, trimmed. Notes are static text baked in at generation time.

---

## 10. Pack and its lints

```bash
node "$RT/pack.mjs" "$MS/html-recap.src.html" --root "$REPO" --role recap -o "$MS/html-recap.html"
node "$RT/pack.mjs" "$MS/html-recap.src.html" --root "$REPO" --role recap --lint-only   # re-check after an edit
```

`--role recap` applies (and implies `--no-ste`, so the budgets stay and the vocabulary/voice/tense lints go):

| Check | Level |
|---|---|
| no `<doc-changes>` in the header | **error** |
| no `<h2>Verification</h2>` | **error** |
| no `<h2>Changes</h2>` (or `Diff`) | warning |
| no `<doc-code diff>` block | warning |
| a `<doc-plan>` on the page | warning |

Always on, whatever the role:

| Check | Level |
|---|---|
| `…` / `...` line inside a diff hunk | **error** |
| hunk has more lines than its `@@` header says | **error** (fewer: warning) |
| `doc-pin line=` on a number the gutter does not show | **error** |
| `src=` not found under `--root`, or `lines=` past the file's end | **error** |
| `src=` file (whole text) or slice matches a secret pattern | **error** — nothing from that file is embedded |
| secret-looking **file name** (`credentials*`, `secrets*`, `id_rsa*`, `*_history`, `*.local.json`) | **error** |
| radio group without `checked`; duplicate control names; `data-if` naming no control | warning / error / error |
| diff block without `@@` header or `start=` | warning (gutter unnumbered) |
| ≥ 3 pasted lines over 90 chars without `wrap` | warning |
| block over ~40 lines without `collapsed`; over 120 | warning |
| tree comment over 60 chars | warning |
| prose over 350 words, paragraph over 40 words, sentence over 25 words | warning |

The packer's final lines: `✓ …html-recap.html  N KB · 2 asset(s) inlined` and `code from K files is now inside the page: …` — the second one goes into the hand-over verbatim.

**Offline check:** `grep -E '<(script|link)[^>]+(src|href)="https?://' "$MS/html-recap.html"` must print nothing.
