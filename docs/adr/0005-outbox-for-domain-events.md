# ADR 0005: Transactional outbox for domain events

## Status
Accepted

## Context
Domain events (`ContractActivated`, `CommissionCalculated`, etc.) trigger side effects
(commission calculation, notifications) that must never fire based on a transaction
that later rolls back, and must never be silently lost if the process crashes between
commit and dispatch.

## Decision
Critical domain events are written to a `domain_outbox` table in the same transaction
as the state change. A Celery Beat task polls the outbox and dispatches unprocessed
rows, marking them processed after successful handling.

## Consequences
- No event is ever published for a transaction that didn't commit.
- No event is silently lost if the process crashes after commit but before an in-memory
  dispatch would have fired.
- Adds one polling task and one table; acceptable given the correctness guarantee it
  buys for commission generation and payment confirmation, both of which touch money.
- Removal/change path: if event volume ever demands it, the outbox poller can be
  replaced by Postgres LISTEN/NOTIFY or a CDC pipeline without changing the writer side
  (the outbox table itself remains the contract).
