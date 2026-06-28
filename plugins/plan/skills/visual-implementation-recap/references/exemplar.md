# Visual Recap — Worked Exemplar

A tiny end-to-end example: the grounding inputs (a `git diff`, the completed `plan.md`
checklist, and the audit report) and the HTML fragments they produce. Use this to
calibrate altitude and tone. Full markup per component lives in `component-catalog.md`;
this shows how to *select* from it for a real milestone. (It uses the same "Silent Token
Refresh" feature as the `visual-architect` / `visual-product-owner` exemplars, so you can
compare the recap of the *result* with the plan and spec of the same work.)

---

## Input — the grounding

`git diff --stat HEAD`:
```
 src/auth/refresh.ts        | 38 ++++++++++++++++++
 src/auth/login.ts          | 16 +++++----
 test/auth/refresh.test.ts  | 46 +++++++++++++++++++++
 src/legacy/token.ts        |  8 ----
 4 files changed, 96 insertions(+), 12 deletions(-)
```

`plan.md` (checked off by the engineer):
```markdown
- [x] Task 1.B: refresh() rotation logic (Status: ✅ Implemented in src/auth/refresh.ts)
- [x] Task 1.C: retry-on-401 in client (Status: ✅ Implemented in src/auth/login.ts)
- [x] Task 2.A: delete dead legacy/token.ts (Status: ✅ Removed)
```

`plans/audit/AUDIT_Silent_Token_Refresh.md` (excerpt):
```markdown
## 📊 Summary
*   Overall Status: PASS
*   Completion Rate: 5/5 Steps verified

## 🚨 Anti-Shortcut & Quality Scan
*   Placeholders/TODOs/Deferred Work: None found
*   Test Integrity: Tests are robust (7 new, all pass)
```
(The `implementation-validator` confirmed one finding — a singleton clock race — but
downgraded it to LOW: impact is gated on same-millisecond concurrent refresh.)

---

## Output — selected HTML fragments

**Overview** (`VIR:OVERVIEW`) — numbers first, then one concrete sentence:

```html
<div class="metrics">
  <div class="metric"><div class="num">4</div><div class="lbl">Files changed</div></div>
  <div class="metric add"><div class="num">+96</div><div class="lbl">Insertions</div></div>
  <div class="metric del"><div class="num">−12</div><div class="lbl">Deletions</div></div>
  <div class="metric pass"><div class="num">PASS</div><div class="lbl">Audit · 5/5 steps</div></div>
</div>
<div class="grid cols-2">
  <div class="card"><dl class="kv">
    <dt>Outcome</dt><dd>Expired JWTs rotate transparently; tampered tokens get <code>401</code>.</dd>
    <dt>Tests</dt><dd>7 added · all green.</dd>
  </dl></div>
  <div class="card"><strong>What shipped</strong>
    <p>A token expires mid-session → the client silently calls <code>refresh()</code> →
       the request retries with a fresh token, so the user never sees a logout.</p></div>
</div>
```

**Tasks Completed** (`VIR:TASKS`) — names verbatim from `plan.md`, chip from the audit:

```html
<ul class="tasks">
  <li><span class="st pass">Done</span><span class="tk">Task 1.B — refresh() rotation logic <span class="ref">src/auth/refresh.ts</span></span></li>
  <li><span class="st pass">Done</span><span class="tk">Task 1.C — retry-on-401 in client <span class="ref">src/auth/login.ts</span></span></li>
  <li><span class="st pass">Done</span><span class="tk">Task 2.A — delete dead legacy/token.ts <span class="ref">src/legacy/token.ts</span></span></li>
</ul>
```

**Changed Files** (`VIR:FILES`) — straight from `git diff --stat`:

```html
<ul class="filetree">
  <li><span class="dir">src/auth/</span>
    <ul>
      <li>refresh.ts <span class="badge new">new</span> <span class="stat"><span class="add">+38</span> <span class="del">−0</span></span></li>
      <li>login.ts <span class="badge mod">modified</span> <span class="stat"><span class="add">+12</span> <span class="del">−4</span></span></li>
    </ul>
  </li>
  <li><span class="dir">test/auth/</span>
    <ul><li>refresh.test.ts <span class="badge new">new</span> <span class="stat"><span class="add">+46</span> <span class="del">−0</span></span></li></ul>
  </li>
  <li>src/legacy/token.ts <span class="badge del">deleted</span> <span class="stat"><span class="del">−8</span></span></li>
</ul>
```

**Key Changes** (`VIR:CHANGES`) — the centerpiece; lines verbatim from `git diff`:

```html
<div class="card">
  <div class="diff-head"><span class="path">src/auth/login.ts</span> <span class="badge mod">modified</span> <span class="stat"><span class="add">+12</span> <span class="del">−4</span></span></div>
  <pre class="diff"><span class="ln hunk">@@ -18,7 +18,9 @@ async function call(req) {</span>
<span class="ln ctx">   const res = await fetch(req);</span>
<span class="ln del">-  if (res.status === 401) throw new AuthError();</span>
<span class="ln add">+  if (res.status === 401) {</span>
<span class="ln add">+    const fresh = await refresh(currentToken());</span>
<span class="ln add">+    return retry(req, fresh);</span>
<span class="ln add">+  }</span>
<span class="ln ctx">   return res;</span></pre>
</div>
```

**Verification** (`VIR:VERIFY`) — verdict from the audit, with the one downgraded finding:

```html
<div class="verdict pass">
  <span class="tag">PASS</span>
  <div><strong>5 / 5 steps verified</strong>
    <div class="detail">Build green · 7/7 tests pass · no placeholders or skipped tests.</div></div>
</div>
<details class="oq severity-low">
  <summary><span class="chip low">LOW</span> Singleton clock could skew <code>exp</code> under load</summary>
  <div class="body">Raised by <code>implementation-validator</code>; confirmed real but
  <strong>downgraded</strong> — gated on same-ms concurrent refresh. Tracked as a follow-up.</div>
</details>
```

This milestone is **backend-only**, so **UI Changes is omitted** with a one-liner ("No
user-facing UI in this milestone"). Every fragment above traces back to a real changed
line, a `plan.md` task, or the audit report — nothing is invented, and any secret in the
diff would have been masked before rendering.
