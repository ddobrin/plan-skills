import pytest
from unittest.mock import AsyncMock, patch

from geap_validator_core import synthesis
from geap_validator_core.stages import SPEC_STAGE, PLAN_STAGE


def spec_finding(fid, clause, severity="high", **extra):
    f = {
        "id": fid, "clause": clause, "severity": severity,
        "interpretation": "int", "harm": "harm", "tightening": "t",
    }
    f.update(extra)
    return f


def consolidated(fid, clause, validated, severity="high"):
    return {
        "id": fid, "clause": clause, "severity": severity,
        "interpretation": "int", "harm": "harm", "tightening": "t",
        "validated_by_synthesis": validated,
    }


# ---------------------------------------------------------------- parser

def test_synthesis_parser_extracts_nested_json():
    text = "Here is the response:\n```json\n{\n  \"consolidated_findings\": [],\n  \"merged_failed_attacks\": []\n}\n```\nHope it helps!"
    parsed = synthesis._parse_synthesis_json(text, SPEC_STAGE)
    assert parsed == {"consolidated_findings": [], "merged_failed_attacks": []}

    text_bracket = 'The response payload: {"consolidated_findings": [], "merged_failed_attacks": []}'
    parsed_bracket = synthesis._parse_synthesis_json(text_bracket, SPEC_STAGE)
    assert parsed_bracket == {"consolidated_findings": [], "merged_failed_attacks": []}


def test_synthesis_parser_plan_stage_requires_plan_keys():
    plan_text = '```json\n{"consolidated_findings": [], "merged_checks_that_passed": [], "first_domino": null}\n```'
    parsed = synthesis._parse_synthesis_json(plan_text, PLAN_STAGE)
    assert parsed["merged_checks_that_passed"] == []

    # Spec-shaped synthesis output must be rejected under the plan stage
    spec_text = '```json\n{"consolidated_findings": [], "merged_failed_attacks": []}\n```'
    with pytest.raises(ValueError):
        synthesis._parse_synthesis_json(spec_text, PLAN_STAGE)


def test_synthesis_parser_rejects_incomplete_consolidated_finding():
    text = '```json\n{"consolidated_findings": [{"id": "x"}], "merged_failed_attacks": []}\n```'
    with pytest.raises(ValueError):
        synthesis._parse_synthesis_json(text, SPEC_STAGE)


# ---------------------------------------------------------------- prompt building

def test_build_synthesis_user_prompt_enumerates_all_agents():
    prompt = synthesis.build_synthesis_user_prompt("DOC", [[{"id": "a"}], [], [{"id": "b"}]])
    assert "TARGET DOCUMENT:\nDOC" in prompt
    assert "AGENT 1 RAW FINDINGS:" in prompt
    assert "AGENT 2 RAW FINDINGS:" in prompt
    assert "AGENT 3 RAW FINDINGS:" in prompt


# ---------------------------------------------------------------- fuzzy matching

def test_texts_match_short_clauses():
    assert synthesis.texts_match("api", "api") is True
    assert synthesis.texts_match("api", "API") is True
    assert synthesis.texts_match("api", "Ensure API keys are rotated") is False
    assert synthesis.texts_match("Ensure API keys are rotated", "api") is False
    assert synthesis.texts_match("Ensure API keys are rotated", "API keys are rotated") is True
    # Back-compat aliases still exposed
    assert synthesis.clauses_match is synthesis.texts_match
    assert synthesis.normalize_clause is synthesis.normalize_text


# ---------------------------------------------------------------- quorum

