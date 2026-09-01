#!/usr/bin/env bash
set -euo pipefail

# Default configuration
REPO="${REPO:-https://github.com/ddobrin/plan-skills.git}"
BRANCH="${BRANCH:-plan-graph}"
TARGET="global"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Install Antigravity custom subagents from a specific GitHub repository and branch.

Options:
  -b, --branch <branch>   Git branch to install from (default: $BRANCH)
  -r, --repo <url>        Git repository URL (default: $REPO)
  -p, --project           Install project-scoped (.agents/agents) instead of global (~/.gemini/config/agents)
  -g, --global            Install globally into ~/.gemini/config/agents (default)
  -h, --help              Show this help message

Environment variables:
  BRANCH                  Alternative way to set default branch
  REPO                    Alternative way to set default repo URL

Examples:
  $(basename "$0")
  $(basename "$0") --branch main
  $(basename "$0") --project
  $(basename "$0") --branch feat/custom-agent --project
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

# Setup temporary directory and ensure cleanup
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo "==> Cloning $REPO (branch: $BRANCH)..."
git clone --depth 1 --branch "$BRANCH" "$REPO" "$TMP_DIR" --quiet

if [[ "$TARGET" == "global" ]]; then
  DEST_DIR="$HOME/.gemini/config/agents"
  echo "==> Installing agents globally to $DEST_DIR..."
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
  echo "==> Installing agents project-scoped to $DEST_DIR..."
  mkdir -p "$DEST_DIR"
  for d in "$TMP_DIR"/agents/*/; do
    [[ -d "$d" ]] || continue
    name=$(basename "$d")
    rm -rf "$DEST_DIR/$name"
    cp -R "$TMP_DIR/agents/$name" "$DEST_DIR/$name"
    echo "  ✔ $name"
  done
fi

echo "==> Successfully installed subagents to $DEST_DIR!"
echo "    Run 'agy agents' to verify."
