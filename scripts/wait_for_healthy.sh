#!/usr/bin/env bash
# Block until every named compose service is healthy, or — for the one-shot
# services — has exited 0.
#
#   scripts/wait_for_healthy.sh [--timeout 300] [--] service [service...]
#
# With no service names, waits on every service the project currently defines.
# Set COMPOSE to add -f overlays: COMPOSE="docker compose -f a.yml -f b.yml"
set -uo pipefail

TIMEOUT="${WAIT_TIMEOUT:-300}"
COMPOSE=${COMPOSE:-docker compose}

while [ $# -gt 0 ]; do
  case "$1" in
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --) shift; break ;;
    *) break ;;
  esac
done

SERVICES=("$@")
if [ ${#SERVICES[@]} -eq 0 ]; then
  mapfile -t SERVICES < <($COMPOSE ps --services)
fi

dump_diagnostics() {
  $COMPOSE ps -a >&2
  for service in "${SERVICES[@]}"; do
    echo "----- $service -----" >&2
    $COMPOSE logs --tail=60 "$service" >&2 2>/dev/null || true
  done
}

deadline=$(( $(date +%s) + TIMEOUT ))
while :; do
  # -a so one-shot services that have already exited are still reported.
  snapshot=$($COMPOSE ps -a --format '{{.Service}}\t{{.State}}\t{{.Health}}\t{{.ExitCode}}')
  pending=()
  for service in "${SERVICES[@]}"; do
    line=$(printf '%s\n' "$snapshot" | awk -F'\t' -v s="$service" '$1 == s { print; exit }')
    if [ -z "$line" ]; then pending+=("$service=absent"); continue; fi

    state=$(printf '%s' "$line" | cut -f2)
    health=$(printf '%s' "$line" | cut -f3)
    code=$(printf '%s' "$line" | cut -f4)

    case "$state" in
      running|restarting)
        case "$health" in
          healthy|"") : ;;
          unhealthy) echo "$service is unhealthy" >&2; dump_diagnostics; exit 1 ;;
          *) pending+=("$service=$health") ;;
        esac
        ;;
      exited)
        if [ "$code" != "0" ]; then
          echo "$service exited $code" >&2; dump_diagnostics; exit 1
        fi
        ;;
      *) pending+=("$service=$state") ;;
    esac
  done

  if [ ${#pending[@]} -eq 0 ]; then
    echo "ready: ${SERVICES[*]}"
    exit 0
  fi

  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "timed out after ${TIMEOUT}s waiting for: ${pending[*]}" >&2
    dump_diagnostics
    exit 1
  fi
  sleep 3
done
