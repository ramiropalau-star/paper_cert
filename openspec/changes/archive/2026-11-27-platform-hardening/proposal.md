# Proposal

## Why

The pipeline is functionally solid — 563 tests pass, recovery is bounded, and catalog learning is idempotent — but the operational layer has gaps that only surface outside a developer laptop: a static `/healthz` reports healthy with the database down, watched-folder intake can read and move a partially copied file, duplicate detection is a check-then-create race against a unique constraint, and a storage failure leaves the upload with no retry path. The repository also has no CI, and lint/format debt is already committed (37 ruff errors, 22 unformatted files). The current test deployment intentionally uses `admin/admin`; production needs a safe credential path instead.

## What Changes

- Watched-folder intake waits for files to settle (stable size and mtime for a configurable window) before reading and moving them.
- Duplicate detection is concurrency-safe: a unique-constraint collision returns the existing document instead of raising `IntegrityError`.
- A duplicate upload of a document stuck in `error` without a Paperless id retries storage with the newly uploaded bytes instead of dead-ending.
- New `/readyz` checks the database and returns HTTP 503 when unavailable; the Compose app healthcheck uses it. `/healthz` remains a pure liveness probe.
- `deploy.sh` no longer defaults the admin password to `admin`: it requires `DEPLOY_ADMIN_PASSWORD` or generates a random one and prints it once. Test deployments can still opt in to `admin` explicitly.
- `.env` is created with mode `600`.
- Application secure-cookie, SSL-redirect, and HSTS settings follow the configured scheme, matching the existing n8n cookie rule; the production checklist is documented.
- CI runs `ruff check`, `ruff format --check`, and `pytest`. Existing lint/format debt is fixed and `openspec/` is excluded from `ruff format`.
- Test tooling adds coverage and parallel execution (`pytest-cov`, `pytest-xdist`).
- `documents/views.py` is split into a focused package; duplicate month-name keys are cleaned up.
- `scripts/backup.sh` plus a timer example automate the documented backup procedure.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `document-ingestion`: watched-folder settle behavior, concurrency-safe duplicate detection, retryable storage failure.
- `platform-operations`: readiness probe, automated backup helper.
- `platform-security`: production admin credentials, `.env` permissions, application cookie/HTTPS parity.
- `code-health`: enforced lint/format/test gates, focused view modules.

## Impact

- Ingestion: `documents/services/inbox.py`, `documents/services/intake.py`, `documents/services/paperless_ingest.py`, `documents/services/review.py`.
- Runtime and deployment: `config/settings.py`, `config/urls.py`, `core/views.py`, `compose.yaml`, `deploy.sh`, `scripts/backup.sh`.
- Code health: `documents/views.py` (split), `documents/services/months.py`, `requirements-dev.txt`, `.github/workflows/ci.yml`.
- Documentation: `docs/operations.md`, `docs/development.md`, `docs/configuration.md`, `docs/security.md`.
- No database migration is required. Test-deployment behavior is unchanged unless it explicitly opts into the new production defaults.
