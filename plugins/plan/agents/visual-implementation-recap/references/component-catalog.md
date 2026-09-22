# Visual Recap — Component Catalog

Copy-paste recipes for the nine recap surfaces. Every class used here is already
defined in `assets/template.html`, so fragments render with zero extra CSS.

## How to fill the template

1. Copy `assets/template.html` → `plans/active_milestones/{moniker}/visual-recap.html`.
2. Replace `{{MONIKER}}` and `{{TIMESTAMP}}` in the header band.
3. For each section, **replace everything between the paired markers** with your content:
   `<!-- VIR:OVERVIEW -->` … `<!-- /VIR:OVERVIEW -->`, `<!-- VIR:TASKS -->` … etc.
   The shipped demo content between the markers is a working example — delete it.
4. Leave the `<head>`, `<style>`, `<nav>`, and the bottom `<script>` untouched.
5. Omit a surface only when it does not apply (see "Gating" at the bottom). If you
   omit one, leave a one-line note in that section saying why ("No UI in this milestone").

Markers, in document order: `OVERVIEW · TASKS · FILES · CHANGES · ARCH · CONTRACTS ·
UI · VERIFY · NOTES`.

## Three rules that make a recap trustworthy

- **Grounded — true by construction.** Every diff line, file path, line count, task
  status, and finding comes from the actual `git diff` / `plan.md` / audit report. Never
  invent code or numbers. "What this means" annotations are fine but mark them as inference.
- **Redact secrets.** The recap shows *real* changed lines. Strip or mask API keys, tokens,
  passwords, and credential-like literals before rendering (`sk-••••`). When in doubt, mask.
- **No silent truncation.** If you clip a long diff to fit the budget, say so
  (`showing 2 of 5 hunks`). A partial diff must never read as complete.

---

## 1. Overview

Lead with metric cards (the headline numbers), then a 1–3-sentence outcome brief and a
small key/value card. Source the numbers from `git diff --stat` and the audit summary.

```html
<div class="metrics">
  <div class="metric"><div class="num">4</div><div class="lbl">Files changed</div></div>
  <div class="metric add"><div class="num">+96</div><div class="lbl">Insertions</div></div>
  <div class="metric del"><div class="num">−12</div><div class="lbl">Deletions</div></div>
  <div class="metric pass"><div class="num">PASS</div><div class="lbl">Audit · 5/5 steps</div></div>
</div>
<div class="grid cols-2">
  <div class="card">
    <dl class="kv">
      <dt>Outcome</dt><dd>Expired JWTs rotate transparently; tampered tokens get 401.</dd>
      <dt>Tasks</dt><dd>5 of 5 complete across 2 groups.</dd>
      <dt>Tests</dt><dd>7 added · all green.</dd>
      <dt>Audit</dt><dd>PASS — no shortcuts found.</dd>
    </dl>
  </div>
  <div class="card">
    <strong>What shipped</strong>
    <p>One concrete sentence of user-facing outcome — the thing a reviewer should remember.</p>
  </div>
</div>
```

Metric variants: `.metric.add` (green number), `.metric.del` (red), `.metric.pass`
(green), `.metric.fail` (red). Use `.fail` and a `FAIL` value when the audit failed —
the Overview must reflect reality.

---

## 2. Tasks Completed

The plan's checklist, as implemented. One `<li>` per task with a leading status chip
mapped to the **audit's** verdict (not just the engineer's `[x]`). Put the task name in
`.tk` and the files it touched in `.ref`.

Status chips: `pass` (Done/green), `partial` (⚠️ amber), `fail` (❌ red).

```html
<ul class="tasks">
  <li><span class="st pass">Done</span><span class="tk">Task 1.B — add <code>refresh()</code> rotation logic <span class="ref">src/auth/refresh.ts</span></span></li>
  <li><span class="st partial">Partial</span><span class="tk">Task 1.C — retry-on-401 (happy path only; timeout path missing) <span class="ref">src/auth/login.ts</span></span></li>
  <li><span class="st fail">Failed</span><span class="tk">Task 2.A — migration not applied <span class="ref">db/migrations/0007.sql</span></span></li>
</ul>
```

Keep the task names verbatim from `plan.md` so the recap lines up 1:1 with the plan.

---

## 3. Changed Files

Nested `<ul class="filetree">`. Folders use `<span class="dir">` (click to collapse).
Tag each file with a change badge and a per-file diffstat. Source from `git status` +
`git diff --stat`.

