import os
import sys
import json
import pytest
from unittest.mock import MagicMock

# Make `geap_validator_core` importable: tests/ -> geap_validator_core/ -> lib/
CORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_DIR = os.path.dirname(CORE_DIR)
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)


def mock_model_reply(system_instruction: str) -> str:
    """Returns a role- and stage-appropriate canned JSON reply.

    Dispatch is on the system prompt, NOT the model name: any model (e.g. the
    flash-lite default in agent slot 3) can hold any role, so only the
    instructions reveal whether the caller expects agent or synthesis JSON.
    """
    si = system_instruction or ""
    if "Synthesis Model" in si:
        if "merged_checks_that_passed" in si:
            return '```json\n{"consolidated_findings": [], "merged_checks_that_passed": [], "first_domino": null}\n```'
        return '```json\n{"consolidated_findings": [], "merged_failed_attacks": []}\n```'
    if "plan review panel" in si:
        return '```json\n{"findings": [], "first_domino": null, "checks_that_passed": []}\n```'
    return '```json\n{"findings": [], "failed_attacks": []}\n```'


def make_http_response(body: dict, status_code: int = 200):
    """A mock httpx response with real string .text (generate_text greps it on 400s)."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = body
    mock_response.text = json.dumps(body)
    return mock_response


@pytest.fixture(scope="session")
def check_gcp_environment():
    import google.auth
    from google.auth.exceptions import DefaultCredentialsError

    ci_mode = os.environ.get("CI") == "true"

    has_creds = False
    auth_project = None
    try:
        _, auth_project = google.auth.default()
        has_creds = True
    except DefaultCredentialsError:
        pass

    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GEAP_VALIDATOR_PROJECT")

    if not project:
        config_path = os.path.join(CORE_DIR, "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    project = json.load(f).get("gcp_project_id")
            except Exception:
                pass

    if not project:
        project = auth_project

    if not has_creds or not project:
        msg = f"GCP credentials or project variable (current project: {project}) not configured."
        if ci_mode:
            pytest.fail(f"CI Mode is active but GCP verification failed: {msg}")
        else:
            pytest.skip(f"Skipping GCP integration test: {msg}")


@pytest.fixture(autouse=True)
def mock_gcp_and_model_apis(request, monkeypatch):
    """Automatically mocks GCP auth and the single httpx REST surface for unit tests.

    All model traffic (Gemini generateContent AND Claude rawPredict, agents and
    synthesis alike) flows through httpx.AsyncClient.post, so one mock covers
    everything; the URL's publisher segment selects the reply shape.
    """
    fspath = str(getattr(request.node, "fspath", ""))
    if "tests/integration" in fspath or "tests\\integration" in fspath:
        # Do not mock for integration tests
        return

    # 1. Mock Google Auth Default credentials
    import google.auth
    mock_creds = MagicMock()
    mock_creds.token = "mock-access-token"

    def mock_refresh(auth_request):
        mock_creds.token = "mock-access-token-refreshed"
    mock_creds.refresh = mock_refresh
    monkeypatch.setattr(google.auth, "default", lambda *args, **kwargs: (mock_creds, "mock-project-id"))

    # 2. Mock the REST transport (bound method: first positional arg is the client self)
    import httpx

    async def mock_post(self, url, json=None, headers=None, **kwargs):
        payload = json or {}
        if "/publishers/google/" in url:
            system = ((payload.get("systemInstruction") or {}).get("parts") or [{}])[0].get("text", "")
            body = {"candidates": [{"content": {"role": "model", "parts": [{"text": mock_model_reply(system)}]}}]}
        else:
            system = payload.get("system", "")
            body = {"content": [{"type": "text", "text": mock_model_reply(system)}]}
        return make_http_response(body)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
