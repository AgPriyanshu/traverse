#!/bin/sh
# Creates *this worktree's own* test database on demand — the shared
# `traverse_test` had no per-worktree isolation and two concurrent
# `docker compose --profile test run --rm test` invocations from different
# worktrees deadlocked each other on it: one run's fixture connection sat
# idle-in-transaction holding a lock the other's teardown TRUNCATE needed
# (do1, Sprint 5 finding; see infra-topology.md). Unlike the cold-volume-only
# docker/postgres/init/ scripts, this runs every time via the `test-db-init`
# compose service, so it also covers a worktree that shows up after the
# cluster is already warm.
#
# TEST_POSTGRES_DB defaults to a name keyed by TEST_IMAGE_TAG, the same
# variable that already tags the `test` image per worktree (Makefile).
set -eu

HOST="${POSTGRES_HOST:-db}"
USER="${POSTGRES_USER:-postgres}"
DATABASE="${TEST_POSTGRES_DB:-traverse_test}"

export PGPASSWORD="${POSTGRES_PASSWORD:-postgres}"

psql -v ON_ERROR_STOP=1 -h "$HOST" -U "$USER" -d postgres -tAc \
  "SELECT 'CREATE DATABASE \"$DATABASE\"' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DATABASE')\gexec"
psql -v ON_ERROR_STOP=1 -h "$HOST" -U "$USER" -d "$DATABASE" \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "test-db-init: $DATABASE ready with pgvector"
