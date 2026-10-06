# `spec.md` → `html-spec.html` — the mapping

> Read `assets/html-runtime/blocks.md` first for block syntax. This file says **which** block each part of `spec.md` becomes, with the fragment to copy. `references/exemplar.src.html` shows all of it on one page.

## The rules in one place

| Rule | Value |
|---|---|
| Top-level claims | **≤ 5** — one per Gherkin Scenario. If the spec has more scenarios, group the ones that share a screen under one claim and make the rest level-2 |
| Depth | **≤ 3** levels; a spec page rarely needs more than 2. **No level-3 claims** — level 3 is "where" (code), and a spec has none |
| Decisions (`doc-ask`) | **2–5**. Ask only about forks that change what gets built; default the rest in `spec.md` |
| Claim text | the *Then*, as a **falsifiable sentence of ≤ 12 words** that ends with a full stop |
| Question text | ≤ 15 words in the first `<p>`; context goes in a second `<p>` |
| Captions, pins | one sentence |
| Prose outside the blocks | ≤ 350 words on the page; ≤ ~30 words per block |
| Quotes | **quote, do not paraphrase**; trim with `…` |
| Exhibits | **one per claim**; a second one gets its own child claim |
| Mocks | `frame="none"` and `w ≤ 480` — the smallest region that makes the point |

## Forbidden on a spec page

`pack --role po` **errors** on any of these: **`doc-calls`**, **`doc-code`**, **`doc-schema`**, **`doc-tree`**. It also errors when there is no `<doc-plan>` and when there is no `<doc-claim aux="scope">`, and warns when there is no `doc-quote`. Beyond the packer, do not use `doc-flow` or `doc-seq` for internals: a user-visible journey can be a `doc-machine`; a system diagram cannot appear at all. Before packing:

```
grep -nE '<doc-(calls|code|schema|tree)\b' html-spec.src.html    # must print nothing
```

## The page skeleton

```html
<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>[Feature Name] · spec</title>
<link rel="stylesheet" href="RELATIVE/PATH/TO/html-runtime/html-runtime.css">
<script src="RELATIVE/PATH/TO/html-runtime/html-runtime.js" defer></script>
<style data-mock-shared> /* CSS shared by every doc-mock on the page */ </style>
<body>
<header> … h1 + Why thread … </header>
<main>
<doc-plan>
  <doc-claim> … one per Scenario … </doc-claim>
  <doc-claim aux="scope"> … non-goals, last … </doc-claim>
</doc-plan>
</main>
</body>
</html>
```

No `doc-changes` in the header — a spec does not count files.

## Section by section

### `## 🎯 Executive Summary` → `h1` + the Why thread

The **Goal** becomes the `h1`: a title of **3–7 words** naming the change and the place, not a sentence (`Scheduling Sent Messages in PostBox`, `Reviewing a Spec in the Browser`). The **Target User** and **Business Value** are not repeated as prose; they live in the claims' wording and, when they must be said, in one `doc-note tone="info"` under the first claim.

The user's original request, and any research or thread that motivated it, go in a `details.thread` of `doc-quote`s **in their own words**. `via="prompt|slack|github|doc|email|meeting|transcript"`. `from` is the bare name or handle (no parentheses, no `file:line`); context goes in `where=`.

```html
<header>
  <h1>Reviewing a Spec in the Browser</h1>
  <details class="thread"><summary>Why · 2 requests</summary>
    <doc-quote via="prompt" from="the user">add send later to the composer. I need to be able to cancel it…</doc-quote>
    <doc-quote via="doc" from="html-plan-feasibility-v2.md" where="§1 Design goals">A review instrument, not a view. Each html-* page is something the reviewer <em>answers</em>…</doc-quote>
  </details>
</header>
```

### `## 🛠️ User Stories & Workflows` → folded into the claims

A story is not a block. Its *I want to* shapes the claim's wording; its *so that* becomes a `doc-note tone="info"` under the claim's exhibit **only if** the reader would otherwise ask "why". Do not render a card per story.

```html
<doc-note tone="info"><strong>So that</strong> people who were not in the chat can still answer.</doc-note>
```

### `## 📋 Acceptance Criteria` → one level-1 claim per Scenario

The centrepiece. Each **Scenario** is a `doc-claim` whose first child is a `<p>` with the **Then** as a falsifiable sentence. Then **one exhibit**. Then the **Given/When/Then** as a 3-card strip. Then `doc-ask` / `doc-note` if that scenario carries a decision or a constraint. Then level-2 claims.

