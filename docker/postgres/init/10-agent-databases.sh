#!/usr/bin/env bash
# Runs only on a cold data volume. scripts/bootstrap_databases.sh does the same
# work against an already-initialised cluster, and both are idempotent.
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
