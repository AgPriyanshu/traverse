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
done
