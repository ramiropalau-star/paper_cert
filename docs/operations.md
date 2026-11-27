# Operations

All services run under `compose.yaml`. The `app` port (`APP_PORT`, default
8080) is the user entry point and binds `APP_BIND_ADDR` (default `0.0.0.0`).
The `n8n` UI (port 5678) is administrative and binds `N8N_BIND_ADDR`
(default `127.0.0.1` — loopback only). `db`, `redis`, `paperless`,
`ocr`, and `ollama` are reachable only on the internal `internal` network.

### Port bindings

Published ports accept an optional bind address via `.env`:

| Variable | Default | Controls |
| --- | --- | --- |
| `APP_BIND_ADDR` | `0.0.0.0` | Interface/IP the app port listens on |
| `N8N_BIND_ADDR` | `127.0.0.1` | Interface/IP the n8n UI listens on |

Set `N8N_BIND_ADDR=0.0.0.0` only for direct LAN access to the n8n UI;
prefer loopback plus an SSH tunnel or reverse proxy. After changing a bind
address, recreate the service: `docker compose up -d n8n` (or `app`).

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

Then log in at `http://localhost:8080` and upload a certificate.

### deploy.sh

`deploy.sh` automates the whole bootstrap: generates `.env` secrets on first
run, builds and starts the stack, runs migrations and the catalog/admin seed,
pulls the Ollama model, imports and activates the n8n workflows, and runs the
smoke test. Options (environment variables):

| Variable | Default | Purpose |
| --- | --- | --- |
| `DEPLOY_HOST` | auto-detected first IP | Public IP/hostname written into `.env`. |
| `DEPLOY_ADMIN_PASSWORD` | `admin` | Django + Paperless admin password. |
| `SKIP_MODEL` | unset | `1` skips the Ollama model pull. |
| `SKIP_SMOKE` | unset | `1` skips the end-to-end smoke test. |
| `FORCE_ENV` | unset | `1` regenerates `.env` even if it exists. |
| `DEPLOY_GPU` | `auto` | `auto`/`gpu`/`cpu` — see GPU deployment below. |

#### GPU deployment

Ollama uses the CPU by default. With an NVIDIA GPU and the
`nvidia-container-toolkit` installed, `deploy.sh` detects them
(`DEPLOY_GPU=auto`) and layers `compose.gpu.yaml` on top of `compose.yaml`,
registers the CDI device spec, and recreates `ollama` on the GPU. `DEPLOY_GPU=gpu`
forces the override; `DEPLOY_GPU=cpu` forces CPU. After pulling the model the
script verifies in the Ollama logs that inference actually lands on the GPU —
if not, it warns and keeps CPU. Without a GPU or toolkit the stack runs on CPU
unchanged.

For a manual GPU deploy: `docker compose -f compose.yaml -f compose.gpu.yaml up -d`.

#### Extraction model selection

`APP_OLLAMA_MODEL` defaults to `qwen2.5:7b-instruct`. The choice was validated
empirically (November 2026) by replaying the real extraction prompt — same
system prompt, JSON schema, and page-evidence validation — over the 13
certificates awaiting review, once per candidate model. Three metrics were
recorded per document: wall-clock latency, extraction rejections caused by
unverifiable evidence quotes, and field-level agreement with the stored
extraction.

| Model | Size | Avg. latency | Rejected extractions | Field agreement |
| --- | --- | --- | --- | --- |
| `qwen2.5:7b-instruct` (chosen) | 4.7 GB | ~22 s | 5/13 | 47/53 |
| `qwen2.5:3b-instruct` | 1.9 GB | ~18 s | 10/13 | 7/20 |
| `qwen2.5:1.5b-instruct` | 1.0 GB | ~10 s* | 4/13 | 30/62 |
| `llama3.2:3b` | 2.0 GB | ~16 s | 8/13 | 17/32 |
| `mistral:7b-instruct` | 4.4 GB | ~29 s | 11/13 | 5/13 |

\* One document timed out at the 180 s transport limit.

Smaller models fail mainly through hallucinated evidence quotes: the strict
page-evidence validation rejects the whole extraction when a quoted string
does not appear verbatim on the cited page, so weak models produce unusable
output rather than merely imperfect fields. The 1.5B model was fastest but
also returned plausible-looking invented values (e.g. scores absent from the
document), which is worse than a rejection because it reaches the review
queue looking valid. `mistral:7b-instruct` was both slower and less accurate
than the incumbent. No tested alternative improved score/date capture on the
hardest document in the corpus — a trilingual certificate layout that the
7B model also only partially extracts — so the gap is document-specific, not
a model-size issue.

Conclusion: keep `qwen2.5:7b-instruct` on GPU (~20 s/document). If GPU is
unavailable, `qwen2.5:3b-instruct` is the least-bad CPU fallback but expect
roughly three quarters of documents to need manual re-extraction. Re-run the
comparison before adopting any newer model (e.g. qwen3 or gemma3).

The Paperless *Document Added* webhook is provisioned automatically: the
`bootstrap` command attempts it (best-effort while Paperless is still
booting) and the `watcher` service retries on startup and every sync cycle
until it succeeds. To run it manually at any time:

```bash
docker compose exec app python manage.py provision_paperless_webhook
```

## Backup

`scripts/backup.sh` captures everything needed to restore the stack:

- `db.sql.gz` — `pg_dumpall` of all PostgreSQL databases (app, Paperless,
  n8n). This is the authoritative database backup; the `postgres-data`
  volume is intentionally not archived.
- One `.tar.gz` per stateful volume: `app-media`, `reports`,
  `paperless-data`, `paperless-media`, `n8n-data`.

Output goes to `./backups/<timestamp>/`. Backups older than
`BACKUP_RETENTION_DAYS` (default `14`) are pruned automatically. The Ollama
model volume is reproducible (`ollama pull`) and is not backed up.

