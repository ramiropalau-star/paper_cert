# Design

## Context

The stack is a Django app (`app`), Paperless-ngx, n8n, Postgres, Redis, Ollama, and a watcher container orchestrated by `compose.yaml` and `deploy.sh`. Planning artifacts live in this repo; implementation happens in the live deploy directory `/root/paperless` and is synced back here. See proposal.md for motivation. Current state verified during planning:

- `documents/services/inbox.py::scan_inbox_once` reads and moves files immediately — no settle check exists.
- `documents/services/intake.py::process_upload` does check-then-create on `Document.fingerprint` (unique column) with no `IntegrityError` handling; a storage failure leaves the row in `error` with no `paperless_document_id` and no retry path.
- `config/urls.py` exposes `/healthz` (shallow) only; the app Compose healthcheck curls `/`.
- `scripts/backup.sh` exists; no automated timer/schedule helper.
- `deploy.sh` already generates a random admin password (production-readiness); `.env` is copied from `.env.example` without permission tightening.
- `config/settings.py` has `DJANGO_SECURE_COOKIES`, `DJANGO_SECURE_SSL_REDIRECT`, no HSTS; n8n derives `N8N_SECURE_COOKIE` from `N8N_PROTOCOL`.
- `documents/views.py` is ~1150 lines; `documents/services/months.py` has duplicate dict keys across language sections; no CI; `requirements-dev.txt` lacks coverage/parallel plugins; committed ruff debt exists.

## Goals / Non-Goals

**Goals:**

- Close the operational gaps listed in the proposal without changing pipeline behavior for valid inputs.
- Make production credential and transport-security posture explicit and scheme-driven.
- Establish a CI quality gate so lint/format/test debt cannot regress.

**Non-Goals:**

- No database migrations.
- No changes to extraction prompts, catalog learning, or review UX.
- No new external services; CI uses GitHub Actions on the existing repo.
- HTTPS termination itself stays with the operator's reverse proxy; this change only makes the app behave correctly behind it.

## Decisions

### Watched-folder settle check lives in `scan_inbox_once`

Before reading a file, stat it and require `size` and `mtime` unchanged across two consecutive scans (tracked in a small in-memory dict keyed by path) for `APP["inbox_settle_seconds"]` (default 2s, env `APP_INBOX_SETTLE_SECONDS`). Alternative considered: `os.stat` twice with `time.sleep` inside one scan — rejected because it blocks the poll loop and still races slow writers. The two-scan approach is simpler, non-blocking, and testable by injecting `now`/stat.

### Duplicate convergence via unique constraint, not locks

Wrap `Document.objects.create` in `transaction.atomic()` and catch `IntegrityError` on `fingerprint`; on collision, re-fetch and return `IntakeResult(existing, duplicate=True)`. Alternative considered: `select_for_update`/advisory lock — rejected as heavier and unnecessary since the unique index already serializes the race; the loser just re-reads.

### Storage retry reuses the existing row

In `process_upload`, when the fingerprint matches an existing document in `error` with empty `paperless_document_id`, attempt `store_document` again with the new bytes and transition to `STORED` on success. This keeps one record per content and makes the failure retryable by simply re-uploading. Alternative considered: delete-and-recreate — rejected because it loses review history and audit fields.

### `/readyz` does a real DB check; healthcheck switches to it

`readyz` runs `connection.ensure_connection()` (cheap `SELECT 1`) and returns 503 on failure. The app healthcheck changes from curling `/` to `/readyz`. `/healthz` stays shallow for orchestrator liveness. Docker `start_period` already covers boot; no compose health gate changes needed elsewhere.

### Scheme-driven transport security via one new env var

Add `APP_SCHEME` (default `http`, values `http`/`https`) read in `settings.py`. When `https`: `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`, and `SECURE_HSTS_SECONDS` (e.g. 31536000 with `SECURE_HSTS_INCLUDE_SUBDOMAINS`) default to enabled. Explicit `DJANGO_SECURE_*` env vars still override. Rationale: mirrors the n8n `N8N_PROTOCOL` → `N8N_SECURE_COOKIE` rule the docs already describe, giving operators one knob. Alternative considered: parsing the scheme out of `DJANGO_CSRF_TRUSTED_ORIGINS` — rejected as implicit and fragile when multiple origins exist.

### deploy.sh prints the generated password once

The final banner prints the admin password only when it was auto-generated (not when `DEPLOY_ADMIN_PASSWORD` was provided), matching the revised spec. `.env` is `chmod 600` after generation and on every run. Weak-password test deploys require `DEPLOY_ADMIN_PASSWORD` plus `BOOTSTRAP_ALLOW_WEAK_PASSWORD=1` (already supported by bootstrap) — documented as test-only.

### CI on GitHub Actions; ruff debt fixed in one commit

`.github/workflows/ci.yml` runs `ruff check`, `ruff format --check`, `pytest` on push/PR. `openspec/` is added to ruff format exclusions (docs, not code). The ~37 ruff errors and 22 unformatted files are fixed mechanically in a dedicated commit so the gate starts green. `pytest-cov` and `pytest-xdist` join `requirements-dev.txt`; `addopts` stays unchanged so local runs are unaffected.

### `documents/views.py` split into a package

Convert `documents/views.py` into `documents/views/` package grouped by concern (list/detail, review actions, upload, reports-facing helpers as applicable), preserving import paths used by `urls.py` and tests. `months.py` duplicate keys are resolved by building the folded map programmatically per language with an explicit dedupe (identical values collapse; conflicting values would fail a test).

## Risks / Trade-offs

- [Settle window delays inbox processing by a few seconds] → Default is small (2s); files already fully written settle on the second scan.
- [Printing the generated admin password once exposes it to shoulder-surfing/log capture] → Only on fresh auto-generated deploys; documented; operators can override with `DEPLOY_ADMIN_PASSWORD`.
- [Scheme-driven defaults could surprise an HTTP deploy behind a TLS proxy that forgets `APP_SCHEME=https`] → Docs checklist updated; explicit `DJANGO_SECURE_*` overrides remain.
- [Splitting views.py risks import breakage] → URLconf and tests pin the public surface; run full suite before deploy.
- [pytest-xdist may expose test isolation bugs] → Run suite both serial and parallel before enabling in CI; keep `-n auto` only if green.

## Migration Plan

No DB migrations. Deploy order: implement → `pytest` (serial + `-n auto`) → `ruff` clean → `docker compose build app watcher` → `docker compose up -d` → `scripts/health.sh` → sync to `/root/paper_cert` and push. Rollback: `git revert` in paper_cert and redeploy previous images; `.env` permission tightening is non-destructive.

## Open Questions

- Exact `APP_SCHEME` name vs reusing an existing var — decided above; can be renamed during apply without spec impact.