def test_vote_calculation_and_quorum():
    """Vote arithmetic across 3 agents + synthesis vote."""
    a1 = [spec_finding("issue-one", "quote1"), spec_finding("issue-two", "quote2", "medium")]
    a2 = [spec_finding("issue-two", "quote2", "medium")]
    a3 = []  # third skeptic found nothing (or failed -> empty list)

    synthesis_output = {
        "consolidated_findings": [
            # issue-one: agent-1 + synthesis = 2 votes -> CONFIRMED
            consolidated("issue-one", "quote1", True),
            # issue-two: agent-1 + agent-2 + synthesis = 3 votes -> CONFIRMED
            consolidated("issue-two", "quote2", True, "medium"),
            # issue-three: synthesis only = 1 vote -> UNCONFIRMED
            consolidated("issue-three", "quote3", True, "low"),
            # issue-four: agent-1 only, rejected by synthesis = 1 vote -> UNCONFIRMED
            dict(consolidated("issue-four", "quote4", False, "low")),
        ],
        "merged_failed_attacks": [],
    }
    # issue-four must fuzzy/ID match agent-1: give agent-1 that finding
    a1.append(spec_finding("issue-four", "quote4", "low"))

    confirmed, unconfirmed = synthesis.compute_votes_and_quorum([a1, a2, a3], synthesis_output, SPEC_STAGE)

    assert {f["id"] for f in confirmed} == {"issue-one", "issue-two"}
    issue_one = next(f for f in confirmed if f["id"] == "issue-one")
    assert issue_one["votes"] == 2
    assert issue_one["sources"] == ["agent-1"]
    issue_two = next(f for f in confirmed if f["id"] == "issue-two")
    assert issue_two["votes"] == 3
    assert set(issue_two["sources"]) == {"agent-1", "agent-2"}

    assert {f["id"] for f in unconfirmed} == {"issue-three", "issue-four"}


def test_two_agents_alone_reach_quorum():
    """Agents 2 and 3 agreeing confirms a finding even when synthesis rejects it."""
    shared_clause = "Every request must be rate limited per tenant"
    a2 = [spec_finding("rate-limit-gap", shared_clause)]
    a3 = [spec_finding("rate-limit-gap", shared_clause)]

    synthesis_output = {
        "consolidated_findings": [consolidated("rate-limit-gap", shared_clause, False)],
        "merged_failed_attacks": [],
    }

    confirmed, unconfirmed = synthesis.compute_votes_and_quorum([[], a2, a3], synthesis_output, SPEC_STAGE)
    assert len(confirmed) == 1
    assert confirmed[0]["votes"] == 2
    assert set(confirmed[0]["sources"]) == {"agent-2", "agent-3"}
    assert unconfirmed == []


def test_compute_votes_and_quorum_fallback_matching():
    """Hallucinated synthesis ID falls back to fuzzy clause matching; 0-vote findings stay listed."""
    a1 = [spec_finding("agent-one-csrf", "Must authenticate all API requests via a CSRF token")]
    a2 = [spec_finding("agent-two-csrf-vuln", "Authenticate all API requests via a CSRF token.")]

    synthesis_output = {
        "consolidated_findings": [
            consolidated("new-csrf-hallucinated-id", "must authenticate all API requests via a CSRF token", True),
            consolidated("unmatched-finding-id", "unmatched clause that does not match anything", False, "medium"),
        ],
        "merged_failed_attacks": [],
    }

    confirmed, unconfirmed = synthesis.compute_votes_and_quorum([a1, a2, []], synthesis_output, SPEC_STAGE)

    assert len(confirmed) == 1
    matched = confirmed[0]
    assert matched["id"] == "agent-one-csrf"  # adopted from the first fuzzy-matched agent
    assert matched["votes"] == 3
    assert set(matched["sources"]) == {"agent-1", "agent-2"}

    assert len(unconfirmed) == 1
    assert unconfirmed[0]["id"] == "unmatched-finding-id"
    assert unconfirmed[0]["votes"] == 0