Each step inside a card is an `<li>` — the runtime makes every `<li>` in `main` a comment target, so a reviewer can comment on *one step*, and the response names it. Give the strip `class="cols gwt"` so you can find it again.

```html
<!-- ═════ 1 ═════ -->
<doc-claim id="s1">
  <p>The reviewer opens the page offline and sees every scenario as a claim.</p>

  <doc-mock frame="none" w="440"><template>
<div class="ui">
  <div class="hd">Reviewing a Spec in the Browser <small>4 to answer</small></div>
  <div class="row"><b>1</b> The reviewer opens the page offline…<span class="pill" data-ref="count">1 decision</span></div>
</div></template>
    <doc-pin ref="count" title="Decisions waiting under this claim">Zero when all are answered.</doc-pin>
  </doc-mock>

  <div class="cols gwt">
    <div class="card"><h4>Given</h4><ul><li>a packed <code>html-spec.html</code> on disk</li><li>no network</li></ul></div>
    <div class="card"><h4>When</h4><ul><li>the reviewer opens it at <code>file://</code></li></ul></div>
    <div class="card"><h4>Then</h4><ul><li>every scenario is a numbered claim</li><li>a count shows the decisions waiting</li></ul></div>
  </div>
</doc-claim>
```

**Lifecycle scenarios.** When the Scenario describes something that moves through states (a draft → scheduled → sent; a decision unopened → opened → answered), the exhibit is a `doc-machine` with a **screen per state**, and the Given/When/Then strip follows it. The reader taps a state and sees its screen; a comment on a state comes back naming it.

```html
<doc-machine name="dec" caption="Tap a state to see what the reviewer sees there.">
<script type="text/plain">
machine dec initial unopened
state unopened          # Closed claim. The default is kept but nothing says the reader looked.
state opened            # The question and its suggested answer are on screen.
state kept      final   # The reader left the suggestion. The response says "kept as proposed".
state changed   final   # The reader picked another option.

| unopened | opened | kept    |
| .        | .      | changed |

unopened -tap->    opened  : open
opened   -leave->  kept    : no change
opened   -pick->   changed : other option
</script>
  <div data-state="unopened"><doc-mock frame="none" w="400"><template>…</template></doc-mock></div>
  <div data-state="opened"><doc-mock frame="none" w="400"><template>…</template></doc-mock></div>
  <div data-state="kept"><doc-mock frame="none" w="400"><template>…</template></doc-mock></div>
  <div data-state="changed"><doc-mock frame="none" w="400"><template>…</template></doc-mock></div>
</doc-machine>
```

Pack refuses unreachable states and dead ends that are not `final`. Keep it to 8 states; give it a grid.

**Alternative placement.** When a Scenario is one of several under a shared screen, make it a **level-2 claim** whose exhibit is the strip's parent mock and put its own Given/When/Then strip under it. A level-2 claim must still have *something* under it (an exhibit or a strip); pack warns on an empty claim.

### `## 🚨 Constraints & Edge Cases` → level-2 claims or `doc-note tone="warn"`

A constraint that is itself testable ("A user can hold 50 scheduled messages at most.") is a **level-2 claim** under the scenario it bounds, with a mock of the moment it bites (the error, the disabled button). A constraint that merely qualifies a scenario is a `doc-note tone="warn"` under that scenario's exhibit.

```html
<doc-claim>
  <p>A reviewer can leave at most one comment per step.</p>
  <doc-mock frame="none" w="400"><template>…the second attempt replaces the first…</template></doc-mock>
</doc-claim>

<doc-note tone="warn"><strong>Limit</strong> Answers live in this browser's storage; another device starts blank.</doc-note>
```

**`**Open Questions:**`** items (residual Grill-Loop unknowns, and anything appended under the append-first rule) → **`doc-ask`**, next.

### Open Questions → `doc-ask` with the recommended answer `checked`

One `doc-ask` per unresolved fork, placed **on the claim it changes**, never stacked back to back. The option you would spec carries `checked`. Where an answer changes the page's shape, add a `data-if` consequence so the reader sees the cost before choosing. Control names are unique on the page.

```html
<doc-ask id="persist">
  <p>Where do a reviewer's answers live between visits?</p>
  <label><input type="radio" name="persist" value="browser" checked> This browser only <small>nothing leaves the machine</small></label>
  <label><input type="radio" name="persist" value="file"> Also in a file next to the page <small>needs a save step</small></label>
  <label><input type="radio" name="persist" value="none"> Not at all <small>scenario 3 goes</small></label>
</doc-ask>
<div data-if="persist=none"><doc-note tone="warn">Then scenario 3 goes: a reload loses every answer.</doc-note></div>
```

