#!/usr/bin/env bash
# Runs only on a cold data volume. scripts/bootstrap_databases.sh does the same
# work against an already-initialised cluster, and both are idempotent.
#
# traverse_test is NOT in this list: it was a single database shared by every
# worktree's `test` compose service, with no isolation between them (do1,
# Sprint 5 finding — two concurrent test runs deadlocked on it). Each
# worktree's own traverse_test_<TEST_IMAGE_TAG> is created on demand by the
# `test-db-init` compose service instead (docker/postgres/init-test-db.sh),
# cold volume or warm cluster alike, so it does not need to be enumerated here.
set -euo pipefail

AGENT_DATABASES="${AGENT_DATABASES:-traverse_be1 traverse_be2 traverse_int}"

for database in "$POSTGRES_DB" $AGENT_DATABASES; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-SQL
	SELECT 'CREATE DATABASE $database'
	WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$database')\gexec
	SQL
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$database" \
    -c "CREATE EXTENSION IF NOT EXISTS vector;"
  echo "postgres-init: $database ready with pgvector"
done
