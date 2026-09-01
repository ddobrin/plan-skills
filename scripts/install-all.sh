#!/usr/bin/env bash
set -euo pipefail

# Default configuration
REPO="${REPO:-https://github.com/ddobrin/plan-skills.git}"
BRANCH="${BRANCH:-plan-graph}"
TARGET="global"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Install BOTH custom subagents and plugin skills from a specific GitHub repository and branch.

Options:
  -b, --branch <branch>   Git branch to install from (default: $BRANCH)
  -r, --repo <url>        Git repository URL (default: $REPO)
  -p, --project           Install agents project-scoped (.agents/agents) instead of global (~/.gemini/config/agents)
  -g, --global            Install agents globally into ~/.gemini/config/agents (default)
  -h, --help              Show this help message

Environment variables:
  BRANCH                  Alternative way to set default branch
  REPO                    Alternative way to set default repo URL

Examples:
  $(basename "$0")
  $(basename "$0") --branch main
  $(basename "$0") --project
EOF
  exit 0
}

# Parse command line options
while [[ $# -gt 0 ]]; do
  case "$1" in
    -b|--branch)
      BRANCH="$2"
      shift 2
      ;;
    -r|--repo)
      REPO="$2"
      shift 2
      ;;
    -p|--project)
      TARGET="project"
      shift
      ;;
    -g|--global)
      TARGET="global"
      shift
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

# Check if agy CLI is available
if ! command -v agy &> /dev/null; then
  echo "Error: 'agy' CLI command not found in PATH." >&2
  echo "Please ensure Antigravity CLI is installed." >&2
  exit 1
fi

# Setup temporary directory and ensure cleanup
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo "================================================================="
echo " Plan Swarm: Installing Agents & Plugin Skills"
echo " Repo:   $REPO"
echo " Branch: $BRANCH"
echo " Scope:  $TARGET (for agents)"
echo "================================================================="

echo "==> Cloning $REPO (branch: $BRANCH)..."
git clone --depth 1 --branch "$BRANCH" "$REPO" "$TMP_DIR" --quiet

# 1. Install Subagents
if [[ "$TARGET" == "global" ]]; then
  DEST_DIR="$HOME/.gemini/config/agents"
  echo "==> [1/3] Installing subagents globally to $DEST_DIR..."
  mkdir -p "$DEST_DIR"
  for d in "$TMP_DIR"/agents/*/; do
    [[ -d "$d" ]] || continue
    name=$(basename "$d")
    rm -rf "$DEST_DIR/$name"
    cp -R "$TMP_DIR/agents/$name" "$DEST_DIR/$name"
    echo "  ✔ $name"
  done
else
  DEST_DIR=".agents/agents"
  echo "==> [1/3] Installing subagents project-scoped to $DEST_DIR..."
  mkdir -p "$DEST_DIR"
  for d in "$TMP_DIR"/agents/*/; do
    [[ -d "$d" ]] || continue
    name=$(basename "$d")
    rm -rf "$DEST_DIR/$name"
    cp -R "$TMP_DIR/agents/$name" "$DEST_DIR/$name"
    echo "  ✔ $name"
  done
fi

# 2. Install Plan Plugin Skills
echo "==> [2/3] Installing 'plan' plugin skills via agy CLI..."
agy plugin install "$TMP_DIR/plugins/plan"

# 3. Install Orchestrator Plugin Skills
echo "==> [3/3] Installing 'orchestrator' plugin skills via agy CLI..."
agy plugin install "$TMP_DIR/plugins/orchestrator"

echo "================================================================="
echo "==> Complete! All agents and plugin skills successfully installed."
echo "    Verify subagents: agy agents"
echo "    Verify plugins:   agy plugin list"
echo "================================================================="
