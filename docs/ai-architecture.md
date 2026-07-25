# AI Architecture (Phase G — not yet implemented in this vertical slice)

## Scope
pgvector-backed semantic search over internal knowledge (regulations, contract
templates, FAQs, operator manuals) plus a hybrid (semantic + full-text) search and an
internal assistant. Explicitly out of scope for the AI layer: deciding commissions,
mutating the ledger, approving contracts, changing qualifications, moving network
nodes, or presenting its output as an administrative decision. The assistant may
*explain* a commission calculation in natural language, but the numbers it explains
must come from the deterministic engine's stored `explanation`/output fields — it never
computes its own figures.

## Planned schema

```
knowledge_documents          (id, organization_id, title, category, status, created_at)
knowledge_document_versions  (id, document_id, version_label, storage_key, checksum, created_at)
knowledge_chunks             (id, organization_id, document_id, document_version_id,
                               content, embedding vector(N), metadata jsonb,
                               checksum, created_at)
knowledge_embeddings         -- model registry: which model/dimension produced which chunk's vector
ai_conversations             (id, organization_id, user_id, created_at)
ai_messages                  (id, conversation_id, role, content, citations jsonb, created_at)
ai_audit_events              (id, organization_id, user_id, query, retrieved_chunk_ids,
                               model, created_at)
```

## Pipeline
1. Ingestion: document uploaded → chunked (configurable size/overlap) → embedded via a
   registered model → stored with checksum and model/dimension metadata for
   reproducible re-embedding if the model changes.
2. Retrieval: hybrid search = pgvector cosine similarity + Postgres full-text search,
   combined and re-ranked, filtered by `organization_id` and the caller's document
   permissions before ranking (never rank-then-filter, to avoid leaking existence of
   restricted documents via ranking side channels).
3. Generation: retrieved chunks + citations passed to the LLM; every response is
   required to carry citations back to `knowledge_chunks.id`.
4. Every query and every retrieved chunk id is written to `ai_audit_events`.

## Guardrails
- No AI-initiated writes to `commission_movements`, `network_nodes`, `contracts`, or
  `agent_rank_history`. The assistant has read-only tool access to those domains
  through the same permission-checked service layer everything else uses — no
  privileged bypass.
- Organization and permission filters are applied before retrieval, not as a post-hoc
  filter on the LLM's answer.

## Status
Not implemented in this session's vertical slice (Phase B–E only). This document is
the target design for Phase G and will be revised once ingestion volume and query
patterns are known.
