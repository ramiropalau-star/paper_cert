#!/usr/bin/env bash
# backup.sh — consistent backup of the whole stack's persistent state.
#
# Captures:
#   - PostgreSQL: pg_dumpall (all databases: app, paperless, n8n)
#   - Docker volumes with user/service state, as tarballs:
#       app-media, reports, paperless-data, paperless-media, n8n-data
#
# Output: ./backups/<timestamp>/  (db.sql.gz + one .tar.gz per volume)
# Retention: backups older than BACKUP_RETENTION_DAYS (default 14) are pruned.
#
# Safe to run while the stack is live. Schedule via cron, e.g. daily at 03:00:
#   0 3 * * * cd /path/to/paperless && ./scripts/backup.sh >> backups/backup.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_ROOT="${BACKUP_DIR:-$PWD/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date +%Y-%m-%d-%H%M%S)"
DEST="$BACKUP_ROOT/$STAMP"

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || die "docker no está instalado"
docker compose version >/dev/null 2>&1 || die "docker compose plugin no está instalado"

# Compose project name (default "paperless-certs" from compose.yaml `name:`).
PROJECT="$(docker compose ps -q app 2>/dev/null | head -1 \
  | xargs -r docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null || true)"
PROJECT="${PROJECT:-paperless-certs}"

# Volumes holding state worth restoring. postgres-data is intentionally
# excluded: pg_dumpall is the authoritative, consistent DB backup.
VOLUMES=(app-media reports paperless-data paperless-media n8n-data)

mkdir -p "$DEST"
log "Backup -> $DEST (project: $PROJECT)"

# --- database -------------------------------------------------------------
log "Dumping PostgreSQL (pg_dumpall)"
docker compose exec -T db pg_dumpall -U "${DB_USER:-paperless}" \
  | gzip > "$DEST/db.sql.gz"
[ -s "$DEST/db.sql.gz" ] || die "db.sql.gz vacío — el dump falló"

# --- volumes ---------------------------------------------------------------
for vol in "${VOLUMES[@]}"; do
  full="$PROJECT"_$vol
  if docker volume inspect "$full" >/dev/null 2>&1; then
    log "Archiving volume $full"
    docker run --rm -v "$full":/v:ro -v "$DEST":/backup alpine \
      tar czf "/backup/$vol.tar.gz" -C /v .
  else
    log "WARN: volumen $full no existe — se omite"
  fi
done

# --- retention ---------------------------------------------------------------
if [ -d "$BACKUP_ROOT" ]; then
  find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" \
    -exec rm -rf {} +
fi

SIZE=$(du -sh "$DEST" | cut -f1)
log "Backup completo: $DEST ($SIZE)"
log "Retención: ${RETENTION_DAYS} días en $BACKUP_ROOT"
