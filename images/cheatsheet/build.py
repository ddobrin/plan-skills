#!/usr/bin/env python3
"""Build the plan-swarm@3.0 cheat-sheet poster (Antigravity) as SVG (light, dark) and 2x PNG.

    python3 images/cheatsheet/build.py

Standard library only; the PNGs need headless Chrome (CHROME, default /usr/bin/google-chrome)
and ffmpeg on PATH. Pass --svg-only to skip the PNGs.

Writes images/cheatsheet/plan-swarm-cheatsheet-{light,dark}.{svg,png}.
Pure SVG (no foreignObject), so it renders the same on GitHub, in browsers, and in print.
"""
import os
import sys
import tempfile
from html import escape

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "_build"))
import gifkit  # noqa: E402

W, H = 1600, 1040
SANS = "-apple-system,BlinkMacSystemFont,'SF Pro Text','Segoe UI',Inter,Helvetica,Arial,sans-serif"
MONO = "'SF Mono',ui-monospace,Menlo,Consolas,'DejaVu Sans Mono',monospace"

CSS = f"""
.light{{--bg:#f7f5f0;--panel:#ffffff;--ink:#1d1d1f;--muted:#666a72;--line:#e0dcd3;--soft:#f1eee7;
--amber:#b06f00;--amber-soft:#fff1d6;--blue:#2f5bd3;--blue-soft:#e3eafc;--green:#1f7a4d;--red:#c0392b;
--purple:#7b3fd1;--purple-soft:#efe7fc;--term:#1e1f24;--termink:#f3c56b;--gray:#9aa0a8}}
.dark{{--bg:#121316;--panel:#1b1c20;--ink:#ececec;--muted:#a0a3aa;--line:#30323a;--soft:#22242a;
--amber:#f0b44c;--amber-soft:#3a2d12;--blue:#7c9cff;--blue-soft:#24304f;--green:#5cc98f;--red:#ff7b72;
--purple:#b38cff;--purple-soft:#2c2142;--term:#0b0c0e;--termink:#f3c56b;--gray:#6f747c}}
text{{font-family:{SANS};fill:var(--ink)}}
.m{{font-family:{MONO}}}
.mu{{fill:var(--muted)}}
.h{{font-size:12px;font-weight:700;letter-spacing:.09em;fill:var(--muted)}}
"""


class S:
    def __init__(self):
        self.parts = []

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, size=15, weight=400, cls="", fill=None, anchor="start", mono=False):
        f = f' style="fill:{fill}"' if fill else ""
        c = (cls + (" m" if mono else "")).strip()
        self.add(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}"'
                 f'{f" class=" + chr(34) + c + chr(34) if c else ""}{f}>{escape(s)}</text>')

    def box(self, x, y, w, h, title, num):
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="var(--panel)" stroke="var(--line)"/>')
        self.add(f'<circle cx="{x + 30}" cy="{y + 32}" r="13" fill="var(--blue)"/>')
        self.text(x + 30, y + 37, str(num), 13, 800, anchor="middle", fill="#fff")
        self.text(x + 52, y + 38, title, 19, 750)

    def term(self, x, y, w, s, size=14, note=None):
        """A dark command bar; note is a gray comment right-aligned inside it (SVG collapses runs of spaces)."""
        self.add(f'<rect x="{x}" y="{y - 19}" width="{w}" height="28" rx="7" fill="var(--term)"/>')
        self.text(x + 12, y, s, size, 500, fill="var(--termink)", mono=True)
        if note:
            self.text(x + w - 12, y, note, size - 1, 400, fill="var(--gray)", anchor="end")

    def chip(self, x, y, s, kind="amber", size=12, mono=True, anchor="middle"):
        cw = len(s) * (size * 0.6 if mono else size * 0.55) + 16
        x0 = x - cw / 2 if anchor == "middle" else x
        fill = {"amber": "var(--amber-soft)", "blue": "var(--blue-soft)", "purple": "var(--purple-soft)"}[kind]
        ink = {"amber": "var(--amber)", "blue": "var(--blue)", "purple": "var(--purple)"}[kind]
        self.add(f'<rect x="{x0:.1f}" y="{y - 15}" width="{cw:.1f}" height="22" rx="11" fill="{fill}"/>')
        self.text(round(x0 + cw / 2, 1), y, s, size, 650, fill=ink, mono=mono, anchor="middle")