def test_stale_id_fallback_matching():
    """Agent-1 fallback updates the ID so the agent-2 stable-ID check then hits directly."""
    a1 = [spec_finding("agent-one-finding", "Must authenticate all API requests via a CSRF token")]
    a2 = [spec_finding("agent-two-finding", "Authenticate all API requests via a CSRF token.")]

    synthesis_output = {
        "consolidated_findings": [
            consolidated("new-csrf-hallucinated-id", "must authenticate all API requests via a CSRF token", True),
        ],
        "merged_failed_attacks": [],
    }

    confirmed, _ = synthesis.compute_votes_and_quorum([a1, a2, []], synthesis_output, SPEC_STAGE)
    assert len(confirmed) == 1
    assert confirmed[0]["id"] == "agent-one-finding"
    assert set(confirmed[0]["sources"]) == {"agent-1", "agent-2"}
    assert confirmed[0]["votes"] == 3


def test_plan_stage_matches_on_evidence():
    """The plan stage fuzzy-matches on 'evidence', not 'clause'."""
    plan_finding = {
        "id": "agent-side-id", "step": "2", "category": "ordering",
        "failure": "f", "evidence": "Step 2 consumes the schema created in step 5",
        "confidence": "high", "severity": "high", "fix": "reorder",
    }
    synthesis_output = {
        "consolidated_findings": [{
            "id": "renamed-by-synthesis", "step": "2", "category": "ordering",
            "failure": "f", "evidence": "step 2 consumes the schema created in step 5.",
            "severity": "high", "fix": "reorder", "validated_by_synthesis": False,
        }],
        "merged_checks_that_passed": [],
    }

    confirmed, unconfirmed = synthesis.compute_votes_and_quorum([[plan_finding], [], []], synthesis_output, PLAN_STAGE)
    # 1 agent vote only -> unconfirmed, but the ID was adopted via evidence matching
    assert confirmed == []
    assert unconfirmed[0]["id"] == "agent-side-id"
    assert unconfirmed[0]["sources"] == ["agent-1"]


# ---------------------------------------------------------------- first domino

def test_compute_first_domino_majority_of_agents():
    outputs = [
        {"findings": [], "first_domino": "early-break", "checks_that_passed": []},
        {"findings": [], "first_domino": "early-break", "checks_that_passed": []},
        {"findings": [], "first_domino": "late-break", "checks_that_passed": []},
    ]
    confirmed = [{"id": "early-break"}, {"id": "late-break"}]
    assert synthesis.compute_first_domino(outputs, {}, confirmed) == "early-break"


def test_compute_first_domino_ignores_unconfirmed_nominations_and_falls_back():
    outputs = [
        {"findings": [], "first_domino": "not-confirmed", "checks_that_passed": []},
        None,  # failed agent
        {"findings": [], "first_domino": None, "checks_that_passed": []},
    ]
    synthesis_output = {"first_domino": "confirmed-id"}
    confirmed = [{"id": "confirmed-id"}]
    assert synthesis.compute_first_domino(outputs, synthesis_output, confirmed) == "confirmed-id"


def test_compute_first_domino_none_when_nothing_qualifies():
    outputs = [{"findings": [], "first_domino": "x", "checks_that_passed": []}]
    assert synthesis.compute_first_domino(outputs, {"first_domino": "y"}, []) is None
    assert synthesis.compute_first_domino(outputs, {"first_domino": "y"}, [{"id": "z"}]) is None


# ---------------------------------------------------------------- transport

@pytest.mark.asyncio
async def test_call_remote_synthesis_gemini_uses_rest_generate_content():
    """Gemini synthesis goes through the same REST transport (no SDK)."""
    import httpx
    from unittest.mock import MagicMock
    captured = {}

    async def spy_post(self, url, json=None, headers=None, **kwargs):
        captured["url"] = url
        captured["payload"] = json
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": "reply"}]}}]}
        resp.text = "ok"
        return resp

    with patch.object(httpx.AsyncClient, "post", spy_post):
        reply = await synthesis.call_remote_synthesis("p1", "global", "gemini-3.5-flash", "sys", "user", 0.15, 100)

    assert reply == "reply"
    assert "/publishers/google/models/gemini-3.5-flash:generateContent" in captured["url"]
    assert captured["payload"]["systemInstruction"] == {"parts": [{"text": "sys"}]}


