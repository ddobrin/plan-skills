import os
import pytest

from geap_validator_core import report
from geap_validator_core.stages import SPEC_STAGE, PLAN_STAGE

THREE_MODELS = ["gemini-3.5-flash", "claude-haiku-4-5", "gemini-3-1-flash-lite"]


# ---------------------------------------------------------------- path resolution

def test_resolve_report_path_derives_moniker(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path, moniker = report.resolve_report_path("plans/active_milestones/wobbly-moose/spec.md", SPEC_STAGE)
    assert moniker == "wobbly-moose"
    assert os.path.normpath(path) == os.path.normpath(
        "plans/active_milestones/wobbly-moose/adversarial-reviews/geap-spec-validation.md"
    )


def test_resolve_report_path_anchors_to_artifact_prefix(tmp_path):
    """An absolute artifact path keeps the report next to the artifact, not in CWD."""
    artifact = str(tmp_path / "repo" / "plans" / "active_milestones" / "m1" / "plan.md")
    path, moniker = report.resolve_report_path(artifact, PLAN_STAGE)
    assert moniker == "m1"
    expected_dir = str(tmp_path / "repo" / "plans" / "active_milestones" / "m1" / "adversarial-reviews")
    assert os.path.dirname(path) == expected_dir
    assert os.path.basename(path) == "geap-plan-validation.md"


def test_resolve_report_path_moniker_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path, moniker = report.resolve_report_path("/somewhere/else/spec.md", SPEC_STAGE, moniker_override="forced-m")
    assert moniker == "forced-m"
    assert os.path.normpath(path) == os.path.normpath(
        "plans/active_milestones/forced-m/adversarial-reviews/geap-spec-validation.md"
    )


def test_resolve_report_path_fallback_for_bare_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path, moniker = report.resolve_report_path("docs/spec.md", SPEC_STAGE)
    assert moniker is None
    assert os.path.normpath(path) == os.path.normpath("plans/adversarial-reviews/geap-spec-validation.md")


def test_resolve_report_path_rerun_suffixes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out_dir = tmp_path / "plans" / "active_milestones" / "m2" / "adversarial-reviews"
    out_dir.mkdir(parents=True)

    (out_dir / "geap-spec-validation.md").write_text("run 1")
    path, _ = report.resolve_report_path("plans/active_milestones/m2/spec.md", SPEC_STAGE)
    assert os.path.basename(path) == "geap-spec-validation-r2.md"

    (out_dir / "geap-spec-validation-r2.md").write_text("run 2")
    path, _ = report.resolve_report_path("plans/active_milestones/m2/spec.md", SPEC_STAGE)
    assert os.path.basename(path) == "geap-spec-validation-r3.md"


# ---------------------------------------------------------------- markdown rendering

SPEC_CONFIRMED = {
    "id": "issue-one", "clause": "quote1", "severity": "high",
    "interpretation": "int1", "harm": "harm1", "tightening": "t1", "votes": 3,
}
SPEC_UNCONFIRMED = {
    "id": "issue-two", "clause": "quote2", "severity": "low",
    "interpretation": "int2", "harm": "harm2", "tightening": "t2", "votes": 1,
}


def test_format_markdown_report_spec():
    text = report.format_markdown_report(
        SPEC_STAGE, "plans/active_milestones/m/spec.md", "m",
        confirmed=[SPEC_CONFIRMED], unconfirmed=[SPEC_UNCONFIRMED],
        no_hole_notes=["bypass-auth"], agent_models=THREE_MODELS,
        synthesis_model="gemini-3-1-flash-lite",
    )
    assert text.startswith("# Spec Adversarial Review (GEAP remote panel)")
    assert "Validation **FAILED**" in text
    assert "### 🔴 `issue-one` · 3/4 votes · severity high" in text
    assert "- **Clause:** `\"quote1\"`" in text
    assert "- **Tightening:** t1" in text
    assert "| `issue-two` | 🟡 low |" in text
    assert "## Attacks That Failed" in text
    assert "- `bypass-auth`" in text
    assert "First domino" not in text  # spec stage has no domino row
    assert "- [ ] Resolved `issue-one` in the spec" in text


PLAN_CONFIRMED = {
    "id": "step-gap", "step": "3", "category": "ordering", "failure": "breaks",
    "evidence": "ev1", "confidence": "high", "severity": "medium", "fix": "reorder", "votes": 2,
}


def test_format_markdown_report_plan():
    text = report.format_markdown_report(
        PLAN_STAGE, "plans/active_milestones/m/plan.md", "m",
        confirmed=[PLAN_CONFIRMED], unconfirmed=[],
        no_hole_notes=[], agent_models=THREE_MODELS,
        synthesis_model="gemini-3-1-flash-lite", first_domino="step-gap",
    )
    assert text.startswith("# Plan Adversarial Review (GEAP remote panel)")
    assert "| 🁢 First domino | `step-gap` |" in text
    assert "### 🟠 `step-gap` · 2/4 votes · severity medium · ordering · confidence high" in text
    assert "- **Evidence:** `\"ev1\"`" in text
    assert "- **Fix:** reorder" in text
    assert "## Checks That Passed" in text


def test_format_markdown_report_clean_pass():
    text = report.format_markdown_report(
        SPEC_STAGE, "spec.md", None,
        confirmed=[], unconfirmed=[],
        no_hole_notes=["probe-a", "probe-b"], agent_models=THREE_MODELS,
        synthesis_model="gemini-3-1-flash-lite",
    )
    assert "Validation **PASSED**" in text
    assert "| Milestone | `—` |" in text
    assert "_None._" in text  # empty findings sections still rendered
    assert "- `probe-a`" in text
