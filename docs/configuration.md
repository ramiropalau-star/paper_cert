# Configuration reference

Every tunable lives in `.env` (copy `.env.example` on first deploy). This page
is the complete variable reference; per-feature details live in the linked
docs. Secrets must be long random values — `deploy.sh` generates them on
first run.

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
