"""Container healthcheck entrypoints: ``python -m api.ops.healthcheck api|worker``.

Both checks assert behaviour rather than liveness. A process that is up but
cannot reach Postgres, or a worker with none of the frozen stages registered,
is a failure the orchestrator should restart around — not a green container.
"""

import asyncio
import os
import sys

import httpx

from ..tasks import STAGES, celery_app
from .probes import gather_health

HTTP_TIMEOUT_S = 5.0
INSPECT_TIMEOUT_S = 10.0


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


async def _check_api() -> int:
    port = os.environ.get("API_PORT", "8000")
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as client:
            response = await client.get(f"http://127.0.0.1:{port}/health")
    except Exception as exc:
        return _fail(f"api: /health unreachable: {type(exc).__name__}: {exc}")
    if response.status_code != 200:
        return _fail(f"api: /health returned {response.status_code}")

    # The route still returns the contract-freeze stub, so the probes are run
    # here directly. Once the route calls gather_health() the two agree and
    # this stays a correct, slightly redundant, second opinion.
    health = await gather_health()
    if health.status != "ok":
        broken = ", ".join(
            f"{d.name}={d.detail}" for d in health.dependencies if not d.ok
        )
        return _fail(f"api: degraded: {broken}")
    return 0


def _check_worker() -> int:
    inspect = celery_app.control.inspect(timeout=INSPECT_TIMEOUT_S)

    pong = inspect.ping()
    if not pong:
        return _fail("worker: no reply to `celery inspect ping`")

    require_stages = os.environ.get("CELERY_REQUIRE_STAGES", "1") != "0"
    registered = inspect.registered() or {}
    known = {name.split(" ")[0] for names in registered.values() for name in names}
    missing = sorted(stage.value for stage in STAGES if stage.value not in known)
    if missing:
        message = f"worker: {len(missing)} frozen stage(s) unregistered: {missing}"
        if require_stages:
            return _fail(message)
        print(f"{message} (CELERY_REQUIRE_STAGES=0, not failing)", file=sys.stderr)
    return 0


def main(argv: list[str]) -> int:
    target = argv[1] if len(argv) > 1 else "api"
    if target == "api":
        return asyncio.run(_check_api())
    if target == "worker":
        return _check_worker()
    return _fail(f"unknown healthcheck target: {target!r} (expected api|worker)")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
