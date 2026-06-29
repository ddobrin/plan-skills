import os
import sys
import json
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import httpx

import config_loader
import client
import synthesis
import validator

class AwaitableMock(AsyncMock):
    def __await__(self):
        self.await_count += 1
        self.await_args = self.call_args
        self.await_args_list.append(self.call_args)
        
        async def _dummy():
            if self.side_effect:
                if callable(self.side_effect):
                    import inspect
                    res = self.side_effect()
                    if res is self:
                        return res
                    if inspect.isawaitable(res):
                        return await res
                    return res
                return self.side_effect
            return self.return_value
        return _dummy().__await__()

# Helper to write a temp file
def write_temp_file(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)

def test_config_json_format():
    """Verify config.json exists and has required keys."""
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config.json")
    assert os.path.exists(config_path)
    with open(config_path, "r") as f:
        data = json.load(f)
    assert "gcp_project_id" in data
    assert "agent_1_model" in data
    assert "agent_2_model" in data
    assert "synthesis_model" in data

def test_config_load_from_file(tmp_path):
    """Test loading configuration from a file."""
    cfg_data = {
        "gcp_project_id": "file-project",
        "agent_1_model": "gemini-3.5-flash",
        "agent_2_model": "claude-haiku-4-5",
        "synthesis_model": "gemini-3-1-flash-lite"
    }
    cfg_file = write_temp_file(tmp_path, "test_config.json", json.dumps(cfg_data))
    
    with patch.dict(os.environ, {}, clear=True):
        resolved = config_loader.load_config(cfg_file)
        assert resolved["gcp_project_id"] == "file-project"
        assert resolved["agent_1_model"] == "gemini-3.5-flash"
        assert resolved["agent_2_model"] == "claude-haiku-4-5"
        assert resolved["synthesis_model"] == "gemini-3-1-flash-lite"
        assert resolved["gcp_location"] == "us" # Default

def test_config_env_variable_overrides(tmp_path):
    """Test environment variable overrides."""
    cfg_data = {
        "gcp_project_id": "file-project",
        "agent_1_model": "gemini-3.5-flash",
        "agent_2_model": "claude-haiku-4-5",
        "synthesis_model": "gemini-3-1-flash-lite"
    }
    cfg_file = write_temp_file(tmp_path, "test_config.json", json.dumps(cfg_data))
    
    env_vars = {
        "GOOGLE_CLOUD_PROJECT": "env-project",
        "CLOUD_VALIDATOR_AGENT_1_MODEL": "gemini-3.5-flash",
        "CLOUD_VALIDATOR_AGENT_2_MODEL": "claude-haiku-4-5",
        "CLOUD_VALIDATOR_SYNTHESIS_MODEL": "gemini-3-1-flash-lite",
        "CLOUD_VALIDATOR_LOCATION": "global"
    }
    with patch.dict(os.environ, env_vars, clear=True):
        resolved = config_loader.load_config(cfg_file)
        assert resolved["gcp_project_id"] == "env-project"
        assert resolved["agent_1_model"] == "gemini-3.5-flash"
        assert resolved["agent_2_model"] == "claude-haiku-4-5"
        assert resolved["synthesis_model"] == "gemini-3-1-flash-lite"
        assert resolved["gcp_location"] == "global"

def test_config_missing_required_keys_raises(tmp_path):
    """Test that ValueErrors are raised when required keys are missing."""
    cfg_data = {
        "agent_1_model": "gemini-3.5-flash",
        "agent_2_model": "claude-haiku-4-5",
        "synthesis_model": "gemini-3-1-flash-lite"
    }
    cfg_file = write_temp_file(tmp_path, "test_config.json", json.dumps(cfg_data))
    
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError) as exc:
            config_loader.load_config(cfg_file)
        assert "gcp_project_id" in str(exc.value)

def test_config_invalid_model_raises_value_error(tmp_path):
    """Test that ValueErrors are raised when invalid models are used."""
    cfg_data = {
        "gcp_project_id": "file-project",
        "agent_1_model": "invalid-model-name",
        "agent_2_model": "claude-haiku-4-5",
        "synthesis_model": "gemini-3-1-flash-lite"
    }
    cfg_file = write_temp_file(tmp_path, "test_config.json", json.dumps(cfg_data))
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError) as exc:
            config_loader.load_config(cfg_file)
        assert "invalid-model-name" in str(exc.value)

