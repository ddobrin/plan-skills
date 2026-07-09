import re
import json
import logging
import asyncio

from .config_loader import clamp_location

logger = logging.getLogger("geap_validator")


class SynthesisFailureException(Exception):
    """Custom exception raised when synthesis fails or cannot return valid JSON."""
    pass


SYSTEM_REMINDER = "REMINDER: You must output your response as a single, valid JSON block matching the requested schema inside a ```json ... ``` block. Ensure all fields are present and correct."


def _parse_synthesis_json(text: str, stage) -> dict:
    """Extracts and parses JSON from the synthesis model response, validating against the stage schema."""
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
    content = None
    if match:
        content = match.group(1).strip()
    else:
        match_outer = re.search(r'\{.*\}', text, re.DOTALL)
        if match_outer:
            content = match_outer.group(0).strip()

    if not content:
        raise ValueError("No JSON content found in synthesis reply.")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to decode JSON from synthesis reply: {e}") from e

    if not isinstance(data, dict) or not all(k in data for k in stage.synthesis_required_keys):
        raise ValueError(
            f"Synthesis output missing required top-level keys: {list(stage.synthesis_required_keys)}."
        )

    for finding in data["consolidated_findings"]:
        required_keys = list(stage.synthesis_finding_required_keys)
        if not all(k in finding for k in required_keys):
            raise ValueError(f"Consolidated finding is missing one or more required keys: {required_keys}")

    return data


async def call_remote_synthesis(project_id: str, location: str, model_name: str, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int, timeout_seconds: int = 120) -> str:
    """Invokes the synthesis model over the same REST transport as the skeptic agents.

    Both gemini-* and claude-* models are first-class synthesizers; the model-name
    prefix routes inside client.generate_text.
    """
    import google.auth

    from .client import generate_text

    location = clamp_location(location)

    credentials, resolved_project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    project = project_id or resolved_project

    return await generate_text(
        credentials, project, location, model_name,
        system_prompt, user_prompt, temperature, max_tokens, timeout_seconds,
    )



def build_synthesis_user_prompt(doc_content: str, agent_findings: list) -> str:
    """Builds the prompt text containing the target document and per-agent findings for the synthesis model."""
    user_prompt = f"TARGET DOCUMENT:\n{doc_content}\n\n"
    for i, findings in enumerate(agent_findings):
        user_prompt += f"AGENT {i + 1} RAW FINDINGS:\n{json.dumps(findings, indent=2)}\n\n"
    user_prompt += "Please group, consolidate, and validate these findings according to your system instructions."
    return user_prompt


def normalize_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()


def texts_match(t1: str, t2: str) -> bool:
    n1 = normalize_text(t1)
    n2 = normalize_text(t2)
    if not n1 or not n2:
        return False
    if len(t1) < 15 or len(t2) < 15:
        return n1 == n2
    return n1 == n2 or n1 in n2 or n2 in n1


# Backwards-friendly aliases: the fuzzy matcher originally operated on spec clauses.
normalize_clause = normalize_text
clauses_match = texts_match


def compute_votes_and_quorum(agent_findings: list, synthesis_output: dict, stage) -> tuple:
    """
    Computes votes programmatically in Python using stable ID mapping to prevent hallucinations.

    agent_findings is one findings list per skeptic agent (an agent that failed
    contributes an empty list). Each consolidated finding earns one vote per agent
    that reported it (matched by stable ID, falling back to fuzzy matching on the
    stage's match field) plus one vote if the synthesis model validated it.
    Classifies findings into confirmed (>= 2 votes) and unconfirmed (< 2 votes) lists.
    """
    ids_per_agent = [{f["id"] for f in findings} for findings in agent_findings]
    all_agent_ids = set().union(*ids_per_agent) if ids_per_agent else set()

    confirmed = []
    unconfirmed = []

    consolidated = synthesis_output.get("consolidated_findings", [])

    for finding in consolidated:
        sources = []
        # An ID already present in any agent's output is authoritative; only a
        # hallucinated/renamed ID gets replaced by the first fuzzy-matched agent's ID.
        id_resolved = finding.get("id") in all_agent_ids

        for i, findings in enumerate(agent_findings):
            agent_name = f"agent-{i + 1}"
            if finding.get("id") in ids_per_agent[i]:
                sources.append(agent_name)
                continue
            for agent_finding in findings:
                if texts_match(finding.get(stage.match_field, ""), agent_finding.get(stage.match_field, "")):
                    sources.append(agent_name)
                    if not id_resolved:
                        finding["id"] = agent_finding.get("id")
                        id_resolved = True
                    break

        # Programmatic vote count
        votes = len(sources)
        validated_by_synthesis = finding.get("validated_by_synthesis", False)
        if validated_by_synthesis:
            votes += 1

        # Update finding fields programmatically
        finding["sources"] = sources
        finding["votes"] = votes

        # Quorum classification
        if votes >= 2:
            confirmed.append(finding)
        else:
            unconfirmed.append(finding)

    return confirmed, unconfirmed


def compute_first_domino(agent_outputs: list, synthesis_output: dict, confirmed: list):
    """Determines the first domino: the confirmed finding most often voted by the
    agents as the earliest failure that invalidates later steps.

    Falls back to the synthesis model's nomination when no agent nomination survived
    the quorum. Returns None when nothing confirmed was nominated.
    """
    confirmed_ids = {f.get("id") for f in confirmed}
    if not confirmed_ids:
        return None

    tally = {}
    for output in agent_outputs:
        if not output:
            continue
        nominee = output.get("first_domino")
        if nominee and nominee in confirmed_ids:
            tally[nominee] = tally.get(nominee, 0) + 1

    if tally:
        return max(tally, key=tally.get)

    synthesis_nominee = synthesis_output.get("first_domino")
    if synthesis_nominee in confirmed_ids:
        return synthesis_nominee
    return None


async def run_synthesis_with_fallbacks(doc_content: str, agent_findings: list, config: dict, stage) -> dict:
    """Runs the synthesis query with temperature tuning and JSON reminders on parse failure.

    The configured model is never substituted: both providers get the same
    3-attempt treatment, then SynthesisFailureException.
    """
    synthesis_model = config.get("synthesis_model", "claude-fable-5")
    temperature = config.get("synthesis_temperature", 0.15)
    max_tokens = config.get("synthesis_max_output_tokens", 8192)
    timeout_seconds = config.get("api_timeout_seconds", 120)
    project_id = config.get("gcp_project_id")
    location = clamp_location(config.get("gcp_location", "global"))

    system_prompt = stage.synthesis_prompt
    user_prompt = build_synthesis_user_prompt(doc_content, agent_findings)

    attempts = 3
    last_exception = None
    for attempt in range(1, attempts + 1):
        try:
            logger.info(f"Synthesis call attempt {attempt}/{attempts} (temp={temperature})")
            reply = await call_remote_synthesis(project_id, location, synthesis_model, system_prompt, user_prompt, temperature, max_tokens, timeout_seconds=timeout_seconds)
            return _parse_synthesis_json(reply, stage)
        except Exception as e:
            logger.warning(f"Synthesis attempt {attempt} failed: {str(e)}")
            last_exception = e
            # Adjust parameters for retry
            temperature = 0.0
            system_prompt = f"{stage.synthesis_prompt}\n\n{SYSTEM_REMINDER}"
            if attempt < attempts:
                await asyncio.sleep(2 ** attempt)
    raise SynthesisFailureException(f"Synthesis model {synthesis_model} failed after {attempts} attempts. Last error: {str(last_exception)}") from last_exception
