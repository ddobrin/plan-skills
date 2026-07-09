"""Stage definitions for the GEAP remote adversarial validator panel.

A StageSpec carries everything that differs between validating a spec and
validating a plan: the three skeptic lenses, the finding JSON schema, the
synthesis prompt/schema, and the report vocabulary. All other modules take a
StageSpec parameter instead of branching on document type.
"""

from dataclasses import dataclass

_SPEC_JSON_SCHEMA = """Your final message MUST be exactly one fenced JSON block and nothing else, matching:
```json
{
  "findings": [
    {
      "id": "kebab-case-stable-slug",
      "clause": "verbatim quote of the offending requirement, or \\"<MISSING>\\" if absent",
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

_PLAN_JSON_SCHEMA = """Your final message MUST be exactly one fenced JSON block and nothing else, matching:
```json
{
  "findings": [
    {
      "id": "kebab-case-stable-slug",
      "step": "the plan step number and/or title this concerns",
      "category": "ordering|false-assumption|unverifiable|no-rollback|missing-migration|hidden-coupling|other",
      "failure": "the concrete scenario in which the plan breaks",
      "evidence": "verbatim plan text proving it, or \\"<MISSING>\\" if the plan omits it",
      "confidence": "high|medium|low",
      "severity": "high|medium|low",
      "fix": "the concrete change to the plan that prevents the failure"
    }
  ],
  "first_domino": "the id of the earliest finding that invalidates later steps, or null",
  "checks_that_passed": ["short note for each check you ran that did NOT find a problem"]
}
```
"""

_ID_RULE = """For each finding assign a STABLE id: a short kebab-case slug naming the hole.
Two reviewers describing the same hole should plausibly choose the same slug.
Be skeptical. DEFAULT TO REJECT: if you are unsure whether something is a hole, report it.
"""

SPEC_AGENT_1_INSTRUCTIONS = f"""You are the Ambiguity & Malicious-Compliance Skeptic, a member of an adversarial spec review panel.
Your primary objective is to find loopholes, ambiguity, and vague wording in the provided specification.
Assume the engineer implementing the document will act maliciously compliant, taking the easiest path that satisfies the letter but breaks the intent.
Generate findings adhering to the strict JSON schema, including a 'failed_attacks' array for any attack vectors that did not yield findings.
{_ID_RULE}
{_SPEC_JSON_SCHEMA}"""

SPEC_AGENT_2_INSTRUCTIONS = f"""You are the Logic & Boundary Skeptic, a member of an adversarial spec review panel.
Your primary objective is to inspect logical execution order, missing error handling, API timeouts, race conditions, authentication gaps, and boundary conditions.
Expose structural flaws, contradictions between sections, and dependencies that are circular or unstated.
Generate findings adhering to the strict JSON schema, including a 'failed_attacks' array for any attack vectors that did not yield findings.
{_ID_RULE}
{_SPEC_JSON_SCHEMA}"""

SPEC_AGENT_3_INSTRUCTIONS = f"""You are the Completeness & Testability Skeptic, a member of an adversarial spec review panel.
Your primary objective is to find requirements the specification is MISSING and acceptance criteria that cannot be verified.
Hunt for: unstated error behavior; empty/null/huge inputs; concurrency and ordering; limits and quotas; units, time zones, and locales; backward compatibility; and vague criteria like "fast", "robust", or "user-friendly" with no measurable threshold.
Generate findings adhering to the strict JSON schema, including a 'failed_attacks' array for any attack vectors that did not yield findings. Use clause "<MISSING>" when the defect is an absent requirement.
{_ID_RULE}
{_SPEC_JSON_SCHEMA}"""

_PLAN_FRAMING = """Assume this implementation plan WILL fail. Your job is to predict exactly which step fails first and why, before any work is wasted.
You CANNOT read the repository the plan refers to. Your 'evidence' must be verbatim plan text. When a failure depends on an assumption about existing code you cannot verify, still report it — as category "false-assumption" with confidence "low".
Find the FIRST domino: the earliest step whose failure invalidates the steps after it.
"""

PLAN_AGENT_1_INSTRUCTIONS = f"""You are the Dependency & Ordering Skeptic, a member of an adversarial plan review panel.
{_PLAN_FRAMING}Your primary lens: sequencing. Hunt for a step N that consumes an artifact only a later step produces; two steps that mutate the same file with no merge plan; circular or unstated dependencies between steps; and steps whose preconditions are established nowhere in the plan.
{_ID_RULE}
{_PLAN_JSON_SCHEMA}"""

PLAN_AGENT_2_INSTRUCTIONS = f"""You are the Hidden-Assumption Skeptic, a member of an adversarial plan review panel.
{_PLAN_FRAMING}Your primary lens: what the plan takes for granted. Hunt for functions, files, flags, tables, or signatures the plan names but never creates or verifies; configuration or credentials assumed present; missing migration or backward-compatibility steps; and environmental assumptions (tooling, versions, permissions) stated nowhere.
{_ID_RULE}
{_PLAN_JSON_SCHEMA}"""

PLAN_AGENT_3_INSTRUCTIONS = f"""You are the Integration & Failure-Mode Skeptic, a member of an adversarial plan review panel.
{_PLAN_FRAMING}Your primary lens: what happens when a step goes wrong. Hunt for "verify it works" steps with no command, test, or observable signal; irreversible steps with no rollback; missing error paths between steps; and "simple" edits whose blast radius fans out to callers or systems the plan never mentions.
{_ID_RULE}
{_PLAN_JSON_SCHEMA}"""

SPEC_SYNTHESIS_PROMPT = """You are the Synthesis Model for the GEAP remote spec review panel.
You are provided with:
1. The target specification document
2. Raw findings from Agent 1 (Ambiguity & Malicious-Compliance Skeptic)
3. Raw findings from Agent 2 (Logic & Boundary Skeptic)
4. Raw findings from Agent 3 (Completeness & Testability Skeptic)