def test_config_invalid_location_defaults_to_us(tmp_path):
    """Test that invalid locations default to us."""
    cfg_data = {
        "gcp_project_id": "file-project",
        "agent_1_model": "gemini-3.5-flash",
        "agent_2_model": "claude-haiku-4-5",
        "synthesis_model": "gemini-3-1-flash-lite",
        "gcp_location": "invalid-location"
    }
    cfg_file = write_temp_file(tmp_path, "test_config.json", json.dumps(cfg_data))
    with patch.dict(os.environ, {}, clear=True):
        resolved = config_loader.load_config(cfg_file)
        assert resolved["gcp_location"] == "us"

@patch("google.auth.default")
@patch("vertexai.init")
def test_initialize_clients_resolves_adc(mock_init, mock_auth):
    """Test ADC credentials resolution."""
    mock_auth.return_value = (MagicMock(), "auth-project")
    creds, project = client.initialize_clients(None, "us")
    assert project == "auth-project"
    mock_init.assert_called_once()

@pytest.mark.asyncio
@patch("vertexai.generative_models.GenerativeModel")
async def test_invoke_gemini_agent(mock_model_class):
    """Verify Gemini calls instantiate GenerativeModel and call generate_content_async."""
    mock_model_instance = MagicMock()
    mock_model_class.return_value = mock_model_instance
    
    mock_response = AwaitableMock()
    mock_response.text = '{"findings": [], "failed_attacks": []}'
    
    async def mock_coro(*args, **kwargs):
        return mock_response
    mock_response.side_effect = mock_coro
    
    mock_model_instance.generate_content_async.return_value = mock_response
    
    engine = client.CloudInvocationEngine("mock-project", "us", MagicMock(), {})
    res = await engine.invoke_gemini_agent("gemini-3.5-flash", "system-prompt", "doc-content")
    
    mock_model_class.assert_called_once_with("gemini-3.5-flash", system_instruction="system-prompt")
    mock_model_instance.generate_content_async.assert_called_once()
    mock_response.assert_awaited_once()
    assert res == {"findings": [], "failed_attacks": []}

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
@patch("google.auth.default")
@patch("asyncio.to_thread")
async def test_invoke_claude_agent(mock_to_thread, mock_auth, mock_post):
    """Verify Claude REST API queries send a valid Anthropic messages payload."""
    mock_creds = MagicMock()
    mock_creds.token = "mock-access-token"
    mock_auth.return_value = (mock_creds, "mock-project")
    
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "content": [
            {
                "type": "text",
                "text": '{"findings": [], "failed_attacks": []}'
            }
        ]
    }
    mock_post.return_value = mock_response
    
    engine = client.CloudInvocationEngine("mock-project", "us", mock_creds, {})
    res = await engine.invoke_claude_agent("claude-haiku-4-5", "system-prompt", "doc-content")
    
    assert res == {"findings": [], "failed_attacks": []}
    mock_post.assert_called_once()
    # Check payload headers
    _, kwargs = mock_post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer mock-access-token"

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
@patch("google.auth.default")
@patch("asyncio.to_thread")
async def test_claude_routing_allowed_global(mock_to_thread, mock_auth, mock_post):
    """Verify that if gcp_location is global, it is preserved."""
    mock_creds = MagicMock()
    mock_creds.token = "mock-access-token"
    mock_auth.return_value = (mock_creds, "mock-project")
    
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "content": [
            {
                "type": "text",
                "text": '{"findings": [], "failed_attacks": []}'
            }
        ]
    }
    mock_post.return_value = mock_response
    
    engine = client.CloudInvocationEngine("mock-project", "global", mock_creds, {})
    res = await engine.invoke_claude_agent("claude-haiku-4-5", "system-prompt", "doc-content")
    
    assert res == {"findings": [], "failed_attacks": []}
    mock_post.assert_called_once()
    url = mock_post.call_args[0][0]
    assert "global-aiplatform.googleapis.com" in url

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
@patch("google.auth.default")
@patch("asyncio.to_thread")
async def test_claude_routing_invalid_fallback(mock_to_thread, mock_auth, mock_post):
    """Verify that if gcp_location is invalid, it fallbacks to us."""
    mock_creds = MagicMock()
    mock_creds.token = "mock-access-token"
    mock_auth.return_value = (mock_creds, "mock-project")
    
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "content": [
            {
                "type": "text",
                "text": '{"findings": [], "failed_attacks": []}'
            }
        ]
    }
    mock_post.return_value = mock_response
    
    engine = client.CloudInvocationEngine("mock-project", "invalid-region", mock_creds, {})
    res = await engine.invoke_claude_agent("claude-haiku-4-5", "system-prompt", "doc-content")
    
    assert res == {"findings": [], "failed_attacks": []}
    mock_post.assert_called_once()
    url = mock_post.call_args[0][0]
    assert "us-aiplatform.googleapis.com" in url

