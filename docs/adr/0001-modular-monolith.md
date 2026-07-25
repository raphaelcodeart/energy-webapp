# ADR 0001: Modular monolith over microservices for v1

## Status
Accepted

## Context
The platform has many bounded contexts (auth, network, contracts, commissions,
documents, AI...). Microservices would let each scale/deploy independently, but this is
a greenfield build with one team and no measured need for independent scaling yet.

## Decision
Build one FastAPI backend with strict internal domain package boundaries
(`app/domains/<name>/`), one Next.js BFF, one Celery worker importing the backend's
domain code directly. No network hop between domains.

## Consequences
- The commission engine has exactly one implementation — no risk of the worker or a
  future service reimplementing (and diverging from) the ledger math.
- Deploys are simpler: one backend image, one frontend image, one worker image.
- Cost: if a specific domain later needs independent scaling (e.g. AI embedding
  ingestion under heavy load), it can be extracted — the domain package boundary is
  designed to make that extraction mechanical rather than a rewrite.
- Removal/change path: extracting a domain into its own service means giving it its own
  router mount and repository package already exist as seams; the main added work would
  be an internal API contract and auth between services, which does not exist today.
