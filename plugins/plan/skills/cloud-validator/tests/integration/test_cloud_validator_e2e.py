import pytest
import os
from unittest.mock import patch
from client import initialize_clients
from config_loader import load_config

pytestmark = pytest.mark.usefixtures("check_gcp_environment")

@pytest.mark.asyncio
async def test_e2e_client_initialization():
    """Verify that configuration loads and clients initialize correctly on GCP."""
    skill_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_path = os.path.join(skill_dir, "config.json")
    config = load_config(config_path)
    
    with patch("vertexai.init") as mock_init:
        credentials, project = initialize_clients(config.get("gcp_project_id"), config.get("gcp_location"))
        assert credentials is not None
        assert project is not None
        mock_init.assert_called_once_with(
            project=project,
            location=config.get("gcp_location"),
            credentials=credentials
        )

