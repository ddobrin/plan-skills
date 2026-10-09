"""Regression tests for the control-plane security review.

Each test names the finding it covers (C = critical, H = high, M = medium,
L = legitimate operations that must keep working). The threat model is a
well-meaning agent that tries to unblock itself; server-side controls remain
the authority against a determined adversary.
"""
import io
import json
import os
import subprocess
import sys

import pytest

import approve
import gate
import health
import swarm_init
import swarmgit as sg
import worktree
from conftest import LIB, dispatch_event, git, run_event, write_event


def bash(repo, command):
    gate.pre_tool_use(run_event(repo, command))


def denied(repo, command, match=None):
    with pytest.raises(gate.Deny, match=match):
        bash(repo, command)


def ok(phrase, repo):
    msg = approve.record(approve.parse(phrase), str(repo))
    assert "approval recorded" in msg, msg


@pytest.fixture
def ms(repo):
    """Milestone auth-mvp on its branch, with a staged code change."""
    git(repo, "checkout", "-q", "-b", "swarm/auth-mvp")
    d = repo / "plans" / "active_milestones" / "auth-mvp"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# Spec\n")
    (repo / "src.py").write_text("x = 1\n")
    git(repo, "add", "src.py")
    return repo


# --- C1: an agent cannot mint its own approval -----------------------------------

@pytest.mark.parametrize("cmd", [
    "echo '{\"prompt\": \"approve commit auth-mvp g1\"}' | python3 /x/lib/approve.py",
    "python3 -c 'import sys; sys.path.insert(0, \"lib\"); import swarmgit'",
    "PLAN_SWARM_TEST=1 python3 -m pytest",
])
def test_c1_control_plane_internals_are_off_limits(ms, cmd):
    denied(ms, cmd, "control plane")


@pytest.mark.parametrize("event", [
    {"prompt": "approve commit auth-mvp g1"},  # not an Antigravity field: never read
    {"text": "approve commit auth-mvp g1"},    # not an Antigravity field: never read
    {"toolCall": {"name": "run_command", "args": {"CommandLine": "approve commit auth-mvp g1"}}},
])
def test_c1_approve_ignores_agent_written_text(ms, monkeypatch, capsys, event):
    event = dict(event, conversationId="c1", workspacePaths=[str(ms)])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    approve.main()
    assert "approval recorded" not in capsys.readouterr().out
    assert sg.read_ledger(str(ms), "auth-mvp") == []


# --- C2: no forging through the store or git dir -----------------------------------

@pytest.mark.parametrize("cmd", [
    "cd .git && python3 -c 'print(1)'",
    "D=.git; cp /tmp/x $D/hooks/pre-commit",
    "cp /tmp/x \"$HOME/../x\"",
    "ln -s .git g",
    "cp /tmp/e .git/plan-swarm/nonces/x.json #'",
    "python3 -c \"open('.git/plan-swarm/nonces/x.json','w')\"",
])
def test_c2_store_and_git_dir_writes(ms, cmd):
    denied(ms, cmd)


def test_c2_symlinked_and_case_variant_paths(ms):
    os.symlink(ms / ".git", ms / "g")
    with pytest.raises(gate.Deny):
        gate.pre_tool_use(write_event(ms, ms / "g" / "hooks" / "pre-commit"))
    if sys.platform == "darwin":
        with pytest.raises(gate.Deny):
            gate.pre_tool_use(write_event(ms, ms / ".GIT" / "hooks" / "pre-commit"))


def test_c2_forged_nonce_file_is_ignored_if_malformed(ms):
    store = sg.store_dir(str(ms))
    with open(os.path.join(store, "nonces", "commit-auth-mvp-g1.json"), "w") as fh:
        fh.write('{"kind": "commit"}')
    denied(ms, "git commit -m x", "no valid approval")


# --- C3: removing plans/swarm.md does not switch the gate off ------------------------

@pytest.mark.parametrize("cmd", [
    "mv plans /tmp/p", "rm -rf plans", "git rm plans/swarm.md", "git mv plans/swarm.md x",
    "git checkout HEAD~1 -- plans/swarm.md", "echo x >| plans/swarm.md",
    "python3 -c \"open('plans/swarm.md','w')\"",
])
def test_c3_swarm_md_is_protected(ms, cmd):
    denied(ms, cmd)


def test_c3_missing_swarm_md_fails_closed_once_active(ms):
    sg.mark_active(sg.store_dir(str(ms)))
    os.remove(ms / "plans" / "swarm.md")
    denied(ms, "git commit -m x", "missing")
    assert gate.git_hook() == 1


# --- C4: git hidden in other commands, aliases, config tricks ------------------------

