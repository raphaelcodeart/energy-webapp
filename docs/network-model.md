# Network Model (Infrastructure)

Not to be confused with the *commercial* network (promoters/agents) — see
`database-model.md §2`. This document covers server/container network topology.

## Topology (docker-compose.dev.yml)

```
Internet
   │
   ▼
nginx (ports 80/443 exposed)
   │
   ├── /            → dashboard:3000
   ├── /api          → api:8000
   └── /storage      → minio:9000 (signed URLs only, never browsable)

Internal-only network (not published to host):
   postgres:5432
   redis:6379
   minio:9000/9001 (console)
   celery-worker (no listening port needed)
   celery-beat (no listening port needed)
```

## Rules
- Only `nginx` publishes ports to the host/internet. `postgres`, `redis`, `minio`
  (admin), and `flower` (if enabled) are reachable only on the internal Compose
  network, never published.
- All application containers run as a non-root user (set explicitly in each
  Dockerfile via `USER app`).
- TLS terminates at nginx; Let's Encrypt (certbot) in production, self-signed/plain
  HTTP acceptable in local dev.
- Service-to-service calls (dashboard → api, worker → postgres/redis) use Compose
  service names as hostnames; no hardcoded IPs.

## Environments
- `development`: docker-compose.dev.yml, MinIO instead of real S3, relaxed CORS for
  local Next.js dev server, seed data loaded.
- `staging` / `production`: docker-compose.production.yml, real S3-compatible storage,
  strict CORS, no seed data, secrets from environment/secret store.
