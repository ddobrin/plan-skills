#!/usr/bin/env python3
"""Build the terminal-replay GIF: one plan-swarm@3.0 milestone as it looks in an Antigravity conversation.

    python3 images/terminal-replay/build.py [TRANSCRIPT]

Standard library only; needs headless Chrome (CHROME, default /usr/bin/google-chrome) and
ffmpeg on PATH (see images/_build/gifkit.py).

TRANSCRIPT defaults to /tmp/swarm-e2e/transcript.json. When it is missing, the build runs
`python3 examples/e2e_demo.py` from the repository root to regenerate it. That driver feeds
the plugin's real hooks (lib/approve.py, lib/gate.py) the JSON events Antigravity sends and runs the
real scripts, git, and tests, so the commands, hook decisions, approval messages, and git/test
output in the replay are copied from the transcript. The supervisor's narration lines (◆) and
the agent-written content are illustrative.

Writes images/terminal-replay/{terminal.html, plan-swarm-terminal.gif, plan-swarm-terminal.png}.
"""
import json
import os
import re
import subprocess
import sys
import textwrap

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(HERE, "..", "_build"))
import gifkit  # noqa: E402

W, H = 960, 600
COLS = 104
ROWS = 24
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
TRANSCRIPT = os.path.abspath(ARGS[0] if ARGS else "/tmp/swarm-e2e/transcript.json")
PLAN_LIB = os.path.join(ROOT, "plugins", "plan", "lib")
CHANGED = "A pre-tool hook changed the arguments ($PLAN_LIB → …/plugins/plan/lib)"
DENIED = "tool call denied by pre-tool hook: "


def load():
    if not os.path.exists(TRANSCRIPT):
        subprocess.run([sys.executable, os.path.join("examples", "e2e_demo.py"), os.path.dirname(TRANSCRIPT)],
                       cwd=ROOT, check=True)
    with open(TRANSCRIPT, encoding="utf-8") as fh:
        steps = json.load(fh)
    work = os.path.dirname(os.path.abspath(TRANSCRIPT))
    for s in steps:
        for key in ("input", "output"):
            text = s.get(key) or ""
            text = text.replace(PLAN_LIB, "…/plugins/plan/lib")
            text = text.replace(os.path.join(work, "shop"), "~/shop").replace(os.path.join(work, "origin.git"), "origin.git")
            s[key] = text
    return steps


class Transcript:
    """Look up steps of the e2e transcript; fail loudly when the demo changed shape."""

    def __init__(self, steps):
        self.steps = steps

    def find(self, label=None, kind=None, inp=None, nth=0):
        hits = [s for s in self.steps
                if (label is None or s["label"].startswith(label))
                and (kind is None or s["kind"] == kind)
                and (inp is None or inp in s["input"])]
        if len(hits) <= nth:
            raise SystemExit(f"transcript has no step label={label!r} kind={kind!r} input~{inp!r} #{nth}; "
                             "update images/terminal-replay/build.py for the new demo")
        return hits[nth]

    def out(self, *a, **k):
        return self.find(*a, **k)["output"].strip()

    def js(self, *a, **k):
        return json.loads(self.out(*a, **k))


def wrap(kind, text, first="", rest=""):
    lines = []
    for para in text.splitlines() or [""]:
        for chunk in textwrap.wrap(para, COLS - len(first)) or [""]:
            lines.append([kind, (first if not lines else rest) + chunk])
    return lines


def recorded(text):
    """The approval hook's message, without its 'Next:' hint."""
    return text.split(" Next:")[0]


def short_cmd(cmd, width=COLS - 18):
    return cmd if len(cmd) <= width else cmd[:width - 1] + "…"


