#!/usr/bin/env python3
"""End-to-end demo of plan-swarm@3.0 on Antigravity: one milestone from setup to release.

Usage (from the repository root):
    python3 examples/e2e_demo.py [WORKDIR]      (default WORKDIR: /tmp/swarm-e2e)

Creates a small Python project with a bare `origin` under WORKDIR, installs the
swarm with lib/swarm_init.py, and drives the milestone "login-rate-limit" through
every stage: intent, research, spec, plan, worktree engineers + squash, audit,
commit, PR push, and release tag.

The plugin's hooks are fed the JSON events Antigravity sends, run the way Antigravity runs
them (`python3 lib/approve.py` / `python3 lib/gate.py` with the plugin folder as
the working directory):

* PreInvocation (before every model call) -> lib/approve.py, with conversationId,
  workspacePaths, transcriptPath, invocationNum. What "you type" goes through
  this hook.
* PreToolUse (before every gated tool call) -> lib/gate.py, with toolCall
  {name, args} for run_command (CommandLine, Cwd), write_to_file /
  replace_file_content (TargetFile), invoke_subagent (Subagents[] with TypeName,
  Role, Prompt), and send_message (Recipient, Message).

A tool call runs only if the gate prints nothing or an allow; when the allow
carries an overwrite (the $PLAN_LIB expansion) the overwritten CommandLine runs.
A deny is recorded with its reason and the call does not run. The git hooks that
swarm-init installs (pre-commit, pre-merge-commit, pre-push) run on every real
commit and push. So hook decisions, script output, git results, and test results
are real. What the agents would write (intent, spec, plan, code, audit text, and
the subagents' own replies) is example content supplied by this script; no model
is called and no network is used.

Outputs (all under WORKDIR):
    transcript.json     captured steps: stage, label, kind, input, output, exit, note
    hook-events.jsonl   every hook payload sent and the hook's raw stdout
    git-state.json      branch / HEAD / working-tree state at the end of each stage
    shop/, origin.git   the scratch repository and its bare remote

Standard library only. Local test driver: commands are fixed strings, not user input.
"""
import datetime as dt
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(os.path.dirname(HERE), "plugins", "plan")
LIB = os.path.join(PLUGIN, "lib")
BASE = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/swarm-e2e")
REPO, ORIGIN = os.path.join(BASE, "shop"), os.path.join(BASE, "origin.git")
BRAIN = os.path.join(BASE, "antigravity", "brain")  # stand-in for Antigravity's per-conversation transcripts
M = "login-rate-limit"
MD = f"plans/active_milestones/{M}"
TODAY = dt.datetime.now(dt.timezone.utc).date().isoformat()
INTENT_FILE = f"plans/intents/{TODAY}-login-rate-limit.md"
HAVE_PYTEST = importlib.util.find_spec("pytest") is not None
TEST_CMD = "python3 -m pytest -q" if HAVE_PYTEST else "python3 run_tests.py"

if os.path.realpath(os.getcwd()).startswith(os.path.realpath(BASE)):
    raise SystemExit("Run this from the plan-skills repository root, not from inside WORKDIR.")

# A clean, reproducible git environment: no global/system config (a global
# core.hooksPath would bypass the hooks swarm-init installs), no test overrides.
env = {k: v for k, v in os.environ.items()
       if not k.startswith("GIT_") and k not in ("PLAN_SWARM_TEST", "PLAN_SWARM_STORE", "PLAN_LIB")}
steps, events, states = [], [], {}

shutil.rmtree(BASE, ignore_errors=True)
os.makedirs(REPO)
os.makedirs(BRAIN)
_gitconfig = os.path.join(BASE, "gitconfig")
open(_gitconfig, "w").close()
env.update(GIT_CONFIG_GLOBAL=_gitconfig, GIT_CONFIG_NOSYSTEM="1")


# --------------------------------------------------------------------------
# recording helpers

def rec(stage, label, kind, inp, out, code=None, note=""):
    steps.append(dict(stage=stage, label=label, kind=kind, input=inp,
                      output=(out or "").rstrip("\n"), exit=code, note=note))


def sh(cmd, cwd=REPO, check=True):
    p = subprocess.run(cmd, shell=True, cwd=cwd, env=env, capture_output=True, text=True)
    if check and p.returncode:
        raise SystemExit(f"FAILED: {cmd}\n{p.stdout}\n{p.stderr}")
    return p


def rel(path):
    return os.path.relpath(path, REPO) if path.startswith(REPO + os.sep) else path


def snapshot(stage):
    """git state at the end of a stage (for the stage cards in docs/usage-e2e.html)."""
    branch = sh("git symbolic-ref --quiet --short HEAD", check=False).stdout.strip() or "(detached)"
    states[stage] = {
        "branch": branch,
        "head": sh("git log -1 --format='%h %s'", check=False).stdout.strip(),
        "status": sh("git status --short", check=False).stdout.rstrip(),
        "log": sh("git log --format='%h %s' -12", check=False).stdout.rstrip(),
        "ledger_rows": sum(1 for line in open(os.path.join(REPO, MD, "approvals.md"))
                           if line.startswith("| 20")) if os.path.exists(os.path.join(REPO, MD, "approvals.md")) else 0,
    }


# --------------------------------------------------------------------------
# Antigravity conversations and hooks

class Conversation:
    """One Antigravity conversation: the top-level one (where the user types) or a subagent."""

    def __init__(self, cid, parent="", role="", prompt=""):
        self.id, self.parent, self.role = cid, parent, role
        self.invocations, self.step_index, self.last_input = 0, 0, ""
        self.transcript = os.path.join(BRAIN, cid, ".system_generated", "logs", "transcript_full.jsonl")
        os.makedirs(os.path.dirname(self.transcript), exist_ok=True)
        open(self.transcript, "w").close()
        if parent:  # a subagent's conversation starts with the parent's message
            self._append({"type": "SYSTEM_MESSAGE", "source": "SYSTEM",
                          "content": f"[Message] sender={parent} priority=MESSAGE_PRIORITY_HIGH content={prompt}"})

    def _append(self, step):
        step = dict(step_index=self.step_index, created_at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    status="DONE", **step)
        self.step_index += 1
        with open(self.transcript, "a") as fh:
            fh.write(json.dumps(step) + "\n")

    def user_input(self, text):
        self.last_input = text
        self._append({"type": "USER_INPUT", "source": "USER_EXPLICIT",
                      "content": f"<USER_REQUEST>\n{text}\n</USER_REQUEST>"})

    def common(self):
        return {"conversationId": self.id, "workspacePaths": [REPO], "transcriptPath": self.transcript}


