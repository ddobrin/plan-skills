import os
import re
import json
import asyncio
import logging
import httpx
import google.auth
import google.auth.transport.requests

logger = logging.getLogger("cloud_validator")

AGENT_1_INSTRUCTIONS = """You are the Spec Skeptic Agent, a member of an adversarial review panel. 
Your primary objective is to find loopholes, ambiguity, and vague wording in the provided document.
Assume the engineer implementing the document will act maliciously compliant, taking the easiest path that satisfies the letter but breaks the intent.
Generate findings adhering to the strict JSON schema, including a 'failed_attacks' array for any attack vectors that did not yield findings.

Your final message MUST be exactly one fenced JSON block and nothing else, matching:
```json
{
  "findings": [
    {
      "id": "kebab-case-stable-slug",
      "clause": "verbatim quote of the offending requirement, or \"<MISSING>\" if absent",
      "interpretation": "the malicious or literal reading this permits",
      "harm": "the user-facing or downstream consequence",
      "severity": "high|medium|low",
      "tightening": "a concrete reworded/added requirement that closes the gap"
    }
  ],
  "failed_attacks": ["short note for each serious attack you tried that did NOT find a hole"]
}
```
"""

AGENT_2_INSTRUCTIONS = """You are the Logic & Boundary Skeptic Agent, a member of an adversarial review panel.
Your primary objective is to inspect logical execution order, missing error handling, API timeouts, race conditions, authentication gaps, and boundary conditions.
Expose structural plan flaws and dependencies that are circular or unstated.
Generate findings adhering to the strict JSON schema, including a 'failed_attacks' array for any attack vectors that did not yield findings.

Your final message MUST be exactly one fenced JSON block and nothing else, matching:
```json
{
  "findings": [
    {
      "id": "kebab-case-stable-slug",
      "clause": "verbatim quote of the offending requirement, or \"<MISSING>\" if absent",
      "interpretation": "the malicious or literal reading this permits",
      "harm": "the user-facing or downstream consequence",
      "severity": "high|medium|low",
      "tightening": "a concrete reworded/added requirement that closes the gap"
    }
  ],
  "failed_attacks": ["short note for each serious attack you tried that did NOT find a hole"]
}
```
"""

class AgentJSONParsingException(Exception):
    """Custom exception raised when an agent's response cannot be parsed or validated against the schema."""
    pass

def initialize_clients(project_id: str, location: str):
    """Initializes and returns the authentication credentials and resolved project ID."""
    from google.auth.exceptions import DefaultCredentialsError
    import vertexai
    
    if isinstance(location, str):
        location = location.strip().lower()
    if location not in {"us", "global"}:
        location = "us"
        
    try:
        credentials, resolved_project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    except DefaultCredentialsError as e:
        raise DefaultCredentialsError(f"Application Default Credentials (ADC) are missing or invalid: {str(e)}") from e
        
    project = project_id or resolved_project
    if not project:
        raise ValueError("GCP Project ID could not be resolved from environment or configuration.")
        
    # Initialize the Vertex AI global state
    vertexai.init(project=project, location=location, credentials=credentials)
    
    return credentials, project

