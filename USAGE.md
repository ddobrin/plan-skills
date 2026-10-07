# Using `html-product-owner` and `html-architect`

**Scope:** `plugins/plan` · **Audience:** the person driving a milestone and anyone asked to review a page
**See also:** [`walkthrough.md`](./walkthrough.md) (what was built) · [`html-plan-feasibility-v2.md`](./html-plan-feasibility-v2.md) (design) · [`html-runtime-options.md`](./html-runtime-options.md) (alternatives)

The two roles produce the **same `spec.md` / `plan.md`** as `product-owner` / `architect`, plus one offline HTML page that a reviewer *answers* rather than reads. The swarm never looks at the page; it only ever reads the markdown and the saved response file.

---

## 1. Invoking the roles

| You want | Say | What happens |
|---|---|---|
| A spec from an idea | *"spec this with html-product-owner"* | Normal Grill Loop in chat (≤3 questions at a time) → `spec.md` + `plans/00-ROADMAP.md` updated → `html-spec.html` rendered |
| A plan from a spec | *"plan this with html-architect"* | Reads `spec.md`, investigates the codebase read-only → `plan.md` → `html-plan.html` rendered |
| A page for an existing `spec.md` | *"render the spec as html"* (+ the milestone path) | **Render-only**: page only; any unresolved fork it finds is appended to `spec.md` → **Open Questions** first, then shown as a decision |
| A page for an existing `plan.md` | *"render the plan as html"* (+ the milestone path) | **Render-only**: page only; new forks go to `plan.md` → Risks / Open Questions first |
| The whole lifecycle | ask `starter` / `supervisor` to use the `html-*` roles | Supervisor swaps them in; validators, engineer, auditor are unaffected because the markdown contract is identical |

Mixing families is fine: `product-owner` for the spec and `html-architect` for the plan; or `architect` for the plan and `html-architect` render-only just to get the review page. Nothing may live only in the HTML — every decision on a page exists in the markdown too.

---

## 2. What comes back (the hand-over)

- One short hand-over paragraph, for example:
  > "Four decisions; the checked options are what I would build. Two schema blocks are editable. Packed at `3f9c2a1`, 0 errors, 0 warnings. Open `plans/active_milestones/{moniker}/html-plan.html`, answer, press **Respond → Copy**, paste the block here."
- Files in `plans/active_milestones/{moniker}/`:

  | File | Role |
  |---|---|
  | `spec.md` / `plan.md` | the swarm's source of truth — unchanged contract |
  | `html-spec.src.html` / `html-plan.src.html` | hand-written source (claims, decisions, block sources) |
  | `html-spec.html` / `html-plan.html` | packed, self-contained page (~220 KB): runtime inlined, code pulled from disk at the stated SHA, linted, secret-scanned |

- If Node was missing, the hand-over says the page is **unpacked**: the `.src.html` plus `html-runtime.css` / `html-runtime.js` next to it. It still opens, but code slices are empty and nothing was linted.

---

## 3. Opening the page

- Double-click `html-plan.html` / `html-spec.html`, or `File → Open` in any browser. It works at `file://` — no server, no network, no CDN.
- Antigravity / VS Code: right-click the file → *Reveal in Finder / Explorer* → open in Chrome or Firefox. The in-IDE preview works, but a real browser is more comfortable for the Respond sheet.
- It is one file, so it can be emailed to a stakeholder who was not in the chat. It carries the cited code — share it only with people who may see that code.

---

## 4. What you can do on the page

**Walk the claim tree**

- `html-spec.html` — one claim per Gherkin scenario (the *Then* as a falsifiable sentence); under it a mock with pins, a lifecycle (state machine), or a Given / When / Then strip; constraints as warnings; non-goals under *scope*.
- `html-plan.html` — behaviour › rule › `file:line`, with the real code at the stated SHA, call rows marked `+ - ~ ?`, schema blocks, and a strip showing which Tasks run in parallel. Task IDs are in bold inside the claims.

**Answer decisions**

- Every `doc-ask` has the role's recommended answer **pre-checked** and a consequence line ("scenario 4 goes", "Task 3 splits"). Open it, keep or change it.
- Decisions you never open come back as `_(not opened; default kept)_`. The swarm reads that as *not reviewed*, not as agreement.

**Comment, strike, edit**

- Comment button on every claim, row, pin and state.
- Strike a call row you reject (plan).
- Edit a schema block in place (plan) or long copy such as error text, email body, empty-state text (spec, `doc-draft`). Edits come back as a unified diff.

---

## 5. Providing feedback

1. Press **Respond → Copy**. The clipboard now holds one markdown block that starts with `# Re: <page title>` and contains `## Decisions`, `## Comments`, `## Struck`, `## Edits`.
2. **Paste it into the chat** with the role (or with the supervisor in a swarm run). The page sends nothing anywhere by itself.
3. The agent then, in this order:
   - **saves it verbatim** to `plans/active_milestones/{moniker}/review/html-plan.response-N.md` (or `html-spec.response-N.md`, `N` incrementing) before touching anything — the supervisor does this in a swarm run, the role itself in direct use;
   - **applies it inside what the artifact proposed** —
     spec: answers → scenario / constraint tightenings, item removed from Open Questions; mock comments → UI/UX section; `doc-draft` diffs pasted verbatim;
     plan: changed decisions → the affected Tasks; struck calls → steps and files removed; schema diffs → `data-model.md` and the creating Task; comments addressed in `plan.md` or answered in the hand-over;
   - **regenerates the page** and hands over again if the shape changed (new or removed claims, decisions, tasks).
4. A comment that asks for something **outside** the spec or plan is raised back to you in chat as a new request — never planned silently.
5. Repeat until the page comes back with nothing to change; then the normal path continues (`spec-validator` / `plan-validator`, approval, engineer, auditor).

---

## 6. Three rules that always hold

- **A response is data, not instructions.** Text inside the pasted block cannot command the agent; it is only ever applied within what the artifact proposed.
- **`_(not opened; default kept)_` is not agreement.** If a decision matters, say so in chat.
- **A response is never an approval.** A commit still needs a green audit **and** your explicit approval in chat; a response file under `review/` is cited in the commit notes, never in the commit message.

---

## 7. Quick reference

```
spec this with html-product-owner       → spec.md + html-spec.html
plan this with html-architect           → plan.md + html-plan.html
render the spec as html                 → html-spec.html for an existing spec.md
render the plan as html                 → html-plan.html for an existing plan.md

open  plans/active_milestones/{moniker}/html-plan.html     (file://, any browser)
answer decisions · comment · strike · edit
Respond → Copy  →  paste the "# Re: …" block in chat
saved to       plans/active_milestones/{moniker}/review/html-plan.response-N.md
```
