# ADR 0004: Closure table + snapshot for commercial network history

## Status
Accepted

## Context
The network needs efficient ancestor/descendant/depth queries (for authorization,
branch production, commission chain walking) and must never let a later reorganization
rewrite history for already-activated contracts.

## Decision
Three complementary structures:
1. `network_nodes` — current-state pointer (`direct_parent_agent_id`) for O(1) writes.
2. `network_edges` — append-only history of every parent/child relationship, closed
   with `effective_to` rather than deleted.
3. `network_closure` — the derived transitive closure (including the reflexive
   ancestor=descendant, depth=0 row), maintained transactionally alongside edges.
4. `network_snapshots` / `network_snapshot_nodes` — an immutable copy of the relevant
   closure rows taken at contract activation, referenced by `contracts.network_snapshot_id`.

## Consequences
- Reads (ancestors, descendants, branch counts, chain walk for commissions) are simple
  indexed SQL against `network_closure`, no recursive CTEs needed at request time.
- Writes (a move) are more expensive — recompute closure rows for the affected subtree
  — but moves are rare relative to reads.
- Because commission calculations read `network_snapshot_nodes` (frozen) rather than
  live `network_closure`, a later move can never retroactively alter a past
  calculation, satisfying the "no retroactive network changes" business rule.
- `ltree` extension was considered as an alternative/complement; deferred until a
  measured need for path-string queries arises — the closure table alone satisfies
  every query pattern identified in `database-model.md §2`.
