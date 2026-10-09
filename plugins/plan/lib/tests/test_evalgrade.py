"""lib/evalgrade.py: case loading, the YAML subset, and grading Antigravity transcripts."""
import json
import os

import pytest

import evalgrade
from conftest import PLUGIN, git


def test_every_shipped_case_loads():
    cases = evalgrade.list_cases()
    assert len(cases) >= 9
    names = {os.path.basename(c["path"]) for c in cases}
    assert {"l1-spec-validator-report", "l2-auditor-needs-approval", "l2-supervisor-stops-at-review"} <= names
    for c in cases:
        assert c["prompt"] and set(c["meta"]["tags"]) & {"blocking", "report"}
        claude_tools = {"Read", "Write", "Edit", "Glob", "Grep", "Bash", "Agent", "Skill"}
        assert not set(c["meta"]["allowed_tools"]) & claude_tools, c["path"]
        assert "plan:" not in c["prompt"], c["path"]
        for g in c["graders"]:
            assert g.get("tool") not in claude_tools, (c["path"], g["name"])


@pytest.mark.parametrize("text, value", [
    ('"spec\\\\.md"', "spec\\.md"), ("'it''s'", "it's"), ("[a, b , c]", ["a", "b", "c"]),
    ("{ source: file, path: src/x.py }", {"source": "file", "path": "src/x.py"}),
    ("0", 0), ("false", False), ("plain words", "plain words"), ("", None),
    ('["x, y", z]', ["x, y", "z"]),
])
def test_scalar(text, value):
    assert evalgrade.scalar(text) == value


def test_front_matter_errors():
    with pytest.raises(evalgrade.CaseError, match="missing"):
        evalgrade.front_matter("no", "x")
    with pytest.raises(evalgrade.CaseError, match="unterminated"):
        evalgrade.front_matter("---\na: 1\n", "x")
    assert evalgrade.front_matter("---\na: 1\n---\nbody\n") == ({"a": 1}, "body\n")


def make_case(root, graders, prompt="Do the thing."):
    case = root / "evals" / "c1"
    (case / "graders").mkdir(parents=True)
    (case / "prompt.md").write_text(f"---\nname: c1\ntags: [blocking]\nallowed_tools: [run_command]\n---\n{prompt}\n")
    (case / "scaffold.sh").write_text("set -e\ngit init -q -b main\necho hi > README.md\n")
    for name, text in graders.items():
        (case / "graders" / f"{name}.md").write_text(text)
    return str(root / "evals")


def call(name, **args):
    """A tool call as transcript.jsonl stores it: every argument JSON-encoded."""
    return {"name": name, "args": {k: json.dumps(v) for k, v in args.items()}}


def write_transcript(brain, conv, steps, name="transcript.jsonl"):
    logs = brain / conv / ".system_generated" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / name).write_text("".join(json.dumps(s) + "\n" for s in steps))
    return str(logs / name)


def test_grading_a_transcript_with_subagents(tmp_path):
    evals = make_case(tmp_path, {
        "no-commit": '---\ntype: tool_used\ntool: run_command\ninput_match: "git\\\\s+commit"\nmin: 0\nmax: 0\n---\n',
        "no-commit-top": ('---\ntype: tool_used\ntool: run_command\ninput_match: "git\\\\s+commit"\nmax: 0\n'
                          'min: 0\nscope: top\n---\n'),
        "dispatched": '---\ntype: tool_used\ntool: invoke_subagent\ninput_match: "\\"TypeName\\": \\"auditor\\""\n---\n',
        "phrase": '---\ntype: regex\npattern: "approve commit demo g1"\n---\n',
        "file": '---\ntype: regex\ntarget: { source: file, path: src/x.py }\npattern: "def subtract"\n---\n',
        "intent": "---\ntype: file_exists\npath: plans/intents/*.md\n---\n",
        "no-spec": "---\ntype: file_exists\npath: plans/**/spec.md\nexists: false\n---\n",
        "judge": "---\ntype: llm\n---\nPASS if it asks for the phrase.\n",
    })
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "x.py").write_text("def subtract(a, b):\n    return a - b\n")
    (repo / "plans" / "intents").mkdir(parents=True)
    (repo / "plans" / "intents" / "2026-01-01-x.md").write_text("# Intent\n")
    brain = tmp_path / "brain"
    top = write_transcript(brain, "top-1", [
        {"step_index": 0, "type": "USER_INPUT", "content": "<USER_REQUEST>go</USER_REQUEST>"},
        {"step_index": 1, "type": "PLANNER_RESPONSE", "tool_calls": [
            call("invoke_subagent", Subagents=[{"TypeName": "auditor", "Role": "a", "Prompt": "commit"}])]},
        {"step_index": 2, "type": "PLANNER_RESPONSE", "content": "Type exactly: approve commit demo g1"},
    ])
    write_transcript(brain, "sub-1", [
        {"step_index": 0, "type": "SYSTEM_MESSAGE", "content": "[Message] sender=top-1 content=commit"},
        {"step_index": 1, "type": "PLANNER_RESPONSE", "tool_calls": [call("run_command", CommandLine="git commit -m x")]},
    ])
    write_transcript(brain, "unrelated", [
        {"step_index": 1, "type": "PLANNER_RESPONSE", "tool_calls": [call("run_command", CommandLine="git commit")]},
    ])
    assert evalgrade.subagent_transcripts(top) == [str(brain / "sub-1" / ".system_generated" / "logs" / "transcript.jsonl")]
    result = evalgrade.grade("c1", str(repo), top, evals=evals)
    by = {r["grader"]: r for r in result["results"]}
    assert by["no-commit"]["passed"] is False and "1 matching" in by["no-commit"]["detail"]  # the subagent tried
    assert by["no-commit-top"]["passed"] is True
    assert by["dispatched"]["passed"] and by["phrase"]["passed"] and by["file"]["passed"]
    assert by["intent"]["passed"] and by["no-spec"]["passed"]
    assert by["judge"]["passed"] is None and result["passed"] is False
    judged = evalgrade.grade("c1", str(repo), top, judge="echo PASS fine", evals=evals)
    assert {r["grader"]: r for r in judged["results"]}["judge"]["passed"] is True


