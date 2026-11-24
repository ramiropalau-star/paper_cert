# Certificados de idiomas

Self-hosted pipeline that ingests language certificates (PDF/images), stores
the originals in Paperless-ngx, extracts structured fields with a local
Ollama model, classifies them against an editable catalog, routes uncertain
records to human review, and produces Excel reports.

## Stack

Django 5 + PostgreSQL + Paperless-ngx (document store) + Ollama (extraction,
GPU-accelerated when available) + an isolated OCR service + n8n
(orchestration), all under Docker Compose.

## Quick start

```bash
./deploy.sh
```

`deploy.sh` performs the whole deployment:

1. Preflight checks (docker, disk space).
2. Generates `.env` with random secrets (skipped if `.env` already exists —
   use `FORCE_ENV=1` to regenerate).
3. Starts `db`, `redis` and `paperless`, waits for healthy, then requests a
   fresh Paperless API token and writes it to `.env`.
4. Runs migrations, catalog seed and admin bootstrap.
5. Starts the full stack and waits for all services to be healthy.
6. Pulls the Ollama model `qwen2.5:7b-instruct` (~4.7 GB).
7. Imports and activates the n8n workflows from `n8n/workflows/`.
8. Verifies the Paperless webhook and runs an end-to-end smoke test.

### Options

| Variable | Effect |
| --- | --- |
| `DEPLOY_HOST` | Public IP/hostname (default: auto-detected) |
| `DEPLOY_ADMIN_PASSWORD` | Django + Paperless admin password (default: `admin`) |
| `DEPLOY_GPU` | `auto` (default) detects NVIDIA + container toolkit; `gpu` forces CUDA; `cpu` forces CPU |
| `SKIP_MODEL=1` | Skip the Ollama model pull |
| `SKIP_SMOKE=1` | Skip the end-to-end smoke test |
| `SKIP_GPU_CHECK=1` | Skip the runtime GPU verification |
| `FORCE_ENV=1` | Regenerate `.env` even if it exists |

When a GPU is detected, `compose.gpu.yaml` is merged automatically so Ollama
runs on CUDA. After the model pull, the script loads it once and checks
`ollama ps`: if the GPU is not actually used, the `ollama` service is
recreated without the GPU override so the stack always picks the best
available option.

## After deploy

- Django app: `http://<host>:8090` (credentials in `.env`)
- Paperless UI: `http://<host>:9090`
- n8n: `http://<host>:5678`
- Inbox folder: `./inbox/` — copy files there and the watcher picks them up

Certificates can also be uploaded from **Documentos → Subir**. n8n runs the
pipeline (text acquisition → OCR if needed → extraction → classification)
and records land in **pending review**. The review UI offers a gallery with
filters, bulk validation/approval, inline editing, prev/next navigation and
rejection with a reason. Approved records feed the Excel reports under
**Reportes**, including a "Rechazados" sheet with rejection reasons.

## Documentation

- [Operations](docs/operations.md) — backup, restore, updates, health checks
- [n8n](docs/n8n.md) — workflow import, credentials, recovery
- [Intake](docs/intake.md) — upload validation, formats, deduplication
- [Text acquisition](docs/text-acquisition.md) — embedded text vs OCR
- [OCR service](docs/ocr.md) — isolated OCR endpoint contract
- [Extraction](docs/extraction.md) — Ollama prompts, schema, retries
- [Classification](docs/classification.md) — catalog matching, CEFR, dates
- [Review](docs/review.md) — queue, gallery, edits, approval, audit history
- [Reporting](docs/reporting.md) — Excel workbooks, filters, sheets
- [Security](docs/security.md) — auth, roles, internal API
- [Data model](docs/data-model.md) — entities and state machine
- [Development](docs/development.md) — local setup and tests

## Local development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
DJANGO_SETTINGS_MODULE=config.settings_test .venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```
