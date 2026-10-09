#!/usr/bin/env python3
"""Render docs/usage-e2e.html from a real run of examples/e2e_demo.py.

Usage (from the repository root):
    python3 examples/e2e_demo.py [WORKDIR]
    python3 examples/render_usage_e2e.py [WORKDIR]      (default WORKDIR: /tmp/swarm-e2e)

Reads WORKDIR/transcript.json, WORKDIR/git-state.json, and WORKDIR/hook-events.jsonl
and writes docs/usage-e2e.html. Every step, hook message, gate decision, command
output, and git state on the page is copied from those files; only the stage
introductions are written here. Absolute paths are shortened (~/shop, origin.git,
<plugin>/lib). Standard library only.
"""
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/swarm-e2e")
OUT = os.path.join(ROOT, "docs", "usage-e2e.html")
LIB = os.path.join(ROOT, "plugins", "plan", "lib")


def clean(text):
    text = str(text if text is not None else "")
    for real in {BASE, os.path.realpath(BASE)}:
        text = text.replace(f"{real}/shop", "~/shop").replace(f"{real}/origin.git", "origin.git")
        text = text.replace(f"{real}/antigravity/brain", "~/.gemini/antigravity/brain")
    return text.replace(LIB, "<plugin>/lib")


def esc(text):
    return html.escape(clean(text), quote=True)


steps = json.load(open(os.path.join(BASE, "transcript.json")))
states = json.load(open(os.path.join(BASE, "git-state.json")))
events = [json.loads(line) for line in open(os.path.join(BASE, "hook-events.jsonl"))]
STAGES = list(dict.fromkeys(s["stage"] for s in steps))

