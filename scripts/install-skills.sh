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

Install the 'plan' and 'orchestrator' plugins (skills, bundled subagents, and
topology tools) directly into ~/.gemini/config/plugins and enable them in
~/.gemini/config/config.json.

Options:
  -g, --global              Install globally to ~/.gemini/config (default)
  -p, --project             Install to current project's ./.agents/plugins
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
    --standalone-skills)
      STANDALONE_SKILLS=true
      shift
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

# Determine source repository root (local checkout vs remote git clone)
SCRIPT_PATH="${BASH_SOURCE[0]:-}"
LOCAL_REPO_ROOT=""
if [[ -n "$SCRIPT_PATH" && -f "$SCRIPT_PATH" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
  CANDIDATE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
  if [[ -d "${CANDIDATE_ROOT}/plugins/plan" ]]; then
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

if [[ ! -d "${SOURCE_ROOT}/plugins" ]]; then
  echo "Error: 'plugins/' directory not found in '$SOURCE_ROOT'." >&2
  exit 1
fi

if [[ "$SCOPE" == "global" ]]; then
  PLUGINS_DEST="${CONFIG_DIR}/plugins"
  SKILLS_DEST="${CONFIG_DIR}/skills"
  CONFIG_JSON="${CONFIG_DIR}/config.json"
else
  PLUGINS_DEST="$(pwd)/.agents/plugins"
  SKILLS_DEST="$(pwd)/.agents/skills"
  CONFIG_JSON=""
fi

mkdir -p "$PLUGINS_DEST"
echo "Installing plugins to: $PLUGINS_DEST ($SCOPE scope)"

INSTALLED_PLUGINS=()
TOTAL_SKILLS=0

for plugin_dir in "${SOURCE_ROOT}/plugins"/*/; do
  [[ -d "$plugin_dir" ]] || continue
  plugin_name="$(basename "$plugin_dir")"
  [[ "$plugin_name" == .* ]] && continue

  if [[ -f "${plugin_dir}/plugin.json" || -d "${plugin_dir}/skills" ]]; then
    target_plugin_dir="${PLUGINS_DEST}/${plugin_name}"
    rm -rf "$target_plugin_dir"
    cp -R "$plugin_dir" "$target_plugin_dir"

    # If installing 'plan' plugin and root agents/ exists while bundled agents/ was missing, ensure bundled agents/ is populated
    if [[ "$plugin_name" == "plan" && ! -d "${target_plugin_dir}/agents" && -d "${SOURCE_ROOT}/agents" ]]; then
      cp -R "${SOURCE_ROOT}/agents" "${target_plugin_dir}/agents"
    fi

    # Strip Python bytecode caches from installed plugin directory
    find "$target_plugin_dir" \( -name "__pycache__" -o -name "*.pyc" -o -name "*.pyo" \) -exec rm -rf {} + 2>/dev/null || true

    skill_count=0
    if [[ -d "${target_plugin_dir}/skills" ]]; then
      for sdir in "${target_plugin_dir}/skills"/*/; do
        [[ -d "$sdir" && -f "${sdir}/SKILL.md" ]] && skill_count=$((skill_count + 1))
      done
    fi
    TOTAL_SKILLS=$((TOTAL_SKILLS + skill_count))
    INSTALLED_PLUGINS+=("$plugin_name")
    echo "  - Installed plugin '${plugin_name}' (${skill_count} skills) -> ${target_plugin_dir}"

    if [[ "$STANDALONE_SKILLS" == "true" && -d "${target_plugin_dir}/skills" ]]; then
      mkdir -p "$SKILLS_DEST"
      for sdir in "${target_plugin_dir}/skills"/*/; do
        [[ -d "$sdir" && -f "${sdir}/SKILL.md" ]] || continue
        sname="$(basename "$sdir")"
        rm -rf "${SKILLS_DEST:?}/${sname}"
        cp -R "$sdir" "${SKILLS_DEST}/${sname}"
      done
    fi
  fi
done

if [[ "${#INSTALLED_PLUGINS[@]}" -eq 0 ]]; then
  echo "Error: No valid plugins found in '${SOURCE_ROOT}/plugins'." >&2
  exit 1
fi

# Enable installed plugins in ~/.gemini/config/config.json (global scope)
if [[ -n "$CONFIG_JSON" ]] && command -v python3 >/dev/null 2>&1; then
  python3 - "$CONFIG_JSON" "${INSTALLED_PLUGINS[@]}" <<'PYEOF'
import json
import os
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
plugin_names = sys.argv[2:]

config_path.parent.mkdir(parents=True, exist_ok=True)
data = {}
orig_mode = 0o600

if config_path.is_file():
    try:
        orig_mode = config_path.stat().st_mode & 0o777
        raw = config_path.read_text(encoding="utf-8").strip()
        if raw:
            data = json.loads(raw)
    except Exception as exc:
        print(f"Warning: Could not parse existing {config_path}: {exc}", file=sys.stderr)
        data = {}

if not isinstance(data, dict):
    data = {}

plugins_map = data.get("plugins")
if not isinstance(plugins_map, dict):
    plugins_map = {}
    data["plugins"] = plugins_map

for name in plugin_names:
    entry = plugins_map.get(name)
    if not isinstance(entry, dict):
        entry = {}
    entry["enabled"] = True
    plugins_map[name] = entry

tmp_path = config_path.with_suffix(".json.tmp")
tmp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
os.chmod(tmp_path, orig_mode)
tmp_path.replace(config_path)
print(f"Enabled plugins {plugin_names} in {config_path}")
PYEOF
fi

# Validate installed plan plugin topology
INSTALLED_GRAPH_PY="${PLUGINS_DEST}/plan/lib/graph/graph.py"
if [[ -f "$INSTALLED_GRAPH_PY" ]] && command -v python3 >/dev/null 2>&1; then
  echo "Validating installed plan plugin topology..."
  if [[ -d "${PLUGINS_DEST}/plan/agents" ]]; then
    python3 "$INSTALLED_GRAPH_PY" validate --agents-dir "${PLUGINS_DEST}/plan/agents"
  else
    python3 "$INSTALLED_GRAPH_PY" validate
  fi
fi

echo "Skills and plugins installation completed successfully (${TOTAL_SKILLS} skills across ${#INSTALLED_PLUGINS[@]} plugins)!"
