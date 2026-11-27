# Configuration reference

Most tunables live in `.env` (copy `.env.example` on first deploy); a
subset is also editable at runtime from the admin panel — see
[Runtime-editable settings](#runtime-editable-settings). This page is the
complete variable reference; per-feature details live in the linked docs.
Secrets must be long random values — `deploy.sh` generates them on first
run.

## Django

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | — | Django secret; app refuses the dev default when `DEBUG=false`. |
| `DJANGO_DEBUG` | `false` | Django debug mode. Never enable in production. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hostnames the app answers to. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | Extra CSRF-trusted origins (scheme + host). |
| `APP_SCHEME` | `http` | Public scheme (`http`/`https`); drives the transport-security defaults below. |
| `DJANGO_SECURE_COOKIES` | follows `APP_SCHEME` | `Secure` flag on session/CSRF cookies; explicit override. |
| `DJANGO_SECURE_SSL_REDIRECT` | follows `APP_SCHEME` | Redirect HTTP → HTTPS; explicit override. |
| `DJANGO_SECURE_HSTS_SECONDS` | `31536000` on https, else `0` | HSTS max-age; explicit override. |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` | follows `APP_SCHEME` | HSTS includeSubDomains; explicit override. |
| `APP_PORT` | `8080` | Host port published by the `app` service. |
| `DJANGO_SUPERUSER_USERNAME/PASSWORD/EMAIL` | `admin` / … | Used once by `manage.py bootstrap`. |

## Database

| Variable | Default | Purpose |
| --- | --- | --- |
| `DB_ENGINE` | `postgres` | `postgres` or `sqlite`. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | — | Shared PostgreSQL instance for app, Paperless, and n8n. |

## Application paths

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_MEDIA_ROOT` | `/data/media` | Staging directory parent (`app-media` volume). |
| `APP_REPORT_OUTPUT_DIR` | `/data/reports` | Report workbook output (`reports` volume). |

## Uploads and text acquisition

See `docs/intake.md` and `docs/text-acquisition.md`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_UPLOAD_MAX_BYTES` | `26214400` (25 MiB) | Maximum size per uploaded file. |
| `APP_REQUEST_MAX_BYTES` | `104857600` (100 MiB) | Maximum total request body. |
| `APP_PDF_MAX_PAGES` | `100` | Maximum pages in a PDF. |
| `APP_EMBEDDED_TEXT_MIN_CHARS` | `30` | Minimum embedded text to skip OCR. |
| `APP_OCR_MIN_TEXT_CHARS` | `30` | Minimum OCR text to accept a page. |
| `APP_OCR_LOW_CONFIDENCE_THRESHOLD` | `0.55` | OCR confidence below which review is flagged. |

## OCR service

See `docs/ocr.md`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_OCR_URL` | `http://ocr:8000` | OCR service base URL. |
| `APP_OCR_LANGUAGES` | `eng,spa` | Tesseract language packs to enable. |
| `APP_OCR_TIMEOUT_SECONDS` | `660` | Per-request OCR timeout. |
| `APP_OCR_RETRIES` | `2` | Retries on OCR failures. |

## Ollama / extraction

See `docs/extraction.md` and `docs/review.md`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_OLLAMA_URL` | `http://ollama:11434` | Ollama base URL. |
| `APP_OLLAMA_MODEL` | `qwen2.5:7b-instruct` | Chat model used for extraction. See `operations.md` → "Extraction model selection" for the comparison that justified this default. |
| `APP_OLLAMA_TIMEOUT_SECONDS` | `180` | Extraction request timeout. |
| `APP_OLLAMA_RETRIES` | `2` | Extraction retries. |
| `APP_LLM_MAX_INPUT_CHARS` | `40000` | Page text cap sent to the model. |
| `APP_CONFIDENCE_REVIEW_THRESHOLD` | `0.6` | Below this overall confidence → review. |
| `APP_FORMAT_MIN_SAMPLES` | `2` | Min approved samples for an anchor to count. |
| `APP_FORMAT_MIN_EXAM_SAMPLES` | `3` | Min samples for an exam-scoped format cohort. |
| `APP_FORMAT_SCORE_THRESHOLD` | `0.4` | Below this format score → `format_mismatch`. |
| `APP_FORMAT_MAX_SCORE` | `0.5` | Weight of the format score in blended confidence. |
| `APP_PRE_DETECTION_ENABLED` | `true` | Deterministic issuer/type pre-detection before extraction. |
| `APP_PRE_DETECTION_CONFIDENCE` | `0.6` | Min confidence for a pre-detection `match`. |
| `APP_PRE_DETECTION_MARGIN` | `0.15` | Min top-two score margin for a `match`. |
| `APP_PRE_DETECTION_CLASSIFIER_ENABLED` | `false` | One bounded classifier call on ambiguous pre-detection. |
| `APP_PROFILE_GUIDED_EXTRACTION_ENABLED` | `true` | Inject issuer profile context + candidate pre-pass on a detected match. |
| `APP_PROFILE_CONTEXT_MAX_CHARS` | `4000` | Character budget for the profile-guided prompt section. |
| `APP_EXTRACTION_FALLBACK_MODEL` | empty | Optional fallback model for missing critical fields (bounded, one call). |
| `APP_VERACITY_ENABLED` | `true` | Veracity score computation and UI. |
| `APP_REVIEW_UI_ENABLED` | `true` | Review UI additions (veracity badge, inline thumbnail, side document). |
| `APP_ALIAS_CORROBORATION_MIN` | `2` | Independent observations before a learned alias activates. |
| `APP_PROFILE_QUALITY_FLOOR` | `0.5` | Profile quality below which it is not used for guidance. |
| `APP_PROFILE_DRIFT_THRESHOLD` | `0.3` | Anchor divergence that flags profile drift. |
| `APP_EVAL_REGRESSION_TOLERANCE` | `0.02` | Accuracy delta counted as regression in eval comparisons. |
| `APP_CODE_REVISION` | empty | Code revision stamped on evaluation runs. |
| `APP_QR_DECODE_ENABLED` | `false` | QR payload decoding during verification. |

## Paperless-ngx (app side)

See `docs/intake.md`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_PAPERLESS_URL` | `http://paperless:8000` | Internal API base URL. |
| `APP_PAPERLESS_UI_URL` | empty | Browser-reachable UI URL for the "view original" link; empty hides it. |
| `APP_PAPERLESS_TOKEN` | empty | API token (`Authorization: Token …`). |
| `APP_PAPERLESS_OTHER_TAG` | `Otros` | Tag for unrecognized/manual-review documents. |
| `APP_PAPERLESS_TIMEOUT_SECONDS` | `30` | HTTP timeout. |
| `APP_PAPERLESS_POLL_INTERVAL_SECONDS` | `1` | Task polling interval. |
| `APP_PAPERLESS_POLL_TIMEOUT_SECONDS` | `60` | Max wait for storage. |
| `APP_PAPERLESS_RETRIES` | `2` | Retries for retryable Paperless calls. |
| `APP_PAPERLESS_RETRY_BACKOFF_SECONDS` | `0.5` | Backoff base between retries. |
| `APP_PAPERLESS_SYNC_SECONDS` | `60` | Watcher sync interval. |
| `APP_PAPERLESS_WEBHOOK_TARGET` | derived | Callback URL provisioned in Paperless. |
| `APP_SYNC_OVERLAP_SECONDS` | `600` | Sync watermark overlap window. |
| `APP_CACHE_DIR` | `var/cache` | Django cache dir (gallery thumbnails). |

## Paperless-ngx (container settings)

Consumed by the `paperless` service in `compose.yaml`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `PAPERLESS_SECRET_KEY` | — | Paperless secret key. |
| `PAPERLESS_ADMIN_USER` / `PAPERLESS_ADMIN_PASSWORD` | `admin` / … | Paperless admin login. |
| `PAPERLESS_URL` | `http://localhost:9090` | Public URL Paperless advertises. |
| `PAPERLESS_OCR_LANGUAGE` | `spa+eng` | Paperless OCR languages. |
| `PAPERLESS_FILENAME_FORMAT` | `{{correspondent}}/{{title}}` | Paperless archive path template. |
| `PAPERLESS_CSRF_TRUSTED_ORIGINS` | — | CSRF origins for the Paperless UI. |

## Internal API and n8n

See `docs/security.md`, `docs/n8n.md`, and `docs/reporting.md`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_INTERNAL_API_TOKEN` | — | `X-Internal-Token` for `/internal/` endpoints. |
| `APP_N8N_PROCESSING_WEBHOOK_URL` | `http://n8n:5678/webhook/process-document` | n8n intake webhook. |
| `APP_N8N_REPORT_WEBHOOK_URL` | `http://n8n:5678/webhook/report-job` | n8n report webhook. |
| `APP_N8N_WEBHOOK_TOKEN` | — | Shared `X-Webhook-Token` between app and n8n. |
| `APP_N8N_WEBHOOK_TIMEOUT_SECONDS` | `10` | Webhook call timeout. |
| `N8N_ENCRYPTION_KEY` | — | n8n credentials encryption key. |
| `GENERIC_TIMEZONE` | `UTC` | n8n timezone. |
| `N8N_PROTOCOL` / `N8N_SECURE_COOKIE` | `http` / `false` | n8n UI scheme and cookie security; `deploy.sh` derives the cookie flag. |

## Inbox and recovery

See `docs/operations.md`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_INBOX_DIR` | `/data/inbox` | Watched folder (`./inbox` bind mount). |
| `APP_INBOX_POLL_SECONDS` | `10` | Inbox poll interval. |
| `APP_INBOX_SETTLE_SECONDS` | `2` | Seconds a file must keep stable size+mtime before intake reads it. |
| `APP_RECOVERY_INTERVAL_SECONDS` | `60` | Watcher recovery loop interval (`0` disables). |
| `APP_RECOVERY_STALE_SECONDS` | `1800` | Age before an item counts as stuck. |
| `APP_RECOVERY_MAX_ATTEMPTS` | `3` | Attempts before `recovery_attempts_exhausted`. |

## Email

See `docs/operations.md` (user management). Default console backend prints
reset emails to the app logs.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_EMAIL_BACKEND` | console backend | Django email backend dotted path. |
| `APP_EMAIL_HOST/PORT/HOST_USER/HOST_PASSWORD/USE_TLS` | — | SMTP settings. |
| `APP_DEFAULT_FROM_EMAIL` | `webmaster@localhost` | Sender address. |

Password-reset links expire after one hour (fixed `PASSWORD_RESET_TIMEOUT`).

## Logging

| Variable | Default | Purpose |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Root log level. |
| `LOG_FORMAT` | `keyvalue` | `keyvalue` or `json` output. |

## Field-label alias lifecycle

`FieldLabelAlias` rows carry a lifecycle (`candidate` → `active` /
`rejected`), a support count, a confidence, provenance, and an optional
entity scope. Only `active` aliases reach extraction.

- **Manual aliases** (taught from the review screen or the alias admin)
  are created `active` and are authoritative.
- **Learned aliases** start as `candidate` with `support_count=1`. Each
  additional observation from a *different* approved certificate raises
  support; at `APP_ALIAS_CORROBORATION_MIN` (default `2`) distinct
  observations the alias activates — unless the same printed label is
  already active for another field in the same scope, in which case it
  stays a candidate flagged `conflict` for a reviewer.
- **Reviewer corrections** can propose candidates scoped to the
  certificate's entity; they never activate without corroboration or an
  explicit **Confirmar** in `/aliases/` (reviewer+ only). **Rechazar**
  marks the alias `rejected` and it is never used again.
- Rejected documents never teach aliases.

### Pre-detection scoping

Before classification there is no resolved entity, so alias scope is
chosen in this order: the certificate's resolved entity (re-extraction),
then a confident pre-detection `match` (`aliases_for_pre_detection`),
otherwise global aliases only. An ambiguous pre-detection never applies
entity-scoped aliases speculatively.

## Verifier configuration

`VerifierConfig` stores per-issuer source-verification settings as data:
`host` (domain or parent domain matched against the certificate's
verification URL host), `url_template` (`{code}`, `{document_id}`, `{url}`
placeholders), `code_pattern` (regex), `success_criteria` JSON
(`{"markers": [...], "require_pdf": true}`), `source_document_parser`
(`pdf_text` extracts fields from a returned PDF for comparison),
`source_field_patterns` JSON (`{field: regex}` with one capture group),
`timeout_seconds` (1–120), and `is_active`. Seeded defaults for `uv.es`
and `tramita.gva.es` ship via `seed_catalog`; entity-scoped rows take
precedence over host-global rows for the same host.

Related flags: `APP_VERACITY_ENABLED` (veracity scoring),
`APP_REVIEW_UI_ENABLED` (review UI additions), `APP_QR_DECODE_ENABLED`
(optional QR decode), `APP_FORMAT_VERIFIED_WEIGHT` (verified-sample weight
in profiles), `APP_PROFILE_QUALITY_FLOOR` / `APP_PROFILE_DRIFT_THRESHOLD`
(profile quality gates).

## Runtime-editable settings

`/admin-panel/configuracion/` (admins only) edits a subset of `APP_*`
parameters without redeploying: Ollama URL/model/timeout/retries,
fallback model, OCR settings, Paperless/n8n endpoints and timeouts,
confidence and format thresholds, feature flags, inbox/sync timings,
and every other key consumed at request time.

How it works:

- Saving writes a `core.ProgramSetting` row and mirrors the value into
  the shared cache (`appcfg:v1:<key>`). `settings.APP` is an
  `AppSettings` dict that checks the cache before the environment
  default, so all gunicorn workers pick up the change immediately — no
  restart, no reload.
- Values are coerced to the type of the environment default
  (int/float/bool/list/string) and validated per field; invalid input is
  rejected with a per-key error.
- Each overridden row shows an `override` badge and a **restablecer**
  button; **Restablecer todos** clears every override at once.
- Overrides persist across restarts (DB is the source of truth; the
  cache is repopulated lazily on first read).

Not editable at runtime (shown read-only): values bound into Django
settings at startup (`media_root`, `report_output_dir`, `inbox_dir`,
`cache_dir`, all `APP_EMAIL_*`) and secrets (`*_token`, `*_password`,
`*_secret` — rendered as `•••`, never editable through the UI). Change
those in `.env` and restart the `app` container.

## Admin panel layout

`/admin-panel/` is an index of subsection pages:

- **Aprendizaje del emisor** (`/admin-panel/aprendizaje/`) — format
  profiles, field-label aliases, per-issuer verifier configs.
- **Usuarios y acceso** (`/admin-panel/usuarios/`) — user management,
  password change/reset.
- **Configuración del programa** (`/admin-panel/configuracion/`) —
  runtime-editable settings above; admins only.