Badges: `<span class="badge new">new</span>` · `<span class="badge mod">modified</span>` ·
`<span class="badge del">deleted</span>`. Diffstat: `<span class="stat">` with
`.add` (+N) and `.del` (−N) children.

```html
<ul class="filetree">
  <li><span class="dir">src/auth/</span>
    <ul>
      <li>refresh.ts <span class="badge new">new</span> <span class="stat"><span class="add">+38</span> <span class="del">−0</span></span></li>
      <li>login.ts <span class="badge mod">modified</span> <span class="stat"><span class="add">+12</span> <span class="del">−4</span></span></li>
    </ul>
  </li>
  <li>src/legacy/token.ts <span class="badge del">deleted</span> <span class="stat"><span class="del">−8</span></span></li>
</ul>
```

---

## 4. Key Changes — the centerpiece

The 3–8 changes that carry the most meaning, each as an annotated diff card. **Lines come
verbatim from `git diff`** — only redact secrets and clip with a stated note.

Each line is a `<span class="ln …">` inside `<pre class="diff">`. Line classes:
`add` (green), `del` (red), `hunk` (the `@@ … @@` header), `meta` (file-mode / index
lines), `ctx` (unchanged context). The leading `+` / `-` / ` ` is part of the text.

> **Escaping:** inside `<pre class="diff">`, write a literal `<` as `&lt;` and `&` as
> `&amp;` (e.g. generics like `Map&lt;K,V&gt;`), or the browser will mis-parse the line.

With an annotation rail (wrap the diff and notes in `.annotated.has-notes`):

```html
<div class="card">
  <div class="diff-head"><span class="path">src/auth/refresh.ts</span> <span class="badge new">new</span> <span class="stat"><span class="add">+38</span> <span class="del">−0</span></span></div>
  <div class="annotated has-notes">
    <div>
      <pre class="diff"><span class="ln meta">new file mode 100644</span>
<span class="ln hunk">@@ -0,0 +1,5 @@</span>
<span class="ln add">+export async function refresh(token: string) {</span>
<span class="ln add">+  const claims = verify(token);</span>
<span class="ln add">+  if (claims.exp >= now()) return token;</span>
<span class="ln add">+  return issue(claims.sub);</span>
<span class="ln add">+}</span></pre>
    </div>
    <ol class="ann-notes">
      <li><span class="ann-num">1</span><div><code>verify</code> rejects tampered tokens first. <em>(inference)</em></div></li>
      <li><span class="ann-num">2</span><div>Rotation only when expired.</div></li>
    </ol>
  </div>
</div>
```

Without the rail (full-width diff), drop the `.annotated` wrapper and put `<pre class="diff">`
directly in the card. When clipped, add a note:

```html
<p class="clip">Showing the salient hunk of 2 in this file.</p>
```

Budgets: 3–8 cards total; prefer ≤ ~150 diff lines per card. Pick the hunks that change
behavior, not boilerplate.

---

## 5. Architecture

Structure as it now stands (post-change). Use `flowchart` for data flow,
`sequenceDiagram` for ordered interactions. **Mandatory:** every `<pre class="mermaid">`
keeps an adjacent raw-source `<details class="src">` with the SAME text, so the diagram
survives offline / render failure.

```html
<figure>
  <pre class="mermaid">
flowchart LR
  C[Client] -->|401| R[refresh]
  R --> V{valid?}
  V -- yes --> I[issue + retry]
  V -- no --> X[401 · re-login]
  </pre>
  <figcaption>Refresh path as implemented.</figcaption>
  <details class="src"><summary>Mermaid source</summary><pre>flowchart LR
  C[Client] -->|401| R[refresh]
  R --> V{valid?}
  V -- yes --> I[issue + retry]
  V -- no --> X[401 · re-login]</pre></details>
</figure>
```

Keep node labels short. `securityLevel:'strict'` is already set — do not put raw HTML in labels.
Include this surface only when the change actually shifted structure; otherwise omit it.

---

## 6. API & Schema

Contract and data-model changes, with what changed **flagged**. Endpoint cards reuse
`.card.endpoint` + `.method` badges (`get post put patch delete`); flag a new/changed
operation or field with a `.badge`. Data-model changes use an `erDiagram` (same
raw-source fallback rule as Architecture).

```html
<div class="card endpoint">
  <div class="ep-head"><span class="method post">POST</span><span class="path">/auth/refresh</span> <span class="badge new">new</span></div>
  <p>Exchange a valid (possibly expired) token for a fresh one.</p>
  <table class="api">
    <thead><tr><th>Field</th><th>Type</th><th>Req</th><th>Notes</th></tr></thead>
    <tbody>
      <tr><td>token</td><td>string</td><td><span class="req-tag">required</span></td><td>Current JWT</td></tr>
    </tbody>
  </table>
</div>
```

