# Proposal

## Why

The stack runs with development-grade credentials and operational gaps that are acceptable on a test LAN but unsafe for production: the deploy script defaults the Django and Paperless admin password to `admin`, the bootstrap command creates the superuser bypassing password validators, the n8n UI is published on all interfaces, there is no automated backup, Docker logs grow unbounded, and nothing alerts when a service fails. The admin password is intentionally weak only while the deployment is in test; production needs these gaps closed.

## What Changes

- **Credential hardening**: `deploy.sh` MUST generate a strong random admin password by default instead of defaulting to `admin`; an explicit `DEPLOY_ADMIN_PASSWORD` override remains available. `bootstrap` MUST validate the superuser password with Django's password validators and refuse weak passwords unless an explicit override is set.
- **Port exposure**: the n8n UI port binding becomes configurable and defaults to loopback (`127.0.0.1:5678`) instead of all interfaces; the application port binding gains an optional bind-address variable so operators can restrict it to loopback or a specific interface. Documented reverse-proxy access remains supported.
- **Automated backups**: a `backup.sh` script (or management command) performs a consistent backup of PostgreSQL plus the persistent volumes that hold user data (app media, reports, Paperless media/data, n8n data), with configurable retention; `deploy.sh` documents or optionally schedules it.
- **Log rotation**: every Compose service gets a `logging` driver configuration with size/count limits so container logs cannot fill the disk.
- **Health visibility**: a lightweight status/health aggregation (script or documented check) reports per-service health so operators can detect failures; documented monitoring guidance added.
- **HTTPS readiness**: document and provide a minimal reverse-proxy example (Caddy or nginx) covering the app, n8n, and Paperless UI with correct `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`/`N8N_PROTOCOL` settings.

## Capabilities

### New Capabilities

- `backup-recovery`: scheduled/manual backup creation, retention, and restore documentation for all persistent data.

### Modified Capabilities

- `platform-security`: new requirements for credential strength at deploy/bootstrap time and for default bind addresses of published admin UIs.
- `platform-operations`: new requirements for automated backups, bounded container logs, and health visibility/monitoring guidance.

## Impact

- `deploy.sh`: password generation default, optional backup step, n8n bind address.
- `compose.yaml`: port bindings, per-service `logging` options.
- `config/settings.py` / `core/management/commands/bootstrap.py`: password validation on bootstrap.
- New `scripts/backup.sh` (and restore notes) plus docs updates in `docs/operations.md` and `docs/security.md`.
- No API or data-model changes; existing deployments keep working but MUST rotate the admin password when upgrading.
