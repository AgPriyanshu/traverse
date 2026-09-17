#!/usr/bin/env bash
# Gives every agent an isolated slice of the shared infra (BRANCH.md §4):
# a Postgres database with pgvector, a RabbitMQ vhost, and a MinIO bucket.
#
# Idempotent — safe to re-run, and safe to run against infra other agents are
# using: it creates, it never drops.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=${COMPOSE:-docker compose}

AGENTS="${AGENTS:-be1 be2 int}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"

echo "==> Postgres databases"
for agent in $AGENTS; do
  database="traverse_${agent}"
  $COMPOSE exec -T db psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
    -tAc "SELECT 'CREATE DATABASE $database' \
          WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='$database')\gexec"
  $COMPOSE exec -T db psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$database" \
    -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null
  echo "    $database ready with pgvector"
done

echo "==> RabbitMQ vhosts"
RABBITMQ_VHOSTS="$AGENTS" $COMPOSE run --rm --no-deps \
  -e RABBITMQ_VHOSTS="$AGENTS" rabbitmq-init

echo "==> MinIO buckets"
buckets=""
for agent in $AGENTS; do buckets="$buckets traverse-${agent}"; done
$COMPOSE run --rm --no-deps \
  -e MINIO_BUCKETS="${buckets# }" minio-init

echo
echo "Done. Put your slice in a worktree .env:"
for agent in $AGENTS; do
  echo "  POSTGRES_DB_STRING=postgresql+psycopg://postgres:postgres@localhost:\${POSTGRES_PORT:-5433}/traverse_${agent}"
  echo "  RABBITMQ_URL=pyamqp://guest:guest@localhost:\${RABBITMQ_PORT:-5672}/%2F${agent}"
  echo "  MINIO_BUCKET=traverse-${agent}"
  echo
done