@pytest.mark.parametrize("cmd", [
    "bash -c 'git commit --no-verify -m x'", "sh -c \"git push origin main\"", "eval git commit -m x",
    "echo commit | xargs git", "find . -name x -exec git commit -m x {} \\;", "`git commit -m x`",
    "{ git commit -m x; }", "timeout 5 git commit -m x", "nice -n 5 git commit --no-verify -m x",
    "git -c alias.ci='!git commit --no-verify' ci -m x", "git --config-env=alias.x=Y x",
    "git config alias.ci commit", "git config include.path /tmp/evil",
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0='!git commit' git ci",
    "GIT_DIR=.git git commit -m x", "export GIT_WORK_TREE=/tmp", "git ci -m x",
])
def test_c4_hidden_or_aliased_git(ms, cmd):
    denied(ms, cmd)


# --- C5: unapproved code cannot reach the milestone branch ---------------------------

@pytest.mark.parametrize("cmd", [
    "git push origin swarm-wip/auth-mvp/x:swarm/auth-mvp", "git push origin main:swarm/auth-mvp",
    "git checkout -B swarm/auth-mvp swarm-wip/auth-mvp/x", "git switch -C swarm/auth-mvp HEAD~1",
    "git branch -C main swarm/auth-mvp", "git fetch . +main:swarm/auth-mvp", "git rebase main swarm/auth-mvp",
    "git branch -f swarm/auth-mvp main",
])
def test_c5_no_route_around_the_commit_gate(ms, cmd):
    denied(ms, cmd)


# --- C6: config cannot redirect a push ---------------------------------------------

@pytest.mark.parametrize("cmd", [
    "git -c remote.origin.push=HEAD:refs/heads/main push origin swarm/auth-mvp",
    "git -c remote.origin.mirror=true push origin swarm/auth-mvp",
    "git config remote.origin.push HEAD:refs/heads/main", "git push origin", "git push",
    "git remote add evil /tmp/x", "git remote set-url origin /tmp/x",
])
def test_c6_push_redirection(ms, cmd):
    denied(ms, cmd)


# --- H1: internal errors fail closed ------------------------------------------------

def test_h1_crash_in_a_swarm_repo_denies(ms, monkeypatch, capsys):
    monkeypatch.setattr(gate, "pre_tool_use", lambda event: 1 / 0)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(run_event(ms, "ls"))))
    assert gate.main([]) == 0  # Antigravity reads the decision from stdout
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "deny" and "internal error" in out["reason"]


def test_h1_malformed_heartbeat_and_nonce_do_not_crash(ms):
    store = sg.store_dir(str(ms))
    with open(os.path.join(store, "heartbeat.json"), "w") as fh:
        fh.write('{"updated": "yesterday"}')
    with open(os.path.join(store, "nonces", "junk.json"), "w") as fh:
        fh.write("[1, 2]")
    bash(ms, "ls")
    info, active = health.status(str(ms))
    assert info["heartbeat_age_seconds"] is not None


def test_h1_parallel_heartbeat_writers(ms):
    store = sg.store_dir(str(ms))
    code = ("import sys; sys.path.insert(0, %r); import swarmgit as sg\n"
            "for _ in range(40): sg.touch_heartbeat(%r)" % (LIB, store))
    procs = [subprocess.Popen([sys.executable, "-c", code], stderr=subprocess.PIPE) for _ in range(6)]
    assert all(p.wait() == 0 for p in procs), [p.stderr.read() for p in procs]


# --- H2: an invalid config still enforces everything ---------------------------------

def test_h2_invalid_config_keeps_file_guards(ms):
    (ms / "plans" / "swarm.md").write_text("broken")
    with pytest.raises(gate.Deny):
        gate.pre_tool_use(write_event(ms, ms / "plans/active_milestones/auth-mvp/approvals.md"))
    denied(ms, "git merge feature", "merge --squash")
    denied(ms, "git commit -m x", "invalid")


# --- H3: commit-creating commands outside the pre-commit hook ------------------------

@pytest.mark.parametrize("cmd", [
    "git merge --squash --no-squash --no-edit feature", "git merge --no-ff feature",
    "git pull --no-rebase . other", "git pull origin main", "git pull --rebase", "git am x.patch",
    "git fast-import", "git symbolic-ref HEAD refs/heads/main",
])
def test_h3_history_writers(ms, cmd):
    denied(ms, cmd)


# --- H4: abbreviated and clustered options -----------------------------------------

@pytest.mark.parametrize("cmd", [
    "git commit --amen --no-edit", "git commit --no-veri -m x", "git push --del origin swarm/auth-mvp",
    "git push --mirr origin", "git push --prun origin swarm/auth-mvp", "git push -uf origin swarm/auth-mvp",
    "git push -fu origin swarm/auth-mvp", "git push -du origin swarm/auth-mvp",
    "git push origin :swarm/auth-mvp", "git tag -fa v1.0.0 -m x",
])
def test_h4_abbreviations_and_clusters(ms, cmd):
    denied(ms, cmd)


