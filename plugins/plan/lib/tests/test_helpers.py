import json
import os

import pytest

import approve
import metrics
import prbody
import swarmgit as sg
import tier
import usage
import worktree
from conftest import git


def mdir(repo, m="auth-mvp"):
    d = repo / "plans" / "active_milestones" / m
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- usage -----------------------------------------------------------------------

def test_usage_log_decline_and_summary(repo):
    mdir(repo)
    assert usage.main(["log", "--milestone", "auth-mvp", "--phase", "2", "--agent", "architect",
                       "--tokens", "1200", "--tools", "14", "--ms", "65000"]) == 0
    assert usage.main(["decline", "--milestone", "auth-mvp", "--gate", "plan-validator", "--tier", "elevated"]) == 0
    s = usage.summary(str(repo), "auth-mvp")
    assert s == {"dispatches": 1, "tokens": 1200, "tool_uses": 14, "seconds": 65,
                 "declined_gates": ["plan-validator (elevated)"]}
    assert usage.main(["log", "--milestone", "../x", "--agent", "a"]) == 2


# --- tier ------------------------------------------------------------------------

def test_tier_rises_with_stage_and_never_falls(repo):
    d = mdir(repo)
    (d / "intent.md").write_text("# Intent: login limits\n## Problem\nBrute force on login.\n")
    r = tier.evaluate(str(repo), "auth-mvp", "intent")
    assert r["tier"] == "routine" and r["reasons"] == []
    (d / "plan.md").write_text("# Technical Plan\n- Task 1.A → `src/auth/attempts.ts`\n- `plans/x.md`\n")
    r = tier.evaluate(str(repo), "auth-mvp", "plan")
    assert r["tier"] == "critical" and "src/auth/attempts.ts" in r["reasons"][0]
    tier.write_line(str(d / "plan.md"), r)
    assert "**Risk tier (proposed):** `critical`" in (d / "plan.md").read_text()
    (d / "plan.md").write_text((d / "plan.md").read_text().replace("src/auth/attempts.ts", "src/x.ts"))
    r = tier.evaluate(str(repo), "auth-mvp", "plan")
    assert r["tier"] == "critical" and "never fall" in r["reasons"][0]


def test_tier_keywords_and_diff_size(repo):
    d = mdir(repo)
    (d / "intent.md").write_text("Add a response cache to the api.\n")
    assert tier.evaluate(str(repo), "auth-mvp", "intent")["tier"] == "elevated"
    (d / "intent.md").write_text("Store payment tokens.\n")
    assert tier.evaluate(str(repo), "auth-mvp", "intent")["tier"] == "critical"
    # word boundaries: 'tokenizer' is not 'token'
    assert tier.keyword_hits("a tokenizer", ["token"]) == []


def test_tier_diff_stage_flags_confirmed_mismatch(repo):
    d = mdir(repo)
    (d / "intent.md").write_text("small tweak\n")
    (d / "plan.md").write_text("# Plan\n")
    approve.record(approve.parse("approve plan auth-mvp tier=routine"), str(repo))
    git(repo, "checkout", "-q", "-b", "swarm/auth-mvp")
    (repo / "migrations").mkdir()
    (repo / "migrations" / "001.sql").write_text("drop table x;\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--no-verify", "-m", "m")
    r = tier.evaluate(str(repo), "auth-mvp", "diff")
    assert r["tier"] == "critical" and r["exceeds_confirmed"]


# --- worktrees -----------------------------------------------------------------------

