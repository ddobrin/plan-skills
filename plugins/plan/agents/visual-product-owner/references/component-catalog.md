# Visual Spec — Component Catalog

Copy-paste recipes for the eight visual surfaces. Every class used here is already
defined in `assets/template.html`, so fragments render with zero extra CSS.

## How to fill the template

1. Copy `assets/template.html` → `plans/active_milestones/{moniker}/visual-spec.html`.
2. Replace `{{MONIKER}}` and `{{TIMESTAMP}}` in the header band.
3. For each section, **replace everything between the paired markers** with your content:
   `<!-- VPO:OVERVIEW -->` … `<!-- /VPO:OVERVIEW -->`, `<!-- VPO:STORIES -->` … etc.
   The shipped demo content between the markers is a working example — delete it.
4. Leave the `<head>`, `<style>`, `<nav>`, and the bottom `<script>` untouched.
5. Omit a surface only when it does not apply (see "Gating" at the bottom). If you
   omit one, leave a one-line note in that section saying why ("No UI in this spec").

Markers, in document order: `OVERVIEW · STORIES · CRITERIA · FLOWS · CONSTRAINTS ·
PROTO · QUESTIONS · COMMENTS`.

Everything here describes **what & why** — never **how**. No file maps, no code, no
API implementations, no system-internals diagrams. Those belong to the Architect.

---

## 1. Overview

Lead with ONE concrete user journey, then the shape of the spec. Source the left card
from the Executive Summary. Keep it scannable.

```html
<div class="grid cols-2">
  <div class="card">
    <dl class="kv">
      <dt>Goal</dt><dd>Keep authenticated users signed in by rotating expired tokens.</dd>
      <dt>Target user</dt><dd>End users with active sessions.</dd>
      <dt>Business value</dt><dd>Fewer drop-offs from surprise logouts.</dd>
      <dt>Scope</dt><dd>2 user stories · 2 acceptance scenarios.</dd>
    </dl>
  </div>
  <div class="card">
    <strong>Concrete walkthrough</strong>
    <p>A user's token expires mid-session → the client silently posts it to
       <code>/auth/refresh</code> → a fresh token comes back and the action completes —
       the user never sees a login screen.</p>
  </div>
</div>
```

---

## 2. User Stories

One `.story` card per story, inside a `.stories` grid. Map straight from the spec's
"User Stories & Workflows". The `.benefit` paragraph auto-prefixes "so that" — write
only the benefit clause.

```html
<div class="stories">
  <div class="story">
    <span class="story-id">US-1</span>
    <div class="role">As an authenticated user</div>
    <p class="want">I want my session to stay alive while I'm active</p>
    <p class="benefit">I'm never logged out mid-task by an expiring token.</p>
  </div>
  <div class="story">
    <span class="story-id">US-2</span>
    <div class="role">As a security owner</div>
    <p class="want">I want tampered tokens rejected outright</p>
    <p class="benefit">a forged token can never be refreshed into a valid one.</p>
  </div>
</div>
```

The `story-id` is optional but recommended — it lets the Acceptance Criteria and
Comments reference a story by id.

---

## 3. Acceptance Criteria — the centerpiece

This is the heart of every spec: the testable contract. Render **every** scenario from
`spec.md` as a `.scenario` card holding a `ul.gherkin` list. Each `<li class="step …">`
gets a keyword class so it's color-coded: `given` (blue), `when` (amber), `then`
(green), `and`/`but` (muted). Put the keyword in `.kw` and the clause in `.txt`.

```html
<div class="scenario">
  <p class="title"><span class="tag">Scenario</span> Expired but untampered token</p>
  <ul class="gherkin">
    <li class="step given"><span class="kw">Given</span><span class="txt">a token whose <code>exp</code> has passed</span></li>
    <li class="step when"><span class="kw">When</span><span class="txt">the client calls <code>POST /auth/refresh</code></span></li>
    <li class="step then"><span class="kw">Then</span><span class="txt">a new token is returned</span></li>
    <li class="step and"><span class="kw">And</span><span class="txt">the original request is retried transparently</span></li>
  </ul>
</div>
```

Rules:
- Keep `.kw` text and the `.step` class in sync (`class="step then"` → `<span class="kw">Then</span>`).
- One `.scenario` per Gherkin scenario; do not merge scenarios into one card.
- Non-Gherkin measurable rules (the spec allows "unambiguous business rules") can use the
  same card with a single `then` step, or live in **Edge Cases & Constraints** instead.
- Wrap literals, fields, endpoints, and values in `<code>` for scannability.

---

## 4. User Flows (Mermaid)

Show the user's path and the system's response **from the user's point of view** — not
internal architecture. Good diagram types: `flowchart` (decisions/branches), `journey`
(satisfaction across steps), `stateDiagram-v2` (status transitions a user perceives).
**Mandatory:** every `<pre class="mermaid">` keeps an adjacent raw-source
`<details class="src">` with the SAME text, so the diagram survives offline / render failure.