# Stage introductions: (title, what happens, you do, approval stage?)
INTRO = {
    "0": ("Prepare the repository once",
          "The plugin folder is installed at <code>~/.gemini/config/plugins/plan</code> (hooks load for new "
          "conversations). In a conversation opened on the repository, the <code>swarm-init</code> skill previews and "
          "installs <code>plans/swarm.md</code>, the three git hooks, <code>REVIEW.md</code>, and the CI workflow. Before "
          "<code>plans/swarm.md</code> exists the hooks are neutral (the gate still expands <code>$PLAN_LIB</code>). "
          "In a new top-level conversation the first <code>PreInvocation</code> announces enforcement and "
          "<code>PLAN_LIB</code>; the supervisor's first act is <code>health.py --status</code>.",
          "Type <code>swarm init</code>, review and commit what it installed yourself, then open a new top-level "
          "conversation on the repository and type <code>Be the supervisor.</code>", False),
    "1": ("Describe the problem",
          "Your request is an ordinary message, so the approval hook ignores it. The supervisor dispatches "
          "<code>product-owner</code> in intent mode with <code>invoke_subagent</code>, then proposes a risk tier from the "
          "intent's wording. A premature commit is refused: nothing is approved yet.",
          "Describe the problem in one or two sentences.", False),
    "2": ("Turn the intent into a milestone",
          "You type the phrase as your whole message in the top-level conversation. <code>approve.py</code> mints a "
          "single-use nonce bound to HEAD, appends a row to <code>approvals.md</code>, and stages it. A second "
          "<code>PreInvocation</code> in the same turn mints nothing. The supervisor creates <code>swarm/login-rate-limit</code>, "
          "moves the intent, the product owner adds the roadmap entry, and the auditor commits <code>plans/</code>.",
          "Type the phrase the supervisor printed.", True),
    "3": ("Learn the code",
          "A read-only research subagent (<code>TypeName: \"self\"</code>) investigates; the supervisor appends its "
          "<code>## Codebase context</code> section to <code>intent.md</code> (a <code>plans/</code> file, not code).",
          "Nothing.", False),
    "4": ("Agree on testable requirements",
          "The product owner runs the Grill Loop with <code>ask_question</code> (at most 3 questions) and writes "
          "<code>spec.md</code>. A phrase typed inside the product owner's subagent conversation is ignored "
          "(its transcript starts with the parent's message), and the gate refuses every attempt to plant a phrase as "
          "another agent's message: <code>send_message</code> and a dispatch whose whole prompt is a phrase. "
          "The declined spec gate is logged.",
          "Answer the questions, decline or accept the offered gates, then type <code>approve spec login-rate-limit</code> "
          "in the top-level conversation.", True),
    "5": ("Plan in parallel groups",
          "The architect writes <code>plan.md</code> with disjoint-file groups. <code>tier.py</code> raises the tier to "
          "<b>critical</b> (an auth path and the keyword <i>password</i>), so the validators are recommended. You decline "
          "the plan-deliberator and accept the plan-validator, which dispatches three read-only skeptics in one call.",
          "Decide on the offered plan gates.", False),
    "6": ("The go / no-go",
          "Before the approval, dispatching an <code>engineer</code> is refused, and so are agent writes to "
          "<code>approvals.md</code> and <code>plans/swarm.md</code>. <code>approve plan</code> confirms the proposed tier; "
          "the auditor commits the plan.",
          "Review <code>spec.md</code>, <code>plan.md</code>, and the gate report, then type "
          "<code>approve plan login-rate-limit</code>.", True),
    "7": ("Engineers build in parallel worktrees",
          "<code>worktree.py create</code> makes one worktree per task on <code>swarm-wip/{m}/{task}</code>. Both engineers "
          "go out in one <code>invoke_subagent</code> call. A WIP commit inside a worktree is allowed; a commit in the main "
          "checkout is refused. <code>worktree.py squash</code> stages the group's diff without committing.",
          "Nothing.", False),
    "8": ("Prove it works",
          "The auditor runs the test command from <code>AGENTS.md</code> and records "
          "<code>### Group 1 · Round 1 · PASS</code> in <code>audit.md</code>. You decline the simplifier and the "
          "implementation gate; both declines are logged with the tier.",
          "Decide on the offered checks.", False),
    "9": ("One audited group, one commit",
          "The auditor's commit is refused until you approve. After <code>approve commit</code> the gate consumes the nonce "
          "and issues a one-time ticket that the <code>pre-commit</code> git hook checks. Reusing the approval is refused.",
          "Type <code>approve commit login-rate-limit g1</code>.", True),
    "10": ("The last group",
           "Group 2 runs the same loop. Before its commit gate the product owner marks the milestone COMPLETED in the "
           "roadmap, so that change ships inside the PR.",
           "Type <code>approve commit login-rate-limit g2</code>.", True),
    "11": ("Open the PR",
           "The tier is re-checked on the real diff, read-only so the PR approval commit stays ledger-only (only a tier "
           "above the confirmed one would mean <code>--write</code> and a new <code>approve plan</code>). The push is "
           "refused by the gate and, from your own terminal, by the "
           "<code>pre-push</code> hook. After <code>approve pr</code> the auditor commits only the ledger row, the push "
           "passes, and <code>prbody.py</code> builds the title and body. This demo has no <code>gh</code>, so the "
           "supervisor prints the push result and the PR text instead of running <code>gh pr create</code>. The CI ledger "
           "job passes; an agent's attempt to merge is refused; a code owner merges.",
           "Type <code>approve pr login-rate-limit</code>; review and merge the PR on GitHub.", True),
    "12": ("Tag the release",
           "Switch and pull must be separate commands (the gate judges a command before it runs). After "
           "<code>approve release</code> the hook reads the conversation transcript and records the release row in "
           "<code>plans/approvals.md</code>. The tag and its push are allowed once; pushing <code>main</code> is refused.",
           "Type <code>approve release v1.0.0</code> and agree to push the tag.", True),
    "13": ("See what happened",
           "<code>metrics.py</code> reads only committed files (lead times are 0.0h because this run took seconds). The "
           "branch history, the ledger, and the cost log are the audit trail.",
           "Run the <code>swarm-metrics</code> skill whenever you like.", False),
}

PILL = {"prompt": ("a", "you type"), "hook": ("b", "hook"), "ran": ("g", "ran"), "blocked": ("r", "denied"),
        "dispatched": ("g", "dispatched"), "file": ("p", "file"), "script": ("x", "script"), "note": ("x", "note"),
        "git-hook": ("r", "git hook"), "ci": ("g", "CI")}
INPUT_KEY = {"prompt": "message", "hook": "event", "ran": "run_command", "blocked": "tool call",
             "dispatched": "tool call", "file": "file", "script": "terminal", "note": "input", "git-hook": "terminal",
             "ci": "job"}


def pre(text, cls="out"):
    text = clean(text)
    lines = text.count("\n") + 1
    block = f'<pre class="{cls}">{html.escape(text)}</pre>'
    return f"<details><summary>show {lines} lines</summary>{block}</details>" if lines > 14 else block


