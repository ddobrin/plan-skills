#!/usr/bin/env bash
set -euo pipefail

# Default values
SCOPE="global"
SOURCE_MODE="auto"
REPO_URL="https://github.com/ddobrin/plan-skills.git"
BRANCH="main"
CONFIG_DIR="${GEMINI_CONFIG_DIR:-$HOME/.gemini/config}"
STANDALONE_SKILLS=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Install all 'plan' and 'orchestrator' plugins, skills, and the 13 custom
reasoning subagents into ~/.gemini/config (or ./.agents for project scope).

Artifacts created in global scope (~/.gemini/config):
  1. ~/.gemini/config/agents/<13 subagents>/agent.md (+ bundled visual assets)
  2. ~/.gemini/config/plugins/plan/ (19 skills including /plan-swarm, 13 subagents, graph.py)
  3. ~/.gemini/config/plugins/orchestrator/ (/orchestrator skill + references)
  4. ~/.gemini/config/config.json (enables 'plan' and 'orchestrator' plugins)

Options:
  -g, --global              Install globally to ~/.gemini/config (default)
  -p, --project             Install subagents and plugins to current project's ./.agents
      --config-dir <dir>    Override global config directory (default: ~/.gemini/config)
      --standalone-skills   Also copy unwrapped skills into ~/.gemini/config/skills
      --local               Install from the local repository checkout
      --remote              Clone from remote Git repository before installing
  -b, --branch <name>       Git branch or tag to clone in remote mode (default: main)
  -r, --repo <url>          Git repository URL to clone in remote mode
  -h, --help                Show this help message and exit
EOF
  exit 0
}

FORWARD_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -g|--global)
      SCOPE="global"
      FORWARD_ARGS+=("$1")
      shift
      ;;
    -p|--project)
      SCOPE="project"
      FORWARD_ARGS+=("$1")
      shift
      ;;
    --config-dir)
      if [[ -n "${2:-}" ]]; then
        CONFIG_DIR="$2"
        FORWARD_ARGS+=("$1" "$2")
        shift 2
      else
        echo "Error: --config-dir requires a directory path." >&2
        exit 1
      fi
      ;;
    --standalone-skills)
      STANDALONE_SKILLS=true
      FORWARD_ARGS+=("$1")
      shift
      ;;
    --local)
      SOURCE_MODE="local"
      FORWARD_ARGS+=("$1")
      shift
      ;;
    --remote)
      SOURCE_MODE="remote"
      FORWARD_ARGS+=("$1")
      shift
      ;;
    -b|--branch)
      if [[ -n "${2:-}" ]]; then
        BRANCH="$2"
        SOURCE_MODE="remote"
        FORWARD_ARGS+=("$1" "$2")
        shift 2
      else
        echo "Error: --branch requires a branch name." >&2
        exit 1
      fi
      ;;
    -r|--repo)
      if [[ -n "${2:-}" ]]; then
        REPO_URL="$2"
        SOURCE_MODE="remote"
        FORWARD_ARGS+=("$1" "$2")
        shift 2
      else
        echo "Error: --repo requires a repository URL." >&2
        exit 1
      fi
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Error: Unknown option '$1'" >&2
      usage
      ;;
  esac
done

SCRIPT_PATH="${BASH_SOURCE[0]:-}"
if [[ -n "$SCRIPT_PATH" && -f "$SCRIPT_PATH" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
else
  SCRIPT_DIR=""
fi

# If invoked via curl | bash (no sibling scripts on disk), clone once and invoke the cloned scripts
TMP_DIR=""
cleanup() {
  if [[ -n "$TMP_DIR" && -d "$TMP_DIR" ]]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT

if [[ -z "$SCRIPT_DIR" || ! -f "${SCRIPT_DIR}/install-agents.sh" || ! -f "${SCRIPT_DIR}/install-skills.sh" ]]; then
  if ! command -v git >/dev/null 2>&1; then
    echo "Error: 'git' command not found in PATH." >&2
    exit 1
  fi
  TMP_DIR="$(mktemp -d)"
  echo "Cloning '$REPO_URL' (branch: '$BRANCH')..."
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$TMP_DIR/repo" >/dev/null 2>&1
  SCRIPT_DIR="${TMP_DIR}/repo/scripts"
  FORWARD_ARGS+=("--local")
fi

echo "=================================================================="
echo "  Plan Swarm & Orchestrator — Unified Installer"
echo "=================================================================="
echo ""
echo "[1/2] Installing Custom Subagents..."
bash "${SCRIPT_DIR}/install-agents.sh" "${FORWARD_ARGS[@]}"
echo ""
echo "[2/2] Installing Plugins & Skills..."
bash "${SCRIPT_DIR}/install-skills.sh" "${FORWARD_ARGS[@]}"
echo ""

if [[ "$SCOPE" == "global" ]]; then
  TARGET_BASE="$CONFIG_DIR"
else
  TARGET_BASE="$(pwd)/.agents"
fi

cat <<EOF
==================================================================
  Installation Complete!
==================================================================
Artifacts installed in: ${TARGET_BASE}
  - Subagents : ${TARGET_BASE}/agents/ (13 self-contained subagents)
  - Plan      : ${TARGET_BASE}/plugins/plan/ (21 skills + 13 bundled subagents)
  - Orch      : ${TARGET_BASE}/plugins/orchestrator/ (6 orchestrator skills)
$(if [[ "$SCOPE" == "global" ]]; then echo "  - Config    : ${TARGET_BASE}/config.json ('plan' & 'orchestrator' enabled)"; fi)

Available Slash Commands in Chat:
  /plan-swarm                Launch or resume the full 4-phase Plan Swarm
  /product-owner             Phase 1: Interactive Grill Loop -> spec.md
  /visual-product-owner      Phase 1: Grill Loop -> spec.md + visual-spec.html
  /spec-deliberator          Phase 1b: Multi-delegate spec deliberation
  /spec-validator            Phase 1c: 3-lens adversarial spec review
  /architect                 Phase 2: Read-only investigation -> plan.md
  /visual-architect          Phase 2: Read-only investigation -> plan.md + visual-plan.html
  /plan-deliberator          Phase 2b: Multi-delegate plan deliberation
  /plan-validator            Phase 2c: 3-lens adversarial plan review
  /engineer                  Phase 3: Strict TDD Red->Green->Refactor execution
  /simplifier                Phase 3b: Behavior-preserving cleanup pass
  /visual-implementation-recap Phase 3c: Self-contained visual-recap.html
  /auditor                   Phase 4a: Static + test verification -> audit.md
  /implementation-validator  Phase 4b: 3-lens adversarial diff review
  /orchestrator              Meta-orchestrator for cross-project decomposition
==================================================================
EOF
