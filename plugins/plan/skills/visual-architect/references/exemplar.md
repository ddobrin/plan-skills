# Visual Plan — Worked Exemplar

A tiny end-to-end example: a spec excerpt + a plan excerpt, then the HTML fragments they
produce. Use this to calibrate altitude and tone. Full markup per component lives in
`component-catalog.md`; this shows how to *select* from it for a real plan.

---

## Input — `spec.md` (excerpt)

```markdown
# Product Specification: Silent Token Refresh
## 🎯 Executive Summary
*   Goal: Keep authenticated users signed in by rotating expired JWTs transparently.
## 📋 Acceptance Criteria
- Scenario: Expired but untampered token
  - Given a token whose `exp` has passed
  - When the client calls POST /auth/refresh
  - Then a new token is returned and the original request retries
- Scenario: Tampered token
  - Given a token with an invalid signature
  - When the client calls POST /auth/refresh
  - Then the API responds 401 and no token is issued
```

## Input — `plan.md` (excerpt produced by the same run)

```markdown
## 🔍 Analysis & Context
* Objective: Add transparent JWT rotation on 401.
* Affected Files: src/auth/login.ts (mod), src/auth/refresh.ts (new)
* Risks/Edge Cases: replay window during rotation; clock skew on exp.
## 📋 Task Execution (Parallel Groups)
### Group 1
- [ ] Task 1.A: Add refresh-on-401 to login.ts
- [ ] Task 1.B: Implement refresh() in refresh.ts
```

---

## Output — selected HTML fragments

**Overview** (`VA:OVERVIEW`) — lead concrete:

```html
<div class="grid cols-2">
  <div class="card"><dl class="kv">
    <dt>Objective</dt><dd>Transparent JWT rotation on 401.</dd>
    <dt>Execution</dt><dd>2 tasks, 1 group.</dd>
    <dt>Key risks</dt><dd>Replay window during rotation.</dd>
  </dl></div>
  <div class="card"><strong>Concrete walkthrough</strong>
    <p>Token expires → client posts it to <code>/auth/refresh</code> → fresh token returned,
       request retries — user never sees a logout.</p></div>
</div>
```

**Architecture** (`VA:ARCHITECTURE`) — one flow, with the mandatory source fallback:

```html
<figure>
  <pre class="mermaid">
flowchart LR
  Client -->|POST /auth/refresh| API
  API --> V{signature valid?}
  V -- no --> R[401, no token]
  V -- yes --> Iss[issue rotated token]
  </pre>
  <figcaption>Refresh decision flow (covers both acceptance scenarios).</figcaption>
  <details class="src"><summary>Mermaid source</summary><pre>flowchart LR
  Client -->|POST /auth/refresh| API
  API --> V{signature valid?}
  V -- no --> R[401, no token]
  V -- yes --> Iss[issue rotated token]</pre></details>
</figure>
```

**File Map** (`VA:FILEMAP`) — straight from "Affected Files", tagged by task:

```html
<ul class="filetree">
  <li><span class="dir">src/auth/</span><ul>
    <li>login.ts <span class="badge mod">modified</span>
        <span class="note">— catch 401, call refresh</span> <span class="task">Task 1.A</span></li>
    <li>refresh.ts <span class="badge new">new</span>
        <span class="note">— verify + rotate</span> <span class="task">Task 1.B</span></li>
  </ul></li>
</ul>
```

**API** (`VA:API`) — the one endpoint the spec names:

```html
<div class="card endpoint">
  <div class="ep-head"><span class="method post">POST</span><span class="path">/auth/refresh</span></div>
  <table class="api"><thead><tr><th>Status</th><th>Shape</th><th>Notes</th></tr></thead><tbody>
    <tr><td>200</td><td><code>{ token, exp }</code></td><td>Expired+untampered → rotated</td></tr>
    <tr><td>401</td><td><code>{ error }</code></td><td>Tampered → no token</td></tr>
  </tbody></table>
</div>
```

**Open Questions** (`VA:QUESTIONS`) — lifted directly from the plan's Risks:

```html
<p class="oq-summary">1 open · 1 high</p>
<details class="oq severity-high" open>
  <summary><span class="chip high">HIGH</span> Bound the rotation chain for a stolen token?</summary>
  <div class="body">A leaked token could rotate forever. Decide before Task 1.B: absolute
  lifetime cap vs. refresh-token allowlist.</div>
</details>
```

This plan is backend-only, so **Wireframes/Prototype is omitted** with a one-liner
("No user-facing UI in this milestone"), and **Schema** is skipped (no model change).
Every visual element above traces back to a line in `spec.md` or `plan.md` — nothing new
is introduced in the HTML.
