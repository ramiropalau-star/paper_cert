# Certificados de idiomas

Self-hosted pipeline that ingests language certificates (PDF/images), stores
the originals in Paperless-ngx, extracts structured fields with a local
Ollama model, classifies them against an editable catalog, routes uncertain
records to human review, and produces Excel reports.

The system learns from every approved or validated certificate — see
[Review-driven learning](#review-driven-learning).

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

## Review-driven learning

Every approved or validated certificate teaches the catalog (post-commit,
never blocking the decision, fully idempotent):

- **Aliases** — printed literals that resolved to catalog entries are saved
  as `LanguageAlias`/`EntityAlias`/`ExamAlias`, so the next document with the
  same wording classifies automatically. Conflicting aliases are never
  overwritten; they are recorded as conflicts in the learning outcome.
- **Missing exams** — a manually assigned exam on an unknown literal creates
  the `Exam` entry (scoped to entity + language). New *entities* are still
  created via the Django admin.
- **Equivalences** — a manually corrected UV L2 level creates an unbanded
  `Equivalence` rule (`source="review"`) when none exists for that exam.
- **CEFR rules** — a manually corrected CEFR level creates an *inactive*
  `CefrConversionRule` candidate pinned to the observed score; a human must
  widen the band and activate it.

The outcome of each learning run is stored in the approve/validate
`ReviewEvent`, and rejected or unapproved certificates never teach.

### Format profiles

Each entity accumulates a textual format profile per **issuance year**
(cohort), built from the normalized boilerplate lines of its approved
certificates. An anchor only counts when corroborated by at least two
approved samples or half the cohort, whichever is stricter — legitimate
year-to-year layout drift is absorbed by separate cohorts, and single-document
quirks never define a format.

During classification, `score_document_format` matches the document's page
text against the profile of its claimed entity/year (falling back to the
entity-wide union, with a cross-entity penalty cap) and stores
`certificate.format_score` + `format_cohort`. The score blends 30% into
`certificate.confidence`, and a score below `APP_FORMAT_SCORE_THRESHOLD`
(default `0.4`) emits the `format_mismatch` review reason — so a plain-text
PDF with plausible fields cannot pass as a genuine certificate.

Relevant settings: `APP_FORMAT_MIN_SAMPLES` (2), `APP_FORMAT_MIN_EXAM_SAMPLES`
(3), `APP_FORMAT_SCORE_THRESHOLD` (0.4), `APP_FORMAT_MAX_SCORE` (0.5).

### Backfill

```bash
docker compose exec app python manage.py learn_from_history --dry-run
docker compose exec app python manage.py learn_from_history
```

Replays catalog + format learning over already-approved/validated
certificates. Idempotent — safe to re-run; `--dry-run` reports without
writing.

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
