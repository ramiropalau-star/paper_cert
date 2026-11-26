# Proposal

## Why

The stack currently exposes more than the documentation claims and accepts orchestration triggers without validating the token the application already sends. Paperless publishes port 9090, n8n webhooks run unauthenticated, the application can start with a known default secret, and `N8N_SECURE_COOKIE` can silently break login over plain HTTP. These are deployment-level gaps that become urgent as soon as the stack is reachable beyond localhost.

## What Changes

- **Authenticated orchestration webhooks**: the n8n processing and report workflows validate `X-Webhook-Token` against `APP_N8N_WEBHOOK_TOKEN` and return HTTP 401 for missing or invalid tokens before any stage runs.
- **Controlled service exposure**: the default Compose configuration keeps Paperless, Ollama, PostgreSQL, and OCR internal; only the application and n8n UI remain published. Any additional exposure is explicit and documented.
- **Fail-fast on insecure secrets**: the application refuses to start with the development `DJANGO_SECRET_KEY`, an empty value, or a short key when `DEBUG` is false. The error names the variable without printing its value.
- **Cookie security matches the scheme**: `N8N_SECURE_COOKIE` is configured for HTTPS deployments, and HTTP LAN deployments either move to HTTPS or explicitly disable secure cookies with a documented warning.
- **Scoped bulk deletion**: bulk deletion removes only documents tracked by the application by default; deleting untracked Paperless documents requires an explicit scope and a separate confirmation, and is audited.
- **Separate upload boundaries**: the per-file limit stays in intake validation, and a configurable total request limit is enforced independently so a valid multi-file upload is not rejected by the per-file cap.
- **Tests and documentation**: cover token rejection, secret failure, deletion scope, request boundaries, and the Compose exposure contract; update `.env.example` and `docs/operations.md`.

## Capabilities

### New Capabilities

- `platform-security`: durable behavior for authenticating orchestration webhooks, controlling service exposure, rejecting insecure startup secrets, matching cookie security to the access scheme, scoping destructive operations, and bounding upload requests.

### Modified Capabilities

None.

## Impact

- **Workflows**: `n8n/workflows/processing.json`, `n8n/workflows/report.json`.
- **Configuration**: `compose.yaml`, `deploy.sh`, `.env.example`, `config/settings.py`.
- **Application**: `core/middleware.py`, `core/` startup checks, `documents/views.py`, `documents/forms.py`, `documents/templates/`.
- **Documentation**: `docs/operations.md`, `README.md` where ports or secrets are described.
- **Risk**: token rotation requires updating both the app and n8n; binding Paperless to loopback changes remote-admin workflows; fail-fast can stop an existing deployment until its secret is fixed.