@pytest.mark.asyncio
async def test_parallel_validation_both_succeed():
    """Verify parallel execution collects and returns findings from both agents."""
    engine = client.CloudInvocationEngine("test-p", "us", MagicMock(), {})
    
    a1_res = {"findings": [{"id": "finding-1", "clause": "c1", "severity": "high", "interpretation": "i1", "harm": "h1", "tightening": "t1"}], "failed_attacks": []}
    a2_res = {"findings": [{"id": "finding-2", "clause": "c2", "severity": "medium", "interpretation": "i2", "harm": "h2", "tightening": "t2"}], "failed_attacks": []}
    
    with patch.object(engine, "invoke_gemini_agent", AsyncMock(return_value=a1_res)), \
         patch.object(engine, "invoke_claude_agent", AsyncMock(return_value=a2_res)):
         
        out1, out2 = await engine.run_parallel_validation("gemini-3.5-flash", "claude-haiku-4-5", "doc")
        assert out1 == a1_res
        assert out2 == a2_res

@pytest.mark.asyncio
async def test_parallel_validation_partial_failure():
    """Verify that if one agent fails, the dispatcher still returns the other's findings."""
    engine = client.CloudInvocationEngine("test-p", "us", MagicMock(), {})
    
    a1_res = {"findings": [{"id": "finding-1", "clause": "c1", "severity": "high", "interpretation": "i1", "harm": "h1", "tightening": "t1"}], "failed_attacks": []}
    
    with patch.object(engine, "invoke_gemini_agent", AsyncMock(return_value=a1_res)), \
         patch.object(engine, "invoke_claude_agent", AsyncMock(side_effect=Exception("Agent 2 failed"))):
         
        out1, out2 = await engine.run_parallel_validation("gemini-3.5-flash", "claude-haiku-4-5", "doc")
        assert out1 == a1_res
        assert out2 is None

@pytest.mark.asyncio
async def test_parallel_validation_total_failure():
    """Verify that if both agents fail, a RuntimeError is raised."""
    engine = client.CloudInvocationEngine("test-p", "us", MagicMock(), {})
    
    with patch.object(engine, "invoke_gemini_agent", AsyncMock(side_effect=Exception("Agent 1 failed"))), \
         patch.object(engine, "invoke_claude_agent", AsyncMock(side_effect=Exception("Agent 2 failed"))):
         
        with pytest.raises(RuntimeError) as exc:
            await engine.run_parallel_validation("gemini-3.5-flash", "claude-haiku-4-5", "doc")
        assert "All agent validation invocations failed" in str(exc.value)

@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("vertexai.generative_models.GenerativeModel")
async def test_timeout_and_retries(mock_model_class, mock_sleep):
    """Test timeout boundary handling and backoff retry loop for Gemini."""
    mock_model_instance = MagicMock()
    mock_model_class.return_value = mock_model_instance
    
    mock_model_instance.generate_content_async.side_effect = asyncio.TimeoutError("Timeout")
    
    config = {
        "api_timeout_seconds": 1,
        "api_max_retries": 3
    }
    
    engine = client.CloudInvocationEngine("test-p", "us", MagicMock(), config)
    
    with pytest.raises(RuntimeError) as exc:
        await engine.invoke_gemini_agent("gemini-3.5-flash", "sys-prompt", "doc-content")
    
    assert "failed after 3 attempts" in str(exc.value)
    assert mock_model_instance.generate_content_async.call_count == 3
    assert mock_sleep.call_count == 2

