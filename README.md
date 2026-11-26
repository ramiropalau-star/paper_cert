# Certificados de idiomas

Self-hosted pipeline that ingests language certificates (PDF/images), stores
the originals in Paperless-ngx, extracts structured fields with a local
Ollama model, classifies them against an editable catalog, routes uncertain
records to human review, and produces Excel reports.

The system learns from every approved or validated certificate: printed
literals become catalog aliases, manual equivalence/CEFR corrections become
rules, and each issuer accumulates a per-year format profile that scores
future documents and can flag `format_mismatch` for review. See
[Review → Learning from review](docs/review.md#learning-from-review) and
`python manage.py learn_from_history` for backfilling from history.

## Stack

Django 5 + PostgreSQL + Paperless-ngx (document store) + Ollama (extraction)
+ an isolated OCR service + n8n (orchestration), all under Docker Compose.

## Quick start

```bash
cp .env.example .env
# edit .env: replace every change-me-* value (deploy.sh generates random
# secrets on first deploy) and set N8N_PROTOCOL to the public scheme of the
# n8n UI (http locally, https behind a reverse proxy)

./deploy.sh   # one-shot: env, build, bootstrap, workflows, smoke test

# Manual equivalent:
docker compose up -d db redis
docker compose run --rm app python manage.py bootstrap
docker compose up -d
docker compose exec ollama ollama pull qwen2.5:7b-instruct
```

Open `http://localhost:8080`, log in with the superuser credentials, and
upload a certificate from **Documentos → Subir**. n8n picks it up, runs
text acquisition → extraction → classification, and the record lands in
**pending review**. Approve it in the review UI, then generate a report
under **Reportes**.

Import the n8n workflows from `n8n/workflows/` — see
[docs/n8n.md](docs/n8n.md).

## Documentation

- [Operations](docs/operations.md) — backup, restore, updates, health checks
- [n8n](docs/n8n.md) — workflow import, credentials, recovery
- [Intake](docs/intake.md) — upload validation and deduplication
- [Text acquisition](docs/text-acquisition.md) — embedded text vs OCR
- [OCR service](docs/ocr.md) — isolated OCR endpoint contract
- [Extraction](docs/extraction.md) — Ollama prompts, schema, retries
- [Classification](docs/classification.md) — catalog matching, CEFR, dates
- [Review](docs/review.md) — queue, edits, approval, audit history
- [Reporting](docs/reporting.md) — Excel workbooks, filters, pending sheet
- [Security](docs/security.md) — auth, roles, internal API
- [Data model](docs/data-model.md) — entities and state machine
- [Development](docs/development.md) — local setup and tests

## Local development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
DJANGO_SETTINGS_MODULE=config.settings_test .venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```