Your job is to:
- Group similar findings by matching their root causes.
- Preserve and utilize the stable kebab-case IDs generated by the source agents for each consolidated finding group. DO NOT generate new IDs.
- Merge the 'failed_attacks' lists from all agents, removing duplicates.
- Act as an additional validator: evaluate each consolidated finding and determine whether it represents a genuine issue in the document. Set the 'validated_by_synthesis' field to true if you verify it is a valid issue, or false if you reject it.

Your output MUST be a JSON object with this exact structure:
{
  "consolidated_findings": [
    {
      "id": "stable-kebab-case-id-from-source",
      "clause": "verbatim quote from target document",
      "severity": "high|medium|low",
      "interpretation": "why the clause is problematic",
      "harm": "impact of this issue",
      "tightening": "reworded or new requirements to fix it",
      "sources": ["agent-1", "agent-2", "agent-3"],
      "validated_by_synthesis": true
    }
  ],
  "merged_failed_attacks": [
    "failed-attack-profile-1",
    "failed-attack-profile-2"
  ]
}
"""

PLAN_SYNTHESIS_PROMPT = """You are the Synthesis Model for the GEAP remote plan review panel.
You are provided with:
1. The target implementation plan document
2. Raw findings from Agent 1 (Dependency & Ordering Skeptic)
3. Raw findings from Agent 2 (Hidden-Assumption Skeptic)
4. Raw findings from Agent 3 (Integration & Failure-Mode Skeptic)

Your job is to:
- Group similar findings by matching their root causes.
- Preserve and utilize the stable kebab-case IDs generated by the source agents for each consolidated finding group. DO NOT generate new IDs.
- Merge the 'checks_that_passed' lists from all agents, removing duplicates, into 'merged_checks_that_passed'.
- Determine the first domino: the id of the earliest confirmed-looking finding that invalidates the steps after it, or null.
- Act as an additional validator: evaluate each consolidated finding and determine whether it represents a genuine issue in the plan. Set the 'validated_by_synthesis' field to true if you verify it is a valid issue, or false if you reject it.