def hook(script, event):
    """Run a plugin hook the way Antigravity does: `python3 lib/<script>` in the plugin folder."""
    p = subprocess.run(["python3", f"lib/{script}"], input=json.dumps(event), env=env,
                       capture_output=True, text=True, cwd=PLUGIN)
    events.append({"hook": script, "event": event, "stdout": p.stdout, "stderr": p.stderr, "exit": p.returncode})
    if p.returncode:
        raise SystemExit(f"hook {script} exited {p.returncode}: {p.stderr}")
    return p.stdout.strip()


def pre_invocation(conv):
    """PreInvocation -> lib/approve.py. Returns the injected ephemeral messages."""
    conv.invocations += 1
    ev = dict(conv.common(), invocationNum=conv.invocations)
    out = hook("approve.py", ev)
    return [s["ephemeralMessage"] for s in json.loads(out)["injectSteps"]] if out else []


def gate(conv, name, args):
    """PreToolUse -> lib/gate.py. Returns (decision dict or None, raw stdout)."""
    ev = dict(conv.common(), toolCall={"name": name, "args": args})
    out = hook("gate.py", ev)
    return (json.loads(out) if out else None), out


def gate_note(decision, note=""):
    if decision is None:
        g = "gate: neutral (no output)"
    elif decision.get("overwrite"):
        g = "gate: allow + overwrite (CommandLine with $PLAN_LIB expanded)"
    else:
        g = f"gate: {decision.get('decision')}"
    return f"{g} — {note}" if note else g


SUP = Conversation("conv-supervisor")
_sub_counter = {}


def user(stage, text, conv=SUP, label=None, note=""):
    """The developer types a message: PreInvocation -> approve.py before the next model call."""
    conv.user_input(text)
    msgs = pre_invocation(conv)
    out = "\n".join(msgs) if msgs else "(no output)"
    rec(stage, label or f"you type: {text}", "prompt", text, out, 0, note)
    return out


def again(stage, conv=SUP, note=""):
    """Another model call in the same turn: PreInvocation fires again with the same transcript step."""
    msgs = pre_invocation(conv)
    rec(stage, "PreInvocation again in the same turn (next model call)", "hook",
        f"invocationNum: {conv.invocations} (same transcript step)", "\n".join(msgs) or "(no output)", 0, note)


def run(stage, command, conv=SUP, cwd=REPO, label=None, note="", expect=None, show=True):
    """An agent calls run_command: the gate first, then the (possibly overwritten) command."""
    d, _raw = gate(conv, "run_command", {"CommandLine": command, "Cwd": cwd})
    if d and d.get("decision") == "deny":
        rec(stage, label or command, "blocked", command, d.get("reason", ""), None, note)
        assert expect in (None, "blocked"), f"unexpectedly blocked: {command}\n{d}"
        return None
    to_run = (d or {}).get("overwrite", {}).get("CommandLine", command)
    p = sh(to_run, cwd=cwd, check=False)
    if show:
        rec(stage, label or command, "ran", command, (p.stdout + p.stderr) or "(no output)", p.returncode,
            gate_note(d, note))
    assert expect in (None, "ran"), f"unexpectedly allowed: {command}"
    return p


def write(stage, conv, path, text, cwd=REPO, label=None, note="", expect=None, tool="write_to_file",
          append=False, show=True):
    """An agent writes a file (write_to_file / replace_file_content): the gate first."""
    full = path if os.path.isabs(path) else os.path.join(cwd, path)
    d, _raw = gate(conv, tool, {"TargetFile": full})
    if d and d.get("decision") == "deny":
        rec(stage, label or f"{tool} {rel(full)}", "blocked", f"{tool}: {rel(full)}", d.get("reason", ""), None, note)
        assert expect in (None, "blocked"), f"unexpectedly blocked write: {full}\n{d}"
        return False
    assert expect in (None, "ran"), f"unexpectedly allowed write: {full}"
    body = textwrap.dedent(text).lstrip("\n")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "a" if append else "w") as fh:
        fh.write(body)
    if show:
        rec(stage, label or f"{conv.role} writes {rel(full)}", "file", rel(full),
            body if append else open(full).read(), None, gate_note(d, note))
    return True


def tick(stage, conv, path, old, new, cwd=REPO):
    """replace_file_content: tick a checkbox / update a line (gated, not recorded separately)."""
    full = os.path.join(cwd, path)
    d, _raw = gate(conv, "replace_file_content", {"TargetFile": full})
    assert not (d and d.get("decision") == "deny"), d
    text = open(full).read()
    assert old in text, (path, old)
    open(full, "w").write(text.replace(old, new, 1))


def dispatch(stage, conv, subagents, label=None, note="", expect=None, record_start=False):
    """The supervisor calls invoke_subagent; on allow each subagent's conversation starts."""
    args = {"Subagents": subagents}
    d, _raw = gate(conv, "invoke_subagent", args)
    shown = json.dumps(args, indent=1, ensure_ascii=False)
    names = ", ".join(s["TypeName"] for s in subagents)
    if d and d.get("decision") == "deny":
        rec(stage, label or f"invoke_subagent {names}", "blocked", shown, d.get("reason", ""), None, note)
        assert expect in (None, "blocked"), f"unexpectedly blocked dispatch: {d}"
        return []
    assert expect in (None, "ran"), "unexpectedly allowed dispatch"
    rec(stage, label or f"invoke_subagent {names}", "dispatched", shown,
        "(no gate output: the dispatch goes ahead)", None, gate_note(d, note))
    started = []
    for s in subagents:
        n = _sub_counter[s["TypeName"]] = _sub_counter.get(s["TypeName"], 0) + 1
        sub = Conversation(f"conv-{s['TypeName']}-{n}", parent=conv.id, role=s["TypeName"], prompt=s["Prompt"])
        msgs = pre_invocation(sub)  # the subagent's first model call
        if record_start:
            rec(stage, f"{s['TypeName']} subagent starts: PreInvocation (first model call)", "hook",
                f"conversationId {sub.id} (subagent of {conv.id})", "\n".join(msgs) or "(no output)", 0,
                "Once per conversation the hook announces enforcement and PLAN_LIB; a subagent gets the short form.")
        started.append(sub)
    return started


