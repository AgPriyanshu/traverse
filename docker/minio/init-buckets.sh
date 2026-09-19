#!/bin/sh
# One bucket per agent (BRANCH.md §4). Idempotent: `mc mb --ignore-existing`.
set -eu

ENDPOINT="${MINIO_INTERNAL_ENDPOINT:-http://minio:9000}"
ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"
BUCKETS="${MINIO_BUCKETS:-traverse-be1 traverse-be2 traverse-int}"

for attempt in $(seq 1 60); do
  if mc alias set local "$ENDPOINT" "$ACCESS_KEY" "$SECRET_KEY" >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    echo "minio-init: $ENDPOINT never became reachable" >&2
    exit 1
  fi
  sleep 2
done

for bucket in $BUCKETS; do
  mc mb --ignore-existing "local/${bucket}"
  echo "minio-init: bucket ${bucket} ready"
  # `mc ilm import` replaces the whole lifecycle config in one call, unlike
  # `mc ilm rule add`, which appends a new randomly-ID'd rule every run and
  # is not safe to re-run on every `docker compose up`. Page renders are a
  # cache the pipeline regenerates on demand, not a database (S2.15).
  mc ilm import "local/${bucket}" <<'ILM_JSON'
{
  "Rules": [
    {
      "ID": "traverse-page-render-cache-expiry",
      "Status": "Enabled",
      "Filter": {"Prefix": "books/*/pages/*"},
      "Expiration": {"Days": 30}
    }
  ]
}
ILM_JSON
  echo "minio-init: bucket ${bucket} lifecycle set (books/*/pages/* expires after 30d)"
done