def step_html(s):
    kind = s["kind"]
    color, word = PILL.get(kind, ("x", kind))
    if kind == "ran" and s["exit"] not in (None, 0):
        word = f"ran · exit {s['exit']}"
    if kind == "git-hook":
        word = f"git hook · exit {s['exit']}"
    if kind == "blocked":
        word = "denied by the gate · not run"
    pills = [f'<span class="pill {color}">{word}</span>']
    note = s.get("note") or ""
    gate = ""
    m = re.match(r"gate: ([^—]+?)(?: — (.*))?$", note)
    if m:
        gate, note = m.group(1).strip(), (m.group(2) or "")
        pills.append(f'<span class="pill b">gate: {esc(gate)}</span>')
    if "Example" in note:
        pills.append('<span class="pill p">example content</span>')
    label = s["label"][len("you type: "):] if kind == "prompt" and s["label"].startswith("you type: ") else s["label"]
    head = f'<div class="head">{" ".join(pills)}<b>{esc(label)}</b></div>'
    if kind == "dispatched" and s["input"].lstrip().startswith("{"):
        inp = (f'<div class="in"><span class="k">{INPUT_KEY[kind]}</span><code>invoke_subagent</code></div>'
               if "Subagents" in s["input"] else
               f'<div class="in"><span class="k">{INPUT_KEY[kind]}</span><code>send_message</code></div>')
        inp += pre(s["input"], "file")
    elif kind == "blocked" and s["input"].lstrip().startswith("{"):
        name = "invoke_subagent" if "Subagents" in s["input"] else "send_message"
        inp = f'<div class="in"><span class="k">tool call</span><code>{name}</code></div>' + pre(s["input"], "file")
    else:
        inp = f'<div class="in"><span class="k">{INPUT_KEY.get(kind, "input")}</span><code>{esc(s["input"])}</code></div>'
    body = f'<div class="note">{esc(note)}</div>' if note else ""
    out_label = {"prompt": "PreInvocation → lib/approve.py injected:", "blocked": "gate reason:",
                 "hook": "PreInvocation → lib/approve.py injected:"}.get(kind)
    if out_label:
        body += f'<div class="note">{out_label}</div>'
    body += pre(s["output"] or "(no output)")
    return f'<div class="step s-{kind}">{head}{inp}{body}</div>'


def stage_summary(stage, items):
    typed = [s["input"] for s in items if s["kind"] == "prompt"]
    dispatches = []
    for s in items:
        if s["kind"] in ("dispatched", "blocked") and '"Subagents"' in s["input"]:
            for sub in json.loads(s["input"])["Subagents"]:
                dispatches.append((sub["TypeName"], sub.get("Role", ""), s["kind"] == "blocked"))
    files = [s["input"] for s in items if s["kind"] == "file"]
    refused = [s for s in items if s["kind"] in ("blocked", "git-hook")]
    st = states.get(stage, {})
    li = lambda xs: "<ul>" + "".join(f"<li>{x}</li>" for x in xs) + "</ul>" if xs else "<p>—</p>"  # noqa: E731
    col1 = (f'<div class="lbl">You type</div>{li([f"<code>{esc(t)}</code>" for t in typed])}'
            f'<div class="lbl">Supervisor dispatches (invoke_subagent)</div>'
            + li([f"<code>{esc(t)}</code> {esc(r)}" + (' <span class="pill r">refused</span>' if b else "")
                  for t, r, b in dispatches]))
    col2 = (f'<div class="lbl">Files written</div>{li([f"<code>{esc(f)}</code>" for f in files])}'
            f'<div class="lbl">Hook decisions</div><p>{len(refused)} refused · '
            f'{sum(1 for s in items if s["kind"] in ("ran", "dispatched", "file"))} allowed tool calls recorded</p>'
            f'<div class="lbl">Git state after the stage</div><p>branch <code>{esc(st.get("branch", ""))}</code> · HEAD '
            f'<code>{esc(st.get("head", ""))}</code> · ledger rows {st.get("ledger_rows", 0)}</p>'
            + (f'<pre class="file">{esc(st["status"])}</pre>' if st.get("status") else "<p>working tree clean</p>"))
    return f'<div class="stage"><div class="grid2"><div>{col1}</div><div>{col2}</div></div></div>'


def num(stage):
    return stage.split(" · ")[0]


def name(stage):
    return stage.split(" · ", 1)[1]


# ------------------------------------------------------------------ page
phrases = [s for s in steps if s["kind"] == "prompt" and s["input"].lower().startswith("approve ")
           and "approval recorded" in s["output"]]
refused = [s for s in steps if s["kind"] in ("blocked", "git-hook")]
final_log = states[STAGES[-1]]["log"].splitlines()
branch_commits = [line for line in final_log if "(login-rate-limit)" in line]