def message(stage, conv, recipient, text, label, note="", expect=None):
    d, _raw = gate(conv, "send_message", {"Recipient": recipient, "Message": text})
    blocked = bool(d and d.get("decision") == "deny")
    rec(stage, label, "blocked" if blocked else "dispatched", json.dumps({"Recipient": recipient, "Message": text}),
        d.get("reason", "") if blocked else "(no gate output: the message is sent)", None, note)
    assert expect in (None, "blocked" if blocked else "ran"), f"send_message: {d}"


def script(stage, label, command, note="", cwd=REPO, kind="script"):
    """Not an agent tool call: the developer's own terminal, or this harness."""
    p = sh(command, cwd=cwd, check=False)
    rec(stage, label, kind, command, (p.stdout + p.stderr) or "(no output)", p.returncode, note)
    return p


def show(stage, label, path, note=""):
    with open(os.path.join(REPO, path)) as fh:
        rec(stage, label, "file", path, fh.read(), None, note)


def note(stage, label, inp, out, note_text=""):
    rec(stage, label, "note", inp, out, None, note_text)


def ledger_kinds():
    path = os.path.join(REPO, MD, "approvals.md")
    if not os.path.exists(path):
        return []
    return [line.split("|")[3].strip() for line in open(path) if line.startswith("| 20")]


def usage(stage, args, label="supervisor: cost log", show_step=True):
    return run(stage, f'python3 "$PLAN_LIB/usage.py" {args}', label=label, show=show_step)


EXAMPLE = "Example agent-written content."

# ================================================================ setup: a small existing project
sh(f"git init -q --bare {ORIGIN}", cwd=BASE)
sh("git init -q -b main && git config user.email dev@shop.example && git config user.name 'Dana Dev' "
   "&& git config commit.gpgsign false")


