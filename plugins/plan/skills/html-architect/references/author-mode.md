# `html-architect` · author mode

Read this file **only in author mode** (no `plan.md` exists yet, or the supervisor dispatched you instead of `architect` / `visual-architect`). Render-only runs never need it. The protocol and the `plan.md` template are the same as `architect`'s — downstream skills (`plan-validator`, `plan-deliberator`, `engineer`, `auditor`) depend on the exact structure.

## 1. Investigation Phase
*   **Deep Investigation:** Comprehensively analyze the codebase to understand existing patterns, dependencies, and business logic.
*   **Action:** Use `find_by_name`, `list_dir`, `grep_search`, and `view_file` to map the affected area. Blind planning is forbidden.
*   **Mandatory Questions to Answer Internally:**
    *   Which specific existing files will be modified?
    *   What is the established architectural pattern we must adhere to?
    *   What existing unit/integration tests will this break or require updating?
*   **No Guessing:** If unsure about a system's behavior or a change's impact, investigate until you have empirical evidence. Do NOT rely on file names or directory listings alone.
*   **Record `path:line` as you go.** Every entrypoint, call site and record you will cite on the page needs a real line number. Collect the symbol names while investigating and resolve them all at once, in **one** command, before writing the page:
    ```bash
    grep -nE 'symbolA|symbolB|symbolC' path/one.ext path/two.ext
    ```
    One `grep` per repository, not one per citation.

## 2. Analysis & Reasoning
*   Document findings: What exists? What needs to change? Why?
*   Identify risks, dependencies, and integration points. Decide which risks are **forks the reviewer can decide** (these become `doc-ask`s, 2–5 of them) and which are notes.

## 3. Plan Creation
Create `plans/active_milestones/{moniker}/plan.md` with **exactly** this structure:

```markdown
# Technical Plan: [Milestone Moniker]

## 🔍 Analysis & Context
*   **Objective:** [One sentence summary]
*   **Affected Files:** [List of exact file paths]
*   **Key Dependencies:** [Libraries/Services involved]
*   **Risks/Edge Cases:** [Anticipated challenges based on spec.md]

## 📋 Task Execution (Parallel Groups)
*CRITICAL: Group tasks by dependencies. Tasks within the same group MUST be entirely independent (they must not modify the same files) to allow for safe parallel execution. Group 2 cannot start until Group 1 is complete.*

### Group 1 (Parallel Execution - Independent Tasks)
- [ ] Task 1.A: [Name - explicitly state target file(s)]
- [ ] Task 1.B: [Name - explicitly state target file(s)]

### Group 2 (Sequential Execution - Depends on Group 1)
- [ ] Task 2.A: [Name - explicitly state target file(s)]

## 📝 Step-by-Step Implementation Details
*CRITICAL: Be extremely specific. You MUST include exact file paths, target line numbers (if known), function signatures, and structural code snippets.*

### Prerequisites
[Setup or dependencies]

#### Task [X].[Y] (e.g., Task 1.A)
1.  **Step 1 (The Unit Test Harness):** Define the verification requirement.
    *   *Target File:* `test/Path/To/Test.ext`
    *   *Test Cases to Write:* [List specific assertions]
2.  **Step 2 (The Implementation):** Execute the core change.
    *   *Target File:* `src/Path/To/File.ext`
    *   *Exact Change:* [Specific logic to implement]
3.  **Step 3 (The Verification):** Verify the harness.
    *   *Action:* Run `[specific unit test command]`.

[...Continue for all tasks in all groups...]

### 🧪 Global Testing Strategy
*   **Unit Tests:** [Summary of pure logic to test in isolation]
*   **Integration Tests:** [Summary of cross-boundary flows to verify]

## 🎯 Success Criteria
*   [Definition of Done Condition 1]
*   [Definition of Done Condition 2]
```

Every fork you intend to render as a `doc-ask` must already be a line under **Risks/Edge Cases** (or an `### Open Questions` subsection at the end of Analysis & Context) — the page never carries a decision `plan.md` does not.

When `plan.md` is complete, return to the SKILL's **Rendering Protocol**.
