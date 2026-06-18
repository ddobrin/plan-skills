---
name: research
description: Use when a new feature, bug, or refactor request arrives and no context report yet exists for it in plans/research/ — before any spec is written, to map the affected codebase domain, existing patterns, dependencies, and constraints. Symptoms - "investigate before we plan", "scope this out", starting a brand-new milestone, supervisor Phase 0.
---

# Phase 0 — Research

## Overview
Investigate the codebase area the request touches and produce a **Context Report** that grounds every
later phase. This phase performs investigation directly with built-in read/search tools — there is no
specialist plan skill for it. **Read-only**: you change no source files and write no spec or plan.

## Precondition
A user request exists, and **no context report in `plans/research/` already covers it**. (Supervisor →
Contract 1 for paths.)

## Inputs
- The user's raw request.
- The repository itself (read/grep/glob).

## Steps
1. **Derive a topic slug** from the request (e.g. an OAuth request → `oauth`). The report path is
   `plans/research/{topic}_context.md`.
2. **Investigate — no guessing.** Use read/grep/glob to find the affected files, the established
   architectural patterns, the dependencies/services involved, existing tests in the area, and any
   constraints. Cite **real file paths**; do not infer behavior from filenames alone.
3. **Write the Context Report** to `plans/research/{topic}_context.md` using this structure:
   ```markdown
   # Context Report: {topic}

   ## Affected Domain
   What part of the system this request touches (modules, layers, entry points).

   ## Existing Patterns
   The conventions any change here must follow (with file:path evidence).

   ## Dependencies & Integration Points
   Libraries, services, and callers that fan out from this area.

   ## Existing Tests
   What tests cover this area today (paths), and obvious coverage gaps.

   ## Constraints & Risks
   Hard limits, compatibility concerns, and likely failure modes.

   ## Key Files
   The specific paths a spec author / planner will need.
   ```

## Exit Gate
`plans/research/{topic}_context.md` exists and references **real** files and patterns (not speculation).

## Hand-off
`discovery` reads `plans/research/{topic}_context.md` and feeds it to `product-owner`.

## Constraints
- **READ-ONLY codebase** — never edit, create, or delete source files.
- **No spec, no plan** — you only produce the Context Report. Authoring belongs to later phases.
- **Evidence over assumption** — every claim cites a path you actually read.

## Red Flags
| Thought | Reality |
|---|---|
| "I roughly know this codebase, I'll skip reading." | Blind research poisons every later phase. Open the files. |
| "I'll note what to build while I'm here." | That's the spec — `product-owner`'s job. Stay read-only. |
| "Filenames tell me enough." | Names lie. Cite real `file:line` evidence. |
