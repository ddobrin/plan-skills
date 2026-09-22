# Usage Guide: TypeSafe System One Validator Swarm

This repository integrates **TypeSafe System One** models (powered by the **Jev** engine) with Antigravity (`agy`) adversarial validation skills and custom agents.

It replaces brittle string-matching heuristics and expensive LLM voting loops with a **Hybrid System One (TypeSafe Jev) + System Two (LLM Skeptics)** architecture:
- **System Two (LLM Skeptics):** 3 independent, parallel skeptic agents read the artifacts and source code with a default-to-reject posture.
- **System One (TypeSafe Jev):** Fast, deterministic classification, discrete semantic alignment, continuous severity scoring, and cascading risk ranking via [`plugins/plan/tools/typesafe_validator_engine.py`](file:///Users/ddobrin/work/dan/danrepos/agentic/active/plan-skills-main-jev/plugins/plan/tools/typesafe_validator_engine.py).

---

## 1. Environment Setup

Configure your TypeSafe API key in your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
export TYPESAFE_API_KEY="ts_your_api_key_here"
```

### Optional Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `TYPESAFE_API_KEY` | *(empty)* | API key for `https://api.typesafe.ai/v1/systemone`. |
| `TYPESAFE_BASE_URL` | `https://api.typesafe.ai/v1/systemone` | Base API endpoint for System One questions. |
| `TYPESAFE_MODEL` | `jev-latest` | Model identifier to use for TypeSafe questions. |

> [!NOTE]
> **Graceful Offline Fallback:** If `TYPESAFE_API_KEY` is not set or network access is unavailable, the validator engine automatically falls back to deterministic offline heuristics (regex rules, token/Jaccard semantic clustering, and mode voting). Validations will never fail or crash due to an unset key.

---

## 2. Using as Custom Agents in Antigravity (`agy`)

When `plugins/plan` is installed (`agy plugin install ./plugins/plan` or symlinked into `~/.gemini/config/agents/`), you can invoke the agents directly by role or prompt:

### A. Spec Validation (`spec-validator`)
* **When to use:** Right after drafting a milestone spec (before any plan or code is written).
* **How to trigger:**
  ```text
  Validate this spec: plans/active_milestones/01-auth/spec.md
  ```
  *(or switch to the agent via `/agents` → `spec-validator`)*.
* **What TypeSafe Jev does:**
  1. **Pre-flight Sieve (<250ms):** Calls TypeSafe `Noul` questions (`has_untestable_buzzwords`, `missing_error_paths`) to immediately screen the spec for unquantified adjectives ("fast", "user-friendly") and missing 4xx/5xx handling.
  2. **Semantic Dedup:** Rather than failing when skeptics report `unhandled-timeout` vs `missing-network-timeout`, TypeSafe `Choice` groups them by underlying root cause.
  3. **Tail Triage:** Solo catches (1 skeptic vote) are evaluated by TypeSafe's SDE cascade ($P \ge 0.85$ auto-promotes to confirmed; $P < 0.40$ filtered as noise).

---

### B. Plan Validation (`plan-validator`)
* **When to use:** After the architect writes `plan.md`, before any implementation starts.
* **How to trigger:**
  ```text
  Validate the plan at plans/active_milestones/01-auth/plan.md
  ```
* **What TypeSafe Jev does:**
  1. **Pre-flight Sieve:** Detects steps missing explicit test/verification commands or irreversible actions missing rollback.
  2. **Citation Verification:** Checks `file:line` references against the codebase and verifies context support via TypeSafe `Choice`.
  3. **First Domino Ranking:** Evaluates step sequencing against TypeSafe cascading failure impact scores to identify the single earliest step whose failure invalidates subsequent tasks.

---

### C. Implementation Validation (`implementation-validator`)
* **When to use:** After code is written (before merging to `main`).
* **How to trigger:**
  ```text
  Validate this implementation between origin/main and HEAD
  ```
* **What TypeSafe Jev does:**
  1. **Citation Verification against `git diff`:** Verifies line numbers and code context.
  2. **Calibrated Severity Rubric:** Scores defects against a 4-level descriptive ordinal rubric (`critical`, `high`, `medium`, `low`) using TypeSafe `Score`, outputting continuous calibrated scores (e.g., `2.85 / High`) and probability distributions.
  3. **Outputs Report:** Writes `adversarial-reviews/implementation-validation.md` with the severity calibration delta table.

---

## 3. Using as Skills (In Any Pair Programming Session)

You can activate the skills during normal pair programming with Antigravity without changing your active agent role:

```text
Run the spec-validator skill on plans/active_milestones/02-payment/spec.md
```
or
```text
Run the plan-validator skill on my current plan.
```

The orchestrating agent will:
1. Run the TypeSafe pre-flight sieve via [`plugins/plan/tools/typesafe_validator_engine.py`](file:///Users/ddobrin/work/dan/danrepos/agentic/active/plan-skills-main-jev/plugins/plan/tools/typesafe_validator_engine.py).
2. Spawn 3 read-only research subagents in parallel with the skeptic prompt.
3. Pass their outputs to `typesafe_validator_engine.py synthesize` to produce the finalized review.

---

## 4. Direct CLI Usage & CI/CD Automation

The standalone Python CLI tool has **zero third-party dependencies** (uses standard library `urllib.request`, `json`, `dataclasses`, `re`, `argparse`) and can be used in local scripts or CI/CD pipelines.

### Run Pre-Flight Screening
```bash
# Advisory mode (exit code 0; outputs JSON warnings to guide reviewers)
python3 plugins/plan/tools/typesafe_validator_engine.py preflight --stage spec --file plans/active_milestones/01-auth/spec.md

# Strict mode (aborts with exit code 2 if any warnings exist)
python3 plugins/plan/tools/typesafe_validator_engine.py preflight --stage plan --file plans/active_milestones/01-auth/plan.md --strict
```

### Synthesize Skeptic Outputs into a Markdown Review
```bash
python3 plugins/plan/tools/typesafe_validator_engine.py synthesize \
  --stage implementation \
  --target /tmp/current.diff \
  --skeptics /tmp/s1.json /tmp/s2.json /tmp/s3.json \
  --out plans/active_milestones/01-auth/adversarial-reviews/implementation-validation.md
```

### Rank First Domino for a Plan
```bash
python3 plugins/plan/tools/typesafe_validator_engine.py first-domino \
  --plan-file plans/active_milestones/01-auth/plan.md \
  --findings-file /tmp/plan_findings.json
```

---

## 5. Under-the-Hood: TypeSafe Jev Primitives

| Primitive | Operation | Role in Validator Swarm |
| :--- | :--- | :--- |
| **`Choice`** | Multi-class selection with probability distribution | Semantic clustering across divergent skeptic wording; citation support verification (`supports`, `contradicts`, `says_nothing`). |
| **`Noul`** | Binary question returning calibrated $P(\text{True}) \in [0.0, 1.0]$ | Pre-flight screening (untestable buzzwords, missing rollbacks); SDE cascade tail triage for 1-vote solo catches. |
| **`Score`** | Continuous expectation over an ordinal rubric $[1.0, 4.0]$ | Calibrated severity scoring (`critical`=4, `high`=3, `medium`=2, `low`=1); cascading impact scoring for domino ranking. |

---

## 6. Running Automated Tests

A comprehensive unit test suite is included in `plugins/plan/tests/test_typesafe_validator_engine.py`:

```bash
python3 -m unittest plugins/plan/tests/test_typesafe_validator_engine.py -v
```

All 10 unit tests run in sub-second time without requiring network connectivity or third-party packages.