def test_vote_calculation_and_quorum():
    """Verify that arithmetic vote counts and stable ID mapping are programmatically computed."""
    a1_findings = [
        {"id": "issue-one", "clause": "quote1", "severity": "high", "interpretation": "int1", "harm": "harm1", "tightening": "t1"},
        {"id": "issue-two", "clause": "quote2", "severity": "medium", "interpretation": "int2", "harm": "harm2", "tightening": "t2"}
    ]
    a2_findings = [
        {"id": "issue-two", "clause": "quote2", "severity": "medium", "interpretation": "int2", "harm": "harm2", "tightening": "t2"}
    ]
    
    # Synthesis output marks issue-one as verified, issue-two as verified, and introduces an unconfirmed finding
    synthesis_output = {
        "consolidated_findings": [
            # issue-one: present in Agent 1, validated by synthesis. 1 + 1 = 2 votes. Should be CONFIRMED.
            {"id": "issue-one", "clause": "quote1", "severity": "high", "interpretation": "int1", "harm": "harm1", "tightening": "t1", "validated_by_synthesis": True},
            # issue-two: present in A1 & A2, validated by synthesis. 2 + 1 = 3 votes. Should be CONFIRMED.
            {"id": "issue-two", "clause": "quote2", "severity": "medium", "interpretation": "int2", "harm": "harm2", "tightening": "t2", "validated_by_synthesis": True},
            # issue-three: present in neither, validated by synthesis. 0 + 1 = 1 vote. Should be UNCONFIRMED.
            {"id": "issue-three", "clause": "quote3", "severity": "low", "interpretation": "int3", "harm": "harm3", "tightening": "t3", "validated_by_synthesis": True},
            # issue-four: present in Agent 1, rejected by synthesis. 1 + 0 = 1 vote. Should be UNCONFIRMED.
            {"id": "issue-four", "clause": "quote4", "severity": "low", "interpretation": "int4", "harm": "harm4", "tightening": "t4", "validated_by_synthesis": False}
        ],
        "merged_failed_attacks": []
    }
    
    confirmed, unconfirmed = synthesis.compute_votes_and_quorum(a1_findings, a2_findings, synthesis_output)
    
    # Confirmed findings (votes >= 2)
    assert len(confirmed) == 2
    conf_ids = {f["id"] for f in confirmed}
    assert "issue-one" in conf_ids
    assert "issue-two" in conf_ids
    
    # Verify votes math
    issue_one_obj = [f for f in confirmed if f["id"] == "issue-one"][0]
    assert issue_one_obj["votes"] == 2
    assert "agent-1" in issue_one_obj["sources"]
    
    # Unconfirmed findings (votes == 1)
    assert len(unconfirmed) == 2
    unconf_ids = {f["id"] for f in unconfirmed}
    assert "issue-three" in unconf_ids
    assert "issue-four" in unconf_ids

def test_synthesis_parser_extracts_nested_json():
    """Verify regex-based JSON extractor parses JSON from markdown blocks."""
    # Text with markdown block
    text = "Here is the response:\n```json\n{\n  \"consolidated_findings\": [],\n  \"merged_failed_attacks\": []\n}\n```\nHope it helps!"
    parsed = synthesis._parse_synthesis_json(text)
    assert parsed == {"consolidated_findings": [], "merged_failed_attacks": []}
    
    # Text without markdown block but outermost brackets
    text_bracket = "The response payload: {\"consolidated_findings\": [], \"merged_failed_attacks\": []}"
    parsed_bracket = synthesis._parse_synthesis_json(text_bracket)
    assert parsed_bracket == {"consolidated_findings": [], "merged_failed_attacks": []}

@pytest.mark.asyncio
async def test_synthesis_fallback_loop_success_on_retry():
    """Test that synthesis fallback loop retries on JSON parsing error."""
    config = {
        "synthesis_model": "gemini-3-1-flash-lite",
        "synthesis_temperature": 0.15,
        "gcp_project_id": "test-p",
        "gcp_location": "us"
    }
    
    call_mock = AsyncMock()
    call_mock.side_effect = [
        "Unparseable response text",
        "Still unparseable response text",
        "```json\n{\n  \"consolidated_findings\": [],\n  \"merged_failed_attacks\": []\n}\n```"
    ]
    
    with patch("synthesis.call_remote_synthesis", call_mock):
        res = await synthesis.run_synthesis_with_fallbacks("doc", [], [], config)
        assert res == {"consolidated_findings": [], "merged_failed_attacks": []}
        
    assert call_mock.call_count == 3
    # Check that temperature was adjusted on retry
    assert call_mock.call_args_list[0][0][5] == 0.15
    assert call_mock.call_args_list[1][0][5] == 0.0

