#!/usr/bin/env bash
# deploy.sh — one-shot deployment of the certificate-recognition stack.
#
# Usage (from the repo root, after cloning):
#   ./deploy.sh
#
# Optional env overrides:
#   DEPLOY_HOST=192.168.1.50     public IP/hostname (default: auto-detect)
#   DEPLOY_ADMIN_PASSWORD=...  Django + Paperless admin password.
#                               Default: randomly generated, written to .env
#                               and shown once in the final summary.
#                               Charset: letters, digits and . _ @ % + = : , ~ -
#                               only (no $, !, spaces, quotes — compose .env
#                               interpolation would corrupt them). Min 8 chars.
#                               Test-only weak password (e.g. admin) requires
#                               DEPLOY_ADMIN_PASSWORD=admin plus
#                               BOOTSTRAP_ALLOW_WEAK_PASSWORD=1 in .env.
#   SKIP_MODEL=1                 skip the Ollama model pull
#   SKIP_SMOKE=1                 skip the end-to-end smoke test
#   FORCE_ENV=1                  regenerate .env even if it exists
#   DEPLOY_GPU=auto|gpu|cpu      GPU para Ollama (default: auto — detecta NVIDIA)
set -euo pipefail

cd "$(dirname "$0")"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWARN:\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

env_val() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2-; }

# Deriva N8N_SECURE_COOKIE del esquema público configurado (N8N_PROTOCOL).
n8n_secure_cookie_value() {
  local protocol
  protocol=$(env_val N8N_PROTOCOL); protocol=${protocol:-http}
  case "$protocol" in
    https) echo true ;;
    http)  echo false ;;
    *) die "N8N_PROTOCOL inválido en .env: $protocol (usá http o https)" ;;
  esac
}

# Pide un token nuevo a la API de Paperless y lo escribe en .env.
# Se usa tanto en el primer deploy como para recuperarse de un token
# stale (p.ej. cuando la base de Paperless se recreó y el token viejo
# ya no existe -> HTTP 401 "Invalid token").
regen_paperless_token() {
  local user pass token
  user=$(env_val PAPERLESS_ADMIN_USER); user=${user:-admin}
  pass=$(env_val PAPERLESS_ADMIN_PASSWORD)
  [ -n "$pass" ] || { warn "PAPERLESS_ADMIN_PASSWORD no está en .env"; return 1; }
  # Paperless >= 3.x exige username/password en el body JSON de /api/token/
  token=$(curl -fsS -X POST \
    "http://localhost:9090/api/token/" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$user\",\"password\":\"$pass\"}" \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])') || return 1
  [ -n "$token" ] || return 1
  sed -i "s|^APP_PAPERLESS_TOKEN=.*|APP_PAPERLESS_TOKEN=$token|" .env
}

# ---------------------------------------------------------------- preflight
command -v docker >/dev/null || die "docker no está instalado"
docker compose version >/dev/null 2>&1 || die "docker compose plugin no está instalado"
FREE_GB=$(df -BG --output=avail . | tail -1 | tr -dc '0-9')
[ "${FREE_GB:-0}" -ge 15 ] || die "Se necesitan ~15 GB libres (hay ${FREE_GB} GB)"

HOST="${DEPLOY_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
[ -n "$HOST" ] || die "No se pudo detectar la IP; definí DEPLOY_HOST"
# Sin override se genera una password fuerte: nunca se usa un default conocido.
ADMIN_PASS_GENERATED=0
if [ -n "${DEPLOY_ADMIN_PASSWORD:-}" ]; then
  # .env values are interpolated by docker compose: $, !, quotes, spaces and
  # shell metacharacters corrupt the value or break parsing. Whitelist only.
  case "$DEPLOY_ADMIN_PASSWORD" in
    *[!A-Za-z0-9._@%+=:,~-]*)
      die "DEPLOY_ADMIN_PASSWORD tiene caracteres no soportados. Usá solo letras, números y . _ @ % + = : , ~ -"
      ;;
  esac
  if [ "${BOOTSTRAP_ALLOW_WEAK_PASSWORD:-}" != "1" ] && \
     { [ ! -f .env ] || ! grep -q '^BOOTSTRAP_ALLOW_WEAK_PASSWORD=1' .env; }; then
    [ "${#DEPLOY_ADMIN_PASSWORD}" -ge 8 ] || die "DEPLOY_ADMIN_PASSWORD debe tener al menos 8 caracteres"
  fi
  ADMIN_PASS="$DEPLOY_ADMIN_PASSWORD"
