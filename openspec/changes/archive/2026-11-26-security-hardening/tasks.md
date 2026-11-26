# Tasks

## 1. Configuration and operations contract

- [x] 1.1 Add `APP_REQUEST_MAX_BYTES` to `read_app_settings()` and `.env.example`, and document the total-vs-per-file distinction; verify the default with a settings test and `python manage.py check`.
- [x] 1.2 Document the published ports, secret generation, webhook token, and cookie scheme rules in `docs/operations.md` and the README; verify the documented Compose and `.env` values match the repository.

## 2. Orchestration webhook authentication

- [x] 2.1 Add an authentication gate and a 401 responder to `n8n/workflows/processing.json` and `n8n/workflows/report.json`, comparing `X-Webhook-Token` with `APP_N8N_WEBHOOK_TOKEN`; verify a workflow-structure test asserts the gate and that no stage can run on the false branch.
- [x] 2.2 Ensure the token is never written to workflow output or application logs; verify with a test that captures the trigger failure log.

## 3. Service exposure

- [x] 3.1 Remove the Paperless host port from `compose.yaml`, document the loopback and SSH-tunnel alternatives, and keep the app able to reach Paperless on the Docker network; verify `docker compose config` shows no Paperless host port by default.

## 4. Startup secret validation

- [x] 4.1 Implement `core/startup.py` and call it from `config/wsgi.py` and `config/asgi.py`; add a Django system check for the same rule; verify default, empty, short, strong, and `DEBUG=true` cases with unit tests.

## 5. n8n cookie security

- [x] 5.1 Update `deploy.sh` and `.env.example` so `N8N_SECURE_COOKIE` follows the public scheme and HTTP prints a warning; verify the generated value for an HTTPS URL and an HTTP URL with tests.

## 6. Scoped bulk deletion

- [x] 6.1 Add a `scope` field with `tracked` as the default, require typed confirmation for `untracked`, and log a structured `bulk_delete` event; verify tracked-only, untracked-confirmed, and missing-confirmation cases with tests.

## 7. Upload request boundaries

- [x] 7.1 Change `RequestSizeLimitMiddleware` to use the total request limit while leaving the per-file limit in `validate_upload`; verify a two-file 20 MB upload is accepted and oversized single-file/total requests are rejected with the right error.

## 8. Integration verification

- [x] 8.1 Run the full suite, `python manage.py check --deploy`, `docker compose config`, and `openspec validate security-hardening --strict`; fix any failures and record the observed results.
- [x] 8.2 Smoke-test the webhook gate with a missing token, an invalid token, and the configured token; verify 401, 401, and normal workflow execution respectively.

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Verify the archived `platform-security` spec and the resulting capability baseline.
