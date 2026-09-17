import asyncio
import os
import subprocess

import pytest
from neo4j.exceptions import ServiceUnavailable

from api.graph import client

RESTART_ENV = "TRAVERSE_NEO4J_RESTART_TEST"
CONTAINER_ENV = "NEO4J_CONTAINER"


async def test_driver_is_a_process_singleton():
    first = await client.get_driver()
    second = await client.get_driver()

    assert first is second


async def test_concurrent_callers_share_one_driver():
    drivers = await asyncio.gather(*(client.get_driver() for _ in range(16)))

    assert len({id(driver) for driver in drivers}) == 1


async def test_healthcheck_reports_connectivity():
    ok, detail = await client.healthcheck()

    assert ok is True
    assert detail


async def test_schema_bootstrap_is_idempotent():
    await client.apply_schema()
    await client.apply_schema()

    async with client.session() as neo:
        result = await neo.run("SHOW CONSTRAINTS YIELD name RETURN collect(name) AS n")
        names = (await result.single())["n"]
        result = await neo.run("SHOW INDEXES YIELD name RETURN collect(name) AS n")
        index_names = (await result.single())["n"]

    assert {"character_id", "book_id"} <= set(names)
    assert {
        "character_book",
        "character_name",
        "rel_predicate",
        "rel_chapter",
    } <= set(index_names)


async def test_backoff_gives_up_with_the_underlying_error():
    class NeverReady:
        async def verify_connectivity(self):
            raise ServiceUnavailable("still starting")

    original = client._CONNECT_ATTEMPTS, client._CONNECT_BACKOFF_SECONDS
    client._CONNECT_ATTEMPTS, client._CONNECT_BACKOFF_SECONDS = 3, 0.01
    try:
        with pytest.raises(ServiceUnavailable):
            await client._verify_with_backoff(NeverReady())
    finally:
        client._CONNECT_ATTEMPTS, client._CONNECT_BACKOFF_SECONDS = original


@pytest.mark.skipif(
    os.environ.get(RESTART_ENV) != "1",
    reason=f"restarts the Neo4j container; set {RESTART_ENV}=1 to run",
)
async def test_driver_survives_a_container_restart():
    """The acceptance criterion for S1.4: no API restart after a Neo4j restart."""
    container = os.environ.get(CONTAINER_ENV, "neo4j")
    driver = await client.get_driver()

    subprocess.run(["docker", "restart", container], check=True, capture_output=True)

    result = await client.execute("RETURN 1 AS ok")
    assert result.records[0]["ok"] == 1

    assert await client.get_driver() is driver