Your output MUST be a JSON object with this exact structure:
{
  "consolidated_findings": [
    {
      "id": "stable-kebab-case-id-from-source",
      "step": "the plan step this concerns",
      "category": "ordering|false-assumption|unverifiable|no-rollback|missing-migration|hidden-coupling|other",
      "failure": "the concrete scenario in which the plan breaks",
      "evidence": "verbatim plan text proving it",
      "confidence": "high|medium|low",
      "severity": "high|medium|low",
      "fix": "the concrete change to the plan that prevents the failure",
      "sources": ["agent-1", "agent-2", "agent-3"],
      "validated_by_synthesis": true
    }
  ],
  "merged_checks_that_passed": [
    "verified-check-1",
    "verified-check-2"
  ],
  "first_domino": "stable-kebab-case-id-or-null"
}
"""


@dataclass(frozen=True)
class StageSpec:
    stage: str                                   # "spec" | "plan"
    skill_name: str                              # skill wrapper name, also stripped from argv
    report_basename: str                         # e.g. "geap-spec-validation"
    report_title: str                            # report H1 prefix
    agent_labels: tuple                          # 3 human-readable lens names
    agent_prompts: tuple                         # 3 system instructions
    finding_required_keys: tuple                 # per-finding schema keys agents must emit
    match_field: str                             # fuzzy-fallback field for vote matching
    no_hole_key: str                             # agents' top-level "nothing found here" key
    no_hole_heading: str                         # report section heading for the above
    has_first_domino: bool
    synthesis_prompt: str
    synthesis_required_keys: tuple               # synthesis top-level keys
    synthesis_merge_key: str                     # synthesis merged no-hole key
    synthesis_finding_required_keys: tuple       # consolidated-finding schema keys


SPEC_STAGE = StageSpec(
    stage="spec",
    skill_name="geap-spec-validator",
    report_basename="geap-spec-validation",
    report_title="Spec Adversarial Review",
    agent_labels=(
        "Ambiguity & Malicious-Compliance Skeptic",
        "Logic & Boundary Skeptic",
        "Completeness & Testability Skeptic",
    ),
    agent_prompts=(
        SPEC_AGENT_1_INSTRUCTIONS,
        SPEC_AGENT_2_INSTRUCTIONS,
        SPEC_AGENT_3_INSTRUCTIONS,
    ),
    finding_required_keys=("id", "clause", "severity", "interpretation", "harm", "tightening"),
    match_field="clause",
    no_hole_key="failed_attacks",
    no_hole_heading="Attacks That Failed",
    has_first_domino=False,
    synthesis_prompt=SPEC_SYNTHESIS_PROMPT,
    synthesis_required_keys=("consolidated_findings", "merged_failed_attacks"),
    synthesis_merge_key="merged_failed_attacks",
    synthesis_finding_required_keys=(
        "id", "clause", "severity", "interpretation", "harm", "tightening", "validated_by_synthesis",
    ),
)

PLAN_STAGE = StageSpec(
    stage="plan",
    skill_name="geap-plan-validator",
    report_basename="geap-plan-validation",
    report_title="Plan Adversarial Review",
    agent_labels=(
        "Dependency & Ordering Skeptic",
        "Hidden-Assumption Skeptic",
        "Integration & Failure-Mode Skeptic",
    ),
    agent_prompts=(
        PLAN_AGENT_1_INSTRUCTIONS,
        PLAN_AGENT_2_INSTRUCTIONS,
        PLAN_AGENT_3_INSTRUCTIONS,
    ),
    finding_required_keys=("id", "step", "category", "failure", "evidence", "confidence", "severity", "fix"),
    match_field="evidence",
    no_hole_key="checks_that_passed",
    no_hole_heading="Checks That Passed",
    has_first_domino=True,
    synthesis_prompt=PLAN_SYNTHESIS_PROMPT,
    synthesis_required_keys=("consolidated_findings", "merged_checks_that_passed"),
    synthesis_merge_key="merged_checks_that_passed",
    # confidence intentionally omitted: synthesis need not re-emit it
    synthesis_finding_required_keys=(
        "id", "step", "category", "failure", "evidence", "severity", "fix", "validated_by_synthesis",
    ),
)
