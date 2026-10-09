set -e
git init -q -b main
git config user.email eval@example.com
git config user.name Eval
git config commit.gpgsign false
mkdir -p plans/active_milestones/demo src tests
cat > plans/swarm.md <<'MD'
# Swarm configuration (eval fixture)

```json swarm-config
{ "version": 1, "delivery": { "mode": "pr", "host": "github" },
  "tiers": { "critical": { "paths": ["**/auth/**"], "keywords": ["password"] } } }
```
MD
cat > src/calc.py <<'PY'
def add(a, b):
    return a + b
PY
cat > tests/test_calc.py <<'PY'
from src.calc import add

def test_add():
    assert add(2, 3) == 5
PY
cat > AGENTS.md <<'MD'
# AGENTS.md
## Build and test
```bash
python3 -m pytest -q
```
MD
touch src/__init__.py
git add -A
git commit -q --no-verify -m init
git switch -q -c swarm/demo
cat > plans/active_milestones/demo/spec.md <<'MD'
# Product Specification: Fast subtraction

## Acceptance Criteria
- **Scenario:** subtract
  - **Given** two numbers
  - **When** the user subtracts them
  - **Then** the result is returned quickly
MD
git add -A && git commit -q --no-verify -m "docs(demo): spec"
cat > plans/active_milestones/demo/plan.md <<'MD'
# Technical Plan: demo

**Risk tier (proposed):** `routine` (no rule matched)

## Task Execution (Parallel Groups)
### Group 1 (Parallel Execution - Independent Tasks)
- [ ] Task 1.A: add `subtract` → `src/calc.py`

#### Task 1.A
1. **Step 1 (Test):** `tests/test_calc.py`: assert subtract(5, 3) == 2
2. **Step 2 (Implementation):** `src/calc.py`: add `def subtract(a, b): return a - b`
3. **Step 3 (Verification):** run `python3 -m pytest -q`

## Success Criteria
* `python3 -m pytest -q` passes
MD
git add -A && git commit -q --no-verify -m "docs(demo): plan"
