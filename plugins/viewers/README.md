# `viewers` Plugin Skills

Visualization and telemetry viewer skills for **Google Antigravity CLI (AGY CLI)**.

## Included Skills

### `teamwork-trajectory` — Swarm Trajectory & Timing Dashboard
Reads **AGY live telemetry** (`~/.gemini/antigravity-cli/conversation_summaries.db` and `brain/<id>/.system_generated/logs/transcript*.jsonl`, with fallback to legacy `.agents/<role>/BRIEFING.md` and `handoff.md` directories) and compiles a self-contained, dark-mode HTML dashboard at `.agents/trajectory.html`.

- **Wall-Clock & Timing Telemetry:** Run wall-clock span, active wall-clock time (merged turns excluding human pauses), cumulative subagent time, parallelism speedup, peak concurrency, and per-round timing tables.
- **Interactive Gantt Waterfall:** Toggleable **Compressed Pauses** vs. **True Wall-Clock** view, depth-indented subagent tree, model badges, and click-to-jump cards.
- **Triggers:** `"generate trajectory"`, `"visualize teamwork"`, `"trace agents"`, `"update trajectory dashboard"`, `"agent timing"`, `"wall clock trajectory"`.

### `boost-trajectory` — `/boost` 3-Tier Execution Trajectory Dashboard
Reads **AGY live telemetry** (`~/.gemini/antigravity-cli/conversation_summaries.db` and `brain/<id>/.system_generated/logs/transcript*.jsonl`) after a `/boost` command finishes and compiles a self-contained, dark-mode HTML dashboard at `.agents/boost-trajectory.html`.

- **3-Tier `/boost` Hierarchy & Routines:** Visualizes both **Delegation** (`Orchestrator` → `DeepCoder` / `DeepInvestigator` → `*WorkerL0` / `*ImprovementWorker`) and **Solo** `/boost` runs, auto-preferring Delegation runs.
- **Invocation Scoping:** Defaults to the **latest `/boost` invocation** in mixed/multi-`/boost` root conversations; pass `--all-invocations` (or `--full-session`) to render every `/boost` invocation grouped as separate pipelines.
- **Structured `send_message` Report Cards & Models:** Extracts `PLANNER_RESPONSE` / `<USER_SETTINGS_CHANGE>` model badges, `Skepticism Disclaimer` warning callouts, `Known Issues` severity pills, and collapsible Markdown report sections alongside a toggleable Gantt waterfall and worker concurrency metrics.
- **Triggers:** `"boost trajectory"`, `"visualize boost"`, `"trace boost"`, `"update boost trajectory"`, `"boost timeline"`, `"boost report"`.

---

## Installation

### 1. Install as an AGY Plugin (Recommended)

#### From a Local Clone / Folder
From the repository root:

```bash
agy plugin validate ./plugins/viewers
agy plugin install ./plugins/viewers
agy plugin list
```

If `viewers` is already installed and you want to refresh it from your local changes:

```bash
agy plugin uninstall viewers && agy plugin install ./plugins/viewers
```

#### From the GitHub Repository
Clone the repository and install the `viewers` plugin directory:

```bash
git clone https://github.com/ddobrin/plan-skills.git
cd plan-skills
agy plugin validate ./plugins/viewers
agy plugin install ./plugins/viewers
```

### 2. Install as Loose Skills (Optional)
Each skill folder under `plugins/viewers/skills/` is self-contained. To install globally or per-project without the plugin wrapper, copy the entire skill directories (`cp -R`):

```bash
# Global loose install
mkdir -p "$HOME/.gemini/config/skills"
for d in plugins/viewers/skills/*/; do
  name=$(basename "$d")
  rm -rf "$HOME/.gemini/config/skills/$name"
  cp -R "$d" "$HOME/.gemini/config/skills/$name"
done

# Or project-scoped loose install
mkdir -p ".agents/skills"
for d in plugins/viewers/skills/*/; do
  name=$(basename "$d")
  rm -rf ".agents/skills/$name"
  cp -R "$d" ".agents/skills/$name"
done
```

---

## Usage

### `teamwork-trajectory`
From any project workspace:

```bash
# Auto-select the newest multi-agent AGY run in the current workspace
python3 ~/.gemini/config/plugins/viewers/skills/teamwork-trajectory/generator.py

# List matching AGY runs for the current workspace
python3 ~/.gemini/config/plugins/viewers/skills/teamwork-trajectory/generator.py --list

# Render a specific conversation ID (full UUID or unique prefix)
python3 ~/.gemini/config/plugins/viewers/skills/teamwork-trajectory/generator.py -c <conv-id> -o .agents/trajectory.html
```

### `boost-trajectory`
From any project workspace:

```bash
# Auto-select latest /boost run (prefers Delegation, scopes to latest invocation)
python3 ~/.gemini/config/plugins/viewers/skills/boost-trajectory/generator.py

# List matching /boost AGY runs for the current workspace
python3 ~/.gemini/config/plugins/viewers/skills/boost-trajectory/generator.py --list

# Render all /boost invocations in a mixed/multi-/boost conversation
python3 ~/.gemini/config/plugins/viewers/skills/boost-trajectory/generator.py --all-invocations

# Render a specific conversation ID (full UUID or unique prefix) to a custom path
python3 ~/.gemini/config/plugins/viewers/skills/boost-trajectory/generator.py -c <conv-id> -o .agents/boost-trajectory.html
```

## Tests

Run all `viewers` skill test suites from the repository root:

```bash
python3 -B -m unittest discover -s plugins/viewers/skills/teamwork-trajectory/tests -v
python3 -B -m unittest discover -s plugins/viewers/skills/boost-trajectory/tests -v
```
