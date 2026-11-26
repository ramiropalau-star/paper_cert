# Design

## Context

The application already sends `X-Webhook-Token`, but the bundled n8n workflows do not validate it. `compose.yaml` publishes Paperless on 9090 even though `docs/operations.md` says only the app and n8n are published. `DJANGO_SECRET_KEY` falls back to `dev-insecure-change-me`, and `N8N_SECURE_COOKIE=true` is set unconditionally. Bulk deletion currently lists every Paperless document, including ones the app does not track. The request-size middleware compares the whole multipart `CONTENT_LENGTH` with the per-file limit.

## Goals / Non-Goals

**Goals:**

- Authenticate both orchestration webhooks before any stage runs.
- Keep administrative services off the host by default.
- Reject insecure startup secrets.
- Make cookie security match the public scheme.
- Scope bulk deletion and separate upload limits.
- Cover the contracts with tests and operational documentation.

**Non-Goals:**

- A full identity provider, SSO, or per-user n8n accounts.
- TLS termination inside the stack (a reverse proxy or external terminator remains the deployment choice).
- Replacing Paperless or n8n.

## Decisions

### 1. Webhook authentication lives in the workflows, not only in the app

Add an IF node after each webhook that compares `$json.headers['x-webhook-token']` with `$env.APP_N8N_WEBHOOK_TOKEN`. The false branch responds with HTTP 401 and ends; the true branch continues to the existing stages. This keeps the secret in environment configuration and lets both services rotate it without editing workflow JSON.

Alternatives: n8n Header Auth credentials (static inside n8n, harder to rotate through `.env`), a reverse-proxy check (does not protect direct n8n access). Rejected.

The comparison is a plain string equality in n8n. Network timing attacks against a shared webhook secret are not a practical risk here; the token is also rate-limited by the workflow's normal request path.

### 2. Paperless is internal by default

Remove the `9090:8000` mapping from `compose.yaml`. Document `127.0.0.1:9090:8000` as the opt-in loopback alternative for local administration, and an SSH tunnel or reverse proxy for remote administration. Update `docs/operations.md` and the README so the published-port claim is true.

Alternatives: keep 9090 with a firewall rule (easy to drift), put Paperless behind n8n (wrong tool). Rejected.

### 3. Startup fails through the WSGI/ASGI entry point and a deploy check

Add `core/startup.py` with `validate_secret_key()` and call it from `config/wsgi.py` and `config/asgi.py` before `get_wsgi_application()`. Also register a Django system check so `manage.py check --deploy` reports the same problem. The validator:

- allows the default only when `DEBUG=true`;
- rejects missing, empty, default, or keys shorter than 32 characters when `DEBUG=false`;
- raises `ImproperlyConfigured` without echoing the value.

This avoids breaking build-time commands such as `collectstatic` or `migrate`, which do not import the WSGI entry point. Tests call the validator directly and use a test key.

Alternatives: fail in `AppConfig.ready()` (runs during every management command, including build steps), fail only at request time (too late). Rejected.

### 4. Cookie security is derived from the deployment scheme

`deploy.sh` reads the configured public scheme (or `N8N_PROTOCOL`) and writes `N8N_SECURE_COOKIE=true` for HTTPS and `false` for HTTP, printing a warning in the HTTP case. `.env.example` documents both paths. Compose passes the variable to n8n. The documentation recommends HTTPS via reverse proxy for any non-local deployment.

Alternatives: always `true` (breaks HTTP login), always `false` (weakens HTTPS). Rejected.

### 5. Bulk deletion is scoped and audited

The delete view accepts a `scope` field with `tracked` as the default and `untracked` as an explicit opt-in. `tracked` deletes only `Document` rows and their Paperless ids; `untracked` lists remote documents not tracked locally and requires a second typed confirmation. Both paths emit a structured `bulk_delete` log with actor, scope, tracked count, and untracked count. No new audit model is introduced; the structured log is the audit record.

Alternatives: remove bulk deletion (loses a legitimate admin tool), add a new audit table (heavier than the need). Rejected.

### 6. Request limits are separate

Add `APP_REQUEST_MAX_BYTES` (default 100 MB). `RequestSizeLimitMiddleware` checks `CONTENT_LENGTH` against that total. Per-file validation remains in `validate_upload` with `APP_UPLOAD_MAX_BYTES`. A multi-file request passes when each file is under the per-file cap and the combined body is under the total cap.

Alternatives: keep one limit (rejects valid multi-file uploads), enforce only in the view (bypasses middleware and reads the body). Rejected.

## Risks / Trade-offs

- Rotating the webhook token requires updating both the app environment and n8n; the workflows read the same variable, and a rolling restart is enough.
- Removing the Paperless port breaks remote admin shortcuts → document the loopback and SSH-tunnel options.
- Fail-fast stops an existing deployment with the default key → the migration plan calls for generating a key before upgrading.
- HTTP cookie disabling weakens session protection → the docs recommend HTTPS; the warning is explicit.
- Untracked deletion remains destructive → typed confirmation and audit logging bound the risk.
- The total request limit is not a substitute for per-file validation → both remain enforced.

## Migration Plan

1. Generate a strong `DJANGO_SECRET_KEY` and set it before deploying the fail-fast change.
2. Update `.env.example`, `compose.yaml`, and `deploy.sh`; run `docker compose config` to confirm Paperless has no host port by default.
3. Import the updated n8n workflows and set `APP_N8N_WEBHOOK_TOKEN` in both the app and n8n environments.
4. Apply the request-limit setting and restart the app.
5. Rollback: restore the previous Compose port mapping or set `APP_REQUEST_MAX_BYTES` high; the secret check can be bypassed only by setting a valid key. No database migration is involved.

## Open Questions

None that change the spec, approach, or task breakdown.