def sample(script, pred):
    for e in events:
        if e["hook"] == script and pred(e):
            return e
    return None


ev_phrase = sample("approve.py", lambda e: "approval recorded for intent" in e["stdout"])
ev_sub = sample("approve.py", lambda e: e["event"].get("conversationId") != "conv-supervisor"
                and e["event"].get("invocationNum") == 2)
ev_cmd = sample("gate.py", lambda e: "health.py" in json.dumps(e["event"]))
ev_eng = sample("gate.py", lambda e: '"engineer"' in json.dumps(e["event"]) and "deny" in e["stdout"])


def payload(e, title):
    if not e:
        return ""
    return (f'<h3>{title}</h3><div class="grid2"><div><div class="lbl">stdin (the event)</div>'
            f'{pre(json.dumps(e["event"], indent=1, ensure_ascii=False), "file")}</div><div><div class="lbl">stdout '
            f'(the hook\'s answer)</div>{pre(e["stdout"].strip() or "(empty: neutral)", "file")}</div></div>')


nav = ('<nav><b>Overview</b><a href="#about">About this run</a><a href="#glance">At a glance</a>'
       '<a href="#events">The hook events</a><b>Stages</b>'
       + "".join(f'<a href="#st{num(s)}">{esc(s)}</a>' for s in STAGES)
       + '<b>After</b><a href="#blocked">Everything that was refused</a><a href="#repro">Reproduce it</a></nav>')

journey = "".join(
    f'<a class="j{" h" if INTRO[num(s)][3] else ""}" href="#st{num(s)}"><b>{num(s)}</b>{esc(name(s))}</a>' for s in STAGES)
typed_list = "".join(f"<li><code>{esc(s['input'])}</code> <span class='ev'>({esc(s['stage'])})</span></li>"
                     for s in phrases)

sections = []
for stage in STAGES:
    items = [s for s in steps if s["stage"] == stage]
    title, what, you, _h = INTRO[num(stage)]
    sections.append(
        f'<section id="st{num(stage)}" class="stagesec">\n'
        f'<h2><span class="sn">{num(stage)}</span> {esc(name(stage))}: {title}</h2>\n'
        f'<div class="grid2"><div><div class="lbl">What happens</div><p>{what}</p></div>'
        f'<div><div class="lbl">You do</div><p>{you}</p></div></div>\n'
        + stage_summary(stage, items) + "\n" + "".join(step_html(s) for s in items) + "\n</section>")

refused_rows = "".join(
    f"<tr><td>{esc(s['stage'])}</td><td>{esc(s['label'])}</td><td>{esc(s['output'].splitlines()[0] if s['output'] else '')}</td></tr>"
    for s in refused)

CSS = open(os.path.join(HERE, "usage-e2e.css")).read()  # the <style> block shared with the other docs pages

page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta charset="viewport" content="width=device-width, initial-scale=1">
<title>plan-swarm@3.0 end to end on Antigravity: one milestone, every stage</title>
<style>
{CSS}</style></head>
<body><div class="wrap">
{nav}
<main>
<h1>plan‑swarm@3.0 end to end on Antigravity</h1>
<p class="sub">One milestone, <em>login rate limiting</em>, taken from an empty setup to a tagged release: what you type, what the supervisor dispatches, what the hooks decide, and what git ends up holding.</p>
<div class="meta"><span>Plugin 3.0.0 · Antigravity</span><span>Scenario: a small Python app, <code>~/shop</code>, with a bare <code>origin</code></span><span>Concepts: <a href="playbook.html">playbook.html</a> · System: <a href="architecture.html">architecture.html</a> · <a href="ai-dlc.html">ai-dlc.html</a></span></div>

