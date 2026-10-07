# `html-product-owner` · author mode

Read this file **only in author mode** (no `spec.md` exists yet, or the supervisor dispatched you instead of `product-owner` / `visual-product-owner`). Render-only runs never need it. The phases and both templates are the same as `product-owner`'s — downstream skills (`spec-validator`, `spec-deliberator`, `architect`, `html-architect`) depend on the exact structure.

## Phase 1: Strategic Alignment & Roadmap Evaluation
1.  **Ingest Context:** Read the Context Report (`plans/research/*.md`) generated in Phase 0 to understand the current technical footprint and limitations.
2.  **Evaluate Backlog:** Read `plans/00-ROADMAP.md`. If it does not exist, initialize it (structure below).

## Phase 2: The Grill Loop (Interactive Interview)
For any non-trivial request:
1.  **Formulate Questions:** Identify the "known unknowns" (e.g., "What happens if the API is offline?", "What are the validation limits on the username field?").
2.  **Socratic Grilling:** Ask the user targeted, Socratic questions. Do not ask more than 3 questions at a time to prevent cognitive overload.
3.  **Refine:** Use the user's answers to clarify the requirements. Repeat until you have a rock-solid, unambiguous understanding of the goal. Keep a list of every question you asked that was answered with "ask X", "not sure", or silence — those are the **residual unknowns** and they go on the page as decisions.

## Phase 3: Spec & Roadmap Deliverables
Once grilling is complete, generate the following artifacts.

### 1. The Specification: `plans/active_milestones/{moniker}/spec.md`
Must follow this **exact structure**:
```markdown
# Product Specification: [Feature Name]

## 🎯 Executive Summary
*   **Goal:** [One sentence explaining what we are building]
*   **Target User:** [The persona/role this benefits]
*   **Business Value:** [Why this matters / ROI]

## 🛠️ User Stories & Workflows
*Detailed narrative from the user's perspective.*
- **As a** [user role], **I want to** [action] **so that** [benefit].

## 📋 Acceptance Criteria
*CRITICAL: Must be written in Gherkin (Given-When-Then) syntax or as unambiguous, measurable business rules. No hand-waving.*
- **Scenario:** [Name]
  - **Given** [precondition]
  - **When** [action]
  - **Then** [expected result]

## 🚨 Constraints & Edge Cases
- [e.g., Maximum file size is 5MB]
- [e.g., Error handling behavior for timeout]

## 🎨 UI/UX Mockups (If applicable)
- [Textual or Mermaid-based layout descriptions]
```
Residual unknowns from the Grill Loop go under `## 🚨 Constraints & Edge Cases` as an `**Open Questions:**` list, each item stating the question, the options, and the answer you recommend. This is the same place the append-first rule writes to in render-only mode, so the page always has a line in `spec.md` to point at.

### 2. Roadmap Update: `plans/00-ROADMAP.md`
Mark the new feature as a "Milestone" under the active or upcoming release target. The roadmap must strictly follow this structure:
```markdown
# Swarm Master Roadmap

## 📦 Release v1.0.0 (Target Date: [Date]) - STATUS: ACTIVE
- [ ] **Milestone 1: [Name]** - STATUS: [PENDING / ACTIVE / COMPLETED]
  - *Description:* [Summary]
  - *Spec:* `plans/active_milestones/{moniker}/spec.md`
- [ ] **Milestone 2: [Name]** - STATUS: PENDING

## 📦 Release v1.1.0 (Target Date: [Date]) - STATUS: PENDING
- [ ] **Milestone 3: [Name]** - STATUS: PENDING
```

When `spec.md` and the roadmap are complete, return to the SKILL's **Rendering Protocol**.
