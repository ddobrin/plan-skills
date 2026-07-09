import os
import json
import pytest
from unittest.mock import patch

from geap_validator_core import config_loader

CORE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def write_temp_file(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


BASE_CFG = {
    "gcp_project_id": "file-project",
    "agent_1_model": "gemini-3.5-flash",
    "agent_2_model": "claude-haiku-4-5",
    "agent_3_model": "gemini-3-1-flash-lite",
    "synthesis_model": "gemini-3-1-flash-lite",
}


def test_config_json_format():
    """Verify the shipped config.json exists and has required keys."""
    config_path = os.path.join(CORE_DIR, "config.json")
    assert os.path.exists(config_path)
    with open(config_path, "r") as f:
        data = json.load(f)
    for key in ["gcp_project_id", "agent_1_model", "agent_2_model", "agent_3_model", "synthesis_model"]:
        assert key in data


def test_config_load_from_file(tmp_path):
    cfg_file = write_temp_file(tmp_path, "test_config.json", json.dumps(BASE_CFG))
    with patch.dict(os.environ, {}, clear=True):
        resolved = config_loader.load_config(cfg_file)
        assert resolved["gcp_project_id"] == "file-project"
        assert resolved["agent_1_model"] == "gemini-3.5-flash"
        assert resolved["agent_2_model"] == "claude-haiku-4-5"
        assert resolved["agent_3_model"] == "gemini-3-1-flash-lite"
        assert resolved["synthesis_model"] == "gemini-3-1-flash-lite"
        assert resolved["gcp_location"] == "global"  # Default (only supported value)


def test_config_env_variable_overrides(tmp_path):
    cfg_file = write_temp_file(tmp_path, "test_config.json", json.dumps(BASE_CFG))
    env_vars = {
        "GOOGLE_CLOUD_PROJECT": "env-project",
        "GEAP_VALIDATOR_AGENT_1_MODEL": "gemini-env-model",
        "GEAP_VALIDATOR_AGENT_2_MODEL": "claude-env-model",
        "GEAP_VALIDATOR_AGENT_3_MODEL": "gemini-env-third",
        "GEAP_VALIDATOR_SYNTHESIS_MODEL": "gemini-env-synth",
        "GEAP_VALIDATOR_LOCATION": "global",
    }
    with patch.dict(os.environ, env_vars, clear=True):
        resolved = config_loader.load_config(cfg_file)
        assert resolved["gcp_project_id"] == "env-project"
        assert resolved["agent_1_model"] == "gemini-env-model"
        assert resolved["agent_2_model"] == "claude-env-model"
        assert resolved["agent_3_model"] == "gemini-env-third"
        assert resolved["synthesis_model"] == "gemini-env-synth"
        assert resolved["gcp_location"] == "global"


def test_config_missing_required_keys_raises(tmp_path):
    cfg = {k: v for k, v in BASE_CFG.items() if k != "gcp_project_id"}
    cfg_file = write_temp_file(tmp_path, "test_config.json", json.dumps(cfg))
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError) as exc:
            config_loader.load_config(cfg_file)
        assert "gcp_project_id" in str(exc.value)


def test_config_invalid_model_raises_value_error(tmp_path):
    cfg = dict(BASE_CFG, agent_1_model="invalid-model-name")
    cfg_file = write_temp_file(tmp_path, "test_config.json", json.dumps(cfg))
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError) as exc:
            config_loader.load_config(cfg_file)
        assert "invalid-model-name" in str(exc.value)


def test_config_any_location_clamps_to_global(tmp_path):
    """Legacy/regional locations are clamped: current-gen models only serve on the global endpoint."""
    for legacy in ["us", "us-central1", "us-east5", "invalid-location"]:
        cfg = dict(BASE_CFG, gcp_location=legacy)
        cfg_file = write_temp_file(tmp_path, "test_config.json", json.dumps(cfg))
        with patch.dict(os.environ, {}, clear=True):
            resolved = config_loader.load_config(cfg_file)
            assert resolved["gcp_location"] == "global"


def test_agent_3_default_applied(tmp_path):
    """A config predating agent_3_model still resolves via DEFAULTS."""
    cfg = {k: v for k, v in BASE_CFG.items() if k != "agent_3_model"}
    cfg_file = write_temp_file(tmp_path, "test_config.json", json.dumps(cfg))
    with patch.dict(os.environ, {}, clear=True):
        resolved = config_loader.load_config(cfg_file)
        assert resolved["agent_3_model"] == config_loader.DEFAULTS["agent_3_model"]


def test_claude_accepted_in_any_agent_slot(tmp_path):
    """Provider-prefix validation puts no whitelist on model names: any slot takes either provider."""
    cfg = dict(BASE_CFG, agent_1_model="claude-opus-4-8", agent_3_model="claude-haiku-4-5")
    cfg_file = write_temp_file(tmp_path, "test_config.json", json.dumps(cfg))
    with patch.dict(os.environ, {}, clear=True):
        resolved = config_loader.load_config(cfg_file)
        assert resolved["agent_1_model"] == "claude-opus-4-8"
        assert resolved["agent_3_model"] == "claude-haiku-4-5"


def test_claude_synthesis_model_accepted(tmp_path):
    """Both providers are first-class synthesizers — same REST transport either way."""
    for model in ["claude-fable-5", "claude-haiku-4-5", "gemini-3.5-flash"]:
        cfg = dict(BASE_CFG, synthesis_model=model)
        cfg_file = write_temp_file(tmp_path, "test_config.json", json.dumps(cfg))
        with patch.dict(os.environ, {}, clear=True):
            resolved = config_loader.load_config(cfg_file)
            assert resolved["synthesis_model"] == model


def test_unsupported_synthesis_provider_rejected(tmp_path):
    cfg = dict(BASE_CFG, synthesis_model="gpt-4o")
    cfg_file = write_temp_file(tmp_path, "test_config.json", json.dumps(cfg))
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError) as exc:
            config_loader.load_config(cfg_file)
        assert "synthesis_model" in str(exc.value)


def test_clamp_location():
    assert config_loader.clamp_location("global") == "global"
    assert config_loader.clamp_location(" Global ") == "global"
    assert config_loader.clamp_location("us") == "global"
    assert config_loader.clamp_location("us-central1") == "global"
    assert config_loader.clamp_location("europe-west1") == "global"
    assert config_loader.clamp_location(None) == "global"