def beats(steps):
    t = Transcript(steps)
    B = []

    def beat(lines, dur=900, typing=None):
        B.append(dict(lines=lines, dur=dur, typing=typing))

    def tool(cmd):
        return ["tool", "▸ run_command  " + short_cmd(cmd)]

    def agent(type_name, role, extra=""):
        return ["agent", f'▸ invoke_subagent  TypeName: "{type_name}" · {role}{extra}']

    def ok(text):
        return wrap("ok", text, "  ⎿  ", "     ")

    def deny(text):
        return wrap("deny", DENIED + text, "  ⎿  ", "     ")

    def say(text):
        return ["sup", "◆ " + text]

    # 0 · Setup: a new top-level conversation on the swarm repository
    start = t.find(kind="prompt", label="you type: Be the supervisor")
    beat([["dim", "~/shop · new top-level Antigravity conversation · plugin plan 3.0.0"]], 700)
    beat([["you", "› "]], 100, typing=start["input"])
    beat(wrap("hook", start["output"], "  ⎿  PreInvocation · ", "     "), 1700)
    health = t.js(inp="health.py\" --status")
    beat([tool(t.find(inp="health.py\" --status")["input"]), ["hook", "  ⎿  " + CHANGED],
          ["out", f'  ⎿  "enforcement": "{health["enforcement"]}", "mode": "{health["mode"]}", '
                  f'"git_hook": "{health["git_hook"]}", "plugin_version": "{health["plugin_version"]}"'],
          say("Enforcement is active. No milestones yet. What would you like to change?")], 1500)

    # 1 · Intent
    request = t.find(kind="prompt", label="you type: Login gets")
    beat([["you", "› "]], 100, typing=request["input"])
    intent_file = t.find(kind="file", label="product-owner (intent mode)")["input"]
    tier0 = t.js(inp="--stage intent")
    beat([agent("product-owner", "Intent writer"), ["out", f"  ⎿  wrote {intent_file}"],
          tool(t.find(inp="--stage intent")["input"]), ["hook", "  ⎿  " + CHANGED],
          ["out", f'  ⎿  "tier": "{tier0["tier"]}"']], 1500)
    phrase = t.find(kind="prompt", label="you type: approve intent")
    beat([say(f"Proposed tier: {tier0['tier']}. To accept the intent, type:"), ["phrase", phrase["input"]]], 1300)
    beat([["you", "› "]], 100, typing=phrase["input"])
    beat(wrap("ok", recorded(phrase["output"]), "  ⎿  PreInvocation · ", "     "), 1800)

    # 2 · Accept → branch, commit, research
    beat([tool("git switch -c swarm/login-rate-limit"), ["out", "  ⎿  " + t.out(inp="git switch -c")],
          agent("auditor", "Committer"), ["out", "  ⎿  " + t.out(label="auditor: artifact commit").splitlines()[0]],
          agent("self", "Codebase researcher (read-only)"), ["out", "  ⎿  returned ## Codebase context → appended to intent.md"]], 1800)

    # 4 · Spec: Grill Loop, a planted phrase refused, the real approval
    qs = t.out(label="product-owner asks").splitlines()
    answer = next(q for q in qs if q.startswith("you answer:")).split(":", 1)[1].strip()
    beat([agent("product-owner", "Spec writer"), say("The product owner has questions (ask_question):")]
         + [["out", "  " + q] for q in qs if q[:2] in ("1.", "2.", "3.")], 1600)
    beat([["you", "› "]], 80, typing=answer)
    planted = t.find(kind="blocked", label="product-owner tries to send_message")
    beat([["out", "  ⎿  wrote spec.md (3 scenarios, Policy Concerns: none open)"],
          ["agent", '▸ send_message  product-owner → supervisor: "approve spec login-rate-limit"']]
         + deny(planted["output"]), 2400)
    phrase = t.find(kind="prompt", label="you type: approve spec")
    beat([say("A phrase only counts when you type it here. You declined the spec-validator (logged). Type:"),
          ["phrase", phrase["input"]]], 1400)
    beat([["you", "› "]], 100, typing=phrase["input"])
    beat(wrap("ok", recorded(phrase["output"]), "  ⎿  PreInvocation · ", "     "), 1500)

    # 5 · Plan: tier rises, an early engineer dispatch is refused
    tier = t.js(inp="--stage plan")
    beat([agent("architect", "Planner"), ["out", "  ⎿  wrote plan.md: Group 1 (1.A, 1.B in parallel) → Group 2 (2.A)"],
          tool(t.find(inp="--stage plan")["input"]), ["hook", "  ⎿  " + CHANGED],
          ["warn", f'  ⎿  "tier": "{tier["tier"]}" ({"; ".join(tier["reasons"])})']], 1900)
    early = t.find(kind="blocked", label="supervisor tries to dispatch an engineer")
    beat([agent("engineer", "Builder 1.A")] + deny(early["output"]), 2300)
    phrase = t.find(kind="prompt", label="you type: approve plan")
    beat([say("Tier raised to critical; the plan-validator found 0 confirmed issues. Review spec.md and plan.md, then type:"),
          ["phrase", phrase["input"]]], 1400)
    beat([["you", "› "]], 100, typing=phrase["input"])
    beat(wrap("ok", recorded(phrase["output"]), "  ⎿  PreInvocation · ", "     "), 1500)

    # 7–8 · Build in worktrees, audit
    squash = t.js(label="supervisor: integrate the group")
    tests = t.out(label="auditor runs the tests from AGENTS.md").splitlines()[-1]
    wt = t.find(label="supervisor: worktree for 1.A")
    wt_b = t.js(label="supervisor: worktree for 1.B")
    beat([tool(wt["input"]), ["hook", "  ⎿  " + CHANGED],
          ["out", f'  ⎿  "branch": "{json.loads(wt["output"])["branch"]}", "created": true   (1.B: {wt_b["branch"]})'],
          agent("engineer", "Builder 1.A", '  +  "engineer" · Builder 1.B   (one call)'),
          ["out", "  ⎿  both done test-first, WIP commits in their worktrees"],
          tool(t.find(label="supervisor: integrate the group")["input"]),
          ["out", f"  ⎿  squashed {', '.join(squash['squashed'])} · {len(squash['files'])} files staged, not committed"],
          agent("auditor", "Group 1 auditor"), ["out", f"  ⎿  python3 -m pytest -q → {tests} · Group 1 · Round 1 · PASS"]], 2400)

    # 9 · Commit gate
    sneak = t.find(kind="blocked", label="auditor tries before your approval")
    beat([["tool", "▸ run_command  (auditor)  " + short_cmd(sneak["input"], COLS - 28)]] + deny(sneak["output"]), 2300)
    phrase = t.find(kind="prompt", label="you type: approve commit login-rate-limit g1")
    beat([say("The gate needs your approval for group 1. Type:"), ["phrase", phrase["input"]]], 1100)
    beat([["you", "› "]], 100, typing=phrase["input"])
    beat(wrap("ok", recorded(phrase["output"]), "  ⎿  PreInvocation · ", "     ")
         + [["out", "  ⎿  " + t.out(label="auditor: group commit (both").splitlines()[0]],
            ["dim", "  …  group 2 the same way → " + t.out(label="auditor: group commit", nth=1).splitlines()[0]]], 2200)

    # 11 · Pull request
    early_push = t.find(kind="blocked", label="supervisor tries to push before approval")
    beat([tool(early_push["input"])] + deny(early_push["output"])
         + [say("To open the pull request, type:"), ["phrase", "approve pr login-rate-limit"]], 2000)
    phrase = t.find(kind="prompt", label="you type: approve pr")
    beat([["you", "› "]], 100, typing=phrase["input"])
    push = t.out(label="supervisor: push (the pre-push").splitlines()
    beat(wrap("ok", recorded(phrase["output"]), "  ⎿  PreInvocation · ", "     ")
         + [agent("auditor", "Committer (ledger-only)"),
            ["out", "  ⎿  " + t.out(label="auditor: commit the PR approval").splitlines()[0]],
            tool("git push -u origin swarm/login-rate-limit"), ["out", "  ⎿  " + push[-1].strip()],
            tool(t.find(label="gh pr create")["input"]),
            ["hook", "  ⎿  " + CHANGED],
            ["out", "  ⎿  (no gh in this demo: the supervisor prints the PR title and body instead)"],
            ["out", "  ⎿  PR: " + t.out(label="PR title (lib/prbody.py)")],
            ["ok", "  ⎿  CI ledger job: " + t.out(kind="ci")]], 3000)
    merge = t.find(kind="blocked", label="an agent tries to merge the PR")
    beat([tool(merge["input"])] + deny(merge["output"])
         + [["dim", "  …  a code owner reviews and merges the PR on GitHub"]], 1800)

    # 12 · Release
    phrase = t.find(kind="prompt", label="you type: approve release")
    switch = t.find(label="supervisor: switch to the default branch")
    pull = t.find(label="supervisor: update it")
    beat([tool(switch["input"]), ["out", "  ⎿  " + switch["output"].strip()],
          tool(pull["input"]), ["out", "  ⎿  " + " · ".join(pull["output"].splitlines()[:2])],
          say("Every milestone for v1.0.0 is merged. To tag the release, type:"), ["phrase", phrase["input"]]], 1500)
    beat([["you", "› "]], 100, typing=phrase["input"])
    tag = t.find(label="supervisor: tag")
    beat(wrap("ok", recorded(phrase["output"]), "  ⎿  PreInvocation · ", "     ")
         + [tool(tag["input"]), say("Tagged v1.0.0 locally. Push the tag?")], 1400)
    yes = t.find(kind="prompt", label="you type: Yes, push the tag")
    beat([["you", "› "]], 100, typing=yes["input"])
    push_tag = t.find(label="supervisor: push the tag")
    beat([tool(push_tag["input"]), ["out", "  ⎿  " + push_tag["output"].splitlines()[-1].strip()],
          say("v1.0.0 is released. Every commit on the way carried its approval in approvals.md.")], 3200)
    return B


