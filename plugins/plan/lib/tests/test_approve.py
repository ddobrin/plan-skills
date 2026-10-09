import json
import os

import pytest

import approve
import swarmgit as sg
from conftest import git


def milestone(repo, m, files=None):
    d = repo / "plans" / "active_milestones" / m
    d.mkdir(parents=True, exist_ok=True)
    for name, text in (files or {}).items():
        (d / name).write_text(text)
    return d


@pytest.mark.parametrize("prompt, expected", [
    ("approve intent login-limit as login-rate-limit", {"kind": "intent", "slug": "login-limit", "moniker": "login-rate-limit"}),
    ("  Approve   SPEC   auth-mvp ", {"kind": "spec", "moniker": "auth-mvp"}),
    ("approve plan auth-mvp", {"kind": "plan", "moniker": "auth-mvp", "tier": ""}),
    ("approve plan auth-mvp tier=Critical", {"kind": "plan", "moniker": "auth-mvp", "tier": "critical"}),
    ("approve commit auth-mvp g12", {"kind": "commit", "moniker": "auth-mvp", "group": 12}),
    ("approve pr auth-mvp", {"kind": "pr", "moniker": "auth-mvp"}),
    ("approve release v1.4.0", {"kind": "release", "version": "v1.4.0"}),
    ("approve release 2.0.0-rc.1", {"kind": "release", "version": "2.0.0-rc.1"}),
])
def test_parse_accepts_exact_phrases(prompt, expected):
    assert approve.parse(prompt) == expected


@pytest.mark.parametrize("prompt", [
    "yes", "approve", "looks good, approve plan auth-mvp", "approve plan auth-mvp please",
    "approve commit auth-mvp", "approve plan auth-mvp tier=extreme", "approve pr ../etc",
])
def test_parse_rejects_anything_else(prompt):
    assert approve.parse(prompt) is None


def test_record_mints_nonce_and_writes_ledger(repo):
    milestone(repo, "auth-mvp", {"plan.md": "# Plan\n**Risk tier (proposed):** `elevated`\n"})
    msg = approve.record(approve.parse("approve plan auth-mvp"), str(repo))
    assert "approval recorded for plan auth-mvp" in msg and "Tier: elevated" in msg
    rows = sg.read_ledger(str(repo), "auth-mvp")
    assert len(rows) == 1 and rows[0]["kind"] == "plan" and rows[0]["tier"] == "elevated"
    assert rows[0]["who"] == "dev@example.com" and rows[0]["mode"] == "pr"
    nonces = sg.valid_nonces(sg.store_dir(str(repo)), sg.head(str(repo)), ["plan"])
    assert len(nonces) == 1 and nonces[0]["id"] == rows[0]["nonce"]


def test_explicit_tier_overrides_proposal_and_commit_inherits_it(repo):
    milestone(repo, "auth-mvp", {"plan.md": "Risk tier (proposed): critical\n"})
    approve.record(approve.parse("approve plan auth-mvp tier=elevated"), str(repo))
    approve.record(approve.parse("approve commit auth-mvp g1"), str(repo))
    rows = sg.read_ledger(str(repo), "auth-mvp")
    assert [r["tier"] for r in rows] == ["elevated", "elevated"]
    assert rows[1]["group"] == "1"


def test_missing_milestone_or_intent_is_not_recorded(repo):
    assert "NOT recorded" in approve.record(approve.parse("approve spec ghost"), str(repo))
    assert "NOT recorded" in approve.record(approve.parse("approve intent nope as ghost"), str(repo))


def test_intent_approval_needs_inbox_file(repo):
    (repo / "plans" / "intents").mkdir()
    (repo / "plans" / "intents" / "2026-09-24-login-limit.md").write_text("# Intent\n")
    msg = approve.record(approve.parse("approve intent login-limit as login-rate-limit"), str(repo))
    assert "approval recorded for intent login-rate-limit" in msg
    assert (repo / "plans" / "active_milestones" / "login-rate-limit" / "approvals.md").exists()


