import os
import sys
import pytest
from unittest.mock import MagicMock

# Inject skill directory into sys.path
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

@pytest.fixture(scope="session")
def check_gcp_environment():
    import google.auth
    from google.auth.exceptions import DefaultCredentialsError
    import json
    
    ci_mode = os.environ.get("CI") == "true"
    
    # Check credentials
    has_creds = False
    auth_project = None
    try:
        _, auth_project = google.auth.default()
        has_creds = True
    except DefaultCredentialsError:
        pass
        
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("CLOUD_VALIDATOR_PROJECT")
    
    if not project:
        config_path = os.path.join(SKILL_DIR, "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config_data = json.load(f)
                    project = config_data.get("gcp_project_id")
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
def mock_gcp_and_vertex_apis(request, monkeypatch):
    """Automatically mocks all GCP authorization and remote model APIs for unit tests."""
    fspath = getattr(request.node, "fspath", None)
    if fspath is not None and ("tests/integration" in getattr(fspath, "strpath", "") or "tests/integration" in str(fspath)):
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

    # 2. Mock Vertex AI Initialization
    import vertexai
    monkeypatch.setattr(vertexai, "init", lambda *args, **kwargs: None)

    # 3. Mock GenerativeModel
    import vertexai.generative_models
    class MockGenerativeModel:
        def __init__(self, model_name, system_instruction=None):
            self.model_name = model_name
            self.system_instruction = system_instruction

        async def generate_content_async(self, contents, generation_config=None):
            mock_response = MagicMock()
            # Dynamic response content based on model
            if "synthesis" in self.model_name or "lite" in self.model_name:
                mock_response.text = '```json\n{\n  "consolidated_findings": [],\n  "merged_failed_attacks": []\n}\n```'
            else:
                mock_response.text = '```json\n{\n  "findings": [],\n  "failed_attacks": []\n}\n```'
            return mock_response
            
    monkeypatch.setattr(vertexai.generative_models, "GenerativeModel", MockGenerativeModel)

    # 4. Mock HTTPX Client post requests for Claude REST APIs
    import httpx
    mock_post_response = MagicMock()
    mock_post_response.status_code = 200
    mock_post_response.json.return_value = {
        "content": [
            {
                "type": "text",
                "text": '```json\n{\n  "findings": [],\n  "failed_attacks": []\n}\n```'
            }
        ]
    }
    mock_post_response.raise_for_status = MagicMock()

    async def mock_post(*args, **kwargs):
        return mock_post_response
        
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