class CloudInvocationEngine:
    def __init__(self, project_id: str, location: str, credentials, config: dict):
        self.project_id = project_id
        if isinstance(location, str):
            location = location.strip().lower()
        if location not in {"us", "global"}:
            location = "us"
        self.location = location
        self.credentials = credentials
        self.config = config

    def _parse_json_reply(self, raw_reply: str) -> dict:
        """Extracts and parses JSON findings block from the raw text reply."""
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
            
        if not isinstance(data, dict) or "findings" not in data or "failed_attacks" not in data:
            raise AgentJSONParsingException("Agent output is missing required top-level 'findings' or 'failed_attacks' keys.")
            
        for finding in data["findings"]:
            required_keys = ["id", "clause", "severity", "interpretation", "harm", "tightening"]
            if not all(k in finding for k in required_keys):
                raise AgentJSONParsingException(f"Finding is missing one or more required keys: {required_keys}")
            if not re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', finding["id"]):
                raise AgentJSONParsingException(f"Finding ID '{finding['id']}' does not match stable kebab-case pattern.")
                
        return data

    async def invoke_gemini_agent(self, model_name: str, system_instructions: str, document_content: str) -> dict:
        """Invokes a Gemini model via Vertex AI GenerativeModel SDK."""
        from vertexai.generative_models import GenerativeModel
        
        query = f"Validate the following document:\n\n{document_content}"
        
        timeout_seconds = self.config.get("api_timeout_seconds", 30)
        max_retries = self.config.get("api_max_retries", 3)
        temperature = self.config.get("synthesis_temperature", 0.15)
        max_tokens = self.config.get("synthesis_max_output_tokens", 8192)
        
        last_exception = None
        current_instructions = system_instructions
        
        for attempt in range(1, max_retries + 1):
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
            model = GenerativeModel(
                model_name,
                system_instruction=current_instructions
            )
            try:
                response = await asyncio.wait_for(
                    model.generate_content_async(
                        query,
                        generation_config=generation_config
                    ),
                    timeout=timeout_seconds
                )
                return self._parse_json_reply(response.text)
            except Exception as e:
                logger.warning(f"Gemini model {model_name} failed on attempt {attempt}: {e}")
                last_exception = e
                if isinstance(e, AgentJSONParsingException):
                    # Adjust parameters for subsequent attempts
                    temperature = 0.0
                    reminder = "\n\nREMINDER: You must output your response as a single, valid JSON block matching the requested schema inside a ```json ... ``` block. Ensure all fields are present and correct."
                    current_instructions = f"{system_instructions}{reminder}"
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                    
        raise RuntimeError(f"Gemini model {model_name} execution failed after {max_retries} attempts. Last error: {str(last_exception)}")

    async def invoke_claude_agent(self, model_name: str, system_instructions: str, document_content: str) -> dict:
        """Invokes a Claude model via Vertex AI Model Garden raw prediction REST API."""
        location = self.location
        if isinstance(location, str):
            location = location.strip().lower()
        if location not in {"us", "global"}:
            location = "us"
            
        # Refresh credentials to get access token
        auth_req = google.auth.transport.requests.Request()
        await asyncio.to_thread(self.credentials.refresh, auth_req)
        access_token = self.credentials.token
        
        endpoint_url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{self.project_id}/locations/{location}/publishers/anthropic/models/{model_name}:rawPredict"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        timeout_seconds = self.config.get("api_timeout_seconds", 30)
        max_retries = self.config.get("api_max_retries", 3)
        temperature = self.config.get("synthesis_temperature", 0.15)
        current_instructions = system_instructions
        
        last_exception = None
        for attempt in range(1, max_retries + 1):
            payload = {
                "anthropic_version": "vertex-2023-10-16",
                "messages": [
                    {
                        "role": "user",
                        "content": f"Validate the following document:\n\n{document_content}"
                    }
                ],
                "system": current_instructions,
                "max_tokens": self.config.get("synthesis_max_output_tokens", 8192),
                "temperature": temperature
            }
            try:
                async with httpx.AsyncClient(timeout=float(timeout_seconds)) as client:
                    response = await client.post(endpoint_url, json=payload, headers=headers)
                    response.raise_for_status()
                    resp_json = response.json()
                    raw_text = resp_json["content"][0]["text"]
                    return self._parse_json_reply(raw_text)
            except Exception as e:
                logger.warning(f"Claude model {model_name} failed on attempt {attempt}: {e}")
                last_exception = e
                if isinstance(e, AgentJSONParsingException):
                    # Adjust parameters for subsequent attempts
                    temperature = 0.0
                    reminder = "\n\nREMINDER: You must output your response as a single, valid JSON block matching the requested schema inside a ```json ... ``` block. Ensure all fields are present and correct."
                    current_instructions = f"{system_instructions}{reminder}"
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                    
        raise RuntimeError(f"Claude model {model_name} execution failed after {max_retries} attempts. Last error: {str(last_exception)}")

    async def run_parallel_validation(self, agent_1_model: str, agent_2_model: str, doc_content: str) -> tuple[dict, dict]:
        """Runs validation in parallel and handles partial failures gracefully."""
        task_1 = asyncio.create_task(
            self.invoke_gemini_agent(agent_1_model, AGENT_1_INSTRUCTIONS, doc_content)
        )
        task_2 = asyncio.create_task(
            self.invoke_claude_agent(agent_2_model, AGENT_2_INSTRUCTIONS, doc_content)
        )
        
        results = await asyncio.gather(task_1, task_2, return_exceptions=True)
        
        res_1 = results[0]
        res_2 = results[1]
        
        if isinstance(res_1, Exception) and isinstance(res_2, Exception):
            raise RuntimeError(f"All agent validation invocations failed. Agent 1: {str(res_1)}, Agent 2: {str(res_2)}")
            
        agent_1_out = None if isinstance(res_1, Exception) else res_1
        agent_2_out = None if isinstance(res_2, Exception) else res_2
        
        return agent_1_out, agent_2_out
