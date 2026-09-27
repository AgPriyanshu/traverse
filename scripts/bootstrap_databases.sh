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
# The four persistent worktree directories (BRANCH.md §3) — each gets its own
# test database/bucket, keyed the same way TEST_IMAGE_TAG already tags each
# worktree's test image, so no worktree's `--profile test` run can deadlock or
# race another's (do1, Sprint 6 fix).
WORKTREES="${WORKTREES:-be1 be2 fe1 do1}"
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

echo "==> Postgres test databases (per worktree)"
# One traverse_test_<worktree> per worktree — not one of $AGENTS' own
# traverse_<agent> databases, and no longer a single shared traverse_test
# (do1, Sprint 5 finding, fixed Sprint 6): two worktrees' `docker compose
# --profile test run --rm test` deadlocked on the one shared database, one
# run's idle-in-transaction fixture connection holding a lock the other's
# TRUNCATE teardown needed. docker-compose.yml's `test-db-init` service
# creates each worktree's own on demand; this loop just pre-warms all four so
# the first test run in a fresh worktree isn't the one paying for it.
for worktree in $WORKTREES; do
  database="traverse_test_${worktree}"
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
# One traverse-test-<worktree> per worktree, same reasoning as the Postgres
# test databases above — never a single shared traverse-test bucket, or two
# worktrees' test runs delete each other's fixtures mid-test via
# delete_prefix("books/").
buckets=""
for agent in $AGENTS; do buckets="$buckets traverse-${agent}"; done
for worktree in $WORKTREES; do buckets="$buckets traverse-test-${worktree}"; done
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