```html
<figure>
  <pre class="mermaid">
flowchart LR
  A[Token expires mid-session] --> B{Signature valid?}
  B -- yes --> C[Issue fresh token]
  C --> D[Retry request · user sees nothing]
  B -- no --> E[401 · forced re-login]
  </pre>
  <figcaption>Refresh decision from the user's perspective.</figcaption>
  <details class="src"><summary>Mermaid source</summary><pre>flowchart LR
  A[Token expires mid-session] --> B{Signature valid?}
  B -- yes --> C[Issue fresh token]
  C --> D[Retry request · user sees nothing]
  B -- no --> E[401 · forced re-login]</pre></details>
</figure>
```

Journey variant (good for multi-step UX), swap the diagram body for:
```
journey
  title Returning user signs in
  section Arrive
    Open app: 4: User
  section Authenticate
    Auto-refresh token: 5: User, System
  section Done
    Land on home: 5: User
```

Keep node labels short. `securityLevel:'strict'` is already set — do not put raw HTML in labels.

---

## 5. Edge Cases & Constraints

A flat `ul.constraints` list. Tag each item with a kind chip: `limit` (amber),
`error` (red), `nfr` (blue), or a plain `<span class="k">RULE</span>` for anything else.
Source straight from the spec's "Constraints & Edge Cases".

```html
<ul class="constraints">
  <li><span class="k limit">Limit</span><span>A token may be refreshed for at most 24h after first issue.</span></li>
  <li><span class="k error">Error</span><span>If <code>/auth/refresh</code> is unreachable, retry twice then show "session expired".</span></li>
  <li><span class="k nfr">NFR</span><span>Refresh round-trip completes within 300&nbsp;ms at p95.</span></li>
</ul>
```

For richer rules (e.g. a limits matrix) you may use a `table.api` instead:
```html
<table class="api">
  <thead><tr><th>Field</th><th>Limit</th><th>On violation</th></tr></thead>
  <tbody>
    <tr><td>username</td><td>3–32 chars</td><td>422, inline error</td></tr>
  </tbody>
</table>
```

---

## 6. Wireframes & Interactive Prototype

Lo-fi, HTML/CSS only — **no images**. Building blocks: `.device-frame` (a screen),
`.wire` (vertical stack), `.wire-bar`, `.wire-input`, `.wire-btn`, `.wire-placeholder`.
Source from the spec's "UI/UX Mockups". This surface describes the desired UX — it is
not a visual design spec or a build artifact.

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

## 7. Open Questions

Each question is a `<details class="oq severity-…">` with a severity chip. Severities:
`severity-high` / `severity-med` / `severity-low` (chip classes `high`/`med`/`low`).
Lead with a one-line count summary. Mark the most blocking question `open`.

These are the ambiguities the **Grill Loop could not resolve** — open product decisions,
not implementation unknowns. A spec with unresolved blocking questions is not done; flag
them honestly rather than guessing an answer.

```html
<p class="oq-summary">2 open · 1 high · 1 medium</p>
<details class="oq severity-high" open>
  <summary><span class="chip high">HIGH</span> Should expired-token refresh be allowed indefinitely?</summary>
  <div class="body">Silent rotation may extend a stolen token's life. Needs a product call
  (hard lifetime cap vs. refresh-token allowlist) before the acceptance criteria are final.</div>
</details>
<details class="oq severity-med">
  <summary><span class="chip med">MED</span> What copy do users see on a failed refresh?</summary>
  <div class="body">Affects the UI/UX mockups and one acceptance scenario. Confirm with design.</div>
</details>
```

---

## 8. Comments

**These are static author callouts baked in at generation time — NOT a live, persisted,
multi-user comment system.** Anything a reviewer types in the browser is not saved. Say so
(the section lede in the template already does). Use inline anchors + a numbered list with
back-links to the relevant tab.

Inline anchor (place near the thing being discussed, in any section):
```html
this assumes "active" means a request in the last 24h<sup class="cmt-anchor">[1]</sup>
```

Comments list (in the COMMENTS section):
```html
<ol class="comments">
  <li id="cmt-1">I assumed "active" means any request in the last 24h — confirm the
     inactivity window with the user. <span class="back"><a href="#criteria">↑ Acceptance Criteria</a></span></li>
  <li id="cmt-2">The failed-refresh copy is a placeholder pending design.
     <span class="back"><a href="#proto">↑ Wireframes / Prototype</a></span></li>
</ol>
```

Back-link hrefs are tab ids: `#overview #stories #criteria #flows #constraints #proto
#questions #comments`.

---

## Gating — which surfaces to include

Mirror the spec; do not invent content. Rough guide:

- **Always:** Overview, User Stories, Acceptance Criteria (render every scenario), Open Questions.
- **Most specs:** add Edge Cases & Constraints and at least one User Flow.
- **UI work:** add Wireframes; add the interactive Prototype only for multi-step flows/wizards
  where the interaction itself is the question. Backend/data-only specs **omit** Wireframes with
  a one-line note ("No user-facing UI in this spec").
- **Comments:** include 1–3 high-value author callouts; skip if there are none worth flagging.

Keep examples at the right altitude: show the core idea, then one concrete instance — not every
case. The HTML is a derived view of `spec.md`; if they disagree, `spec.md` wins.
