#!/bin/sh
# Creates one vhost per agent (BRANCH.md §4) through the management API, so no
# password hash has to be committed as a definitions file.
set -eu

HOST="${RABBITMQ_MANAGEMENT_HOST:-rabbitmq}"
PORT="${RABBITMQ_MANAGEMENT_PORT:-15672}"
USER="${RABBITMQ_USER:-guest}"
PASS="${RABBITMQ_PASSWORD:-guest}"
VHOSTS="${RABBITMQ_VHOSTS:-be1 be2 int}"
BASE="http://${HOST}:${PORT}/api"

for attempt in $(seq 1 60); do
  if curl -fsS -u "${USER}:${PASS}" "${BASE}/overview" >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    echo "rabbitmq-init: management API never came up at ${BASE}" >&2
    exit 1
  fi
  sleep 2
done

for vhost in $VHOSTS; do
  curl -fsS -u "${USER}:${PASS}" -X PUT "${BASE}/vhosts/%2F${vhost}" \
    -H 'content-type: application/json' -d '{}'
  curl -fsS -u "${USER}:${PASS}" -X PUT \
    "${BASE}/permissions/%2F${vhost}/${USER}" \
    -H 'content-type: application/json' \
    -d '{"configure":".*","write":".*","read":".*"}'
  echo "rabbitmq-init: vhost /${vhost} ready"
done
