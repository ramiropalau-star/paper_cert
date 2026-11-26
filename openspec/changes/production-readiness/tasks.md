# Tasks

## 1. Credential hardening

- [x] 1.1 In `deploy.sh`, replace `DEPLOY_ADMIN_PASSWORD:-admin` with a generated strong password (`openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24` or equivalent) written only to `.env`; keep the env override; verify a fresh `.env` generation produces a non-`admin` password and the console banner does not print it.
- [x] 1.2 Update `deploy.sh` usage header and docs to state the new default behavior; verify `bash -n deploy.sh` passes and a dry review shows no password echo.
- [x] 1.3 In `core/management/commands/bootstrap.py`, validate `DJANGO_SUPERUSER_PASSWORD` with `validate_password()` before `create_superuser`, gated by a `BOOTSTRAP_ALLOW_WEAK_PASSWORD` env override; verify unit tests cover weak-password rejection, valid-password creation, and override bypass.
- [x] 1.4 Add/extend tests for bootstrap password validation; run `python manage.py test core` (or the relevant test module) and confirm pass.

## 2. Port exposure

- [x] 2.1 Add `N8N_BIND_ADDR` (default `127.0.0.1`) to `compose.yaml` n8n ports and `.env.example`; verify `docker compose config` shows `127.0.0.1:5678:5678` by default and honors an override.
- [x] 2.2 Add `APP_BIND_ADDR` (default `0.0.0.0`) for the app port the same way; verify `docker compose config` output for both defaults and an override.
- [x] 2.3 Update `deploy.sh` banner and `docs/operations.md`/`docs/security.md` to document loopback defaults, LAN override, and reverse-proxy access; verify docs match the compose variables.

## 3. Backups

- [x] 3.1 Create `scripts/backup.sh` implementing `pg_dumpall` + volume tarballs into `./backups/<timestamp>/` with `BACKUP_RETENTION_DAYS` pruning (default 14); verify a manual run produces a complete backup set and old backups are pruned.
- [x] 3.2 Document backup schedule (cron example) and the restore procedure in `docs/operations.md`; verify the restore steps against a real backup in a scratch directory.
- [x] 3.3 Add `.gitignore`/docs note for `backups/` so backup output is not committed; verify `git status`/`check-ignore` behavior in `/root/paper_cert` mirror if applicable.

## 4. Log rotation and health visibility

- [x] 4.1 Add a compose `x-logging` anchor (`json-file`, `max-size: 10m`, `max-file: 3`) and apply it to every service; verify `docker compose config` renders the logging block for all services.
- [x] 4.2 Create `scripts/health.sh` aggregating `docker compose ps` health into a readable table with non-zero exit on unhealthy; verify it runs against the live stack and reports current status.

## 5. Production docs

- [x] 5.1 Add a production section (HTTPS reverse-proxy example, required env vars: `DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_ALLOWED_HOSTS`, `N8N_PROTOCOL=https`, `N8N_SECURE_COOKIE=true`, `DJANGO_SECURE_COOKIES=true`, bind addresses, credential rotation, backup cron) to `docs/security.md` or `docs/operations.md`; verify every referenced variable exists in `.env.example`/`settings.py`.
- [x] 5.2 Update README/docs index if a new doc section warrants it; verify links resolve.

## 6. Verification

- [x] 6.1 Run `python manage.py check`, the test suite, `docker compose config`, and `openspec validate production-readiness --strict`; fix failures and record results.
- [x] 6.2 Smoke-verify: fresh `.env` path generates strong password, `docker compose config` shows loopback n8n, `scripts/backup.sh` and `scripts/health.sh` execute successfully.
