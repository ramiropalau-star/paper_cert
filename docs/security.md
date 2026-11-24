# Authentication, roles, and internal API security

## Session authentication

The web application uses Django session authentication. Login is available at
`/accounts/login/` and logout is a POST to `/accounts/logout/`. All application
pages require an authenticated session; anonymous requests are redirected to
the login page with a `next` parameter.

Role groups are created idempotently:

```bash
.venv/bin/python manage.py seed_roles
```

## Roles

Roles are Django groups. The hierarchy is cumulative:

| Role | Capabilities |
| --- | --- |
| `viewer` | View documents and certificate data; generate and download reports. |
| `reviewer` | Everything a viewer can do, plus edit, approve, reject, and reprocess records. |
| `admin` | Everything a reviewer can do, plus catalog editing, user management, and deletion. |

Superusers bypass group checks. An authenticated user with no role can sign in
but receives HTTP 403 on application pages. Permission helpers live in
`core/permissions.py`; views use `role_required(...)` or the corresponding
`can_*` helper. The admin site is restricted to superusers or members of the
`admin` group.

## Internal service API

Pipeline endpoints live under `/internal/` and are called by n8n. They are
CSRF-exempt because they do not use session cookies, and they require a shared
service token in the `X-Internal-Token` header.

- The configured token is `APP_INTERNAL_API_TOKEN`.
- Comparison uses `hmac.compare_digest` (constant time).
- An empty configured token denies every request, including requests with an
  empty header.
- Missing or wrong tokens return `401 {"error": "unauthorized"}`.
- Each request is logged to the `core.internal` logger with method, path,
  optional `X-Request-ID`, and `accepted`/`denied` outcome. Tokens are never
  logged.

Example:

```bash
curl -H "X-Internal-Token: $APP_INTERNAL_API_TOKEN" \
  http://app:8000/internal/healthz
```

Do not expose `/internal/` outside the internal Docker network.

## CSRF and cookies

- `CsrfViewMiddleware` protects all session-authenticated POST requests.
- Session cookies are `HttpOnly` and `SameSite=Lax`.
- CSRF cookies are `SameSite=Lax`.
- `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` default to enabled when
  `DEBUG` is false, and can be overridden with `DJANGO_SECURE_COOKIES`.
- `SECURE_SSL_REDIRECT`, `SECURE_CONTENT_TYPE_NOSNIFF`,
  `SECURE_REFERRER_POLICY`, and `X_FRAME_OPTIONS=DENY` are configured in
  `config/settings.py`.

## Upload and request limits

- `APP_UPLOAD_MAX_BYTES` (default 25 MiB) is enforced by
  `core.middleware.RequestSizeLimitMiddleware` from the request
  `Content-Length`, returning HTTP 413 before the view runs.
- `DATA_UPLOAD_MAX_MEMORY_SIZE` is 2 MiB as a secondary guard for non-file form
  data.
- File type, magic bytes, page counts, and PDF parseability are validated in the
  intake pipeline (see `docs/intake.md`).

## Manual-review label

Unrecognized documents are tagged in Paperless-ngx with
`APP_PAPERLESS_OTHER_TAG` (default `Otros`). The label is applied to
non-certificate documents, unresolved language or entity records, and
processing failures; approval clears it. Tag failures are logged without
blocking the review queue.

## Test coverage

`tests/test_auth.py`, `tests/test_security.py`, and
`tests/test_internal_api.py` cover login/logout redirects, the role matrix,
admin access restrictions, CSRF rejection, secure cookie flags, oversized
requests, and internal token acceptance/denial.
