# n8n orchestration

n8n sequences the pipeline; Django owns all business logic. Flows call
authenticated internal endpoints by id — payloads carry ids only, never
document bytes.

## Workflows

Exported JSON lives in `n8n/workflows/`:

- `processing.json` — **Certificate Processing Pipeline**
  - Webhook `POST /webhook/process-document` receives `{"document_id": N}`
    (the app posts this after a successful upload or reprocess).
  - `Acquire text` → `POST /internal/documents/<id>/text/`
  - `Extract fields (Ollama)` → `POST /internal/documents/<id>/extract/`
  - `Classify against catalog` → `POST /internal/documents/<id>/classify/`
  - Success and error branches respond to the webhook. Each HTTP node has
    bounded retries (`retryOnFail`, `maxTries` 2–3); on final failure the
    error branch responds and the app-side state remains `error` /
    `pending_review` as set by the service layer.

- `report.json` — **Certificate Report Generation**
  - Webhook `POST /webhook/report-job` receives `{"report_job_id": N}`
    (posted by the app when a report job is created).
  - `Run report job` → `POST /internal/report-jobs/<id>/run/` (idempotent:
    a `ready` job is returned unchanged).

## Credentials and variables

Create these as n8n **Variables** (Settings → Variables) after import:

| Variable | Value |
| --- | --- |
| `APP_INTERNAL_URL` | `http://app:8000` (compose network name) |
| `APP_INTERNAL_API_TOKEN` | same value as `APP_INTERNAL_API_TOKEN` in `.env` |

App-side `.env` keys:

- `APP_INTERNAL_API_TOKEN` — shared secret sent as `X-Internal-Token`.
- `APP_N8N_PROCESSING_WEBHOOK_URL` — e.g. `http://n8n:5678/webhook/process-document`.
- `APP_N8N_REPORT_WEBHOOK_URL` — e.g. `http://n8n:5678/webhook/report-job`.
- `APP_N8N_WEBHOOK_TOKEN` — optional token echoed back to n8n webhooks
  (`X-Webhook-Token` header on outbound triggers).

## Import

1. Start n8n (`docker compose up -d n8n`) and open `http://localhost:5678`.
2. Workflows → Import from File → select each JSON in `n8n/workflows/`.
3. Activate both workflows.
4. Create the two variables above with the values from `.env`.

## Failure handling and recovery

- Each internal endpoint is idempotent per document state: calling
  `text`/`extract`/`classify` again on an already-processed document
  returns `skipped`/`refused` without duplicating rows.
- If a flow execution fails mid-pipeline, the document keeps its last
  persisted state; fix the cause (Ollama down, bad scan) and either replay
  the n8n execution or use **Reprocesar** in the review UI, which resets the
  document to `stored` and re-triggers the webhook.
- Report jobs: a failed or unfinished job can be re-run by calling the run
  endpoint again; `ready` jobs are never regenerated.
- To re-trigger processing manually:
  `curl -X POST -H "X-Internal-Token: $APP_INTERNAL_API_TOKEN" http://localhost:8000/internal/documents/<id>/classify/`
