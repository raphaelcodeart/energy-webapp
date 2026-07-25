# ADR 0002: No graph database (Neo4j) in v1

## Status
Accepted

## Context
The commercial network is a strict ancestor/descendant hierarchy. Graph databases
excel at flexible multi-relationship traversal and complex graph analytics, neither of
which is a proven requirement yet.

## Decision
Represent the network in PostgreSQL using a closure table (`network_closure`), backed
by a direct parent/child pointer (`network_nodes`) and full edge history
(`network_edges`). No Neo4j or other graph engine in v1.

## Consequences
- All network queries (ancestors, descendants, depth, branch production) are plain
  indexed SQL, transactional with the rest of the domain (contracts, commissions) —
  no cross-database consistency problem.
- Closure table writes on a move are O(affected subtree) rather than O(1); acceptable
  at expected network sizes (thousands, not millions, of agents per organization).
- Trigger to revisit: sustained need for deep, ad-hoc graph analytics (e.g. multi-path
  simulations, non-hierarchical relationship types) that closure-table SQL cannot
  express efficiently. Until then, introducing Neo4j would add an operational
  dependency (another datastore to back up, secure, and keep consistent with Postgres)
  with no measured problem it solves.
- Removal/change path: none needed — this is the default we start from, not something
  to unwind.