Other controls when a radio does not fit: checkboxes sharing one `name` (pick several), `<input type="range" name min max value>` (a scale), `<textarea name>` (free text), `<ol class="rank" data-name="x"><li data-value="a">` (drag to rank). Short options sit side by side in `<div class="opts-row">`.

### `## 🎨 UI/UX Mockups` → `doc-mock frame="none" w≤480` with pins

Draw the **smallest region that makes the point** — one card, one menu, one row — in real HTML with inline styles or a `<style>` in the template; share CSS across mocks with one page-level `<style data-mock-shared>`. Mark the elements a reviewer should be able to comment on with `data-ref="name"`, and put a `doc-pin ref="name" title="…"` on the ones they must notice. A pin describes; it never adds a requirement. Give neighbouring pins different anchors.

```html
<doc-mock frame="none" w="440" caption="The Respond sheet, after Copy."><template>
<div class="ui">
  <div class="hd">Respond</div>
  <div class="ln">3 decisions · 2 comments · 1 edit</div>
  <div class="ft"><span class="btn pri" data-ref="copy">Copy</span><span class="btn" data-ref="reset">Reset</span></div>
</div></template>
  <doc-pin ref="copy" title="One markdown block">Starts with “# Re:”.</doc-pin>
  <doc-pin ref="reset" anchor="tl" title="Clears this browser's answers"></doc-pin>
</doc-mock>
```

A behaviour whose output is text (a CLI line, a generated message) is a `doc-mock frame="terminal" w≤480`. UI that already exists is a `doc-shot src="…png"` (the packer inlines the image); UI that does not exist yet is a mock.

### Long copy the reviewer should edit → `doc-draft`

Error text, an email body, an empty-state message, a hand-over line. Not a block of requirements. The reader presses Edit; the response carries a diff you paste into `spec.md` verbatim. Always give it an `id`.

```html
<doc-draft id="handover" label="The hand-over line">
<script type="text/plain">
Three decisions; the checked options are what I would spec. One copy block is editable.
</script>
</doc-draft>
```

### Non-goals → `doc-claim aux="scope"`

Required by `--role po`. Last in the tree. A `<p>` naming what is not changing, then a `<ul>` of one-line items. Each `<li>` is a comment target, which is where "but what about X" lands instead of on a scenario.

```html
<doc-claim aux="scope">
  <p>Not in this spec: the architect's page, the recap, the approval phrase.</p>
  <ul>
    <li>No code, call trees, schemas or file trees on this page — that is <code>html-plan.html</code>.</li>
    <li>A response is never an approval; the phrase is typed on its own.</li>
  </ul>
</doc-claim>
```

## What the packer checks under `--role po`

| Level | Check |
|---|---|
| **error** | any `doc-calls`, `doc-code`, `doc-schema`, `doc-tree` |
| **error** | no `<doc-plan>`; no `<doc-claim aux="scope">` |
| **error** | a block whose source is not inside `<script type="text/plain">` and contains `<`; a `doc-pin ref=` with no matching `data-ref` in its mock; a `data-if` naming a control that does not exist; a machine with an unreachable state or a non-final dead end; a radio without a `value`; a duplicate control name; a `doc-claim` with no `<p>` |
| warning | no `doc-quote`; a claim over ~12 words or without a verb; two exhibits under one claim; an empty claim; more than 5 top claims or 5 children; level > 3; more than 6 decisions; two `doc-ask`s back to back; a radio group with nothing `checked`; a question over ~15 words; a `doc-draft` or `doc-ask` without an `id`; prose over the budgets; a mock ≥ 800 wide without `thumbnail` |

`--role` implies `--no-ste`: vocabulary, contraction, tense and voice lints are off; the budgets above stay.

## Self-check before the hand-over

- [ ] one level-1 claim per Scenario, and no Scenario without a claim
- [ ] each claim: `<p>` → one exhibit → strip → (`doc-ask` | `doc-note`) → children
- [ ] every `doc-ask` has a line in `spec.md`'s `**Open Questions:**`; every `data-if` has a control
- [ ] `grep -nE '<doc-(calls|code|schema|tree)\b'` prints nothing
- [ ] `aux="scope"` is last; nothing follows it
- [ ] the packed file has no `http(s)://` in a `<script src>` or `<link href>`
