#!/usr/bin/env python3
"""PreInvocation hook: turn a human approval phrase into a single-use nonce.

Antigravity has no prompt-submit hook. Instead, before every model call (PreInvocation)
and before every gated tool call (lib/gate.py calls capture() too), this module
looks at the conversation's latest user input. When the WHOLE input is exactly
one of (case-insensitive):

    approve intent  <slug> as <milestone>
    approve spec    <milestone>
    approve plan    <milestone> [tier=routine|elevated|critical]
    approve commit  <milestone> g<n>
    approve pr      <milestone>
    approve release <version>

it mints a nonce bound to the current HEAD (single use, expires after
approvals.nonce_ttl_minutes), appends a row to the milestone's approvals.md,
stages that row, and tells the session what was recorded.

Only a person can approve:
* the input must come from a top-level conversation. A subagent's prompt is
  written by another agent, so conversations whose transcript starts with a
  parent's message never mint; when the transcript is unavailable, nothing is
  minted;
* each user input is processed once. Its identity is the transcript step index,
  so an old approval phrase is never replayed when the agent wakes up later;
* lib/gate.py refuses tool calls that try to plant a phrase as a new message
  (send_message, or a dispatch whose whole message is a phrase).

This script also refreshes the control-plane heartbeat and, once per
conversation, injects the enforcement status and the PLAN_LIB path.
"""
import contextlib
import datetime as dt
import fcntl
import glob
import hashlib
import json
import os
import re
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import antigravity  # noqa: E402
import swarmdoc  # noqa: E402
import swarmgit as sg  # noqa: E402

M = sg.MONIKER
VERSION = r"v?\d+\.\d+\.\d+[0-9A-Za-z.+-]*"
GRAMMAR = [
    ("intent", re.compile(rf"approve intent ({M}) as ({M})", re.I)),
    ("spec", re.compile(rf"approve spec ({M})", re.I)),
    ("plan", re.compile(rf"approve plan ({M})(?: tier=(routine|elevated|critical))?", re.I)),
    ("commit", re.compile(rf"approve commit ({M}) g(\d+)", re.I)),
    ("pr", re.compile(rf"approve pr ({M})", re.I)),
    ("release", re.compile(rf"approve release ({VERSION})", re.I)),
]
NEXT_STEP = {
    "intent": "create branch swarm/{m} (pr mode), move the intent into the milestone, and commit plans/",
    "spec": "commit spec.md and its gate reports (plans/ paths only)",
    "plan": "commit the plan (plans/ paths only), then dispatch engineers",
    "commit": "have the auditor create the group commit",
    "pr": "record the PR approval, push swarm/{m}, and open the pull request",
    "release": "create the annotated tag (and push it if the user agrees)",
}


def parse(prompt):
    text = " ".join((prompt or "").strip().split())
    for kind, pattern in GRAMMAR:
        m = pattern.fullmatch(text)
        if not m:
            continue
        g = m.groups()
        if kind == "intent":
            return {"kind": kind, "slug": g[0].lower(), "moniker": g[1].lower()}
        if kind == "plan":
            return {"kind": kind, "moniker": g[0].lower(), "tier": (g[1] or "").lower()}
        if kind == "commit":
            return {"kind": kind, "moniker": g[0].lower(), "group": int(g[1])}
        if kind == "release":
            return {"kind": kind, "version": g[0]}
        return {"kind": kind, "moniker": g[0].lower()}
    return None


def proposed_tier(root, moniker):
    for name in ("plan.md", "intent.md"):
        path = os.path.join(sg.milestone_dir(root, moniker), name)
        try:
            with open(path, encoding="utf-8") as fh:
                m = re.search(r"Risk tier \(proposed\)\W*(routine|elevated|critical)", fh.read(), re.I)
        except OSError:
            continue
        if m:
            return m.group(1).lower()
    return ""


