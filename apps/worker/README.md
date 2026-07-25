# apps/worker

There is no separate Python package here. The Celery application lives at
`apps/api/app/celery_app.py` and is built from the exact same Docker image as
`apps/api` (see `apps/api/Dockerfile` and the `celery-worker`/`celery-beat` services
in `docker-compose.dev.yml`) -- only the container `command` differs.

This is deliberate: the worker must reuse the backend's domain code (models,
services, the commission engine) rather than reimplementing or vendoring a copy of
it, per `docs/architecture.md` and `docs/adr/0001-modular-monolith.md`. If a
worker-specific dependency ever needs isolating from the API (e.g. a heavy ML
library for Phase G's AI document ingestion), that's the trigger to give this
directory its own `pyproject.toml` and Dockerfile -- not before.
