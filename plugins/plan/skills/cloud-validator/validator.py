#!/usr/bin/env python3
import os
import sys
import argparse
import asyncio
import datetime
from google.auth.exceptions import DefaultCredentialsError

# Inject parent skill directory path to make sure local imports succeed
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

from config_loader import load_config
from client import initialize_clients, CloudInvocationEngine
from synthesis import run_synthesis_with_fallbacks, compute_votes_and_quorum

def preprocess_input_file(file_path: str) -> str:
    """Validates existence, empty state, and size boundaries of the input file."""
    if not os.path.exists(file_path):
        raise ValueError(f"Input file not found: {file_path}")
        
    # Check size bounds using os.path.getsize
    file_size = os.path.getsize(file_path)
    if file_size == 0:
        raise ValueError("Input file is empty")
        
    if file_size > 1024 * 1024:
        raise ValueError("Input file size exceeds 1MB limit")
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        raise ValueError(f"Failed to read input file: {e}")
        
    if len(content.strip()) == 0:
        raise ValueError("Input file is empty")
        
    if len(content) > 200000:
        raise ValueError("Input file character count exceeds 200,000 character limit")
        
    return content

def format_markdown_report(target_path: str, confirmed: list, unconfirmed: list, failed_attacks: list, synthesis_model: str, is_plan: bool) -> str:
    """Generates a structured validation markdown report, adapting fields dynamically if target is a plan."""
    status = "Validation Failed" if confirmed else "Passed"
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    lines = []
    lines.append("# Adversarial Cloud Validation Report")
    lines.append("")
    lines.append(f"**Target Document**: `{target_path}`")
    lines.append(f"**Status**: `{status}`")
    lines.append(f"**Models Utilized**: Agent 1: Spec-Skeptic, Agent 2: Logic-Skeptic, Synthesis: {synthesis_model}")
    lines.append(f"**Timestamp**: `{timestamp}`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🔒 Confirmed Findings (≥ 2 Votes)")
    lines.append("")
    
    if not confirmed:
        lines.append("No confirmed findings.")
    else:
        lines.append("These findings have been verified by a majority of the adversarial review panel. They must be resolved before proceeding.")
        lines.append("")
        for finding in confirmed:
            finding_id = finding.get("id")
            severity = finding.get("severity", "unknown").upper()
            votes = finding.get("votes", 2)
            
            lines.append(f"### {finding_id} (Severity: {severity}, Votes: {votes})")
            
            if is_plan:
                evidence = finding.get("evidence") or finding.get("clause") or ""
                interpretation = finding.get("interpretation") or ""
                first_domino = finding.get("first_domino") or finding.get("harm") or ""
                fix = finding.get("fix") or finding.get("tightening") or ""
                
                lines.append(f'* **Evidence**: `"{evidence}"`' if evidence else '* **Evidence**: `<MISSING>`')
                lines.append(f'* **Interpretation**: {interpretation}')
                lines.append(f'* **First Domino**: {first_domino}')
                lines.append(f'* **Fix**: {fix}')
            else:
                clause = finding.get("clause", "")
                interpretation = finding.get("interpretation", "")
                harm = finding.get("harm", "")
                tightening = finding.get("tightening", "")
                
                lines.append(f'* **Clause**: `"{clause}"`' if clause else '* **Clause**: `<MISSING>`')
                lines.append(f'* **Interpretation**: {interpretation}')
                lines.append(f'* **Harm**: {harm}')
                lines.append(f'* **Tightening**: {tightening}')
            lines.append("")
            
    lines.append("---")
    lines.append("")
    lines.append("## ⚠️ Unconfirmed Findings (1 Vote, FYI)")
    lines.append("")
    
    if not unconfirmed:
        lines.append("No unconfirmed findings.")
    else:
        lines.append("These findings were flagged by only one agent. They may point to subtle edge cases or represent false positives. Review them to confirm intent.")
        lines.append("")
        for finding in unconfirmed:
            finding_id = finding.get("id")
            severity = finding.get("severity", "unknown").upper()
            votes = finding.get("votes", 1)
            
            lines.append(f"### {finding_id} (Severity: {severity}, Votes: {votes})")
            
            if is_plan:
                evidence = finding.get("evidence") or finding.get("clause") or ""
                interpretation = finding.get("interpretation") or ""
                first_domino = finding.get("first_domino") or finding.get("harm") or ""
                fix = finding.get("fix") or finding.get("tightening") or ""
                
                lines.append(f'* **Evidence**: `"{evidence}"`' if evidence else '* **Evidence**: `<MISSING>`')
                lines.append(f'* **Interpretation**: {interpretation}')
                lines.append(f'* **First Domino**: {first_domino}')
                lines.append(f'* **Fix**: {fix}')
            else:
                clause = finding.get("clause", "")
                interpretation = finding.get("interpretation", "")
                harm = finding.get("harm", "")
                tightening = finding.get("tightening", "")
                
                lines.append(f'* **Clause**: `"{clause}"`' if clause else '* **Clause**: `<MISSING>`')
                lines.append(f'* **Interpretation**: {interpretation}')
                lines.append(f'* **Harm**: {harm}')
                lines.append(f'* **Tightening**: {tightening}')
            lines.append("")
            
    lines.append("---")
    lines.append("")
    lines.append("## Failed Attacks")
    lines.append("")
    lines.append("The following attack profiles were executed by the agents but yielded no findings:")
    if not failed_attacks:
        lines.append("None")
    else:
        for attack in failed_attacks:
            lines.append(f"- `{attack}`")
            
    return "\n".join(lines)

