# Operations

All services run under `compose.yaml`. Only `app` (port `APP_PORT`, default
8080) and `n8n` (port 5678) publish ports; `db`, `redis`, `paperless`,
`ocr`, and `ollama` are reachable only on the internal `internal` network.

## Volumes

| Volume | Contents |
| --- | --- |
| `postgres-data` | All PostgreSQL databases (app, Paperless, n8n) |
| `paperless-data` / `paperless-media` / `paperless-consume` | Paperless index, files, consume dir |
| `n8n-data` | n8n credentials, workflows, executions |
| `ollama-models` | Downloaded Ollama models |
| `app-media` | Staged uploads |
| `reports` | Generated `.xlsx` workbooks |

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
3. **Paperless-ngx** — upload through the Paperless UI (`:9090`) or its
   `consume` folder. A Paperless workflow fires a webhook on *Document
   Added* to `POST /internal/paperless/webhook/` with header
   `X-Internal-Token`. The app downloads the original, deduplicates by
   SHA-256, creates the record already `stored`, and notifies n8n.

### Paperless webhook setup (automated in this deployment)

The workflow `App intake webhook` is provisioned in Paperless with:

- Trigger: *Document Added*, all sources.
- Action: Webhook `POST http://app:8000/internal/paperless/webhook/`,
  `as_json`, params `{"document_id": "{{ doc_id }}", "event": "document_added"}`,
  header `X-Internal-Token: $APP_INTERNAL_API_TOKEN`.

To recreate it manually: Paperless UI → Settings → Automation → Workflows →
add trigger *Document Added* + action *Webhook* with the values above.
