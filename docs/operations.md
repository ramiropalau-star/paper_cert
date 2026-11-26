# Operations

All services run under `compose.yaml`. Only `app` (port `APP_PORT`, default
8080) and `n8n` (port 5678) publish ports; `db`, `redis`, `paperless`,
`ocr`, and `ollama` are reachable only on the internal `internal` network.

### Service exposure

Paperless-ngx is internal by default: the app reaches it at
`http://paperless:8000` on the Docker network, so no host port is published.
To administer the Paperless UI locally, opt in to a loopback-only mapping in
`compose.yaml`:

```yaml
    ports:
      - "127.0.0.1:9090:8000"
```

For remote administration use an SSH tunnel
(`ssh -L 9090:127.0.0.1:9090 user@host`) or a reverse proxy — never publish
`0.0.0.0:9090`.

### Secrets and orchestration tokens

`.env` holds every secret; `deploy.sh` generates random values on first
deploy. Never commit `.env` or reuse the `change-me-*` placeholders outside
local development.

- `APP_INTERNAL_API_TOKEN` authenticates service-to-service calls to the
  app's `/internal/` endpoints (`X-Internal-Token` header).
- `APP_N8N_WEBHOOK_TOKEN` authenticates calls to the n8n orchestration
  webhooks (`/webhook/process-document`, `/webhook/report-job`). The app
  sends it as `X-Webhook-Token`; both bundled workflows reject requests
  without a matching token with HTTP 401 before any stage runs. The same
  value must be present in the app and n8n environments (both read `.env`).
- `DJANGO_SECRET_KEY` must be a long random value; the app refuses to start
  with the development default when `DEBUG=false`.

### n8n cookie security

`N8N_SECURE_COOKIE` must match the scheme operators use to reach the n8n
UI. `deploy.sh` derives it from `N8N_PROTOCOL` (`https` → `true`,
`http` → `false` plus a warning). For any non-local deployment put n8n
behind a TLS-terminating reverse proxy, set `N8N_PROTOCOL=https`, and keep
`N8N_SECURE_COOKIE=true`.

## Volumes

| Volume | Contents |
| --- | --- |
| `postgres-data` | All PostgreSQL databases (app, Paperless, n8n) |
| `paperless-data` / `paperless-media` / `paperless-consume` | Paperless index, files, consume dir |
| `n8n-data` | n8n credentials, workflows, executions |
| `ollama-models` | Downloaded Ollama models |
| `app-media` | Staged uploads |
| `reports` | Generated `.xlsx` workbooks |
| `app-cache` | Django file-based cache (thumbnails) |

## Fresh start

```bash
cp .env.example .env   # fill every change-me value
# generate strong secrets, e.g.:
#   openssl rand -hex 32

docker compose up -d db redis
docker compose run --rm app python manage.py bootstrap   # migrate + seed + admin
docker compose up -d                                 # remaining services
docker compose exec ollama ollama pull qwen2.5:7b-instruct
```

Then import the n8n workflows (see `docs/n8n.md`), log in at
`http://localhost:8080`, and upload a certificate.

The Paperless *Document Added* webhook is provisioned automatically: the
`bootstrap` command attempts it (best-effort while Paperless is still
booting) and the `watcher` service retries on startup and every sync cycle
until it succeeds. To run it manually at any time:

```bash
docker compose exec app python manage.py provision_paperless_webhook
```

## Backup

```bash
# PostgreSQL dump (covers app, Paperless, and n8n databases)
docker compose exec db pg_dumpall -U "$DB_USER" > backup-$(date +%F).sql

# Volume archives
docker run --rm -v paperless-certs_postgres-data:/v -v "$PWD":/backup alpine \
  tar czf /backup/postgres-data.tgz -C /v .
docker run --rm -v paperless-certs_paperless-data:/v -v "$PWD":/backup alpine \
  tar czf /backup/paperless-data.tgz -C /v .
docker run --rm -v paperless-certs_paperless-media:/v -v "$PWD":/backup alpine \
  tar czf /backup/paperless-media.tgz -C /v .
docker run --rm -v paperless-certs_reports:/v -v "$PWD":/backup alpine \
  tar czf /backup/reports.tgz -C /v .
```

Store dumps and archives off-host. The Ollama model volume is reproducible
(`ollama pull`) and does not need backups.

## Restore

```bash
docker compose down
docker compose up -d db
# restore the dump into the fresh postgres volume
docker compose exec -T db psql -U "$DB_USER" -d postgres < backup-YYYY-MM-DD.sql
# or restore volume archives into named volumes before `up`
docker compose up -d
```

## Updates

Images are pinned in `compose.yaml`. To update:

1. Review the changelog of each pinned tag and bump the tags deliberately.
2. `docker compose pull`
3. `docker compose run --rm app python manage.py migrate`
4. `docker compose up -d`

Never run `docker compose pull` without pinning first — unpinned `latest`
tags make rollbacks impossible.

## Routine checks

```bash
docker compose ps                     # all services healthy
docker compose logs -f app ocr n8n    # pipeline errors surface here
curl -s http://localhost:8080/healthz # app liveness
curl -s http://localhost:8080/internal/healthz -H "X-Internal-Token: $APP_INTERNAL_API_TOKEN"
```

Documents stuck in `error` can be retried from the review UI
(**Reprocesar**) or by replaying the n8n execution.

### User management

The deploy bootstrap creates a single `admin` superuser. Additional users are
managed from the app itself at `/users/` (visible only to the `admin` role):
create accounts with one role (`viewer`, `reviewer`, or `admin`), edit roles,
reset passwords, and activate/deactivate. Every signed-in user can change
their own password from **Cambiar contraseña** in the nav, and the login page
offers a password-reset flow.