def record(approval, root):
    """Mint the nonce and write the ledger row. Returns a message for the session."""
    cfg = swarmdoc.load_config(root)
    store = sg.store_dir(root)
    if not store:
        return "Approval NOT recorded: this directory is not a git repository."
    kind, moniker = approval["kind"], approval.get("moniker")

    if kind == "intent":
        found = glob.glob(os.path.join(root, "plans", "intents", f"*{approval['slug']}.md"))
        if not found and not os.path.exists(os.path.join(sg.milestone_dir(root, moniker), "intent.md")):
            return f"Approval NOT recorded: no intent file matching plans/intents/*{approval['slug']}.md."
    elif kind != "release" and not os.path.isdir(sg.milestone_dir(root, moniker)):
        return f"Approval NOT recorded: plans/active_milestones/{moniker}/ does not exist."

    tier = approval.get("tier") or ""
    if kind == "plan" and not tier:
        tier = proposed_tier(root, moniker)
    if kind in ("commit", "pr") and moniker:
        tier = sg.confirmed_tier(root, moniker)

    head_sha = sg.head(root)
    if not head_sha:
        return "Approval NOT recorded: the repository has no commits yet."
    t = sg.now()
    ttl = cfg["approvals"]["nonce_ttl_minutes"]
    rec = {
        "kind": kind, "moniker": moniker, "group": approval.get("group"),
        "version": approval.get("version"), "slug": approval.get("slug"),
        "tier": tier, "mode": cfg["delivery"]["mode"], "head": head_sha,
        "branch": sg.branch(root), "who": sg.user_email(root),
        "created": sg.iso(t), "expires": sg.iso(t + dt.timedelta(minutes=ttl)),
        "id": "n_" + secrets.token_hex(6),
    }
    # Ledger first: an approval that cannot be recorded must not become usable.
    ledger = sg.append_ledger(root, moniker if kind != "release" else None, {
        "when": rec["created"], "who": rec["who"], "kind": kind,
        "milestone": moniker or approval.get("version"), "group": approval.get("group") or "",
        "tier": tier, "mode": rec["mode"], "head": head_sha[:12], "nonce": rec["id"],
    })
    # Stage the ledger so its row ships inside the commit it authorizes (CI and the
    # pre-push hook match each commit's parent against these rows).
    sg.git("add", "--", ledger, cwd=root)
    nonce = sg.mint_nonce(store, rec)
    label = kind + (f" {moniker}" if moniker else f" {approval['version']}")
    label += f" g{approval['group']}" if approval.get("group") else ""
    tier_note = f" Tier: {tier}." if tier else ""
    return (f"plan-swarm: approval recorded for {label} (nonce {nonce['id']}, valid once until "
            f"{nonce['expires'][11:16]} UTC while HEAD stays at {nonce['head'][:12]}).{tier_note} "
            f"Next: {NEXT_STEP[kind].format(m=moniker)}.")


# --------------------------------------------------------------------------
# input bookkeeping (in the store, so every hook process sees it)

def _key(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:32]


def _claim_once(store, name):
    """Atomically create store/seen/<name>; True for the first caller only."""
    folder = os.path.join(store, "seen")
    os.makedirs(folder, exist_ok=True)
    try:
        fd = os.open(os.path.join(folder, name), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    os.write(fd, sg.iso(sg.now()).encode())
    os.close(fd)
    return True


def _swap_last(store, conversation, identity):
    """Record identity as the conversation's latest input; return the previous one."""
    folder = os.path.join(store, "seen")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "last-" + _key(conversation))
    try:
        with open(path, encoding="utf-8") as fh:
            previous = fh.read().strip()
    except OSError:
        previous = ""
    if previous != identity:
        tmp = f"{path}.{os.getpid()}.{secrets.token_hex(3)}"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(identity)
        os.replace(tmp, path)
    return previous


def _first_time(store, conversation, identity, text, created):
    """True exactly once per user input (see the module docstring).

    A step identity is claimed atomically so the same user step is never
    minted twice across repeated invocations in a turn."""
    previous = _swap_last(store, conversation, identity)
    text_mark = "textmint-" + _key(conversation, antigravity.text_identity(text))
    if identity.startswith("step-"):
        if not _claim_once(store, _key(conversation, identity)):
            return False
        minted_at = sg.parse_iso(_read_mark(store, text_mark))
        step_at = sg.parse_iso(created)
        return not (minted_at and (step_at is None or minted_at >= step_at))
    if previous == identity:
        return False
    _write_mark(store, text_mark, sg.iso(sg.now()))
    return True