def project_file(path, text):
    full = os.path.join(REPO, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as fh:
        fh.write(textwrap.dedent(text).lstrip("\n"))


project_file("src/shop/__init__.py", "")
project_file("src/shop/auth/__init__.py", "")
project_file("src/shop/routes/__init__.py", "")
project_file("src/shop/routes/login.py", '''
    from shop.auth.passwords import verify


    def login(username, password, ip, users):
        user = users.get(username)
        if user and verify(password, user["hash"]):
            return {"status": 200, "user": username}
        return {"status": 401, "error": "Invalid username or password"}
''')
project_file("src/shop/auth/passwords.py", '''
    import hashlib


    def verify(password, stored_hash):
        return hashlib.sha256(password.encode()).hexdigest() == stored_hash
''')
project_file("tests/test_login.py", '''
    import hashlib
    from shop.routes.login import login

    USERS = {"ana": {"hash": hashlib.sha256(b"s3cret").hexdigest()}}


    def test_login_ok():
        assert login("ana", "s3cret", "1.2.3.4", USERS)["status"] == 200


    def test_login_bad_password():
        assert login("ana", "nope", "1.2.3.4", USERS)["status"] == 401
''')
project_file(".gitignore", "__pycache__/\n.pytest_cache/\n")
project_file("pyproject.toml", '''
    [tool.pytest.ini_options]
    pythonpath = ["src"]
''')
if not HAVE_PYTEST:  # stdlib stand-in so the demo needs nothing beyond python3 and git
    project_file("run_tests.py", '''
        """Minimal stand-in for pytest: run every test_* function in tests/."""
        import glob, importlib.util, os, sys
        sys.path.insert(0, "src")
        passed = failed = 0
        for path in sorted(glob.glob("tests/test_*.py")):
            spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for name in sorted(n for n in dir(mod) if n.startswith("test_")):
                try:
                    getattr(mod, name)()
                    passed += 1
                except Exception as err:  # report and keep going
                    failed += 1
                    print(f"FAILED {path}::{name}: {err!r}")
        print(f"{passed} passed" + (f", {failed} failed" if failed else ""))
        sys.exit(1 if failed else 0)
    ''')
project_file("AGENTS.md", f'''
    # AGENTS.md

    ## Build and test

    ```bash
    {TEST_CMD}
    ```
''')
sh("git add -A && git commit -q -m 'initial shop app' && git remote add origin " + ORIGIN +
   " && git push -q origin main && git remote set-head origin main")

# ================================================================ stage 0: setup
S = "0 · Setup"
INIT = Conversation("conv-setup")
user(S, "swarm init", conv=INIT, note="A new top-level Antigravity conversation opened on ~/shop. Not a plan-swarm "
     "repository yet, so the approval hook stays neutral: no output, no files.")
run(S, 'python3 "$PLAN_LIB/swarm_init.py" --dry-run', conv=INIT, label="swarm-init skill: preview",
    note="The gate is neutral in a repository without plans/swarm.md, but still expands $PLAN_LIB.")
run(S, 'python3 "$PLAN_LIB/swarm_init.py" --only swarm,hook,review,ci,agents', conv=INIT,
    label="swarm-init skill: install")
script(S, "you commit and push the setup yourself (outside Antigravity)",
       "git add -A && git commit -q -m 'chore: adopt plan-swarm' && git push -q origin main && git log --oneline -1",
       note="The swarm never commits its own settings. The pre-commit hook allows a person's commit on main "
            "in pr mode; the pre-push hook lets people push other branches when no swarm session is active.")
user(S, "Be the supervisor.", label="you type: Be the supervisor.",
     note="A new top-level conversation: the first PreInvocation in a plan-swarm repository announces enforcement "
          "and PLAN_LIB (once per conversation).")
run(S, 'python3 "$PLAN_LIB/health.py" --status', label="supervisor orientation: health.py --status")
snapshot(S)

# ================================================================ stage 1: intent
S = "1 · Intent"
user(S, "Login gets brute-forced; limit failed attempts per account and per IP.",
     note="An ordinary request: the approval hook ignores it.")
REQUEST = "Login gets brute-forced; limit failed attempts per account and per IP."
(po,) = dispatch(S, SUP, [{"TypeName": "product-owner", "Role": "Intent writer",
                           "Prompt": f"Intent mode. Write an intent for: {REQUEST} Save it as `{INTENT_FILE}`."}],
                 label="supervisor dispatches product-owner (intent mode)", record_start=True)
write(S, po, INTENT_FILE, '''
    # Intent: Login rate limiting

    ## Problem
    The login endpoint accepts unlimited failed attempts, so accounts can be brute-forced.

    ## Outcome
    After repeated failures an account (and a noisy IP) is locked out for a while, and
    the response never reveals whether the account exists.

    ## Users & systems
    Everyone who logs in; `src/shop/routes/login.py`; the auth package.

    ## Constraints
    No new infrastructure (in-memory is acceptable for v1).

    ## Open questions
    Thresholds and lockout duration; whether internal IPs are exempt.
''', label="product-owner (intent mode) writes the intent", note=EXAMPLE)
run(S, f'python3 "$PLAN_LIB/tier.py" --milestone {M} --stage intent --intent-file {INTENT_FILE} --write',
    label="supervisor: propose a tier from the intent")
run(S, "git add plans && git commit -m 'docs: intent'", label="an agent tries to commit before approval",
    expect="blocked")
snapshot(S)

# ================================================================ stage 2: accept the intent
S = "2 · Accept the intent"
user(S, f"approve intent login-rate-limit as {M}",
     note="The whole message is a phrase, typed in the top-level conversation.")
again(S, note="Antigravity fires PreInvocation before every model call of the turn, on the same transcript step. "
               "Each user input is processed once, so nothing is minted twice.")
run(S, f"git switch -c swarm/{M}", label="supervisor: create the milestone branch")
run(S, f"mkdir -p {MD} && mv {INTENT_FILE} {MD}/intent.md", label="supervisor: move the intent into the milestone")
(po2,) = dispatch(S, SUP, [{"TypeName": "product-owner", "Role": "Roadmap owner",
                            "Prompt": f"Add milestone {M} to `plans/00-ROADMAP.md`."}],
                  label="supervisor dispatches product-owner (roadmap)")
write(S, po2, "plans/00-ROADMAP.md", f'''
    # Swarm Master Roadmap

    ## 📦 Release v1.0.0 (Target Date: 2026-10-15) - STATUS: ACTIVE
    - [ ] **Milestone 1: Login rate limiting** - STATUS: ACTIVE
      - *Intent:* `{MD}/intent.md`
      - *Spec:* `{MD}/spec.md`
''', label="product-owner adds the roadmap entry", note=EXAMPLE)
usage(S, f"log --milestone {M} --phase 0 --agent product-owner --tokens 6100 --tools 4 --ms 41000")
(aud,) = dispatch(S, SUP, [{"TypeName": "auditor", "Role": "Committer",
                            "Prompt": f"Commit `plans/` for milestone {M} with message `docs({M}): accept intent`. "
                                      f"The user approved it with `approve intent login-rate-limit as {M}`."}],
                  label="supervisor dispatches auditor (artifact commit)",
                  note="A phrase quoted inside a longer prompt is fine; only a prompt that IS a phrase is refused.")
run(S, f"git add plans/ && git commit -m 'docs({M}): accept intent' -- plans/", conv=aud,
    label="auditor: artifact commit")
snapshot(S)

# ================================================================ stage 3: research
S = "3 · Research"
(res,) = dispatch(S, SUP, [{"TypeName": "self", "Role": "Codebase researcher",
                            "Prompt": f"Stay read-only. Investigate the codebase for `{MD}/intent.md`: affected domain, "
                                      "existing patterns, constraints. Return a `## Codebase context` section in your "
                                      "final message."}],
                  label="supervisor dispatches a read-only research subagent (TypeName self)")
write(S, SUP, f"{MD}/intent.md", '''

    ## Codebase context
    - `src/shop/routes/login.py::login(username, password, ip, users)` returns 200/401 dicts; no state.
    - Password checks live in `src/shop/auth/passwords.py`; tests in `tests/test_login.py` (pytest, `pythonpath = src`).
    - No existing rate limiting, cache, or clock abstraction.
''', tool="replace_file_content", append=True,
      label="supervisor appends the returned Codebase context to intent.md",
      note="Example agent-written content (the research subagent's reply).")
usage(S, f"log --milestone {M} --phase 0b --agent self --tokens 9800 --tools 12 --ms 63000", show_step=False)
snapshot(S)

# ================================================================ stage 4: spec
S = "4 · Spec"
(po3,) = dispatch(S, SUP, [{"TypeName": "product-owner", "Role": "Spec writer",
                            "Prompt": f"Read `{MD}/intent.md`. Run the Grill Loop and write `spec.md` in the same folder."}],
                  label="supervisor dispatches product-owner (Grill Loop)")
note(S, "product-owner asks (ask_question, at most 3 questions)",
     "ask_question",
     "1. After how many failures should an account lock, and for how long?\n"
     "2. Should the lockout message reveal that the account exists?\n"
     "3. Are internal IPs exempt?\n"
     "you answer: 5 in 15 minutes, lock for 15 minutes; never reveal accounts; no exemptions.",
     "ask_question is not a gated tool. Example dialogue.")
write(S, po3, f"{MD}/spec.md", '''
    # Product Specification: Login rate limiting

    ## 🎯 Executive Summary
    *   **Goal:** Stop brute-force login attempts without revealing which accounts exist.
    *   **Target User:** Every account holder; the security team.
    *   **Business Value:** Removes the top finding of the last security review.

    ## 📋 Acceptance Criteria
    - **Scenario:** Account lockout
      - **Given** 5 failed logins for one account within 15 minutes
      - **When** a 6th attempt arrives, even with the right password
      - **Then** the response is 429 with the generic lockout message for 15 minutes
    - **Scenario:** No account enumeration
      - **Given** an unknown username
      - **When** it fails 5 times
      - **Then** the responses are identical to a real account's
    - **Scenario:** Noisy IP
      - **Given** 20 failures from one IP within 15 minutes across accounts
      - **When** another attempt arrives from that IP
      - **Then** it gets 429 with the same message

    ## 🚨 Constraints & Edge Cases
    - In-memory counters (single instance) for v1; counters reset on restart.
    - No exemptions for internal IPs.

    ## ⚖️ Policy Concerns
    - None open (lockout messages follow the security policy's no-enumeration rule).
''', label="product-owner writes spec.md after the Grill Loop", note=EXAMPLE)
user(S, f"approve spec {M}", conv=po3, label="you type the phrase inside the product-owner subagent's conversation",
     note="The subagent's transcript starts with the parent's message, so this is a subagent conversation: the hook "
          "mints nothing and writes no ledger row. Only the top-level conversation records approvals.")
assert "spec" not in ledger_kinds(), ledger_kinds()
message(S, po3, SUP.id, f"approve spec {M}", label="product-owner tries to send_message the phrase to the supervisor",
        expect="blocked")
dispatch(S, SUP, [{"TypeName": "auditor", "Role": "Committer", "Prompt": f"approve spec {M}"}],
         label="supervisor tries a dispatch whose whole prompt is the phrase", expect="blocked")
usage(S, f"log --milestone {M} --phase 1 --agent product-owner --tokens 18400 --tools 9 --ms 142000")
user(S, "No spec-validator this time.", note="Your answer to the offered gate: an ordinary message, ignored by the "
     "approval hook.")
usage(S, f"decline --milestone {M} --phase 1b --gate spec-validator",
      label="you decline the offered spec-validator; the supervisor logs it")
user(S, f"approve spec {M}", note="Now typed in the top-level conversation: recorded.")
(aud,) = dispatch(S, SUP, [{"TypeName": "auditor", "Role": "Committer",
                            "Prompt": f"Commit `plans/` for milestone {M} with message `docs({M}): spec`. "
                                      f"The user approved it with `approve spec {M}`."}],
                  label="supervisor dispatches auditor (artifact commit)")
run(S, f"git add plans/ && git commit -m 'docs({M}): spec' -- plans/", conv=aud, label="auditor: artifact commit")
snapshot(S)

# ================================================================ stage 5: plan
S = "5 · Plan"
(arch,) = dispatch(S, SUP, [{"TypeName": "architect", "Role": "Planner",
                             "Prompt": f"Read `{MD}/spec.md`. Write `plan.md` in the same folder."}],
                   label="supervisor dispatches architect")
write(S, arch, f"{MD}/plan.md", f'''
    # Technical Plan: {M}

    ## 🔍 Analysis & Context
    *   **Objective:** Lock out accounts and noisy IPs after repeated login failures.
    *   **Affected Files:** `src/shop/auth/attempts.py`, `src/shop/auth/messages.py`, `src/shop/routes/login.py`
    *   **Risks/Edge Cases:** clock handling; identical responses for unknown users.
    *   **Irreversible Steps:** None

    ## 📋 Task Execution (Parallel Groups)
    ### Group 1 (Parallel Execution - Independent Tasks)
    - [ ] Task 1.A: attempt counter → `src/shop/auth/attempts.py`, `tests/test_attempts.py`
    - [ ] Task 1.B: lockout message → `src/shop/auth/messages.py`, `tests/test_messages.py`

    ### Group 2 (Sequential Execution - Depends on Group 1)
    - [ ] Task 2.A: enforce limits in login → `src/shop/routes/login.py`, `tests/test_login.py`

    ## 🎯 Success Criteria
    *   `{TEST_CMD}` passes; every acceptance criterion has a test.
''', label="architect writes plan.md", note=EXAMPLE)
usage(S, f"log --milestone {M} --phase 2 --agent architect --tokens 22700 --tools 15 --ms 171000", show_step=False)
run(S, f'python3 "$PLAN_LIB/tier.py" --milestone {M} --stage plan --write', label="supervisor: re-check the tier")
user(S, "Skip the deliberator; run the plan-validator.", note="An ordinary message: your decision on the offered gates.")
usage(S, f"decline --milestone {M} --phase 2a --gate plan-deliberator",
      label="you decline the recommended plan-deliberator; the supervisor logs it")
(pv,) = dispatch(S, SUP, [{"TypeName": "plan-validator", "Role": "Plan skeptic panel",
                           "Prompt": f"Validate `{MD}/plan.md` against this repository."}],
                 label="you accept plan-validator; supervisor dispatches it")
dispatch(S, pv, [{"TypeName": "self", "Role": f"Skeptic {i}",
                  "Prompt": f"Stay read-only. Assume `{MD}/plan.md` WILL fail. Read the codebase and find the first "
                            "domino. Return JSON findings with file:line evidence."} for i in (1, 2, 3)],
         label="plan-validator dispatches 3 read-only skeptics in one invoke_subagent call")
write(S, pv, f"{MD}/adversarial-reviews/plan-validation.md", f'''
    # Plan Adversarial Review — Technical Plan: {M}

    > `plan-validator` · 3 independent skeptics, no shared scratchpad · default-to-reject · skeptics READ the codebase · 2-of-3 majority gate

    | Field | Value |
    |---|---|
    | Milestone | `{M}` |
    | Artifact | `{MD}/plan.md` |
    | Date | {TODAY} |
    | Gate | 2-of-3 |
    | Result | **0 confirmed · 1 unconfirmed** — highest severity **none** |
    | 🁢 First domino | `none` — no confirmed finding |

    ## Verdict
    The plan survives execution: groups touch disjoint files and Group 2 depends only on Group 1's modules.

    ## Confirmed Findings (≥ 2 votes)
    _None._

    ## Unconfirmed (FYI · 1 vote)
    | `id` | severity | step | note |
    |---|---|---|---|
    | `clock-source` | 🟡 low | 2.A | `login()` takes `now` from the caller; a real clock is out of scope for v1 |
''', label="plan-validator writes its report", note=EXAMPLE)
usage(S, f"log --milestone {M} --phase 2b --agent plan-validator --tokens 31200 --tools 27 --ms 208000",
      show_step=False)
snapshot(S)

# ================================================================ stage 6: approve the plan
S = "6 · Approve the plan"
ENG_PROMPT = (f"Implement Task 1.A defined in `{MD}/plan.md`. Worktree mode: work only inside "
              f"`.swarm/worktrees/{M}/1.A` (branch `swarm-wip/{M}/1.A`); WIP commits there are allowed; do not edit `plans/`.")
dispatch(S, SUP, [{"TypeName": "engineer", "Role": "Builder 1.A", "Prompt": ENG_PROMPT}],
         label="supervisor tries to dispatch an engineer before the plan approval", expect="blocked")
write(S, arch, f"{MD}/approvals.md", "| forged | row |\n", label="an agent tries to write approvals.md itself",
      expect="blocked")
write(S, arch, "plans/swarm.md", "", tool="replace_file_content",
      label="an agent tries to edit plans/swarm.md (raise engineers.max_concurrent)", expect="blocked")
user(S, f"approve plan {M}", note="The proposed tier from plan.md is confirmed with the approval.")
(aud,) = dispatch(S, SUP, [{"TypeName": "auditor", "Role": "Committer",
                            "Prompt": f"Commit `plans/` for milestone {M} with message `docs({M}): plan`. "
                                      f"The user approved it with `approve plan {M}`."}],
                  label="supervisor dispatches auditor (artifact commit)")
run(S, f"git add plans/ && git commit -m 'docs({M}): plan' -- plans/", conv=aud, label="auditor: artifact commit")
snapshot(S)

# ================================================================ stage 7: build group 1
S = "7 · Build (group 1)"
out_a = run(S, f'python3 "$PLAN_LIB/worktree.py" create --milestone {M} --task 1.A', label="supervisor: worktree for 1.A")
out_b = run(S, f'python3 "$PLAN_LIB/worktree.py" create --milestone {M} --task 1.B', label="supervisor: worktree for 1.B")
wa, wb = json.loads(out_a.stdout)["path"], json.loads(out_b.stdout)["path"]
eng_a, eng_b = dispatch(S, SUP, [
    {"TypeName": "engineer", "Role": "Builder 1.A", "Prompt": ENG_PROMPT.replace(f".swarm/worktrees/{M}/1.A", wa)},
    {"TypeName": "engineer", "Role": "Builder 1.B",
     "Prompt": ENG_PROMPT.replace("1.A", "1.B").replace(f".swarm/worktrees/{M}/1.B", wb)},
], label="supervisor dispatches two engineers in one invoke_subagent call (parallel)",
    note="Allowed now: approvals.md has the plan row.")
write(S, eng_a, os.path.join(wa, "src/shop/auth/attempts.py"), '''
    """Sliding-window failure counters for accounts and IPs (in memory, single instance)."""
    WINDOW = 15 * 60


    class AttemptCounter:
        def __init__(self, limit, window=WINDOW):
            self.limit, self.window, self.failures = limit, window, {}

        def record_failure(self, key, now):
            recent = [t for t in self.failures.get(key, []) if now - t < self.window]
            recent.append(now)
            self.failures[key] = recent

        def is_locked(self, key, now):
            return len([t for t in self.failures.get(key, []) if now - t < self.window]) >= self.limit
''', show=False)
write(S, eng_a, os.path.join(wa, "tests/test_attempts.py"), '''
    from shop.auth.attempts import AttemptCounter


    def test_locks_after_limit_within_window():
        c = AttemptCounter(limit=5)
        for t in range(5):
            c.record_failure("ana", now=t)
        assert c.is_locked("ana", now=10)


    def test_window_expires():
        c = AttemptCounter(limit=5)
        for t in range(5):
            c.record_failure("ana", now=t)
        assert not c.is_locked("ana", now=15 * 60 + 5)
''', show=False)
write(S, eng_b, os.path.join(wb, "src/shop/auth/messages.py"), '''
    LOCKOUT_MESSAGE = "Too many attempts. Try again later."
''', show=False)
write(S, eng_b, os.path.join(wb, "tests/test_messages.py"), '''
    from shop.auth.messages import LOCKOUT_MESSAGE


    def test_message_does_not_reveal_accounts():
        assert "account" not in LOCKOUT_MESSAGE.lower() and "user" not in LOCKOUT_MESSAGE.lower()
''', show=False)
note(S, "engineers write code + tests in their worktrees (TDD, write_to_file; gate neutral)", f"{wa}\n{wb}",
     "src/shop/auth/attempts.py + tests/test_attempts.py  (1.A)\nsrc/shop/auth/messages.py + tests/test_messages.py  (1.B)",
     EXAMPLE)
run(S, f"git add -A && git commit -m 'wip({M}): 1.A counter'", conv=eng_a, cwd=wa,
    label="engineer 1.A: WIP commit in its worktree (Cwd = the worktree)")
run(S, "git add -A && git commit -m 'sneak it in'", conv=eng_b, label="an engineer tries to commit in the main checkout",
    expect="blocked")
run(S, f'python3 "$PLAN_LIB/worktree.py" squash --milestone {M}',
    label="supervisor: integrate the group (1.B's work is auto-committed as WIP)")
tick(S, SUP, f"{MD}/plan.md", "- [ ] Task 1.A", "- [x] Task 1.A")
tick(S, SUP, f"{MD}/plan.md", "- [ ] Task 1.B", "- [x] Task 1.B")
note(S, "supervisor ticks Task 1.A and 1.B in plan.md (replace_file_content; gate neutral)",
     f"{MD}/plan.md", "- [x] Task 1.A ...\n- [x] Task 1.B ...")
usage(S, f"log --milestone {M} --phase 4 --agent engineer --tokens 15300 --tools 21 --ms 133000 --note 1.A",
      show_step=False)
usage(S, f"log --milestone {M} --phase 4 --agent engineer --tokens 9100 --tools 11 --ms 87000 --note 1.B",
      show_step=False)
run(S, "git diff --cached --stat", label="staged group diff")
snapshot(S)

# ================================================================ stage 8: audit group 1
S = "8 · Audit (group 1)"
user(S, "Skip the simplifier and the implementation validator for this group.",
     note="An ordinary message: your decision on the offered checks.")
usage(S, f"decline --milestone {M} --phase 4 --gate simplifier", label="you decline the offered simplifier")
(aud,) = dispatch(S, SUP, [{"TypeName": "auditor", "Role": "Group 1 auditor",
                            "Prompt": f"Verify group 1 of `{MD}/plan.md` (the staged changes). Record the round in "
                                      f"`{MD}/audit.md`."}],
                  label="supervisor dispatches auditor (verify group 1)")
t = run(S, TEST_CMD, conv=aud, label="auditor runs the tests from AGENTS.md")
assert t.returncode == 0, t.stdout + t.stderr
result_line = (t.stdout.strip().splitlines() or [""])[-1]
write(S, aud, f"{MD}/audit.md", f'''
    # Audit: {M}

    ### Group 1 · Round 1 · PASS
    *   **Completion:** 2/2 steps verified
    *   **Tasks:** Task 1.A: ✅ · Task 1.B: ✅

    #### Step 1.A: attempt counter
    *   **Status:** ✅ Verified
    *   **Evidence:** `AttemptCounter.is_locked` in `src/shop/auth/attempts.py` lines 14-15 counts failures inside the window
    *   **Dynamic Check:** `{TEST_CMD}` → {result_line}

    #### Anti-Shortcut & Quality Scan
    *   **Placeholders/TODOs/Deferred Work:** None found
    *   **Test Integrity:** Tests are robust

    #### Conclusion
    PASS.
''', label="auditor records the round", note="Example agent-written content; the test result line is real.")
usage(S, f"log --milestone {M} --phase 4 --agent auditor --tokens 12800 --tools 14 --ms 96000", show_step=False)
usage(S, f"decline --milestone {M} --phase 4 --gate implementation-validator",
      label="you decline the implementation gate for group 1")
snapshot(S)

# ================================================================ stage 9: commit gate group 1
S = "9 · Commit gate (group 1)"
G1_MSG = f"feat({M}): attempt counter and lockout message"
run(S, f"git add plans/ && git commit -m '{G1_MSG}'", conv=aud, label="auditor tries before your approval",
    expect="blocked")
user(S, f"approve commit {M} g1")
(aud,) = dispatch(S, SUP, [{"TypeName": "auditor", "Role": "Committer",
                            "Prompt": f"Commit group 1 (the staged code plus the milestone's updated `plans/` files) with "
                                      f"message: {G1_MSG}. The user approved it with `approve commit {M} g1`."}],
                  label="supervisor dispatches auditor (group commit)")
run(S, f"git add plans/ && git commit -m '{G1_MSG}'", conv=aud,
    label="auditor: group commit (both git-hook layers pass)")
run(S, "git commit --allow-empty -m 'one more'", conv=aud, label="reusing the approval", expect="blocked")
run(S, f'python3 "$PLAN_LIB/worktree.py" cleanup --milestone {M}', label="supervisor: clean up worktrees")
snapshot(S)

# ================================================================ stage 10: group 2
S = "10 · Group 2 and the last commit"
out_c = run(S, f'python3 "$PLAN_LIB/worktree.py" create --milestone {M} --task 2.A', label="supervisor: worktree for 2.A")
wc = json.loads(out_c.stdout)["path"]
(eng_c,) = dispatch(S, SUP, [{"TypeName": "engineer", "Role": "Builder 2.A",
                              "Prompt": f"Implement Task 2.A defined in `{MD}/plan.md`. Worktree mode: work only inside "
                                        f"`{wc}` (branch `swarm-wip/{M}/2.A`); WIP commits there are allowed; do not "
                                        "edit `plans/`."}],
                    label="supervisor dispatches the engineer for 2.A")
write(S, eng_c, os.path.join(wc, "src/shop/routes/login.py"), '''
    from shop.auth.attempts import AttemptCounter
    from shop.auth.messages import LOCKOUT_MESSAGE
    from shop.auth.passwords import verify

    ACCOUNTS = AttemptCounter(limit=5)
    IPS = AttemptCounter(limit=20)


    def login(username, password, ip, users, now=0):
        if ACCOUNTS.is_locked(username, now) or IPS.is_locked(ip, now):
            return {"status": 429, "error": LOCKOUT_MESSAGE}
        user = users.get(username)
        if user and verify(password, user["hash"]):
            return {"status": 200, "user": username}
        ACCOUNTS.record_failure(username, now)
        IPS.record_failure(ip, now)
        return {"status": 401, "error": "Invalid username or password"}
''', label="engineer 2.A writes login.py in its worktree", note=EXAMPLE)
write(S, eng_c, os.path.join(wc, "tests/test_login.py"), '''


    def test_lockout_after_five_failures():
        for _ in range(5):
            login("bob", "x", "9.9.9.9", USERS)
        assert login("bob", "x", "9.9.9.9", USERS)["status"] == 429
''', tool="replace_file_content", append=True, show=False)
run(S, f'python3 "$PLAN_LIB/worktree.py" squash --milestone {M}', label="supervisor: integrate group 2")
tick(S, SUP, f"{MD}/plan.md", "- [ ] Task 2.A", "- [x] Task 2.A")
(aud,) = dispatch(S, SUP, [{"TypeName": "auditor", "Role": "Group 2 auditor",
                            "Prompt": f"Verify group 2 of `{MD}/plan.md` (the staged changes). Record the round in "
                                      f"`{MD}/audit.md`."}],
                  label="supervisor dispatches auditor (verify group 2)")
t = run(S, TEST_CMD, conv=aud, label="auditor runs the tests (group 2)")
assert t.returncode == 0, t.stdout + t.stderr
write(S, aud, f"{MD}/audit.md", f'''

    ### Group 2 · Round 1 · PASS
    *   **Completion:** 1/1 steps verified
    *   **Dynamic Check:** `{TEST_CMD}` → {(t.stdout.strip().splitlines() or [""])[-1]}
''', tool="replace_file_content", append=True, label="auditor appends the group 2 round",
      note="Example agent-written content; the test result line is real.")
(po4,) = dispatch(S, SUP, [{"TypeName": "product-owner", "Role": "Roadmap owner",
                            "Prompt": f"Mark milestone {M} COMPLETED in `plans/00-ROADMAP.md`."}],
                  label="supervisor dispatches product-owner (mark the milestone COMPLETED)")
tick(S, po4, "plans/00-ROADMAP.md", "- [ ] **Milestone 1: Login rate limiting** - STATUS: ACTIVE",
     "- [x] **Milestone 1: Login rate limiting** - STATUS: COMPLETED")
usage(S, f"log --milestone {M} --phase 4 --agent engineer --tokens 11900 --tools 16 --ms 102000 --note 2.A",
      show_step=False)
G2_MSG = f"feat({M}): enforce limits in login"
user(S, f"approve commit {M} g2")
(aud,) = dispatch(S, SUP, [{"TypeName": "auditor", "Role": "Committer",
                            "Prompt": f"Commit group 2 (the staged code plus the milestone's updated `plans/` files) with "
                                      f"message: {G2_MSG}. The user approved it with `approve commit {M} g2`."}],
                  label="supervisor dispatches auditor (group commit)")
run(S, f"git add plans/ && git commit -m '{G2_MSG}'", conv=aud, label="auditor: group commit")
run(S, f'python3 "$PLAN_LIB/worktree.py" cleanup --milestone {M}', label="supervisor: clean up worktrees")
snapshot(S)

# ================================================================ stage 11: pull request
S = "11 · Pull request"
tier = run(S, f'python3 "$PLAN_LIB/tier.py" --milestone {M} --stage diff', label="supervisor: tier check on the real diff",
           note="Read-only (no --write) so the PR approval commit stays ledger-only; only exceeds_confirmed would "
                "lead to --write and a new `approve plan … tier=<new>`.")
assert not json.loads(tier.stdout)["exceeds_confirmed"], tier.stdout
run(S, f"git push -u origin swarm/{M}", label="supervisor tries to push before approval", expect="blocked")
p = sh(f"git push -q origin swarm/{M}", check=False)
rec(S, "…and outside Antigravity the pre-push hook refuses too", "git-hook", f"git push origin swarm/{M}",
    p.stderr, p.returncode, "Run in the developer's own terminal: layer 2 (git hooks) does not depend on Antigravity.")
assert p.returncode != 0, "pre-push should refuse the unapproved PR push"
user(S, f"approve pr {M}")
(aud,) = dispatch(S, SUP, [{"TypeName": "auditor", "Role": "Committer",
                            "Prompt": f"Commit only `{MD}/approvals.md` with message `docs({M}): record PR approval`."}],
                  label="supervisor dispatches auditor (ledger-only commit)")
run(S, f"git commit -m 'docs({M}): record PR approval' -- {MD}/approvals.md", conv=aud,
    label="auditor: commit the PR approval (ledger-only commit)")
push = run(S, f"git push -u origin swarm/{M}", label="supervisor: push (the pre-push hook checks every commit)")
assert push.returncode == 0, push.stdout + push.stderr
title = run(S, f'python3 "$PLAN_LIB/prbody.py" --milestone {M} --title', label="PR title (lib/prbody.py)")
body = run(S, f'python3 "$PLAN_LIB/prbody.py" --milestone {M}', label="PR body (lib/prbody.py)")
gh_cmd = (f'gh pr create --head swarm/{M} --title "$(python3 "$PLAN_LIB/prbody.py" --milestone {M} --title)" '
          f'--body "$(python3 "$PLAN_LIB/prbody.py" --milestone {M})"')
d, _raw = gate(SUP, "run_command", {"CommandLine": gh_cmd, "Cwd": REPO})
assert not (d and d.get("decision") == "deny"), d
note(S, "gh pr create: allowed by the gate, not run in this demo (no gh, no GitHub)", gh_cmd,
     gate_note(d) + ". Without gh the supervisor gives you the push result and the generated title and body.")
note(S, "what the supervisor prints instead of opening the PR", "(supervisor message)",
     f"Pushed swarm/{M}:\n{(push.stdout + push.stderr).strip()}\n\nPR title:\n{title.stdout.strip()}\n\n"
     f"PR body:\n{body.stdout.strip()}")
yml = open(os.path.join(PLUGIN, "templates", "ci", "plan-swarm.yml")).read()
import re as _re  # noqa: E402
ci = _re.search(r"python3 - <<'PY'\n(.*?)\n\s*PY\n", yml, _re.S).group(1)
ci = "\n".join(line[10:] if line.startswith(" " * 10) else line for line in ci.splitlines())
base = sh("git merge-base origin/main HEAD").stdout.strip()
p = subprocess.run(["python3", "-c", ci], cwd=REPO, capture_output=True, text=True,
                   env=dict(env, BASE=base, MILESTONE=f"swarm/{M}", GITHUB_OUTPUT=os.path.join(BASE, "gh_out")))
rec(S, "CI ledger job (from templates/ci/plan-swarm.yml)", "ci", "ledger job on the PR", p.stdout + p.stderr, p.returncode,
    "The job's script, extracted from the template and run against the pushed branch.")
assert p.returncode == 0, p.stdout + p.stderr
run(S, "gh pr merge 1 --squash", label="an agent tries to merge the PR", expect="blocked")
tip = sh(f"git rev-parse swarm/{M}").stdout.strip()
sh(f"git --git-dir={ORIGIN} update-ref refs/heads/main {tip}")
note(S, "a code owner merges the PR on GitHub", "(server side)",
     "origin/main now points at the milestone tip (simulated merge; the merge strategy is the host's choice)")
snapshot(S)

# ================================================================ stage 12: release
S = "12 · Release"
dirty = sh("git status --porcelain --untracked-files=no").stdout.strip()
assert not dirty, f"working tree should be clean before the release:\n{dirty}"
run(S, "git switch main && git pull --ff-only origin main", label="supervisor tries switch + pull in one command",
    expect="blocked", note="The gate judges a command before it runs, so the pull is still seen on the swarm branch.")
run(S, "git switch main", label="supervisor: switch to the default branch")
run(S, "git pull --ff-only origin main", label="supervisor: update it (separate command)")
user(S, "approve release v1.0.0",
     note="The hook reads the conversation transcript (transcriptPath) for the input and for top-level detection, "
          "and records the release row in plans/approvals.md.")
run(S, "git tag -a v1.0.0 -m 'Release v1.0.0'", label="supervisor: tag")
user(S, "Yes, push the tag.", note="The supervisor asked whether to push the tag; an ordinary message.")
tagpush = run(S, "git push origin v1.0.0", label="supervisor: push the tag (you agreed)")
assert tagpush.returncode == 0, tagpush.stdout + tagpush.stderr
run(S, "git push origin main", label="an agent tries to push main", expect="blocked")
snapshot(S)

# ================================================================ stage 13: measure
S = "13 · Measure"
run(S, 'python3 "$PLAN_LIB/metrics.py" --format text', label="swarm-metrics")
script(S, "the milestone branch as its audit trail", "git log --format='%h %s' main -8")
show(S, "approvals.md (written only by the approval hook)", f"{MD}/approvals.md")
show(S, "plans/approvals.md (release rows)", "plans/approvals.md")
show(S, "usage.md", f"{MD}/usage.md")
script(S, "files the milestone produced", "find plans -type f | sort")
snapshot(S)

# ---------------------------------------------------------------- checks and output
assert sh(f"git --git-dir={ORIGIN} tag --list v1.0.0").stdout.strip() == "v1.0.0"
assert ledger_kinds() == ["intent", "spec", "plan", "commit", "commit", "pr"], ledger_kinds()
with open(os.path.join(BASE, "transcript.json"), "w") as fh:
    json.dump(steps, fh, indent=1, ensure_ascii=False)
with open(os.path.join(BASE, "hook-events.jsonl"), "w") as fh:
    for e in events:
        fh.write(json.dumps(e, ensure_ascii=False) + "\n")
with open(os.path.join(BASE, "git-state.json"), "w") as fh:
    json.dump(states, fh, indent=1, ensure_ascii=False)
blocked = sum(1 for s in steps if s["kind"] == "blocked")
print(f"{len(steps)} steps captured ({blocked} refused, {len(events)} hook calls) → {BASE}/transcript.json")