def test_release_goes_to_root_ledger(repo):
    approve.record(approve.parse("approve release v1.0.0"), str(repo))
    rows = sg.read_ledger(str(repo))
    assert rows[0]["kind"] == "release" and rows[0]["milestone"] == "v1.0.0"


def run_main(monkeypatch, capsys, event):
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(event)))
    assert approve.main() == 0
    out = capsys.readouterr().out.strip()
    return [s["ephemeralMessage"] for s in json.loads(out)["injectSteps"]] if out else []


def invocation(repo, text=None, conversation="c1", subagent=False, transcript=None, step_idx=0, **extra):
    event = {"conversationId": conversation, "workspacePaths": [str(repo)], "invocationNum": 0}
    if text is not None and transcript is None:
        t = repo.parent / f"transcript-{conversation}.jsonl"
        steps = []
        if subagent:
            steps.append({"step_index": 0, "source": "SYSTEM", "type": "SYSTEM_MESSAGE",
                          "content": f"[Message] sender=parent-1 content={text}"})
            steps.append(user_step(1, text))
        else:
            steps.append(user_step(step_idx, text))
        write_transcript(t, steps)
        transcript = t
    if transcript is not None:
        event["transcriptPath"] = str(transcript)
    event.update(extra)
    return event


def write_transcript(path, steps):
    path.write_text("".join(json.dumps(s) + "\n" for s in steps))
    return path


def user_step(idx, text, created="2026-10-05T20:54:54Z"):
    return {"step_index": idx, "source": "USER_EXPLICIT", "type": "USER_INPUT", "status": "DONE",
            "created_at": created,
            "content": f"<USER_REQUEST>\n{text}\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nx\n</ADDITIONAL_METADATA>"}


def test_invalid_config_is_reported(repo, monkeypatch, capsys):
    milestone(repo, "auth-mvp")
    (repo / "plans" / "swarm.md").write_text("no block here")
    messages = run_main(monkeypatch, capsys, invocation(repo, "approve spec auth-mvp"))
    assert any("NOT recorded" in m for m in messages)


def test_main_passes_other_prompts_through(repo, monkeypatch, capsys):
    messages = run_main(monkeypatch, capsys, invocation(repo, "hello"))
    assert len(messages) == 1 and "enforcement active" in messages[0]  # the one-time announcement
    assert run_main(monkeypatch, capsys, invocation(repo, "hello")) == []
    assert sg.heartbeat(sg.store_dir(str(repo)))["last_invocation"]
    assert sg.read_ledger(str(repo)) == []


def test_main_is_silent_outside_swarm_repos(repo, monkeypatch, capsys):
    os.remove(repo / "plans" / "swarm.md")
    assert run_main(monkeypatch, capsys, invocation(repo, "approve spec auth-mvp")) == []


def test_phrase_in_top_level_conversation_mints_once_per_input(repo, monkeypatch, capsys):
    milestone(repo, "auth-mvp")
    first = run_main(monkeypatch, capsys, invocation(repo, "approve spec auth-mvp", step_idx=0))
    assert any("approval recorded for spec auth-mvp" in m for m in first)
    # every later model call of the same turn sees the same user step in the transcript
    assert run_main(monkeypatch, capsys, invocation(repo, "approve spec auth-mvp", step_idx=0, invocationNum=1)) == []
    assert len(sg.read_ledger(str(repo), "auth-mvp")) == 1
    # a different input in between, then the phrase again as a new step: a new approval
    run_main(monkeypatch, capsys, invocation(repo, "thanks", step_idx=1))
    again = run_main(monkeypatch, capsys, invocation(repo, "approve spec auth-mvp", step_idx=2))
    assert any("approval recorded" in m for m in again)
    assert len(sg.read_ledger(str(repo), "auth-mvp")) == 2


