import os
import pytest

from geap_validator_core.config_loader import load_config
from geap_validator_core.client import initialize_clients, generate_text

pytestmark = pytest.mark.usefixtures("check_gcp_environment")

CORE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load():
    config = load_config(os.path.join(CORE_DIR, "config.json"))
    credentials, project = initialize_clients(config.get("gcp_project_id"), config.get("gcp_location"))
    return config, credentials, project


def test_e2e_client_initialization():
    """Configuration loads and ADC credentials resolve — no SDK involved."""
    config, credentials, project = _load()
    assert credentials is not None
    assert project is not None
    assert config["gcp_location"] == "global"


@pytest.mark.asyncio
async def test_e2e_gemini_rest_smoke():
    """Real generateContent micro-call: proves the Gemini REST endpoint and payload shape."""
    config, credentials, project = _load()
    text = await generate_text(
        credentials, project, config["gcp_location"], "gemini-3.1-flash-lite",
        "You are terse.", "Reply with exactly: OK", 0.0, 50, 60,
    )
    assert text.strip()


@pytest.mark.asyncio
async def test_e2e_claude_rest_smoke():
    """Real rawPredict micro-call on the global endpoint: proves the Claude REST path."""
    config, credentials, project = _load()
    text = await generate_text(
        credentials, project, config["gcp_location"], "claude-haiku-4-5",
        "You are terse.", "Reply with exactly: OK", 0.0, 20, 60,
    )
    assert text.strip()
