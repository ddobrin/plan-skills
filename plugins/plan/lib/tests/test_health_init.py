import json
import os

import health
import swarm_init
import swarmgit as sg
from conftest import git, run_event


def test_status_reports_off_without_heartbeat_and_active_with_one(repo):
    info, active = health.status(str(repo))
    assert not active and info["enforcement"] == "OFF" and info["git_hook"].startswith("missing")
    sg.touch_heartbeat(sg.store_dir(str(repo)))
    info, active = health.status(str(repo))
    assert active and info["mode"] == "pr" and info["max_engineers"] == 5


def test_status_outside_swarm_repo(repo):
    os.remove(repo / "plans" / "swarm.md")
    info, active = health.status(str(repo))
    assert not active and "swarm-init" in info["message"]


def test_announce_message_plan_lib_and_invalid_config(repo, tmp_path):
    msg = health.announce({"conversationId": "c1", "workspacePaths": [str(repo)]}, str(repo))
    assert "enforcement active" in msg and "Git hooks missing" in msg
    assert f"PLAN_LIB={health.LIB}" in msg and "typed by the user" in msg
    assert sg.is_active(sg.store_dir(str(repo)))
    assert sg.heartbeat(sg.store_dir(str(repo)))["conversation"] == "c1"
    sub_t = tmp_path / "sub.jsonl"
    sub_t.write_text(json.dumps({"step_index": 0, "type": "SYSTEM_MESSAGE", "content": "[Message] sender=c1 content=hi"}) + "\n")
    sub = health.announce({"conversationId": "c2", "transcriptPath": str(sub_t)}, str(repo))
    assert "only the auditor commits" in sub and "PLAN_LIB=" in sub
    (repo / "plans" / "swarm.md").write_text("broken")
    assert "Gated operations are refused" in health.announce({}, str(repo))


def test_announce_is_silent_outside_swarm_repos(repo):
    os.remove(repo / "plans" / "swarm.md")
    assert health.announce({}, str(repo)) is None


def test_status_reports_plan_lib_and_cli(repo, capsys):
    assert health.status(str(repo))[0]["plan_lib"] == health.LIB
    sg.touch_heartbeat(sg.store_dir(str(repo)))
    assert health.main(["--status"]) == 0
    assert json.loads(capsys.readouterr().out)["enforcement"] == "active"
    assert health.main([]) == 2


def test_swarm_init_installs_without_overwriting(repo):
    os.remove(repo / "plans" / "swarm.md")
    dry = swarm_init.install(str(repo), dry_run=True)
    assert ("swarm", "would install", os.path.join("plans", "swarm.md")) in dry
    res = dict((n, s) for n, s, _ in swarm_init.install(str(repo)))
    assert res["swarm"] == "installed"
    assert all(res[f"hook:{h}"] == "installed" for h in health.HOOK_NAMES)
    assert all(health.git_hook_installed(str(repo), h) for h in health.HOOK_NAMES)
    assert os.path.exists(os.path.join(sg.store_dir(str(repo)), "bin", "gate.py"))
    assert sg.is_active(sg.store_dir(str(repo)))
    again = dict((n, s) for n, s, _ in swarm_init.install(str(repo)))
    assert again["swarm"] == "exists" and again["hook:pre-push"] == "exists"


def test_swarm_init_installs_agents_md_only_without_project_instructions(repo):
    res = {n: (s, d) for n, s, d in swarm_init.install(str(repo), only={"agents"})}
    assert res["agents"] == ("installed", "AGENTS.md")
    assert (repo / "AGENTS.md").read_text().startswith("# AGENTS.md")
    assert not (repo / "CLAUDE.md").exists()
    # "claude" and "gemini" are accepted as other names of the item
    assert swarm_init.install(str(repo), only={"claude"})[0][:2] == ("agents", "exists")
    assert swarm_init.install(str(repo), only={"gemini"})[0][:2] == ("agents", "exists")


