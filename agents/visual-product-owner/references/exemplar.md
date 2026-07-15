# Visual Spec — Worked Exemplar

A tiny end-to-end example: a `spec.md` excerpt, then the HTML fragments it produces. Use
this to calibrate altitude and tone. Full markup per component lives in
`component-catalog.md`; this shows how to *select* from it for a real spec. (It uses the
same "Silent Token Refresh" feature as `visual-architect`'s exemplar, so you can compare
the spec view with the plan view of the same work.)

---

## Input — `spec.md` (excerpt)

```markdown
# Product Specification: Silent Token Refresh

## 🎯 Executive Summary
*   Goal: Keep authenticated users signed in by rotating expired JWTs transparently.
*   Target User: End users with active sessions.
*   Business Value: Fewer drop-offs caused by surprise logouts.

## 🛠️ User Stories & Workflows
- As an authenticated user, I want my session to stay alive while I'm active so that I'm
  never logged out mid-task.
- As a security owner, I want tampered tokens rejected so that a forged token can't be
  refreshed into a valid one.

## 📋 Acceptance Criteria
- Scenario: Expired but untampered token
  - Given a token whose `exp` has passed
  - When the client calls POST /auth/refresh
  - Then a new token is returned and the original request retries
- Scenario: Tampered token
  - Given a token with an invalid signature
  - When the client calls POST /auth/refresh
  - Then the API responds 401 and no token is issued

## 🚨 Constraints & Edge Cases
- A token may be refreshed for at most 24h after first issue.
- Refresh round-trip must complete within 300ms at p95.
```

---

## Output — selected HTML fragments

**Overview** (`VPO:OVERVIEW`) — lead concrete:

```html
<div class="grid cols-2">
  <div class="card"><dl class="kv">
    <dt>Goal</dt><dd>Transparent JWT rotation so active users stay signed in.</dd>
    <dt>Target user</dt><dd>End users with active sessions.</dd>
    <dt>Scope</dt><dd>2 user stories · 2 acceptance scenarios.</dd>
  </dl></div>
  <div class="card"><strong>Concrete walkthrough</strong>
    <p>Token expires → client posts it to <code>/auth/refresh</code> → fresh token returned,
       request retries — the user never sees a logout.</p></div>
</div>
```

**User Stories** (`VPO:STORIES`) — one card per story:

```html
<div class="stories">
  <div class="story">
    <span class="story-id">US-1</span>
    <div class="role">As an authenticated user</div>
    <p class="want">I want my session to stay alive while I'm active</p>
    <p class="benefit">I'm never logged out mid-task.</p>
  </div>
  <div class="story">
    <span class="story-id">US-2</span>
    <div class="role">As a security owner</div>
    <p class="want">I want tampered tokens rejected</p>
    <p class="benefit">a forged token can't be refreshed into a valid one.</p>
  </div>
</div>
```

**Acceptance Criteria** (`VPO:CRITERIA`) — the centerpiece; every scenario rendered:

```html
<div class="scenario">
  <p class="title"><span class="tag">Scenario</span> Expired but untampered token</p>
  <ul class="gherkin">
    <li class="step given"><span class="kw">Given</span><span class="txt">a token whose <code>exp</code> has passed</span></li>
    <li class="step when"><span class="kw">When</span><span class="txt">the client calls <code>POST /auth/refresh</code></span></li>
    <li class="step then"><span class="kw">Then</span><span class="txt">a new token is returned</span></li>
    <li class="step and"><span class="kw">And</span><span class="txt">the original request retries</span></li>
  </ul>
</div>
<div class="scenario">
  <p class="title"><span class="tag">Scenario</span> Tampered token</p>
  <ul class="gherkin">
    <li class="step given"><span class="kw">Given</span><span class="txt">a token with an invalid signature</span></li>
    <li class="step when"><span class="kw">When</span><span class="txt">the client calls <code>POST /auth/refresh</code></span></li>
    <li class="step then"><span class="kw">Then</span><span class="txt">the API responds <code>401</code></span></li>
    <li class="step and"><span class="kw">And</span><span class="txt">no token is issued</span></li>
  </ul>
</div>
```

**User Flows** (`VPO:FLOWS`) — one user-facing flow, with the mandatory source fallback:

```html
<figure>
  <pre class="mermaid">
flowchart LR
  A[Token expires mid-session] --> B{Signature valid?}
  B -- yes --> C[Issue fresh token]
  C --> D[Retry request · user sees nothing]
  B -- no --> E[401 · forced re-login]
  </pre>
  <figcaption>Refresh decision from the user's perspective (covers both scenarios).</figcaption>
  <details class="src"><summary>Mermaid source</summary><pre>flowchart LR
  A[Token expires mid-session] --> B{Signature valid?}
  B -- yes --> C[Issue fresh token]
  C --> D[Retry request · user sees nothing]
  B -- no --> E[401 · forced re-login]</pre></details>
</figure>
```

**Edge Cases & Constraints** (`VPO:CONSTRAINTS`) — straight from the spec:

```html
<ul class="constraints">
  <li><span class="k limit">Limit</span><span>A token may be refreshed for at most 24h after first issue.</span></li>
  <li><span class="k nfr">NFR</span><span>Refresh round-trip completes within 300&nbsp;ms at p95.</span></li>
</ul>
```

**Open Questions** (`VPO:QUESTIONS`) — an ambiguity the Grill Loop surfaced but the user
deferred:

```html
<p class="oq-summary">1 open · 1 high</p>
<details class="oq severity-high" open>
  <summary><span class="chip high">HIGH</span> Cap the refresh chain for a stolen token?</summary>
  <div class="body">The 24h window bounds it, but should a single token also have a hard
  refresh-count cap? Product decision needed before the criteria are final.</div>
</details>
```

This spec is **backend-only**, so **Wireframes / Prototype is omitted** with a one-liner
("No user-facing UI in this spec"). Every visual element above traces back to a line in
`spec.md` — nothing new is introduced in the HTML, and nothing about *how* it's built
appears (no endpoints' internals, no data model, no code — that's the Architect's job).
