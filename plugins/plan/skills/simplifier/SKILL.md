---
name: simplifier
description: Use when existing code works but is hard to read, to reduce its complexity without changing what it does. Cuts nesting, redundant abstraction, and cognitive load while preserving every behavior, output, and side effect. Symptoms - "simplify this code", "refactor for clarity", "clean up this file", "this function is hard to follow", a working implementation that reviewers keep stumbling over.
---

# Simplification

## Overview

Make code easier to read without making it do anything different. Code is read far more
often than it is written, and the cost of a confusing function is paid by everyone who
touches it afterwards.

**Announce at start:** "I'm using the simplifier skill to clarify {target} without changing behavior."

## When to Use

- Code that works and is tested, but is hard to follow.
- A file with deep nesting, tangled conditionals, or abstractions that no longer earn their
  indirection.

## When NOT to Use

- The code is broken — fix it first; simplifying around a bug hides it.
- The code is untested. Without tests you cannot demonstrate you preserved behavior, so
  characterize it first (see `engineer`).

## Core Contract

1. **Zero regression.** Every feature, output, side effect, and error path behaves exactly as
   before. You change *how*, never *what*.
2. **Match the surrounding code.** Follow the conventions already in the files you are
   editing — naming, comment density, structure, idiom. Check `CLAUDE.md` for anything the
   code alone wouldn't tell you.
3. **Simpler to read, not shorter to print.** A change that reduces line count but takes
   longer to understand is not a simplification. Preserve type safety and the structure that
   makes future change possible.

## Process

1. **Read the target and its neighbors.** Establish what the code does and what conventions
   the module follows.
2. **Find the real cost centers** — deep nesting, long parameter threading, duplicated
   branches, conditionals that could be early returns, abstractions with one caller.
3. **Refactor in small passes**, keeping the build green between them.
4. **Confirm behavior held** by running the existing tests.

## Boundaries

- **No behavior changes**, including error handling and timing-visible side effects.
- **No new features or options.**
- **No unrelated bug fixes.** If simplification exposes a real bug, stop and report it rather
  than folding a fix into a "no behavior change" diff — the two must not travel together.