Password-reset emails use the console email backend by default — the message
is printed to the `app` container logs (`docker compose logs -f app`). To
deliver real email, set `APP_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
plus `APP_EMAIL_HOST`, `APP_EMAIL_PORT`, `APP_EMAIL_HOST_USER`,
`APP_EMAIL_HOST_PASSWORD`, `APP_EMAIL_USE_TLS`, and `APP_DEFAULT_FROM_EMAIL`
in `.env`. Reset links expire after one hour (`PASSWORD_RESET_TIMEOUT`).

Django admin at `/admin/` remains available to superusers only; regular users
(including the `admin` group) cannot open it — use `/users/` instead.

### Stuck-work recovery

The `watcher` service runs recovery every `APP_RECOVERY_INTERVAL_SECONDS`
(default `60`, `0` disables the loop). A document or report job untouched for
longer than `APP_RECOVERY_STALE_SECONDS` (default `1800`) is recovered:

- Documents in `stored`, `text_ready`, or `extracted` are requeued through the
  n8n pipeline; each attempt increments `recovery_attempts`.
- Documents in `received` are moved to `error` with
  `recovery_orphaned_received` because the staged upload no longer exists.
- Report jobs in `queued`/`running` are retried locally via `run_report_job`;
  each attempt increments `attempts`.
- After `APP_RECOVERY_MAX_ATTEMPTS` (default `3`) a stale item moves to
  `error` with `recovery_attempts_exhausted` and is no longer retried.

Manual inspection and runs:

```bash
docker compose exec app python manage.py recover_stuck --dry-run   # list only
docker compose exec app python manage.py recover_stuck             # real run
docker compose exec app python manage.py recover_stuck --older-than 600 --max-attempts 5
docker compose exec app python manage.py recover_stuck --documents-only
```

Recovery events are logged as `recovery_run`, `recovery_document_requeued`,
`recovery_document_failed`, `recovery_report_retried`, and
`recovery_report_failed` with `document_id`/`report_id` correlation fields.

## Smoke test

`scripts/smoke.sh` exercises the full stack against the committed fixtures:

```bash
./scripts/smoke.sh
```

It waits for the app health endpoint, logs in, uploads
`text-certificate.pdf`, `scanned-certificate.pdf`, and `certificate.png`,
waits for n8n to drive them to `pending_review`, approves them, generates a
report job, runs it, and downloads the resulting `.xlsx` to
`report-smoke.xlsx`. Requires a completed first-time setup (see above) with
the Ollama model pulled and the n8n workflows imported.

## Intake channels

Documents enter the pipeline through any of these paths; all of them end in
the same dedup → Paperless storage → n8n → review flow.

1. **Web upload** — `Subir certificado` accepts multiple files per request.
2. **Inbox folder** — copy files into `./inbox/` on the host. The `watcher`
   service polls `APP_INBOX_DIR` (default every `APP_INBOX_POLL_SECONDS=10`s),
   ingests them through the normal pipeline, and moves them to
   `inbox/processed/` or `inbox/failed/`.
3. **Paperless-ngx** — upload through the Paperless UI (requires the
   optional loopback port mapping above) or its `consume` folder. A
   Paperless workflow fires a webhook on *Document Added* to
   `POST /internal/paperless/webhook/` with header
   `X-Internal-Token`. The app downloads the original, deduplicates by
   SHA-256, creates the record already `stored`, and notifies n8n.

### Paperless sync watermark and thumbnails

The `watcher` service reconciles Paperless every
`APP_PAPERLESS_SYNC_SECONDS` (default 60s). Instead of listing the whole
archive each run, the sync persists a watermark in `PaperlessSyncState`
(`documents_paperlesssyncstate` table) and requests only documents with
`added__gte = last_added - APP_SYNC_OVERLAP_SECONDS` (default 600s). The
first run after deploy — or any run when the watermark is empty — is a full
listing.

Watermark rules:

- A successful listing with no ingest errors advances the watermark to the
  newest `added` seen.
- Ingest errors advance it only to the oldest failed document's `added`
  minus the overlap, so the bad document is retried without hiding newer
  ones.
- A listing failure leaves the watermark unchanged.

Manual commands:

```bash
# incremental run (same as the watcher)
docker compose exec app python manage.py sync_paperless
# full reconcile: ignores the watermark, repairs missing local documents
docker compose exec app python manage.py sync_paperless --full
```

Run `sync_paperless --full` once after deploying this change to establish
the baseline; the watcher then stays incremental. If a Paperless version
rejects the `added__gte` filter (HTTP 400), the sync logs
`sync_filter_unsupported` and falls back to a full listing automatically.

Gallery thumbnails are cached in the Django cache
(`APP_CACHE_DIR`, default `var/cache`; `/data/cache` volume in compose)
under `thumbnail:{paperless_id}:{updated_at}` for 24 hours. A cache hit
makes no Paperless call; a document update changes the key and refetches.
On a Paperless failure the endpoint returns a placeholder SVG with HTTP
200 so the gallery keeps working.

### Paperless webhook setup (automated in this deployment)

The workflow `App intake webhook` is provisioned in Paperless with:

- Trigger: *Document Added*, all sources.
- Action: Webhook `POST http://app:8000/internal/paperless/webhook/`,
  `as_json`, params `{"document_id": "{{ doc_id }}", "event": "document_added"}`,
  header `X-Internal-Token: $APP_INTERNAL_API_TOKEN`.

To recreate it manually: Paperless UI → Settings → Automation → Workflows →
add trigger *Document Added* + action *Webhook* with the values above.
