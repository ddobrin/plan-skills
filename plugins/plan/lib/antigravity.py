#!/usr/bin/env python3
"""Antigravity hook payload helpers for the plan-swarm control plane.

Antigravity runs plugin hooks declared in the plugin's hooks.json. Every hook gets a
JSON payload on stdin with camelCase keys. The fields this module relies on:

    conversationId          the conversation the hook fires in
    workspacePaths          workspace roots (the hook's own cwd is the plugin dir)
    transcriptPath          the conversation's transcript_full.jsonl
    toolCall {name, args}   PreToolUse only
    invocationNum           PreInvocation only

PreToolUse output: print nothing (or {"decision": "allow"}) to stay neutral,
{"decision": "deny", "reason": ...} to block. Printing "{}" blocks the call
with an empty reason, and a non-zero exit blocks it too, so the gate never
prints an empty object and treats its own crashes as a deny.

Standard library only.
"""
import hashlib
import json
import os
import re

LIB = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(LIB)

WRITE_TOOLS = {
    "write_to_file": "TargetFile",
    "replace_file_content": "TargetFile",
    "multi_replace_file_content": "TargetFile",
    "notebook_edit": "NotebookPath",
}
USER_REQUEST = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.DOTALL)
PLAN_LIB_VAR = re.compile(r"\$\{PLAN_LIB\}|\$PLAN_LIB(?![A-Za-z0-9_])")


def read_event(stream):
    """Parse the hook payload; {} for anything that is not a JSON object."""
    try:
        data = json.load(stream)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def tool_call(event):
    call = event.get("toolCall") or {}
    if not isinstance(call, dict):
        return "", {}
    args = call.get("args") or {}
    return str(call.get("name") or ""), args if isinstance(args, dict) else {}


def _existing_dir(path):
    """The nearest existing directory at or above path."""
    probe = os.path.abspath(os.path.expanduser(path))
    while probe and not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    return probe


def workspace_dir(event):
    for path in event.get("workspacePaths") or []:
        if isinstance(path, str) and os.path.isdir(path):
            return path
    return os.environ.get("PWD") or os.getcwd()


def _outside_git_dir(path):
    """path with any trailing `.git/...` part removed (git cannot find the work tree
    from inside its own directory)."""
    parts = os.path.realpath(path).split(os.sep)
    if ".git" in parts:
        parts = parts[: parts.index(".git")]
    return os.sep.join(parts) or os.sep


def tool_dir(event):
    """The directory a tool call acts in: the command's Cwd, the written file's folder,
    or the first workspace."""
    name, args = tool_call(event)
    if name == "run_command" and isinstance(args.get("Cwd"), str) and args["Cwd"]:
        return _existing_dir(_outside_git_dir(os.path.expanduser(args["Cwd"])))
    key = WRITE_TOOLS.get(name)
    if key and isinstance(args.get(key), str) and args[key]:
        target = os.path.dirname(os.path.abspath(os.path.expanduser(args[key])))
        return _existing_dir(_outside_git_dir(_existing_dir(target)))
    return workspace_dir(event)


def candidate_dirs(event):
    """tool_dir first, then the workspaces: the gate checks the first plan-swarm
    repository among them, so a write outside the repository (say, to Antigravity's
    settings) is still judged by the workspace's rules."""
    out = []
    for path in [tool_dir(event)] + [p for p in event.get("workspacePaths") or [] if isinstance(p, str)]:
        if path and os.path.isdir(path) and path not in out:
            out.append(path)
    return out or [workspace_dir(event)]


# --------------------------------------------------------------------------
# transcript fallback

HEAD_BYTES = 64 * 1024
TAIL_BYTES = 2 * 1024 * 1024


def _parse_lines(chunk):
    steps = []
    for line in chunk.splitlines():
        try:
            step = json.loads(line)
        except ValueError:
            continue  # includes a line cut in half at a chunk boundary
        if isinstance(step, dict):
            steps.append(step)
    return steps


def transcript_steps(event):
    """Steps from the conversation's transcript (full form first), oldest first.

    Large files are read as their first 64 KiB (enough to tell a subagent from a
    top-level conversation) plus their last 2 MiB (enough to find the newest
    user input). Lines that are not JSON objects are skipped; a missing file
    yields []."""
    path = event.get("transcriptPath") or ""
    candidates = [path]
    if path.endswith("transcript_full.jsonl"):
        candidates.append(path[: -len("transcript_full.jsonl")] + "transcript.jsonl")
    for candidate in candidates:
        if not candidate or not os.path.isfile(candidate):
            continue
        try:
            size = os.path.getsize(candidate)
            with open(candidate, "rb") as fh:
                if size <= HEAD_BYTES + TAIL_BYTES:
                    steps = _parse_lines(fh.read().decode("utf-8", "replace"))
                else:
                    head = fh.read(HEAD_BYTES).decode("utf-8", "replace")
                    fh.seek(size - TAIL_BYTES)
                    tail = fh.read().decode("utf-8", "replace")
                    steps = _parse_lines(head) + _parse_lines(tail)
        except OSError:
            continue
        if steps:
            return steps
    return []


def user_request_text(content):
    """The user's own words: the <USER_REQUEST> block when present, else the whole text."""
    content = content or ""
    m = USER_REQUEST.search(content)
    return (m.group(1) if m else content).strip()


def last_user_step(steps):
    """(step_index, text, created_at) of the newest explicit user input, or (None, "", None)."""
    for step in reversed(steps):
        if step.get("type") == "USER_INPUT" and step.get("source", "USER_EXPLICIT") == "USER_EXPLICIT":
            idx = step.get("step_index")
            return ((idx if isinstance(idx, int) else None), user_request_text(step.get("content")),
                    step.get("created_at"))
    return None, "", None


def looks_like_subagent(steps):
    """A subagent's conversation starts with the parent's message (a SYSTEM_MESSAGE
    naming a sender) rather than with a user input."""
    for step in steps:
        kind = step.get("type")
        if kind == "USER_INPUT":
            return False
        if kind == "SYSTEM_MESSAGE" and "sender=" in str(step.get("content") or ""):
            return True
    return False


def is_subagent(event, steps=None):
    """True for subagents, False for top-level conversations, None when unknown."""
    steps = transcript_steps(event) if steps is None else steps
    if not steps:
        return None
    return looks_like_subagent(steps)


def text_identity(text):
    return "text-" + hashlib.sha256(" ".join((text or "").split()).encode("utf-8")).hexdigest()[:16]


def user_input(event, steps=None):
    """The latest explicit user input as (identity, text, created_at).

    identity is "step-<n>" for the newest explicit user step in the transcript,
    so each user input is processed once."""
    steps = transcript_steps(event) if steps is None else steps
    idx, text, created = last_user_step(steps)
    if idx is not None:
        return f"step-{idx}", text, created
    return None, "", None


# --------------------------------------------------------------------------
# hook output

def deny(reason):
    return json.dumps({"decision": "deny", "reason": f"plan-swarm: {reason}"})


def inject(messages):
    return json.dumps({"injectSteps": [{"ephemeralMessage": m} for m in messages if m]})


def expand_plan_lib(command):
    """Replace $PLAN_LIB / ${PLAN_LIB} with this plugin's lib directory."""
    return PLAN_LIB_VAR.sub(lambda _m: LIB, command)
