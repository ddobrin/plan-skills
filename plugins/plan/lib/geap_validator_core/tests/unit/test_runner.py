import os
import json
import pytest

from geap_validator_core import runner
from geap_validator_core.stages import SPEC_STAGE, PLAN_STAGE


def write_temp_file(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------- preprocessing

def test_preprocess_empty_file_fails(tmp_path):
    empty_file = write_temp_file(tmp_path, "empty.md", "")
    with pytest.raises(ValueError) as exc:
        runner.preprocess_input_file(empty_file)
    assert "empty" in str(exc.value)


def test_preprocess_missing_file_fails(tmp_path):
    with pytest.raises(ValueError) as exc:
        runner.preprocess_input_file(str(tmp_path / "nope.md"))
    assert "not found" in str(exc.value)


def test_preprocess_too_large_bytes_fails(tmp_path):
    large_file = write_temp_file(tmp_path, "large.md", "a" * (1024 * 1024 + 1))
    with pytest.raises(ValueError) as exc:
        runner.preprocess_input_file(large_file)
    assert "exceeds 1MB" in str(exc.value)


def test_preprocess_too_many_characters_fails(tmp_path):
    # Multibyte chars keep the byte size under 1MB while crossing the char limit
    large_char_file = write_temp_file(tmp_path, "large_char.md", "a" * 200001)
    with pytest.raises(ValueError) as exc:
        runner.preprocess_input_file(large_char_file)
    assert "exceeds 200,000" in str(exc.value)


# ---------------------------------------------------------------- argv stripping

def test_strip_cli_prefix():
    assert runner.strip_cli_prefix(
        ["plan", "geap-spec-validator", "--file", "x"], "geap-spec-validator"
    ) == ["--file", "x"]
    assert runner.strip_cli_prefix(["plan", "--file", "x"], "geap-spec-validator") == ["--file", "x"]
    assert runner.strip_cli_prefix(["geap-plan-validator", "--file", "x"], "geap-plan-validator") == ["--file", "x"]
    assert runner.strip_cli_prefix(["--file", "x"], "geap-spec-validator") == ["--file", "x"]
    assert runner.strip_cli_prefix([], "geap-spec-validator") == []


# ---------------------------------------------------------------- end-to-end (mocked APIs)

def _write_config(tmp_path):
    cfg = {
        "gcp_project_id": "test-project",
        "gcp_location": "us",
        "agent_1_model": "gemini-3.5-flash",
        "agent_2_model": "claude-haiku-4-5",
        "agent_3_model": "gemini-3-1-flash-lite",
        "synthesis_model": "gemini-3-1-flash-lite",
    }
    return write_temp_file(tmp_path, "config.json", json.dumps(cfg))


def test_main_spec_end_to_end(tmp_path, monkeypatch, capsys):
    """Full spec run under mocks: clean pass, exit 0, report in the fallback dir."""
    monkeypatch.chdir(tmp_path)
    cfg = _write_config(tmp_path)
    spec = write_temp_file(tmp_path, "spec.md", "# Spec\nThe system shall do things.")

    with pytest.raises(SystemExit) as exc:
        runner.main(SPEC_STAGE, ["--file", spec, "--config", cfg])
    assert exc.value.code == 0

    report_path = tmp_path / "plans" / "adversarial-reviews" / "geap-spec-validation.md"
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert content.startswith("# Spec Adversarial Review (GEAP remote panel)")
    assert "Validation **PASSED**" in content

    out = capsys.readouterr().out
    assert str(report_path) in out


def test_main_plan_end_to_end_with_milestone(tmp_path, monkeypatch):
    """Full plan run under mocks, invoked agy-style, report filed under the milestone."""
    monkeypatch.chdir(tmp_path)
    cfg = _write_config(tmp_path)
    milestone = tmp_path / "plans" / "active_milestones" / "m1"
    milestone.mkdir(parents=True)
    (milestone / "plan.md").write_text("# Plan\n1. Do the thing.", encoding="utf-8")

    argv = ["plan", "geap-plan-validator",
            "--file", "plans/active_milestones/m1/plan.md", "--config", cfg]
    with pytest.raises(SystemExit) as exc:
        runner.main(PLAN_STAGE, argv)
    assert exc.value.code == 0

    report_path = milestone / "adversarial-reviews" / "geap-plan-validation.md"
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert content.startswith("# Plan Adversarial Review (GEAP remote panel)")
    assert "First domino" in content
    assert "## Checks That Passed" in content


def test_main_missing_file_exits_with_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    cfg = _write_config(tmp_path)
    with pytest.raises(SystemExit) as exc:
        runner.main(SPEC_STAGE, ["--file", "does-not-exist.md", "--config", cfg])
    assert exc.value.code == 1
    assert "Validation Error" in capsys.readouterr().err