```bash
./scripts/backup.sh
```

Schedule it daily, for example:

```cron
0 3 * * * cd /path/to/paperless && ./scripts/backup.sh >> backups/backup.log 2>&1
```

Copy `backups/` off-host (rsync, object storage, etc.) — local backups do
not survive disk or host loss.

## Restore

```bash
docker compose down
# 1. Restore volumes first (while db is still down)
for v in app-media reports paperless-data paperless-media n8n-data; do
  docker run --rm -v "paperless-certs_$v":/v -v "$PWD/backups/<timestamp>":/backup alpine \
    sh -c "rm -rf /v/* /v/.[!.]* 2>/dev/null; tar xzf /backup/$v.tar.gz -C /v"
done
# 2. Start only the database and restore the dump
docker compose up -d db
zcat backups/<timestamp>/db.sql.gz | docker compose exec -T db psql -U "$DB_USER" -d postgres
# 3. Start the rest
docker compose up -d
```

`pg_dumpall` output contains `\connect <db>` directives, so pipe it
directly to `psql -d postgres` — do not extract per-database sections
manually. Volume names assume the default Compose project
(`paperless-certs`); adjust if `COMPOSE_PROJECT_NAME` differs.

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
./scripts/health.sh                    # per-service health table (exit 1 if any unhealthy)
docker compose ps                     # all services healthy
docker compose logs -f app ocr n8n    # pipeline errors surface here
curl -s http://localhost:8080/healthz # app liveness
curl -s http://localhost:8080/internal/healthz -H "X-Internal-Token: $APP_INTERNAL_API_TOKEN"
```

Container logs are bounded: every service uses the json-file driver with
`max-size: 10m` / `max-file: 3` (see the `x-logging` anchor in
`compose.yaml`), so logs cannot fill the disk.

Documents stuck in `error` can be retried from the review UI
(**Reprocesar**) or by replaying the n8n execution.

After catalog changes (new entities, exams, aliases, equivalences), pending
documents can be reclassified without re-uploading:

```bash
docker compose exec app python manage.py reclassify_certificates            # pending_review only
docker compose exec app python manage.py reclassify_certificates --reextract  # also re-run LLM extraction
docker compose exec app python manage.py reclassify_certificates --document 42 --document 43
```

### Logging

`LOG_LEVEL` (default `INFO`) and `LOG_FORMAT` (`keyvalue` or `json`) control
the app's structured logs. `RequestIdMiddleware` propagates an
`X-Request-ID` header (or a generated id) through the request so log lines
carry a correlation id. See `core/logging.py` and `core/middleware.py`.

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
docker compose exec app python manage.py recover_stuck --reports-only
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

## Production deployment

The defaults are safe for a trusted LAN. For anything exposed beyond it,
apply this checklist:

### Credentials

- `deploy.sh` generates a random admin password on first deploy, writes it
  to `.env` (`DJANGO_SUPERUSER_PASSWORD`, shared with
  `PAPERLESS_ADMIN_PASSWORD`) and shows it once in the final summary.
  Change it after first login via `/users/` or the Paperless UI, and
  update `.env` accordingly.
- For a throwaway test deployment you may set
  `DEPLOY_ADMIN_PASSWORD=admin`, but `manage.py bootstrap` will still
  reject it unless you also set `BOOTSTRAP_ALLOW_WEAK_PASSWORD=1` in
  `.env`. Never use this combination outside local testing.
- `manage.py bootstrap` validates the superuser password with Django's
  password validators and refuses weak values. For local tests only, set
  `BOOTSTRAP_ALLOW_WEAK_PASSWORD=1`.
- Rotate any `change-me-*` placeholder in `.env` — `deploy.sh` already
  generates random values for all secrets on first deploy.

### HTTPS

Terminate TLS at a reverse proxy and keep the containers on HTTP internally.
Example with Caddy:

```caddy
app.example.com {
    reverse_proxy localhost:8080    # APP_PORT
}
n8n.example.com {
    reverse_proxy localhost:5678    # requires N8N_BIND_ADDR reachable by the proxy
}
```

Then set in `.env` and recreate the app and n8n:

```dotenv
APP_SCHEME=https                  # secure cookies, SSL redirect and HSTS follow automatically
DJANGO_CSRF_TRUSTED_ORIGINS=https://app.example.com
DJANGO_ALLOWED_HOSTS=app.example.com,localhost,127.0.0.1
N8N_PROTOCOL=https
N8N_SECURE_COOKIE=true
```

`APP_SCHEME=https` turns on `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
`SECURE_SSL_REDIRECT`, and HSTS by default; the individual `DJANGO_SECURE_*`
variables remain available as explicit overrides. `SECURE_PROXY_SSL_HEADER`
is already configured, so Django trusts `X-Forwarded-Proto` from the proxy —
only enable `SECURE_SSL_REDIRECT` when the proxy actually sets it. Paperless-ngx stays internal; expose
its UI only via SSH tunnel or a separate authenticated proxy path.

### Exposure

- Keep `N8N_BIND_ADDR=127.0.0.1` unless you deliberately expose the n8n UI;
  with a reverse proxy, proxy to `127.0.0.1:5678`.
- Restrict `APP_BIND_ADDR` if the app should only be reachable through the
  proxy (e.g. `APP_BIND_ADDR=127.0.0.1` and let the proxy connect locally).
- `db`, `redis`, `paperless`, `ocr`, and `ollama` never publish ports.

### Backups and health

- Schedule `./scripts/backup.sh` via cron (see *Backup*) and copy
  `backups/` off-host.
- Run `./scripts/health.sh` from monitoring or cron; it exits non-zero when
  any service is unhealthy.