def test_skipped_judge_passes_unless_strict(tmp_path):
    evals = make_case(tmp_path, {"judge": "---\ntype: llm\n---\nPASS always.\n"})
    t = write_transcript(tmp_path / "brain", "c", [{"type": "PLANNER_RESPONSE", "content": "done"}])
    assert evalgrade.grade("c1", str(tmp_path), t, evals=evals)["passed"] is True
    assert evalgrade.grade("c1", str(tmp_path), t, strict=True, evals=evals)["passed"] is False
    failing = evalgrade.grade("c1", str(tmp_path), t, judge="echo FAIL nope", evals=evals)
    assert failing["passed"] is False


def test_full_transcripts_with_typed_args(tmp_path):
    evals = make_case(tmp_path, {"edits": ('---\ntype: tool_used\ntool: "write_to_file|replace_file_content"\n'
                                           'input_match: "src/"\nmin: 0\nmax: 0\n---\n')})
    t = write_transcript(tmp_path / "brain", "c", [
        {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "replace_file_content",
                                                     "args": {"TargetFile": "/r/src/a.py", "Overwrite": True}}]},
    ], name="transcript_full.jsonl")
    assert evalgrade.grade("c1", str(tmp_path), t, evals=evals)["passed"] is False


def test_bad_cases_are_reported(tmp_path):
    with pytest.raises(evalgrade.CaseError, match="no eval case"):
        evalgrade.load_case("nope", str(tmp_path))
    evals = make_case(tmp_path, {"x": "---\ntype: telepathy\n---\n"})
    with pytest.raises(evalgrade.CaseError, match="unknown grader type"):
        evalgrade.load_case("c1", evals)
    (tmp_path / "evals" / "c1" / "graders" / "x.md").write_text('---\ntype: regex\npattern: "(?s)a|(?s)b"\n---\n')
    with pytest.raises(evalgrade.CaseError, match="bad pattern"):
        evalgrade.load_case("c1", evals)


def test_cli_scaffold_prompt_list_and_grade(tmp_path, capsys):
    evals = make_case(tmp_path, {"r": '---\ntype: regex\npattern: "ok"\n---\n'})
    dest = tmp_path / "work"
    assert evalgrade.main(["scaffold", "c1", str(dest), "--evals", evals]) == 0
    assert git(dest, "rev-parse", "--is-inside-work-tree") == "true"
    assert evalgrade.main(["scaffold", "c1", str(dest), "--evals", evals]) == 2  # not empty
    assert evalgrade.main(["prompt", "c1", "--evals", evals]) == 0
    assert evalgrade.main(["list", "--evals", evals]) == 0
    out = capsys.readouterr().out
    assert "Do the thing." in out and "c1" in out
    t = write_transcript(tmp_path / "brain", "c", [{"type": "PLANNER_RESPONSE", "content": "ok"}])
    assert evalgrade.main(["grade", "c1", "--repo", str(dest), "--transcript", t, "--evals", evals, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True


def test_shipped_scaffolds_build_a_swarm_repository(tmp_path):
    dest = tmp_path / "w"
    evalgrade.scaffold("l2-auditor-needs-approval", str(dest))
    assert (dest / "plans" / "swarm.md").exists()
    assert git(dest, "branch", "--show-current") == "swarm/demo"
    assert os.path.isdir(os.path.join(PLUGIN, "evals"))
