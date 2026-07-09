import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from geap_validator_core import client
from geap_validator_core.stages import SPEC_STAGE, PLAN_STAGE


def make_http_response(body: dict, status_code: int = 200):
    """Mock httpx response with a real string .text (generate_text greps it on 400s)."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = body
    mock_response.text = json.dumps(body)
    return mock_response

THREE_MODELS = ["gemini-3.5-flash", "claude-haiku-4-5", "gemini-3.1-flash-lite"]

SPEC_FINDING = {
    "id": "finding-1", "clause": "c1", "severity": "high",
    "interpretation": "i1", "harm": "h1", "tightening": "t1",
}
PLAN_FINDING = {
    "id": "step-gap", "step": "3", "category": "ordering", "failure": "f",
    "evidence": "e", "confidence": "high", "severity": "high", "fix": "x",
}

VALID_SPEC_REPLY = '{"findings": [], "failed_attacks": []}'


@patch("google.auth.default")
def test_initialize_clients_resolves_adc(mock_auth):
    mock_auth.return_value = (MagicMock(), "auth-project")
    creds, project = client.initialize_clients(None, "global")
    assert creds is not None
    assert project == "auth-project"


# ---------------------------------------------------------------- endpoints

def test_build_endpoint_gemini_global():
    url = client.build_endpoint("p1", "global", "gemini-3.5-flash")
    assert url == ("https://aiplatform.googleapis.com/v1/projects/p1/locations/global"
                   "/publishers/google/models/gemini-3.5-flash:generateContent")


def test_build_endpoint_claude_global():
    url = client.build_endpoint("p1", "global", "claude-haiku-4-5")
    assert url == ("https://aiplatform.googleapis.com/v1/projects/p1/locations/global"
                   "/publishers/anthropic/models/claude-haiku-4-5:rawPredict")


def test_build_endpoint_unknown_prefix_raises():
    with pytest.raises(ValueError) as exc:
        client.build_endpoint("p1", "global", "gpt-4o")
    assert "gpt-4o" in str(exc.value)


def test_build_endpoint_clamps_regional_locations_to_global():
    """Current-generation models are global-only; legacy regions are clamped away."""
    for loc in ["us-central1", "us", "us-east5", None, "europe-west1"]:
        url = client.build_endpoint("p1", loc, "gemini-3.5-flash")
        assert url.startswith("https://aiplatform.googleapis.com/v1/projects/p1/locations/global/")


# ---------------------------------------------------------------- generate_text

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_generate_text_gemini_payload_and_multipart_reply(mock_post):
    mock_post.return_value = make_http_response({
        "candidates": [{"content": {"role": "model", "parts": [
            {"text": "A", "thoughtSignature": "sig"},
            {"text": "B"},
        ]}}]
    })
    creds = MagicMock()
    creds.token = "tok"

    text = await client.generate_text(creds, "p1", "global", "gemini-3.5-flash",
                                      "sys", "user", 0.15, 100, 30)
    assert text == "AB"

    url = mock_post.call_args[0][0]
    assert "/publishers/google/models/gemini-3.5-flash:generateContent" in url
    payload = mock_post.call_args[1]["json"]
    assert payload["systemInstruction"] == {"parts": [{"text": "sys"}]}
    assert payload["contents"] == [{"role": "user", "parts": [{"text": "user"}]}]
    assert payload["generationConfig"] == {"temperature": 0.15, "maxOutputTokens": 100}
    assert "temperature" not in payload  # only inside generationConfig


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_generate_text_claude_payload(mock_post):
    mock_post.return_value = make_http_response({"content": [{"type": "text", "text": "OK"}]})
    creds = MagicMock()
    creds.token = "tok"

    text = await client.generate_text(creds, "p1", "global", "claude-haiku-4-5",
                                      "sys", "user", 0.15, 100, 30)
    assert text == "OK"

    url = mock_post.call_args[0][0]
    assert "/publishers/anthropic/models/claude-haiku-4-5:rawPredict" in url
    kwargs = mock_post.call_args[1]
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    payload = kwargs["json"]
    assert payload["anthropic_version"] == "vertex-2023-10-16"
    assert payload["system"] == "sys"
    assert payload["max_tokens"] == 100
    assert payload["temperature"] == 0.15


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_generate_text_claude_drops_rejected_temperature(mock_post):
    """claude-fable-5-style 400 on temperature is resent once without the parameter."""
    rejection = make_http_response(
        {"type": "error", "error": {"type": "invalid_request_error",
                                    "message": "`temperature` is deprecated for this model."}},
        status_code=400,
    )
    success = make_http_response({"content": [{"type": "text", "text": "OK"}]})
    mock_post.side_effect = [rejection, success]
    creds = MagicMock()
    creds.token = "tok"

    text = await client.generate_text(creds, "p1", "global", "claude-fable-5",
                                      "sys", "user", 0.15, 100, 30)
    assert text == "OK"
    assert mock_post.call_count == 2
    first_payload = mock_post.call_args_list[0][1]["json"]
    second_payload = mock_post.call_args_list[1][1]["json"]
    assert first_payload["temperature"] == 0.15
    assert "temperature" not in second_payload
    rejection.raise_for_status.assert_not_called()


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_generate_text_unrelated_400_still_raises(mock_post):
    """A 400 that does not mention temperature surfaces via raise_for_status."""
    import httpx
    bad = make_http_response({"error": {"message": "model not found"}}, status_code=400)
    bad.raise_for_status.side_effect = httpx.HTTPStatusError("400", request=MagicMock(), response=MagicMock())
    mock_post.return_value = bad
    creds = MagicMock()
    creds.token = "tok"

    with pytest.raises(httpx.HTTPStatusError):
        await client.generate_text(creds, "p1", "global", "claude-haiku-4-5",
                                   "sys", "user", 0.15, 100, 30)
    assert mock_post.call_count == 1


# ---------------------------------------------------------------- schema parsing

def test_parse_json_reply_plan_stage_accepts_plan_shape():
    engine = client.CloudInvocationEngine("p", "global", MagicMock(), {})
    raw = ('```json\n{"findings": [' +
           '{"id": "step-gap", "step": "3", "category": "ordering", "failure": "f", '
           '"evidence": "e", "confidence": "high", "severity": "high", "fix": "x"}],'
           '"first_domino": "step-gap", "checks_that_passed": ["ok"]}\n```')
    data = engine._parse_json_reply(raw, PLAN_STAGE)
    assert data["findings"][0]["id"] == "step-gap"
    assert data["checks_that_passed"] == ["ok"]


def test_parse_json_reply_plan_stage_rejects_spec_shape():
    """A spec-shaped reply lacks checks_that_passed and the plan finding keys."""
    engine = client.CloudInvocationEngine("p", "global", MagicMock(), {})
    raw = '```json\n{"findings": [], "failed_attacks": []}\n```'
    with pytest.raises(client.AgentJSONParsingException) as exc:
        engine._parse_json_reply(raw, PLAN_STAGE)
    assert "checks_that_passed" in str(exc.value)


def test_parse_json_reply_rejects_missing_finding_keys():
    engine = client.CloudInvocationEngine("p", "global", MagicMock(), {})
    raw = '```json\n{"findings": [{"id": "a-b"}], "failed_attacks": []}\n```'
    with pytest.raises(client.AgentJSONParsingException):
        engine._parse_json_reply(raw, SPEC_STAGE)


def test_parse_json_reply_rejects_non_kebab_id():
    engine = client.CloudInvocationEngine("p", "global", MagicMock(), {})
    bad = dict(SPEC_FINDING, id="Bad_ID")
    raw = '```json\n' + json.dumps({"findings": [bad], "failed_attacks": []}) + '\n```'
    with pytest.raises(client.AgentJSONParsingException) as exc:
        engine._parse_json_reply(raw, SPEC_STAGE)
    assert "kebab-case" in str(exc.value)


# ---------------------------------------------------------------- invoke_agent

@pytest.mark.asyncio
async def test_invoke_agent_unknown_prefix_raises():
    engine = client.CloudInvocationEngine("p", "global", MagicMock(), {})
    with pytest.raises(ValueError) as exc:
        await engine.invoke_agent("gpt-4o", "sys", "doc", SPEC_STAGE)
    assert "gpt-4o" in str(exc.value)


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_invoke_agent_json_repair_retry(mock_sleep):
    """On AgentJSONParsingException the retry drops temperature to 0 and appends the JSON reminder —
    same behavior regardless of provider, since both share the retry loop."""
    config = {
        "synthesis_temperature": 0.15,
        "synthesis_max_output_tokens": 8192,
        "api_timeout_seconds": 30,
        "api_max_retries": 3,
    }
    engine = client.CloudInvocationEngine("p", "global", MagicMock(), config)

    gen_mock = AsyncMock(side_effect=["invalid json text", VALID_SPEC_REPLY])
    with patch("geap_validator_core.client.generate_text", gen_mock):
        res = await engine.invoke_agent("claude-haiku-4-5", "system-prompt", "doc", SPEC_STAGE)

    assert res == {"findings": [], "failed_attacks": []}
    assert gen_mock.call_count == 2
    first_args = gen_mock.call_args_list[0][0]
    second_args = gen_mock.call_args_list[1][0]
    # positional layout: creds, project, location, model, system, user, temperature, max_tokens, timeout
    assert first_args[4] == "system-prompt"
    assert first_args[6] == 0.15
    assert "REMINDER" in second_args[4]
    assert second_args[6] == 0.0


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_invoke_agent_retries_exhausted(mock_sleep):
    config = {"api_timeout_seconds": 1, "api_max_retries": 3}
    engine = client.CloudInvocationEngine("p", "global", MagicMock(), config)

    gen_mock = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("geap_validator_core.client.generate_text", gen_mock):
        with pytest.raises(RuntimeError) as exc:
            await engine.invoke_agent("gemini-3.5-flash", "sys", "doc", SPEC_STAGE)

    assert "failed after 3 attempts" in str(exc.value)
    assert gen_mock.call_count == 3
    assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_invoke_agent_end_to_end_over_mock_rest():
    """Both providers succeed through the real generate_text against the conftest httpx mock."""
    engine = client.CloudInvocationEngine("p", "global", MagicMock(), {})
    for model in ["gemini-3.5-flash", "claude-haiku-4-5"]:
        res = await engine.invoke_agent(model, "spec skeptic instructions", "doc", SPEC_STAGE)
        assert res == {"findings": [], "failed_attacks": []}


# ---------------------------------------------------------------- 3-agent panel

@pytest.mark.asyncio
async def test_parallel_validation_all_succeed():
    engine = client.CloudInvocationEngine("test-p", "global", MagicMock(), {})
    results = [
        {"findings": [dict(SPEC_FINDING, id=f"finding-{i}")], "failed_attacks": []}
        for i in range(3)
    ]
    with patch.object(engine, "invoke_agent", AsyncMock(side_effect=results)) as mock_invoke:
        outputs = await engine.run_parallel_validation(THREE_MODELS, SPEC_STAGE, "doc")

    assert outputs == results
    # Each slot gets its own lens prompt
    for i in range(3):
        args = mock_invoke.call_args_list[i][0]
        assert args[0] == THREE_MODELS[i]
        assert args[1] == SPEC_STAGE.agent_prompts[i]


@pytest.mark.asyncio
async def test_parallel_validation_one_failure_proceeds():
    """2 of 3 succeeding keeps the panel alive; the failed slot becomes None."""
    engine = client.CloudInvocationEngine("test-p", "global", MagicMock(), {})
    r1 = {"findings": [SPEC_FINDING], "failed_attacks": []}
    r3 = {"findings": [], "failed_attacks": ["probe"]}
    with patch.object(engine, "invoke_agent", AsyncMock(side_effect=[r1, Exception("Agent 2 failed"), r3])):
        outputs = await engine.run_parallel_validation(THREE_MODELS, SPEC_STAGE, "doc")

    assert outputs == [r1, None, r3]


@pytest.mark.asyncio
async def test_parallel_validation_two_failures_raise():
    engine = client.CloudInvocationEngine("test-p", "global", MagicMock(), {})
    r3 = {"findings": [], "failed_attacks": []}
    with patch.object(engine, "invoke_agent", AsyncMock(side_effect=[Exception("a1"), Exception("a2"), r3])):
        with pytest.raises(RuntimeError) as exc:
            await engine.run_parallel_validation(THREE_MODELS, SPEC_STAGE, "doc")
    assert "Quorum unreachable" in str(exc.value)


@pytest.mark.asyncio
async def test_parallel_validation_total_failure_raises():
    engine = client.CloudInvocationEngine("test-p", "global", MagicMock(), {})
    with patch.object(engine, "invoke_agent", AsyncMock(side_effect=[Exception("a1"), Exception("a2"), Exception("a3")])):
        with pytest.raises(RuntimeError) as exc:
            await engine.run_parallel_validation(THREE_MODELS, SPEC_STAGE, "doc")
    assert "Quorum unreachable" in str(exc.value)
