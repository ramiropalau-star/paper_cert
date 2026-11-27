# Tasks

## 1. Watched-folder settle

- [x] 1.1 Add `APP_INBOX_SETTLE_SECONDS` (default 2) to `read_app_settings`/`settings.APP` and `.env.example`; verify a unit test shows a file whose size/mtime changed between scans is skipped and processed after settling.
- [x] 1.2 Implement the settle check in `documents/services/inbox.py` (track per-path stat signature across scans); verify tests cover: partial write left in place, settled file processed, subdirectory files ignored, configurable window.

## 2. Concurrency-safe intake and storage retry

- [x] 2.1 In `documents/services/intake.py`, wrap document creation in `transaction.atomic()`, catch `IntegrityError` on `fingerprint`, re-fetch and return `duplicate=True`; verify a test simulates the race (e.g. pre-create between check and create via mock) and asserts one record.
- [x] 2.2 Add retry path: existing document in `error` with empty `paperless_document_id` re-attempts `store_document` with the uploaded bytes and transitions to `STORED` on success; verify tests cover success retry, repeated failure staying in `error`, and non-error duplicates still short-circuiting.
- [x] 2.3 Apply the same duplicate-convergence handling in `documents/services/paperless_ingest.py` if it has its own check-then-create path; verify with its tests.

## 3. Readiness probe

- [x] 3.1 Add `/readyz` in `config/urls.py` + view performing `connection.ensure_connection()` and returning 503 on failure; verify tests cover DB-up 200 and DB-down 503 (mock connection).
- [x] 3.2 Switch the app Compose healthcheck in `compose.yaml` to `/readyz`; verify `docker compose config` renders it and `scripts/health.sh` still reports correctly against the live stack.

## 4. Platform security deltas

- [x] 4.1 `deploy.sh`: `chmod 600 .env` after generation and tighten existing `.env` permissions on every run; verify with a manual run and `stat -c %a .env`.
- [x] 4.2 `deploy.sh`: print the generated admin password once in the final summary only when auto-generated (never when `DEPLOY_ADMIN_PASSWORD` was provided, never in logs); verify by inspecting the script and a dry review.
- [x] 4.3 Document the weak-password test opt-in (`DEPLOY_ADMIN_PASSWORD=admin` + `BOOTSTRAP_ALLOW_WEAK_PASSWORD=1`, test-only) in `deploy.sh` header and `docs/security.md`.
- [x] 4.4 `settings.py`: add `APP_SCHEME` (`http`/`https`, default `http`); when `https`, default `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`, and HSTS (`SECURE_HSTS_SECONDS` + includeSubdomains) on, with explicit `DJANGO_SECURE_*` env overrides winning; verify unit tests for http/https/override combinations.
- [x] 4.5 Update `docs/operations.md` production checklist and `.env.example` for `APP_SCHEME` and the cookie/redirect/HSTS behavior; verify documented vars exist.

## 5. Backups

- [x] 5.1 Verify `scripts/backup.sh` produces a timestamped backup set (pg_dumpall + volume tarballs) under `backups/` with `BACKUP_RETENTION_DAYS` pruning; fix gaps found; verify a manual run.
- [x] 5.2 Add a scheduling example (cron and/or systemd timer) to `docs/operations.md`; verify the documented command matches the script's interface.

## 6. Code health: lint/format debt, CI, test tooling

- [x] 6.1 Add `.github/workflows/ci.yml` running `ruff check`, `ruff format --check`, and `pytest` on push/PR; verify workflow syntax (e.g. `actionlint` or careful review) and that `openspec/` is excluded from ruff format via `pyproject.toml`.
- [x] 6.2 Fix all existing `ruff check` violations and run `ruff format`; verify both commands exit clean on the repo.
- [x] 6.3 Add `pytest-cov` and `pytest-xdist` to `requirements-dev.txt`; verify `pytest -n auto` passes (investigate and fix any test-isolation failures, or document serial-only if unfixable).
- [x] 6.4 Resolve duplicate month-name keys in `documents/services/months.py` (build folded map with explicit dedupe); verify existing date tests still pass and add a test asserting no conflicting duplicates.

## 7. View module split

- [x] 7.1 Split `documents/views.py` (~1150 lines) into a `documents/views/` package grouped by concern; keep `documents/urls.py` and all imports working; verify `pytest documents` passes and no behavior change.

## 8. Docs and verification

- [x] 8.1 Update `docs/development.md` (CI, coverage/parallel test commands) and `docs/configuration.md` (new env vars); verify links/vars accurate.
- [x] 8.2 Full verification: `pytest` serial and `-n auto`, `ruff check`, `ruff format --check`, `bash -n deploy.sh`, `docker compose config` clean; verify all green.
- [x] 8.3 Deploy to the live stack (`docker compose build` + `up -d` for app/watcher as needed), run `scripts/health.sh`, and smoke-test upload + inbox paths; verify healthy status.
