"""Antigravity payload helpers (lib/antigravity.py)."""
import io
import json
import os

import pytest

import antigravity


def test_read_event_tolerates_garbage():
    assert antigravity.read_event(io.StringIO('{"a": 1}')) == {"a": 1}
    assert antigravity.read_event(io.StringIO("[1]")) == {}
    assert antigravity.read_event(io.StringIO("nope")) == {}


def test_tool_call_shapes():
    assert antigravity.tool_call({"toolCall": {"name": "run_command", "args": {"CommandLine": "ls"}}}) == \
        ("run_command", {"CommandLine": "ls"})
    assert antigravity.tool_call({"toolCall": "x"}) == ("", {})
    assert antigravity.tool_call({"toolCall": {"name": "x", "args": "y"}}) == ("x", {})
    assert antigravity.tool_call({}) == ("", {})


def test_tool_dir_prefers_cwd_then_target_then_workspace(tmp_path):
    ws, sub = tmp_path / "ws", tmp_path / "ws" / "a"
    sub.mkdir(parents=True)
    base = {"workspacePaths": [str(ws)]}
    assert antigravity.tool_dir(dict(base, toolCall={"name": "run_command", "args": {"Cwd": str(sub)}})) == str(sub)
    new_file = sub / "b" / "c" / "new.py"  # folders that do not exist yet
    assert antigravity.tool_dir(dict(base, toolCall={"name": "write_to_file", "args": {"TargetFile": str(new_file)}})) \
        == str(sub)
    nb = {"name": "notebook_edit", "args": {"NotebookPath": str(sub / "n.ipynb")}}
    assert antigravity.tool_dir(dict(base, toolCall=nb)) == str(sub)
    assert antigravity.tool_dir(dict(base, toolCall={"name": "view_file", "args": {}})) == str(ws)


def test_tool_dir_steps_out_of_the_git_directory(tmp_path):
    (tmp_path / "r" / ".git" / "hooks").mkdir(parents=True)
    os.symlink(tmp_path / "r" / ".git", tmp_path / "r" / "g")
    for target in (".git/hooks/pre-commit", "g/hooks/pre-commit", ".git/config"):
        call = {"name": "write_to_file", "args": {"TargetFile": str(tmp_path / "r" / target)}}
        assert antigravity.tool_dir({"toolCall": call}) == os.path.realpath(tmp_path / "r")


def test_candidate_dirs_adds_workspaces(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    call = {"name": "write_to_file", "args": {"TargetFile": str(tmp_path / "x.json")}}
    assert antigravity.candidate_dirs({"workspacePaths": [str(ws), 3], "toolCall": call}) == [str(tmp_path), str(ws)]


def step(idx, kind, content, source="USER_EXPLICIT", created="2026-10-05T20:00:00Z"):
    return {"step_index": idx, "type": kind, "source": source, "content": content, "created_at": created}


def test_transcript_falls_back_to_the_compact_file(tmp_path):
    full = tmp_path / "transcript_full.jsonl"
    (tmp_path / "transcript.jsonl").write_text(json.dumps(step(0, "USER_INPUT", "hi")) + "\nnot json\n[1]\n")
    assert [s["step_index"] for s in antigravity.transcript_steps({"transcriptPath": str(full)})] == [0]
    full.write_text(json.dumps(step(0, "USER_INPUT", "a")) + "\n" + json.dumps(step(1, "USER_INPUT", "b")) + "\n")
    assert len(antigravity.transcript_steps({"transcriptPath": str(full)})) == 2
    assert antigravity.transcript_steps({}) == []


def test_large_transcripts_are_read_head_and_tail(tmp_path, monkeypatch):
    monkeypatch.setattr(antigravity, "HEAD_BYTES", 200)
    monkeypatch.setattr(antigravity, "TAIL_BYTES", 400)
    lines = [json.dumps(step(i, "PLANNER_RESPONSE", "x" * 50, source="MODEL")) for i in range(50)]
    lines[0] = json.dumps(step(0, "USER_INPUT", "first"))
    lines[-1] = json.dumps(step(49, "USER_INPUT", "last"))
    path = tmp_path / "transcript_full.jsonl"
    path.write_text("\n".join(lines) + "\n")
    steps = antigravity.transcript_steps({"transcriptPath": str(path)})
    assert steps[0]["step_index"] == 0 and steps[-1]["step_index"] == 49 and len(steps) < 50


def test_user_request_text_and_last_user_step():
    assert antigravity.user_request_text("<USER_REQUEST>\n approve spec m \n</USER_REQUEST>\n<X>y</X>") == "approve spec m"
    assert antigravity.user_request_text("  plain ") == "plain"
    steps = [step(0, "USER_INPUT", "<USER_REQUEST>one</USER_REQUEST>"),
             step(1, "PLANNER_RESPONSE", "", source="MODEL"),
             step(2, "USER_INPUT", "<USER_REQUEST>two</USER_REQUEST>", created="t2"),
             step(3, "USER_INPUT", "implicit", source="USER_IMPLICIT")]
    assert antigravity.last_user_step(steps) == (2, "two", "t2")
    assert antigravity.last_user_step([]) == (None, "", None)


@pytest.mark.parametrize("steps, expected", [
    ([step(0, "SYSTEM_MESSAGE", "[Message] sender=p content=x", source="SYSTEM")], True),
    ([step(0, "USER_INPUT", "x")], False),
    ([], None),
])
def test_is_subagent(steps, expected):
    assert antigravity.is_subagent({}, steps) is expected


def test_user_input_identity():
    steps = [step(4, "USER_INPUT", "<USER_REQUEST>approve spec m</USER_REQUEST>", created="t4")]
    assert antigravity.user_input({}, steps) == ("step-4", "approve spec m", "t4")
    assert antigravity.user_input({}, []) == (None, "", None)
    assert antigravity.text_identity("a  b") == antigravity.text_identity(" a b ")


def test_outputs():
    assert json.loads(antigravity.deny("no")) == {"decision": "deny", "reason": "plan-swarm: no"}
    assert json.loads(antigravity.inject(["a", "", None, "b"])) == \
        {"injectSteps": [{"ephemeralMessage": "a"}, {"ephemeralMessage": "b"}]}


def test_expand_plan_lib():
    assert antigravity.expand_plan_lib('python3 "$PLAN_LIB/x.py" ${PLAN_LIB}/y') == \
        f'python3 "{antigravity.LIB}/x.py" {antigravity.LIB}/y'
    assert antigravity.expand_plan_lib("echo $PLAN_LIBX $PLAN") == "echo $PLAN_LIBX $PLAN"


def test_hooks_json_registers_the_gate_and_the_approval_hook():
    with open(os.path.join(antigravity.PLUGIN_ROOT, "hooks.json"), encoding="utf-8") as fh:
        hooks = json.load(fh)
    (config,) = hooks.values()
    pre = config["PreInvocation"][0]
    assert pre["type"] == "command" and pre["command"].endswith("lib/approve.py")
    (gate_entry,) = config["PreToolUse"]
    assert gate_entry["hooks"][0]["command"].endswith("lib/gate.py")
    import re
    matcher = re.compile(gate_entry["matcher"])
    for tool in ("run_command", "invoke_subagent", "run_workflow", "send_message", *antigravity.WRITE_TOOLS):
        assert matcher.fullmatch(tool), tool
    assert not matcher.fullmatch("view_file")
