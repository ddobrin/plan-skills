"""CLI orchestration for the GEAP remote adversarial validator panel.

Skill wrappers call main(STAGE, sys.argv[1:]) with their StageSpec; everything
else — config, preprocessing, the 3-skeptic fan-out, synthesis, quorum, and the
report — is stage-agnostic.
"""

import os
import sys
import argparse
import asyncio
import logging

from .config_loader import load_config
from .client import initialize_clients, CloudInvocationEngine
from .synthesis import run_synthesis_with_fallbacks, compute_votes_and_quorum, compute_first_domino
from .report import resolve_report_path, format_markdown_report

CORE_DIR = os.path.dirname(os.path.abspath(__file__))


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


def strip_cli_prefix(argv: list, skill_name: str) -> list:
    """Strips 'plan' and the skill's own name when invoked as 'agy plan <skill> ...'."""
    args_list = list(argv)
    if args_list and args_list[0] == "plan":
        args_list = args_list[1:]
    if args_list and args_list[0] == skill_name:
        args_list = args_list[1:]
    return args_list


async def main_async(stage, argv: list) -> None:
    parser = argparse.ArgumentParser(
        prog=stage.skill_name,
        description=f"GEAP remote adversarial {stage.stage} validator (3 skeptics + synthesis on Vertex AI)",
    )
    parser.add_argument("--file", required=True, help=f"Path to the {stage.stage} document to validate")
    parser.add_argument("--config", help="Path to the config.json file")
    parser.add_argument("--moniker", help="Milestone moniker override for the report location")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args(strip_cli_prefix(argv, stage.skill_name))

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    # 1. Load configuration
    config_path = args.config or os.path.join(CORE_DIR, "config.json")
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
    from google.auth.exceptions import DefaultCredentialsError
    try:
        credentials, project = initialize_clients(config.get("gcp_project_id"), config.get("gcp_location"))
    except DefaultCredentialsError as e:
        sys.stderr.write(f"Authentication Error: {str(e)}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Initialization Error: {str(e)}\n")
        sys.exit(1)

    # 4. Invoke the skeptic panel in parallel
    engine = CloudInvocationEngine(project, config.get("gcp_location"), credentials, config)
    agent_models = [config["agent_1_model"], config["agent_2_model"], config["agent_3_model"]]

    print(f"Starting {stage.stage} validation of '{args.file}' with skeptics: {', '.join(agent_models)}")
    try:
        agent_outputs = await engine.run_parallel_validation(agent_models, stage, content)
    except Exception as e:
        sys.stderr.write(f"Execution Error: {str(e)}\n")
        sys.exit(1)

    # A failed agent (None) contributes no findings and no notes but keeps its
    # slot so vote sources stay aligned to agent numbers.
    agent_findings = [o.get("findings", []) if o else [] for o in agent_outputs]
    no_hole_notes = []
    for output in agent_outputs:
        if output:
            no_hole_notes.extend(output.get(stage.no_hole_key, []))

    # 5. Synthesis model consolidates and writes the final response
    print("Running synthesis model consolidation...")
    try:
        synthesis_output = await run_synthesis_with_fallbacks(content, agent_findings, config, stage)
    except Exception as e:
        sys.stderr.write(f"Synthesis Error: {str(e)}\n")
        sys.exit(1)

    # 6. Programmatic vote counting and quorum classification
    confirmed, unconfirmed = compute_votes_and_quorum(agent_findings, synthesis_output, stage)

    merged_no_hole = sorted(set(no_hole_notes + list(synthesis_output.get(stage.synthesis_merge_key, []))))

    first_domino = None
    if stage.has_first_domino:
        first_domino = compute_first_domino(agent_outputs, synthesis_output, confirmed)

    # 7. Write the final markdown report to the milestone's adversarial-reviews dir
    report_path, moniker = resolve_report_path(args.file, stage, args.moniker)
    report_content = format_markdown_report(
        stage=stage,
        target_path=args.file,
        moniker=moniker,
        confirmed=confirmed,
        unconfirmed=unconfirmed,
        no_hole_notes=merged_no_hole,
        agent_models=agent_models,
        synthesis_model=config.get("synthesis_model", "claude-fable-5"),
        first_domino=first_domino,
    )
    try:
        report_dir = os.path.dirname(report_path)
        if report_dir:
            os.makedirs(report_dir, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"Report saved to {os.path.abspath(report_path)}")
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


def main(stage, argv: list = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    try:
        asyncio.run(main_async(stage, argv))
    except KeyboardInterrupt:
        sys.stderr.write("Execution interrupted.\n")
        sys.exit(1)