def lock(s, x, y):
    s.add(f'<g transform="translate({x - 10},{y - 10})"><circle cx="10" cy="10" r="11" fill="var(--amber)" stroke="var(--panel)" stroke-width="2.5"/>'
          f'<rect x="5.6" y="9" width="8.8" height="6.6" rx="1.3" fill="var(--panel)"/>'
          f'<path d="M7.4 9.2 V7.4 a2.6 2.6 0 0 1 5.2 0 V9.2" fill="none" stroke="var(--panel)" stroke-width="1.6"/></g>')


# (stage, who acts: a role subagent by its invoke_subagent TypeName, or "you", artifact, phrase)
LOOP = [
    ("Intent", "product-owner", "intent.md", "approve intent"),
    ("Research", "research subagent", "§ Codebase context", None),
    ("Spec", "product-owner", "spec.md", "approve spec"),
    ("Plan", "architect", "plan.md + tier", None),
    ("Approve", "you", "plan committed", "approve plan"),
    ("Build", "engineer ×≤5", "worktrees → squash", None),
    ("Audit", "auditor", "audit.md", None),
    ("Commit", "auditor", "group commit", "approve commit"),
    ("PR", "supervisor", "push + PR", "approve pr"),
    ("Release", "supervisor", "tag", "approve release"),
]


