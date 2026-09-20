#!/usr/bin/env bash
set -euo pipefail

# Default values
SCOPE="global"
SOURCE_MODE="auto"
REPO_URL="https://github.com/ddobrin/plan-skills.git"
BRANCH="main"
CONFIG_DIR="${GEMINI_CONFIG_DIR:-$HOME/.gemini/config}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Install the 13 self-contained reasoning subagents into ~/.gemini/config/agents
(global scope) or ./.agents/agents (project scope).

Options:
  -g, --global            Install globally to ~/.gemini/config/agents (default)
  -p, --project           Install to current project's ./.agents/agents
      --config-dir <dir>  Override global config directory (default: ~/.gemini/config)
      --local             Install from the local repository checkout
      --remote            Clone from remote Git repository before installing
  -b, --branch <name>     Git branch or tag to clone in remote mode (default: main)
  -r, --repo <url>        Git repository URL to clone in remote mode
  -h, --help              Show this help message and exit
EOF
  exit 0
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    -g|--global)
      SCOPE="global"
      shift
      ;;
    -p|--project)
      SCOPE="project"
      shift
      ;;
    --config-dir)
      if [[ -n "${2:-}" ]]; then
        CONFIG_DIR="$2"
        shift 2
      else
        echo "Error: --config-dir requires a directory path." >&2
        exit 1
      fi
      ;;
    --local)
      SOURCE_MODE="local"
      shift
      ;;
    --remote)
      SOURCE_MODE="remote"
      shift
      ;;
    -b|--branch)
      if [[ -n "${2:-}" ]]; then
        BRANCH="$2"
        SOURCE_MODE="remote"
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

# Resolve destination directory
if [[ "$SCOPE" == "global" ]]; then
  DEST_DIR="${CONFIG_DIR}/agents"
else
  DEST_DIR="$(pwd)/.agents/agents"
fi

# Determine source repository root (local checkout vs remote git clone)
SCRIPT_PATH="${BASH_SOURCE[0]:-}"
LOCAL_REPO_ROOT=""
if [[ -n "$SCRIPT_PATH" && -f "$SCRIPT_PATH" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
  CANDIDATE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
  if [[ -d "${CANDIDATE_ROOT}/plugins/plan/agents" || -d "${CANDIDATE_ROOT}/agents" ]]; then
    LOCAL_REPO_ROOT="$CANDIDATE_ROOT"
  fi
fi

TMP_DIR=""
cleanup() {
  if [[ -n "$TMP_DIR" && -d "$TMP_DIR" ]]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT

if [[ "$SOURCE_MODE" == "auto" ]]; then
  if [[ -n "$LOCAL_REPO_ROOT" ]]; then
    SOURCE_MODE="local"
  else
    SOURCE_MODE="remote"
  fi
fi

if [[ "$SOURCE_MODE" == "local" ]]; then
  if [[ -z "$LOCAL_REPO_ROOT" ]]; then
    echo "Error: Could not locate local repository root relative to script." >&2
    exit 1
  fi
  SOURCE_ROOT="$LOCAL_REPO_ROOT"
  echo "Using local repository source: $SOURCE_ROOT"
else
  if ! command -v git >/dev/null 2>&1; then
    echo "Error: 'git' command not found in PATH." >&2
    exit 1
  fi
  TMP_DIR="$(mktemp -d)"
  echo "Cloning '$REPO_URL' (branch: '$BRANCH')..."
  if ! git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$TMP_DIR/repo" >/dev/null 2>&1; then
    echo "Error: Failed to clone repository '$REPO_URL' (branch '$BRANCH')." >&2
    exit 1
  fi
  SOURCE_ROOT="$TMP_DIR/repo"
fi

# Prefer plugins/plan/agents if present, otherwise root agents/
if [[ -d "${SOURCE_ROOT}/plugins/plan/agents" ]]; then
  AGENTS_SRC="${SOURCE_ROOT}/plugins/plan/agents"
elif [[ -d "${SOURCE_ROOT}/agents" ]]; then
  AGENTS_SRC="${SOURCE_ROOT}/agents"
else
  echo "Error: No 'agents/' directory found in '$SOURCE_ROOT'." >&2
  exit 1
fi

mkdir -p "$DEST_DIR"
echo "Installing subagents to: $DEST_DIR ($SCOPE scope)"

INSTALLED_COUNT=0
INSTALLED_NAMES=()
for agent_dir in "$AGENTS_SRC"/*/; do
  [[ -d "$agent_dir" ]] || continue
  agent_name="$(basename "$agent_dir")"
  [[ "$agent_name" == .* ]] && continue
  if [[ -f "${agent_dir}/agent.md" ]]; then
    rm -rf "${DEST_DIR:?}/${agent_name}"
    cp -R "$agent_dir" "${DEST_DIR}/${agent_name}"
    find "${DEST_DIR}/${agent_name}" \( -name "__pycache__" -o -name "*.pyc" -o -name "*.pyo" \) -exec rm -rf {} + 2>/dev/null || true
    INSTALLED_NAMES+=("$agent_name")
    INSTALLED_COUNT=$((INSTALLED_COUNT + 1))
  fi
done

if [[ -f "${AGENTS_SRC}/README.md" ]]; then
  cp "${AGENTS_SRC}/README.md" "${DEST_DIR}/README.md"
fi
if [[ -f "${AGENTS_SRC}/README.html" ]]; then
  cp "${AGENTS_SRC}/README.html" "${DEST_DIR}/README.html"
fi
rm -f "${DEST_DIR}/README.HTML"

if [[ "$INSTALLED_COUNT" -eq 0 ]]; then
  echo "Error: No valid subagent directories (containing agent.md) found in '$AGENTS_SRC'." >&2
  exit 1
fi

echo "Installed ${INSTALLED_COUNT} subagents into ${DEST_DIR}:"
printf "  - %s\n" "${INSTALLED_NAMES[@]}"

# Validate installed subagents if graph.py is available
GRAPH_PY="${SOURCE_ROOT}/plugins/plan/lib/graph/graph.py"
if [[ -f "$GRAPH_PY" ]] && command -v python3 >/dev/null 2>&1; then
  echo "Validating installed subagents against swarm graph contracts..."
  python3 "$GRAPH_PY" validate-agents --agents-dir "$DEST_DIR"
fi

echo "Subagents installation completed successfully!"