@pytest.mark.asyncio
async def test_synthesis_max_retries_raises_exception():
    """Test that after 3 failed synthesis attempts, SynthesisFailureException is raised."""
    config = {
        "synthesis_model": "gemini-3-1-flash-lite",
        "gcp_project_id": "test-p",
        "gcp_location": "us"
    }
    
    call_mock = AsyncMock()
    call_mock.return_value = "Unparseable text"
    
    with patch("synthesis.call_remote_synthesis", call_mock):
        with pytest.raises(synthesis.SynthesisFailureException):
            await synthesis.run_synthesis_with_fallbacks("doc", [], [], config)
            
    assert call_mock.call_count == 3

def test_preprocess_empty_file_fails(tmp_path):
    """Verify preprocessing rejects empty files."""
    empty_file = write_temp_file(tmp_path, "empty.md", "")
    with pytest.raises(ValueError) as exc:
        validator.preprocess_input_file(empty_file)
    assert "empty" in str(exc.value)

def test_preprocess_too_large_bytes_fails(tmp_path):
    """Verify preprocessing rejects files over 1MB."""
    # Write a file slightly over 1MB
    large_file = write_temp_file(tmp_path, "large.md", "a" * (1024 * 1024 + 1))
    with pytest.raises(ValueError) as exc:
        validator.preprocess_input_file(large_file)
    assert "exceeds 1MB" in str(exc.value)

def test_preprocess_too_many_characters_fails(tmp_path):
    """Verify preprocessing rejects files with over 200k characters."""
    large_char_file = write_temp_file(tmp_path, "large_char.md", "a" * 200001)
    with pytest.raises(ValueError) as exc:
        validator.preprocess_input_file(large_char_file)
    assert "exceeds 200,000" in str(exc.value)

def test_report_formatting():
    """Test report formatting logic for specs and plans."""
    # Spec file formatting
    confirmed = [
        {"id": "issue-one", "clause": "quote1", "severity": "high", "interpretation": "int1", "harm": "harm1", "tightening": "t1", "votes": 3}
    ]
    unconfirmed = [
        {"id": "issue-two", "clause": "quote2", "severity": "low", "interpretation": "int2", "harm": "harm2", "tightening": "t2", "votes": 1}
    ]
    failed_attacks = ["bypass-auth"]
    
    report = validator.format_markdown_report("spec.md", confirmed, unconfirmed, failed_attacks, "gemini-3-1-flash-lite", is_plan=False)
    assert "# Adversarial Cloud Validation Report" in report
    assert "quote1" in report
    assert "* **Tightening**:" in report
    assert "- `bypass-auth`" in report
    
    # Plan file formatting
    plan_confirmed = [
        {"id": "issue-one", "clause": "evidence1", "severity": "high", "interpretation": "int1", "harm": "harm1", "tightening": "t1", "votes": 2, "fix": "fix1", "first_domino": "domino1", "evidence": "evidence1"}
    ]
    plan_report = validator.format_markdown_report("plan.md", plan_confirmed, [], [], "gemini-3-1-flash-lite", is_plan=True)
    assert "* **Evidence**:" in plan_report
    assert "* **First Domino**:" in plan_report
    assert "* **Fix**:" in plan_report

