#!/usr/bin/env bash
set -euo pipefail

# Default configuration
REPO="${REPO:-https://github.com/ddobrin/plan-skills.git}"
BRANCH="${BRANCH:-plan-graph}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Install Antigravity planning and orchestrator plugin skills from a specific GitHub repository and branch.

Options:
  -b, --branch <branch>   Git branch to install from (default: $BRANCH)
  -r, --repo <url>        Git repository URL (default: $REPO)
  -h, --help              Show this help message

Environment variables:
  BRANCH                  Alternative way to set default branch
  REPO                    Alternative way to set default repo URL

Examples:
  $(basename "$0")
  $(basename "$0") --branch main
  $(basename "$0") --branch feat/my-skill-update
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

echo "==> Cloning $REPO (branch: $BRANCH)..."
git clone --depth 1 --branch "$BRANCH" "$REPO" "$TMP_DIR" --quiet

echo "==> Installing 'plan' plugin skills via agy CLI..."
agy plugin install "$TMP_DIR/plugins/plan"

echo "==> Installing 'orchestrator' plugin skills via agy CLI..."
agy plugin install "$TMP_DIR/plugins/orchestrator"

echo "==> Successfully installed planning and orchestrator plugin skills!"
echo "    Run 'agy plugin list' to verify."
