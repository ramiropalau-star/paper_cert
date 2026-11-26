# Design

## Context

Single-host Docker Compose stack (`compose.yaml`) with Django app, watcher, n8n, Paperless-ngx, Ollama, PostgreSQL, Redis, and a custom OCR service. `deploy.sh` is the one-shot installer that generates `.env` with `openssl rand` secrets — except the admin password, which defaults to `admin`. `bootstrap` creates the Django superuser via `create_superuser`, which does not run password validators. Compose publishes the app port (`${APP_PORT:-8080}:8000`) and n8n (`5678:5678`) on all interfaces. Backups exist only as manual commands in `docs/operations.md`. No `logging:` options anywhere, so Docker's json-file driver grows unbounded. Healthchecks exist per service but nothing aggregates them.

## Goals / Non-Goals

**Goals:**
- Strong credentials by default on fresh deploys; weak passwords rejected at bootstrap.
- Admin UIs (n8n) bound to loopback unless explicitly overridden.
- One-command backup with retention covering all persistent state.
- Bounded container logs on every service.
- One-command health overview + production TLS/exposure docs.

**Non-Goals:**
- No centralized monitoring stack (Prometheus/Grafana) — out of scope for a single-host deploy.
- No automated off-site backup shipping — local backups + documented copy step only.
- No change to application runtime behavior, data model, or pipeline logic.
- No mandatory HTTPS — TLS stays opt-in via reverse proxy, but the docs must make it turnkey.

## Decisions

### Admin password generation in deploy.sh

Generate with `openssl rand -base64 24` (URL-safe enough for env files; avoids `+`/`/` issues by using `tr -dc` or hex). Store only in `.env`; never echo. Keep `DEPLOY_ADMIN_PASSWORD` as explicit override. Alternative considered: prompting interactively — rejected because deploy.sh is non-interactive-friendly and CI/SSH-friendly; env override covers automation.

### Bootstrap password validation

In `bootstrap`, when creating the superuser, run `django.contrib.auth.password_validation.validate_password()` against all `AUTH_PASSWORD_VALIDATORS`. Add `DEPLOY_ALLOW_WEAK_ADMIN=1`-style env override (`BOOTSTRAP_ALLOW_WEAK_PASSWORD`) for tests/local. Alternative: always validate — rejected because test environments legitimately use weak passwords and `create_superuser` semantics shouldn't change for existing users (only creation is gated).

### Bind addresses via env vars

Introduce `APP_BIND_ADDR` (default `0.0.0.0` for the app — it IS the user entry point) and `N8N_BIND_ADDR` (default `127.0.0.1` — admin UI). Compose port syntax: `"${N8N_BIND_ADDR:-127.0.0.1}:5678:5678"`. Document that LAN access requires setting the var or using a reverse proxy/SSH tunnel. Alternative: keep 0.0.0.0 and rely on firewall — rejected, binding is cheaper and self-documenting. Note: existing deployments that rely on LAN n8n access will need `N8N_BIND_ADDR` set — this is a deliberate breaking-ish change called out in migration.

### Backup via script, not sidecar

`scripts/backup.sh`: `pg_dumpall` inside the db container + `docker run --rm -v <volume>` tarballs for each persistent volume (same technique already documented), output to `./backups/YYYY-MM-DD-HHMM/` (or single tarball), then prune by `BACKUP_RETENTION_DAYS` (default 14). Volume list sourced from a small manifest inside the script; adding a volume = one line. Alternative: add a `backup` compose service on a cron — rejected as heavier; a script + documented cron line covers both manual and scheduled use. Consistency: `pg_dumpall` is online-safe; volume tarballs of live Paperless media may catch a file mid-write — acceptable for this workload, restore doc notes it.

### Log rotation via compose `logging:`

Add a YAML anchor (`x-logging: &default-logging`) with `driver: json-file`, `max-size: 10m`, `max-file: 3` applied to every service. Zero moving parts, works with any Docker engine.

### Health aggregation

`scripts/health.sh`: `docker compose ps --format json` → table of service/health; exit non-zero if any unhealthy. Cheaper than a status page; documented cron/monitoring hook.

### HTTPS docs

Add `docs/security.md` (or operations.md) production section + `deploy/` example: Caddyfile snippet terminating TLS for app:8080, n8n:5678 (via published loopback or proxy), paperless via SSH tunnel or optional publish; lists required env changes (`DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_ALLOWED_HOSTS`, `N8N_PROTOCOL=https`, `N8N_SECURE_COOKIE=true`, `DJANGO_SECURE_COOKIES=true`).

## Risks / Trade-offs

- [Loopback n8n breaks existing LAN workflows] → Migration note + `N8N_BIND_ADDR` escape hatch; smoke step in deploy prints the bind.
- [Backup of live volumes can capture partial files] → Acceptable for document store; restore doc verifies integrity; DB dump is the authoritative state.
- [Random admin password is unknown to operator] → deploy.sh prints where to find it (`.env`) not the value; `/users/` admin UI can reset later.
- [Log rotation could hide forensic history] → 30MB/service retained; sufficient for this scale.

## Migration Plan

1. Deploy code changes; existing `.env` untouched except new optional vars default safely.
2. On upgrade, operator MUST set new strong passwords for Django + Paperless admin and rotate `DEPLOY_ADMIN_PASSWORD` usage; documented in migration notes.
3. If n8n was accessed over LAN, set `N8N_BIND_ADDR=0.0.0.0` (or better, put it behind the proxy) before `up -d`.
4. First backup run creates `./backups/`; add cron line from docs.
5. Rollback: revert compose/deploy changes; `.env` additions are backward compatible.