else
  ADMIN_PASS="$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)"
  ADMIN_PASS_GENERATED=1
fi
log "Host detectado: $HOST"

# ------------------------------------------------------- GPU NVIDIA (opcional)
# DEPLOY_GPU=auto (default): usa GPU si hay nvidia-smi + nvidia-container-toolkit.
# DEPLOY_GPU=gpu: fuerza compose.gpu.yaml aunque la detección falle.
# DEPLOY_GPU=cpu: fuerza CPU aunque haya GPU.
# Sin GPU o sin toolkit, el stack funciona igual por CPU. Después del pull del
# modelo se verifica en runtime que Ollama realmente usa la GPU; si no, el
# servicio se recrea sin compose.gpu.yaml.
GPU_MODE="${DEPLOY_GPU:-auto}"
USE_GPU=0
if [ "$GPU_MODE" = "gpu" ] || { [ "$GPU_MODE" = "auto" ] && command -v nvidia-smi >/dev/null 2>&1 && command -v nvidia-ctk >/dev/null 2>&1; }; then
  log "GPU NVIDIA detectada — habilitando Ollama con CUDA (compose.gpu.yaml)"
  nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml >/dev/null 2>&1 \
    || warn "No se pudo generar /etc/cdi/nvidia.yaml — Ollama puede no ver la GPU"
  export COMPOSE_FILE="compose.yaml:compose.gpu.yaml"
  USE_GPU=1
elif [ "$GPU_MODE" = "cpu" ]; then
  log "DEPLOY_GPU=cpu — Ollama va a usar CPU"
elif command -v nvidia-smi >/dev/null 2>&1; then
  warn "Hay GPU NVIDIA pero falta nvidia-container-toolkit — Ollama va a usar CPU (DEPLOY_GPU=gpu para forzar)"
fi

# ---------------------------------------------------------------------- .env
if [ ! -f .env ] || [ "${FORCE_ENV:-0}" = "1" ]; then
  log "Generando .env con secrets aleatorios"
  cp .env.example .env
  set_env() { sed -i "s|^$1=.*|$1=$2|" .env; }

  set_env DJANGO_SECRET_KEY          "$(openssl rand -hex 32)"
  set_env DB_PASSWORD                "$(openssl rand -hex 24)"
  set_env PAPERLESS_SECRET_KEY       "$(openssl rand -hex 32)"
  set_env APP_INTERNAL_API_TOKEN     "$(openssl rand -hex 32)"
  set_env APP_N8N_WEBHOOK_TOKEN      "$(openssl rand -hex 32)"
  set_env N8N_ENCRYPTION_KEY         "$(openssl rand -hex 32)"
  set_env N8N_SECURE_COOKIE          "$(n8n_secure_cookie_value)"
  set_env DJANGO_SUPERUSER_USERNAME  admin
  set_env DJANGO_SUPERUSER_PASSWORD  "$ADMIN_PASS"
  set_env PAPERLESS_ADMIN_USER       admin
  set_env PAPERLESS_ADMIN_PASSWORD   "$ADMIN_PASS"
  set_env PAPERLESS_URL              "http://$HOST:9090"
  set_env APP_PAPERLESS_UI_URL       "http://$HOST:9090"
  set_env DJANGO_ALLOWED_HOSTS       "localhost,127.0.0.1,$HOST,app,watcher,n8n,paperless"
  APP_PORT=$(env_val APP_PORT); APP_PORT=${APP_PORT:-8080}
  set_env DJANGO_CSRF_TRUSTED_ORIGINS "http://$HOST:$APP_PORT,http://localhost:$APP_PORT,http://127.0.0.1:$APP_PORT"
  set_env PAPERLESS_CSRF_TRUSTED_ORIGINS "http://$HOST:9090,http://localhost:9090,http://127.0.0.1:9090"
else
  log ".env ya existe — se respeta (FORCE_ENV=1 para regenerar)"
fi

# .env contains secrets: keep it readable only by the owner.
chmod 600 .env

# Puerto publicado de la app: única fuente para health check y banner.
# Default 8080, igual que .env.example y compose.yaml.
APP_PORT=$(env_val APP_PORT); APP_PORT=${APP_PORT:-8080}