<section id="about">
<div class="callout"><b>How this page was made.</b> <code>examples/e2e_demo.py</code> drove the milestone in a scratch repository and <code>examples/render_usage_e2e.py</code> rendered this page from the captured run. The demo feeds the plan plugin's hooks the JSON events Antigravity sends and runs them the way Antigravity does (<code>python3 lib/approve.py</code> and <code>python3 lib/gate.py</code>, plugin folder as the working directory): <code>PreInvocation</code> before every model call, with <code>conversationId</code>, <code>workspacePaths</code>, <code>transcriptPath</code>, and <code>invocationNum</code>; <code>PreToolUse</code> before every gated tool call, with <code>toolCall {{name, args}}</code> for <code>run_command</code>, <code>write_to_file</code>, <code>replace_file_content</code>, <code>invoke_subagent</code>, and <code>send_message</code>. A tool call runs only when the gate prints nothing or an allow; when the allow carries an <code>overwrite</code> (the <code>$PLAN_LIB</code> expansion) the rewritten command runs. The git hooks installed by <code>swarm-init</code> (<code>pre-commit</code>, <code>pre-merge-commit</code>, <code>pre-push</code>) ran on every real commit and push.
<br><br><b>Real vs example.</b> Hook messages, gate decisions and reasons, script output, git results, test results, the pre-push verdicts, and the CI ledger job are <b>real output</b> of this run. What the agents write (intent, spec, plan, code, audit text, the validator report, the Grill Loop dialogue, and the subagents' replies) is <span class="pill p">example content</span> supplied by the script: no model is called, and the subagents are simulated by sending their tool calls through the same gate. SHAs, nonce ids, and times differ on every run. Paths are shortened to <code>~/shop</code> and <code>&lt;plugin&gt;/lib</code>.</div>
</section>

<section id="glance">
<h2>At a glance</h2>
<div class="kpis">
<div class="kpi"><div class="n">{len(phrases)}</div><div class="l">approval phrases recorded, all typed in the top-level conversation</div></div>
<div class="kpi"><div class="n">{len(branch_commits)}</div><div class="l">commits on <code>swarm/login-rate-limit</code>, each with a ledger row</div></div>
<div class="kpi"><div class="n">{len(refused)}</div><div class="l">attempts refused (shortcuts, premature steps, forged approvals, merges)</div></div>
<div class="kpi"><div class="n">{len(events)}</div><div class="l">hook calls across {len(steps)} captured steps and {len(STAGES)} stages</div></div>
</div>
<div class="journey">{journey}</div>
<p class="ev">Amber stages are where you type an approval phrase.</p>
<h3>Every approval you type in the whole milestone</h3>
<ol>{typed_list}</ol>
<p>Plus your original request, <code>swarm init</code> and <code>Be the supervisor.</code>, your Grill Loop answers, and yes / no to the offered checks. Every other step below is the swarm's.</p>
</section>

<section id="events">
<h2>The hook events</h2>
<p>Four real payloads from this run, exactly as the hooks received and answered them (paths shortened). See <a href="architecture.html">architecture.html</a> for the control plane and <a href="../plugins/plan/hooks.json">hooks.json</a> for the registration.</p>
{payload(ev_phrase, "PreInvocation: the user types an approval phrase in the top-level conversation")}
{payload(ev_sub, "PreInvocation in a subagent conversation: the same phrase, no approval")}
{payload(ev_cmd, "PreToolUse on run_command: $PLAN_LIB expanded through an allow + overwrite")}
{payload(ev_eng, "PreToolUse on invoke_subagent: an engineer before the plan approval")}
</section>

{chr(10).join(sections)}

<section id="blocked">
<h2>Everything that was refused</h2>
<p>Each refusal names the phrase to ask for, or the direct form to use. None suggests a way around the gate. A refused tool call never runs; the supervisor reports the reason and asks you for the phrase.</p>
<table><thead><tr><th style="width:18%">Stage</th><th style="width:34%">Attempt</th><th>Reason given</th></tr></thead><tbody>{refused_rows}</tbody></table>
</section>

<section id="repro">
<h2>Reproduce it</h2>
<pre><code>python3 examples/e2e_demo.py /tmp/swarm-e2e          # writes /tmp/swarm-e2e/transcript.json
python3 examples/render_usage_e2e.py /tmp/swarm-e2e  # rewrites docs/usage-e2e.html
cd /tmp/swarm-e2e/shop &amp;&amp; git log --oneline --graph --all</code></pre>
<p>Run both from the repository root. The demo needs only <code>git</code> and <code>python3</code> (it uses <code>pytest</code> for the scenario's tests when installed, else a stdlib stand-in). It calls no model, uses no network, and touches nothing outside the work directory. See <a href="../examples/README.md">examples/README.md</a>, <a href="walkthrough.html">walkthrough.html</a>, and <a href="../plugins/plan/README.md">the plugin README</a>.</p>
</section>
<footer>plan‑swarm@3.0 end to end on Antigravity · generated from a real run of <code>examples/e2e_demo.py</code> by <code>examples/render_usage_e2e.py</code> · self‑contained, no external assets.</footer>
</main></div></body></html>
"""
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as fh:
    fh.write(page)
print(f"wrote {OUT} ({len(page)} bytes, {len(steps)} steps)")
