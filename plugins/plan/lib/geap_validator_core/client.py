import re
import json
import asyncio
import logging
import httpx
import google.auth
import google.auth.transport.requests

from .config_loader import clamp_location

logger = logging.getLogger("geap_validator")

JSON_REMINDER = "\n\nREMINDER: You must output your response as a single, valid JSON block matching the requested schema inside a ```json ... ``` block. Ensure all fields are present and correct."

VERTEX_HOST = "aiplatform.googleapis.com"


class AgentJSONParsingException(Exception):
    """Custom exception raised when an agent's response cannot be parsed or validated against the schema."""
    pass


def initialize_clients(project_id: str, location: str):
    """Resolves ADC credentials and the target project. Pure REST transport — no SDK state to initialize."""
    from google.auth.exceptions import DefaultCredentialsError

    try:
        credentials, resolved_project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    except DefaultCredentialsError as e:
        raise DefaultCredentialsError(f"Application Default Credentials (ADC) are missing or invalid: {str(e)}") from e

    project = project_id or resolved_project
    if not project:
        raise ValueError("GCP Project ID could not be resolved from environment or configuration.")

    return credentials, project


def build_endpoint(project: str, location: str, model_name: str) -> str:
    """Builds the Vertex AI REST endpoint for a model; the name prefix selects publisher and verb.

    The global endpoint host carries no region prefix (aiplatform.googleapis.com,
    NOT global-aiplatform...); regional hosts are {region}-aiplatform.googleapis.com.
    """
    if model_name.startswith("gemini-"):
        publisher, verb = "google", "generateContent"
    elif model_name.startswith("claude-"):
        publisher, verb = "anthropic", "rawPredict"
    else:
        raise ValueError(f"Unsupported model provider for {model_name!r}: expected a 'gemini-*' or 'claude-*' model name.")

    location = clamp_location(location)
    host = VERTEX_HOST if location == "global" else f"{location}-{VERTEX_HOST}"
    return f"https://{host}/v1/projects/{project}/locations/{location}/publishers/{publisher}/models/{model_name}:{verb}"


async def _get_access_token(credentials) -> str:
    auth_req = google.auth.transport.requests.Request()
    await asyncio.to_thread(credentials.refresh, auth_req)
    return credentials.token


async def generate_text(credentials, project: str, location: str, model_name: str,
                        system_prompt: str, user_prompt: str,
                        temperature: float, max_tokens: int, timeout_seconds: int) -> str:
    """Single REST text-generation call with identical control flow for both providers.

    gemini-* -> :generateContent, claude-* -> :rawPredict. Some Claude models
    (e.g. claude-fable-5) reject the temperature parameter outright; a 400
    naming temperature is resent once without it rather than surfaced.
    """
    endpoint_url = build_endpoint(project, location, model_name)
    access_token = await _get_access_token(credentials)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    if model_name.startswith("gemini-"):
        payload = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
    else:
        payload = {
            "anthropic_version": "vertex-2023-10-16",
            "messages": [{"role": "user", "content": user_prompt}],
            "system": system_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

    async with httpx.AsyncClient(timeout=float(timeout_seconds)) as http_client:
        response = await http_client.post(endpoint_url, json=payload, headers=headers)
        if (response.status_code == 400 and "temperature" in payload
                and "temperature" in response.text):
            payload = {k: v for k, v in payload.items() if k != "temperature"}
            response = await http_client.post(endpoint_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    if model_name.startswith("gemini-"):
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    return data["content"][0]["text"]


class CloudInvocationEngine:
    def __init__(self, project_id: str, location: str, credentials, config: dict):
        self.project_id = project_id
        self.location = clamp_location(location)
        self.credentials = credentials
        self.config = config

    def _parse_json_reply(self, raw_reply: str, stage) -> dict:
        """Extracts and parses the JSON findings block from the raw text reply, validating against the stage schema."""
        match = re.search(r'```json\s*(.*?)\s*```', raw_reply, re.DOTALL | re.IGNORECASE)
        content = None
        if match:
            content = match.group(1).strip()
        else:
            match_outer = re.search(r'\{.*\}', raw_reply, re.DOTALL)
            if match_outer:
                content = match_outer.group(0).strip()

        if not content:
            raise AgentJSONParsingException("No JSON content found in agent reply.")

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise AgentJSONParsingException(f"Failed to decode JSON from agent reply: {e}") from e

        if not isinstance(data, dict) or "findings" not in data or stage.no_hole_key not in data:
            raise AgentJSONParsingException(
                f"Agent output is missing required top-level 'findings' or '{stage.no_hole_key}' keys."
            )

        for finding in data["findings"]:
            required_keys = list(stage.finding_required_keys)
            if not all(k in finding for k in required_keys):
                raise AgentJSONParsingException(f"Finding is missing one or more required keys: {required_keys}")
            if not re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', finding["id"]):
                raise AgentJSONParsingException(f"Finding ID '{finding['id']}' does not match stable kebab-case pattern.")

        return data

    async def invoke_agent(self, model_name: str, system_instructions: str, document_content: str, stage) -> dict:
        """Runs one skeptic agent over the shared REST transport, with retries and JSON-repair tightening."""
        if not model_name.startswith(("gemini-", "claude-")):
            raise ValueError(f"Unsupported model provider for {model_name!r}: expected a 'gemini-*' or 'claude-*' model name.")

        query = f"Validate the following document:\n\n{document_content}"

        timeout_seconds = self.config.get("api_timeout_seconds", 30)
        max_retries = self.config.get("api_max_retries", 3)
        temperature = self.config.get("synthesis_temperature", 0.15)
        max_tokens = self.config.get("synthesis_max_output_tokens", 8192)

        last_exception = None
        current_instructions = system_instructions

        for attempt in range(1, max_retries + 1):
            try:
                raw_text = await generate_text(
                    self.credentials, self.project_id, self.location, model_name,
                    current_instructions, query, temperature, max_tokens, timeout_seconds,
                )
                return self._parse_json_reply(raw_text, stage)
            except Exception as e:
                logger.warning(f"Model {model_name} failed on attempt {attempt}: {e}")
                last_exception = e
                if isinstance(e, AgentJSONParsingException):
                    # Adjust parameters for subsequent attempts
                    temperature = 0.0
                    current_instructions = f"{system_instructions}{JSON_REMINDER}"
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)

        raise RuntimeError(f"Model {model_name} execution failed after {max_retries} attempts. Last error: {str(last_exception)}")

    async def run_parallel_validation(self, agent_models: list, stage, doc_content: str) -> list:
        """Runs all skeptic agents in parallel.

        Returns one entry per agent (parsed dict, or None for a failed agent).
        Requires at least 2 successes: with fewer, the 2-vote quorum can only be
        reached by a single skeptic plus the synthesis vote, which defeats the
        panel's purpose.
        """
        tasks = [
            asyncio.create_task(self.invoke_agent(model, stage.agent_prompts[i], doc_content, stage))
            for i, model in enumerate(agent_models)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        outputs = [None if isinstance(r, Exception) else r for r in results]

        successes = sum(1 for o in outputs if o is not None)
        if successes < 2:
            errors = "; ".join(
                f"agent-{i + 1} ({agent_models[i]}): {r}"
                for i, r in enumerate(results) if isinstance(r, Exception)
            )
            raise RuntimeError(f"Quorum unreachable: fewer than 2 of {len(agent_models)} skeptic agents succeeded. {errors}")

        return outputs