def test_swarm_init_keeps_an_existing_gemini_md(repo):
    (repo / "GEMINI.md").write_text("# GEMINI.md\n")
    name, state, detail = swarm_init.install(str(repo), only={"agents"})[0]
    assert (name, state) == ("agents", "exists") and detail.startswith("GEMINI.md")
    assert not (repo / "AGENTS.md").exists()  # Antigravity already reads GEMINI.md as project rules


def test_swarm_init_prefers_an_existing_agents_md(repo):
    (repo / "AGENTS.md").write_text("# AGENTS.md\n")
    (repo / "GEMINI.md").write_text("# GEMINI.md\n")
    assert swarm_init.install(str(repo), only={"agents"})[0][1:] == ("exists", "AGENTS.md")


def test_swarm_init_cli(repo, capsys):
    os.remove(repo / "plans" / "swarm.md")
    assert swarm_init.main(["--dry-run", "--root", str(repo)]) == 0
    assert "would install" in capsys.readouterr().out


def test_swarm_init_reports_foreign_hook(repo):
    hook = health.hook_path(str(repo))
    os.makedirs(os.path.dirname(hook), exist_ok=True)
    with open(hook, "w") as fh:
        fh.write("#!/bin/sh\nnpx lint-staged\n")
    res = {n: (s, d) for n, s, d in swarm_init.install(str(repo), only={"hook"})}
    assert res["hook:pre-commit"][0] == "exists" and "--git-hook" in res["hook:pre-commit"][1]
    assert res["hook:pre-push"][0] == "installed"


def test_installed_git_hook_blocks_unapproved_commit_end_to_end(repo):
    swarm_init.install(str(repo), only={"hook"})
    git(repo, "checkout", "-q", "-b", "swarm/auth-mvp")
    (repo / "x.py").write_text("x\n")
    git(repo, "add", "x.py")
    import subprocess
    proc = subprocess.run(["git", "commit", "-m", "sneaky"], cwd=repo, capture_output=True, text=True)
    assert proc.returncode != 0 and "need an approval phrase" in proc.stderr


def ledger_check_script():
    import re
    from conftest import PLUGIN
    text = open(os.path.join(PLUGIN, "templates", "ci", "plan-swarm.yml")).read()
    body = re.search(r"python3 - <<'PY'\n(.*?)\n\s*PY\n", text, re.S).group(1)
    return "\n".join(line[10:] if line.startswith(" " * 10) else line for line in body.splitlines())


def test_ci_ledger_check_matches_commits_to_approvals(repo, tmp_path, monkeypatch):
    import subprocess
    import approve
    import gate
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "swarm/auth-mvp")
    d = repo / "plans" / "active_milestones" / "auth-mvp"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# Spec\n")
    approve.record(approve.parse("approve plan auth-mvp tier=elevated"), str(repo))
    git(repo, "add", "-A")
    gate.pre_tool_use(run_event(repo, "git commit -m plan"))
    git(repo, "commit", "-q", "-m", "plan")  # hook not installed here; the gate allowed it above
    out = tmp_path / "gh_out"
    env = dict(os.environ, BASE=base, MILESTONE="swarm/auth-mvp", GITHUB_OUTPUT=str(out))
    script = ledger_check_script()
    ok = subprocess.run(["python3", "-c", script], cwd=repo, env=env, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "tier=elevated" in out.read_text()
    approve.record(approve.parse("approve pr auth-mvp"), str(repo))
    gate.pre_tool_use(run_event(repo, "git commit -m rec -- plans/active_milestones/auth-mvp/approvals.md"))
    git(repo, "commit", "-q", "-m", "rec", "--", "plans/active_milestones/auth-mvp/approvals.md")
    rec_ok = subprocess.run(["python3", "-c", script], cwd=repo, env=env, capture_output=True, text=True)
    assert rec_ok.returncode == 0, rec_ok.stdout + rec_ok.stderr   # the ledger-only PR record is accepted
    (repo / "sneaky.py").write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--no-verify", "-m", "unapproved")
    bad = subprocess.run(["python3", "-c", script], cwd=repo, env=env, capture_output=True, text=True)
    assert bad.returncode == 1 and "unapproved" in bad.stdout