def _read_mark(store, name):
    try:
        with open(os.path.join(store, "seen", name), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _write_mark(store, name, value):
    folder = os.path.join(store, "seen")
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, f".{name}.{os.getpid()}.{secrets.token_hex(3)}")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(value)
    os.replace(tmp, os.path.join(folder, name))


@contextlib.contextmanager
def _locked(store):
    """Serialize check-and-mint across hook processes (two registrations of the hook,
    or PreInvocation and PreToolUse firing close together)."""
    folder = os.path.join(store, "seen")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, ".lock"), "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def stash(store, conversation, message):
    """Queue a message for the conversation's next PreInvocation."""
    folder = os.path.join(store, "pending")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, _key(conversation) + ".txt"), "a", encoding="utf-8") as fh:
        fh.write(message.replace("\n", " ") + "\n")


def take_stashed(store, conversation):
    path = os.path.join(store, "pending", _key(conversation) + ".txt")
    claimed = f"{path}.{os.getpid()}"
    try:
        os.rename(path, claimed)
    except OSError:
        return []
    with open(claimed, encoding="utf-8") as fh:
        lines = [line.strip() for line in fh if line.strip()]
    os.remove(claimed)
    return lines


def capture(event, root=None):
    """Mint an approval if the conversation's newest user input is a phrase.

    Returns the session message, or None when there is nothing to report."""
    conversation = event.get("conversationId") or ""
    root = root or sg.repo_root(antigravity.workspace_dir(event))
    store = sg.store_dir(root)
    if not store:
        return None
    steps = antigravity.transcript_steps(event)
    identity, text, created = antigravity.user_input(event, steps)
    if not identity:
        return None
    approval = parse(text)
    if not approval:
        _swap_last(store, conversation, identity)
        return None
    subagent = antigravity.is_subagent(event, steps)
    if subagent:
        return None  # a subagent's prompt is another agent's words, never an approval
    with _locked(store):
        if not _first_time(store, conversation, identity, text, created):
            return None
        if subagent is None:
            return ("Approval NOT recorded: plan-swarm could not confirm that this is the top-level "
                    "conversation (no transcript). Type the phrase again.")
        try:
            return record(approval, root)
        except swarmdoc.SwarmDocError as err:
            return f"Approval NOT recorded: plans/swarm.md is invalid ({err}). Fix it and type the phrase again."
        except Exception as err:  # never mint silently: report and record nothing usable
            return f"Approval NOT recorded: {type(err).__name__}: {err}"


def pre_invocation(event):
    """Messages to inject before this model call."""
    import health  # local import: health imports this module's neighbours only

    root = sg.repo_root(antigravity.workspace_dir(event))
    if not os.path.exists(os.path.join(root, swarmdoc.CONFIG_PATH)) and not sg.is_active(sg.store_dir(root, create=False)):
        return []
    store = sg.store_dir(root)
    if not store:
        return []
    sg.touch_heartbeat(store, last_invocation=sg.iso(sg.now()))
    conversation = event.get("conversationId") or ""
    messages = []
    if conversation and _claim_once(store, "announced-" + _key(conversation)):
        messages.append(health.announce(event, root))
    messages.extend(take_stashed(store, conversation))
    message = capture(event, root)
    if message:
        messages.append(message)
    return [m for m in messages if m]


def main():
    event = antigravity.read_event(sys.stdin)
    try:
        messages = pre_invocation(event)
    except Exception as err:  # never block the model call; say what went wrong
        messages = [f"plan-swarm: approval hook error ({type(err).__name__}: {err}); no approval was recorded."]
    if messages:
        print(antigravity.inject(messages))
    return 0


if __name__ == "__main__":
    sys.exit(main())