# Secure cookies de n8n siguen el esquema público (N8N_PROTOCOL). En HTTP se
# desactivan explícitamente y se avisa: para producción usar HTTPS.
N8N_COOKIE_VALUE=$(n8n_secure_cookie_value)
if [ "$N8N_COOKIE_VALUE" = "false" ]; then
  warn "n8n se sirve por HTTP — secure cookies desactivadas; usá un reverse proxy HTTPS para despliegues no locales"
fi
if ! grep -q '^N8N_SECURE_COOKIE=' .env; then
  echo "N8N_SECURE_COOKIE=$N8N_COOKIE_VALUE" >> .env
fi
mkdir -p inbox

wait_paperless_healthy() {
  local status
  for i in $(seq 1 60); do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q paperless)" 2>/dev/null || echo starting)
    [ "$status" = "healthy" ] && return 0
    sleep 5
  done
  return 1
}

# ------------------------------------------------------------------ build
# Sin esto el deploy reutiliza la imagen vieja y el código nuevo nunca llega
# a los contenedores. app y watcher comparten la misma imagen.
log "Building app image"
docker compose build app

# ------------------------------------------------------- databases + paperless
log "Levantando db + redis + paperless"
docker compose up -d db redis paperless

log "Esperando a que Paperless esté healthy"
wait_paperless_healthy || die "Paperless no llegó a healthy"

# ------------------------------------------------- paperless API token -> .env
if grep -q 'APP_PAPERLESS_TOKEN=change-me' .env; then
  log "Generando token de API de Paperless"
  regen_paperless_token || die "No se pudo generar el token de Paperless"
fi

# ------------------------------------------------------------------ bootstrap
log "Bootstrap: migraciones + seed + admin + webhook"
docker compose run --rm app python manage.py bootstrap

# -------------------------------------------------------------------- full up
log "Levantando stack completo"
docker compose up -d
log "Esperando a que todos los servicios estén healthy"
sleep 10
for i in $(seq 1 36); do
  unhealthy=$(docker compose ps --format '{{.Health}}' | grep -c '^unhealthy\|^starting' || true)
  [ "$unhealthy" = "0" ] && break
  sleep 5
done

# ------------------------------------------------------------------ ollama
if [ "${SKIP_MODEL:-0}" != "1" ]; then
  log "Descargando modelo Ollama qwen2.5:7b-instruct (~4.7 GB)"
  docker compose exec -T ollama ollama pull qwen2.5:7b-instruct
fi

# ------------------------------------- verificación runtime de la aceleración
OLLAMA_MODEL=$(env_val APP_OLLAMA_MODEL); OLLAMA_MODEL=${OLLAMA_MODEL:-qwen2.5:7b-instruct}

ollama_using_gpu() {
  # Carga el modelo con una generación mínima vía la API HTTP (sin modo
  # interactivo) y consulta el procesador que reporta `ollama ps`
  # ("100% GPU" vs "100% CPU").
  if ! docker compose exec -T ollama ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"; then
    log "Modelo $OLLAMA_MODEL no instalado — se omite la verificación de GPU"
    return 0
  fi
  docker compose exec -T app python - "$OLLAMA_MODEL" <<'PY' >/dev/null 2>&1 || true
import sys
import httpx

model = sys.argv[1]
httpx.post(
    "http://ollama:11434/api/generate",
    json={"model": model, "prompt": "ok", "stream": False,
          "options": {"num_predict": 1}},
    timeout=600.0,
)
PY
  sleep 2
  local ps_out
  ps_out=$(docker compose exec -T ollama ollama ps 2>/dev/null)
  # Si el modelo no llegó a cargar no se puede concluir: se mantiene la GPU.
  echo "$ps_out" | grep -q "$OLLAMA_MODEL" || return 0
  echo "$ps_out" | grep -qi "gpu"
}

if [ "$USE_GPU" = "1" ] && [ "${SKIP_GPU_CHECK:-0}" != "1" ]; then
  log "Verificando que Ollama usa la GPU"
  if ollama_using_gpu; then
    log "Ollama usando GPU"
  else
    warn "Ollama no está usando la GPU — recreando el servicio sin aceleración"
    COMPOSE_FILE="compose.yaml" docker compose up -d --force-recreate --no-deps ollama
    sleep 5
  fi
fi

# ---------------------------------------------------------------------- n8n
log "Importando workflows de n8n"
sleep 5
EXISTING=$(docker compose exec -T n8n n8n list:workflow 2>/dev/null | grep -c '|' || true)
if [ "$EXISTING" = "0" ]; then
  for wf in n8n/workflows/processing.json n8n/workflows/report.json; do
    docker compose cp "$wf" "n8n:/tmp/$(basename "$wf")" >/dev/null
    docker compose exec -T n8n n8n import:workflow --input="/tmp/$(basename "$wf")" 2>&1 | tail -1
  done
