---
name: release
description: Use when every milestone under the active release in 00-ROADMAP.md is completed and committed — to finalize, tag, and ship the release behind explicit human approval. Symptoms - "ship it", "cut the release", "tag the version", supervisor Phase 4, all milestones in the active release marked COMPLETED.
---

# Phase 4 — Release & Tag

## Overview
Finalize a release: confirm every milestone is done, get explicit approval, create the git tag,
optionally push, and have `product-owner` mark the release **Shipped** and activate the next one.

## Precondition
Every milestone under the **active release** in `plans/00-ROADMAP.md` is `COMPLETED` and committed. See
Supervisor → Contract 1 & Contract 4.

## Inputs
- `plans/00-ROADMAP.md` (release + milestone statuses)

## Steps
1. **Verify completeness.** Read `plans/00-ROADMAP.md` and confirm all milestones under the active
   release are `COMPLETED`. If any is not, return to the Supervisor — you are not in Phase 4 yet.
2. **🛑 Release gate (Supervisor → Contract 4).** Ask the user:
   *"All features for Release `{version}` are complete. Shall I finalize the release and create the git
   tag?"* Do nothing irreversible until they approve.
3. **Tag** (Supervisor is the only git authority):
   ```bash
   git tag -a {version} -m "Release {version}"
   ```
4. **Offer to push:** ask before running `git push --tags`.
5. **Delegate `product-owner`** (Supervisor → Contract 2) to mark the release **Shipped** in
   `plans/00-ROADMAP.md` and **activate the next release**.

## Exit Gate
The tag exists, `00-ROADMAP.md` shows the release as Shipped, and the next release is Active.

## Hand-off
Back to the Supervisor — idle until the next user request restarts the lifecycle at `research`.
(Consider `/swarm:archive` to move completed milestones out of the active context.)

## Constraints
- **Only the Supervisor tags/pushes** — and only after explicit approval.
- **Never tag with incomplete milestones.**
- **Push is opt-in** — always ask before `git push --tags`.

## Red Flags
| Thought | Reality |
|---|---|
| "Most milestones are done, tag it." | Every milestone must be COMPLETED. Partial ≠ shippable. |
| "I'll tag and push in one go." | Tag, then ask separately before pushing. |
| "Tagging done, we're finished." | Have `product-owner` mark Shipped and activate the next release. |
