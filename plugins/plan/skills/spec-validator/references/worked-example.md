# Worked Example — spec-validator

> Spec excerpt: *"The export endpoint returns the user's records as a downloadable file."*

Three skeptics dispatched. Results after dedup + majority gate:

**Confirmed (≥ 2 votes):**

- `format-unspecified` (3 votes, high) — "downloadable file" names no format. Malicious read:
  return an empty `.txt`. Tightening: *"returns a UTF-8 CSV with header row matching the
  schema in §2; one record per row."*
- `no-pagination-limit` (2 votes, high) — no bound on record count. Malicious read: stream
  10M rows, OOM the server. Tightening: *"records exceeding 50k are paginated via `?cursor=`;
  a single response returns ≤ 50k rows."*

**Single vote (triage required):**

- `auth-on-export` (1 vote, medium) — the spec doesn't restate that export honors row-level
  access. Triaged with the author: **intended** — row-level access is enforced globally at the
  data layer per the platform spec, so restating it here would be redundant. Recorded so the
  next reader doesn't re-raise it.

The two confirmed holes get written into the spec before any plan is drafted.
