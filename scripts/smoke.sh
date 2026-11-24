#!/usr/bin/env bash
# Compose smoke test: upload fixtures, run the pipeline via n8n, approve,
# and produce a downloadable Excel report.
#
# Prerequisites: `docker compose up -d` completed, Ollama model pulled,
# n8n workflows imported and activated (docs/n8n.md), .env filled in.
set -euo pipefail

# shellcheck disable=SC1091
set -a; . ./.env; set +a
APP_URL="${APP_URL:-http://localhost:${APP_PORT:-8080}}"
FIXTURES_DIR="$(cd "$(dirname "$0")/../tests/fixtures/files" && pwd)"
JAR="$(mktemp)"
trap 'rm -f "$JAR"' EXIT

echo "== health =="
for i in $(seq 1 60); do
  curl -fsS "$APP_URL/healthz" >/dev/null && break
  sleep 2
done
curl -fsS "$APP_URL/healthz"

echo "== login =="
curl -fsS -c "$JAR" "$APP_URL/accounts/login/" -o /dev/null
CSRF=$(grep csrftoken "$JAR" | awk '{print $7}')
curl -fsS -b "$JAR" -c "$JAR" -X POST "$APP_URL/accounts/login/" \
  --data-urlencode "csrfmiddlewaretoken=$CSRF" \
  --data-urlencode "username=${DJANGO_SUPERUSER_USERNAME}" \
  --data-urlencode "password=${DJANGO_SUPERUSER_PASSWORD}" \
  -o /dev/null
# Django rotates the CSRF token on login; re-read the fresh cookie value.
CSRF=$(grep csrftoken "$JAR" | awk '{print $7}')

echo "== upload fixtures =="
for f in text-certificate.pdf scanned-certificate.pdf certificate.png; do
  curl -fsS -b "$JAR" -X POST "$APP_URL/documents/upload/" \
    -F "csrfmiddlewaretoken=$CSRF" \
    -F "document=@$FIXTURES_DIR/$f" -o /dev/null
  echo "uploaded $f"
done

echo "== waiting for pipeline (n8n) =="
for i in $(seq 1 120); do
  PENDING=$(docker compose exec -T app python manage.py shell -c \
    "from documents.models import Document; print(Document.objects.filter(processing_state='pending_review').count())" | tail -1)
  [ "$PENDING" -ge 3 ] && break
  sleep 5
done
echo "pending_review documents: $PENDING"

echo "== approve all pending =="
docker compose exec -T app python manage.py shell <<'PY'
from documents.models import Document
from documents.services.review import approve_certificate
for doc in Document.objects.filter(processing_state="pending_review"):
    cert = getattr(doc, "certificate", None)
    if cert is not None:
        approve_certificate(cert, actor=None)
        print("approved", doc.pk)
PY

echo "== generate report =="
docker compose exec -T app python manage.py shell <<'PY'
from django.contrib.auth import get_user_model
from reports.services import create_report_job, run_report_job
user = get_user_model().objects.filter(is_superuser=True).first()
job = create_report_job({}, user)
run_report_job(job.pk)
print("report_job", job.pk, job.status, job.artifact_path)
PY

echo "== download report =="
docker compose exec -T app python manage.py shell -c \
  "from reports.models import ReportJob; j=ReportJob.objects.latest('id'); print(j.artifact_path)" \
  | tail -1 | xargs -I{} docker compose exec -T app cat {} > report-smoke.xlsx
ls -la report-smoke.xlsx
echo "SMOKE OK"