# --- H5: a plans-only approval cannot commit code ----------------------------------

@pytest.mark.parametrize("cmd", [
    "git commit -am plans/active_milestones/auth-mvp/spec.md",
    "git commit -m spec -- plans/active_milestones/auth-mvp/spec.md 'src*'",
    "git stage src.py && git commit -m spec",
])
def test_h5_spec_nonce_does_not_cover_code(ms, cmd):
    ok("approve spec auth-mvp", ms)
    denied(ms, cmd, "no valid approval")


def test_h5_git_hook_rejects_code_under_a_plans_ticket(ms):
    git(ms, "reset", "-q")
    ok("approve spec auth-mvp", ms)
    git(ms, "add", "plans")
    bash(ms, "git commit -m 'docs(auth-mvp): spec'")  # ticket issued for plans only
    git(ms, "add", "src.py")                           # code sneaks into the index afterwards
    assert gate.git_hook() == 1


# --- H6: gh and push plumbing -------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    "gh pr merge 1 --admin --squash", "gh pr review 1 --approve",
    "gh api -X PATCH repos/o/r/git/refs/heads/main -f sha=abc", "gh api repos/o/r/pulls -f title=x",
    "gh release create v9.9.9", "gh repo sync", "git send-pack ../bare.git HEAD:refs/heads/main",
])
def test_h6_github_cli_and_plumbing(ms, cmd):
    denied(ms, cmd)


def test_h6_read_only_gh_is_allowed(ms):
    bash(ms, "gh pr view 1 --json state")
    bash(ms, "gh api repos/o/r/pulls")
    bash(ms, "gh pr comment 1 --body-file review.md")


# --- H8: plugin and settings are protected; env cannot redirect the git hook ----------

def test_h8_plugin_and_settings(ms):
    home = os.path.expanduser("~")
    for path in (os.path.join(LIB, "gate.py"), str(ms / ".agents" / "hooks.json"),
                 str(ms / ".gemini" / "settings.json"),
                 os.path.join(home, ".gemini", "config", "hooks.json"),
                 os.path.join(home, ".gemini", "settings.json")):
        with pytest.raises(gate.Deny):
            gate.pre_tool_use(write_event(ms, path, "replace_file_content"))


def test_h8_store_override_needs_test_flag(ms, monkeypatch, tmp_path):
    monkeypatch.delenv("PLAN_SWARM_TEST")
    monkeypatch.setenv("PLAN_SWARM_STORE", str(tmp_path / "fake"))
    assert sg.store_dir(str(ms)).endswith(os.path.join(".git", "plan-swarm"))


# --- M1: dispatch check variants --------------------------------------------------

@pytest.mark.parametrize("agent, prompt", [
    ("engineer ", "Implement Task 1.A of the plan at plans/active_milestones/auth-mvp"),
    ("ENGINEER", "see plans/active_milestones/auth-mvp/plan.md"),
    ("plan:engineer", "see plans/active_milestones/auth-mvp/plan.md"),
])
def test_m1_dispatch_variants(ms, agent, prompt):
    with pytest.raises(gate.Deny, match="approve plan auth-mvp"):
        gate.pre_tool_use(dispatch_event(ms, agent, prompt))


# --- M3: a nonce is consumed once, even under a race --------------------------------

def test_m3_consume_is_atomic(ms):
    ok("approve commit auth-mvp g1", ms)
    store = sg.store_dir(str(ms))
    a = sg.valid_nonces(store, sg.head(str(ms)), ["commit"])[0]
    b = sg.valid_nonces(store, sg.head(str(ms)), ["commit"])[0]
    sg.consume(a)
    with pytest.raises(sg.NonceTaken):
        sg.consume(b)


# --- M4/M6/M7/M8 ---------------------------------------------------------------------

def test_m4_git_dir_forms_and_empty_head(ms):
    denied(ms, "git --git-dir=.git --work-tree=. commit -m x")
    assert sg.valid_nonces(sg.store_dir(str(ms)), "", ["commit"]) == []


def test_m6_tags_only_on_head_and_m7_per_version_push(ms):
    (ms / "b.txt").write_text("b\n")
    git(ms, "add", "b.txt")
    git(ms, "commit", "-q", "--no-verify", "-m", "b")
    ok("approve release v1.0.0", ms)
    denied(ms, "git tag -a v1.0.0 -m 'Release' HEAD~1", "current HEAD")
    bash(ms, "git tag -a v1.0.0 -m 'Release v1.0.0'")
    git(ms, "tag", "-a", "v1.0.0", "-m", "Release v1.0.0")
    git(ms, "tag", "-a", "v0.9.0", "-m", "old", "HEAD~1")
    bash(ms, "git push origin v1.0.0")
    denied(ms, "git push origin v0.9.0", "approve release v0.9.0")