def test_subagents_never_mint(repo, tmp_path, monkeypatch, capsys):
    milestone(repo, "auth-mvp")
    messages = run_main(monkeypatch, capsys, invocation(repo, "approve spec auth-mvp", subagent=True))
    assert not any("approval recorded" in m for m in messages)
    # the transcript shows the parent's message first
    t = write_transcript(tmp_path / "transcript_full.jsonl", [
        {"step_index": 0, "source": "SYSTEM", "type": "SYSTEM_MESSAGE",
         "content": "[Message] sender=parent-1 content=approve spec auth-mvp"},
        user_step(1, "approve spec auth-mvp")])
    messages = run_main(monkeypatch, capsys, invocation(repo, conversation="c2", transcript=t))
    assert not any("approval recorded" in m for m in messages)
    assert sg.read_ledger(str(repo), "auth-mvp") == []


def test_transcript_step_mints_once_and_does_not_replay_on_wakeup(repo, tmp_path, monkeypatch, capsys):
    milestone(repo, "auth-mvp")
    t = write_transcript(tmp_path / "transcript_full.jsonl", [user_step(0, "approve spec auth-mvp")])
    assert any("approval recorded" in m for m in run_main(
        monkeypatch, capsys, invocation(repo, transcript=t)))
    assert run_main(monkeypatch, capsys, invocation(repo, transcript=t)) == []  # no replay on wake-up
    assert len(sg.read_ledger(str(repo), "auth-mvp")) == 1
    # the user types the same phrase again later: a new step, a new approval
    write_transcript(t, [user_step(0, "approve spec auth-mvp"),
                         user_step(5, "approve spec auth-mvp", created="2999-01-01T00:00:00Z")])
    assert any("approval recorded" in m for m in run_main(
        monkeypatch, capsys, invocation(repo, transcript=t)))
    assert len(sg.read_ledger(str(repo), "auth-mvp")) == 2


def test_unknown_origin_is_not_minted(repo, monkeypatch, capsys):
    milestone(repo, "auth-mvp")
    # no transcript: nothing to read
    assert not any("approval recorded" in m for m in run_main(monkeypatch, capsys, invocation(repo)))
    assert sg.read_ledger(str(repo), "auth-mvp") == []


def test_stashed_messages_are_delivered_once(repo, monkeypatch, capsys):
    run_main(monkeypatch, capsys, invocation(repo, "hi"))
    approve.stash(sg.store_dir(str(repo)), "c1", "plan-swarm: approval recorded for x")
    assert run_main(monkeypatch, capsys, invocation(repo, "hi")) == ["plan-swarm: approval recorded for x"]
    assert run_main(monkeypatch, capsys, invocation(repo, "hi")) == []


def test_hook_errors_are_reported_not_raised(repo, monkeypatch, capsys):
    monkeypatch.setattr(approve, "pre_invocation", lambda event: 1 / 0)
    messages = run_main(monkeypatch, capsys, invocation(repo, "hi"))
    assert "no approval was recorded" in messages[0]


def test_concurrent_hook_processes_mint_once(repo):
    import subprocess
    import sys
    from conftest import LIB
    milestone(repo, "auth-mvp")
    event = json.dumps(invocation(repo, "approve spec auth-mvp"))
    procs = [subprocess.Popen([sys.executable, os.path.join(LIB, "approve.py")], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(repo))
             for _ in range(6)]
    outs = [p.communicate(event)[0] for p in procs]
    assert sum("approval recorded" in o for o in outs) == 1, outs
    assert len(sg.read_ledger(str(repo), "auth-mvp")) == 1


def test_phrase_in_non_swarm_repo_is_neutral_and_leaves_no_store(tmp_path, monkeypatch):
    """A phrase typed in a repository without plans/swarm.md records nothing and does not
    create .git/plan-swarm (the live probe in a plain workspace)."""
    plain = tmp_path / "plain"
    plain.mkdir()
    git(plain, "init", "-q", "-b", "main")
    monkeypatch.delenv("PLAN_SWARM_TEST", raising=False)
    monkeypatch.delenv("PLAN_SWARM_STORE", raising=False)
    assert approve.pre_invocation(invocation(plain, "approve spec probe-milestone")) == []
    assert not (plain / ".git" / "plan-swarm").exists()
    assert not (plain / "plans").exists()
