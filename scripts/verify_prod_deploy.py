#!/usr/bin/env python3

from __future__ import annotations

import os
import ssl
import sys
import urllib.error
import urllib.request

EDGE_HTTP_PORT = os.environ.get("EDGE_HTTP_PORT", "8080")
EDGE_TLS_PORT = os.environ.get("EDGE_TLS_PORT", "8443")
HOST = "127.0.0.1"

# Self-signed local cert; never used for anything a real client would trust.
_INSECURE_CTX = ssl.create_default_context()
_INSECURE_CTX.check_hostname = False
_INSECURE_CTX.verify_mode = ssl.CERT_NONE


def _log(message: str) -> None:
    print(message, flush=True)


def check_https_health() -> bool:
    url = f"https://{HOST}:{EDGE_TLS_PORT}/health"
    try:
        with urllib.request.urlopen(url, timeout=10, context=_INSECURE_CTX) as resp:
            ok = resp.status == 200
    except (urllib.error.URLError, TimeoutError) as exc:
        _log(f"FAIL https health: {exc}")
        return False
    _log(f"{'PASS' if ok else 'FAIL'} https health: status={resp.status if ok else '?'}")
    return ok


def check_http_redirects_to_https() -> bool:
    url = f"http://{HOST}:{EDGE_HTTP_PORT}/"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            # urllib follows redirects by default; inspect the final URL.
            landed_on_https = resp.geturl().startswith("https://")
    except (urllib.error.URLError, TimeoutError) as exc:
        _log(f"FAIL http->https redirect: {exc}")
        return False
    _log(f"{'PASS' if landed_on_https else 'FAIL'} http->https redirect: landed on {resp.geturl()}")
    return landed_on_https


def check_rate_limit_trips() -> bool:
    """Hammer a request past the edge's `perip` burst and expect a 429."""
    url = f"https://{HOST}:{EDGE_TLS_PORT}/health"
    saw_429 = False
    for _ in range(60):
        try:
            urllib.request.urlopen(url, timeout=5, context=_INSECURE_CTX)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                saw_429 = True
                break
        except (urllib.error.URLError, TimeoutError):
            continue
    _log(f"{'PASS' if saw_429 else 'FAIL'} rate limiting trips under burst load")
    return saw_429


def main() -> int:
    results = [
        check_https_health(),
        check_http_redirects_to_https(),
        check_rate_limit_trips(),
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
