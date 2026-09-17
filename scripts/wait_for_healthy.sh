#!/usr/bin/env bash
# Block until every named compose service is healthy (or has exited 0).
#
#   scripts/wait_for_healthy.sh [--timeout 300] [--] service [service...]
#
# With no service names, waits on every service the project currently defines.
set -euo pipefail

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

deadline=$(( $(date +%s) + TIMEOUT ))
while :; do
  pending=()
  for service in "${SERVICES[@]}"; do
    state=$($COMPOSE ps --format '{{.Service}} {{.State}} {{.Health}}' \
      | awk -v s="$service" '$1 == s { print $2" "$3; exit }')
    case "$state" in
      "running healthy"|"exited "*) : ;;
      "running ") : ;;                      # no healthcheck declared
      "exited"*) : ;;
      "") pending+=("$service:absent") ;;
      *) pending+=("$service:${state// /\/}") ;;
    esac
  done

  if [ ${#pending[@]} -eq 0 ]; then
    echo "all services healthy: ${SERVICES[*]}"
    exit 0
  fi

  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "timed out after ${TIMEOUT}s waiting for: ${pending[*]}" >&2
    $COMPOSE ps >&2
    for service in "${SERVICES[@]}"; do
      echo "----- $service -----" >&2
      $COMPOSE logs --tail=50 "$service" >&2 || true
    done
    exit 1
  fi
  sleep 3
done
