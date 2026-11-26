#!/usr/bin/env bash
# health.sh — one-glance health status for every Compose service.
# Exit code: 0 when no service is unhealthy, 1 otherwise.
set -uo pipefail

cd "$(dirname "$0")/.."

rows=$(docker compose ps --format '{{.Service}}|{{.Health}}|{{.Status}}' 2>/dev/null)
if [ -z "$rows" ]; then
  echo "No running services found (docker compose ps is empty)." >&2
  exit 1
fi

printf '%-12s %-10s %s\n' SERVICE HEALTH STATUS
printf '%-12s %-10s %s\n' ------- ------ ------

bad=0
while IFS='|' read -r svc health status; do
  [ -z "$svc" ] && continue
  # Services without a healthcheck report empty health — shown as '-'.
  printf '%-12s %-10s %s\n' "$svc" "${health:--}" "$status"
  [ "$health" = "unhealthy" ] && bad=1
done <<< "$rows"

exit "$bad"
