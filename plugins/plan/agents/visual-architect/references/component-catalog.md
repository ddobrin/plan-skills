# Visual Plan — Component Catalog

Copy-paste recipes for the nine visual surfaces. Every class used here is already
defined in `assets/template.html`, so fragments render with zero extra CSS.

## How to fill the template

1. Copy `assets/template.html` → `plans/active_milestones/{moniker}/visual-plan.html`.
2. Replace `{{MONIKER}}` and `{{TIMESTAMP}}` in the header band.
3. For each section, **replace everything between the paired markers** with your content:
   `<!-- VA:OVERVIEW -->` … `<!-- /VA:OVERVIEW -->`, `<!-- VA:ARCHITECTURE -->` … etc.
   The shipped demo content between the markers is a working example — delete it.
4. Leave the `<head>`, `<style>`, `<nav>`, and the bottom `<script>` untouched.
5. Omit a surface only when it does not apply (see "Gating" at the bottom). If you
   omit one, leave a one-line note in that section saying why ("No UI in this plan").

Markers, in document order: `OVERVIEW · ARCHITECTURE · FILEMAP · CODE · API · SCHEMA ·
PROTO · QUESTIONS · COMMENTS`.

---

## 1. Overview

Lead with ONE concrete product example, then the shape of the work. Keep it scannable.

```html
<div class="grid cols-2">
  <div class="card">
    <dl class="kv">
      <dt>Objective</dt><dd>Rotate expired JWTs without forcing re-login.</dd>
      <dt>Target user</dt><dd>End users with active sessions.</dd>
      <dt>Execution</dt><dd>5 tasks across 2 parallel groups.</dd>
      <dt>Key risks</dt><dd>Token replay window during rotation.</dd>
    </dl>
  </div>
  <div class="card">
    <strong>Concrete walkthrough</strong>
    <p>A user's token expires mid-session → the client posts it to <code>/auth/refresh</code>
       → a fresh token is returned and the request retries transparently.</p>
  </div>
</div>
```

---

## 2. Architecture / Flow / Sequence (Mermaid)

Use `flowchart` for structure/data-flow, `sequenceDiagram` for ordered interactions.
**Mandatory:** every `<pre class="mermaid">` keeps an adjacent raw-source `<details class="src">`
so the diagram survives offline / render failure. Put the SAME Mermaid text in both places.

```html
<figure>
  <pre class="mermaid">
flowchart LR
  Client -->|POST /auth/refresh| API
  API --> Verify{valid?}
  Verify -- no --> Reject[401]
  Verify -- yes --> Rotate[issue new token]
  </pre>
  <figcaption>Token refresh flow.</figcaption>
  <details class="src"><summary>Mermaid source</summary><pre>flowchart LR
  Client -->|POST /auth/refresh| API
  API --> Verify{valid?}
  Verify -- no --> Reject[401]
  Verify -- yes --> Rotate[issue new token]</pre></details>
</figure>
```

Sequence variant: swap the diagram body for
```
sequenceDiagram
  Client->>API: POST /auth/refresh (token)
  API->>API: verify + check exp
  API-->>Client: 200 { token, exp }
```

Keep node labels short. Use `securityLevel:'strict'` is already set — do not put raw HTML in labels.

---

## 3. File Map

Nested `<ul class="filetree">`. Folders use `<span class="dir">` (click to collapse).
Tag each touched file with a status badge and the task(s) that touch it.

Badges: `<span class="badge new">new</span>` · `<span class="badge mod">modified</span>` ·
`<span class="badge del">deleted</span>`. Untouched/context files get no badge.

```html
<ul class="filetree">
  <li><span class="dir">src/auth/</span>
    <ul>
      <li>login.ts <span class="badge mod">modified</span>
          <span class="note">— call refresh on 401</span> <span class="task">Task 1.A</span></li>
      <li>refresh.ts <span class="badge new">new</span>
          <span class="note">— rotation logic</span> <span class="task">Task 1.B</span></li>
    </ul>
  </li>
  <li>src/legacy/token.ts <span class="badge del">deleted</span> <span class="task">Task 2.A</span></li>
</ul>
```

---

## 4. Annotated Code

Two-column layout: proposed snippet on the left, numbered notes on the right. Add
`class="annotated has-notes"` to get the side rail (drop `has-notes` for full-width).
**Always label snippets "proposed"** — they are illustrative targets, not live source.
Set `language-*` so highlight.js colors it (`language-typescript`, `language-python`, …).

```html
<div class="annotated has-notes">
  <div>
    <div class="label">src/auth/refresh.ts · proposed</div>
    <pre><code class="language-typescript">export async function refresh(token: string) {
  const claims = verify(token);     // 1
  if (claims.exp < now()) {
    return issue(claims.sub);       // 2
  }
  return token;
}</code></pre>
  </div>
  <ol class="ann-notes">
    <li><span class="ann-num">1</span><div><code>verify</code> must reject tampered tokens — characterize first.</div></li>
    <li><span class="ann-num">2</span><div>Rotate only when expired; otherwise return as-is.</div></li>
  </ol>
</div>
```

The `// 1`, `// 2` markers in the code line up by eye with the numbered notes. Keep
snippets short (a function, not a file); for whole files, link the path in the File Map instead.

---

## 5. API (OpenAPI-style endpoint cards)

One `<div class="card endpoint">` per operation. Method badge classes: `get post put patch delete`.