async def main_async():
    parser = argparse.ArgumentParser(description="Adversarial Cloud Validator CLI")
    parser.add_argument("--file", required=True, help="Path to the document file (spec.md or plan.md) to validate")
    parser.add_argument("--config", help="Path to the config.json file")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    
    # Strip subcommands if run as 'agy plan cloud-validator'
    args_list = sys.argv[1:]
    if args_list and args_list[0] == "plan":
        args_list = args_list[1:]
    if args_list and args_list[0] == "cloud-validator":
        args_list = args_list[1:]
        
    args = parser.parse_args(args_list)
    
    # 1. Load configuration
    config_path = args.config
    if not config_path:
        config_path = os.path.join(SKILL_DIR, "config.json")
        
    try:
        config = load_config(config_path)
    except ValueError as e:
        sys.stderr.write(f"Configuration Error: {str(e)}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Failed to load configuration: {str(e)}\n")
        sys.exit(1)
        
    # 2. Preprocess input document
    try:
        content = preprocess_input_file(args.file)
    except ValueError as e:
        sys.stderr.write(f"Validation Error: {str(e)}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Error reading file: {str(e)}\n")
        sys.exit(1)
        
    # 3. Authenticate and initialize clients
    try:
        credentials, project = initialize_clients(config.get("gcp_project_id"), config.get("gcp_location"))
    except DefaultCredentialsError as e:
        sys.stderr.write(f"Authentication Error: {str(e)}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Initialization Error: {str(e)}\n")
        sys.exit(1)
        
    # 4. Invoke parallel skepticism agents
    engine = CloudInvocationEngine(project, config.get("gcp_location"), credentials, config)
    agent_1_model = config.get("agent_1_model")
    agent_2_model = config.get("agent_2_model")
    
    print(f"Starting parallel validation on '{args.file}' using models: {agent_1_model}, {agent_2_model}")
    try:
        agent_1_out, agent_2_out = await engine.run_parallel_validation(agent_1_model, agent_2_model, content)
    except Exception as e:
        sys.stderr.write(f"Execution Error: {str(e)}\n")
        sys.exit(1)
        
    # Extract findings from successful agent responses
    a1_findings = agent_1_out.get("findings", []) if agent_1_out else []
    a2_findings = agent_2_out.get("findings", []) if agent_2_out else []
    
    a1_failed = agent_1_out.get("failed_attacks", []) if agent_1_out else []
    a2_failed = agent_2_out.get("failed_attacks", []) if agent_2_out else []
    
    # 5. Invoke synthesis models to group and validate
    print("Running synthesis model consolidation...")
    try:
        synthesis_output = await run_synthesis_with_fallbacks(content, a1_findings, a2_findings, config)
    except Exception as e:
        sys.stderr.write(f"Synthesis Error: {str(e)}\n")
        sys.exit(1)
        
    # 6. Perform programmatic vote counting and stable ID mapping
    confirmed, unconfirmed = compute_votes_and_quorum(a1_findings, a2_findings, synthesis_output)
    
    # Compute merged failed attacks list
    synthesis_failed = synthesis_output.get("merged_failed_attacks", [])
    merged_failed = sorted(list(set(a1_failed + a2_failed + synthesis_failed)))
    
    # 7. Write final markdown report
    is_plan = "plan" in os.path.basename(args.file).lower()
    synthesis_model = config.get("synthesis_model", "gemini-3-1-flash-lite")
    
    report_content = format_markdown_report(
        target_path=args.file,
        confirmed=confirmed,
        unconfirmed=unconfirmed,
        failed_attacks=merged_failed,
        synthesis_model=synthesis_model,
        is_plan=is_plan
    )
    
    report_path = "cloud-validation-report.md"
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"Report saved to {report_path}")
    except Exception as e:
        sys.stderr.write(f"Failed to write report file: {str(e)}\n")
        sys.exit(1)
        
    # 8. Exit code policy
    if confirmed:
        print(f"Validation FAILED: {len(confirmed)} confirmed findings found.")
        sys.exit(1)
    else:
        print("Validation PASSED: No confirmed findings found.")
        sys.exit(0)

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        sys.stderr.write("Execution interrupted.\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
