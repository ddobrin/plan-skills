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