def test_compute_votes_and_quorum_fallback_matching():
    """Verify fallback clause matching and 0-vote unconfirmed safety logic."""
    a1_findings = [
        {"id": "agent-one-csrf", "clause": "Must authenticate all API requests via a CSRF token", "severity": "high", "interpretation": "int1", "harm": "harm1", "tightening": "t1"}
    ]
    a2_findings = [
        {"id": "agent-two-csrf-vuln", "clause": "Authenticate all API requests via a CSRF token.", "severity": "high", "interpretation": "int2", "harm": "harm2", "tightening": "t2"}
    ]
    
    # Synthesis output has a completely new ID, but the clause matches
    synthesis_output = {
        "consolidated_findings": [
            {
                "id": "new-csrf-hallucinated-id", 
                "clause": "must authenticate all API requests via a CSRF token", 
                "severity": "high", 
                "interpretation": "int3", 
                "harm": "harm3", 
                "tightening": "t3", 
                "validated_by_synthesis": True
            },
            # Finding with 0 votes, validated_by_synthesis is False
            {
                "id": "unmatched-finding-id",
                "clause": "unmatched clause that does not match anything",
                "severity": "medium",
                "interpretation": "int4",
                "harm": "harm4",
                "tightening": "t4",
                "validated_by_synthesis": False
            }
        ],
        "merged_failed_attacks": []
    }
    
    confirmed, unconfirmed = synthesis.compute_votes_and_quorum(a1_findings, a2_findings, synthesis_output)
    
    # The first consolidated finding should have matched both Agent 1 and Agent 2 via normalized clause
    # So votes = 2 (agent-1 and agent-2 matched) + 1 (validated_by_synthesis) = 3 votes.
    # Its ID should be preserved from Agent 1 (since it matched Agent 1 fallback first).
    assert len(confirmed) == 1
    matched_finding = confirmed[0]
    assert matched_finding["id"] == "agent-one-csrf"
    assert matched_finding["votes"] == 3
    assert set(matched_finding["sources"]) == {"agent-1", "agent-2"}
    
    # The second finding has 0 votes, so it should be in unconfirmed, not silently dropped.
    assert len(unconfirmed) == 1
    unconfirmed_finding = unconfirmed[0]
    assert unconfirmed_finding["id"] == "unmatched-finding-id"
    assert unconfirmed_finding["votes"] == 0

def test_no_violating_files_in_agents_dir():
    """Ensure no Python source code or JSON files reside within metadata folder .agents/."""
    # Start walking up from __file__
    current_path = os.path.abspath(__file__)
    project_root = None
    # Try walking up to 10 levels checking strictly for .git folder
    for _ in range(10):
        current_path = os.path.dirname(current_path)
        if os.path.exists(os.path.join(current_path, ".git")):
            project_root = current_path
            break
    # Fallback to going exactly 7 levels up if not found
    if not project_root:
        current = os.path.abspath(__file__)
        for _ in range(7):
            current = os.path.dirname(current)
        project_root = current
        
    agents_dir = os.path.join(project_root, ".agents")
    assert os.path.exists(agents_dir), f"Metadata folder .agents/ does not exist at resolved path: {agents_dir}"
    for root, dirs, files in os.walk(agents_dir):
        for file in files:
            assert not file.endswith(".py") and not file.endswith(".json"), f"Violating file found in metadata dir: {os.path.join(root, file)}"

def test_clauses_match_short_clauses():
    """Verify that if either clause is short, exact normalized match is required."""
    # Length < 15 check
    assert synthesis.clauses_match("api", "api") is True
    assert synthesis.clauses_match("api", "API") is True
    assert synthesis.clauses_match("api", "Ensure API keys are rotated") is False
    assert synthesis.clauses_match("Ensure API keys are rotated", "api") is False
    # Length >= 15 check
    assert synthesis.clauses_match("Ensure API keys are rotated", "API keys are rotated") is True

def test_stale_id_fallback_matching():
    """Verify that Agent 1 fallback matching updates the ID dynamically and is correctly referenced by Agent 2 check."""
    a1_findings = [
        {"id": "agent-one-finding", "clause": "Must authenticate all API requests via a CSRF token", "severity": "high", "interpretation": "int1", "harm": "harm1", "tightening": "t1"}
    ]
    a2_findings = [
        {"id": "agent-two-finding", "clause": "Authenticate all API requests via a CSRF token.", "severity": "high", "interpretation": "int2", "harm": "harm2", "tightening": "t2"}
    ]
    
    # Synthesis output has a completely new ID, but the clause matches both Agent 1 and Agent 2
    synthesis_output = {
        "consolidated_findings": [
            {
                "id": "new-csrf-hallucinated-id", 
                "clause": "must authenticate all API requests via a CSRF token", 
                "severity": "high", 
                "interpretation": "int3", 
                "harm": "harm3", 
                "tightening": "t3", 
                "validated_by_synthesis": True
            }
        ],
        "merged_failed_attacks": []
    }
    
    confirmed, unconfirmed = synthesis.compute_votes_and_quorum(a1_findings, a2_findings, synthesis_output)
    
    # Verify that the ID was mapped to Agent 1's ID first ("agent-one-finding")
    # and then Agent 2 check correctly resolved it using the updated ID (so both agent-1 and agent-2 matched).
    assert len(confirmed) == 1
    matched_finding = confirmed[0]
    assert matched_finding["id"] == "agent-one-finding"
    assert set(matched_finding["sources"]) == {"agent-1", "agent-2"}
    assert matched_finding["votes"] == 3

