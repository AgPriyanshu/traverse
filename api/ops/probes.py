"""Real dependency probes behind ``/health``. Owned by devops engineer 1.

``api/routes/ops.py`` is not a do1 file, so the probes live here and the route
owner wires them in with a one-line call — see plans/sprint-1/HANDOFF.md.
"""

import asyncio
import os

import httpx
from neo4j import AsyncGraphDatabase
from sqlalchemy import text

from ..config import settings
from ..contracts.api import DependencyHealth, HealthOut
from ..contracts.enums import InferenceMode
from ..db.engine import engine

PROBE_TIMEOUT_S = 5.0

# Which dependencies make /health "degraded" rather than merely informative.
# The CI subset runs Postgres and RabbitMQ only, so this has to be tunable from
# the environment; settings.py is orchestrator-owned and cannot gain a key
# mid-sprint.
DEFAULT_REQUIRED = ("db", "broker", "neo4j", "object_store")


def required_dependencies() -> frozenset[str]:
    raw = os.environ.get("HEALTH_REQUIRED_DEPS")
    if raw is None:
        return frozenset(DEFAULT_REQUIRED)
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _detail(exc: Exception) -> str:
    text_ = f"{type(exc).__name__}: {exc}".replace("\n", " ")
    return text_[:200]


async def probe_db() -> DependencyHealth:
    """Postgres reachable *and* carrying pgvector.

    A Postgres without the extension accepts connections and then fails every
    embedding write, which is a much more expensive way to find out.
    """
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            )
            has_vector = result.scalar() is not None
    except Exception as exc:
        return DependencyHealth(name="db", ok=False, detail=_detail(exc))
    if not has_vector:
        return DependencyHealth(
            name="db", ok=False, detail="connected, but the vector extension is missing"
        )
    return DependencyHealth(name="db", ok=True, detail="pgvector present")


async def probe_neo4j() -> DependencyHealth:
    try:
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
            connection_acquisition_timeout=PROBE_TIMEOUT_S,
            # Retries are for real transient errors on a server we know is
            # there, not for a host that never resolves — the CI subset never
            # runs neo4j at all. Without disabling this, execute_query()
            # below retries a failed DNS lookup for the driver's default 30s
            # per /health call, starving the event loop and making the whole
            # process unresponsive.
            max_transaction_retry_time=0,
        )
        try:
            # Belt-and-braces on top of max_transaction_retry_time=0: a slow
            # first DNS/connect attempt (observed 15s+ under WSL2's resolver)
            # is not a "retry" and isn't bounded by that setting, so wall-clock
            # this probe to PROBE_TIMEOUT_S regardless of driver internals.
            records, _, _ = await asyncio.wait_for(
                driver.execute_query(
                    "RETURN 1 AS ok", database_=settings.neo4j_database
                ),
                timeout=PROBE_TIMEOUT_S,
            )
        finally:
            await driver.close()
    except Exception as exc:
        return DependencyHealth(name="neo4j", ok=False, detail=_detail(exc))
    if not records or records[0]["ok"] != 1:
        return DependencyHealth(
            name="neo4j", ok=False, detail="unexpected query result"
        )
    return DependencyHealth(name="neo4j", ok=True, detail=settings.neo4j_database)


def _broker_check() -> str:
    from kombu import Connection

    with Connection(settings.rabbitmq_url, connect_timeout=PROBE_TIMEOUT_S) as conn:
        conn.ensure_connection(max_retries=0, timeout=PROBE_TIMEOUT_S)
        return conn.as_uri()


async def probe_broker() -> DependencyHealth:
    try:
        uri = await asyncio.to_thread(_broker_check)
    except Exception as exc:
        return DependencyHealth(name="broker", ok=False, detail=_detail(exc))
    return DependencyHealth(name="broker", ok=True, detail=uri)


async def probe_object_store() -> DependencyHealth:
    scheme = "https" if settings.minio_secure else "http"
    url = f"{scheme}://{settings.minio_endpoint}/minio/health/live"
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_S) as client:
            response = await client.get(url)
        response.raise_for_status()
    except Exception as exc:
        return DependencyHealth(name="object_store", ok=False, detail=_detail(exc))
    return DependencyHealth(name="object_store", ok=True, detail=settings.minio_bucket)


async def probe_llm() -> DependencyHealth:
    """Never gating: the default profile ships without a GPU (PRD NFR-deploy)."""
    if settings.inference_mode is not InferenceMode.LOCAL:
        return DependencyHealth(
            name="llm",
            ok=True,
            detail=f"inference_mode={settings.inference_mode.value}",
        )
    url = settings.vllm_base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_S) as client:
            response = await client.get(url)
        response.raise_for_status()
    except Exception as exc:
        return DependencyHealth(name="llm", ok=False, detail=_detail(exc))
    return DependencyHealth(name="llm", ok=True, detail=settings.llm_model)


PROBES = (probe_db, probe_broker, probe_neo4j, probe_object_store, probe_llm)


async def gather_health() -> HealthOut:
    """Run every probe concurrently and fold them into one ``HealthOut``."""
    results = await asyncio.gather(*(probe() for probe in PROBES))
    dependencies = [
        DependencyHealth(name="api", ok=True, detail=f"env={settings.env}"),
        *results,
    ]
    required = required_dependencies()
    degraded = any(d.name in required and not d.ok for d in dependencies)
    return HealthOut(status="degraded" if degraded else "ok", dependencies=dependencies)