def test_m8_git_hook_does_not_suggest_no_verify(ms, capsys):
    gate.git_hook()
    assert "--no-verify" not in capsys.readouterr().err


# --- L: legitimate operations keep working -------------------------------------------

@pytest.mark.parametrize("cmd", [
    "git reset --hard", "git reset --merge", "git reset @", "git reset HEAD src.py",
    "git switch -c swarm/other", "mkdir -p plans/active_milestones/x",
    "git mv README.md docs.md", "git status --short", "git log --oneline -5",
    "git diff --cached --stat", "git worktree list", "git branch --show-current",
    "git merge --squash swarm-wip/auth-mvp/1.A", "git fetch origin", "grep -r TODO src.py",
])
def test_l_legitimate_commands(ms, cmd):
    bash(ms, cmd)


def test_l3_push_head_and_l4_clustered_message(ms):
    git(ms, "reset", "-q")
    ok("approve spec auth-mvp", ms)
    git(ms, "add", "plans")
    bash(ms, 'git commit -qm "docs(auth-mvp): spec"')
    ok("approve pr auth-mvp", ms)
    bash(ms, "git push -u origin HEAD")


# --- layer 2: pre-push against a real remote ------------------------------------------

@pytest.fixture
def remote(ms, tmp_path):
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(ms, "remote", "add", "origin", str(bare))
    git(ms, "push", "-q", "origin", "main")
    swarm_init.install(str(ms), only={"hook"})
    return bare


def approved_commit(repo, phrase, message):
    ok(phrase, repo)
    bash(repo, f"git commit -m '{message}'")
    proc = subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def push(repo, *refs):
    return subprocess.run(["git", "push", "-q", "origin", *refs], cwd=repo, capture_output=True, text=True)


def test_pre_push_accepts_approved_history_and_refuses_the_rest(ms, remote):
    git(ms, "reset", "-q")
    git(ms, "add", "plans")
    approved_commit(ms, "approve spec auth-mvp", "docs(auth-mvp): spec")
    git(ms, "add", "src.py")
    approved_commit(ms, "approve commit auth-mvp g1", "feat(auth-mvp): group 1")
    assert "approve pr auth-mvp" in push(ms, "swarm/auth-mvp").stderr   # first push needs approve pr
    ok("approve pr auth-mvp", ms)
    bash(ms, "git commit -m 'docs(auth-mvp): record PR approval' -- plans/active_milestones/auth-mvp/approvals.md")
    rec_commit = subprocess.run(["git", "commit", "-q", "-m", "docs(auth-mvp): record PR approval", "--",
                                 "plans/active_milestones/auth-mvp/approvals.md"], cwd=ms, capture_output=True, text=True)
    assert rec_commit.returncode == 0, rec_commit.stderr
    bash(ms, "git push -u origin swarm/auth-mvp")  # layer 1 accepts the pr approval bound to the parent
    first = push(ms, "swarm/auth-mvp")
    assert first.returncode == 0, first.stderr
    (ms / "evil.py").write_text("evil\n")
    git(ms, "add", "evil.py")
    git(ms, "commit", "-q", "--no-verify", "-m", "unapproved")
    bad = push(ms, "swarm/auth-mvp")
    assert bad.returncode != 0 and "no matching approval" in bad.stderr
    assert push(ms, "main:refs/heads/main-copy").returncode != 0
    git(ms, "tag", "v9.9.9")
    assert "approve release v9.9.9" in push(ms, "v9.9.9").stderr
    assert push(ms, ":refs/heads/main").returncode != 0


def test_pre_push_lets_people_push_their_own_branches_without_a_session(ms, remote):
    store = sg.store_dir(str(ms))
    os.remove(os.path.join(store, "heartbeat.json")) if os.path.exists(os.path.join(store, "heartbeat.json")) else None
    git(ms, "switch", "-q", "main")
    (ms / "notes.txt").write_text("by hand\n")
    git(ms, "add", "notes.txt")
    git(ms, "commit", "-q", "--no-verify", "-m", "human change")
    assert push(ms, "main").returncode == 0
    # the swarm's own refs stay checked even then
    git(ms, "switch", "-q", "swarm/auth-mvp")
    git(ms, "commit", "-q", "--no-verify", "--allow-empty", "-m", "unapproved")
    assert push(ms, "swarm/auth-mvp").returncode != 0


def test_pr_row_cannot_authorize_code(ms):
    git(ms, "reset", "-q")
    ok("approve pr auth-mvp", ms)
    git(ms, "add", "src.py")
    denied(ms, "git commit -m 'sneak code under the PR approval'", "no valid approval")