def fit(line):
    """Wrap a line wider than the terminal, indenting continuations under its text."""
    kind, text = line
    if kind == "phrase" or len(text) <= COLS:
        return [line]
    lead = len(text) - len(text.lstrip(" "))
    marker = text.lstrip(" ")[:3] if text.lstrip(" ")[:1] in "⎿▸◆…" else ""
    indent = " " * (lead + len(marker))
    parts = textwrap.wrap(text.strip(), COLS - len(indent))
    return [[kind, (" " * lead) + parts[0]]] + [[kind, indent + p] for p in parts[1:]]


def frames(B, speed=0.8):
    """Return (lines, frames): each frame shows lines[:n], plus a partly typed `tail` while typing."""
    lines, out = [], []
    for b in B:
        if b["typing"]:
            text = b["typing"]
            for k in (1, 2):
                out.append(dict(n=len(lines), tail="› " + text[:round(len(text) * k / 3)] + "▌", dur=130))
            lines.append(["you", "› " + text])
            out.append(dict(n=len(lines), dur=400))
        else:
            lines += [piece for line in b["lines"] for piece in fit(line)]
            out.append(dict(n=len(lines), dur=max(600, round(b["dur"] * speed / 10) * 10)))
    out.append(dict(n=len(lines), card=True, dur=3200))
    return lines, out


HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>plan-swarm terminal replay (Antigravity)</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:960px;height:600px;overflow:hidden;background:#e9e6df;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Inter,Helvetica,Arial,sans-serif}
#win{position:absolute;left:20px;top:16px;width:920px;height:542px;background:#16171b;border-radius:12px;overflow:hidden;box-shadow:0 14px 40px rgba(0,0,0,.28)}
#bar{height:34px;background:#24252b;display:flex;align-items:center;padding:0 14px;gap:8px}
#bar i{width:12px;height:12px;border-radius:50%;display:inline-block}
#bar span{flex:1;text-align:center;color:#9a9ca3;font-size:12.5px;margin-right:52px}
#term{position:absolute;top:34px;left:0;right:0;bottom:0;padding:12px 16px;font:12.5px/19.5px "SF Mono",ui-monospace,Menlo,"DejaVu Sans Mono",monospace;color:#d7d8dc;overflow:hidden;display:flex;flex-direction:column;justify-content:flex-end}
.l{white-space:pre}
.dim{color:#7d808a}.sup{color:#eceef2}.you{color:#f3c56b}.agent{color:#8fb0ff}.tool{color:#c9cbd3}
.out{color:#9fa2ab}.ok{color:#6fd39b}.deny{color:#ff8a80}.warn{color:#f3c56b}.hook{color:#b8a6ff}
.phrase{color:#16171b;background:#f3c56b;display:inline-block;border-radius:4px;padding:0 6px;margin-left:30px}
#cap{position:absolute;left:24px;right:24px;bottom:12px;font-size:11.5px;color:#6b6f76;text-align:center}
#card{position:absolute;inset:0;display:none;align-items:center;justify-content:center;background:rgba(22,23,27,.78)}
#card div{background:#fff;border-radius:16px;padding:26px 32px;width:580px}
#card h1{font-size:25px;letter-spacing:-.01em;color:#1d1d1f}
#card p{color:#5f6368;font-size:14.5px;margin-top:8px;line-height:1.5}
#card code{display:inline-block;margin:12px 8px 0 0;font:13px "SF Mono",ui-monospace,Menlo,"DejaVu Sans Mono",monospace;background:#16171b;color:#f3c56b;border-radius:7px;padding:6px 10px}
</style></head><body>
<div id="win"><div id="bar"><i style="background:#ff5f57"></i><i style="background:#febc2e"></i><i style="background:#28c840"></i>
<span>Antigravity · ~/shop · top-level conversation · supervisor</span></div><div id="term"></div>
<div id="card"><div><h1>One milestone, six phrases</h1><p>The supervisor dispatched every role as a subagent with invoke_subagent. You typed the approvals in the top-level conversation; the Antigravity hooks and git hooks refused everything else, and every commit carried the approval that authorized it.</p><code>swarm init</code><code>be the supervisor</code></div></div></div>
<div id="cap">Condensed from examples/e2e_demo.py (real hooks, scripts, git, tests): commands, hook decisions and output verbatim; ◆ narration and agent text illustrative.</div>
<script>
const LINES = __LINES__;
const FRAMES = __FRAMES__;
const ROWS = __ROWS__;
const P = new URLSearchParams(location.hash.slice(1));
const fr = FRAMES[Math.min(+P.get("f") || 0, FRAMES.length - 1)];
const shown = LINES.slice(0, fr.n).concat(fr.tail ? [["you", fr.tail]] : []);
const esc = s => s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
const term = document.getElementById("term");
term.innerHTML = shown.slice(-ROWS).map(([k, t]) => k === "phrase"
  ? `<div class="l"><span class="phrase">${esc(t.trim())}</span></div>` : `<div class="l ${k}">${esc(t)}</div>`).join("");
if (fr.card) document.getElementById("card").style.display = "flex";
</script></body></html>"""


def main():
    steps = load()
    lines, fr = frames(beats(steps))
    page = os.path.join(HERE, "terminal.html")
    with open(page, "w", encoding="utf-8") as fh:
        fh.write(HTML.replace("__LINES__", json.dumps(lines, ensure_ascii=False))
                 .replace("__FRAMES__", json.dumps(fr)).replace("__ROWS__", str(ROWS)))
    if "--html-only" in sys.argv:
        print(f"wrote terminal.html ({len(fr)} frames, {sum(f['dur'] for f in fr) / 1000:.1f}s)")
        return
    # The GIF is captured at 1×: hinted 1× text compresses about twice as well as 2× frames scaled
    # down (every scroll repaints the whole terminal, so each frame is a near-full rectangle).
    tmp, pngs = gifkit.render_frames(page, [f"f={i}" for i in range(len(fr))], W, H, scale=1)
    try:
        durations = [f["dur"] for f in fr]
        size = gifkit.save_gif(pngs, durations, os.path.join(HERE, "plan-swarm-terminal.gif"), W, H)
        still = max(i for i, f in enumerate(fr) if not f.get("card"))
        big = os.path.join(tmp, "still.png")
        gifkit.shoot(page, f"f={still}", big, W, H, scale=2)
        png = gifkit.save_png(big, os.path.join(HERE, "plan-swarm-terminal.png"), W, H)
    finally:
        gifkit.cleanup(tmp)
    print(f"terminal: {len(fr)} frames, {sum(durations) / 1000:.1f}s, GIF {size / 1e6:.2f} MB, PNG {png / 1e3:.0f} KB")


if __name__ == "__main__":
    main()