def test_worktree_group_lifecycle(repo):
    git(repo, "checkout", "-q", "-b", "swarm/auth-mvp")
    a = worktree.create(str(repo), "auth-mvp", "1.A")
    b = worktree.create(str(repo), "auth-mvp", "1.B")
    assert a["branch"] == "swarm-wip/auth-mvp/1.A" and os.path.isdir(a["path"])
    assert ".swarm/" in open(os.path.join(repo, ".git", "info", "exclude")).read()
    open(os.path.join(a["path"], "a.py"), "w").write("a\n")          # left uncommitted: squash commits it
    open(os.path.join(b["path"], "b.py"), "w").write("b\n")
    git(b["path"], "add", "b.py")
    git(b["path"], "commit", "-q", "--no-verify", "-m", "wip b")
    code, out = worktree.squash(str(repo), "auth-mvp")
    assert code == 0 and out["squashed"] == ["1.A", "1.B"] and out["files"] == ["a.py", "b.py"]
    assert sg.changed_paths(str(repo)) == {"a.py", "b.py"}
    assert sg.branch(str(repo)) == "swarm/auth-mvp"
    assert worktree.cleanup(str(repo), "auth-mvp")["removed"] == ["swarm-wip/auth-mvp/1.A", "swarm-wip/auth-mvp/1.B"]
    assert worktree.task_branches(str(repo), "auth-mvp") == []


def test_worktree_squash_refuses_overlap_and_plans_edits(repo):
    git(repo, "checkout", "-q", "-b", "swarm/auth-mvp")
    for t in ("1.A", "1.B"):
        p = worktree.create(str(repo), "auth-mvp", t)["path"]
        open(os.path.join(p, "shared.py"), "w").write(t + "\n")
    code, out = worktree.squash(str(repo), "auth-mvp")
    assert code == 3 and out["overlapping_files"] == {"shared.py": ["1.A", "1.B"]}
    assert sg.changed_paths(str(repo)) == set()


def test_worktree_squash_refuses_dirty_checkout(repo):
    git(repo, "checkout", "-q", "-b", "swarm/auth-mvp")
    (repo / "README.md").write_text("dirty\n")
    code, out = worktree.squash(str(repo), "auth-mvp")
    assert code == 3 and out["paths"] == ["README.md"]


# --- PR body & metrics ------------------------------------------------------------------

def seeded_milestone(repo):
    d = mdir(repo)
    (d / "intent.md").write_text("# Intent: Login rate limit\n## Problem\nBrute force.\n## Outcome\nLockout after 5.\n")
    (d / "spec.md").write_text("# Product Specification: Login rate limiting\n")
    (d / "audit.md").write_text("# Audit\n### Group 1 · Round 1 · FAIL\n### Group 1 · Round 2 · PASS\n### Group 2 · Round 1 · PASS\n")
    (d / "adversarial-reviews").mkdir()
    (d / "adversarial-reviews" / "spec-validation.md").write_text("| Result | **2 confirmed** |\n")
    (d / "adversarial-reviews" / "spec-validation-r2.md").write_text("| Result | **0 confirmed** |\n")
    for phrase in ("approve spec auth-mvp", "approve plan auth-mvp tier=elevated", "approve commit auth-mvp g1"):
        approve.record(approve.parse(phrase), str(repo))
    usage.main(["decline", "--milestone", "auth-mvp", "--gate", "implementation-validator"])
    return d


def test_prbody_title_and_sections(repo):
    seeded_milestone(repo)
    assert prbody.title(str(repo), "auth-mvp") == "feat(auth-mvp): Login rate limiting"
    b = prbody.body(str(repo), "auth-mvp")
    for needle in ("## Intent", "**Problem.** Brute force.", "## Gates", "spec-validation.md`: **2 confirmed**",
                   "Declined: implementation-validator (elevated)", "- Group 1 · Round 2 · PASS", "| commit | 1 | elevated |"):
        assert needle in b, needle


def test_metrics(repo):
    seeded_milestone(repo)
    m = metrics.collect(str(repo), "auth-mvp")["milestones"][0]
    assert m["tier"] == "elevated" and m["groups_committed"] == 1
    assert m["audit_rounds_failed"] == 1 and m["first_pass_audit_rate"] == 0.5
    assert m["validator_reruns"] == 1
    assert m["lead_time_hours"]["spec_to_plan"] is not None
    (repo / "plans" / "intents" / "closed").mkdir(parents=True)
    (repo / "plans" / "intents" / "closed" / "old.md").write_text("x")
    (repo / "plans" / "intents" / "new.md").write_text("x")
    i = metrics.intent_metrics(str(repo))
    assert i == {"open": 1, "accepted": 1, "closed": 1, "survival_rate": 0.5}
    assert "first-pass audit 0.5" in metrics.as_text(metrics.collect(str(repo)))
