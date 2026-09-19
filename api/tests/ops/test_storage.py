import time
import uuid
from collections.abc import AsyncIterator
from io import BytesIO

import httpx
import pytest_asyncio

from api.ops import storage


@pytest_asyncio.fixture
async def object_prefix() -> AsyncIterator[str]:
    """A key prefix unique to this test run, cleaned up regardless of outcome."""
    prefix = f"tests/ops/{uuid.uuid4().hex}/"
    yield prefix
    await storage.delete_prefix(prefix)


async def test_put_stream_then_exists_roundtrip(object_prefix: str) -> None:
    key = f"{object_prefix}hello.txt"

    assert await storage.exists(key) is False

    await storage.put_stream(
        key, BytesIO(b"traverse storage roundtrip"), content_type="text/plain"
    )

    assert await storage.exists(key) is True


async def test_delete_prefix_removes_only_the_matching_keys(object_prefix: str) -> None:
    matching = [f"{object_prefix}a.txt", f"{object_prefix}sub/b.txt"]
    outside = f"tests/ops/outside-{uuid.uuid4().hex}.txt"

    for key in matching:
        await storage.put_stream(key, BytesIO(b"x"))
    await storage.put_stream(outside, BytesIO(b"x"))

    try:
        removed = await storage.delete_prefix(object_prefix)

        assert removed == len(matching)
        for key in matching:
            assert await storage.exists(key) is False
        assert await storage.exists(outside) is True
    finally:
        await storage.delete_prefix(outside)


async def test_delete_prefix_on_empty_prefix_is_a_noop(object_prefix: str) -> None:
    assert await storage.delete_prefix(object_prefix) == 0


async def test_presigned_get_serves_the_object_then_expires_it(
    object_prefix: str,
) -> None:
    key = f"{object_prefix}presigned.txt"
    body = b"presigned body"
    await storage.put_stream(key, BytesIO(body))

    url = await storage.presigned_get(key, expires_in=60)
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
    assert response.status_code == 200
    assert response.content == body

    # A URL signed with a 1s TTL must be rejected shortly after — the whole
    # point of presigning is that it does NOT stay valid forever (S2.15).
    expired_url = await storage.presigned_get(key, expires_in=1)
    # `X-Amz-Date` truncates to whole seconds, so a 1s TTL can still validate
    # up to ~2s later; give it enough margin to be unambiguous.
    time.sleep(3)
    async with httpx.AsyncClient() as client:
        expired_response = await client.get(expired_url)
    assert expired_response.status_code == 403
