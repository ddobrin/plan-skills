import os
import json

DEFAULTS = {
    "gcp_location": "us",
    "agent_1_model": "gemini-3.5-flash",
    "agent_2_model": "claude-haiku-4-5",
    "synthesis_model": "gemini-3-1-flash-lite",
    "synthesis_temperature": 0.15,
    "synthesis_max_output_tokens": 8192,
    "api_timeout_seconds": 30,
    "api_max_retries": 3
}

def load_config(config_path: str = None) -> dict:
    """Loads and validates configuration from environment, file, and defaults."""
    config = {}
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except Exception:
            pass

    # Resolve GCP Project ID
    project_id = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("CLOUD_VALIDATOR_PROJECT")
        or config.get("gcp_project_id")
    )
    
    # Resolve Models
    agent_1_model = (
        os.environ.get("CLOUD_VALIDATOR_AGENT_1_MODEL")
        or config.get("agent_1_model")
        or DEFAULTS["agent_1_model"]
    )
    agent_2_model = (
        os.environ.get("CLOUD_VALIDATOR_AGENT_2_MODEL")
        or config.get("agent_2_model")
        or DEFAULTS["agent_2_model"]
    )
    synthesis_model = (
        os.environ.get("CLOUD_VALIDATOR_SYNTHESIS_MODEL")
        or config.get("synthesis_model")
        or DEFAULTS["synthesis_model"]
    )

    resolved = {
        "gcp_project_id": project_id,
        "agent_1_model": agent_1_model,
        "agent_2_model": agent_2_model,
        "synthesis_model": synthesis_model,
    }
    
    # Whitelist validation of models
    allowed_models = {"gemini-3.5-flash", "claude-haiku-4-5", "gemini-3-1-flash-lite"}
    for model_key in ["agent_1_model", "agent_2_model", "synthesis_model"]:
        if resolved[model_key] not in allowed_models:
            raise ValueError(f"Model {resolved[model_key]} is not in the allowed set {allowed_models}")
    
    # Optional parameters and types
    loc = (
        os.environ.get("CLOUD_VALIDATOR_LOCATION")
        or config.get("gcp_location")
        or DEFAULTS["gcp_location"]
    )
    if isinstance(loc, str):
        loc = loc.strip().lower()
    if loc not in {"us", "global"}:
        loc = "us"
    resolved["gcp_location"] = loc
    
    temp_raw = os.environ.get("CLOUD_VALIDATOR_TEMP") or config.get("synthesis_temperature")
    resolved["synthesis_temperature"] = float(temp_raw) if temp_raw is not None else DEFAULTS["synthesis_temperature"]
    
    tokens_raw = os.environ.get("CLOUD_VALIDATOR_MAX_TOKENS") or config.get("synthesis_max_output_tokens")
    resolved["synthesis_max_output_tokens"] = int(tokens_raw) if tokens_raw is not None else DEFAULTS["synthesis_max_output_tokens"]
    
    timeout_raw = os.environ.get("CLOUD_VALIDATOR_TIMEOUT") or config.get("api_timeout_seconds")
    resolved["api_timeout_seconds"] = int(timeout_raw) if timeout_raw is not None else DEFAULTS["api_timeout_seconds"]
    
    retries_raw = os.environ.get("CLOUD_VALIDATOR_RETRIES") or config.get("api_max_retries")
    resolved["api_max_retries"] = int(retries_raw) if retries_raw is not None else DEFAULTS["api_max_retries"]

    if not resolved["gcp_project_id"]:
        raise ValueError("Missing required configuration key: gcp_project_id")

    return resolved