For a schema change, note the delta in the figcaption (e.g. "SESSION gained
`rotated_at`"). Include this surface only when contracts or the data model changed.

---

## 7. UI Changes

Before / after of any user-facing surface, as lo-fi wireframes — **HTML/CSS only, no
images**. Put the two frames in a `.grid.cols-2` so they sit side by side. Building
blocks: `.device-frame`, `.wire`, `.wire-bar`, `.wire-input`, `.wire-btn`,
`.wire-placeholder`.

```html
<div class="grid cols-2">
  <div class="device-frame">
    <div class="caption">Before — token expires</div>
    <div class="wire">
      <div class="wire-bar">Session expired</div>
      <button class="wire-btn">Log in again</button>
    </div>
  </div>
  <div class="device-frame">
    <div class="caption">After — silent refresh</div>
    <div class="wire">
      <div class="wire-bar">Welcome back · no interruption</div>
      <div class="wire-placeholder"></div>
    </div>
  </div>
</div>
```

For a multi-step interaction you may use the prototype pattern (screens as
`<section class="screen" id="screen-…">`, one without `hidden`, buttons with
`data-goto="screen-…"`; the chrome handles show/hide + breadcrumb). Most recaps only
need the static before/after. Omit this surface for backend/data-only work, with a
one-line note.

---

## 8. Verification

The audit's verdict and its evidence — straight from `plans/audit/AUDIT_[Plan_Name].md`.
Lead with the verdict banner, then per-step evidence, the anti-shortcut scan, the test
results, and any findings.

Verdict banner — `.verdict.pass` (green) or `.verdict.fail` (red):

```html
<div class="verdict pass">
  <span class="tag">PASS</span>
  <div>
    <strong>5 / 5 steps verified</strong>
    <div class="detail">Build green · 7/7 tests pass · no placeholders or skipped tests.</div>
  </div>
</div>
```

Per-step evidence reuses `ul.tasks` with the `Verified` chip and `file:lines` refs.
Anti-shortcut scan is a short paragraph. Tests use a `table.api`. Findings (including
`implementation-validator` severity calibrations) reuse the collapsible
`details.oq.severity-*` pattern with a `.chip`:

```html
<p class="oq-summary">1 confirmed · 0 blocking · 1 follow-up</p>
<details class="oq severity-low">
  <summary><span class="chip low">LOW</span> Clock skew on <code>exp</code> under load</summary>
  <div class="body">Confirmed real but <strong>downgraded</strong> — gated on same-ms concurrent
  refresh. Tracked as follow-up, not a blocker.</div>
</details>
```

If the audit failed, use `.verdict.fail` / a `FAIL` banner and list the failing steps as
`details.oq.severity-high`. Never soften a FAIL into a PASS.

---

## 9. Notes

**Static author callouts baked in at generation time — NOT a live, persisted, multi-user
comment system.** Anything a reviewer types in the browser is not saved (the section lede
in the template already says so). Use inline anchors + a numbered list with back-links.

Inline anchor (place near the thing being discussed, in any section):
```html
deleted with no remaining importers<sup class="cmt-anchor">[1]</sup>
```

Notes list (in the NOTES section):
```html
<ol class="comments">
  <li id="cmt-1">Deleted legacy <code>token.ts</code> — nothing imported it (grep-verified).
     <span class="back"><a href="#files">↑ Changed Files</a></span></li>
  <li id="cmt-2">Clock-skew item deferred to a tracked ticket — surfaced, not dropped.
     <span class="back"><a href="#verify">↑ Verification</a></span></li>
</ol>
```

Back-link hrefs are tab ids: `#overview #tasks #files #changes #arch #contracts #ui
#verify #notes`.

---

## Gating — which surfaces to include

Mirror what actually changed; do not invent. Rough guide:

- **Always:** Overview, Tasks Completed, Changed Files, Key Changes, Verification.
- **Most milestones:** add Architecture when structure shifted.
- **Contract / data work:** add API & Schema (flag what changed).
- **UI work:** add UI Changes (before/after). Backend/data-only milestones **omit** it with
  a one-line note ("No user-facing UI in this milestone").
- **Notes:** include 1–3 high-value callouts (decisions, compatibility risk, deferred
  follow-ups); skip if there are none worth flagging.

The HTML is a derived view of the real diff + `plan.md` + the audit report; if they
disagree, the source artifacts win — regenerate the recap.