else
  log "n8n ya tiene workflows importados — se omite"
fi

# Los workflows quedan inactivos tras importar (y pueden estarlo de un
# deploy anterior). Activarlos siempre, uno por uno.
for wf_id in $(docker compose exec -T n8n n8n list:workflow 2>/dev/null | grep '|' | cut -d'|' -f1); do
  docker compose exec -T n8n n8n update:workflow --id="$wf_id" --active=true >/dev/null 2>&1 \
    || warn "No se pudo activar el workflow $wf_id — activalo en la UI de n8n"
done

# La activación por CLI solo marca la DB; los webhooks se registran al
# arrancar n8n. Sin el restart los endpoints siguen devolviendo 404.
log "Reiniciando n8n para registrar los webhooks"
# En Docker Desktop/WSL `compose restart` a veces se queda colgado para
# siempre; timeout + recreación forzada como fallback.
if ! timeout 120 docker compose restart n8n >/dev/null 2>&1; then
  warn "docker compose restart n8n no respondió — recreando el contenedor"
  docker rm -f "$(docker compose ps -q n8n)" >/dev/null 2>&1 || true
  docker compose up -d --no-deps n8n >/dev/null
fi
for i in $(seq 1 36); do
  status=$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q n8n)" 2>/dev/null || echo starting)
  [ "$status" = "healthy" ] && break
  sleep 5
done

# Verificar que los webhooks respondan (404 = workflow inactivo)
sleep 3
for hook in process-document report-job; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 10 -X POST \
    "http://localhost:5678/webhook/$hook" -H 'Content-Type: application/json' -d '{}')
  if [ "$code" = "404" ]; then
    warn "Webhook /webhook/$hook devuelve 404 — el workflow está inactivo"
  else
    log "Webhook /webhook/$hook responde ($code)"
  fi
done

# --------------------------------------------------------------- verificación
log "Verificación final"
curl -fsS "http://localhost:$APP_PORT/healthz" >/dev/null && echo "  Django healthz OK"
# 'up -d' puede haber recreado Paperless; esperar healthy + reintentar el
# provisioning porque la API puede tardar en aceptar tokens tras el boot.
wait_paperless_healthy || die "Paperless no llegó a healthy"
for i in 1 2 3 4; do
  out=$(docker compose exec app python manage.py provision_paperless_webhook 2>&1 | tail -1) || true
  echo "  $out"
  [[ "$out" == *"Webhook ya existe"* || "$out" == *"Webhook creado"* ]] && break
  # 401 = token stale: regenerarlo y recrear app/watcher para que tomen el nuevo .env
  if [[ "$out" == *"401"* || "$out" == *"Invalid token"* ]]; then
    log "Token de Paperless inválido — regenerando"
    if regen_paperless_token; then
      docker compose up -d app watcher >/dev/null
      sleep 10
    fi
  fi
  sleep 15
done

# Real credentials from .env for the final banner
DJANGO_USER=$(env_val DJANGO_SUPERUSER_USERNAME); DJANGO_USER=${DJANGO_USER:-admin}
PAPERLESS_USER=$(env_val PAPERLESS_ADMIN_USER); PAPERLESS_USER=${PAPERLESS_USER:-admin}

if [ "${SKIP_SMOKE:-0}" != "1" ]; then
  log "Smoke test end-to-end (puede tardar varios minutos por Ollama)"
  ./scripts/smoke.sh || warn "El smoke falló — revisá 'docker compose logs app watcher ocr n8n'"
fi

cat <<EOF

============================================================
 Deploy completo.
   Django app:     http://$HOST:$APP_PORT   ($DJANGO_USER / ver .env)
   Paperless UI:   http://$HOST:9090               ($PAPERLESS_USER / ver .env)
   n8n:            http://127.0.0.1:5678  (solo loopback — N8N_BIND_ADDR para LAN/proxy)
   Inbox folder:   ./inbox/  (copiá archivos ahí)
EOF

if [ "$ADMIN_PASS_GENERATED" = "1" ]; then
  cat <<EOF
   Password admin autogenerada (guardala, no se vuelve a mostrar):
   $ADMIN_PASS
============================================================
EOF
else
  echo "============================================================"
fi
