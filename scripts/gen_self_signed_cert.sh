#!/usr/bin/env bash
# S9.4: a local, throwaway TLS cert so `make up-prod` can verify the edge
# proxy's HTTPS path without a real domain or a CA. Never used for anything
# public — plans/sprint-9/HANDOFF.md documents swapping this for a real
# Let's Encrypt/ACME certificate before any public host serves traffic.
set -euo pipefail

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/docker/nginx/certs"
mkdir -p "$CERT_DIR"

if [[ -f "$CERT_DIR/edge.crt" && -f "$CERT_DIR/edge.key" ]]; then
    echo "gen_self_signed_cert: $CERT_DIR already has a cert pair, leaving it alone"
    exit 0
fi

openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$CERT_DIR/edge.key" \
    -out "$CERT_DIR/edge.crt" \
    -days 30 \
    -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

echo "gen_self_signed_cert: wrote $CERT_DIR/edge.{crt,key} (self-signed, 30 days, local verification only)"