def poster(theme):
    s = S()
    s.add(f'<rect width="{W}" height="{H}" fill="var(--bg)"/>')
    # header
    s.text(48, 86, "plan‑swarm@3.0 · cheat sheet · Antigravity", 38, 800)
    s.text(48, 118, "From intent to release with role subagents and six approval phrases. Antigravity hooks enforce the phrases; git keeps the record.", 17, 400, "mu")
    s.add(f'<rect x="{W - 200}" y="58" width="152" height="34" rx="17" fill="var(--blue-soft)"/>')
    s.text(W - 124, 81, "plugin 3.0.0", 15, 700, fill="var(--blue)", anchor="middle")

    # row 1
    bw, by, bh = 485, 150, 196
    xs = [48, 48 + bw + 24, 48 + 2 * (bw + 24)]
    s.box(xs[0], by, bw, bh, "Set up once", 1)
    s.term(xs[0] + 20, by + 80, bw - 40, 'ln -s "$PWD/plugins/plan" ~/.gemini/config/plugins/plan', 12.5)
    s.text(xs[0] + 20, by + 111, "Then open a new conversation: hooks load at its start.", 14.5)
    s.term(xs[0] + 20, by + 148, bw - 40, "swarm init", 13.5, note="say it · settings + 3 git hooks")
    s.text(xs[0] + 20, by + 180, "Then fill AGENTS.md, review plans/swarm.md, commit both yourself.", 13.5, 400, "mu")

    s.box(xs[1], by, bw, bh, "Run the supervisor", 2)
    s.term(xs[1] + 20, by + 80, bw - 40, "be the supervisor", 15, note="say it")
    s.text(xs[1] + 20, by + 114, "in a top-level conversation opened on the repository.", 14.5)
    s.text(xs[1] + 20, by + 140, "Every role runs as a subagent with its own context.", 14.5, 400, "mu")
    s.text(xs[1] + 20, by + 162, "Type the approval phrases in this same conversation.", 14.5, 400, "mu")
    s.text(xs[1] + 20, by + 184, "Resume any time with the same words: state lives in plans/.", 14.5, 400, "mu")

    s.box(xs[2], by, bw, bh, "Call one role yourself", 3)
    s.term(xs[2] + 20, by + 80, bw - 40, 'invoke_subagent TypeName: "architect"', 14, note="a subagent")
    s.text(xs[2] + 20, by + 113, "or load its skill: use the architect skill to plan <spec>", 14.5)
    s.term(xs[2] + 20, by + 148, bw - 40, "validate this spec · simplify this file", 14, note="a skill")
    s.text(xs[2] + 20, by + 180, "Skills load into your conversation; subagents get their own.", 13.5, 400, "mu")

    # row 2: the loop
    ly, lh = 372, 300
    s.add(f'<rect x="48" y="{ly}" width="{W - 96}" height="{lh}" rx="16" fill="var(--panel)" stroke="var(--line)"/>')
    s.text(72, ly + 34, "THE LOOP", 12, 700, "h")
    s.text(160, ly + 34, "amber = you type the phrase · blue = a subagent works · stages 6–8 repeat per group · offered checks: deliberators, validators, simplifier, recap", 13, 400, "mu")
    s.add('<defs><marker id="a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
          '<path d="M0,0 L10,5 L0,10 z" fill="var(--gray)"/></marker>'
          '<marker id="r" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
          '<path d="M0,0 L10,5 L0,10 z" fill="var(--red)"/></marker></defs>')
    x0, step, cy = 128, 149, ly + 118
    for i, (name, agent, art, phrase) in enumerate(LOOP):
        x = x0 + i * step
        if i < len(LOOP) - 1:
            s.add(f'<line x1="{x + 33}" y1="{cy}" x2="{x + step - 36}" y2="{cy}" stroke="var(--gray)" stroke-width="2.5" marker-end="url(#a)"/>')
        gate = phrase is not None
        s.add(f'<circle cx="{x}" cy="{cy}" r="30" fill="{"var(--amber-soft)" if gate else "var(--blue-soft)"}" '
              f'stroke="{"var(--amber)" if gate else "var(--blue)"}" stroke-width="3"/>')
        s.text(x, cy + 6, str(i + 1), 18, 800, anchor="middle", fill="var(--amber)" if gate else "var(--blue)")
        if gate:
            lock(s, x + 22, cy - 22)
            s.chip(x, cy - 52, phrase, "amber", 12)
        s.text(x, cy + 58, name, 16, 750, anchor="middle")
        s.text(x, cy + 79, agent, 12, 500, "mu" if agent == "you" else "", fill=None if agent == "you" else "var(--blue)",
               anchor="middle", mono=agent != "you")
        s.text(x, cy + 98, art, 12, 400, "mu", anchor="middle", mono=True)
    # feedback arcs, routed below the labels
    ax = lambda i: x0 + i * step  # noqa: E731
    top = cy + 110
    # Path A above Build and Audit (neither carries a phrase chip)
    s.add(f'<path d="M{ax(6) - 14},{cy - 27} C{ax(6) - 30},{cy - 74} {ax(5) + 30},{cy - 74} {ax(5) + 14},{cy - 29}" fill="none" stroke="var(--red)" stroke-width="2.4" stroke-dasharray="6 4" marker-end="url(#r)"/>')
    s.text((ax(5) + ax(6)) / 2, cy - 70, "Path A · FAIL → fix, ≤3 rounds", 12, 700, fill="var(--red)", anchor="middle")
    # Path B below the labels, back to the architect
    s.add(f'<path d="M{ax(6)},{top} C{ax(6)},{top + 58} {ax(3)},{top + 58} {ax(3)},{top + 4}" fill="none" stroke="var(--red)" stroke-width="2.4" stroke-dasharray="3 4" marker-end="url(#r)"/>')
    s.text((ax(3) + ax(6)) / 2, top + 64, "Path B · plan impossible → architect re-plans · approve plan again", 12, 700, fill="var(--red)", anchor="middle")
    s.chip(ax(8), top + 18, "review findings → fix group (6–8)", "purple", 11.5, False)
    s.chip(ax(1) + 30, top + 18, "next intent starts the loop again", "blue", 11.5, False)

    # row 3
    ry, rh = 694, 292
    s.box(xs[0], ry, bw, rh, "The six approval phrases", 4)
    rows = [("approve intent <slug> as <m>", "milestone + branch"), ("approve spec <m>", "spec committed"),
            ("approve plan <m> [tier=…]", "engineers unblocked"), ("approve commit <m> g<n>", "one group commit"),
            ("approve pr <m>", "record + push + PR"), ("approve release <version>", "tag the release")]
    for k, (p, what) in enumerate(rows):
        y = ry + 82 + k * 32
        s.add(f'<rect x="{xs[0] + 20}" y="{y - 19}" width="262" height="26" rx="6" fill="var(--term)"/>')
        s.text(xs[0] + 30, y - 1, p, 12.5, 500, fill="var(--termink)", mono=True)
        s.text(xs[0] + 296, y - 1, what, 13.5)
    s.text(xs[0] + 20, ry + rh - 14, "Your whole message, top-level conversation. Single use, 15 min.", 12.5, 400, "mu")

    s.box(xs[1], ry, bw, rh, "Rules that always hold", 5)
    rules = ["Type phrases in the top-level conversation; a phrase", "in a subagent prompt or send_message never counts.",
             "“yes” or “looks good” never approves anything.",
             "Approvals are tied to the current commit (HEAD).",
             "Only the auditor commits; reviewers never edit.",
             "Checks are offered; the tier only recommends.",
             "A code owner merges; the swarm never pushes main."]
    yy = ry + 80
    for k, r in enumerate(rules):
        bullet = k != 1
        if bullet:
            s.add(f'<circle cx="{xs[1] + 26}" cy="{yy - 5}" r="3.2" fill="var(--blue)"/>')
        s.text(xs[1] + 40, yy, r, 14.5)
        yy += 26 if k != 0 else 22
    s.text(xs[1] + 20, ry + rh - 14, "Local hooks stop shortcuts; branch protection is the authority.", 12.5, 400, "mu")

    s.box(xs[2], ry, bw, rh, "If you see …", 6)
    tro = [("enforcement OFF", "new conversation; check the install"),
           ("$PLAN_LIB unexpanded", "hooks not running: treat as enforcement off"),
           ("no valid approval", "type the exact phrase the message names"),
           ("stale (HEAD moved)", "approve the new diff again"),
           ("engineers cannot start", "type approve plan <m> first"),
           ("Approval NOT recorded", "read the reason; retype as whole message"),
           ("3 failed audit rounds", "re-plan, drop the task, or take over")]
    for k, (m_, act) in enumerate(tro):
        y = ry + 80 + k * 28
        s.text(xs[2] + 20, y, m_, 12, 600, fill="var(--red)", mono=True)
        s.text(xs[2] + 204, y, act, 13)
    s.text(xs[2] + 20, ry + rh - 14, "Open the swarm repo as the workspace, or dispatch rules don’t apply.", 12.5, 400, "mu")

    # footer
    s.text(48, H - 22, "Docs: docs/playbook.html · docs/usage-e2e.html · docs/ai-dlc.html · plugins/plan/README.md · SUBAGENTS.md", 13, 400, "mu")
    s.text(W - 48, H - 22, "plugin folder plugins/plan → ~/.gemini/config/plugins/plan", 13, 400, "mu", anchor="end")
    body = "\n".join(p for p in s.parts if p)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="{theme}" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'<style>{CSS}</style>\n{body}\n</svg>\n')


def main(argv):
    for theme in ("light", "dark"):
        svg = os.path.join(HERE, f"plan-swarm-cheatsheet-{theme}.svg")
        with open(svg, "w", encoding="utf-8") as fh:
            fh.write(poster(theme))
        if "--svg-only" in argv:
            print(theme, os.path.getsize(svg), "bytes svg")
            continue
        png = os.path.join(HERE, f"plan-swarm-cheatsheet-{theme}.png")
        with tempfile.TemporaryDirectory(prefix="cheatsheet-") as tmp:
            raw = os.path.join(tmp, "raw.png")
            gifkit.shoot(svg, "", raw, W, H, scale=2)
            gifkit.save_png(raw, png)  # recompress; stays 2x (3200x2080)
        print(theme, os.path.getsize(svg), "bytes svg ·", os.path.getsize(png), "bytes png (2x)")


if __name__ == "__main__":
    main(sys.argv[1:])