@pytest.mark.asyncio
async def test_call_remote_synthesis_claude_uses_global_raw_predict():
    """Claude synthesis is first-class: global endpoint, no us-east5 remap."""
    import httpx
    from unittest.mock import MagicMock
    captured = {}

    async def spy_post(self, url, json=None, headers=None, **kwargs):
        captured["url"] = url
        captured["payload"] = json
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"content": [{"type": "text", "text": "reply"}]}
        resp.text = "ok"
        return resp

    with patch.object(httpx.AsyncClient, "post", spy_post):
        reply = await synthesis.call_remote_synthesis("p1", "global", "claude-fable-5", "sys", "user", 0.15, 100)

    assert reply == "reply"
    assert captured["url"].startswith("https://aiplatform.googleapis.com/")
    assert "/locations/global/publishers/anthropic/models/claude-fable-5:rawPredict" in captured["url"]
    assert captured["payload"]["anthropic_version"] == "vertex-2023-10-16"


# ---------------------------------------------------------------- fallback loop

@pytest.mark.asyncio
async def test_synthesis_fallback_loop_success_on_retry():
    config = {
        "synthesis_model": "gemini-3-1-flash-lite",
        "synthesis_temperature": 0.15,
        "gcp_project_id": "test-p",
        "gcp_location": "us",
    }

    call_mock = AsyncMock(side_effect=[
        "Unparseable response text",
        "Still unparseable response text",
        "```json\n{\n  \"consolidated_findings\": [],\n  \"merged_failed_attacks\": []\n}\n```",
    ])

    with patch("geap_validator_core.synthesis.call_remote_synthesis", call_mock):
        res = await synthesis.run_synthesis_with_fallbacks("doc", [[], [], []], config, SPEC_STAGE)
        assert res == {"consolidated_findings": [], "merged_failed_attacks": []}

    assert call_mock.call_count == 3
    # Temperature drops to 0 and the reminder is appended after the first failure
    assert call_mock.call_args_list[0][0][5] == 0.15
    assert call_mock.call_args_list[1][0][5] == 0.0
    assert "REMINDER" in call_mock.call_args_list[1][0][3]


@pytest.mark.asyncio
async def test_synthesis_max_retries_raises_exception():
    config = {
        "synthesis_model": "gemini-3.1-flash-lite",
        "gcp_project_id": "test-p",
        "gcp_location": "global",
    }

    call_mock = AsyncMock(return_value="Unparseable text")

    with patch("geap_validator_core.synthesis.call_remote_synthesis", call_mock):
        with pytest.raises(synthesis.SynthesisFailureException):
            await synthesis.run_synthesis_with_fallbacks("doc", [[], [], []], config, SPEC_STAGE)

    assert call_mock.call_count == 3


@pytest.mark.asyncio
async def test_claude_synthesis_never_substituted():
    """A failing claude synthesizer retries and raises — it is NOT silently swapped for a Gemini model."""
    config = {
        "synthesis_model": "claude-fable-5",
        "gcp_project_id": "test-p",
        "gcp_location": "global",
    }

    call_mock = AsyncMock(return_value="Unparseable text")

    with patch("geap_validator_core.synthesis.call_remote_synthesis", call_mock):
        with pytest.raises(synthesis.SynthesisFailureException) as exc:
            await synthesis.run_synthesis_with_fallbacks("doc", [[], [], []], config, SPEC_STAGE)

    assert "claude-fable-5" in str(exc.value)
    assert call_mock.call_count == 3
    # Every attempt used the configured model — no fallback substitution
    for call in call_mock.call_args_list:
        assert call[0][2] == "claude-fable-5"
