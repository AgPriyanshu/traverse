#!/usr/bin/env bash
# Fails when the committed frontend client no longer matches the API's schema.
# A stale schema.d.ts is a type-clean frontend calling routes that do not exist.
set -euo pipefail

cd "$(dirname "$0")/.."
TARGET="${OPENAPI_CLIENT:-web/src/api/schema.d.ts}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python scripts/dump_openapi.py "$WORK/openapi.json"

if [ ! -f "$TARGET" ]; then
  echo "note: $TARGET does not exist yet (fe1 lands it in S1.16); drift check skipped."
  exit 0
fi

pnpm --dir web exec openapi-typescript "$WORK/openapi.json" -o "$WORK/schema.d.ts"

if ! diff -u "$TARGET" "$WORK/schema.d.ts"; then
  echo >&2
  echo "OpenAPI drift: $TARGET is stale. Regenerate it with 'make openapi'." >&2
  exit 1
fi
echo "$TARGET matches /openapi.json"
