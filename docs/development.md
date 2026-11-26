# Development

## Requirements

- Python 3.12 in Docker; local development works with Python 3.11+.
- Docker Engine and Docker Compose for the full stack.
- No local PostgreSQL is required for tests: the test settings use in-memory SQLite.

## Local setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/python manage.py check
.venv/bin/python manage.py migrate
```

The default settings expect PostgreSQL when `DB_ENGINE=postgres`. For a local SQLite run without Docker:

```bash
DB_ENGINE=sqlite DJANGO_DEBUG=true .venv/bin/python manage.py migrate
DB_ENGINE=sqlite DJANGO_DEBUG=true .venv/bin/python manage.py runserver
```

## Tests and lint

```bash
.venv/bin/ruff check .
.venv/bin/pytest
```

`pytest.ini` selects `config.settings_test`, which uses in-memory SQLite, a temporary media root, and fake service URLs. External services are mocked with `respx`; no Paperless, n8n, Ollama, or OCR container is needed for unit tests.

## Layout

- `config/`: Django settings, URL root, WSGI/ASGI entry points.
- `core/`: health endpoint, landing page, shared templates and static assets.
- `catalog/`: languages, certifying entities, aliases, exams, equivalences,
  CEFR rules, and format profiles.
- `documents/`: document and certificate models, intake, text acquisition,
  extraction, classification, review views, and Paperless sync.
- `reports/`: report jobs and Excel generation.
- `accounts/`: user management views on top of Django auth.
- `ocr-service/`: standalone OCR HTTP service.
- `n8n/workflows/`: exported n8n workflows.
- `docker/`: Dockerfiles.
- `deploy.sh`, `compose.yaml`, `compose.gpu.yaml`: deployment.
- `scripts/`: smoke test and helper scripts.
- `inbox/`: watched intake folder (bind-mounted into the watcher).
- `docs/`: operational and design documentation.
- `tests/`: cross-cutting tests; each app keeps its own tests next to the code.

## Environment

All runtime configuration comes from environment variables. See `.env.example` for the complete list. Key groups: Django, database, upload and pipeline thresholds, OCR, Ollama, Paperless, internal API, and n8n webhooks.