```html
<div class="card endpoint">
  <div class="ep-head"><span class="method post">POST</span><span class="path">/auth/refresh</span></div>
  <p>Exchange a valid (possibly expired) token for a fresh one.</p>
  <table class="api">
    <thead><tr><th>Field</th><th>Type</th><th>Req</th><th>Notes</th></tr></thead>
    <tbody>
      <tr><td>token</td><td>string</td><td><span class="req-tag">required</span></td><td>Current JWT</td></tr>
    </tbody>
  </table>
  <table class="api">
    <thead><tr><th>Status</th><th>Shape</th><th>Notes</th></tr></thead>
    <tbody>
      <tr><td>200</td><td><code>{ token, exp }</code></td><td>Rotated token</td></tr>
      <tr><td>401</td><td><code>{ error }</code></td><td>Tampered / invalid</td></tr>
    </tbody>
  </table>
</div>
```

Source this from the plan's `api-contracts.md` when it exists.

---

## 6. Schema (ER / data-model, Mermaid)

`erDiagram` with the same raw-source fallback rule as section 2. Source from `data-model.md`.

```html
<figure>
  <pre class="mermaid">
erDiagram
  USER ||--o{ SESSION : has
  USER { uuid id PK
         string email }
  SESSION { uuid id PK
            uuid user_id FK
            datetime expires_at }
  </pre>
  <figcaption>User ↔ Session relationship.</figcaption>
  <details class="src"><summary>Mermaid source</summary><pre>erDiagram
  USER ||--o{ SESSION : has
  USER { uuid id PK
         string email }
  SESSION { uuid id PK
            uuid user_id FK
            datetime expires_at }</pre></details>
</figure>
```

---

## 7. Wireframes & Interactive Prototype

Lo-fi, HTML/CSS only — **no images**. Building blocks: `.device-frame` (a screen),
`.wire` (vertical stack), `.wire-bar`, `.wire-input`, `.wire-btn`, `.wire-placeholder`.

Static wireframe:
```html
<div class="device-frame">
  <div class="caption">Login</div>
  <div class="wire">
    <div class="wire-bar">App</div>
    <div class="wire-input">email</div>
    <div class="wire-input">password</div>
    <button class="wire-btn">Sign in</button>
  </div>
</div>
```

Interactive prototype — wrap screens as `<section class="screen" id="screen-…">` (one
visible, the rest `hidden`); buttons carry `data-goto="screen-…"`. The template's JS
handles show/hide and updates the breadcrumb (`#crumb-label`) from each screen's `.caption`.

```html
<div class="crumb">Screen: <b id="crumb-label">Login</b></div>
<div class="device-frame">
  <section class="screen" id="screen-login">
    <div class="caption">Login</div>
    <div class="wire">
      <div class="wire-input">email</div>
      <button class="wire-btn" data-goto="screen-home">Sign in →</button>
    </div>
  </section>
  <section class="screen" id="screen-home" hidden>
    <div class="caption">Home</div>
    <div class="wire">
      <div class="wire-bar">Welcome back</div>
      <button class="wire-btn" data-goto="screen-login">Sign out →</button>
    </div>
  </section>
</div>
```

Rules: exactly one screen WITHOUT `hidden` (the entry screen); every `data-goto` must
match a `.screen` `id`; keep `#crumb-label` text equal to the entry screen's caption.

---

## 8. Open Questions

Each question is a `<details class="oq severity-…">` with a severity chip. Severities:
`severity-high` / `severity-med` / `severity-low` (chip classes `high`/`med`/`low`).
Lead with a one-line count summary. Mark the most blocking question `open`.

```html
<p class="oq-summary">2 open · 1 high · 1 medium</p>
<details class="oq severity-high" open>
  <summary><span class="chip high">HIGH</span> Cap on indefinite expired-token rotation?</summary>
  <div class="body">A stolen token could be rotated forever. Options: (a) absolute lifetime cap,
  (b) refresh-token allowlist. <strong>Blocks Task 1.B.</strong></div>
</details>
<details class="oq severity-med">
  <summary><span class="chip med">MED</span> Clock source for <code>exp</code> comparison?</summary>
  <div class="body">Server time vs. issuer skew tolerance — affects test assertions.</div>
</details>
```

Draw questions from the plan's Risks/Edge-Cases and any spec ambiguity you hit while planning.

---

## 9. Comments

**These are static author callouts baked in at generation time — NOT a live, persisted,
multi-user comment system.** Anything a reviewer types in the browser is not saved. Say so
(the section lede in the template already does). Use inline anchors + a numbered list with
back-links to the relevant tab.

Inline anchor (place near the thing being discussed, in any section):
```html
this relies on verify()<sup class="cmt-anchor">[1]</sup>
```

Comments list (in the COMMENTS section):
```html
<ol class="comments">
  <li id="cmt-1">I assumed <code>verify()</code> already rejects tampered tokens — confirm
     with the security owner. <span class="back"><a href="#code">↑ Annotated Code</a></span></li>
  <li id="cmt-2">Queue hop is optional for v1; kept for forward-compat.
     <span class="back"><a href="#architecture">↑ Architecture</a></span></li>
</ol>
```

Back-link hrefs are tab ids: `#overview #architecture #filemap #code #api #schema #proto
#questions #comments`.

---

## Gating — which surfaces to include

Mirror the plan; do not invent UI. Rough guide:

- **Always:** Overview, Architecture (at least one diagram), File Map, Open Questions.
- **Backend / data / refactor work:** add Annotated Code, API, Schema. Skip Wireframes/Prototype
  (leave a one-line "No UI in this plan").
- **UI work:** add Wireframes; add the interactive Prototype only for multi-step flows/wizards
  where interaction is the question.
- **Comments:** include 1–3 high-value author callouts; skip if there are none worth flagging.

Keep examples at the right altitude: show the core abstraction, then one concrete instance —
not every case. The HTML is a derived view of `plan.md`; if they disagree, `plan.md` wins.
