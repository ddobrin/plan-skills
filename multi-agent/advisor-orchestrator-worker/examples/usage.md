# Usage Example: Vector Database Decision Memo

Scenario: pick a vector database for a RAG product. Eight candidates,
one decision memo. Shows waves, both mandatory consults, a FIX, and the
verification ledger.

## Prompt

```
We need to choose a vector DB for our RAG product (50M embeddings,
p95 < 40ms, hybrid search, self-host option required). Candidates:
pgvector, Qdrant, Weaviate, Milvus, Pinecone, Chroma, Vespa,
Elasticsearch. Produce a decision memo. This is too big for one pass —
run the three-tier loop.
```

## 1. Frame

Deliverable: decision memo with one recommendation.
Success criteria: (a) every candidate scored on the same 5 dimensions,
(b) all claims dated and sourced, (c) hard requirements eliminate
candidates explicitly, (d) one recommendation + runner-up with
switching cost, (e) under 2 pages.

## 2. Plan

- Wave 1: 8 parallel research workers, one per candidate, identical
  brief template, read-only.
- Wave 2: 1 worker builds the comparison matrix; 1 worker drafts the
  memo from the matrix (serialized: memo needs matrix).

## 3. Plan review — consult #1

```
Advisor VERDICT: sound decomposition, one gap.
TOP RISKS: (1) research briefs don't pin a date window — workers will
mix 2024 benchmarks with 2026 pricing; (2) no criterion forces
like-for-like deployment mode (managed vs self-host numbers differ).
SPECIFIC FIXES: add "cite source + date, nothing older than 2025-07"
to the brief; score self-hosted mode only.
WHAT TO IGNORE: you don't need a 9th worker for "other candidates" —
the list is fixed.
```

Orchestrator applies both fixes, rejects nothing. `consults 1/5`

## 4. Delegate — Wave 1 (one of 8 briefs)

```
SUBTASK: Research Qdrant for our RAG use case.
INPUTS: requirements — 50M embeddings, p95 < 40ms, hybrid search,
self-host required. Use web search.
CONSTRAINTS: self-hosted mode only; sources dated 2025-07 or later.
ACCEPTANCE CRITERIA:
1. Scores 1-5 on: performance at scale, hybrid search maturity,
   ops burden, ecosystem, cost — each with a sourced, dated citation
2. Explicit pass/fail on each hard requirement
3. Under 300 words
OUTPUT FORMAT: markdown, sections SCORES / HARD REQS / CITATIONS.
```

All 8 dispatched in a single message, run in parallel.
`W1-8:DISPATCHED | consults 1/5 workers 8/20`

## 5. Verify

Seven PASS. Chroma worker cites a 2024 benchmark → FIX, redispatched
with: "Criterion 1 failed: 'performance at scale' citation dated
2024-11; brief requires 2025-07+. Replace or mark unverifiable."
Redispatch returns PASS. `workers 9/20`

## 6. Wave 2 + Synthesize

Matrix worker: PASS. Memo worker: PASS. Orchestrator resolves one
conflict explicitly: Milvus and Qdrant workers scored ops burden with
different assumptions — memo notes it as a footnote, not an average.
`workers 11/20`

## 7. Taste pass — consult #2

```
Advisor VERDICT: conditional pass.
TOP RISKS: (1) memo recommends Qdrant but never states switching cost
from it later — criterion (d) half-met.
SPECIFIC FIXES: add 3 lines: runner-up = pgvector, switching cost low
(both speak standard APIs via the abstraction layer).
WHAT TO IGNORE: prose polish; it's a memo, not a blog post.
```

Applied. Ship. Final: `consults 2/5 workers 11/20`

## Final report includes

The memo, the plan, the ledger (8 research + 2 synthesis subtasks with
verdicts, 1 FIX documented), advisor notes (4 applied, 0 rebutted,
1 ignored-as-advised), remaining risks (Chroma data marked
unverifiable).

## What to notice

- Consult #1 cost ~200 advisor tokens and fixed the briefs BEFORE 8
  workers ran with a dating bug — the whole argument for the pattern.
- The FIX was a redispatch quoting the criterion, not the orchestrator
  patching the data itself.
- Total advisor involvement: 2 consults. Total orchestrator context:
  briefs, 11 short summaries, 2 verdicts. Workers carried the bulk.
