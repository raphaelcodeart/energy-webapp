# ADR 0003: pgvector scoped to document/AI search only

## Status
Accepted

## Context
Phase G calls for AI-assisted document search (regulations, contracts, knowledge base).
pgvector is the natural fit since the data already lives in Postgres. There is a
temptation to also use vector similarity for "similar agents" or network exploration.

## Decision
pgvector is used exclusively for `knowledge_chunks.embedding` (Phase G). The commercial
network continues to use the closure table (ADR 0002) as its sole representation.

## Consequences
- Keeps the network's authoritative representation single and transactional.
- AI search failures/latency never affect network or commission correctness — they are
  additive read paths, not on the critical path of any economic calculation.
- Removal/change path: pgvector extension can be dropped without touching any
  commission or network table if AI search is ever removed.