@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("vertexai.generative_models.GenerativeModel")
async def test_invoke_gemini_agent_fallback_on_json_parse_exception(mock_model_class, mock_sleep):
    """Verify that invoke_gemini_agent adjusts temperature and appends JSON reminder on AgentJSONParsingException."""
    mock_model_instance = MagicMock()
    mock_model_class.return_value = mock_model_instance
    
    mock_response = AwaitableMock()
    # First response fails to parse as valid JSON
    mock_response.text = "invalid json text"
    # Second response parses successfully
    mock_response.text_ok = '{"findings": [], "failed_attacks": []}'
    
    async def mock_coro(*args, **kwargs):
        return mock_response
    mock_response.side_effect = mock_coro
    
    def side_effect(*args, **kwargs):
        # We simulate first call returning bad json, second returning good json
        if mock_model_instance.generate_content_async.call_count == 1:
            return mock_response
        else:
            mock_response.text = mock_response.text_ok
            return mock_response
            
    mock_model_instance.generate_content_async.side_effect = side_effect
    
    config = {
        "synthesis_temperature": 0.15,
        "synthesis_max_output_tokens": 8192,
        "api_timeout_seconds": 30,
        "api_max_retries": 3
    }
    engine = client.CloudInvocationEngine("test-p", "us", MagicMock(), config)
    
    res = await engine.invoke_gemini_agent("gemini-3.5-flash", "system-prompt", "doc-content")
    assert res == {"findings": [], "failed_attacks": []}
    
    # Assert model was initialized twice (once for initial attempt, once for retry with adjusted parameters)
    assert mock_model_class.call_count == 2
    # Verify first call args
    first_call_kwargs = mock_model_class.call_args_list[0][1]
    assert first_call_kwargs["system_instruction"] == "system-prompt"
    # Verify second call args (has JSON reminder)
    second_call_kwargs = mock_model_class.call_args_list[1][1]
    assert "REMINDER" in second_call_kwargs["system_instruction"]
    # Check that temperature was lowered to 0.0 for the second call
    _, first_generate_kwargs = mock_model_instance.generate_content_async.call_args_list[0]
    _, second_generate_kwargs = mock_model_instance.generate_content_async.call_args_list[1]
    assert first_generate_kwargs["generation_config"]["temperature"] == 0.15
    assert second_generate_kwargs["generation_config"]["temperature"] == 0.0

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
@patch("google.auth.default")
@patch("asyncio.to_thread")
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_invoke_claude_agent_fallback_on_json_parse_exception(mock_sleep, mock_to_thread, mock_auth, mock_post):
    """Verify that invoke_claude_agent adjusts temperature and appends JSON reminder on AgentJSONParsingException."""
    mock_creds = MagicMock()
    mock_creds.token = "mock-access-token"
    mock_auth.return_value = (mock_creds, "mock-project")
    
    mock_response_fail = MagicMock()
    mock_response_fail.raise_for_status = MagicMock()
    mock_response_fail.json.return_value = {
        "content": [{"type": "text", "text": "invalid json"}]
    }
    
    mock_response_pass = MagicMock()
    mock_response_pass.raise_for_status = MagicMock()
    mock_response_pass.json.return_value = {
        "content": [{"type": "text", "text": '{"findings": [], "failed_attacks": []}'}]
    }
    
    mock_post.side_effect = [mock_response_fail, mock_response_pass]
    
    config = {
        "synthesis_temperature": 0.15,
        "synthesis_max_output_tokens": 8192,
        "api_timeout_seconds": 30,
        "api_max_retries": 3
    }
    engine = client.CloudInvocationEngine("mock-project", "us", mock_creds, config)
    
    res = await engine.invoke_claude_agent("claude-haiku-4-5", "system-prompt", "doc-content")
    assert res == {"findings": [], "failed_attacks": []}
    
    assert mock_post.call_count == 2
    # First post call payload check
    first_payload = mock_post.call_args_list[0][1]["json"]
    assert first_payload["temperature"] == 0.15
    assert first_payload["system"] == "system-prompt"
    
    # Second post call payload check
    second_payload = mock_post.call_args_list[1][1]["json"]
    assert second_payload["temperature"] == 0.0
    assert "REMINDER" in second_payload["system"]
