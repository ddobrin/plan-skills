import os
import pytest
from wf_model import parse_run, transcript_path, ParseError

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "wf_c8873586-bae.json")


def test_parse_run_header():
    r = parse_run(FIXTURE)
    assert r.run_id == "wf_c8873586-bae"
    assert r.workflow_name == "proofread-pr6408-review"
    assert r.agent_count == 13
    assert r.status == "completed"
    assert r.default_model == "claude-opus-4-8"


def test_parse_run_agents_and_phases():
    r = parse_run(FIXTURE)
    assert len(r.phases) == 1
    assert r.phases[0].title == "Verify"
    assert len(r.agents) == 13
    labels = [a.label for a in r.agents]
    assert all(l.startswith("verify:") for l in labels)
    a = r.agents[0]
    assert a.tokens is not None and a.duration_ms is not None


def test_transcript_path_shape():
    r = parse_run(FIXTURE)
    a = r.agents[0]
    p = transcript_path(r, a)
    assert p.endswith(os.path.join("subagents", "workflows", r.run_id, f"agent-{a.agent_id}.jsonl"))


def test_phase_keyed_by_marker_index_preserves_detail():
    # Regression: phases[] is 0-based but agents/markers use a 1-based
    # phaseIndex. Phases must be keyed by the marker index (so agents attach)
    # AND keep the detail text from phases[] (not a synthetic empty phase).
    r = parse_run(FIXTURE)
    assert len(r.phases) == 1
    p = r.phases[0]
    assert p.title == "Verify"
    assert p.index == 1                     # marker index, not array position 0
    assert p.detail == "one skeptic per inline comment"
    assert len(p.agents) == 13              # all agents attached to the real phase


def test_parse_run_malformed_json_raises_with_path(tmp_path):
    bad = tmp_path / "wf_bad.json"
    bad.write_text('{ "runId": "wf_bad", truncated', encoding="utf-8")
    with pytest.raises(ParseError) as ei:
        parse_run(str(bad))
    # design §7: the error must name the offending file and be a parse error
    assert str(bad) in str(ei.value)
